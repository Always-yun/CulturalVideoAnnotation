"""Frozen image/multimodal extension; reuse historical Free/Text C blocks."""
import argparse,base64,csv,hashlib,itertools,json,os,platform,sys,time
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor,as_completed
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from src.experiments.c_retrieval import fuse
from src.knowledge.symbol_kb import SymbolKnowledgeBase
from src.knowledge.retriever import KeywordCulturalRetriever
OLD=ROOT/'experiments/innovation2/results/four_method_accuracy_20261119'
OUT=ROOT/'experiments/innovation2/results/image_multimodal_c_20261119'
MODES=('free','text','image','multimodal')
PROMPT='''请仅输出EMCAST的C文化维度层，保留完整中文自然语言说明，不输出其余五层。
根据视频实际可见证据识别文化符号。文化类别可多选：古城与历史文化、红色文化、民族与民俗文化、科技与创新文化、现代城市与国际文化；证据不足可写无法确认。
候选知识只是待核实材料，不证明画面已出现该实体。允许命名候选之外的实体，允许无候选或无法确认，不强迫选择。不要给数值置信度。
核心符号行请用规范名称列出实际确认的实体，多个用顿号分隔；没有可靠身份则写unknown_symbol。其他说明放在价值指向中，不把身份猜测写成已识别事实。
输出格式沿用现有C层：
【C｜文化维度层】：该场景隶属于……（多类可并列，无法确认则说明）。
核心符号：……
价值指向：描述可见视觉依据、文化内涵与不确定之处。
'''
# Manual observable descriptions of the 13 held-out photographs, inspected in
# /tmp/cultural_dev_sheet.jpg. No KB descriptive text or test-video output copied.
DESCRIPTIONS=[
'白天现代城市，河道与桥梁，高楼密集，其中有很高的细长塔楼。',
'红色宫殿门洞，彩绘屋檐和黄色瓦，门外有游客，远处可见传统楼阁。',
'黄色瓦顶红色大殿，多层白色石栏杆和宽阔台阶，地面积水倒影。',
'城墙与河道转角处的多重屋檐楼阁，黄瓦红柱，长城墙沿水延伸。',
'树木间的红砖教学建筑，白色柱廊和中央门廊，两侧对称。',
'城市远景航拍，大片绿地和河流、立交道路、低密度现代建筑。',
'树荫下狭窄街巷，灰砖院墙、门洞、自行车和电动车。',
'舞台上两位传统戏曲演员，华丽头饰，白色水袖和刺绣服饰。',
'桌上的彩绘兔头人身小塑像，长耳、白脸，穿彩色服装。',
'夜晚红墙黄瓦的城楼，国徽与中央人像，两侧大型文字标语。',
'城市广场中央高大方形石碑，白色多层台基，背景有大型建筑。',
'路旁低矮现代玻璃建筑，屋顶曲线起伏，树木和骑车人。',
'现代高楼之间的广场，前景立体字样清楚可见“中关村1号”，旁有水面。']
def dump(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');tmp.replace(p)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def now():return datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
def csvwrite(p,rows):
 if not rows:return
 with Path(p).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rows for k in r)));w.writeheader();w.writerows({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()} for r in rows)
def texts(kb,text):return {c.symbol_id:c.score for c in KeywordCulturalRetriever(kb).retrieve({'scene_text':text},top_k=len(kb))}
def parse(raw):
 from src.pipeline.cultural_rag import parse_c_layer
 c=parse_c_layer(raw)
 if not c['raw_block'] or not c['core_symbol']:raise ValueError('Missing C block or core_symbol line')
 if any(('【'+s+'｜') in raw for s in ('E','M','A','S','T')):raise ValueError('Unexpected non-C output')
 return c

