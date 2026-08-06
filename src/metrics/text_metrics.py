"""
文本生成评估指标
包含：
- BLEU (nltk实现，带pycocoevalcap fallback)
- CIDEr (自定义实现，带pycocoevalcap fallback)
- ROUGE (rouge-score库实现)
"""

from typing import List, Dict, Any
import numpy as np
import re

try:
    import nltk
    from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction
    from nltk.tokenize import word_tokenize
    NLTK_AVAILABLE = True
except ImportError:
    NLTK_AVAILABLE = False

try:
    from rouge_score import rouge_scorer
    ROUGE_AVAILABLE = True
except ImportError:
    ROUGE_AVAILABLE = False

try:
    from pycocoevalcap.bleu.bleu import Bleu
    from pycocoevalcap.cider.cider import Cider
    PYCOCOAVAILABLE = True
except ImportError:
    PYCOCOAVAILABLE = False


def _tokenize(text: str) -> List[str]:
    """
    中文分词处理
    
    Args:
        text: 输入文本
        
    Returns:
        分词后的词列表
    """
    if not text:
        return []
    
    text = text.strip()
    
    if NLTK_AVAILABLE:
        try:
            return word_tokenize(text)
        except:
            pass
    
    chars = []
    for char in text:
        if char.strip():
            chars.append(char)
    return chars


def compute_bleu(
    candidate: str,
    references: List[str],
    n_grams: int = 4
) -> Dict[str, float]:
    """
    计算 BLEU 分数
    
    Args:
        candidate: 候选文本（模型输出）
        references: 参考文本列表（标准答案）
        n_grams: 最大n-gram阶数
        
    Returns:
        包含各阶BLEU分数的字典
    """
    if not candidate or not references:
        result = {"bleu1": 0.0, "bleu2": 0.0, "bleu3": 0.0, "bleu4": 0.0}
        return result
    
    if PYCOCOAVAILABLE:
        return _compute_bleu_pycoco(candidate, references)
    
    return _compute_bleu_nltk(candidate, references, n_grams)


def _compute_bleu_nltk(
    candidate: str,
    references: List[str],
    n_grams: int = 4
) -> Dict[str, float]:
    """
    使用nltk计算BLEU分数
    
    Args:
        candidate: 候选文本
        references: 参考文本列表
        n_grams: 最大n-gram阶数
        
    Returns:
        BLEU分数字典
    """
    candidate_tokens = _tokenize(candidate)
    reference_tokens = [_tokenize(ref) for ref in references]
    
    smoothie = SmoothingFunction().method4
    
    result = {}
    for n in range(1, n_grams + 1):
        weights = tuple([1.0 / n] * n)
        try:
            score = sentence_bleu(
                reference_tokens,
                candidate_tokens,
                weights=weights,
                smoothing_function=smoothie
            )
        except Exception:
            score = 0.0
        result[f"bleu{n}"] = score
    
    return result


def _compute_bleu_pycoco(
    candidate: str,
    references: List[str]
) -> Dict[str, float]:
    """
    使用pycocoevalcap计算BLEU分数
    
    Args:
        candidate: 候选文本
        references: 参考文本列表
        
    Returns:
        BLEU分数字典
    """
    candidate_dict = {"0": [candidate]}
    references_dict = {"0": references}
    
    bleu_scorer = Bleu(4)
    scores, _ = bleu_scorer.compute_score(references_dict, candidate_dict)
    
    result = {}
    for i in range(4):
        result[f"bleu{i+1}"] = scores[i]
    
    return result


def compute_cider(
    candidate: str,
    references: List[str]
) -> Dict[str, float]:
    """
    计算 CIDEr 分数
    
    Args:
        candidate: 候选文本
        references: 参考文本列表
        
    Returns:
        包含CIDEr分数的字典
    """
    if not candidate or not references:
        return {"cider": 0.0}
    
    if PYCOCOAVAILABLE:
        return _compute_cider_pycoco(candidate, references)
    
    return _compute_cider_custom(candidate, references)


def _compute_cider_pycoco(
    candidate: str,
    references: List[str]
) -> Dict[str, float]:
    """
    使用pycocoevalcap计算CIDEr分数
    
    Args:
        candidate: 候选文本
        references: 参考文本列表
        
    Returns:
        CIDEr分数字典
    """
    candidate_dict = {"0": [candidate]}
    references_dict = {"0": references}
    
    cider_scorer = Cider()
    score, _ = cider_scorer.compute_score(references_dict, candidate_dict)
    
    if isinstance(score, list):
        return {"cider": score[0]}
    else:
        return {"cider": score}


