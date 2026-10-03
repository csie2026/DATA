# 사용한 외부 API 명세

산·코스 데이터 구축과 날씨 기능에 사용한 외부 API의 호출 방법, 사용 범위(호출 한도·라이선스), 우리 프로젝트의 사용량을 정리한 문서입니다.
우리 BE가 제공하는 API(`GET /api/mountains/{id}/weather` 등)는 DOCS 저장소의 [`ToPeak_API명세서.md`](https://github.com/csie2026/DOCS/blob/main/ToPeak_API%EB%AA%85%EC%84%B8%EC%84%9C.md)를 참고하세요.

## 한눈에 보기

| API | 용도 | 호출 시점 | 인증 | 호출 한도 | 라이선스 / 출처 표시 |
|---|---|---|---|---|---|
| [기상청 단기예보](#1-기상청-단기예보-조회서비스) | 산별 날씨, 등산 적합도 | **앱 실행 중** (BE가 요청마다, 캐시) | data.go.kr 키 | 개발계정 10,000회/일 | 공공누리 제1유형 — "기상청" 표시 |
| [산림청 산정보](#2-산림청-산정보-서비스) | 산 높이·주소·설명 | 데이터 구축 시 1회 | data.go.kr 키 | 개발계정 10,000회/일 | 이용허락범위 제한 없음 |
| [Overpass (OSM)](#3-overpass-api-openstreetmap) | 산림청 코스가 없는 산의 등산로 | 데이터 구축 시 1회 | 없음 | 10,000회/일, 1GB/일 미만 | 데이터 ODbL — "© OpenStreetMap contributors" |
| [Open-Meteo 고도](#4-open-meteo-elevation-api) | 코스 출발점 고도 | 데이터 구축 시 1회 | 없음 | 600회/분, 5,000회/시, 10,000회/일 | CC BY 4.0 + Copernicus DEM 표시 |

- 앱이 실행 중에 호출하는 외부 API는 **기상청 하나**입니다. 나머지는 DATA 저장소의 스크립트가 데이터를 만들 때만 호출하고, 결과는 CSV와 BE 마이그레이션 SQL에 들어가 있습니다.
- 키(`DATA_GO_KR_KEY`, `KMA_SERVICE_KEY`)는 같은 data.go.kr 계정 키이며 `.env`에만 두고 저장소에 올리지 않습니다. data.go.kr은 같은 키라도 **API마다 활용신청**이 필요합니다.

---

## 1. 기상청 단기예보 조회서비스

| 항목 | 내용 |
|---|---|
| 제공 | 기상청 (공공데이터포털 [15084084](https://www.data.go.kr/data/15084084/openapi.do)) |
| 엔드포인트 | `GET https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst` |
| 사용 위치 | BE `com.ggmount.weather.KmaForecastClient` |
| 인증 | 쿼리 `serviceKey` = 일반인증키 **Decoding** 값. BE 설정 `app.kma.service-key` ← `.env`의 `KMA_SERVICE_KEY` |
| 승인 | 개발·운영 모두 자동승인 |

### 요청 파라미터

| 이름 | 예 | 설명 |
|---|---|---|
| serviceKey | (키) | URL 인코딩 1회. Spring에서는 `UriComponentsBuilder`의 템플릿 변수로 넣어야 `+ / =`까지 인코딩됨 |
| pageNo | 1 | |
| numOfRows | 1000 | 3일치 × 시간 × 12항목 ≈ 900행을 한 번에 받기 위함 |
| dataType | JSON | 기본은 XML. 인증 오류 등은 JSON을 요청해도 XML로 옴 |
| base_date | 20261002 | 발표일 (yyyyMMdd) |
| base_time | 0200 | 발표시각. **02, 05, 08, 11, 14, 17, 20, 23시** 하루 8회, 발표 약 10분 뒤부터 조회 가능 |
| nx, ny | 60, 127 | 기상청 5km 격자 좌표. `mountains.grid_nx/ny`에 미리 계산해 둠(위경도 → LCC 변환) |

### 응답

```json
{ "response": {
    "header": { "resultCode": "00", "resultMsg": "NORMAL_SERVICE" },
    "body": { "items": { "item": [
      { "baseDate": "20261002", "baseTime": "0200", "category": "TMP",
        "fcstDate": "20261002", "fcstTime": "0300", "fcstValue": "10", "nx": 60, "ny": 129 }
    ] } } } }
```

`item` 한 행 = (예보 시각, 항목) 하나. BE는 예보 시각별로 묶어 아래 항목을 사용합니다.

| category | 의미 | 값 형식 | 사용 |
|---|---|---|---|
| TMP | 1시간 기온 | ℃ | 기온 판별 |
| SKY | 하늘상태 | 1 맑음, 3 구름많음, 4 흐림 | 표시만 |
| PTY | 강수형태 | 0 없음, 1 비, 2 비/눈, 3 눈, 4 소나기 | 판별 |
| POP | 강수확률 | % | 판별 |
| PCP | 1시간 강수량 | `강수없음`, `1mm 미만`, `2.4mm`, `30.0~50.0mm`, `50.0mm 이상` (문자열) | 판별 (숫자로 변환: 미만은 절반, 범위는 하한) |
| SNO | 1시간 신적설 | `적설없음`, `1cm 미만`, `2.0cm` … (문자열) | 판별 (PCP와 같은 방식) |
| WSD | 풍속 | m/s | 판별 |
| REH | 습도 | % | 표시만 |
| UUU, VVV, VEC, WAV, TMN, TMX | 풍향 성분, 풍향, 파고, 최저·최고기온 | | 사용 안 함 |

- 제공 범위: 발표 시각부터 약 3일(글피 일부)까지 1시간 간격.
- `resultCode`가 `00`이 아니면 실패입니다(예: `03` 데이터 없음, `30` 등록되지 않은 키). 키 미등록·트래픽 초과는 HTTP 403/429로 오기도 합니다.

### 사용 범위와 우리 사용량

- **호출 한도**: 개발계정 10,000회/일. 운영계정은 활용사례 등록 시 증설 가능.
- **우리 사용량**: 산 140개가 쓰는 격자는 **112개**. BE가 격자·발표시각별로 캐시하므로 하루 최대 112 × 8 = **896회**(사용자가 많아도 늘지 않음). 서버를 여러 대 띄우면 서버 수만큼 늘어나므로 그때는 공용 캐시가 필요합니다.
- **라이선스**: 공공누리 제1유형(출처 표시). 상업적 이용·변경 가능. 앱 날씨 화면에 "기상청" 출처를 표시합니다(응답 `source` 필드).
- **함께 시험만 한 오퍼레이션**: `getUltraSrtNcst`(초단기실황). 도심 관측값 영향으로 단기예보보다 기온이 높게 나와 사용하지 않습니다. 낙뢰(`LGT`)가 필요하면 `getUltraSrtFcst`(초단기예보)를 추가해야 합니다.

---

## 2. 산림청 산정보 서비스

| 항목 | 내용 |
|---|---|
| 제공 | 산림청 (공공데이터포털 [15058662](https://www.data.go.kr/data/15058662/openapi.do), 「산림청_산정보 서비스」) |
| 엔드포인트 | `GET https://apis.data.go.kr/1400000/service/cultureInfoService2/mntInfoOpenAPI2` |
| 사용 위치 | DATA `scripts/fetch_forest_api.py` → `data/raw/forest_api.json` (로컬 전용) |
| 인증 | 쿼리 `serviceKey` (Decoding 키), `.env`의 `DATA_GO_KR_KEY` |
| 응답 형식 | XML만 제공 |

### 요청 파라미터

| 이름 | 예 | 설명 |
|---|---|---|
| serviceKey | (키) | |
| pageNo | 1, 2, … | `totalCount`에 도달할 때까지 반복 |
| numOfRows | 500 | |

### 응답 항목 (사용한 것)

| 필드 | 의미 | 우리 데이터 |
|---|---|---|
| mntilistno | 산 코드(9자리) | `mountains.csv`의 `code` — 산림청 등산로 파일과 연결하는 키 |
| mntiname | 산 이름 | 이름 매칭 후보 |
| mntihigh | 높이(m) | `height_src=forest_api`인 산의 높이 |
| mntiadd | 소재지 | 주소 |
| mntidetails | 상세 설명 | `mountain_descriptions.csv`(앞 1~2문장, `desc_src=forest_api`) |

- `mntisummary`, `mntitop`은 대부분 비어 있어 쓰지 않았습니다. `mntidetails`도 41개 산은 `( - )`만 들어 있어 직접 작성했습니다.
- 포털 설명은 3,368개 산이지만 2026-09-27 조회 결과는 전국 **4,705행**이었습니다.

### 사용 범위와 우리 사용량

- **호출 한도**: 개발계정 10,000회/일, 개발·운영 자동승인.
- **우리 사용량**: 페이지 10번 내외로 전체를 1회 받아 로컬에 저장. 앱은 호출하지 않습니다.
- **라이선스**: 이용허락범위 **제한 없음**. 산림청 출처 표시를 권장합니다.

---

## 3. Overpass API (OpenStreetMap)

| 항목 | 내용 |
|---|---|
| 제공 | OpenStreetMap 커뮤니티 공개 인스턴스 `overpass-api.de` |
| 엔드포인트 | `POST https://overpass-api.de/api/interpreter` (본문 `data=<쿼리>`) |
| 사용 위치 | DATA `scripts/osm_trails.py` → `data/raw/osm_paths/<산 id>.json` (로컬 캐시) |
| 인증 | 없음. **User-Agent 헤더 필수**(없으면 HTTP 406) — `csie2026-hiking-data/0.1 (team project)` |
| 대상 | 산림청 코스가 없는 산 57개(당시 기준) |

### 쿼리 (산 하나)

```
[out:json][timeout:180];
way(around:R,정상위도,정상경도)[highway~"^(path|footway|steps|track|bridleway)$"]->.p;    // 등산로
way(around:R+500,…)[highway~"^(motorway|…|residential|service|road)$"]->.r;              // 도로(출발점 판정)
node(around:R+2000,…)[place~"^(town|village|hamlet|suburb|quarter|neighbourhood)$"]->.n; // 출발점 이름
.p out body geom; .r out body; .n out body;
```

- `R`: 정상 높이 500m 이상 5km, 미만 3km. 시간 초과가 반복되면 4번째 시도부터 2.5km.
- 사용한 태그: `highway`, `name`, `surface`, `sac_scale`, `trail_visibility`, `informal`, `access`, `foot`, `footway`. 험로(`sac_scale` T4+), 잘 안 보이는 길, 비공식 길, 통행금지, 인도는 제외합니다.

### 사용 범위와 우리 사용량

- **사용 정책**: 하루 10,000회 미만, 다운로드 1GB/일 미만, 동시 요청 금지. 정기적으로 돌리는 작업은 그 1/100 수준. 혼잡하면 HTTP 429/504 → 기다렸다 재시도.
- **상업적 이용**: 공개 인스턴스는 상업 서비스용이 아닙니다(자체 서버나 유료 서버 권장). 우리는 데이터 구축 때 1회만 쓰고 앱은 호출하지 않습니다.
- **우리 사용량**: 산 57개 × 1회(시간 초과 재시도 포함 약 100~150회), 응답 합계 약 48MB. 결과는 캐시해 다시 받지 않습니다.
- **데이터 라이선스 — ODbL**:
  - 앱 화면과 정보 페이지에 **"© OpenStreetMap contributors"** 표시.
  - OSM에서 파생한 데이터베이스(`courses`의 `source=OSM` 178개, `trails`의 `source=osm`)를 외부에 **배포·공개**하면 같은 ODbL 조건으로 공개해야 합니다(동일조건 공유). 앱 화면에 보여주기만 하는 것은 "생산물"로 출처 표시만 필요합니다.
  - 그래서 데이터에 `source` 컬럼으로 출처를 구분해 둡니다.

---

## 4. Open-Meteo Elevation API

| 항목 | 내용 |
|---|---|
| 제공 | Open-Meteo (고도 데이터: Copernicus DEM GLO-90) |
| 엔드포인트 | `GET https://api.open-meteo.com/v1/elevation?latitude=37.1,37.2&longitude=127.1,127.2` |
| 사용 위치 | DATA `scripts/build_trails.py`의 `elevations()` → `data/raw/elevation_cache.json` (로컬 캐시) |
| 인증 | 없음 |

- 좌표를 쉼표로 이어 **최대 100개**를 한 번에 요청하고, 응답 `{"elevation": [m, m, …]}`의 순서대로 받습니다.
- 용도: 코스 출발점 고도(`courses.start_elevation`) → 오르막(`climb`) → 난이도·경사 계산.

### 사용 범위와 우리 사용량

- **호출 한도**: 600회/분, 5,000회/시, 10,000회/일, 300,000회/월. 좌표를 여러 개 넣으면 그만큼 여러 번으로 셀 수 있어(실제로 수백 좌표 연속 요청에서 HTTP 429 발생), 스크립트는 100좌표마다 5초 쉬고 429면 65초 기다립니다.
- **무료 조건**: **비상업 용도만**(광고·구독이 있는 서비스는 상업으로 봄). 우리는 데이터 구축 때만 쓰고 결과를 저장해 두며 앱은 호출하지 않습니다. 앱이 상업 서비스가 되면 고도값의 출처(유료 플랜 또는 Copernicus DEM 직접 사용)를 다시 검토해야 합니다.
- **우리 사용량**: 코스 출발점 약 1,400개 좌표(누적 1,431개), 캐시 후 재호출 없음.
- **라이선스**: API 데이터는 CC BY 4.0 — "Open-Meteo" 출처 표시. 고도 원천은 Copernicus DEM(© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018, provided under COPERNICUS by the European Union and ESA).

---

## 5. 검토했지만 쓰지 않은 API

| API | 이유 |
|---|---|
| Open-Meteo Forecast (`/v1/forecast`, 정상 고도 보정 기온) | 기상청 데이터로 충분하고 정상 기온 추정은 보류. 무료는 비상업 조건 |
| 기상청 단기예보 「API허브 연계」판 ([15139470](https://www.data.go.kr/data/15139470/openapi.do)) | 별도 API허브 키가 필요하고 운영 단계 심의가 있어, 같은 키로 쓰는 15084084를 선택 |
| 네이버 지도 등산 코스 | 공개 API가 없고 수집은 이용약관 위반이라 제외 |

## 앱에 표시할 출처 (정리)

> 날씨: 기상청 · 등산로: 산림청, 산림빅데이터거래소(© 시선아이티, CC BY), © OpenStreetMap contributors (ODbL) · 고도: Open-Meteo, Copernicus DEM
