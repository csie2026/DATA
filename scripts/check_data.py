"""Consistency checks across all data/*.csv (and the matching .geojson). Prints problems; exit code 1 if any.
Per-row mountain checks (OSM, borders, heights) live in check_selected.py."""
import csv, json, math, sys
from geo import P

issues = []
bad = lambda msg: issues.append(msg)


def read(name):
    raw = open(P('data', name), 'rb').read()
    if not raw.startswith(b'\xef\xbb\xbf'):
        bad(f'{name}: no UTF-8 BOM (Excel shows Korean garbled)')
    rows = list(csv.reader(raw.decode('utf-8-sig').splitlines()))
    head, body = rows[0], rows[1:]
    for n, r in enumerate(body, 2):
        if len(r) != len(head):
            bad(f'{name}:{n}: {len(r)} fields, header has {len(head)}')
        if any(v != v.strip() for v in r):
            bad(f'{name}:{n}: leading/trailing spaces')
    return [dict(zip(head, r)) for r in body]


def num(name, rows, col, lo, hi, blank=False):
    for r in rows:
        v = r[col]
        if v == '' and blank:
            continue
        try:
            if not lo <= float(v) <= hi:
                bad(f'{name}: {col}={v} out of [{lo}, {hi}] ({r.get("name") or r.get("mountain_name")})')
        except ValueError:
            bad(f'{name}: {col}={v!r} not a number ({r.get("name") or r.get("mountain_name")})')


