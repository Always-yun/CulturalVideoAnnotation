"""
向量数据库模块 - 离线版
使用 JSON 文件存储和关键词检索
无需安装 ChromaDB，完全离线可用
"""

import os
import json
from typing import Dict, List, Optional, Any
from datetime import datetime


class VectorStore:
    """基于 JSON 文件的向量数据库（离线模式）"""
    
    def __init__(self, config):
        """
        初始化向量数据库
        
        Args:
            config: LearningConfig 配置对象
        """
        self.config = config
        self.db_path = config.vector_db_path
        os.makedirs(self.db_path, exist_ok=True)
        
        # 修正案例索引文件
        self.index_file = os.path.join(self.db_path, "cases_index.json")
        self._load_index()
    
    def _load_index(self):
        """加载索引"""
        if os.path.exists(self.index_file):
            with open(self.index_file, 'r', encoding='utf-8') as f:
                self.index = json.load(f)
        else:
            self.index = []
    
    def _save_index(self):
        """保存索引"""
        with open(self.index_file, 'w', encoding='utf-8') as f:
            json.dump(self.index, f, ensure_ascii=False, indent=2)
    
    def add_correction_case(
        self,
        case_id: str,
        video_path: str,
        scene_category: str,
        original_annotation: str,
        corrected_annotation: str,
        differences: List[Dict],
        correction_reason: str = None,
        key_frame_description: str = None,
        metadata: Dict[str, Any] = None
    ):
        """添加修正案例"""
        # 构建案例数据
        case_data = {
            "case_id": case_id,
            "video_path": video_path,
            "scene_category": scene_category,
            "original_annotation": original_annotation,
            "corrected_annotation": corrected_annotation,
            "correction_reason": correction_reason or "",
            "key_frame_description": key_frame_description or "",
            "timestamp": datetime.now().isoformat(),
            "diff_count": len(differences)
        }
        
        if metadata:
            case_data.update(metadata)
        
        # 保存到文件
        case_file = os.path.join(self.db_path, f"case_{case_id}.json")
        with open(case_file, 'w', encoding='utf-8') as f:
            json.dump(case_data, f, ensure_ascii=False, indent=2)
        
        # 更新索引
        # 移除已存在的同名案例
        self.index = [c for c in self.index if c.get('case_id') != case_id]
        self.index.append({
            "case_id": case_id,
            "video_path": video_path,
            "scene_category": scene_category,
            "timestamp": case_data["timestamp"]
        })
        self._save_index()
        
        print(f"案例已存入: {case_file}")
    
    def search_similar_cases(
        self,
        query: str,
        scene_category: str = None,
        n_results: int = 5,
        min_distance: float = None
    ) -> List[Dict[str, Any]]:
        """搜索相似的修正案例（基于关键词）"""
        results = []
        query_lower = query.lower()
        keywords = query_lower.replace('，', ',').replace('、', ',').split()
        
        # 从 corrections 目录搜索
        corrections_dir = self.config.corrections_dir
        
        if not os.path.exists(corrections_dir):
            return results
        
        for filename in os.listdir(corrections_dir):
            if not filename.startswith('correction_') or not filename.endswith('.json'):
                continue
            
            filepath = os.path.join(corrections_dir, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 场景分类过滤
                if scene_category and data.get('scene_category') != scene_category:
                    continue
                
                # 计算关键词匹配分数
                score = 0
                text_to_search = (
                    data.get('scene_category', '') + ' ' +
                    data.get('corrected_annotation', '') + ' ' +
                    data.get('correction_reason', '') + ' ' +
                    os.path.basename(data.get('video_path', ''))
                ).lower()
                
                for kw in keywords:
                    if kw in text_to_search:
                        score += 1
                
                if score > 0:
                    # 计算距离（分数越高，距离越近）
                    distance = 1.0 - (score / max(len(keywords), 1))
                    
                    if min_distance is not None and distance > min_distance:
                        continue
                    
                    results.append({
                        'case_id': data.get('case_id', filename),
                        'distance': distance,
                        'metadata': data
                    })
            except Exception as e:
                continue
        
        # 按相似度排序
        results.sort(key=lambda x: x['distance'])
        return results[:n_results]
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = {
            'total_count': 0,
            'by_category': {},
            'recent_added': []
        }
        
        # 从 corrections 目录统计
        corrections_dir = self.config.corrections_dir
        if os.path.exists(corrections_dir):
            for filename in os.listdir(corrections_dir):
                if filename.startswith('correction_') and filename.endswith('.json'):
                    filepath = os.path.join(corrections_dir, filename)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        stats['total_count'] += 1
                        cat = data.get('scene_category', '未分类')
                        stats['by_category'][cat] = stats['by_category'].get(cat, 0) + 1
                    except:
                        continue
        
        return stats
    
    def delete_case(self, case_id: str):
        """删除案例"""
        case_file = os.path.join(self.db_path, f"case_{case_id}.json")
        if os.path.exists(case_file):
            os.remove(case_file)
            print(f"案例已删除: {case_id}")
    
    def clear_all(self):
        """清空所有数据"""
        for filename in os.listdir(self.db_path):
            if filename.endswith('.json') and filename != 'cases_index.json':
                os.remove(os.path.join(self.db_path, filename))
        self.index = []
        self._save_index()
        print("已清空所有案例文件")