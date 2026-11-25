"""Import the user's 20-video human review without changing AI/reference answers."""
import csv
import json
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'experiments/innovation1/four_group_v2/human_user_20261125'
DATA = '''T01 G1 Y N Y N N N Y
T01 G2 Y N Y N N N Y
T01 G3 Y Y Y Y Y Y Y
T01 G4 Y Y Y Y Y Y Y
T04 G1 Y U Y Y N Y Y
T04 G2 Y U Y Y N Y Y
T04 G3 Y U Y Y N Y Y
T04 G4 Y U Y Y N Y Y
T06 G1 N N N N N Y Y
T06 G2 N N Y N N Y Y
T06 G3 Y Y Y ONE_CORRECT M Y Y
T06 G4 Y Y Y ONE_CORRECT M Y Y
T07 G1 Y Y Y N N Y Y
T07 G2 Y Y Y Y N Y Y
T07 G3 Y Y Y Y N Y Y
T07 G4 Y Y Y Y M Y Y
T10 G1 N N N N N N Y
T10 G2 N N N N N N Y
T10 G3 Y Y Y N Y Y Y
T10 G4 Y Y Y Y Y Y Y'''

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows=[]
    mapping={'Y':'Yes','N':'No','U':'Uncertain','ONE_CORRECT':'No'}
    form={'Y':'Match','N':'Mismatch','M':'Partial'}
    for line in DATA.splitlines():
        tid,g,*values=line.split()
        row={'task_id':tid,'group_id':g,'generated_video_id':f'{tid}-{g}',
             'manifest_video_id':f'{tid}_{g}_r01','rater_id':'not_provided',
             'source':'user_supplied_human_review_2026-11-25'}
        for i,value in enumerate(values[:4],1):
            row[f'F{i}']=mapping[value]
            row[f'F{i}_raw']='一个对一个不对' if value=='ONE_CORRECT' else value
        row.update(overall_form=form[values[4]],overall_form_raw=values[4],
                   camera_CMA=mapping[values[5]],conditions_TWA=mapping[values[6]])
        row['fact_yes_rate']=sum(row[f'F{i}']=='Yes' for i in range(1,5))/4
        rows.append(row)
    with (OUT/'human_ratings.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    groups={}
    for g in ['G1','G2','G3','G4']:
        block=[r for r in rows if r['group_id']==g]
        groups[g]={'tasks':len(block),
            'fact_yes_rate':sum(r['fact_yes_rate'] for r in block)/len(block),
            'fact_answer_counts':dict(Counter(r[f'F{i}'] for r in block for i in range(1,5))),
            'overall_form_counts':dict(Counter(r['overall_form'] for r in block)),
            'camera_CMA_yes_rate':sum(r['camera_CMA']=='Yes' for r in block)/len(block),
            'conditions_TWA_yes_rate':sum(r['conditions_TWA']=='Yes' for r in block)/len(block),
            'repeat_sd':None}
    summary={'source':'user_supplied_human_review_2026-11-25','rater_id':None,
        'status':'human_generated_video_review_received; source_reference_answers_still_pending',
        'rules':{'overall':'Y=Match,N=Mismatch,M=Partial',
                 'facts':'Y=Yes,N=No,U=Uncertain; Uncertain stays in denominator',
                 'T06-F4':'一个对一个不对 => No because both identities are required; raw text retained',
                 'aggregation':'one sample per task/group, then equal task average',
                 'conditions_TWA':'retained as user composite field, not split into subject/scene/weather'},
        'groups':groups,'details':rows}
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(groups,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
