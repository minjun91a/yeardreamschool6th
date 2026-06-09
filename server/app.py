#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
app.py — 학습올인원 웹 서버 (P0 PoC)

기존 데스크톱 앱의 로직(app/core.py)을 '수정 없이 그대로' 재사용해,
같은 기능을 브라우저에서 쓰도록 HTTP로 노출한다.

이 PoC가 하는 일:
  1) GET  /                   : 기존 web/ 화면(index.html·styles.css·app.js) 정적 서빙
  2) POST /api/convert/upload : .ipynb 업로드 -> 마크다운 변환 결과(HTML) 반환
  3) GET  /api/health         : 동작 확인용

실행:
    py -3 app.py                                  # http://127.0.0.1:8000
    py -3 -m uvicorn app:app --reload --port 8000 # (개발용 자동 새로고침)
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import Body, FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

# ── 기존 로직(core.py)을 재사용하기 위해 app/ 을 import 경로에 추가 ──
SERVER_DIR = Path(__file__).resolve().parent     # 학습올인원/server
BASE = SERVER_DIR.parent                          # 학습올인원/
APP_DIR = BASE / "app"                            # 학습올인원/app  (core.py 위치)
WEB_DIR = BASE / "web"                            # 학습올인원/web  (UI)
sys.path.insert(0, str(APP_DIR))
import core  # noqa: E402  (경로 추가 뒤에 import해야 함)
import support_kb  # noqa: E402  고객센터 지식베이스(데스크톱과 공유)

# 클라우드(Render 등) 로그 뷰어에서 core 의 로그도 보이도록 stdout 으로도 출력
# (core 는 파일 data/app.log 에 기록 — core.py 는 수정하지 않고 여기서 핸들러만 추가).
import logging  # noqa: E402
logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))

app = FastAPI(title="학습올인원 서버 (P0 PoC)")

MAX_UPLOAD_BYTES = 3 * 1024 * 1024   # 업로드 .ipynb 최대 3MB (메모리 DoS 방지; 노트북은 보통 ~100KB)


@app.middleware("http")
async def cache_headers(request, call_next):
    """API 응답엔 키·개인 데이터가 담길 수 있어 캐시 금지(no-store).
    정적 자산은 재검증 허용(no-cache: 옛 캐시는 안 쓰되 304로 빠르게)."""
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    else:
        response.headers.setdefault("Cache-Control", "no-cache")
    return response


@app.get("/api/health")
def health():
    """서버가 살아있는지 확인하는 가장 단순한 엔드포인트."""
    return {"ok": True, "service": "학습올인원 서버 PoC"}


@app.post("/api/convert/upload")
async def convert_upload(file: UploadFile = File(...)):
    """업로드된 .ipynb 를 core 로 변환해 결과 HTML 을 돌려준다.

    데스크톱 앱의 Api.pick_notebook 과 동일한 로직 — '네이티브 파일 선택'만
    'HTTP 업로드'로 바뀌었을 뿐, 변환은 같은 core 함수를 쓴다.
    """
    # 메모리 DoS 방지: 상한까지만 청크로 읽는다(초과 시 즉시 중단).
    raw = b""
    while True:
        chunk = await file.read(256 * 1024)
        if not chunk:
            break
        raw += chunk
        if len(raw) > MAX_UPLOAD_BYTES:
            return JSONResponse({"ok": False, "error": "파일이 너무 커요(최대 3MB)."}, status_code=413)
    name = file.filename or "노트.ipynb"
    stem = Path(name).stem

    tmp: Path | None = None
    try:
        # 업로드 바이트를 임시 .ipynb 로 저장해 core.read_notebook 으로 검증·파싱
        with tempfile.NamedTemporaryFile(suffix=".ipynb", delete=False) as f:
            f.write(raw)
            tmp = Path(f.name)
        nb = core.read_notebook(tmp)
        md, images = core.notebook_to_markdown(nb, title=stem)
    except ValueError as e:
        # 잘못된 노트북 등 사용자 입력 오류
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    except Exception as e:  # noqa: BLE001
        core.log.exception("변환 오류")
        return JSONResponse({"ok": False, "error": "서버 처리 중 오류가 발생했어요. 잠시 후 다시 시도해 주세요."}, status_code=500)
    finally:
        if tmp and tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass

    return {"ok": True, "name": name, "chars": len(md), "images": len(images),
            "md": md, "html": core.md_to_html(md)}


