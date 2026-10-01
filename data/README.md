# Mountain dataset (경기도)

The team's mountain list: 140 mountains, covering all 31 시·군 of 경기도. ids run to 141; 112 (도라산, inside the civilian control zone, no reachable trail) was removed and ids are never reused.

## Files

| File | What | Edit by |
|---|---|---|
| `mountains.csv` | Mountain table: one row per mountain, with summit coordinates and height. Sorted by `sigungu_name`, then `name`. | Hand (Excel). This is the source of truth. |
| `mountain_descriptions.csv` | 1–2 sentence description per mountain. `desc_src` is `forest_api` (cut from the 산림청 API text) or `generated` (written by us). | Hand (Excel) |
| `mountain_names.txt` | Mountain names in CSV order; `check_selected.py` compares it with the CSV. | Keep in sync with the CSV |
| `trails.csv` / `.geojson` | 산림청 trail segments of the selected mountains | `build_trails.py` |
| `courses.csv` / `.geojson` | Trailhead-to-summit courses, with difficulty | `build_trails.py` |
| `raw/` | Downloaded inputs: `forest_api.json` (산림청 산정보 API), `osm_peaks.json` (OSM `natural=peak`), `provinces_geo.json` (시도 경계), and `elevation_cache.json` (Open-Meteo DEM cache) | Scripts |
| `archive/` | Old 443-mountain pipeline (`mountains_443_old.csv`, `excluded_*`, `manual_summits.csv`, ...). It is superseded and kept only as a lookup pool for adding mountains. | Don't edit |

`mountains.csv` columns:
- `id`: the mountain id. It equals DB `mountains.id`, and `trails.csv` / `courses.csv` reference it as `mountain_id`. **Never renumber; a new mountain gets max id + 1.**
- `code` / `codes`: 산림청 mountain code / all merged codes. Only the data pipeline uses them (they are the only key into the 산림청 trail files; names are ambiguous), and they are not in the DB.
- `name`, `sigungu_name`, `address`
- `height` and `height_src`, where it came from: `forest_api`, `osm` or `manual`
- `summit_lat`, `summit_lon` and `summit_src`. When `summit_src` is `osm`, the coordinates are ODbL.

Trail statistics live in `trails.csv`. The weather grid and the official 시군구 code are added by `build_seed_sql.py`.

Names keep their parentheses, e.g. `검단산 (성남/광주)`: the parentheses tell same-name mountains apart.

## Scripts (`../scripts`)

| Script | Does |
|---|---|
| `check_data.py` | Cross-file checks across all CSVs and GeoJSONs: ids and foreign keys, value ranges, description rules, the difficulty rule, and whether each course line runs from its trailhead to the summit. It must print 0 issues. |
| `check_selected.py` | Sanity checks for `mountains.csv`. The remaining flags have been reviewed and accepted (border mountains, hills under 100 m, rows with no code, and so on). |
| `build_seed_sql.py <BE migration dir>` | Writes the BE Flyway files `V2__mountains.sql` (from the two CSVs) and `V3__courses.sql` (from `courses.geojson`; paths simplified to 2 m, difficulty as EASY/NORMAL/HARD). It adds the region and the KMA weather grid, and moves the Seoul border mountains and 수리산 under their Gyeonggi city. |
| `build_trails.py` | Builds `trails.*` and `courses.*` (`trails.id` = plain integers 1..N, renumbered on every rebuild; courses have no id (the DB assigns it); `mountain_id` → `mountains.id`; `courses.segment_ids` → `trails.id`; `trails.source` = forest/osm, `source_id` = 산림청 `MNTN_CODE-PMNTN_SN` (not unique) or OSM `way/<id>`; `courses.source` = forest/osm). Needs `../FRT000801` and `../mountain`. |
| `geo.py` | Shared paths and TM projections (EPSG 5179/5186); `python geo.py` runs the self-check. |
| `fetch_forest_api.py` | Re-downloads `raw/forest_api.json`. Needs `DATA_GO_KR_KEY` in `../.env`. |
| `archive/` | Old pipeline scripts (`build_mountains.py`, `build_selected.py`, `suggest_summits.py`). **Do not run them.** `build_selected.py` would overwrite the hand edits in `mountains.csv`, and the input paths have moved to `data/archive/`. |

After editing a CSV, run `check_data.py` and `check_selected.py`, then `build_seed_sql.py ../BE/src/main/resources/db/migration`.

## Courses (provisional)

- A trailhead is a 산림청 시종점 spot; the course is the shortest open path from it to the summit. Closed segments are not used.
- `up_min` and `down_min` are the 산림청 segment times, summed.
- `start_elev_m` comes from the Open-Meteo elevation API (Copernicus DEM 90 m).
- `difficulty`:
  - 어려움: climb ≥ 600 m or length ≥ 8 km
  - 쉬움: climb < 200 m and length < 3 km
  - 보통: everything else
- The thresholds are still being tuned.
- At most 5 courses per mountain. Their starts must be at least 45° apart as seen from the summit; within one direction the shortest course is kept.
- Courses with an average grade over 35% are dropped (a DEM error, or not a walking route).
- OSM courses fill in only the mountains with no 산림청 course.
  - The trailhead is where a path meets a road, and it is named after the nearest place.
  - Excluded ways: sac_scale T4 and above, poor trail visibility, informal paths, no access, sidewalks. T3 is kept and flagged as '험로'.
  - Times use 17.5 / 12.5 min per km.
  - Code: `scripts/osm_trails.py`. Overpass responses are cached in `raw/osm_paths/`.
- Rebuilt on 2026-10-02: 420 courses on 134 mountains (forest 242, OSM 178). Hand-excluded: 덕성산 신계리 (`EXCLUDE_COURSES` in build_trails.py).

## Sources

| Data | Provider | License |
|---|---|---|
| 등산로_전국 (FRT000801, TB_FGDI_WG_MT_WAY_ALL) | 산림빅데이터거래소, © 시선아이티 | CC BY |
| 등산로정보 산별 파일 (PMNTN, PMNTN_SPOT) | 산림청 forest.go.kr | No restriction on permitted use |
| 산정보 API (mntInfoOpenAPI2) | 산림청 via data.go.kr | Check the permitted-use terms on data.go.kr |
| 시도 경계 (2013) | 통계청 via github.com/southkorea/southkorea-maps | Check the repo license |
| natural=peak, paths (highway=path etc.) | © OpenStreetMap contributors | ODbL |
| Elevation | Copernicus DEM via Open-Meteo | Attribution required |

The trail survey baseline is 2016-12-31. The app must show attribution for 산림청 / 시선아이티, OSM, and Copernicus DEM.
