"""Trail segments and trailhead-to-summit courses from OpenStreetMap (ODbL) paths, for mountains whose
산림청 data gives no course. Used by build_trails.py.

Network: highway=path/footway/steps/track/bridleway ways around the summit, split at shared nodes.
Trailheads: path nodes that are also road nodes (where the trail leaves the road), else network dead ends.
Overpass responses are cached in data/raw/osm_paths/<mountain id>.json; delete a file to refetch.
"""
import collections, heapq, json, math, os, re, time, urllib.parse, urllib.request
from geo import P, to_5179_from_wgs, to_wgs_5179

URLS = ['https://overpass-api.de/api/interpreter']  # mirrors tried (kumi, private.coffee) time out from here
PATHS = 'path|footway|steps|track|bridleway'
ROADS = 'motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street|service|road'
PLACES = 'town|village|hamlet|suburb|quarter|neighbourhood'
UP_MIN_PER_KM, DOWN_MIN_PER_KM = 17.5, 12.5  # what the 산림청 segment times work out to, so both sources compare
MAX_COURSE_KM = 10     # longer = the path wanders over neighbouring peaks
PLACE_M = 2000         # trailhead label = nearest place within this distance
SAME_START_M = 300     # same as build_trails.SAME_START_M
SURFACE = {'ground': '토사', 'dirt': '토사', 'earth': '토사', 'mud': '토사', 'sand': '토사', 'grass': '토사',
           'rock': '암석', 'stone': '암석', 'gravel': '자갈', 'fine_gravel': '자갈', 'compacted': '자갈',
           'pebblestone': '자갈', 'paved': '포장', 'asphalt': '포장', 'concrete': '포장', 'paving_stones': '포장',
           'wood': '목재'}
# Not a hiking trail for this app: climbing grade (T4+), barely visible, informal, or no access.
TOO_HARD_SAC = {'alpine_hiking', 'demanding_alpine_hiking', 'difficult_alpine_hiking'}
ROCKY_SAC = 'demanding_mountain_hiking'  # T3: rocky but the main trail on 북한산/관악산 etc. -> kept, risk '험로'
BAD_VISIBILITY = {'bad', 'horrible', 'no'}


def is_trail(t):
    return (t.get('footway') not in ('sidewalk', 'crossing')  # city pavements
            and t.get('sac_scale') not in TOO_HARD_SAC and t.get('trail_visibility') not in BAD_VISIBILITY
            and t.get('informal') != 'yes' and t.get('access') not in ('no', 'private') and t.get('foot') != 'no')


def radius_m(m):
    return 5000 if float(m['height']) >= 500 else 3000


def fetch(m):
    path = P('data', 'raw', 'osm_paths', f"{m['id']}.json")
    if os.path.exists(path):
        return json.load(open(path, encoding='utf-8'))
    lat, lon = m['summit_lat'], m['summit_lon']
    query = lambda r: f"""[out:json][timeout:180];
way(around:{r},{lat},{lon})[highway~"^({PATHS})$"]->.p;
way(around:{r + 500},{lat},{lon})[highway~"^({ROADS})$"]->.r;
node(around:{r + PLACE_M},{lat},{lon})[place~"^({PLACES})$"]->.n;
.p out body geom; .r out body; .n out body;"""
    data = None
    for attempt in range(6):  # 429 / 504 when Overpass is busy: alternate servers, back off
        url = URLS[attempt % len(URLS)]
        r = radius_m(m) if attempt < 3 else 2500  # dense areas (북한산 일대) time out at 5 km
        req = urllib.request.Request(url, data=urllib.parse.urlencode({'data': query(r)}).encode(),
                                     headers={'User-Agent': 'csie2026-hiking-data/0.1 (team project)'})
        try:
            data = json.load(urllib.request.urlopen(req, timeout=240))
            break
        except Exception as e:
            print(f"  overpass retry {attempt + 1} for {m['name']} ({url.split('/')[2]}): {e}", flush=True)
            time.sleep(20 * (attempt + 1))
    if data is None:
        return None  # not cached: the next run tries again
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(data, open(path, 'w', encoding='utf-8'), ensure_ascii=False)
    time.sleep(2)
    return data


