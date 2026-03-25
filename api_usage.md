kipris_API_key=Lzi/NPqAISbYoiaJ1yRn0n92MS6phGddsICRMI9x=HU=

http://plus.kipris.or.kr/openapi/rest/CitationService/citationInfoV3?applicationNumber=1020230008170&accessKey=Lzi/NPqAISbYoiaJ1yRn0n92MS6phGddsICRMI9x=HU=


## KIPRIS Plus API 전체 정리

---

## 1. 특허·실용 통합검색 (전체검색)

**서비스:** `patUtiModInfoSearchSevice`
**오퍼레이션:** `getAdvancedSearch`
**타입:** REST
**Base URL:** `http://plus.kipris.or.kr/kipo-api/kipi/patUtiModInfoSearchSevice/getAdvancedSearch`

### 파라미터

| 파라미터명 | 설명 | 비고 |
|---|---|---|
| `word` | 자유검색 | |
| `inventionTitle` | 발명의명칭 | |
| `astrtCont` | 초록 | |
| `claimScope` | 청구범위 | |
| `ipcNumber` | IPC 코드 | |
| `applicationNumber` | 출원번호 | |
| `openNumber` | 공개번호 | |
| `publicationNumber` | 공보(고)번호 | |
| `registerNumber` | 등록번호 | |
| `priorityApplicationNumber` | 우선권주장번호 | |
| `internationalApplicationNumber` | 국제출원번호 | |
| `internationOpenNumber` | 국제공개번호 | |
| `applicationDate` | 출원일자 | |
| `openDate` | 공개일자 | |
| `publicationDate` | 공고일자 | |
| `registerDate` | 등록일자 | |
| `priorityApplicationDate` | 우선권주장일자 | |
| `internationalApplicationDate` | 국제출원일자 | |
| `internationOpenDate` | 국제공개일자 | |
| `applicant` | 출원인명 / 특허고객번호 | |
| `inventors` | 발명자명 / 특허고객번호 | |
| `agent` | 대리인명 / 대리인코드 | |
| `rightHoler` | 등록권자(특허권자) | |
| `patent` | 특허 포함 여부 | `true` / `false` |
| `utility` | 실용 포함 여부 | `true` / `false` |
| `lastvalue` | 행정처분 | 공백=전체, `A`=공개, `C`=취하, `F`=소멸, `G`=포기, `I`=무효, `J`=거절, `R`=등록 |
| `pageNo` | 페이지 번호 | |
| `numOfRows` | 페이지당 건수 | 기본 30, 최대 500 |
| `sortSpec` | 정렬 기준 | `PD`=공고일자, `AD`=출원일자, `GD`=등록일자, `OPD`=공개일자, `FD`=국제출원일자, `FOD`=국제공개일자, `RD`=우선권주장일자 |
| `descSort` | 정렬 방식 | `false`=오름차순, `true`=내림차순 |
| `ServiceKey` | 인증키 | |

### 샘플 요청
```
http://plus.kipris.or.kr/kipo-api/kipi/patUtiModInfoSearchSevice/getAdvancedSearch
  ?astrtCont=발명
  &inventionTitle=센서
  &ServiceKey=YOUR_KEY
```

---

## 2. 보정이력 (ClaimsChangeHistoryService)

**서비스:** `ClaimsChangeHistoryService`
**타입:** REST / BULK
**Base URL:** `http://plus.kipris.or.kr/openapi/rest/ClaimsChangeHistoryService/`

### 오퍼레이션 목록

| # | 오퍼레이션명 | 설명 |
|---|---|---|
| 1 | `amendmentHistoryInfo` | 보정이력 순서 |
| 2 | (미전달) | 보정이력 상세내역 |
| 3 | (미전달) | 변동정보 |

### 파라미터 (amendmentHistoryInfo)

| 파라미터명 | 설명 | 필수 |
|---|---|---|
| `applicationNumber` | 출원번호 | ✅ |
| `accessKey` | 인증키 | ✅ |

### 샘플 요청
```
http://plus.kipris.or.kr/openapi/rest/ClaimsChangeHistoryService/amendmentHistoryInfo
  ?applicationNumber=1020160162297
  &accessKey=YOUR_KEY
```

---

## 3. 중간사건 서류 (의견제출통지서 등)

**서비스:** `IntermediateDocumentOPService`
**타입:** REST / BULK
**Base URL:** `http://plus.kipris.or.kr/openapi/rest/IntermediateDocumentOPService/`

### 오퍼레이션 목록

| # | 오퍼레이션명 | 설명 |
|---|---|---|
| 1 | `advancedSearchInfo` | 전체검색 |

### 파라미터 (advancedSearchInfo)

| 파라미터명 | 설명 | 비고 |
|---|---|---|
| `word` | 자유검색 | |
| `applicationDate` | 출원일자 | |
| `applicationNumber` | 출원번호 | |
| `inventionTitle` | 발명의명칭/물품명칭 | 상표명 지원 안함 |
| `rejectionContent` | 거절사유 | |
| `sendDate` | 발송일자 | |
| `sendNumber` | 발송번호 | |
| `relationpersonName` | 관련자 검색 (출원인, 대리인) | |
| `patent` | 특허 포함 여부 | `true`/`false`, 미입력 시 자동 `true` |
| `utility` | 실용신안 포함 여부 | `true`/`false`, 미입력 시 자동 `true` |
| `design` | 디자인 포함 여부 | `true`/`false`, 미입력 시 자동 `true` |
| `tradeMark` | 상표 포함 여부 | `true`/`false`, 미입력 시 자동 `true` |
| `docsStart` | 페이지 번호 | |
| `docsCount` | 페이지당 건수 | 기본 30, 최대 500 |
| `descSort` | 정렬 방식 | `false`=오름차순, `true`=내림차순 |
| `sortSpec` | 정렬 기준 | `AN`=출원번호, `AD`=출원일자, `MN`=발송번호, `SD`=발송일자 |
| `accessKey` | 인증키 | |

