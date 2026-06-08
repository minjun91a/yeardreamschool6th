# 🎓 학습 올인원 (All-in-One Learning)

> Jupyter 노트 변환 · 백지 코딩 훈련 · 코드 도우미 · AI 고객센터를 **한 화면에 합친 코딩 학습 웹 서비스**

![Python](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-ASGI-009688?logo=fastapi&logoColor=white)
![Pyodide](https://img.shields.io/badge/Pyodide-WASM-blueviolet)
![Render](https://img.shields.io/badge/Deploy-Render-46E3B7?logo=render&logoColor=white)
![Status](https://img.shields.io/badge/status-live-success)

**🔗 라이브:** https://hakseup-allinone.onrender.com &nbsp;|&nbsp; **개발:** 최민준 (기획·설계·개발·배포 1인) · 2026

---

## 한눈에 (Summary)

- 데스크톱 앱으로 시작한 코딩 학습 도구를 **FastAPI 웹 서비스로 전환해 클라우드에 공개 배포**한 풀사이클 프로젝트.
- **BYOK · 무상태(stateless) · 브라우저 코드 실행** 설계로 **운영 반복비용 0원 · 멀티유저 안전 · 서버 RCE 원천 차단**을 달성.
- 공개 전 **자체 보안 감사**를 거쳐 Render 무료 티어에 자동 HTTPS로 배포, **`git push` 기반 자동 배포(CI)** 구성.

---

## ✨ 핵심 기능

| | 기능 | 설명 |
|---|---|---|
| 📄 | **변환** | Jupyter(.ipynb)를 학습노트로. 원본 그대로 또는 **AI 요점정리**(핵심·표준·치트시트). .md 저장 |
| 🧠 | **코드연습** | 예시 없이 스스로: ① 한국어로 풀이 설계 → ② 코드 작성·실행(**자동 채점**) → ③ 백지 복원. 막히면 힌트·정답 단계 공개 |
| 💬 | **코드도우미** | 모르는 코드를 붙여넣고 질문하면 AI가 초보자 눈높이로 설명 |
| 🎧 | **고객센터** | 앱 사용법을 학습한 **멀티턴 챗봇(grounded)**. 자주 묻는 질문은 고정 답변으로 즉답 |

---

## 🛠 기술 스택

| 영역 | 기술 |
|---|---|
| **Backend** | Python 3.14 · FastAPI · Uvicorn (ASGI) |
| **Frontend** | Vanilla HTML / CSS / JavaScript · 테마 3종(파스텔·라이트·다크) |
| **코드 실행** | Pyodide (브라우저 WebAssembly Python) |
| **AI** | Google Gemini · Anthropic Claude (BYOK) |
| **Infra** | Render (무료 티어·자동 HTTPS) · GitHub (`git push` CI) |
| **Desktop** | pywebview (레거시·폴백 — 동일 로직 공유) |

---

## 🏗 시스템 아키텍처

```
┌──────────────────────────┐      ┌──────────────────────────┐      ┌─────────────────┐
│   브라우저 (Client)       │  ⇄   │  FastAPI 서버 (Stateless) │  ⇄   │     AI API       │
│                          │      │                          │      │                 │
│ · UI                     │      │ · 변환·요약·도우미·챗봇    │      │ Gemini · Claude  │
│ · Pyodide로 코드 실행·채점 │      │ · 키 미저장 (BYOK 중계)    │      │ (사용자 키로 호출) │
│ · 키/진행상황 localStorage │      │ · 사용자 코드 실행 안 함    │      │                 │
└──────────────────────────┘      └──────────────────────────┘      └─────────────────┘
```

**설계 원칙**
- **서버 무상태** — 진행상황은 브라우저, API 키는 요청 시에만 전달·미저장 → DB 없이 멀티유저 안전
- **단일 로직 공유** — UI 없는 `core.py`를 데스크톱·웹이 수정 없이 import해 재사용
- **사용자 코드는 브라우저(Pyodide)에서만 실행** → 서버 RCE 원천 차단

---

## 🔑 기술적 도전 · 의사결정

<table>
<tr><th>도전</th><th>해결</th></tr>
<tr>
<td>공개 서버에서 사용자 코드 실행 = <b>RCE 위험</b></td>
<td><b>Pyodide(브라우저 WASM)</b>로 실행 — 서버는 코드를 절대 실행 안 함. 무한 루프는 <b>웹 워커 + 6초 타임아웃</b>으로 차단</td>
</tr>
<tr>
<td>AI 비용을 운영자가 부담하면 지속 불가</td>
<td><b>BYOK</b> 구조(사용자 키)·서버 키 미저장 → <b>운영 반복비용 0원</b></td>
</tr>
<tr>
<td>단일 진행파일 = <b>멀티유저 충돌</b></td>
<td>진행상황을 <b>localStorage로 이전</b>, 서버 완전 무상태화 → 무료 인프라 배포 가능</td>
</tr>
<tr>
<td>데스크톱·웹 로직 중복</td>
<td><code>core.py</code> 단일 소스를 양쪽이 공유</td>
</tr>
<tr>
<td>매일 늘어나는 수업 내용을 문제로 만드는 수작업</td>
<td>노트북 → 문제 <b>AI 자동 생성 + 검증 게이트</b>(실행·결정성·출력 자동 점검) 파이프라인</td>
</tr>
<tr>
<td>로컬 PoC ≠ 공개 서버 위험</td>
<td>배포 전 <b>전면 보안 감사</b> — XSS·키 누출·RCE·업로드 제한·캐시·에러 마스킹 점검·보강</td>
</tr>
</table>

---

## 🚀 배포

- **Render 무료 티어** — DB 불필요·무상태 설계라 무료 컨테이너에 적합. `render.yaml` 블루프린트로 원클릭 구성
- **`git push` → 자동 재배포(CI)** · 자동 HTTPS · 배포본은 운영자 키·개인 데이터를 **누출 검사**로 제외
- **비용 모델:** 문제 생성은 1회(운영자) + 런타임은 BYOK → **반복 운영비 0원**

### 로컬 실행
```bash
pip install -r requirements.txt
cd server
python app.py            # http://127.0.0.1:8000
```

---

## 📁 저장소 구조 (배포본)

```
.
├── server/app.py        # FastAPI 진입점 (API 엔드포인트)
├── app/
│   ├── core.py          # UI 없는 순수 로직 (변환·채점·AI 호출) — 데스크톱과 공유
│   └── support_kb.py    # 고객센터 지식베이스
├── web/                 # 화면 (HTML·CSS·JS·Pyodide 워커)
├── 문제은행/             # 코드연습 문제 (.md)
├── render.yaml          # Render 블루프린트
└── requirements.txt
```

---

## 💡 회고

- 보안을 '나중'이 아니라 **설계 단계**에서 고려(BYOK·Pyodide·무상태)한 것이 배포를 단순하게 만들었다.
- 기존 자산(`core.py`)을 재사용해 데스크톱·웹·콘텐츠 도구가 한 로직을 공유 — 유지보수 비용을 낮춤.
- **무료 인프라로도 보안·멀티유저 안전을 갖춘 실서비스를 낼 수 있다**는 걸 확인.

---

<sub>학습 올인원 · 2026 · 최민준 — 본 문서는 실제 개발·배포 과정을 기반으로 작성되었습니다.</sub>
