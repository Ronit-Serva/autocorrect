#!/usr/bin/env python3
"""Build an offline lexicon from WordNet 3.0; no misspelling pairs are used."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import re
import zipfile

WORD = re.compile(r"[a-z]+(?:'[a-z]+)*\Z")
TOKEN = re.compile(r"[a-z]+(?:'[a-z]+)*")
POS = ('noun', 'verb', 'adj', 'adv')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--wordnet', type=Path, required=True, help='NLTK wordnet.zip')
    p.add_argument('--webster', type=Path, help='Optional BSD web2 word list')
    p.add_argument('--frequencies', type=Path, help='Optional trusted word COUNT file')
    p.add_argument('--output', type=Path, default=Path('data'))
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    gloss = collections.Counter()
    tags = collections.Counter()
    lexicon = set()
    components = set()
    forms = set()
    webster = set()
    if args.webster:
        webster = {s for s in args.webster.read_text().splitlines() if WORD.fullmatch(s)}
    with zipfile.ZipFile(args.wordnet) as z:
        read = lambda f: z.read('wordnet/' + f).decode('utf-8')
        (args.output / 'WORDNET-LICENSE.txt').write_text(read('LICENSE'))
        for pos in POS:
            for line in read('index.' + pos).splitlines():
                if not line or line[0].isspace():
                    continue
                word = line.split()[0]
                if WORD.fullmatch(word):
                    lexicon.add(word)
                components.update(TOKEN.findall(word.replace('_', ' ')))
            for line in read(pos + '.exc').splitlines():
                forms.update(w for w in line.split() if WORD.fullmatch(w))
            for line in read('data.' + pos).splitlines():
                if ' | ' in line:
                    gloss.update(TOKEN.findall(line.split(' | ', 1)[1].lower()))
        for line in read('cntlist.rev').splitlines():
            sense, _, count = line.split()
            lemma = sense.split('%', 1)[0]
            if WORD.fullmatch(lemma):
                tags[lemma] += int(count)

    # Webster is a validation source, not a blanket whitelist of archaic forms.
    lexicon.update(forms)
    lexicon.update(w for w, count in gloss.items()
                   if count >= 2 and (w in webster or w in components))
    lexicon.update(w for w in components if w in webster and gloss[w])
    # Closed-class words missing from WordNet's noun/verb/adjective/adverb indexes.
    lexicon.update('a an the i you he she it we they me him her us them my your his '
                   'its our their mine yours hers ours theirs this that these those '
                   'and or but if so as than because although while unless until '
                   'of to in on at by for from with without into onto upon through '
                   'is am are was were be been being do does did done have has had '
                   'can could may might must shall should will would not no yes '
                   'who whom whose which what when where why how'.split())
    # Standard contractions are dictionary entries, never correction overrides.
    lexicon.update(("i'm you're we're they're he's she's it's that's there's here's "
                    "who's what's where's how's let's i've you've we've they've "
                    "i'll you'll he'll she'll it'll we'll they'll i'd you'd he'd "
                    "she'd we'd they'd isn't aren't wasn't weren't haven't hasn't "
                    "hadn't don't doesn't didn't can't couldn't won't wouldn't "
                    "shouldn't mustn't needn't mightn't shan't").split())
    lexicon = {w for w in lexicon if WORD.fullmatch(w) and len(w) <= 64}
    weights = {w: 1 + gloss[w] + 10 * tags[w] for w in lexicon}
    if args.frequencies:
        # Do not add arbitrary web tokens to the dictionary; use trusted vocabulary.
        for line in args.frequencies.read_text().splitlines():
            word, count = line.split()
            if word in weights:
                weights[word] = max(1, min(int(count), 2**32 - 1))
    output = ''.join(f'{w}\t{weights[w]}\n' for w in sorted(lexicon))
    (args.output / 'words.tsv').write_text(output)
    provenance = {
        'entries': len(lexicon),
        'wordnet_version': '3.0',
        'wordnet_sha256': hashlib.sha256(args.wordnet.read_bytes()).hexdigest(),
        'webster_sha256': hashlib.sha256(args.webster.read_bytes()).hexdigest() if args.webster else None,
        'frequency_sha256': hashlib.sha256(args.frequencies.read_bytes()).hexdigest() if args.frequencies else None,
        'words_sha256': hashlib.sha256(output.encode()).hexdigest(),
        'weight': '1 + WordNet gloss token count + 10 * WordNet tagged sense count',
        'note': 'Weights are a hand-selected count heuristic, not general-English corpus frequencies. Optional external counts replace weights for matching entries.'
    }
    (args.output / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    print(f'Wrote {len(lexicon):,} entries to {args.output / "words.tsv"}')


if __name__ == '__main__':
    main()
