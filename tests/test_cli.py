#!/usr/bin/env python3
import os
import struct
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
EXE = Path(os.environ.get('AUTOCORRECT_EXE', ROOT / 'autocorrect')).resolve()


class CLITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temp.name)
        cls.index = cls.directory / 'toy.bin'
        cls.lexicon = cls.directory / 'toy.tsv'
        cls.lexicon.write_text('planet\t20\ngarden\t20\nmusic\t20\nschool\t20\nphonetic\t20\ncan\'t\t20\n')
        subprocess.run([str(EXE), '--build-index', str(cls.lexicon), str(cls.index)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_cli(self, text, *args):
        return subprocess.run([str(EXE), '--index', str(self.index), *args], input=text,
                              text=True, capture_output=True, cwd=self.directory, timeout=20)

    def test_corrections_and_clean_protocol(self):
        proc = self.run_cli("plnaet\ngarrden\nmusci\nskool\nfonetik\ncant\n")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "planet\ngarden\nmusic\nschool\nphonetic\ncan't\n")
        self.assertEqual(proc.stderr, '')

    def test_preservation_and_line_endings(self):
        proc = self.run_cli("planet\r\ngarden\r\ncan't")
        self.assertEqual(proc.stdout, "planet\ngarden\ncan't\n")

    def test_empty_and_long_inputs(self):
        self.assertEqual(self.run_cli('').stdout, '')
        words = ['x' * 64, 'x' * 65, 'a' * 5000, 'q', "'''"]
        proc = self.run_cli('\n'.join(words))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.splitlines(), words)

    def test_explanation(self):
        proc = self.run_cli('', '--explain', 'plnaet')
        self.assertIn('plnaet -> planet', proc.stdout)
        self.assertIn('weighted_cost', proc.stdout)

    def test_index_encoder_modes(self):
        for mode in ('--build-index-enhanced', '--build-index-refined', '--build-index-compact'):
            index = self.directory / (mode + '.bin')
            subprocess.run([str(EXE), mode, str(self.lexicon), str(index)], check=True, capture_output=True)
            proc = self.run_cli('skool\nfonetik\n', '--index', str(index))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stdout, 'school\nphonetic\n')

    def test_compact_and_original_contextual_indexes_have_identical_traces(self):
        text = "plnaet\ngarrden\nskool\nfonetik\nplanet\ncan't\nzzzz\n"
        traces = []
        for mode in ('--build-index-enhanced', '--build-index-compact'):
            index = self.directory / (mode + '.bin')
            subprocess.run([str(EXE), mode, str(self.lexicon), str(index)], check=True, capture_output=True)
            proc = self.run_cli(text, '--index', str(index), '--trace')
            self.assertEqual(proc.returncode, 0, proc.stderr)
            traces.append(proc.stdout)
        self.assertEqual(*traces)

    def test_compact_index_rejects_corrupt_offsets_ids_and_trailing_bytes(self):
        index = self.directory / 'compact.bin'
        subprocess.run([str(EXE), '--build-index-compact', str(self.lexicon), str(index)], check=True, capture_output=True)
        data = index.read_bytes()
        n, = struct.unpack_from('<I', data, 8)
        at = 28
        for _ in range(n):
            word_len = data[at]
            at += 5 + word_len
            phone_len = data[at]
            at += 1 + phone_len
        groups, = struct.unpack_from('<Q', data, at)
        offsets_bad = bytearray(data)
        struct.pack_into('<I', offsets_bad, at + 8 + 8, 1)
        ids_bad = bytearray(data)
        struct.pack_into('<I', ids_bad, at + 8 + groups * 12, n)
        for invalid in (offsets_bad, ids_bad, data + b'junk', data[:-1]):
            broken = self.directory / 'broken-compact.bin'
            broken.write_bytes(invalid)
            proc = self.run_cli('planet\n', '--index', str(broken))
            self.assertNotEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout, '')

    def test_numeric_option_validation(self):
        for option, value in [('--edit-weight', 'nan'), ('--sound-weight', '-1'),
                              ('--prior-weight', '2'), ('--transpose-cost', '.3oops'),
                              ('--known-ratio', 'inf'), ('--profile', 'absent')]:
            proc = self.run_cli('plnaet\n', option, value)
            self.assertNotEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout, '')

    def test_transposition_option_does_not_change_prior(self):
        proc = self.run_cli('', '--profile', 'legacy', '--prior-weight', '0',
                            '--transpose-cost', '.35', '--explain', 'plnaet')
        fields = next(line.split('\t') for line in proc.stdout.splitlines() if line.startswith('planet\t'))
        self.assertAlmostEqual(float(fields[-1]), .35)

    def test_trace_stream_keeps_decisions_explicit(self):
        proc = self.run_cli('plnaet\ngarden\n', '--trace')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('plnaet\tplanet\t', proc.stdout)
        self.assertIn('garden\tgarden\tdictionary word: preserved', proc.stdout)

    def test_fast_prediction_matches_exhaustive_candidate_decisions(self):
        words = set(['planet', 'garden', 'music', 'school', "can't", 'phonetic'])
        for word in tuple(words):
            for i in range(len(word)):
                words.add(word[:i] + word[i + 1:])
                words.add(word[:i] + 'a' + word[i:])
                words.add(word[:i] + 'x' + word[i + 1:])
                if i + 1 < len(word):
                    words.add(word[:i] + word[i + 1] + word[i] + word[i + 2:])
        text = '\n'.join(sorted(words)) + '\n'
        for flags in [[], ['--wide'], ['--insertion-scale', '.75'],
                      ['--edit-weight', '1'], ['--known-ratio', '10'],
                      ['--vowel-weight', '.15']]:
            fast = self.run_cli(text, *flags)
            traced = self.run_cli(text, *flags, '--trace')
            self.assertEqual(fast.returncode, 0, fast.stderr)
            self.assertEqual(traced.returncode, 0, traced.stderr)
            exhaustive = [line.split('\t')[1] for line in traced.stdout.splitlines()
                          if not line.startswith('\t')]
            self.assertEqual(fast.stdout.splitlines(), exhaustive)

    def test_wide_search_option_runs(self):
        proc = self.run_cli('plnaet\nskool\n', '--wide')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, 'planet\nschool\n')

    def test_missing_and_corrupt_index_fail_on_stderr(self):
        for contents in (b'', b'ACIDX003' + b'\xff' * 20, self.index.read_bytes()[:-1]):
            broken = self.directory / 'broken.bin'
            broken.write_bytes(contents)
            proc = self.run_cli('planet\n', '--index', str(broken))
            self.assertNotEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout, '')
            self.assertIn('autocorrect:', proc.stderr)
        proc = self.run_cli('planet\n', '--index', str(self.directory / 'missing'))
        self.assertNotEqual(proc.returncode, 0)

    def test_bundled_dictionary_is_preserved_from_other_directory(self):
        words = [line.split()[0] for line in (ROOT / 'data/words.tsv').read_text().splitlines()]
        proc = subprocess.run([str(EXE)], input='\n'.join(words), text=True,
                              capture_output=True, cwd=self.directory, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.splitlines(), words)


if __name__ == '__main__':
    unittest.main()
