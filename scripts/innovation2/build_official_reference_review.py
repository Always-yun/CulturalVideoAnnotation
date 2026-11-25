"""Build a local photo review document from explicitly inspected candidates."""
import csv
from datetime import datetime
import hashlib
import html
import json
from pathlib import Path
import re

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'archives/knowledge_base_history_20261119/reference_images_official_20261119'


def page_date(row):
    if row.get('page_publication_date'):
        return row['page_publication_date']
    cache = OUT / 'pages' / (hashlib.sha256(row['source_page_url'].encode()).hexdigest()[:16] + '.html')
    if not cache.is_file():
        return None
    raw = cache.read_text(errors='replace')
    if 'ZGC-International-Innovation-Center-Completion-zh' in row['source_page_url']:
        # The official article's own embedded record pairs this date with the
        # completion excerpt, unlike the many unrelated dates in its nav feed.
        fragments = []
        for match in re.finditer(r'self\.__next_f\.push\(', raw):
            try:
                value, _ = json.JSONDecoder().raw_decode(raw, match.end())
                if isinstance(value, list) and len(value) > 1 and isinstance(value[1], str):
                    fragments.append(value[1])
            except ValueError:
                pass
        stream = ''.join(fragments) + raw
        for match in re.finditer(r'"date":"([0-9-]+)","excerpt":"([^"]*)"', stream):
            if 'MAD建筑事务所设计的位于北京的中关村国际创新中心' in match.group(2):
                return match.group(1)
    m = re.search(r'var\s+storyInfo\s*=\s*', raw)
    if m:
        try:
            info, _ = json.JSONDecoder().raw_decode(raw, m.end())
            value = info.get('publishTime') or info.get('publish_time')
            if isinstance(value, str):
                return value
        except ValueError:
            pass
    soup = BeautifulSoup(raw, 'html.parser')
    for node in soup.select('time,.date,.time,.pubtime,.publishTime'):
        m = re.search(r'20\d{2}[-/]\d{1,2}[-/]\d{1,2}(?:\s+\d{2}:\d{2})?', node.get_text(' ', strip=True))
        if m:
            return m.group()
    return None


