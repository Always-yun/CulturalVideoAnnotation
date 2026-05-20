"""
提示词管理模块 (EMCAST v2.2 多建筑解耦独立标注版)
负责管理和生成符合学术级受控词表约束的提示词模板
深度修复多建筑形态被模型强行合并、糊弄描述的底层缺陷
"""

from typing import Dict, Any, Optional
import os


class PromptManager:
    """提示词管理器，负责生成和管理统一的标准闭集约束提示词"""
    
    # 场景关键词映射表（仅用于动态确定推理范围，不干预模板本身）
    SCENE_KEYWORDS = {
        # 创新科技文化
        "中关村": {"category": "创新科技文化", "description": "中关村论坛、科技园区、前沿实验室等体现当代科技气质的内容", 
                   "location": "中关村国际创新中心、中关村国家自主创新示范区展示中心等论坛活动场所"},
        "科技": {"category": "创新科技文化", "description": "科技园区、前沿技术、现代科技设施", "location": "科技相关场所"},
        "创新": {"category": "创新科技文化", "description": "创新园区、创新中心、科技创新展示", "location": "创新相关场所"},
        "大兴机场": {"category": "创新科技文化", "description": "大兴机场及周边现代化设施", "location": "北京大兴国际机场"},
        "自动驾驶": {"category": "创新科技文化", "description": "自动驾驶车辆、智能交通", "location": "自动驾驶测试区域"},
        "数字": {"category": "创新科技文化", "description": "数字科技、数字化展示", "location": "数字科技相关场所"},
        
        # 古都文化
        "故宫": {"category": "古都文化", "description": "故宫博物院及周边历史建筑", "location": "故宫博物院"},
        "中轴线": {"category": "古都文化", "description": "北京中轴线及其周边历史遗迹", "location": "北京中轴线区域"},
        "钟鼓楼": {"category": "古都文化", "description": "钟楼、鼓楼及周边历史区域", "location": "钟鼓楼"},
        "长城": {"category": "古都文化", "description": "长城及相关历史遗迹", "location": "长城"},
        "皇城": {"category": "古都文化", "description": "皇城格局及相关历史建筑", "location": "皇城区域"},
        "天坛": {"category": "古都文化", "description": "天坛及周边历史区域", "location": "天坛公园"},
        "颐和园": {"category": "古都文化", "description": "颐和园及周边皇家园林", "location": "颐和园"},
        "圆明园": {"category": "圆明园遗址及周边区域", "location": "圆明园"},
        "历史": {"category": "古都文化", "description": "历史建筑、历史遗迹", "location": "历史相关场所"},
        
        # 红色文化
        "天安门": {"category": "红色文化", "description": "天安门广场及周边纪念设施", "location": "天安门广场"},
        "革命": {"category": "红色文化", "description": "革命旧址、纪念设施", "location": "革命纪念场所"},
        "国家庆典": {"category": "红色文化", "description": "国家庆典相关活动", "location": "庆典活动场所"},
        "博物馆": {"category": "红色文化", "description": "革命博物馆、历史博物馆", "location": "博物馆"},
        
        # 京味文化
        "胡同": {"category": "京味文化", "description": "胡同生活、老北京风情", "location": "胡同区域"},
        "老字号": {"category": "京味文化", "description": "老字号店铺、传统商业", "location": "老字号店铺"},
        "京剧": {"category": "京味文化", "description": "京剧表演、传统戏曲", "location": "戏曲演出场所"},
        "相声": {"category": "京味文化", "description": "相声表演、传统曲艺", "location": "曲艺演出场所"},
        "非遗": {"category": "京味文化", "description": "非物质文化遗产、传统手工艺", "location": "非遗展示场所"},
        "民俗": {"category": "京味文化", "description": "民俗活动、传统节日", "location": "民俗活动场所"},
        
        # 国际时尚文化
        "三里屯": {"category": "国际时尚文化", "description": "国际消费商圈、时尚购物", "location": "三里屯"},
        "亮马河": {"category": "国际时尚文化", "description": "国际商圈、高端消费", "location": "亮马河"},
        "使馆区": {"category": "国际时尚文化", "description": "使馆区、外交场所", "location": "使馆区"},
        "外交": {"category": "国际时尚文化", "description": "重大外交 activity 场所", "location": "外交活动场所"},
        "国际": {"category": "国际时尚文化", "description": "国际活动、国际交流", "location": "国际活动场所"},
    }
    
    def __init__(self):
        """初始化提示词管理器"""
        self._base_prompt = None
        self._template_prompt = None
    
    def _detect_scene_from_path(self, video_path: str) -> Dict[str, str]:
        """从视频路径中动态检索并锁定推理范围"""
        if not video_path:
            return {"category": "", "description": "", "location": ""}
        
        filename = os.path.splitext(os.path.basename(video_path))[0]
        dirname = os.path.basename(os.path.dirname(video_path))
        text_to_check = f"{dirname} {filename}".lower()
        
        for keyword, info in self.SCENE_KEYWORDS.items():
            if keyword.lower() in text_to_check:
                return info
        return {"category": "", "description": "", "location": ""}
    
    def get_emcast_prompt(self, video_metadata: Optional[Dict[str, Any]] = None, 
                          video_path: Optional[str] = None) -> str:
        """
        获取全面对接多建筑独立分层拆分规范的EMCAST六维分层标注提示词
        """
        scene_info = self._detect_scene_from_path(video_path)
        scene_category = scene_info.get("category", "")
        scene_description = scene_info.get("description", "")
        scene_location = scene_info.get("location", "")
        
        metadata_info = self._format_metadata_info(video_metadata) if video_metadata else ""
        tech_layer_template = self._generate_tech_layer_template(video_metadata)
        
        if scene_category:
            task_context = (
                f"【任务上下文】：本次标注任务的视频素材专属为「{scene_description}」。"
                f"视频中出现的场所与地标建筑（如{scene_location}）均为相关活动场所。"
                f"请将你的视觉辨识与语义空间严格锁定于此，禁止泛化或盲目类比至其他不相关区域。\n\n"
            )
        else:
            task_context = ""

        selected_category = scene_category if scene_category else "[古都文化/红色文化/京味文化/创新科技文化/国际时尚文化]"

        prompt = (
            "你是一位专业的北京城市文化与视听语言分析师，严格遵循「EMCAST六维分层标注体系」对视频进行标注。\n"
            f"{task_context}"
            "请严格执行以下双重规范：\n\n"
            "============================================================\n"
            "一、 EMCAST 结构化标注规范\n"
            "============================================================\n"
            "【E｜场景环境层】\n"
            "- 标注目标：确立物理空间容器与感官基调，为生成模型设定整体影调。\n"
            "- 标注逻辑：具体空间场所 + 时间/天气 + 环境/情绪氛围。\n\n"
            "【M｜主体行为层】\n"
            "- 标注目标：定义画面的视觉代理与核心行为。\n"
            "- 核心限制规则（多建筑解耦分离描述要求）：\n"
            "  1. 本次标注任务以建筑空间为主。你必须把出现在画面中的、看起来像核心主体的建筑全部标注并罗列出来。若画面同时包含多座外观或功能不同的独立建筑（如一个长方形、一个流线圆形），你必须在输出时‘完全清晰拆分描述’各自独立的特征。严禁使用一个合成句将不同形态的建筑混淆合并描述。\n"
            "  2. 对于每一座罗列出来的核心建筑，必须独立写清其具体的[方位/相对位置]+[几何形态]（如：曲面、流线型、轴对称、矩形矩阵、飞檐斗拱）以及各自对应的[外立面材质质感]（如：玻璃幕墙、金属铝板、清水混凝土、青砖灰瓦）。\n"
            "  3. 活跃主体判定：如果活跃主体（如人物、车辆）在全图画面中的视觉占比小于或等于 70%，经判断不是主要焦点，则在最终输出中必须‘完全剥离、剔除并隐藏’任何关于活跃主体动态以及关系的字眼。只有当活跃主体占比大于 70% 时，才允许在‘视觉焦点’中并列写出活跃主体并保留其动态和关系描述。\n\n"
            "【C｜文化维度层】\n"
            "- 标注目标：界定视频的文化本体属性与符号学内涵。\n"
            "- 分类标准（唯一排他性选择）：古都文化、红色文化、京味文化、创新科技文化、国际时尚文化。\n"
            "- 核心符号：识别并精准锚定承载该文化内涵的关键视觉要素（如：特定的流线型穹顶/科技标识/国际旗帜阵列/古建斗拱）。\n\n"
            "【A｜视听语言层】\n"
            "- 标注目标：使用电影叙事学闭集术语，客观描述影像的拍摄手法与视听组织范式。\n"
            "- 核心禁止规则：严禁在最终输出中包含任何诸如‘若镜头运动详细描述：’等带有控制逻辑的提示短语。直接根据物理画面机位判定结果，平铺直叙对应结构的描述语句。\n"
            "- 闭集受控词表集合：\n"
            "  * 运镜：移动类[推（前）/拉（后）/升（上）/降（下）/平移（左/右）]；旋转类[摇摄（左/右/俯/仰）/滚转/变焦]；追踪类[侧向追踪/尾随跟拍/前方领拍/弧形追踪/环绕拍摄]。\n"
            "  * 基础要素：状态[稳定/晃动]、节奏[快/慢]、景别[大远景/全景/中景/近景/特写/大特写]、景深[浅/深]。\n"
            "  * 画面表征：构图[三分法/中轴线对称/框架式/几何引导线]；光影[高调/低调/自然漫射光/侧逆光/逆光/黄金时刻/硬光/软光]；色彩[高饱和/低饱和/冷调/暖调/对比色/同类色]。\n\n"
            "【S｜整体叙事层】\n"
            "- 标注目标：实现时序维度的语义合成与密集叙事总结。必须串联时间演进、多座核心建筑在画面中的空间对位与呼应逻辑，形成高度连贯的密集语言流。\n\n"
            "【T｜技术属性层】\n"
            "- 标注目标：记录由底层引擎解析传入的视频物理元数据。\n\n"
            "============================================================\n"
            "二、 EMCAST 标准化标注模板 (输出格式要求)\n"
            "============================================================\n"
            "严禁在最终生成的文本中遗留任何中括号占位符、条件控制说明文字。请严格依据实际画面条件，选择并组装以下对应的纯净段落格式进行输出：\n\n"
            "【EMCAST 视频标注结果】\n\n"
            "【E｜场景环境层】：视频构建了一个[具体空间场所]的物理环境。此时处于[时间/天气]状态。整体场景呈现出[氛围词表选一]的感官基调。\n\n"
            "根据活跃主体占比条件，【M｜主体行为层】严格选择以下两种格式之一输出（多建筑主体必须在‘承载主体外观’中逐一换行或分句清晰陈述，严禁合并）：\n"
            "  - 格式分支M1 (若活跃主体占比 <= 70%，完全隐藏活跃主体信息，格式必须对齐如下):\n"
            "    【M｜主体行为层】：视觉焦点包含承载主体：[列出画面中出现的所有核心建筑/场馆主体的名称或代称]\n"
            "    承载主体外观：[必须逐一、分开清晰描述各个核心建筑的具体几何形态与对应材质，多建筑严禁共用一段含糊句。格式参考：左侧/主体一呈现出...，外立面材质主要为...；右侧/主体二呈现出...，外立面材质主要为...]\n"
            "    若画面涉及文字，文字符号：[\"提取的文字内容\"]\n\n"
            "  - 格式分支M2 (若活跃主体占比 > 70%，格式必须对齐如下):\n"
            "    【M｜主体行为层】：视觉焦点包含承载主体：[列出画面中出现的所有核心建筑/场馆主体名称] 与 活跃主体：[名称]\n"
            "    承载主体外观：[必须逐一、分开清晰描述各个核心建筑的具体几何形态与对应材质，多建筑严禁共用一段含糊句。格式参考：左侧/主体一呈现出...，外立面材质主要为...；右侧/主体二呈现出...，外立面材质主要为...]\n"
            "    活跃主体动态：主体正在进行[具体动作]，状态呈现为[行为方式/节奏]。若画面涉及文字，文字符号：[\"提取的文字内容\"]。\n"
            "    主体关系：描述[活跃主体]与[各个承载主体]的空间交互逻辑。\n\n"
            "【C｜文化维度层】：该场景隶属于[古都文化/红色文化/京味文化/创新科技文化/国际时尚文化]。\n\n"
            "核心符号：识别出承载该文化内涵的关键视觉锚点为[具体元素]。\n"
            "价值指向：场景表达了[时代精神/文化内涵]。\n\n"
            "根据机位判定条件，【A｜视听语言层】严格选择以下两种格式之一平铺直叙输出（严禁夹杂控制条件括号）：\n"
            "  - 格式分支A1 (若判定为运动机位，格式必须对齐如下):\n"
            "    【A｜视听语言层】\n"
            "    镜头语法：镜头为运动机位。运镜采用[具体动作+方向]，状态[稳定/晃动]，节奏[快/慢]，以[标准景别词]为主，景深[浅/深]，视觉重心位于[具体视觉核心区域]\n"
            "    构图遵循[标准构图词]，光影特征呈现为[标准光影词]，视觉色彩倾向于[标准色彩词]。\n\n"
            "  - 格式分支A2 (若判定为固定机位，格式必须对齐如下):\n"
            "    【A｜视听语言层】\n"
            "    镜头语法：镜头为固定机位，状态[稳定/晃动]，节奏[快/慢]，以[标准景别词]为主，景深[浅/深]，视觉重心位于[具体视觉核心区域]\n"
            "    构图遵循[标准构图词]，光影特征呈现为[标准光影词]，视觉色彩倾向于[标准色彩词]。\n\n"
            "【S｜整体叙事层】：[密集化描述视频从空间组织到时序演进的连贯过程]。\n\n"
             f"{tech_layer_template}"
            "------------------------------\n"
            f"{metadata_info}"
            "现在，请严格执行多主体拆分逻辑与判定规则，仅输出干净、标准、无逻辑残留的最终标注结果。"
        )
        return prompt
    
    def _format_metadata_info(self, metadata: Dict[str, Any]) -> str:
        """格式化视频元数据参考信息"""
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
            return "【视频技术参数参考元数据】：\n   " + "\n   ".join(info_lines) + "\n"
        return ""
    
    def _generate_tech_layer_template(self, metadata: Optional[Dict[str, Any]]) -> str:
        """根据底层解析的硬核元数据，构建闭环自动对齐的【T｜技术属性层】"""
        if not metadata:
            return (
                "【T｜技术属性层】\n"
                "分辨率：[ ]；帧率：[ ] FPS；画幅：[ ]；动态范围：[HDR/SDR]；"
                "色彩空间/像素格式：[ ]；采样方式：[ ]；编码格式：[ ]；码率：[ ]；视频时长：[ ]s。\n"
            )
        
        res = metadata.get('resolution', '[ ]')
        fps = f"{metadata['fps']}" if metadata.get('fps') else '[ ]'
        aspect = metadata.get('aspect_ratio', '[ ]')
        dyn = metadata.get('dynamic_range', 'SDR')
        pix = metadata.get('pixel_format', '[ ]')
        chroma = metadata.get('chroma_subsampling', '[ ]')
        codec = metadata.get('codec', '[ ]')
        bitrate = metadata.get('bitrate', '[ ]')
        dur = metadata.get('duration', '[ ]')
        
        template = (
            "【T｜技术属性层】\n"
            f"分辨率：{res}；帧率：{fps} FPS；画幅：{aspect}；动态范围：{dyn}；"
            f"色彩空间/像素格式：{pix}；采样方式：{chroma}；编码格式：{codec}；"
            f"码率：{bitrate}；视频时长：{dur}s。\n"
        )
        return template
    
    def get_simple_prompt(self, task_description: str) -> str:
        """获取极简约束提示词"""
        return f"{task_description}\n请严格按照要求完成任务，仅输出最终标准化结果。"
    
    def create_custom_prompt(self, template: str, **kwargs) -> str:
        """支持模板化、动态插值的自定义提示词生成"""
        try:
            return template.format(**kwargs)
        except KeyError as e:
            raise ValueError(f"模板插值变量 {e} 未完整提供")