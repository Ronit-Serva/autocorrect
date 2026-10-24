# Autocorrect implementation guide for coding agents

This document describes the implementation after the accuracy iteration campaign,
with extra detail on its hand-written phonetic encoding. It is intended as a map
for controlled algorithm experiments. Read it alongside `src/autocorrect.cpp`;
the source is authoritative if this document and the code ever differ.

## Current submission result and configuration

The shipped default scores **1,844/2,000 (92.20%)** on hackathon and
**14,660/35,267 (41.569%)** on Birkbeck. The original baseline scored 72.60%
and 39.694%; the previous release scored 91.40% and 40.865%. The 99% target
has not been reached. Both datasets were used for development, so these are
not held-out accuracy estimates.

The submission enables the former `--insertion-scale .75 --ngram-weight .5
--edge-transpositions` experiment by default, with the same 161,847-word
WordNet/Webster dictionary and contextual sound encoder. Known words remain
preserved; wide search, known-word replacement, possessive handling and the
vowel-signature feature remain off.

### Submission run record

Fresh default runs on macOS 12.7.6 x86-64, including startup and index loading:

| Dataset | Matches | Accuracy | Clean preservation | Typo accuracy | Time | Peak RSS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Hackathon | 1,844 / 2,000 | 92.200% | 95.750% | 91.313% | 0.592206 s | 90.84 MiB |
| Birkbeck | 14,660 / 35,267 | 41.569% | 98.667% | 41.447% | 7.895524 s | 93.50 MiB |

Executable SHA-256: `6d3d282c4d39ccb6d8853300b089c2fd2a32f2fe61ffb047ad268a602ac2f541`.
The complete measurement metadata and input/reference hashes are in
`results/public-development.json` and `results/birkbeck-final.json`. Predictions
exactly match the selected resumed experiment. The unit suite and all 17
Python tests pass. Linux execution has not been verified in this workspace;
`./build.sh` provides an offline native build for the judge's Linux x86-64 host.
Timing values are local single-run observations.

See `ALGORITHM.md` for all 21 resumed comparisons and their tradeoffs.
Historical error categories in `ITERATION_REPORT.md` describe the previous
91.40% release. Obsolete JSON run reports and the old summary were removed
in submission cleanup; only the two final evaluation reports remain. No new
candidate-level audit was run for the submission, and no result is claimed
for the interrupted frequency-source import.

## Project at a glance

The program is a deterministic, offline, single-token English spelling
corrector. It reads one lowercase ASCII word per line and emits one word per
line. It has no sentence context, learned model, network calls, or runtime
Python dependency. The task constraint in `hackathon.pdf` also rules out ML, so
candidate retrieval and ranking use dictionary lookups and hand-coded costs.

At runtime the path is:

1. Load a prebuilt dictionary and two sorted posting indexes.
2. Preserve an exact dictionary word immediately.
3. For an unknown eligible token, retrieve candidates through spelling-delete
   keys and phonetic keys.
4. Verify candidates with ordinary and weighted string distances.
5. Rank by weighted edit cost, phonetic-key distance, and dictionary count.
6. Correct only if the best candidate passes confidence gates; otherwise keep
   the input unchanged.

## Phonetic encoding

### Purpose and scope

`phonetic()` in `src/autocorrect.cpp` maps a spelling to a broad uppercase sound
key. It is a retrieval aid and one ranking feature, not an IPA transcription,
pronunciation dictionary, or formal Soundex/Metaphone implementation. The rules
are English-oriented and deliberately approximate. The same function is used
when building the lexicon's sound index and when encoding an input, so changes
to its output require rebuilding `data/index.bin`.

### Exact behavior

The underlying `phonetic()` encoder applies these operations, in order. The
default first applies the contextual rewrites described just after this table:

1. **Initial silent-letter cleanup.** If the first two letters are `kn`, `gn`,
   `pn`, `wr`, or `ps`, drop the first letter. Examples: `knight` starts as
   `night`; `write` starts as `rite`.
2. **Scan left to right.** Apostrophes emit nothing. Vowels `a e i o u y` emit
   nothing except at position zero, where any initial vowel emits `A`.
3. **Recognize digraphs before single letters.** `ph` emits `F`; `sh` and `ch`
   emit `X`; `th` emits `T`; `wh` emits `W`. Each pair consumes both letters.
   `gh` after a vowel is silent, except word-final `gh`, which emits `F`; it
   consumes both letters.