def main():
    confirmation_path = OUT / 'confirmed_reference_images.json'
    confirmation = json.loads(confirmation_path.read_text()) if confirmation_path.exists() else {}
    approved_ids = set(confirmation.get('human_confirmed_candidate_ids', []))
    kb_path = ROOT / 'archives/knowledge_base_history_20261119/chinese_cultural_symbols_v3.json'
    kb = json.loads(kb_path.read_text())
    names = {s['symbol_id']: s['canonical_name'] for s in kb['symbols']}
    names.update(EXT_GREAT_HALL='人民大会堂（原知识库未收录）', EXT_TANGHULU='冰糖葫芦（原知识库未收录）')
    candidates = {r['candidate_id']: r for f in (OUT / 'candidates').glob('*.json') for r in [json.loads(f.read_text())]}
    decisions = {}
    for path in sorted(OUT.glob('visual_reviews_*.json')):
        for row in json.loads(path.read_text()):
            decisions[row['candidate_id']] = row
    selected = []
    for cid, review in decisions.items():
        if review['review_status'] != 'assistant_passed':
            continue
        row = dict(candidates[cid])
        assert row['download_status'] == 'downloaded'
        path = ROOT / row['local_path']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256']
        row.update(symbol_id=review['assigned_symbol_id'], canonical_name=names.get(review['assigned_symbol_id'], review['assigned_symbol_id']),
                   visual_review=review, verification_status='assistant_reviewed',
                   use_for_retrieval=False, human_verified=False,
                   page_publication_date=page_date(row),
                   image_capture_date=review.get('image_capture_date') or row.get('image_capture_date'),
                   capture_date_evidence=review.get('capture_date_evidence') or row.get('capture_date_evidence'))
        if cid in approved_ids:
            row.update(verification_status='human_verified', human_verified=True,
                       use_for_retrieval=True, confirmation_source='explicit_user_message',
                       confirmed_at=confirmation.get('confirmed_at'))
        selected.append(row)
    selected.sort(key=lambda r: (r['symbol_id'], r['candidate_id']))
    (OUT / 'selected_references.json').write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT / 'visual_review_decisions.json').write_text(json.dumps(list(decisions.values()), ensure_ascii=False, indent=2), encoding='utf-8')
    fields = ['symbol_id', 'canonical_name', 'candidate_id', 'local_path', 'width', 'height',
              'source_organization', 'page_publication_date', 'image_capture_date', 'source_page_url',
              'image_url', 'verification_status', 'human_verified', 'use_for_retrieval']
    with (OUT / 'selected_references.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        w.writerows({key: row.get(key) for key in fields} for row in selected)
    grouped = {}
    for row in selected:
        grouped.setdefault(row['symbol_id'], []).append(row)
    # Build a staged version with reviewed candidates only; no old logo/photo
    # records are silently promoted, and no human approval is fabricated.
    for symbol in kb['symbols']:
        symbol['reference_images'] = grouped.get(symbol['symbol_id'], [])
    kb.update(version='v4_official_photo_candidates_20261119',
              reference_collection_status=('user confirmed' if selected and all(r['human_verified'] for r in selected)
                                           else 'assistant visually screened; pending user confirmation'),
              base_kb_sha256=hashlib.sha256(kb_path.read_bytes()).hexdigest())
    (ROOT / 'archives/knowledge_base_history_20261119/chinese_cultural_symbols_v4_official_candidates.json').write_text(json.dumps(kb, ensure_ascii=False, indent=2), encoding='utf-8')
    esc = html.escape
    cards = []
    for sid, rows in grouped.items():
        cards.append(f'<section><h2>{esc(names.get(sid,sid))} <small>{len(rows)}张</small></h2><div class="grid">')
        for row in rows:
            src = Path(row['local_path']).relative_to(OUT.relative_to(ROOT)).as_posix()
            date = row['page_publication_date'] or '页面日期未注明'
            capture = row['image_capture_date'] or '未注明，不能用发布日期代替'
            label = f"{row['canonical_name']} · {row['width']}×{row['height']}"
            cards.append(f'''<article><a href="{esc(src)}" target="_blank"><img loading="lazy" src="{esc(src)}" alt="{esc(label)}"></a>
<div class="body"><label><input type="checkbox" value="{row['candidate_id']}"> 我已核对这张图，可用于参考检索</label>
<p class="reason">{esc(row['visual_review']['reason'])}</p><p>{row['width']}×{row['height']} 原始像素 · {esc(row['candidate_id'])}</p>
<p>来源：{esc(row.get('source_organization') or '')}<br>页面发布：{esc(str(date))}<br>拍摄日期：{esc(str(capture))}</p>
<p><a target="_blank" href="{esc(row['source_page_url'])}">打开官方来源页</a> · <a target="_blank" href="{esc(row['image_url'])}">官方原图直链</a> · <a target="_blank" href="{esc(src)}">打开本地原图</a></p></div></article>''')
        cards.append('</div></section>')
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>官方实景参考图审核</title><style>
body{font:16px/1.6 system-ui,sans-serif;margin:0;background:#f4f5f7;color:#17212c}header,main{max-width:1450px;margin:auto;padding:24px}header{background:white}h1{margin:0;font-size:30px}small{font-weight:400;color:#667}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(350px,1fr));gap:20px}article{background:white;border-radius:10px;overflow:hidden}img{width:100%;height:300px;object-fit:contain;background:#eef0f3}.body{padding:16px}.body p{font-size:13px;overflow-wrap:anywhere}.body .reason{font-size:15px}a{color:#176ca7}label{font-weight:600}button{background:#176ca7;color:white;border:0;border-radius:6px;padding:12px 20px;cursor:pointer}.note{background:#fff4d8;padding:12px}section{margin-bottom:36px}.toolbar{position:sticky;top:0;background:#fff;padding:12px;z-index:1;border-bottom:1px solid #ddd}</style>
<header><h1>官方实景参考图审核</h1><p>原始照片独立下载；点图片可查看本地原尺寸。已由助手目视初筛，不冒充人工确认。</p><p class="note">只展示本次新找到且通过目视初筛的照片。原149张旧图不在此页。页面发布日期与照片拍摄日期分别记录；未注明的拍摄时间保留未知。</p>'''
    page += f'<p>当前 {len(selected)} 张照片，{len(grouped)} 个实体。默认未勾选；人工确认后可导出所选图片清单。来源页未声明开放许可时不推断图片可自由转载。</p></header>'
    page += '<div class="toolbar"><button onclick="exportSelection()">导出我确认的图片清单</button> <span id="count">0 张已确认</span></div><main>' + ''.join(cards) + '</main>'
    page += '''<script>document.addEventListener('change',()=>document.getElementById('count').textContent=document.querySelectorAll('input:checked').length+' 张已确认');function exportSelection(){let ids=[...document.querySelectorAll('input:checked')].map(x=>x.value);let data={collection:'official_20261119',human_confirmed_candidate_ids:ids,confirmed_at:new Date().toISOString()};let a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));a.download='confirmed_reference_images.json';a.click();URL.revokeObjectURL(a.href);}</script></html>'''
    (OUT / 'review.html').write_text(page, encoding='utf-8')
    markdown = ['# 本次新筛选的官方实景参考图', '',
                '这是新图集。请用Markdown预览查看照片，或打开review.html逐张勾选并导出确认清单。',
                '页面发布日期和照片拍摄日期不同；未注明的拍摄时间保留未知。助手初筛不冒充人工确认。', '']
    for sid, rows in grouped.items():
        markdown += ['## '+names.get(sid,sid), '']
        for row in rows:
            src = Path(row['local_path']).relative_to(OUT.relative_to(ROOT)).as_posix()
            markdown += [f"![{row['canonical_name']}]({src})", '',
                         f"**{row['width']}×{row['height']}** · 页面日期：{row['page_publication_date'] or '未注明'} · 拍摄日期：{row['image_capture_date'] or '未注明'}", '',
                         row['visual_review']['reason'], '',
                         f"[官方来源页]({row['source_page_url']}) · [本地原图]({src}) · 图片ID：`{row['candidate_id']}`", '']
    (OUT / 'review.md').write_text('\n'.join(markdown)+'\n', encoding='utf-8')
    report = ['# 官方实景参考图重建记录', '', f'更新时间：{datetime.now().isoformat(timespec="seconds")}',
              f'已下载候选{sum(r["download_status"]=="downloaded" for r in candidates.values())}张；已目视初筛{len(decisions)}条；选入审核页{len(selected)}张，涉及{len(grouped)}个实体。',
              '', '新照片审核页：[review.html](review.html)。新清单：[selected_references.csv](selected_references.csv)。',
              '', '旧实验reference_audit.json保留旧149张图片的审计记录；它不是本次新图集。',
              '来源为政府、机构和运营主体官网，以及官方发布账号所在权威媒体平台；照片正文、图注和外观同时核对。',
              '助手初筛不能冒充用户人工确认；use_for_retrieval目前保持False，用户确认清单可通过审核页导出。',
              '不将搜索缩略图、生成图、规划渲染图、拼图、Logo、文字封面、地图或相邻主体误当成该实体实景。',
              '', '|实体|本次候选原图数|', '|---|---:|']
    report += [f'|{names.get(sid,sid)}|{len(rows)}|' for sid,rows in grouped.items()]
    report += ['', '## 全库尚未补齐的实体', '', '、'.join(s['canonical_name'] for s in kb['symbols'] if not s['reference_images']),
               '', '候选知识库：../chinese_cultural_symbols_v4_official_candidates.json；保留原实体字段，仅替换reference_images为本次初筛图。EXT条目暂存图片，不擅自加入实体知识库。']
    (OUT / 'README.md').write_text('\n'.join(report)+'\n', encoding='utf-8')
    if selected and all(r['human_verified'] for r in selected):
        for filename in ['review.html', 'review.md', 'README.md']:
            path = OUT / filename
            content = path.read_text()
            content = content.replace('已由助手目视初筛，不冒充人工确认。', '已由助手目视初筛，并由用户在对话中确认全部47张图片。')
            content = content.replace('默认未勾选；人工确认后可导出所选图片清单。', '本批图片已全部确认；确认记录见confirmed_reference_images.json。')
            content = content.replace('助手初筛不冒充人工确认。', '用户已在对话中确认本批全部47张图片。')
            content = content.replace('助手初筛不能冒充用户人工确认；use_for_retrieval目前保持False，用户确认清单可通过审核页导出。', '用户已在对话中确认全部47张图片；确认记录保存在confirmed_reference_images.json。库内43张已启用检索；库外4张暂存，不擅自创建实体。')
            path.write_text(content, encoding='utf-8')
    print(json.dumps({'downloaded':sum(r['download_status']=='downloaded' for r in candidates.values()),'inspected':len(decisions),'selected':len(selected),'entities':len(grouped),'review_html':str(OUT/'review.html')},ensure_ascii=False))


if __name__ == '__main__':
    main()
