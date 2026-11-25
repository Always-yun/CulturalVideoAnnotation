import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from src.pipeline.scene_evidence import contextual_evidence_text, subject_evidence_text
from src.knowledge.identity_verifier_v2 import IdentityVerifierV2
import test_cultural_integration as integration


class AccuracyRepairTest(unittest.TestCase):
    def test_background_is_available_but_not_subject_identity(self):
        scene = {'scene': '白天', 'subject': '石柱', 'visible_features': ['龙纹'],
                 'background': ['远处北京大学校门'], 'readable_text': [],
                 'uncertain_entities': ['猜测故宫']}
        text = contextual_evidence_text(scene, [])
        self.assertIn('北京大学', text)
        self.assertNotIn('北京大学', subject_evidence_text(text))
        self.assertNotIn('故宫', text)

    def test_cached_evidence_rebuilt_and_forwarded_without_new_pass1(self):
        helper = integration.IntegrationTest(); helper.setUp()
        engine = integration.FakeEngine(helper.final)
        seen = []
        verifier = SimpleNamespace(decide=lambda *args, **kw: (seen.append(args[2]) or {'final_symbol': '鸟巢'}))
        pipeline = helper.pipeline(engine, verifier=verifier)
        pipeline.evidence_policy = 'context_v2'
        cache = {'scene_description': '旧描述', 'scene_evidence_version': 'structured_v1',
                 'structured_scene': {'scene':'白天','subject':'鸟巢','visible_features':[],
                                      'background':['远处建筑'],'readable_text':[]},
                 'text_recognition': {'status':'not_needed','items':[]}}
        trace = pipeline.run('sample.mp4', controlled=True, save=False, prepared_evidence=cache)
        self.assertEqual(len(engine.prompts), 1)
        self.assertIn('远处建筑', trace['cultural_query']['scene_text'])
        self.assertIn('远处建筑', seen[0])
        self.assertEqual(cache['scene_description'], '旧描述')

    def verifier(self):
        v = IdentityVerifierV2.__new__(IdentityVerifierV2)
        v.ver_cfg = {'num_frames': 4, 'max_candidates': 3}
        v.visual = SimpleNamespace(frame_matrix=lambda paths: (None, []))
        v.screen = lambda *args: None
        v.build_candidate = lambda c, i, *args: SimpleNamespace(
            canonical_name=c['canonical_name'], symbol_id=c['symbol_id'], verification_required=False,
            to_dict=lambda: {'symbol_id':c['symbol_id']})
        v._rule_status = lambda ev: {'identity_status':'accept_exact_identity','reason':'test'}
        return v

    @patch('src.knowledge.identity_verifier_v2.extract_keyframes', return_value=[])
    def test_verifies_selected_fifth_candidate_not_first(self, _):
        candidates = [{'canonical_name':str(i),'symbol_id':str(i)} for i in range(5)]
        result = self.verifier().decide('id','video','scene', candidates, pred_symbol='4')
        self.assertEqual(result['final_symbol'], '4')
        self.assertEqual(result['decisions'][0]['symbol_id'], '4')

    @patch('src.knowledge.identity_verifier_v2.extract_keyframes', return_value=[])
    def test_unmatched_prediction_never_accepts_top1(self, _):
        result = self.verifier().decide('id','video','scene', [{'canonical_name':'A','symbol_id':'a'}], pred_symbol='B')
        self.assertEqual(result['final_symbol'], '')
        self.assertEqual(result['final_reason'], 'predicted_symbol_not_in_candidates')

if __name__ == '__main__':
    unittest.main()
