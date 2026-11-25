"""Consolidate both actual batches, preserving evidence and missing-value semantics."""
import csv
import json
import statistics
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'experiments/innovation1'
OLD=BASE/'t2v_cultural_taskset'
NEW=BASE/'four_group_v2'
OUT=BASE/'combined_results'

def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def save(p,x): p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def csvsave(p,rows):
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def main():
    OUT.mkdir(exist_ok=True)
    old=read(OLD/'batch1_machine_eval_merged_v1.json')
    conditions={r['video_id']:r for r in read(OLD/'exp3_cma_twa_eval_v1.json')['results']}
    quality={(r['task_id'],r['group_id']):r for r in read(OLD/'vbench_test/batch1_iq_sc_summary.json')['details']}
    facts={r['video_id']:r for r in old['local_facts_eval']['results']}
    rows=[]
    for r in old['overall_form_eval']['results']:
        vid=r['video_id'];tid=r['task_id'];g=r['group_id']
        fs=facts.get(vid,{}).get('facts',[])
        row={'batch':'batch1','task_id':tid,'group_id':g,'video_id':vid+'_r01','evaluator':'AI',
             'fact_yes_rate':sum(f['verdict']=='Yes' for f in fs)/len(fs) if fs else None,
             'fact_count':len(fs),'overall_form':r.get('verdict',r.get('overall_form',r.get('result',{}))),
             'keyframe_consistency':None,'keyframe_consistency_status':'pending_original_video_pair',
             'camera_CMA':conditions[vid]['cma']['verdict'],'conditions_TWA':conditions[vid]['twa']['verdict'],
             'VBench_IQ':quality[tid,g]['imaging_quality_0_100'],'VBench_SC':quality[tid,g]['subject_consistency'],
             'provenance_status':'historical_mapping_unverified; KB_reference_not_source_keyframes'}
        rows.append(row)
    new=read(NEW/'computer_evaluation_summary.json')
    with (NEW/'metrics.csv').open(encoding='utf-8-sig') as f: metrics={r['video_id']:r for r in csv.DictReader(f) if r['evaluator']=='AI'}
    for r in new['details']:
        m=metrics[r['video_id']]
        rows.append({'batch':'batch2','task_id':r['task_id'],'group_id':r['group'],'video_id':r['video_id'],'evaluator':'AI',
            'fact_yes_rate':r['machine_yes_rate'],'fact_count':4,'overall_form':r['overall_form'],
            'keyframe_consistency':None,'keyframe_consistency_status':'pending_separate_rating; existing_overall_form_not_copied',
            'camera_CMA':m['camera_motion'],'conditions_TWA':m['time_weather'],
            'VBench_IQ':float(m['VBench_IQ']),'VBench_SC':float(m['VBench_SC']),
            'provenance_status':'source_answers_and_generation_inputs_pending_human_verification'})
    csvsave(OUT/'ai_video_results.csv',rows)
    human=read(NEW/'human_user_20261125/summary.json')['details']
    hrows=[]
    for r in human:
        hrows.append({'batch':'batch2','task_id':r['task_id'],'group_id':r['group_id'],'video_id':r['manifest_video_id'],
            'rater_id':r['rater_id'],**{f'F{i}':r[f'F{i}'] for i in range(1,5)},
            'fact_yes_rate':r['fact_yes_rate'],'overall_form':r['overall_form'],
            'keyframe_consistency':None,'keyframe_consistency_status':'pending_separate_human_rating',
            'camera_CMA':r['camera_CMA'],'conditions_TWA':r['conditions_TWA']})
    csvsave(OUT/'human_video_results.csv',hrows)
    batch1_human=NEW/'human_batch1_20261125/ratings.json'
    rating=[]
    for r in rows:
        rating.append({'batch':r['batch'],'task_id':r['task_id'],'group_id':r['group_id'],'video_id':r['video_id'],
            'evaluator':'','keyframe_consistency':'','evidence':'','source_timestamp':'','generated_timestamp':'',
            'status':r['keyframe_consistency_status']})
    if not (OUT/'keyframe_consistency_ratings.csv').exists(): csvsave(OUT/'keyframe_consistency_ratings.csv',rating)
    groups={}
    for batch in ['batch1','batch2','combined']:
        groups[batch]={}
        for g in ['G1','G2','G3','G4']:
            block=[r for r in rows if r['group_id']==g and (batch=='combined' or r['batch']==batch)]
            group={'videos':len(block),'warning':'different cultural evidence protocols; descriptive aggregation only'}
            for metric in ['fact_yes_rate','VBench_IQ','VBench_SC']:
                vals=[r[metric] for r in block if r[metric] is not None]
                group[metric]={'mean':statistics.mean(vals) if vals else None,'tasks':len(vals)}
            group['overall_form_counts']={v:sum(r['overall_form']==v for r in block) for v in ['Match','Partial','Mismatch','Uncertain']}
            group['keyframe_consistency']={'rated':0,'mean':None}
            groups[batch][g]=group
    save(OUT/'summary.json',{'groups':groups,'human_batch1':'missing_scores; empty_templates_only',
        'human_batch2':read(NEW/'human_user_20261125/summary.json')['groups'],
        'keyframe_consistency_definition':{'answers':['Match','Partial','Mismatch','Uncertain'],
        'criteria':'Compare source/generated keyframes for subject silhouette, component spatial relations, scene layout and framing/viewpoint. Ignore pixel identity and style-only differences. Assess camera movement only from video.',
        'separate_from':'overall cultural form; no reuse of prior scores'},'repeat_count':1})
    links={'batch1_raw':OLD,'batch2_raw':NEW,'videos_batch1':BASE/'videos/batch1','videos_batch2':BASE/'videos/four_group_v2'}
    for name,target in links.items():
        p=OUT/name
        if not p.exists():p.symlink_to(target,target_is_directory=True)
    report=['# 创新点一：10任务40视频统一实验结果','',
        '第一批T02/T03/T05/T08/T09，第二批T01/T04/T06/T07/T10；每任务四组各一次，共40条实际视频。',
        '','## AI描述性汇总','',
        '|组别|事实Yes率（有效任务）|IQ|SC|','|---|---:|---:|---:|']
    for g,v in groups['combined'].items():
        report.append(f"|{g}|{v['fact_yes_rate']['mean']:.2%}（{v['fact_yes_rate']['tasks']}/10）|{v['VBench_IQ']['mean']:.4f}|{v['VBench_SC']['mean']:.4f}|")
    report += ['', '文化结果仅作描述性合并：第一批使用历史视频/知识库参考图，第二批使用原视频关键帧；第一批T08局部事实未评，因此事实比例每组只覆盖9任务。第一批组别映射历史上仍未独立核验。不可据此宣称10任务统一方案正式结论。',
        '', '## 人工结果', '', '第一批三份评分表均为空，尚不能形成10任务人工合并统计。第二批人工事实Yes率为G1 40%、G2 50%、G3 85%、G4 90%。完整明细见human_video_results.csv。',
        '', '## 独立评价点：关键帧一致性', '',
        '新增独立字段keyframe_consistency，答案Match/Partial/Mismatch/Uncertain。判断原视频与生成视频的主体轮廓、部件空间关系、场景布局、视角构图是否一致。整体文化形态仍单列。现有整体分数不复制成此项，40条均列入待评表keyframe_consistency_ratings.csv；第一批原视频尚未登记，无法补造对照证据。',
        '', '## 文件入口', '',
        'ai_video_results.csv：两批AI逐视频合并；human_video_results.csv：已收到的人工结果；summary.json：分批和合并汇总；keyframe_consistency_ratings.csv：新独立评分项。batch1_raw、batch2_raw和videos_*链接统一访问原始材料，避免复制。原始回复、历史评分和视频保留。']
    (OUT/'RESULTS.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
    if batch1_human.exists():
        from import_batch1_human import main as import_human
        import_human()
    print(f'Combined {len(rows)} AI video records; {len(hrows)} human records; 40 independent keyframe items pending')

if __name__=='__main__':main()
