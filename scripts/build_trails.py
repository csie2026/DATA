"""Build trail segments and trailhead-to-summit courses for data/mountains.csv.

Outputs:
  data/trails.csv, data/trails.geojson    one row per 산림청 trail segment (FRT000801)
  data/courses.csv, data/courses.geojson  one row per trailhead (산림청 시종점 spot) -> summit, shortest open path

산림청 difficulty is useless here (99 % '쉬움') and its times are length x ~17.5 min/km, so course
difficulty is recomputed from length and net climb. Trailhead elevation: Open-Meteo elevation API
(Copernicus DEM 90 m, attribution required), cached in data/raw/elevation_cache.json.
"""
import csv, heapq, json, math, os, re, sys, time, urllib.request, zipfile, collections
import shapefile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from geo import P, to_wgs_5179, to_5179_from_wgs, to_5179_from_5186
import osm_trails

# Extra trail codes for a table row whose own code has no trails (same mountain, other side of a border).
EXTRA_CODES = {'412900201': ['116500401']}  # 우면산: trails are under the Seoul code
SNAP_M = 1.0           # segment endpoints closer than this are the same node
TRAILHEAD_SNAP_M = 50  # 시종점 spot must be this close to a trail node
SUMMIT_GAP_M = 300     # summit farther than this from any trail node -> no courses
MIN_COURSE_KM = 0.3
MIN_CLIMB_SHARE = 0.4   # start must climb >= this share of the mountain's biggest climb (drops mid-slope 시종점)
SAME_START_M = 300     # courses starting this close together are one trailhead; the shortest is kept
MAX_GRADE = 0.35       # average climb/length above this = DEM error or not a walking route
MAX_COURSES = 5        # per mountain, picked so their start directions differ
# Hand-reviewed bad courses: (mountain name, start name). 덕성산 신계리: 14.4 km detour for 4.3 km straight-line.
EXCLUDE_COURSES = {('덕성산', '신계리')}
MIN_BEARING_DEG = 45   # two kept courses must start at least this far apart, seen from the summit
GENERIC = {'시종점', '안내도', '안내판', '이정표', '화장실', '벤치', '분기', '분기점', '주차장', '음수대', '약수터', '지도', '안내'}


def difficulty(km, climb):
    # ponytail: two-threshold rule on one-way length and net climb, tune after comparing with real courses
    if climb is not None and climb >= 600 or km >= 8:
        return '어려움'
    if (climb is None or climb < 200) and km < 3:
        return '쉬움'
    return '보통'


def elevations(points):
    """{(lat, lon): elevation m} via Open-Meteo, 100 points per request, cached on disk."""
    path = P('data', 'raw', 'elevation_cache.json')
    cache = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else {}
    key = lambda p: f'{p[0]:.5f},{p[1]:.5f}'
    todo = sorted({key(p) for p in points} - cache.keys())
    for i in range(0, len(todo), 100):
        chunk = todo[i:i + 100]
        url = ('https://api.open-meteo.com/v1/elevation?latitude=' + ','.join(k.split(',')[0] for k in chunk)
               + '&longitude=' + ','.join(k.split(',')[1] for k in chunk))
        for attempt in range(6):  # Open-Meteo counts each point; 429 = wait for the minute window
            try:
                vals = json.load(urllib.request.urlopen(url, timeout=60))['elevation']
                break
            except urllib.error.HTTPError as e:
                if e.code != 429 or attempt == 5:
                    raise
                print(f'  elevation 429, waiting 65 s ({i}/{len(todo)})', flush=True)
                time.sleep(65)
        cache.update(zip(chunk, vals))
        json.dump(cache, open(path, 'w', encoding='utf-8'))  # keep progress if a later chunk fails
        time.sleep(5)
    json.dump(cache, open(path, 'w', encoding='utf-8'))
    return {p: cache[key(p)] for p in points}


