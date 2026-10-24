#!/usr/bin/env python3
"""Generate POS-based inflections using independent WordNet data, never error pairs."""
import argparse, hashlib, json, math, re, zipfile
from pathlib import Path

VALID = re.compile(r"[a-z]+(?:'[a-z]+)*\Z")
VOWELS = set('aeiou')

def plural(w, noun=True):
    if noun and w.endswith('man') and not w.endswith(('human','shaman','talisman','roman','german','ottoman','norman','caiman')): return w[:-3]+'men'
    if w.endswith('y') and len(w)>1 and w[-2] not in VOWELS: return w[:-1]+'ies'
    if w.endswith(('s','x','z','ch','sh')): return w+'es'
    return w+'s'

def verb_forms(w):
    forms = {plural(w, noun=False)}
    if w.endswith('e'):
        forms.add(w+'d')
        forms.add((w if w.endswith(('ee','ye','oe')) else w[:-1])+'ing')
        if w.endswith('ie'): forms.add(w[:-2]+'ying')
    elif w.endswith('y') and len(w)>1 and w[-2] not in VOWELS:
        forms.update({w[:-1]+'ied', w+'ing'})
    else:
        forms.update({w+'ed',w+'ing'})
        # Stress cannot be inferred from spelling. Retain both regular candidates
        # for CVC stems; dictionary evidence supplies their eventual ranking.
        if len(w)>=3 and w[-1] not in VOWELS|set('wxy') and w[-2] in VOWELS and w[-3] not in VOWELS:
            forms.update({w+w[-1]+'ed', w+w[-1]+'ing'})
        if w.endswith('c'): forms.update({w+'ked',w+'king'})
    return forms

