"""
EMCAST Baseline 对比实验评估主程序
负责：
1. 读取输入数据（jsonl/csv）
2. 计算所有指标（文化符号P/R/F1、结构准确率、BLEU、CIDEr、ROUGE）
3. 生成对比表格（DataFrame + CSV + Markdown）
4. 输出结果摘要
"""

import os
import json
import pandas as pd
import numpy as np
from typing import Dict, List, Any

from .cultural_metrics import (
    compute_cultural_accuracy, extract_cultural_symbols, extract_cultural_category,
    compute_precision_recall_f1, compute_structural_accuracy
)
from .text_metrics import compute_text_metrics


class BaselineEvaluator:
    """
    Baseline对比实验评估器
    
    支持的方法：
    - GPT (gpt_output)
    - Prompt (prompt_output)
    - EMCAST (emcast_output)
    
    评估指标：
    - 文化符号：Precision / Recall / F1
    - 结构指标：Structural Accuracy, Layer Completeness, Layer Validity
    - 文本指标：BLEU-1/2/3/4, CIDEr, ROUGE-1/2/L
    """
    
    METHODS = {
        "gpt": {"name": "GPT", "column": "gpt_output"},
        "prompt": {"name": "Prompt", "column": "prompt_output"},
        "emcast": {"name": "EMCAST", "column": "emcast_output"},
    }
    
    def __init__(self, data_path: str, output_dir: str = "outputs/eval"):
        """
        初始化评估器
        
        Args:
            data_path: 输入数据文件路径（jsonl或csv）
            output_dir: 输出目录
        """
        self.data_path = data_path
        self.output_dir = output_dir
        self.data = []
        self.results = []
        self.summary_df = None
        
        os.makedirs(output_dir, exist_ok=True)
    
    def load_data(self) -> List[Dict[str, Any]]:
        """
        加载输入数据
        
        Returns:
            数据列表
        """
        ext = os.path.splitext(self.data_path)[1].lower()
        
        if ext == ".jsonl":
            self.data = self._load_jsonl(self.data_path)
        elif ext in [".csv", ".tsv"]:
            self.data = self._load_csv(self.data_path)
        else:
            raise ValueError(f"不支持的文件格式: {ext}")
        
        print(f"加载了 {len(self.data)} 条数据")
        return self.data
    
    def _load_jsonl(self, path: str) -> List[Dict[str, Any]]:
        """加载jsonl格式数据"""
        data = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    data.append(json.loads(line))
        return data
    
    def _load_csv(self, path: str) -> List[Dict[str, Any]]:
        """加载csv格式数据"""
        df = pd.read_csv(path)
        return df.to_dict("records")
    
    def evaluate_single_sample(self, sample: Dict[str, Any]) -> Dict[str, Any]:
        """
        评估单个样本
        
        Args:
            sample: 样本字典，包含 video_id, gt_emcast, gpt_output, prompt_output, emcast_output
            
        Returns:
            评估结果字典
        """
        video_id = sample.get("video_id", "")
        gt_emcast = sample.get("gt_emcast", "")
        
        results = {"video_id": video_id}
        
        for method_key, method_info in self.METHODS.items():
            method_name = method_info["name"]
            output_col = method_info["column"]
            model_output = sample.get(output_col, "")
            
            if model_output:
                cultural_acc = compute_cultural_accuracy(model_output, gt_emcast)
                text_metrics = compute_text_metrics(model_output, [gt_emcast])
                
                results.update({
                    f"{method_key}_category_match": cultural_acc["category_match"],
                    f"{method_key}_symbol_precision": cultural_acc["symbol_precision"],
                    f"{method_key}_symbol_recall": cultural_acc["symbol_recall"],
                    f"{method_key}_symbol_f1": cultural_acc["symbol_f1"],
                    f"{method_key}_structural_accuracy": cultural_acc["structural_accuracy"],
                    f"{method_key}_layer_completeness": cultural_acc["layer_completeness"],
                    f"{method_key}_layer_validity": cultural_acc["layer_validity"],
                    f"{method_key}_layer_consistency": cultural_acc["layer_consistency"],
                    f"{method_key}_bleu1": text_metrics["bleu1"],
                    f"{method_key}_bleu2": text_metrics["bleu2"],
                    f"{method_key}_bleu3": text_metrics["bleu3"],
                    f"{method_key}_bleu4": text_metrics["bleu4"],
                    f"{method_key}_cider": text_metrics["cider"],
                    f"{method_key}_rouge1_f1": text_metrics["rouge1_f1"],
                    f"{method_key}_rouge2_f1": text_metrics["rouge2_f1"],
                    f"{method_key}_rougel_f1": text_metrics["rougel_f1"],
                })
            else:
                for metric in [
                    "category_match", "symbol_precision", "symbol_recall", "symbol_f1",
                    "structural_accuracy", "layer_completeness", "layer_validity", "layer_consistency",
                    "bleu1", "bleu2", "bleu3", "bleu4", "cider", "rouge1_f1", "rouge2_f1", "rougel_f1"
                ]:
                    results[f"{method_key}_{metric}"] = np.nan
        
        return results
    
    def evaluate_all(self) -> pd.DataFrame:
        """
        评估所有样本
        
        Returns:
            评估结果DataFrame
        """
        if not self.data:
            self.load_data()
        
        print("开始评估...")
        for i, sample in enumerate(self.data):
            if (i + 1) % 10 == 0:
                print(f"已评估 {i + 1}/{len(self.data)} 条")
            result = self.evaluate_single_sample(sample)
            self.results.append(result)
        
        df = pd.DataFrame(self.results)
        print("评估完成")
        return df
    
    def compute_summary(self, df: pd.DataFrame = None) -> pd.DataFrame:
        """
        计算汇总统计（均值 + 标准差）
        
        Args:
            df: 评估结果DataFrame
            
        Returns:
            汇总DataFrame
        """
        if df is None:
            df = pd.DataFrame(self.results)
        
        summary_rows = []
        
        for method_key, method_info in self.METHODS.items():
            method_name = method_info["name"]
            
            metrics = [
                "category_match", "symbol_precision", "symbol_recall", "symbol_f1",
                "structural_accuracy", "layer_completeness", "layer_validity", "layer_consistency",
                "bleu1", "bleu2", "bleu3", "bleu4", "cider", "rouge1_f1", "rouge2_f1", "rougel_f1"
            ]
            
            row = {"Method": method_name}
            
            for metric in metrics:
                col_name = f"{method_key}_{metric}"
                if col_name in df.columns:
                    values = df[col_name].dropna()
                    if len(values) > 0:
                        mean_val = values.mean()
                        std_val = values.std()
                        row[f"{metric}_mean"] = mean_val
                        row[f"{metric}_std"] = std_val
                    else:
                        row[f"{metric}_mean"] = np.nan
                        row[f"{metric}_std"] = np.nan
            
            summary_rows.append(row)
        
        self.summary_df = pd.DataFrame(summary_rows)
        return self.summary_df
    
    def save_results(self, df: pd.DataFrame, summary_df: pd.DataFrame = None):
        """
        保存评估结果
        
        Args:
            df: 详细评估结果DataFrame
            summary_df: 汇总结果DataFrame
        """
        result_csv_path = os.path.join(self.output_dir, "result.csv")
        df.to_csv(result_csv_path, index=False, encoding="utf-8-sig")
        print(f"详细结果已保存: {result_csv_path}")
        
        if summary_df is None:
            summary_df = self.summary_df
        
        summary_csv_path = os.path.join(self.output_dir, "result_summary.csv")
        summary_df.to_csv(summary_csv_path, index=False, encoding="utf-8-sig")
        print(f"汇总结果已保存: {summary_csv_path}")
        
        markdown_path = os.path.join(self.output_dir, "result_summary.md")
        self._generate_markdown(summary_df, markdown_path)
        print(f"Markdown报告已保存: {markdown_path}")
    
    def _generate_markdown(self, summary_df: pd.DataFrame, path: str):
        """
        生成Markdown格式的结果报告
        
        Args:
            summary_df: 汇总结果DataFrame
            path: 输出路径
        """
        metric_groups = [
            {
                "name": "文化符号指标",
                "metrics": [
                    ("category_match", "文化分类匹配"),
                    ("symbol_precision", "符号Precision"),
                    ("symbol_recall", "符号Recall"),
                    ("symbol_f1", "符号F1"),
                ]
            },
            {
                "name": "结构指标",
                "metrics": [
                    ("structural_accuracy", "结构准确率"),
                    ("layer_completeness", "层级完整性"),
                    ("layer_validity", "层级规范性"),
                    ("layer_consistency", "层级一致性"),
                ]
            },
            {
                "name": "文本生成指标",
                "metrics": [
                    ("bleu1", "BLEU-1"),
                    ("bleu2", "BLEU-2"),
                    ("bleu3", "BLEU-3"),
                    ("bleu4", "BLEU-4"),
                    ("cider", "CIDEr"),
                    ("rouge1_f1", "ROUGE-1"),
                    ("rouge2_f1", "ROUGE-2"),
                    ("rougel_f1", "ROUGE-L"),
                ]
            }
        ]
        
        with open(path, "w", encoding="utf-8") as f:
            f.write("# EMCAST Baseline 对比实验结果\n\n")
            f.write(f"评估样本数: {len(self.data)}\n\n")
            
            for group in metric_groups:
                f.write(f"## {group['name']}\n\n")
                f.write("| 方法 | " + " | ".join([m[1] for m in group["metrics"]]) + " |\n")
                f.write("|------|" + "|".join(["---" for _ in group["metrics"]]) + "|\n")
                
                for _, row in summary_df.iterrows():
                    method_name = row["Method"]
                    values = []
                    for metric_key, _ in group["metrics"]:
                        mean_val = row.get(f"{metric_key}_mean", "")
                        if pd.notna(mean_val):
                            values.append(f"{mean_val:.4f}")
                        else:
                            values.append("-")
                    f.write("| " + method_name + " | " + " | ".join(values) + " |\n")
                f.write("\n")
            
            f.write("## 指标说明\n\n")
            f.write("- **文化分类匹配**: 预测的文化分类与真实分类是否一致\n")
            f.write("- **符号Precision/Recall/F1**: 基于受控词表的文化符号匹配精度\n")
            f.write("- **结构准确率**: EMCAST六层结构的完整性与规范性综合得分\n")
            f.write("- **层级完整性**: 六层中包含有效内容的比例\n")
            f.write("- **层级规范性**: 各层内容符合格式要求的比例\n")
            f.write("- **层级一致性**: 预测与真实标注在各层的符号一致性\n")
            f.write("- **BLEU-1~4**: n-gram匹配精度\n")
            f.write("- **CIDEr**: 基于TF-IDF的句子相似度\n")
            f.write("- **ROUGE-1/2/L**: 召回导向的文本相似度\n")
    
    def run(self) -> pd.DataFrame:
        """
        完整评估流程
        
        Returns:
            汇总结果DataFrame
        """
        self.load_data()
        df = self.evaluate_all()
        summary_df = self.compute_summary(df)
        self.save_results(df, summary_df)
        
        print("\n" + "=" * 60)
        print("评估完成！")
        print("输出目录:", self.output_dir)
        print("=" * 60)
        
        return summary_df


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="EMCAST Baseline 对比实验评估")
    parser.add_argument("--data", required=True, help="输入数据文件路径（jsonl/csv）")
    parser.add_argument("--output", default="outputs/eval", help="输出目录")
    
    args = parser.parse_args()
    
    evaluator = BaselineEvaluator(args.data, args.output)
    evaluator.run()


if __name__ == "__main__":
    main()
