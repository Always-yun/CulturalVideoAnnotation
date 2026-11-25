"""为 30 个实验用视频建立 GT

GT 来源：
1. 视频文件名（语义直接指向）
2. 已有 gate_on_test/per_video.csv 的 gt_symbols（v2 KB 更新后 sample_type 重新判定）
3. 人工判断（不臆造）

sample_type 判定：
- Known: GT 符号在 v2 KB 有 canonical_name 或 alias 命中
- Easy Unknown: 不在 KB 且无同类/同维度/父子/视觉高度相似
- Hard Unknown: 不在 KB 但 KB 有同类/同维度/父子/视觉高度相似

注意：旧 ablation 里标 gap 的 神武门 / 中关村国际创新中心 / 中关村展示中心 需要重新判定
- 神武门：Hard Unknown（父实体故宫在 KB；同 ANCIENT 维度还有太和殿、角楼等）
- 中关村国际创新中心：Known（v2 新增 CN2_TECH_006）
- 中关村展示中心：Known（v2 新增 CN2_TECH_005）
"""
import os, json, csv

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KB_JSON = os.path.join(ROOT, "archives", "knowledge_base_history_20261119", "chinese_cultural_symbols_v2.json")
VIDEO_DIR = os.path.join(ROOT, 'experiments/innovation2/data/videos')
OUT_CSV = os.path.join(ROOT, 'experiments/innovation2/data/cultural_eval', "cultural_eval_30.csv")
os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)

# v2 KB 别名索引
kb = json.load(open(KB_JSON, encoding="utf-8"))
name_to_symbol = {}
for s in kb["symbols"]:
    name_to_symbol[s["canonical_name"]] = s
    for alias in s.get("aliases", "").split("|"):
        alias = alias.strip()
        if alias and alias not in name_to_symbol:
            name_to_symbol[alias] = s
    for kw in s.get("keywords", "").split("|"):
        kw = kw.strip()
        if kw and kw not in name_to_symbol:
            name_to_symbol[kw] = s


def resolve(name):
    """尝试在 v2 KB 里解析 GT 名称 → (symbol_id, canonical_name, dimension_code) 或 None"""
    # 精确
    if name in name_to_symbol:
        s = name_to_symbol[name]
        return s["symbol_id"], s["canonical_name"], s["dimension_code"]
    # 子串
    for k, s in name_to_symbol.items():
        if k in name or name in k:
            return s["symbol_id"], s["canonical_name"], s["dimension_code"]
    return None


