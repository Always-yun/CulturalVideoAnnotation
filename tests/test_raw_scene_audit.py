import json
from pathlib import Path
import tempfile
import unittest
from scripts.innovation2.run_four_method_with_raw_audit import audited_parse


class RawSceneAuditTest(unittest.TestCase):
    def test_malformed_response_is_saved_before_parser_raises(self):
        raw = '{"scene":"example",broken}'
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(json.JSONDecodeError):
                audited_parse(raw, json.loads, tmp)
            files = list(Path(tmp).glob('*.json'))
            self.assertEqual(len(files), 1)
            self.assertEqual(json.loads(files[0].read_text())['raw_response'], raw)


if __name__ == '__main__':
    unittest.main()
