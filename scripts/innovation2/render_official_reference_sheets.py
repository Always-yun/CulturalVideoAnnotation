"""Render labeled contact sheets for inspection, never as retrieval references."""
import argparse
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'archives/knowledge_base_history_20261119/reference_images_official_20261119'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', required=True)
    a = parser.parse_args()
    seen = {r['candidate_id'] for p in OUT.glob('visual_reviews_*.json') for r in json.loads(p.read_text())}
    names = {s['symbol_id']:s['canonical_name'] for s in json.loads((ROOT/'archives/knowledge_base_history_20261119/chinese_cultural_symbols_v3.json').read_text())['symbols']}
    names.update(EXT_GREAT_HALL='人民大会堂（待扩库）', EXT_TANGHULU='冰糖葫芦（待扩库）')
    rows = [json.loads(p.read_text()) for p in (OUT/'candidates').glob('*.json')]
    rows = [r for r in rows if r['download_status']=='downloaded' and r['candidate_id'] not in seen]
    rows.sort(key=lambda r:(r['candidate_entity_ids'],r['candidate_id']))
    folder = OUT / ('review_sheets_'+a.batch); folder.mkdir(exist_ok=True)
    font = ImageFont.truetype('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',17)
    for i,r in enumerate(rows):r['review_index']=i
    for start in range(0,len(rows),12):
        canvas=Image.new('RGB',(1440,1080),'#eaeaea');draw=ImageDraw.Draw(canvas)
        for j,r in enumerate(rows[start:start+12]):
            x=j%4*360;y=j//4*360
            im=Image.open(ROOT/r['local_path']).convert('RGB');im.thumbnail((350,280))
            canvas.paste(im,(x+(360-im.width)//2,y+(280-im.height)//2))
            draw.text((x+5,y+285),f"{r['review_index']} {r['candidate_id'][:8]} {r['width']}x{r['height']}",font=font,fill='black')
            draw.text((x+5,y+310),'/'.join(names.get(s,s) for s in r['candidate_entity_ids'])[:21],font=font,fill='black')
            draw.text((x+5,y+335),str(r.get('page_publication_date') or '日期未注明')[:28],font=font,fill='black')
        canvas.save(folder/f'{start//12:03d}.jpg',quality=90)
    (OUT/('review_index_'+a.batch+'.json')).write_text(json.dumps(rows,ensure_ascii=False,indent=2))
    print('unreviewed',len(rows),'sheets',(len(rows)+11)//12)


if __name__=='__main__':main()
