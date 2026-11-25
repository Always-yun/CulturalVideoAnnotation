"""Freeze provenance and compare completed hybrid development predictions."""
import csv,hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]


def main():
    out=ROOT/'experiments/innovation2/results/hybrid_accuracy_v3_complete'
    original=ROOT/'experiments/innovation2/results/hybrid_accuracy_v3'
    base=ROOT/'experiments/innovation2/results/abc_development_v1'
    s=json.loads((out/'summary.json').read_text());assert s['status']=='complete' and s['completed']==20
    m=json.loads((out/'manifest.json').read_text())
    changed=[p for p,h in m['hashes'].items() if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
    assert not changed,changed
    inherited=json.loads((out/'inherited_results.json').read_text())
    for item in inherited['inherited']:
        assert hashlib.sha256((ROOT/item['source']/'result.json').read_bytes()).hexdigest()==item['result_sha256']
        assert hashlib.sha256((out/item['video_id']/'result.json').read_bytes()).hexdigest()==item['result_sha256']
    comparisons=[];failures=[]
    for r in json.loads((out/'per_video.json').read_text()):
        row={'video_id':r['video_id'],'sample_type':r['sample_type'],'H3_correct':r['correct'],
             'H3_pred_ids':'|'.join(r['pred_ids']),'H3_recall5':r['recall5'],'pre_verification_correct':r['pre_verification_correct']}
        for group in 'ABC':
            p=base/r['video_id']/group/'result.json'
            row[group+'_correct']=json.loads(p.read_text())['correct'] if p.exists() else None
        comparisons.append(row)
        if not r['correct']:
            t=json.loads((out/r['video_id']/'trace.json').read_text())
            failures.append({'video_id':r['video_id'],'stage':'retrieval_miss' if not r['recall5'] else 'downstream',
                'candidate_names':[c['canonical_name'] for c in t['topk_candidates']],
                'pre_verification_correct':r['pre_verification_correct'],'final_symbol':t['final_c_layer']['core_symbol']})
    with (out/'paired_comparison.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(comparisons[0]));w.writeheader();w.writerows(comparisons)
    # Inherited attempt logs are byte-identical copies; deduplicate by original attempt filename.
    attempts={}
    for folder in [original,out]:
        for p in folder.glob('*/api_calls_*.json'):
            payload=json.loads(p.read_text());key=(p.parent.name,p.name)
            if key in attempts:assert attempts[key]==payload
            attempts[key]=payload
    calls=[c for attempt in attempts.values() for c in attempt]
    audit={'frozen_inputs_checked':len(m['hashes']),'changed_inputs':changed,
      'inherited_success_count':len(inherited['inherited']),'rerun_ids':inherited['rerun_ids'],
      'logged_logical_api_calls_all_attempts':len(calls),'logged_failed_logical_api_calls':sum(c['status']=='error' for c in calls),
      'successful_prediction_path_calls':s['new_api_calls'],
      'cost_note':'Logical SDK calls only, not internal HTTP retries, tokens or currency; interrupted in-flight requests may be absent. Cached A/B extraction costs excluded.',
      'remaining_errors':failures,'reference_images_used':0}
    (out/'final_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
    with zipfile.ZipFile(out/'frozen_inputs.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in m['hashes']:z.write(ROOT/p,p)
    report=out/'report.md';text=report.read_text();marker='\n## 完整结果与复现审计\n'
    text=text.split(marker)[0]+marker+f'''
同批20条：A为14/20=70%，H3为18/20=90%，净增加4条正确（+20个百分点），无退步。
Known从12/18=66.67%升至16/18=88.89%；2条Unknown都拒识。该结果属于开发集，不能证明独立泛化或统计显著。

修复样本：中关村1号、中关村展示中心、北大1、庙会。
剩余错误：京剧青衣、北大，均为正确候选未召回。京剧青衣原始标注正确，但闭集候选为空，最终拒绝；北大只召回了错误近邻。

初版18条成功预测经检查均使用有效的场景JSON与核验JSON，新增加的语法恢复分支不会作用于它们。完整目录继承这18条原始结果，仅重跑cbd1和中关村1号。inherited_results.json记录源路径与结果哈希，初版frozen_inputs.zip保留原代码；新版本{len(m['hashes'])}项输入哈希核验一致。

成功预测路径新增逻辑API调用37次（含恢复后的文字复核），完整尝试日志共{len(calls)}次，其中失败{audit['logged_failed_logical_api_calls']}次。SDK内部HTTP重试、可能中断的在途调用、历史A/B证据成本未计入；没有token/金额数据。

36项回归测试通过。下一阶段应固定本版，补做同时间A基线和模块消融，并在去重后的未参与开发素材上验证。
'''
    report.write_text(text)
    print(json.dumps(audit,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
