import json
from pathlib import Path
import tempfile
import unittest

from scripts.innovation2.run_four_method_accuracy import score_prediction
from src.knowledge.symbol_kb import SymbolKnowledgeBase


class FinalEntityAccuracyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        p = Path(self.tmp.name, 'kb.json')
        p.write_text(json.dumps({'symbols': [dict(symbol_id='pku', canonical_name='北京大学',
            aliases='北大', keywords='石狮|校门')]}))
        self.kb = SymbolKnowledgeBase(str(p))
        self.gt = {'gt_symbols': ['北京大学'], 'gt_symbol_ids': ['pku']}

    def tearDown(self):
        self.tmp.cleanup()

    def test_alias_correct_but_feature_keyword_and_prefix_incorrect(self):
        self.assertTrue(score_prediction('北大', False, self.gt, self.kb))
        self.assertFalse(score_prediction('石狮', False, self.gt, self.kb))
        self.assertFalse(score_prediction('北京大学附属小学', False, self.gt, self.kb))

    def test_extra_wrong_entity_does_not_receive_full_credit(self):
        self.assertFalse(score_prediction('北京大学、清华大学', False, self.gt, self.kb))

    def test_kb_gap_uses_actual_entity_not_unknown_rejection(self):
        gt = {'gt_symbols': ['冰糖葫芦'], 'gt_symbol_ids': []}
        self.assertTrue(score_prediction('冰糖葫芦', False, gt, self.kb))
        self.assertFalse(score_prediction('unknown_symbol', True, gt, self.kb))


if __name__ == '__main__':
    unittest.main()
