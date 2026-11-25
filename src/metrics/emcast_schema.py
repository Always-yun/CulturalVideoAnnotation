"""
EMCAST 标注体系 Schema 定义
定义六维分层结构、文化分类标准、受控词表等核心规范
供评估指标计算统一调用
"""

from typing import Dict, List, Tuple

EMCAST_LAYERS: List[Tuple[str, str, str]] = [
    ("E", "场景环境层", "scene_environment"),
    ("M", "主体行为层", "subject_behavior"),
    ("C", "文化维度层", "cultural_dimension"),
    ("A", "视听语言层", "audio_visual_language"),
    ("S", "整体叙事层", "narrative_structure"),
    ("T", "技术属性层", "technical_attributes"),
]

EMCAST_LAYER_KEYS: List[str] = [layer[2] for layer in EMCAST_LAYERS]

EMCAST_LAYER_HEADERS: Dict[str, str] = {
    "E": "【E｜场景环境层】",
    "M": "【M｜主体行为层】",
    "C": "【C｜文化维度层】",
    "A": "【A｜视听语言层】",
    "S": "【S｜整体叙事层】",
    "T": "【T｜技术属性层】",
}

# =====================================================================
# 文化五维分类（2026-10 重新冻结，创新点2升级：面向中华文化）
# 旧五维 → 新五维：
#   古都文化 → 古城与历史文化；红色文化 → 红色文化；
#   京味文化 → 民族与民俗文化；创新科技文化 → 科技与创新文化；
#   国际时尚文化 → 现代城市与国际文化。
# 北京为当前实验案例（知识库 region=北京），不再作为覆盖范围上限。
# =====================================================================
CULTURAL_CATEGORIES: List[str] = [
    "古城与历史文化",
    "红色文化",
    "民族与民俗文化",
    "科技与创新文化",
    "现代城市与国际文化",
]

# 维度码（与 chinese_cultural_symbols_v2 的 dimension_code 一致）
CULTURAL_DIMENSION_CODES: Dict[str, str] = {
    "古城与历史文化": "ANCIENT",
    "红色文化": "RED",
    "民族与民俗文化": "FOLK",
    "科技与创新文化": "TECH",
    "现代城市与国际文化": "MODERN",
}

# 维度码 → 维度名（反向索引）
CULTURAL_CODE_TO_NAME: Dict[str, str] = {v: k for k, v in CULTURAL_DIMENSION_CODES.items()}

# 旧五维 → 新五维（兼容历史标注/评测数据的迁移）
LEGACY_CULTURAL_DIMENSION_MAP: Dict[str, str] = {
    "古都文化": "古城与历史文化",
    "红色文化": "红色文化",
    "京味文化": "民族与民俗文化",
    "创新科技文化": "科技与创新文化",
    "国际时尚文化": "现代城市与国际文化",
}


def normalize_cultural_category(name: str) -> str:
    """把任意旧/新维度名归一化到新五维；无法识别时返回空串。

    多标签（以 ; 分隔）逐个映射后以 ; 重组，顺序保持不变。
    """
    if not name:
        return ""
    parts = [p.strip() for p in name.split(";") if p.strip()]
    out = []
    for p in parts:
        if p in CULTURAL_DIMENSION_CODES:
            out.append(p)
        elif p in LEGACY_CULTURAL_DIMENSION_MAP:
            out.append(LEGACY_CULTURAL_DIMENSION_MAP[p])
    return ";".join(out)


