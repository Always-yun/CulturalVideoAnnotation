#!/usr/bin/env python3
"""Four-group experiment adapter. No network calls except explicit evaluate command."""
import argparse
import base64
import csv
import hashlib
import html
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
import shutil

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'experiments/innovation1'
OLD = BASE / 't2v_cultural_taskset'
RUN = BASE / 'four_group_v2'
GROUPS = ['G1', 'G2', 'G3', 'G4']
ANSWERS = {'Yes', 'No', 'Uncertain'}
FORMS = {'Match', 'Partial', 'Mismatch', 'Uncertain'}

CURRENT_QUESTIONS = {
    'T01': {
        'focus':'陶俑形态、材质、军阵和考古坑道布局',
        'questions':[
            ('T01-F1','视频中是否出现多排整齐排列的人物陶俑面向镜头？','同一画面可见至少两排人物陶俑有序排列，且主体整体朝向镜头或可见正面/侧正面','人物主体清晰，但未形成至少两排有序陶俑军阵，或整体背向镜头','人物过小、严重遮挡，无法判断排列层次或朝向','keyframes'),
            ('T01-F2','视频中的陶俑是否具有古代军士的服饰或甲胄特征？','至少一个主要陶俑可辨认古代军士服饰、发髻或甲胄特征','陶俑主体清晰，但呈现代人物、普通雕像或缺少古代军士造型','服饰和甲胄细节过小、模糊或被遮挡','keyframes'),
            ('T01-F3','视频中的人物雕塑是否呈现明显的陶土材质质感？','主要人物雕塑呈土褐、灰褐等陶土色泽，并具有哑光、粗粝或烧制陶塑表面感','人物清晰但呈真人皮肤、金属、塑料或其他明显非陶土材质','光照、清晰度或画面尺寸不足以判断材质','keyframes'),
            ('T01-F4','视频中的陶俑是否排列在由土质隔墙分隔的长方形坑道内？','可见陶俑位于长方形考古坑道中，坑道之间由土质隔墙分隔','陶俑主体清晰，但位于普通室内地面、广场或没有土质隔墙分隔的空间','坑道边界或隔墙被遮挡，无法判断空间布局','keyframes')]
    },
    'T04': {
        'focus':'传统木质船形、船舱结构和湖面空间关系',
        'overall_reference_note':'四项局部事实全为Yes也只说明符合传统船只特征，不能单独证明准确还原南湖红船；必须另做整体参考图匹配评价。',
        'questions':[
            ('T04-F1','视频中的船只是否具有狭长的传统木质船体？','主要船只呈狭长传统中式船形，并可见木质色泽、纹理或木构外观','船只清晰但为现代快艇、金属船或不具狭长传统木船形态','船体遮挡、过小或材质无法辨认','keyframes'),
            ('T04-F2','船体上方是否存在带有传统中式屋顶的船舱？','船体上方可见连续船舱，船舱顶部具有传统中式坡屋顶、瓦顶或飞檐式轮廓','船体清晰但无有顶船舱，或船舱仅为现代平顶/封闭舱体','船舱顶部未入画、被遮挡或轮廓无法判断','keyframes'),
            ('T04-F3','视频中的船只是否呈现有顶船舱与前后露出船体部分的分段结构？','可同时辨认中部或主要有顶舱段，以及舱体前后至少一端露出的船体部分，形成明确分段','船只清晰但舱体覆盖全部船身，或无法区分舱段与前后船体','视角或遮挡导致船体分段关系无法判断','keyframes'),
            ('T04-F4','视频中是否能够辨认停泊在湖面上的较完整船体轮廓？','船只与湖面接触关系清楚，船体大部分轮廓可见并呈停泊状态','船体明显残缺、离开水面，或主体不是停泊在湖面上的船只','水面关系、船体轮廓或运动状态无法判断','keyframes')]
    },
    'T06': {
        'focus':'皮影人物、传统舞台装饰、两人打斗及人物身份',
        'questions':[
            ('T06-F1','视频中是否出现两个平面剪影式的皮影人物？','同一表演画面可见两个扁平、透光或剪影式皮影人物','主体清晰但不是皮影人物，或只出现一个皮影人物','人物过小、重叠、遮挡或画面模糊，无法判断数量及平面皮影形态','keyframes'),
            ('T06-F2','舞台背景是否出现传统中式建筑图案或亭阁造型？','幕布或舞台装饰中可见传统中式屋顶、门楼、亭阁或相应建筑图案','背景清晰但仅为普通空白幕布、现代建筑或无中式建筑装饰','背景过暗、过曝、遮挡或细节不足','keyframes'),
            ('T06-F3','两个皮影人物是否发生连续的打斗或武打动作？','连续视频中两个皮影人物存在至少两个连续时刻的攻防、挥击、追逐或武打动作变化','人物仅静止、摆姿或彼此没有连续武打互动','片段过短、动作被遮挡、播放异常或无法区分动作连续性','continuous_video'),
            ('T06-F4','视频中的两个皮影人物是否分别具有孙悟空和白骨精的可辨认角色特征？','两个角色可分别凭稳定可见的标志性造型辨认为孙悟空与白骨精，例如孙悟空的猴相/金箍棒及白骨精的女性妖怪或白骨主题造型','两个主体清晰但角色造型不对应孙悟空和白骨精，或只能辨认其中一个角色','缺少足够标志性特征，虽为皮影人物但无法可靠确认两者身份','keyframes')]
    },
    'T07': {
        'focus':'竖直火箭、发射塔架、点火烟焰和升空过程',
        'questions':[
            ('T07-F1','视频中是否出现竖直位于发射工位的大型运载火箭？','可见大型运载火箭竖直立于明确的发射工位或发射平台区域','主体清晰但不是大型运载火箭，或火箭不在发射工位','火箭主体、姿态或工位关系被遮挡而无法判断','keyframes'),
            ('T07-F2','火箭旁是否出现高大的金属桁架发射塔架？','火箭旁可见高度与其相当或更高的金属桁架式发射塔架/勤务塔','火箭周边清晰但不存在高大金属桁架塔架','塔架区域未入画、严重遮挡或结构细节不足','keyframes'),
            ('T07-F3','视频中是否出现火箭底部点火并伴随明显火焰或烟雾的过程？','连续视频中可见火箭底部由未点火到出现明显喷射火焰、烟柱或大量烟雾的点火过程','火箭底部始终无火焰烟雾，或所见烟雾与火箭点火无明确关系','底部被遮挡、片段缺失、解码异常或无法确认点火过程','continuous_video'),
            ('T07-F4','视频中是否呈现火箭从发射工位向上升空的连续变化？','连续视频中火箭相对发射工位发生持续向上的位移，并逐步离开平台或塔架','火箭始终静止在工位，或运动方向不是向上升空','镜头运动、遮挡、片段过短或解码异常导致无法判断相对位移','continuous_video')]
    },
    'T10': {
        'focus':'球形结构、竖向塔身、倾斜支撑和主体空间关系',
        'questions':[
            ('T10-F1','视频中的主要塔楼是否具有多个大小不同的球形结构？','主要塔楼可见至少两个大小不同的球体','塔楼清晰但少于两个球体，或球体大小没有可辨认差异','球体被遮挡、过小或画面裁切导致数量和大小无法判断','keyframes'),
            ('T10-F2','这些球形结构是否沿高耸的竖向塔身分布？','多个球体沿同一高耸竖向塔体上下分布，并形成完整组合关系','球体清晰但未沿竖向塔身组织，或属于彼此无关的建筑','塔身或球体连接关系被遮挡、裁切或无法辨认','keyframes'),
            ('T10-F3','主要塔楼下部是否具有明显的倾斜支撑柱结构？','塔体下部可见明显斜向支撑柱，并与主塔形成承托关系','塔楼下部清晰但只有垂直柱、普通基座或无斜向支撑','塔楼下部未入画、被背景遮挡或细节不足','keyframes'),
            ('T10-F4','东方明珠形态的塔楼是否位于画面中央且明显突出于其他背景建筑？','东方明珠形态塔楼位于画面中央或中央主要区域，是明确视觉焦点，其他高楼仅作背景','塔楼明显偏离主要构图区域，或被其他建筑遮挡且不是视觉焦点','画面裁切、遮挡或构图不清，无法判断主体与背景关系','keyframes')]
    }
}

def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8-sig'))