@app.post("/api/convert/summarize")
async def convert_summarize(payload: dict = Body(...)):
    """변환된 원본 마크다운(md)을 AI로 요점정리한다. (BYOK: 키는 클라이언트가 보냄)

    core.summarize_notebook_md 의 본문 구성과 동일하되, 디스크 키 대신
    요청에 담겨 온 사용자 키(anthropic_key / gemini_key)로 호출한다.
    서버는 키를 저장하지 않는다.
    """
    md = (payload.get("md") or "").strip()
    level = payload.get("level") or "concise"
    title = payload.get("title") or None
    anthropic_key = (payload.get("anthropic_key") or "").strip()
    gemini_key = (payload.get("gemini_key") or "").strip()

    if not md:
        return JSONResponse({"ok": False, "error": "요약할 내용이 없어요. 먼저 변환하세요."}, status_code=400)
    if not (anthropic_key or gemini_key):
        return {"ok": False, "nokey": True}

    cfg = core.SUMMARY_LEVELS.get(level, core.SUMMARY_LEVELS["concise"])
    header = "아래는 Jupyter 노트북을 그대로 변환한 원본입니다." + (f" 제목: {title}" if title else "")
    body = f"{header}\n\n----- 원본 시작 -----\n{md}\n----- 원본 끝 -----"

    try:
        if anthropic_key:   # Claude 우선(고품질) — 둘 다 등록 시 Claude 사용
            provider = "claude"
            messages = [{
                "role": "user",
                "content": [
                    {"type": "text", "text": body, "cache_control": {"type": "ephemeral"}},
                    {"type": "text", "text": cfg["instruction"]},
                ],
            }]
            note = core._anthropic_generate(core._SUM_SHARED_SYSTEM, messages,
                                            anthropic_key, max_tokens=cfg["max_tokens"])
        else:               # Gemini(무료) — Claude 키가 없을 때
            provider = "gemini"
            system = core._SUM_SHARED_SYSTEM + "\n\n" + cfg["instruction"]
            note = core._gemini_generate(system, body, gemini_key, max_tokens=cfg["max_tokens"])
    except core.GeminiError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:  # noqa: BLE001
        core.log.exception("요약 오류")
        return JSONResponse({"ok": False, "error": "서버 처리 중 오류가 발생했어요. 잠시 후 다시 시도해 주세요."}, status_code=500)

    return {"ok": True, "provider": provider, "html": core.md_to_html(note)}


@app.post("/api/helper")
async def helper(payload: dict = Body(...)):
    """[코드도우미] 코드+질문을 무료 Gemini로 설명. (BYOK: 키는 클라이언트가 보냄)

    데스크톱 Api.helper_ask 와 동일 로직 — core.call_gemini 재사용.
    서버에 Q&A를 저장하지는 않는다(데스크톱은 로컬 저장했지만, 멀티유저 대비).
    """
    code = payload.get("code") or ""
    question = payload.get("question") or ""
    gemini_key = (payload.get("gemini_key") or "").strip()

    if not gemini_key:
        return {"ok": False, "nokey": True}
    if not code.strip() and not question.strip():
        return JSONResponse({"ok": False, "error": "코드나 질문 중 하나는 입력해 주세요."}, status_code=400)

    try:
        ans = core.call_gemini(question, code, gemini_key)
    except core.GeminiError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:  # noqa: BLE001
        core.log.exception("helper 오류")
        return JSONResponse({"ok": False, "error": "서버 처리 중 오류가 발생했어요. 잠시 후 다시 시도해 주세요."}, status_code=500)

    return {"ok": True, "html": core.md_to_html(ans)}


# ── 코드연습(trainer) ──
# stateless: 출제 시 문제+정답+힌트를 한 번에 내려주고, 공개는 클라이언트가 단계적으로.
# 코드 실행/채점은 브라우저(Pyodide)에서 — 서버는 사용자 코드를 실행하지 않는다(7b).
# 진행상황은 '클라이언트(localStorage)' 가 보관·전송한다 — 서버는 저장하지 않는다(멀티유저 분리).
#   topics/start/summary: 받은 progress 로 약점 계산(읽기 전용)
#   finish: 받은 progress 에 결과 반영 후 '갱신된 progress' 를 돌려준다(저장은 클라이언트가).
def _client_progress(payload: dict) -> dict:
    """클라이언트가 보낸 진행상황을 검증해 반환(없으면 빈 진행). 서버는 디스크에 저장하지 않는다."""
    p = payload.get("progress")
    if isinstance(p, dict) and isinstance(p.get("topics"), dict):
        p.setdefault("history", [])
        p.setdefault("totals", {"problems": 0, "mastered": 0})
        return p
    return {"version": 1, "topics": {}, "history": [], "totals": {"problems": 0, "mastered": 0}}


@app.post("/api/trainer/topics")
def trainer_topics(payload: dict = Body(default={})):
    prog = _client_progress(payload)
    tops = core.all_topics()
    ranked = sorted(tops, key=lambda t: core.topic_weakness(prog, t), reverse=True)
    weakest = ranked[0] if ranked else None
    out = []
    for t in tops:
        st = prog.get("topics", {}).get(t, {})
        out.append({"topic": t, "stage": core.STAGE.get(t, 0),
                    "seen": st.get("seen", 0), "mastered": st.get("mastered", 0),
                    "needed": st.get("needed_answer", 0), "bank": t in core.BANK,
                    "weakest": t == weakest})
    return {"topics": out}


