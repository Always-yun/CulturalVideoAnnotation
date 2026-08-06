"""
文化维度评估指标
包含：
- C层文化符号提取与匹配
- Precision/Recall/F1 计算
- Structural Accuracy（EMCAST六层完整性）
"""

from typing import List, Set, Dict, Tuple
import re
from .emcast_schema import (
    CULTURAL_CATEGORIES, CULTURAL_SYMBOLS, VISUAL_SYMBOLS,
    EMCAST_LAYERS, EMCAST_LAYER_KEYS, parse_emcast_format
)


def extract_cultural_symbols(text: str, category: str = None) -> Set[str]:
    """
    从文本中提取文化符号（基于受控词表匹配）
    
    Args:
        text: 输入文本
        category: 文化分类（可选，用于限定匹配范围）
        
    Returns:
        匹配到的文化符号集合
    """
    symbols = set()
    
    if not text:
        return symbols
    
    text_lower = text.lower()
    
    if category and category in CULTURAL_SYMBOLS:
        target_symbols = CULTURAL_SYMBOLS[category]
    else:
        target_symbols = []
        for cat_symbols in CULTURAL_SYMBOLS.values():
            target_symbols.extend(cat_symbols)
    
    for symbol in target_symbols:
        if symbol.lower() in text_lower:
            symbols.add(symbol)
    
    for symbol in VISUAL_SYMBOLS:
        if symbol.lower() in text_lower:
            symbols.add(symbol)
    
    return symbols


def extract_cultural_category(text: str) -> str:
    """
    从文本中提取文化分类
    
    Args:
        text: 输入文本
        
    Returns:
        匹配到的文化分类，未匹配返回空字符串
    """
    if not text:
        return ""
    
    text_lower = text.lower()
    
    for category in CULTURAL_CATEGORIES:
        if category.lower() in text_lower:
            return category
    
    return ""


def compute_precision_recall_f1(
    predicted: Set[str],
    ground_truth: Set[str]
) -> Dict[str, float]:
    """
    计算 Precision、Recall、F1 指标
    
    Args:
        predicted: 预测的符号集合
        ground_truth: 真实的符号集合
        
    Returns:
        包含 precision, recall, f1 的字典
    """
    predicted = set(predicted)
    ground_truth = set(ground_truth)
    
    if not predicted and not ground_truth:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    
    if not predicted:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    
    if not ground_truth:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    
    intersection = predicted & ground_truth
    tp = len(intersection)
    fp = len(predicted - ground_truth)
    fn = len(ground_truth - predicted)
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    
    return {"precision": precision, "recall": recall, "f1": f1}


def compute_structural_accuracy(
    predicted_text: str,
    ground_truth_text: str = None
) -> Dict[str, float]:
    """
    计算 EMCAST 结构化准确率
    
    包含两个维度：
    1. 层级完整性：六层结构是否都有内容
    2. 层级规范性：各层内容是否符合规范格式
    
    Args:
        predicted_text: 预测的EMCAST格式文本
        ground_truth_text: 真实的EMCAST格式文本（可选，用于计算一致性）
        
    Returns:
        包含 structural_accuracy, layer_completeness, layer_validity 的字典
    """
    predicted_parsed = parse_emcast_format(predicted_text)
    
    layer_completeness = 0.0
    layer_validity = 0.0
    valid_count = 0
    
    for layer_code, layer_name, _ in EMCAST_LAYERS:
        content = predicted_parsed.get(layer_code, "")
        if content and content.strip():
            layer_completeness += 1
            if len(content.strip()) >= 5:
                valid_count += 1
    
    layer_completeness /= len(EMCAST_LAYERS)
    layer_validity = valid_count / len(EMCAST_LAYERS)
    
    structural_accuracy = (layer_completeness + layer_validity) / 2.0
    
    if ground_truth_text:
        ground_truth_parsed = parse_emcast_format(ground_truth_text)
        layer_consistency = 0.0
        
        for layer_code in [l[0] for l in EMCAST_LAYERS]:
            pred_content = predicted_parsed.get(layer_code, "").strip()
            gt_content = ground_truth_parsed.get(layer_code, "").strip()
            
            if pred_content and gt_content:
                pred_symbols = extract_cultural_symbols(pred_content)
                gt_symbols = extract_cultural_symbols(gt_content)
                if pred_symbols or gt_symbols:
                    f1 = compute_precision_recall_f1(pred_symbols, gt_symbols)["f1"]
                    layer_consistency += f1
        
        layer_consistency /= len(EMCAST_LAYERS)
    else:
        layer_consistency = None
    
    result = {
        "structural_accuracy": structural_accuracy,
        "layer_completeness": layer_completeness,
        "layer_validity": layer_validity,
    }
    
    if layer_consistency is not None:
        result["layer_consistency"] = layer_consistency
    
    return result


def compute_cultural_accuracy(
    predicted_text: str,
    ground_truth_text: str
) -> Dict[str, float]:
    """
    计算文化维度综合准确率
    
    Args:
        predicted_text: 预测的EMCAST格式文本
        ground_truth_text: 真实的EMCAST格式文本
        
    Returns:
        包含各项文化指标的字典
    """
    pred_category = extract_cultural_category(predicted_text)
    gt_category = extract_cultural_category(ground_truth_text)
    
    category_match = 1.0 if pred_category == gt_category else 0.0
    
    pred_symbols = extract_cultural_symbols(predicted_text, pred_category)
    gt_symbols = extract_cultural_symbols(ground_truth_text, gt_category)
    
    prf = compute_precision_recall_f1(pred_symbols, gt_symbols)
    
    structural = compute_structural_accuracy(predicted_text, ground_truth_text)
    
    return {
        "category_match": category_match,
        "symbol_precision": prf["precision"],
        "symbol_recall": prf["recall"],
        "symbol_f1": prf["f1"],
        "structural_accuracy": structural["structural_accuracy"],
        "layer_completeness": structural["layer_completeness"],
        "layer_validity": structural["layer_validity"],
        "layer_consistency": structural.get("layer_consistency", 0.0),
    }