# C 层受控符号词表：以中华文化符号知识库 47 条 canonical_name 为权威实体，
# 并补充通用构件/民俗/科技/都市词。材质类视觉词统一归入 VISUAL_SYMBOLS。
CULTURAL_SYMBOLS: Dict[str, List[str]] = {
    "古城与历史文化": [
        # 知识库实体（北京实验案例）
        "故宫", "紫禁城", "太和殿", "天坛", "祈年殿", "钟鼓楼", "北京中轴线",
        "中轴线", "正阳门", "前门", "景山", "什刹海", "角楼",
        # 通用历史文化符号
        "长城", "颐和园", "圆明园", "皇城", "斗拱", "飞檐", "青砖灰瓦",
        "琉璃瓦", "牌楼", "石狮", "红墙", "黄瓦", "榫卯结构", "藻井",
        "匾额", "碑刻", "护城河", "古城墙", "古遗址",
    ],
    "红色文化": [
        # 知识库实体
        "北大红楼", "天安门广场", "天安门", "人民英雄纪念碑", "卢沟桥",
        "宛平城", "中国国家博物馆", "国家博物馆", "双清别墅",
        "中国人民革命军事博物馆", "军事博物馆", "李大钊故居",
        # 通用红色文化符号
        "人民大会堂", "革命博物馆", "国旗", "国徽", "庆典", "阅兵",
        "红色标语", "纪念馆", "烈士纪念碑", "军礼", "党旗", "革命旧址",
    ],
    "民族与民俗文化": [
        # 知识库实体
        "胡同", "四合院", "京剧", "兔儿爷", "兔爷", "京韵大鼓",
        "北京烤鸭", "烤鸭", "北京庙会", "庙会", "剪纸", "鸽哨", "大栅栏",
        # 通用民族民俗符号
        "老字号", "相声", "评书", "冰糖葫芦", "炸酱面", "豆汁",
        "景泰蓝", "玉雕", "风筝", "皮影戏", "锣鼓", "茶馆", "非遗",
        "民族服饰", "传统节日", "民俗活动",
    ],
    "科技与创新文化": [
        # 知识库实体
        "中关村", "中关村科学城", "奥林匹克公园", "鸟巢", "国家体育场",
        "水立方", "国家游泳中心", "北京大学", "清华大学",
        "未来科学城", "国家会议中心", "首钢园",
        # 通用科技创新符号
        "科技园区", "实验室", "自动驾驶", "数字科技", "人工智能",
        "大数据", "云计算", "科技标识", "芯片", "机器人", "高等学府",
    ],
    "现代城市与国际文化": [
        # 知识库实体
        "三里屯", "798艺术区", "798", "CBD", "国贸", "望京",
        "王府井", "郎园Station", "北京坊",
        # 通用现代国际都市符号
        "亮马河", "使馆区", "国际品牌", "奢侈品", "时装周", "高端消费",
        "摩天大楼", "现代艺术", "画廊", "音乐节", "时尚街区", "外籍人士",
        "中央商务区",
    ],
}

VISUAL_SYMBOLS: List[str] = [
    "玻璃幕墙", "金属铝板", "清水混凝土", "青砖灰瓦", "琉璃瓦",
    "曲面", "流线型", "轴对称", "矩形矩阵", "飞檐斗拱",
    "框架式构图", "三分法", "中轴线对称", "几何引导线",
    "高调", "低调", "自然漫射光", "侧逆光", "逆光",
    "高饱和", "低饱和", "冷调", "暖调", "对比色", "同类色"
]

EMCAST_SCHEMA = {
    "layers": EMCAST_LAYERS,
    "layer_keys": EMCAST_LAYER_KEYS,
    "layer_headers": EMCAST_LAYER_HEADERS,
    "cultural_categories": CULTURAL_CATEGORIES,
    "cultural_dimension_codes": CULTURAL_DIMENSION_CODES,
    "legacy_cultural_dimension_map": LEGACY_CULTURAL_DIMENSION_MAP,
    "cultural_symbols": CULTURAL_SYMBOLS,
    "visual_symbols": VISUAL_SYMBOLS,
}

def parse_emcast_format(text: str) -> Dict[str, str]:
    """
    解析EMCAST标准格式文本，提取各层内容
    
    Args:
        text: EMCAST格式的标注文本
        
    Returns:
        各层内容的字典，key为层标识(E/M/C/A/S/T)
    """
    result = {layer[0]: "" for layer in EMCAST_LAYERS}
    
    if not text:
        return result
    
    current_layer = None
    for line in text.split('\n'):
        line = line.strip()
        
        for layer_code, _, _ in EMCAST_LAYERS:
            header = EMCAST_LAYER_HEADERS[layer_code]
            if header in line or line.startswith(f"【{layer_code}｜"):
                current_layer = layer_code
                content_start = line.find(header) + len(header)
                content = line[content_start:].strip()
                if content and not content.startswith("："):
                    if content.startswith("："):
                        content = content[1:].strip()
                    result[current_layer] = content
                break
        
        if current_layer and line and not any(header in line for header in EMCAST_LAYER_HEADERS.values()):
            if result[current_layer]:
                result[current_layer] += "\n" + line
            else:
                result[current_layer] = line
    
    return result

def extract_layer_text(text: str, layer_code: str) -> str:
    """
    提取指定层的文本内容
    
    Args:
        text: EMCAST格式文本
        layer_code: 层标识(E/M/C/A/S/T)
        
    Returns:
        该层的文本内容
    """
    parsed = parse_emcast_format(text)
    return parsed.get(layer_code, "")
