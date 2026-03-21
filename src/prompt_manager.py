"""
提示词管理模块
负责管理和生成各种提示词模板
"""

from typing import Dict, Any, Optional


class PromptManager:
    """提示词管理器，负责生成和管理各种提示词"""
    
    def __init__(self):
        """初始化提示词管理器"""
        self._base_prompt = None
        self._template_prompt = None
    
    def get_emcast_prompt(self, video_metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        获取EMCAST六维分层标注提示词
        
        Args:
            video_metadata: 视频元数据，可用于动态调整提示词
        
        Returns:
            完整的提示词字符串
        """
        metadata_info = self._format_metadata_info(video_metadata) if video_metadata else ""
        tech_layer_template = self._generate_tech_layer_template(video_metadata)
        
        prompt = (
            "你是一位专业的北京城市文化与视听语言分析师，严格遵循「EMCAST六维分层标注体系」对视频进行标注。\n"
            "请你严格按照以下要求执行：\n"
            "1. 角色定位：专业标注师，仅输出最终标注结果，不包含任何思考、分析、修正或解释过程。\n"
            "2. 文化分类规则（必须严格遵循，唯一选择）：\n"
            "   - 古都文化：仅标注中轴线、皇城格局、世界遗产（如故宫、长城、钟鼓楼）等体现北京历史延续性的内容；\n"
            "   - 红色文化：仅标注革命旧址、纪念设施（如天安门广场、革命博物馆）及国家庆典相关内容；\n"
            "   - 京味文化：仅标注胡同生活、老字号、非遗技艺（如京剧、相声、传统手工艺）及民俗活动相关内容；\n"
            "   - 创新文化：仅标注科技园区、大兴机场、自动驾驶、现代文创园区等体现当代科技与创新气质的内容；\n"
            "   - 国际时尚文化：仅标注使馆区、国际消费商圈（如亮马河、三里屯）、重大外交活动场所相关内容；\n"
            "3. 格式要求：完全遵循下方「EMCAST标注模板」结构，每个维度单独成段，不添加编号、占位符或多余内容；\n"
            "4. 风格参考：输出的语言专业度、细节粒度；\n"
            "5. 主体识别：精准区分活跃主体/承载主体，若涉及非遗技艺、特定行业场景，需明确标注核心动作或技艺名称；\n"
            "6. 多主体处理：若存在多主体（如人与景、人与人交互），需分别描述并指明关系；\n"
            "7. 技术参数：优先使用下方提供的视频原生参数，无法识别时留空，禁止主观推测。\n"
            f"{metadata_info}"
            "------------------------------\n"
            "【EMCAST标注模板】\n"
            "【E｜场景环境层】\n"
            "视频构建了一个[空间场所]的物理环境。此时处于[时间/天气]状态。整体场景呈现出[情绪氛围]的感官基调。\n"
            "【M｜主体行为层】\n"
            "画面的视觉焦点是[主体类型]（区分活跃主体/承载主体）。\n"
            "外观特征：该主体具有[材质/衣着/形态细节]特征。\n"
            "动态行为：主体正在进行[具体动作/核心技艺]，其状态呈现为[行为方式/节奏]。若涉及文字，画面中清晰可见的文字符号为[\" \"]。\n"
            "注：若存在多主体（如人与景交互），需分别描述并指明关系。\n"
            "【C｜文化维度层】\n"
            "该场景隶属于[五大文化类别之一]（需严格匹配上述分类规则）。\n"
            "核心符号：画面中承载该文化的关键符号是[具体元素，需对应文化类别核心特征]。\n"
            "价值指向：场景表达了[历史语境/时代精神/文化内涵，需贴合所选文化类别]。\n"
            "【A｜视听语言层】\n"
            "镜头采用 [运镜方式]，以 [景别] 为主，景深为 [浅/深]。光影条件为 [光线特征]，构图方式为 [构图范式]，视觉重心集中于 [主体/区域]。\n"
            "音频方面主要为[环境音/讲解/配乐/静音]，声音与画面的关系为[实时/配音]。\n"
            "【S｜整体叙事层】\n"
            "对视频内容进行整体性、密集化的综合描述，总结前述各层信息，概括视频的整体叙事、场景组织及时序变化。\n"
            f"{tech_layer_template}"
            "------------------------------\n"
            "现在，请你对当前视频进行EMCAST六维分层标注，严格遵循上述分类规则、模板和案例风格。"
        )
        
        return prompt
    
    def _format_metadata_info(self, metadata: Dict[str, Any]) -> str:
        """
        格式化视频元数据信息
        
        Args:
            metadata: 视频元数据字典
        
        Returns:
            格式化后的元数据信息字符串
        """
        if not metadata:
            return ""
        
        info_lines = []
        if metadata.get('duration'):
            info_lines.append(f"视频时长：{metadata['duration']}秒")
        if metadata.get('fps'):
            info_lines.append(f"帧率：{metadata['fps']} FPS")
        if metadata.get('resolution'):
            info_lines.append(f"分辨率：{metadata['resolution']}")
        if metadata.get('codec'):
            info_lines.append(f"编码格式：{metadata['codec']}")
        
        if info_lines:
            return "\n8. 视频技术参数参考：\n   " + "\n   ".join(info_lines) + "\n"
        
        return ""
    
    def _generate_tech_layer_template(self, metadata: Optional[Dict[str, Any]]) -> str:
        """
        根据ffmpeg读取的元数据生成【T｜技术属性层】模板
        只包含有实际数据的字段
        
        Args:
            metadata: 视频元数据字典
        
        Returns:
            技术属性层模板字符串
        """
        if not metadata:
            # 没有元数据时返回通用模板
            return (
                "【T｜技术属性层】\n"
                "分辨率：[ ]; 帧率：[ ] FPS; 画幅：[ ]; 动态范围：[ ]; 色彩空间：[ ]; 采样方式：[ ]; 编码格式：[ ]; 视频时长：[ ]秒\n"
            )
        
        # 构建实际有值的参数字段
        params = []
        
        # 分辨率
        if metadata.get('resolution'):
            params.append(f"分辨率：{metadata['resolution']}")
        else:
            params.append("分辨率：[ ]")
        
        # 帧率
        if metadata.get('fps'):
            params.append(f"帧率：{metadata['fps']} FPS")
        else:
            params.append("帧率：[ ] FPS")
        
        # 画幅/宽高比
        if metadata.get('aspect_ratio'):
            params.append(f"画幅：{metadata['aspect_ratio']}")
        else:
            params.append("画幅：[ ]")
        
        # 动态范围
        if metadata.get('dynamic_range'):
            params.append(f"动态范围：{metadata['dynamic_range']}")
        else:
            params.append("动态范围：[ ]")
        
        # 色彩空间/像素格式
        if metadata.get('pixel_format'):
            params.append(f"色彩空间/像素格式：{metadata['pixel_format']}")
        else:
            params.append("色彩空间：[ ]")
        
        # 采样方式（色度子采样）
        if metadata.get('chroma_subsampling'):
            params.append(f"采样方式：{metadata['chroma_subsampling']}")
        else:
            params.append("采样方式：[ ]")
        
        # 编码格式
        if metadata.get('codec'):
            params.append(f"编码格式：{metadata['codec']}")
        else:
            params.append("编码格式：[ ]")
        
        # 视频时长
        if metadata.get('duration'):
            params.append(f"视频时长：{metadata['duration']}秒")
        else:
            params.append("视频时长：[ ]秒")
        
        # 码率（如果有）
        if metadata.get('bitrate'):
            params.append(f"码率：{metadata['bitrate']}")
        
        # 宽度高度（单独显示）
        if metadata.get('width') and metadata.get('height'):
            params.append(f"尺寸：{metadata['width']}x{metadata['height']}")
        
        # 构建模板
        template = "【T｜技术属性层】\n" + "； ".join(params) + "\n"
        
        return template
    
    def get_simple_prompt(self, task_description: str) -> str:
        """
        获取简单提示词
        
        Args:
            task_description: 任务描述
        
        Returns:
            简单提示词字符串
        """
        return f"{task_description}\n请严格按照要求完成任务，仅输出最终结果。"
    
    def create_custom_prompt(self, template: str, **kwargs) -> str:
        """
        创建自定义提示词
        
        Args:
            template: 提示词模板，支持{variable}格式的占位符
            **kwargs: 模板变量
        
        Returns:
            填充后的提示词字符串
        """
        try:
            return template.format(**kwargs)
        except KeyError as e:
            raise ValueError(f"模板变量 {e} 未提供")