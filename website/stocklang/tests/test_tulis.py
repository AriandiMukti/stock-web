"""The plain-language writer (stocklang_web.tulis) with Claude and the runner faked: no API calls."""
import unittest

import stocklang_web as web
import twin.llm as llm


class TestTulis(unittest.TestCase):
    def setUp(self):
        self._saved = (llm.panggil_json, web.jalankan)
        self.prompts = []

    def tearDown(self):
        llm.panggil_json, web.jalankan = self._saved

    def test_error_is_sent_back_for_a_fix(self):
        replies = iter([{'skrip': 'stock BBCA\nprint(clsoe)', 'penjelasan': 'a', 'asumsi': []},
                        {'skrip': 'stock BBCA\nprint(close)', 'penjelasan': 'b', 'asumsi': ['x']}])

        def fake_claude(system, user, schema, **kw):
            self.prompts.append(user)
            return next(replies)

        def fake_run(src):
            if 'clsoe' in src:
                return {'output': [], 'images': [], 'error': {'text': "unknown name 'clsoe'", 'line': 2, 'col': 7}}
            return {'output': ['4,940'], 'images': [], 'error': None}

        llm.panggil_json, web.jalankan = fake_claude, fake_run
        r = web.tulis('harga BBCA')
        self.assertEqual(r['percobaan'], 2)
        self.assertEqual(r['skrip'], 'stock BBCA\nprint(close)')
        self.assertEqual(r['output'], ['4,940'])
        self.assertIn("unknown name 'clsoe'", self.prompts[1])

    def test_gives_up_after_the_limit(self):
        llm.panggil_json = lambda *a, **k: {'skrip': 'bad(', 'penjelasan': '', 'asumsi': []}
        web.jalankan = lambda src: {'output': [], 'images': [], 'error': {'text': 'boom'}}
        r = web.tulis('x')
        self.assertEqual(r['percobaan'], web.MAKS_PERCOBAAN)
        self.assertTrue(r['error'])

    def test_claude_errors_and_empty_input(self):
        def fail(*a, **k):
            raise llm.GalatLLM('Belum ada kredensial Claude.')
        llm.panggil_json = fail
        self.assertEqual(web.tulis('x'), {'galat': 'Belum ada kredensial Claude.'})
        self.assertIn('galat', web.tulis('   '))

    def test_system_prompt_documents_the_new_features(self):
        s = web._system_tulis()
        for word in ('study(', 'param', 'rank(', 'ihsg', 'idx_rules', 'trailing_stop'):
            self.assertIn(word, s)