def dist_m(lat1, lon1, lat2, lon2):
    x = math.radians(lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    return 6371000 * math.hypot(x, math.radians(lat2 - lat1))


def main():
    M = read('mountains.csv')
    D = read('mountain_descriptions.csv')
    T = read('trails.csv')
    C = read('courses.csv')
    names = [l.strip() for l in open(P('data', 'mountain_names.txt'), encoding='utf-8') if l.strip()]

    # mountains
    ids = [r['id'] for r in M]
    if len(set(ids)) != len(ids) or not all(i.isdigit() for i in ids):
        bad('mountains: id not unique positive integers')
    if len({r['name'] for r in M}) != len(M):
        bad('mountains: duplicate name')
    if names != [r['name'] for r in M]:
        bad('mountain_names.txt differs from mountains.csv (names or order)')
    num('mountains', M, 'height', 30, 1500)
    num('mountains', M, 'summit_lat', 36.8, 38.4)
    num('mountains', M, 'summit_lon', 126.3, 127.9)
    for r in M:
        if r['code'] and r['code'] not in r['codes'].split(';'):
            bad(f'mountains: code {r["code"]} not in codes ({r["name"]})')
    mid = {r['id']: r for r in M}

    # descriptions
    if sorted(r['name'] for r in D) != sorted(mid[i]['name'] for i in mid):
        bad('mountain_descriptions: names differ from mountains')
    by_name = {r['name']: r for r in M}
    for r in D:
        m = by_name.get(r['name'])
        if m and r['code'] != m['code']:
            bad(f'mountain_descriptions: code {r["code"]} != {m["code"]} ({r["name"]})')
        if not r['description'] or len(r['description']) > 300:
            bad(f'mountain_descriptions: description empty or > 300 chars ({r["name"]})')
        if r['desc_src'] not in ('forest_api', 'generated'):
            bad(f'mountain_descriptions: desc_src {r["desc_src"]!r} ({r["name"]})')

    # trails
    if [r['id'] for r in T] != [str(i) for i in range(1, len(T) + 1)]:
        bad('trails: id is not 1..N')
    for f in ('trails', 'courses'):
        for r in (T if f == 'trails' else C):
            m = mid.get(r['mountain_id'])
            if not m or m['name'] != r['mountain_name']:
                bad(f'{f}: mountain_id {r["mountain_id"]} / mountain_name {r["mountain_name"]} mismatch')
    num('trails', T, 'length_km', 0, 30)  # OSM ridge ways (한남정맥) can be one long way
    num('trails', T, 'up_min', 0, 600)
    num('trails', T, 'down_min', 0, 600)
    for r in T:
        if r['closed'] not in ('True', 'False'):
            bad(f'trails: closed={r["closed"]!r} (id {r["id"]})')
    tid = {r['id']: r for r in T}
    for f, rows in (('trails', T), ('courses', C)):
        if {r['source'] for r in rows} - {'forest', 'osm'}:
            bad(f'{f}: source must be forest or osm')

    # courses
    num('courses', C, 'length_km', 0.3, 30)
    num('courses', C, 'climb_m', 0, 1500, blank=True)
    num('courses', C, 'start_lat', 36.8, 38.4)
    num('courses', C, 'start_lon', 126.3, 127.9)
    per = {}
    for r in C:
        per[r['mountain_id']] = per.get(r['mountain_id'], 0) + 1
    if per and max(per.values()) > 5:
        bad(f'courses: more than 5 courses on a mountain ({max(per.values())})')
    seen = set()
    for r in C:
        if r['climb_m'] and float(r['climb_m']) > 0.35 * float(r['length_km']) * 1000:
            bad(f'courses: average grade over 35% ({r["mountain_name"]} {r["name"]})')
        key = (r['mountain_id'], r['name'])
        if key in seen:
            bad(f'courses: duplicate name {r["name"]} on {r["mountain_name"]}')
        seen.add(key)
        segs = r['segment_ids'].split(';')
        if any(s in tid and tid[s]['source'] != r['source'] for s in segs):
            bad(f'courses: segments from another source ({r["mountain_name"]} {r["name"]})')
        if any(s not in tid or tid[s]['mountain_id'] != r['mountain_id'] for s in segs):
            bad(f'courses: segment_ids point to missing/other-mountain trails ({r["mountain_name"]} {r["name"]})')
        elif any(tid[s]['closed'] == 'True' for s in segs):
            bad(f'courses: uses a closed segment ({r["mountain_name"]} {r["name"]})')
        km = float(r['length_km'])
        seg_km = sum(float(tid[s]['length_km']) for s in segs if s in tid)
        if seg_km + 0.05 < km:  # summit splits can make the course shorter than its segments, never longer
            bad(f'courses: length {km} > segments {seg_km:.2f} ({r["mountain_name"]} {r["name"]})')
        m = mid.get(r['mountain_id'])  # missing -> already reported above
        if r['climb_m'] and m:
            if abs(float(m['height']) - float(r['start_elev_m']) - float(r['climb_m'])) > 1:
                bad(f'courses: climb_m != height - start_elev_m ({r["mountain_name"]} {r["name"]})')
            climb = float(r['climb_m'])
            want = '어려움' if climb >= 600 or km >= 8 else '쉬움' if climb < 200 and km < 3 else '보통'
            if r['difficulty'] != want:
                bad(f'courses: difficulty {r["difficulty"]} != rule {want} ({r["mountain_name"]} {r["name"]})')

    # geojson mirrors csv; course line runs trailhead -> summit
    for name, rows in (('trails', T), ('courses', C)):
        feats = json.load(open(P('data', name + '.geojson'), encoding='utf-8'))['features']
        if len(feats) != len(rows):
            bad(f'{name}.geojson: {len(feats)} features, csv has {len(rows)}')
            continue
        for f, r in zip(feats, rows):
            if {k: str(v) for k, v in f['properties'].items()} != r:
                bad(f'{name}.geojson: properties differ from csv ({r["mountain_name"]} {r["name"]})')
                break
        if name == 'courses':
            for f, r in zip(feats, rows):
                pts = f['geometry']['coordinates']
                m = mid.get(r['mountain_id'])
                if not m:
                    continue
                if dist_m(float(r['start_lat']), float(r['start_lon']), pts[0][1], pts[0][0]) > 60:
                    bad(f'courses.geojson: line does not start at the trailhead ({r["mountain_name"]} {r["name"]})')
                if dist_m(float(m['summit_lat']), float(m['summit_lon']), pts[-1][1], pts[-1][0]) > 300:
                    bad(f'courses.geojson: line does not end near the summit ({r["mountain_name"]} {r["name"]})')

    print('\n'.join(issues) or 'ok')
    print(f'{len(M)} mountains, {len(D)} descriptions, {len(T)} trails, {len(C)} courses, {len(issues)} issues')
    sys.exit(1 if issues else 0)


if __name__ == '__main__':
    main()
