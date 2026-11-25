import json
from pathlib import Path
import tempfile
import unittest

from src.knowledge.reference_policy import eligible_reference_paths
from src.knowledge.symbol_kb import SymbolKnowledgeBase
from src.knowledge.multimodal_retriever import MultimodalCulturalRetriever


class ReferencePolicyTest(unittest.TestCase):
    def test_explicit_review_and_enable_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'ref.jpg').write_bytes(b'fixture')
            ref = {'local_path': 'ref.jpg', 'verification_status': 'candidate_unreviewed',
                   'use_for_retrieval': False}
            symbol = {'reference_images': [ref]}
            self.assertEqual(eligible_reference_paths(symbol, tmp), [])
            ref['use_for_retrieval'] = True
            self.assertEqual(eligible_reference_paths(symbol, tmp), [])
            ref['verification_status'] = 'human_verified'
            self.assertEqual(eligible_reference_paths(symbol, tmp), [str(Path(tmp, 'ref.jpg'))])
            ref['local_path'] = 'missing.jpg'
            self.assertEqual(eligible_reference_paths(symbol, tmp), [])

    def test_no_images_does_not_load_clip_or_return_text_in_image_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp, 'kb.json')
            p.write_text(json.dumps({'symbols': [dict(symbol_id='s', canonical_name='故宫',
                aliases='', keywords='宫殿', visual_features='', cultural_description='',
                typical_scene='', reference_images=[])]}))
            kb = SymbolKnowledgeBase(str(p))
            r = MultimodalCulturalRetriever(kb=kb, fusion_alpha=0)
            self.assertEqual(r.retrieve({'scene_text': '故宫'}), [])
            self.assertIsNone(r._clip)
            self.assertEqual(r.image_unavailable_symbols, {'s'})

    def test_image_scores_cannot_include_text_only_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp, 'kb.json')
            p.write_text(json.dumps({'symbols': [dict(symbol_id=s, canonical_name=n,
                aliases='', keywords='', visual_features='', cultural_description='', typical_scene='')
                for s, n in [('a', '故宫'), ('b', '天坛')]]}))
            r = MultimodalCulturalRetriever(kb=SymbolKnowledgeBase(str(p)), fusion_alpha=0)
            rows = r.rank_with_scores({'scene_text': '故宫'}, {'b': .7})
            self.assertEqual([x.symbol_id for x in rows], ['b'])


if __name__ == '__main__':
    unittest.main()
