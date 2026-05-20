# """
# 提示词管理模块
# 负责管理和生成各种提示词模板
# 支持根据视频路径动态确定推理范围
# """

# from typing import Dict, Any, Optional
# import os


# class PromptManager:
#     """提示词管理器，负责生成和管理各种提示词"""
    
#     # 场景关键词映射表
#     SCENE_KEYWORDS = {
#         # 创新科技文化
#         "中关村": {"category": "创新科技文化", "description": "中关村论坛、科技园区、前沿实验室等体现当代科技气质的内容", 
#                    "location": "中关村国际创新中心、中关村国家自主创新示范区展示中心等论坛活动场所"},
#         "科技": {"category": "创新科技文化", "description": "科技园区、前沿技术、现代科技设施", "location": "科技相关场所"},
#         "创新": {"category": "创新科技文化", "description": "创新园区、创新中心、科技创新展示", "location": "创新相关场所"},
#         "大兴机场": {"category": "创新科技文化", "description": "大兴机场及周边现代化设施", "location": "北京大兴国际机场"},
#         "自动驾驶": {"category": "创新科技文化", "description": "自动驾驶车辆、智能交通", "location": "自动驾驶测试区域"},
#         "数字": {"category": "创新科技文化", "description": "数字科技、数字化展示", "location": "数字科技相关场所"},
        
#         # 古都文化
#         "故宫": {"category": "古都文化", "description": "故宫博物院及周边历史建筑", "location": "故宫博物院"},
#         "中轴线": {"category": "古都文化", "description": "北京中轴线及其周边历史遗迹", "location": "北京中轴线区域"},
#         "钟鼓楼": {"category": "古都文化", "description": "钟楼、鼓楼及周边历史区域", "location": "钟鼓楼"},
#         "长城": {"category": "古都文化", "description": "长城及相关历史遗迹", "location": "长城"},
#         "皇城": {"category": "古都文化", "description": "皇城格局及相关历史建筑", "location": "皇城区域"},
#         "天坛": {"category": "古都文化", "description": "天坛及周边历史区域", "location": "天坛公园"},
#         "颐和园": {"category": "古都文化", "description": "颐和园及周边皇家园林", "location": "颐和园"},
#         "圆明园": {"category": "古都文化", "description": "圆明园遗址及周边区域", "location": "圆明园"},
#         "历史": {"category": "古都文化", "description": "历史建筑、历史遗迹", "location": "历史相关场所"},
        
#         # 红色文化
#         "天安门": {"category": "红色文化", "description": "天安门广场及周边纪念设施", "location": "天安门广场"},
#         "革命": {"category": "红色文化", "description": "革命旧址、纪念设施", "location": "革命纪念场所"},
#         "国家庆典": {"category": "红色文化", "description": "国家庆典相关活动", "location": "庆典活动场所"},
#         "博物馆": {"category": "红色文化", "description": "革命博物馆、历史博物馆", "location": "博物馆"},
        
#         # 京味文化
#         "胡同": {"category": "京味文化", "description": "胡同生活、老北京风情", "location": "胡同区域"},
#         "老字号": {"category": "京味文化", "description": "老字号店铺、传统商业", "location": "老字号店铺"},
#         "京剧": {"category": "京味文化", "description": "京剧表演、传统戏曲", "location": "戏曲演出场所"},
#         "相声": {"category": "京味文化", "description": "相声表演、传统曲艺", "location": "曲艺演出场所"},
#         "非遗": {"category": "京味文化", "description": "非物质文化遗产、传统手工艺", "location": "非遗展示场所"},
#         "民俗": {"category": "京味文化", "description": "民俗活动、传统节日", "location": "民俗活动场所"},
        
#         # 国际时尚文化
#         "三里屯": {"category": "国际时尚文化", "description": "国际消费商圈、时尚购物", "location": "三里屯"},
#         "亮马河": {"category": "国际时尚文化", "description": "国际商圈、高端消费", "location": "亮马河"},
#         "使馆区": {"category": "国际时尚文化", "description": "使馆区、外交场所", "location": "使馆区"},
#         "外交": {"category": "国际时尚文化", "description": "重大外交活动场所", "location": "外交活动场所"},
#         "国际": {"category": "国际时尚文化", "description": "国际活动、国际交流", "location": "国际活动场所"},
#     }
    
