"""Auditable candidate-specific identity evidence for cultural-symbol RAG."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .symbol_kb import SymbolKnowledgeBase


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "config" / "identity_evidence_gate.json"
_CJK_OR_ALNUM = re.compile(r"[\u3400-\u9fffA-Za-z0-9]")


def _normalise(value: Any) -> str:
    return re.sub(r"[\s\W_]+", "", str(value or "").lower(), flags=re.UNICODE)


def _terms(symbol: Dict[str, Any]) -> Iterable[tuple[str, str]]:
    canonical = str(symbol.get("canonical_name", "")).strip()
    if len(_normalise(canonical)) >= 2:
        yield "canonical", canonical
    aliases = symbol.get("aliases") or ""
    if isinstance(aliases, str):
        aliases = aliases.split("|")
    for alias in aliases:
        alias = str(alias).strip()
        if len(_normalise(alias)) >= 2:
            yield "alias", alias


def _focus_text(scene_description: str) -> str:
    """Keep the scene-description portion and exclude the element list."""
    text = str(scene_description or "")
    for marker in ("2.【文化视觉元素】", "【文化视觉元素】", "2.文化视觉元素"):
        if marker in text:
            text = text.split(marker, 1)[0]
    return text


def _is_complete_entity(text: str, start: int, end: int, suffixes: List[str],
                        regions: Iterable[str] = ()) -> bool:
    """Reject a candidate name used merely as another entity's prefix."""
    before = text[start - 1] if start else ""
    after = text[end:end + 12]
    term = text[start:end]
    # Latin/acronym names (for example CBD) have ordinary alphanumeric word
    # boundaries even when Chinese location text precedes them.
    ascii_term = bool(re.fullmatch(r"[A-Za-z0-9]+", term))
    permitted_left_context = "的在于为是从向与和及、，。；：()（）【】"
    prefix_is_region = any(region and text[:start].endswith(region) for region in regions)
    if before and _CJK_OR_ALNUM.match(before) and not ascii_term and not prefix_is_region and before not in permitted_left_context and before not in "旁前后内中上下":
        return False
    if not after or not _CJK_OR_ALNUM.match(after[0]):
        return True
    return any(after.startswith(suffix) for suffix in suffixes)


def _occurrences(text: str, term: str) -> Iterable[tuple[int, int]]:
    start = 0
    while True:
        pos = text.find(term, start)
        if pos < 0:
            return
        yield pos, pos + len(term)
        start = pos + max(1, len(term))


@dataclass
class IdentityEvidence:
    symbol_id: str
    canonical_name: str
    identity_name_match: bool
    identity_alias_match: bool
    identity_ocr_match: str
    identity_unique_attribute_match: bool
    identity_reference_image_match: str
    identity_evidence_count: int
    identity_evidence_level: str
    identity_gate_pass: bool
    identity_gate_reason: str
    category_evidence: str
    weak_name_mentions: List[str]
    unique_attribute_matches: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


