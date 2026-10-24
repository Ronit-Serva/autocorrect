#!/usr/bin/env python3
"""Audit full predictions against reference answers without modifying the corrector."""
import argparse,collections,hashlib,json,subprocess
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--expected',type=Path,required=True)
    p.add_argument('--lexicon',type=Path,default=Path('data/words.tsv'))
    p.add_argument('--executable',type=Path,default=Path('autocorrect'))
    p.add_argument('--program-arg',action='append',default=[])
    p.add_argument('--report',type=Path,required=True)
    a=p.parse_args()
    xs=a.input.read_text().splitlines();ys=a.expected.read_text().splitlines()
    if len(xs)!=len(ys) or not xs: p.error('aligned nonempty files required')
    weights={w:int(n) for w,n in (l.split() for l in a.lexicon.read_text().splitlines())}
    cmd=[str(a.executable.resolve()),*a.program_arg]
    proc=subprocess.run(cmd,input='\n'.join(xs)+'\n',text=True,capture_output=True,check=True,timeout=60)
    actual=proc.stdout.splitlines()
    if len(actual)!=len(xs): p.error('prediction count does not match inputs')
    wrong=[i for i,(y,out) in enumerate(zip(ys,actual)) if y!=out]
    trace=subprocess.run(cmd+['--trace'],input='\n'.join(dict.fromkeys(xs[i] for i in wrong))+'\n',text=True,capture_output=True,check=True,timeout=60)
    details={};current=None
    for line in trace.stdout.splitlines():
        fields=line.split('\t')
        if not line.startswith('\t'):
            current=fields[0];details[current]={'prediction':fields[1],'reason':fields[2],'candidates':[]}
        else:
            details[current]['candidates'].append(dict(word=fields[1],edits=int(fields[2]),sound_edits=int(fields[3]),weighted_cost=float(fields[4]),weight=int(fields[5]),score=float(fields[6])))
    errors=[];counts=collections.Counter();groups=collections.defaultdict(collections.Counter)
    for x,y in zip(xs,ys):groups[x][y]+=1
    for i in wrong:
        x,y=xs[i],ys[i];d=details[x];c=d['candidates'];target=next((t for t in c if t['word']==y),None)
        if y not in weights: reason='missing_vocabulary'
        elif x in weights and not c: reason='known_word_preserved'
        elif not target: reason='not_retrieved_or_filtered'
        elif actual[i]==x: reason='abstention'
        else:reason='ranking'
        counts[reason]+=1
        errors.append({'line':i+1,'input':x,'expected':y,'actual':actual[i],'category':reason,'decision':d['reason'],'target_rank':1+c.index(target) if target else None,'target_candidate':target,'top_candidates':c[:5]})
    report={'command':cmd,'words':len(xs),'matches':len(xs)-len(wrong),'accuracy':1-len(wrong)/len(xs),'target_coverage':sum(y in weights for y in ys)/len(ys),'identity_pairs':sum(x==y for x,y in zip(xs,ys)),'deterministic_input_only_ceiling':sum(max(c.values()) for c in groups.values())/len(xs),'conflicting_inputs':{x:dict(c) for x,c in groups.items() if len(c)>1},'error_categories':dict(counts),'errors':errors,'executable_sha256':hashlib.sha256(a.executable.read_bytes()).hexdigest(),'lexicon_sha256':hashlib.sha256(a.lexicon.read_bytes()).hexdigest()}
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['errors','conflicting_inputs']},indent=2))
if __name__=='__main__':main()
