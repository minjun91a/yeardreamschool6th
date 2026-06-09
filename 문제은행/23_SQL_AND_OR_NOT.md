# 주제: SQL AND·OR·NOT
# 단계: 23
# 종류: sql
# 데이터: chinook.db

> 🎵 여러 조건을 엮습니다. `AND`(둘 다) · `OR`(하나라도) · `!=`/`NOT`(아닌 것).

---

## 문제
미국에 있으면서 캘리포니아(CA) 주에 사는 고객을 찾으려 합니다.
`Country` 가 `'USA'` **그리고** `State` 가 `'CA'` 인 고객을 보여주세요.

## 풀이
```sql
SELECT * FROM customers WHERE Country = 'USA' AND State = 'CA';
```

---

## 문제
미국 또는 캐나다 고객을 한 번에 보려 합니다.
`Country` 가 `'USA'` **이거나** `'Canada'` 인 고객을 보여주세요.

## 풀이
```sql
SELECT * FROM customers WHERE Country = 'USA' OR Country = 'Canada';
```

---

## 문제
미국이 **아닌** 해외 고객만 보려 합니다.
`Country` 가 `'USA'` 가 아닌 고객을 보여주세요.

## 풀이
```sql
SELECT * FROM customers WHERE Country != 'USA';
```
