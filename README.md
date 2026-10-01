# 산·코스·날씨 데이터 사용법

경기도 산(140개), 등산 코스(420개), 산별 날씨 API를 FE·BE에서 쓰는 방법을 정리한 문서입니다.
데이터 생성·수정은 DB 담당이 맡고, 이 문서는 **사용하는 쪽** 기준입니다.

- 이 저장소(DATA): 데이터 원본 CSV와 생성 스크립트. 데이터셋 자체 설명은 [`data/README_ko.md`](data/README_ko.md)
- BE 저장소: 실제로 DB에 들어가는 Flyway 마이그레이션(`src/main/resources/db/migration/V2__mountains.sql`, `V3__courses.sql`)과 날씨 API(`com.ggmount.weather`)

## 1. 구조

```
FE ──fetch──▶ BE API ──JPA/JDBC──▶ PostgreSQL
                │                    ├─ mountains (V2)  산 140개
                │                    └─ courses   (V3)  코스 420개
                └─ 날씨: 요청 시 기상청 단기예보 API 호출 (BE에서 키 보관·캐시)
```

- FE는 DB나 기상청을 직접 호출하지 않고 항상 BE API를 거칩니다.
- 산·코스는 정적 데이터입니다. Flyway 마이그레이션(`V2__mountains.sql`, `V3__courses.sql`)이 BE 시작 시 자동으로 넣습니다. 이 두 파일은 스크립트로 생성되므로 **직접 수정하지 마세요**(수정이 필요하면 DB 담당에게 요청).
- 날씨는 저장하지 않고 요청 때마다 받아오며, 같은 기상청 격자·같은 발표분은 BE 메모리에 캐시합니다.

## 2. 로컬 실행

### 2.1 PostgreSQL

PostgreSQL 17을 설치합니다(Windows: `winget install PostgreSQL.PostgreSQL.17`). 설치 후 데이터베이스를 하나 만듭니다.

```
psql -U postgres -h localhost -c "create database ggmount;"
```

### 2.2 BE/.env

`.env.example`을 복사해 `.env`를 만들고 값을 채웁니다. `.env`는 Git에 올리지 않습니다.

```
GOOGLE_CLIENT_ID=...          # OAuth 키는 BE 담당에게 받기
GOOGLE_CLIENT_SECRET=...
KAKAO_CLIENT_ID=...
KAKAO_CLIENT_SECRET=...

DB_URL=jdbc:postgresql://localhost:5432/ggmount
DB_USERNAME=postgres
DB_PASSWORD=설치 때 정한 비밀번호

KMA_SERVICE_KEY=data.go.kr 일반인증키(Decoding)
```

- `KMA_SERVICE_KEY`는 data.go.kr에서 「기상청_단기예보 조회서비스」(15084084) 활용신청이 된 계정의 **Decoding** 키입니다. Encoding 키를 넣으면 이중 인코딩으로 인증에 실패합니다.
- 값에 따옴표나 공백을 넣지 않습니다(`KEY=값` 형식).

### 2.3 실행

```
./mvnw.cmd spring-boot:run "-Dspring-boot.run.profiles=local"
```

로그에 `Successfully applied 3 migrations ... now at version v3`이 나오면 산·코스 데이터가 들어간 것입니다.

### 2.4 테스트

```
./mvnw.cmd test
```

- `SeedDataTests`: 산·코스 데이터 무결성(개수, 외래키, 경로 JSON, 경사 등).
- `HikingWeatherRulesTests`: 날씨 등급 판별 기준.
- `WeatherLiveTests`: 실제 기상청 호출. 환경변수 `KMA_SERVICE_KEY`가 있을 때만 실행되고, 없으면 건너뜁니다.

## 3. DB 스키마

모든 컬럼이 `BIGINT / INTEGER / DOUBLE PRECISION / VARCHAR / TEXT`라서 JPA 엔티티 필드를 `Long / Integer / Double / String`으로 두면 `ddl-auto: validate`를 그대로 통과합니다. 컬럼 이름도 기본 이름 규칙(camelCase → snake_case)과 맞으므로 `@Column(name=...)`이 필요 없습니다.

### 3.1 mountains (산 140개)

| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | BIGINT PK | 1~141. **112(도라산)는 비어 있음.** id는 재사용하지 않으며, 새 산은 142번부터 |
| name | VARCHAR(30) UNIQUE | 같은 이름의 산은 괄호로 구분합니다(예: `검단산 (성남/광주)`, `검단산 (하남/광주)`). 46개가 괄호를 포함합니다 |
| region | VARCHAR(10) | 권역 `NORTH` / `EAST` / `CENTRAL` / `SOUTH` |
| sigungu_code | VARCHAR(5) | 행정표준 시군구 코드(예: `41410`) |
| sigungu_name | VARCHAR(20) | 탐색 화면용 경기 시·군(31개). 서울 경계 산 8개와 수리산은 인접한 경기 시·군으로 지정 |
| address | VARCHAR(100) | 실제 주소(서울 경계 산은 서울 주소) |
| height | DOUBLE PRECISION | 정상 높이(m) |
| lat, lng | DOUBLE PRECISION | 정상 좌표(WGS84) |
| grid_nx, grid_ny | INTEGER | 기상청 단기예보 격자 좌표(날씨 API가 사용) |
| description | VARCHAR(300) | 1~2문장 소개 |

### 3.2 courses (코스 420개, 산 134개)

| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | BIGINT PK | DB가 자동으로 붙임. **데이터를 다시 생성하면 바뀝니다**(아래 주의사항 참고) |
| mountain_id | BIGINT FK → mountains.id | |
| source | VARCHAR(10) | `FOREST`(산림청 등산로) / `OSM`(OpenStreetMap) |
| name | VARCHAR(50) | 코스 이름(예: `별내동 코스 3`). 산 안에서 유일 |
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
- 코스가 없는 산 6개: 여기산, 고왕산, 방울산, 심술산, 쌍봉산, 오두산(화성). 화면에서 "등록된 코스가 없어요" 처리가 필요합니다.
- 난이도 기준(임시): 어려움 = 오르막 600m 이상 또는 거리 8km 이상, 쉬움 = 오르막 200m 미만이면서 3km 미만, 나머지 보통.

### 3.3 SQL 예시

```sql
-- 권역·시군별 산
SELECT region, sigungu_name, id, name, height FROM mountains ORDER BY region, sigungu_name, name;

-- 한 산의 코스(짧은 순)
SELECT id, name, length_km, climb, up_min, difficulty FROM courses WHERE mountain_id = 53 ORDER BY length_km;

-- 코스가 없는 산
SELECT m.name FROM mountains m LEFT JOIN courses c ON c.mountain_id = m.id WHERE c.id IS NULL;
```

## 4. API

### 4.1 날씨 (구현 완료)

```
GET /api/mountains/{id}/weather      (로그인 필요)
```

응답 예시:

```json
{
  "mountainId": 3,
  "mountainName": "고동산",
  "baseTime": "2026-10-02T02:00",
  "source": "기상청 단기예보",
  "days": [
    {
      "date": "2026-10-05",
      "level": "BAD",
      "message": "강수확률이 60%예요(6시). 산행을 미루는 걸 권해요.",
      "notes": ["6시에 비나 눈 예보가 있어요. 우비를 챙기세요."],
      "hours": [
        { "time": "2026-10-05T06:00", "temperature": 12.0, "sky": 3, "pty": 1, "pop": 60,
          "precipitationMm": 1.0, "snowCm": 0.0, "windSpeed": 1.0, "humidity": 95 }
      ]
    }
  ]
}
```

- `days`: 오늘~모레(3일). 날짜마다 **06~18시**만 판단합니다. 오늘은 지난 시간을 빼며, 18시가 지나면 오늘은 빠집니다. 마지막 날은 예보 범위 때문에 일부 시간만 있을 수 있습니다.
- `message`: 가장 나쁜 항목 하나. `notes`: 나머지 주의 사항.
- 오류: 없는 산 404, 서버에 키 미설정 503, 기상청 호출 실패 502.

등급 기준(시간대 중 가장 나쁜 값으로 판단):

| 항목 | 주의(CAUTION) | 나쁨(BAD) |
|---|---|---|
| 비·눈(`pty` ≠ 0) | 1시간 | 2시간 이상 |
| 강수확률 `pop` | 30~59% | 60% 이상 |
| 시간당 강수량 | 0 초과 | 3mm 이상 |
| 시간당 적설 | 0 초과 | 1cm 이상 |
| 풍속 `windSpeed` | 7~9 m/s | 10 m/s 이상 |
| 최고기온 | 30~32℃ | 33℃ 이상 |
| 최저기온 | 0~−9℃ | −10℃ 이하 |

### 4.2 산·코스 API (BE 담당 구현 예정, 권장 형태)

