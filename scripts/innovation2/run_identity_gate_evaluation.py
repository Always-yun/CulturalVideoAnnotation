"""Offline, reproducible evaluation of Existing Gate vs Identity Evidence Gate.

No VLM, CLIP encoder, retriever, or video is invoked.  The script replays the
same 20 saved `gate_on_final` controlled-mode outputs and applies only the new
deterministic identity decision.  Thus the comparison isolates the effect of
the gate and does not overwrite historical experiment artefacts.
"""

from __future__ import annotations

import csv
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.experiments.ablation_metrics import (  # noqa: E402
    build_kb_vocab, compute_annotation_metrics, hit_gt_symbol, is_hallucination,
)
from src.knowledge import IdentityEvidenceGate, SymbolKnowledgeBase  # noqa: E402


SOURCE = ROOT / "experiments/innovation2/runs/cultural_ablation/gate_on_final/results.json"
GT_PATH = ROOT / "experiments/innovation2/data/eval/cultural_ablation_gt_v2.jsonl"
CACHE_PATH = ROOT / "experiments/innovation2/cache/scene_desc_cache_v2.json"
CONFIG_PATH = ROOT / "config/identity_evidence_gate.json"
OUT_DIR = ROOT / "experiments/innovation2/results/cultural_rag/identity_gate"


def extract_pred_names(core_symbol: str) -> List[str]:
    """Local copy of the existing C-layer name parser; avoids inference imports."""
    if not core_symbol:
        return []
    m = re.search(r"为(.+?)(?:。|（|$)", core_symbol.strip())
    segment = m.group(1) if m else core_symbol.split("（")[0]
    return [part.strip(" 。[]") for part in re.split(r"[、，,；;]", segment.strip("[] \t"))
            if part.strip(" 。[]")]


def load_gt() -> Dict[str, Dict[str, Any]]:
    with GT_PATH.open(encoding="utf-8") as f:
        return {row["video_id"]: row for row in (json.loads(line) for line in f) if row}


def aliases(symbol: Dict[str, Any]) -> List[str]:
    out = [str(symbol.get("canonical_name", "")).strip()]
    raw = symbol.get("aliases") or ""
    out += raw.split("|") if isinstance(raw, str) else [str(x) for x in raw]
    return [x for x in out if len(x.strip()) >= 2]


def prediction_candidate_ids(prediction: str, candidates: Iterable[Dict[str, Any]],
                             kb: SymbolKnowledgeBase) -> set[str]:
    """Map a saved controlled output to candidates using existing aliases.

    This mirrors the existing constraint's inclusive name matching only for
    replay.  Identity acceptance itself remains candidate-specific and does
    not use this mapping.
    """
    predicted_parts = extract_pred_names(prediction)
    result = set()
    for candidate in candidates:
        symbol = kb.get(candidate.get("symbol_id", "")) or candidate
        for name in aliases(symbol):
            if any(part == name or name in part or part in name for part in predicted_parts):
                result.add(symbol.get("symbol_id", ""))
    return result


def copy_record_with_prediction(record: Dict[str, Any], prediction: str, rejected: bool) -> Dict[str, Any]:
    out = dict(record)
    out["pred_symbol"] = prediction
    out["unknown_symbol"] = rejected
    return out


def row_metrics(records: List[Dict[str, Any]], hard_ids: set[str], kb: SymbolKnowledgeBase) -> Dict[str, Any]:
    vocab = build_kb_vocab(kb)
    base = compute_annotation_metrics(records, kb, vocab)
    known = [r for r in records if r.get("kb_coverage") == "hit"]
    unknown = [r for r in records if r.get("kb_coverage") == "gap"]
    hard = [r for r in records if r["video_id"] in hard_ids]
    false_rejects = [r for r in known if r.get("unknown_symbol")]
    forced = [r for r in hard if not r.get("unknown_symbol")]
    return {
        "Known Symbol Accuracy": base["hit_symbol_accuracy"],
        "Known Accept Rate": round((len(known) - len(false_rejects)) / len(known), 4),
        "Unknown Rejection Rate": base["gap_reject_rate"],
        "Hard Unknown Rejection Rate": round(sum(r.get("unknown_symbol") for r in hard) / len(hard), 4),
        "Hallucination Rate": base["hallucination_rate"],
        "Known False Rejection Rate": round(len(false_rejects) / len(known), 4),
        "Known count": len(known), "Unknown count": len(unknown), "Hard Unknown count": len(hard),
        "Identity-level forced-match rate": round(len(forced) / len(hard), 4),
    }