# 30 个视频的 GT（人工确定）
GT = {
    "cbd":                    ("CBD",                               "MODERN", "ablation_per_video + 文件名"),
    "cbd1":                   ("CBD",                               "MODERN", "ablation_per_video + 文件名"),
    "cbd2":                   ("CBD",                               "MODERN", "ablation_per_video + 文件名"),
    "cbd3":                   ("CBD",                               "MODERN", "文件名"),
    "中关村1号":              ("中关村壹号",                          "TECH",  "ablation_per_video + 文件名"),
    "中关村国际创新中心":       ("中关村国际创新中心",                   "TECH",  "文件名（v2 KB 新增 CN2_TECH_006）"),
    "中关村展示中心":           ("中关村国家自主创新示范区展示中心",       "TECH",  "文件名（v2 KB 新增 CN2_TECH_005）"),
    "京剧青衣":                ("京剧",                              "FOLK",  "ablation_per_video + 文件名"),
    "人民大会堂":              ("人民大会堂",                          "ANCIENT", "文件名（KB 未收录，需确认）"),
    "人民大会堂1":             ("人民大会堂",                          "ANCIENT", "文件名（KB 未收录，需确认）"),
    "人民英雄纪念碑":           ("人民英雄纪念碑",                       "RED",   "ablation_per_video + 文件名"),
    "人民英雄纪念碑1":          ("人民英雄纪念碑",                       "RED",   "ablation_per_video + 文件名"),
    "兔爷":                    ("兔儿爷",                              "FOLK",  "ablation_per_video + 文件名"),
    "北大":                    ("北京大学",                            "TECH",  "ablation_per_video + 文件名"),
    "北大1":                   ("北京大学",                            "TECH",  "ablation_per_video + 文件名"),
    "国博":                    ("中国国家博物馆",                       "RED",   "文件名（KB 别名 国博 命中 BJ_RED_006）"),
    "天安门":                  ("天安门广场",                          "RED",   "文件名（KB 别名 天安门 命中 BJ_RED_002）"),
    "天安门1":                 ("天安门广场",                          "RED",   "ablation_per_video + 文件名"),
    "太和殿":                  ("太和殿",                              "ANCIENT", "ablation_per_video + 文件名"),
    "庙会":                    ("北京庙会",                            "FOLK",  "ablation_per_video + 文件名"),
    "故宫":                    ("故宫",                                "ANCIENT", "文件名"),
    "故宫全景":                ("故宫",                                "ANCIENT", "ablation_per_video + 文件名"),
    "未来科学城":               ("未来科学城",                          "TECH",  "ablation_per_video + 文件名"),
    "清华":                    ("清华大学",                            "TECH",  "文件名（KB 别名 清华 命中 BJ_INNOV_007）"),
    "神武门":                  ("神武门",                              "ANCIENT", "文件名（KB 未收录但父实体故宫在 KB → Hard Unknown）"),
    "糖葫芦":                  ("冰糖葫芦",                            "FOLK",  "文件名（KB 无小吃类符号 → Easy Unknown）"),
    "胡同":                    ("胡同",                                "FOLK",  "文件名"),
    "胡同1":                   ("胡同",                                "FOLK",  "ablation_per_video + 文件名"),
    "角楼":                    ("角楼",                                "ANCIENT", "文件名"),
    "角楼1":                   ("角楼",                                "ANCIENT", "ablation_per_video + 文件名"),
    "鸟巢":                    ("鸟巢",                                "TECH",  "文件名"),
}


def classify_sample_type(gt_symbol, gt_dim_code):
    """判定 sample_type"""
    resolved = resolve(gt_symbol)
    if resolved is not None:
        return "known", resolved  # 在 KB 里

    # 不在 KB。判断 Easy / Hard Unknown
    # Hard Unknown 判定：KB 存在
    #   - 同维度实体（≥2 个）
    #   - 或 父子实体关系（神武门→故宫）
    #   - 或 视觉高度相似 / 名称相似

    # 1. 同维度实体计数
    same_dim = sum(1 for s in kb["symbols"]
                   if gt_dim_code and (s["dimension_code"] == gt_dim_code
                                       or s["dimension_code"].startswith(gt_dim_code + ";")
                                       or s["dimension_code"].endswith(";" + gt_dim_code)))

    # 2. 父子实体关系（特例硬编码）
    parent_child_map = {
        "神武门": "故宫",      # 故宫的北门
        "太和殿": "故宫",      # 特例：太和殿在 KB 且不在 Unknown 列表；但就算 parent-child 也要看 GT 本身是否 Known
        "角楼": "故宫",        # 角楼也 Known
    }
    has_parent = (gt_symbol in parent_child_map
                  and parent_child_map[gt_symbol] in name_to_symbol)

    # 3. 名字相似度（子串重叠）
    name_substr_overlap = any(gt_symbol in s["canonical_name"]
                              or s["canonical_name"] in gt_symbol
                              or any(gt_symbol in a or a in gt_symbol
                                     for a in s.get("aliases","").split("|"))
                              for s in kb["symbols"])

    # 4. 同文化类型 / 同视觉场景粗略判断
    # ANCIENT 古建筑群体 → 同维度且 visual_features 共享"红墙""黄瓦""琉璃"等
    # 这里简化：同维度 ≥ 5 个 + 古建筑场景 → Hard
    hard_signals = 0
    if gt_dim_code == "ANCIENT" and same_dim >= 10:
        hard_signals += 1
    if gt_dim_code == "FOLK" and same_dim >= 5:
        hard_signals += 1
    if has_parent:
        hard_signals += 1
    if name_substr_overlap and same_dim >= 3:
        hard_signals += 1

    if hard_signals >= 1:
        return "hard_unknown", None
    return "easy_unknown", None


