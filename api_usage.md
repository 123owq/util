kipris_API_key=Lzi/NPqAISbYoiaJ1yRn0n92MS6phGddsICRMI9x=HU=

AP=[한국타이어앤테크놀로지] = [120120550993]

예시 = http://plus.kipris.or.kr/kipo-api/kipi/patUtiModInfoSearchSevice/getAdvancedSearch?applicant=120120550993&numOfRows=1&pageNo=1&descSort=true&sortSpec=OPD&ServiceKey=Lzi/NPqAISbYoiaJ1yRn0n92MS6phGddsICRMI9x=HU=

---

### **[KIPRIS Plus] getAdvancedSearch 입력 파라미터**

**요청 주소:** `http://plus.kipris.or.kr/kipo-api/kipi/patUtiModInfoSearchSevice/getAdvancedSearch`

| 레벨 | 구분 | 데이터항목 | 설명 | 부가정보 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | DATA | **word** | 자유검색 | |
| 1 | DATA | **inventionTitle** | 발명의명칭 | |
| 1 | DATA | **astrtCont** | 초록 | |
| 1 | DATA | **claimScope** | 청구범위 | |
| 1 | DATA | **ipcNumber** | IPC코드 | |
| 1 | DATA | **applicationNumber** | 출원번호 | |
| 1 | DATA | **openNumber** | 공개번호 | |
| 1 | DATA | **publicationNumber** | 공보(고)번호 | |
| 1 | DATA | **registerNumber** | 등록번호 | |
| 1 | DATA | **priorityApplicationNumber** | 우선권주장번호 | |
| 1 | DATA | **internationalApplicationNumber** | 국제출원번호 | |
| 1 | DATA | **internationOpenNumber** | 국제공개번호 | |
| 1 | DATA | **applicationDate** | 출원일자 | |
| 1 | DATA | **openDate** | 공개일자 | |
| 1 | DATA | **publicationDate** | 공고일자 | |
| 1 | DATA | **registerDate** | 등록일자 | |
| 1 | DATA | **priorityApplicationDate** | 우선권주장일자 | |
| 1 | DATA | **internationalApplicationDate** | 국제출원일자 | |
| 1 | DATA | **internationOpenDate** | 국제공개일자 | |
| 1 | DATA | **applicant** | 출원인명/특허고객번호 | 출원인명 및 특허고객번호 |
| 1 | DATA | **inventors** | 발명자명/특허고객번호 | 발명자명 및 특허고객번호 |
| 1 | DATA | **agent** | 대리인명/대리인코드 | 대리인명 및 대리인코드 |
| 1 | DATA | **rightHoler** | 등록권자 | (특허권자) |
| 1 | DATA | **patent** | 특허 | (포함 : true, 미포함 : false) |
| 1 | DATA | **utility** | 실용 | (포함 : true, 미포함 : false) |
| 1 | DATA | **lastvalue** | 행정처분 | (전체:공백입력, 공개:A, 취하:C, 소멸:F, 포기:G, 무효:I, 거절:J, 등록:R) |
| 1 | DATA | **pageNo** | 페이지번호 | |
| 1 | DATA | **numOfRows** | 페이지당건수 | (기본 : 30, 최대 500) |
| 1 | DATA | **sortSpec** | 정렬기준 | (PD-공고일자, AD-출원일자, GD-등록일자, OPD-공개일자, FD-국제출원일자, FOD-국제공개일자, RD-우선권주장일자) |
| 1 | DATA | **descSort** | 정렬방식 | (asc방식 : false, desc방식 : true) |

---

그 외에도 도면이나 특허pdf 링크를 얻는api가 있습니다.