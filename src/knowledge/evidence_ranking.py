"""候选排序实验v1：固定尺度文本证据、双路候选；不替代身份核验或门控分数。"""
import math
import re
from collections import Counter
from .retriever import CulturalCandidate

# 通用物件或环境词只提供弱相关性，不提供具体实体身份。
GENERIC_TERMS = frozenset('湖面 湖泊 水面 石狮 红墙 黄瓦 绿树 树木 建筑 建筑群 广场 道路 山脉 灯笼 人群 公园 城市'.split())


def terms(value):
    return list(dict.fromkeys(x.strip() for x in (value if isinstance(value, list) else str(value or '').split('|')) if isinstance(x, str) and x.strip()))


def matched(term, text):
    if not term or len(term) < 2:
        return False
    if term.isascii():
        return re.search(r'(?<![a-z0-9])' + re.escape(term.lower()) + r'(?![a-z0-9])', text.lower()) is not None
    return term in text


class EvidenceRanker:
    def __init__(self, kb):
        self.kb = kb
        self.df = Counter()
        for symbol in kb.symbols:
            self.df.update(self._vocabulary(symbol))

    @staticmethod
    def _vocabulary(symbol):
        return set(t for f in ('canonical_name', 'aliases', 'keywords', 'visual_features', 'typical_scene')
                   for t in terms(symbol.get(f)) if len(t) >= 2)

    def text_evidence(self, symbol, context):
        text = str(context.get('scene_text') or '')
        if not text:
            text = ' '.join(terms(context.get('keywords')))
        names = terms([symbol.get('canonical_name', '')] + terms(symbol.get('aliases')))
        # 同一词在规范名/别名/关键词等多字段出现不重复加分。
        hits = sorted(t for t in self._vocabulary(symbol) if matched(t, text))
        from ..pipeline.scene_evidence import subject_evidence_text
        name_hits = [t for t in names if t not in GENERIC_TERMS and matched(t, subject_evidence_text(text))]
        review = context.get('text_recognition') or {}
        scene = context.get('structured_scene') or {}
        # 复核已发生时仅使用复核文字；否则允许结构化Pass-1的清楚文字。
        items = review.get('items', []) if review.get('status') in {'completed', 'partial_failure'} else scene.get('readable_text', [])
        clear = [x['text'].strip() for x in items if isinstance(x, dict) and isinstance(x.get('text'), str)
                 and x.get('legibility') == 'clear' and not any(c in x['text'] for c in '?？□�')]
        # 文字须完整等于规范名/别名；含父实体名称的更长牌名不能视作该候选精确命中。
        ocr_hits = sorted(set(t for t in names if t not in GENERIC_TERMS and t in clear))
        weak = [t for t in hits if t not in names]
        weighted = sum((0.02 if t in GENERIC_TERMS else 0.12 *
                        (math.log((len(self.kb)+1)/(self.df[t]+1))+1)/(math.log(len(self.kb)+1)+1))
                       for t in weak)
        strength = 1.0 if ocr_hits else 0.8 if name_hits else min(0.35, weighted)
        return {'name_hits': name_hits, 'clear_text_exact_hits': ocr_hits,
                'generic_hits': [t for t in hits if t in GENERIC_TERMS],
                'feature_hits': [t for t in weak if t not in GENERIC_TERMS],
                'text_evidence_strength': round(strength, 6),
                'identity_verified': False}

    def rerank(self, context, image_scores, legacy_candidates, top_k=5, region=None, dimension=None, fusion_alpha=0.5):
        if not 0 <= fusion_alpha <= 1:
            raise ValueError("fusion_alpha must be between 0 and 1")
        if top_k < 1:
            return []
        pool = [s for s in self.kb.symbols if (not region or s.get('region') == region)
                and (not dimension or dimension in str(s.get('dimension_code', '')).split(';')
                     or dimension in str(s.get('cultural_dimension', '')).split(';'))]
        evidence = {s['symbol_id']: self.text_evidence(s, context) for s in pool}
        # 每路各取至少top_k个，再合并，避免某一路低分直接消灭另一条召回路径。
        depth = max(10, top_k)
        text_pool = sorted((s for s in pool if fusion_alpha > 0 and evidence[s['symbol_id']]['text_evidence_strength'] > 0),
            key=lambda s: (-evidence[s['symbol_id']]['text_evidence_strength'], s['symbol_id']))[:depth]
        image_pool = sorted((s for s in pool if fusion_alpha < 1 and s['symbol_id'] in image_scores),
            key=lambda s: (-image_scores[s['symbol_id']], s['symbol_id']))[:depth]
        ids = {s['symbol_id'] for s in text_pool + image_pool}
        legacy = {c.symbol_id: c for c in legacy_candidates}
        ranked = []
        for symbol in pool:
            sid = symbol['symbol_id']
            if sid not in ids:
                continue
            ev = evidence[sid]
            im = image_scores.get(sid, 0.0)
            # 排序强度为开发版规则，非正确概率，门控仍使用原有标定分数。
            rank = fusion_alpha * ev['text_evidence_strength'] + (1-fusion_alpha) * im
            prior = legacy.get(sid)
            candidate = CulturalCandidate(sid, symbol['canonical_name'], symbol['cultural_dimension'],
                symbol['dimension_code'], score=prior.score if prior else 0,
                reason='证据排序v1；名称=' + '、'.join(ev['name_hits']) + '；文字=' + '、'.join(ev['clear_text_exact_hits'])
                       + '；弱特征=' + '、'.join(ev['generic_hits'] + ev['feature_hits']),
                image_score=round(im, 4), text_score=prior.text_score if prior else 0,
                fusion_score=prior.fusion_score if prior else 0, raw=symbol,
                ranking_score=round(rank, 6), retrieval_evidence=dict(ev,
                    strategy='evidence_v1', score_semantics='ranking_only_not_probability',
                    gate_score_source='legacy_fusion_not_recalibrated',
                    in_text_pool=sid in {s['symbol_id'] for s in text_pool},
                    in_image_pool=sid in {s['symbol_id'] for s in image_pool}))
            ranked.append(candidate)
        # 清楚文字名称 > 描述中的名称 > 仅弱特征/图像；每层内部按融合排序。
        ranked.sort(key=lambda c: (-bool(fusion_alpha > 0 and c.retrieval_evidence['clear_text_exact_hits']),
                                  -bool(fusion_alpha > 0 and c.retrieval_evidence['name_hits']), -c.ranking_score, c.symbol_id))
        return ranked[:top_k]
