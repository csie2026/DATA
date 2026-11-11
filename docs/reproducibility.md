# 21번 데이터 재현·검증 절차

## 현재 가능한 검증과 한계

이 공유본은 산 140개, 구간 11,257개, 코스 420개의 CSV와 기존 BE seed를 포함합니다. 코스가 있는 산은 134개입니다. 코스가 없는 산 6개는 여기산, 고왕산, 방울산, 심술산, 쌍봉산, 오두산 (화성)입니다. 없는 코스를 임의 생성하지 않습니다.

`data/*.geojson`은 `.gitignore`에 명시적으로 제외되어 있습니다. 코드상 `build_trails.py`가 만드는 중간 산출물이며 원천 데이터 자체는 아닙니다. 이번 ZIP에서 제외된 구체적인 작업자 사정이나 실제 저장소의 Git 이력은 확인할 수 없습니다.

CSV만으로는 선형 경로를 복원할 수 없습니다. BE seed의 `path`는 2m 단순화 및 소수 6자리 반올림을 거쳤으므로 원본 GeoJSON의 대체 입력으로 쓰지 않습니다. 현재 자료로 원본 → GeoJSON → seed 전체 재현은 불가능합니다. 원본·캐시를 확보하기 전에는 아래 제한 검증만 실행합니다.

```powershell
# DATA 폴더에서 실행
python -B scripts/check_data.py --csv-only
python -B scripts/check_seed.py
python -B scripts/geo.py
python -B -m unittest discover -s tests -v
```

`check_seed.py`는 실제 PostgreSQL에 연결하지 않습니다. 기존 V2·V3을 메모리 SQLite에서 해석해 CSV와 비교하고, seed SHA-256·고정 ID·단순화 경로를 검사합니다. PostgreSQL migration 실행 검증과는 다릅니다.

## 필요한 입력과 역할

| 경로 (DATA 기준) | 역할·확보 방법 | 보관 필요성 |
| --- | --- | --- |
| `data/mountains.csv` | 직접 관리하는 산 기준 원본. 이름·ID·높이·정상 좌표·산림청 코드 | Git 유지, ID 재사용 금지 |
| `data/mountain_descriptions.csv`, `mountain_names.txt` | 설명·이름 검증과 산 seed 생성 | Git 유지 |
| `data/seed_identity.json` | 기존 V2·V3의 산·코스 ID 대응과 체크섬 | Git 유지, 임의 갱신 금지 |
| `FRT000801/TB_FGDI_WG_MT_WAY_ALL.{shp,shx,dbf,prj}` | 기존 작업자가 사용한 산림빅데이터거래소 등산로_전국 원본 묶음 | 당시 파일 전체와 수집일·버전·체크섬 보존 |
| `mountain/mountain/<산코드>_geojson.zip` | 산림청 산별 `PMNTN_SPOT` 시종점. CSV의 `codes` 및 우면산 추가 코드 `116500401` 사용 | 해당 원본 ZIP과 순서·내용 보존 |
| `data/raw/osm_paths/<mountain_id>.json` | 산림청 후보 코스가 없는 산의 OSM Overpass 원응답 | 당시 캐시 보존. 새 조회는 기존 스냅샷 재현이 아님 |
| `data/raw/elevation_cache.json` | 출발점 좌표 소수 5자리 키별 Open-Meteo 고도 | 당시 캐시 보존. `null`은 결측으로 유지 |
| `data/raw/provinces_geo.json`, `osm_peaks.json` | `check_selected.py`의 도 경계·정상 좌표·높이 외부 대조 | 산별 외부 검증에 필요. 기존 담당자 스냅샷 확보 |
| `data/raw/forest_api.json` | 산정보 API에서 확보한 과거 원본·출처 추적 | 현재 코스 생성의 직접 입력은 아님 |
| `data/trails.geojson`, `courses.geojson` | 구간·코스 경로와 CSV 속성을 담은 중간 산출물 | 기존 2026-10-02 산출물 우선 확보·체크섬 보존 |

산림청 원본 SHP는 EPSG:5179, 산별 시종점 JSON은 EPSG:5186을 전제로 기존 좌표 변환을 유지합니다. 이름이 같은 최신 자료라고 해서 당시 입력과 동일하다고 간주하지 않습니다. 원본 획득 경로가 바뀌었으면 담당자의 원본 묶음을 우선 확보합니다. 과거 `scripts/archive/`를 실행해 수작업 기준 CSV를 다시 만들지 않습니다.

## 원본 산출물을 확보한 경우

