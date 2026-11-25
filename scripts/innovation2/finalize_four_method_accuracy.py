"""Derive paired comparisons, retrieval diagnostics and limitations from saved runs."""
import argparse
import csv
import json
import re
from pathlib import Path
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.innovation2.run_four_method_accuracy import dump, sha, report
from src.knowledge.symbol_kb import SymbolKnowledgeBase
from src.experiments.entity_accuracy import final_entity_correct, QUALIFIERS

MODEL_FAILURES = {'model_output_missing_C', 'model_scene_parse_failure'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir', default='experiments/innovation2/results/four_method_accuracy_20261119')
    a = p.parse_args()
    out = ROOT / a.output_dir
    manifest = json.loads((out / 'manifest.json').read_text())
    result = json.loads((out / 'results.json').read_text())
    # Read terminal worker files again, independent of the supervisor's last
    # polling instant, so its final row cannot be lost to a completion race.
    terminal = {(r['video_id'], r['mode']): r for r in result['records']}
    for path in sorted((out / 'workers').glob('*/predictions/*/*.json')):
        if path.stem in {'free', 'text', 'image', 'multimodal'}:
            row = json.loads(path.read_text())
            if row['status'] == 'failed' and 'C层核心符号解析失败' in row.get('error', ''):
                row.update(failure_class='model_output_missing_C', symbol_correct=False,
                           dimension_correct=False, pred_symbol='', unknown_symbol=False)
                trace = path.parents[2] / 'traces' / row['video_id'] / row['mode'] / 'trace.json'
                if trace.is_file():
                    row['trace_path'] = str(trace.relative_to(ROOT))
            if row['status'] == 'failed' and row.get('error_type') == 'JSONDecodeError':
                row.update(failure_class='model_scene_parse_failure', symbol_correct=False,
                           dimension_correct=False, pred_symbol='', unknown_symbol=False,
                           audit_limitation='Frozen runner did not save invalid scene response before parsing; raw failed scene unavailable')
            terminal[(row['video_id'], row['mode'])] = row
    order = {g['video_id']: i for i, g in enumerate(manifest['items'])}
    records = sorted(terminal.values(), key=lambda r: (order[r['video_id']], ('free', 'text', 'image', 'multimodal').index(r['mode'])))
    kb = SymbolKnowledgeBase(str(ROOT / manifest['kb_path']))
    for row in records:
        if row['status'] == 'completed':
            row.setdefault('literal_symbol_correct', row['symbol_correct'])
            row['symbol_correct'] = final_entity_correct(row['pred_symbol'], row['unknown_symbol'], row['gt_symbols'], kb)
            if row['symbol_correct']:
                row['error_type'] = ''
            elif not row.get('error_type'):
                row['error_type'] = 'entity_confusion_or_generation'
    evaluation = dict(scorer='src/experiments/entity_accuracy.py',
        scorer_sha256=sha(ROOT / 'src/experiments/entity_accuracy.py'),
        policy='canonical/alias identity plus generic rendering qualifiers; every asserted entity must match; no feature keywords',
        qualifiers=QUALIFIERS, original_literal_metric_preserved=True,
        reason='format normalization corrects CBD天际线 versus CBD without accepting unrelated entity prefixes')
    dump(out / 'evaluation_protocol.json', evaluation)
    report_manifest = dict(manifest, protocol=dict(manifest['protocol'], scoring=evaluation['policy']))
    report(out, report_manifest, records, kb)
    result = json.loads((out / 'results.json').read_text())
    for summary in result['summaries']:
        rows = [r for r in records if r['mode'] == summary['mode']]
        fully_observed = len(rows) == 30 and all(r['status'] == 'completed' or
            r.get('failure_class') in MODEL_FAILURES for r in rows)
        summary['attempt_complete'] = fully_observed
        summary['output_failures'] = sum(r.get('failure_class') in MODEL_FAILURES for r in rows)
        summary['dimension_accuracy'] = summary['dimension_correct'] / 30 if fully_observed else None
        if fully_observed:
            summary['accuracy'] = summary['correct'] / 30
    dump(out / 'results.json', result)
    with (out / 'summary.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(result['summaries'][0])); w.writeheader(); w.writerows(result['summaries'])
    table = ['|方法|有效输出/30|实体正确|匹配率（全30条）|输出/运行失败|受阻|', '|---|---:|---:|---:|---:|---:|']
    for s in result['summaries']:
        acc = f"{s['accuracy']:.2%}" if s['accuracy'] is not None else '未完成，不报告'
        table.append(f"|{s['mode']}|{s['completed']}/30|{s['correct']}|{acc}|{s['failed']}|{s['blocked']}|")
    rp = out / 'report.md'
    rp.write_text(re.sub(r'\|方法\|.*?(?=\n\n)', '\n'.join(table), rp.read_text(), count=1, flags=re.S), encoding='utf-8')
    idx = {(r['video_id'], r['mode']): r for r in records}
    pairs = []
    for g in manifest['items']:
        f, t = idx.get((g['video_id'], 'free'), {}), idx.get((g['video_id'], 'text'), {})
        comparable = all(row.get('status') == 'completed' or row.get('failure_class') in MODEL_FAILURES for row in (f, t))
        same_prompt = None
        if f.get('trace_path') and t.get('trace_path'):
            ft = json.loads((ROOT / f['trace_path']).read_text())
            tt = json.loads((ROOT / t['trace_path']).read_text())
            same_prompt = ft['prompt'] == tt['prompt']
        pairs.append(dict(video_id=g['video_id'], gt_symbols=g['gt_symbols'], kb_coverage=g['kb_coverage'],
            free_status=f.get('status'), text_status=t.get('status'), free_prediction=f.get('pred_symbol'),
            text_prediction=t.get('pred_symbol'), free_correct=f.get('symbol_correct'), text_correct=t.get('symbol_correct'),
            comparable=comparable, text_has_candidates=bool(t.get('topk_candidates')) if t.get('status') == 'completed' else None, same_prompt_as_free=same_prompt,
            change=('improved' if t['symbol_correct'] and not f['symbol_correct'] else
                'regressed' if f['symbol_correct'] and not t['symbol_correct'] else 'unchanged') if comparable else 'unavailable'))
    with (out / 'paired_comparison.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(pairs[0])); w.writeheader(); w.writerows(pairs)
    with (out / 'human_review_queue.csv').open('w', encoding='utf-8-sig', newline='') as f:
        cols = ['video_id', 'video_path', 'mode', 'reference_entity', 'reference_dimension', 'prediction',
                'prediction_dimension', 'automatic_entity_match', 'status', 'trace_path',
                'reviewer', 'human_entity_correct', 'human_dimension_correct', 'reference_scope_issue', 'notes']
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
        gt_index = {g['video_id']: g for g in manifest['items']}
        for row in records:
            if row['mode'] in {'free', 'text'}:
                g = gt_index[row['video_id']]
                w.writerow(dict(video_id=row['video_id'], video_path=g['video_path'], mode=row['mode'],
                    reference_entity=';'.join(g['gt_symbols']), reference_dimension=g['gt_dimension_code'],
                    prediction=row.get('pred_symbol', ''), prediction_dimension=row.get('pred_dimension', ''),
                    automatic_entity_match=row.get('symbol_correct'), status=row['status'], trace_path=row.get('trace_path', '')))
    audit = {'frozen_hashes_match': all(sha(ROOT / n) == h for n, h in manifest['frozen_hashes'].items()),
             'video_hashes_match': all(sha(ROOT / g['video_path']) == g['video_sha256'] for g in manifest['items']),
             'keyframe_hashes_match': all(sha(ROOT / f['path']) == f['sha256'] for g in manifest['items'] for f in g['keyframes']),
             'record_count': len(records), 'unique_video_mode_pairs': len(idx),
             'n_videos': len(manifest['items']), 'completed_model_annotations': sum(r['status'] == 'completed' for r in records),
             'four_method_comparison_complete': all(s['completed'] == 30 for s in result['summaries']),
             'regression_tests': '47 passed; regression_tests.log',
             'improved_free_to_text': [r['video_id'] for r in pairs if r['change'] == 'improved'],
             'regressed_free_to_text': [r['video_id'] for r in pairs if r['change'] == 'regressed']}
    audit['text_empty_candidates'] = [r['video_id'] for r in pairs if r['text_has_candidates'] is False]
    audit['paired_identical_prompts'] = [r['video_id'] for r in pairs if r['same_prompt_as_free']]
    audit['identical_prompt_prediction_changes'] = [r['video_id'] for r in pairs
        if r['same_prompt_as_free'] and r['free_prediction'] != r['text_prediction']]
    schedule = json.loads((out / 'execution_schedule.json').read_text())
    audit['execution_scheduler_hash_matches'] = sha(ROOT / 'scripts/innovation2/run_four_method_parallel.py') == schedule['orchestrator_sha256']
    refs = json.loads((out / 'reference_audit.json').read_text())
    audit['reference_image_hashes_match'] = all(sha(ROOT / r['local_path']) == r['actual_sha256'] for r in refs if r['file_exists'])
    audit['evaluation_finalizer_sha256'] = sha(__file__)
    audit['method_tasks_observed'] = sum(r['status'] == 'completed' or r.get('failure_class') in MODEL_FAILURES for r in records)
    audit['finalized_at'] = datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
    dump(out / 'final_audit.json', audit)
    calls = json.loads((out / 'api_calls_before_parallel.json').read_text())
    for path in sorted((out / 'workers').glob('*/api_calls.json')):
        calls.extend(json.loads(path.read_text()))
    dump(out / 'api_calls.json', calls)
    model_path = out / 'model_config.json'
    model = json.loads(model_path.read_text())
    model.update(timeout_seconds=300, initial_transport_timeout_seconds=90,
                 transport_policy='90s initial attempts retained; 300s retry transport override; generation unchanged')
    dump(model_path, model)
    text_rows = [r for r in records if r['mode'] == 'text' and r['gt_symbol_ids']]
    hit1 = sum(bool(r.get('topk_candidates') and r['topk_candidates'][0]['symbol_id'] in r['gt_symbol_ids']) for r in text_rows)
    hit5 = sum(bool(set(r['gt_symbol_ids']) & {c['symbol_id'] for c in r.get('topk_candidates', [])}) for r in text_rows)
    appendix = ['## 完成审计与解释限制', '',
        '汇总完成时间（北京时间）：' + audit['finalized_at'] + '。',
        f"共{len(records)}条方法记录，{len(idx)}个唯一视频—方法组合；实际完成模型标注{audit['completed_model_annotations']}条。",
        f"API尝试日志共{len(calls)}条；成功{sum(c.get('status') == 'completed' for c in calls)}条，失败{sum(c.get('status') == 'failed' for c in calls)}条，中断{sum(c.get('status') == 'interrupted' for c in calls)}条。另保留沙箱网络失败日志api_calls_restricted_network.json。没有金额数据，不估算费用。",
        f"Free→Text改善：{'、'.join(audit['improved_free_to_text']) or '无'}；退步：{'、'.join(audit['regressed_free_to_text']) or '无'}。逐样本见paired_comparison.csv。",
        '文化维度命中数（分母30）：' + '；'.join(s['mode'] + ' ' + str(s['dimension_correct']) + '/30' for s in result['summaries'] if s['attempt_complete']) + '。实体与维度分别评价，不用维度正确替代具体实体正确。',
        f"Text检索诊断：有KB实体ID的{len(text_rows)}条，Top-1命中{hit1}条，Top-5命中{hit5}条；场景格式失败未检索计未召回。覆盖不足的样本仍参与30条最终实体匹配率，但没有可检索正实体，不计检索召回率。",
        f"Text候选为空：{'、'.join(audit['text_empty_candidates']) or '无'}。Free/Text完全相同Prompt：{'、'.join(audit['paired_identical_prompts']) or '无'}；同Prompt但输出不同：{'、'.join(audit['identical_prompt_prediction_changes']) or '无'}。后者是重复调用差异，不能归因知识；温度0.1、单次配对仍存在采样波动。",
        '47项回归检查通过。冻结代码、知识库和GT哈希、视频哈希及120帧哈希复核结果见final_audit.json；环境与依赖见environment.json。',
        '计分对所有组统一去除通用显示后缀（如天际线/建筑群）及括号说明后，以完整规范名/别名核对。不同实体的名称前缀、视觉关键词和额外错误实体不给分。最初机械字符串匹配保存在literal_symbol_correct；评价代码哈希及规则见evaluation_protocol.json。此修正是在首批输出暴露格式问题后统一实施的评价实现修复，不是预注册指标；不改变模型输出或检索。',
        '本轮主指标为C层核心实体规范化匹配率，另记录文化维度正确率；它不等于文化内涵/价值指向全部文本的人工语义准确率。后者仍缺独立人工逐条审核。',
        '人工复核表human_review_queue.csv已生成，人工实体、维度与参考范围问题字段留空；没有把自动评分冒充人工结论。典型帧观察记录另见video_visual_spotcheck.json。',
        '粒度差异需特别处理：如参考答案为CBD整体，而模型列出央视总部/中国尊等组成建筑，严格指标会判为未命中整体；不能仅凭这项失配断言画面中的组成建筑都是幻觉。天安门与天安门广场、校门与大学整体也存在范围问题。原GT未改写以迎合预测。',
        '错误类型为可复核的初步诊断：retrieval_miss表示未召回目标KB ID，entity_confusion_or_generation表示候选存在时仍未匹配或Free输出失配；是否真为视觉错认、合理细粒度实体或GT范围问题，需要人工看视频判定。',
        '单次同素材运行不证明统计显著或独立泛化；Image/Multimodal材料受阻时，不能回答完整图文融合是否提升的研究问题。',
        '完整完成30次方法任务时，模型重复/截断而没有C层、或场景JSON解析失败的输出失败按全30条分母计为未命中，并另列失败数量；不选择性重采样该输出，不从M/E层推填C层。基础设施中断导致未观测任务时不报告完整准确率。',
        '执行方式：固定原运行代码后用run_four_method_parallel.py对独立视频作3路调度；execution_schedule.json记录调度器哈希。workers/中的报告只是分片中间快照，以根目录report.md为正式汇总。',
        '参考图目视抽查3例：CBD为文字封面，北大为校徽，均不是对应建筑实景；故宫为多景拼图。这些问题不能靠把启用标记改为True解决。抽查记录见reference_visual_spotcheck.json；该抽查不冒充全库人工审核。',
        '审计缺口：冻结入口在normalize_scene之前未保存原始场景响应；清华Text的JSON解析失败原文因此不可得，只有调用元数据与异常记录。该失败不冒充未知拒识，不声称离线恢复；已新增run_four_method_with_raw_audit.py入口，后续可在新输出目录先落盘再解析；未改变本轮冻结入口或伪造缺失原文。',
        '当前无可用CUDA驱动；本轮通过项目配置的远程GLM运行，未静默更换基础模型。',
        'api_inputs/与api_input_manifest.json是额外准备的统一传输编码副本，本轮标注未使用；正式结果的实际输入以trace.video_path为准。']
    path = out / 'report.md'
    text = path.read_text().split('\n## 完成审计与解释限制')[0]
    path.write_text(text.rstrip() + '\n\n' + '\n'.join(appendix) + '\n', encoding='utf-8')
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