### 샘플 요청
```
http://plus.kipris.or.kr/openapi/rest/IntermediateDocumentOPService/advancedSearchInfo
  ?rejectionContent=식별력
  &patent=true
  &utility=false
  &design=false
  &tradeMark=false
  &accessKey=YOUR_KEY
```

---

## 4. 인용문헌 (CitationService)

**서비스:** `CitationService`
**타입:** REST / BULK
**Base URL:** `http://plus.kipris.or.kr/openapi/rest/CitationService/`

### 오퍼레이션 목록

| # | 오퍼레이션명 | 상태 |
|---|---|---|
| 1 | `citationInfoV2` | ⚠️ 폐기 예정 |
| 2 | `citationInfo` | ⚠️ 폐기 예정 |
| 3 | `citationInfoV3` | ✅ 현행 사용 권장 |
| 4 | (미전달) | 변동정보 |
| 5 | (미전달) | 최종변동일자 |

### 파라미터 (citationInfoV2 기준, V3도 동일 추정)

| 파라미터명 | 설명 | 필수 |
|---|---|---|
| `applicationNumber` | 출원번호 | ✅ |
| `accessKey` | 인증키 | ✅ |

### 샘플 요청
```
# V2 (폐기 예정)
http://plus.kipris.or.kr/openapi/rest/CitationService/citationInfoV2
  ?applicationNumber=1019950039253
  &accessKey=YOUR_KEY

# V3 (권장)
http://plus.kipris.or.kr/openapi/rest/CitationService/citationInfoV3
  ?applicationNumber=1019950039253
  &accessKey=YOUR_KEY
```

---

## 5. 도면/전문 (patUtiModInfoSearchSevice - 도면/전문)

**서비스:** `patUtiModInfoSearchSevice`
**타입:** REST
**Base URL:** `http://plus.kipris.or.kr/kipo-api/kipi/patUtiModInfoSearchSevice/`

### 오퍼레이션 목록

| # | 오퍼레이션명 | 설명 | 상태 |
|---|---|---|---|
| 1 | `getPubFullTextInfoSearch` | 공개전문PDF | ✅ |
| 2 | (미전달) | 공고전문PDF | |
| 3 | (미전달) | 정정공고PDF | ⚠️ 폐기예정 |
| 4 | (미전달) | 대표도면 | |
| 5 | (미전달) | 정정공고PDF_V2 | |
| 6 | (미전달) | 공개책자 | |
| 7 | (미전달) | 공보책자 | |
| 8 | (미전달) | 모든 전문 및 대표도 유무 | |
| 9 | (미전달) | 전문파일정보 | |
| 10 | (미전달) | 표준화 공개전문PDF | |
| 11 | (미전달) | 표준화 공고전문PDF | |

### 파라미터 (getPubFullTextInfoSearch)

| 파라미터명 | 설명 | 필수 |
|---|---|---|
| `applicationNumber` | 출원번호 | ✅ |
| `ServiceKey` | 인증키 | ✅ |

### 샘플 요청
```
http://plus.kipris.or.kr/kipo-api/kipi/patUtiModInfoSearchSevice/getPubFullTextInfoSearch
  ?applicationNumber=1020050050026
  &ServiceKey=YOUR_KEY
```

---

## 📋 전체 요약

| 서비스 | 인증키 파라미터명 | Base URL 패턴 |
|---|---|---|
| 특허·실용 통합검색 | `ServiceKey` | `/kipo-api/kipi/patUtiModInfoSearchSevice/` |
| 보정이력 | `accessKey` | `/openapi/rest/ClaimsChangeHistoryService/` |
| 중간사건 서류 | `accessKey` | `/openapi/rest/IntermediateDocumentOPService/` |
| 인용문헌 | `accessKey` | `/openapi/rest/CitationService/` |

> ⚠️ **주의:** 서비스마다 인증키 파라미터명이 `ServiceKey` vs `accessKey`로 다름. 같은 키값을 쓰더라도 파라미터명은 구분해서 넣어야 함.


---

보정항 및 변동이력 표시
http://plus.kipris.or.kr/openapi/rest/ClaimsChangeHistoryService/amendmentHistoryDetailInfo?applicationNumber=1020120111868&accessKey=Lzi/NPqAISbYoiaJ1yRn0n92MS6phGddsICRMI9x=HU=

---

인용문헌 
http://plus.kipris.or.kr/openapi/rest/CitationService/citationInfoV3?applicationNumber=1020120111868&accessKey=Lzi/NPqAISbYoiaJ1yRn0n92MS6phGddsICRMI9x=HU=

---

의견제출서, 특허

그대로 pdf 다운로드 후 파싱

---

도면은 
특허 pdf 에서 직접 추출 

        f"{BASE}/openapi/rest/IntermediateDocumentOPService/advancedSearchInfo",
        {"applicationNumber": appl_no, "patent": "true", "utility": "true", "accessKey": API_KEY}
http://plus.kipris.or.kr/openapi/rest/IntermediateDocumentOPService/advancedSearchInfo?applicationNumber=1020230165920&patent=true&utility=true&accessKey=Lzi/NPqAISbYoiaJ1yRn0n92MS6phGddsICRMI9x=HU=

---