#     def __init__(self):
#         """初始化提示词管理器"""
#         self._base_prompt = None
#         self._template_prompt = None
    
#     def _detect_scene_from_path(self, video_path: str) -> Dict[str, str]:
#         """
#         从视频路径中检测场景类型
        
#         Args:
#             video_path: 视频文件路径
        
#         Returns:
#             场景信息字典，包含category、description、location
#         """
#         if not video_path:
#             return {"category": "", "description": "", "location": ""}
        
#         # 获取文件名（不含扩展名）
#         filename = os.path.splitext(os.path.basename(video_path))[0]
#         # 获取目录名
#         dirname = os.path.basename(os.path.dirname(video_path))
        
#         # 组合用于匹配的文本
#         text_to_check = f"{dirname} {filename}".lower()
        
#         # 查找匹配的关键词
#         for keyword, info in self.SCENE_KEYWORDS.items():
#             if keyword.lower() in text_to_check:
#                 return info
        
#         # 如果没有匹配到任何关键词，返回空
#         return {"category": "", "description": "", "location": ""}
    
#     def get_emcast_prompt(self, video_metadata: Optional[Dict[str, Any]] = None, 
#                           video_path: Optional[str] = None) -> str:
#         """
#         获取EMCAST六维分层标注提示词
        
#         Args:
#             video_metadata: 视频元数据，可用于动态调整提示词
#             video_path: 视频文件路径，用于动态检测场景类型
        
#         Returns:
#             完整的提示词字符串
#         """
#         # 从视频路径检测场景类型
#         scene_info = self._detect_scene_from_path(video_path)
#         scene_category = scene_info.get("category", "")
#         scene_description = scene_info.get("description", "")
#         scene_location = scene_info.get("location", "")
        
#         metadata_info = self._format_metadata_info(video_metadata) if video_metadata else ""
#         tech_layer_template = self._generate_tech_layer_template(video_metadata)
        
#         # 构建任务上下文（根据检测到的场景动态生成）
#         if scene_category:
#             task_context = (
#                 f"【任务上下文】：本次标注任务的视频素材专属为「{scene_description}」。"
#                 f"视频中出现的场所（如{scene_location}）均为相关活动场所。"
#                 f"请将识别范围锁定于此，严禁泛化至其他区域。\n\n"
#             )
#         else:
#             task_context = ""
        
