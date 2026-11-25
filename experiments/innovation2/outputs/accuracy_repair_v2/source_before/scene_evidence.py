"""结构化场景证据与按需文字复核；不使用文件名、KB候选补全文字。"""
import base64
import json
import math
from pathlib import Path

LEGACY_SCENE_PROMPT = (
    '请观看视频并用中文简要回答，输出以下两部分，总长不超过300字：\n'
    '1.【场景描述】：一句话概括视频的空间场所、时间与画面主体。\n'
    '2.【文化视觉元素】：逐个列出画面中真实可见的中华文化相关符号（专有名词优先），'
    '如地标建筑、纪念设施、民俗物件、戏曲元素、科技园区、现代都市景观、文字标语等；'
    '只列出画面中真实可见的元素，禁止臆测；若无可靠文化元素，请输出"无明确文化符号"。'
)
STRUCTURED_SCENE_PROMPT = '''观看视频，仅输出一个JSON对象。描述画面证据，不做文化分类，不猜地标名称，不利用常识补齐文字。
主体与背景分开；仅凭“湖面”“石狮”“红墙”等通用元素不能命名具体场所。
无法识别身份时使用通用主体名称，将猜测放入uncertain_entities，禁止写进subject或visible_features。
文字必须逐字抄录，模糊字用?，不得凭建筑外形或上下文补字。
若出现匾额、招牌、标牌、碑刻等可能承载名称的区域，即使文字读不清也报告text_regions。
每个区域用time_ratio表示其清楚出现的时刻/视频总时长（0至1），bbox为该时刻整帧上归一化的[x1,y1,x2,y2]（0至1）。最多报告3个区域，优先主体名称牌。
格式：
{"scene":"空间场所、时间天气的客观概述","subject":"主要主体及行为（不猜专名）",
"visible_features":["真实可见的主体外观特征"],"background":["背景元素"],
"readable_text":[{"text":"逐字文字","legibility":"clear或partial或unreadable"}],
"text_regions":[{"kind":"匾额或标牌等","time_ratio":0.5,"bbox":[0.3,0.2,0.7,0.4]}],
"uncertain_entities":["身份猜测与原因，仅供审计，不参与检索"]}
'''
TEXT_REVIEW_PROMPT = '''请只转录图片中实际可辨认的文字，不识别建筑名称，不使用常识补字。图片依次为文字区域及其整帧上下文。
模糊字用?，没有文字返回空字符串。仅输出JSON：
{"text":"按原图阅读顺序抄录文字，不自行倒序或扩写","legibility":"clear或partial或unreadable"}'''


def json_object(raw):
    """允许Markdown代码围栏；拒绝尾随非JSON内容。"""
    if not isinstance(raw, str):
        raise ValueError("Expected response text")
    text = raw.strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[1].rsplit('```', 1)[0].strip()
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError('Expected JSON object')
    return value


def text_items(value):
    if not isinstance(value, list):
        return []
    return [x.strip() for x in value if isinstance(x, str) and x.strip()]


def readable_items(value):
    out = []
    for x in value if isinstance(value, list) else []:
        if isinstance(x, dict) and isinstance(x.get('text'), str):
            out.append({'text': x['text'].strip(), 'legibility': x.get('legibility', 'unreadable')})
    return out


def normalize_scene(raw):
    d = json_object(raw)
    if not all(isinstance(d.get(k), str) for k in ['scene', 'subject']):
        raise ValueError('scene and subject must be strings')
    regions = []
    for x in d.get('text_regions', []) if isinstance(d.get('text_regions'), list) else []:
        if not isinstance(x, dict):
            continue
        box, t = x.get('bbox'), x.get('time_ratio')
        def number(v):
            return type(v) in (int, float) and math.isfinite(v)
        if not number(t) or not 0 <= t <= 1 or not isinstance(box, list) or len(box) != 4:
            continue
        if not all(number(v) and 0 <= v <= 1 for v in box):
            continue
        if box[0] >= box[2] or box[1] >= box[3]:
            continue
        region = {'kind': str(x.get('kind', '文字区域')), 'time_ratio': t, 'bbox': box}
        if region not in regions:
            regions.append(region)
    return {'scene': d['scene'].strip(), 'subject': d['subject'].strip(),
            'visible_features': text_items(d.get('visible_features')),
            'background': text_items(d.get('background')),
            'readable_text': readable_items(d.get('readable_text')),
            'text_regions': regions[:3], 'uncertain_entities': text_items(d.get('uncertain_entities'))}


