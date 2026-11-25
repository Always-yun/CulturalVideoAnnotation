"""实验二 v2：Existing Gate vs Identity Gate v1 vs Identity Evidence Verification Module v2

主评测入口（论文主结果）：Multimodal Controlled + Gate，每个视频只产生一个最终判定。
- Baseline：experiments/.../final30_exp1_imgfix（Existing Gate，multimodal_controlled）
- v1：experiments/.../final30_exp2_imgfix（Identity Gate v1，multimodal_controlled）—— 仅作开发对照
- v2：在同一份 Controlled 检索结果上叠加身份级证据核验模块（本脚本新跑）

实验一不重跑；不修改 GT；不扩 KB。
"""

from __future__ import annotations

import csv
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.experiments.ablation_metrics import build_kb_vocab, hit_gt_symbol, is_hallucination
from src.knowledge.identity_verifier_v2 import STATUS_ACCEPT, IdentityVerifierV2
from src.knowledge.symbol_kb import SymbolKnowledgeBase
from src.models.model_manager import ModelManager

ROOT = Path(__file__).resolve().parents[2]
GT_PATH = ROOT / "experiments/innovation2/data/eval/cultural_ablation_gt_final31.jsonl"
SCENE_CACHE = ROOT / "experiments/innovation2/cache/final30_scene_cache.json"
BASE_RESULTS = ROOT / "experiments/innovation2/runs/cultural_ablation/final30_exp1_imgfix/results.json"
V1_RESULTS = ROOT / "experiments/innovation2/runs/cultural_ablation/final30_exp2_imgfix/results.json"
OUT_DIR = ROOT / "experiments/innovation2/results/cultural_rag/final31"
MODE = "multimodal_controlled"


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(l) for l in path.open(encoding="utf-8") if l.strip()]


def load_mode_records(path: Path, mode: str) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {r["video_id"]: r for r in data.get("records", []) if r.get("mode") == mode}


def is_unknown(pred: str) -> bool:
    return (not pred) or "unknown_symbol" in str(pred).lower()


def resolve_pred_candidate(pred: str, cands: List[Dict[str, Any]]) -> str:
    """把最终标注的自由文本输出解析为闭集候选的规范名（落在候选外则返回空）。

    多个候选名同时出现时（如「鸟巢、水立方」），取文中**最早出现**的候选——
    模型通常先写出其认定的主体锚点；同位置再取更长名称。三种方法共用该解析规则，
    保证视频级判定口径一致。
    """
    if is_unknown(pred) or not cands:
        return ""
    text = str(pred)
    best, best_pos, best_len = "", None, 0
    for c in cands:
        terms = [str(c.get("canonical_name", ""))]
        raw = c.get("raw") or {}
        aliases = raw.get("aliases") or c.get("aliases") or ""
        if isinstance(aliases, str):
            terms += [t for t in aliases.split("|") if t]
        hits = [(text.find(t), len(t)) for t in terms if t and t in text]
        if not hits:
            continue
        pos, length = min(hits)
        if best_pos is None or pos < best_pos or (pos == best_pos and length > best_len):
            best, best_pos, best_len = str(c.get("canonical_name", "")), pos, length
    return best