def spot_trailheads(codes):
    """[(x, y) in 5179, label] for 산림청 시종점 spots."""
    out = []
    for code in codes:
        zf = P('mountain', 'mountain', f'{code}_geojson.zip')
        if not os.path.exists(zf):
            continue
        z = zipfile.ZipFile(zf)
        for n in z.namelist():
            if 'PMNTN_SPOT' in n and 'SAFE' not in n and n.endswith('.json'):
                for f in json.loads(z.read(n))['features']:
                    a = f['attributes']
                    if a.get('MANAGE_SP2') == '시종점':
                        words = [w.strip() for w in re.split(r'[,/]', a.get('DETAIL_SPO') or '')]
                        label = next((w for w in words if w and w not in GENERIC), '')
                        out.append((to_5179_from_5186(f['geometry']['x'], f['geometry']['y']), label))
    return out


def main():
    table = list(csv.DictReader(open(P('data', 'mountains.csv'), encoding='utf-8-sig')))
    owner = {}
    for m in table:
        for c in [c for c in m['codes'].split(';') if c] + EXTRA_CODES.get(m['code'], []):
            owner[c] = m

    segs, seen = collections.defaultdict(list), set()
    for sr in shapefile.Reader(P('FRT000801', 'TB_FGDI_WG_MT_WAY_ALL.shp'), encoding='cp949').iterShapeRecords():
        a = sr.record.as_dict()
        m = owner.get(a['MNTN_CODE'])
        pts = sr.shape.points
        if not m or len(pts) < 2 or (a['MNTN_CODE'], a['PMNTN_SN'], pts[0], pts[-1]) in seen:
            continue
        seen.add((a['MNTN_CODE'], a['PMNTN_SN'], pts[0], pts[-1]))
        segs[m['id']].append({
            'id': len(seen), 'source': 'forest', 'source_id': f"{a['MNTN_CODE']}-{a['PMNTN_SN']}", 'mountain_id': m['id'], 'mountain_name': m['name'],
            'name': a['PMNTN_NM'].strip(), 'length_km': round(sum(math.dist(p, q) for p, q in zip(pts, pts[1:])) / 1000, 3),
            'length_km_src': a['PMNTN_LT'],  # 산림청 attribute, off from the geometry on some segments
            'up_min': a['PMNTN_UPPL'] or 0, 'down_min': a['PMNTN_GODN'] or 0,
            'surface': a['PMNTN_MTRQ'].strip(), 'closed': a['PMNTN_CLS'] == 'Y', 'risk': a['PMNTN_RISK'].strip(),
            'difficulty_src': a['PMNTN_DFFL'].strip(), 'pts': pts})

    trails, courses, no_course = [], [], []
    for m in table:
        ss = segs.get(m['id'], [])
        trails += ss
        if not ss:
            continue
        summit = to_5179_from_wgs(float(m['summit_lon']), float(m['summit_lat']))
        gap, i, k = min((math.dist(p, summit), i, k) for i, s in enumerate(ss) for k, p in enumerate(s['pts']))
        if gap > SUMMIT_GAP_M:
            no_course.append(f"{m['name']}: summit {gap:.0f} m from trails")
            continue
        s = ss[i]
        if 0 < k < len(s['pts']) - 1:  # summit is mid-segment: split it there so it becomes a node
            part = lambda pts: sum(math.dist(p, q) for p, q in zip(pts, pts[1:]))
            frac = part(s['pts'][:k + 1]) / part(s['pts'])
            ss = ss[:i] + ss[i + 1:] + [
                dict(s, pts=pts, length_km=round(s['length_km'] * f, 3), up_min=s['up_min'] * f, down_min=s['down_min'] * f)
                for pts, f in ((s['pts'][:k + 1], frac), (s['pts'][k:], 1 - frac))]
        top_xy = s['pts'][k]
        node = lambda p: (round(p[0] / SNAP_M), round(p[1] / SNAP_M))
        adj = collections.defaultdict(list)
        xy = {}
        for i, s in enumerate(ss):
            a, b = node(s['pts'][0]), node(s['pts'][-1])
            xy[a], xy[b] = s['pts'][0], s['pts'][-1]
            if not s['closed']:
                adj[a].append((b, i)); adj[b].append((a, i))
        nearest = lambda p: min(xy, key=lambda n: math.dist(xy[n], p))
        top = node(top_xy)

        # shortest open path from the summit to every node
        dist, prev = {top: 0.0}, {}
        heap = [(0.0, top)]
        while heap:
            d, n = heapq.heappop(heap)
            if d > dist[n]:
                continue
            for n2, i in adj[n]:
                d2 = d + ss[i]['length_km']
                if d2 < dist.get(n2, 1e9):
                    dist[n2], prev[n2] = d2, (n, i)
                    heapq.heappush(heap, (d2, n2))

        heads = {}
        for p, label in spot_trailheads([c for c in m['codes'].split(';') if c] + EXTRA_CODES.get(m['code'], [])):
            n = nearest(p)
            if math.dist(xy[n], p) <= TRAILHEAD_SNAP_M and n in dist:
                heads.setdefault(n, label or heads.get(n, ''))
        heads = {n: l for n, l in heads.items() if dist[n] >= MIN_COURSE_KM}
        if not heads:  # no usable 시종점 spot: dead ends of the network, else (a loop) the farthest node
            heads = {n: '' for n in dist if len(adj[n]) == 1 and dist[n] >= MIN_COURSE_KM}
        if not heads and dist:
            far = max(dist, key=dist.get)
            heads = {far: ''} if dist[far] >= MIN_COURSE_KM else {}
        found = 0
        for n, label in heads.items():
            if dist[n] < MIN_COURSE_KM:
                continue
            path, cur = [], n
            while cur != top:
                cur, i = prev[cur]
                path.append(i)
            line = []
            here = xy[n]
            for i in path:  # walk trailhead -> summit, flipping segments as needed
                pts = ss[i]['pts']
                if math.dist(pts[0], here) > math.dist(pts[-1], here):
                    pts = pts[::-1]
                line += pts if not line else pts[1:]
                here = pts[-1]
            first = ss[path[0]]['name']
            label = label or re.sub(r'구간$', '', first) or '무명'
            lon, lat = to_wgs_5179(*xy[n])
            courses.append({'mountain_id': m['id'], 'mountain_name': m['name'], 'source': 'forest', 'start_name': label,
                            'start_lat': round(lat, 6), 'start_lon': round(lon, 6),
                            'length_km': round(dist[n], 2), 'up_min': round(sum(ss[i]['up_min'] for i in path)),
                            'down_min': round(sum(ss[i]['down_min'] for i in path)), 'segment_ids': ';'.join(str(i) for i in dict.fromkeys(ss[i]['id'] for i in path)),
                            'risk': ' / '.join(dict.fromkeys(ss[i]['risk'] for i in path if ss[i]['risk'])),
                            'summit_height': float(m['height']) if m['height'] else None, 'pts': line})
            found += 1
        if not found:
            no_course.append(f"{m['name']}: no trailhead reaches the summit")

    # OSM (ODbL) for mountains the 산림청 data gives no course
    done, osm_n = {c['mountain_id'] for c in courses}, 0
    for m in table:
        if m['id'] in done:
            continue
        ts, cs, problem = osm_trails.build(m, len(seen) + 1 + osm_n, SUMMIT_GAP_M, MIN_COURSE_KM)
        trails += ts; courses += cs; osm_n += len(ts)
        no_course.append(f"{m['name']}: " + (f'OSM {problem}' if problem else f'OSM {len(cs)} candidate courses'))

    by_id = {m['id']: m for m in table}
    elev = elevations([(c['start_lat'], c['start_lon']) for c in courses])
    by_m = collections.defaultdict(list)
    for c in courses:
        e = elev[(c['start_lat'], c['start_lon'])]
        c['start_elev_m'] = round(e) if e is not None else ''
        c['climb_m'] = round(c['summit_height'] - e) if c['summit_height'] is not None and e is not None else ''
        c['difficulty'] = difficulty(c['length_km'], c['climb_m'] if c['climb_m'] != '' else None)
        by_m[c['mountain_id']].append(c)
    for mid, cs in by_m.items():
        # ponytail: elevation/proximity heuristics, compare with real course lists and tune the two constants
        top = max((c['climb_m'] for c in cs if c['climb_m'] != ''), default=None)
        if top is not None and top > 0:
            cs = [c for c in cs if c['climb_m'] == '' or c['climb_m'] >= MIN_CLIMB_SHARE * top]
        cs.sort(key=lambda c: c['length_km'])
        kept = []
        for c in cs:
            if all(math.dist(*(to_5179_from_wgs(x['start_lon'], x['start_lat']) for x in (c, k))) > SAME_START_M for k in kept):
                kept.append(c)
        kept = [c for c in kept if c['climb_m'] == '' or c['climb_m'] <= MAX_GRADE * c['length_km'] * 1000]
        kept = [c for c in kept if (c['mountain_name'], c['start_name']) not in EXCLUDE_COURSES]
        # ponytail: shortest course per direction; upgrade to OSM route=hiking relations if picks look off
        m = by_id[mid]
        bearing = lambda c: math.degrees(math.atan2((c['start_lon'] - float(m['summit_lon'])) * math.cos(math.radians(c['start_lat'])), c['start_lat'] - float(m['summit_lat']))) % 360
        picked = []
        for c in kept:  # already shortest first
            if len(picked) < MAX_COURSES and all(min(abs(bearing(c) - bearing(p)), 360 - abs(bearing(c) - bearing(p))) >= MIN_BEARING_DEG for p in picked):
                picked.append(c)
        by_m[mid] = cs = picked
        names = collections.Counter(c['start_name'] for c in cs)
        k = collections.Counter()
        for c in cs:
            k[c['start_name']] += 1
            c['name'] = f"{c['start_name']} 코스" + (f" {k[c['start_name']]}" if names[c['start_name']] > 1 else '')

    wgs = lambda pts: [[round(v, 7) for v in to_wgs_5179(*p)] for p in pts]
    tf = ['id', 'source', 'source_id', 'mountain_id', 'mountain_name', 'name', 'length_km', 'length_km_src', 'up_min', 'down_min', 'surface', 'closed', 'risk', 'difficulty_src']
    cf = ['mountain_id', 'mountain_name', 'source', 'name', 'start_name', 'start_lat', 'start_lon', 'start_elev_m',
          'climb_m', 'length_km', 'up_min', 'down_min', 'difficulty', 'risk', 'segment_ids']
    courses = [c for cs in by_m.values() for c in cs]
    # Trail ids are plain integers set when read (source_id is not unique: one 산림청 key can have several
    # geometries); split summit segments keep their parent's id. Courses get no id: the DB assigns it on import.
    # ponytail: trail ids are renumbered on every rebuild, freeze them once the app references trails
    trails.sort(key=lambda s: s['id'])
    for name, rows, fields in (('trails', trails, tf), ('courses', courses, cf)):
        with open(P('data', name + '.csv'), 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fields, extrasaction='ignore')
            w.writeheader(); w.writerows(rows)
        fc = {'type': 'FeatureCollection', 'features': [
            {'type': 'Feature', 'properties': {k: r[k] for k in fields},
             'geometry': {'type': 'LineString', 'coordinates': wgs(r['pts'])}} for r in rows]}
        json.dump(fc, open(P('data', name + '.geojson'), 'w', encoding='utf-8'), ensure_ascii=False)

    print(f'trails {len(trails)} segments on {len({t["mountain_id"] for t in trails})} mountains; courses {len(courses)} on {len(by_m)} mountains; '
          f'difficulty {dict(collections.Counter(c["difficulty"] for c in courses))}')
    print('\n'.join(no_course))


if __name__ == '__main__':
    main()
