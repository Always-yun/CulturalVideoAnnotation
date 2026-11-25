"""
创新点2 消融实验指标计算

检索实验指标（基于 Top-K 候选与 GT 符号）：
- Recall@1 / Recall@5 / MRR
- GT 为 unknown_symbol 的样本不参与检索指标（无正样本可检索）

标注实验指标（基于最终 C 层输出与 GT）：
- 文化符号准确率：预测符号命中 GT 规范名/别名；GT 为 unknown 时预测拒识即正确
- 文化维度准确率：预测维度码与 GT 维度码有交集
- 文化幻觉率：预测符号非 unknown 且不含任何知识库词表项（编造符号）
- unknown 拒识率：unknown_symbol 输出占比（描述性）
- 人工修改率：预留 human_edit 人工审核字段（1=需修改 / 0=无需修改），
  人工填写后自动统计；为空时返回 None
"""

import json
import re
from typing import Any, Dict, List, Optional

from ..knowledge.symbol_kb import SymbolKnowledgeBase
from ..metrics.emcast_schema import CULTURAL_DIMENSION_CODES


def load_gt(gt_path: str) -> List[Dict[str, Any]]:
    items = []
    with open(gt_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", str(s or "")).lower()


def build_kb_vocab(kb: SymbolKnowledgeBase) -> List[str]:
    """知识库全词表（规范名+别名+关键词），用于幻觉判定"""
    vocab = set()
    for s in kb.symbols:
        for t in kb.expand_terms(s):
            if len(t.strip()) >= 2:
                vocab.add(_norm(t))
    return sorted(vocab)


def hit_gt_symbol(pred_symbol: str, gt_symbols: List[str],
                  kb: SymbolKnowledgeBase) -> bool:
    """预测符号文本是否命中 GT 符号（规范名或任一别名出现在预测文本中）"""
    pred = _norm(pred_symbol)
    if not pred:
        return False
    if "unknown_symbol" in pred:
        # GT unknown 时单独处理
        return False
    for g in gt_symbols:
        if "unknown_symbol" in g:
            continue
        sym = kb.get_by_name(g)
        terms = kb.expand_terms(sym) if sym else [g]
        for t in terms:
            if len(t.strip()) >= 2 and _norm(t) in pred:
                return True
    return False


def is_hallucination(pred_symbol: str, kb_vocab: List[str]) -> bool:
    """预测符号非 unknown 且不含任何知识库词表项 → 文化幻觉"""
    pred = _norm(pred_symbol)
    if not pred or "unknown_symbol" in pred:
        return False
    return not any(v in pred for v in kb_vocab)


def dimension_hit(pred_dimension: str, gt_dimension_code: str) -> bool:
    """预测维度名（转码后）与 GT 维度码是否存在交集"""
    if not gt_dimension_code or not pred_dimension:
        return False
    pred_code = CULTURAL_DIMENSION_CODES.get(pred_dimension, "")
    gt_codes = set(c.strip() for c in gt_dimension_code.split(";") if c.strip())
    return bool(pred_code and pred_code in gt_codes)


def compute_retrieval_metrics(records: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    """Recall@1 / Recall@5 / MRR（仅统计 GT 含真实符号的样本）"""
    n, hit1, hit5, rr_sum = 0, 0, 0, 0.0
    for r in records:
        gt_ids = [i for i in r.get("gt_symbol_ids", []) if i]
        if not gt_ids:
            continue  # unknown 样本不参与检索指标
        cands = r.get("topk_candidates", [])
        cand_ids = [c["symbol_id"] for c in cands]
        n += 1
        if cand_ids[:1] and cand_ids[0] in gt_ids:
            hit1 += 1
        if any(cid in gt_ids for cid in cand_ids[:5]):
            hit5 += 1
        rank = next((i + 1 for i, cid in enumerate(cand_ids) if cid in gt_ids), None)
        if rank:
            rr_sum += 1.0 / rank
    return {
        "recall@1": round(hit1 / n, 4) if n else None,
        "recall@5": round(hit5 / n, 4) if n else None,
        "mrr": round(rr_sum / n, 4) if n else None,
        "n_evaluable": n,
    }


def compute_annotation_metrics(records: List[Dict[str, Any]],
                               kb: SymbolKnowledgeBase,
                               kb_vocab: List[str]) -> Dict[str, Any]:
    """符号准确率 / 维度准确率 / 幻觉率 / unknown拒识率 / 人工修改率
    分层指标（按 KB 覆盖）：
    - gap_reject_rate：GT=unknown_symbol（知识库覆盖缺口）样本的拒识率
    - hit_symbol_accuracy：GT 含真实符号样本的符号准确率
    """
    n = len(records)
    sym_hit, dim_eval, dim_hit = 0, 0, 0
    halluc_cnt, unknown_cnt, edit_cnt, edit_flag = 0, 0, 0, 0
    gap_n, gap_reject, hit_n, hit_correct = 0, 0, 0, 0
    for r in records:
        pred_symbol = r.get("pred_symbol", "") or ""
        pred_is_unknown = r.get("unknown_symbol", False) or "unknown_symbol" in _norm(pred_symbol)
        gt_symbols = r.get("gt_symbols", [])

        # 符号准确率：GT 为 unknown 时预测拒识即正确
        gt_is_unknown = any("unknown_symbol" in g for g in gt_symbols)
        if gt_is_unknown:
            gap_n += 1
            if pred_is_unknown:
                sym_hit += 1
                gap_reject += 1
        else:
            hit_n += 1
            if pred_symbol and not pred_is_unknown and hit_gt_symbol(pred_symbol, gt_symbols, kb):
                sym_hit += 1
                hit_correct += 1

        # 维度准确率（GT 无维度则跳过）
        if r.get("gt_dimension_code"):
            dim_eval += 1
            if dimension_hit(r.get("pred_dimension", ""), r["gt_dimension_code"]):
                dim_hit += 1

        # 幻觉率
        if pred_symbol and not pred_is_unknown and is_hallucination(pred_symbol, kb_vocab):
            halluc_cnt += 1

        # unknown 拒识率
        if pred_is_unknown:
            unknown_cnt += 1

        # 人工修改率（预留字段：人工审核后填 1/0）
        he = r.get("human_edit", None)
        if he is not None and str(he) != "":
            edit_cnt += 1
            edit_flag += int(he)

    return {
        "symbol_accuracy": round(sym_hit / n, 4) if n else None,
        "dimension_accuracy": round(dim_hit / dim_eval, 4) if dim_eval else None,
        "hallucination_rate": round(halluc_cnt / n, 4) if n else None,
        "unknown_reject_rate": round(unknown_cnt / n, 4) if n else None,
        "gap_reject_rate": round(gap_reject / gap_n, 4) if gap_n else None,
        "hit_symbol_accuracy": round(hit_correct / hit_n, 4) if hit_n else None,
        "n_gap_samples": gap_n,
        "human_edit_rate": round(edit_flag / edit_cnt, 4) if edit_cnt else None,
        "n_videos": n,
        "n_dimension_evaluable": dim_eval,
    }


def compute_mode_summary(records: List[Dict[str, Any]],
                         kb: SymbolKnowledgeBase,
                         kb_vocab: List[str]) -> Dict[str, Any]:
    """单模式汇总：检索指标 + 标注指标 + 耗时"""
    summary = {"mode": records[0]["mode"] if records else ""}
    summary.update(compute_retrieval_metrics(records))
    summary.update(compute_annotation_metrics(records, kb, kb_vocab))
    secs = [r.get("seconds", 0) for r in records]
    summary["avg_seconds"] = round(sum(secs) / len(secs), 1) if secs else None
    return summary
