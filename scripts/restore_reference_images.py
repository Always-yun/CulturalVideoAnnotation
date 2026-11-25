"""重下 v2.json 里 149 张参考图

遍历 v2.json 的 reference_images[].image_url，直链能下载的直接下；
ncha 直链被墙的，从 source_page_url 正文重新抓 /picture/ 图。
"""
import os, json, time, hashlib, re, io, sys
from urllib.parse import urljoin

import requests
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB_JSON = os.path.join(ROOT, "archives", "knowledge_base_history_20261119", "chinese_cultural_symbols_v2.json")
IMG_DIR = os.path.join(ROOT, "archives", "knowledge_base_history_20261119", "reference_images_v2")
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"}

MIN_W, MIN_H = 400, 260


def download_direct(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
        if r.status_code != 200:
            return None, f"http_{r.status_code}"
        if len(r.content) < 8_000:
            return None, "too_small"
        # 校验是图像
        try:
            im = Image.open(io.BytesIO(r.content))
            im.verify()
        except Exception as e:
            return None, f"not_image:{type(e).__name__}"
        return r.content, None
    except Exception as e:
        return None, f"{type(e).__name__}"


def scrape_ncha_page(page_url):
    """从 ncha 文章页重新抓 /picture/ 图"""
    try:
        r = requests.get(page_url, headers=HEADERS, timeout=30, allow_redirects=True)
        if r.status_code != 200:
            return [], f"http_{r.status_code}"
        r.encoding = r.apparent_encoding or "utf-8"
        # 用正则找 /picture/ 下的 jpg/png
        urls = re.findall(r'(https?://[^"\'<> ]+?/picture/[^"\'<> ]+?\.(?:jpe?g|png))', r.text, re.I)
        uniq = []
        seen = set()
        for u in urls:
            u = u.rstrip(')"\' ,')
            if u not in seen:
                seen.add(u)
                uniq.append(u)
        return uniq[:10], None
    except Exception as e:
        return [], f"{type(e).__name__}"


def sha_of(content):
    return hashlib.sha256(content).hexdigest()


def save(sid, idx, content):
    out_dir = os.path.join(IMG_DIR, sid)
    os.makedirs(out_dir, exist_ok=True)
    sha = sha_of(content)[:12]
    ext = ".jpg"
    fn = f"{idx:02d}_{sha}{ext}"
    path = os.path.join(out_dir, fn)
    with open(path, "wb") as f:
        f.write(content)
    return os.path.relpath(path, ROOT)


def main():
    d = json.load(open(KB_JSON, encoding="utf-8"))
    stats = {"direct_ok": 0, "direct_fail": 0, "scrape_ok": 0, "scrape_fail": 0,
             "skipped": 0, "total_records": 0}

    for s in d["symbols"]:
        sid = s["symbol_id"]
        refs = s.get("reference_images") or []
        if not refs:
            continue
        stats["total_records"] += len(refs)

        for i, r in enumerate(refs):
            # 已经有 local_path 的跳过
            if r.get("local_path") and os.path.exists(os.path.join(ROOT, r["local_path"])):
                stats["skipped"] += 1
                continue

            img_url = r.get("image_url") or ""
            page_url = r.get("source_page_url") or ""

            content, err = None, None
            # 1. 先直链
            if img_url:
                content, err = download_direct(img_url)
                if content:
                    stats["direct_ok"] += 1
                else:
                    stats["direct_fail"] += 1
                    print(f"    direct fail {sid} [{i}] {err} {img_url[:60]}")

            # 2. 直链不行且是 ncha，从文章页重新抓
            if not content and "ncha.gov.cn" in img_url and page_url:
                candidates, err2 = scrape_ncha_page(page_url)
                if candidates:
                    for c in candidates:
                        content, err = download_direct(c)
                        if content:
                            # 更新 image_url 为抓到的新图
                            r["image_url"] = c
                            break
                    if content:
                        stats["scrape_ok"] += 1
                    else:
                        stats["scrape_fail"] += 1
                        print(f"    ncha scrape no good {sid} page={page_url[:60]}")
                else:
                    stats["scrape_fail"] += 1
                    print(f"    ncha scrape fail {sid} err={err2} page={page_url[:60]}")

            if content:
                lp = save(sid, i + 1, content)
                r["local_path"] = lp
                r["image_status"] = "downloaded"
            else:
                r["local_path"] = ""
                r["image_status"] = "unavailable"
                r.setdefault("notes", "") + "; download_failed"

            time.sleep(0.3)

    json.dump(d, open(KB_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("\n=== STATS ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    avail = sum(1 for s in d["symbols"]
                for r in (s.get("reference_images") or [])
                if r.get("local_path"))
    print(f"  total local_path now: {avail}")


if __name__ == "__main__":
    main()
