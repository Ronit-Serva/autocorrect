#!/usr/bin/env python3
"""Create a reproducible source submission; never include the host executable."""
import gzip
import hashlib
import io
from pathlib import Path
import tarfile


def main():
    root = Path(__file__).resolve().parents[1]
    files = [root / name for name in ('README.md', 'build.sh', 'test.sh')]
    for directory in ('src', 'tests', 'tools', 'results'):
        files.extend(p for p in (root / directory).rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc')
    files.extend(root / 'data' / name for name in
                 ('words.tsv', 'provenance.json', 'WORDNET-LICENSE.txt', 'WEBSTER-NOTICE.txt'))
    target = root / 'dist/autocorrect-submission.tar.gz'
    target.parent.mkdir(exist_ok=True)
    with target.open('wb') as raw, gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode='w', format=tarfile.PAX_FORMAT) as tar:
            for path in sorted(files):
                data = path.read_bytes()
                info = tarfile.TarInfo('autocorrect-submission/' + path.relative_to(root).as_posix())
                info.size = len(data)
                info.mode = 0o755 if path.name in ('build.sh', 'test.sh') else 0o644
                info.mtime = 0
                tar.addfile(info, io.BytesIO(data))
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix(target.suffix + '.sha256').write_text(f'{digest}  {target.name}\n')
    print(f'{target}\n{target.stat().st_size:,} bytes\nSHA-256: {digest}')
    if not (root / 'results/public-development.json').exists():
        print('Public development report is absent; record it and repackage before submission.')


if __name__ == '__main__':
    main()
