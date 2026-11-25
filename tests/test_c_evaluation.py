import unittest
from src.experiments.c_evaluation import core_names


class CExtractionTest(unittest.TestCase):
    def test_other_asserted_entity_not_hidden_by_explanation_parentheses(self):
        self.assertEqual(core_names('识别出关键视觉锚点为北京大学（红门、石狮）、中国国家博物馆。'),
                         ['北京大学', '中国国家博物馆'])

    def test_duplicate_identity_does_not_inflate_prediction_count(self):
        self.assertEqual(core_names('北京大学、北京大学'), ['北京大学'])

    def test_no_scene_qualifier_identity_credit(self):
        self.assertEqual(core_names('CBD天际线'), ['cbd天际线'])

    def test_decorative_brackets_follow_frozen_punctuation_rule(self):
        self.assertEqual(core_names('[冰糖葫芦]'), ['冰糖葫芦'])