def expand(base, archive, ratio=.5, smooth=False, conservative=False):
    weights=dict(base); parents={}
    with zipfile.ZipFile(archive) as z:
        for pos in ['noun','verb','adj']:
            exceptions={}
            for line in z.read('wordnet/'+pos+'.exc').decode().splitlines():
                form,*roots=line.split()
                for root in roots: exceptions.setdefault(root,set()).add(form)
            lines=z.read('wordnet/index.'+pos).decode().splitlines()
            lemmas={line.split()[0] for line in lines if line and not line[0].isspace()}
            already_inflected=set()
            proper_only=set()
            if conservative:
                already_inflected.update(f for root,forms in exceptions.items() for f in forms if f != root)
                if pos=='noun':
                    already_inflected.update(plural(root) for root in lemmas if VALID.fullmatch(root))
                    # WordNet data preserves capitalization; its index does not.
                    # Keep proper nouns in vocabulary, but do not invent plurals.
                    if 'wordnet/data.noun' in z.namelist():
                        common=set(); proper=set()
                        for row in z.read('wordnet/data.noun').decode().splitlines():
                            if not row or row[0].isspace(): continue
                            fields=row.split(' | ',1)[0].split()
                            for i in range(int(fields[3],16)):
                                spelling=fields[4+2*i]
                                (proper if any(c.isupper() for c in spelling) else common).add(spelling.lower())
                        proper_only=proper-common
                elif pos=='adj':
                    for root in lemmas:
                        if root.endswith('y'): already_inflected.update({root[:-1]+'ier',root[:-1]+'iest'})
                        elif root.endswith('e'): already_inflected.update({root+'r',root+'st'})
                        else: already_inflected.update({root+'er',root+'est'})
            for line in lines:
                if not line or line[0].isspace(): continue
                w=line.split()[0]
                if w not in base or not VALID.fullmatch(w) or len(w)<3: continue
                forms=set(exceptions.get(w,()))
                if pos=='noun':
                    if (not conservative or (w not in already_inflected and w not in proper_only)) and (w not in exceptions or any(f.endswith(('ae','i')) for f in forms)): forms.add(plural(w))
                elif pos=='verb':
                    regular=verb_forms(w)
                    irregular=exceptions.get(w,set())
                    for suffix in ('ing','ed'):
                        category={f for f in irregular if (f.endswith('ing') if suffix=='ing' else not f.endswith('ing'))}
                        if category: regular={f for f in regular if not f.endswith(suffix)}
                    # WordNet's exception table supplies stress-dependent doubling.
                    if len(w)>=3:
                        doubled={w+w[-1]+'ed',w+w[-1]+'ing'}
                        regular-=doubled-irregular
                    if w.endswith('c'): regular-={w+'ed',w+'ing'}
                    forms.update(regular)
                elif pos=='adj' and not exceptions.get(w) and (not conservative or w not in already_inflected) and len(w)<=7 and len(re.findall('[aeiouy]+',w))<=2 and not w.endswith(('ous','ful','ing','ed','ic','al')):
                    if w.endswith('y'): forms.update({w[:-1]+'ier',w[:-1]+'iest'})
                    elif w.endswith('e'): forms.update({w+'r',w+'st'})
                    else: forms.update({w+'er',w+'est'})
                for form in forms:
                    if len(form)>64 or not VALID.fullmatch(form): continue
                    if form not in base or smooth:
                        weights[form]=max(weights.get(form,1),max(1,round(base[w]*ratio)))
                        parents.setdefault(form,[]).append(w)
    return weights,parents

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base',type=Path,default=Path('data/base-words.tsv'))
    p.add_argument('--wordnet',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--ratio',type=float,default=.5)
    p.add_argument('--derived-prefixes',action='store_true')
    p.add_argument('--extra-words',type=Path,action='append',default=[])
    p.add_argument('--observed-webster',action='store_true')
    p.add_argument('--smooth-existing',action='store_true')
    p.add_argument('--conservative-morphology',action='store_true')
    p.add_argument('--blend-ranks',action='store_true')
    p.add_argument('--add-ranked',action='store_true')
    p.add_argument('--webster',type=Path)
    p.add_argument('--ranked-words',type=Path,help='Independent descending frequency word list')
    a=p.parse_args()
    if not math.isfinite(a.ratio) or not 0 < a.ratio <= 1:
        p.error('--ratio must be in (0,1]')
    if (a.blend_ranks or a.add_ranked) and not a.ranked_words:
        p.error('--blend-ranks and --add-ranked require --ranked-words')
    if (a.observed_webster or a.derived_prefixes) and not a.webster:
        p.error('Webster options require --webster')
    base={w:int(n) for w,n in (line.split() for line in a.base.read_text().splitlines())}
    weights,parents=expand(base,a.wordnet,a.ratio,a.smooth_existing,a.conservative_morphology)
    for path in a.extra_words:
        for w in path.read_text().splitlines():
            w=w.lower()
            if VALID.fullmatch(w) and len(w)<=64: weights.setdefault(w,1)
    if a.webster:
        web={w.strip().lower() for w in a.webster.read_text().splitlines()}
        if a.derived_prefixes:
            for w,n in list(weights.items()):
                for prefix in ['re','un','sub','non','pre','mis','dis']:
                    f=prefix+w
                    if f not in web or len(f)>60: continue
                    for derived in {f,plural(f),*verb_forms(f)}:
                        if VALID.fullmatch(derived): weights.setdefault(derived,max(1,round(n*.1)))
        if a.observed_webster:
            with zipfile.ZipFile(a.wordnet) as z:
                for pos in ['noun','verb','adj','adv']:
                    for line in z.read('wordnet/data.'+pos).decode().splitlines():
                        if ' | ' not in line: continue
                        for w in re.findall(r"[a-z]+(?:'[a-z]+)*",line.split(' | ',1)[1].lower()):
                            if w in web and len(w)<=64: weights.setdefault(w,1)
        for w in list(weights):
            forms={w+'ly':w, w[:-2]+'ly':w} if w.endswith('le') else {w+'ly':w}
            if w.endswith('y'): forms[w[:-1]+'ily']=w
            if w.endswith('able'): forms[w[:-4]+'ability']=w
            for f in forms:
                if f in web and f not in weights: weights[f]=max(1,round(weights[w]*.25))
    if a.ranked_words:
        # Approximate Zipf counts from independently observed word ranks.
        # Add only already validated vocabulary: ranking is not a spell lexicon.
        ranks={w:i+1 for i,w in enumerate(a.ranked_words.read_text().splitlines())}
        if a.add_ranked:
            for w in ranks:
                if VALID.fullmatch(w) and 2<len(w)<=64: weights.setdefault(w,1)
        rank_weight=lambda w:max(1,round(1000000/ranks[w])) if w in ranks else 1
        weights={w:max(1,round((n*rank_weight(w))**.5)) if a.blend_ranks else rank_weight(w) for w,n in weights.items()}
    a.output.mkdir(parents=True,exist_ok=True)
    output=''.join(f'{w}\t{weights[w]}\n' for w in sorted(weights))
    (a.output/'words.tsv').write_text(output)
    report={'base_sha256':hashlib.sha256(a.base.read_bytes()).hexdigest(),'wordnet_sha256':hashlib.sha256(a.wordnet.read_bytes()).hexdigest(),'entries':len(weights),'added':len(weights)-len(base),'ratio':a.ratio,'smooth_existing':a.smooth_existing,'conservative_morphology':a.conservative_morphology,'derived_prefixes':a.derived_prefixes,'observed_webster':a.observed_webster,'blend_ranks':a.blend_ranks,'add_ranked':a.add_ranked,'webster_sha256':hashlib.sha256(a.webster.read_bytes()).hexdigest() if a.webster else None,'extra_word_sources':[{'name':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in a.extra_words],'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'ranked_words_sha256':hashlib.sha256(a.ranked_words.read_bytes()).hexdigest() if a.ranked_words else None,'words_sha256':hashlib.sha256(output.encode()).hexdigest(),'method':'WordNet POS rules and exceptions; no benchmark answers used'}
    (a.output/'provenance.json').write_text(json.dumps(report,indent=2)+'\n')
    (a.output/'inflection-parents.json').write_text(json.dumps(parents,sort_keys=True)+'\n')
    print(json.dumps(report))
if __name__=='__main__': main()