아래는 PowerShell 예시입니다. `../phase21-input` 등 경로는 매번 새 빈 폴더를 사용합니다. 기존 `DATA/data`와 BE migration을 덮어쓰지 않습니다.

```powershell
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory ../phase21-input
Copy-Item data/*.csv ../phase21-input/
Copy-Item data/mountain_names.txt ../phase21-input/
# 담당자에게 받은 동일 버전의 trails.geojson과 courses.geojson을 phase21-input에 배치
python -B scripts/check_data.py --data-dir ../phase21-input
python -B scripts/check_seed.py --data-dir ../phase21-input
python -B scripts/build_seed_sql.py ../phase21-sql --data-dir ../phase21-input
```

`check_data`는 CSV↔GeoJSON의 전체 속성·구간 참조·난이도·경로를 검사합니다. `check_seed`는 CSV↔기존 seed 대조이며 원본과 단순화 경로의 완전 동일성까지 증명하지 않습니다. 생성 후보 SQL의 경로는 원본 GeoJSON이 있을 때만 기존 단순화 함수를 거쳐 만들어집니다. 기존 seed 경로와 새 후보의 추가 대조 후에 검토 결과를 기록합니다.

## 원본에서 다시 생성해야 하는 경우

1. 담당자의 당시 원본·캐시 묶음을 위 경로로 확보하고 SHA-256과 수집일을 기록합니다. 두 GeoJSON이 있으면 위의 직접 검증을 우선합니다.
2. Python 3.11 이상 환경에서 `python -m pip install -r requirements.txt`로 `pyshp==2.3.1`을 설치합니다. CSV/seed 검사와 단위 테스트는 표준 라이브러리만 사용합니다.
3. `python -B scripts/build_trails.py ../phase21-generated`를 실행합니다. 기본은 오프라인입니다. 필요한 SHP·OSM·고도 캐시가 없거나 코스 420개·기존 ID 대응이 달라지면 중단합니다. 산별 시종점 ZIP은 산림청이 일부 산(2026-09-27 수집본 기준 45개 코드, 예: 우면산 412900201)에 제공하지 않으므로 없으면 건너뛰고 `provenance.json`의 `missing_trailhead_zips`에 기록합니다. 이 ZIP 없이 생성한 결과가 기존 GeoJSON·CSV와 바이트 동일함을 확인했습니다. 기존 난이도·최단 경로·코스 선정 기준은 유지합니다.
4. 생성된 폴더에 `mountains.csv`, `mountain_descriptions.csv`, `mountain_names.txt`를 복사해 `check_data.py --data-dir ../phase21-generated`를 실행합니다.
5. `check_seed.py --data-dir ../phase21-generated`로 기존 속성과 비교합니다. 다르면 후보를 현행 데이터에 적용하지 말고 차이를 검토합니다.
6. 검증 후 `build_seed_sql.py ../phase21-sql --data-dir ../phase21-generated`로 검토용 SQL을 생성합니다. 출력은 빈 별도 폴더만 허용합니다. 새 코스 SQL은 기존 1~420의 ID를 명시하고 시퀀스 다음 값을 421로 설정합니다.

OSM·고도 캐시를 새로 수집해야 한다면 `--allow-network`를 명시해야 합니다. 이 옵션은 새 후보 수집을 허용할 뿐 기존 데이터 범위 변경을 승인하지 않습니다. 외부 서비스 재시도 결과, 현재 OSM 수정, 타임아웃 후 조회 반경 축소 등으로 기존 결과와 달라질 수 있습니다. 네트워크 실패는 빈 코스로 바꾸지 않고 전체 생성을 중단합니다. 생성 성공 시 `provenance.json`에 입력·스크립트·결과 체크섬, Python·pyshp 버전과 네트워크 허용 여부를 기록합니다. 과거 원본의 체크섬은 자료가 없어 소급 생성하지 않았습니다.

## 식별자와 변경 절차

