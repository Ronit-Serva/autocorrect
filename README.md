# Autocorrect — algorithmic hackathon solution

A standalone C++17 program that reads one lowercase word per line and writes one
best correction per line. It uses a bundled dictionary, spelling edits, general
phonetic rules, and a count-based ranking heuristic. There are no trained models,
model APIs, network calls, runtime Python dependencies, or example-specific
correction tables.

## Build and run

On Linux x86-64, install a C++17 compiler (GCC 9+ or a recent Clang), then:

```sh
./build.sh
./autocorrect < input.txt > output.txt
```

The build is entirely offline. It compiles the native `autocorrect` executable
and generates `data/index.bin` from the included `data/words.tsv`. Build time is
outside the timed inference run. Keep the executable and `data/` together; the
program locates its data relative to its executable, even from another working
directory. Use `CXX=clang++ ./build.sh` to select a compiler.

Normal execution prints only corrections to stdout. Errors go to stderr and
produce a nonzero exit status. Input has no header; CRLF and a final line without
a newline are supported. The expected apostrophe is ASCII `'`.

To inspect a decision:

```sh
./autocorrect --explain fonetik
```

This separate diagnostic mode prints the decision and up to ten ranked
candidates, including edit distance, sound-key distance, weighted edit cost,
dictionary weight, and final score. Do not use it in the judge's invocation.

## How it works

1. **Preserve known words.** An exact dictionary match returns unchanged. Unknown
   inputs shorter than three or longer than 64 characters are also preserved.
   The length limit bounds approximate-search work; it never truncates output.
2. **Retrieve spelling candidates.** At build time, take the first seven letters
   of every dictionary word and index all keys made by deleting zero, one, or two
   letters. At runtime, generate the same keys for the input and retrieve words
   with matching keys. This avoids generating every possible replacement letter.
   Full-word distances eliminate irrelevant prefix matches and hash collisions.
3. **Retrieve sound candidates.** A hand-written encoder removes most vowels,
   folds similar consonants, handles common digraphs and silent initial letters,
   and collapses duplicates. An additional index of sound keys and their
   one-character deletions finds candidates beyond two spelling edits. Broad
   buckets are capped at 128 or 256 frequency-ranked postings to control work.
4. **Verify and rank.** Optimal string alignment distance counts insertion,
   deletion, replacement, and adjacent transposition. A weighted dynamic program
   gives lower costs to doubled letters, vowel changes, neighboring keyboard keys,
   apostrophes, transpositions, and general spelling/sound correspondences such as
   `ph`/`f` and `tion`/`shun`. A candidate's score is:

   ```text
   weighted_edit_cost + 0.28 * sound_key_distance - 0.12 * log(1 + dictionary_weight)
   ```

   Lower is better. Equal scores use dictionary weight, then alphabetical order,
   making results deterministic. All constants are hand-selected heuristics;
   there is no training or parameter fitting.
5. **Abstain on weak matches.** Three-character inputs permit only one edit.
   More distant phonetic matches must meet spelling and sound limits, a weighted
   cost ceiling, and a score margin. If nothing qualifies, preserve the input.
6. **Reuse repeated work.** A bounded 50,000-entry cache avoids repeated searches.

The indexes are sorted arrays of 64-bit key hashes and 32-bit word IDs. A query
uses binary searches followed by candidate verification. A prefix contributes at
most `1 + 7 + 21 = 29` spelling keys. Candidate ranking takes
`O(candidates * input_length * candidate_length)`, followed by sorting. Sound-key
search is a heuristic, not an exhaustive search of every English pronunciation.

The binary index uses explicit little-endian fields rather than native structs.
Loading checks the header, file length, word lengths, posting IDs, and sort order.
Rebuild the index whenever the source or lexicon changes. The build script always
does this. Compilation and index construction are not performed at runtime.

## Dictionary and counts

The bundled lexicon has **85,030 entries**. It is derived from WordNet 3.0's
single-word lemmas, morphology exception lists, and tokens in its definitions and
examples. A BSD Webster word list validates additional observed tokens. The full
archaic Webster vocabulary is not blindly accepted. A small hand-written list
adds grammatical function words and standard contractions that WordNet's four
parts of speech do not fully cover.

Default dictionary weights are:

```text
1 + occurrences in WordNet definitions/examples + 10 * tagged WordNet sense count
```

These are **dictionary-derived count weights, not representative modern English
corpus frequencies**. They provide a reproducible offline prior, but technical
and encyclopedic vocabulary can be overrepresented. See
[`data/provenance.json`](data/provenance.json) for source hashes and the generated
lexicon hash. WordNet is lexical data, not a trained model.

Data preparation is optional; the normalized lexicon is already included. To
reproduce it using the same source files:

```sh
python3 tools/prepare_data.py --wordnet /path/to/wordnet.zip \
  --webster /path/to/web2 --output data
./build.sh
```

The script accepts NLTK's WordNet 3.0 archive layout. `--webster` is optional, but
omitting it changes the vocabulary. `--frequencies /path/to/word-counts.txt` can
replace count weights for existing dictionary entries using an independently
sourced `word COUNT` file. Cite that data and retain its license if used. Do not
use development/test reference answers to modify the dictionary or rules.

## Tests and measurements

Python 3 is needed only for development tools, not the built autocorrector.

```sh
./test.sh
python3 tools/make_synthetic.py
python3 tools/evaluate.py \
  --input build/synthetic/input.txt \
  --expected build/synthetic/expected.txt \
  --label synthetic-10000 --report build/synthetic/report.json
```

Validation includes:

