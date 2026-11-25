"""
创新点2 端到端文化检索链路编排（Cultural RAG Pipeline）

链路：视频关键帧 → VLM视觉描述 → 提取文化Query → KeywordCulturalRetriever
      → Top-K文化候选 → 动态注入Prompt → EMCAST C层文化标注

设计约束（对应创新点2）：
- 完全复用现有 InferenceEngine / PromptManager / knowledge 检索器，不改变既有行为；
- 知识库候选仅作参考线索注入 Prompt，最终 C 层结论由模型结合画面证据判定；
- 画面证据不足时允许输出 unknown_symbol，禁止强行匹配；
- Free Prompt 模式（use_kb=False，不检索、不注入候选）完整保留，可作 A/B 对照；
- Retriever 可插拔（BaseCulturalRetriever 子类），为后续图像/多模态检索预留接口；
- 中间结果全部落盘：视觉描述 / Query / Top-K候选及分数 / Prompt / 最终C层结果。
"""

import os
import re
import json
import time
import hashlib
from typing import Any, Dict, List, Optional

from .inference_engine import InferenceEngine
from ..knowledge.symbol_kb import SymbolKnowledgeBase
from ..knowledge.retriever import (
    BaseCulturalRetriever,
    KeywordCulturalRetriever,
    extract_cultural_query,
)
from ..knowledge.rejection_gate import RejectionGate
from ..knowledge.identity_evidence_gate import IdentityEvidenceGate
from ..metrics.cultural_metrics import extract_cultural_category


from .scene_evidence import (
    STRUCTURED_SCENE_PROMPT, LEGACY_SCENE_PROMPT,
    normalize_scene, retrieval_text, review_text_regions,
)

SCENE_DESCRIBE_PROMPT = STRUCTURED_SCENE_PROMPT


def parse_c_layer(text: str) -> Dict[str, Any]:
    """从最终 EMCAST 标注文本中解析 C 文化维度层结果。

    Returns:
        {'dimension': 五维维度名（可能空）, 'core_symbol': 核心符号行,
         'unknown_symbol': bool, 'raw_block': C层原文}
    """
    if not text:
        return {"dimension": "", "core_symbol": "", "unknown_symbol": False, "raw_block": ""}
    m = re.search(r"【C｜文化维度层】(.*?)(?=\n\s*【|\Z)", text, re.S)
    block = m.group(1).strip() if m else ""
    core_symbol = ""
    ms = re.search(r"核心符号[：:]\s*(.+)", block)
    if ms:
        core_symbol = ms.group(1).strip()
    return {
        "dimension": extract_cultural_category(block),
        "core_symbol": core_symbol,
        "unknown_symbol": "unknown_symbol" in block,
        "raw_block": block,
    }


def extract_pred_names(core_symbol: str) -> List[str]:
    """从模型核心符号输出中抽取其选择的符号名（可多个，顿号分隔）"""
    if not core_symbol:
        return []
    t = core_symbol.strip()
    m = re.search(r"为(.+?)(?:。|（|$)", t)
    seg = m.group(1) if m else t.split("（")[0]
    seg = seg.strip("[] \t")
    parts = re.split(r"[、，,；;]", seg)
    return [p.strip(" 。[]") for p in parts if p.strip(" 。[]")]


def alias_set_of(kb: "SymbolKnowledgeBase", symbol: Dict[str, Any]) -> set:
    """规范名+别名集合（兼容 list 与 '|' 分隔字符串两种存储格式）"""
    names = set()
    if symbol.get("canonical_name"):
        names.add(str(symbol["canonical_name"]).strip())
    aliases = symbol.get("aliases") or []
    if isinstance(aliases, str):
        aliases = [x.strip() for x in aliases.split("|") if x.strip()]
    names.update(str(a).strip() for a in aliases if str(a).strip())
    return names


