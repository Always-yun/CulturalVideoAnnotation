"""
Few-shot 示例管理模块
负责管理和构建 Few-shot 学习示例
"""

import os
import json
from typing import Dict, List, Optional, Any
from datetime import datetime


class FewShotManager:
    """Few-shot 示例管理器"""
    
    def __init__(self, config, vector_store=None):
        """
        初始化 Few-shot 管理器
        
        Args:
            config: LearningConfig 配置对象
            vector_store: VectorStore 向量数据库实例
        """
        self.config = config
        self.vector_store = vector_store
        self.max_examples = config.max_examples_per_query
        self.min_similarity = config.min_similarity_score
        
        # 预定义的高质量示例模板（作为基础示例）
        self._base_examples = self._load_base_examples()
    
    def _load_base_examples(self) -> Dict[str, List[Dict]]:
        """加载预定义的基础示例"""
        base_examples = {
            "古都文化": [
                {
                    "scene": "故宫博物院",
                    "example_annotation": """【E｜场景环境层】：视频构建了一个故宫博物院太和殿广场的物理环境。此时处于白天，天气晴朗。整体场景呈现出庄严、肃穆、历史厚重的感官基调。

【M｜主体行为层】：视觉焦点包含承载主体：太和殿
承载主体外观：太和殿呈现出中国传统宫殿建筑的典型特征，重檐庑殿顶，黄色琉璃瓦覆盖，檐角装饰有仙人走兽。外立面材质主要为朱红色宫墙与汉白玉基座相结合，展现出皇家建筑的尊贵气质。
若画面涉及文字，文字符号：无

【C｜文化维度层】：该场景隶属于古都文化。
核心符号：识别出承载该文化内涵的关键视觉锚点为黄色琉璃瓦、朱红宫墙、汉白玉栏杆、飞檐斗拱。
价值指向：场景表达了明清皇家建筑的恢宏气势与中华传统建筑艺术的精髓。

【A｜视听语言层】
镜头语法：镜头为固定机位，状态稳定，节奏缓慢，以全景为主，景深深，视觉重心位于画面中央的主体建筑。
构图遵循中轴线对称，光影特征呈现为自然漫射光，视觉色彩倾向于暖调与高饱和。

【S｜整体叙事层】：视频通过稳定的全景视角展现了故宫太和殿的宏伟外观，中轴线对称构图强化了皇家建筑的庄严秩序感，朱红与金黄的色彩组合传递出深厚的历史文化底蕴。"""
                }
            ],
            "京味文化": [
                {
                    "scene": "胡同",
                    "example_annotation": """【E｜场景环境层】：视频构建了一个北京胡同巷道的物理环境。此时处于白天，天气晴朗。整体场景呈现出宁静、质朴、生活化的感官基调。

【M｜主体行为层】：视觉焦点包含承载主体：胡同两侧传统民居建筑
承载主体外观：左侧民居呈现出青砖灰瓦的传统北京四合院建筑风格，外立面材质主要为青砖墙面与木质门窗；右侧民居同样为青砖灰瓦结构，门楼上方可见传统门楣装饰。
若画面涉及文字，文字符号：无

【C｜文化维度层】：该场景隶属于京味文化。
核心符号：识别出承载该文化内涵的关键视觉锚点为青砖灰瓦、四合院格局、传统门楼。
价值指向：场景表达了老北京传统居住文化的烟火气息与市井生活韵味。

【A｜视听语言层】
镜头语法：镜头为缓慢平移机位，状态稳定，节奏缓慢，以中景为主，景深深，视觉重心沿胡同纵深方向移动。
构图遵循几何引导线，光影特征呈现为自然漫射光，视觉色彩倾向于低饱和与冷调。

【S｜整体叙事层】：视频通过缓慢的平移镜头展现了胡同的空间纵深，青砖灰瓦的建筑肌理传递出老北京的传统居住风貌，狭窄的巷道空间营造出亲切的邻里生活氛围。"""
                }
            ],
            "创新科技文化": [
                {
                    "scene": "中关村论坛",
                    "example_annotation": """【E｜场景环境层】：视频构建了一个中关村国际创新中心会议厅的物理环境。此时处于白天，室内照明充足。整体场景呈现出现代、专业、科技感的感官基调。

【M｜主体行为层】：视觉焦点包含承载主体：中关村论坛主会场建筑
承载主体外观：主体建筑呈现出极具张力的流线型现代主义风格，巨大的白色曲面屋顶呈波浪状向外大幅延伸覆盖入口上方，外立面材质主要为大面积通透的玻璃幕墙与白色金属板结合，展现出轻盈而坚固的科技质感。
若画面涉及文字，文字符号：["WELCOME TO 2025 ZGC FORUM"]

【C｜文化维度层】：该场景隶属于创新科技文化。
核心符号：识别出承载该文化内涵的关键视觉锚点为流线型穹顶结构、ZGC FORUM 英文标识、玻璃幕墙。
价值指向：场景表达了面向未来的科技创新与国际交流的时代精神。

【A｜视听语言层】
镜头语法：镜头为固定机位，状态稳定，节奏缓慢，以全景为主，景深深，视觉重心位于右侧的主体建筑入口区域。
构图遵循三分法与几何引导线，光影特征呈现为自然漫射光，视觉色彩倾向于冷调与高亮。

【S｜整体叙事层】：视频通过稳定的广角视角确立了中关村论坛会场的宏大外观与空间开阔感，明亮的天空与洁白的建筑线条共同构建了清爽的视觉基调，整体叙事强调了这一科技地标作为高端交流枢纽的功能性与开放性。"""
                }
            ]
        }
        
        return base_examples
    
    def get_fewshot_examples(
        self,
        scene_category: str = None,
        video_description: str = None,
        include_base_examples: bool = True
    ) -> List[Dict[str, Any]]:
        """
        获取 Few-shot 示例
        
        Args:
            scene_category: 场景分类
            video_description: 视频描述（用于相似性检索）
            include_base_examples: 是否包含基础示例
        
        Returns:
            Few-shot 示例列表
        """
        examples = []
        
        # 1. 从向量数据库检索相似案例
        if self.vector_store and video_description:
            similar_cases = self.vector_store.search_similar_cases(
                query=video_description,
                scene_category=scene_category,
                n_results=self.max_examples,
                min_distance=1 - self.min_similarity  # 转换距离阈值
            )
            
            for case in similar_cases:
                metadata = case.get('metadata', {})
                example = {
                    'source': 'correction',
                    'case_id': case.get('case_id'),
                    'scene': metadata.get('scene_category', ''),
                    'original': metadata.get('original_annotation', ''),
                    'corrected': metadata.get('corrected_annotation', ''),
                    'correction_reason': metadata.get('correction_reason', ''),
                    'distance': case.get('distance', 0)
                }
                
                # 使用修正后的标注作为示例
                if example['corrected']:
                    example['example_annotation'] = example['corrected']
                    examples.append(example)
        
        # 2. 添加基础示例（如果需要且数量不足）
        if include_base_examples and len(examples) < self.max_examples:
            if scene_category and scene_category in self._base_examples:
                base_list = self._base_examples[scene_category]
                for base_ex in base_list[:self.max_examples - len(examples)]:
                    examples.append({
                        'source': 'base',
                        'scene': base_ex['scene'],
                        'example_annotation': base_ex['example_annotation']
                    })
        
        return examples[:self.max_examples]
    
    def build_fewshot_prompt(
        self,
        examples: List[Dict[str, Any]],
        show_corrections: bool = True
    ) -> str:
        """
        构建 Few-shot 提示词部分
        
        Args:
            examples: Few-shot 示例列表
            show_corrections: 是否显示修正过程
        
        Returns:
            Few-shot 提示词文本
        """
        if not examples:
            return ""
        
        prompt_parts = ["\n============================================================"]
        prompt_parts.append("【参考示例】以下是相似场景的高质量标注示例，请参考其风格与规范：")
        prompt_parts.append("============================================================\n")
        
        for i, example in enumerate(examples, 1):
            prompt_parts.append(f"示例 {i}：{example.get('scene', '未知场景')}")
            
            # 如果是修正案例，可以展示修正过程
            if show_corrections and example.get('source') == 'correction':
                if example.get('correction_reason'):
                    prompt_parts.append(f"（修正原因：{example['correction_reason']}）")
                
                # 可选：展示原始标注的问题
                if example.get('original') and example.get('corrected'):
                    prompt_parts.append("\n【需避免的问题示例】：")
                    prompt_parts.append(example['original'][:300] + "...")
                    prompt_parts.append("\n【正确标注示例】：")
            
            prompt_parts.append(example['example_annotation'])
            prompt_parts.append("\n" + "-" * 60 + "\n")
        
        return "\n".join(prompt_parts)
    
    def enrich_prompt_with_examples(
        self,
        base_prompt: str,
        scene_category: str = None,
        video_description: str = None,
        position: str = "before_template"
    ) -> str:
        """
        将 Few-shot 示例融入基础提示词
        
        Args:
            base_prompt: 原始提示词
            scene_category: 场景分类
            video_description: 视频描述
            position: 插入位置 (before_template/after_context)
        
        Returns:
            增强后的提示词
        """
        # 获取示例
        examples = self.get_fewshot_examples(
            scene_category=scene_category,
            video_description=video_description
        )
        
        if not examples:
            return base_prompt
        
        # 构建 Few-shot 部分
        fewshot_prompt = self.build_fewshot_prompt(examples)
        
        # 根据位置插入
        if position == "before_template":
            # 在模板之前插入
            return fewshot_prompt + "\n" + base_prompt
        elif position == "after_context":
            # 在任务上下文之后插入
            # 找到 "请严格执行以下双重规范" 的位置
            marker = "请严格执行以下双重规范"
            if marker in base_prompt:
                parts = base_prompt.split(marker, 1)
                return parts[0] + fewshot_prompt + "\n" + marker + parts[1]
            else:
                return fewshot_prompt + "\n" + base_prompt
        else:
            return fewshot_prompt + "\n" + base_prompt
    
    def update_base_examples(self, scene_category: str, examples: List[Dict]):
        """
        更新基础示例库
        
        Args:
            scene_category: 场景分类
            examples: 新示例列表
        """
        if scene_category not in self._base_examples:
            self._base_examples[scene_category] = []
        
        self._base_examples[scene_category].extend(examples)
        
        # 保存到文件
        self._save_base_examples()
    
    def _save_base_examples(self):
        """保存基础示例到文件"""
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        examples_path = os.path.join(base_dir, "data", "learning", "base_examples.json")
        
        os.makedirs(os.path.dirname(examples_path), exist_ok=True)
        
        with open(examples_path, 'w', encoding='utf-8') as f:
            json.dump(self._base_examples, f, ensure_ascii=False, indent=2)
    
    def load_base_examples_from_file(self):
        """从文件加载基础示例"""
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        examples_path = os.path.join(base_dir, "data", "learning", "base_examples.json")
        
        if os.path.exists(examples_path):
            with open(examples_path, 'r', encoding='utf-8') as f:
                self._base_examples = json.load(f)
            print(f"已加载基础示例: {examples_path}")
    
    def get_example_stats(self) -> Dict[str, Any]:
        """获取示例统计信息"""
        stats = {
            'base_examples_count': {},
            'correction_examples_available': 0
        }
        
        for category, examples in self._base_examples.items():
            stats['base_examples_count'][category] = len(examples)
        
        if self.vector_store:
            stats['correction_examples_available'] = self.vector_store.get_stats().get('total_count', 0)
        
        return stats