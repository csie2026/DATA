"""Download 산림청 산정보 API (all mountains) to data/raw/forest_api.json. Key: DATA_GO_KR_KEY in .env (decoding key)."""
import json, os, urllib.parse, urllib.request
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = 'https://apis.data.go.kr/1400000/service/cultureInfoService2/mntInfoOpenAPI2'
key = next(l.split('=', 1)[1].strip() for l in open(os.path.join(ROOT, '.env'), encoding='utf-8')
           if l.startswith('DATA_GO_KR_KEY='))

items, page = [], 1
while True:
    q = urllib.parse.urlencode({'serviceKey': key, 'pageNo': page, 'numOfRows': 500})
    root = ET.fromstring(urllib.request.urlopen(f'{URL}?{q}', timeout=60).read())
    if root.findtext('header/resultCode') != '00':
        raise SystemExit(f"API error: {root.findtext('header/resultMsg')}")
    batch = [{c.tag: (c.text or '').strip() for c in it} for it in root.iter('item')]
    items += batch
    total = int(root.findtext('body/totalCount'))
    if not batch or len(items) >= total:
        break
    page += 1

json.dump(items, open(os.path.join(ROOT, 'data', 'raw', 'forest_api.json'), 'w', encoding='utf-8'), ensure_ascii=False)
print(f'{len(items)} / {total}')