def write(p, data):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def stable(x):
    return hashlib.sha256(json.dumps(x, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def table(p, rows, fields=None):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields or list(rows[0])); w.writeheader(); w.writerows(rows)

def init():
    if (RUN / 'protocol.json').exists():
        raise ValueError('已有配置，拒绝覆盖人工修改')
    batch = read(OLD / 'batch2_v1/taskset_batch2_v1.json')
    first = read(OLD / 'eval_batch1_input_v3.json')
    names = {'T02':'故宫角楼', 'T03':'遵义会址', 'T05':'福建土楼', 'T08':'首钢大跳台', 'T09':'北京CBD'}
    sources = {'T01':'兵马俑.mp4', 'T04':'南湖红船.mp4', 'T07':'海南文昌发射场.mp4', 'T10':'东方明珠.mp4'}
    tasks = []
    for tid in [f'T{i:02}' for i in range(1, 11)]:
        old = next((t for t in batch['tasks'] if t['task_id'] == tid), None)
        facts = old['facts'] if old else [f for f in first['features'] if f['task_id'] == tid]
        prompts = {}
        for g in GROUPS:
            text = old['groups'][g]['prompt'] if old else ''
            path = RUN / 'descriptions' / tid / f'{g}.txt'
            path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text, encoding='utf-8')
            prompts[g] = {'file':str(path.relative_to(ROOT)), 'source':str((OLD / 'batch2_v1/taskset_batch2_v1.json' if old else OLD / 'eval_batch1_input_v3.json').relative_to(ROOT)), 'status':'pending_human_correction', 'reviewer':None, 'version':None, 'sha256':None, 'target_fact_ids': [f.get('fact_id',f.get('feature_id')) for f in facts] if g in ('G3','G4') else []}
        qs = []
        for f in facts:
            qs.append({'fact_id':f.get('fact_id', f.get('feature_id')), 'question':'画面是否呈现：' + f.get('statement', f.get('feature_description','')) + '？', 'yes_rule':f.get('yes_rule', f.get('yes_criteria')), 'no_rule':f.get('no_rule', f.get('no_criteria')), 'uncertain_rule':f.get('uncertain_rule', f.get('uncertain_criteria')), 'provenance':f, 'reference_answer':None, 'status':'pending_human_verification', 'required':False, 'reviewer':None, 'source_evidence_sha256':None})
        tasks.append({'task_id':tid, 'name':old['canonical_name'] if old else names[tid], 'source_video':str(Path('data/video') / sources[tid]) if tid in sources else None, 'source_note':'T06配置为兔儿爷；皮影戏身份不同，待用户确认是否另建任务' if tid=='T06' else '', 'sampling':{'fractions':[0.5], 'status':'pending_source_review', 'reviewer':None, 'reason':'默认中点；如主体显露/遮挡需补充，在查看生成结果前改为[0.25,0.75]', 'source_sha256':None}, 'conditions':old.get('scene_text') if old else None, 'conditions_status':'pending_human_review', 'equivalence_review':{'status':'pending', 'reviewer':None, 'note':'核对各组基础条件一致及G3/G4文化事实等价，保持各组组织形式'}, 'descriptions':prompts, 'questions':qs})
    write(RUN / 'protocol.json', {'version':'four_group_v2', 'groups':GROUPS, 'repeats':3, 'planned_tasks':10, 'planned_videos':120, 'completed_videos':0, 'technical_layer':'post_generation_only', 'tasks':tasks})
    videos = []
    for t in tasks:
        for g in GROUPS:
            for r in range(1,4):
                videos.append({'video_id':f"{t['task_id']}_{g}_r{r:02}", 'task_id':t['task_id'], 'group':g, 'repeat':r, 'video_file':str((BASE / 'videos/four_group_v2' / f"{t['task_id']}_{g}_r{r:02}.mp4").relative_to(ROOT)), 'description_version':None, 'description_sha256':None, 'video_sha256':None, 'model_config':{'model':None,'seed':None,'seed_supported':None,'resolution':None,'fps':None,'duration_sec':None,'other':None}, 'provenance_status':'pending', 'provenance_evidence':None})
    write(RUN/'generation_manifest.json', videos)
    write(RUN/'history_audit.json', {'status':'not_admitted', 'reason':'旧组别映射未经核实；无人工冻结描述、模型与种子证据；旧评分仅属于原视频', 'files':[{'file':str(p.relative_to(ROOT)), 'sha256':digest(p), 'reuse':'historical_only_pending_input_and_config_verification'} for p in sorted(OLD.glob('*.json'))], 'historical_videos':[{'path':str(p.relative_to(ROOT)), 'sha256':digest(p)} for p in sorted((BASE/'videos/batch1').glob('*.mp4'))]})
    (BASE/'videos/four_group_v2').mkdir(parents=True, exist_ok=True)
    audit()

def protocol():
    x = read(RUN/'protocol.json')
    assert x['groups'] == GROUPS
    assert isinstance(x['repeats'], int) and x['repeats'] >= 1
    assert len(x['tasks']) == x['planned_tasks']
    assert x['planned_videos'] == len(x['tasks']) * len(GROUPS) * x['repeats']
    return x

def sampling_ok(t):
    s=t['sampling']; p=ROOT/(t['source_video'] or '__missing__')
    return s['status']=='confirmed_before_generated_review' and bool(s['reviewer']) and s['fractions'] in ([0.5],[0.25,0.75]) and p.is_file() and s['source_sha256']==digest(p)

def description_ok(t,g):
    d=t['descriptions'][g]; p=ROOT/d['file']
    return d['status']=='frozen' and bool(d['version']) and bool(d['reviewer']) and p.is_file() and bool(p.read_text().strip()) and d['sha256']==digest(p)

def task_ok(t):
    e=t['equivalence_review']
    return sampling_ok(t) and t['conditions_status']=='confirmed' and e['status']=='confirmed' and bool(e['reviewer']) and all(description_ok(t,g) for g in GROUPS) and t['descriptions']['G3']['target_fact_ids']==t['descriptions']['G4']['target_fact_ids']

def admitted(t,v):
    d=t['descriptions'][v['group']]; p=ROOT/v['video_file']; c=v['model_config']
    peers=[p for p in read(RUN/'generation_manifest.json') if p['task_id']==v['task_id'] and p['repeat']==v['repeat']]
    matched=all(p['model_config']==c for p in peers)
    return matched and task_ok(t) and v['provenance_status']=='verified' and bool(v['provenance_evidence']) and p.is_file() and v['video_sha256']==digest(p) and v['description_version']==d['version'] and v['description_sha256']==d['sha256'] and all(c.get(k) is not None for k in ('model','resolution','fps','duration_sec','seed_supported')) and (c.get('seed') is not None or c['seed_supported'] is False)

def audit():
    x=protocol(); vs=read(RUN/'generation_manifest.json'); issues=[]; rows=[]
    expected={(t['task_id'],g,r) for t in x['tasks'] for g in GROUPS for r in range(1,x['repeats']+1)}
    actual=[(v['task_id'],v['group'],v['repeat']) for v in vs]
    if set(actual)!=expected or len(actual)!=len(expected): raise ValueError('生成清单存在缺失、重复或额外组别')
    for t in x['tasks']:
        tid=t['task_id']
        if not t['source_video'] or not (ROOT/t['source_video']).is_file(): issues.append({'task':tid,'item':'source_video','detail':t['source_note'] or '缺原视频'})
        if not sampling_ok(t): issues.append({'task':tid,'item':'sampling','detail':'待仅依据原视频预先确认1/2帧规则、审核人及原视频sha256'})
        if not task_ok(t): issues.append({'task':tid,'item':'descriptions','detail':'待人工纠正冻结、基础条件核对和G3/G4等价核对'})
        for q in t['questions']:
            if q['status']!='confirmed': issues.append({'task':tid,'item':q['fact_id'],'detail':'待原视频模型初答与人工核准；不可直接使用知识库事实为真值'})
    for v in vs:
        t=next(t for t in x['tasks'] if t['task_id']==v['task_id']); ok=admitted(t,v)
        rows.append({'video_id':v['video_id'],'task_id':v['task_id'],'group':v['group'],'repeat':v['repeat'],'video_file':v['video_file'],'file_exists':(ROOT/v['video_file']).is_file(),'eligible':ok,'description_version':v['description_version'],'status':'verified' if ok else 'planned_or_pending_verification'})
    question_rows=[{'task_id':t['task_id'],'evaluation_focus':t.get('evaluation_focus',''),**{k:q[k] for k in ('fact_id','question','yes_rule','no_rule','uncertain_rule','evidence_mode','reference_answer','status','required','reviewer')}} for t in x['tasks'] for q in t['questions']]
    table(RUN/'objective_questions.csv',question_rows)
    write(RUN/'pending.json',issues); table(RUN/'generation_checklist.csv',rows)
    seeds=[]
    for t in x['tasks']:
        for r in range(1,x['repeats']+1):
            block=[v for v in vs if v['task_id']==t['task_id'] and v['repeat']==r]
            configs=[{k:val for k,val in v['model_config'].items() if k!='seed'} for v in block]
            if any(c!=configs[0] for c in configs) or len({v['model_config']['seed'] for v in block})>1: seeds.append(f"{t['task_id']}/r{r}:组间配置或对应种子不一致")
    write(RUN/'audit.json',{'planned':x['planned_videos'],'files_present':sum(r['file_exists'] for r in rows),'verified':sum(r['eligible'] for r in rows),'pending_count':len(issues),'configuration_conflicts':seeds,'unmatched_sources':[str(p.relative_to(ROOT)) for p in sorted((ROOT/'data/video').glob('*')) if str(p.relative_to(ROOT)) not in {t['source_video'] for t in x['tasks']}]})
    print(json.dumps(read(RUN/'audit.json'),ensure_ascii=False))

