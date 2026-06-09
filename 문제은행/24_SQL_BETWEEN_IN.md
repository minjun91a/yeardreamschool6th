# 주제: SQL BETWEEN·IN
# 단계: 24
# 종류: sql
# 데이터: chinook.db

> 🎵 범위·목록 연산자. `BETWEEN a AND b`(a·b 포함), `IN (...)`(목록 중 하나), `NOT IN (...)`(목록 제외).

---

## 문제
결제 금액이 5~10달러 사이인 인보이스를 보려 합니다. (5와 10 포함)
`invoices` 에서 `Total` 이 5 이상 10 이하인 건을 보여주세요.

## 풀이
```sql
SELECT * FROM invoices WHERE Total BETWEEN 5 AND 10;
```

---

## 문제
미국, 캐나다, 브라질 고객만 한 번에 뽑으려 합니다.
`customers` 에서 `Country` 가 이 세 나라 중 하나인 고객을 보여주세요.

## 풀이
```sql
SELECT * FROM customers WHERE Country IN ('USA', 'Canada', 'Brazil');
```

---

## 문제
위 세 나라를 **제외한** 나머지 나라 고객을 보려 합니다.
`customers` 에서 `Country` 가 그 세 나라에 속하지 않는 고객을 보여주세요.

## 풀이
```sql
SELECT * FROM customers WHERE Country NOT IN ('USA', 'Canada', 'Brazil');
```
