"""
中华文化符号知识库模块（创新点2）

职责：
- SymbolKnowledgeBase：加载/查询中华文化符号知识库（当前为北京实验案例 47 条）
- CulturalSymbolRetriever：文化候选检索接口（多模态检索预留，默认不启用）

下游链路：
  中华文化知识库 → 多模态检索 → Top-K 文化候选 → 动态 Prompt
  → EMCAST 受控标注 → 人工审核 → 反馈回写知识库
"""

from .symbol_kb import SymbolKnowledgeBase
from .retriever import (
    CulturalCandidate,
    BaseCulturalRetriever,
    NullCulturalRetriever,
    KeywordCulturalRetriever,
)
from .clip_encoder import CLIPEncoder
from .multimodal_retriever import MultimodalCulturalRetriever
from .identity_evidence_gate import IdentityEvidenceGate

__all__ = [
    "SymbolKnowledgeBase",
    "CulturalCandidate",
    "BaseCulturalRetriever",
    "NullCulturalRetriever",
    "KeywordCulturalRetriever",
    "CLIPEncoder",
    "MultimodalCulturalRetriever",
    "IdentityEvidenceGate",
]
