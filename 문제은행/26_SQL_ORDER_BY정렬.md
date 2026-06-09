# 주제: SQL ORDER BY 정렬
# 단계: 26
# 종류: sql
# 데이터: chinook.db
# 정렬채점: on

> 🎵 결과를 정렬합니다. `ORDER BY 열 ASC`(오름차순·기본) / `DESC`(내림차순).
> 상위 몇 개만 보려면 `LIMIT n` 과 함께 씁니다.
> ⚠️ 이 단원은 **행의 순서까지** 채점합니다(정렬이 핵심이라서).

---

## 문제
결제 금액이 가장 큰 인보이스 5건을 보려 합니다.
`invoices` 를 `Total` **내림차순(DESC)** 으로 정렬해 앞 5건 보여주세요.

## 풀이
```sql
SELECT * FROM invoices ORDER BY Total DESC LIMIT 5;
```

---

## 문제
앨범 제목을 **알파벳 오름차순(ASC)** 으로 정렬해 앞 10건 보여주세요.
`albums` 에서 `Title` 기준으로 정렬합니다.

## 풀이
```sql
SELECT * FROM albums ORDER BY Title ASC LIMIT 10;
```

---

## 문제
재생 시간이 가장 긴 곡 5개를 보려 합니다.
`tracks` 에서 곡 이름(`Name`)과 재생시간(`Milliseconds`)을, `Milliseconds` **내림차순(DESC)** 으로 앞 5건 보여주세요.

## 풀이
```sql
SELECT Name, Milliseconds FROM tracks ORDER BY Milliseconds DESC LIMIT 5;
```
