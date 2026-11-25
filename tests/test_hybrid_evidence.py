import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from src.pipeline.scene_evidence import recover_scene, SceneEvidenceError
from src.pipeline.hybrid_evidence import prepare_hybrid_evidence, IndependentVideoVerifier, parse_verifier_response
import test_cultural_integration as integration


class HybridEvidenceTest(unittest.TestCase):
    def scene(self):
        return {'scene':'白天','subject':'石柱','visible_features':['龙纹'],
                'background':['树林'],'readable_text':[],'text_regions':[],'uncertain_entities':[]}

    def test_isolated_bad_optional_field_preserves_literal_text_without_api(self):
        raw = '{"scene":"白天","subject":"喷泉","visible_features":["建筑","名称"标牌"],"background":["蓝天"],"readable_text":[{"text":"名称","legibility":"clear"}],"text_regions":[],"uncertain_entities":[]}'
        scene, audit = recover_scene(raw, lambda *a, **kw: self.fail('must not call model'))
        self.assertEqual(scene['subject'], '喷泉')
        self.assertEqual(scene['readable_text'][0]['text'], '名称')
        self.assertEqual(scene['visible_features'], [])
        self.assertEqual(audit['discarded_fields'], ['visible_features'])

    def test_invalid_verifier_escape_preserves_literal_content(self):
        raw = r'{"reason":"arch \_ detail","identity_status":"accept_exact_identity"}'
        value, status = parse_verifier_response(raw)
        self.assertEqual(value['reason'], r'arch \_ detail')
        self.assertEqual(status, 'literal_backslash_escape_repair')

    def test_valid_verifier_json_is_unchanged(self):
        expected = {'reason':'可见结构','identity_status':'accept_exact_identity'}
        value, status = parse_verifier_response(json.dumps(expected))
        self.assertEqual(value, expected); self.assertEqual(status, 'valid')

    def test_format_repair_preserves_observations(self):
        good=json.dumps(self.scene(),ensure_ascii=False);raw=good[:-1]+',}'
        calls=[]
        scene,audit=recover_scene(raw,lambda *a,**k:(calls.append(a) or good))
        self.assertEqual(scene,self.scene());self.assertEqual(len(calls),1)
        self.assertEqual(audit['status'],'syntax_repaired')

    def test_format_repair_cannot_invent_an_identity(self):
        repaired=dict(self.scene(),subject='故宫')
        with self.assertRaises(SceneEvidenceError):
            recover_scene(json.dumps(self.scene(),ensure_ascii=False)+',',lambda *a,**k:json.dumps(repaired,ensure_ascii=False))

    def test_failed_repair_is_error_not_unknown(self):
        with self.assertRaises(SceneEvidenceError):recover_scene('{bad',lambda *a,**k:'{}')

    def test_hypotheses_reach_retrieval_not_verification(self):
        scene=self.scene();source={'structured_scene':scene,'text_recognition':{'status':'not_needed','items':[]}}
        evidence=prepare_hybrid_evidence({'scene_description':'假设故宫'},source,None,'video','unused')
        self.assertIn('故宫',evidence['retrieval_scene_text'])
        self.assertNotIn('故宫',evidence['scene_description'])
        self.assertNotIn('retrieval_scene_text',source)
        helper=integration.IntegrationTest();helper.setUp();contexts=[];observed=[]
        verifier=SimpleNamespace(decide=lambda *a,**kw:(observed.append(a[2]) or {'final_symbol':'鸟巢'}))
        pipeline=helper.pipeline(integration.FakeEngine(helper.final),verifier=verifier)
        pipeline.retriever=SimpleNamespace(retrieve=lambda c,top_k:(contexts.append(c) or [helper.candidate]))
        pipeline.run('sample.mp4',controlled=True,save=False,prepared_evidence=evidence)
        self.assertIn('故宫',contexts[0]['scene_text']);self.assertNotIn('故宫',observed[0])

    @patch('src.pipeline.hybrid_evidence.extract_keyframes',return_value=[])
    def test_missing_frames_are_error_not_rejection(self,_):
        kb=SimpleNamespace(get=lambda sid:{'canonical_name':'测试'})
        with self.assertRaises(ValueError):
            IndependentVideoVerifier(kb,None).decide('id','missing','scene',[{'symbol_id':'x','canonical_name':'测试'}],pred_symbol='测试')

    @patch('src.pipeline.hybrid_evidence.extract_keyframes')
    def test_verifier_only_sends_query_frames_and_candidate_definition(self,extract):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'frame.jpg';Image.new('RGB',(10,10)).save(p);extract.return_value=[str(p)]
            calls=[]
            def caller(messages,**kw):
                calls.append(messages)
                return json.dumps({'identity_status':'accept_exact_identity','reason':'test','visual_identity_evidence':'可见独特结构'})
            kb=SimpleNamespace(get=lambda sid:{'canonical_name':'测试','reference_images':['DO_NOT_SEND']})
            v=IndependentVideoVerifier(kb,caller)
            r=v.decide('id','video','石柱',[{'symbol_id':'x','canonical_name':'测试','fusion_score':.99}],pred_symbol='测试')
            self.assertEqual(r['final_symbol'],'测试')
            self.assertNotIn('DO_NOT_SEND',str(calls));self.assertNotIn('fusion_score',str(calls))
            self.assertEqual(sum(x['type']=='image_url' for x in calls[0][1]['content']),1)

if __name__=='__main__':unittest.main()