4. **Fold single consonants into broad classes.** `c` emits `S` before `e`,
   `i`, or `y`, otherwise `K`. `g` emits `J` before those same letters,
   otherwise `K`. `q` and `k` emit `K`; `x` emits `KS`; `z` and `s` emit `S`;
   `v` and `f` emit `F`; `d` and `t` emit `T`; `b` and `p` emit `P`.
5. **Handle h contextually.** `h` emits `H` at the start, or before a vowel
   when the immediately preceding letter is not a vowel. Otherwise it emits
   nothing.
6. **Pass through remaining letters as uppercase.** This includes `m`, `n`,
   `l`, `r`, and other letters not covered above.
7. **Collapse adjacent duplicate output symbols.** The `emit()` helper appends
   each symbol only when it differs from the last emitted symbol. This also
   collapses duplicates across a multi-character emission such as `x -> KS`.
8. **Cap output length at 64 characters.** `x -> KS` can expand the key beyond
   the input length, so truncation protects the fixed-size distance matrix.

Examples useful for orientation:

| Input | Key | Reason |
| --- | --- | --- |
| `phone` | `FN` | `ph -> F`, vowels omitted, `n -> N` |
| `fone` | `FN` | `f -> F`, vowels omitted, `n -> N` |
| `knight` | `NT` | initial `k` removed, `i` omitted, `gh` silent, `t -> T` |
| `cat` | `KT` | `c -> K`, `a` omitted, `t -> T` |
| `city` | `ST` | soft `c -> S`, `i` and `y` omitted, `t -> T` |
| `school` | `SXL` | `s` emits `S`, then `ch -> X`; `oo` is omitted, then `l -> L` |

This is a useful reminder that the local rules do not model overlapping
digraphs such as `sch` as a single pronunciation unit.

### Default contextual wrapper and experimental finer encoding

`contextual_phonetic()` rewrites `sch -> sk`, `tion/sion/cian -> shn`,
`tch -> ch`, `dge/dgi/dgy -> j`, and `igh -> i` before calling `phonetic()`.
It handles terminal `mb -> m`, terminal `gn -> n`, and `chr/chl -> kr/kl`.
Thus the shipped encoder maps `school` and `skool` to `SKL`; the low-level
legacy encoder alone produces the `SXL` key shown above for `school`.

The experimental refined encoder additionally preserves initial vowel identity
and distinguishes voiced consonants (`b/p`, `d/t`, `v/f`, `z/s`, hard `g/k`).
It did not improve the selected final combination. It is retained as
`--build-index-refined` for controlled comparisons, not enabled by default.
These encoders are custom implementations, not Double Metaphone.

### Using phonetic keys for retrieval

At index-build time each dictionary entry stores its encoded key in memory and
contributes the key plus all distinct one-character deletions of that key to a
sound posting index. A posting is `(64-bit FNV-1a hash, 32-bit word ID)`.

For an unknown input, runtime does two sound-index lookups:

- Exact hash of the input key, capped at the first 256 postings.
- If the input has at least five characters, hashes for the key and each
  distinct one-character deletion, capped at 128 postings per key.

Dictionary entries were sorted by descending count weight before posting IDs
were assigned. Therefore these caps keep relatively high-count words in broad
sound buckets and can omit a rare candidate. Hash collisions can only add an
extra candidate because every retrieved word is checked later using full
strings and distances.

The sound index is separate from the spelling-delete index. Candidates from
either route are unioned and deduplicated by a generation-mark array. A phonetic
match can therefore introduce a candidate whose spelling is farther than two
edits, but it still has to pass length, edit-distance, sound-distance, weighted
cost, and confidence checks.

### Known limitations and high-value phonetic experiments

- Many English spellings are irregular or language-specific. One output key
  cannot represent all pronunciations (`ough`, `c`, `g`, `th`, and vowels are
  especially ambiguous).
- The key is not conditioned on dialect, stress, syllable boundaries, or
  morphology. Initial-vowel handling is intentionally coarse.
- `sh` and `ch` share `X`, which increases recall while also creating collisions.
- Adjacent-symbol collapse loses length distinctions. `m` and `mm` encode the
  same output sequence.
- Sound buckets have hard caps; changes in dictionary sorting/weights affect
  which postings survive the cap.
