"""Verify all terminal attempts and assemble the C-only extension deliverables."""
import json,sys
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from scripts.innovation2.run_image_multimodal_c import OUT,OLD,verify,dump,sha,csvwrite
from src.experiments.c_evaluation import evaluate

def main():
 verify();items=json.loads((OUT/'test_manifest.json').read_text())['items'];failures=[];attempts=[]
 for g in items:
  for mode in ('image','multimodal'):
   path=OUT/'predictions'/g['video_id']/f'{mode}.json'
   if not path.exists():raise RuntimeError('Not completed: '+str(path))
   r=json.loads(path.read_text());assert r['protocol_sha256']==sha(OUT/'protocol.json');assert 1<=len(r['attempts'])<=2
   for a in r['attempts']:
    saved=OUT/'api'/g['video_id']/mode/f'attempt_{a["attempt"]}.json';assert saved.exists();assert json.loads(saved.read_text())==a
    attempts.append(dict(video_id=g['video_id'],mode=mode,**a))
   if r['status']!='completed':failures.append(dict(video_id=g['video_id'],mode=mode,status=r['status']))
 evaluate(ROOT,OUT,OLD)
 result=json.loads((OUT/'results.json').read_text());rows=result['records'];assert len(rows)==120 and len({(r['video_id'],r['mode']) for r in rows})==120
 # Error interpretation is deliberately separate from frozen identity scoring.
 # A generic object label is not automatically a wrongly named landmark.
 from src.knowledge.symbol_kb import SymbolKnowledgeBase
 from src.experiments.c_evaluation import norm
 kb=SymbolKnowledgeBase();aliases={norm(a) for s in kb.symbols for a in [s['canonical_name']]+str(s.get('aliases','')).split('|') if len(norm(a))>=2}
 generic={'宝塔','石狮子','折扇','红色灯笼','红色横幅','红墙黄瓦','飞檐斗拱','红墙灰瓦','红墙黄琉璃瓦','中轴对称布局','现代桥梁','高层建筑群','灰色高层建筑群','红砖建筑群','国徽','红旗','护城河','城墙','国际旗帜阵列'}
 diagnostics=[]
 for row in rows:
  labels=[]
  for name in row['predicted_names']:
   if name in aliases:kind='registered_identity'
   elif name in generic:kind='generic_visual_or_object_description'
   elif any(a in name for a in aliases):kind='registered_name_inside_unmatched_phrase'
   else:kind='unregistered_specific_name_or_unresolved'
   labels.append(dict(name=name,kind=kind))
  group=('no_specific_identity_generic_only' if labels and all(x['kind']=='generic_visual_or_object_description' for x in labels) else 'identity_phrase_not_normalized' if not row['main_correct'] and any(x['kind']=='registered_name_inside_unmatched_phrase' for x in labels) else row['outcome'])
  diagnostics.append(dict(video_id=row['video_id'],mode=row['mode'],diagnostic=group,name_details=labels,changes_frozen_metric=False))
 dump(OUT/'semantic_error_diagnostics.json',dict(note='Text interpretation aid, not new GT, not a scoring-rule update. Generic descriptions and unmatched naming modifiers are separated from specific misidentification. Unregistered names still require visual adjudication.',records=diagnostics))
 for mode in ('free','text','image','multimodal'):
  rs=[r for r in rows if r['mode']==mode];assert len(rs)==30
  for r in rs:
   assert r['tp']+r['fn']==1
   assert r['strict_correct']==(r['main_correct'] and r['fp']==0)
 audit=dict(new_tasks=60,all_four_method_rows=120,attempts=len(attempts),attempt_statuses=dict(Counter(a['status'] for a in attempts)),terminal_failures=failures,all_frozen_input_hashes_verified=True,all_raw_replies_saved_before_parsing=True,all_denominators_30=True,zero_main_entity_count_for_missing_identity=True,rule_correction_log='evaluation_implementation_correction.json',reference_status='pending independent human confirmation',no_reference_relabeling_or_parameter_changes=True,finalizer_sha256=sha(__file__))
 audit['execution_interruption_record']='execution_interruption.json'
 audit['interrupted_requests_without_reply']=len(json.loads((OUT/'execution_interruption.json').read_text())['unfinished_requests']) if (OUT/'execution_interruption.json').exists() else 0
 dump(OUT/'final_audit.json',audit)
 report=OUT/'report.md';text=report.read_text();summary=result['summaries'];s={r['mode']:r for r in summary}
 text+='\n## 实际结果的范围\n\n'
 text+=f"本次Image完成{s['image']['completed']}/30，Multimodal完成{s['multimodal']['completed']}/30；新任务均按固定规则保留，未删除失败。"
 text+=f"按冻结的主要实体登记名规则，暂定命中分别为{s['image']['main_correct']}/30和{s['multimodal']['main_correct']}/30。"
 diff=s['multimodal']['main_correct']-s['image']['main_correct'];text+=f"二者差值为{diff:+d}条（{diff/30:+.2%}）；这是样本内暂定差异，不预设图文融合最优，也不推断总体统计显著性。\n\n"
 text+='阅读完整限制：[指标阅读与人工复核注意事项](evaluation_reading_notes.md)；[待核验参考问题](reference_review_notes.md)。登记名严格匹配可能将正确身份的自然语言限定词记为未匹配；不能把所有未匹配等同于视觉命名错误。\n\n'
 text+='[材料与实现清单](materials_and_implementation.md)、[四组方法配置](method_configs.json)、[分数尺度与聚合审计](score_scale_and_aggregation_audit.json)、[近重复筛查](perceptual_overlap_audit.json)、[最终运行审计](final_audit.json)。\n\n'
 text+='融合/解析合计7项测试通过。图片pHash筛查未发现Hamming≤6的测试关键帧与索引原图对，但不保证无同源或近重复。冻结后有一项标点规范化实现修正，按同一规则应用四组并完整记录；未变更权重、Top-K、阈值或提示。\n\n'
 text+='运行进程曾以143终止（具体外部终止来源未确定），3个已发请求未取得回复，保存中断记录后仅续跑未完成任务；这3个请求另计，不伪称从未发出或有可恢复原始回复。终止失败任务仍按冻结重试上限保留，不循环刷成功。\n\n'
 text+='[语义错误解释辅助记录](semantic_error_diagnostics.json)进一步区分仅给出一般物件/视觉描述、含登记名但措辞未规范化、具体身份不匹配；它不更改冻结指标，避免把全部未命中笼统称作错误命名。\n\n'
 text+='每个视频只有一个预定参考主体，因此实体微平均Recall在这里与主要实体Accuracy数值相同，不是额外的独立验证；P/F1只增加参考集外输出的惩罚信息。完整多实体评价仍需人工穷尽标注。\n\n'
 text+='历史Text检索指标为Recall@5，本次Image和Multimodal为冻结的Recall@3，不将不同K值当作同等检索设置直接比较。旧报告的实体分数还采用了“所有断言都有效”及限定词归一化规则，本轮改为预定主要实体命中与严格无附加不匹配两列，因此Free/Text重新评分值可能与旧报告不同；模型输出本身没有重跑或修改。\n\n'
 text+='案例分析见[case_analysis.md](case_analysis.md)；该文件基于保存的实际输出和已查看关键帧，不以笼统“模型幻觉”代替原因。\n'
 indexed={(r['video_id'],r['mode']):r for r in rows};paired=[]
 for g in items:
  v=g['video_id'];a=indexed[v,'image'];b=indexed[v,'multimodal']
  paired.append(dict(video_id=v,reference=g['gt_symbols'],image_names=a['predicted_names'],multimodal_names=b['predicted_names'],image_main_correct=a['main_correct'],multimodal_main_correct=b['main_correct'],image_strict_correct=a['strict_correct'],multimodal_strict_correct=b['strict_correct'],main_result_changed=a['main_correct']!=b['main_correct']))
 csvwrite(OUT/'paired_image_multimodal.csv',paired)
 text+='\n## Image与Multimodal差异核对\n\n[逐视频配对表](paired_image_multimodal.csv)。主要实体命中结果变化的样本：'
 changed=[r for r in paired if r['main_result_changed']]
 text+='；'.join(r['video_id']+'：Image='+str(r['image_names'])+'，Multimodal='+str(r['multimodal_names']) for r in changed) if changed else '无'
 text+='。\n\n本次差异仅“故宫”一条，涉及宫殿单体与建筑群的身份层级；额外提到太和殿也使该条未通过严格无附加不匹配指标。本轮多1条命中不应解释为普遍、更稳定的图文融合优势，仍需确认参考身份粒度。\n'
 report.write_text(text)
 print(json.dumps(audit,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
