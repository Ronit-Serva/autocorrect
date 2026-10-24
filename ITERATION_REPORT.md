# Accuracy iteration report

The selected default reaches **91.40% (1,828/2,000)** on the supplied hackathon
set and **40.865% (14,412/35,267)** on Birkbeck. The original implementation
scored 72.60% and 39.694%. **The requested 99% hackathon accuracy was not
achieved.** The final system fixes 415 hackathon rows that the original got
wrong and regresses 39, a net gain of 376 correct answers.

The campaign measured 43 paired configurations, including the final release
build. The two supplied datasets were used for diagnosis and iteration, so all
reported comparisons are development results. There is no untouched holdout,
and these scores do not establish hidden-test accuracy or a state-of-the-art
ranking. No reference-answer mappings were added to prediction or lexical data.

## What the initial failures revealed

The original dictionary contained only 1,612 of the 2,000 hackathon targets.
Of its 548 errors, **385 had an expected answer absent from the dictionary**.
Common plural and verb forms such as `inputs`, `consulted`, and `guidelines`
were missing. Phonetic changes alone could not recover absent candidates.

The original Birkbeck target coverage was 31,798/35,267. Its errors also include
very distant spelling attempts, real-word inputs, proper nouns, and identical
inputs assigned to different intended words. The last category limits any
fixed context-free prediction function to **94.1106%** on that dataset, even
with an ideal dictionary and ranking. The hackathon file has no such duplicate
input conflicts; this particular upper bound is 100% there, not a promise that
99% is attainable by these algorithms.

## Research and the implemented experiments

