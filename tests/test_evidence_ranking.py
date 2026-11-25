import json
import tempfile
import unittest
from pathlib import Path
from src.knowledge.symbol_kb import SymbolKnowledgeBase
from src.knowledge.multimodal_retriever import MultimodalCulturalRetriever
from src.knowledge.evidence_ranking import EvidenceRanker


class EvidenceRankingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        symbols = []
        for sid, name, kw in [('university', '北京大学', '校门'), ('bridge', '卢沟桥', '石狮'),
                              ('lake', '西湖', '湖面'), ('palace', '故宫', '宫殿')]:
            symbols.append(dict(symbol_id=sid, canonical_name=name, aliases='', keywords=kw,
                                visual_features=kw, typical_scene='', cultural_dimension='古城与历史文化',
                                dimension_code='ANCIENT', region='测试'))
        p = Path(self.tmp.name) / 'kb.json';p.write_text(json.dumps({'symbols': symbols}))
        self.kb = SymbolKnowledgeBase(str(p))

    def tearDown(self):
        self.tmp.cleanup()

    def rank(self, ctx, images, strategy='evidence_v1', k=5):
        return MultimodalCulturalRetriever(kb=self.kb, ranking_strategy=strategy).rank_with_scores(ctx, images, k)

    def test_generic_hit_not_promoted_to_full_strength(self):
        result = self.rank({'scene_text': '湖面'}, {'lake': .9})
        lake = next(c for c in result if c.symbol_id == 'lake')
        self.assertLess(lake.retrieval_evidence['text_evidence_strength'], .1)
        self.assertEqual(lake.text_score, 1)  # Historical score retained exclusively for gate compatibility.

    def test_clear_name_precedes_generic_feature_and_strong_visual_neighbor(self):
        ctx = {'scene_text': '石狮 可读文字：北京大学', 'text_recognition': {
            'status': 'completed', 'items': [{'text': '北京大学', 'legibility': 'clear'}]}}
        result = self.rank(ctx, {'bridge': .99, 'university': .5})
        self.assertEqual(result[0].symbol_id, 'university')
        self.assertEqual(result[0].retrieval_evidence['clear_text_exact_hits'], ['北京大学'])
        self.assertFalse(result[0].retrieval_evidence['identity_verified'])

    def test_merged_pool_preserves_visual_candidates_without_text(self):
        result = self.rank({'scene_text': '石狮'}, {'university': .99, 'bridge': .2}, k=2)
        self.assertEqual({c.symbol_id for c in result}, {'bridge', 'university'})
        self.assertEqual(len({c.symbol_id for c in result}), len(result))

    def test_duplicate_keywords_do_not_inflate_evidence(self):
        ranker = EvidenceRanker(self.kb);s = self.kb.get('bridge')
        a = ranker.text_evidence(s, {'scene_text': '石狮', 'keywords': ['石狮']})
        b = ranker.text_evidence(s, {'scene_text': '石狮石狮石狮', 'keywords': ['石狮']*10})
        self.assertEqual(a['text_evidence_strength'], b['text_evidence_strength'])

    def test_longer_plaque_does_not_prove_parent_identity(self):
        ev = EvidenceRanker(self.kb).text_evidence(self.kb.get('palace'), {
            'scene_text': '故宫的神武门', 'text_recognition': {'status': 'completed',
                'items': [{'text': '故宫的神武门', 'legibility': 'clear'}]}})
        self.assertEqual(ev['clear_text_exact_hits'], [])
        self.assertFalse(ev['identity_verified'])

    def test_legacy_scores_unchanged_when_ranking_changes(self):
        ctx = {'scene_text': '北京大学 石狮'}; images = {'bridge': .99, 'university': .5}
        old = {c.symbol_id:c for c in self.rank(ctx, images, 'legacy')}
        new = self.rank(ctx, images)
        for c in new:
            self.assertEqual((c.text_score, c.image_score, c.fusion_score),
                             (old[c.symbol_id].text_score, old[c.symbol_id].image_score, old[c.symbol_id].fusion_score))

    def test_image_only_mode_does_not_prioritize_text(self):
        r = MultimodalCulturalRetriever(kb=self.kb, ranking_strategy='evidence_v1', fusion_alpha=0)
        rows = r.rank_with_scores({'scene_text':'北京大学'}, {'bridge': .99, 'university': .5})
        self.assertEqual(rows[0].symbol_id, 'bridge')
        self.assertAlmostEqual(rows[0].ranking_score, .99)

    def test_filters_apply_to_both_candidate_sources(self):
        r = MultimodalCulturalRetriever(kb=self.kb, ranking_strategy='evidence_v1')
        self.assertEqual(r.rank_with_scores({'scene_text':'北京大学'}, {'university':1}, region='其他'), [])
        self.assertEqual(r.rank_with_scores({'scene_text':'北京大学'}, {'university':1}, dimension='TECH'), [])
        self.assertEqual(r.rank_with_scores({}, {}, 0), [])


if __name__ == '__main__':
    unittest.main()
