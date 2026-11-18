# DATA

ToPeak(경기도 등산 앱)의 산·등산 코스 데이터를 만들고 관리하는 저장소입니다.

경기도 31개 시·군의 산 140개와, 출발점에서 정상까지 가는 등산 코스 420개(산 134개)를 담고 있습니다. 이 데이터는 BE 저장소의 Flyway 마이그레이션(`V2__mountains.sql`, `V3__courses.sql`)으로 변환되어 DB에 들어갑니다.

## 구성

```
data/      산·등산로·코스 데이터(CSV)와 데이터셋 설명
scripts/   데이터 생성·검사 스크립트, BE 마이그레이션 SQL 생성
tests/     데이터 계약 단위 테스트
docs/      재현 절차, 원본 수집 기록(체크섬)·라이선스
API.md     데이터 수집과 날씨에 사용한 외부 API 명세
```

| 파일 | 내용 |
|---|---|
| `data/mountains.csv` | 산 140개: 이름, 시·군, 주소, 높이, 정상 좌표. 직접 관리하는 기준 원본 |
| `data/mountain_descriptions.csv` | 산별 1~2문장 소개 |
| `data/trails.csv` | 선정된 산의 등산로 구간(산림청, OpenStreetMap) |
| `data/courses.csv` | 출발점 → 정상 코스: 거리, 소요시간, 난이도, 위험 정보 |
| `scripts/build_trails.py` | 원본·캐시에서 구간과 코스 후보를 별도 빈 폴더에 생성. 기존 `data/`는 덮어쓰지 않음 |
| `scripts/build_seed_sql.py` | 산 CSV와 `courses.geojson`을 별도 빈 폴더의 검토용 SQL로 변환. 기존 migration 폴더 출력 금지 |
| `scripts/check_data.py`, `check_selected.py` | 데이터 정합성 검사 |
| `scripts/data_contract.py`, `geo.py`, `osm_trails.py` | 공용 검증 도구, 좌표 변환(EPSG 5179/5186), OSM 등산로·코스 생성(`build_trails.py`가 사용) |
| `scripts/fetch_forest_api.py` | 산림청 산정보 API 재수집(`.env`의 `DATA_GO_KR_KEY` 필요) |
| `requirements.txt` | `build_trails.py` 재생성용 `pyshp==2.3.1`. 검증 스크립트·테스트는 표준 라이브러리만 사용 |
| `scripts/check_seed.py` | CSV와 기존 BE seed의 전체 속성·ID·경로 비교. 실제 DB 연결 없음 |
| `data/seed_identity.json` | 제공된 기존 V2·V3 기준 산·코스 ID 대응표와 migration SHA-256. 자동 갱신 금지 |

## 21번 작업: 안전한 검증과 재현

원본 GeoJSON이 없어도 아래 검증은 가능합니다. Python 3.11 이상을 사용합니다.

```powershell
python -B scripts/check_data.py --csv-only
python -B scripts/check_seed.py
python -B -m unittest discover -s tests -v
```

`--csv-only` 통과는 전체 경로 검증 통과가 아닙니다. `python -B scripts/check_data.py`는 GeoJSON 누락 시 누락 파일을 알리고 종료 코드 2를 반환합니다. `check_selected.py`도 산별 외부 검증 입력이 없으면 2로 종료합니다. 오류는 1, 요청한 범위의 검증 통과는 0입니다.

**현재 공유 자료에는 `courses.geojson`, `trails.geojson`, 산림청 원본 및 `data/raw/` 캐시가 없습니다.** 원본·캐시(약 330MB)는 Git에 올리지 않고(`.gitignore`) 작업자 PC에만 있으며, 수집일과 SHA-256은 [재현 절차](docs/reproducibility.md)에 기록돼 있습니다. 같은 원본·캐시가 있으면 `build_trails.py`가 기존 GeoJSON·CSV와 바이트 동일한 결과를 만드는 것을 확인했습니다(2026-11-11). 원본이 없으면 기존 420개 코스와 경로를 재현할 수 없습니다. CSV에는 경로 좌표가 없고, seed의 경로는 단순화된 값이므로 원본 GeoJSON으로 역변환하지 않습니다.

`build_trails.py`는 산림청이 시종점 ZIP을 제공하지 않는 산(2026-09-27 수집본 기준 코드 45개)을 건너뛰고, 실제로 필요했던 누락 코드를 `provenance.json`의 `missing_trailhead_zips`에 기록합니다. 다른 입력이 없으면 중단합니다. 검사·생성 스크립트는 `--data-dir`로 별도 폴더의 데이터를 읽을 수 있습니다.

`check_seed.py`는 통과하지만, seed 경로 끝점이 정상 좌표에서 30m 넘게 떨어진 코스가 36개 있습니다(예: 우면산 약 286m). 정상·경로·난이도는 담당자 검토 전에 임의로 바꾸지 않습니다.

실제 입력 목록·확보 방법·재생성 명령·보관 방안·외부 출처 라이선스는 [재현 절차](docs/reproducibility.md)를 따릅니다. 현재 검증 범위와 승인 필요 사항은 DOCS의 `21번_데이터_계약.md`에도 정리돼 있습니다.

