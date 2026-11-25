"""Render real saved cases with explicit observation limits; no expected outputs."""
import json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from scripts.innovation2.run_image_multimodal_c import OUT,OLD

def main():
 results=json.loads((OUT/'results.json').read_text());rows={(r['video_id'],r['mode']):r for r in results['records']};items={g['video_id']:g for g in json.loads((OUT/'test_manifest.json').read_text())['items']}
 eligible=[v for v in ('未来科学城','cbd','京剧青衣','国博') if not rows[v,'free']['main_correct'] and rows[v,'multimodal']['main_correct']]
 cases=[]
 if eligible:
  v=eligible[0]
  if v=='未来科学城':
   notes='已查看4个真实关键帧：前景为跨水面的灰色桥梁，周围大片树木，后方有红褐色及灰色建筑。不能仅凭通用桥梁/楼群独立确定园区名称。'
   analysis='Free只给出通用桥梁和建筑群，未给出预设园区身份。增强候选包含未来科学城，最终C层输出命中该登记名。属于从通用外观描述到具体身份的改善；只说明这条样本出现了改善，不排除C-only提示与旧六维提示的影响。未根据该成功样本调整参数。'
  elif v=='cbd':
   notes='已查看首帧：现代城市天际线，门型建筑、细长高楼和周边玻璃幕墙建筑可见。'
   analysis='Free列出若干子地标而未给出预设主要身份CBD；增强输出CBD。此处是主要实体任务的命名命中改善，不证明Free列出的每个子地标都错误；也不能排除输出格式差异。'
  elif v=='京剧青衣':
   notes='已查看4帧：传统服装的袖口、刺绣服饰、折扇及持扇动作；头部只局部可见。'
   analysis='Free输出服饰/折扇等描述，增强输出登记实体京剧。该案例受名称抽取粒度影响，不能把措辞规范化带来的分数差全视为视觉识别能力提高。'
  else:
   notes='已查看首帧：大型对称立面、列柱、国徽及红色装饰可见。'
   analysis='Free名称含建筑限定词或其他对象，增强按登记名输出；涉及严格名称归一化限制，不作纯视觉识别改善结论。'
  cases.append(dict(title='无知识库未命中主要身份，增强后命中',video=v,mode='multimodal',notes=notes,analysis=analysis,kind='main_identity_improvement'))
 cases.append(dict(title='加入知识后仍错误：北大湖塔场景',video='北大',mode='multimodal',notes='已查看4帧：湖面、树木与远处多层塔楼，塔在水中有倒影；关键帧未见可读场所名牌。',analysis='预定身份北京大学未进入两种Top-3候选。库内北京大学仅有校门参考图，不能代表本视频的湖塔视角；图像候选偏向角楼/西湖/清华。文本原分只命中西湖，故融合也未补入北京大学。Multimodal原回复明确排除雷峰塔后改判宝轮寺塔，进一步给出地理归属；这种具体身份结论没有可读名称证据支撑。属于候选漏召回、参考视角不足及相似塔楼混淆，而不是笼统用一个错误标签解释。',kind='retrieval_miss_and_similar_entity_confusion'))
 cases.append(dict(title='知识候选未带来改善且出现错误：人民大会堂',video='人民大会堂',mode='multimodal',notes='已查看4帧：仰视灰色石柱、对称门窗，中央上方有国徽。仅凭柱廊和国徽不能区分所有国家机构建筑。',analysis='Free命中了预定实体人民大会堂。本次知识库没有该实体条目，尽管人民大会堂的2张图片均已确认，仍未关联到正式实体，因而不会进入检索。候选包含清华大学、国博和天安门广场；增强回复选择国博，并在价值指向中直接以候选的“柱廊仰视/广场立面”说明作认定依据。这是库覆盖缺口、相似候选误选及解释将候选提升为画面身份的实际失败。前后Prompt不同，因此不把单次差异当作候选注入的独立因果证明；原文化类别ANCIENT也待核验。',kind='kb_gap_and_wrong_candidate_selection'))
 md=['# 实际成功与失败案例','','本文件只引用已保存的实际输出与已目视检查的关键帧。主要参考标签尚待人工确认；案例结论均相对当前预定身份。旧Free是六维回复中提取的C层，新方法只输出C，不能作纯模态因果归因。','','[已查看的关键帧联系图](case_keyframes_contact_sheet.jpg)（仅分析展示，不作为检索参考图）。','']
 for c in cases:
  v=c['video'];m=c['mode'];g=items[v];base=rows[v,'free'];enh=rows[v,m];retr=json.loads((OUT/'retrieval'/f'{v}.json').read_text());cands=retr['candidates'][m];md+=['## '+c['title'],'', '**输入视频**：['+v+']('+os.path.relpath(ROOT/g['video_path'],OUT)+')','', '**参考实体**：'+ '、'.join(g['gt_symbols'])+'；类别：'+g['gt_dimension_code']+'（待核验）。','',c['notes'],'']
  for f in g['keyframes']:
   md +=[f'![{v} {f["time_seconds"]:.2f}s]({os.path.relpath(ROOT/f["path"],OUT)})','']
  md+=['**实际检索候选**（分数仅供排序，不是身份正确概率）：','', '|顺序|实体|原始文本分|图像余弦|归一化文本/图像分|融合分|','|---|---|---:|---:|---|---:|']
  for i,r in enumerate(cands):md.append(f'|{i+1}|{r["knowledge"]["canonical_name"]}|{r["raw_text_score"]}|{r["raw_image_cosine"]}|{r["text_score"]}/{r["image_score"]}|{r["fusion_score"]:.6f}|')
  md+=['','**Free实际C层原文**：','', '```text',base['c_layer_natural_language'] or '(未取得有效C层)', '```','', '**'+m+'实际C层原文**：','', '```text',enh['c_layer_natural_language'] or '(未取得有效C层)', '```','', '**具体原因与范围**：'+c['analysis'],'',f'辅助抽取：Free={base["predicted_names"]}；{m}={enh["predicted_names"]}。','', f'[候选完整知识与原始排序](retrieval/{v}.json) · [Free抽取记录](evaluated/{v}/free.json) · [增强抽取记录](evaluated/{v}/{m}.json)','']
 (OUT/'case_analysis.md').write_text('\n'.join(md)+'\n');print('Actual cases:',[(c['video'],c['kind']) for c in cases])
if __name__=='__main__':main()