@app.post("/api/trainer/start")
def trainer_start(payload: dict = Body(...)):
    topic = payload.get("topic") or None
    count = int(payload.get("count") or 5)
    restriction = None if topic is None else [topic]
    prog = _client_progress(payload)
    problems = core.build_session(prog, count, restriction)
    items = []
    for i, p in enumerate(problems):
        h = core.problem_hints(p)
        items.append({
            "idx": i, "topic": p["topic"], "stage": core.STAGE.get(p["topic"], 0),
            "q_html": core.md_to_html(p["q"]),
            # 종류(python/sql) — SQL 은 브라우저 워커가 dataset 에 쿼리 실행, ordered=순서까지 채점
            "kind": p.get("kind", "python"),
            "dataset": p.get("dataset", ""),
            "ordered": bool(p.get("ordered", False)),
            # 아래는 클라이언트가 '단계적으로만' 공개한다(처음엔 화면에 안 보임)
            "ans": p["ans"], "out": (p["out"] or "").strip(),
            "intent": h["intent"],
            "skeleton": h["skeleton"],
            "korean_example": h["korean_example"],
        })
    return {"count": len(items), "items": items,
            "scope": topic if topic else "약점 우선(전체)",
            "korean_step": core.korean_step_guide()}


@app.post("/api/trainer/finish")
def trainer_finish(payload: dict = Body(...)):
    rec = dict(payload.get("rec") or {})
    rec.setdefault("ts", datetime.now().isoformat(timespec="seconds"))
    rec["reconstructed"] = bool(rec.get("mastered"))
    prog = _client_progress(payload)
    core.record_result(prog, rec)
    # 디스크에 저장하지 않고, 갱신된 진행상황을 클라이언트(localStorage)에 돌려준다.
    return {"ok": True, "progress": prog}


@app.post("/api/trainer/summary")
def trainer_summary(payload: dict = Body(default={})):
    prog = _client_progress(payload)
    ranked = sorted(prog.get("topics", {}).items(),
                    key=lambda kv: core.topic_weakness(prog, kv[0]), reverse=True)
    weak = ", ".join(t for t, _ in ranked[:3]) if ranked else "(데이터 부족)"
    return {"weak": weak}


@app.get("/api/trainer/cheatsheet")
def trainer_cheatsheet():
    return {"html": core.md_to_html(core.cheatsheet_md())}


# ── 고객센터(앱 사용법 챗봇) ──
# 앱 사용법을 멀티턴으로 안내한다. 무료 Gemini 우선(없으면 Claude 폴백).
# 시스템 프롬프트/대화 펼치기는 app/support_kb.py 에 둬서 데스크톱(app_web.py)과 공유한다.
# 서버는 대화를 저장하지 않는다(클라이언트가 히스토리를 보관·전송). core 수정 없이 생성함수 재사용.
@app.post("/api/support")
async def support(payload: dict = Body(...)):
    """[고객센터] 앱 사용법 챗봇(멀티턴). 무료 Gemini 우선·Claude 폴백. (BYOK)"""
    messages = payload.get("messages") or []
    gemini_key = (payload.get("gemini_key") or "").strip()
    anthropic_key = (payload.get("anthropic_key") or "").strip()

    if not (gemini_key or anthropic_key):
        return {"ok": False, "nokey": True}
    if not any((m.get("content") or "").strip() for m in messages):
        return JSONResponse({"ok": False, "error": "질문을 입력해 주세요."}, status_code=400)

    claude_msgs = [{"role": m.get("role"), "content": m.get("content")}
                   for m in messages if (m.get("content") or "").strip()]
    try:
        if gemini_key:   # 무료 Gemini 우선 — 누구나 무료로 도움말 사용
            provider = "gemini"
            try:
                ans = core._gemini_generate(support_kb.SUPPORT_SYSTEM, support_kb.support_transcript(messages),
                                            gemini_key, max_tokens=2048)
            except core.GeminiError as ge:
                # 무료 Gemini 한도(429)·혼잡(503)·일시오류(500) → Claude 키가 있으면 자동 전환
                if getattr(ge, "code", None) in (429, 500, 503) and anthropic_key:
                    provider = "claude"
                    ans = core._anthropic_generate(support_kb.SUPPORT_SYSTEM, claude_msgs, anthropic_key, max_tokens=2048)
                else:
                    raise
        else:            # Gemini 키가 없으면 처음부터 Claude
            provider = "claude"
            ans = core._anthropic_generate(support_kb.SUPPORT_SYSTEM, claude_msgs, anthropic_key, max_tokens=2048)
    except core.GeminiError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:  # noqa: BLE001
        core.log.exception("고객센터 오류")
        return JSONResponse({"ok": False, "error": "서버 처리 중 오류가 발생했어요. 잠시 후 다시 시도해 주세요."}, status_code=500)

    return {"ok": True, "provider": provider, "html": core.md_to_html(ans)}


# 기존 web/ UI 정적 서빙.
# 반드시 위의 /api 경로들을 '먼저' 등록한 뒤 "/" 에 mount 해야
# /api 요청이 정적 서빙에 가려지지 않는다. html=True 면 "/" 가 index.html 을 준다.
app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")


if __name__ == "__main__":
    import uvicorn

    print("학습올인원 서버 PoC → http://127.0.0.1:8000  (끄기: Ctrl+C)")
    uvicorn.run(app, host="127.0.0.1", port=8000)
