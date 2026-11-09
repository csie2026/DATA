"""Consistency checks across all data/*.csv (and the matching .geojson). Prints problems; exit code 1 if any.
Per-row mountain checks (OSM, borders, heights) live in check_selected.py."""
import argparse, csv, json, math, sys
from pathlib import Path
from geo import P
from data_contract import load_identity, validate_scope, validate_features

issues = []
bad = lambda msg: issues.append(msg)


def read(name, data_dir=None):
    raw = (Path(data_dir or P('data')) / name).read_bytes()
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


def main(csv_only=False, data_dir=None):
    issues.clear()
    data_dir = Path(data_dir or P('data'))
    M = read('mountains.csv', data_dir)
    D = read('mountain_descriptions.csv', data_dir)
    T = read('trails.csv', data_dir)
    C = read('courses.csv', data_dir)
    try:
        validate_scope(M, C, load_identity())
    except (ValueError, KeyError) as exc:
        bad(str(exc))
    names = [l.strip() for l in (data_dir / 'mountain_names.txt').read_text(encoding='utf-8').splitlines() if l.strip()]

    # mountains
    ids = [r['id'] for r in M]
    if len(set(ids)) != len(ids) or not all(i.isdigit() and int(i) > 0 for i in ids):
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
    num('courses', C, 'start_elev_m', -500, 1500, blank=True)
    num('courses', C, 'up_min', 1, 600)
    num('courses', C, 'down_min', 1, 600)
    num('courses', C, 'start_lat', 36.8, 38.4)
    num('courses', C, 'start_lon', 126.3, 127.9)
    per = {}
    for r in C:
        if float(r['down_min']) > float(r['up_min']):
            bad(f'courses: 내리막 시간이 오르막보다 큽니다 ({r["name"]})')
        if bool(r['climb_m']) != bool(r['start_elev_m']):
            bad(f'courses: 고도와 상승고도 결측이 다릅니다 ({r["name"]})')
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
        climb = float(r['climb_m']) if r['climb_m'] else None
        want = '어려움' if km >= 8 or (climb is not None and climb >= 600) else '쉬움' if km < 3 and (climb is None or climb < 200) else '보통'
        if r['difficulty'] != want:
            bad(f'courses: difficulty {r["difficulty"]} != rule {want} ({r["mountain_name"]} {r["name"]})')

    # geojson mirrors csv; course line runs trailhead -> summit
    missing = []
    if not csv_only:
        for name, rows in (('trails', T), ('courses', C)):
            try:
                with (data_dir / (name + '.geojson')).open(encoding='utf-8') as stream:
                    collection = json.load(stream)
                if collection.get('type') != 'FeatureCollection':
                    raise ValueError('FeatureCollection 형식이 아닙니다.')
                validate_features(collection['features'], rows, mid, name)
            except FileNotFoundError:
                missing.append(name + '.geojson')
            except (ValueError, KeyError, TypeError) as exc:
                bad(f'{name}.geojson: {exc}')

    print('\n'.join(issues) or 'CSV 검사 통과')
    print(f'{len(M)} mountains, {len(D)} descriptions, {len(T)} trails, {len(C)} courses, {len(issues)} issues')
    if csv_only:
        print('GeoJSON 검증 제외 (--csv-only). 전체 데이터 검증 통과를 의미하지 않습니다.')
    elif missing:
        print('전체 검증 미완료: ' + ', '.join(missing) + ' 없음. 원본 산출물을 확보하거나 README의 재현 절차를 확인하세요.')
    elif not issues:
        print('GeoJSON 검사 통과')
    return 1 if issues else 2 if missing else 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv-only', action='store_true', help='CSV만 검사하고 GeoJSON 검증 제외를 명시')
    parser.add_argument('--data-dir', type=Path, help='검토용 후보 데이터 폴더 (기본값: DATA/data)')
    args = parser.parse_args()
    try:
        sys.exit(main(args.csv_only, args.data_dir))
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        print(f'검증 실패: 입력 파일의 존재 및 형식을 확인하세요 ({exc})', file=sys.stderr)
        sys.exit(1)