- The sound-key delete radius is one. Broadening it can increase recall and
  runtime substantially.
- Special sequences such as `sch`, `ough`, `tion`, `sion`, and silent `e` are
  better addressed with targeted tests and measured changes than a large set of
  intuition-only rules.

Promising non-ML experiments include alternative encoders (e.g. a carefully
implemented Double Metaphone variant), position-sensitive consonant classes,
separate primary/alternate keys, syllable or prefix-aware variants, and
frequency-neutral bucket sampling. Each should be compared independently and
in combinations, since a better retrieval key can change downstream candidate
competition even when its own recall improves.

## Candidate retrieval, verification, and ranking

### Text validation and early exits

Only lowercase ASCII `a-z` and apostrophe are accepted as corrector tokens. An
exact dictionary match is returned unchanged, which protects ordinary known
words but means a real-word typo such as `form` for `from` is not fixed. Unknown
tokens shorter than 3, longer than 64, or containing other characters are
preserved. Input is line-oriented; a trailing CR is removed to support CRLF.

### Spelling index

`deletes(s, 2)` returns the FNV-1a hash of the original string, each distinct
one-character deletion, and each distinct two-character deletion. During index
construction the string is first truncated to its first seven characters. At
query time the first seven input characters are used the same way. Matching
delete keys retrieve dictionary words with overlapping deletion signatures;
this is the core SymSpell-inspired candidate-generation step. Full word
distances later verify candidates, so a shared prefix signature does not itself
mean the words are close.

Hashing keeps postings compact. Sorted `(hash,id)` pairs and binary search give
deterministic lookup; the word strings are used for all final comparisons.

### Distance features

- `distance()` computes optimal-string-alignment distance: insertion,
  deletion, substitution, and adjacent transposition each cost 1. It is used as
  a hard filter and shown as `edits` by `--explain`.
- `distance(phoneA, phoneB)` applies the same metric to encoded sound keys. This
  result is displayed as `sound_edits` and contributes `0.15 * sound_edits` to
  ranking.
- `weighted_distance()` is a dynamic program over the full input and candidate.
  With the default spelling costs, apostrophe insertion/deletion costs 0.35,
  terminal `e` costs 0.45, other repeated letters cost 0.35, other vowels cost
  0.8, and other letters cost 1. Substitution costs 0 for the same letter, 0.8
  between vowels or neighboring QWERTY keys, and 1 otherwise. Adjacent
  transposition costs 0.35. Candidate-letter insertion gaps are additionally
  scaled by 0.75; deletion gaps and multi-character rules retain their costs.
  `--profile legacy` restores the original costs, disables bigram/boundary
  exemptions, and restores insertion scale 1.
- A table of bidirectional multi-character spelling/sound rules can add a
  lower-cost transition, including `ph/f`, `ck/k`, `qu/kw`, `c/k`, `c/s`,
  `g/j`, `tion/shun`, `sion/zhun`, `ture/cher`, `ee/i`, `oo/u`, `eau/o`,
  `ai/ay`, `ie/ei`, `ight/ite`, `dge/j`, and `tch/ch`. The dynamic program
  indexes candidate rules by the final characters, then checks the complete
  suffix before applying them. Extended rules cover silent initial `kn/n`,
  `wr/r`, `wh/w`, final `mb/m`, `gn/n`, final `ey/y`, and general vowel/spelling
  pairs `ght/t`, `ea/e`, `ea/ee`, `oa/o`, `ai/a`, `ou/u`, `au/o`, `ough/o`,
  `y/i`, `ch/k`, `sc/s`. Rules carry initial/final restrictions and apply
  bidirectionally. See `rules()` for every exact cost.

The final lower-is-better score is:

```text
0.5 * weighted_distance(input, candidate)
+ 0.5 * optimal_string_alignment(input, candidate)
+ 0.15 * optimal_string_alignment(sound_key(input), sound_key(candidate))
- 0.08 * log(1 + dictionary_weight(candidate))
+ 0.25 * (first characters differ)
+ 0.15 * (last characters differ)
+ 0.5 * letter_bigram_Dice_distance(input, candidate)
```

The first/last mismatch term is waived when the corresponding two boundary
letters are swapped. Bigram distance counts multiset overlap of sorted adjacent
letter pairs: `1 - 2 * common / (input_pair_count + candidate_pair_count)`.
The weighted-distance term uses insertion scale 0.75.