def extract(video, output, fractions):
    import cv2
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_frames','-show_streams','-show_entries','frame=best_effort_timestamp_time:stream=avg_frame_rate,duration','-of','json',str(video)]))
    pts=[float(f['best_effort_timestamp_time']) for f in probe['frames']]
    count=len(pts)
    if count<1: raise ValueError(f'无法解码 {video}')
    num,den=probe['streams'][0]['avg_frame_rate'].split('/');fps=float(num)/float(den)
    output.mkdir(parents=True,exist_ok=True); records=[]
    if any(b<=a for a,b in zip(pts,pts[1:])): raise ValueError('PTS异常，停止抽帧，不静默使用估计值')
    origin=pts[0]; pts=[p-origin for p in pts]
    duration=float(probe['streams'][0].get('duration') or (pts[-1]+1/fps))
    for fraction in fractions:
        target=duration*fraction; center=min(range(count),key=lambda i:abs(pts[i]-target)); chosen=None; attempts=[]
        # Same bounded fallback for every video: nearest, previous, next (<=0.1s).
        radius=max(1,int(fps*0.1))
        offsets=[0]+[s*d for d in range(1,radius+1) for s in (-1,1)]
        for offset in offsets:
            i=center+offset
            if i<0 or i>=count: continue
            if offset and abs(pts[i]-pts[center])>0.1: continue
            import numpy as np
            raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(video),'-vf',f'select=eq(n\\,{i})','-vsync','0','-frames:v','1','-f','image2pipe','-vcodec','mjpeg','-threads','1','pipe:1'])
            frame=cv2.imdecode(np.frombuffer(raw,dtype=np.uint8),cv2.IMREAD_COLOR)
            if frame is None: raise ValueError('FFmpeg选定帧解码失败')
            gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
            black=float((gray<8).mean())>0.98
            attempts.append({'index':i,'pts_sec':pts[i],'black':black})
            if not black: chosen=i; break
        if chosen is None: raise ValueError('统一邻域内无有效帧；停止并人工登记异常，不按效果挑帧')
        p=output/f'{int(fraction*100):02}.jpg'
        if not cv2.imwrite(str(p),frame): raise ValueError('帧写入失败')
        records.append({'fraction':fraction,'duration_sec':duration,'requested_sec':target,'actual_sec':pts[chosen],'absolute_pts_sec':pts[chosen]+origin,'frame_index':chosen,'frame_file':str(p.relative_to(ROOT)),'sha256':digest(p),'attempts':attempts})
    return {'video_file':str(video.relative_to(ROOT)),'video_sha256':digest(video),'frames':records,'T':{'fps':fps,'decoded_frames':count,'duration_sec':duration,'duration_scope_warning':None if 3<=duration<=5 else 'outside_3_to_5_seconds_review_scope'},'exception_rule':'nearest PTS; black >98% gray<8; previous then next within 0.1s; failure blocks; no aesthetic selection'}

def frames(preview=False):
    x=protocol(); vs=read(RUN/'generation_manifest.json')
    if preview:
        for source in sorted((ROOT/'data/video').glob('*.mp4')):
            matched=next((t['task_id'] for t in x['tasks'] if t['source_video']==str(source.relative_to(ROOT))),None)
            if matched: continue
            folder=RUN/'source_preview/unmatched'/source.stem
            try:
                write(folder/'source.json',extract(source,folder/'source',[0.5]))
            except ValueError as e:write(folder/'source_error.json',{'error':str(e)})

    for t in x['tasks']:
        tid=t['task_id']; source=ROOT/(t['source_video'] or '__missing__')
        if not source.is_file(): continue
        if not preview and not sampling_ok(t): continue
        folder=RUN/('source_preview' if preview else 'keyframes')/tid
        try:
            data=extract(source,folder/'source',t['sampling']['fractions'])
            write(folder/'source.json',data)
        except ValueError as e:
            write(folder/'source_error.json',{'error':str(e)}); continue
        if preview: continue
        for v in vs:
            video=ROOT/v['video_file']
            if v['task_id']!=tid or not video.is_file(): continue
            try:
                generated=extract(video,folder/v['video_id'],t['sampling']['fractions'])
                generated['formal_eligibility']=admitted(t,v)
                generated['eligibility_note']='关键帧可先提取；正式评价仍需冻结描述及核验生成配置'
                write(folder/(v['video_id']+'.json'),generated)
            except ValueError as e: write(folder/(v['video_id']+'_error.json'),{'error':str(e)})
    if preview:
        inventory=[]
        source_paths={t['source_video'] for t in x['tasks']}
        for p in sorted((RUN/'source_preview').rglob('source.json')):
            e=read(p)
            if '/unmatched/' in str(p) and e['video_file'] in source_paths:
                continue
            for f in e['frames']:
                inventory.append({'source_video':e['video_file'],'video_sha256':e['video_sha256'],'duration_sec':e['T']['duration_sec'],'sampling_status':'preview_pending_source_review','fraction':f['fraction'],'requested_sec':f['requested_sec'],'actual_sec':f['actual_sec'],'absolute_pts_sec':f['absolute_pts_sec'],'frame_file':f['frame_file'],'scope_warning':e['T']['duration_scope_warning']})
        if inventory:table(RUN/'source_frame_inventory.csv',inventory)
    else:
        inventory=[]
        for p in sorted((RUN/'keyframes').glob('*/*.json')):
            if p.name.endswith('_error.json'):
                continue
            e=read(p)
            video_id='source' if p.name=='source.json' else p.stem
            for f in e['frames']:
                inventory.append({
                    'task_id':p.parent.name,'video_id':video_id,
                    'video_file':e['video_file'],'video_sha256':e['video_sha256'],
                    'fraction':f['fraction'],'requested_sec':f['requested_sec'],
                    'actual_sec':f['actual_sec'],'absolute_pts_sec':f['absolute_pts_sec'],
                    'frame_index':f['frame_index'],'frame_file':f['frame_file'],
                    'frame_sha256':f['sha256'],
                    'formal_eligibility':e.get('formal_eligibility','source_pending_reference_answer')
                })
        if inventory:
            table(RUN/'keyframe_inventory.csv',inventory)
            cards=['<!doctype html><meta charset="utf-8"><title>当前20条收到视频关键帧</title>',
                   '<p>按任务完整展示原视频与G1—G4的50%关键帧；不按效果筛选。生成输入与模型配置未核验，页面不代表正式评分。</p>']
            for task_id in [t['task_id'] for t in x['tasks']]:
                task=next(t for t in x['tasks'] if t['task_id']==task_id)
                cards.append('<h2>'+html.escape(task_id+' '+task['name'])+'</h2>')
                for row in [r for r in inventory if r['task_id']==task_id]:
                    cards.append('<figure style="display:inline-block;margin:8px"><img width="320" src="../../../'+html.escape(row['frame_file'])+'"><figcaption>'+html.escape(row['video_id'])+' · '+f"{row['actual_sec']:.3f}s"+'</figcaption></figure>')
            (RUN/'cases_received.html').write_text(''.join(cards),encoding='utf-8')

def evidence(t, vid):
    p=RUN/'keyframes'/t['task_id']/(vid+'.json')
    if not sampling_ok(t) or not p.is_file(): return None
    e=read(p)
    if e['video_sha256']!=digest(ROOT/e['video_file']): return None
    if [f['fraction'] for f in e['frames']]!=t['sampling']['fractions']: return None
    if any(digest(ROOT/f['frame_file'])!=f['sha256'] for f in e['frames']): return None
    return e

def reference_ok(t):
    e=evidence(t,'source')
    if not e:
        return False
    video_sha=digest(ROOT/t['source_video']) if any(q['evidence_mode']=='continuous_video' for q in t['questions']) else None
    return all(
        q['status']=='confirmed' and q['reviewer'] and q['reference_answer'] in ANSWERS
        and q['source_evidence_sha256']==(video_sha if q['evidence_mode']=='continuous_video' else stable(e))
        and (not q['required'] or q['reference_answer']=='Yes')
        for q in t['questions']
    )

def requests():
    x=protocol(); vs=read(RUN/'generation_manifest.json'); jobs=[]; temporal_jobs=[]
    for t in x['tasks']:
        e=evidence(t,'source')
        if not e: continue
        jobs.append(make_request(t,'source',e))
        if any(q['evidence_mode']=='continuous_video' for q in t['questions']):
            temporal_jobs.append(make_temporal_request(t,'source',ROOT/t['source_video']))
        for v in vs:
            video=ROOT/v['video_file']
            received_ok=v['task_id']==t['task_id'] and video.is_file() and v.get('video_sha256')==digest(video)
            if received_ok:
                e=evidence(t,v['video_id'])
                if e:
                    job=make_request(t,v['video_id'],e)
                    job['evaluation_status']='provisional_pending_human_reference_and_generation_provenance'
                    jobs.append(job)
                    if any(q['evidence_mode']=='continuous_video' for q in t['questions']):
                        temporal_jobs.append(make_temporal_request(t,v['video_id'],video))
    write(RUN/'evaluation_requests.json',jobs)
    write(RUN/'temporal_evaluation_requests.json',temporal_jobs)
    video_jobs=[]
    for t in x['tasks']:
        temporal=[q for q in t['questions'] if q['evidence_mode']=='continuous_video']
        if temporal:
            video_jobs.append(make_video_request(t,'source',ROOT/t['source_video'],None,temporal,'source_reference'))
        for v in vs:
            if v['task_id']!=t['task_id']:
                continue
            video=ROOT/v['video_file']
            if not video.is_file() or v.get('video_sha256')!=digest(video):
                continue
            desc=t['descriptions'][v['group']]
            desc_path=ROOT/desc['file']
            description=desc_path.read_text(encoding='utf-8').strip() if desc_path.is_file() else ''
            basis='stored_group_description' if description else 'task_conditions_fallback'
            video_jobs.append(make_video_request(t,v['video_id'],video,description or t.get('conditions'),temporal,basis))
    write(RUN/'video_evaluation_requests.json',video_jobs)
    print(f'{len(jobs)} keyframe requests and {len(video_jobs)} continuous-video/condition requests prepared; no API called')

