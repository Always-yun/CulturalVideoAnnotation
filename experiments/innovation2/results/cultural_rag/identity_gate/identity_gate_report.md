# Identity Evidence Gate evaluation report

## Protocol

The proposed gate was implemented in `src/knowledge/identity_evidence_gate.py` and integrated after `RejectionGate` in `src/pipeline/cultural_rag.py`. This evaluation is an offline replay of the 20 saved `gate_on_final` `multimodal_controlled` outputs. It does not call a VLM, CLIP encoder, retriever, or video input; the only changed decision is the deterministic candidate identity gate. The original `gate_on_final` artefacts remain unchanged.

The v1 rule was selected without test tuning: accept a candidate only at `strong` level—complete canonical/alias mention in the scene description without a conflicting explicit focus entity, or an exact existing KB unique-attribute match. OCR and reference-image evidence are `unavailable`; image/fusion score is not used as identity evidence.

## Validation check

GT candidate identity evidence passed for 6/8 Known validation samples. No KB candidate passed for 3/3 validation unknown samples. This is a rule-coverage check, not a model-prediction metric.

## Test metrics

| Version | Known Symbol Accuracy | Known Accept Rate | Unknown Rejection Rate | Hard Unknown Rejection Rate | Hallucination Rate | Known False Rejection Rate |
|---|---:|---:|---:|---:|---:|---:|
| Baseline: Existing Confidence Gate | 64.71% | 64.71% | 33.33% | 33.33% | 0.00% | 35.29% |
| Proposed: Existing Gate + Identity Evidence Gate | 58.82% | 58.82% | 100.00% | 100.00% | 0.00% | 41.18% |

## Hard Unknown cases

| Video | Top-1 candidate | Fusion | Existing Gate | Identity level (Top-1) | Proposed result | Reason |
|---|---|---:|---|---|---|---|
| 神武门 | 故宫 | 0.8124 | confident / rejected=False | weak | rejected=True | Existing Gate passed, but no candidate has strong identity evidence. |
  - Category evidence: `dimension=ANCIENT; type=皇家宫殿建筑群`. Identity evidence: canonical=False, alias=False, weak_mentions=['故宫', '故宫博物院'], unique_attribute=False, OCR=unavailable, reference image=unavailable.
| 中关村国际创新中心 | 中关村 | 0.8085 | confident / rejected=False | weak | rejected=True | Existing Gate passed, but no candidate has strong identity evidence. |
  - Category evidence: `dimension=TECH; type=科技街区与地标`. Identity evidence: canonical=False, alias=False, weak_mentions=['中关村'], unique_attribute=False, OCR=unavailable, reference image=unavailable.
| 人民大会堂1 | 北京大学 | 0.3187 | insufficient / rejected=True | none | rejected=True | Existing Confidence Gate / controlled output already returned unknown_symbol. |
  - Category evidence: `dimension=TECH; type=高等学府`. Identity evidence: canonical=False, alias=False, weak_mentions=[], unique_attribute=False, OCR=unavailable, reference image=unavailable.

## Known false rejections

Proposed gate rejects 7/17 Known samples. 1 are newly rejected by the identity layer; the remainder were already rejected by the existing system.

- **京剧青衣**: Existing Gate already rejected; Identity Gate does not recover rejected samples.
- **庙会**: Existing Gate already rejected; Identity Gate does not recover rejected samples.
- **未来科学城**: Existing Gate already rejected; Identity Gate does not recover rejected samples.
- **中关村1号**: New Identity Gate rejection: Existing Gate passed, but no candidate has strong identity evidence.
- **北大**: Existing Gate already rejected; Identity Gate does not recover rejected samples.
- **北大1**: Existing Gate already rejected; Identity Gate does not recover rejected samples.
- **cbd1**: Existing Gate already rejected; Identity Gate does not recover rejected samples.

## Interpretation

The replay directly tests the separation between candidate relevance and candidate identity. A high fusion score can be retained as category/retrieval evidence while the candidate is rejected when its name is only a parent-context or a prefix of another explicit entity. The remaining false rejection cases identify missing aliases, missing scene name evidence, or KB granularity limits; they must not be silently converted into KB additions during this rejection experiment.
