"""Collect attributable official reference photos into a separate review pack.

Downloads do not imply identity approval. Original images and existing KBs are
never overwritten. Only visually inspected records can be promoted later.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import re
import threading
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'archives/knowledge_base_history_20261119/reference_images_official_20261119'
LOCK = threading.Lock()
UA = {'User-Agent': 'Mozilla/5.0 (compatible; CulturalReferenceResearch/1.0)'}
BAD = re.compile(r'(?:logo|qrcode|weixin|weibo|icon|share|loading|spacer|code\.png|png21\.png)', re.I)


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def fetch(url, referer=None):
    headers = dict(UA)
    if referer:
        headers['Referer'] = referer
    response = requests.get(url, headers=headers, timeout=(12, 35))
    response.raise_for_status()
    return response


def collect_page(task):
    url = task['url']
    key = hashlib.sha256(url.encode()).hexdigest()[:16]
    cache = OUT / 'pages' / (key + '.html')
    try:
        if cache.is_file():
            raw = cache.read_bytes()
        else:
            response = fetch(url)
            raw = response.content
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(raw)
        soup = BeautifulSoup(raw, 'html.parser')
        title = soup.title.get_text(' ', strip=True) if soup.title else task.get('title', '')
        date = task.get('publication_date')
        for meta in soup.find_all('meta'):
            name = str(meta.get('name') or meta.get('property') or '').lower()
            if name in {'pubdate', 'publishdate', 'pubtime', 'date', 'dc.date', 'article:published_time', 'publishdate'}:
                date = meta.get('content') or date
        if not date:
            m = re.search(r'/(20\d\d)[/-]?(\d\d)[/-]?(\d\d)(?:/|_)', url)
            if m:
                date = '-'.join(m.groups())
        main = None
        for selector in ['.TRS_Editor', '.TRS_UEDITOR', '#UCAP-CONTENT', '#UCAPCONTENT',
                         '.article-content', '.article_content', '.v_news_content', 'article', '.content-article']:
            node = soup.select_one(selector)
            if node and node.find('img'):
                main = node; break
        main = main or soup
        candidates, seen = [], set()
        for tag in main.find_all(['img', 'a']):
            attrs = ['href', 'data-urls'] if tag.name == 'a' else ['data-original', 'data-src', 'srcset', 'src', 'oldsrc']
            for attr in attrs:
                value = tag.get(attr)
                if not value or value.startswith('data:'):
                    continue
                if attr == 'srcset':
                    value = value.split(',')[-1].strip().split()[0]
                image_url = urljoin(url, value.strip())
                if '/_next/image' in image_url:
                    original = parse_qs(urlparse(image_url).query).get('url', [])
                    if original:
                        image_url = urljoin(url, original[0])
                if not re.search(r'\.(?:jpe?g|png|webp)(?:[?#]|$)', image_url, re.I) or BAD.search(image_url):
                    continue
                if image_url in seen:
                    continue
                seen.add(image_url)
                caption = str(tag.get('alt') or tag.get('title') or '')
                parent = tag.parent
                nearby = parent.get_text(' ', strip=True)[:300] if parent else ''
                sibling = parent.find_next_sibling() if parent else None
                if sibling and len(sibling.get_text(' ', strip=True)) < 240:
                    nearby += ' ' + sibling.get_text(' ', strip=True)
                candidates.append(dict(source_page_url=url, page_title=title,
                    source_organization=task.get('organization'), page_publication_date=date,
                    image_capture_date=None, candidate_entity_ids=task['symbol_ids'],
                    image_url=image_url, caption=caption, nearby_text=nearby.strip(),
                    discovery='official_page_dom', retrieved_at=datetime.now().isoformat(timespec='seconds')))
        for image_url in task.get('image_urls', []):
            if image_url not in seen:
                candidates.insert(0, dict(source_page_url=url, page_title=title,
                    source_organization=task.get('organization'), page_publication_date=date,
                    image_capture_date=None, candidate_entity_ids=task['symbol_ids'],
                    image_url=image_url, caption=task.get('caption', ''), nearby_text='',
                    discovery='official_page_explicit_image_link', retrieved_at=datetime.now().isoformat(timespec='seconds')))
        # A supplied exact subset avoids scraping unrelated news / navigation.
        if task.get('only_image_urls'):
            wanted = set(task['image_urls'])
            candidates = [c for c in candidates if c['image_url'] in wanted]
        return {'url': url, 'status': 'ok', 'title': title, 'date': date,
                'symbol_ids': task['symbol_ids'], 'candidates': candidates[:task.get('max_images', 10)]}
    except Exception as e:
        if task.get('image_urls') and task.get('web_tool_verified'):
            return {'url': url, 'status': 'page_http_failed_web_tool_verified',
                    'symbol_ids': task['symbol_ids'], 'error': str(e)[:300],
                    'candidates': [dict(source_page_url=url, page_title=task.get('title', ''),
                        source_organization=task.get('organization'), page_publication_date=task.get('publication_date'),
                        image_capture_date=None, candidate_entity_ids=task['symbol_ids'], image_url=image_url,
                        caption=task.get('caption', ''), nearby_text='', discovery='web_tool_official_page_image_link',
                        retrieved_at=datetime.now().isoformat(timespec='seconds')) for image_url in task['image_urls']]}
        return {'url': url, 'status': 'failed', 'symbol_ids': task['symbol_ids'],
                'error_type': type(e).__name__, 'error': str(e)[:300], 'candidates': []}


def download(record):
    key = hashlib.sha256((record['source_page_url'] + '|' + record['image_url']).encode()).hexdigest()[:20]
    meta = OUT / 'candidates' / (key + '.json')
    if meta.is_file():
        existing = json.loads(meta.read_text())
        if existing.get('download_status') == 'downloaded' or 'Insufficient resolution' not in existing.get('error', ''):
            return existing
    result = dict(record, candidate_id=key, verification_status='candidate_unreviewed',
                  use_for_retrieval=False, human_verified=False)
    try:
        response = fetch(record['image_url'], record['source_page_url'])
        blob = response.content
        with Image.open(io.BytesIO(blob)) as im:
            width, height = im.size
            im.verify()
        if min(width, height) < 320 or max(width, height) < 600:
            raise ValueError(f'Insufficient resolution {width}x{height}')
        sha = hashlib.sha256(blob).hexdigest()
        ext = '.png' if blob.startswith(b'\x89PNG') else '.jpg' if blob.startswith(b'\xff\xd8') else '.webp'
        dest = OUT / 'assets' / (sha[:20] + ext)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.is_file():
            dest.write_bytes(blob)
        result.update(download_status='downloaded', local_path=str(dest.relative_to(ROOT)),
                      sha256=sha, width=width, height=height, byte_size=len(blob),
                      resolution_tier='high' if min(width, height) >= 600 and max(width, height) >= 1000 else 'standard_native',
                      final_image_url=response.url, content_type=response.headers.get('Content-Type'))
    except Exception as e:
        result.update(download_status='failed', error_type=type(e).__name__, error=str(e)[:300])
    with LOCK:
        save(meta, result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--queue', required=True)
    p.add_argument('--workers', type=int, default=6)
    args = p.parse_args()
    tasks = json.loads((ROOT / args.queue).read_text())
    pages, records = [], []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for fut in as_completed([pool.submit(collect_page, task) for task in tasks]):
            page = fut.result(); pages.append(page)
            print('PAGE', page['status'], len(page['candidates']), page['url'], flush=True)
    queue_key = Path(args.queue).stem
    save(OUT / 'logs' / (queue_key + '_pages.json'), pages)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for fut in as_completed([pool.submit(download, c) for page in pages for c in page['candidates']]):
            rec = fut.result(); records.append(rec)
            print('IMAGE', rec['download_status'], rec.get('width'), rec.get('height'), rec['image_url'], flush=True)
    save(OUT / 'logs' / (queue_key + '_downloads.json'), records)
    print('SUMMARY', len(tasks), 'pages', sum(r['download_status'] == 'downloaded' for r in records), 'downloaded', flush=True)


if __name__ == '__main__':
    main()
