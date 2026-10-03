# DATA

ToPeak(경기도 등산 앱)의 산·등산 코스 데이터를 만들고 관리하는 저장소입니다.

경기도 31개 시·군의 산 140개와, 출발점에서 정상까지 가는 등산 코스 420개(산 134개)를 담고 있습니다. 이 데이터는 BE 저장소의 Flyway 마이그레이션(`V2__mountains.sql`, `V3__courses.sql`)으로 변환되어 DB에 들어갑니다.

## 구성

```
data/      산·등산로·코스 데이터(CSV)와 데이터셋 설명
scripts/   데이터 생성·검사 스크립트, BE 마이그레이션 SQL 생성
API.md     데이터 수집과 날씨에 사용한 외부 API 명세
```

| 파일 | 내용 |
|---|---|
| `data/mountains.csv` | 산 140개: 이름, 시·군, 주소, 높이, 정상 좌표. 직접 관리하는 기준 원본 |
| `data/mountain_descriptions.csv` | 산별 1~2문장 소개 |
| `data/trails.csv` | 선정된 산의 등산로 구간(산림청, OpenStreetMap) |
| `data/courses.csv` | 출발점 → 정상 코스: 거리, 소요시간, 난이도, 위험 정보 |
| `scripts/build_trails.py` | 등산로 원본에서 구간과 코스를 생성(`trails.*`, `courses.*`). GeoJSON은 Git에 올리지 않고 이 스크립트로 다시 만듭니다 |
| `scripts/build_seed_sql.py` | 산 CSV와 `courses.geojson`을 BE 마이그레이션 SQL(V2, V3)로 변환 |
| `scripts/check_data.py`, `check_selected.py` | 데이터 정합성 검사 |

컬럼 정의, 코스 생성 규칙, 스크립트 실행 순서는 [`data/README_ko.md`](data/README_ko.md)에 있습니다.

## 데이터 흐름

```
산림청 등산로·산정보, OpenStreetMap, Open-Meteo 고도
        │  scripts/build_trails.py
        ▼
data/*.csv, courses.geojson ── scripts/build_seed_sql.py ──▶ BE V2__mountains.sql, V3__courses.sql ──▶ PostgreSQL
```

- 산 id는 DB `mountains.id`와 같으며 다시 매기지 않습니다.
- 코스 id는 DB가 붙이고, 등산기록(`hiking_activities.course_id`)이 참조하므로 바꾸면 안 됩니다. 이미 적용된 V2·V3은 고치지 않고, 데이터 변경은 기존 id를 유지하는 새 마이그레이션으로 반영합니다.

## DB 스키마

`build_seed_sql.py`가 만드는 BE 마이그레이션 V2·V3의 테이블입니다. BE는 별도 엔티티 없이 `JdbcTemplate`으로 조회하며, API가 응답하는 필드는 DOCS API 명세서 M01~M03을 따릅니다.

### mountains (산 140개)

| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | BIGINT PK | 1~141. **112(도라산)는 비어 있음.** id는 재사용하지 않으며, 새 산은 142번부터 |
| name | VARCHAR(30) UNIQUE | 같은 이름의 산은 괄호로 구분합니다(예: `검단산 (성남/광주)`, `검단산 (하남/광주)`). 46개가 괄호를 포함합니다 |
| region | VARCHAR(10) | 권역 `NORTH` / `EAST` / `CENTRAL` / `SOUTH` |
| sigungu_code | VARCHAR(5) | 행정표준 시군구 코드(예: `41410`) |
| sigungu_name | VARCHAR(20) | 탐색 화면용 경기 시·군(31개). 서울 경계 산 8개와 수리산은 인접한 경기 시·군으로 지정 |
| address | VARCHAR(100) | 실제 주소. 경계에 걸친 산 13개는 서울·인천·강원 주소 |
| height | DOUBLE PRECISION | 정상 높이(m) |
| lat, lng | DOUBLE PRECISION | 정상 좌표(WGS84) |
| grid_nx, grid_ny | INTEGER | 기상청 단기예보 격자 좌표(날씨 API가 사용) |
| description | VARCHAR(300) | 1~2문장 소개 |

### courses (코스 420개, 산 134개)

| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | BIGINT PK | DB가 자동으로 붙임. 등산기록이 참조하므로 바꾸지 않습니다 |
| mountain_id | BIGINT FK → mountains.id | |
| source | VARCHAR(10) | `FOREST`(산림청 등산로) / `OSM`(OpenStreetMap) |
| name | VARCHAR(50) | 코스 이름(예: `도평리 코스 3`). 산 안에서 유일 |
| start_name | VARCHAR(30) | 출발점 이름(동·리 등) |
| start_lat, start_lng | DOUBLE PRECISION | 출발점 좌표 |
| start_elevation | INTEGER | 출발점 고도(m) |
| climb | INTEGER | 오르막 높이(m) = 정상 높이 − 출발점 고도 |
| length_km | DOUBLE PRECISION | 출발점 → 정상 편도 거리 |
| up_min, down_min | INTEGER | 오르막·내리막 소요시간(분) |
| difficulty | VARCHAR(10) | `EASY` / `NORMAL` / `HARD` |
| risk | VARCHAR(100) | 위험 정보(예: `험로`, `암석코스 추락위험`), 없으면 NULL |
| path | TEXT | 출발점 → 정상 경로. `[[lng,lat],[lng,lat],...]` JSON 문자열(GeoJSON LineString 좌표 순서) |

- 산마다 코스는 최대 5개이며, 정상에서 본 출발 방향이 서로 다른 코스로 골랐습니다.
- 코스가 없는 산 6개: 여기산, 고왕산, 방울산, 심술산, 쌍봉산, 오두산 (화성). 화면에서 "등록된 코스가 없어요" 처리가 필요합니다.
- 난이도 기준(임시): 어려움 = 오르막 600m 이상 또는 거리 8km 이상, 쉬움 = 오르막 200m 미만이면서 3km 미만, 나머지 보통.

### SQL 예시

```sql
-- 권역·시군별 산
SELECT region, sigungu_name, id, name, height FROM mountains ORDER BY region, sigungu_name, name;

-- 한 산의 코스(짧은 순)
SELECT id, name, length_km, climb, up_min, difficulty FROM courses WHERE mountain_id = 53 ORDER BY length_km;

-- 코스가 없는 산
SELECT m.name FROM mountains m LEFT JOIN courses c ON c.mountain_id = m.id WHERE c.id IS NULL;
```

## 관련 문서

- 데이터셋 상세: [`data/README_ko.md`](data/README_ko.md)
- 사용한 외부 API: [`API.md`](API.md)
- 앱 전체 API 명세: DOCS 저장소 [`ToPeak_API명세서.md`](https://github.com/csie2026/DOCS/blob/main/ToPeak_API%EB%AA%85%EC%84%B8%EC%84%9C.md)

## 출처

| 데이터 | 출처 | 조건 |
|---|---|---|
| 등산로·코스(`FOREST`) | 산림청, 산림빅데이터거래소 © 시선아이티 | CC BY |
| 등산로·코스(`OSM`), 정상 좌표 99개(`summit_src=osm`) | © OpenStreetMap contributors | ODbL |
| 출발점 고도 | Copernicus DEM (Open-Meteo) | 출처 표시 |
| 날씨(BE에서 사용) | 기상청 | 공공누리 제1유형(출처 표시) |

앱에는 위 출처를 표시해야 합니다. 전체 출처와 라이선스는 [`data/README_ko.md`](data/README_ko.md#출처)를 참고하세요.
