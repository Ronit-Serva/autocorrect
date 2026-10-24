# Offline algorithmic autocorrect

A C++17 single-word English corrector using dictionary morphology, symmetric
deletion retrieval, hand-written phonetic encoding, and weighted edit ranking.
It uses no ML model or network service. Python is needed only for development.

The default improved from **72.60% to 91.40%** on the supplied 2,000-row hackathon
set and from **39.694% to 40.865%** on the 35,267-row Birkbeck set. The requested
99% hackathon accuracy has not been achieved. Both datasets were used repeatedly
for development, so these scores do not estimate unseen-test performance.

See [the implementation guide](ALGORITHM_GUIDE.md) for the encoder and pipeline,
and [the iteration report](ITERATION_REPORT.md) for experiments and failure causes.

## Build and run

```sh
./build.sh
./autocorrect < input.txt > output.txt
./autocorrect --explain misspelling
./test.sh
```

The build is offline and creates the native executable and `data/index.bin`.
Use `CXX=clang++ ./build.sh` to select a compiler. Runtime reads one lowercase
ASCII token per line, accepts apostrophes, and writes exactly one output per
line. CRLF and missing final newlines are supported. Keep the executable and
`data/` together. `--index PATH` overrides the executable-relative index path.

Known dictionary words are preserved. Unknown tokens shorter than three or
longer than 64 characters, or outside the supported alphabet, are preserved.
No input or output is silently truncated. Errors go to stderr with nonzero exit.

## Selected implementation

The dictionary contains **161,847 entries**. Starting from the original 85,030
WordNet/Webster entries, the generator adds POS-based inflections, respects
WordNet exception categories, and validates additional adverb/ability forms
against Webster. Inflected counts receive a floor of 20% of their root count.

Retrieval uses two-deletion signatures of seven-character spelling prefixes
and one-deletion sound-key signatures. The default sound encoder handles
contextual sequences such as `sch`, `tion`, `sion`, `tch`, and terminal silent
consonants. Binary headers select the matching encoder automatically.

The default lower-is-better score combines 0.5 times weighted edit cost, 0.5
times ordinary OSA edit distance, 0.15 times sound-key distance, minus 0.08 times
`log(1 + count)`, plus penalties of 0.25/0.15 for first/last-character mismatch.
Transposition costs 0.35. General spelling rules cover silent letters and vowel
pairs, including positional restrictions. Confidence gates can preserve an
unknown word when the best correction is weak. A bounded cache reuses work.

All rules and weights are deterministic heuristics. No benchmark answer pairs
are included in the executable or generated vocabulary.

## Measurements

Final default runs on macOS 12.7.6 x86-64:

| Dataset | Correct | Accuracy | Wall time | Peak RSS |
| --- | ---: | ---: | ---: | ---: |
| Hackathon | 1,828 / 2,000 | 91.40% | 1.14 s | 162.16 MiB |
| Birkbeck | 14,412 / 35,267 | 40.865% | 11.70 s | 164.88 MiB |

Hackathon clean-input preservation improved from 70.25% to **95.75%**;
misspelling accuracy improved from 73.1875% to **90.3125%**. There were 415 newly
correct rows and 39 regressions relative to the original implementation.

These are single-run local timings including startup and index loading. Linux
execution has not been verified here. Build and measure on the judge's target
machine. The evaluator checks the 60-second and 4-GiB limits; it observes RSS
rather than imposing an OS memory limit.

```sh
python3 tools/evaluate.py --input hackathon_test/input.txt \
  --expected hackathon_test/expected.txt --report results/new-hackathon.json \
  --output build/hackathon-predictions.txt --all-errors
python3 tools/evaluate.py --input my_dataset/input.txt \
  --expected my_dataset/expected.txt --report results/new-birkbeck.json
python3 tools/analyze_failures.py --input hackathon_test/input.txt \
  --expected hackathon_test/expected.txt --report results/new-failure-analysis.json
```

The prediction executable only reads inputs. The separate evaluator/auditor
reads references after prediction. Detailed saved runs, outputs, and candidate
traces are in `results/iterations/`; the comparison is
[`summary.json`](results/iterations/summary.json).

## Optional experiments

`--help` lists all controls. `--profile legacy` restores the original ranking
weights, not the old vocabulary or index. Put a profile before its overrides.
`--no-spelling-costs` and `--no-extended-rules` support ablations. Numeric controls
include `--edit-weight`, `--sound-weight`, `--prior-weight`, `--boundary-weight`,
`--suffix-weight`, and `--transpose-cost`.

`--wide` broadens phonetic retrieval and filtering. Combined with
`--edit-weight .25`, it measured 91.25% on hackathon and 41.387% on Birkbeck, with
roughly 28 seconds Birkbeck runtime. This trades hackathon accuracy and time for
more Birkbeck recall. `--known-ratio 50` and `--possessives` are also retained as
experiments but are off by default after regressions. `--trace` emits decisions
and all candidates for debugging and should not be used for judge output.

The program can build legacy, contextual, or refined phonetic indexes using
`--build-index`, `--build-index-enhanced`, or `--build-index-refined`, respectively.
Each takes `words.tsv index.bin`. Rebuild after changing the encoder or lexicon.

## Reproduce the selected dictionary

The normalized dictionary is bundled, so this is optional. Given the same
WordNet 3.0 archive and BSD Webster `web2` file:

```sh
python3 tools/expand_lexicon.py --base data/base-words.tsv \
  --wordnet /path/to/wordnet.zip --webster /path/to/web2 \
  --smooth-existing --ratio .2 --output build/reproduced-data
```

Compare its `words.tsv` hash with `data/provenance.json`. The generator never
reads test inputs or expected answers. `data/base-provenance.json` records how
`tools/prepare_data.py` originally produced the base lexicon. Alternative
frequency/extra-word sources are optional experiments and are not required by
the selected default. Dictionary weights are not modern usage frequencies.

`tools/split_birkbeck.py` preserves the original source and produces aligned
files, lowercasing and skipping unsupported multiword/punctuated entries.
`my_dataset/conversion.json` records the 35,267 retained pairs and 866 exclusions.
Some Birkbeck inputs map to conflicting targets; a deterministic context-free
predictor cannot exceed 94.11% on those rows collectively.

## Packaging and attribution

```sh
python3 tools/package.py
```

This creates `dist/autocorrect-submission.tar.gz` with portable source, build
scripts, dictionaries, licenses, guides, and compact measurements. Local
binaries, generated indexes, benchmark datasets, and large iteration traces are
excluded. The full local diagnostic artifacts remain in `results/iterations/`.

The dictionary uses [Princeton WordNet 3.0](https://wordnet.princeton.edu/)
and BSD Webster data; their notices are in `data/WORDNET-LICENSE.txt` and
`data/WEBSTER-NOTICE.txt`. The implementation draws on
[SymSpell deletion indexing](https://github.com/wolfgarbe/SymSpell),
[Hunspell's suggestion mechanisms](https://github.com/hunspell/hunspell/blob/master/man/hunspell.5),
and [Aspell's phonetic retrieval approach](https://aspell.sourceforge.net/man-html/Notes-on-the-Different-Suggestion-Modes.html).
The project implements its own code and does not claim benchmark-leading
performance over those systems.
