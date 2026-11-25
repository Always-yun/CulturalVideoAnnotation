import csv
import json
import re
from pathlib import Path
from collections import Counter

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'experiments/innovation1'
SOURCE=Path('/home/aws/.codex/attachments/39c441d8-7fb2-4d4a-bf45-2614d40fc038/已粘贴的文本.txt')

def main():
    mapping={r['anon_id']:r for r in json.loads((BASE/'t2v_cultural_taskset/human_eval/anonymous_mapping.json').read_text())['mapping']}
    result={};raw=[]
    for line in SOURCE.read_text(encoding='utf-8-sig').splitlines()[1:]:
        cols=line.split('\t')
        if len(cols)<7 or not cols[1].strip():continue
        filename,anon,tid,item,*rest=cols
        m=mapping[anon.strip()]
        assert tid.strip()==m['task_id']
        if filename.strip():assert filename.strip()==m['file']
        score=cols[-1].strip();key=score.lower()
        norm={'y':'Yes','yes':'Yes','n':'No','no':'No','u':'Uncertain','uncertain':'Uncertain','match':'Match','mismatch':'Mismatch','partial':'Partial'}.get(key)
        if key=='par':norm='Partial'
        if key=='mis':norm='Mismatch'
        if norm is None:raise ValueError(f'Unknown score {anon} {item}: {score!r}')
        r=result.setdefault(anon,{'batch':'batch1','task_id':m['task_id'],'group_id':m['group_id'],'video_id':f"{m['task_id']}_{m['group_id']}_r01",'rater_id':'not_provided'})
        fact=re.search(r'局部事实-F([1-4])',item)
        field=f'F{fact[1]}' if fact else ('overall_form' if '整体' in item else ('camera_CMA' if '镜头' in item else 'conditions_TWA'))
        if field=='overall_form':norm={'Yes':'Match','No':'Mismatch'}.get(norm,norm)
        if field in r:raise ValueError(f'Duplicate {anon}/{field}')
        r[field]=norm;raw.append({'anon_id':anon,'file':m['file'],'item':item,'raw_score':score,'normalized':norm})
    assert len(result)==20
    rows=[]
    for r in result.values():
        assert all(k in r for k in ['F1','F2','F3','F4','overall_form','camera_CMA','conditions_TWA'])
        r['fact_yes_rate']=sum(r[f'F{i}']=='Yes' for i in range(1,5))/4
        r.update(keyframe_consistency='',keyframe_consistency_status='pending_original_video_pair')
        rows.append(r)
    out=BASE/'four_group_v2/human_batch1_20261125';out.mkdir(exist_ok=True)
    (out/'ratings.json').write_text(json.dumps({'source':str(SOURCE),'raw':raw,'details':rows},ensure_ascii=False,indent=2)+'\n')
    target=BASE/'combined_results/human_video_results.csv'
    with target.open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f);fields=reader.fieldnames;existing=[r for r in reader if r['batch']!='batch1']
    combined=sorted(existing+rows,key=lambda r:(r['task_id'],r['group_id']))
    with target.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(combined)
    p=BASE/'combined_results/summary.json';summary=json.loads(p.read_text())
    summary['human_batch1']='20 supplied human video reviews imported 2026-11-25'
    groups={}
    for g in ['G1','G2','G3','G4']:
        b=[r for r in combined if r['group_id']==g]
        groups[g]={'tasks':len(b),'fact_yes_rate':sum(float(r['fact_yes_rate']) for r in b)/len(b),'overall_form_counts':dict(Counter(r['overall_form'] for r in b)),'camera_CMA_yes_rate':sum(r['camera_CMA']=='Yes' for r in b)/len(b),'conditions_TWA_yes_rate':sum(r['conditions_TWA']=='Yes' for r in b)/len(b)}
    summary['human_combined']=groups;p.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(groups,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
