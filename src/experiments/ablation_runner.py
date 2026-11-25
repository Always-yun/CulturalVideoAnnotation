"""
创新点2 消融实验运行器（5 种实验模式端到端）

模式定义：
  1. free                  — Free Prompt：无检索，仅 EMCAST 五维闭集
  2. text                  — Keyword/Text Retrieval + Prompt（fusion = text）
  3. image                 — Image Retrieval + Prompt（fusion = image，alpha=0）
  4. multimodal            — Text + Image Multimodal Retrieval + Prompt（alpha 融合）
  5. multimodal_controlled — Multimodal Retrieval + Controlled Output（候选闭集约束）

统一记录（每视频×每模式）：
  Top-K候选（含 text_score / image_score / fusion_score）、最终文化符号、
  最终文化维度、unknown_symbol、模型输出全文、Prompt、计时

输出（experiments/innovation2/runs/cultural_ablation/<时间戳>/）：
  results.json   — 全量记录（含 Prompt 与模型输出，可直接喂论文表格脚本）
  per_video.csv  — 逐视频逐模式明细
  summary.csv    — 模式×指标汇总（Recall@1/5、MRR、符号/维度准确率、
                   幻觉率、unknown拒识率、人工修改率预留）
"""

import csv
import json
import os
import time
from typing import Any, Dict, List, Optional

from ..pipeline.cultural_rag import CulturalRAGPipeline, SCENE_DESCRIBE_PROMPT
from ..knowledge.symbol_kb import SymbolKnowledgeBase
from ..knowledge.retriever import KeywordCulturalRetriever
from ..knowledge.multimodal_retriever import MultimodalCulturalRetriever
from ..knowledge.rejection_gate import RejectionGate
from ..knowledge.identity_evidence_gate import IdentityEvidenceGate
from .ablation_metrics import (
    load_gt,
    build_kb_vocab,
    compute_mode_summary,
    is_hallucination,
)

ALL_MODES = ["free", "text", "image", "multimodal", "multimodal_controlled"]


