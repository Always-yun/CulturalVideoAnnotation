"""Resolve historical worker observations without additional model calls.

Uses exactly the frozen C experiment ranking and four frames. Does not inspect
reference answers or final test predictions for parameter selection.
"""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from scripts.innovation2.run_image_multimodal_c import ROOT,OUT,OLD,verify,sha,dump,texts

def main():
 verify()
 import torch
 torch.set_num_threads(4)
 from src.knowledge.clip_encoder import CLIPEncoder
 from src.knowledge.symbol_kb import SymbolKnowledgeBase
 from src.pipeline.scene_evidence import retrieval_text
 from src.experiments.c_retrieval import fuse
 kb=SymbolKnowledgeBase();params=json.loads((OUT/'protocol.json').read_text())['parameters'];items=json.loads((OUT/'test_manifest.json').read_text())['items'];data=torch.load(OUT/'reference_index.pt',weights_only=False);encoder=CLIPEncoder(device='cpu');sources=[]
 for g in items:
  dest=OUT/'retrieval'/f'{g["video_id"]}.json'
  if dest.exists():continue
  paths=sorted((OLD/'workers').glob('*/predictions/'+g['video_id']+'/scene.json'))
  if not paths:continue
  source=paths[0];saved=json.loads(source.read_text());scene=saved['structured_scene'];sources.append(dict(path=str(source.relative_to(ROOT)),sha256=sha(source)))
  emb=encoder.encode_images([str(ROOT/f['path']) for f in g['keyframes']]).float();q=emb.mean(0);q=q/q.norm().clamp(min=1e-8);im=dict(zip(data['ids'],(data['centroids']@q).tolist()));t=texts(kb,retrieval_text(scene,[],False));modes={m:fuse(t,im,m,params['alpha'],params['top_k'],params['threshold']) for m in ('image','multimodal')}
  for ranked in modes.values():
   for row in ranked:
    s=dict(kb.get(row['symbol_id']));s.pop('reference_images',None);row['knowledge']=s
  if dest.exists():continue
  dump(OUT/'observations'/f'{g["video_id"]}.json',saved)
  dump(dest,dict(video_id=g['video_id'],observation_source='historical_worker_structured_observation',observation_source_path=str(source.relative_to(ROOT)),text_available=True,raw_text_scores=t,raw_image_cosines=im,candidates=modes))
  print('REUSED',g['video_id'],flush=True)
 dump(OUT/'worker_observation_resolution.json',dict(helper_sha256=sha(__file__),sources=sources,parameters_changed=False,policy='Only literal prior structured observations; no label/prediction feedback; uncertain_entities excluded from retrieval'))
if __name__=='__main__':main()