def make_request(t,vid,e):
    questions=[{k:q[k] for k in ('fact_id','question','yes_rule','no_rule','uncertain_rule','evidence_mode')} for q in t['questions'] if q['evidence_mode']=='keyframes']
    source=evidence(t,'source')
    if vid=='source':
        image_note=f'所给{len(e["frames"])}张图片均为原视频关键帧；每题frames数组必须恰有{len(e["frames"])}项。overall_form固定返回Match。'
        source_frames=[]
    else:
        image_note=f'前{len(source["frames"])}张为原视频，后{len(e["frames"])}张为当前生成视频；每题frames数组只填写当前生成视频的逐帧答案，必须恰有{len(e["frames"])}项。'
        source_frames=source['frames']
    content=('仅依据所给关键帧回答客观问题，禁止使用知识推断不可见事实。每事实只计一次。'
             '跨帧Yes与No冲突为Uncertain，Yes+Uncertain为Yes，No+Uncertain为No，全Uncertain为Uncertain。'
             '只返回一个完整JSON对象，不要Markdown，不要解释。overall_form和overall_evidence必须位于facts对象之外。'
             '格式：{"facts":{"事实ID":{"frames":["Yes"],"evidence":"可见依据"}},'
             '"overall_form":"Match/Partial/Mismatch/Uncertain","overall_evidence":"依据"}。'
             +image_note+'整体形态比较轮廓、布局和部件关系；运动不能根据关键帧判断。问题：'+json.dumps(questions,ensure_ascii=False))
    return {'id':f"{t['task_id']}_{vid}",'task_id':t['task_id'],'video_id':vid,'question_ids':[q['fact_id'] for q in questions],'question_sha256':stable(questions),'reference_sha256':stable(t['questions']),'evidence_sha256':stable(e),'source_evidence_sha256':stable(source),'text':content,'source_frames':source_frames,'target_frames':e['frames']}

def make_temporal_request(t,vid,video):
    questions=[{k:q[k] for k in ('fact_id','question','yes_rule','no_rule','uncertain_rule','evidence_mode')} for q in t['questions'] if q['evidence_mode']=='continuous_video']
    return {
        'id':f"{t['task_id']}_{vid}_continuous_video",'task_id':t['task_id'],'video_id':vid,
        'video_file':str(video.relative_to(ROOT)),'video_sha256':digest(video),
        'question_ids':[q['fact_id'] for q in questions],'question_sha256':stable(questions),
        'questions':questions,
        'instruction':'必须观看完整连续视频判断过程变化；不得根据单张关键帧判断。按每题Yes/No/Uncertain输出并保留证据时间段。'
    }

def make_video_request(t,vid,video,description,temporal_questions,basis):
    condition_names=[] if vid=='source' else ['subject','scene','time_weather','camera_motion']
    questions=[{k:q[k] for k in ('fact_id','question','yes_rule','no_rule','uncertain_rule')} for q in temporal_questions]
    prompt=(
        '观看完整连续视频后，只依据视频可见内容评价。返回严格JSON：'
        '{"conditions": {评价项: {"verdict":"Yes/No/Uncertain","evidence":"依据","timestamps":"时间段"}},'
        '"temporal_facts": {事实ID: {"verdict":"Yes/No/Uncertain","evidence":"依据","timestamps":"时间段"}}}。'
        '镜头运动必须依据连续变化；无法可靠判断时答Uncertain。'
        f'条件评价项：{json.dumps(condition_names,ensure_ascii=False)}。'
        f'目标描述：{description or "原视频参考，不做条件遵循评分"}。'
        f'时序事实及判据：{json.dumps(questions,ensure_ascii=False)}'
    )
    return {
        'id':f"{t['task_id']}_{vid}_video",'task_id':t['task_id'],'video_id':vid,
        'video_file':str(video.relative_to(ROOT)),'video_sha256':digest(video),
        'condition_names':condition_names,'temporal_question_ids':[q['fact_id'] for q in questions],
        'description_basis':basis,
        'prompt':prompt,'request_sha256':stable({'video_sha256':digest(video),'prompt':prompt})
    }

def merge_answers(values):
    if not values or any(v not in ANSWERS for v in values): raise ValueError('非法逐帧答案')
    definite=set(values)-{'Uncertain'}
    return next(iter(definite)) if len(definite)==1 else 'Uncertain'

def parse(raw,job):
    text=raw.strip()
    if text.startswith('```'): text='\n'.join(text.splitlines()[1:-1])
    try:
        x=json.loads(text)
    except json.JSONDecodeError:
        repaired=None
        for marker in (',"overall_form"',', "overall_form"'):
            if marker in text and text.count('{')==text.count('}')+1:
                repaired=text.replace(marker,'}'+marker,1)
                break
        if repaired is None:
            raise
        x=json.loads(repaired)
    if 'overall_form' in x.get('facts',{}):
        x['overall_form']=x['facts'].pop('overall_form')
        x['overall_evidence']=x['facts'].pop('overall_evidence','')
    expected=set(job['question_ids'])
    if not expected.issubset(x['facts']):
        raise ValueError('缺少预期事实字段')
    unexpected=sorted(set(x['facts'])-expected)
    facts={}
    for fid in job['question_ids']:
        item=x['facts'][fid]
        assert len(item['frames'])==len(job['target_frames']) and isinstance(item['evidence'],str)
        facts[fid]={'answer':merge_answers(item['frames']),'frames':item['frames'],'evidence':item['evidence']}
    assert x['overall_form'] in FORMS
    return {'facts':facts,'overall_form':x['overall_form'],'overall_evidence':x.get('overall_evidence',''),'unexpected_fact_ids_ignored':unexpected}

