"""Development policy: hypotheses retrieve; observed video evidence verifies independently."""
import copy
import json
import re
from .scene_evidence import contextual_evidence_text, recover_scene, review_text_regions
from ..knowledge.identity_verifier_v2 import extract_keyframes


def parse_verifier_response(raw):
    from .scene_evidence import json_object
    try:
        return json_object(raw), 'valid'
    except json.JSONDecodeError as exc:
        if not exc.msg.startswith('Invalid \\escape'):
            raise
        # Preserve an invalid JSON escape as a literal backslash, without changing words.
        repaired = re.sub(r'\\(?!["\\/bfnrtu])', lambda _: '\\\\', raw)
        return json_object(repaired), 'literal_backslash_escape_repair'


def prepare_hybrid_evidence(legacy, structured, manager, video_path, output_dir):
    prepared = copy.deepcopy(structured)
    if not prepared.get('structured_scene'):
        scene, repair = recover_scene(prepared.get('scene_description_raw', ''), manager.call_glm_api)
        prepared['structured_scene'] = scene
        prepared['scene_repair'] = repair
        prepared['text_recognition'] = review_text_regions(
            video_path, scene['text_regions'], manager, output_dir)
    review = prepared.get('text_recognition', {})
    observed = contextual_evidence_text(prepared['structured_scene'], review.get('items', []),
                       reviewed=review.get('status') in {'completed', 'partial_failure'})
    hypothesis = str(legacy.get('scene_description', '')).strip()
    if not hypothesis:
        raise ValueError('Missing legacy hypothesis evidence')
    prepared['scene_description'] = observed
    prepared['retrieval_scene_text'] = hypothesis + '\n' + observed
    prepared['hypothesis_provenance'] = {'source': 'cached_legacy_pass1',
        'text': hypothesis, 'use': 'retrieval_only_not_identity_evidence'}
    prepared['scene_evidence_version'] = 'hybrid_v3'
    return prepared


class IndependentVideoVerifier:
    """No retrieval hypotheses, retrieval scores, or unreviewed reference images."""
    SYSTEM_PROMPT = '''你是独立的视频文化实体核验器。输入只有待核验候选的知识库定义、观察记录和视频关键帧；不提供检索假设和GT。
判断视频是否确实呈现候选定义覆盖的文化实体。以关键帧为主，观察记录可能有误，必须核对。
候选可以是具体建筑、区域、建筑群、民俗物件、表演或活动；按规范名、别名、类型和典型场景共同确定粒度。
区域/建筑群不要求全景全部入镜，民俗活动不要求完整流程，但必须有能区分候选的可见证据组合。
没有名称文字不等于没有身份；可由独特外观、布局、服饰、物件与活动组合判断。不要要求画面显示无法直接观察的材料细节或精确尺寸。
通用红墙/高楼/人群、仅同类或同景区不足以接受。主体若是候选范围外的另一个具体实体，必须拒绝。不能仅凭背景名称或知识库描述推断主体。
不确定时拒绝；接受时必须写出视频中实际可见的具体依据。输出JSON，不输出其他文字：
{"identity_status":"accept_exact_identity或reject_related_but_not_exact或reject_insufficient_evidence","reason":"理由","visual_identity_evidence":"可见依据","text_identity_evidence":"可读文字或none","hierarchy_relation":"none或parent_entity或child_entity或same_scenic_area","confidence":0.0}'''

    def __init__(self, kb, caller):
        self.kb, self.caller = kb, caller

    def decide(self, video_id, video_path, scene_description, candidates, pred_symbol='', **kwargs):
        candidate = next((c for c in candidates if c.get('canonical_name') == pred_symbol), None)
        if candidate is None:
            raise ValueError('Selected entity is not in candidate set')
        symbol = self.kb.get(candidate['symbol_id'])
        if not symbol:
            raise ValueError('Selected entity missing from KB')
        frames = extract_keyframes(video_path, video_id, num_frames=4)
        if not frames:
            raise ValueError('Video frames unavailable; not a valid semantic rejection')
        import base64, io
        from PIL import Image
        content = [{'type': 'text', 'text': '以下图片均为待识别视频的关键帧，不是候选参考图。'}]
        for path in frames:
            with Image.open(path) as im:
                im = im.convert('RGB'); im.thumbnail((1280, 1280))
                buf = io.BytesIO(); im.save(buf, format='JPEG', quality=90)
                content.append({'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+base64.b64encode(buf.getvalue()).decode()}})
        definition = {k:symbol.get(k, '') for k in ('canonical_name','aliases','symbol_type','visual_features','typical_scene','cultural_description')}
        content.append({'type':'text','text':'候选定义：\n'+json.dumps(definition,ensure_ascii=False)+'\n观察记录（不能替代关键帧）：\n'+str(scene_description)[:2500]})
        messages = [{'role':'system','content':self.SYSTEM_PROMPT},{'role':'user','content':content}]
        raw = self.caller(messages, temperature=0)
        from ..knowledge.identity_verifier_v2 import STATUS_ACCEPT, STATUS_RELATED, STATUS_INSUFFICIENT
        result, format_status = parse_verifier_response(raw)
        if result.get('identity_status') not in {STATUS_ACCEPT, STATUS_RELATED, STATUS_INSUFFICIENT}:
            raise ValueError('Malformed verifier decision; do not score as unknown')
        if not isinstance(result.get('reason'), str) or not result['reason'].strip():
            raise ValueError('Verifier must provide a reason')
        accepted = result['identity_status'] == STATUS_ACCEPT
        if accepted and (not isinstance(result.get('visual_identity_evidence'), str) or
                         result['visual_identity_evidence'].strip().lower() in {'','none','无'}):
            raise ValueError('Accepted identity without observable supporting evidence')
        return {'video_id':video_id,'final_symbol':pred_symbol if accepted else '',
                'final_status':result['identity_status'],'final_reason':result['reason'],
                'verification_required':True,'decisions':[dict(result,symbol_id=candidate['symbol_id'])],
                'n_llm_calls':1,'reference_images_used':0,'retrieval_hypotheses_used':False,
                'frame_paths':frames,'raw_response':raw,'response_format_status':format_status}
