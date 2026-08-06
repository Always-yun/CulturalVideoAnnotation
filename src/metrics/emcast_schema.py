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

CULTURAL_CATEGORIES: List[str] = [
    "古都文化",
    "红色文化",
    "京味文化",
    "创新科技文化",
    "国际时尚文化",
]

CULTURAL_SYMBOLS: Dict[str, List[str]] = {
    "古都文化": [
        "故宫", "中轴线", "钟鼓楼", "长城", "天坛", "颐和园", 
        "圆明园", "皇城", "斗拱", "飞檐", "青砖灰瓦", "琉璃瓦", 
        "四合院", "胡同", "牌楼", "石狮", "红墙", "黄瓦",
        "榫卯结构", "藻井", "匾额", "碑刻", "护城河"
    ],
    "红色文化": [
        "天安门", "人民英雄纪念碑", "人民大会堂", "国家博物馆",
        "革命博物馆", "国旗", "国徽", "庆典", "阅兵", 
        "红色标语", "纪念馆", "烈士纪念碑", "军礼", "党旗"
    ],
    "京味文化": [
        "胡同", "四合院", "老字号", "京剧", "相声", "评书",
        "冰糖葫芦", "炸酱面", "豆汁", "景泰蓝", "玉雕", 
        "兔爷", "风筝", "皮影戏", "庙会", "锣鼓", "茶馆"
    ],
    "创新科技文化": [
        "中关村", "科技园区", "实验室", "自动驾驶", "数字科技",
        "人工智能", "大数据", "云计算", "玻璃幕墙", "金属铝板",
        "流线型", "曲面", "现代建筑", "科技标识", "芯片", "机器人"
    ],
    "国际时尚文化": [
        "三里屯", "亮马河", "使馆区", "国际品牌", "奢侈品",
        "时装周", "高端消费", "国际旗帜", "摩天大楼", "玻璃大厦",
        "现代艺术", "画廊", "音乐节", "时尚街区", "外籍人士"
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
