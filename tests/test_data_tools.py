"""Regression checks for morphology; use an independent miniature lexical source."""
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from expand_lexicon import expand, plural, verb_forms


class InflectionTest(unittest.TestCase):
    def test_conservative_morphology_avoids_reinflection_and_proper_noun_plurals(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / 'wordnet.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('wordnet/index.noun', 'reed\nreeds\nclass\nada\n')
                z.writestr('wordnet/noun.exc', '')
                z.writestr('wordnet/data.noun', '00000001 00 n 04 reed 0 reeds 0 class 0 Ada 0 | example\n')
                z.writestr('wordnet/index.verb', '')
                z.writestr('wordnet/verb.exc', '')
                z.writestr('wordnet/index.adj', 'clear\nclearer\ngood\nbetter\n')
                z.writestr('wordnet/adj.exc', 'better good\n')
            base = dict.fromkeys(['reed', 'reeds', 'class', 'ada', 'clear', 'clearer', 'good', 'better'], 100)
            words, _ = expand(base, archive, .2, smooth=True, conservative=True)
            for word in ['reeds', 'classes', 'clearer', 'clearest', 'better', 'ada']:
                self.assertIn(word, words)
            for word in ['reedses', 'adas', 'clearerer', 'clearerest', 'betterer']:
                self.assertNotIn(word, words)

    def test_plural_and_third_person_are_distinct(self):
        self.assertEqual(plural('chairman'), 'chairmen')
        self.assertEqual(plural('human'), 'humans')
        self.assertEqual(plural('german'), 'germans')
        self.assertIn('mans', verb_forms('man'))
        self.assertNotIn('men', verb_forms('man'))

    def test_exception_forms_suppress_invalid_regular_forms(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / 'wordnet.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('wordnet/index.noun', 'city\nformula\n')
                z.writestr('wordnet/noun.exc', 'formulae formula\n')
                z.writestr('wordnet/index.verb', 'ship\ndie\nwalk\n')
                z.writestr('wordnet/verb.exc', 'shipped ship\nshipping ship\ndying die\n')
                z.writestr('wordnet/index.adj', 'big\n')
                z.writestr('wordnet/adj.exc', 'bigger big\nbiggest big\n')
            base = dict.fromkeys(['city', 'formula', 'ship', 'die', 'walk', 'big'], 100)
            base['shipping'] = 1
            words, _ = expand(base, archive, .2, smooth=True)
            for word in ['cities', 'formulae', 'formulas', 'shipped', 'shipping',
                         'died', 'dying', 'walked', 'walking', 'bigger', 'biggest']:
                self.assertIn(word, words)
            for word in ['shiping', 'dieing', 'biger', 'biggestest']:
                self.assertNotIn(word, words)
            self.assertEqual(words['shipping'], 20)


if __name__ == '__main__':
    unittest.main()
