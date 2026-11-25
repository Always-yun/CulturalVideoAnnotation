"""
提示词管理模块 (EMCAST v2.3 多建筑解耦独立标注 + 中华文化维度受控版)
负责管理和生成符合学术级受控词表约束的提示词模板
深度修复多建筑形态被模型强行合并、糊弄描述的底层缺陷

创新点2升级：
- C 文化维度层由"北京地方文化硬编码"升级为面向中华文化的新五维受控分类；
- 支持注入知识库检索得到的 Top-K 文化符号候选（cultural_candidates），
  候选仅作参考，最终维度与符号须结合画面判定（动态 Prompt / RAG 插槽）；
- 五维分类与符号词表统一从 src.metrics.emcast_schema 获取，避免多处维护。
"""

from typing import Dict, Any, List, Optional
import os

from ..metrics.emcast_schema import CULTURAL_CATEGORIES, CULTURAL_SYMBOLS


class PromptManager:
    """提示词管理器，负责生成和管理统一的标准闭集约束提示词"""

    # 历史上基于视频路径关键词锁定场景范围的 _CATEGORY_SCENES / SCENE_KEYWORDS
    # 已随创新点2升级移除：文化维度改为由"中华文化五维闭集 + 知识库 Top-K 候选"
    # 动态驱动（见 _build_c_layer_instruction 与 src/knowledge 检索器）。

    # 技术属性层 / 元数据参考信息共用的字段定义： (metadata键, 展示标签, 单位后缀)
    _TECH_FIELDS = [
        ("resolution", "分辨率", ""),
        ("avg_frame_rate", "实际帧率", " FPS"),
        ("r_frame_rate", "标称帧率", " FPS"),
        ("aspect_ratio", "画幅", ""),
        ("dynamic_range", "动态范围", ""),
        ("pixel_format", "色彩空间/像素格式", ""),
        ("chroma_subsampling", "采样方式", ""),
        ("codec", "编码格式", ""),
        ("bitrate", "码率", ""),
        ("duration", "视频时长", "s"),
    ]
    _TECH_DEFAULTS = {"dynamic_range": "SDR"}

    def __init__(self):
        """初始化提示词管理器"""
        self._base_prompt = None
        self._template_prompt = None

    def _detect_scene_from_path(self, video_path: str) -> Dict[str, str]:
        """从视频路径推断场景范围（已停用）。

        文化维度不再由路径关键词锁定，统一走五维闭集 + 知识库 Top-K 候选，
        故此函数始终返回空信息，仅保留接口以兼容旧调用。
        """
        return {"category": "", "description": "", "location": ""}

    def _format_cultural_candidates(self, cultural_candidates: Optional[List[Dict[str, Any]]],
                                    controlled: bool = False,
                                    rejection: Optional[Dict[str, Any]] = None) -> str:
        """把知识库检索到的 Top-K 文化符号候选渲染为 C 层提示文本（动态 Prompt 插槽）

        controlled=False：候选仅作参考线索（自由判定）；
        controlled=True：候选升级为受控闭集（消融实验模式5）；
        rejection：拒识门控决策（score/margin/视觉证据三信号），注入检索置信度
        快照，使模型可感知"检索其实高度不确定"，避免顺候选强行匹配。
        """
        if not cultural_candidates:
            return ""
        if controlled:
            lines = [
                f"- 受控候选闭集（知识库检索 Top-{len(cultural_candidates)}）："
            ]
        else:
            lines = [
                f"- 知识库候选（检索 Top-{len(cultural_candidates)}，仅供参考，须结合画面实际判定，禁止照抄）："
            ]
        for i, s in enumerate(cultural_candidates, 1):
            aliases = s.get('aliases') or []
            alias_txt = f"；别名：{'、'.join(aliases)}" if aliases else ""
            lines.append(
                f"    {i}. {s.get('canonical_name', '')}"
                f"（维度：{s.get('cultural_dimension', '')}{alias_txt}；"
                f"典型视觉特征：{s.get('visual_features', '')}）"
            )
        # 检索置信度快照（分数感知注入：让模型看到候选之间的区分度）
        if rejection:
            sig = rejection.get("signals", {}) or {}
            t1, mg = sig.get("top1_score"), sig.get("margin_rel")
            if t1 is not None:
                conf = {"confident": "高", "uncertain": "低（区分度不足）",
                        "insufficient": "不足（证据不达标）"}.get(rejection.get("level", ""), "")
                lines.append(
                    f"    [检索置信度] Top1检索分={t1}，Top1-Top2相对分差={mg}，"
                    f"门控判定：{conf}")
        return "\n".join(lines) + "\n"

    def _build_c_dimension_hint(self) -> str:
        """五维闭集 + 各维度代表性符号锚点（取自统一受控词表 CULTURAL_SYMBOLS）"""
        lines = []
        for dim in CULTURAL_CATEGORIES:
            examples = "、".join(CULTURAL_SYMBOLS.get(dim, [])[:8])
            lines.append(f"    · {dim}：{examples}")
        return "\n".join(lines)

    def _build_c_layer_instruction(self, cultural_candidates: Optional[List[Dict[str, Any]]],
                                   controlled: bool = False,
                                   rejection: Optional[Dict[str, Any]] = None) -> str:
        """构建 C 文化维度层的判定指令（新五维受控 + 可选 Top-K 候选注入 + 门控拒识）

        rejection 三档（RejectionGate 产出，阈值来自验证集搜索）：
        - insufficient：检索分数/关键词/场景负信号任一不达标 → 知识库无可靠对应
          符号，强制输出 unknown_symbol（受控闭集同时解除，禁止错误匹配）；
        - uncertain：分数达标但 Top1-Top2 分差不足 → 候选区分度低，仅画面证据
          明确对应才可选，否则 unknown_symbol；
        - confident / None：维持原有判定规则。
        """
        dims = "、".join(CULTURAL_CATEGORIES)
        candidate_text = self._format_cultural_candidates(
            cultural_candidates, controlled=controlled, rejection=rejection)
        hint = self._build_c_dimension_hint()
        level = (rejection or {}).get("level", "")

        if level == "insufficient":
            sig = (rejection or {}).get("signals", {}) or {}
            reason = (rejection or {}).get("reason", "")
            gate_text = (
                f"- 【拒识指令｜检索证据不足，最高优先级】知识库检索置信度不足（{reason}；"
                f"Top1检索分={sig.get('top1_score')}，命中关键词数={sig.get('n_keywords')}），"
                "说明知识库中很可能没有与画面可靠对应的文化符号：\n"
                "  * 默认输出 unknown_symbol，并在价值指向中说明画面实际可见的视觉元素；\n"
                "  * 唯一例外：画面中出现与某个候选（规范名或别名）明确对应的决定性视觉证据"
                "（候选符号的专有名称文字、其独有标志性形态），此时才可输出该候选的规范名并写出对应依据；\n"
                "  * 若画面中清晰可读的专有名称不属于任何候选（如知识库未收录的建筑/物件名称），"
                "核心符号必须输出 unknown_symbol，并在价值指向中如实记录画面可见名称，"
                "严禁把该名称当作结论——错误匹配比拒识更严重。\n"
                "  * 候选列表仅作背景参考，不构成可选答案（闭集约束在本档位解除）。\n"
            )
            rule_text = ""  # 覆盖原有规则，以拒识指令为准
        elif level == "uncertain":
            sig = (rejection or {}).get("signals", {}) or {}
            gate_text = (
                f"- 【拒识指令｜候选区分度不足】Top1 与 Top2 检索分差过小"
                f"（相对分差={sig.get('margin_rel')} < 门限{sig.get('margin_thr')}），"
                "候选之间无法区分，存在强行匹配风险：\n"
                "  * 仅当画面证据能明确对应其中某一个候选（如出现其专有名称、独有标志性形态）时，"
                "才输出该候选的规范名，并在价值指向中写出对应的具体画面依据；\n"
                "  * 若画面无法与任一候选明确对应，必须输出 unknown_symbol，禁止凭猜测选择。\n"
            )
            rule_text = ""
        else:
            gate_text = ""
            if controlled:
                rule_text = (
                    "- 受控输出规则：核心符号必须且只能从上述受控候选闭集中选择（使用其规范名）；"
                    "若画面主体与任一候选都无法可靠对应（没有专有名称、独有形态等明确依据），"
                    "必须输出 unknown_symbol 并在价值指向中说明画面证据；"
                    "若画面中清晰可读的专有名称不属于任何候选（规范名或别名），"
                    "核心符号必须输出 unknown_symbol，并在价值指向中如实记录画面可见名称；"
                    "严禁借用候选之外的名称或自造名称充当结论。\n"
                )
            elif cultural_candidates:
                rule_text = ("- 候选使用规则：知识库候选仅作参考线索，不得直接照抄为结论；"
                             "候选与画面不符或画面证据不足时，核心符号必须输出 unknown_symbol，"
                             "并在价值指向中说明画面证据为何不足以匹配；"
                             "若画面中清晰可读的专有名称不属于任何候选（规范名或别名），"
                             "核心符号必须输出 unknown_symbol，并在价值指向中如实记录画面可见名称，"
                             "严禁强行匹配。\n")
            else:
                rule_text = ("- 无知识库候选辅助：核心符号完全依据画面证据判定，"
                             "画面证据不足时输出 unknown_symbol，严禁强行匹配。\n")
        return (
            "【C｜文化维度层】\n"
            "- 标注目标：界定视频的文化本体属性与符号学内涵。\n"
            f"- 分类标准：从中华文化五维闭集中选择最契合的一项——{dims}；"
            "单一维度优先，确属跨界时可用分号并列（最多2个）。\n"
            "- 各维度典型符号锚点（受控参考，非穷举）：\n"
            f"{hint}\n"
            f"{candidate_text}"
            "- 判定要求：以画面真实视觉证据为唯一依据，禁止脱离画面臆测；"
            "核心符号须精准锚定承载该文化内涵的关键视觉要素"
            "（如斗拱飞檐/红墙黄瓦、红色纪念设施、民俗物件与戏曲、科技地标、现代都市天际线等）。\n"
            f"{gate_text}"
            f"{rule_text}"
        )

    def _build_c_layer_template(self, rejection: Optional[Dict[str, Any]] = None) -> str:
        """构建 C 文化维度层的输出模板（闭集选择 + 门控拒识级联）

        insufficient 档的核心符号行默认 unknown_symbol（保留决定性视觉证据例外），
        使输出模板与拒识指令一致——修复旧实验"指令要求拒识、模板却引导照写画面"
        的冲突（非受控模式下模型顺着模板直写画面元素绕过拒识的根因之一）。
        """
        dims = "/".join(CULTURAL_CATEGORIES)
        level = (rejection or {}).get("level", "")
        if level == "insufficient":
            symbol_line = (
                "核心符号：unknown_symbol（知识库检索证据不足；"
                "仅当画面存在与某个候选（规范名或别名）明确对应的决定性视觉证据时，"
                "才可改写为该候选规范名；若画面可见的专有名称不在候选列表中，"
                "保持 unknown_symbol 并在价值指向中如实记录该名称）。\n"
            )
        elif level == "uncertain":
            symbol_line = (
                "核心符号：识别出承载该文化内涵的关键视觉锚点为[具体元素，尽量使用知识库规范名；"
                "候选区分度不足，无法与任一候选明确对应时必须输出 unknown_symbol]。\n"
            )
        else:
            symbol_line = (
                "核心符号：识别出承载该文化内涵的关键视觉锚点为[具体元素，尽量使用知识库规范名；"
                "画面证据不足时输出 unknown_symbol]。\n"
            )
        return (
            f"【C｜文化维度层】：该场景隶属于[{dims}中的一项（确属跨界可分号并列，最多2个）]。\n\n"
            f"{symbol_line}"
            "价值指向：[结合该符号的历史文化背景，阐明其文化内涵与时代价值]。\n"
        )

    def get_emcast_prompt(self, video_metadata: Optional[Dict[str, Any]] = None,
                          video_path: Optional[str] = None,
                          cultural_candidates: Optional[List[Dict[str, Any]]] = None,
                          controlled_output: bool = False,
                          rejection: Optional[Dict[str, Any]] = None) -> str:
        """
        获取全面对接多建筑独立分层拆分规范的EMCAST六维分层标注提示词

        Args:
            video_metadata: ffprobe 解析的视频技术元数据
            video_path: 视频路径（预留给场景/地域感知）
            cultural_candidates: 知识库检索得到的 Top-K 文化符号候选（dict 列表），
                由 src.knowledge 检索器产出；None 表示不注入候选，仅按五维闭集判定。
            controlled_output: 受控输出模式（消融实验模式5）：候选作为闭集，
                核心符号必须从候选中选择或输出 unknown_symbol；
                False（默认）时候选仅作参考线索（保持既有行为）。
            rejection: 拒识门控决策（RejectionGate 三信号产出）；
                insufficient=强制拒识，uncertain=区分度警告，None/confident=旧行为。
        """
        scene_info = self._detect_scene_from_path(video_path)
        scene_category = scene_info.get("category", "")
        scene_description = scene_info.get("description", "")
        scene_location = scene_info.get("location", "")

        tech_layer_template = self._generate_tech_layer_template(video_metadata)
        c_layer_instruction = self._build_c_layer_instruction(
            cultural_candidates, controlled=controlled_output, rejection=rejection)
        c_layer_template = self._build_c_layer_template(rejection)

        # 构建播放速度检测指令（优先级：ffprobe帧率检测 > LLM视觉验证）
        speed_status = "[正常速度]"
        fps_ratio_info = ""
        visual_speed_instruction = ""
        
        if video_metadata:
            status = video_metadata.get("speed_status")
            fps_ratio = video_metadata.get("fps_ratio")
            r_frame = video_metadata.get("r_frame_rate")
            avg_frame = video_metadata.get("avg_frame_rate")
            
            # 格式化帧率信息
            if fps_ratio is not None:
                fps_ratio_info = f"（标称帧率{r_frame}fps，实际帧率{avg_frame}fps，比值{fps_ratio:.2f}）"
            
            # 确定ffprobe判定结果
            if status == "慢放":
                speed_status = "慢放"
            elif status == "快放":
                speed_status = "快放"
            elif status == "正常":
                speed_status = "正常速度"
        
        # 构建播放速度检测指令（ffprobe仅作为辅助信息，视觉时间尺度判断为主）
        # 延时摄影不能仅通过 FPS 判断；当 FPS 正常时，必须结合画面视觉变化继续分析。
        visual_speed_instruction = (
            f"  * 播放速度效果检测：\n"
            f"    - ffprobe仅提供编码参数参考，帧率信息不一定代表真实拍摄时间间隔。判断延时摄影时，"
            f"应关注连续画面之间的真实视觉变化速度，而不是只依据 FPS。\n"
            f"    - 如果 ffprobe明确检测到慢放/快放，可作为参考；但若 ffprobe显示正常速度，仍须继续结合视觉判断。\n"
            f"    - 视觉判断要点：\n"
            f"      ▸ 延时摄影：云层快速移动、日出日落/光影变化明显加速、星轨变化、车流/人群变化速度明显超过现实、"
            f"植物生长/天气变化等长期过程被压缩。\n"
            f"      ▸ 慢放：人物动作明显缓慢、运动过程被拉长、动作细节展开。\n"
            f"      ▸ 快放：普通运动速度明显加快，但不是长期时间压缩效果。\n"
            f"      ▸ 倒放：事件发展顺序与正常时间相反。\n"
            f"    - 选项：[正常速度/慢放/快放/延时摄影/倒放]\n\n"
        )

        if scene_category:
            task_context = (
                f"【任务上下文】：本次标注任务的视频素材专属为「{scene_description}」。"
                f"视频中出现的场所与地标建筑（如{scene_location}）均为相关活动场所。"
                f"请将你的视觉辨识与语义空间严格锁定于此，禁止泛化或盲目类比至其他不相关区域。\n\n"
            )
        else:
            task_context = ""

        prompt = (
            "你是一位专业的中华文化与视听语言分析师，严格遵循「EMCAST六维分层标注体系」对视频进行标注。\n"
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
            # C 文化维度层：新五维受控闭集 + 可选 Top-K 知识库候选（由方法动态生成）
            "{c_layer_instruction}\n"
            "【A｜视听语言层】\n"
            "- 标注目标：使用电影叙事学闭集术语，客观描述影像的拍摄手法与视听组织范式。\n"
            "- 核心禁止规则：严禁在最终输出中包含任何诸如‘若镜头运动详细描述：’等带有控制逻辑的提示短语。直接根据物理画面机位判定结果，平铺直叙对应结构的描述语句。\n"
            "- 闭集受控词表集合：\n"
            "  * 运镜：移动类[推（前）/拉（后）/升（上）/降（下）/平移（左/右）]；旋转类[摇摄（左/右/俯/仰）/滚转/变焦]；追踪类[侧向追踪/尾随跟拍/前方领拍/弧形追踪/环绕拍摄]。\n"
            "  * 基础要素：状态[稳定/晃动]、节奏[快/慢]、景别[大远景/全景/中景/近景/特写/大特写]、景深[浅/深]。\n"
            "  * 画面表征：构图[三分法/中轴线对称/框架式/几何引导线]；光影[高调/低调/自然漫射光/侧逆光/逆光/黄金时刻/硬光/软光]；色彩[高饱和/低饱和/冷调/暖调/对比色/同类色]。\n\n"
            "{visual_speed_instruction}"
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
            "【M｜主体行为层】按以下统一格式输出（多建筑主体必须在‘承载主体外观’中逐一换行或分句清晰陈述，严禁合并）。"
            "标记为【仅占比>70%时追加】的部分，只有当活跃主体占比 > 70% 时才写入；占比 <= 70% 时必须完全省略这些部分，不得出现任何活跃主体动态或关系的字眼：\n"
            "    【M｜主体行为层】：视觉焦点包含承载主体：[列出画面中出现的所有核心建筑/场馆主体的名称或代称]【仅占比>70%时追加：与 活跃主体：[名称]】\n"
            "    承载主体外观：[必须逐一、分开清晰描述各个核心建筑的具体几何形态与对应材质，多建筑严禁共用一段含糊句。格式参考：左侧/主体一呈现出...，外立面材质主要为...；右侧/主体二呈现出...，外立面材质主要为...]\n"
            "    【仅占比>70%时追加】活跃主体动态：主体正在进行[具体动作]，状态呈现为[行为方式/节奏]。\n"
            "    【仅占比>70%时追加】主体关系：描述[活跃主体]与[各个承载主体]的空间交互逻辑。\n"
            "    若画面涉及文字，文字符号：[\"提取的文字内容\"]\n\n"
            # C 文化维度层输出模板：新五维闭集选择（由方法动态生成，不再硬编码单一维度）
            "{c_layer_template}\n"
            "【A｜视听语言层】按以下统一格式平铺直叙输出（严禁夹杂控制条件括号）：\n"
            "    【A｜视听语言层】\n"
            "    镜头语法：镜头为[运动机位/固定机位]。若为运动机位，需紧接着写明具体运镜方式，即“运镜采用[具体动作+方向]，”；若为固定机位则不写这半句，直接续写：状态[稳定/晃动]，节奏[快/慢]，以[标准景别词]为主，景深[浅/深]，视觉重心位于[具体视觉核心区域]\n"
            "    播放速度效果：[正常速度/慢放/快放/延时摄影/倒放]\n"
            "    构图遵循[标准构图词]，光影特征呈现为[标准光影词]，视觉色彩倾向于[标准色彩词]。\n\n"
            "【S｜整体叙事层】：[密集化描述视频从空间组织到时序演进的连贯过程]。\n\n"
             f"{tech_layer_template}"
            "现在，请严格执行多主体拆分逻辑与判定规则，仅输出干净、标准、无逻辑残留的最终标注结果。"
        )
        return prompt.format(
            speed_status=speed_status,
            visual_speed_instruction=visual_speed_instruction,
            c_layer_instruction=c_layer_instruction,
            c_layer_template=c_layer_template,
        )

    def _generate_tech_layer_template(self, metadata: Optional[Dict[str, Any]]) -> str:
        """根据底层解析的硬核元数据，构建闭环自动对齐的【T｜技术属性层】

        无论是否传入 metadata，都走同一套字段组装逻辑：
        有值则展示实际值，无值则回退为占位符 "[ ]"（或该字段的默认值，如动态范围默认 SDR）。
        """
        metadata = metadata or {}
        parts = []
        for key, label, unit in self._TECH_FIELDS:
            value = metadata.get(key, self._TECH_DEFAULTS.get(key, "[ ]"))
            parts.append(f"{label}：{value}{unit}")
        return "【T｜技术属性层】\n" + "；".join(parts) + "。\n"

    def get_simple_prompt(self, task_description: str) -> str:
        """获取极简约束提示词"""
        return f"{task_description}\n请严格按照要求完成任务，仅输出最终标准化结果。"

    def create_custom_prompt(self, template: str, **kwargs) -> str:
        """支持模板化、动态插值的自定义提示词生成"""
        try:
            return template.format(**kwargs)
        except KeyError as e:
            raise ValueError(f"模板插值变量 {e} 未完整提供")