[SymSpell's implementation and documentation](https://github.com/wolfgarbe/SymSpell)
combine deletion-based retrieval with a vocabulary filtered for valid spellings
and representative count frequencies. The existing project already used
similar retrieval, but its dictionary coverage and WordNet-derived counts were
weak. POS-based inflection generation delivered the largest improvement.
Replacing counts with approximate Wikipedia rank-derived counts performed
worse; blending the two also failed to improve the best combination. A direct
frequency-dictionary download was unavailable through the local shell's
restricted network, so a modern full frequency corpus remains untested.

[Hunspell's own manual](https://github.com/hunspell/hunspell/blob/master/man/hunspell.5)
describes affix handling, phonetic rules, related-character mappings, replacement
patterns, keyboard neighbors, and n-gram suggestions. This motivated treating
morphology, candidate generation, and ranking as separate experiments. The
selected implementation uses WordNet POS/exception data and general spelling
rules with explicit initial/final restrictions. Broader prefix derivation
and extra vocabulary increased coverage but introduced competing candidates.

[Aspell's suggestion modes](https://aspell.sourceforge.net/man-html/Notes-on-the-Different-Suggestion-Modes.html)
use both spelling and soundlike distance. Experiments compared the original
broad encoder, a contextual wrapper, and a finer encoder retaining vowel and
voicing distinctions. The contextual wrapper won in the final combination.
A broader phonetic-search mode improved Birkbeck with a small hackathon
regression. These are custom encoders; the code does not implement or claim
to be Double Metaphone.

## Selected changes and ablations

| Configuration | Hackathon | Birkbeck |
| --- | ---: | ---: |
| Original baseline | 72.60% | 39.694% |
| Initial POS-based inflections | 86.75% | 41.186% |
| Improved inflection exceptions + hybrid ranking | 88.60% | 39.618% |
| Inflection count smoothing + hybrid ranking | 88.80% | 40.083% |
| Add initial-character penalty | 89.40% | 40.565% |
| Spelling costs + initial-character penalty | 90.15% | 40.378% |
| Conservative form weights + 50% raw edit component | 90.70% | 40.355% |
| Extended spelling/sound rules | 91.35% | 40.619% |
| Final default, including final-character penalty | **91.40%** | **40.865%** |
| Optional broad search + smaller raw-edit component | 91.25% | **41.387%** |

The steps above summarize useful combinations, not a claim that every individual
change improves both datasets. Some changes interact. All paired results and
command lines are recorded in `results/iterations/summary.json`.

The final ranking uses half raw OSA distance and half weighted edit distance,
a 0.15 sound-distance term, a -0.08 log-count term, and 0.25/0.15 penalties for
first/last-character changes. Weighted edits discount transpositions, doubled
letters, final silent `e`, and general sound/spelling correspondences. Rules
are reusable character sequences, not whole-word exceptions. Inflection counts
receive a 20% parent-weight floor; the final dictionary contains 161,847 words.

Known-word correction was tested with ratio thresholds 10 and 50. It improved
Birkbeck but reduced hackathon accuracy and clean-word preservation. It remains
optional. Automatic possessive-stem correction and a much larger lexicon were
also tested and left off after regressions. The optional `--wide` mode expands
sound retrieval and loosens distant-spelling filters; it is slower and trades
a little hackathon accuracy for Birkbeck recall.

## Remaining hackathon errors

The final full audit classifies the 172 remaining errors as:

| Cause | Count |
| --- | ---: |
| Intended word is retrieved but another candidate wins | 125 |
| Expected word is absent from the dictionary | 28 |
| Input is already a dictionary word and is preserved | 17 |
| Confidence gate preserves the input | 1 |
| Expected candidate is not retrieved or is filtered | 1 |

Examples include `spund -> spend` versus reference `spun`, `boaring -> bearing`
versus `boring`, and `discusted -> discussed` versus `disgusted`. Multiple
plausible edits and imperfect count priors compete. `gasses -> gases` and
`conveyer -> conveyor` illustrate the tension between preserving valid spellings
and matching a preferred answer. Targets such as abbreviations, modern terms,
and some proper names remain outside the vocabulary.

The final dictionary covers 98.5% of hackathon reference rows, and retrieval
is nearly complete for covered non-word errors. Consequently, further broad
retrieval is unlikely to be the main hackathon improvement. The strongest
remaining research directions are independently sourced vocabulary/frequencies
and more discriminating, independently validated edit costs. Sentence context
could resolve some ambiguity, but these files supply isolated words only.
Achieving 99% would require correcting at least **152 additional rows net**.
Nothing in these runs demonstrates that a few more phonetic rules will do so.

Birkbeck has a different error distribution. Its final audit finds 7,634
retrieval/filter failures, 7,989 ranking failures, 4,153 preserved dictionary
inputs, 365 missing-vocabulary failures, and 714 abstentions. Broader retrieval
is more useful there. `--wide --edit-weight .25` measured 14,596 correct rows
(41.387%) while scoring 91.25% on hackathon, compared with 14,412 and 91.40%
for the selected default.

## Reproduction and artifacts

```sh
./build.sh
./test.sh
python3 tools/evaluate.py --input hackathon_test/input.txt \
  --expected hackathon_test/expected.txt --report results/new-hackathon.json \
  --output build/hackathon-predictions.txt --all-errors
python3 tools/evaluate.py --input my_dataset/input.txt \
  --expected my_dataset/expected.txt --report results/new-birkbeck.json
python3 tools/analyze_failures.py --input hackathon_test/input.txt \
  --expected hackathon_test/expected.txt --report results/new-analysis.json
```

Use repeated `--program-arg=VALUE` to pass experimental flags through the
evaluator. `tools/run_iterations.py` runs one explicit configuration on both
datasets; for example:

```sh
python3 tools/run_iterations.py another-wide-run --index data/index.bin \
  --wide --edit-weight .25
```

The default executable never reads expected outputs. `tools/analyze_failures.py`
compares references after collecting predictions, then requests candidate
traces for the failed inputs. Each error records the target's rank and features,
the top candidates, and the failure category.

- `results/iterations/hackathon-final-analysis.json`: all remaining hackathon errors.
- `results/iterations/birkbeck-final-analysis.json`: complete Birkbeck error audit.
- `results/iterations/hackathon-changes.json`: 415 fixes and 39 regressions.
- `results/iterations/summary.json`: every paired experiment.
- `results/public-development.json` and `results/birkbeck-final.json`: compact final metrics.
- `data/provenance.json`: generator settings and source/output hashes.

Historical executables and intermediate dictionaries remain under ignored
`build/iterations/`. They are not runtime dependencies. The final normalized
dictionary and base dictionary are bundled. Runtime remains entirely offline.
Tests cover core distances, phonetic/index consistency, position-restricted
rules, morphology exceptions, CLI validation, and preservation of all bundled
words. The unit suite and twelve Python tests passed on macOS. Linux has not
been executed here. Timings are local single-run observations and are affected
by machine load; no statistical runtime superiority is claimed.
