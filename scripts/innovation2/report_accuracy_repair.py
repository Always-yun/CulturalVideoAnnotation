"""Render honest paired development metrics from persisted repair results."""
import argparse,csv,json,math
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',required=True);a=p.parse_args()
    out=Path(a.output_dir);summary=json.loads((out/'summary.json').read_text());manifest=json.loads((out/'manifest.json').read_text())
    rows=json.loads((out/'per_video.json').read_text())
    lines=['# 准确率修复开发对照','',f"状态：{summary['status']}；完成 {summary['completed']}/{summary['expected']}。",'',
       '固定旧B场景证据，修改背景传递、KB范围核验与实际选择候选核验。阈值保持不变。开发诊断结果，不是独立测试收益。','',
       '|组别|完成|Known准确率|Known误拒率|Unknown错误接受率|Recall@5|API调用数|','|---|---:|---:|---:|---:|---:|---:|']
    fmt=lambda n:'—' if n is None else f'{n:.2%}'
    for g,r in summary['groups'].items():lines.append(f"|{g}|{r['n']}|{fmt(r['known_accuracy'])}|{fmt(r['known_false_reject'])}|{fmt(r['unknown_false_accept'])}|{fmt(r['recall5'])}|{r['api_calls']}|")
    lines += ['','## 同视频配对比较','','|组别|共同视频数|旧版正确|新版正确|修复|退步|','|---|---:|---:|---:|---|---|']
    for g,r in summary['paired'].items():lines.append(f"|{g}|{r['n']}|{r['before_correct']}|{r['after_correct']}|{'、'.join(r['improved']) or '无'}|{'、'.join(r['regressed']) or '无'}|")
    lines += ['','C旧版只完成18条；不得将新版20条总准确率与旧版18条直接比较。',
              '未知样本很少，错误接受率为0不能证明泛化。未开展重复采样，也不声称统计显著。',
              '旧6条校准素材与final31存在一个完全相同的视频（SHA-256），正式论文需去重后重新校准。',
              '模型/API错误应记运行失败，不算正确拒识；早期沙箱失败日志保留，成功重试以result.json为准。']
    (out/'report.md').write_text('\n'.join(lines)+'\n')
    if rows:
        with (out/'per_video.csv').open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print('\n'.join(lines))

if __name__=='__main__':main()
