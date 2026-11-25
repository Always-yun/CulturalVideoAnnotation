"""Regression checks for the public annotation and persisted cultural results."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from src.pipeline.cultural_rag import CulturalRAGPipeline, parse_c_layer
from src.pipeline.inference_engine import InferenceEngine
from src.pipeline.prompt_manager import PromptManager
from src.knowledge.retriever import CulturalCandidate
from src.knowledge.symbol_kb import SymbolKnowledgeBase


class FakeEngine:
    def __init__(self, final):
        self.final = final
        self.prompts = []
        self.prompt_manager = PromptManager()
        self.video_processor = SimpleNamespace(
            validate_video=lambda p: (True, ''),
            get_video_metadata=lambda p: SimpleNamespace(to_dict=lambda: {'resolution': '640x360', 'duration': 5}))

    def initialize(self):
        pass

    def annotate_video(self, path, prompt=None):
        assert prompt is not None, 'Internal passes must bypass public RAG dispatch'
        self.prompts.append(prompt)
        return self.final


class IntegrationTest(unittest.TestCase):
    def setUp(self):
        self.kb = SymbolKnowledgeBase()
        self.symbol = self.kb.get_by_name('鸟巢')
        self.candidate = CulturalCandidate(
            self.symbol['symbol_id'], self.symbol['canonical_name'],
            self.symbol['cultural_dimension'], self.symbol['dimension_code'], raw=self.symbol)
        self.final = ('【E｜场景环境层】白天\n【M｜主体行为层】建筑\n'
                      '【C｜文化维度层】该场景隶属于科技与创新文化。\n核心符号：鸟巢\n'
                      '【A｜视听语言层】固定\n【S｜整体叙事层】展示\n【T｜技术属性层】编造的参数')

    def pipeline(self, engine, level='confident', verifier=None):
        return CulturalRAGPipeline(
            engine=engine, kb=self.kb,
            retriever=SimpleNamespace(retrieve=lambda context, top_k: [self.candidate]),
            rejection_gate=SimpleNamespace(decide=lambda *a, **kw: SimpleNamespace(
                to_dict=lambda: {'level': level, 'signals': {}, 'reason': 'test'})),
            identity_verifier=verifier)

    def test_rejection_updates_saved_text_and_parse_and_preserves_other_layers(self):
        engine = FakeEngine(self.final)
        with tempfile.TemporaryDirectory() as d:
            trace = self.pipeline(engine, 'insufficient').run('sample.mp4', controlled=True,
                                                            out_dir=d, scene_description='鸟巢')
            self.assertTrue(parse_c_layer(trace['final_annotation'])['unknown_symbol'])
            self.assertEqual(trace['raw_final_annotation'], self.final)
            self.assertIn('640x360', trace['final_annotation'])
            self.assertNotIn('编造的参数', trace['final_annotation'])
            saved = (Path(d) / '05_final_annotation_kb.txt').read_text()
            self.assertEqual(saved, trace['final_annotation'])
            for layer in ['E', 'M', 'C', 'A', 'S', 'T']:
                self.assertEqual(saved.count('【' + layer + '｜'), 1)

    def test_mixed_candidate_output_does_not_accept_unknown_entity(self):
        p = self.pipeline(FakeEngine(self.final))
        c = {'core_symbol': '鸟巢、凭空地标', 'unknown_symbol': False}
        self.assertTrue(p.enforce_symbol_constraint(c, [self.candidate], True, 'confident')['unknown_symbol'])

    def test_v2_rejection_reaches_final_annotation(self):
        verifier = SimpleNamespace(decide=lambda *a, **kw: {'final_symbol': '', 'final_status': 'reject'})
        trace = self.pipeline(FakeEngine(self.final), verifier=verifier).run(
            'sample.mp4', controlled=True, save=False, scene_description='鸟巢')
        self.assertTrue(trace['final_c_layer']['unknown_symbol'])
        self.assertIn('identity_verification', trace)

    def test_v2_acceptance_preserves_known_symbol(self):
        verifier = SimpleNamespace(decide=lambda *a, **kw: {'final_symbol': '鸟巢', 'final_status': 'accept'})
        trace = self.pipeline(FakeEngine(self.final), verifier=verifier).run(
            'sample.mp4', controlled=True, save=False, scene_description='鸟巢')
        self.assertFalse(trace['final_c_layer']['unknown_symbol'])
        self.assertEqual(trace['final_c_layer']['core_symbol'], '鸟巢')

    def test_multi_gpu_forwards_culture_options(self):
        from unittest.mock import patch
        from scripts.run_multi_gpu import run_single_gpu_task
        with patch('scripts.run_multi_gpu.subprocess.run', return_value=SimpleNamespace(returncode=0)) as run:
            result = run_single_gpu_task(0, 'sample.mp4', '/tmp/output', culture_mode='off',
                                         cultural_top_k=3, kb_path='custom.json', identity_verifier='off')
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[cmd.index('--culture-mode') + 1], 'off')
        self.assertEqual(cmd[cmd.index('--cultural-top-k') + 1], '3')
        self.assertEqual(cmd[cmd.index('--kb-path') + 1], 'custom.json')
        self.assertTrue(result['success'])

    def test_public_engine_dispatch_and_custom_prompt_bypass(self):
        engine = InferenceEngine()
        engine._is_initialized = True
        engine.video_processor = FakeEngine(self.final).video_processor
        calls = []
        engine.cultural_pipeline = SimpleNamespace(
            run=lambda *a, **kw: calls.append('rag') or {'final_annotation': 'integrated', 'output_dir': 'ignored'},
            save_trace=lambda *a: None)
        engine.model_manager.is_glm_mode = lambda: True
        engine._annotate_with_glm_api = lambda path, prompt: 'custom'
        self.assertEqual(engine.annotate_video('sample.mp4'), 'integrated')
        self.assertEqual(engine.annotate_video('sample.mp4', prompt='scene'), 'custom')
        self.assertEqual(calls, ['rag'])


if __name__ == '__main__':
    unittest.main()