- 산 ID는 CSV와 `mountains.id`가 같은 값입니다. 112는 제외된 ID이며 재사용하지 않습니다.
- `trails.id`는 DATA 내 구간 연결 키로 재생성 시 바뀔 수 있습니다. `courses.segment_ids`가 참조하며 BE `courses.id`와 다른 개념입니다. `source_id`도 구간별 유일키라고 볼 수 없습니다.
- `seed_identity.json`의 코스 ID는 기존 V3의 삽입 순서에서 추출하고 현재 CSV 전체 속성과 대조한 결과입니다. `(mountain_id, name)`으로 대응을 찾되 출처·출발점 좌표도 함께 확인합니다. 후보 순서 변경은 ID에 영향을 주지 않습니다. 자동 생성 코스명은 영구 자연키가 아니므로 이름·출발점·출처 변경은 자동 병합하지 않고 중단합니다.
- 경로만 크게 달라진 경우 같은 출발점·이름이어도 동일한 코스로 확정하지 않습니다. 원본·경로 비교와 담당자 검토가 필요합니다.
- 실제 운영 DB가 다른 ID를 가지고 있다면 이 대응표를 운영 기준이라고 선언하거나 덮어쓰지 않습니다. 운영 참조를 조사한 뒤 팀장 승인으로 별도 변경 계획을 수립합니다.
- 기존 V2·V3은 그대로 유지합니다. 데이터 변경이 승인되면 새 Flyway migration에서 기존 ID를 유지하는 제한적 UPDATE/INSERT를 검토합니다. DELETE·TRUNCATE·ID 재배정·기존 활동/일지 재연결은 이번 작업에 포함하지 않습니다.

## 보관과 외부 출처

대용량 원본을 무조건 Git에 넣지 않습니다. 팀의 버전 보관 스토리지 또는 승인된 Git LFS/DVC 중 하나를 선택해 원본·캐시·GeoJSON·체크섬·수집일·출처·이용조건을 버전별로 묶는 방안을 제안합니다. 아직 저장 위치나 운영 정책은 결정되지 않았습니다. `.env`, API 키, 세션 쿠키, 개인 GPS 기록은 보관 묶음에 넣지 않습니다. 현재 `.gitignore`의 원본·캐시 제외는 유지하며 문서와 작은 ID 대응표만 Git 관리 대상으로 추가했습니다.

2026-11-08 확인 기준:

- [OpenStreetMap 저작권·라이선스](https://www.openstreetmap.org/copyright/en): ODbL, 기여자 표시 및 라이선스 안내를 확인했습니다. 데이터 배포 형태에 따른 의무도 함께 검토해야 합니다.
- [Open-Meteo 고도 API](https://open-meteo.com/en/docs/elevation-api): Copernicus DEM GLO-90 기반이며 Copernicus와 Open-Meteo 출처 표시를 요구합니다. 서비스 이용 형태에 맞는 조건도 확인해야 합니다.
- [산림빅데이터거래소 FRT000801](https://www.bigdata-forest.kr/product/FRT000801): 기존 프로젝트 문서는 시선아이티·CC BY로 기록하지만 이번 직접 조회는 타임아웃으로 최신 상품 조건을 확인하지 못했습니다. 당시 내려받은 라이선스 원문을 담당자에게 확보해야 합니다.
- [산림청 등산로 안내](https://www.forest.go.kr/kfsweb/kfi/kfs/trail/trailInformation.do?mn=NKFS_06_08_02), [공공데이터포털 등산로](https://www.data.go.kr/data/3034022/fileData.do): 원본 확보 후보 경로입니다. 이번 직접 조회 제한으로 현재 산별 ZIP 형식·이용조건을 확정하지 않았습니다. 신규 파일이 기존 EPSG·필드 구조와 맞는지 검토해야 합니다.
- `check_selected.py`용 도 경계와 OSM 정상 캐시의 정확한 생성 스크립트는 현재 공유본에 없습니다. 기존 원본 묶음·출처·버전을 확보하기 전에는 재현 완료로 표시하지 않습니다.

## 운영 DB 검증

BE `docs/verify-data-readonly.sql`은 제공된 seed 전체 속성·ID·경로 문자열 체크섬과 산행 활동/일지 참조를 확인하는 PostgreSQL 읽기 전용 SQL입니다. 실제 DB에서 실행하지 않았고 PostgreSQL 문법 실행 검증도 아직 하지 않았습니다. 팀의 접근 절차를 따라 읽기 전용 계정으로 실행해 결과를 검토합니다. 차이가 발견되면 데이터 복구·변경 없이 보고합니다. 이 SQL은 migration이 아니며 Flyway 폴더에 복사하지 않습니다.

seed 경로 끝점이 정상 좌표에서 30m 넘게 떨어진 코스 36개가 있습니다. 기존 300m 경로 연결 허용 범위에는 들어가지만 GPS 정상 도달 반경 30m와는 다릅니다. 경로 끝점만으로 완등을 인정하거나 정상 좌표·난이도를 임의 변경하지 않습니다. 현장 또는 담당자 자료로 정상·경로를 검토할 사항입니다.