def build(m, next_id, summit_gap_m, min_course_km):
    """-> (trails, courses, problem). Dict layout matches build_trails.py; pts are EPSG 5179."""
    data = fetch(m)
    if data is None:
        return [], [], 'Overpass fetch failed (rerun to retry)'
    els = data['elements']
    paths = [e for e in els if e['type'] == 'way' and re.fullmatch(PATHS, e['tags'].get('highway', '')) and is_trail(e['tags'])]
    roads = [e for e in els if e['type'] == 'way' and re.fullmatch(ROADS, e['tags'].get('highway', ''))]
    places = [(to_5179_from_wgs(e['lon'], e['lat']), e['tags'].get('name:ko') or e['tags'].get('name', ''))
              for e in els if e['type'] == 'node' and e['tags'].get('name')]
    if not paths:
        return [], [], 'no OSM paths'

    xy = {}
    for w in paths:
        for n, g in zip(w['nodes'], w['geometry']):
            xy[n] = to_5179_from_wgs(g['lon'], g['lat'])
    summit = to_5179_from_wgs(float(m['summit_lon']), float(m['summit_lat']))
    top = min(xy, key=lambda n: math.dist(xy[n], summit))
    if math.dist(xy[top], summit) > summit_gap_m:
        return [], [], f'summit {math.dist(xy[top], summit):.0f} m from OSM paths'

    use = collections.Counter(n for w in paths for n in set(w['nodes']))
    road_nodes = {n for w in roads for n in w['nodes']} & xy.keys()
    road_name = {n: w['tags'].get('name', '') for w in roads for n in w['nodes'] if w['tags'].get('name')}
    split = {n for n, c in use.items() if c > 1} | road_nodes | {top}
    segs = []
    for w in paths:
        t = w['tags']
        closed = False  # no-access ways are dropped by is_trail
        ns, start = w['nodes'], 0
        for i in range(1, len(ns)):
            if ns[i] in split or i == len(ns) - 1:
                piece = ns[start:i + 1]
                pts = [xy[n] for n in piece]
                segs.append({'nodes': piece, 'pts': pts, 'way': w['id'], 'name': t.get('name', ''), 'closed': closed,
                             'km': sum(math.dist(p, q) for p, q in zip(pts, pts[1:])) / 1000,
                             'surface': SURFACE.get(t.get('surface', ''), t.get('surface', '')),
                             'risk': '험로' if t.get('sac_scale') == ROCKY_SAC else ''})
                start = i

    adj = collections.defaultdict(list)
    for i, s in enumerate(segs):
        if not s['closed']:
            a, b = s['nodes'][0], s['nodes'][-1]
            adj[a].append((b, i)); adj[b].append((a, i))
    dist, prev, heap = {top: 0.0}, {}, [(0.0, top)]
    while heap:
        d, n = heapq.heappop(heap)
        if d > dist[n]:
            continue
        for n2, i in adj[n]:
            d2 = d + segs[i]['km']
            if d2 < dist.get(n2, 1e9):
                dist[n2], prev[n2] = d2, (n, i)
                heapq.heappush(heap, (d2, n2))

    ok = lambda n: min_course_km <= dist[n] <= MAX_COURSE_KM
    heads = [n for n in dist if n in road_nodes and ok(n)]
    if not heads:  # no road contact: dead ends of the network
        heads = [n for n in dist if len(adj[n]) == 1 and ok(n)]
    if not heads:
        return [], [], 'no OSM trailhead reaches the summit'
    # nearby road contacts are one trailhead: keep the closest-to-summit one (build_trails merges at 300 m too,
    # doing it here keeps the elevation lookups down)
    kept = []
    for n in sorted(heads, key=dist.get):
        if all(math.dist(xy[n], xy[k]) > SAME_START_M for k in kept):
            kept.append(n)
    heads = kept

    # trail rows: the open network connected to the summit (plus closed pieces touching it)
    keep = [i for i, s in enumerate(segs) if s['nodes'][0] in dist or s['nodes'][-1] in dist]
    sid = {i: next_id + k for k, i in enumerate(keep)}
    trails = [{'id': sid[i], 'source': 'osm', 'source_id': f"way/{segs[i]['way']}", 'mountain_id': m['id'],
               'mountain_name': m['name'], 'name': segs[i]['name'], 'length_km': round(segs[i]['km'], 3),
               'length_km_src': '', 'up_min': round(segs[i]['km'] * UP_MIN_PER_KM, 1),
               'down_min': round(segs[i]['km'] * DOWN_MIN_PER_KM, 1), 'surface': segs[i]['surface'],
               'closed': segs[i]['closed'], 'risk': segs[i]['risk'], 'difficulty_src': '', 'pts': segs[i]['pts']}
              for i in keep]

    courses = []
    for n in heads:
        path, cur = [], n
        while cur != top:
            cur, i = prev[cur]
            path.append(i)
        line, here = [], n
        for i in path:  # trailhead -> summit, flipping segments as needed
            ns, pts = segs[i]['nodes'], segs[i]['pts']
            if ns[0] != here:
                ns, pts = ns[::-1], pts[::-1]
            line += pts if not line else pts[1:]
            here = ns[-1]
        near = min(places, key=lambda p: math.dist(p[0], xy[n]), default=None)
        label = (near[1] if near and math.dist(near[0], xy[n]) <= PLACE_M else '') or road_name.get(n, '') \
            or segs[path[0]]['name'] or '무명'
        lon, lat = to_wgs_5179(*xy[n])
        km = dist[n]
        courses.append({'mountain_id': m['id'], 'mountain_name': m['name'], 'source': 'osm', 'start_name': label,
                        'start_lat': round(lat, 6), 'start_lon': round(lon, 6), 'length_km': round(km, 2),
                        'up_min': round(km * UP_MIN_PER_KM), 'down_min': round(km * DOWN_MIN_PER_KM),
                        'segment_ids': ';'.join(str(sid[i]) for i in dict.fromkeys(path)),
                        'risk': ' / '.join(dict.fromkeys(segs[i]['risk'] for i in path if segs[i]['risk'])),
                        'summit_height': float(m['height']), 'pts': line})
    return trails, courses, None