def _compute_cider_custom(
    candidate: str,
    references: List[str]
) -> Dict[str, float]:
    """
    自定义CIDEr分数计算
    
    Args:
        candidate: 候选文本
        references: 参考文本列表
        
    Returns:
        CIDEr分数字典
    """
    candidate_tokens = _tokenize(candidate)
    reference_tokens_list = [_tokenize(ref) for ref in references]
    
    if len(candidate_tokens) == 0:
        return {"cider": 0.0}
    
    doc_freq = {}
    for ref_tokens in reference_tokens_list:
        unique_ngrams = set()
        for n in range(1, 5):
            for i in range(len(ref_tokens) - n + 1):
                ngram = tuple(ref_tokens[i:i+n])
                unique_ngrams.add(ngram)
        for ngram in unique_ngrams:
            doc_freq[ngram] = doc_freq.get(ngram, 0) + 1
    
    score = 0.0
    count = 0
    
    for n in range(1, 5):
        candidate_ngrams = {}
        for i in range(len(candidate_tokens) - n + 1):
            ngram = tuple(candidate_tokens[i:i+n])
            candidate_ngrams[ngram] = candidate_ngrams.get(ngram, 0) + 1
        
        for ngram, count_c in candidate_ngrams.items():
            count_ref = 0
            for ref_tokens in reference_tokens_list:
                ref_count = 0
                for i in range(len(ref_tokens) - n + 1):
                    if tuple(ref_tokens[i:i+n]) == ngram:
                        ref_count += 1
                count_ref += ref_count
            
            if count_ref > 0:
                idf = max(0, np.log((len(references) + 1) / (doc_freq.get(ngram, 0) + 0.5)))
                score += idf * (count_c * count_ref) / (count_c + count_ref)
                count += 1
    
    score = score / count if count > 0 else 0.0
    
    return {"cider": score}


def compute_rouge(
    candidate: str,
    references: List[str]
) -> Dict[str, float]:
    """
    计算 ROUGE 分数
    
    Args:
        candidate: 候选文本
        references: 参考文本列表
        
    Returns:
        包含ROUGE分数的字典
    """
    if not candidate or not references:
        return {"rouge1_f1": 0.0, "rouge2_f1": 0.0, "rougel_f1": 0.0}
    
    if ROUGE_AVAILABLE:
        return _compute_rouge_rouge_score(candidate, references)
    
    return _compute_rouge_custom(candidate, references)


def _compute_rouge_rouge_score(
    candidate: str,
    references: List[str]
) -> Dict[str, float]:
    """
    使用rouge-score库计算ROUGE分数
    
    Args:
        candidate: 候选文本
        references: 参考文本列表
        
    Returns:
        ROUGE分数字典
    """
    scorer = rouge_scorer.RougeScorer(["rouge1", "rouge2", "rougeL"])
    
    max_scores = {"rouge1": None, "rouge2": None, "rougeL": None}
    
    for ref in references:
        scores = scorer.score(ref, candidate)
        for key in ["rouge1", "rouge2", "rougeL"]:
            if max_scores[key] is None or scores[key].fmeasure > max_scores[key].fmeasure:
                max_scores[key] = scores[key]
    
    return {
        "rouge1_f1": max_scores["rouge1"].fmeasure if max_scores["rouge1"] else 0.0,
        "rouge2_f1": max_scores["rouge2"].fmeasure if max_scores["rouge2"] else 0.0,
        "rougel_f1": max_scores["rougeL"].fmeasure if max_scores["rougeL"] else 0.0,
    }


def _compute_rouge_custom(
    candidate: str,
    references: List[str]
) -> Dict[str, float]:
    """
    自定义ROUGE分数计算
    
    Args:
        candidate: 候选文本
        references: 参考文本列表
        
    Returns:
        ROUGE分数字典
    """
    candidate_tokens = _tokenize(candidate)
    
    def compute_rouge_n(n):
        max_f1 = 0.0
        
        for ref in references:
            ref_tokens = _tokenize(ref)
            
            candidate_ngrams = set()
            for i in range(len(candidate_tokens) - n + 1):
                candidate_ngrams.add(tuple(candidate_tokens[i:i+n]))
            
            ref_ngrams = set()
            for i in range(len(ref_tokens) - n + 1):
                ref_ngrams.add(tuple(ref_tokens[i:i+n]))
            
            if not candidate_ngrams or not ref_ngrams:
                continue
            
            overlap = len(candidate_ngrams & ref_ngrams)
            precision = overlap / len(candidate_ngrams)
            recall = overlap / len(ref_ngrams)
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
            
            if f1 > max_f1:
                max_f1 = f1
        
        return max_f1
    
    def compute_rouge_l():
        max_f1 = 0.0
        
        for ref in references:
            ref_tokens = _tokenize(ref)
            
            lcs_len = _lcs(candidate_tokens, ref_tokens)
            
            if lcs_len == 0:
                continue
            
            precision = lcs_len / len(candidate_tokens)
            recall = lcs_len / len(ref_tokens)
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
            
            if f1 > max_f1:
                max_f1 = f1
        
        return max_f1
    
    return {
        "rouge1_f1": compute_rouge_n(1),
        "rouge2_f1": compute_rouge_n(2),
        "rougel_f1": compute_rouge_l(),
    }


def _lcs(a: List[str], b: List[str]) -> int:
    """
    计算最长公共子序列长度
    
    Args:
        a: 序列a
        b: 序列b
        
    Returns:
        LCS长度
    """
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    
    return dp[m][n]


def compute_text_metrics(
    candidate: str,
    references: List[str]
) -> Dict[str, float]:
    """
    计算所有文本指标（BLEU + CIDEr + ROUGE）
    
    Args:
        candidate: 候选文本
        references: 参考文本列表
        
    Returns:
        包含所有文本指标的字典
    """
    bleu_scores = compute_bleu(candidate, references)
    cider_score = compute_cider(candidate, references)
    rouge_scores = compute_rouge(candidate, references)
    
    return {**bleu_scores, **cider_score, **rouge_scores}
