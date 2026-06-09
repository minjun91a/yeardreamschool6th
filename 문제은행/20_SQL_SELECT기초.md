# 주제: SQL SELECT 기초
# 단계: 20
# 종류: sql
# 데이터: chinook.db

> 🎵 Chinook(디지털 음악 스토어) 데이터로 SELECT 기초를 연습합니다.
> 정답(예상 결과)은 적지 않습니다 — 쿼리를 실제 DB에 실행해 자동 채점합니다.
> 문제는 `---` 로 구분합니다.

---

## 문제
신입 사원이 우리 회사가 보유한 앨범 목록을 보고 싶어 합니다.
`albums` 테이블에서 앨범 제목(`Title`)만 모두 보여주세요.

## 풀이
```sql
SELECT Title FROM albums;
```

---

## 문제
마케팅팀이 아티스트 전체 명단을 요청했습니다.
`artists` 테이블의 모든 정보(모든 컬럼)를 보여주세요.

## 풀이
```sql
SELECT * FROM artists;
```

---

## 문제
곡(track) 데이터가 어떻게 생겼는지 빠르게 확인하려 합니다.
`tracks` 테이블의 모든 컬럼을, 데이터가 많으니 앞 10건만 보여주세요. (`LIMIT`)

## 풀이
```sql
SELECT * FROM tracks LIMIT 10;
```

---

## 문제
고객지원팀이 "곡 이름과 그 곡의 가격"만 정리한 표를 원합니다.
`tracks` 테이블에서 곡 이름(`Name`)과 단가(`UnitPrice`)만, 앞 10건 보여주세요.

## 풀이
```sql
SELECT Name, UnitPrice FROM tracks LIMIT 10;
```