class CulturalAblationExperiment:
    """5 模式消融实验：同一视频按不同检索/受控策略标注并统一评测"""

    def __init__(self,
                 gt_path: str,
                 top_k: int = 5,
                 fusion_alpha: float = 0.5,
                 num_frames: int = 4,
                 output_root: Optional[str] = None,
                 use_rejection_gate: bool = False,
                 thresholds_path: Optional[str] = None,
                 scene_cache_path: Optional[str] = None,
                 use_identity_gate: bool = False):
        """
        Args:
            gt_path: GT 评测集（experiments/innovation2/data/eval/cultural_ablation_gt.jsonl）
            top_k: 检索候选数
            fusion_alpha: 融合权重（text 占比；image 模式自动置 0）
            num_frames: CLIP 视频关键帧采样数
            output_root: 实验输出根目录，默认 experiments/innovation2/runs/cultural_ablation
            use_rejection_gate: 是否启用拒识门控（默认关闭保持旧行为）
            thresholds_path: 拒识阈值配置（验证集搜索产出，不硬编码）
            scene_cache_path: Pass-1 场景描述缓存 JSON（同视频跨模式/跨实验复用）
            use_identity_gate: 是否在拒识门控之上叠加身份证据门控（实验二 Proposed）
        """
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.gt_items = load_gt(gt_path)
        self.top_k = top_k
        self.fusion_alpha = fusion_alpha
        self.num_frames = num_frames
        self.project_root = project_root
        self.output_root = output_root or os.path.join(
            project_root, 'experiments/innovation2/runs/cultural_ablation')

        self.kb = SymbolKnowledgeBase()
        self.kb_vocab = build_kb_vocab(self.kb)
        self.rejection_gate = RejectionGate(thresholds_path) if use_rejection_gate else None
        self.identity_gate = IdentityEvidenceGate(kb=self.kb) if use_identity_gate else None
        self.pipeline = CulturalRAGPipeline(kb=self.kb, top_k=top_k,
                                            rejection_gate=self.rejection_gate,
                                            identity_gate=self.identity_gate)
        self.keyword_retriever = KeywordCulturalRetriever(self.kb)
        self._multimodal_retriever: Optional[MultimodalCulturalRetriever] = None
        # Pass-1 场景描述缓存：video_path → 描述文本（同视频跨模式复用，省 VLM 调用）
        self.scene_cache_path = scene_cache_path
        self._scene_cache: Dict[str, str] = {}
        if scene_cache_path and os.path.exists(scene_cache_path):
            with open(scene_cache_path, "r", encoding="utf-8") as f:
                self._scene_cache = json.load(f)
            print(f"[场景缓存] 已加载 {len(self._scene_cache)} 条 Pass-1 场景描述")

    # ------------------------------------------------------------------ #
    # 检索器调度（可插拔体现：同一管线按模式切换检索器与受控开关）
    # ------------------------------------------------------------------ #
    def _get_multimodal(self) -> MultimodalCulturalRetriever:
        if self._multimodal_retriever is None:
            self._multimodal_retriever = MultimodalCulturalRetriever(
                kb=self.kb, fusion_alpha=self.fusion_alpha,
                num_frames=self.num_frames)
        return self._multimodal_retriever

    def _mode_config(self, mode: str):
        if mode == "free":
            return dict(use_kb=False, controlled=False, retriever=None)
        if mode == "text":
            return dict(use_kb=True, controlled=False, retriever=self.keyword_retriever)
        if mode == "image":
            mm = self._get_multimodal()
            mm.fusion_alpha = 0.0  # 纯图像分数
            return dict(use_kb=True, controlled=False, retriever=mm)
        if mode == "multimodal":
            mm = self._get_multimodal()
            mm.fusion_alpha = self.fusion_alpha
            return dict(use_kb=True, controlled=False, retriever=mm)
        if mode == "multimodal_controlled":
            mm = self._get_multimodal()
            mm.fusion_alpha = self.fusion_alpha
            return dict(use_kb=True, controlled=True, retriever=mm)
        raise ValueError(f"未知实验模式: {mode}")

    # ------------------------------------------------------------------ #
    # 主流程
    # ------------------------------------------------------------------ #
    def run(self, modes: Optional[List[str]] = None,
            video_ids: Optional[List[str]] = None,
            out_dir: Optional[str] = None,
            split: Optional[str] = None) -> Dict[str, Any]:
        """
        Args:
            modes: 实验模式列表，默认全部 5 种
            video_ids: 仅跑指定 video_id（默认 GT 全部）
            out_dir: 指定实验输出目录
            split: 仅跑指定划分（val/test，GT v2 支持；None=全部）
        """
        modes = modes or ALL_MODES
        gt_items = self.gt_items
        if video_ids:
            gt_items = [g for g in gt_items if g["video_id"] in video_ids]
        if split:
            gt_items = [g for g in gt_items if g.get("split", "test") == split]

        run_id = time.strftime("%Y%m%d_%H%M%S")
        exp_dir = out_dir or os.path.join(self.output_root, run_id)
        os.makedirs(exp_dir, exist_ok=True)
        print(f"[实验配置] gate={'on' if self.rejection_gate else 'off'} "
              f"split={split or 'all'} modes={modes}")

        records: List[Dict[str, Any]] = []
        for gi, gt in enumerate(gt_items):
            video_path = os.path.join(self.project_root, gt["video_path"]) \
                if not os.path.isabs(gt["video_path"]) else gt["video_path"]
            if not os.path.exists(video_path):
                print(f"[跳过] 视频不存在: {video_path}")
                continue
            video_dir = os.path.join(exp_dir, gt["video_id"])
            os.makedirs(video_dir, exist_ok=True)
            print(f"\n===== [{gi + 1}/{len(gt_items)}] {gt['video_id']} "
                  f"(GT={gt['gt_symbols']}, {gt.get('kb_coverage', '?')}) =====")

            # Pass-1 场景描述：同视频跨模式复用（每视频仅 1 次 VLM 调用）
            kb_modes = [m for m in modes if m != "free"]
            scene_desc = self._scene_cache.get(gt["video_path"])
            if kb_modes and scene_desc is None:
                t = time.time()
                scene_desc = self.pipeline.engine.annotate_video(
                    video_path, prompt=SCENE_DESCRIBE_PROMPT)
                self._scene_cache[gt["video_path"]] = scene_desc
                self._save_scene_cache()
                print(f"    [Pass-1 场景描述] {round(time.time() - t, 1)}s "
                      f"(缓存共{len(self._scene_cache)}条)")
            elif kb_modes:
                print("    [Pass-1 场景描述] 使用缓存")

            for mode in modes:
                cfg = self._mode_config(mode)
                self.pipeline.retriever = cfg["retriever"]  # 可插拔切换
                print(f"--- 模式 [{mode}] ---")
                try:
                    trace = self.pipeline.run(
                        video_path, use_kb=cfg["use_kb"],
                        controlled=cfg["controlled"],
                        out_dir=video_dir, tag=mode,
                        scene_description=scene_desc if cfg["use_kb"] else None,
                        gate_mode=mode)
                except Exception as e:
                    print(f"[错误] {gt['video_id']}/{mode}: {e}")
                    records.append(self._empty_record(gt, mode))
                    continue
                trace["mode"] = mode  # 覆盖为实验模式名
                record = self._build_record(gt, mode, trace)
                records.append(record)
                gate_s = record["gate_level"] or "-"
                print(f"    Top1={record['top1_symbol']}  pred={record['pred_symbol']} "
                      f"({record['pred_dimension']})  unknown={record['unknown_symbol']}  "
                      f"gate={gate_s}  {trace['total_seconds']}s")

        # 保存与统计
        results_path = os.path.join(exp_dir, "results.json")
        with open(results_path, "w", encoding="utf-8") as f:
            json.dump({
                "config": {"top_k": self.top_k, "fusion_alpha": self.fusion_alpha,
                           "num_frames": self.num_frames, "modes": modes,
                           "split": split,
                           "use_rejection_gate": self.rejection_gate is not None,
                           "use_identity_gate": self.identity_gate is not None,
                           "thresholds_path": self.rejection_gate.thresholds_path
                           if self.rejection_gate else None},
                "records": records,
            }, f, ensure_ascii=False, indent=2)
        per_video_path = os.path.join(exp_dir, "per_video.csv")
        self._save_per_video_csv(records, per_video_path)

        summaries = []
        for mode in modes:
            mode_records = [r for r in records if r["mode"] == mode]
            if mode_records:
                summaries.append(compute_mode_summary(mode_records, self.kb, self.kb_vocab))
        summary_path = os.path.join(exp_dir, "summary.csv")
        self._save_summary_csv(summaries, summary_path)

        print(f"\n实验完成：{len(records)} 条记录 → {exp_dir}")
        return {"exp_dir": exp_dir, "records": records, "summaries": summaries}

    # ------------------------------------------------------------------ #
    # 场景描述缓存落盘
    # ------------------------------------------------------------------ #
    def _save_scene_cache(self) -> None:
        if not self.scene_cache_path:
            return
        os.makedirs(os.path.dirname(self.scene_cache_path), exist_ok=True)
        with open(self.scene_cache_path, "w", encoding="utf-8") as f:
            json.dump(self._scene_cache, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------ #
    # 记录构建
    # ------------------------------------------------------------------ #
    def _build_record(self, gt: Dict[str, Any], mode: str,
                      trace: Dict[str, Any]) -> Dict[str, Any]:
        cands = trace.get("topk_candidates") or []
        c_layer = trace.get("final_c_layer") or {}
        pred_symbol = c_layer.get("core_symbol", "")
        pred_is_unknown = c_layer.get("unknown_symbol", False) or \
            "unknown_symbol" in (pred_symbol or "")
        gate = trace.get("rejection_gate") or {}
        ident = trace.get("identity_gate") or {}
        ident_ev = trace.get("identity_evidence") or []
        eff = trace.get("effective_gate") or gate
        return {
            "video_id": gt["video_id"],
            "video_path": gt["video_path"],
            "split": gt.get("split", ""),
            "kb_coverage": gt.get("kb_coverage", ""),
            "sample_type": gt.get("sample_type", ""),
            "mode": mode,
            "gt_symbol_ids": gt.get("gt_symbol_ids", []),
            "gt_symbols": gt.get("gt_symbols", []),
            "gt_dimension_code": gt.get("gt_dimension_code", ""),
            "retriever": trace.get("retriever"),
            "top1_symbol": cands[0]["canonical_name"] if cands else "",
            "top5_symbols": [c["canonical_name"] for c in cands[:5]],
            "topk_candidates": cands,
            "text_scores": {c["symbol_id"]: c.get("text_score", 0) for c in cands},
            "image_scores": {c["symbol_id"]: c.get("image_score", 0) for c in cands},
            "fusion_scores": {c["symbol_id"]: c.get("fusion_score", 0) for c in cands},
            "gate_level": gate.get("level", ""),
            "gate_reason": gate.get("reason", ""),
            "gate_signals": gate.get("signals", {}),
            "effective_gate_level": (eff or {}).get("level", ""),
            "effective_gate_reason": (eff or {}).get("reason", ""),
            "identity_gate_pass": ident.get("identity_gate_pass"),
            "identity_gate_reason": ident.get("reason", ""),
            "identity_passed_symbol_ids": ident.get("passed_symbol_ids", []),
            "identity_evidence": [
                {"symbol_id": e.get("symbol_id"),
                 "canonical_name": e.get("canonical_name"),
                 "identity_evidence_level": e.get("identity_evidence_level"),
                 "identity_gate_pass": e.get("identity_gate_pass"),
                 "canonical_hit": e.get("identity_name_match"),
                 "alias_hit": e.get("identity_alias_match"),
                 "ocr_hit": e.get("identity_ocr_match"),
                 "unique_attribute_hit": e.get("identity_unique_attribute_match"),
                 "reference_image_match": e.get("identity_reference_image_match"),
                 "unique_attribute_matches": e.get("unique_attribute_matches", []),
                 "weak_name_mentions": e.get("weak_name_mentions", []),
                 "category_evidence": e.get("category_evidence", "")}
                for e in ident_ev],
            "pred_symbol": pred_symbol,
            "pred_dimension": c_layer.get("dimension", ""),
            "unknown_symbol": pred_is_unknown,
            "hallucination": (not pred_is_unknown and bool(pred_symbol) and
                              is_hallucination(pred_symbol, self.kb_vocab)),
            "prompt": trace.get("prompt", ""),
            "model_output": trace.get("final_annotation", ""),
            "scene_description": trace.get("scene_description", ""),
            "cultural_query": trace.get("cultural_query", {}),
            "seconds": trace.get("total_seconds", 0),
            "output_dir": trace.get("output_dir", ""),
            "human_edit": None,  # 人工审核后填 1(需修改)/0(无需修改)
        }

    def _empty_record(self, gt: Dict[str, Any], mode: str) -> Dict[str, Any]:
        return {
            "video_id": gt["video_id"], "video_path": gt["video_path"],
            "split": gt.get("split", ""), "kb_coverage": gt.get("kb_coverage", ""),
            "sample_type": gt.get("sample_type", ""),
            "mode": mode, "gt_symbol_ids": gt.get("gt_symbol_ids", []),
            "gt_symbols": gt.get("gt_symbols", []),
            "gt_dimension_code": gt.get("gt_dimension_code", ""),
            "retriever": None, "top1_symbol": "", "top5_symbols": [],
            "topk_candidates": [], "text_scores": {}, "image_scores": {},
            "fusion_scores": {}, "gate_level": "", "gate_reason": "",
            "gate_signals": {}, "effective_gate_level": "", "effective_gate_reason": "",
            "identity_gate_pass": None, "identity_gate_reason": "",
            "identity_passed_symbol_ids": [], "identity_evidence": [], "pred_symbol": "", "pred_dimension": "",
            "unknown_symbol": False, "hallucination": False,
            "prompt": "", "model_output": "",
            "scene_description": "", "cultural_query": {},
            "seconds": 0, "output_dir": "", "human_edit": None,
        }

    # ------------------------------------------------------------------ #
    # 落盘
    # ------------------------------------------------------------------ #
    @staticmethod
    def _save_per_video_csv(records: List[Dict[str, Any]], path: str) -> None:
        cols = ["video_id", "mode", "kb_coverage", "gate_level",
                "gt_symbols", "gt_dimension_code",
                "top1_symbol", "top5_symbols",
                "text_scores", "image_scores", "fusion_scores",
                "pred_symbol", "pred_dimension", "unknown_symbol",
                "symbol_note", "hallucination", "top1_hit", "top5_hit",
                "mrr_rank", "human_edit", "seconds", "output_dir"]
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=cols)
            writer.writeheader()
            for r in records:
                gt_ids = set(r["gt_symbol_ids"])
                cand_ids = [c["symbol_id"] for c in r["topk_candidates"]]
                rank = next((i + 1 for i, cid in enumerate(cand_ids) if cid in gt_ids), "")
                writer.writerow({
                    "video_id": r["video_id"], "mode": r["mode"],
                    "kb_coverage": r.get("kb_coverage", ""),
                    "gate_level": r.get("gate_level", ""),
                    "gt_symbols": ";".join(r["gt_symbols"]),
                    "gt_dimension_code": r["gt_dimension_code"],
                    "top1_symbol": r["top1_symbol"],
                    "top5_symbols": " > ".join(r["top5_symbols"]),
                    "text_scores": json.dumps(r["text_scores"], ensure_ascii=False),
                    "image_scores": json.dumps(r["image_scores"], ensure_ascii=False),
                    "fusion_scores": json.dumps(r["fusion_scores"], ensure_ascii=False),
                    "pred_symbol": r["pred_symbol"],
                    "pred_dimension": r["pred_dimension"],
                    "unknown_symbol": r["unknown_symbol"],
                    "symbol_note": "", "hallucination": r.get("hallucination", ""),
                    "top1_hit": bool(cand_ids[:1] and cand_ids[0] in gt_ids) if gt_ids else "",
                    "top5_hit": bool(any(cid in gt_ids for cid in cand_ids[:5])) if gt_ids else "",
                    "mrr_rank": rank, "human_edit": r.get("human_edit") or "",
                    "seconds": r["seconds"], "output_dir": r["output_dir"],
                })

    @staticmethod
    def _save_summary_csv(summaries: List[Dict[str, Any]], path: str) -> None:
        if not summaries:
            return
        cols = ["mode", "n_videos", "n_evaluable", "n_dimension_evaluable",
                "recall@1", "recall@5", "mrr",
                "symbol_accuracy", "dimension_accuracy",
                "hallucination_rate", "unknown_reject_rate",
                "gap_reject_rate", "hit_symbol_accuracy",
                "human_edit_rate", "avg_seconds"]
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=cols)
            writer.writeheader()
            for s in summaries:
                writer.writerow({c: s.get(c, "") for c in cols})
