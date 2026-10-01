# 경기도 산 데이터셋

팀에서 고른 산 목록입니다. 산은 140개이고, 경기도 31개 시·군에 모두 1개 이상 있습니다. id는 141까지이며 112번(도라산: 민통선 안이라 정상까지 가는 등산로가 없음)은 제외했습니다. id는 재사용하지 않습니다.

## 파일

| 파일 | 내용 | 수정 방법 |
|---|---|---|
| `mountains.csv` | 산 테이블. 산 하나가 한 행이고, 정상 좌표와 높이가 들어 있습니다. `sigungu_name` 순으로 정렬하고, 같은 시·군 안에서는 `name` 순입니다. | 직접 수정 (엑셀). **기준 원본입니다.** |
| `mountain_descriptions.csv` | 산마다 1~2문장 설명. `desc_src`는 `forest_api`(산림청 API 원문에서 발췌)이거나 `generated`(직접 작성)입니다. | 직접 수정 (엑셀) |
| `mountain_names.txt` | CSV와 같은 순서의 산 이름 목록입니다. `check_selected.py`가 CSV와 비교합니다. | CSV와 맞춰서 유지 |
| `trails.csv` / `.geojson` | 선정된 산의 산림청 등산로 구간 | `build_trails.py` |
| `courses.csv` / `.geojson` | 출발점에서 정상까지 가는 코스와 난이도 | `build_trails.py` |
| `raw/` | 내려받은 원본: `forest_api.json`(산림청 산정보 API), `osm_peaks.json`(OSM `natural=peak`), `provinces_geo.json`(시도 경계), `elevation_cache.json`(Open-Meteo 고도 캐시) | 스크립트 |
| `archive/` | 예전 443개 산 파이프라인(`mountains_443_old.csv`, `excluded_*`, `manual_summits.csv` 등). 더 이상 쓰지 않으며, 산을 추가할 때 후보를 찾는 용도로만 남겨 둡니다. | 수정 금지 |

### `mountains.csv` 컬럼

| 컬럼 | 설명 |
|---|---|
| `id` | 산 id. DB `mountains.id`와 같은 값이고, `trails.csv`와 `courses.csv`가 `mountain_id`로 참조합니다. **번호를 다시 매기면 안 됩니다. 새 산은 가장 큰 id + 1로 추가합니다.** |
| `code` / `codes` | 산림청 산 코드 / 같은 산으로 합쳐진 코드 전체. 데이터 파이프라인에서만 씁니다. 산림청 등산로 파일과 연결할 수 있는 유일한 키이고, 산 이름은 같은 이름이 많아서 키로 쓸 수 없습니다. DB에는 넣지 않습니다. |
| `name`, `sigungu_name`, `address` | 산 이름, 시·군, 주소 |
| `height`, `height_src` | 높이(m)와 그 출처: `forest_api`, `osm`, `manual` |
| `summit_lat`, `summit_lon`, `summit_src` | 정상 좌표와 그 출처. `summit_src`가 `osm`이면 좌표는 ODbL 라이선스입니다. |

- 등산로 통계는 `trails.csv`에 있습니다. 날씨 격자 좌표와 표준 시군구 코드는 `build_seed_sql.py`가 SQL을 만들 때 계산해서 넣습니다.
- 산 이름의 괄호도 이름의 일부입니다(예: `검단산 (성남/광주)`). 같은 이름의 산을 구분하는 용도입니다.

### `trails.csv` 컬럼

| 컬럼 | 설명 |
|---|---|
| `id` | 구간 id. 1부터 빠짐없이 이어지는 정수이고, 다시 생성할 때마다 새로 매겨집니다. |
| `source`, `source_id` | 출처: `forest`(산림청, 키 `MNTN_CODE-PMNTN_SN`, **유일하지 않음**) 또는 `osm`(OpenStreetMap, 키 `way/<id>`) |
| `mountain_id`, `mountain_name` | 산 (`mountains.id`) |
| `name` | 구간 이름. 절반 이상이 비어 있습니다. |
| `length_km` | 지도 경로로 직접 잰 길이. `length_km_src`는 산림청 속성값이고, 일부 구간은 실제 경로와 다릅니다. |
| `up_min`, `down_min` | 산림청 기준 오르막·내리막 소요시간(분) |
| `surface`, `closed`, `risk` | 노면, 폐쇄 여부, 위험 정보(암벽, 추락 위험, 뱀 등) |
| `difficulty_src` | 산림청 원래 난이도. 99%가 '쉬움'이라 쓸 수 없습니다. |

### `courses.csv` 컬럼

| 컬럼 | 설명 |
|---|---|
| `mountain_id`, `mountain_name` | 산 (`mountains.id`). 코스 id는 따로 없고, DB에 넣을 때 DB가 붙입니다. |
| `source` | `forest`(산림청 등산로) 또는 `osm`(산림청 코스가 없는 산만 OpenStreetMap으로 채움, ODbL 출처 표시 필요) |
| `name`, `start_name` | 코스 이름(`<출발점> 코스 N`), 출발점 이름 |
| `start_lat`, `start_lon`, `start_elev_m` | 출발점 좌표와 고도 |
| `climb_m` | 오르막 높이 = 정상 높이 − 출발점 고도 |
| `length_km`, `up_min`, `down_min` | 편도 거리, 오르막·내리막 소요시간 |
| `difficulty` | 쉬움 / 보통 / 어려움 (기준은 아래 참고) |
| `risk` | 코스에 들어 있는 구간의 위험 정보 |
| `segment_ids` | 코스를 이루는 구간들 (`trails.id`, `;`로 구분) |

