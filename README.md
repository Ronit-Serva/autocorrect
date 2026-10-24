# Offline algorithmic autocorrect — hackathon submission

This archive contains the C++17 source, an offline build script, the bundled
dictionary and its notices, and saved accuracy and timing reports. The selected
configuration is enabled by default: run `./autocorrect < input.txt > output.txt`
without extra flags.

## Build on Linux x86-64

Requirements: a C++17 compiler with the standard filesystem library, a POSIX
shell, and standard command-line utilities. No download, Python installation,
or external library is needed to build or run the corrector.

```sh
tar -xzf autocorrect-submission.tar.gz
cd autocorrect-submission
./build.sh
./autocorrect < input.txt > output.txt
```

`./build.sh` compiles `src/autocorrect.cpp` and creates the native executable
`autocorrect` and `data/index.bin`. It uses `c++` by default; select another
compiler with `CXX=g++ ./build.sh` or `CXX=clang++ ./build.sh`. Build on the
judge's Linux x86-64 machine to produce a Linux executable. The archive contains
source rather than a macOS prebuilt binary. Linux execution has not been
verified in this workspace.

Keep the executable and `data/` directory together. The program finds the index
relative to its executable, so it can be launched from another working directory.
`--index PATH` overrides that location.

## Public development accuracy A and running time T

The submitted default was measured on macOS 12.7.6 x86-64:

| Dataset | Correct / total | Accuracy A | Wall time T | Peak RSS |
| --- | ---: | ---: | ---: | ---: |
| Public hackathon development | 1,844 / 2,000 | **0.922 (92.20%)** | **0.592206 s** | 90.84 MiB |
| Birkbeck | 14,660 / 35,267 | 0.415686 (41.569%) | 7.895524 s | 93.50 MiB |

T includes process startup and index loading. These are individual local runs;
judge-machine timings will differ. Hackathon clean-word preservation is 95.75%
and misspelling accuracy is 91.3125%. Both datasets were used during development;
these results do not estimate unseen-test performance. The requested 99% target
was not reached.

The reports [results/public-development.json](results/public-development.json)
and [results/birkbeck-final.json](results/birkbeck-final.json) contain the exact
command, platform, executable/input/reference hashes, and sampled errors. The
measured executable SHA-256 is `6d3d282c4d39ccb6d8853300b089c2fd2a32f2fe61ffb047ad268a602ac2f541`. A native Linux build
will have a different executable hash.

## Input and output

Input is one lowercase ASCII word per line, using `a-z` and apostrophe. Output
is exactly one corrected word per line with no header or explanatory text.
CRLF and a missing final newline are supported. Known dictionary words are
preserved. Unknown tokens shorter than 3, longer than 64, or outside the
supported alphabet are preserved. Errors go to stderr with nonzero exit status.

## Approach

The system is deterministic and offline. It uses no trained model or runtime
network service. Its 161,847-entry WordNet/Webster dictionary includes POS-based
inflections, WordNet irregular forms and conservative count smoothing.

Candidates come from two indexes: two-character-deletion signatures of spelling
prefixes (first seven characters), and one-character-deletion signatures of
hand-written sound keys. Full-word checks verify retrieved candidates.

The default score combines 50% weighted spelling cost, 50% ordinary OSA edit
distance, 0.15 times sound-key distance, minus 0.08 times log dictionary weight,
plus first/last-letter penalties of 0.25/0.15 and 0.5 times letter-bigram Dice
distance. Missing-letter insertions are scaled to 75% in weighted distance.
Boundary penalties are waived for an adjacent swap at that boundary. General
spelling rules discount common sound/letter patterns; no whole-word benchmark
exceptions are included. Confidence gates can leave uncertain inputs unchanged.

The compact `ACIDX006` index stores each posting hash once with offsets into
word-ID arrays. Bounded edit distance, letter-set checks, a flat exact-word
lookup, safe score pruning, and a bounded cache reduce runtime and memory.
Normal prediction retains the best two candidates; diagnostic mode retains all.

See [ALGORITHM.md](ALGORITHM.md) for a beginner walkthrough with diagrams,
[ALGORITHM_GUIDE.md](ALGORITHM_GUIDE.md) for implementation details, and
[ITERATION_REPORT.md](ITERATION_REPORT.md) for experimental history.

## Tests and reproducible evaluation

Python 3 is needed only for the development tools and tests:

```sh
./test.sh
./autocorrect --explain speling
python3 tools/evaluate.py --input /path/to/input.txt \
  --expected /path/to/expected.txt --report results/new-evaluation.json
```

Core unit checks and all 17 Python tests passed on the submitted source on
macOS. Tests cover compact/legacy index equivalence, corrupt index rejection,
fast/exhaustive decision equivalence, input handling, morphology, and preservation
of every bundled dictionary word. `--trace` and `--explain` are diagnostics;
use the plain invocation for judge output.

Benchmark datasets are excluded from the archive. The evaluator reads references
after the prediction process; the corrector never reads expected outputs.
Historical comparisons remain in `ALGORITHM.md` and `ITERATION_REPORT.md`.
Older JSON run reports were removed during submission cleanup. The archive
contains only the two final evaluation reports; local prediction traces are
excluded.

## Optional controls and dictionary reproduction

The default equals the formerly optional combination
`--insertion-scale .75 --ngram-weight .5 --edge-transpositions`.
Use `--help` for controls. To use the previous 91.40% ranking with this dictionary:

```sh
./autocorrect --insertion-scale 1 --ngram-weight 0 --no-edge-transpositions
```

`--profile legacy` restores the original ranking costs; put overrides after a
profile. `--wide`, `--known-ratio`, `--possessives`, and `--vowel-weight` remain
optional experiments. The selected dictionary is bundled; regeneration is
optional and requires independent WordNet 3.0 and BSD Webster source files:

```sh
python3 tools/expand_lexicon.py --base data/base-words.tsv \
  --wordnet /path/to/wordnet.zip --webster /path/to/web2 \
  --smooth-existing --ratio .2 --output build/reproduced-data
```

Compare `words.tsv` with the hash in `data/provenance.json`. The selected
configuration does not use the experimental conservative-morphology dictionary
or the ranked-frequency word lists. Dictionary weights approximate lexical
support rather than modern usage frequency.

## Attribution and packaging

The dictionary uses [Princeton WordNet 3.0](https://wordnet.princeton.edu/) and
BSD Webster data. Notices are in `data/WORDNET-LICENSE.txt` and
`data/WEBSTER-NOTICE.txt`. The algorithm draws on
[SymSpell deletion indexing](https://github.com/wolfgarbe/SymSpell),
[Hunspell's suggestion mechanisms](https://github.com/hunspell/hunspell/blob/master/man/hunspell.5),
and [Aspell's phonetic retrieval approach](https://aspell.sourceforge.net/man-html/Notes-on-the-Different-Suggestion-Modes.html).
This is an independent implementation, without a claim of general benchmark
superiority over those systems.

`python3 tools/package.py` creates `dist/autocorrect-submission.tar.gz` and a
SHA-256 sidecar. The source archive includes the build script, dictionaries,
licenses, documentation and compact results. Generated binaries, indexes,
benchmark files, source caches and large experiment outputs are excluded.
