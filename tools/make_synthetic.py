#!/usr/bin/env python3
"""Generate reproducible diagnostics, NOT an estimate of hidden-set accuracy."""
import argparse
import collections
import json
from pathlib import Path
import random


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--lexicon', type=Path, default=Path('data/words.tsv'))
    p.add_argument('--output', type=Path, default=Path('build/synthetic'))
    p.add_argument('--size', type=int, default=10000)
    p.add_argument('--seed', type=int, default=20261025)
    args = p.parse_args()
    rng = random.Random(args.seed)
    entries = [(w, int(c)) for w, c in (line.split() for line in args.lexicon.read_text().splitlines())]
    known = {w for w, _ in entries}
    pool = [w for w, _ in sorted(entries, key=lambda x: (-x[1], x[0])) if 4 <= len(w) <= 16 and "'" not in w][:30000]
    if not 1 <= args.size <= len(pool):
        p.error(f'size must be in 1..{len(pool)}')
    targets = rng.sample(pool, args.size)
    categories = ['correct'] * 3 + ['delete', 'insert', 'replace', 'transpose', 'double', 'sound', 'two_edits']
    sound_patterns = [('ph', 'f'), ('ck', 'k'), ('tion', 'shun'), ('ee', 'i'), ('oo', 'u'), ('ight', 'ite'), ('c', 'k')]
    def mutate(word, kind):
        i = rng.randrange(len(word))
        if kind == 'delete': return word[:i] + word[i + 1:]
        if kind == 'insert': return word[:i] + rng.choice('abcdefghijklmnopqrstuvwxyz') + word[i:]
        if kind == 'replace': return word[:i] + rng.choice('abcdefghijklmnopqrstuvwxyz') + word[i + 1:]
        if kind == 'transpose':
            i = rng.randrange(len(word) - 1)
            return word[:i] + word[i + 1] + word[i] + word[i + 2:]
        if kind == 'double': return word[:i] + word[i] + word[i:]
        if kind == 'two_edits': return mutate(mutate(word, 'delete'), 'replace')
        if kind == 'sound':
            patterns = [(a, b) for a, b in sound_patterns if a in word]
            if patterns:
                a, b = rng.choice(patterns)
                return word.replace(a, b, 1)
        return word
    rows = []
    counts = collections.Counter()
    for i, target in enumerate(targets):
        kind = categories[i % len(categories)]
        typed = target
        if kind != 'correct':
            for _ in range(100):
                typed = mutate(target, kind)
                # Exclude accidental real-word errors: the task has no context.
                if typed != target and typed not in known:
                    break
            else:
                kind = 'correct'
                typed = target
        counts[kind] += 1
        rows.append((typed, target, kind))
    rng.shuffle(rows)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'input.txt').write_text(''.join(w + '\n' for w, _, _ in rows))
    (args.output / 'expected.txt').write_text(''.join(w + '\n' for _, w, _ in rows))
    (args.output / 'cases.tsv').write_text(''.join('\t'.join(row) + '\n' for row in rows))
    meta = {'seed': args.seed, 'words': len(rows), 'categories': dict(counts),
            'limitation': 'Targets come from the bundled dictionary. Sound mutations overlap generic correction rules. This checks implementation behavior, not unseen vocabulary or real misspelling accuracy.'}
    (args.output / 'metadata.json').write_text(json.dumps(meta, indent=2) + '\n')
    print(json.dumps(meta, indent=2))


if __name__ == '__main__':
    main()
