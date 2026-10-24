#!/usr/bin/env python3
"""Combine independent frequency ranks with a spelling lexicon; never reads benchmarks."""
import argparse
import hashlib
import json
import math
import re
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base', type=Path, required=True)
    p.add_argument('--ranked', type=Path, action='append', required=True)
    p.add_argument('--base-power', type=float, default=.5)
    p.add_argument('--rank-power', type=float, default=1.)
    p.add_argument('--add-ranked', action='store_true')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if not all(math.isfinite(x) and 0 <= x <= 4 for x in (a.base_power, a.rank_power)):
        p.error('powers must be finite numbers in [0,4]')
    base = {w: int(n) for w, n in (line.split() for line in a.base.read_text().splitlines())}
    evidence = {}
    for path in a.ranked:
        seen = set()
        for rank, w in enumerate(path.read_text().splitlines(), 1):
            if w in seen or not re.fullmatch("[a-z']{1,64}", w):
                continue
            seen.add(w)
            evidence[w] = evidence.get(w, 0.) + 10000. / rank / len(a.ranked)
    vocabulary = set(base)
    if a.add_ranked:
        vocabulary.update(evidence)
    weights = {
        w: max(1, min(2**32 - 1, round(base.get(w, 1)**a.base_power *
                                      (1 + evidence.get(w, 0.))**a.rank_power)))
        for w in vocabulary
    }
    a.output.mkdir(parents=True, exist_ok=True)
    output = ''.join(f'{w}\t{weights[w]}\n' for w in sorted(weights))
    (a.output / 'words.tsv').write_text(output)
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    provenance = {
        'method': 'WordNet lexical weights and independent rank-derived usage evidence; no benchmark pairs',
        'formula': 'round(base_weight**base_power * (1 + mean(10000/source_rank))**rank_power)',
        'base_sha256': digest(a.base),
        'ranked_sources': [{'name': x.name, 'sha256': digest(x)} for x in a.ranked],
        'base_power': a.base_power, 'rank_power': a.rank_power,
        'add_ranked': a.add_ranked, 'entries': len(weights),
        'added': len(vocabulary - set(base)),
        'words_sha256': digest(a.output / 'words.tsv'),
        'generator_sha256': digest(Path(__file__)),
    }
    (a.output / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    print(json.dumps(provenance))


if __name__ == '__main__':
    main()