def prepare():
 OUT.mkdir(parents=True,exist_ok=True)
 if (OUT/'protocol.json').exists():verify();print('Already frozen');return
 import torch
 torch.set_num_threads(4)
 from src.knowledge.clip_encoder import CLIPEncoder
 from PIL import Image
 kb=SymbolKnowledgeBase();payload=json.loads(Path(kb.json_path).read_text());old=json.loads((OLD/'manifest.json').read_text());dev=[];index=[]
 for s in kb.symbols:
  refs=sorted(s.get('reference_images',[]),key=lambda r:r['sha256'])
  if len(refs)>1:
   q=refs[0];dev.append(dict(dev_id='photo_'+s['symbol_id'],symbol_id=s['symbol_id'],query=q,observable_description=DESCRIPTIONS[len(dev)]));refs=refs[1:]
  for ref in refs:index.append(dict(symbol_id=s['symbol_id'],**{k:ref[k] for k in ('local_path','sha256','source_page_url')}))
 assert len(dev)==13 and len(index)==30
 assert not ({d['query']['sha256'] for d in dev}&{r['sha256'] for r in index})
 framehash={f['sha256'] for g in old['items'] for f in g['keyframes']};assert not framehash&{d['query']['sha256'] for d in dev}
 encoder=CLIPEncoder(device='cpu');refs=encoder.encode_images([str(ROOT/r['local_path']) for r in index]).float();queries=encoder.encode_images([str(ROOT/d['query']['local_path']) for d in dev]).float()
 # Mean normalized photo embeddings once per entity; normalize entity centroid.
 ids=sorted({r['symbol_id'] for r in index});centroids=[]
 for sid in ids:
  v=refs[[i for i,r in enumerate(index) if r['symbol_id']==sid]].mean(0);centroids.append(v/v.norm().clamp(min=1e-8))
 matrix=torch.stack(centroids);devscores=[]
 for d,q in zip(dev,queries):
  im=dict(zip(ids,(matrix@q).tolist()));t=texts(kb,d['observable_description']);devscores.append(dict(dev_id=d['dev_id'],target=d['symbol_id'],text=t,image=im))
 trials=[]
 for alpha,k,th in itertools.product((.25,.5,.75),(1,3,5),(0,.25,.5)):
  hits=[];rr=[];nonempty=[]
  for d in devscores:
   ranked=fuse(d['text'],d['image'],'multimodal',alpha,k,th);found=next((j+1 for j,r in enumerate(ranked) if r['symbol_id']==d['target']),None);hits.append(bool(found));rr.append(1/found if found else 0);nonempty.append(bool(ranked))
  recall=sum(hits)/len(hits);mrr=sum(rr)/len(rr);objective=recall+.1*mrr-.02*k
  trials.append(dict(alpha=alpha,top_k=k,threshold=th,recall_at_k=recall,mrr=mrr,objective=objective))
 trials.sort(key=lambda r:(-r['objective'],abs(r['alpha']-.5),r['top_k'],r['threshold'],r['alpha']));chosen=trials[0]
 dump(OUT/'development_materials.json',dict(samples=dev,reference_index=index,selection='sha256-first photo held out for each entity with >=2 photos; excluded from final reference index',limitations='13 still photographs, not independent development videos; same semantic entities, no test frames or labels used to select parameters; near-duplicate/source-level overlap not guaranteed absent'))
 dump(OUT/'development_scores.json',devscores);dump(OUT/'development_grid.json',dict(objective='Recall@K + .1*MRR - .02*K; ties alpha closest .5, smaller K, lower threshold, alpha ascending',trials=trials,selected=chosen))
 # Preserve the agreed original 30 video paths, labels and frame sampling.
 items=old['items'];dump(OUT/'test_manifest.json',dict(items=items,reference_status='pending independent human confirmation',source_manifest=str((OLD/'manifest.json').relative_to(ROOT)),source_sha256=sha(OLD/'manifest.json')))
 csvwrite(OUT/'reference_answers_for_review.csv',[dict(video_id=g['video_id'],video_path=g['video_path'],primary_entity=g['gt_symbols'],entity_ids=g['gt_symbol_ids'],cultural_categories=g['gt_dimension_code'],basis=g['gt_source'],human_confirmed=False) for g in items])
 from src.models.config import Config
 cfg=Config()
 protocol=dict(frozen_at=now(),modes=MODES,new_runs=['image','multimodal'],reuse=['free','text'],kb_path=str(Path(kb.json_path).relative_to(ROOT)),kb_entities=len(kb),reference_index_photos=len(index),reference_index_entities=len(ids),parameters=chosen,normalization='per-modality average-tie entity rank: 1-(rank-1)/(n-1); singleton=1; scores are not probabilities',aggregation='L2-normalized per-photo CLIP embedding -> mean per entity -> L2 normalization; same 4 frozen video frames -> mean -> L2 normalization; cosine; one row per stable entity ID',missing='candidate-specific absent modality contributes 0 without entitywise weight renormalization; globally absent modality reweights remaining modality; pure image never returns text candidates',deduplication='SHA256 unique reference files; entity ID unique candidates; canonical/registered alias unique predictions',clip_model='ViT-B/32',clip_weights_sha256=sha(Path.home()/'.cache/clip/ViT-B-32.pt'),base_model=cfg.model.glm_model_name,model_version_note='provider alias; actual response model/id retained; no stable provider revision exposed',generation=dict(temperature=.1,max_tokens=cfg.generation.max_new_tokens),retry=dict(max_attempts=2,retry_service_and_parse=True,sdk_retries=0,timeout_seconds=300,sleep_seconds=2,resume='terminal completed/failure records are not retried automatically'),prompt_version='c_only_v1',identity_gate=False,controlled=False,input='identical original video bytes sent via video_url for new methods; same input mechanism as historical runs',comparability_limitations=['Historical Free/Text C extracted from six-layer outputs; Image/Multimodal C-only prompt by explicit user instruction; prompt confound.','Historical Free/Text used v2 114 entities and old reference state; new Image/Multimodal use consolidated 126 entities and 30 held-in photos; KB confound.','Historical failed raw replies/retry rules may be incomplete/different; report failures without deletion.'],evaluation=dict(ground_truth_status='pending human confirmation',denominator=30,main_accuracy='at least one asserted entity matches preset main target; extras permitted but false extras counted separately',strict_accuracy='main match and no false extra identities',normalization='exact canonical/registered aliases only; no keyword or substring credit; whitespace/punctuation normalization only',category='label-set exact match and micro P/R/F1; never force mutually exclusive categories',empty_prediction='no identity is incorrect for preset-entity task, separate from wrong naming',failure='all 30 retained; service/parse failures have empty prediction and one FN; completed-only also secondary',zero_division='P/R/F1=0 when denominator=0',auxiliary_fields='parsed entities are experiment-only extraction records, not production Schema fields',retrieval_denominator='only gt IDs present in that method KB; image coverage reported separately'))
 frozen=[Path(kb.json_path),Path(__file__),ROOT/'src/experiments/c_retrieval.py',ROOT/'src/experiments/c_evaluation.py',ROOT/'src/pipeline/cultural_rag.py',ROOT/'src/pipeline/scene_evidence.py',ROOT/'src/knowledge/retriever.py',ROOT/'src/knowledge/symbol_kb.py',ROOT/'src/knowledge/clip_encoder.py',OUT/'development_materials.json',OUT/'development_grid.json',OUT/'development_scores.json',OUT/'test_manifest.json',OUT/'reference_answers_for_review.csv']
 hashes={str(p.relative_to(ROOT)):sha(p) for p in frozen}
 for ref in index:hashes[ref['local_path']]=ref['sha256']
 for d in dev:hashes[d['query']['local_path']]=d['query']['sha256']
 for g in items:
  hashes[g['video_path']]=g['video_sha256']
  for f in g['keyframes']:hashes[f['path']]=f['sha256']
 dump(OUT/'frozen_hashes.json',hashes);dump(OUT/'protocol.json',protocol);dump(OUT/'protocol.sha256.json',{'sha256':sha(OUT/'protocol.json')})
 torch.save(dict(ids=ids,centroids=matrix,index=index),OUT/'reference_index.pt');dump(OUT/'reference_index.sha256.json',{'sha256':sha(OUT/'reference_index.pt')})
 dump(OUT/'environment.json',dict(python=sys.version,platform=platform.platform(),torch=torch.__version__,cuda=torch.cuda.is_available(),clip_device='cpu',network='remote GLM API',prepared_at=now()))
 print('FROZEN',json.dumps(chosen),flush=True)