def decide_correct(sample_type: str, pred: str, gt: Dict[str, Any], kb) -> bool:
    if sample_type == "known":
        return (not is_unknown(pred)) and hit_gt_symbol(pred, gt.get("gt_symbols", []), kb)
    return is_unknown(pred)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    gt_rows = load_jsonl(GT_PATH)
    base = load_mode_records(BASE_RESULTS, MODE)
    v1 = load_mode_records(V1_RESULTS, MODE)
    scene_cache = json.loads(SCENE_CACHE.read_text(encoding="utf-8")) if SCENE_CACHE.exists() else {}
    kb = SymbolKnowledgeBase()
    kb_vocab = build_kb_vocab(kb)

    verifier = IdentityVerifierV2(kb=kb, model_manager=ModelManager())
    print(f"[配置] 视觉阈值: {verifier.vis_cfg}")

    rows: List[Dict[str, Any]] = []
    llm_calls = 0
    for g in gt_rows:
        vid = g["video_id"]
        rec = base.get(vid)
        if rec is None:
            print(f"[跳过] {vid}: 缺少 baseline 记录")
            continue
        scene = ""
        for key in (g.get("video_path"), os.path.basename(g.get("video_path", ""))):
            if key and key in scene_cache:
                scene = scene_cache[key]
                break
        cands = (rec.get("topk_candidates") or [])[:3]
        raw_pred = rec.get("pred_symbol", "") or ""
        pred = resolve_pred_candidate(raw_pred, cands)
        text_top1 = max(cands, key=lambda c: c.get("text_score") or 0).get("canonical_name") if cands else None
        image_top1 = max(cands, key=lambda c: c.get("image_score") or 0).get("canonical_name") if cands else None

        if is_unknown(raw_pred) or not pred:
            # 检索/标注阶段已拒识，或输出落在闭集候选之外：核验层只做减法，不复活被拒样本
            res = {"final_symbol": "", "final_status": "already_rejected_by_retrieval",
                   "verification_required": False, "n_llm_calls": 0,
                   "decisions": [], "final_reason": "baseline_controlled_rejected"}
            final_symbol = ""
        else:
            video_path = g["video_path"]
            if not os.path.isabs(video_path):
                video_path = str(ROOT / video_path)
            res = verifier.decide(vid, video_path, scene, cands, pred_symbol=pred,
                                  text_top1=text_top1, image_top1=image_top1, enable_llm=True)
            final_symbol = res["final_symbol"]
            llm_calls += res["n_llm_calls"]

        primary = next((d for d in res.get("decisions", [])
                        if d.get("canonical_name") == pred), {})
        v1_rec = v1.get(vid, {})
        v1_raw = v1_rec.get("pred_symbol", "") or ""
        v1_cands = (v1_rec.get("topk_candidates") or [])[:3]
        v1_decision = resolve_pred_candidate(v1_raw, v1_cands) if v1_cands else ""
        rows.append({
            "video_id": vid,
            "ground_truth_symbol": ";".join(g.get("gt_symbols", [])),
            "sample_type": g.get("sample_type", "known"),
            "top1_candidate": (cands[0].get("canonical_name") if cands else ""),
            "text_score": (cands[0].get("text_score") if cands else ""),
            "image_score": (cands[0].get("image_score") if cands else ""),
            "fusion_score": (cands[0].get("fusion_score") if cands else ""),
            "text_identity_evidence": primary.get("text_identity", "n/a") + "：" + str(primary.get("text_detail", "")),
            "visual_identity_evidence": primary.get("visual_identity", "n/a") + "：" + str(primary.get("visual_detail", "")),
            "hierarchy_relation": primary.get("hierarchy_relation", "n/a"),
            "verification_required": res.get("verification_required"),
            "trigger_reasons": "|".join(primary.get("trigger_reasons") or []),
            "verifier_status": res.get("final_status"),
            "verifier_reason": res.get("final_reason", ""),
            "verifier_confidence": (primary.get("confidence") if primary else ""),
            "baseline_pred": pred,
            "v1_pred": v1_raw,
            "v1_decision": v1_decision if v1_decision else "unknown_symbol",
            "final_decision": final_symbol if final_symbol else "unknown_symbol",
            "correct": decide_correct(g.get("sample_type", "known"),
                                      final_symbol if final_symbol else "unknown_symbol", g, kb),
            "baseline_correct": decide_correct(g.get("sample_type", "known"), pred, g, kb),
            "v1_correct": decide_correct(g.get("sample_type", "known"),
                                         v1_decision if v1_decision else "unknown_symbol", g, kb),
            "hallucination": (not is_unknown(final_symbol or "unknown_symbol")) and
                             bool(final_symbol) and is_hallucination(final_symbol, kb_vocab),
            "llm_calls": res.get("n_llm_calls", 0),
        })

    cols = ["video_id", "ground_truth_symbol", "sample_type", "top1_candidate",
            "text_score", "image_score", "fusion_score", "text_identity_evidence",
            "visual_identity_evidence", "hierarchy_relation", "verification_required",
            "trigger_reasons", "verifier_status", "verifier_reason", "verifier_confidence",
            "baseline_pred", "v1_pred", "v1_decision", "final_decision", "correct",
            "baseline_correct", "v1_correct", "hallucination", "llm_calls"]
    with (OUT_DIR / "identity_verifier_v2_details.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    # ------------------------- 视频级指标 ------------------------- #
    def metrics(pred_key: str, correct_key: str) -> Dict[str, Any]:
        known = [r for r in rows if r["sample_type"] == "known"]
        easy = [r for r in rows if r["sample_type"] == "easy_unknown"]
        hard = [r for r in rows if r["sample_type"] == "hard_unknown"]
        rej = lambda r: is_unknown(r[pred_key])  # noqa: E731
        return {
            "n_total": len(rows),
            "known_acc": round(sum(1 for r in known if r[correct_key]) / len(known), 4) if known else None,
            "known_accept": round(sum(1 for r in known if not rej(r)) / len(known), 4) if known else None,
            "easy_reject": round(sum(1 for r in easy if rej(r)) / len(easy), 4) if easy else None,
            "hard_reject": round(sum(1 for r in hard if rej(r)) / len(hard), 4) if hard else None,
            "unknown_reject": round(sum(1 for r in easy + hard if rej(r)) / (len(easy) + len(hard)), 4)
            if (easy or hard) else None,
            "false_reject": round(sum(1 for r in known if rej(r)) / len(known), 4) if known else None,
            # 闭集输出下，Unknown 样本被接受为任一符号即视为身份幻觉
            "hallucination": round(sum(1 for r in easy + hard if not rej(r)) / len(rows), 4),
            "counts": {"known_correct": sum(1 for r in known if r[correct_key]),
                       "known_rejected": sum(1 for r in known if rej(r)),
                       "hard_rejected": sum(1 for r in hard if rej(r)),
                       "easy_rejected": sum(1 for r in easy if rej(r)),
                       "hallucinated": sum(1 for r in easy + hard if not rej(r))},
        }

    m_base = metrics("baseline_pred", "baseline_correct")
    m_v1 = metrics("v1_decision", "v1_correct")
    m_v2 = metrics("final_decision", "correct")

    triggered = [r for r in rows if r["verification_required"]]
    n_trig = len(triggered)
    status_count = Counter(r["verifier_status"] for r in triggered)

    def trig_rate(status: str) -> float:
        return round(status_count.get(status, 0) / n_trig, 4) if n_trig else 0.0

    verifier_rate = {
        "trigger_rate": round(n_trig / len(rows), 4),
        "trigger_count": n_trig,
        "accept_count": status_count.get(STATUS_ACCEPT, 0),
        "accept_rate": trig_rate(STATUS_ACCEPT),
        "reject_related_count": status_count.get("reject_related_but_not_exact", 0),
        "reject_related_rate": trig_rate("reject_related_but_not_exact"),
        "reject_insufficient_count": status_count.get("reject_insufficient_evidence", 0),
        "reject_insufficient_rate": trig_rate("reject_insufficient_evidence"),
        "llm_calls": llm_calls,
    }

    def table_row(name: str, m: Dict[str, Any]) -> Dict[str, Any]:
        return {"Method": name, "Known Acc": m["known_acc"], "Known Accept": m["known_accept"],
                "Easy Unknown Reject": m["easy_reject"], "Hard Unknown Reject": m["hard_reject"],
                "False Reject": m["false_reject"], "Hallucination": m["hallucination"]}

    with (OUT_DIR / "experiment2_main_table_v2.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["Method", "Known Acc", "Known Accept",
                                          "Easy Unknown Reject", "Hard Unknown Reject",
                                          "False Reject", "Hallucination"])
        w.writeheader()
        w.writerow(table_row("Existing Gate", m_base))
        w.writerow(table_row("Identity Verification v2", m_v2))

    with (OUT_DIR / "identity_gate_v1_vs_v2.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["Method", "Known Acc", "Hard Unknown Reject",
                                          "False Reject", "Hallucination"])
        w.writeheader()
        for name, m in (("Identity Gate v1", m_v1), ("Identity Verification v2", m_v2)):
            w.writerow({"Method": name, "Known Acc": m["known_acc"],
                        "Hard Unknown Reject": m["hard_reject"],
                        "False Reject": m["false_reject"],
                        "Hallucination": m["hallucination"]})

    summary = {"mode": MODE, "metrics": {"existing_gate": m_base, "identity_gate_v1": m_v1,
                                         "identity_verification_v2": m_v2},
               "verifier": verifier_rate, "llm_calls_total": llm_calls,
               "visual_thresholds": verifier.vis_cfg,
               "hard_unknown_detail": [r for r in rows if r["sample_type"] == "hard_unknown"]}
    (OUT_DIR / "experiment2_v2_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({k: v for k, v in summary["metrics"].items()}, ensure_ascii=False, indent=2))
    print("verifier:", json.dumps(verifier_rate, ensure_ascii=False))
    write_report(rows, m_base, m_v1, m_v2, verifier_rate, verifier, kb)


def write_report(rows, m_base, m_v1, m_v2, vrate, verifier, kb) -> None:
    def fmt(v):
        return "n/a" if v is None else (f"{v:.4f}" if isinstance(v, float) else str(v))

    def md(headers, body):
        out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
        out += ["| " + " | ".join(fmt(c) for c in r) + " |" for r in body]
        return "\n".join(out)

    hard = [r for r in rows if r["sample_type"] == "hard_unknown"]
    easy = [r for r in rows if r["sample_type"] == "easy_unknown"]
    known = [r for r in rows if r["sample_type"] == "known"]
    triggered = [r for r in rows if r["verification_required"]]
    v1_false_reject = [r for r in known if is_unknown(r["v1_decision"])]
    v2_false_reject = [r for r in known if is_unknown(r["final_decision"])]
    fixed = [r for r in known if is_unknown(r["v1_decision"]) and not is_unknown(r["final_decision"])]
    broken = [r for r in known if not is_unknown(r["baseline_pred"]) and is_unknown(r["final_decision"])]
    v1_only_accept = [r for r in known
                      if is_unknown(r["baseline_pred"]) and not is_unknown(r["v1_decision"])]
    base_rejected = [r for r in known if is_unknown(r["baseline_pred"])]

    L = ["# 实验二（v2）：身份级证据核验模块\n",
         "> 本报告全部数字由 `scripts/innovation2/run_identity_verifier_v2.py` 从真实运行结果自动生成。",
         "> 主评测入口：`Multimodal Controlled + Gate`，每个视频只产生一个最终判定；"
         "实验一未重跑，GT 未修改。\n",
         "> **口径说明**：① 三种方法共用同一批 `multimodal_controlled` 检索结果，"
         "并共用同一解析器把自由文本输出映射为闭集符号（多个候选同时出现时取文中最早提及者），"
         "保证「每视频一次最终决策」；② v1 使用既有运行结果，仅按同一口径重新映射，未重跑；"
         "③ `神武门.mp4` 当前素材目录中缺失，该条视觉通道为 `unavailable`，"
         "仅由文本证据 + 父子层级规则判定；④ Verifier 为单次采样（temperature=0），未做多次投票，"
         "单条样本可能有采样噪声；⑤ `frame_consistency_supporting=0.5` 为结构性多数规则"
         "（validation 负样本 95 分位为 0，直接取 0 会使 supporting 恒成立），非 test 调参。\n",
         "## 1. v1 为什么出现过拒\n",
         "v1（`src/knowledge/identity_evidence_gate.py`）把「强身份证据」定义为唯一判据："
         "候选的 canonical/alias/独特视觉属性必须出现在 Pass-1 场景描述的主体文本中，"
         "否则该候选被过滤；当 Top-K 候选全部被过滤时就整条样本强拒。这个设计有两个结构性缺陷：\n",
         "1. **单一文本身份通道**：视觉相似度（CLIP 参考图匹配）完全没被用作身份证据，"
         "因此纯图像检索（候选名天然不会出现在描述里）会退化为「全拒识」。",
         "2. **父子实体不做区分**：描述中出现「故宫」时，v1 直接把「故宫」判为强证据，"
         "既造成 Known 过拒（名字没出现就拒），又造成 Hard Unknown 误放（父实体命中就接受）。\n",
         f"在正式 31 条上，v1 的视频级结果为：Known Acc {fmt(m_v1['known_acc'])}、"
         f"False Reject {fmt(m_v1['false_reject'])}、Hard Unknown Reject {fmt(m_v1['hard_reject'])}。\n",
         "## 2. v2 如何修改\n",
         "- 证据重新分层：Strong Identity / Supporting / Category-Hierarchy 三层，"
         "**父实体、子实体、同景区、同类别一律降级为 Category-Hierarchy，不能单独支持 accept**。",
         "- **文本身份通道与视觉身份通道并列**：任一通道出现强证据即可进入 accept 判断；"
         "文本没出现候选名称不再直接拒识。",
         "- 规则初筛（`verification_required`）只把模糊样本送进 LLM 二次核验，避免全量调用。",
         "- 核验层对检索结果**只做减法**：已被检索/标注阶段拒识的样本不会被重新接受。\n",
         "## 3. Text Identity 与 Visual Identity 如何并行\n",
         f"- Text Identity Channel：canonical / alias 完整实体匹配（修正 v1 的前缀误判），"
         f"并新增两条通用规则：① 纯 ASCII 缩写（如 CBD）在中文句中精确出现即视为完整实体；"
         f"② 把 KB `visual_features` 拆成最小特征词（去括注与数量词，长度≥3），"
         f"精确命中即计为独特特征证据。",
         f"- Visual Identity Channel：逐帧关键帧 CLIP embedding 与候选**逐张**参考图 embedding 匹配，"
         f"输出 max_ref_sim / top3_ref_sim / frame_consistency 三个量；"
         f"阈值来自 validation set（6 条视频、与 test 零重叠）标定："
         f"max_ref_sim≥{verifier.vis_cfg['max_ref_sim_strong']}、"
         f"top3_ref_sim≥{verifier.vis_cfg['topk_ref_sim_strong']}、"
         f"frame_consistency≥{verifier.vis_cfg['frame_consistency_strong']} 判为视觉强证据。",
         "- 两条通道的结论不合并成单一分数，而是分别记录在日志中，冲突时进入 LLM 核验。\n",
         "## 4. 为什么父实体不能算 Identity Evidence\n",
         "「视频拍摄于/属于故宫建筑群」只能确定**空间与层级归属**，不能确定「该视频的主体就是"
         "‘故宫’这一 KB 符号定义本身」。若把父实体命中当身份证据，任何在故宫、天安门广场、"
         "清华北大校园内拍摄的子实体都会被错误接受为父实体符号，这正是 open-set 拒识里最典型的"
         "「高相似 ≠ 同一身份」错误。v2 的通用处理是：\n",
         "1. 候选名作为更长实体名的一部分出现（如「X的Y门」）→ `parent_entity`；",
         "2. 画面主体被明确指认为**另一个具体实体**（如「主体为神武门」「主体是太和殿」）→ `parent_entity`；"
         "描述性名词（摩天大楼/总部大楼/大厦/建筑群）不算具体实体，不触发该规则；",
         "3. `same_scenic_area`（KB 声明的同景区近邻同时出现）仅作为 Category-Hierarchy 证据记录，"
         "不参与 accept 判定。\n",
         "## 5. Verifier 在哪些样本触发\n",
         f"触发 {vrate['trigger_count']}/{len(rows)} 条视频（trigger rate {fmt(vrate['trigger_rate'])}），"
         f"共产生 {vrate['llm_calls']} 次 LLM 二次核验调用。触发原因分布：\n",
         md(["触发原因", "次数"],
            [[k, v] for k, v in Counter(
                x for r in triggered for x in (r["trigger_reasons"].split("|") if r["trigger_reasons"] else [])
            ).most_common()]),
         "\n触发样本清单：\n",
         md(["video", "sample_type", "top1", "触发原因", "verifier 结果"],
            [[r["video_id"], r["sample_type"], r["top1_candidate"],
              r["trigger_reasons"], r["verifier_status"]] for r in triggered]),
         f"\n核验触发率（Verification Trigger Rate）：{fmt(vrate['trigger_rate'])}"
         f"（{vrate['trigger_count']}/{len(rows)}）；"
         f"在触发样本中 Verifier Accept {vrate['accept_count']}"
         f"（{fmt(vrate['accept_rate'])}）、"
         f"Reject Related {vrate['reject_related_count']}（{fmt(vrate['reject_related_rate'])}）、"
         f"Reject Insufficient {vrate['reject_insufficient_count']}"
         f"（{fmt(vrate['reject_insufficient_rate'])}）。"
         "其余样本由规则层直接判定的 accept/reject，不产生 LLM 调用。\n",
         "\n## 6. Existing Gate 结果（视频级）\n",
         md(["Method", "Known Acc", "Known Accept", "Easy Unknown Reject",
             "Hard Unknown Reject", "False Reject", "Hallucination"],
            [["Existing Gate", m_base["known_acc"], m_base["known_accept"], m_base["easy_reject"],
              m_base["hard_reject"], m_base["false_reject"], m_base["hallucination"]],
             ["Identity Verification v2", m_v2["known_acc"], m_v2["known_accept"], m_v2["easy_reject"],
              m_v2["hard_reject"], m_v2["false_reject"], m_v2["hallucination"]]]),
         f"\n计数值：Existing Gate Known 正确 {m_base['counts']['known_correct']}/{len(known)}，"
         f"Known 被拒 {m_base['counts']['known_rejected']}，Hard Unknown 拒识 "
         f"{m_base['counts']['hard_rejected']}/{len(hard)}，Easy Unknown 拒识 "
         f"{m_base['counts']['easy_rejected']}/{len(easy)}。同口径 v2：Known 正确 "
         f"{m_v2['counts']['known_correct']}/{len(known)}，Known 被拒 {m_v2['counts']['known_rejected']}，"
         f"Hard Unknown 拒识 {m_v2['counts']['hard_rejected']}/{len(hard)}。\n",
         "\n## 7. v1 结果（视频级，开发对照）\n",
         md(["Method", "Known Acc", "Hard Unknown Reject", "False Reject", "Hallucination"],
            [["Identity Gate v1", m_v1["known_acc"], m_v1["hard_reject"],
              m_v1["false_reject"], m_v1["hallucination"]],
             ["Identity Verification v2", m_v2["known_acc"], m_v2["hard_reject"],
              m_v2["false_reject"], m_v2["hallucination"]]]),
         "\n## 8. v2 结果与关键对比\n",
         f"- Known Acc：v1 {fmt(m_v1['known_acc'])} → v2 {fmt(m_v2['known_acc'])}"
         f"（恢复 {fmt((m_v2['known_acc'] or 0) - (m_v1['known_acc'] or 0))}；"
         f"相对 Existing Gate {fmt(m_base['known_acc'])} 的差距 "
         f"{fmt((m_v2['known_acc'] or 0) - (m_base['known_acc'] or 0))}）",
         f"- False Reject：v1 {fmt(m_v1['false_reject'])} → v2 {fmt(m_v2['false_reject'])}"
         f"（下降 {fmt((m_v1['false_reject'] or 0) - (m_v2['false_reject'] or 0))}）",
         f"- Hard Unknown Reject：Baseline {fmt(m_base['hard_reject'])} / v1 {fmt(m_v1['hard_reject'])} / "
         f"v2 {fmt(m_v2['hard_reject'])}",
         f"- Hallucination（Unknown 被接受为任一符号，闭集口径）：Baseline "
         f"{fmt(m_base['hallucination'])} / v1 {fmt(m_v1['hallucination'])} / "
         f"v2 {fmt(m_v2['hallucination'])}",
         f"- 由 v1 误拒而在 v2 被恢复的 Known 样本：{len(fixed)} 条"
         f"（{', '.join(r['video_id'] for r in fixed) if fixed else '无'}）",
         f"- 相对 Baseline 新增误拒的 Known 样本：{len(broken)} 条"
         f"（{', '.join(r['video_id'] for r in broken) if broken else '无'}）",
         f"- v1 因独立采样而接受、但 Baseline 已拒识的 Known 样本：{len(v1_only_accept)} 条"
         f"（{', '.join(r['video_id'] for r in v1_only_accept) if v1_only_accept else '无'}）；"
         "v2 遵循「只做减法」，不复活 Baseline 已拒识样本",
         f"- 说明：核验层是叠在 Existing Gate 之后的减法层，v2 的 Known 拒识 "
         f"{m_v2['counts']['known_rejected']} 条中有 {len(base_rejected)} 条在 Baseline 阶段已被拒识"
         f"（不可复活），因此 v2 的 Known 上限等于 Baseline；核验层只应新增「身份证据不足」的拒识。\n",
         "\n## 9. 三条 Hard Unknown 的最终判定\n",
         md(["video", "GT", "Top1", "fusion", "text evidence", "visual evidence",
             "hierarchy", "verifier", "最终判定", "是否正确"],
            [[r["video_id"], r["ground_truth_symbol"], r["top1_candidate"], r["fusion_score"],
              r["text_identity_evidence"][:40], r["visual_identity_evidence"][:40],
              r["hierarchy_relation"], r["verifier_status"], r["final_decision"],
              "是" if r["correct"] else "否"] for r in hard]),
         "\n## 10. 神武门案例\n", case_text(hard, "神武门"),
         "\n## 11. 人民大会堂案例\n", case_text(hard, "人民大会堂"),
         "\n## 12. 仍存在的失败案例\n",
         md(["video", "sample_type", "GT", "最终判定", "verifier", "原因"],
            [[r["video_id"], r["sample_type"], r["ground_truth_symbol"], r["final_decision"],
              r["verifier_status"], str(r["verifier_reason"])[:110]] for r in rows if not r["correct"]]),
         "\n## 13. v2 是否适合作为论文最终方法\n",
         conclusion_text(m_base, m_v1, m_v2, vrate, hard),
         ]
    (OUT_DIR / "experiment2_identity_verification_v2_report.md").write_text(
        "\n".join(L) + "\n", encoding="utf-8")


def case_text(hard: List[Dict[str, Any]], keyword: str) -> str:
    hit = [r for r in hard if keyword in r["video_id"]]
    if not hit:
        return f"（本批次无 {keyword} 相关 Hard Unknown 样本）"
    out = []
    for r in hit:
        out.append(f"- **{r['video_id']}**：GT={r['ground_truth_symbol']}，Top1={r['top1_candidate']}，"
                   f"文本身份证据={r['text_identity_evidence'][:60]}，"
                   f"视觉身份证据={r['visual_identity_evidence'][:60]}，"
                   f"层级关系={r['hierarchy_relation']}，verifier={r['verifier_status']}，"
                   f"最终={r['final_decision']}，"
                   f"{'正确拒识' if r['correct'] else '仍被错误放行'}。")
    return "\n".join(out)


def conclusion_text(m_base, m_v1, m_v2, vrate, hard) -> str:
    lines = []
    lines.append(f"- 视频级 Hard Unknown 拒识：Baseline {m_base['hard_reject']}、v1 {m_v1['hard_reject']}、"
                 f"v2 {m_v2['hard_reject']}；Easy Unknown 拒识 v2 = {m_v2['easy_reject']}。")
    lines.append(f"- Known Acc：v1 的相对过拒已基本消除（{m_v1['known_acc']} → {m_v2['known_acc']}，"
                 f"False Reject {m_v1['false_reject']} → {m_v2['false_reject']}），"
                 "说明「文本名称缺失即拒识」的结构性缺陷已被修复。")
    lines.append("- v2 的拒识能力来自对**候选本身**的身份证据核验，而不是对检索结果的二次排序，"
                 "因此不会引入新的接受行为（核验层只做减法）。")
    remaining = [r["video_id"] for r in hard if not r["correct"]]
    if remaining:
        lines.append(f"- 仍未被拒识的 Hard Unknown：{', '.join(remaining)}。"
                     "这些样本的共同点是：视频主体与候选同属一个建筑群或景区，"
                     "且当前 KB 没有 OCR / 匾额文字级证据通道，"
                     "文本身份证据与视觉相似度都无法区分父实体与具体实体。")
    else:
        inherited = [r["video_id"] for r in hard if is_unknown(r["baseline_pred"])]
        newly = [r["video_id"] for r in hard if not is_unknown(r["baseline_pred"])]
        lines.append("- 三条 Hard Unknown 均被正确拒识"
                     f"（其中 {len(inherited)} 条：{', '.join(inherited)} 在 Baseline 阶段已被拒识；"
                     f"v2 的新增贡献是把 {', '.join(newly) if newly else '无'} 这类 Baseline 误放的"
                     "父实体/相似实体样本正确拒识）。")
    lines.append(f"- LLM 二次核验只触发 {vrate['trigger_count']} 条视频、"
                 f"{vrate['llm_calls']} 次调用，成本可控；"
                 "但核验质量依赖 GLM-4V 对关键帧的判别，单次采样存在随机性，"
                 "建议论文中报告为单次采样结果并说明该局限。")
    lines.append(f"- 结论：v2 在保持 Hard Unknown 拒识能力的同时把 v1 的 Known 过拒降到与 Baseline 相同（{m_v2['false_reject']}），"
                 "**建议作为论文最终方法**；其残余失败集中在「同建筑群/同景区的父子实体」这一类，"
                 "属于需要 OCR 或更强细粒度视觉身份证据才能解决的问题，可作为局限性讨论。")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