## 스크립트 (`../scripts`)

| 스크립트 | 하는 일 |
|---|---|
| `check_data.py` | CSV와 GeoJSON 전체를 서로 대조해서 검사합니다. id와 참조 관계, 값 범위, 설명 규칙, 난이도 기준, 코스 선이 출발점에서 정상까지 이어지는지를 봅니다. **결과가 0 issues여야 합니다.** |
| `check_selected.py` | `mountains.csv`의 산별 검사입니다(OSM 정상, 도 경계, 높이 등). 남아 있는 경고는 모두 확인하고 넘어간 항목입니다(경계에 걸친 산, 100m 미만 산, 코드 없는 산 등). |
| `build_seed_sql.py <BE 마이그레이션 폴더>` | BE Flyway 파일 `V2__mountains.sql`(CSV 두 개)과 `V3__courses.sql`(`courses.geojson`, 경로는 2m 기준으로 단순화, 난이도는 EASY/NORMAL/HARD)을 만듭니다. 권역과 기상청 격자 좌표를 넣고, 서울 경계에 있는 산과 수리산은 인접한 경기 시·군으로 지정합니다. |
| `build_trails.py` | `trails.*`와 `courses.*`를 만듭니다. `../FRT000801`과 `../mountain` 폴더가 필요합니다. |
| `geo.py` | 공용 경로와 좌표 변환(EPSG 5179/5186). `python geo.py`를 실행하면 자체 검사를 합니다. |
| `fetch_forest_api.py` | `raw/forest_api.json`을 다시 내려받습니다. `../.env`에 `DATA_GO_KR_KEY`가 있어야 합니다. |
| `archive/` | 예전 파이프라인 스크립트(`build_mountains.py`, `build_selected.py`, `suggest_summits.py`). **실행 금지.** `build_selected.py`를 실행하면 엑셀로 고친 `mountains.csv`를 덮어씁니다. 입력 파일도 `data/archive/`로 옮겨져 있어서 그대로는 동작하지 않습니다. |

CSV를 고친 다음에는 아래 순서로 실행합니다.

```
python scripts/check_data.py
python scripts/check_selected.py
python scripts/build_seed_sql.py ../BE/src/main/resources/db/migration
```

## 코스 (임시)

- 출발점은 산림청 '시종점' 지점입니다. 코스는 출발점에서 정상까지 가는 최단 경로이고, 폐쇄된 구간은 쓰지 않습니다.
- `up_min`, `down_min`은 산림청 구간 소요시간을 더한 값입니다.
- `start_elev_m`은 Open-Meteo 고도 API에서 가져옵니다(Copernicus DEM 90m).
- `difficulty` 기준:
  - 어려움: 오르막 600m 이상 또는 거리 8km 이상
  - 쉬움: 오르막 200m 미만이면서 거리 3km 미만
  - 보통: 나머지
- 기준값은 아직 조정 중입니다.
- 산마다 최대 5개만 남깁니다. 정상에서 본 출발 방향이 45° 이상 서로 다른 코스를 고르고, 같은 방향이면 가장 짧은 코스를 남깁니다.
- 평균 경사가 35%를 넘는 코스는 뺍니다(고도 데이터 오류이거나 걸어서 오르는 길이 아님).
- OSM 코스: 출발점은 등산로가 도로와 만나는 지점이고, 이름은 가장 가까운 동·리입니다. 험로(sac_scale T4 이상), 잘 안 보이는 길, 비공식 샛길, 통행금지 길, 인도는 쓰지 않습니다. T3(바위 구간)는 `risk`에 '험로'로 표시합니다. 소요시간은 산림청 평균과 같은 1km당 17.5분(오르막)과 12.5분(내리막)입니다.
- 2026-10-02에 다시 생성했습니다. 산 134개, 코스 420개입니다(산림청 242, OSM 178). 직접 제외한 코스: 덕성산 신계리 (`build_trails.py`의 `EXCLUDE_COURSES`).

## 출처

| 데이터 | 제공 | 라이선스 |
|---|---|---|
| 등산로_전국 (FRT000801, TB_FGDI_WG_MT_WAY_ALL) | 산림빅데이터거래소, © 시선아이티 | CC BY |
| 등산로정보 산별 파일 (PMNTN, PMNTN_SPOT) | 산림청 forest.go.kr | 이용허락범위 제한 없음 |
| 산정보 API (mntInfoOpenAPI2) | 산림청 (data.go.kr) | data.go.kr에서 이용허락범위 확인 필요 |
| 시도 경계 (2013) | 통계청 (github.com/southkorea/southkorea-maps) | 저장소 라이선스 확인 필요 |
| natural=peak, 등산로(highway=path 등) | © OpenStreetMap contributors | ODbL |
| 고도 | Copernicus DEM (Open-Meteo) | 출처 표시 필요 |

등산로 조사 기준일은 2016-12-31입니다. 앱에는 산림청 / 시선아이티, OSM, Copernicus DEM의 출처를 표시해야 합니다.