def verify():
 for name,value in json.loads((OUT/'frozen_hashes.json').read_text()).items():
  if sha(ROOT/name)!=value:raise RuntimeError('Frozen input changed: '+name)
 assert sha(OUT/'protocol.json')==json.loads((OUT/'protocol.sha256.json').read_text())['sha256']
 assert sha(OUT/'reference_index.pt')==json.loads((OUT/'reference_index.sha256.json').read_text())['sha256']

def api_raw(media_path,kind,prompt,directory,parser):
 from src.models.config import Config
 from zai import ZhipuAiClient
 cfg=Config();client=ZhipuAiClient(api_key=cfg.model.glm_api_key,timeout=300,max_retries=0);directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
 prefix='data:video/mp4;base64,' if kind=='video_url' else 'data:image/jpeg;base64,'
 encoded=base64.b64encode(Path(media_path).read_bytes()).decode();messages=[{'role':'user','content':[{'type':kind,kind:{'url':prefix+encoded}},{'type':'text','text':prompt}]}]
 dump(directory/'request.json',dict(media_path=str(media_path),media_sha256=sha(media_path),media_kind=kind,prompt=prompt,model=cfg.model.glm_model_name,temperature=.1,max_tokens=cfg.generation.max_new_tokens,base64_omitted=True))
 attempts=[];last=None
 for attempt in range(1,3):
  entry=dict(attempt=attempt,started_at=now());begin=time.time()
  try:
   response=client.chat.completions.create(model=cfg.model.glm_model_name,messages=messages,temperature=.1,max_tokens=cfg.generation.max_new_tokens)
   raw=response.choices[0].message.content;entry.update(status='response_received',raw_reply=raw,response_model=getattr(response,'model',None),response_id=getattr(response,'id',None),finish_reason=response.choices[0].finish_reason,usage=str(getattr(response,'usage',None)))
   dump(directory/f'attempt_{attempt}.json',entry) # before parsing
   try:parsed=parser(raw)
   except Exception as e:entry.update(status='parse_failure',error_type=type(e).__name__,error=str(e));raise
   entry.update(status='completed',seconds=time.time()-begin);attempts.append(entry);dump(directory/f'attempt_{attempt}.json',entry)
   return dict(status='completed',raw_reply=raw,parsed=parsed,attempts=attempts)
  except Exception as e:
   if entry.get('status')!='parse_failure':entry.update(status='service_failure',error_type=type(e).__name__,error=str(e)[:1000])
   entry['seconds']=time.time()-begin;attempts.append(entry);dump(directory/f'attempt_{attempt}.json',entry);last=entry
   # Do not conceal an infrastructure failure as an identity rejection.
   if attempt<2:time.sleep(2)
 return dict(status=last['status'],raw_reply=last.get('raw_reply'),parsed=None,attempts=attempts)

