"""
中华文化符号知识库加载与查询

数据来源：data/knowledge_base/chinese_cultural_symbols.json（126条实体，43张库内已确认参考图）
- culture_scope=中华文化：知识库总范围
- region=北京：当前实验案例的地域子集
- cultural_dimension / dimension_code：新五维（支持 ; 多标签）

本模块只做"加载 + 结构化查询 + Prompt 候选渲染"，不依赖任何模型/向量库，
供检索器（retriever.py）与 Prompt 管理器调用。
"""

import os
import json
from typing import Any, Dict, List, Optional


# 项目根目录下的默认知识库路径
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_KB_PATH = os.path.join(
    _PROJECT_ROOT, "data", "knowledge_base", "chinese_cultural_symbols.json"
)


class SymbolKnowledgeBase:
    """中华文化符号知识库（内存态，从 JSON 加载一次）"""

    def __init__(self, json_path: Optional[str] = None, region: Optional[str] = None):
        """
        Args:
            json_path: 知识库 JSON 路径，默认 chinese_cultural_symbols.json
            region: 仅加载该地域子集（如 "北京"）；None 表示加载全部地域
        """
        self.json_path = json_path or DEFAULT_KB_PATH
        self.region_filter = region
        self._meta: Dict[str, Any] = {}
        self._symbols: List[Dict[str, Any]] = []
        self._by_id: Dict[str, Dict[str, Any]] = {}
        self.load()

    # ------------------------------------------------------------------ #
    # 加载
    # ------------------------------------------------------------------ #
    def load(self) -> None:
        if not os.path.exists(self.json_path):
            raise FileNotFoundError(f"中华文化符号知识库不存在: {self.json_path}")
        with open(self.json_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        self._meta = {k: v for k, v in payload.items() if k != "symbols"}
        symbols = payload.get("symbols", [])
        if self.region_filter:
            symbols = [s for s in symbols if s.get("region") == self.region_filter]
        self._symbols = symbols
        self._by_id = {s["symbol_id"]: s for s in symbols}

    def reload(self) -> None:
        """审核反馈回写知识库后，可调用 reload 刷新内存态"""
        self.load()

    # ------------------------------------------------------------------ #
    # 基础查询
    # ------------------------------------------------------------------ #
    @property
    def symbols(self) -> List[Dict[str, Any]]:
        return self._symbols

    @property
    def dimensions(self) -> List[str]:
        return self._meta.get("dimensions", [])

    @property
    def dimension_codes(self) -> Dict[str, str]:
        return self._meta.get("dimension_codes", {})

    @property
    def meta(self) -> Dict[str, Any]:
        return self._meta

    def __len__(self) -> int:
        return len(self._symbols)

    def get(self, symbol_id: str) -> Optional[Dict[str, Any]]:
        return self._by_id.get(symbol_id)

    def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """按规范名（或别名）查符号，供评测端 GT→符号展开使用"""
        name = str(name).strip()
        if not name:
            return None
        for s in self._symbols:
            if s.get("canonical_name", "") == name:
                return s
        for s in self._symbols:
            if name in self.expand_terms(s):
                return s
        return None

    def by_dimension(self, dimension: str) -> List[Dict[str, Any]]:
        """返回归属该维度的符号（多标签符号会计入其每一个维度）"""
        result = []
        for s in self._symbols:
            dims = [d.strip() for d in s.get("cultural_dimension", "").split(";")]
            if dimension in dims:
                result.append(s)
        return result

    def expand_terms(self, symbol: Dict[str, Any]) -> List[str]:
        """展开一个符号的全部文本匹配项：规范名 + 别名 + 关键词"""
        terms = [symbol.get("canonical_name", "")]
        terms.extend(symbol.get("aliases", "").split("|"))
        terms.extend(symbol.get("keywords", "").split("|"))
        return [t.strip() for t in terms if t and t.strip()]

    # ------------------------------------------------------------------ #
    # 轻量文本检索（无模型；真正的多模态检索见 retriever.py 扩展点）
    # ------------------------------------------------------------------ #
    def search_scored(self, query_text: str, top_k: int = 5,
                      dimension: Optional[str] = None) -> List[tuple]:
        """带分数与命中依据的检索（search 的可解释版本）。

        Returns:
            [(score, matched_terms, symbol), ...] 按 score 降序，最多 top_k 条；
            matched_terms 为该符号命中的具体词（规范名/别名/关键词/特征词）。
        """
        if not query_text:
            return []
        query = query_text.lower()
        pool = self.by_dimension(dimension) if dimension else self._symbols
        scored = []
        for s in pool:
            score = 0
            matched = []
            # 规范名/别名/关键词命中权重最高
            for term in self.expand_terms(s):
                if term and term.lower() in query:
                    score += 3
                    matched.append(term)
            # 视觉特征/文化描述命中权重较低
            for field in ("visual_features", "cultural_description", "typical_scene"):
                for token in str(s.get(field, "")).split("|"):
                    token = token.strip()
                    if token and token.lower() in query:
                        score += 1
                        matched.append(token)
            if score > 0:
                scored.append((score, matched, s))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:top_k]

    def search(self, query_text: str, top_k: int = 5,
               dimension: Optional[str] = None) -> List[Dict[str, Any]]:
        """基于规范名/别名/关键词/视觉特征的子串打分检索。

        仅作为多模态检索未启用时的确定性兜底，不依赖 embedding 模型。
        """
        return [s for _, _, s in self.search_scored(query_text, top_k=top_k, dimension=dimension)]

    # ------------------------------------------------------------------ #
    # Prompt 候选渲染
    # ------------------------------------------------------------------ #
    @staticmethod
    def format_candidates(symbols: List[Dict[str, Any]]) -> str:
        """把 Top-K 符号候选渲染成可注入 C 层 Prompt 的中文文本块"""
        if not symbols:
            return ""
        lines = ["以下是知识库检索到的 Top-%d 文化符号候选（仅供参考，须结合画面实际判定，不得照抄）：" % len(symbols)]
        for i, s in enumerate(symbols, 1):
            lines.append(
                f"  {i}. {s.get('canonical_name')}"
                f"（维度：{s.get('cultural_dimension')}；"
                f"视觉特征：{s.get('visual_features', '')}）"
            )
        return "\n".join(lines)
