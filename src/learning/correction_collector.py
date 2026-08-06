"""
修正数据收集模块
负责收集、分析和存储人工修改的标注数据
"""

import os
import json
import re
import difflib
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
import hashlib


@dataclass
class CorrectionCase:
    """修正案例数据结构"""
    case_id: str  # 唯一标识
    video_path: str  # 视频路径
    scene_category: str  # 场景分类
    
    # 原始标注
    original_annotation: str
    
    # 人工修改后的标注
    corrected_annotation: str
    
    # 差异分析结果
    differences: List[Dict[str, Any]]
    
    # 修改原因（人工标注）
    correction_reason: Optional[str] = None
    
    # 元数据
    timestamp: str = None
    annotator: str = None
    video_metadata: Dict[str, Any] = None
    
    # 提取的关键帧描述（用于检索）
    key_frame_description: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()


class CorrectionCollector:
    """修正数据收集器"""
    
    def __init__(self, config):
        """
        初始化收集器
        
        Args:
            config: LearningConfig 配置对象
        """
        self.config = config
        self.corrections_dir = config.corrections_dir
        os.makedirs(self.corrections_dir, exist_ok=True)
    
    def collect_correction(
        self,
        video_path: str,
        original_annotation: str,
        corrected_annotation: str,
        scene_category: str = "",
        correction_reason: str = None,
        annotator: str = None,
        video_metadata: Dict[str, Any] = None,
        key_frame_description: str = None
    ) -> CorrectionCase:
        """
        收集一个修正案例
        
        Args:
            video_path: 视频文件路径
            original_annotation: 模型原始标注
            corrected_annotation: 人工修改后的标注
            scene_category: 场景分类
            correction_reason: 修改原因说明
            annotator: 标注员标识
            video_metadata: 视频元数据
            key_frame_description: 关键帧描述
            
        Returns:
            CorrectionCase 对象
        """
        # 生成唯一ID
        case_id = self._generate_case_id(video_path, original_annotation, corrected_annotation)
        
        # 分析差异
        differences = self._analyze_differences(original_annotation, corrected_annotation)
        
        # 如果没有提供场景分类，尝试自动检测
        if not scene_category:
            scene_category = self._detect_scene_category(corrected_annotation)
        
        # 创建修正案例
        case = CorrectionCase(
            case_id=case_id,
            video_path=video_path,
            scene_category=scene_category,
            original_annotation=original_annotation,
            corrected_annotation=corrected_annotation,
            differences=differences,
            correction_reason=correction_reason,
            annotator=annotator,
            video_metadata=video_metadata or {},
            key_frame_description=key_frame_description
        )
        
        # 保存到文件
        self._save_correction(case)
        
        return case
    
    def _generate_case_id(self, video_path: str, original: str, corrected: str) -> str:
        """生成唯一案例ID"""
        content = f"{video_path}_{original}_{corrected}_{datetime.now().isoformat()}"
        return hashlib.md5(content.encode()).hexdigest()[:12]
    
    def _analyze_differences(self, original: str, corrected: str) -> List[Dict[str, Any]]:
        """
        分析原始标注和修改后标注的差异
        
        Returns:
            差异列表，每个差异包含：
            - type: 差异类型 (addition/deletion/modification)
            - original: 原始内容
            - corrected: 修改后内容
            - position: 位置信息
            - category: 差异类别（术语/格式/内容）
        """
        differences = []
        
        # 按行分割
        original_lines = original.split('\n')
        corrected_lines = corrected.split('\n')
        
        # 使用 difflib 进行差异分析
        diff = difflib.unified_diff(
            original_lines, 
            corrected_lines,
            lineterm=''
        )
        
        # 解析差异
        current_diff = None
        for line in diff:
            if line.startswith('@@'):
                if current_diff:
                    differences.append(current_diff)
                current_diff = {
                    'type': 'modification',
                    'original': '',
                    'corrected': '',
                    'position': line,
                    'category': 'unknown'
                }
            elif line.startswith('-') and not line.startswith('---'):
                if current_diff:
                    current_diff['original'] += line[1:] + '\n'
            elif line.startswith('+') and not line.startswith('+++'):
                if current_diff:
                    current_diff['corrected'] += line[1:] + '\n'
        
        if current_diff and (current_diff['original'] or current_diff['corrected']):
            differences.append(current_diff)
        
        # 对差异进行分类
        for diff in differences:
            diff['category'] = self._classify_difference(diff)
        
        # 过滤无效差异
        differences = [d for d in differences if self._is_valid_difference(d)]
        
        return differences
    
    def _classify_difference(self, diff: Dict[str, Any]) -> str:
        """
        对差异进行分类
        
        类别：
        - terminology: 术语修正（专业词汇替换）
        - format: 格式调整（换行、标点、结构）
        - content: 内容补充（新增信息）
        - correction: 错误修正（事实性错误）
        """
        original = diff.get('original', '').strip()
        corrected = diff.get('corrected', '').strip()
        
        # 检测术语修正
        terminology_patterns = [
            r'古建筑|现代建筑|传统建筑',
            r'古都文化|红色文化|京味文化|创新科技文化|国际时尚文化',
            r'镜头|机位|景别|构图|光影'
        ]
        
        for pattern in terminology_patterns:
            if re.search(pattern, original) or re.search(pattern, corrected):
                return 'terminology'
        
        # 检测格式调整
        if len(original) < 10 and len(corrected) < 10:
            return 'format'
        
        if re.match(r'^[\s\p{P}]+$', original) or re.match(r'^[\s\p{P}]+$', corrected):
            return 'format'
        
        # 检测内容补充
        if len(corrected) > len(original) * 1.5:
            return 'content'
        
        # 默认为错误修正
        return 'correction'
    
    def _is_valid_difference(self, diff: Dict[str, Any]) -> bool:
        """检查差异是否有效（值得学习）"""
        original = diff.get('original', '').strip()
        corrected = diff.get('corrected', '').strip()
        
        # 忽略纯空白差异
        if not original and not corrected:
            return False
        
        # 忽略过短的差异
        min_len = self.config.diff_min_length
        if len(original) < min_len and len(corrected) < min_len:
            return False
        
        # 检查忽略模式
        for pattern in self.config.ignore_patterns:
            if re.match(pattern, original) and re.match(pattern, corrected):
                return False
        
        return True
    
    def _detect_scene_category(self, text: str) -> str:
        """从文本中检测场景分类"""
        category_keywords = {
            "古都文化": ["故宫", "中轴线", "钟鼓楼", "长城", "皇城", "天坛", "颐和园", "圆明园", "历史"],
            "红色文化": ["天安门", "革命", "国家庆典", "博物馆"],
            "京味文化": ["胡同", "老字号", "京剧", "相声", "非遗", "民俗"],
            "创新科技文化": ["中关村", "科技", "创新", "大兴机场", "自动驾驶", "数字"],
            "国际时尚文化": ["三里屯", "亮马河", "使馆区", "外交", "国际"]
        }
        
        for category, keywords in category_keywords.items():
            for keyword in keywords:
                if keyword in text:
                    return category
        
        return "未分类"
    
    def _save_correction(self, case: CorrectionCase):
        """保存修正案例到文件"""
        filename = f"correction_{case.case_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(self.corrections_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(asdict(case), f, ensure_ascii=False, indent=2)
        
        print(f"修正案例已保存: {filepath}")
    
    def load_corrections(self) -> List[CorrectionCase]:
        """加载所有修正案例"""
        cases = []
        
        for filename in os.listdir(self.corrections_dir):
            if filename.startswith('correction_') and filename.endswith('.json'):
                filepath = os.path.join(self.corrections_dir, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    cases.append(CorrectionCase(**data))
        
        return cases
    
    def get_correction_summary(self) -> Dict[str, Any]:
        """获取修正数据统计摘要"""
        cases = self.load_corrections()
        
        summary = {
            'total_cases': len(cases),
            'by_category': {},
            'by_diff_type': {},
            'recent_cases': []
        }
        
        for case in cases:
            # 按场景分类统计
            cat = case.scene_category
            summary['by_category'][cat] = summary['by_category'].get(cat, 0) + 1
            
            # 按差异类型统计
            for diff in case.differences:
                diff_type = diff.get('category', 'unknown')
                summary['by_diff_type'][diff_type] = summary['by_diff_type'].get(diff_type, 0) + 1
        
        # 最近案例
        sorted_cases = sorted(cases, key=lambda x: x.timestamp, reverse=True)
        summary['recent_cases'] = [
            {
                'case_id': c.case_id,
                'video_path': c.video_path,
                'scene_category': c.scene_category,
                'timestamp': c.timestamp
            }
            for c in sorted_cases[:5]
        ]
        
        return summary
    
    def export_for_training(self, output_path: str = None) -> str:
        """
        导出训练数据格式
        
        Returns:
            导出文件路径
        """
        cases = self.load_corrections()
        
        training_data = []
        for case in cases:
            training_data.append({
                'input': {
                    'video_path': case.video_path,
                    'scene_category': case.scene_category,
                    'original_annotation': case.original_annotation,
                    'key_frame_description': case.key_frame_description
                },
                'output': case.corrected_annotation,
                'metadata': {
                    'differences': case.differences,
                    'correction_reason': case.correction_reason,
                    'annotator': case.annotator
                }
            })
        
        if output_path is None:
            output_path = os.path.join(self.corrections_dir, 'training_data.json')
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(training_data, f, ensure_ascii=False, indent=2)
        
        print(f"训练数据已导出: {output_path}")
        return output_path