#         # 构建主体识别规则（根据场景类型调整）
#         if scene_category == "创新科技文化":
#             subject_rules = (
#                 "3. 主体识别进阶规则（核心要求）：\n"
#                 "   - 承载主体（建筑）：需进行密集化描述。包括但不限于：建筑形态（如曲面、几何折叠）、外立面材质（如玻璃幕墙、金属铝板）、地标性设计元素及与周围环境的衔接；\n"
#                 "   - 活跃主体（活动/人物）：描述与会人员、技术演示或核心交互行为，需明确标注其在该场景下的功能属性；\n"
#                 "   - 多主体关联：当画面同时出现建筑与活动时，必须阐明人物行为如何依托于建筑空间展开；\n"
#             )
#             e_template = "视频构建了一个[特定空间场所]的物理环境。此时处于[时间/天气]状态。整体场景呈现出[高科技感/商务严谨/创新活力]等感官基调。\n"
#             m_template = (
#                 "画面的视觉焦点包含：[承载主体：特定建筑名称] 与 [活跃主体：人员/设备]。\n"
#                 "承载主体外观：详细描述建筑的[形态设计/材质特征/光影反射/地标标识]。\n"
#                 "活跃主体动态：主体正在进行[具体动作/技术展示]，其状态呈现为[节奏/行为方式]。若涉及文字（如主题标语），画面中清晰可见的文字符号为[\" \"]。\n"
#                 "主体关系：[描述人员活动与建筑空间的交互逻辑]。\n"
#             )
#             c_template = (
#                 f"该场景隶属于[{scene_category}]。\n"
#                 "核心符号：画面中承载该文化的关键符号是[建筑标识/科技设备/活动LOGO等]。\n"
#                 "价值指向：场景表达了[全球科技创新交流/国家发展战略/未来城市愿景]等时代精神。\n"
#             )
#         elif scene_category == "古都文化":
#             subject_rules = (
#                 "3. 主体识别进阶规则（核心要求）：\n"
#                 "   - 承载主体（建筑）：需进行密集化描述。包括但不限于：建筑形态（如飞檐斗拱、传统结构）、外立面材质（如青砖灰瓦、木质结构）、历史特征及与周围环境的协调；\n"
#                 "   - 活跃主体（活动/人物）：描述游客活动、历史展示或相关文化活动，需明确标注其历史文化背景；\n"
#                 "   - 多主体关联：当画面同时出现历史建筑与活动时，必须阐明人与历史建筑的互动关系；\n"
#             )
#             e_template = "视频构建了一个[历史空间场所]的物理环境。此时处于[时间/天气]状态。整体场景呈现出[历史厚重感/庄重典雅]等感官基调。\n"
#             m_template = (
#                 "画面的视觉焦点包含：[承载主体：历史建筑名称] 与 [活跃主体：游客/活动]。\n"
#                 "承载主体外观：详细描述建筑的[历史形态/材质特征/雕刻装饰/历史标识]。\n"
#                 "活跃主体动态：主体正在进行[具体动作/文化活动]，其状态呈现为[节奏/行为方式]。若涉及文字（如匾额题字），画面中清晰可见的文字符号为[\" \"]。\n"
#                 "主体关系：[描述人员活动与历史建筑的互动逻辑]。\n"
#             )
#             c_template = (
#                 f"该场景隶属于[{scene_category}]。\n"
#                 "核心符号：画面中承载该文化的关键符号是[历史建筑/传统元素/文化符号等]。\n"
#                 "价值指向：场景表达了[历史传承/文化遗产保护/中华文明延续]等时代精神。\n"
#             )
#         elif scene_category == "红色文化":
#             subject_rules = (
#                 "3. 主体识别进阶规则（核心要求）：\n"
#                 "   - 承载主体（建筑）：需进行密集化描述。包括但不限于：建筑形态（如纪念性建筑、革命旧址）、历史标识、纪念设施及与历史事件的关联；\n"
#                 "   - 活跃主体（活动/人物）：描述参观人员、纪念活动或相关仪式，需明确标注其红色文化意义；\n"
#                 "   - 多主体关联：当画面同时出现纪念建筑与活动时，必须阐明活动与历史意义的联系；\n"
#             )
#             e_template = "视频构建了一个[纪念空间场所]的物理环境。此时处于[时间/天气]状态。整体场景呈现出[庄严肃穆/庄重典雅]等感官基调。\n"
#             m_template = (
#                 "画面的视觉焦点包含：[承载主体：纪念建筑/旧址名称] 与 [活跃主体：参观人员/活动]。\n"
#                 "承载主体外观：详细描述建筑的[历史形态/纪念标识/展览内容]。\n"
#                 "活跃主体动态：主体正在进行[具体动作/纪念活动]，其状态呈现为[节奏/行为方式]。若涉及文字（如标语/题词），画面中清晰可见的文字符号为[\" \"]。\n"
#                 "主体关系：[描述人员活动与纪念场所的互动逻辑]。\n"
#             )
#             c_template = (
#                 f"该场景隶属于[{scene_category}]。\n"
#                 "核心符号：画面中承载该文化的关键符号是[纪念标识/历史遗物/红色标语等]。\n"
#                 "价值指向：场景表达了[革命历史传承/爱国主义精神/国家记忆]等时代精神。\n"
#             )
#         elif scene_category == "京味文化":
#             subject_rules = (
#                 "3. 主体识别进阶规则（核心要求）：\n"
#                 "   - 承载主体（建筑/场所）：需进行密集化描述。包括但不限于：胡同风貌、传统店铺、民俗场所及老北京特色元素；\n"
#                 "   - 活跃主体（活动/人物）：描述居民生活、传统技艺表演或民俗活动，需明确标注其京味文化特色；\n"
#                 "   - 多主体关联：当画面同时出现传统场所与活动时，必须阐明活动与老北京文化的联系；\n"
#             )
#             e_template = "视频构建了一个[老北京特色空间场所]的物理环境。此时处于[时间/天气]状态。整体场景呈现出[市井生活气息/传统韵味]等感官基调。\n"
#             m_template = (
#                 "画面的视觉焦点包含：[承载主体：传统建筑/店铺名称] 与 [活跃主体：居民/表演者]。\n"
#                 "承载主体外观：详细描述建筑的[传统形态/特色装饰/老字号标识]。\n"
#                 "活跃主体动态：主体正在进行[具体动作/传统技艺/民俗活动]，其状态呈现为[节奏/行为方式]。若涉及文字（如店铺招牌），画面中清晰可见的文字符号为[\" \"]。\n"
#                 "主体关系：[描述人员活动与传统空间的互动逻辑]。\n"
#             )
#             c_template = (
#                 f"该场景隶属于[{scene_category}]。\n"
#                 "核心符号：画面中承载该文化的关键符号是[胡同/老字号/传统技艺/民俗元素等]。\n"
#                 "价值指向：场景表达了[老北京文化传承/市井生活气息/传统文化延续]等时代精神。\n"
#             )
#         elif scene_category == "国际时尚文化":
#             subject_rules = (
#                 "3. 主体识别进阶规则（核心要求）：\n"
#                 "   - 承载主体（建筑/场所）：需进行密集化描述。包括但不限于：现代化建筑、国际商圈、高端消费场所及时尚元素；\n"
#                 "   - 活跃主体（活动/人物）：描述国际人士、时尚活动或高端消费行为，需明确标注其国际时尚特色；\n"
#                 "   - 多主体关联：当画面同时出现国际场所与活动时，必须阐明活动与国际化定位的联系；\n"
#             )
#             e_template = "视频构建了一个[国际时尚空间场所]的物理环境。此时处于[时间/天气]状态。整体场景呈现出[时尚现代感/国际化氛围]等感官基调。\n"
#             m_template = (
#                 "画面的视觉焦点包含：[承载主体：现代建筑/商圈名称] 与 [活跃主体：时尚人群/国际人士]。\n"
#                 "承载主体外观：详细描述建筑的[现代设计/高端装饰/国际品牌标识]。\n"
#                 "活跃主体动态：主体正在进行[具体动作/时尚活动/消费行为]，其状态呈现为[节奏/行为方式]。若涉及文字（如品牌标识），画面中清晰可见的文字符号为[\" \"]。\n"
#                 "主体关系：[描述人员活动与时尚空间的互动逻辑]。\n"
#             )
#             c_template = (
#                 f"该场景隶属于[{scene_category}]。\n"
#                 "核心符号：画面中承载该文化的关键符号是[国际品牌/时尚元素/高端设施等]。\n"
#                 "价值指向：场景表达了[国际交流/时尚潮流/高端生活方式]等时代精神。\n"
#             )
#         else:
#             # 默认通用规则
#             subject_rules = ""
#             e_template = "视频构建了一个[空间场所]的物理环境。此时处于[时间/天气]状态。整体场景呈现出[情绪氛围]的感官基调。\n"
#             m_template = (
#                 "画面的视觉焦点是[主体类型]（区分活跃主体/承载主体）。\n"
#                 "外观特征：该主体具有[材质/衣着/形态细节]特征。\n"
#                 "动态行为：主体正在进行[具体动作/核心技艺]，其状态呈现为[行为方式/节奏]。若涉及文字，画面中清晰可见的文字符号为[\" \"]。\n"
#                 "注：若存在多主体（如人与景交互），需分别描述并指明关系。\n"
#             )
#             c_template = (
#                 "该场景隶属于[五大文化类别之一]（需严格匹配上述分类规则）。\n"
#                 "核心符号：画面中承载该文化的关键符号是[具体元素，需对应文化类别核心特征]。\n"
#                 "价值指向：场景表达了[历史语境/时代精神/文化内涵，需贴合所选文化类别]。\n"
#             )
        
