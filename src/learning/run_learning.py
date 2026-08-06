"""
学习流程主程序
提供完整的学习流程入口和命令行接口
"""

import os
import sys
import json
import argparse
from datetime import datetime

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .config import LearningConfig
from .correction_collector import CorrectionCollector, CorrectionCase
from .vector_store import VectorStore
from .fewshot_manager import FewShotManager


class LearningPipeline:
    """学习流程管理器"""
    
    def __init__(self, config: LearningConfig = None):
        """
        初始化学习流程
        
        Args:
            config: 学习配置，如果为 None 则使用默认配置
        """
        self.config = config or LearningConfig()
        self.correction_collector = CorrectionCollector(self.config)
        self.vector_store = VectorStore(self.config)
        self.fewshot_manager = FewShotManager(self.config, self.vector_store)
        
        # 加载基础示例
        self.fewshot_manager.load_base_examples_from_file()
    
    def collect_and_learn(
        self,
        video_path: str,
        original_annotation: str,
        corrected_annotation: str,
        correction_reason: str = None,
        annotator: str = None,
        video_metadata: dict = None
    ) -> CorrectionCase:
        """
        收集修正案例并学习
        
        Args:
            video_path: 视频路径
            original_annotation: 原始标注
            corrected_annotation: 修正后标注
            correction_reason: 修改原因
            annotator: 标注员
            video_metadata: 视频元数据
        
        Returns:
            CorrectionCase 对象
        """
        print(f"\n{'='*60}")
        print(f"开始收集修正案例: {os.path.basename(video_path)}")
        print(f"{'='*60}")
        
        # 1. 收集修正案例
        case = self.correction_collector.collect_correction(
            video_path=video_path,
            original_annotation=original_annotation,
            corrected_annotation=corrected_annotation,
            correction_reason=correction_reason,
            annotator=annotator,
            video_metadata=video_metadata
        )
        
        # 2. 添加到向量数据库
        self.vector_store.add_correction_case(
            case_id=case.case_id,
            video_path=case.video_path,
            scene_category=case.scene_category,
            original_annotation=case.original_annotation,
            corrected_annotation=case.corrected_annotation,
            differences=case.differences,
            correction_reason=case.correction_reason,
            key_frame_description=case.key_frame_description
        )
        
        print(f"\n修正案例已学习并存储:")
        print(f"  - 案例ID: {case.case_id}")
        print(f"  - 场景分类: {case.scene_category}")
        print(f"  - 差异数量: {len(case.differences)}")
        
        return case
    
    def get_enhanced_prompt(
        self,
        base_prompt: str,
        scene_category: str = None,
        video_description: str = None
    ) -> str:
        """
        获取增强后的提示词（包含 Few-shot 示例）
        
        Args:
            base_prompt: 基础提示词
            scene_category: 场景分类
            video_description: 视频描述
        
        Returns:
            增强后的提示词
        """
        if not self.config.enabled:
            return base_prompt
        
        return self.fewshot_manager.enrich_prompt_with_examples(
            base_prompt=base_prompt,
            scene_category=scene_category,
            video_description=video_description
        )
    
    def batch_import_corrections(self, corrections_dir: str = None):
        """
        批量导入修正数据
        
        Args:
            corrections_dir: 修正数据目录
        """
        if corrections_dir is None:
            corrections_dir = self.config.corrections_dir
        
        print(f"\n{'='*60}")
        print(f"批量导入修正数据: {corrections_dir}")
        print(f"{'='*60}")
        
        # 加载所有修正案例
        cases = self.correction_collector.load_corrections()
        
        # 导入到向量数据库
        self.vector_store.import_from_corrections(cases)
        
        print(f"\n批量导入完成，共 {len(cases)} 个案例")
    
    def show_stats(self):
        """显示学习系统统计信息"""
        print(f"\n{'='*60}")
        print("学习系统统计信息")
        print(f"{'='*60}")
        
        # 修正数据统计
        correction_stats = self.correction_collector.get_correction_summary()
        print(f"\n【修正数据统计】")
        print(f"  总案例数: {correction_stats['total_cases']}")
        print(f"  按场景分类:")
        for cat, count in correction_stats['by_category'].items():
            print(f"    - {cat}: {count}")
        print(f"  按差异类型:")
        for diff_type, count in correction_stats['by_diff_type'].items():
            print(f"    - {diff_type}: {count}")
        
        # 向量数据库统计
        vector_stats = self.vector_store.get_stats()
        print(f"\n【向量数据库统计】")
        print(f"  总存储数: {vector_stats['total_count']}")
        print(f"  按场景分类:")
        for cat, count in vector_stats['by_category'].items():
            print(f"    - {cat}: {count}")
        
        # Few-shot 示例统计
        fewshot_stats = self.fewshot_manager.get_example_stats()
        print(f"\n【Few-shot 示例统计】")
        print(f"  基础示例数:")
        for cat, count in fewshot_stats['base_examples_count'].items():
            print(f"    - {cat}: {count}")
        print(f"  可用修正案例数: {fewshot_stats['correction_examples_available']}")
    
    def search_examples(self, query: str, scene_category: str = None):
        """
        搜索相似示例
        
        Args:
            query: 查询文本
            scene_category: 场景分类
        """
        print(f"\n{'='*60}")
        print(f"搜索相似示例: {query}")
        print(f"{'='*60}")
        
        examples = self.fewshot_manager.get_fewshot_examples(
            scene_category=scene_category,
            video_description=query
        )
        
        if not examples:
            print("未找到相似示例")
            return
        
        print(f"\n找到 {len(examples)} 个相似示例:")
        for i, ex in enumerate(examples, 1):
            print(f"\n示例 {i}:")
            print(f"  来源: {ex.get('source', 'unknown')}")
            print(f"  场景: {ex.get('scene', 'unknown')}")
            if ex.get('distance'):
                print(f"  相似度: {1 - ex['distance']:.2f}")
            if ex.get('correction_reason'):
                print(f"  修正原因: {ex['correction_reason']}")
            print(f"  标注内容: {ex['example_annotation'][:100]}...")
    
    def export_training_data(self, output_path: str = None):
        """导出训练数据"""
        print(f"\n{'='*60}")
        print("导出训练数据")
        print(f"{'='*60}")
        
        path = self.correction_collector.export_for_training(output_path)
        print(f"\n训练数据已导出: {path}")


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(description='学习系统命令行工具')
    
    subparsers = parser.add_subparsers(dest='command', help='子命令')
    
    # collect 命令：收集单个修正案例
    collect_parser = subparsers.add_parser('collect', help='收集修正案例')
    collect_parser.add_argument('--video', required=True, help='视频路径')
    collect_parser.add_argument('--original', required=True, help='原始标注文件路径')
    collect_parser.add_argument('--corrected', required=True, help='修正后标注文件路径')
    collect_parser.add_argument('--reason', help='修改原因')
    collect_parser.add_argument('--annotator', help='标注员')
    
    # batch 命令：批量导入
    batch_parser = subparsers.add_parser('batch', help='批量导入修正数据')
    batch_parser.add_argument('--dir', help='修正数据目录')
    
    # stats 命令：显示统计
    stats_parser = subparsers.add_parser('stats', help='显示统计信息')
    
    # search 命令：搜索示例
    search_parser = subparsers.add_parser('search', help='搜索相似示例')
    search_parser.add_argument('--query', required=True, help='查询文本')
    search_parser.add_argument('--category', help='场景分类')
    
    # export 命令：导出训练数据
    export_parser = subparsers.add_parser('export', help='导出训练数据')
    export_parser.add_argument('--output', help='输出文件路径')
    
    # enable 命令：启用/禁用学习功能
    enable_parser = subparsers.add_parser('enable', help='启用学习功能')
    enable_parser.add_argument('--status', choices=['on', 'off'], default='on', help='启用状态')
    
    args = parser.parse_args()
    
    # 初始化学习流程
    config = LearningConfig()
    pipeline = LearningPipeline(config)
    
    if args.command == 'collect':
        # 读取标注文件
        with open(args.original, 'r', encoding='utf-8') as f:
            original = f.read()
        with open(args.corrected, 'r', encoding='utf-8') as f:
            corrected = f.read()
        
        pipeline.collect_and_learn(
            video_path=args.video,
            original_annotation=original,
            corrected_annotation=corrected,
            correction_reason=args.reason,
            annotator=args.annotator
        )
    
    elif args.command == 'batch':
        pipeline.batch_import_corrections(args.dir)
    
    elif args.command == 'stats':
        pipeline.show_stats()
    
    elif args.command == 'search':
        pipeline.search_examples(args.query, args.category)
    
    elif args.command == 'export':
        pipeline.export_training_data(args.output)
    
    elif args.command == 'enable':
        config.enabled = (args.status == 'on')
        print(f"学习功能已{'启用' if config.enabled else '禁用'}")
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()