# 주제: SQL DISTINCT
# 단계: 21
# 종류: sql
# 데이터: chinook.db

> 🎵 중복을 없애고 '종류'만 추리는 `DISTINCT` 를 연습합니다.

---

## 문제
우리 고객들이 어느 나라에 있는지 "나라 목록"을 정리하려 합니다.
`customers` 테이블에서 `Country` 를 **중복 없이** 보여주세요.

## 풀이
```sql
SELECT DISTINCT Country FROM customers;
```

---

## 문제
곡 단가가 몇 종류인지 확인하려 합니다.
`tracks` 테이블에서 `UnitPrice` 의 종류를 중복 없이 보여주세요.

## 풀이
```sql
SELECT DISTINCT UnitPrice FROM tracks;
```

---

## 문제
"도시 + 나라" 조합 기준으로 고객 분포를 보려 합니다.
`customers` 에서 `City` 와 `Country` 를 함께 중복 없이 보여주세요.

## 풀이
```sql
SELECT DISTINCT City, Country FROM customers;
```