#         # 构建完整提示词
#         if scene_category:
#             prompt = (
#                 "你是一位专业的北京城市文化与视听语言分析师，严格遵循「EMCAST六维分层标注体系」对视频进行标注。\n"
#                 f"{task_context}"
#                 "请严格按照以下要求执行：\n"
#                 "1. 角色定位：专业标注师，直接输出标注结果，严禁包含任何思考、分析或解释过程。\n"
#                 "2. 文化分类规则（必须严格遵循，唯一选择）：\n"
#                 "   - 古都文化：北京历史延续性的中轴线、皇城格局及世界遗产；\n"
#                 "   - 红色文化：革命旧址、纪念设施及国家庆典相关内容；\n"
#                 "   - 京味文化：胡同生活、老字号、非遗技艺及民俗活动；\n"
#                 "   - 创新科技文化：科技园区、前沿实验室、大兴机场、自动驾驶等体现当代科技气质的内容；\n"
#                 "   - 国际时尚文化：使馆区、国际商圈（如亮马河、三里屯）、重大外交/商务活动场所；\n"
#                 f"{subject_rules}"
#                 "4. 格式要求：完全遵循下方模板，不添加编号或多余占位符；\n"
#                 "5. 技术参数：优先使用下方提供的原生参数，无法识别时留空。\n"
#                 f"{metadata_info}\n"
#                 "------------------------------\n"
#                 "【EMCAST标注模板】\n"
#                 "【E｜场景环境层】\n"
#                 f"{e_template}"
#                 "【M｜主体行为层】\n"
#                 f"{m_template}"
#                 "【C｜文化维度层】\n"
#                 f"{c_template}"
#                 "【A｜视听语言层】\n"
#                 "镜头采用 [运镜方式]，以 [景别] 为主，景深为 [浅/深]。光影条件为 [光线特征]，构图方式为 [构图范式]，视觉重心集中于 [主体/区域]。\n"
#                 "音频方面主要为[环境音/讲解/配乐/静音]，声音与画面的关系为[实时/配音]。\n"
#                 "【S｜整体叙事层】\n"
#                 "对视频内容进行整体性、密集化的综合描述，总结前述各层信息，概括视频在时间维度上的叙事演进。\n"
#                 f"{tech_layer_template}\n"
#                 "------------------------------\n"
#                 "现在，请对当前视频进行标注。"
#             )
#         else:
#             # 未检测到特定场景，使用通用提示词
#             prompt = (
#                 "你是一位专业的北京城市文化与视听语言分析师，严格遵循「EMCAST六维分层标注体系」对视频进行标注。\n\n"
#                 "请严格按照以下要求执行：\n"
#                 "1. 角色定位：专业标注师，仅输出最终标注结果，不包含任何思考、分析、修正或解释过程。\n"
#                 "2. 文化分类规则（必须严格遵循，唯一选择）：\n"
#                 "   - 古都文化：仅标注中轴线、皇城格局、世界遗产（如故宫、长城、钟鼓楼）等体现北京历史延续性的内容；\n"
#                 "   - 红色文化：仅标注革命旧址、纪念设施（如天安门广场、革命博物馆）及国家庆典相关内容；\n"
#                 "   - 京味文化：仅标注胡同生活、老字号、非遗技艺（如京剧、相声、传统手工艺）及民俗活动相关内容；\n"
#                 "   - 创新文化：仅标注科技园区、大兴机场、自动驾驶、现代文创园区等体现当代科技与创新气质的内容；\n"
#                 "   - 国际时尚文化：仅标注使馆区、国际消费商圈（如亮马河、三里屯）、重大外交活动场所相关内容；\n"
#                 "3. 格式要求：完全遵循下方「EMCAST标注模板」结构，每个维度单独成段，不添加编号、占位符或多余内容；\n"
#                 "4. 风格参考：输出的语言专业度、细节粒度；\n"
#                 "5. 主体识别：精准区分活跃主体/承载主体，若涉及非遗技艺、特定行业场景，需明确标注核心动作或技艺名称；\n"
#                 "6. 多主体处理：若存在多主体（如人与景、人与人交互），需分别描述并指明关系；\n"
#                 "7. 技术参数：优先使用下方提供的视频原生参数，无法识别时留空，禁止主观推测。\n"
#                 f"{metadata_info}"
#                 "------------------------------\n"
#                 "【EMCAST标注模板】\n"
#                 "【E｜场景环境层】\n"
#                 "视频构建了一个[空间场所]的物理环境。此时处于[时间/天气]状态。整体场景呈现出[情绪氛围]的感官基调。\n"
#                 "【M｜主体行为层】\n"
#                 "画面的视觉焦点是[主体类型]（区分活跃主体/承载主体）。\n"
#                 "外观特征：该主体具有[材质/衣着/形态细节]特征。\n"
#                 "动态行为：主体正在进行[具体动作/核心技艺]，其状态呈现为[行为方式/节奏]。若涉及文字，画面中清晰可见的文字符号为[\" \"]。\n"
#                 "注：若存在多主体（如人与景交互），需分别描述并指明关系。\n"
#                 "【C｜文化维度层】\n"
#                 "该场景隶属于[五大文化类别之一]（需严格匹配上述分类规则）。\n"
#                 "核心符号：画面中承载该文化的关键符号是[具体元素，需对应文化类别核心特征]。\n"
#                 "价值指向：场景表达了[历史语境/时代精神/文化内涵，需贴合所选文化类别]。\n"
#                 "【A｜视听语言层】\n"
#                 "镜头采用 [运镜方式]，以 [景别] 为主，景深为 [浅/深]。光影条件为 [光线特征]，构图方式为 [构图范式]，视觉重心集中于 [主体/区域]。\n"
#                 "音频方面主要为[环境音/讲解/配乐/静音]，声音与画面的关系为[实时/配音]。\n"
#                 "【S｜整体叙事层】\n"
#                 "对视频内容进行整体性、密集化的综合描述，总结前述各层信息，概括视频的整体叙事、场景组织及时序变化。\n"
#                 f"{tech_layer_template}\n"
#                 "------------------------------\n"
#                 "现在，请你对当前视频进行EMCAST六维分层标注，严格遵循上述分类规则、模板和案例风格。"
#             )
        