def main():
    rows = []
    video_files = sorted(os.listdir(VIDEO_DIR))
    for fn in video_files:
        if not fn.endswith(".mp4"):
            continue
        video_id = os.path.splitext(fn)[0]
        video_path = os.path.join('experiments/innovation2/data/videos', fn)

        if video_id not in GT:
            rows.append({
                "video_id": video_id, "video_path": video_path,
                "ground_truth_symbol": "", "ground_truth_dimension": "",
                "kb_covered": "", "sample_type": "",
                "gt_source": "", "review_status": "needs_review",
                "notes": "视频名未在 GT 表中，需人工补充",
            })
            continue

        gt_sym, gt_dim, gt_src = GT[video_id]
        stype, resolved = classify_sample_type(gt_sym, gt_dim)

        kb_cov = (stype == "known")

        notes = ""
        if stype == "hard_unknown":
            notes = "Hard Unknown: 父实体/同类实体在 KB；详见 classification 逻辑"
        elif stype == "easy_unknown":
            notes = "Easy Unknown: 不在 KB 且无强匹配信号"

        # 人民大会堂：KB 未收录，硬编码走 Hard Unknown（因为属于国家重要建筑，有同维度同类）
        if video_id in ("人民大会堂", "人民大会堂1"):
            # ANCIENT 维度 KB 有很多古建筑；且人民大会堂的建筑风格和故宫/天安门/天坛共享"琉璃瓦""重檐""红墙"视觉特征
            stype = "hard_unknown"
            kb_cov = False
            notes = "Hard Unknown: ANCIENT 维度 KB 有故宫/天安门/天坛等古建筑，同类型同视觉"

        # 糖葫芦：硬编码 Easy Unknown（无同类型同场景）
        if video_id == "糖葫芦":
            stype = "easy_unknown"
            kb_cov = False
            notes = "Easy Unknown: KB 无北京小吃/民俗食品类符号"

        # 神武门：Hard Unknown（父实体故宫在 KB；同 ANCIENT 有太和殿/角楼/祈年殿）
        if video_id == "神武门":
            stype = "hard_unknown"
            kb_cov = False
            notes = "Hard Unknown: 父实体故宫 BJ_GUDU_001 在 KB；同 ANCIENT 有角楼/太和殿/祈年殿"

        rows.append({
            "video_id": video_id,
            "video_path": video_path,
            "ground_truth_symbol": gt_sym,
            "ground_truth_dimension": gt_dim,
            "kb_covered": "yes" if kb_cov else "no",
            "sample_type": stype,
            "gt_source": gt_src,
            "review_status": "frozen",
            "notes": notes,
        })

    fields = ["video_id", "video_path", "ground_truth_symbol", "ground_truth_dimension",
              "kb_covered", "sample_type", "gt_source", "review_status", "notes"]
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    # 打印分布
    from collections import Counter
    st = Counter(r["sample_type"] for r in rows)
    dim = Counter(r["ground_truth_dimension"] for r in rows if r["ground_truth_dimension"])
    print(f"总计视频: {len(rows)}")
    print(f"可用视频: {sum(1 for r in rows if r['review_status']=='frozen')}")
    print(f"sample_type 分布: {dict(st)}")
    print(f"dimension 分布: {dict(dim)}")
    print(f"输出: {OUT_CSV}")
    print()
    for r in rows:
        print(f"  [{r['sample_type']:15s}] {r['video_id']:15s} -> {r['ground_truth_symbol']:20s} ({r['ground_truth_dimension']})  kb={r['kb_covered']}")


if __name__ == "__main__":
    main()
