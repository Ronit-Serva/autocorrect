# Autocorrect implementation guide for coding agents

This document describes the implementation currently present in this checkout,
with extra detail on its hand-written phonetic encoding. It is intended as a map
for controlled algorithm experiments. Read it alongside `src/autocorrect.cpp`;
the source is authoritative if this document and the code ever differ.

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

The current encoder applies these operations, in order:

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
  result is displayed as `sound_edits` and contributes `0.28 * sound_edits` to
  ranking.
- `weighted_distance()` is a dynamic program over the full input and candidate.
  It makes apostrophe insertion/deletion cost 0.35, repeated-letter
  insertion/deletion cost 0.45, vowel insertion/deletion cost 0.8, and other
  insertions/deletions cost 1. Substitution costs 0 for a same letter, 0.55
  between vowels, 0.8 for neighboring QWERTY keys, and 1 otherwise. Adjacent
  transposition costs 0.65.
- A table of bidirectional multi-character spelling/sound rules can add a
  lower-cost transition, including `ph/f`, `ck/k`, `qu/kw`, `c/k`, `c/s`,
  `g/j`, `tion/shun`, `sion/zhun`, `ture/cher`, `ee/i`, `oo/u`, `eau/o`,
  `ai/ay`, `ie/ei`, `ight/ite`, `dge/j`, and `tch/ch`. The dynamic program
  indexes candidate rules by the final characters, then checks the complete
  suffix before applying them.

The final lower-is-better score is:

```text
weighted_distance(input, candidate)
+ 0.28 * optimal_string_alignment(phonetic(input), phonetic(candidate))
- 0.12 * log(1 + dictionary_weight(candidate))
```

Ties break by larger raw dictionary weight and then alphabetical spelling.
Weights are a fixed count heuristic from WordNet data, not modern corpus
frequencies. The correction gate requires weighted cost at most
`min(3.2, 1.05 + 0.2 * input_length)` and either raw spelling distance at most
two or a best-versus-second score margin of at least 0.12. For inputs up to
three characters, candidates more than one raw edit away are filtered before
ranking. If no candidate qualifies, the input is preserved.

## Dictionary and generated index

`data/words.tsv` contains sorted `word<TAB>positive_integer_weight` rows (85,030
entries in the current build). `tools/prepare_data.py` creates this lexicon from
WordNet 3.0 lemmas, exception forms, and validated definition/example tokens,
plus selected grammatical words and contractions. It does not use the Birkbeck
misspelling pairs. The default weight is `1 + gloss token count + 10 * tagged
sense count`. `data/provenance.json` records source and output hashes.

`./build.sh` compiles `src/autocorrect.cpp` as C++17, then calls the executable
with `--build-index data/words.tsv data/index.bin`. The binary file starts with
`ACIDX003`, entry/posting counts, then word lengths, weights, word bytes, and
the sorted spelling and sound posting arrays. Integer fields are serialized
explicitly little-endian. Runtime validates the header, lengths, posting IDs,
array ordering, and total file size before accepting the data.

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
   Avoid changing multiple coefficients and rules in one patch.
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

## Source map

| Path | Role |
| --- | --- |
| `src/autocorrect.cpp` | Encoder, indexes, edit distances, ranking, CLI |
| `data/words.tsv` | Bundled vocabulary and count weights |
| `data/provenance.json` | Lexicon sources and hashes |
| `tools/prepare_data.py` | Rebuild normalized lexicon from supplied corpora |
| `tools/split_birkbeck.py` | Convert Birkbeck grouped source to aligned pairs |
| `tools/evaluate.py` | Accuracy/runtime/resource measurement |
| `tools/make_synthetic.py` | Deterministic synthetic diagnostic generator |
| `tests/unit.cpp` | Core distance, phonetic, and index-retrieval checks |
| `tests/test_cli.py` | Command-line and stream behavior checks |
| `build.sh`, `test.sh` | Build/index generation and local test entry points |
| `results/` | Saved evaluation reports from prior runs |

