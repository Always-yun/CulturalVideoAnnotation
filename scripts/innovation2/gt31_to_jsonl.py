"""把 31 个视频的 GT 转成 CulturalAblationExperiment 能读的 jsonl 格式

同时把 v2 KB 里的 symbol_id 解析进去（Known 样本必须精确到 symbol_id）。
"""
import os, json, csv

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KB_JSON = os.path.join(ROOT, "archives", "knowledge_base_history_20261119", "chinese_cultural_symbols_v2.json")
GT_CSV = os.path.join(ROOT, 'experiments/innovation2/data/cultural_eval', "cultural_eval_30.csv")
OUT = os.path.join(ROOT, 'experiments/innovation2/data/eval/cultural_ablation_gt_final31.jsonl')
os.makedirs(os.path.dirname(OUT), exist_ok=True)

kb = json.load(open(KB_JSON, encoding="utf-8"))
name_to_sid = {}
for s in kb["symbols"]:
    name_to_sid[s["canonical_name"]] = s["symbol_id"]
    for alias in s.get("aliases", "").split("|"):
        alias = alias.strip()
        if alias and alias not in name_to_sid:
            name_to_sid[alias] = s["symbol_id"]
    for kw in s.get("keywords", "").split("|"):
        kw = kw.strip()
        if kw and kw not in name_to_sid:
            name_to_sid[kw] = s["symbol_id"]

with open(GT_CSV, encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))

# 补 split：简单 test（本次不按 val/test 分）
# 对每个 video 判定 gt_symbol_ids：Known 则填 v2 KB 的 symbol_id，Unknown 则空数组
lines = []
missing = []
for r in rows:
    stype = r["sample_type"]
    gt_sym = r["ground_truth_symbol"]
    dim = r["ground_truth_dimension"]
    video_id = r["video_id"]
    video_path = r["video_path"]

    if stype == "known":
        sid = name_to_sid.get(gt_sym)
        if sid is None:
            # 子串模糊
            for k, v in name_to_sid.items():
                if gt_sym in k or k in gt_sym:
                    sid = v
                    break
        if sid is None:
            missing.append((video_id, gt_sym))
            gt_ids = []
        else:
            gt_ids = [sid]
        kb_cov = "hit"
    else:  # easy_unknown / hard_unknown
        gt_ids = []
        kb_cov = "gap"

    item = {
        "video_id": video_id,
        "video_path": video_path,
        "split": "test",
        "kb_coverage": kb_cov,
        "sample_type": stype,
        "gt_symbol_ids": gt_ids,
        "gt_symbols": [gt_sym],
        "gt_dimension_code": dim,
        "notes": r.get("notes", ""),
    }
    lines.append(json.dumps(item, ensure_ascii=False))

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

print(f"写入 {len(lines)} 条 → {OUT}")
if missing:
    print("WARNING 以下 Known 样本无法从 v2 KB 解析 symbol_id:")
    for v, s in missing:
        print(f"  {v}: {s}")
else:
    print("所有 Known 样本 symbol_id 解析成功")

from collections import Counter
print("sample_type:", Counter(json.loads(l)["sample_type"] for l in lines))
print("kb_coverage:", Counter(json.loads(l)["kb_coverage"] for l in lines))