Ties break by larger raw dictionary weight and then alphabetical spelling.
Weights start from WordNet counts and are smoothed across inflections; they
are not representative modern corpus frequencies. The correction gate requires weighted cost at most
`min(3.2, 1.05 + 0.2 * input_length)` and either raw spelling distance at most
two or a best-versus-second score margin of at least 0.12. For inputs up to
three characters, candidates more than one raw edit away are filtered before
ranking. If no candidate qualifies, the input is preserved.

## Dictionary and generated index

`data/base-words.tsv` contains the original 85,030 sorted
`word<TAB>positive_integer_weight` rows. `tools/prepare_data.py` creates that base from
WordNet 3.0 lemmas, exception forms, and validated definition/example tokens,
plus selected grammatical words and contractions. It does not use benchmark
pairs. The base weight is `1 + gloss token count + 10 * tagged sense count`.
`tools/expand_lexicon.py` creates the final 161,847-entry `data/words.tsv`.
It uses noun/verb/adjective POS membership, WordNet exception forms, and English
inflection rules. Exception categories suppress conflicting regular forms;
consonant doubling uses WordNet exceptions. Existing and generated form weights
are at least 20% of the parent count, rounded with a minimum of one. Additional
adverb/ability forms require independent Webster validation. Generated
morphology can still overgenerate; it is not a complete English grammar.
`data/provenance.json` records all selected options and source/output hashes;
`data/base-provenance.json` describes the original dictionary.

`./build.sh` compiles `src/autocorrect.cpp` as C++17 and calls
`--build-index-compact data/words.tsv data/index.bin`. The `ACIDX006` format
stores words, weights and precomputed contextual sound keys, then unique
posting hashes with offsets into contiguous word-ID arrays. All integer fields
are explicitly little-endian. The loader validates lengths, keys, offsets,
posting IDs, ordering and total file size. It also supports `ACIDX003`,
`ACIDX004` and `ACIDX005` with their matching encoders. The compact index is
about 36 MiB for the selected dictionary.

A flat open-addressed table supports exact-word lookups. Bounded OSA, rotating
row pointers and distinct-letter masks reject impossible candidates cheaply.
Normal prediction keeps the best two and uses a nonnegative weighted-cost
lower bound to skip scores that cannot enter that pair. Diagnostic mode retains
the full list. Exhaustive small-alphabet bounded-distance checks and
fast/exhaustive decision-equivalence tests cover these optimizations.

## Data, evaluation, and reproducible iteration

### Existing datasets

- `my_dataset/source.txt` is the original Birkbeck aggregate source. It is kept
  unchanged.
- `my_dataset/input.txt` and `my_dataset/expected.txt` are aligned one-word
  pairs created by `tools/split_birkbeck.py`. Conversion lowercases and skips
  entries that cannot fit the supported single-token alphabet; see
  `my_dataset/conversion.json` for counts. Repeated inputs with different
  targets remain repeated, so this context-free task can have irreducible
  ambiguity.
- `hackathon_test/input.txt` and `hackathon_test/expected.txt` are the public
  development set.
- `tools/make_synthetic.py` makes a deterministic implementation diagnostic;
  generated sound mutations partly overlap the hand-coded rules and are not a
  proxy for real typo accuracy.

### Baseline commands

```sh
./build.sh
./test.sh
python3 tools/evaluate.py --input my_dataset/input.txt \
  --expected my_dataset/expected.txt --executable ./autocorrect \
  --label birkbeck --report results/birkbeck/current.json
python3 tools/evaluate.py --input hackathon_test/input.txt \
  --expected hackathon_test/expected.txt --executable ./autocorrect \
  --label public-development --report results/public-development-current.json
```

`tools/evaluate.py` reports exact matches, runtime including process startup and
index loading, observed peak RSS, clean-input preservation, and typo accuracy.
It checks output line count/alphabet and applies a 60 second timeout by default.
Use the same input files and invocation when comparing variants. Save a JSON
report for every run. Do not tune against a hidden test or add per-answer
exceptions from the development set.

### Iteration workflow for an agent

1. Record the baseline commit/state and rerun both datasets before changing
   behavior. Keep the existing default report unchanged for comparison.
2. Form a specific hypothesis (for example, a phonetic rule should retrieve a
   set of currently missed intended words without increasing false corrections
   of identity pairs).