def retrieval_text(scene, reviews, reviewed=False):
    # 背景、猜测及模糊文字不成为主体身份证据；背景仍在原始审计JSON里保留。
    chunks = [scene['scene'], scene['subject']] + scene['visible_features']
    for item in (reviews if reviewed else scene['readable_text']):
        if item.get('legibility') == 'clear' and item.get('text') and not any(c in item['text'] for c in '?？□�'):
            chunks.append('可读文字：' + item['text'])
    return '\n'.join(dict.fromkeys(x for x in chunks if x))


def review_text_regions(video_path, regions, manager, output_dir):
    """最多3次多图视觉文字转录；区域由Pass-1定位，不等同于OCR检测器。"""
    import cv2
    if not regions:
        return {'status': 'not_needed', 'calls': 0, 'items': [], 'attempts': []}
    if not manager.is_glm_mode():
        return {'status': 'unsupported_backend', 'calls': 0, 'items': [], 'attempts': []}
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(video_path))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    result = {'status': 'completed', 'calls': 0, 'items': [], 'attempts': []}
    try:
        for i, region in enumerate(regions[:3]):
            attempt = dict(region, index=i)
            result['attempts'].append(attempt)
            try:
                frame_index = min(max(0, total - 1), int(region['time_ratio'] * max(0, total - 1)))
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                ok, frame = cap.read()
                if not ok:
                    raise ValueError('Cannot decode requested frame')
                h, w = frame.shape[:2]
                x1, y1, x2, y2 = region['bbox']
                # 稍微扩展定位框，减少截断首尾文字；保存原始像素，不进行生成式增强。
                left, top = max(0, int((x1-.02)*w)), max(0, int((y1-.02)*h))
                right, bottom = min(w, int((x2+.02)*w)), min(h, int((y2+.02)*h))
                crop = frame[top:bottom, left:right]
                if crop.size == 0:
                    raise ValueError('Empty text crop')
                content = [{'type': 'text', 'text': TEXT_REVIEW_PROMPT}]
                attempt['frame_index'] = frame_index
                attempt['pixel_bbox'] = [left, top, right, bottom]
                attempt['images'] = []
                for name, img in [('crop', crop), ('context', frame)]:
                    scale = min(1.0, 1600 / max(img.shape[:2]))
                    if scale < 1:
                        img = cv2.resize(img, None, fx=scale, fy=scale)
                    ok, data = cv2.imencode('.jpg', img)
                    if not ok:
                        raise ValueError('JPEG encoding failed')
                    path = output_dir / f'region_{i}_{name}.jpg'
                    path.write_bytes(data.tobytes())
                    attempt['images'].append(str(path))
                    content.append({'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + base64.b64encode(data).decode()}})
                result['calls'] += 1
                raw = manager.call_glm_api([{'role': 'user', 'content': content}], temperature=0)
                attempt['raw_response'] = raw
                parsed = json_object(raw)
                items = readable_items([parsed])
                if not items or items[0]['legibility'] not in {'clear', 'partial', 'unreadable'}:
                    raise ValueError('Invalid transcription response')
                attempt['result'] = items[0]
                result['items'].extend(items)
            except Exception as exc:
                attempt['error'] = str(exc)
                result['status'] = 'partial_failure'
    finally:
        cap.release()
    return result
