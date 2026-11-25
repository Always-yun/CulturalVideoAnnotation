"""Independent source/generated keyframe consistency evaluation, existing pairs only."""
import base64
import csv
import json
import sys
from pathlib import Path
import four_group_pipeline as p

OUT=p.BASE/'combined_results'

def main():
    sys.path.insert(0,str(p.ROOT))
    from src.models.model_manager import ModelManager
    manager=ModelManager()
    tasks={t['task_id']:t for t in p.protocol()['tasks']}
    results=[]
    for v in p.read(p.RUN/'generation_manifest.json'):
        t=tasks[v['task_id']]; source=p.evidence(t,'source'); generated=p.evidence(t,v['video_id'])
        if not source or not generated:continue
        prompt=('第一张为原视频50%关键帧，第二张为纯文生视频50%关键帧。评价标准版本semantic_v2：'
            '没有向生成模型提供图片，不要求复现原图。仅判断主要主体、核心视觉形态、大致场景关系与总体效果。'
            '允许视角、机位、构图、主体位置与尺度、背景建筑/装饰细节、光照、色彩和画风不同；这些差异本身不得降级。'
            'Match=主要主体正确且核心形态、大致场景效果相符，即使细节与视角不同也应通过；'
            'Partial=主体类别正确且部分核心特征相符，但关键结构、重要主体关系或核心场景存在明显缺失/错误；'
            'Mismatch=主要主体错误、关键主体缺失或核心形态严重偏离，不能仅因构图背景不同判Mismatch；'
            'Uncertain=图片证据不足以判断。不得根据单帧推断打斗、点火、升空或镜头运动。'
            '禁止以是否知道地标名称替代图像比较。只输出严格JSON：'
            '{"verdict":"Match/Partial/Mismatch/Uncertain","evidence":"明确指出两张图相同与不同之处"}。')
        request={'video_id':v['video_id'],'task_id':v['task_id'],'group':v['group'],
                 'source':source,'generated':generated,'prompt':prompt}
        file=OUT/'keyframe_machine_semantic_v2'/f"{v['video_id']}_{p.stable(request)[:16]}.json"
        if file.exists():result=p.read(file)
        else:
            content=[{'type':'text','text':prompt}]
            for e in [source,generated]:
                for frame in e['frames']:
                    content.append({'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+base64.b64encode((p.ROOT/frame['frame_file']).read_bytes()).decode()}})
            result={'request':request,'model':manager.config.model.glm_model_name,'temperature':0,'parse_ok':False}
            try:
                raw=manager.call_glm_api([{'role':'user','content':content}],temperature=0)
                result['raw_response']=raw
                text=raw.strip()
                if text.startswith('```'):text='\n'.join(text.splitlines()[1:-1])
                parsed=json.loads(text)
                assert parsed['verdict'] in p.FORMS
                result.update(parsed=parsed,parse_ok=True)
            except Exception as e:result['error']=type(e).__name__
            p.write(file,result)
        results.append((v,result,file))
    with (OUT/'keyframe_consistency_ratings.csv').open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
    for v,r,file in results:
        if not r['parse_ok']:continue
        row=next(x for x in rows if x['video_id']==v['video_id'])
        row.update(evaluator='AI',keyframe_consistency=r['parsed']['verdict'],evidence=r['parsed']['evidence'],
                   source_timestamp=r['request']['source']['frames'][0]['actual_sec'],
                   generated_timestamp=r['request']['generated']['frames'][0]['actual_sec'],status='rated_semantic_v2')
    p.table(OUT/'keyframe_consistency_ratings.csv',rows,fields)
    rated={r['video_id']:r for r in rows if r['keyframe_consistency']}
    with (OUT/'ai_video_results.csv').open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f);fields=reader.fieldnames;ai=list(reader)
    for r in ai:
        if r['video_id'] in rated:r.update(keyframe_consistency=rated[r['video_id']]['keyframe_consistency'],keyframe_consistency_status='rated_semantic_v2')
    p.table(OUT/'ai_video_results.csv',ai,fields)
    summary=p.read(OUT/'summary.json');groups={}
    for g in p.GROUPS:
        block=[r for r in rows if r['group_id']==g and r['keyframe_consistency']]
        groups[g]={'rated':len(block),'counts':{a:sum(r['keyframe_consistency']==a for r in block) for a in sorted(p.FORMS)}}
    summary['independent_keyframe_consistency']={'scope':'batch2 existing original pairs only','groups':groups,'missing_batch1':20,'rubric_version':'semantic_v2','rubric_revision':'User requested revised semantic criterion after inspecting strict_v1 results; all 20 pairs rerated uniformly','strict_v1_archive':'history/keyframe_strict_v1/keyframe_consistency_ratings.csv','criteria':'Correct main subject and core form/scene effect sufficient for Match; viewpoint/composition/scale/background/lighting differences alone do not downgrade'}
    p.write(OUT/'summary.json',summary)
    print(json.dumps(groups,ensure_ascii=False))

if __name__=='__main__':main()
