"""单独诊断第一步证据提取，不修改GT、权重、门控或历史实验结果。"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.pipeline.inference_engine import InferenceEngine
from src.pipeline.scene_evidence import STRUCTURED_SCENE_PROMPT, normalize_scene, retrieval_text, review_text_regions
from src.knowledge.symbol_kb import SymbolKnowledgeBase
from src.knowledge.retriever import extract_cultural_query
from src.knowledge.multimodal_retriever import MultimodalCulturalRetriever


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--video', required=True)
    p.add_argument('--output-dir', required=True)
    p.add_argument('--no-text-recognition', action='store_true')
    args = p.parse_args()
    out = Path(args.output_dir); out.mkdir(parents=True, exist_ok=True)
    engine = InferenceEngine()
    started = time.monotonic()
    try:
        engine.initialize()
        raw = engine.annotate_video(args.video, prompt=STRUCTURED_SCENE_PROMPT)
        (out / 'pass1_raw.txt').write_text(raw)
        scene = normalize_scene(raw)
        (out / 'structured_scene.json').write_text(json.dumps(scene, ensure_ascii=False, indent=2))
        review = ({'status': 'disabled', 'calls': 0, 'items': []} if args.no_text_recognition
                  else review_text_regions(args.video, scene['text_regions'], engine.model_manager, out / 'text_evidence'))
        query = retrieval_text(scene, review['items'], reviewed=review['status'] in {'completed', 'partial_failure'})
        kb = SymbolKnowledgeBase()
        keywords = extract_cultural_query(kb, query)
        candidates = MultimodalCulturalRetriever(kb=kb).retrieve(
            {'video_path': args.video, 'scene_text': query, 'keywords': keywords}, top_k=5)
        report = {'video_path': args.video, 'scene_evidence_version': 'structured_v1',
                  'scene_description_raw': raw, 'structured_scene': scene, 'text_recognition': review,
                  'retrieval_text': query, 'keywords': keywords,
                  'topk_candidates': [{'symbol_id': c.symbol_id, 'canonical_name': c.canonical_name,
                      'text_score': c.text_score, 'image_score': c.image_score,
                      'fusion_score': c.fusion_score, 'reason': c.reason} for c in candidates],
                  'seconds': round(time.monotonic()-started, 2),
                  'scope': '开发诊断，只运行第一步及未改动的检索器；不代表独立测试集收益'}
        (out / 'scene_evidence_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps({'output': str(out), 'keywords': keywords, 'text_status': review['status'],
                          'top5': [c.canonical_name for c in candidates]}, ensure_ascii=False))
    finally:
        engine.cleanup()


if __name__ == '__main__':
    main()