```
GET /api/mountains                  산 목록(140개, 페이징 불필요)
GET /api/mountains/{id}             산 상세
GET /api/mountains/{id}/courses     코스 목록(path 제외)
GET /api/courses/{id}               코스 상세(path 포함)
```

- 산 응답 필드는 FE `Mountain` 타입(`InteractiveMountainMap.tsx`)과 맞춥니다: `id, name, region, city(= sigungu_name), height, lat, lng, description`.
- `path`는 **문자열 그대로 내보내지 마세요.** 그대로 두면 FE가 `JSON.parse`를 한 번 더 해야 합니다. 필드에 `@JsonRawValue`를 붙이거나 파싱해서 배열로 응답합니다. 코스 전체 경로를 합치면 약 1.4MB이므로 목록 응답에서는 빼는 것을 권장합니다.
- 산·코스 조회를 로그인 없이 허용할지는 팀 결정 사항입니다(현재 `SecurityConfig`는 로그인 관련 URL 외 전부 인증 필요).

## 5. FE에서 쓰기

`src/api.ts`의 `api()`에 함수를 추가합니다. 개발 서버의 Vite proxy가 `/api`를 BE(8080)로 넘깁니다.

```ts
export const getWeather = (id: number) => api<Weather>(`/api/mountains/${id}/weather`);
```

코드값 → 화면 문구:

| 필드 | 값 → 표시 |
|---|---|
| region | `NORTH` 북부권역, `EAST` 동부권역, `CENTRAL` 중부권역, `SOUTH` 남부권역 |
| difficulty | `EASY` 쉬움, `NORMAL` 보통, `HARD` 어려움 |
| source | `FOREST` 산림청, `OSM` OpenStreetMap |
| level | `GOOD` 좋음, `CAUTION` 주의, `BAD` 나쁨 |
| sky | `1` 맑음, `3` 구름많음, `4` 흐림 |
| pty | `0` 없음, `1` 비, `2` 비/눈, `3` 눈, `4` 소나기 |

주의:

- 산·코스는 **id로만 연결**하세요. 이름은 괄호가 붙어 있어(`감악산 (경기)`) 기존 목데이터 이름과 절반만 일치합니다.
- 기존 목데이터의 원적산·마구산은 DB에 없습니다.
- `usePersistentIds`로 localStorage에 저장한 문자열 산 id(`"용인시-0"` 등)는 새 숫자 id와 호환되지 않으니 초기화 또는 변환이 필요합니다.
- 권역 → 시·군 → 산 탐색 트리는 산 목록 응답을 `region`, `city`로 묶어서 만듭니다.
- 지도에 코스를 그릴 때 `path`의 좌표 순서는 `[경도, 위도]`입니다(Leaflet 등은 `[위도, 경도]`를 받으므로 뒤집어야 합니다).

## 6. 주의사항

- **코스 id는 고정되지 않습니다.** 데이터를 다시 생성하면 바뀝니다. 등산일지 등 다른 테이블이 코스를 참조하기 전에 DB 담당과 고정 방법을 정하세요.
- **이미 적용된 마이그레이션은 수정하지 않습니다.** 운영 DB에 V2·V3이 들어간 뒤의 데이터 변경은 새 버전(V5 등)으로 추가됩니다.
- 등산일지의 산 연결(V4)은 8장 참고.
- 소요시간은 거리만 반영한 값이고(1km당 오르막 17.5분, 내리막 12.5분 수준), 일부 코스 이름(`무명 코스`, 표지판 이름 등)은 정리 예정입니다.

## 7. 출처 표시 (앱에 반드시 표시)

| 데이터 | 출처 | 조건 |
|---|---|---|
| 등산로·코스(`source=FOREST`) | 산림청, 산림빅데이터거래소 © 시선아이티 | CC BY |
| 등산로·코스(`source=OSM`), 일부 정상 좌표 | © OpenStreetMap contributors | ODbL |
| 출발점 고도 | Copernicus DEM (Open-Meteo) | 출처 표시 |
| 날씨 | 기상청 | 공공누리 제1유형(출처 표시) |

## 8. 등산일지 ↔ 산 연결 (V4, BE 담당 작업)

등산일지 `hiking_records`는 산 이름 문자열(`mountain_name`) 대신 `mountain_id` 외래키로 산을 참조하도록 바꿉니다. 진영별 산 점령(등산 횟수)을 집계하려면 기록이 어느 산인지 정확해야 하는데, 이름 문자열은 오타·띄어쓰기·같은 이름의 산(`검단산`, `광덕산` 등)을 구분하지 못하기 때문입니다. 목록에 없는 산은 등산일지에 기록할 수 없게 됩니다.