def smoke():
 verify();d=json.loads((OUT/'development_materials.json').read_text())['samples'][0];p=OUT/'development_smoke.json'
 if p.exists():print(json.loads(p.read_text())['status']);return
 result=api_raw(ROOT/d['query']['local_path'],'image_url',PROMPT,OUT/'development_smoke',parse);dump(p,result);print('SMOKE',result['status'],flush=True)

def run(workers):
 verify()
 if not (OUT/'development_smoke.json').exists() or json.loads((OUT/'development_smoke.json').read_text())['status']!='completed':raise RuntimeError('Independent development interface smoke must pass before test runs')
 import torch
 torch.set_num_threads(4)
 from src.knowledge.clip_encoder import CLIPEncoder
 from src.pipeline.scene_evidence import normalize_scene,retrieval_text,STRUCTURED_SCENE_PROMPT
 kb=SymbolKnowledgeBase();protocol=json.loads((OUT/'protocol.json').read_text());params=protocol['parameters'];items=json.loads((OUT/'test_manifest.json').read_text())['items'];data=torch.load(OUT/'reference_index.pt',weights_only=False);encoder=CLIPEncoder(device='cpu')
 # Retrieval is prepared once with unchanged frozen parameters, never evaluated
 # against test labels here. No parameter updates in this phase.
 for g in items:
  dest=OUT/'retrieval'/f'{g["video_id"]}.json'
  if dest.exists():continue
  print('RETRIEVE',g['video_id'],flush=True)
  embeddings=encoder.encode_images([str(ROOT/f['path']) for f in g['keyframes']]).float();q=embeddings.mean(0);q=q/q.norm().clamp(min=1e-8);im=dict(zip(data['ids'],(data['centroids']@q).tolist()))
  oldscene=OLD/'predictions'/g['video_id']/'scene.json';scene=None;acquisition=''
  if oldscene.exists():
   saved=json.loads(oldscene.read_text());scene=saved['structured_scene'];acquisition='reused historical raw structured observation; excludes uncertain identities';dump(OUT/'observations'/f'{g["video_id"]}.json',saved)
  else:
   result=api_raw(ROOT/g['video_path'],'video_url',STRUCTURED_SCENE_PROMPT,OUT/'observations'/g['video_id'],normalize_scene);dump(OUT/'observations'/f'{g["video_id"]}.json',result);scene=result['parsed'];acquisition=result['status']
  t=texts(kb,retrieval_text(scene,[],False)) if scene else {}
  modes={m:fuse(t,im,m,params['alpha'],params['top_k'],params['threshold']) for m in ('image','multimodal')}
  for ranked in modes.values():
   for row in ranked:
    symbol=dict(kb.get(row['symbol_id']));symbol.pop('reference_images',None);row['knowledge']=symbol
  dump(dest,dict(video_id=g['video_id'],observation_source=acquisition,text_available=bool(scene),raw_text_scores=t,raw_image_cosines=im,candidates=modes))
 def worker(g,mode):
  dest=OUT/'predictions'/g['video_id']/f'{mode}.json'
  if dest.exists():return json.loads(dest.read_text())
  retrieval=json.loads((OUT/'retrieval'/f'{g["video_id"]}.json').read_text());candidates=retrieval['candidates'][mode]
  content=[]
  for c in candidates:
   s=c['knowledge'];content.append({key:s.get(key,'') for key in ('symbol_id','canonical_name','aliases','cultural_dimension','dimension_code','visual_features','cultural_description','typical_scene')})
  prompt=PROMPT+'\n以下为检索到的待核实文化知识（不是已经出现的事实；可不选）：\n'+json.dumps(content,ensure_ascii=False)
  print('RUN',g['video_id'],mode,flush=True);result=api_raw(ROOT/g['video_path'],'video_url',prompt,OUT/'api'/g['video_id']/mode,parse);result.update(video_id=g['video_id'],mode=mode,candidates=candidates,prompt_version='c_only_v1',protocol_sha256=sha(OUT/'protocol.json'));dump(dest,result);print('DONE',g['video_id'],mode,result['status'],flush=True);return result
 with ThreadPoolExecutor(max_workers=workers) as pool:
  futures=[pool.submit(worker,g,m) for g in items for m in ('image','multimodal')]
  for future in as_completed(futures):future.result()
 print('Test extension complete',flush=True)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('phase',choices=('prepare','smoke','run','report'));p.add_argument('--workers',type=int,default=3);a=p.parse_args()
 if a.phase=='prepare':prepare()
 elif a.phase=='smoke':smoke()
 elif a.phase=='run':run(a.workers)
 else:
  from src.experiments.c_evaluation import evaluate
  evaluate(ROOT,OUT,OLD)
if __name__=='__main__':main()
