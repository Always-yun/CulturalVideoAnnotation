"""Auditable entity-level retrieval for the frozen C-layer experiment.

These ranking scores are not identity probabilities. Production retrieval stays
unchanged; this module makes experimental normalization and missingness explicit.
"""
import math


def rank_scale(scores):
    """Average ties, map descending entity ranks to [0,1], singleton to 1.

    The candidate pool size is the number of observed scores in this modality.
    Missing entities are absent, not an invented zero cosine measurement.
    """
    values = {k: float(v) for k, v in scores.items() if math.isfinite(float(v))}
    n = len(values)
    if n == 0:
        return {}
    ordered = sorted(values, key=lambda k: (-values[k], k))
    result = {}
    start = 0
    while start < n:
        end = start + 1
        while end < n and values[ordered[end]] == values[ordered[start]]:
            end += 1
        mean_rank = (start + end - 1) / 2
        score = 1.0 if n == 1 else 1 - mean_rank / (n - 1)
        for sid in ordered[start:end]:
            result[sid] = score
        start = end
    return result


def fuse(text, image, mode, alpha, top_k, threshold):
    if mode not in {'text', 'image', 'multimodal'}:
        raise ValueError(mode)
    t, i = rank_scale(text), rank_scale(image)
    if mode == 'text':
        wt, wi = 1.0, 0.0
    elif mode == 'image':
        wt, wi = 0.0, 1.0
    else:
        wt, wi = (alpha if t else 0.0), (1-alpha if i else 0.0)
        total = wt + wi
        if total:
            wt, wi = wt/total, wi/total
    ids = (set(t) if wt else set()) | (set(i) if wi else set())
    rows = []
    for sid in ids:
        score = wt*t.get(sid, 0.0) + wi*i.get(sid, 0.0)
        rows.append(dict(symbol_id=sid, raw_text_score=text.get(sid),
                         raw_image_cosine=image.get(sid), text_score=t.get(sid),
                         image_score=i.get(sid), fusion_score=score,
                         text_available=sid in t, image_available=sid in i,
                         effective_text_weight=wt, effective_image_weight=wi))
    rows.sort(key=lambda r: (-r['fusion_score'], r['symbol_id']))
    return [r for r in rows if r['fusion_score'] >= threshold][:top_k]
