"""Reference-relative, provisional C-layer entity evaluation and trace export."""
import csv,json,re
from pathlib import Path
from collections import Counter
from src.knowledge.symbol_kb import SymbolKnowledgeBase

MODES=('free','text','image','multimodal')
def norm(s):return re.sub(r'[\s“”\"\[\]。]', '',str(s)).lower()
def core_names(core):
 text=str(core).strip()
 if '为' in text:text=text.split('为',1)[1]
 text=text.split('。',1)[0];parts=[];current=[];depth=0
 for ch in text:
  if ch in '（(':depth+=1
  elif ch in '）)':depth=max(0,depth-1)
  if ch in '、,，;；' and depth==0:parts.append(''.join(current));current=[]
  else:current.append(ch)
 parts.append(''.join(current))
 # An explanatory parenthesis is not a second asserted identity. No removal
 # of suffixes or scene-type words: only canonical and pre-registered aliases.
 return list(dict.fromkeys(norm(re.sub(r'（[^（）]*）|\([^()]*\)','',p)) for p in parts if norm(p)))
def categories(value,mapping):
 return {code for name,code in mapping.items() if name in str(value)}|{code for code in mapping.values() if re.search(r'\b'+code+r'\b',str(value))}
def ratios(tp,fp,fn):
 p=tp/(tp+fp) if tp+fp else 0.;r=tp/(tp+fn) if tp+fn else 0.;return dict(precision=p,recall=r,f1=2*p*r/(p+r) if p+r else 0.)