`V4__hiking_records_mountain_fk.sql`은 `HikingRecord` 엔티티 변경과 **같은 PR**로 머지해야 합니다(`ddl-auto: validate`라서 `mountain_name` 컬럼을 먼저 지우면 앱이 시작되지 않음).

```sql
ALTER TABLE hiking_records ADD COLUMN mountain_id BIGINT REFERENCES mountains(id);
UPDATE hiking_records h SET mountain_id = m.id FROM mountains m WHERE m.name = h.mountain_name;
ALTER TABLE hiking_records ALTER COLUMN mountain_id SET NOT NULL;  -- 이름이 안 맞는 행이 있으면 여기서 실패
ALTER TABLE hiking_records DROP COLUMN mountain_name;
CREATE INDEX hiking_records_mountain ON hiking_records(mountain_id);
```

기존 개발 DB에 산 이름이 목록과 다른 일지가 있으면 `SET NOT NULL`에서 마이그레이션이 멈춥니다. 그 경우 해당 행을 정리하거나 개발 DB를 초기화한 뒤 다시 실행하세요.

### BE 변경사항
1. `mountain` 패키지 구현
   - `Mountain` 엔티티 (3.1의 컬럼), `MountainRepository`
   - `GET /api/mountains` — 전체 목록 (140개라 페이징 불필요)
   - `GET /api/mountains/{id}` — 단건
   - 응답 필드: `id, name, region, city(=sigungu_name), height, lat, lng, description` — FE `Mountain` 타입(`InteractiveMountainMap.tsx`)과 동일한 이름
2. `HikingRecord`
   - `private String mountainName` → `@ManyToOne(fetch = LAZY, optional = false) @JoinColumn(name = "mountain_id") private Mountain mountain`
   - `update()`에서 `mountainName` 대신 `Mountain`을 받도록 변경
3. `HikingRecordRequest`
   - `@NotBlank @Size(max=100) String mountainName` → `@NotNull Long mountainId`
4. `HikingRecordService.save()`
   - `mountainId`로 산 조회, 없으면 `400` 또는 `404` 반환
5. `HikingRecordResponse`
   - `mountainId` 필드 추가, `mountainName`은 `r.getMountain().getName()`으로 유지
   - 목록 조회 시 N+1 방지: 리포지토리 쿼리에 `@EntityGraph(attributePaths = {"member", "mountain"})`
6. `SecurityConfig`: 산 목록·상세를 비로그인 사용자에게도 공개할지 결정 필요 (현재는 로그인 관련 URL 외 전부 인증 필요)

### FE 변경사항
1. 산 데이터를 API로 교체
   - `src/data/sampleMountains.ts`, `src/data/exploreRegions.ts`의 목데이터 → `GET /api/mountains`
   - 산 `id`는 DB의 숫자 id를 사용 (현재 `exploreRegions.ts`의 `"${시군}-${index}"` 문자열 id는 폐기)
   - 권역 → 시·군 → 산 트리는 응답의 `region`, `city`로 묶어서 구성
   - `usePersistentIds`로 localStorage에 저장된 문자열 산 id는 새 id와 호환되지 않음 → 초기화 또는 변환 필요
2. 등산일지 작성/수정 (`App.tsx` 427행 부근)
   - 요청 본문: `mountainName: journalMountain || mountain.name` → `mountainId: mountain.id`
   - 산 이름 직접 입력란이 있다면 산 선택(목록/검색)으로 변경
   - `api.ts`의 `Journal` 타입에 `mountainId: number` 추가, 요청 타입의 `'mountainName'`을 `'mountainId'`로
3. 일지 표시(`j.mountainName`)는 응답에 계속 포함되므로 변경 없음

### API 계약 (변경 후)

```
POST /api/journals
PATCH /api/journals/{id}
{ "mountainId": 12, "title": "...", "content": "...", "hikingDate": "2026-10-02", "isPublic": true }

응답 (HikingRecordResponse)
{ "id": 1, "userId": 3, "nickname": "...", "mountainId": 12, "mountainName": "수리산",
  "title": "...", "content": "...", "hikingDate": "2026-10-02", "isPublic": true }

GET /api/mountains
[ { "id": 12, "name": "수리산", "region": "CENTRAL", "city": "군포시", "height": 469.3,
    "lat": 37.359685, "lng": 126.906911, "description": "수리산은 안양, 군포, 안산시 경계에 자리한 산이다. …" } ]
```
