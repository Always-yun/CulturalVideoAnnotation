"""Freeze the existing 30 videos and run a C-layer retrieval ablation.

No historical predictions, named-scene caches, unknown groups or thresholds
are used. Unavailable image evidence is a blocked method, never a text proxy.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import subprocess
import time
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.knowledge.symbol_kb import SymbolKnowledgeBase
from src.knowledge.reference_policy import eligible_reference_paths

MODES = ('free', 'text', 'image', 'multimodal')


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def norm(s):
    return re.sub(r'[\s“”\"\[\]。]', '', s).lower()


def accepted_names(gt, kb):
    # Keywords describe categories and are deliberately excluded from identity.
    names = list(gt['gt_symbols'])
    for sid in gt['gt_symbol_ids']:
        s = kb.get(sid)
        if s:
            names += [s['canonical_name']] + str(s.get('aliases', '')).split('|')
    return {norm(n) for n in names if n}


def score_prediction(core, unknown, gt, kb):
    from src.pipeline.cultural_rag import extract_pred_names
    names = extract_pred_names(core)
    # All asserted entities must match the frozen target; no substring credit.
    return bool(names and not unknown and all(norm(n) in accepted_names(gt, kb) for n in names))


def prepare(out, kb):
    source = ROOT / 'experiments/innovation2/data/eval/cultural_ablation_gt_final31.jsonl'
    original = [json.loads(l) for l in source.read_text().splitlines() if l.strip()]
    csv_path = ROOT / 'experiments/innovation2/data/cultural_eval/cultural_eval_30.csv'
    provenance = {r['video_id']: r for r in csv.DictReader(csv_path.open(encoding='utf-8-sig'))}
    import cv2
    items, excluded = [], []
    for g in original:
        path = ROOT / g['video_path']
        if not path.is_file():
            excluded.append({'video_id': g['video_id'], 'reason': 'missing_video', 'path': str(path)})
            continue
        probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error',
            '-show_entries', 'format=duration:stream=codec_type,nb_frames,avg_frame_rate',
            '-of', 'json', str(path)], timeout=20))
        stream = next(x for x in probe['streams'] if x['codec_type'] == 'video')
        duration = float(probe['format']['duration'])
        total = int(stream.get('nb_frames', '0')) if str(stream.get('nb_frames', '0')).isdigit() else None
        ratio = stream['avg_frame_rate'].split('/')
        fps = float(ratio[0]) / float(ratio[1]) if float(ratio[1]) else None
        frames = []
        print(f"PREPARE {g['video_id']}", flush=True)
        for i in range(4):
            p = out / 'keyframes' / g['video_id'] / f'{i}.jpg'
            p.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(['ffmpeg', '-v', 'error', '-threads', '1', '-y',
                '-ss', str(i * duration / 4), '-i', str(path), '-frames:v', '1',
                '-threads', '1', str(p)], check=True, capture_output=True, timeout=30)
            if not p.is_file() or cv2.imread(str(p)) is None:
                raise RuntimeError(f'Unreadable video {g["video_id"]} at {i * duration / 4}s')
            frames.append({'path': str(p.relative_to(ROOT)), 'sha256': sha(p),
                           'decoder': 'ffmpeg_presentation_timestamp', 'time_seconds': i * duration / 4})
        item = {k: g[k] for k in ('video_id', 'video_path', 'gt_symbols', 'gt_symbol_ids', 'gt_dimension_code')}
        item.update(video_sha256=sha(path), frame_count=total, fps=fps, keyframes=frames,
                    kb_coverage=bool(g['gt_symbol_ids']),
                    gt_source=provenance[g['video_id']]['gt_source'],
                    gt_review_status=provenance[g['video_id']]['review_status'])
        items.append(item)
    if len(items) != 30:
        raise RuntimeError(f'Expected exactly the agreed 30 videos, got {len(items)}')
    refs = []
    for s in kb.symbols:
        eligible = eligible_reference_paths(s, ROOT)
        for r in s.get('reference_images') or []:
            if not isinstance(r, dict):
                continue
            p = ROOT / r.get('local_path', '__missing__')
            valid = False
            if p.is_file():
                from PIL import Image
                try:
                    with Image.open(p) as im:
                        im.verify()
                    valid = True
                except Exception:
                    pass
            refs.append(dict(symbol_id=s['symbol_id'], canonical_name=s['canonical_name'],
                             **r, file_exists=p.is_file(), decodes=valid,
                             actual_sha256=sha(p) if p.is_file() else None,
                             eligible=str(p) in eligible))
    frozen = {str(p.relative_to(ROOT)): sha(p) for p in [source, csv_path, Path(kb.json_path)]}
    for folder in ('src/knowledge', 'src/pipeline', 'src/models', 'config'):
        for p in (ROOT / folder).rglob('*'):
            if p.suffix in {'.py', '.json'}:
                frozen[str(p.relative_to(ROOT))] = sha(p)
    frozen[str(Path(__file__).relative_to(ROOT))] = sha(__file__)
    dump(out / 'reference_audit.json', refs)
    manifest = dict(created_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
                    kb_path=str(Path(kb.json_path).relative_to(ROOT)), kb_version=kb.meta.get('version'),
                    kb_entities=len(kb), n_videos=len(items), excluded=excluded, items=items,
                    reference_records=len(refs), eligible_references=sum(r['eligible'] for r in refs),
                    frozen_hashes=frozen,
                    protocol=dict(modes=MODES, top_k=5, fusion_alpha=0.5,
                                  scene_cache='fresh structured observation only',
                                  rejection_gate=False, identity_gate=False, controlled=False,
                                  scoring='exact canonical/alias entity match; all asserted entities must be valid',
                                  ground_truth='Existing labels retained, including KB gaps; not independent human reannotation'))
    dump(out / 'manifest.json', manifest)
    return manifest


def report(out, manifest, records, kb):
    from src.experiments.ablation_metrics import dimension_hit
    summaries = []
    for mode in MODES:
        rows = [r for r in records if r['mode'] == mode]
        completed = [r for r in rows if r['status'] == 'completed']
        count = sum(r.get('symbol_correct', False) for r in completed)
        summaries.append(dict(mode=mode, expected=30, attempted=sum(r['status'] in {'completed', 'failed'} for r in rows),
                              completed=len(completed), correct=count,
                              accuracy=count / 30 if len(completed) == 30 else None,
                              completed_accuracy=count / len(completed) if completed else None,
                              dimension_correct=sum(r.get('dimension_correct', False) for r in completed),
                              failed=sum(r['status'] == 'failed' for r in rows),
                              blocked=sum(r['status'].startswith('blocked') for r in rows)))
    dump(out / 'results.json', {'config': manifest['protocol'], 'records': records, 'summaries': summaries})
    for filename, rows in [('summary.csv', summaries), ('predictions.csv', records)]:
        if rows:
            keys = list(dict.fromkeys(k for row in rows for k in row))
            with (out / filename).open('w', encoding='utf-8-sig', newline='') as f:
                w = csv.DictWriter(f, fieldnames=keys); w.writeheader()
                for row in rows:
                    w.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for k, v in row.items()})
    text = ['# 文化知识增强的文化符号标注：30视频四组实验', '',
            f"运行时间（北京时间）：{manifest['created_at']}。原31条清单排除缺失的神武门，现存30条均验证4帧可读。",
            f"冻结知识库：{manifest['kb_path']}，{manifest['kb_entities']}实体；参考图{manifest['reference_records']}条，符合启用和审核条件{manifest['eligible_references']}条。", '',
            '|方法|完成/30|实体正确|全30条准确率|运行失败|受阻|', '|---|---:|---:|---:|---:|---:|']
    for s in summaries:
        accuracy = f"{s['accuracy']:.2%}" if s['accuracy'] is not None else '未完成，不报告'
        text.append(f"|{s['mode']}|{s['completed']}/30|{s['correct']}|{accuracy}|{s['failed']}|{s['blocked']}|")
    text += ['', '## 材料与实现核查', '',
             '- 已实现：视频入口scripts/run_annotation.py；InferenceEngine调用GLM/Qwen；PromptManager与emcast_schema定义EMCAST；CulturalRAGPipeline完成描述、检索、候选注入与标注。',
             '- 文本检索为确定性关键词/别名/视觉特征匹配，不是训练的文本嵌入模型。图像检索为CLIP ViT-B/32，视频均匀4帧及实体参考图分别平均并归一化；余弦分数映射至[0,1]；融合为0.5×归一化文本分+0.5×图像分。',
             '- v2实际114实体，v3实际126实体；默认代码使用v2，本次固定v2，不将较新版本与旧GT混用。实体字段有规范名、别名、文化维度、visual_features、spatial_features、typical_scene、cultural_description、来源与图片记录等。',
             '- 已修复：图像检索原来忽略use_for_retrieval与verification_status；纯Image无图时仍可从文本候选池返回零分实体；并列排序不稳定。现按审核标记过滤，纯Image不混入文本候选，固定并列次序。',
             '- 缺失材料：可用于检索的已审核真实参考图片。现存图片保留原始文件与来源，不擅自改为已审核；Image与Multimodal未满足运行条件，不能算作Text或Free的复本。',
             '- IdentityEvidenceGate实际是确定性完整规范名/别名匹配，或visual_features片段精确匹配；OCR和参考图身份匹配标记unavailable。只有配置拒识门控后才执行。它不是知识图谱推理或训练模块。本轮四组均不启用，避免引入额外变量及旧阈值重叠问题。',
             '- 受控生成在既有代码中是候选闭集Prompt与确定性后处理。本轮四组均controlled=False；保留实现，不增加第五组。',
             '- 最终准确率按实际实体参考答案计算；知识库不覆盖不等于参考答案unknown。只用规范名与别名，不用keywords子串；额外错误实体也算错误。运行异常和解析失败不算拒识正确。',
             '- 原参考答案来源含文件名和历史预测，虽标frozen，并非本轮独立双人核验；天安门/天安门广场等实体范围、人民大会堂文化类别仍有审核局限。因此本轮是既有素材上的复现实验，不能直接宣称独立泛化。',
             '- 不设置Known/Easy Unknown/Hard Unknown分组，不训练、不新增损失函数或端到端优化；知识库覆盖仅作逐条材料记录。', '', '## 运行与结论边界', '',
             '所有标注组共用相同基础模型、生成参数与视频文件；Text使用本轮重新提取的结构化视觉观察，uncertain_entities不参与检索，未复用历史命名描述或旧预测。Prompt和模型原文、候选与关键帧均落盘。',
             'Image/Multimodal材料未就绪时不输出准确率，不据此断言图文融合提升。完整四组结论须参考图核验并启用后补跑。', '', '## 错误与受阻记录', '']
    for r in records:
        if r['status'] == 'failed' or (r['status'] == 'completed' and not r.get('symbol_correct')):
            text.append(f"- {r['video_id']}/{r['mode']}：{r.get('error') or ('预测'+r.get('pred_symbol','')+'；参考'+str(r.get('gt_symbols'))+'；'+r.get('error_type',''))}")
    reasons = sorted({r.get('reason', '') for r in records if r['status'].startswith('blocked')})
    text.extend('- ' + reason for reason in reasons)
    text += ['', '复现：`python scripts/innovation2/run_four_method_accuracy.py --output-dir '+str(out.relative_to(ROOT))+'`；`--prepare-only`仅核查材料。已完成结果逐条保存，重启仅重试未完成项。',
             '材料索引：manifest.json、reference_audit.json、keyframes/；运行记录：results.json、predictions.csv、summary.csv及每视频trace。']
    (out / 'report.md').write_text('\n'.join(text) + '\n', encoding='utf-8')


def run(out, manifest, kb):
    from src.pipeline.cultural_rag import CulturalRAGPipeline
    from src.pipeline.scene_evidence import STRUCTURED_SCENE_PROMPT, normalize_scene, retrieval_text
    from src.experiments.ablation_metrics import dimension_hit
    from src.knowledge.multimodal_retriever import MultimodalCulturalRetriever
    from src.knowledge.retriever import KeywordCulturalRetriever
    from zai import ZhipuAiClient
    pipeline = CulturalRAGPipeline(kb=kb, text_recognition=False)
    config = pipeline.engine.config
    client = ZhipuAiClient(api_key=config.model.glm_api_key, timeout=90, max_retries=0)
    calls = []
    def call(messages, temperature=None):
        begin = time.time()
        entry = {'model': config.model.glm_model_name, 'temperature': 0.1, 'started_at': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()}
        try:
            response = client.chat.completions.create(model=config.model.glm_model_name,
                messages=messages, temperature=0.1, max_tokens=config.generation.max_new_tokens)
            value = response.choices[0].message.content
            entry.update(status='completed', usage=str(getattr(response, 'usage', None)))
            if not value:
                raise RuntimeError('Empty model output')
            return value
        except Exception as e:
            entry.update(status='failed', error_type=type(e).__name__, error=str(e)[:800])
            raise
        finally:
            entry['seconds'] = time.time() - begin
            calls.append(entry)
            dump(out / 'api_calls.json', calls)
    pipeline.engine.model_manager.call_glm_api = call
    dump(out / 'model_config.json', {'model': config.model.glm_model_name, 'temperature': .1,
         'max_tokens': config.generation.max_new_tokens, 'input': 'same original video bytes across methods',
         'sdk': 'zai', 'timeout_seconds': 90, 'sdk_retries': 0})
    records, systemic_error = [], None
    for gt in manifest['items']:
        prepared = None
        for mode in MODES:
            base = {k: gt[k] for k in ('video_id', 'gt_symbols', 'gt_symbol_ids', 'gt_dimension_code', 'kb_coverage')}
            base['mode'] = mode
            path = out / 'predictions' / gt['video_id'] / (mode + '.json')
            if mode in {'image', 'multimodal'} and not manifest['eligible_references']:
                base.update(status='blocked_material', reason='全部参考图未审核且use_for_retrieval=False；需要审核并启用真实图片')
            elif path.is_file() and json.loads(path.read_text()).get('status') == 'completed':
                base = json.loads(path.read_text())
            elif systemic_error:
                base.update(status='blocked_runtime', reason=systemic_error)
            else:
                print(f"RUN {gt['video_id']}/{mode}", flush=True)
                try:
                    vid = str(ROOT / gt['video_path'])
                    evidence_path = out / 'predictions' / gt['video_id'] / 'scene.json'
                    if mode != 'free' and prepared is None:
                        if evidence_path.is_file():
                            prepared = json.loads(evidence_path.read_text())
                        else:
                            raw = pipeline.engine.annotate_video(vid, prompt=STRUCTURED_SCENE_PROMPT)
                            scene = normalize_scene(raw)
                            prepared = {'scene_description_raw': raw, 'scene_description': retrieval_text(scene, [], reviewed=False),
                                        'structured_scene': scene, 'scene_evidence_version': 'structured_v1',
                                        'text_recognition': {'status': 'disabled', 'calls': 0, 'items': []}}
                            dump(evidence_path, prepared)
                    pipeline.retriever = (MultimodalCulturalRetriever(kb=kb, fusion_alpha=0 if mode == 'image' else .5)
                                          if mode in {'image', 'multimodal'} else KeywordCulturalRetriever(kb))
                    trace_dir = out / 'traces' / gt['video_id'] / mode
                    trace = pipeline.run(vid, use_kb=mode != 'free', controlled=False,
                                        out_dir=str(trace_dir), tag=mode, prepared_evidence=prepared if mode != 'free' else None)
                    dump(trace_dir / 'trace.json', trace)
                    c = trace['final_c_layer']
                    if not c.get('core_symbol'):
                        raise ValueError('C层核心符号解析失败，不能作为unknown或正确结果')
                    correct = score_prediction(c['core_symbol'], c['unknown_symbol'], gt, kb)
                    candidate_ids = [x['symbol_id'] for x in trace.get('topk_candidates', [])]
                    hit = bool(set(candidate_ids) & set(gt['gt_symbol_ids']))
                    base.update(status='completed', pred_symbol=c['core_symbol'], pred_dimension=c['dimension'],
                                unknown_symbol=c['unknown_symbol'], symbol_correct=correct,
                                dimension_correct=dimension_hit(c['dimension'], gt['gt_dimension_code']),
                                topk_candidates=trace.get('topk_candidates', []), recall_at_5=hit if mode != 'free' and gt['gt_symbol_ids'] else None,
                                seconds=trace['total_seconds'], error_type='' if correct else
                                ('evidence_insufficient' if c['unknown_symbol'] else 'retrieval_miss' if mode != 'free' and not hit else 'entity_confusion_or_generation'),
                                trace_path=str((trace_dir / 'trace.json').relative_to(ROOT)))
                except Exception as e:
                    base.update(status='failed', error_type=type(e).__name__, error=str(e)[:1000])
                    # Infrastructure failures must not generate 60 repeated requests.
                    if any(t in str(e).lower() for t in ('connection', 'connect', '401', '403', '429', '余额', '认证', 'timeout', '1113', '1002')):
                        systemic_error = '基础模型调用受阻：' + type(e).__name__ + '；详情见api_calls.json'
            dump(path, base)
            records.append(base)
            report(out, manifest, records, kb)
    return records


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir', default='experiments/innovation2/results/four_method_accuracy_20261119')
    p.add_argument('--prepare-only', action='store_true')
    args = p.parse_args()
    out = ROOT / args.output_dir
    kb = SymbolKnowledgeBase()
    manifest_path = out / 'manifest.json'
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text())
        for name, expected in manifest['frozen_hashes'].items():
            if sha(ROOT / name) != expected:
                raise RuntimeError(f'Frozen input changed: {name}; use a new output directory')
    else:
        manifest = prepare(out, kb)
    print(f"Prepared {manifest['n_videos']} videos; eligible references={manifest['eligible_references']}", flush=True)
    if not args.prepare_only:
        run(out, manifest, kb)


if __name__ == '__main__':
    main()