#         return prompt
    
#     def _format_metadata_info(self, metadata: Dict[str, Any]) -> str:
#         """
#         格式化视频元数据信息
        
#         Args:
#             metadata: 视频元数据字典
        
#         Returns:
#             格式化后的元数据信息字符串
#         """
#         if not metadata:
#             return ""
        
#         info_lines = []
#         if metadata.get('duration'):
#             info_lines.append(f"视频时长：{metadata['duration']}秒")
#         if metadata.get('fps'):
#             info_lines.append(f"帧率：{metadata['fps']} FPS")
#         if metadata.get('resolution'):
#             info_lines.append(f"分辨率：{metadata['resolution']}")
#         if metadata.get('codec'):
#             info_lines.append(f"编码格式：{metadata['codec']}")
        
#         if info_lines:
#             return "\n8. 视频技术参数参考：\n   " + "\n   ".join(info_lines) + "\n"
        
#         return ""
    
#     def _generate_tech_layer_template(self, metadata: Optional[Dict[str, Any]]) -> str:
#         """
#         根据ffmpeg读取的元数据生成【T｜技术属性层】模板
#         只包含有实际数据的字段
        
#         Args:
#             metadata: 视频元数据字典
        
#         Returns:
#             技术属性层模板字符串
#         """
#         if not metadata:
#             # 没有元数据时返回通用模板
#             return (
#                 "【T｜技术属性层】\n"
#                 "分辨率：[ ]; 帧率：[ ] FPS; 画幅：[ ]; 动态范围：[ ]; 色彩空间：[ ]; 采样方式：[ ]; 编码格式：[ ]; 视频时长：[ ]秒\n"
#             )
        
