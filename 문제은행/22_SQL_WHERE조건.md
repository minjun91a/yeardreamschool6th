# 주제: SQL WHERE 조건
# 단계: 22
# 종류: sql
# 데이터: chinook.db

> 🎵 `WHERE` 로 원하는 행만 걸러 냅니다. 비교 연산자 `=  !=  >  <  >=  <=`.
> 문자열 값은 작은따옴표로 감쌉니다: `'USA'`.

---

## 문제
미국(USA) 고객만 따로 확인하려 합니다.
`customers` 에서 `Country` 가 `'USA'` 인 고객을 모두 보여주세요.

## 풀이
```sql
SELECT * FROM customers WHERE Country = 'USA';
```

---

## 문제
단가가 0.99달러보다 비싼 곡을 찾으려 합니다.
`tracks` 에서 `UnitPrice` 가 0.99 **초과**인 곡을 앞 10건 보여주세요.

## 풀이
```sql
SELECT * FROM tracks WHERE UnitPrice > 0.99 LIMIT 10;
```

---

## 문제
결제 금액이 큰 인보이스를 점검하려 합니다.
`invoices` 에서 `Total` 이 10 **이상**인 건을 보여주세요.

## 풀이
```sql
SELECT * FROM invoices WHERE Total >= 10;
```