class IdentityEvidenceGate:
    """Separate identity evidence from retrieval/category similarity."""

    def __init__(self, kb: Optional[SymbolKnowledgeBase] = None,
                 config_path: Optional[str] = None):
        self.kb = kb or SymbolKnowledgeBase()
        self.config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        with self.config_path.open(encoding="utf-8") as f:
            self.config = json.load(f)
        self.suffixes = list(self.config["focus_suffixes"])
        self.min_unique_len = int(self.config["unique_attribute"]["minimum_normalized_length"])
        self.regions = {str(s.get("region", "")).strip() for s in self.kb.symbols if s.get("region")}

    def _symbol_for(self, candidate: Any) -> Dict[str, Any]:
        if isinstance(candidate, dict):
            return candidate.get("raw") or self.kb.get(candidate.get("symbol_id", "")) or candidate
        return getattr(candidate, "raw", None) or self.kb.get(getattr(candidate, "symbol_id", "")) or {}

    def _unique_attributes(self, symbol: Dict[str, Any]) -> List[str]:
        names = {_normalise(term) for _, term in _terms(symbol)}
        attrs = []
        for raw in str(symbol.get("visual_features", "")).split("|"):
            raw, norm = raw.strip(), _normalise(raw)
            if len(norm) < self.min_unique_len or any(name and name in norm for name in names):
                continue
            # Compound lists describe broad categories/relations, not a unique
            # property that this first deterministic version can safely prove.
            if any(ch in raw for ch in "（）()/、；;"):
                continue
            attrs.append(raw)
        return attrs

    @staticmethod
    def _focus_subject(text: str) -> str:
        """Extract the declared visual focus, if the scene description has one."""
        m = re.search(r"(?:画面)?主体(?:为|是)\s*([^，。；;\n]+)", text)
        return m.group(1).strip() if m else ""

    def _has_conflicting_focus_entity(self, focus: str, symbol: Dict[str, Any]) -> bool:
        """Detect a named focus different from this candidate without an NER model.

        It only acts on explicit quotation or common named-entity endings.  A
        generic subject such as '现代化高楼、车流与河流' is therefore not a
        conflict, while a specifically named gate/building or a quoted plaque
        is.
        """
        subject = self._focus_subject(focus)
        if not subject:
            return False
        for _, term in _terms(symbol):
            subject = subject.replace(term, "")
        if re.search(r"[“\"'].*?[”\"']", subject):
            return True
        generic = ("现代化|传统|中式|宏伟|一座|建筑群|建筑|高楼|车流|河流|人群|街道|"
                   "景观|广场|天空|画面|外观|前方|周边|及其")
        residual = re.sub(generic, "", subject)
        return bool(re.search(r"[\u4e00-\u9fff]{2,}(?:门|中心|馆|堂|园|楼|塔|院|城)", residual))

    def assess_candidate(self, candidate: Any, scene_description: str) -> IdentityEvidence:
        symbol = self._symbol_for(candidate)
        focus, all_text = _focus_text(scene_description), str(scene_description or "")
        canonical_hit = alias_hit = False
        weak_mentions: List[str] = []
        conflict = self._has_conflicting_focus_entity(focus, symbol)
        for kind, term in _terms(symbol):
            complete = any(_is_complete_entity(focus, start, end, self.suffixes, self.regions)
                           for start, end in _occurrences(focus, term))
            if complete:
                canonical_hit |= kind == "canonical"
                alias_hit |= kind == "alias"
                continue
            global_complete = any(
                _is_complete_entity(all_text, start, end, self.suffixes, self.regions)
                for start, end in _occurrences(all_text, term)
            )
            if global_complete and not conflict:
                canonical_hit |= kind == "canonical"
                alias_hit |= kind == "alias"
            elif term in all_text:
                weak_mentions.append(term)
        attributes = [attr for attr in self._unique_attributes(symbol) if attr in focus]
        unique_hit = bool(attributes)
        strong = canonical_hit or alias_hit or unique_hit
        if strong:
            level, reason = "strong", "场景主体描述中命中候选完整名称/别名或KB独特属性"
        elif weak_mentions:
            level, reason = "weak", "仅有上下文提及或更长实体中的名称前缀，不能确认具体身份"
        else:
            level, reason = "none", "未发现候选完整名称、别名或KB独特属性"
        return IdentityEvidence(
            symbol_id=str(symbol.get("symbol_id", "")), canonical_name=str(symbol.get("canonical_name", "")),
            identity_name_match=canonical_hit, identity_alias_match=alias_hit,
            identity_ocr_match="unavailable", identity_unique_attribute_match=unique_hit,
            identity_reference_image_match="unavailable",
            identity_evidence_count=int(canonical_hit) + int(alias_hit) + int(unique_hit),
            identity_evidence_level=level, identity_gate_pass=strong,
            identity_gate_reason=reason,
            category_evidence=f"dimension={symbol.get('dimension_code', '')}; type={symbol.get('symbol_type', '')}",
            weak_name_mentions=sorted(set(weak_mentions)), unique_attribute_matches=attributes,
        )

    def assess_candidates(self, candidates: Iterable[Any], scene_description: str) -> List[IdentityEvidence]:
        return [self.assess_candidate(candidate, scene_description) for candidate in candidates]

    @staticmethod
    def passed_symbol_ids(evidence: Iterable[IdentityEvidence]) -> set[str]:
        return {item.symbol_id for item in evidence if item.identity_gate_pass}