def evaluate(root,out,old):
 from scripts.innovation2.run_image_multimodal_c import dump,csvwrite,sha
 from src.pipeline.cultural_rag import parse_c_layer
 root,out,old=map(Path,(root,out,old));kb=SymbolKnowledgeBase();protocol=json.loads((out/'protocol.json').read_text());items=json.loads((out/'test_manifest.json').read_text())['items'];rows=[]
 historical = {(r['video_id'],r['mode']):r for r in json.loads((old/'results.json').read_text())['records']}
 lookup={};canonical={}
 for s in kb.symbols:
  sid=s['symbol_id'];canonical[sid]=s['canonical_name']
  for a in [s['canonical_name']]+str(s.get('aliases','')).split('|'):
   if a:lookup.setdefault(norm(a),set()).add(sid)
 for g in items:
  target=g['gt_symbol_ids'] or ['OUTSIDE_KB:'+norm(g['gt_symbols'][0])]
  for a in g['gt_symbols']:lookup.setdefault(norm(a),set()).update(target)
 for g in items:
  for mode in MODES:
   path=(old if mode in ('free','text') else out)/'predictions'/g['video_id']/f'{mode}.json';result=(historical[(g['video_id'],mode)] if mode in ('free','text') else json.loads(path.read_text()) if path.exists() else {'status':'not_run'});raw=None;c={};candidates=[];status=result['status'];trace={}
   if mode in ('free','text'):
    tracepath=old/'traces'/g['video_id']/mode/'trace.json'
    if not tracepath.exists():
     paths=sorted((old/'workers').glob('*/traces/'+g['video_id']+'/'+mode+'/trace.json'))
     if paths:tracepath=paths[0]
    if tracepath.exists():trace=json.loads(tracepath.read_text());raw=trace.get('final_annotation');c=parse_c_layer(raw or '')
    candidates=result.get('topk_candidates',[])
    if status=='failed':status='parse_failure' if result.get('error_type') in ('ValueError','SceneEvidenceError','JSONDecodeError') else 'service_failure_or_legacy_unclassified'
   else:raw=result.get('raw_reply');c=result.get('parsed') or {};candidates=result.get('candidates',[])
   core=c.get('core_symbol','');unknown=bool(c.get('unknown_symbol')) or norm(core) in {'unknown_symbol','无法确认','无','无明确文化符号','未知','none',''}
   names=[] if unknown or status!='completed' else core_names(core);pred=[];ambiguous=[]
   for name in names:
    matches=lookup.get(name,set())
    if len(matches)==1:pred.append(next(iter(matches)))
    else:
     pred.append('UNRESOLVED:'+name)
     if len(matches)>1:ambiguous.append(dict(name=name,possible_ids=sorted(matches)))
   pred=set(pred);truth=set(g['gt_symbol_ids'] or ['OUTSIDE_KB:'+norm(g['gt_symbols'][0])]);tp=len(pred&truth);fp=len(pred-truth);fn=len(truth-pred)
   category_text=c.get('raw_block','').split('核心符号',1)[0] or c.get('dimension','')
   actual_category=categories(category_text,kb.dimension_codes);target_category=set(g['gt_dimension_code'].split(';'));category_tp=len(actual_category&target_category);category_fp=len(actual_category-target_category);category_fn=len(target_category-actual_category)
   hit=bool(pred&truth);candidate_ids=[r['symbol_id'] for r in candidates];covered=bool(g['gt_symbol_ids'])
   recall=bool(set(candidate_ids)&truth) if covered and mode!='free' else None
   outcome=('not_run' if status=='not_run' else 'service_failure' if status.startswith('service') else 'parse_failure' if status=='parse_failure' or (status=='completed' and not c.get('core_symbol')) else 'no_identity' if not pred else 'correct_main' if hit else 'wrong_identity')
   row=dict(video_id=g['video_id'],mode=mode,status=status,outcome=outcome,reference_names=g['gt_symbols'],reference_ids=sorted(truth),predicted_names=names,predicted_ids=sorted(pred),main_correct=hit,strict_correct=hit and fp==0,reference_extra_entities=sorted(pred-truth),tp=tp,fp=fp,fn=fn,predicted_categories=sorted(actual_category),reference_categories=sorted(target_category),category_exact=actual_category==target_category,category_tp=category_tp,category_fp=category_fp,category_fn=category_fn,recall_at_k=recall,candidate_ids=candidate_ids,raw_reply=raw,c_layer_natural_language=c.get('raw_block',''),auxiliary_extraction={'production_schema_field':False,'source':'core_symbol line in existing C natural-language block','ambiguous_aliases':ambiguous},source_path=str(path.relative_to(root)),attempts=result.get('attempts',[]),raw_available=raw is not None,full_c_available=bool(c.get('raw_block')))
   if mode in ('free','text'):
    row['source_path']=str((old/'results.json').relative_to(root))
    row['original_trace_path']=str(tracepath.relative_to(root)) if tracepath.exists() else None
    row['historical_model_config_path']=str((old/'model_config.json').relative_to(root))
   rows.append(row)
   dump(out/'evaluated'/g['video_id']/f'{mode}.json',row)
 summaries=[]
 for mode in MODES:
  rs=[r for r in rows if r['mode']==mode];tp=sum(r['tp'] for r in rs);fp=sum(r['fp'] for r in rs);fn=sum(r['fn'] for r in rs);ctp=sum(r['category_tp'] for r in rs);cfp=sum(r['category_fp'] for r in rs);cfn=sum(r['category_fn'] for r in rs);retr=[r for r in rs if r['recall_at_k'] is not None];completed=[r for r in rs if r['status']=='completed'];n=len(rs)
  summaries.append(dict(mode=mode,videos=n,completed=len(completed),not_run=sum(r['status']=='not_run' for r in rs),main_correct=sum(r['main_correct'] for r in rs),provisional_accuracy=sum(r['main_correct'] for r in rs)/n,strict_correct=sum(r['strict_correct'] for r in rs),provisional_strict_accuracy=sum(r['strict_correct'] for r in rs)/n,completed_only_accuracy=sum(r['main_correct'] for r in completed)/len(completed) if completed else None,tp=tp,fp=fp,fn=fn,**ratios(tp,fp,fn),extra_entity_videos=sum(bool(r['reference_extra_entities']) for r in rs),outcomes=dict(Counter(r['outcome'] for r in rs)),category_exact_correct=sum(r['category_exact'] for r in rs),category_exact_accuracy=sum(r['category_exact'] for r in rs)/n,category_micro=ratios(ctp,cfp,cfn),retrieval_recall_at_k=sum(r['recall_at_k'] for r in retr)/len(retr) if retr else None,retrieval_denominator=len(retr),raw_available=sum(r['raw_available'] for r in rs)))
 dump(out/'results.json',dict(reference_status='pending human confirmation; all metrics provisional',protocol=protocol,summaries=summaries,records=rows));csvwrite(out/'summary.csv',summaries);csvwrite(out/'per_video_evaluation.csv',rows)
 differences=[]
 for g in items:
  group={r['mode']:r for r in rows if r['video_id']==g['video_id']};differences.append(dict(video_id=g['video_id'],reference=g['gt_symbols'],**{m:dict(names=group[m]['predicted_names'],correct=group[m]['main_correct'],status=group[m]['status']) for m in MODES}))
 dump(out/'differences.json',differences)
 md=['# 文化知识增强C层实验：Image与Multimodal补充运行','', '**结果状态：参考答案待人工核验，所有指标均为相对现有标签的暂定值，不是最终准确率。**','', '按用户要求不重跑Free/Text，直接从已存六维原始回复提取完整C层。本次Image/Multimodal只生成C层。前后提示条件、知识库版本及失败重试规则存在差异，不能将方法差值完全归因为检索模态。','', '## 当前指标','', '|方法|完成/30|主要实体命中|暂定Accuracy|无附加不匹配实体的命中|参考集TP/FP/FN|实体微P/R/F1|类别集合完全匹配|','|---|---:|---:|---:|---:|---|---|---|']
 for s in summaries:md.append(f'|{s["mode"]}|{s["completed"]}/30|{s["main_correct"]}|{s["provisional_accuracy"]:.2%}|{s["strict_correct"]}|{s["tp"]}/{s["fp"]}/{s["fn"]}|{s["precision"]:.3f}/{s["recall"]:.3f}/{s["f1"]:.3f}|{s["category_exact_correct"]}/30|')
 md+=['','## 材料、参数与可比性','',f'当前知识库126个实体、43张库内确认图片；13张作为独立开发查询图，严格从本次测试索引留出；测试索引30张，覆盖20实体。库外人民大会堂、糖葫芦4张虽确认，尚无实体知识条目，不伪造候选。',f'冻结时间：{protocol["frozen_at"]}；开发选择：{json.dumps(protocol["parameters"],ensure_ascii=False)}。','开发集仅为13张静态参考图，覆盖13个实体，标签来自用户已确认的图文对应。没有独立开发视频，存在照片到视频的域差异；不将其称为独立视频开发集。查询图与参考索引原图SHA-256不相交，不能据此排除同源或近重复。','', 'CLIP ViT-B/32，CPU，权重SHA-256、环境与全部冻结文件见protocol.json、frozen_hashes.json和environment.json。每张图先归一化，实体内均值后再归一化；视频使用旧实验相同4帧均值并归一化。参考图数量不会通过累加分数直接提高实体分。', '关键词原始分和图像余弦分均保存；各自转为实体排名分（并列平均排名），再按冻结权重融合。排名分是排序依据，不是正确概率。缺失某实体模态记为缺失并在融合项贡献0，不逐实体重新分配权重；全局某模态缺失才将总权重移给可用模态。纯Image不返回文本候选。','', '本次新标注直接发送原始视频，温度0.1、最大2048 tokens、SDK重试0，每任务最多2次（服务或解析失败均重试），超时300秒；每次原始响应在解析前落盘。Image/Multimodal的任务级规则一致。历史Free/Text规则和已丢失原始失败回复不能补造。模型实际返回model/id/finish_reason保存于attempt文件；glm-4v是服务别名，不能保证跨时间后端修订相同。', 'Identity Evidence Gate在旧代码实际为名称/别名或视觉特征片段匹配，OCR与参考图身份识别另有不可用标志；本次延续旧实验不启用，亦不启用候选闭集强制选择或后处理替换。没有训练、损失函数、知识图谱推理。','', '## 评价规则与局限','', '30条任务均预设一个主要实体。主指标允许额外实体，但单独报告参考集外实体；严格指标要求命中主要实体且无额外不匹配。名称仅按冻结规范名及登记别名匹配，去重，不用关键词、子串或仅类别正确计分。所有服务/解析失败留在30条分母，空预测产生FN；拒绝身份与错误命名分开。completed-only仅为辅助。P/R/F1零分母记0。','主要实体标签不是完整画面实体集合：微平均P/R/F1与附加实体仅表示相对当前参考集的匹配，参考外不等于肉眼确认的错误。额外可见地标需人工补标才能判定。没有用模型自报置信度评价正确概率。','类别按完整标签集合匹配，另保存微平均；参考标签可能不完整或错误（例如人民大会堂原标签为ANCIENT），保持冻结并在参考表中供核验，不根据输出改标签。','检索Recall@K只对库内27个视频计分，分母不包含人民大会堂两条和糖葫芦一条。图像参考覆盖另列；C层自然语言全文和辅助实体抽取记录分开存，辅助字段不宣称属于生产Schema。','', '## 交付与运行','', '`reference_answers_for_review.csv`为待核验答案表；`test_manifest.json`为30视频及原关键帧清单；`protocol.json`与`frozen_hashes.json`为冻结配置；`development_*`为独立开发材料及全部参数试验。','`api/<video>/<method>/request.json`保存请求参数与知识文本，`attempt_*.json`保存完整原始回复、服务与解析失败、重试；`predictions/`为新标注；`evaluated/`为四组C层及辅助实体结果；`retrieval/`为全部原分、排序与候选知识。','`summary.csv`、`per_video_evaluation.csv`与`differences.json`为汇总和逐样本核对。历史六维回复保留原文件，没有覆盖或重跑。','', '复用入口：`python scripts/innovation2/run_image_multimodal_c.py prepare` → `smoke` → `run --workers 3` → `report`。冻结后任何输入或代码改变会拒绝续跑；已终止失败不会自动反复重试。','', '## 失败、拒绝与检索辅助统计','']
 for s in summaries:md +=[f'- {s["mode"]}：{s["outcomes"]}；原始回复可用{s["raw_available"]}/30；Recall@K={s["retrieval_recall_at_k"]}，分母{s["retrieval_denominator"]}。']
 (out/'report.md').write_text('\n'.join(md)+'\n')
 print(json.dumps(summaries,ensure_ascii=False,indent=2))
