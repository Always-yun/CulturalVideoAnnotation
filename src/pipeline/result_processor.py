"""
结果处理模块
负责标注结果的处理、格式化和保存
"""

import os
import json
import re
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict


@dataclass
class AnnotationResult:
    """标注结果数据类"""
    video_path: str
    video_name: str
    annotation_text: str
    timestamp: str
    processing_time: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return asdict(self)
    
    def to_json(self) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


class ResultProcessor:
    """结果处理器，负责处理和保存标注结果"""
    
    def __init__(self, output_dir: Optional[str] = None):
        """
        初始化结果处理器
        
        Args:
            output_dir: 输出目录，如果为None则使用默认目录
        """
        self.output_dir = output_dir or "./outputs"
        self._ensure_output_dir()
    
    def _ensure_output_dir(self):
        """确保输出目录存在"""
        os.makedirs(self.output_dir, exist_ok=True)
    
    def create_result(self, video_path: str, annotation_text: str,
                     metadata: Optional[Dict[str, Any]] = None, 
                     processing_time: Optional[str] = None) -> AnnotationResult:
        """
        创建标注结果对象
        
        Args:
            video_path: 视频文件路径
            annotation_text: 标注文本
            metadata: 视频元数据
            processing_time: 处理时间
        
        Returns:
            AnnotationResult对象
        """
        return AnnotationResult(
            video_path=video_path,
            video_name=os.path.basename(video_path),
            annotation_text=annotation_text,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            processing_time=processing_time,
            metadata=metadata
        )
    
    def format_output(self, result: AnnotationResult, 
                     format_type: str = "standard") -> str:
        """
        格式化输出结果
        
        Args:
            result: 标注结果对象
            format_type: 格式类型 ("clean", "standard", "detailed")
        
        Returns:
            格式化后的字符串
        """
        if format_type == "clean":
            return self._format_clean(result)
        elif format_type == "standard":
            return self._format_standard(result)
        elif format_type == "detailed":
            return self._format_detailed(result)
        else:
            return self._format_standard(result)
    
    def _format_clean(self, result: AnnotationResult) -> str:
        """
        clean格式 - 只输出纯净的EMCAST六维标注
        去除思考过程，不包含文件信息
        """
        return self._extract_emcast_content(result.annotation_text)
    
    def _format_standard(self, result: AnnotationResult) -> str:
        """
        standard格式 - 文件信息 + EMCAST六维标注
        去除思考过程，包含基本的文件信息
        """
        header = [
            f"视频文件: {result.video_name}",
            f"视频路径: {result.video_path}",
            f"标注时间: {result.timestamp}",
        ]
        if result.processing_time:
            header.append(f"处理时间: {result.processing_time}")
        header.append("")
        emcast_content = self._extract_emcast_content(result.annotation_text)
        return "\n".join(header) + emcast_content
    
    def _format_detailed(self, result: AnnotationResult) -> str:
        """
        detailed格式 - 完整的终端输出
        包含文件信息、元数据、完整标注内容（含思考过程）
        """
        separator = "=" * 80
        output = [
            separator,
            f"【文化特征分层标注结果】",
            f"视频文件: {result.video_name}",
            f"视频路径: {result.video_path}",
            f"标注时间: {result.timestamp}",
        ]
        if result.processing_time:
            output.append(f"处理时间: {result.processing_time}")
        output.append(separator)
        
        if result.metadata:
            output.append("【视频元数据】")
            for key, value in result.metadata.items():
                if value is not None:
                    output.append(f"  {key}: {value}")
            output.append(separator)
        
        output.append("【完整标注内容（含思考过程）】")
        output.append(result.annotation_text)
        output.append(separator)
        
        return "\n".join(output)
    
    def save_result(self, result: AnnotationResult, 
                   output_format: str = "txt",
                   filename: Optional[str] = None,
                   format_type: str = "standard") -> str:
        """
        保存标注结果
        
        Args:
            result: 标注结果对象
            output_format: 输出格式 ("txt", "json", "both")
            filename: 输出文件名，如果为None则自动生成
            format_type: 格式类型 ("clean", "standard", "detailed")
        
        Returns:
            保存的文件路径
        """
        if filename is None:
            base_name = os.path.splitext(result.video_name)[0]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{base_name}_annotation_{format_type}_{timestamp}"
        
        saved_files = []
        
        if output_format in ["txt", "both"]:
            txt_path = os.path.join(self.output_dir, f"{filename}.txt")
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(self.format_output(result, format_type))
            saved_files.append(txt_path)
        
        if output_format in ["json", "both"]:
            json_path = os.path.join(self.output_dir, f"{filename}.json")
            with open(json_path, 'w', encoding='utf-8') as f:
                f.write(result.to_json())
            saved_files.append(json_path)
        
        return saved_files[0] if len(saved_files) == 1 else saved_files
    
    def save_batch_results(self, results: List[AnnotationResult],
                         output_format: str = "both",
                         format_type: str = "standard") -> List[str]:
        """
        批量保存标注结果
        
        Args:
            results: 标注结果列表
            output_format: 输出格式
            format_type: 格式类型
        
        Returns:
            保存的文件路径列表
        """
        saved_files = []
        
        for result in results:
            try:
                file_path = self.save_result(result, output_format, format_type=format_type)
                saved_files.append(file_path)
            except Exception as e:
                print(f"保存结果失败 {result.video_name}: {str(e)}")
        
        return saved_files
    
    def print_result(self, result: AnnotationResult, 
                    format_type: str = "standard"):
        """
        打印标注结果
        
        Args:
            result: 标注结果对象
            format_type: 格式类型
        """
        print(self.format_output(result, format_type))
    
    def _extract_emcast_content(self, annotation_text: str) -> str:
        """
        从标注文本中提取EMCAST六维标注内容
        去除模型的思考过程，只保留最终标注结果
        
        Args:
            annotation_text: 原始标注文本
        
        Returns:
            清理后的EMCAST六维标注文本
        """
        # 移除<think>标签及其内容（模型思考过程）
        annotation_text = re.sub(r'<think>.*?</think>', '', annotation_text, flags=re.DOTALL)
        annotation_text = annotation_text.replace('</think>', '')
        
        lines = annotation_text.split('\n')
        
        # 找到所有EMCAST层级标记的位置，按层级分组
        # 模型可能会输出多遍EMCAST内容，我们需要找到最后一遍（最终输出）
        emcast_groups = []
        current_group = []
        
        for i, line in enumerate(lines):
            if line.strip().startswith('【') and '｜' in line and '】' in line:
                layer_code = line.split('｜')[0].replace('【', '').strip()
                if layer_code in ['E', 'M', 'C', 'A', 'S', 'T']:
                    # 如果是E层级且当前组不为空，说明开始新的一组
                    if layer_code == 'E' and current_group:
                        emcast_groups.append(current_group)
                        current_group = []
                    current_group.append(i)
        
        # 添加最后一组
        if current_group:
            emcast_groups.append(current_group)
        
        if not emcast_groups:
            # 如果没有找到EMCAST标记，返回清理后的文本
            return annotation_text.strip()
        
        # 使用最后一组（最终输出）
        last_group = emcast_groups[-1]
        start_idx = last_group[0]
        end_idx = last_group[-1]
        
        # 找到最后一个EMCAST层级的结束位置
        last_layer_end = end_idx + 1
        while last_layer_end < len(lines):
            line = lines[last_layer_end].strip()
            # 如果遇到下一个【层级】标记，停止
            if line.startswith('【') and '｜' in line:
                break
            # 如果遇到"检查一遍"、"OK，准备输出"等思考标记，停止
            if any(marker in line for marker in ['检查一遍', 'OK，准备', '修正', '润色', 'Drafting', 'Final Polish']):
                break
            last_layer_end += 1
        
        # 提取EMCAST内容
        emcast_lines = lines[start_idx:last_layer_end]
        
        # 清理空行和多余的空白
        cleaned_lines = []
        prev_empty = False
        for line in emcast_lines:
            stripped = line.strip()
            if stripped:
                cleaned_lines.append(line)
                prev_empty = False
            elif not prev_empty:
                cleaned_lines.append('')
                prev_empty = True
        
        # 去除末尾的空行
        while cleaned_lines and cleaned_lines[-1] == '':
            cleaned_lines.pop()
        
        return '\n'.join(cleaned_lines)
    
    def extract_layers(self, annotation_text: str) -> Dict[str, str]:
        """
        从标注文本中提取各个层级的内容
        
        Args:
            annotation_text: 标注文本
        
        Returns:
            字典，键为层级名称，值为对应内容
        """
        layers = {}
        current_layer = None
        current_content = []
        
        lines = annotation_text.split('\n')
        
        for line in lines:
            line = line.strip()
            if line.startswith('【') and '｜' in line and '】' in line:
                if current_layer is not None:
                    layers[current_layer] = '\n'.join(current_content).strip()
                
                current_layer = line.split('】')[0] + '】'
                current_content = []
            elif current_layer is not None:
                current_content.append(line)
        
        if current_layer is not None:
            layers[current_layer] = '\n'.join(current_content).strip()
        
        return layers
    
    def compare_results(self, result1: AnnotationResult, 
                       result2: AnnotationResult) -> Dict[str, Any]:
        """
        比较两个标注结果
        
        Args:
            result1: 第一个标注结果
            result2: 第二个标注结果
        
        Returns:
            比较结果字典
        """
        layers1 = self.extract_layers(result1.annotation_text)
        layers2 = self.extract_layers(result2.annotation_text)
        
        comparison = {
            "video1": result1.video_name,
            "video2": result2.video_name,
            "common_layers": [],
            "different_layers": [],
            "layer_details": {}
        }
        
        all_layers = set(layers1.keys()) | set(layers2.keys())
        
        for layer in all_layers:
            if layer in layers1 and layer in layers2:
                if layers1[layer] == layers2[layer]:
                    comparison["common_layers"].append(layer)
                else:
                    comparison["different_layers"].append(layer)
                    comparison["layer_details"][layer] = {
                        "result1": layers1[layer],
                        "result2": layers2[layer]
                    }
            else:
                comparison["different_layers"].append(layer)
                comparison["layer_details"][layer] = {
                    "result1": layers1.get(layer, "不存在"),
                    "result2": layers2.get(layer, "不存在")
                }
        
        return comparison
