import json
from pathlib import Path
import tempfile
import unittest
from src.experiments.entity_accuracy import final_entity_correct
from src.knowledge.symbol_kb import SymbolKnowledgeBase


class EntityAccuracyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name, 'kb.json')
        path.write_text(json.dumps({'symbols': [
            dict(symbol_id='pku', canonical_name='北京大学', aliases='北大', keywords='石狮|校门', region='北京'),
            dict(symbol_id='cbd', canonical_name='CBD', aliases='中央商务区|北京中央商务区', keywords='高楼', region='北京')]}))
        self.kb = SymbolKnowledgeBase(str(path))

    def tearDown(self):
        self.tmp.cleanup()

    def test_generic_rendering_suffixes_do_not_change_entity(self):
        for text in ['CBD天际线', '北京中央商务区（CBD）天际线', 'CBD（中央商务区）']:
            self.assertTrue(final_entity_correct(text, False, ['CBD'], self.kb))

    def test_another_entity_or_visual_keyword_never_matches(self):
        for text in ['北京大学附属小学', '石狮', '清华大学']:
            self.assertFalse(final_entity_correct(text, False, ['北京大学'], self.kb))

    def test_parenthesis_does_not_hide_extra_asserted_entity(self):
        self.assertFalse(final_entity_correct('北京大学（校门）、清华大学', False, ['北京大学'], self.kb))

    def test_unknown_is_not_correct_for_uncovered_actual_entity(self):
        self.assertFalse(final_entity_correct('unknown_symbol', True, ['冰糖葫芦'], self.kb))
        self.assertTrue(final_entity_correct('冰糖葫芦', False, ['冰糖葫芦'], self.kb))


if __name__ == '__main__':
    unittest.main()