- Edit-distance, weighting, phonetic, and long-sound-key checks.
- Exhaustive two-edit retrieval checks over a small alphabet, including the
  seven-character prefix boundary.
- CLI corrections, apostrophes, blank streams, line endings, long inputs,
  dictionary corruption, and execution from another directory.
- Preservation of every one of the 85,030 bundled words.

AddressSanitizer and UndefinedBehaviorSanitizer checks also passed for the unit
suite and 2,004 random/adversarial inputs. The submission archive was extracted
into a fresh directory (including spaces in its path), rebuilt offline, and all
six integration tests passed there.

Recorded local diagnostic result on **macOS 12.7.6, x86-64**:

| Measurement | Result |
| --- | ---: |
| Synthetic inputs | 10,000 |
| Exact-match accuracy A | 0.8881 (88.81%) |
| Launch-to-exit wall time T | 1.671 seconds |
| Peak resident memory | 83.72 MiB |
| Preservation of already-correct synthetic inputs | 100% |
| Correction accuracy on synthetic misspellings | 82.50% |

The recorded report is in [`results/synthetic-macos.json`](results/synthetic-macos.json).
The generator uses seed `20261025`, samples targets from the bundled dictionary,
and creates spelling edits and sound substitutions. Its sound patterns overlap
the algorithm's general rules. It excludes accidental real-word substitutions.
Consequently, **this is an implementation diagnostic, not an estimate of hidden
test accuracy**. It does not test unseen vocabulary or natural human error rates.

After implementation, a read-only check of Table 1 in the problem brief yielded
**12/16 correct**. The remaining outputs were `restaraunt -> restraint`,
`nitch -> notch`, `yot -> yet`, and `expresso -> express`. These expose the limits
of dictionary-derived priors and approximate phonetics. No rules or word entries
were changed in response to that check. This small example check is not the
public development set, either.

**Public development accuracy A and time T: not measured.** The public input and
reference files were not supplied. Measure them with:

```sh
python3 tools/evaluate.py \
  --input /path/to/dev-input.txt --expected /path/to/dev-reference.txt \
  --label public-development --report results/public-development.json
```

The evaluator includes startup/data loading in wall time, checks output count and
alphabet, records resident memory, and reports preservation and typo accuracy
separately. It returns nonzero for an invalid run. It uses the official 60-second
timeout by default. Peak RSS is observed after execution, not enforced as an OS
memory cap. Add `--tmin SECONDS` only when the fastest valid competition time is
known; otherwise the total competition score cannot be calculated.

The executable and tests were run locally on macOS. **A Linux execution has not
been verified in this environment.** The archive includes portable source and a
Linux build script; it deliberately excludes the macOS binary. Build, test, and
measure again on the actual Linux judging environment.

## Submission archive

```sh
python3 tools/package.py
```

This writes `dist/autocorrect-submission.tar.gz`, containing source, executable
build/test scripts, the normalized dictionary and licenses, documentation, tools,
and available measurement reports. It excludes local binaries, generated indexes,
temporary files, and the problem PDF. The judge can extract it, enter
`autocorrect-submission/`, and run `./build.sh` followed by `./autocorrect`.

The archive is a **submission candidate** until the required public-development
report is added. Rerun the packaging command after recording that result.

## Limits and useful next steps

- Without sentence context, real-word errors are ambiguous. Exact dictionary
  matches are intentionally preserved, including alternate spellings that might
  disagree with a reference's preferred spelling.
- Some names, recent words, and regular inflections are absent. A missing correct
  word can be overcorrected; an absent intended word cannot be recovered.
- The broad sound key is approximate. Irregular loanword pronunciations and
  short sound-alike spellings may remain unresolved. Capped buckets may omit rare
  candidates.
- Modern independently sourced frequency counts and a curated, licensed modern
  dictionary would improve coverage and ranking. The current build needs neither
  downloads nor credentials.
- Do not insert answer mappings for the brief or development set. Use public
  development data to report the required metrics, not to special-case words.

## Sources, attribution, and licenses

- **Princeton WordNet 3.0**, copyright 2006 Princeton University. Vocabulary,
  gloss text token counts, and tagged sense counts were used to derive the
  bundled dictionary. The complete required notice is in
  [`data/WORDNET-LICENSE.txt`](data/WORDNET-LICENSE.txt).
  [WordNet database documentation](https://wordnet.princeton.edu/documentation/wndb5wn),
  [WordNet licensing](https://wordnet.princeton.edu/license-and-commercial-use),
  [NLTK WordNet archive distribution](https://github.com/nltk/nltk_data/blob/gh-pages/packages/corpora/wordnet.zip).
- **BSD `web2` / Webster's Second International word list**, obtained from the
  system's `/usr/share/dict/web2`, used to validate observed vocabulary. The
  accompanying distribution notice describes its source and public-domain
  status; it is preserved in
  [`data/WEBSTER-NOTICE.txt`](data/WEBSTER-NOTICE.txt).
- **Symmetric deletion indexing** is inspired by
  [Wolf Garbe's SymSpell](https://github.com/wolfgarbe/SymSpell). This project
  implements its own C++ index and ranking; it does not bundle SymSpell code or
  its frequency dictionary.
- Count-based spelling ranking is informed by
  [Peter Norvig's spelling-corrector explanation](https://www.norvig.com/spell-correct.html).
  No code, spelling-error datasets, or trained error probabilities from that
  project are included.
- Runtime library dependencies: the C++ standard library and platform API for
  executable location. Development scripts use only the Python standard library.

For a judges' walkthrough, read `deletes`, `phonetic`, `weighted_distance`,
`build_index`, and `Corrector::analyze` in that order. `--explain` exposes how the
same components contribute to any individual decision.
