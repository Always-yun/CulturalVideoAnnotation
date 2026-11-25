import unittest
from src.experiments.c_retrieval import rank_scale, fuse


class FusionTest(unittest.TestCase):
    def test_rank_scale_removes_incompatible_units_and_treats_ties_equally(self):
        self.assertEqual(rank_scale({'a': 100, 'b': 50, 'c': 50}),
                         rank_scale({'a': .8, 'b': .6, 'c': .6}))
        self.assertEqual(rank_scale({'a': 100, 'b': 50, 'c': 50})['b'], .25)

    def test_missing_image_never_creates_image_candidate(self):
        self.assertEqual(fuse({'a': 10}, {}, 'image', .5, 5, 0), [])
        row = fuse({'a': 10}, {}, 'multimodal', .5, 5, 0)[0]
        self.assertEqual(row['effective_text_weight'], 1)
        self.assertIsNone(row['raw_image_cosine'])

    def test_no_entitywise_weight_inflation_or_duplicate(self):
        rows = fuse({'a': 10}, {'b': .8}, 'multimodal', .5, 5, 0)
        self.assertEqual(len(rows), 2)
        self.assertEqual([r['fusion_score'] for r in rows], [.5, .5])
        self.assertEqual(fuse({}, {}, 'multimodal', .5, 5, 0), [])