#         # 构建实际有值的参数字段
#         params = []
        
#         # 分辨率
#         if metadata.get('resolution'):
#             params.append(f"分辨率：{metadata['resolution']}")
#         else:
#             params.append("分辨率：[ ]")
        
#         # 帧率
#         if metadata.get('fps'):
#             params.append(f"帧率：{metadata['fps']} FPS")
#         else:
#             params.append("帧率：[ ] FPS")
        
#         # 画幅/宽高比
#         if metadata.get('aspect_ratio'):
#             params.append(f"画幅：{metadata['aspect_ratio']}")
#         else:
#             params.append("画幅：[ ]")
        
#         # 动态范围
#         if metadata.get('dynamic_range'):
#             params.append(f"动态范围：{metadata['dynamic_range']}")
#         else:
#             params.append("动态范围：[ ]")
        
#         # 色彩空间/像素格式
#         if metadata.get('pixel_format'):
#             params.append(f"色彩空间/像素格式：{metadata['pixel_format']}")
#         else:
#             params.append("色彩空间：[ ]")
        
#         # 采样方式（色度子采样）
#         if metadata.get('chroma_subsampling'):
#             params.append(f"采样方式：{metadata['chroma_subsampling']}")
#         else:
#             params.append("采样方式：[ ]")
        
