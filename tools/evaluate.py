#!/usr/bin/env python3
"""Measure exact-match accuracy and wall time, including process startup."""
import argparse
import hashlib
import json
import platform
from pathlib import Path
import re
import resource
import subprocess
import sys
import tempfile
import time


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--expected', type=Path, required=True)
    p.add_argument('--executable', type=Path, default=Path('./autocorrect'))
    p.add_argument('--program-arg', action='append', default=[], help='Repeat for each executable argument (use = for flags)')
    p.add_argument('--output', type=Path, help='Save all predictions for error analysis')
    p.add_argument('--all-errors', action='store_true', help='Include every mismatch in the JSON report')
    p.add_argument('--timeout', type=float, default=60)
    p.add_argument('--tmin', type=float, help='Fastest valid official run, if known')
    p.add_argument('--report', type=Path)
    p.add_argument('--label', default='user-supplied dataset')
    args = p.parse_args()
    inputs = args.input.read_text().splitlines()
    expected = args.expected.read_text().splitlines()
    if not inputs or len(inputs) != len(expected):
        p.error('input and expected must contain the same nonzero number of lines')
    if any(not re.fullmatch("[a-z']+", w) for w in inputs + expected):
        p.error('input and expected must contain one lowercase word per line')
    if args.timeout <= 0 or (args.tmin is not None and args.tmin <= 0):
        p.error('timeout and tmin must be positive')
    errors = []
    with args.input.open('rb') as source, tempfile.TemporaryFile() as output:
        started = time.perf_counter()
        try:
            proc = subprocess.run([str(args.executable.resolve()), *args.program_arg], stdin=source,
                                  stdout=output, stderr=subprocess.PIPE, timeout=args.timeout)
            elapsed = time.perf_counter() - started
            if proc.returncode:
                errors.append(f'exit status {proc.returncode}: {proc.stderr.decode(errors="replace").strip()}')
        except subprocess.TimeoutExpired:
            elapsed = time.perf_counter() - started
            errors.append(f'exceeded timeout ({args.timeout}s)')
        output.seek(0)
        actual = output.read().decode('utf-8', errors='replace').splitlines()
    actual = [s.strip() for s in actual]
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text('\n'.join(actual) + '\n')
    if len(actual) != len(expected):
        errors.append(f'expected {len(expected)} output lines, got {len(actual)}')
    if any(not re.fullmatch("[a-z']+", w) for w in actual):
        errors.append('output contains an invalid word')
    peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    peak_bytes = peak if sys.platform == 'darwin' else peak * 1024
    if peak_bytes > 4 * 1024**3:
        errors.append('exceeded 4 GiB peak resident memory')
    if elapsed > 60:
        errors.append('exceeded official 60 second wall-clock limit')
    matches = sum(a == b for a, b in zip(actual, expected))
    clean_indices = [i for i, (a, b) in enumerate(zip(inputs, expected)) if a == b]
    typo_indices = [i for i, (a, b) in enumerate(zip(inputs, expected)) if a != b]
    def accuracy(indices):
        return (sum(i < len(actual) and actual[i] == expected[i] for i in indices) / len(indices)) if indices else None
    report = {
        'dataset': args.label,
        'command': [str(args.executable), *args.program_arg],
        'executable_sha256': hashlib.sha256(args.executable.read_bytes()).hexdigest(),
        'input_sha256': hashlib.sha256(args.input.read_bytes()).hexdigest(),
        'expected_sha256': hashlib.sha256(args.expected.read_bytes()).hexdigest(),
        'platform': platform.platform(),
        'words': len(expected), 'matches': matches,
        'accuracy_A': matches / len(expected), 'wall_seconds_T': elapsed,
        'peak_rss_mib': peak_bytes / 1024**2,
        'correct_word_preservation': accuracy(clean_indices),
        'misspelling_accuracy': accuracy(typo_indices),
        'valid': not errors, 'errors': errors,
        'points': None,
        'mismatches_sample': [
            {'input': a, 'expected': b, 'actual': actual[i] if i < len(actual) else None}
            for i, (a, b) in enumerate(zip(inputs, expected))
            if i >= len(actual) or actual[i] != b
        ][:None if args.all_errors else 20]
    }
    if errors:
        report['points'] = 0
    elif args.tmin is not None:
        if args.tmin > elapsed:
            p.error('tmin exceeds measured T; it must be the fastest valid time')
        report['points'] = 100 * report['accuracy_A'] + 20 * args.tmin / elapsed
    rendered = json.dumps(report, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered)
    print(rendered, end='')
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