def validation_rows(gt: Dict[str, Dict[str, Any]], kb: SymbolKnowledgeBase,
                    gate: IdentityEvidenceGate) -> List[Dict[str, Any]]:
    cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    rows = []
    for item in gt.values():
        if item.get("split") != "val":
            continue
        scene = cache.get(item["video_path"], "")
        if item["kb_coverage"] == "hit":
            evidence = [gate.assess_candidate(kb.get(sid), scene).to_dict()
                        for sid in item["gt_symbol_ids"]]
            passed = any(item_["identity_gate_pass"] for item_ in evidence)
            scope = "GT candidate evidence coverage (not a model prediction)"
        else:
            evidence = [item_.to_dict() for item_ in gate.assess_candidates(kb.symbols, scene)]
            passed = any(item_["identity_gate_pass"] for item_ in evidence)
            scope = "All-KB candidate scan (not a model prediction)"
        rows.append({
            "video_id": item["video_id"], "kb_coverage": item["kb_coverage"],
            "identity_gate_pass": passed, "scope": scope,
            "evidence": json.dumps(evidence, ensure_ascii=False),
        })
    return rows


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else [])
        writer.writeheader()
        writer.writerows(rows)


def pct(value: float) -> str:
    return f"{value * 100:.2f}%" if value is not None else "N/A"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CONFIG_PATH, OUT_DIR / "identity_gate_config.json")
    kb, gate, gt = SymbolKnowledgeBase(), IdentityEvidenceGate(), load_gt()
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    baseline = [r for r in source["records"] if r["mode"] == "multimodal_controlled"]
    assert len(baseline) == 20, f"Expected 20 controlled test records, got {len(baseline)}"
    hard_ids = {r["video_id"] for r in csv.DictReader(
        (ROOT / "experiments/innovation2/results/cultural_rag/unknown_analysis/cultural_unknown_analysis.csv").open(encoding="utf-8-sig"))
        if r["split"] == "test" and r["unknown_type"] == "hard_unknown"}

    proposed, result_rows = [], []
    for record in baseline:
        evidence = gate.assess_candidates(record["topk_candidates"], record["scene_description"])
        evidence_by_id = {item.symbol_id: item for item in evidence}
        passed_ids = gate.passed_symbol_ids(evidence)
        existing_rejected = bool(record.get("unknown_symbol"))
        predicted_ids = prediction_candidate_ids(record.get("pred_symbol", ""), record["topk_candidates"], kb)

        if existing_rejected:
            proposed_rejected, outcome = True, "preserve_existing_rejection"
            reason = "Existing Confidence Gate / controlled output already returned unknown_symbol."
        elif not passed_ids:
            proposed_rejected, outcome = True, "identity_rejection_no_passing_candidate"
            reason = "Existing Gate passed, but no candidate has strong identity evidence."
        elif predicted_ids & passed_ids:
            proposed_rejected, outcome = False, "accept_identity_verified_prediction"
            reason = "The saved final candidate is among candidates with strong identity evidence."
        else:
            proposed_rejected, outcome = True, "identity_rejection_predicted_candidate_unverified"
            reason = "The saved final candidate lacks strong identity evidence."

        prediction = "unknown_symbol" if proposed_rejected else record["pred_symbol"]
        replay = copy_record_with_prediction(record, prediction, proposed_rejected)
        proposed.append(replay)
        top = record["topk_candidates"][0] if record["topk_candidates"] else {}
        top_ev = evidence_by_id.get(top.get("symbol_id", ""))
        result_rows.append({
            "video_id": record["video_id"], "split": record["split"],
            "kb_coverage": record["kb_coverage"],
            "unknown_type": "hard_unknown" if record["video_id"] in hard_ids else "known",
            "top1_candidate": top.get("canonical_name", ""),
            "fusion_score": top.get("fusion_score", ""),
            "existing_gate_result": record.get("gate_level", ""),
            "existing_rejected": existing_rejected,
            "identity_name_match": top_ev.identity_name_match if top_ev else "",
            "identity_alias_match": top_ev.identity_alias_match if top_ev else "",
            "identity_ocr_match": top_ev.identity_ocr_match if top_ev else "unavailable",
            "identity_unique_attribute_match": top_ev.identity_unique_attribute_match if top_ev else "",
            "identity_reference_image_match": top_ev.identity_reference_image_match if top_ev else "unavailable",
            "identity_evidence_count": top_ev.identity_evidence_count if top_ev else 0,
            "identity_evidence_level": top_ev.identity_evidence_level if top_ev else "none",
            "identity_gate_pass": bool(passed_ids),
            "identity_gate_reason": reason,
            "passed_candidate_ids": ";".join(sorted(passed_ids)),
            "category_evidence": top_ev.category_evidence if top_ev else "",
            "candidate_identity_evidence": json.dumps([item.to_dict() for item in evidence], ensure_ascii=False),
            "baseline_prediction": record.get("pred_symbol", ""),
            "proposed_prediction": prediction,
            "proposed_rejected": proposed_rejected,
            "outcome": outcome,
        })

    b_metrics, p_metrics = row_metrics(baseline, hard_ids, kb), row_metrics(proposed, hard_ids, kb)
    metric_rows = [
        {"version": "Baseline: Existing Confidence Gate", **b_metrics},
        {"version": "Proposed: Existing Gate + Identity Evidence Gate", **p_metrics},
    ]
    write_csv(OUT_DIR / "identity_gate_results.csv", result_rows)
    write_csv(OUT_DIR / "identity_gate_comparison.csv", metric_rows)

    errors = []
    for before, after, detail in zip(baseline, proposed, result_rows):
        if after["kb_coverage"] != "hit" or not after["unknown_symbol"]:
            continue
        if before["unknown_symbol"]:
            cause = "Existing Gate already rejected; Identity Gate does not recover rejected samples."
        else:
            cause = "New Identity Gate rejection: " + detail["identity_gate_reason"]
        errors.append({
            "video_id": after["video_id"], "baseline_rejected": before["unknown_symbol"],
            "proposed_rejected": True, "top1_candidate": detail["top1_candidate"],
            "passed_candidate_ids": detail["passed_candidate_ids"],
            "identity_evidence_level": detail["identity_evidence_level"], "cause": cause,
            "scene_description": after["scene_description"],
        })
    write_csv(OUT_DIR / "identity_gate_error_analysis.csv", errors)
    val = validation_rows(gt, kb, gate)
    write_csv(OUT_DIR / "identity_gate_validation.csv", val)

    hard_rows = [r for r in result_rows if r["unknown_type"] == "hard_unknown"]
    val_hit = [r for r in val if r["kb_coverage"] == "hit"]
    val_gap = [r for r in val if r["kb_coverage"] == "gap"]
    lines = [
        "# Identity Evidence Gate evaluation report", "",
        "## Protocol", "",
        "The proposed gate was implemented in `src/knowledge/identity_evidence_gate.py` and integrated after `RejectionGate` in `src/pipeline/cultural_rag.py`. This evaluation is an offline replay of the 20 saved `gate_on_final` `multimodal_controlled` outputs. It does not call a VLM, CLIP encoder, retriever, or video input; the only changed decision is the deterministic candidate identity gate. The original `gate_on_final` artefacts remain unchanged.", "",
        "The v1 rule was selected without test tuning: accept a candidate only at `strong` level—complete canonical/alias mention in the scene description without a conflicting explicit focus entity, or an exact existing KB unique-attribute match. OCR and reference-image evidence are `unavailable`; image/fusion score is not used as identity evidence.", "",
        "## Validation check", "",
        f"GT candidate identity evidence passed for {sum(r['identity_gate_pass'] for r in val_hit)}/{len(val_hit)} Known validation samples. No KB candidate passed for {sum(not r['identity_gate_pass'] for r in val_gap)}/{len(val_gap)} validation unknown samples. This is a rule-coverage check, not a model-prediction metric.", "",
        "## Test metrics", "",
        "| Version | Known Symbol Accuracy | Known Accept Rate | Unknown Rejection Rate | Hard Unknown Rejection Rate | Hallucination Rate | Known False Rejection Rate |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in metric_rows:
        lines.append("| " + row["version"] + " | " + " | ".join(pct(row[key]) for key in [
            "Known Symbol Accuracy", "Known Accept Rate", "Unknown Rejection Rate",
            "Hard Unknown Rejection Rate", "Hallucination Rate", "Known False Rejection Rate"]) + " |")
    lines += ["", "## Hard Unknown cases", "",
              "| Video | Top-1 candidate | Fusion | Existing Gate | Identity level (Top-1) | Proposed result | Reason |",
              "|---|---|---:|---|---|---|---|"]
    for row in hard_rows:
        all_evidence = json.loads(row["candidate_identity_evidence"])
        top_evidence = next((item for item in all_evidence if item["canonical_name"] == row["top1_candidate"]), {})
        lines.append(f"| {row['video_id']} | {row['top1_candidate']} | {row['fusion_score']} | "
                     f"{row['existing_gate_result']} / rejected={row['existing_rejected']} | "
                     f"{row['identity_evidence_level']} | rejected={row['proposed_rejected']} | {row['identity_gate_reason']} |")
        lines.append(
            f"  - Category evidence: `{row['category_evidence']}`. Identity evidence: "
            f"canonical={top_evidence.get('identity_name_match')}, "
            f"alias={top_evidence.get('identity_alias_match')}, "
            f"weak_mentions={top_evidence.get('weak_name_mentions')}, "
            f"unique_attribute={top_evidence.get('identity_unique_attribute_match')}, "
            "OCR=unavailable, reference image=unavailable."
        )
    lines += ["", "## Known false rejections", "",
              f"Proposed gate rejects {len(errors)}/17 Known samples. {sum(not r['baseline_rejected'] for r in errors)} are newly rejected by the identity layer; the remainder were already rejected by the existing system.", ""]
    for row in errors:
        lines.append(f"- **{row['video_id']}**: {row['cause']}")
    lines += ["", "## Interpretation", "",
              "The replay directly tests the separation between candidate relevance and candidate identity. A high fusion score can be retained as category/retrieval evidence while the candidate is rejected when its name is only a parent-context or a prefix of another explicit entity. The remaining false rejection cases identify missing aliases, missing scene name evidence, or KB granularity limits; they must not be silently converted into KB additions during this rejection experiment.", ""]
    (OUT_DIR / "identity_gate_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Results written to {OUT_DIR}")


if __name__ == "__main__":
    main()
