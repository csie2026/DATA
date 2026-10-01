"""Sanity checks for data/mountains.csv. Prints one line per problem; exit code 1 if any."""
import csv, json, math, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = lambda *a: os.path.join(ROOT, *a)
PROVINCE = {'11': '서울', '23': '인천', '31': '경기', '32': '강원', '33': '충북', '34': '충남'}  # KOSTAT 2013 codes
ADDR_PROVINCE = {'11': '서울', '28': '인천', '41': '경기', '42': '강원', '51': '강원', '43': '충북', '44': '충남'}


def dist_m(lat1, lon1, lat2, lon2):
    x = math.radians(lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    return 6371000 * math.hypot(x, math.radians(lat2 - lat1))


def inside(lon, lat, ring):
    hit = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > lat) != (y2 > lat) and lon < x1 + (lat - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def province_of(lat, lon, provinces):
    for code, polys in provinces.items():
        if any(inside(lon, lat, poly[0]) for poly in polys):
            return PROVINCE.get(code, code)
    return '?'


def main():
    rows = list(csv.DictReader(open(P('data', 'mountains.csv'), encoding='utf-8-sig')))
    names = [l.strip() for l in open(P('data', 'mountain_names.txt'), encoding='utf-8') if l.strip()]
    provinces = {}
    for f in json.load(open(P('data', 'raw', 'provinces_geo.json'), encoding='utf-8'))['features']:
        g = f['geometry']
        provinces[f['properties']['code']] = g['coordinates'] if g['type'] == 'MultiPolygon' else [g['coordinates']]
    peaks = [e for e in json.load(open(P('data', 'raw', 'osm_peaks.json'), encoding='utf-8'))['elements']
             if 'name' in e.get('tags', {})]
    issues = []
    add = lambda r, msg: issues.append(f"{r['name'] if r else '-'}: {msg}")

    # list vs table
    if sorted(names) != sorted(r['name'] for r in rows):
        add(None, f'names differ from list: missing {set(names) - {r["name"] for r in rows}}, '
                  f'extra {({r["name"] for r in rows}) - set(names)}')
    ids = [r['id'] for r in rows]
    if not all(i.isdigit() for i in ids) or len(set(ids)) != len(ids):
        add(None, 'id must be a unique positive integer (never renumber; new mountain = max id + 1)')
    seen = {}
    for r in rows:
        for c in filter(None, r['codes'].split(';')):
            if c in seen:
                add(r, f'code {c} also used by {seen[c]}')
            seen[c] = r['name']
    key = [(r['sigungu_name'] or '힣', r['name']) for r in rows]
    if key != sorted(key):
        add(None, 'rows are not sorted by sigungu_name, name')

    for r in rows:
        # blanks
        for k in ('code', 'address', 'sigungu_name', 'height', 'summit_lat'):
            if not r[k]:
                add(r, f'blank {k}')
        # code / address consistency
        if r['code'] and r['address']:
            want = ADDR_PROVINCE.get(r['code'][:2], '?')
            if not r['address'].startswith(('서울' if want == '서울' else want[:2])):
                add(r, f'code province {want} but address "{r["address"][:20]}"')
        if r['address'] and r['sigungu_name'] and r['sigungu_name'].replace('서울 ', '') not in r['address']:
            add(r, f'sigungu_name {r["sigungu_name"]} not in address "{r["address"][:25]}"')
        # heights
        if r['height']:
            h = float(r['height'])
            if h < 100:
                add(r, f'height {h} < 100 m')
        if not r['summit_lat']:
            continue
        lat, lon = float(r['summit_lat']), float(r['summit_lon'])
        prov = province_of(lat, lon, provinces)
        if prov not in ('경기', '서울', '인천'):
            add(r, f'summit in {prov}')
        # nearest named OSM peak: same name nearby, and its ele agrees with height
        # substring match: OSM names sub-peaks like '용문산 가섭봉', '북한산(백운대)'
        base = re.sub(r'\s*\(.*\)', '', r['name'])
        near = min(peaks, key=lambda e: dist_m(lat, lon, e['lat'], e['lon']))
        d = dist_m(lat, lon, near['lat'], near['lon'])
        same = [e for e in peaks if base in e['tags']['name'] and dist_m(lat, lon, e['lat'], e['lon']) < 1500]
        if not same:
            add(r, f'no OSM peak named {base} within 1.5 km (nearest: {near["tags"]["name"]} {d:.0f} m)')
        else:
            ele = same[0]['tags'].get('ele', '').replace('m', '').strip()
            try:
                if r['height'] and abs(float(ele) - float(r['height'])) > 30:
                    add(r, f'height {r["height"]} vs OSM ele {ele}')
            except ValueError:
                pass

    # two rows on the same summit
    pts = [(r['name'], float(r['summit_lat']), float(r['summit_lon'])) for r in rows if r['summit_lat']]
    for i, (n1, a1, o1) in enumerate(pts):
        for n2, a2, o2 in pts[i + 1:]:
            if dist_m(a1, o1, a2, o2) < 300:
                issues.append(f'{n1} / {n2}: summits {dist_m(a1, o1, a2, o2):.0f} m apart')

    print('\n'.join(issues) or 'ok')
    print(f'{len(rows)} rows, {len(issues)} issues')
    sys.exit(1 if issues else 0)


if __name__ == '__main__':
    main()