#         # 编码格式
#         if metadata.get('codec'):
#             params.append(f"编码格式：{metadata['codec']}")
#         else:
#             params.append("编码格式：[ ]")
        
#         # 视频时长
#         if metadata.get('duration'):
#             params.append(f"视频时长：{metadata['duration']}秒")
#         else:
#             params.append("视频时长：[ ]秒")
        
#         # 码率（如果有）
#         if metadata.get('bitrate'):
#             params.append(f"码率：{metadata['bitrate']}")
        
#         # 宽度高度（单独显示）
#         if metadata.get('width') and metadata.get('height'):
#             params.append(f"尺寸：{metadata['width']}x{metadata['height']}")
        
#         # 构建模板
#         template = "【T｜技术属性层】\n" + "； ".join(params) + "\n"
        
#         return template
    
#     def get_simple_prompt(self, task_description: str) -> str:
#         """
#         获取简单提示词
        
#         Args:
#             task_description: 任务描述
        
#         Returns:
#             简单提示词字符串
#         """
#         return f"{task_description}\n请严格按照要求完成任务，仅输出最终结果。"
    
#     def create_custom_prompt(self, template: str, **kwargs) -> str:
#         """
#         创建自定义提示词
        
#         Args:
#             template: 提示词模板，支持{variable}格式的占位符
#             **kwargs: 模板变量
        
#         Returns:
#             填充后的提示词字符串
#         """
#         try:
#             return template.format(**kwargs)
#         except KeyError as e:
#             raise ValueError(f"模板变量 {e} 未提供")

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
            "  * 基础要素：状态[稳定 / 晃动]、节奏[快 / 慢]、景别[大远景 / 全景 / 中景 / 近景 / 特写 / 大特写]、景深[浅 / 深]。\n"
            "  * 画面表征：构图[三分法 / 中轴线对称 / 框架式 / 几何引导线]；光影[高调 / 低调 / 自然漫射光 / 侧逆光 / 逆光 / 黄金时刻 / 硬光 / 软光]；色彩[高饱和 / 低饱和 / 冷调 / 暖调 / 对比色 / 同类色]。\n\n"
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
            "    镜头语法：镜头为运动机位。运镜采用[具体动作+方向]，状态 [稳定 / 晃动]，节奏[快/慢]，以 [标准景别词] 为主，景深 [浅 / 深]，视觉重心位于 [具体视觉核心区域]\n"
            "    构图遵循[标准构图词]，光影特征呈现为[标准光影词]，视觉色彩倾向于[标准色彩词]。\n\n"
            "  - 格式分支A2 (若判定为固定机位，格式必须对齐如下):\n"
            "    【A｜视听语言层】\n"
            "    镜头语法：镜头为固定机位，状态 [稳定 / 晃动]，节奏[快/慢]，以 [标准景别词] 为主，景深 [浅 / 深]，视觉重心位于 [具体视觉核心区域]\n"
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