컬럼 정의, 코스 생성 규칙, 스크립트 실행 순서는 [`data/README_ko.md`](data/README_ko.md)에 있습니다.

## 데이터 흐름

```
산림청 등산로·산정보, OpenStreetMap, Open-Meteo 고도
        │  scripts/build_trails.py
        ▼
data/*.csv, courses.geojson ── scripts/build_seed_sql.py ──▶ BE V2__mountains.sql, V3__courses.sql ──▶ PostgreSQL
```

- 산 id는 DB `mountains.id`와 같으며 다시 매기지 않습니다. BE V2는 CSV id를 명시해 삽입하고, V3 코스는 id를 명시하지 않아 삽입 순서대로 1~420이 붙었습니다(그래서 `seed_identity.json`으로 고정).
- BE migration: V1 회원·일지, V2 산, V3 코스, V4~V8 활동·점수·목표·가입 시각, V9005 테스트 데이터 정리. V9000·V9001(테스트 코스·산)은 기존 운영 이력 호환용(`db/compat/rds-v9001`)으로만 남아 있고 신규 DB에는 쓰지 않습니다.
- 기존 V3의 삽입 순서로 만들어진 코스 ID 1~420을 `seed_identity.json`에 고정했습니다. 새 검토용 SQL에는 이 ID를 명시하므로 입력 행 순서가 달라도 ID가 유지됩니다. 출처·출발점·산·코스명 대응이 달라지면 자동 재배정하지 않고 중단합니다.
- 등산기록(`hiking_activities.course_id`)이 참조하므로 기존 코스 ID를 바꾸면 안 됩니다. 이미 적용된 V2·V3은 고치지 않고, 승인된 데이터 변경은 기존 ID를 유지하는 새 마이그레이션으로 반영합니다. 생성한 검토용 SQL을 기존 V2·V3 위에 복사하거나 운영 DB에 재적용하지 않습니다.

## DB 스키마

`build_seed_sql.py`가 만드는 BE 마이그레이션 V2·V3의 테이블입니다. BE는 별도 엔티티 없이 `JdbcTemplate`으로 조회합니다(`MountainController`). 응답은 DOCS API 명세서 M01~M03을 따르며 컬럼 전체를 내려주지는 않습니다.

| API | 응답에 쓰는 컬럼 |
|---|---|
| M01 `GET /api/mountains` | `id`, `name`, `sigungu_name`(→`city`), `height`, `lat`, `lng`, 코스 수(`courseCount`) |
| M02 `GET /api/mountains/{id}/courses` | 코스 `id`, `mountain_id`, `name`, `start_name`, `start_lat/lng`, `length_km`, `up_min`, `down_min`, `difficulty`, `risk`, `source` |
| M03 `GET /api/courses/{id}` | M02 필드 + `path`(JSON 목록으로 변환) |

`region`, `address`, `description`, `grid_nx/ny`, `start_elevation`, `climb`은 현재 API로 나가지 않습니다. 날씨 API(W01)가 `grid_nx/ny`를 내부에서 씁니다.

### mountains (산 140개)

| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | BIGINT PK | 1~141. **112(도라산)는 비어 있음.** id는 재사용하지 않으며, 새 산은 142번부터(V2가 시퀀스를 142로 재시작). BE 로컬 전용 `db/local-test`의 `테스트산`도 142번을 쓰므로 로컬 DB에 남아 있을 수 있음(운영에서는 V9005가 제거) |
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
| id | BIGINT PK | 기존 1~420의 대응을 고정. 검토용 SQL은 ID를 명시하고 다음 번호를 421로 설정. 기존 DB에는 적용하지 않음 |
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
- 코스가 없는 산 6개: 여기산, 고왕산, 방울산, 심술산, 쌍봉산, 오두산 (화성). M01의 `courseCount`가 0이라 FE가 "등록된 코스 없음"으로 표시하고, M02는 404가 아니라 빈 목록을 반환합니다.
- 난이도 기준 유지: 어려움 = 오르막 600m 이상 또는 거리 8km 이상, 쉬움 = 오르막 200m 미만이면서 3km 미만, 나머지 보통. 고도 결측 시 거리 3km 미만은 쉬움, 8km 이상은 어려움, 그 사이는 보통이라는 기존 분기도 유지합니다.

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
- 앱 전체 API 명세: DOCS 저장소 [`ToPeak API 명세서.md`](https://github.com/csie2026/DOCS/blob/main/ToPeak%20API%20%EB%AA%85%EC%84%B8%EC%84%9C.md)

## 출처

| 데이터 | 출처 | 조건 |
|---|---|---|
| 등산로·코스(`FOREST`) | 산림청, 산림빅데이터거래소 © 시선아이티 | CC BY |
| 등산로·코스(`OSM`), 정상 좌표 99개(`summit_src=osm`) | © OpenStreetMap contributors | ODbL |
| 출발점 고도 | Copernicus DEM (Open-Meteo) | 출처 표시 |
| 날씨(BE에서 사용) | 기상청 | 공공누리 제1유형(출처 표시) |

앱에는 위 출처를 표시해야 합니다. 전체 출처와 라이선스는 [`data/README_ko.md`](data/README_ko.md#출처)를 참고하세요.
