#!/usr/bin/env python3
"""Convert Birkbeck's `$reference` + following misspellings into aligned files.

The autocorrect benchmark accepts only one lowercase ASCII word (letters and
apostrophes) per line. Multiword and punctuated Birkbeck entries are counted and
skipped instead of being silently rewritten into different words.
"""
import argparse
import collections
import json
from pathlib import Path
import re

WORD = re.compile(r"[a-z']+\Z")


def convert(source: Path, inputs: Path, expected: Path):
    if source.resolve() in (inputs.resolve(), expected.resolve()):
        raise ValueError('source must be separate from the generated input and expected files')
    lines = source.read_text(encoding='utf-8').splitlines()
    pairs = []
    stats = collections.Counter()
    target = None

    def flush():
        nonlocal target
        if target is None:
            return
        stats['reference_groups'] += 1
        if not WORD.fullmatch(target):
            stats['skipped_groups_invalid_reference'] += 1
            stats['skipped_variants_invalid_reference'] += len(variants)
            target = None
            return
        for raw in variants:
            word = raw.lower()
            if not WORD.fullmatch(word):
                stats['skipped_variants_invalid_word'] += 1
                continue
            pairs.append((word, target))
        target = None

    variants = []
    for number, raw in enumerate(lines, 1):
        if raw.startswith('$'):
            flush()
            target = raw[1:].lower()
            variants = []
        elif target is None:
            raise ValueError(f'line {number} occurs before the first $reference marker')
        else:
            variants.append(raw)
    flush()
    if not stats['reference_groups']:
        raise ValueError('no $reference groups found')

    inputs.parent.mkdir(parents=True, exist_ok=True)
    expected.parent.mkdir(parents=True, exist_ok=True)
    inputs.write_text(''.join(word + '\n' for word, _ in pairs), encoding='utf-8')
    expected.write_text(''.join(target + '\n' for _, target in pairs), encoding='utf-8')
    stats['source_lines'] = len(lines)
    stats['usable_pairs'] = len(pairs)
    # Count identity pairs after case normalization; they represent correctly
    # spelled variants in the source corpus and belong in a fair evaluation.
    stats['identity_pairs_after_lowercasing'] = sum(word == target for word, target in pairs)
    stats['skipped_total_variants'] = (stats['skipped_variants_invalid_reference'] +
                                       stats['skipped_variants_invalid_word'])
    report = {
        'source': str(source),
        'input': str(inputs),
        'expected': str(expected),
        'reference_groups': stats['reference_groups'],
        'source_lines': stats['source_lines'],
        'usable_pairs': stats['usable_pairs'],
        'skipped_groups_invalid_reference': stats['skipped_groups_invalid_reference'],
        'skipped_variants_invalid_reference': stats['skipped_variants_invalid_reference'],
        'skipped_variants_invalid_word': stats['skipped_variants_invalid_word'],
        'skipped_total_variants': stats['skipped_total_variants'],
        'identity_pairs_after_lowercasing': stats['identity_pairs_after_lowercasing'],
        'normalization': 'lowercase; entries containing characters other than ASCII letters and apostrophes are omitted; source preserved unchanged',
        'note': 'Repeated misspellings attached to different references are retained as separate rows. Context-free predictions can only match one target for a repeated input.'
    }
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True, help='Unmodified Birkbeck source file')
    p.add_argument('--input', type=Path, default=Path('my_dataset/input.txt'))
    p.add_argument('--expected', type=Path, default=Path('my_dataset/expected.txt'))
    p.add_argument('--report', type=Path, default=Path('my_dataset/conversion.json'))
    args = p.parse_args()
    try:
        report = convert(args.source, args.input, args.expected)
    except (OSError, UnicodeError, ValueError) as e:
        p.error(str(e))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