3. Add focused unit cases for encoder outputs and retrieval edge cases. Include
   confusable minimal pairs, examples where a rule should not fire, short words,
   duplicate collapse, apostrophes, and maximum-length input.
4. Change one mechanism at a time: encoder mapping, sound-key index strategy,
   candidate cap, edit/ranking feature, dictionary source, or confidence gate.
   Label combinations explicitly and retain individual ablations.
5. Rebuild the index after any encoder or dictionary change. Run unit and CLI
   tests, then measure Birkbeck and public-development datasets.
6. Compare total exact accuracy and the clean/typo slices. Inspect mismatch
   samples and `./autocorrect --explain WORD` output to determine whether a
   failure is candidate recall, ranking, or abstention.
7. Keep a change only if its gains generalize across datasets or the tradeoff
   is explicitly justified. Then measure promising combinations, because
   interactions are possible. Report accuracy, runtime, memory, and confidence
   slices together.
8. Update this guide and the results manifest with implementation details,
   command lines, and measured outcomes. Ensure the package is rebuilt from the
   final source.

For an individual decision, run `./autocorrect --explain misspelling`. It prints
the chosen correction, reason, and up to ten candidate rows with raw edit
distance, sound-key distance, weighted cost, dictionary weight, and total score.

## Experiment controls and failure analysis

`--profile default` selects the shipped ranking; `--profile legacy` restores
original ranking costs, not the original dictionary/encoder. Put the profile
before overrides. Numeric controls are `--edit-weight`, `--sound-weight`,
`--prior-weight`, `--boundary-weight`, `--suffix-weight`, `--transpose-cost`,
`--insertion-scale`, `--ngram-weight`, and `--vowel-weight`.
`--edge-transpositions` / `--no-edge-transpositions` control boundary exemptions.
The edit weight blends raw OSA distance with weighted distance. Other switches
are `--spelling-costs` / `--no-spelling-costs` and `--extended-rules` /
`--no-extended-rules`. `--known-ratio N`, `--possessives`, and `--wide` are
optional experiments. Known-word correction uses stricter edit, frequency-ratio,
and score gates but still damaged hackathon clean-word preservation.

`--wide` queries two-deletion sound keys and permits sound distance two for
more distant spellings. Its added candidates still pass full-string checks.

Use `--trace < input.txt` to emit decisions and all surviving candidates.
`tools/analyze_failures.py` runs prediction first, then compares references in a
separate process and classifies errors as missing vocabulary, preserved known
word, retrieval/filter loss, ranking, or abstention. Reference files never enter
the prediction executable or dictionary generator. The analysis also computes
the upper bound imposed by identical inputs with different reference answers.

```sh
python3 tools/analyze_failures.py --input hackathon_test/input.txt \
  --expected hackathon_test/expected.txt --report results/new-analysis.json
```

`tools/evaluate.py` accepts repeated `--program-arg=VALUE`, `--output PATH`,
and `--all-errors`. Always record executable, dictionary, input and reference
hashes alongside experiments. Historic iteration executables and indexes are
kept under ignored `build/iterations/`; local text outputs remain under
`results/iterations/`. Older JSON run reports were removed during submission
cleanup. The archive includes only the two final evaluation reports; historical
comparison tables remain in the Markdown documents.

## Source map

| Path | Role |
| --- | --- |
| `src/autocorrect.cpp` | Encoder, indexes, edit distances, ranking, CLI |
| `data/words.tsv` | Bundled vocabulary and count weights |
| `data/provenance.json` | Lexicon sources and hashes |
| `tools/expand_lexicon.py` | POS inflections, exception handling, weight smoothing |
| `tools/analyze_failures.py` | Complete candidate-level error audit |
| `tools/run_iterations.py` | Run explicit configurations on both datasets |
| `tools/prepare_data.py` | Rebuild normalized base lexicon from supplied corpora |
| `tools/split_birkbeck.py` | Convert Birkbeck grouped source to aligned pairs |
| `tools/evaluate.py` | Accuracy/runtime/resource measurement |
| `tools/make_synthetic.py` | Deterministic synthetic diagnostic generator |
| `tests/unit.cpp` | Core distance, phonetic, and index-retrieval checks |
| `tests/test_cli.py` | Command-line and stream behavior checks |
| `build.sh`, `test.sh` | Build/index generation and local test entry points |
| `results/` | The two final evaluation reports and local text traces |

