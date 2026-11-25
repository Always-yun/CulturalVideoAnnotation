import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.pipeline.scene_evidence import normalize_scene, retrieval_text, review_text_regions, SceneEvidenceError
import test_cultural_integration as integration

FakeEngine = integration.FakeEngine


def scene():
    return {'scene': '白天', 'subject': '中式校门', 'visible_features': ['匾额'],
            'background': ['背景猜测长城'], 'readable_text': [{'text': '猜错名称', 'legibility': 'clear'}],
            'text_regions': [{'kind': '匾额', 'time_ratio': .5, 'bbox': [.2, .2, .8, .6]}],
            'uncertain_entities': ['或许是长城']}


class SceneEvidenceTest(unittest.TestCase):
    def test_uncertainties_and_background_not_retrieval_identity(self):
        s = normalize_scene(json.dumps(scene()))
        text = retrieval_text(s, [{'text': '北京大学', 'legibility': 'clear'}], reviewed=True)
        self.assertIn('北京大学', text)
        self.assertNotIn('长城', text)
        self.assertNotIn('猜错名称', text)
        self.assertNotIn('北京大学', retrieval_text(s, [{'text': '北京大学', 'legibility': 'partial'}], reviewed=True))

    def test_invalid_regions_discarded_and_bounded(self):
        d = scene()
        good = d['text_regions'][0]
        d['text_regions'] = [dict(good, bbox=[-1, 0, 1, 1]), dict(good, time_ratio=True),
                             dict(good, bbox=[.8, .2, .2, .6]), good] * 5
        s = normalize_scene(json.dumps(d))
        self.assertEqual(len(s['text_regions']), 1)
        with self.assertRaises(ValueError):
            normalize_scene('{"scene": 1}')

    def test_real_video_crop_and_image_request(self):
        import cv2
        import numpy as np
        with tempfile.TemporaryDirectory() as tmp:
            video = str(Path(tmp) / 'untrusted_filename.mp4')
            writer = cv2.VideoWriter(video, cv2.VideoWriter_fourcc(*'mp4v'), 5, (200, 100))
            for i in range(5):
                writer.write(np.full((100, 200, 3), i * 40, dtype=np.uint8))
            writer.release()
            calls = []
            def respond(messages, temperature):
                calls.append(messages)
                return '{"text":"北京大学", "legibility":"clear"}'
            manager = SimpleNamespace(is_glm_mode=lambda: True, call_glm_api=respond)
            result = review_text_regions(video, scene()['text_regions'], manager, Path(tmp) / 'frames')
            self.assertEqual(result['items'][0]['text'], '北京大学')
            self.assertEqual(result['attempts'][0]['frame_index'], 2)
            self.assertEqual(len(calls[0][0]['content']), 3)
            self.assertNotIn('untrusted_filename', str(calls))
            self.assertTrue(Path(result['attempts'][0]['images'][0]).exists())

    def test_no_regions_and_unsupported_backend_do_not_call_api(self):
        manager = SimpleNamespace(is_glm_mode=lambda: False)
        self.assertEqual(review_text_regions('missing', [], manager, '/tmp/unused')['calls'], 0)
        self.assertEqual(review_text_regions('missing', scene()['text_regions'], manager, '/tmp/unused')['status'], 'unsupported_backend')

    def test_pipeline_uses_ocr_for_query_and_persists_raw(self):
        helper = integration.IntegrationTest(); helper.setUp()
        engine = FakeEngine(helper.final)
        engine.model_manager = object()
        pipeline = helper.pipeline(engine)
        review = {'status': 'completed', 'calls': 1, 'items': [{'text': '北京大学', 'legibility': 'clear'}]}
        with tempfile.TemporaryDirectory() as tmp, patch('src.pipeline.cultural_rag.review_text_regions', return_value=review):
            trace = pipeline.run('sample.mp4', scene_description=json.dumps(scene()), out_dir=tmp)
            self.assertIn('北京大学', trace['cultural_query']['scene_text'])
            self.assertNotIn('或许', trace['cultural_query']['scene_text'])
            self.assertEqual(trace['structured_scene']['uncertain_entities'], ['或许是长城'])
            self.assertTrue((Path(tmp) / '00_scene_evidence.json').exists())

    def test_legacy_cache_and_disabled_recognition_remain_usable(self):
        helper = integration.IntegrationTest(); helper.setUp()
        trace = helper.pipeline(FakeEngine(helper.final)).run(
            'sample.mp4', save=False, scene_description='原始描述：鸟巢')
        self.assertEqual(trace['scene_evidence_version'], 'legacy_cache')
        self.assertEqual(trace['scene_description'], '原始描述：鸟巢')
        pipeline = helper.pipeline(FakeEngine(helper.final))
        pipeline.text_recognition = False
        trace = pipeline.run('sample.mp4', save=False, scene_description=json.dumps(scene()))
        self.assertEqual(trace['text_recognition']['calls'], 0)
        self.assertEqual(trace['text_recognition']['status'], 'disabled')

    def test_prepared_evidence_bypasses_scene_and_ocr_calls(self):
        helper = integration.IntegrationTest(); helper.setUp()
        engine = FakeEngine(helper.final)
        evidence = {'scene_description': '可读文字：北京大学', 'scene_description_raw': '{}',
                    'scene_evidence_version': 'structured_v1', 'structured_scene': scene(),
                    'text_recognition': {'status': 'completed', 'calls': 1, 'items': []}}
        with patch('src.pipeline.cultural_rag.review_text_regions', side_effect=AssertionError('must reuse')):
            trace = helper.pipeline(engine).run('sample.mp4', save=False, prepared_evidence=evidence)
        self.assertEqual(len(engine.prompts), 1)
        self.assertEqual(trace['scene_description'], evidence['scene_description'])
        self.assertTrue(trace['prepared_evidence_reused'])

    def test_invalid_structured_cache_does_not_leak_guessed_names(self):
        helper = integration.IntegrationTest(); helper.setUp()
        with self.assertRaises(SceneEvidenceError):
            helper.pipeline(FakeEngine(helper.final)).run(
                'sample.mp4', save=False, scene_description='{"uncertain_entities": ["长城"]}')

    def test_fresh_malformed_response_is_not_retrieved_as_evidence(self):
        helper = integration.IntegrationTest(); helper.setUp()
        engine = FakeEngine('not json guessed 长城')
        with self.assertRaises(SceneEvidenceError):
            helper.pipeline(engine).run('sample.mp4', save=False)
        self.assertEqual(len(engine.prompts), 1)


if __name__ == '__main__':
    unittest.main()