class CulturalRAGPipeline:
    """创新点2 端到端链路：检索 → 动态Prompt → 受控标注（Retriever 可插拔）"""

    def __init__(self,
                 engine: Optional[InferenceEngine] = None,
                 kb: Optional[SymbolKnowledgeBase] = None,
                 retriever: Optional[BaseCulturalRetriever] = None,
                 top_k: int = 5,
                 output_root: Optional[str] = None,
                 rejection_gate: Optional[RejectionGate] = None,
                 identity_gate: Optional[IdentityEvidenceGate] = None,
                 identity_verifier=None, scene_mode="structured", text_recognition=True,
                 evidence_policy="v1"):
        """
        Args:
            engine: 推理引擎；None 时按默认配置创建（GLM API 模式）
            kb: 知识库；None 时加载默认 data/knowledge_base/chinese_cultural_symbols.json
            retriever: 检索器（可插拔）；None 时使用 KeywordCulturalRetriever，
                后续可替换为图像/多模态检索子类而不改动本管线
            top_k: 检索候选数
            output_root: 中间结果根目录，默认 experiments/innovation2/outputs/cultural_rag
            rejection_gate: 拒识门控（None=关闭，保持旧行为）；启用后按
                检索分数/Top1-Top2分差/视觉证据充分性三信号决定候选注入策略
            identity_gate: 身份证据门控；仅保留有完整名称/别名或KB独特属性
                证据的候选，None 时保持既有行为。
        """
        self.engine = engine or InferenceEngine()
        self.kb = kb or SymbolKnowledgeBase()
        self.retriever = retriever or KeywordCulturalRetriever(self.kb)
        self.rejection_gate = rejection_gate
        self.identity_gate = identity_gate
        self.identity_verifier = identity_verifier
        if evidence_policy not in {"v1", "context_v2"}:
            raise ValueError("Unknown evidence policy")
        self.evidence_policy = evidence_policy
        if scene_mode not in {"structured", "legacy"}:
            raise ValueError("scene_mode must be structured or legacy")
        self.scene_mode = scene_mode
        self.text_recognition = text_recognition
        self.top_k = top_k
        base = output_root or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            'experiments/innovation2/outputs/cultural_rag')
        self.output_root = base
        self.engine.initialize()

    # ------------------------------------------------------------------ #
    # 主入口
    # ------------------------------------------------------------------ #
    def run(self, video_path: str, use_kb: bool = True,
            controlled: bool = False,
            save: bool = True, out_dir: Optional[str] = None,
            tag: Optional[str] = None,
            scene_description: Optional[str] = None,
            gate_mode: Optional[str] = None,
            prepared_evidence: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Args:
            video_path: 视频路径
            use_kb: True=知识库检索链路（kb模式）；False=Free Prompt 模式
            controlled: 受控输出模式（消融实验模式5）：Top-K候选作为闭集，
                核心符号必须从候选中选择或输出 unknown_symbol
            save: 是否落盘中间结果
            out_dir: 指定输出目录（both 模式复用同一目录）
            tag: 产物文件名标签（消融实验传模式名）；默认 kb/free
            scene_description: 外部缓存的 Pass-1 场景描述；传入则跳过 Pass-1
                VLM 调用（消融实验同视频跨模式复用，省 API 次数）
            gate_mode: 拒识门控模式族名（text/image/multimodal/multimodal_controlled）；
                None 时按检索器类型推断
        Returns:
            trace 字典（含全部中间结果与计时）
        """
        t0 = time.time()
        valid, error = self.engine.video_processor.validate_video(video_path)
        if not valid:
            raise ValueError(error)
        stem = os.path.splitext(os.path.basename(video_path))[0]
        if out_dir is None:
            out_dir = os.path.join(
                self.output_root,
                time.strftime("%Y%m%d_%H%M%S") + "_" + stem)
        if save:
            os.makedirs(out_dir, exist_ok=True)

        trace: Dict[str, Any] = {
            "video_path": video_path,
            "mode": "kb" if use_kb else "free",
            "controlled_output": controlled,
            "kb_enabled": use_kb,
            "top_k": self.top_k if use_kb else 0,
            "retriever": type(self.retriever).__name__ if use_kb else None,
            "retrieval_strategy": getattr(self.retriever, "ranking_strategy", "legacy"),
            "retrieval_calibration_status": "experimental_unrecalibrated" if getattr(self.retriever, "ranking_strategy", "legacy") != "legacy" else "legacy_thresholds",
            "steps": {},
        }

        # 1. 视频元数据（与 engine 内部一致，用于复现 Prompt）
        metadata = self.engine.video_processor.get_video_metadata(video_path)
        meta_dict = metadata.to_dict()

        if not use_kb:
            # ---------------- Free Prompt 模式（无知识库） ----------------
            t = time.time()
            prompt = self.engine.prompt_manager.get_emcast_prompt(meta_dict, video_path, None)
            final = self.engine.annotate_video(video_path, prompt=prompt)
            trace["steps"]["annotate"] = round(time.time() - t, 2)
            trace["prompt"] = prompt
            trace["final_annotation"] = final
            trace["final_c_layer"] = parse_c_layer(final)
        else:
            # ---------------- KB 检索链路 ----------------
            if prepared_evidence is not None:
                import copy
                for key in ("scene_description_raw", "scene_description", "scene_evidence_version", "structured_scene", "scene_parse_error", "text_recognition", "retrieval_scene_text", "scene_repair", "hypothesis_provenance"):
                    if key in prepared_evidence:
                        trace[key] = copy.deepcopy(prepared_evidence[key])
                scene_description = trace["scene_description"]
                if trace.get("scene_evidence_version") == "structured_parse_failed":
                    from .scene_evidence import SceneEvidenceError
                    raise SceneEvidenceError("Cached scene acquisition failed; repair before inference")
                trace["scene_description_cached"] = True
                trace["prepared_evidence_reused"] = True
                if save:
                    with open(os.path.join(out_dir, "00_scene_evidence.json"), "w", encoding="utf-8") as f:
                        json.dump(prepared_evidence, f, ensure_ascii=False, indent=2)
            else:
                # Step1: VLM 视觉描述（Pass-1，关键帧→文本桥梁）；外部缓存可复用
                used_cache = scene_description is not None
                if not used_cache:
                    t = time.time()
                    scene_description = self.engine.annotate_video(
                        video_path, prompt=(SCENE_DESCRIBE_PROMPT if self.scene_mode == "structured" else LEGACY_SCENE_PROMPT))
                    trace["steps"]["scene_description"] = round(time.time() - t, 2)
                trace["scene_description_raw"] = scene_description
                trace["scene_evidence_version"] = "structured_v1" if self.scene_mode == "structured" else "legacy"
                if self.scene_mode == "structured":
                    try:
                        scene = normalize_scene(scene_description)
                    except (ValueError, TypeError) as exc:
                        # 历史缓存保留可复用；新格式失败时不把未校验JSON/猜测直接送进检索。
                        trace["scene_parse_error"] = str(exc)
                        legacy_cache = used_cache and isinstance(scene_description, str) and not scene_description.lstrip().startswith(("{", "```"))
                        trace["scene_evidence_version"] = "legacy_cache" if legacy_cache else "structured_parse_failed"
                        if not legacy_cache:
                            from .scene_evidence import recover_scene
                            manager = getattr(self.engine, "model_manager", None)
                            scene, repair = recover_scene(scene_description, getattr(manager, "call_glm_api", None))
                            trace["scene_repair"] = repair
                            trace["structured_scene"] = scene
                            trace["scene_evidence_version"] = "structured_repaired"
                            trace["text_recognition"] = {"status": "not_reviewed_after_repair", "calls": 0, "items": []}
                            scene_description = retrieval_text(scene, [], reviewed=False)
                    else:
                        trace["structured_scene"] = scene
                        if self.text_recognition and scene["text_regions"]:
                            started = time.time()
                            import tempfile
                            if save:
                                review = review_text_regions(video_path, scene["text_regions"],
                                    self.engine.model_manager, os.path.join(out_dir, "text_evidence"))
                            else:
                                with tempfile.TemporaryDirectory(prefix="emcast_text_") as tmp:
                                    review = review_text_regions(video_path, scene["text_regions"],
                                        self.engine.model_manager, tmp)
                                review["temporary_images_removed"] = True
                            trace["text_recognition"] = review
                            trace["steps"]["text_recognition"] = round(time.time() - started, 2)
                        else:
                            trace["text_recognition"] = {"status": "disabled" if not self.text_recognition else "not_needed", "calls": 0, "items": []}
                        scene_description = retrieval_text(scene, trace["text_recognition"]["items"],
                            reviewed=trace["text_recognition"].get("status") in {"completed", "partial_failure"})
                trace["scene_description"] = scene_description
                trace["scene_description_cached"] = used_cache

                if save:
                    with open(os.path.join(out_dir, "00_scene_evidence.json"), "w", encoding="utf-8") as f:
                        json.dump({k: trace[k] for k in ("scene_description_raw", "scene_description", "scene_evidence_version", "structured_scene", "scene_parse_error", "text_recognition") if k in trace}, f, ensure_ascii=False, indent=2)

            if self.evidence_policy == "context_v2" and trace.get("structured_scene"):
                from .scene_evidence import contextual_evidence_text
                review = trace.get("text_recognition", {})
                scene_description = contextual_evidence_text(
                    trace["structured_scene"], review.get("items", []),
                    reviewed=review.get("status") in {"completed", "partial_failure"})
                trace["scene_description"] = scene_description
                trace["scene_evidence_version"] = "structured_context_v2"
                if save:
                    with open(os.path.join(out_dir, "00_scene_evidence.json"), "w", encoding="utf-8") as f:
                        json.dump({k: trace[k] for k in ("scene_description_raw", "scene_description", "scene_evidence_version", "structured_scene", "text_recognition") if k in trace}, f, ensure_ascii=False, indent=2)

            # Step2: 提取文化Query（知识库词表确定性扫描）
            keywords = extract_cultural_query(self.kb, scene_description)
            video_context = {
                "video_path": video_path,
                "scene_text": trace.get("retrieval_scene_text", scene_description),
                "keywords": extract_cultural_query(self.kb, trace["retrieval_scene_text"]) if trace.get("retrieval_scene_text") else keywords,
                "structured_scene": trace.get("structured_scene", {}),
                "text_recognition": trace.get("text_recognition", {}),
            }
            trace["cultural_query"] = {"scene_text": video_context["scene_text"],
                                       "keywords": video_context["keywords"],
                                       "identity_evidence_text": scene_description}

            # Step3: 检索 Top-K 文化候选
            t = time.time()
            candidates = self.retriever.retrieve(video_context, top_k=self.top_k)
            trace["steps"]["retrieve"] = round(time.time() - t, 2)
            trace["topk_candidates"] = [
                {"symbol_id": c.symbol_id, "canonical_name": c.canonical_name,
                 "cultural_dimension": c.cultural_dimension,
                 "dimension_code": c.dimension_code,
                 "score": c.score, "reason": c.reason,
                 "image_score": c.image_score, "text_score": c.text_score,
                 "fusion_score": c.fusion_score,
                 "ranking_score": c.ranking_score, "retrieval_evidence": c.retrieval_evidence}
                for c in candidates]

            # Step3.5: 拒识门控（三信号：检索分数/Top1-Top2分差/视觉证据充分性）
            gate_decision = None
            effective_gate_decision = None
            if self.rejection_gate is not None:
                gate_mode_eff = gate_mode or (
                    "text" if isinstance(self.retriever, KeywordCulturalRetriever)
                    else "multimodal")
                gate_decision = self.rejection_gate.decide(
                    candidates, keywords, scene_description,
                    mode=gate_mode_eff).to_dict()
                trace["rejection_gate"] = gate_decision
                print(f"    [拒识门控] {gate_decision['level']}：{gate_decision['reason']}")
                effective_gate_decision = gate_decision

            # Step3.6: 身份证据门控。该层不改变既有检索排序；只在
            # Confidence Gate 已放行时，筛掉没有具体身份依据的候选。
            prompt_candidates = candidates
            if self.identity_gate is not None and gate_decision is not None:
                evidence = self.identity_gate.assess_candidates(candidates, scene_description)
                passed_ids = self.identity_gate.passed_symbol_ids(evidence)
                trace["identity_evidence"] = [item.to_dict() for item in evidence]
                if gate_decision["level"] == "insufficient":
                    trace["identity_gate"] = {
                        "identity_gate_pass": False,
                        "reason": "Existing Confidence Gate already rejected the sample.",
                        "passed_symbol_ids": [],
                    }
                elif not passed_ids:
                    trace["identity_gate"] = {
                        "identity_gate_pass": False,
                        "reason": "No retrieval candidate has strong identity evidence.",
                        "passed_symbol_ids": [],
                    }
                    effective_gate_decision = {
                        "level": "insufficient",
                        "signals": gate_decision.get("signals", {}),
                        "reason": "Identity Evidence Gate: no candidate-specific identity evidence",
                    }
                    prompt_candidates = []
                    print("    [身份门控] insufficient：没有候选具备身份级证据")
                else:
                    trace["identity_gate"] = {
                        "identity_gate_pass": True,
                        "reason": "At least one candidate has strong identity evidence.",
                        "passed_symbol_ids": sorted(passed_ids),
                    }
                    prompt_candidates = [
                        c for c in candidates
                        if (c.get("symbol_id") if isinstance(c, dict) else c.symbol_id) in passed_ids
                    ]
                    print(f"    [身份门控] pass：保留 {len(prompt_candidates)} 个候选")

            trace["effective_gate"] = effective_gate_decision

            # Step4: 动态注入 Prompt（复现 engine 将使用的完整 Prompt 供留存；
            # 受控模式时候选升级为闭集约束；门控决策注入拒识指令）
            symbol_dicts = [c.to_symbol_dict() for c in prompt_candidates]
            prompt = self.engine.prompt_manager.get_emcast_prompt(
                meta_dict, video_path, symbol_dicts, controlled_output=controlled,
                rejection=effective_gate_decision)
            trace["prompt"] = prompt

            # Step5: EMCAST 受控标注（Pass-2，C层结合画面证据终判；
            # 显式传入已构建 Prompt，与 engine 内部构建逻辑一致）
            t = time.time()
            final = self.engine.annotate_video(video_path, prompt=prompt)
            trace["steps"]["annotate"] = round(time.time() - t, 2)
            trace["final_annotation"] = final
            c_layer = parse_c_layer(final)
            # 确定性输出约束：gate=insufficient 或受控模式时，
            # 最终符号必须属于候选闭集（规范名/别名），否则改写 unknown_symbol
            if effective_gate_decision is not None or controlled:
                c_layer = self.enforce_symbol_constraint(
                    c_layer, prompt_candidates, controlled,
                    (effective_gate_decision or {}).get("level", "confident"))
                if trace.get("rejection_gate") is not None:
                    trace["rejection_gate"]["constraint_overridden"] = c_layer.get("overridden", False)
            if self.identity_verifier is not None and not c_layer.get("unknown_symbol"):
                names = extract_pred_names(c_layer.get("core_symbol", ""))
                selected = [c for c in prompt_candidates
                            if any(n in alias_set_of(self.kb, c.to_symbol_dict()) for n in names)]
                decisions = []
                # Verify every emitted entity, never accept a whole list on one matching name.
                for candidate in selected:
                    pred = candidate.canonical_name
                    decisions.append(self.identity_verifier.decide(
                        hashlib.sha256(os.path.realpath(video_path).encode()).hexdigest()[:16] + "_" + stem,
                        video_path, scene_description,
                        [dict(c) for c in trace["topk_candidates"]], pred_symbol=pred,
                        text_top1=max(trace["topk_candidates"], key=lambda c: c.get("text_score") or 0)["canonical_name"],
                        image_top1=max(trace["topk_candidates"], key=lambda c: c.get("image_score") or 0)["canonical_name"]))
                trace["identity_verification"] = decisions
                if not decisions or any(not d.get("final_symbol") for d in decisions):
                    c_layer = dict(c_layer, overridden=True,
                                   original_core_symbol=c_layer.get("core_symbol", ""),
                                   core_symbol="unknown_symbol", unknown_symbol=True)
            trace["raw_final_annotation"] = final
            if c_layer.get("overridden"):
                replacement = ("【C｜文化维度层】：" + ("该场景隶属于" + c_layer["dimension"] + "。" if c_layer.get("dimension") else "文化维度证据不足。")
                               + "\n核心符号：unknown_symbol\n价值指向：缺少足够的具体文化符号身份证据，保留未知判定。\n")
                final = re.sub(r"【C｜文化维度层】.*?(?=\n\s*【|\Z)",
                               lambda _: replacement, final, count=1, flags=re.S)
            trace["final_annotation"] = final
            trace["final_c_layer"] = dict(parse_c_layer(final),
                                          **{k: v for k, v in c_layer.items() if k in {"overridden", "original_core_symbol"}})

        # T is always rendered from extracted metadata, never inferred by the VLM.
        final = trace["final_annotation"]
        final = re.sub(r"【T｜技术属性层】.*?(?=\n\s*【|\Z)", "", final, flags=re.S).rstrip()
        trace["final_annotation"] = final + "\n\n" + self.engine.prompt_manager._generate_tech_layer_template(meta_dict)
        trace["kb_path"] = self.kb.json_path
        trace["total_seconds"] = round(time.time() - t0, 2)
        trace["output_dir"] = out_dir
        if save:
            self._save_artifacts(trace, use_kb, tag=tag)
        return trace

    # ------------------------------------------------------------------ #
    # 确定性输出约束（拒识机制的硬保证层）
    # ------------------------------------------------------------------ #
    def _candidate_names(self, candidates: List[Any]) -> set:
        names = set()
        for c in candidates:
            sym = None
            sid = c.get("symbol_id") if isinstance(c, dict) else getattr(c, "symbol_id", None)
            raw = c.get("raw") if isinstance(c, dict) else getattr(c, "raw", None)
            if raw:
                names |= alias_set_of(self.kb, raw)
            elif sid and self.kb.get(sid):
                names |= alias_set_of(self.kb, self.kb.get(sid))
            cname = c.get("canonical_name") if isinstance(c, dict) \
                else getattr(c, "canonical_name", "")
            if cname:
                names.add(str(cname).strip())
        return {n for n in names if n}

    def enforce_symbol_constraint(self, c_layer: Dict[str, Any],
                                  candidates: List[Any], controlled: bool,
                                  gate_level: str) -> Dict[str, Any]:
        """最终符号 ∈ 候选闭集 ∪ {unknown_symbol} 的确定性保证（禁闭集外错误匹配）

        - 模型已输出 unknown_symbol → 保留；
        - 输出符号名与任一候选（规范名/别名）匹配（规范名或别名精确匹配）→ 保留；
        - 否则：gate=insufficient 或受控模式 → 确定性改写为 unknown_symbol，
          并保留原始输出供追溯（overridden/original_core_symbol）；
        - 非受控且 gate=confident/uncertain → 不干预（保留模型判定自由）。
        """
        pred = c_layer.get("core_symbol", "") or ""
        if c_layer.get("unknown_symbol"):
            return c_layer
        names = self._candidate_names(candidates)
        pred_names = extract_pred_names(pred)
        matched = bool(pred_names) and all(pn in names for pn in pred_names)
        if matched and gate_level != "insufficient":
            return c_layer
        if gate_level == "insufficient" or controlled:
            out = dict(c_layer)
            out["overridden"] = True
            out["original_core_symbol"] = pred
            out["core_symbol"] = "unknown_symbol"
            out["unknown_symbol"] = True
            print(f"    [约束执行] 输出符号不在候选闭集内 → 改写 unknown_symbol")
            return out
        return c_layer

    # ------------------------------------------------------------------ #
    # 中间结果落盘
    # ------------------------------------------------------------------ #
    def _save_artifacts(self, trace: Dict[str, Any], use_kb: bool,
                        tag: Optional[str] = None) -> None:
        out_dir = trace["output_dir"]
        tag = tag or ("kb" if use_kb else "free")
        with open(os.path.join(out_dir, f"01_scene_description_{tag}.txt"),
                  "w", encoding="utf-8") as f:
            f.write(trace.get("scene_description", "") or "")
        with open(os.path.join(out_dir, f"02_cultural_query_{tag}.json"),
                  "w", encoding="utf-8") as f:
            json.dump(trace.get("cultural_query", {}),
                      f, ensure_ascii=False, indent=2)
        with open(os.path.join(out_dir, f"03_topk_candidates_{tag}.json"),
                  "w", encoding="utf-8") as f:
            json.dump(trace.get("topk_candidates", []),
                      f, ensure_ascii=False, indent=2)
        with open(os.path.join(out_dir, f"04_prompt_{tag}.txt"),
                  "w", encoding="utf-8") as f:
            f.write(trace.get("prompt", "") or "")
        with open(os.path.join(out_dir, f"05_final_annotation_{tag}.txt"),
                  "w", encoding="utf-8") as f:
            f.write(trace.get("final_annotation", "") or "")
        if trace.get("rejection_gate"):
            with open(os.path.join(out_dir, f"06_rejection_gate_{tag}.json"),
                      "w", encoding="utf-8") as f:
                json.dump(trace["rejection_gate"], f, ensure_ascii=False, indent=2)
        if trace.get("identity_evidence"):
            with open(os.path.join(out_dir, f"07_identity_evidence_{tag}.json"),
                      "w", encoding="utf-8") as f:
                json.dump({"decision": trace.get("identity_gate", {}),
                           "candidates": trace["identity_evidence"]},
                          f, ensure_ascii=False, indent=2)

    def save_trace(self, traces: List[Dict[str, Any]], out_dir: str) -> str:
        """汇总 trace（含最终C层解析结果）写入 pipeline_trace.json"""
        path = os.path.join(out_dir, "pipeline_trace.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(traces, f, ensure_ascii=False, indent=2)
        return path
