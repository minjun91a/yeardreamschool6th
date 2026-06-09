# 주제: SQL LIKE 패턴
# 단계: 25
# 종류: sql
# 데이터: chinook.db

> 🎵 문자열 일부로 찾기. `LIKE '패턴'`, `%` = 아무 글자 0개 이상.
> 시작 `'Rock%'` · 끝 `'%Live'` · 포함 `'%Love%'`.

---

## 문제
제목이 `'Rock'` 으로 **시작**하는 앨범을 찾으려 합니다.
`albums` 에서 `Title` 이 `'Rock'` 으로 시작하는 앨범을 보여주세요.

## 풀이
```sql
SELECT * FROM albums WHERE Title LIKE 'Rock%';
```

---

## 문제
제목이 `'Live'` 로 **끝나는**(라이브 앨범) 앨범을 찾으려 합니다.
`albums` 에서 `Title` 이 `'Live'` 로 끝나는 앨범을 보여주세요.

## 풀이
```sql
SELECT * FROM albums WHERE Title LIKE '%Live';
```

---

## 문제
곡 이름 어딘가에 `'Love'` 가 들어간 곡을 찾으려 합니다.
`tracks` 에서 `Name` 에 `'Love'` 가 포함된 곡을 앞 10건 보여주세요.

## 풀이
```sql
SELECT * FROM tracks WHERE Name LIKE '%Love%' LIMIT 10;
```