def evaluate(limit):
    # Reuse existing project API adapter/config; bounded explicit invocation only.
    sys.path.insert(0,str(ROOT))
    from src.models.model_manager import ModelManager
    manager=ModelManager(); jobs=read(RUN/'evaluation_requests.json'); n=0
    for job in jobs:
        p=RUN/'machine'/f"{job['id']}_{stable(job)[:16]}.json"
        if p.exists(): continue
        if n>=limit: break
        images=[]
        for f in job['source_frames']+job['target_frames']:
            images.append({'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+base64.b64encode((ROOT/f['frame_file']).read_bytes()).decode()}})
        result={'request':job,'model':manager.config.model.glm_model_name,'temperature':0,'raw_response':None,'parse_ok':False}
        try:
            fresh=next(t for t in protocol()['tasks'] if t['task_id']==job['task_id'])
            ev=evidence(fresh,job['video_id'])
            expected=make_request(fresh,job['video_id'],ev) if ev else None
            if expected and 'evaluation_status' in job:
                expected['evaluation_status']=job['evaluation_status']
            if not ev or expected!=job: raise ValueError('评价输入已过期')
            result['raw_response']=manager.call_glm_api([{'role':'user','content':[{'type':'text','text':job['text']}]+images}],temperature=0)
            result['parsed']=parse(result['raw_response'],job); result['parse_ok']=True
        except Exception as e: result['error']=type(e).__name__
        write(p,result); n+=1
    print(f'{n} API calls; raw responses retained')

def reparse_machine():
    repaired=0
    current={j['id']:j for j in read(RUN/'evaluation_requests.json')}
    for p in sorted((RUN/'machine').glob('*.json')):
        result=read(p); job=result.get('request',{})
        if current.get(job.get('id'))!=job or not result.get('raw_response'):
            continue
        try:
            result['parsed']=parse(result['raw_response'],job)
            result['parse_ok']=True
            result.pop('error',None)
            write(p,result); repaired+=1
        except Exception as e:
            result['parse_ok']=False; result['error']=type(e).__name__; write(p,result)
    print(f'{repaired} current machine responses parsed')

def parse_video_response(raw,job):
    text=raw.strip()
    if text.startswith('```'):
        text='\n'.join(text.splitlines()[1:-1])
    data=json.loads(text)
    conditions=data.get('conditions',{})
    temporal=data.get('temporal_facts',{})
    if set(conditions)!=set(job['condition_names']):
        raise ValueError('条件评价字段不完整')
    if set(temporal)!=set(job['temporal_question_ids']):
        raise ValueError('时序事实字段不完整')
    for item in list(conditions.values())+list(temporal.values()):
        if item.get('verdict') not in ANSWERS:
            raise ValueError('非法判定值')
    return {'conditions':conditions,'temporal_facts':temporal}

def evaluate_video(limit):
    sys.path.insert(0,str(ROOT))
    from src.models.model_manager import ModelManager
    manager=ModelManager(); jobs=read(RUN/'video_evaluation_requests.json'); n=0
    for job in jobs:
        p=RUN/'machine_video'/f"{job['id']}_{job['request_sha256'][:16]}.json"
        if p.exists():
            continue
        if n>=limit:
            break
        video=ROOT/job['video_file']
        fresh=next((j for j in read(RUN/'video_evaluation_requests.json') if j['id']==job['id']),None)
        result={'request':job,'model':manager.config.model.glm_model_name,'temperature':0,'raw_response':None,'parse_ok':False}
        try:
            if fresh!=job or not video.is_file() or digest(video)!=job['video_sha256']:
                raise ValueError('连续视频评价输入已过期')
            payload=base64.b64encode(video.read_bytes()).decode()
            messages=[{'role':'user','content':[
                {'type':'video_url','video_url':{'url':'data:video/mp4;base64,'+payload}},
                {'type':'text','text':job['prompt']}
            ]}]
            result['raw_response']=manager.call_glm_api(messages,temperature=0)
            result['parsed']=parse_video_response(result['raw_response'],job)
            result['parse_ok']=True
        except Exception as e:
            result['error']=type(e).__name__
        write(p,result); n+=1
    print(f'{n} continuous-video API calls; raw responses retained')

def collect_video_results():
    request_by_id={j['id']:j for j in read(RUN/'video_evaluation_requests.json')}
    temporal=[]; metric_rows=[]
    for p in sorted((RUN/'machine_video').glob('*.json')):
        result=read(p); job=result['request']
        if not result.get('parse_ok') or request_by_id.get(job['id'])!=job:
            continue
        parsed=result['parsed']
        temporal.append({
            'task_id':job['task_id'],'video_id':job['video_id'],'video_sha256':job['video_sha256'],
            'question_sha256':stable(job['temporal_question_ids']),'parse_ok':True,
            'facts':{fid:{'answer':item['verdict'],'evidence':item.get('evidence',''),'timestamps':item.get('timestamps','')} for fid,item in parsed['temporal_facts'].items()},
            'source_file':str(p.relative_to(ROOT))
        })
        if job['video_id']!='source':
            row={'video_id':job['video_id'],'evaluator':'AI','subject':'','scene':'','time_weather':'','camera_motion':'','VBench_IQ':'','VBench_SC':'','provenance':str(p.relative_to(ROOT))}
            for name,item in parsed['conditions'].items():
                row[name]=item['verdict']
            metric_rows.append(row)
    write(RUN/'temporal_results.json',temporal)
    existing=[]
    metrics=RUN/'metrics.csv'
    if metrics.exists():
        with metrics.open(encoding='utf-8-sig',newline='') as f:
            existing=list(csv.DictReader(f))
    by_key={(r['video_id'],r['evaluator']):r for r in existing if r['evaluator']}
    for row in metric_rows:
        key=(row['video_id'],row['evaluator'])
        merged=by_key.get(key,{'video_id':row['video_id'],'evaluator':row['evaluator'],'subject':'','scene':'','time_weather':'','camera_motion':'','VBench_IQ':'','VBench_SC':'','provenance':''})
        for field in ('subject','scene','time_weather','camera_motion'):
            merged[field]=row[field]
        merged['provenance']=';'.join(filter(None,[merged.get('provenance',''),row['provenance']]))
        by_key[key]=merged
    blanks=[r for r in existing if not r['evaluator']]
    table(metrics,blanks+list(by_key.values()),['video_id','evaluator','subject','scene','time_weather','camera_motion','VBench_IQ','VBench_SC','provenance'])
    print(f'{len(temporal)} temporal records and {len(metric_rows)} condition records collected')

def collect_vbench():
    files=sorted((RUN/'vbench').glob('*_eval_results.json'),key=lambda p:p.stat().st_mtime)
    if not files:
        raise ValueError('未找到VBench结果')
    source=files[-1]; data=read(source)
    manifest=read(RUN/'generation_manifest.json')
    by_path={str((ROOT/v['video_file']).resolve()):v for v in manifest}
    scores={v['video_id']:{'VBench_IQ':None,'VBench_SC':None} for v in manifest}
    for item in data['imaging_quality'][1]:
        scores[by_path[str(Path(item['video_path']).resolve())]['video_id']]['VBench_IQ']=float(item['video_results'])
    for item in data['subject_consistency'][1]:
        scores[by_path[str(Path(item['video_path']).resolve())]['video_id']]['VBench_SC']=float(item['video_results'])
    if any(v is None for score in scores.values() for v in score.values()):
        raise ValueError('VBench结果不完整')
    metrics=RUN/'metrics.csv'; existing=[]
    if metrics.exists():
        with metrics.open(encoding='utf-8-sig',newline='') as f: existing=list(csv.DictReader(f))
    by_key={(r['video_id'],r['evaluator']):r for r in existing if r['evaluator']}
    for vid,score in scores.items():
        row=by_key.get((vid,'AI'),{'video_id':vid,'evaluator':'AI','subject':'','scene':'','time_weather':'','camera_motion':'','VBench_IQ':'','VBench_SC':'','provenance':''})
        row['VBench_IQ']=score['VBench_IQ'];row['VBench_SC']=score['VBench_SC']
        provenance=str(source.relative_to(ROOT))
        row['provenance']=';'.join(filter(None,[row.get('provenance',''),provenance]))
        by_key[(vid,'AI')]=row
    blanks=[r for r in existing if not r['evaluator']]
    table(metrics,blanks+list(by_key.values()),['video_id','evaluator','subject','scene','time_weather','camera_motion','VBench_IQ','VBench_SC','provenance'])
    task_rows=[]
    for v in manifest:
        score=scores[v['video_id']]
        task_rows.append({'task_id':v['task_id'],'group':v['group'],'video_id':v['video_id'],**score})
    groups={}
    for g in GROUPS:
        block=[r for r in task_rows if r['group']==g]
        groups[g]={'tasks':len(block),'VBench_IQ_mean':statistics.mean(r['VBench_IQ'] for r in block),'VBench_SC_mean':statistics.mean(r['VBench_SC'] for r in block),'repeat_sd':None}
    write(RUN/'vbench_summary.json',{'source_file':str(source.relative_to(ROOT)),'scale':{'VBench_IQ':'MUSIQ 0-100','VBench_SC':'DINO consistency 0-1'},'details':task_rows,'groups':groups})
    print(f'{len(scores)} VBench IQ/SC records collected from {source.name}')

def summarize_computer():
    x=protocol(); tasks={t['task_id']:t for t in x['tasks']}
    jobs={j['id']:j for j in read(RUN/'evaluation_requests.json')}
    keyframe={}
    for p in sorted((RUN/'machine').glob('*.json')):
        result=read(p); job=result.get('request',{})
        if result.get('parse_ok') and jobs.get(job.get('id'))==job:
            keyframe[job['video_id']]={'result':result['parsed'],'source_file':str(p.relative_to(ROOT))}
    temporal_list=[r for r in (read(RUN/'temporal_results.json') if (RUN/'temporal_results.json').exists() else []) if r.get('parse_ok')]
    temporal={r['video_id']:r for r in temporal_list if r['video_id']!='source'}
    source_proposals=[]; details=[]
    manifest={v['video_id']:v for v in read(RUN/'generation_manifest.json')}
    # Source IDs repeat across tasks, so index the stored keyframe files directly by request task.
    for p in sorted((RUN/'machine').glob('*.json')):
        result=read(p); job=result.get('request',{})
        if job.get('video_id')!='source' or not result.get('parse_ok') or jobs.get(job.get('id'))!=job:
            continue
        facts=dict(result['parsed']['facts'])
        tr=next((r for r in temporal_list if r['video_id']=='source' and r['task_id']==job['task_id']),None)
        if tr: facts.update(tr['facts'])
        source_proposals.append({'task_id':job['task_id'],'answers':facts,'status':'machine_proposal_pending_human_verification','reference_truth_written':False,'source_file':str(p.relative_to(ROOT))})
    for vid,v in manifest.items():
        static=keyframe.get(vid)
        if not static: continue
        facts=dict(static['result']['facts'])
        if vid in temporal: facts.update(temporal[vid]['facts'])
        expected=[q['fact_id'] for q in tasks[v['task_id']]['questions']]
        missing=[fid for fid in expected if fid not in facts]
        details.append({
            'video_id':vid,'task_id':v['task_id'],'group':v['group'],'repeat':v['repeat'],
            'facts':facts,'expected_fact_count':len(expected),'evaluated_fact_count':len(expected)-len(missing),
            'missing_fact_ids':missing,'machine_yes_rate':sum(facts[fid]['answer']=='Yes' for fid in expected if fid in facts)/len(expected),
            'overall_form':static['result']['overall_form'],'overall_evidence':static['result']['overall_evidence'],
            'status':'complete_machine_evaluation_pending_human_reference' if not missing else 'partial_machine_evaluation',
            'formal_cultural_satisfaction_rate':None
        })
    group_summary={}
    for g in GROUPS:
        block=[r for r in details if r['group']==g and not r['missing_fact_ids']]
        group_summary[g]={
            'complete_tasks':len(block),
            'machine_yes_rate_mean':statistics.mean(r['machine_yes_rate'] for r in block) if block else None,
            'overall_form_distribution':{f:sum(r['overall_form']==f for r in block)/len(block) if block else None for f in sorted(FORMS)},
            'repeat_sd':None
        }
    metric_rows=[]
    if (RUN/'metrics.csv').exists():
        with (RUN/'metrics.csv').open(encoding='utf-8-sig',newline='') as f:
            metric_rows=[r for r in csv.DictReader(f) if r['evaluator']=='AI']
    other_metrics={}
    for g in GROUPS:
        block=[r for r in metric_rows if f'_{g}_' in r['video_id']]
        other_metrics[g]={
            'videos':len(block),
            'condition_distribution':{name:{a:sum(r[name]==a for r in block)/len(block) if block else None for a in sorted(ANSWERS)} for name in ('subject','scene','time_weather','camera_motion')},
            'VBench_IQ_mean':statistics.mean(float(r['VBench_IQ']) for r in block if r['VBench_IQ']) if block and all(r['VBench_IQ'] for r in block) else None,
            'VBench_SC_mean':statistics.mean(float(r['VBench_SC']) for r in block if r['VBench_SC']) if block and all(r['VBench_SC'] for r in block) else None,
            'repeat_sd':None
        }
    write(RUN/'computer_evaluation_summary.json',{
        'status':'provisional_pending_human_reference_verification',
        'source_reference_proposals':source_proposals,'details':details,'groups':group_summary,'other_metrics':other_metrics,
        'notes':['machine_yes_rate不是正式文化视觉事实满足率','原视频机器答案未写入reference_answer','单次生成不估计重复波动']
    })
    review_rows=[]
    for proposal in source_proposals:
        for fact_id,item in proposal['answers'].items():
            review_rows.append({'task_id':proposal['task_id'],'fact_id':fact_id,'machine_answer':item['answer'],'machine_evidence':item.get('evidence',''),'machine_timestamps':item.get('timestamps',''),'human_answer':'','human_reviewer':'','human_note':'','status':'pending_human_verification'})
    if review_rows:
        table(RUN/'computer_reference_review.csv',review_rows)
    if details:
        table(RUN/'computer_generated_detail.csv',[{
            'video_id':r['video_id'],'task_id':r['task_id'],'group':r['group'],'repeat':r['repeat'],
            'evaluated_fact_count':r['evaluated_fact_count'],'expected_fact_count':r['expected_fact_count'],
            'missing_fact_ids':'|'.join(r['missing_fact_ids']),'machine_yes_rate':r['machine_yes_rate'],
            'overall_form':r['overall_form'],'status':r['status']
        } for r in details])
    print(f'{len(source_proposals)} source proposals and {len(details)} generated-video records summarized')

def summarize():
    x=protocol(); vs=read(RUN/'generation_manifest.json'); details=[]; excluded=[]
    current={j['id']:j for j in read(RUN/'evaluation_requests.json')} if (RUN/'evaluation_requests.json').exists() else {}
    temporal_results=read(RUN/'temporal_results.json') if (RUN/'temporal_results.json').exists() else []
    temporal_by_video={r['video_id']:r for r in temporal_results if r.get('parse_ok')}
    for p in sorted((RUN/'machine').glob('*.json')):
        result=read(p); j=result['request']; vid=j['video_id']
        if vid=='source': continue
        t=next(t for t in x['tasks'] if t['task_id']==j['task_id']); v=next((v for v in vs if v['video_id']==vid),None)
        if not v or not admitted(t,v) or not reference_ok(t) or not result['parse_ok'] or current.get(j['id'])!=j:
            excluded.append({'file':str(p.relative_to(ROOT)),'reason':'未准入、待核准、旧版本或解析失败'});continue
        qs=[q for q in t['questions'] if q['required']]
        if not qs: continue
        answers=dict(result['parsed']['facts'])
        if vid in temporal_by_video:
            answers.update(temporal_by_video[vid].get('facts',{}))
        missing=[q['fact_id'] for q in qs if q['fact_id'] not in answers]
        if missing:
            excluded.append({'file':str(p.relative_to(ROOT)),'reason':'缺连续视频或关键帧事实评价: '+','.join(missing)})
            continue
        yes=sum(answers[q['fact_id']]['answer']=='Yes' for q in qs)
        comparable=[q for q in t['questions'] if q['reference_answer']!='Uncertain']
        agree=sum(answers[q['fact_id']]['answer']==q['reference_answer'] for q in comparable)
        details.append({'video_id':vid,'task_id':t['task_id'],'group':v['group'],'repeat':v['repeat'],'facts_satisfied':yes,'facts_required':len(qs),'cultural_visual_fact_rate':yes/len(qs),'uncertain_count':sum(answers[q['fact_id']]['answer']=='Uncertain' for q in qs),'overall_form':result['parsed']['overall_form'],'answer_agreement_aux':agree/len(comparable) if comparable else None,'evaluator':'AI'})
    ids=[d['video_id'] for d in details]
    if len(ids)!=len(set(ids)): raise ValueError('同视频有重复评价，不自动挑选；先明确评价版本')
    task_rows=[]; summary={}
    for t in x['tasks']:
        for g in GROUPS:
            ds=[d for d in details if d['task_id']==t['task_id'] and d['group']==g]
            if ds:
                rates=[d['cultural_visual_fact_rate'] for d in ds]
                task_rows.append({'task_id':t['task_id'],'group':g,'n':len(ds),'complete':len(ds)==x['repeats'],'mean':statistics.mean(rates),'repeat_sd':statistics.stdev(rates) if len(rates)>1 else None,'forms':{f:sum(d['overall_form']==f for d in ds)/len(ds) for f in sorted(FORMS)}})
    complete=[t['task_id'] for t in x['tasks'] if all(any(r['task_id']==t['task_id'] and r['group']==g and r['complete'] for r in task_rows) for g in GROUPS)]
    for g in GROUPS:
        rs=[r for r in task_rows if r['group']==g and r['task_id'] in complete]
        repeat_sds=[r['repeat_sd'] for r in rs if r['repeat_sd'] is not None]
        summary[g]={'tasks':len(rs),'cultural_visual_fact_rate':statistics.mean(r['mean'] for r in rs) if rs else None,'mean_repeat_sd':statistics.mean(repeat_sds) if repeat_sds else None,'overall_form_distribution':{f:statistics.mean(r['forms'][f] for r in rs) if rs else None for f in sorted(FORMS)}}
    write(RUN/'evaluation_details.json',details);write(RUN/'task_aggregates.json',task_rows)
    write(RUN/'summary.json',{'status':'complete' if len(complete)==x['planned_tasks'] else 'incomplete_not_final','complete_common_tasks':complete,'groups':summary,'comparisons':{f'{a}_vs_{b}':summary[b]['cultural_visual_fact_rate']-summary[a]['cultural_visual_fact_rate'] if complete else None for a,b in [('G1','G3'),('G3','G4'),('G1','G2')]},'excluded':excluded,'other_metrics':'separate metrics.csv; no composite score'})

def export_generation():
    x=protocol(); jobs=[]
    for v in read(RUN/'generation_manifest.json'):
        t=next(t for t in x['tasks'] if t['task_id']==v['task_id'])
        if not task_ok(t): continue
        d=t['descriptions'][v['group']]; prompt=(ROOT/d['file']).read_text()
        if '【T' in prompt or '技术参数层' in prompt: raise ValueError('T层不得输入生成模型')
        jobs.append({**v,'prompt':prompt,'description_version':d['version'],'description_sha256':d['sha256'],'status':'planned_not_generated'})
    write(RUN/'generation_jobs.json',jobs)
    print(f'{len(jobs)} frozen generation inputs; no generation API configured or called')

def summarize_metrics():
    path=RUN/'metrics.csv'
    if not path.exists(): return
    vs={v['video_id']:v for v in read(RUN/'generation_manifest.json')};tasks={t['task_id']:t for t in protocol()['tasks']}
    with path.open(encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
    accepted=[];seen=set()
    for row in rows:
        if not row['evaluator'] or not row['provenance']: continue
        v=vs.get(row['video_id'])
        if not v or not admitted(tasks[v['task_id']],v):continue
        key=(row['video_id'],row['evaluator'])
        if key in seen:raise ValueError('重复指标记录')
        seen.add(key)
        for metric in ('subject','scene','time_weather','camera_motion','VBench_IQ','VBench_SC'):
            value=row[metric]
            if not value:continue
            if metric.startswith('VBench'): value=float(value)
            else:
                if value not in ANSWERS:raise ValueError('条件评分仅允许Yes/No/Uncertain')
            accepted.append({'task_id':v['task_id'],'group':v['group'],'repeat':v['repeat'],'evaluator':row['evaluator'],'metric':metric,'value':value})
    result=[]
    for evaluator in sorted({r['evaluator'] for r in accepted}):
        for metric in sorted({r['metric'] for r in accepted}):
            for g in GROUPS:
                per_task=[]
                for tid in tasks:
                    block=[r['value'] for r in accepted if r['evaluator']==evaluator and r['metric']==metric and r['group']==g and r['task_id']==tid]
                    if len(block)!=protocol()['repeats']:continue
                    if metric.startswith('VBench'):
                        if not all(math.isfinite(v) for v in block):raise ValueError('非有限指标')
                        per_task.append({'task_id':tid,'mean':statistics.mean(block),'repeat_sd':statistics.stdev(block)})
                    else:per_task.append({'task_id':tid,'distribution':{a:block.count(a)/len(block) for a in sorted(ANSWERS)}})
                result.append({'evaluator':evaluator,'metric':metric,'group':g,'tasks':per_task,'equal_task_mean':statistics.mean(t['mean'] for t in per_task) if per_task and metric.startswith('VBench') else None,'equal_task_distribution':{a:statistics.mean(t['distribution'][a] for t in per_task) for a in sorted(ANSWERS)} if per_task and not metric.startswith('VBench') else None})
    write(RUN/'other_metric_summary.json',result)

def summarize_human():
    mapping_path=RUN/'human_private/anonymous_mapping.json'
    mapping=read(mapping_path) if mapping_path.exists() else {}
    vs={v['video_id']:v for v in read(RUN/'generation_manifest.json')}
    tasks={t['task_id']:t for t in protocol()['tasks']}; output={}
    for path in sorted((RUN/'human_blind').glob('scoring_sheet_rater*.csv')):
        with path.open(encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f); columns=reader.fieldnames; rows=list(reader)
        score_col=columns[5]; detail=[]
        for anon,vid in mapping.items():
            if vid not in vs:continue
            v=vs[vid]; t=tasks[v['task_id']]
            if not admitted(t,v) or not reference_ok(t):continue
            block=[r for r in rows if r[columns[0]]==anon]; facts={}; form=None
            for row in block:
                item=row[columns[2]]; score=row[score_col].strip()
                if not score:continue
                if item=='整体文化形态':
                    if score not in FORMS:raise ValueError('人工整体形态格式错误')
                    form=score
                elif ':' in item and item.split(':',1)[0] in {q['fact_id'] for q in t['questions']}:
                    fid=item.split(':',1)[0]
                    if fid in facts or score not in ANSWERS:raise ValueError('人工事实重复或格式错误')
                    facts[fid]=score
            required=[q['fact_id'] for q in t['questions'] if q['required']]
            if not required or not all(f in facts for f in required) or form is None:continue
            detail.append({'video_id':vid,'task_id':t['task_id'],'group':v['group'],'repeat':v['repeat'],'facts':facts,'cultural_visual_fact_rate':sum(facts[f]=='Yes' for f in required)/len(required),'overall_form':form})
        aggregates=[]
        for tid in tasks:
            for g in GROUPS:
                block=[r for r in detail if r['task_id']==tid and r['group']==g]
                if len(block)==protocol()['repeats']:
                    aggregates.append({'task_id':tid,'group':g,'mean':statistics.mean(r['cultural_visual_fact_rate'] for r in block),'repeat_sd':statistics.stdev(r['cultural_visual_fact_rate'] for r in block) if len(block)>1 else None,'forms':{f:sum(r['overall_form']==f for r in block)/len(block) for f in sorted(FORMS)}})
        common=[tid for tid in tasks if all(any(r['task_id']==tid and r['group']==g for r in aggregates) for g in GROUPS)]
        groups={}
        for g in GROUPS:
            block=[r for r in aggregates if r['task_id'] in common and r['group']==g]
            repeat_sds=[r['repeat_sd'] for r in block if r['repeat_sd'] is not None]
            groups[g]={'tasks':len(block),'cultural_visual_fact_rate':statistics.mean(r['mean'] for r in block) if block else None,'mean_repeat_sd':statistics.mean(repeat_sds) if repeat_sds else None,'overall_form_distribution':{f:statistics.mean(r['forms'][f] for r in block) if block else None for f in sorted(FORMS)}}
        output[path.stem]={'source_sha256':digest(path),'details':detail,'task_aggregates':aggregates,'common_tasks':common,'groups':groups,'status':'complete' if len(common)==protocol()['planned_tasks'] else 'incomplete_not_final'}
    write(RUN/'human_summary.json',output)

def review_pack():
    x=protocol(); vs=read(RUN/'generation_manifest.json'); valid=[v for v in vs if admitted(next(t for t in x['tasks'] if t['task_id']==v['task_id']),v) and reference_ok(next(t for t in x['tasks'] if t['task_id']==v['task_id'])) and evidence(next(t for t in x['tasks'] if t['task_id']==v['task_id']),v['video_id'])]
    # Hash ordering hides group and is deterministic; mapping is private, never in blind sheet.
    valid.sort(key=lambda v:stable({'blind_salt':'four_group_v2','id':v['video_id']}))
    mapping_path=RUN/'human_private/anonymous_mapping.json'
    mapping=read(mapping_path) if mapping_path.exists() else {}
    for v in valid:
        if v['video_id'] not in mapping.values(): mapping[f'N{len(mapping)+1:03}']=v['video_id']
    write(RUN/'human_private/anonymous_mapping.json',mapping)
    header=['匿名编号','任务（仅供定位参考图，不代表组别）','评价项','Yes/Match标准','No/Mismatch标准','评分(局部:Yes/No/Uncertain; 整体:Match/Partial/Mismatch/Uncertain; 镜头/天气:Yes/No/Uncertain)','证据','无法判断原因','备注']
    rows=[]
    for v in valid:
        anon=next(a for a,vid in mapping.items() if vid==v['video_id'])
        t=next(t for t in x['tasks'] if t['task_id']==v['task_id'])
        e=evidence(t,'source')
        if e:
            import shutil
            for frame in e['frames']:
                dest=RUN/'human_blind/source'/t['task_id']/Path(frame['frame_file']).name
                dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/frame['frame_file'],dest)
        folder=RUN/'human_blind/videos';folder.mkdir(parents=True,exist_ok=True)
        link=folder/(anon+'.mp4')
        if not link.exists(): link.symlink_to(ROOT/v['video_file'])
        items=[(q['fact_id']+': '+q['question'],q['yes_rule'],q['no_rule']) for q in t['questions'] if q['required']]
        items += [('整体文化形态','轮廓、布局与关键部件空间关系匹配原视频','明显偏离为Mismatch；部分匹配为Partial；证据不足Uncertain'),('主体/场景/时间天气条件遵循',str(t['conditions']),'与冻结条件不符'),('镜头运动遵循（观看连续视频）',str(t['conditions']),'不符')]
        for item,yes,no in items: rows.append(dict(zip(header,[anon,t['task_id'],item,yes,no,'','','','独立盲评；禁止查看AI评分与private映射'])))
    for r in range(1,4):
        path=RUN/f'human_blind/scoring_sheet_rater{r}.csv'
        if path.exists():
            with path.open(encoding='utf-8-sig',newline='') as f: existing=list(csv.DictReader(f))
            keyed={(r[header[0]],r[header[2]]):r for r in existing}
            for row in rows:
                key=(row[header[0]],row[header[2]])
                if key not in keyed:existing.append(row)
            table(path,existing,header)
        else: table(path,rows,header)
    metrics=RUN/'metrics.csv'
    if not metrics.exists(): table(metrics,[{'video_id':v['video_id'],'evaluator':'','subject':'','scene':'','time_weather':'','camera_motion':'','VBench_IQ':'','VBench_SC':'','provenance':''} for v in vs])
    cards=[]
    for t in x['tasks']:
        cards.append('<h2>'+html.escape(t['task_id']+' '+t['name'])+'</h2>')
        for vid in ['source']+[v['video_id'] for v in valid if v['task_id']==t['task_id']]:
            e=evidence(t,vid)
            if e:
                cards.append('<p>'+html.escape(vid)+'</p>')
                for f in e['frames']: cards.append('<figure><img width="320" src="../../../'+html.escape(f['frame_file'])+'"><figcaption>'+str(f['actual_sec'])+'s</figcaption></figure>')
    (RUN/'cases.html').write_text('<!doctype html><meta charset="utf-8"><title>原视频与四组实际证据</title><p>完整列出可用证据，不自动挑选最好样本。最终案例标注待人工复核。</p>'+''.join(cards),encoding='utf-8')

def media_info(path):
    info=json.loads(subprocess.check_output([
        'ffprobe','-v','error','-select_streams','v:0','-show_streams',
        '-show_format','-of','json',str(path)
    ]))
    stream=info['streams'][0]
    num,den=stream['avg_frame_rate'].split('/')
    return {
        'resolution':f"{stream['width']}x{stream['height']}",
        'fps':float(num)/float(den),
        'duration_sec':float(info['format']['duration']),
        'decoded_frame_count':int(stream.get('nb_frames') or 0),
        'codec':stream.get('codec_name')
    }

def apply_current_questions():
    x=protocol()
    for t in x['tasks']:
        spec=CURRENT_QUESTIONS[t['task_id']]
        t['evaluation_focus']=spec['focus']
        if 'overall_reference_note' in spec:
            t['overall_reference_note']=spec['overall_reference_note']
        t['question_version']='user_confirmed_wording_2026-11-24_v1'
        questions=[]
        for fact_id,question,yes_rule,no_rule,uncertain_rule,evidence_mode in spec['questions']:
            questions.append({
                'fact_id':fact_id,'question':question,
                'yes_rule':yes_rule,'no_rule':no_rule,'uncertain_rule':uncertain_rule,
                'evidence_mode':evidence_mode,
                'provenance':{'source':'user_message_2026-11-24','status':'wording_supplied_by_user; operational rules added locally'},
                'reference_answer':None,'status':'pending_human_verification','required':False,
                'reviewer':None,'source_evidence_sha256':None
            })
        t['questions']=questions
        for g in ('G3','G4'):
            t['descriptions'][g]['target_fact_ids']=[q['fact_id'] for q in questions]
    write(RUN/'protocol.json',x)
    audit()

def ingest_current_batch():
    """Migrate the received five-task, one-repeat batch without inventing prompts."""
    x=read(RUN/'protocol.json')
    keep=['T01','T04','T06','T07','T10']
    tasks={t['task_id']:t for t in x['tasks']}
    selected=[tasks[tid] for tid in keep]
    source_names={'T01':'兵马俑.mp4','T04':'南湖红船.mp4','T06':'皮影戏.mp4','T07':'海南文昌发射场.mp4','T10':'东方明珠.mp4'}
    for t in selected:
        tid=t['task_id']; source=ROOT/'data/video'/source_names[tid]
        if not source.is_file(): raise ValueError(f'缺少原视频: {source}')
        t['source_video']=str(source.relative_to(ROOT))
        t['source_note']='当前五任务批次；原视频时长不作为排除条件'
        t['sampling']={
            'fractions':[0.5],
            'status':'confirmed_before_generated_review',
            'reviewer':'protocol_default_registered_2026-11-24',
            'reason':'用户规则默认取50%；该规则在本批生成视频接入与评价前已登记',
            'source_sha256':digest(source)
        }
    t6=tasks['T06']
    history=RUN/'history/T06_rabbit_prompts'
    history.mkdir(parents=True,exist_ok=True)
    for g in GROUPS:
        desc=t6['descriptions'][g]
        prompt=ROOT/desc['file']
        if prompt.is_file() and prompt.read_text(encoding='utf-8').strip():
            shutil.copy2(prompt,history/f'{g}.txt')
        prompt.write_text('',encoding='utf-8')
        desc.update({
            'source':'missing_actual_generation_input_for_received_T06_video',
            'status':'missing_actual_generation_input',
            'reviewer':None,'version':None,'sha256':None,
            'target_fact_ids':['T06-F1','T06-F2','T06-F3','T06-F4'] if g in ('G3','G4') else []
        })
    t6.update({
        'name':'皮影戏',
        'conditions':'室内白色幕布皮影舞台，两个皮影人物同台表演，固定机位全景，暖色背光',
        'conditions_status':'pending_human_review',
        'equivalence_review':{'status':'pending','reviewer':None,'note':'实际G1—G4生成提示词尚未入库；收到后核对基础条件及G3/G4事实等价'},
        'questions':[
            {'fact_id':'T06-F1','question':'画面是否可见至少两个扁平的皮影人物形象？','yes_rule':'同一幕布上可辨认至少两个扁平人物剪影或彩色透光人物形象','no_rule':'主体清晰但不是皮影人物，或仅有一个人物','uncertain_rule':'人物严重模糊、遮挡或过小，数量无法判断'},
            {'fact_id':'T06-F2','question':'人物是否呈现在由背光照亮的浅色幕布前？','yes_rule':'可见浅色透光幕布及其前方/上方形成的皮影人物影像','no_rule':'人物位于普通实景舞台且没有背光幕布关系','uncertain_rule':'背景或光照关系无法辨认'},
            {'fact_id':'T06-F3','question':'皮影人物是否具有可辨认的传统人物轮廓与分节肢体？','yes_rule':'至少一个人物具有传统服饰/头饰轮廓，且肢体呈可活动的分节或关节结构','no_rule':'主体清晰但为普通真人、完整实心卡通或无分节结构','uncertain_rule':'轮廓或关节细节不足以判断'},
            {'fact_id':'T06-F4','question':'两个皮影人物是否在同一幕布表演区形成对向互动关系？','yes_rule':'两个主体位于同一幕布表演区并相向、对峙或以动作形成明确互动','no_rule':'人物彼此无空间关系，或不在同一表演区','uncertain_rule':'主体位置或朝向无法判断'}
        ]
    })
    for q in t6['questions']:
        q.update({
            'provenance':{
                'source':'outputs/annotations/cultural_traces/20261123_151809_皮影戏/00_scene_evidence.json',
                'status':'candidate_from_visible_source_evidence_pending_human_verification'
            },
            'reference_answer':None,'status':'pending_human_verification','required':False,
            'reviewer':None,'source_evidence_sha256':None
        })
    x.update({
        'version':'four_group_v2_five_task_single_generation',
        'repeats':1,'planned_tasks':5,'planned_videos':20,
        'received_videos':20,'completed_videos':20,'formally_verified_videos':0,
        'scope_note':'当前批次五任务×四组×一次生成；20条生成文件已完成并收到，正式准入仍需输入描述与模型配置核验',
        'tasks':selected
    })
    write(RUN/'protocol.json',x)
    manifest=[]
    for t in selected:
        for g in GROUPS:
            path=BASE/'videos/four_group_v2'/f"{t['task_id']}-{g}.mp4"
            if not path.is_file(): raise ValueError(f'缺少生成视频: {path}')
            meta=media_info(path); desc=t['descriptions'][g]
            prompt=ROOT/desc['file']
            prompt_sha=digest(prompt) if prompt.is_file() and prompt.read_text(encoding='utf-8').strip() else None
            manifest.append({
                'video_id':f"{t['task_id']}_{g}_r01",'task_id':t['task_id'],'group':g,'repeat':1,
                'video_file':str(path.relative_to(ROOT)),
                'description_version':'batch2_v1_candidate_unfrozen' if prompt_sha else None,
                'description_sha256':prompt_sha,'video_sha256':digest(path),
                'model_config':{'model':None,'seed':None,'seed_supported':None,**meta,'other':'生成接口配置待补'},
                'provenance_status':'received_pending_input_and_model_config_verification',
                'provenance_evidence':'用户于2026-11-24确认五任务均替换并按文件名提供G1—G4；文件身份已登记，实际提示词/模型/种子待核验'
            })
    write(RUN/'generation_manifest.json',manifest)
    table(RUN/'received_video_inventory.csv',[{
        'video_id':v['video_id'],'task_id':v['task_id'],'group':v['group'],'repeat':v['repeat'],
        'video_file':v['video_file'],'video_sha256':v['video_sha256'],
        'resolution':v['model_config']['resolution'],'fps':v['model_config']['fps'],
        'duration_sec':v['model_config']['duration_sec'],'decoded_frame_count':v['model_config']['decoded_frame_count'],
        'codec':v['model_config']['codec'],'formal_eligibility':'pending_input_and_model_config_verification'
    } for v in manifest])
    table(RUN/'metrics.csv',[{'video_id':v['video_id'],'evaluator':'','subject':'','scene':'','time_weather':'','camera_motion':'','VBench_IQ':'','VBench_SC':'','provenance':''} for v in manifest])
    apply_current_questions()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['init','ingest-current-batch','apply-current-questions','audit','source-preview','frames','requests','evaluate','reparse-machine','evaluate-video','collect-video-results','collect-vbench','summarize-computer','summarize','review-pack','export-generation','summarize-metrics','summarize-human']);parser.add_argument('--limit',type=int,default=1);args=parser.parse_args()
    if args.command=='init':init()
    elif args.command=='ingest-current-batch':ingest_current_batch()
    elif args.command=='apply-current-questions':apply_current_questions()
    elif args.command=='audit':audit()
    elif args.command=='source-preview':frames(True)
    elif args.command=='frames':frames()
    elif args.command=='requests':requests()
    elif args.command=='evaluate':
        if args.limit<1:parser.error('--limit must be positive')
        evaluate(args.limit)
    elif args.command=='reparse-machine':reparse_machine()
    elif args.command=='evaluate-video':
        if args.limit<1:parser.error('--limit must be positive')
        evaluate_video(args.limit)
    elif args.command=='collect-video-results':collect_video_results()
    elif args.command=='collect-vbench':collect_vbench()
    elif args.command=='summarize-computer':summarize_computer()
    elif args.command=='summarize':summarize()
    elif args.command=='review-pack':review_pack()
    elif args.command=='export-generation':export_generation()
    elif args.command=='summarize-metrics':summarize_metrics()

    elif args.command=='summarize-human':summarize_human()
