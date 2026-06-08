#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
core.py — 학습 올인원: 순수 로직 계층 (UI 없음)

이 모듈은 화면(tkinter)과 무관한 모든 기능을 담는다. 덕분에 단위 테스트가 쉽고,
탭 UI들은 이 함수를 호출하기만 하면 된다.

담는 것:
  - 노트북 변환:   Jupyter(.ipynb) → Markdown 문자열 + 이미지
  - 코드 실행/채점: 학습자 코드를 별도 프로세스로 실행, 정답 출력과 비교
  - 힌트:          의도→도구, 뼈대, 한국어 단계 설계
  - 문제은행:       문제은행/*.md 로드 + 기본 내장 템플릿 + 약점 기반 출제
  - 진행 상황:      study_progress.json 저장/로드/집계
  - 코드도우미:     Gemini REST 호출 (표준 urllib만)

경로(헤드폴더 기준):
  학습올인원/
    app/core.py        ← 이 파일
    문제은행/*.md
    data/study_progress.json, .gemini_key, app.log
    코드질문/<날짜>_*.md
"""
from __future__ import annotations

import base64
import html as _html
import json
import logging
import os
import random
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path

# ── 콘솔 인코딩 안전화 ──
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── 경로 ──
APP_DIR = Path(__file__).resolve().parent          # 학습올인원/app
BASE = APP_DIR.parent                               # 학습올인원/
DATA_DIR = BASE / "data"
PROBLEM_BANK_DIR = BASE / "문제은행"
CODE_QA_DIR = BASE / "코드질문"
PROGRESS_FILE = DATA_DIR / "study_progress.json"
UI_FILE = DATA_DIR / "ui_settings.json"             # 테마 등 UI 설정
KEY_FILE = DATA_DIR / ".gemini_key"                 # 개인 키(배포·깃 제외)
ANTHROPIC_KEY_FILE = DATA_DIR / ".anthropic_key"    # Claude 키(개인, 배포·깃 제외)
LOG_FILE = DATA_DIR / "app.log"

# ── 상수 ──
ANSWER_DELAY_DEFAULT = 90
ANSWER_UNLOCK_ATTEMPTS = 5
RUN_TIMEOUT = 6
KOREAN_MIN_CHARS = 8
HISTORY_CAP = 500

DEFAULT_MODEL = "gemini-2.5-flash"
API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
AI_STUDIO_URL = "https://aistudio.google.com/apikey"

# Claude(Anthropic) — '요점정리' 품질용(코드도우미는 무료 Gemini 유지).
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
CLAUDE_MODEL = "claude-sonnet-4-6"   # 사용자 선택(Sonnet). 최고 품질이 필요하면 claude-opus-4-8.
ANTHROPIC_CONSOLE_URL = "https://console.anthropic.com/settings/keys"

# ── 로깅 ──
try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass
logging.basicConfig(filename=str(LOG_FILE), level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s", encoding="utf-8")
log = logging.getLogger("allinone")


# ════════════════════════════════════════════════════════════════════════════
#  1) 노트북(.ipynb) → Markdown 변환
# ════════════════════════════════════════════════════════════════════════════
def _src(cell: dict) -> str:
    s = cell.get("source", "")
    return "".join(s) if isinstance(s, list) else (s or "")


def _join(field) -> str:
    return "".join(field) if isinstance(field, list) else (field or "")


def _guess_lang(nb: dict) -> str:
    meta = nb.get("metadata", {})
    lang = (meta.get("kernelspec", {}).get("language")
            or meta.get("language_info", {}).get("name") or "python")
    return "python" if lang in ("python", "python3") else lang


def read_notebook(path: Path) -> dict:
    """ .ipynb 파일을 dict 로 읽는다(JSON). 실패 시 ValueError. """
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"파일을 찾을 수 없어요: {path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"올바른 .ipynb(JSON) 형식이 아니에요: {e}")
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"노트북을 읽을 수 없어요: {e}")


def notebook_to_markdown(nb: dict, title: str | None = None):
    """노트북 dict → (markdown 문자열, 이미지목록[(파일명, bytes)]).

    이미지는 `assets/output_NN.png` 로 참조하며, 실제 바이트는 따로 반환한다
    (저장할 때 호출자가 assets 폴더에 쓰면 된다).
    """
    cells = nb.get("cells", [])
    lang = _guess_lang(nb)
    out: list[str] = []
    images: list[tuple[str, bytes]] = []
    img_count = 0

    out.append(f"# {title or '수업 노트'}\n")
    out.append(f"> 변환일: {date.today().isoformat()}\n")
    out.append("\n---\n")

    for cell in cells:
        ctype = cell.get("cell_type")
        src = _src(cell).rstrip("\n")
        if ctype == "markdown":
            if src.strip():
                out.append("\n" + src + "\n")
        elif ctype == "code":
            if src.strip():
                out.append(f"\n```{lang}\n{src}\n```\n")
            for o in cell.get("outputs", []):
                otype = o.get("output_type")
                if otype == "stream":
                    txt = _join(o.get("text", "")).rstrip("\n")
                    if txt:
                        out.append(f"\n**출력:**\n```\n{txt}\n```\n")
                elif otype in ("execute_result", "display_data"):
                    data = o.get("data", {})
                    if "image/png" in data:
                        img_count += 1
                        name = f"output_{img_count:02d}.png"
                        b64 = data["image/png"]
                        b64 = "".join(b64) if isinstance(b64, list) else b64
                        try:
                            images.append((name, base64.b64decode(b64)))
                            out.append(f"\n![결과 이미지 {img_count}](assets/{name})\n")
                        except Exception:  # noqa: BLE001
                            log.warning("이미지 디코드 실패(셀 %d)", img_count)
                    elif "text/plain" in data:
                        txt = _join(data["text/plain"]).rstrip("\n")
                        if txt:
                            out.append(f"\n**결과:**\n```\n{txt}\n```\n")
                elif otype == "error":
                    ename = o.get("ename", "Error")
                    evalue = o.get("evalue", "")
                    out.append(f"\n> ⚠️ **{ename}**: {evalue}\n")

    return "".join(out), images


def save_markdown_bundle(md_text: str, images, out_path: Path) -> Path:
    """MD 문자열과 이미지들을 out_path(.md)와 그 옆 assets/ 폴더에 저장."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md_text, encoding="utf-8")
    if images:
        assets = out_path.with_name("assets")
        assets.mkdir(parents=True, exist_ok=True)
        for name, payload in images:
            (assets / name).write_bytes(payload)
    return out_path


def md_to_html(md: str) -> str:
    """간단 마크다운 → HTML (웹 미리보기용, 외부 패키지 없이).

    지원: 제목/굵게/인라인코드/펜스코드/불릿(체크리스트)/번호/구분선/인용/표.
    모든 텍스트는 HTML 이스케이프한다(XSS 방지).
    """
    lines = (md or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    i, n = 0, len(lines)

    def inline(s: str) -> str:
        s = _html.escape(s, quote=False)
        s = re.sub(r"`([^`]+)`", lambda m: f"<code>{m.group(1)}</code>", s)
        s = re.sub(r"\*\*(.+?)\*\*", lambda m: f"<strong>{m.group(1)}</strong>", s)
        return s

    def is_block_start(ln: str) -> bool:
        return bool(re.match(r"^(#{1,6}\s|```|>\s?|\s*[-*]\s|\s*\d+\.\s)", ln)) \
            or bool(re.match(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$", ln))

    while i < n:
        line = lines[i]
        st = line.strip()
        if st.startswith("```"):
            i += 1
            buf = []
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i]); i += 1
            i += 1
            out.append("<pre><code>" + _html.escape("\n".join(buf), quote=False) + "</code></pre>")
            continue
        if re.match(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$", line):
            out.append("<hr>"); i += 1; continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            lv = len(m.group(1))
            out.append(f"<h{lv}>{inline(m.group(2))}</h{lv}>"); i += 1; continue
        # GFM 표
        if "|" in line and i + 1 < n and "-" in lines[i + 1] \
                and re.match(r"^\s*\|?[\s:|-]+\|?\s*$", lines[i + 1]):
            header = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2
            rows = []
            while i < n and "|" in lines[i] and lines[i].strip():
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")]); i += 1
            th = "".join(f"<th>{inline(c)}</th>" for c in header)
            body = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows)
            out.append(f"<table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>")
            continue
        if st.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(re.sub(r"^\s*>\s?", "", lines[i])); i += 1
            out.append(f"<blockquote>{inline(' '.join(buf))}</blockquote>")
            continue
        if re.match(r"^\s*[-*]\s+", line):
            items = []
            while i < n and re.match(r"^\s*[-*]\s+", lines[i]):
                it = re.sub(r"^\s*[-*]\s+", "", lines[i])
                cm = re.match(r"^\[([ xX])\]\s*(.*)$", it)
                if cm:
                    it = ("☑ " if cm.group(1).lower() == "x" else "☐ ") + cm.group(2)
                items.append(f"<li>{inline(it)}</li>"); i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue
        if re.match(r"^\s*\d+\.\s+", line):
            items = []
            while i < n and re.match(r"^\s*\d+\.\s+", lines[i]):
                items.append(f"<li>{inline(re.sub(r'^\\s*\\d+\\.\\s+', '', lines[i]))}</li>"); i += 1
            out.append("<ol>" + "".join(items) + "</ol>")
            continue
        if not st:
            i += 1; continue
        buf = [line]; i += 1
        while i < n and lines[i].strip() and not is_block_start(lines[i]):
            buf.append(lines[i]); i += 1
        out.append(f"<p>{inline(' '.join(buf))}</p>")
    return "\n".join(out)


# ════════════════════════════════════════════════════════════════════════════
#  2) 학습자 코드 실행 / 채점
# ════════════════════════════════════════════════════════════════════════════
def _runner_python() -> str:
    exe = sys.executable or "python"
    if exe.lower().endswith("pythonw.exe"):
        cand = exe[:-len("pythonw.exe")] + "python.exe"
        if Path(cand).exists():
            return cand
    return exe


def run_user_code(code: str, timeout: int = RUN_TIMEOUT):
    """학습자 코드를 별도 프로세스로 실행. (kind, stdout, stderr) 반환.

    kind: ok / timeout / empty / launch
    -I(격리)는 환경변수를 무시하므로 UTF-8 강제는 -X utf8 로 한다(한글 출력 보존).
    """
    if not (code or "").strip():
        return ("empty", "", "")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(
            [_runner_python(), "-I", "-X", "utf8", "-c", code],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, env=env, creationflags=creationflags)
    except subprocess.TimeoutExpired:
        return ("timeout", "", "")
    except Exception as e:  # noqa: BLE001
        log.exception("코드 실행 실패")
        return ("launch", "", str(e))
    return ("ok", proc.stdout or "", proc.stderr or "")


def normalize_output(s: str) -> str:
    s = (s or "").replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in s.split("\n")).strip()


def outputs_match(got: str, expected: str) -> bool:
    return normalize_output(got) == normalize_output(expected)


def friendly_error(stderr: str) -> str:
    lines = [ln for ln in (stderr or "").strip().split("\n") if ln.strip()]
    if not lines:
        return ""
    last = lines[-1].strip()
    tips = {
        "SyntaxError": "문법 오류예요. 콜론(:) 빠짐, 괄호/따옴표 짝, 오타를 확인해 보세요.",
        "IndentationError": "들여쓰기 문제예요. for/if 아래 줄은 보통 공백 4칸 들여써야 해요.",
        "NameError": "정의하지 않은 이름을 썼어요. 변수 철자나 따옴표 누락을 확인해 보세요.",
        "TypeError": "자료형이 안 맞아요. 숫자+글자는 str() 로 바꿔서 합쳐야 해요.",
        "IndexError": "리스트 범위를 벗어났어요. 번호는 0부터, 길이보다 작아야 해요.",
        "KeyError": "딕셔너리에 없는 이름표(key)를 꺼냈어요.",
        "ZeroDivisionError": "0으로 나눴어요. 나누는 값이 0이 아닌지 확인해 보세요.",
        "ValueError": "값이 함수가 기대하는 형태가 아니에요(예: 숫자 변환 실패).",
    }
    for key, tip in tips.items():
        if key in last:
            return f"{last}\n   → {tip}"
    return last


def compute_auto_indent(line_before_cursor: str) -> str:
    """Enter 후 새 줄 들여쓰기: 이전 줄 공백 유지 + ':'로 끝나면 4칸 추가."""
    indent = re.match(r"[ \t]*", line_before_cursor or "").group(0)
    if (line_before_cursor or "").rstrip().endswith(":"):
        indent += "    "
    return indent


# ════════════════════════════════════════════════════════════════════════════
#  3) 기본 내장 문제 템플릿 (랜덤 파라미터)
# ════════════════════════════════════════════════════════════════════════════
NAMES = ["민준", "서연", "지호", "하은", "도윤", "수아", "예준", "지우"]
ITEMS = ["사탕", "쿠키", "연필", "사과", "구슬", "스티커"]
JOBS = ["개발자", "디자이너", "기획자", "분석가", "마케터"]


def t_typecast():
    name = random.choice(NAMES); age = random.randint(8, 60)
    q = ("**[형 변환]** 변수 `name`에 이름, `age`에 나이를 담고 아래처럼 출력하세요. "
         "(힌트: 숫자를 글자와 합치려면 `str()` 필요)\n\n"
         f"**예상 출력**\n```\n{name}님은 {age}살입니다\n```")
    ans = ('name = "%s"\nage = %d\nprint(name + "님은 " + str(age) + "살입니다")' % (name, age))
    return dict(topic="기초", q=q, ans=ans, out=f"{name}님은 {age}살입니다")


def t_divmod():
    a = random.randint(13, 99); b = random.randint(2, 9); item = random.choice(ITEMS)
    q = (f"**[연산]** {item} {a}개를 {b}명이 똑같이 나눕니다. 한 명당 갖는 개수와 남는 개수를 "
         "출력하세요. (힌트: `//`, `%`)\n\n"
         f"**예상 출력**\n```\n한 명당: {a // b} 개\n남는 것: {a % b} 개\n```")
    ans = (f'total = {a}\npeople = {b}\nprint("한 명당:", total // people, "개")\n'
           f'print("남는 것:", total % people, "개")')
    return dict(topic="연산", q=q, ans=ans, out=f"한 명당: {a // b} 개\n남는 것: {a % b} 개")


def t_power():
    base = random.randint(2, 6); exp = random.randint(2, 5)
    q = (f"**[연산]** {base}을(를) {exp}번 곱한 값(거듭제곱)을 출력하세요. (힌트: `**`)\n\n"
         f"**예상 출력**\n```\n{base ** exp}\n```")
    return dict(topic="연산", q=q, ans=f"print({base} ** {exp})", out=str(base ** exp))


def t_index():
    pool = ["빨강", "주황", "노랑", "초록", "파랑", "보라"]
    lst = random.sample(pool, 4)
    q = (f"**[인덱싱]** 리스트 `colors = {lst}` 가 있습니다. 1) 맨 마지막 색, 2) 첫 번째 색을 "
         "차례로 출력하세요. (음수 인덱스 활용)\n\n"
         f"**예상 출력**\n```\n{lst[-1]}\n{lst[0]}\n```")
    return dict(topic="인덱싱", q=q,
                ans=f"colors = {lst}\nprint(colors[-1])\nprint(colors[0])",
                out=f"{lst[-1]}\n{lst[0]}")


def t_slice():
    base = [random.randint(1, 9) for _ in range(7)]
    start = random.randint(0, 2); end = start + random.randint(2, 3)
    q = (f"**[슬라이싱]** `nums = {base}` 에서 인덱스 {start}부터 {end} '직전'까지 잘라 출력하세요.\n\n"
         f"**예상 출력**\n```\n{base[start:end]}\n```")
    return dict(topic="인덱싱", q=q, ans=f"nums = {base}\nprint(nums[{start}:{end}])",
                out=f"{base[start:end]}")


def t_grade():
    score = random.randint(40, 100)
    grade = "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "F"
    q = (f"**[조건문]** 점수 `score = {score}` 의 등급을 출력하세요. "
         "기준: 90↑ A / 80↑ B / 70↑ C / 그 외 F\n\n"
         f"**예상 출력**\n```\n{grade}\n```")
    ans = (f"score = {score}\nif score >= 90:\n    print('A')\nelif score >= 80:\n    print('B')\n"
           "elif score >= 70:\n    print('C')\nelse:\n    print('F')")
    return dict(topic="조건문", q=q, ans=ans, out=grade)


def t_evenodd():
    n = random.randint(1, 99)
    res = f"{n}은(는) 짝수" if n % 2 == 0 else f"{n}은(는) 홀수"
    q = (f"**[조건문]** 숫자 `n = {n}` 이 짝수인지 홀수인지 출력하세요. (힌트: `% 2`)\n\n"
         f"**예상 출력**\n```\n{res}\n```")
    ans = (f"n = {n}\nif n % 2 == 0:\n    print(f'{{n}}은(는) 짝수')\nelse:\n    print(f'{{n}}은(는) 홀수')")
    return dict(topic="조건문", q=q, ans=ans, out=res)


def t_listmethod():
    base = random.sample(["우유", "빵", "계란", "사과", "치즈", "주스"], 2)
    add = random.choice(["라면", "과자", "커피", "김밥"])
    res = sorted(base + [add])
    q = (f"**[리스트]** `cart = {base}` 에 '{add}'을(를) 추가한 뒤 가나다순 정렬해 출력하세요. "
         "(힌트: `.append()`, `.sort()`)\n\n"
         f"**예상 출력**\n```\n{res}\n```")
    return dict(topic="리스트", q=q,
                ans=f"cart = {base}\ncart.append('{add}')\ncart.sort()\nprint(cart)", out=f"{res}")


def t_forsum():
    n = random.randint(5, 30)
    q = (f"**[반복문]** 1부터 {n}까지 모두 더한 합을 출력하세요. (for + range)\n\n"
         f"**예상 출력**\n```\n{sum(range(1, n + 1))}\n```")
    return dict(topic="반복문", q=q,
                ans=f"total = 0\nfor i in range(1, {n + 1}):\n    total += i\nprint(total)",
                out=str(sum(range(1, n + 1))))


def t_gugudan():
    dan = random.randint(2, 9)
    lines = "\n".join(f"{dan} x {i} = {dan * i}" for i in range(1, 10))
    q = (f"**[반복문]** {dan}단을 출력하세요. (for + range, f-string)\n\n"
         f"**예상 출력**\n```\n{lines}\n```")
    return dict(topic="반복문", q=q,
                ans="dan = %d\nfor i in range(1, 10):\n    print(f'{dan} x {i} = {dan * i}')" % dan,
                out=lines)


def t_func_avg():
    nums = [random.randint(50, 100) for _ in range(random.randint(3, 5))]
    avg = sum(nums) / len(nums)
    q = ("**[함수]** 숫자 리스트를 받아 평균을 돌려주는 함수 `average(nums)`를 만들고, "
         f"`{nums}` 의 평균을 출력하세요.\n\n**예상 출력**\n```\n{avg}\n```")
    return dict(topic="함수", q=q,
                ans=f"def average(nums):\n    return sum(nums) / len(nums)\n\nprint(average({nums}))",
                out=str(avg))


def t_class():
    name = random.choice(NAMES); job = random.choice(JOBS)
    q = ("**[클래스]** 이름(`name`)과 직업(`job`)을 속성으로 갖는 `Person` 클래스를 만드세요. "
         "`introduce()`는 '저는 OOO, 직업은 XXX입니다'를 출력합니다. "
         f"name='{name}', job='{job}' 객체를 만들어 `introduce()`를 호출하세요.\n\n"
         f"**예상 출력**\n```\n저는 {name}, 직업은 {job}입니다\n```")
    ans = ("class Person:\n    def __init__(self, name, job):\n        self.name = name\n"
           "        self.job = job\n    def introduce(self):\n"
           "        print(f'저는 {self.name}, 직업은 {self.job}입니다')\n\n"
           "p = Person('%s', '%s')\np.introduce()") % (name, job)
    return dict(topic="클래스", q=q, ans=ans, out=f"저는 {name}, 직업은 {job}입니다")


TEMPLATES = {
    "기초": [t_typecast], "연산": [t_divmod, t_power], "인덱싱": [t_index, t_slice],
    "조건문": [t_grade, t_evenodd], "리스트": [t_listmethod], "반복문": [t_forsum, t_gugudan],
    "함수": [t_func_avg], "클래스": [t_class],
}


# ════════════════════════════════════════════════════════════════════════════
#  4) 힌트
# ════════════════════════════════════════════════════════════════════════════
TOOL_MAP = {
    "기초": "값은 `변수 = 값` 으로 담는다. 숫자를 글자와 합칠 땐 `str(숫자)` 로 바꿔야 `+` 로 이어붙는다.",
    "연산": "사칙연산 `+ - * /`, 몫 `//`, 나머지 `%`, 거듭제곱 `**`.",
    "인덱싱": "`리스트[번호]` — 0부터, 맨 뒤는 `-1`. 범위는 `리스트[시작:끝]`(끝 직전까지).",
    "슬라이싱": "`리스트[시작:끝]` → 시작부터 끝 ‘직전’까지. 끝 번호는 포함되지 않는다.",
    "조건문": "`if 조건:` / `elif 조건:` / `else:`. 짝/홀은 `% 2 == 0`.",
    "리스트": "추가 `리스트.append(값)`, 정렬 `리스트.sort()`. 메서드는 ‘자료.기능()’.",
    "반복문": "`for 변수 in range(시작, 끝):`. 합 누적은 `total = 0` 만들고 `total += i`.",
    "함수": "`def 이름(매개변수):` 로 정의하고 `return` 으로 값을 돌려준다. 쓸 땐 `이름(값)`.",
    "클래스": "`class 이름:` 안에 `__init__(self, ...)` 로 속성 저장(`self.x = x`), 기능은 `def 메서드(self):`.",
    "딕셔너리": "`{이름표: 값}`. 꺼내기 `d[이름표]`, 추가 `d[새이름표]=값`, 순회 `for k, v in d.items():`.",
}
GENERIC_TOOL_HINT = ("먼저 한국어 단계를 한 줄씩 코드로 옮겨 봐. ‘반복’이면 for, ‘조건’이면 if, "
                     "‘모아두기’면 리스트 `[]`, ‘문장에 값 끼우기’면 f-string `f\"{x}\"`.")


def intent_hint(topic: str) -> str:
    return TOOL_MAP.get(topic, GENERIC_TOOL_HINT)


def skeleton_hint(ans: str) -> str:
    lines = (ans or "").split("\n")
    if len(lines) > 1:
        return lines[0] + "\n    ⋯  (이 구조로 시작해 나머지 줄을 직접 채워 보세요)"
    masked = re.sub(r"'[^']*'|\"[^\"]*\"|\d+", "__", lines[0] if lines else "")
    return masked or "(뼈대를 만들 수 없어요 — 한국어 단계를 한 줄씩 코드로 옮겨 보세요)"


def korean_step_guide() -> str:
    return ("단계 나누는 틀: ① 무엇이 주어졌나(값·입력) → ② 무엇을 해야 하나"
            "(반복? 조건? 계산?) → ③ 결과를 어떻게 만드나 → ④ 무엇을 출력하나.\n"
            "한 문장에 한 가지씩, 사람한테 시키듯 순서대로 적어 보세요. "
            "아직 코드 문법은 신경 쓰지 말고 ‘무엇을 할지’만!")


def describe_code_korean(ans: str) -> str:
    steps: list[str] = []

    def add(s: str) -> None:
        if not steps or steps[-1] != s:
            steps.append(s)

    for raw in (ans or "").split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m_cls = re.match(r"^class\s+(\w+)", line)
        m_def = re.match(r"^def\s+(\w+)", line)
        if m_cls:
            add(f"클래스 `{m_cls.group(1)}` 를 만든다")
        elif re.match(r"^def\s+__init__", line):
            add("객체가 생길 때 값을 받아 속성으로 저장하도록 준비한다 (__init__)")
        elif m_def:
            add(f"함수/메서드 `{m_def.group(1)}` 를 정의한다")
        elif re.match(r"^self\.\w+\s*=", line):
            add("받은 값을 객체 속성(self.…)에 저장한다")
        elif line.startswith("return"):
            add("계산 결과를 return 으로 돌려준다")
        elif re.match(r"^for\s+\w+\s+in\s+range", line):
            add("range 로 숫자를 하나씩 꺼내며 반복한다")
        elif re.match(r"^for\s+", line):
            add("묶음(리스트·딕셔너리)에서 하나씩 꺼내며 반복한다")
        elif line.startswith("while"):
            add("조건이 참인 ‘동안’ 반복한다 (끝으로 가는 변화 잊지 말기)")
        elif re.match(r"^if\b", line) and "% 2" in line:
            add("2로 나눈 나머지(% 2)로 짝수/홀수를 가른다")
        elif re.match(r"^if\b", line):
            add("조건에 따라 경우를 나눈다 (if)")
        elif line.startswith("elif"):
            add("다른 조건도 차례로 검사한다 (elif)")
        elif line.startswith("else"):
            add("나머지 경우를 처리한다 (else)")
        elif re.search(r"\.append\(", line):
            add("리스트에 원소를 추가한다 (.append)")
        elif re.search(r"\.sort\(", line):
            add("리스트를 정렬한다 (.sort)")
        elif re.match(r"^\w+\s*\+=", line):
            add("값을 계속 더해 누적한다 (+=)")
        elif re.match(r"^\w+\s*=\s*0\b", line):
            add("누적·합계를 담을 변수를 0으로 초기화한다")
        elif re.match(r"^\w+\s*=\s*[\[{]", line):
            mm = re.match(r"^(\w+)", line)
            add(f"`{mm.group(1)}` 에 묶음(리스트/딕셔너리)을 만든다")
        elif re.match(r"^\w+\s*=", line):
            mm = re.match(r"^(\w+)", line)
            add(f"변수 `{mm.group(1)}` 에 값을 담는다")
        elif line.startswith("print"):
            extra = " (몫 //)" if "//" in line else (" (거듭제곱 **)" if "**" in line
                                                      else (" (나머지 %)" if "%" in line else ""))
            add(f"결과를 출력한다{extra}")
        else:
            add("(이 줄은 직접 해석해 보세요)")
    if not steps:
        return "이 문제는 단계가 단순해요 — 무엇을 출력해야 하는지부터 한국어로 적어 보세요."
    return "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))


# ════════════════════════════════════════════════════════════════════════════
#  5) 마크다운 문제은행 (커리큘럼 단원 확장)
# ════════════════════════════════════════════════════════════════════════════
def parse_problem_md(text: str):
    topic = None
    stage = None
    m = re.search(r"^#\s*주제\s*[:：]\s*(.+)$", text, re.M)
    if m:
        topic = m.group(1).strip()
    m = re.search(r"^#\s*단계\s*[:：]\s*(\d+)", text, re.M)
    if m:
        stage = int(m.group(1))
    body = re.sub(r"^#\s*(주제|단계)\s*[:：].*$", "", text, flags=re.M)
    blocks = re.split(r"^\s*-{3,}\s*$", body, flags=re.M)
    problems = []
    for blk in blocks:
        codem = re.search(r"```(?:python|py)?\s*\n(.*?)```", blk, re.S)
        if not codem:
            continue
        answer = codem.group(1).rstrip("\n")
        if not answer.strip():
            continue
        prompt = blk[:codem.start()]
        prompt = re.sub(r"^##\s*(문제|풀이)\s*$", "", prompt, flags=re.M)
        prompt = re.sub(r"^>.*$", "", prompt, flags=re.M)
        prompt = re.sub(r"^#\s+.*$", "", prompt, flags=re.M)
        problems.append({"q": prompt.strip() or "(문제 설명 없음)", "answer": answer})
    return topic, stage, problems


def load_problem_bank():
    bank: dict = {}
    stages: dict = {}
    if not PROBLEM_BANK_DIR.exists():
        return bank, stages
    for path in sorted(PROBLEM_BANK_DIR.glob("*.md")):
        if path.name.startswith("_"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            log.warning("문제파일 읽기 실패 %s: %s", path.name, e)
            continue
        topic, stage, problems = parse_problem_md(text)
        if not topic or not problems:
            log.warning("문제파일 형식 부족: %s", path.name)
            continue
        bank.setdefault(topic, []).extend(problems)
        if stage is not None:
            stages[topic] = stage
    return bank, stages


BANK, BANK_STAGES = load_problem_bank()


def _build_stage_map() -> dict:
    stage = {t: i for i, t in enumerate(TEMPLATES.keys(), 1)}
    stage.update(BANK_STAGES)
    base = max(stage.values(), default=0)
    extra = 1
    for t in BANK:
        if t not in stage:
            stage[t] = base + extra
            extra += 1
    return stage


STAGE = _build_stage_map()


def all_topics(allowed=None) -> list[str]:
    topics = set(TEMPLATES) | set(BANK)
    if allowed:
        topics = {t for t in topics if t in allowed}
    return sorted(topics, key=lambda t: (STAGE.get(t, 999), t))


def _materialize_md_problem(topic: str, spec: dict):
    if "out" not in spec:
        kind, out, err = run_user_code(spec.get("answer", ""))
        if kind == "ok" and not err.strip():
            spec["out"] = out
        else:
            spec["out"] = None
            log.warning("문제 풀이 실행 실패(%s): kind=%s", topic, kind)
    if spec.get("out") is None:
        return None
    expected = spec["out"].strip()
    display_q = spec.get("q", "") + f"\n\n**예상 출력**\n```\n{expected}\n```"
    return dict(topic=topic, q=display_q, ans=spec.get("answer", ""), out=spec["out"])


# ════════════════════════════════════════════════════════════════════════════
#  6) 진행 상황 + 약점 기반 출제
# ════════════════════════════════════════════════════════════════════════════
def topic_weakness(progress: dict, topic: str) -> float:
    st = progress.get("topics", {}).get(topic, {})
    seen = st.get("seen", 0)
    score = (st.get("needed_answer", 0) + 1) / (st.get("solved", 0) + 1)
    if seen == 0:
        score *= 2.5
    return score


def pick_topics(progress: dict, n: int, allowed=None) -> list[str]:
    topics = all_topics(allowed) or all_topics()
    weights = [topic_weakness(progress, t) for t in topics]
    return random.choices(topics, weights=weights, k=max(1, n))


def make_problem(topic: str) -> dict:
    candidates = [("bank", spec) for spec in BANK.get(topic, [])]
    candidates += [("fn", fn) for fn in TEMPLATES.get(topic, [])]
    random.shuffle(candidates)
    for kind, c in candidates:
        try:
            p = _materialize_md_problem(topic, c) if kind == "bank" else c()
        except Exception:  # noqa: BLE001
            log.exception("문제 생성 실패(%s)", topic)
            p = None
        if p:
            p.setdefault("topic", topic)
            p.setdefault("q", "(문제 설명 없음)")
            p.setdefault("ans", "")
            p.setdefault("out", "")
            return p
    return dict(topic=topic, ans="", out="",
                q=f"**[{topic}]** 이 단원의 문제를 불러오지 못했어요. 문제은행 .md 를 확인해 주세요.")


def build_session(progress: dict, count: int, allowed=None) -> list[dict]:
    return [make_problem(t) for t in pick_topics(progress, count, allowed)]


def _default_progress() -> dict:
    return {"version": 1, "topics": {}, "history": [], "totals": {"problems": 0, "mastered": 0}}


def load_progress() -> dict:
    try:
        if PROGRESS_FILE.exists():
            data = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "topics" in data:
                data.setdefault("history", [])
                data.setdefault("totals", {"problems": 0, "mastered": 0})
                return data
    except Exception as e:  # noqa: BLE001
        log.warning("진행 파일 읽기 실패(%s) → 초기화", e)
    return _default_progress()


def save_progress(progress: dict) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = PROGRESS_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(PROGRESS_FILE)
    except Exception as e:  # noqa: BLE001
        log.exception("진행 파일 저장 실패: %s", e)


def load_ui() -> dict:
    """UI 설정(테마 등) 로드. 없으면 빈 dict."""
    try:
        if UI_FILE.exists():
            d = json.loads(UI_FILE.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                return d
    except Exception as e:  # noqa: BLE001
        log.warning("UI 설정 읽기 실패: %s", e)
    return {}


def save_ui(d: dict) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        UI_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        log.exception("UI 설정 저장 실패: %s", e)


def record_result(progress: dict, rec: dict) -> None:
    topic = rec.get("topic", "기타")
    t = progress["topics"].setdefault(
        topic, {"seen": 0, "solved": 0, "mastered": 0, "needed_answer": 0,
                "last_seen": "", "best_seconds": None})
    t["seen"] += 1
    if rec.get("solved"):
        t["solved"] += 1
    if rec.get("saw_answer"):
        t["needed_answer"] += 1
    if rec.get("mastered"):
        t["mastered"] += 1
        progress["totals"]["mastered"] += 1
    secs = rec.get("seconds")
    if rec.get("solved") and isinstance(secs, (int, float)):
        prev = t.get("best_seconds")
        t["best_seconds"] = secs if prev is None else min(prev, secs)
    t["last_seen"] = rec.get("ts", "")
    progress["totals"]["problems"] += 1
    progress["history"].append(rec)
    if len(progress["history"]) > HISTORY_CAP:
        progress["history"] = progress["history"][-HISTORY_CAP:]


# ════════════════════════════════════════════════════════════════════════════
#  7) 코드도우미 (Gemini)
# ════════════════════════════════════════════════════════════════════════════
SYSTEM_INSTRUCTION = (
    "당신은 프로그래밍을 처음 배우는 한국인 수강생을 가르치는 친절한 코딩 튜터입니다.\n"
    "학생이 막힌 '코드'와 '질문'을 줍니다. 다음 원칙으로 한국어로 답하세요.\n"
    "1) 초보자 눈높이: 어려운 용어는 쉬운 말로 풀고, 필요하면 일상 비유를 씁니다.\n"
    "2) 핵심은 '왜 이렇게 작성했는가'입니다. 코드를 의미 단위(줄)로 나눠 설명합니다.\n"
    "3) 가능하면 예상 실행 결과도 보여 줍니다.\n"
    "4) 흔한 실수는 '⚠️', 더 쉬운 대안은 '✅'로 짧게 덧붙입니다.\n"
    "5) 마크다운(소제목·목록·코드블록)으로 한눈에 읽기 쉽게 정리합니다.\n"
    "6) 코드가 비어 있으면 질문만으로 일반 개념을 설명합니다.\n"
    "7) 제공된 범위를 벗어나 단정하기 어려운 부분은 '[추측]'이라 표시합니다.\n"
    "장황한 인사말 없이 본문부터 시작하세요.")

# ── 요약(변환 탭 'AI 요점정리') ──
# 구조: 공통 시스템 프롬프트(레벨 무관) + 레벨별 지시문(원본 뒤에 붙음).
# 이렇게 나누면 Claude에서 '큰 원본'을 prompt caching 할 수 있다(같은 문서를 3레벨로 호출 시 비용 절감).
_SUM_SHARED_SYSTEM = (
    "당신은 한국인 초보 수강생을 위한 학습 자료를 정리하는 전문가입니다.\n"
    "입력은 Jupyter 노트북을 그대로 변환한 '긴 원본'입니다. 절대 그대로 베끼지 말고, "
    "요청한 형식과 분량에 맞게 핵심만 남겨 과감히 '압축'하세요. 한국어 마크다운으로 쓰고, "
    "장황한 인사말 없이 본문부터 시작합니다.")

_SUM_CONCISE = (
    "【형식: 핵심 요약】 시험 전에 빠르게 훑어보는 핵심 노트로 과감히 압축하세요.\n"
    "- 분량은 원본의 1/4 이하. 중복·잡담·비슷한 예시·사소한 출력은 모두 삭제.\n"
    "- 맨 위 `# 제목` + `## 📌 한 줄 요약`. 그다음 개념별 `## 소제목`.\n"
    "- 각 개념은 핵심을 2~4줄로만. 꼭 필요할 때만 대표 코드 1개를 ```python```으로(짧게), 결과는 `# → 결과` 한 줄.\n"
    "- 비슷한 예시가 여럿이면 가장 대표적인 하나만 남긴다.\n"
    "- 자주 틀리는 점은 '⚠️ …' 한 줄.\n"
    "- 맨 아래 `## ✅ 복습 체크리스트` `- [ ]` 5개 내외.\n"
    "- 교과서처럼 늘어놓지 말 것.")

_SUM_STANDARD = (
    "【형식: 표준 학습노트】 군더더기·중복을 걷어내 요점이 잘 정리된 학습노트로 재구성하세요.\n"
    "- 분량은 원본의 1/2 정도. 반복 예시는 합치거나 줄인다.\n"
    "- `# 제목` + `## 📌 한 줄 요약` + 개념별 `## 소제목`.\n"
    "- 각 개념: 쉬운 설명(비유 환영) + 핵심 코드 1~2개(```python```) + 필요 시 '화면 →' 결과.\n"
    "- 자주 헷갈리는 점은 '⚠️'.\n"
    "- 맨 아래 `## ✅ 복습 체크리스트` `- [ ]` 5~8개.")

_SUM_CHEAT = (
    "【형식: 치트시트】 한 화면에 들어오는 초압축 요약표로 만드세요.\n"
    "- 표(| … |)와 짧은 불릿 위주, 최소 분량.\n"
    "- 개념 → 문법/형태 → 한 줄 예시 순. 코드는 한 줄 예시만.\n"
    "- 맨 위 `# 제목 치트시트`. 섹션은 `## 소제목`.\n"
    "- 꼭 기억할 함정은 '⚠️ …' 불릿 몇 개.\n"
    "- 설명 문장은 최소화.")

SUMMARY_LEVELS = {
    "concise":    {"label": "핵심 요약",    "max_tokens": 4096, "instruction": _SUM_CONCISE},
    "standard":   {"label": "표준 학습노트", "max_tokens": 8192, "instruction": _SUM_STANDARD},
    "cheatsheet": {"label": "치트시트",     "max_tokens": 4096, "instruction": _SUM_CHEAT},
}


class GeminiError(Exception):
    """사용자에게 그대로 보여 줄 한국어 오류 메시지."""


def load_api_key() -> str:
    env = os.environ.get("GEMINI_API_KEY", "").strip()
    if env:
        return env
    try:
        if KEY_FILE.exists():
            return KEY_FILE.read_text(encoding="utf-8").strip()
    except Exception as e:  # noqa: BLE001
        log.warning("키 파일 읽기 실패: %s", e)
    return ""


def save_api_key(key: str) -> None:
    key = key.strip()
    if not key:
        raise GeminiError("빈 키는 저장할 수 없습니다.")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    KEY_FILE.write_text(key, encoding="utf-8")
    log.info("Gemini API 키 저장")


def load_anthropic_key() -> str:
    """Claude 키: 환경변수 ANTHROPIC_API_KEY → 로컬 .anthropic_key 순."""
    env = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if env:
        return env
    try:
        if ANTHROPIC_KEY_FILE.exists():
            return ANTHROPIC_KEY_FILE.read_text(encoding="utf-8").strip()
    except Exception as e:  # noqa: BLE001
        log.warning("Claude 키 파일 읽기 실패: %s", e)
    return ""


def save_anthropic_key(key: str) -> None:
    key = key.strip()
    if not key:
        raise GeminiError("빈 키는 저장할 수 없습니다.")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ANTHROPIC_KEY_FILE.write_text(key, encoding="utf-8")
    log.info("Claude API 키 저장")


def summary_provider():
    """요약에 쓸 제공자 결정: Claude 키 있으면 Claude(고품질), 없으면 Gemini, 둘 다 없으면 None."""
    ak = load_anthropic_key()
    if ak:
        return ("claude", ak)
    gk = load_api_key()
    if gk:
        return ("gemini", gk)
    return (None, "")


def build_user_text(question: str, code: str) -> str:
    question = (question or "").strip()
    code = (code or "").strip()
    parts = ["아래 코드에 대한 학생의 질문입니다.\n",
             "【질문】\n" + (question or "(질문 없음 — 코드 전체를 초보자용으로 설명해 주세요)")]
    parts.append("\n\n【코드】\n```\n" + code + "\n```" if code else "\n\n【코드】\n(코드 없음 — 개념 위주로 설명)")
    return "".join(parts)


def _explain_http_error(code: int, detail: str) -> str:
    snippet = (detail or "").strip()
    if len(snippet) > 300:
        snippet = snippet[:300] + " …"
    table = {
        400: "요청 형식 또는 API 키에 문제가 있습니다. 키를 다시 확인하세요.",
        403: "API 키 권한 문제입니다. Google AI Studio에서 키 상태를 확인하세요.",
        404: f"모델을 찾을 수 없습니다. 모델명('{DEFAULT_MODEL}')을 확인하세요.",
        429: "무료 사용 한도를 초과했습니다. 잠시 후 다시 시도하세요.",
        500: "Gemini 서버 일시 오류입니다. 잠시 후 다시 시도하세요.",
        503: "Gemini 서버가 혼잡합니다. 잠시 후 다시 시도하세요.",
    }
    return f"{table.get(code, f'HTTP 오류({code})')}\n[상세] {snippet}"


def _diagnose_empty(payload: dict) -> str:
    fb = payload.get("promptFeedback", {})
    if fb.get("blockReason"):
        return f"콘텐츠가 안전 필터에 막혔습니다(blockReason={fb['blockReason']})."
    cands = payload.get("candidates") or []
    if cands and cands[0].get("finishReason") == "SAFETY":
        return "응답이 안전 필터에 의해 중단되었습니다."
    if cands and cands[0].get("finishReason") == "MAX_TOKENS":
        return "답변이 최대 길이에 도달해 잘렸습니다. 질문을 더 좁혀 보세요."
    return "빈 응답을 받았습니다. 잠시 후 다시 시도하세요."


def _gemini_generate(system_instruction: str, user_text: str, api_key: str,
                     model: str = DEFAULT_MODEL, timeout: int = 60,
                     max_tokens: int = 4096) -> str:
    """Gemini generateContent 공용 호출. 실패 시 GeminiError(한국어)."""
    if not api_key:
        raise GeminiError("API 키가 없습니다. 먼저 'API 키 설정'에서 무료 키를 등록하세요.")
    url = f"{API_BASE}/{model}:generateContent"
    body = {
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "contents": [{"role": "user", "parts": [{"text": user_text}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": max_tokens},
    }
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("x-goog-api-key", api_key)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            pass
        log.error("HTTPError %s", e.code)
        raise GeminiError(_explain_http_error(e.code, detail))
    except urllib.error.URLError as e:
        raise GeminiError(f"네트워크에 연결할 수 없습니다: {e.reason}\n인터넷/방화벽/프록시를 확인하세요.")
    except Exception as e:  # noqa: BLE001
        log.exception("호출 오류")
        raise GeminiError(f"알 수 없는 오류: {e}")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise GeminiError("서버 응답을 해석할 수 없습니다(JSON 아님).")
    try:
        cand = payload["candidates"][0]
        text = cand["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, TypeError):
        raise GeminiError(_diagnose_empty(payload))
    if cand.get("finishReason") == "MAX_TOKENS":
        text += ("\n\n> ⚠️ 답변이 최대 길이에 도달해 **일부가 잘렸습니다.** "
                 "더 짧은 요약 모드(핵심 요약/치트시트)로 다시 시도하면 잘림 없이 받을 수 있어요.")
    return text


def call_gemini(question: str, code: str, api_key: str,
                model: str = DEFAULT_MODEL, timeout: int = 60) -> str:
    """[코드도우미] 코드 설명."""
    return _gemini_generate(SYSTEM_INSTRUCTION, build_user_text(question, code),
                            api_key, model, timeout, max_tokens=4096)


def _explain_anthropic_error(code: int, detail: str) -> str:
    """Claude(Anthropic) HTTP 오류를 한국어로 설명. detail 에서 error.message 추출 시도."""
    msg = ""
    try:
        msg = (json.loads(detail or "{}").get("error", {}) or {}).get("message", "")
    except Exception:  # noqa: BLE001
        pass
    table = {
        400: "요청 형식 또는 본문에 문제가 있습니다.",
        401: "API 키가 올바르지 않습니다. Claude 키(sk-ant-…)를 다시 확인하세요.",
        403: "이 키로는 접근 권한이 없습니다(결제/권한 설정 확인).",
        404: f"모델을 찾을 수 없습니다. 모델명('{CLAUDE_MODEL}')을 확인하세요.",
        413: "원본이 너무 깁니다. 더 짧은 노트로 나눠서 시도하세요.",
        429: "사용 한도(분당/일일)를 초과했습니다. 잠시 후 다시 시도하세요.",
        500: "Claude 서버 일시 오류입니다. 잠시 후 다시 시도하세요.",
        529: "Claude 서버가 혼잡합니다. 잠시 후 다시 시도하세요.",
    }
    base = table.get(code, f"HTTP 오류({code})가 발생했습니다.")
    return f"{base}" + (f"\n[상세] {msg[:300]}" if msg else "")


def _anthropic_generate(system: str, messages: list, api_key: str, max_tokens: int,
                        model: str = CLAUDE_MODEL, timeout: int = 240) -> str:
    """Claude Messages API 호출(표준 urllib). 실패 시 GeminiError(한국어 메시지)."""
    if not api_key:
        raise GeminiError("Claude API 키가 없습니다. 먼저 'Claude 키 설정'에서 등록하세요.")
    body = {"model": model, "max_tokens": max_tokens, "system": system, "messages": messages}
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(ANTHROPIC_API_URL, data=data, method="POST")
    req.add_header("content-type", "application/json")
    req.add_header("x-api-key", api_key)
    req.add_header("anthropic-version", ANTHROPIC_VERSION)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            pass
        log.error("Anthropic HTTPError %s", e.code)
        raise GeminiError(_explain_anthropic_error(e.code, detail))
    except urllib.error.URLError as e:
        raise GeminiError(f"네트워크에 연결할 수 없습니다: {e.reason}\n인터넷/방화벽/프록시를 확인하세요.")
    except Exception as e:  # noqa: BLE001
        log.exception("Anthropic 호출 오류")
        raise GeminiError(f"알 수 없는 오류: {e}")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise GeminiError("서버 응답을 해석할 수 없습니다(JSON 아님).")
    blocks = payload.get("content") or []
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
    if not text:
        if payload.get("stop_reason") == "refusal":
            raise GeminiError("Claude가 안전상의 이유로 요약을 거부했습니다.")
        raise GeminiError("빈 응답을 받았습니다. 잠시 후 다시 시도하세요.")
    if payload.get("stop_reason") == "max_tokens":
        text += ("\n\n> ⚠️ 답변이 최대 길이에 도달해 **일부가 잘렸을 수 있어요.** "
                 "더 짧은 모드(핵심 요약/치트시트)로 다시 시도해 보세요.")
    usage = payload.get("usage", {})
    log.info("Claude 요약 usage: in=%s out=%s cache_read=%s",
             usage.get("input_tokens"), usage.get("output_tokens"),
             usage.get("cache_read_input_tokens"))
    return text


def summarize_notebook_md(raw_md: str, level: str = "concise",
                          title: str | None = None, timeout: int = 240) -> str:
    """[변환] 원본 변환 마크다운을 요점 정리한다(AI).

    Claude 키가 있으면 Claude(고품질, 사용자 선택)로, 없으면 Gemini로 폴백한다.
    level: concise/standard/cheatsheet.
    """
    if not (raw_md or "").strip():
        raise GeminiError("요약할 내용이 없습니다. 먼저 노트북을 변환하세요.")
    cfg = SUMMARY_LEVELS.get(level, SUMMARY_LEVELS["concise"])
    provider, key = summary_provider()
    if not key:
        raise GeminiError("요약용 API 키가 없습니다. Claude 키(권장) 또는 Gemini 키를 등록하세요.")

    header = ("아래는 Jupyter 노트북을 그대로 변환한 원본입니다."
              f"{(' 제목: ' + title) if title else ''}")
    body = f"{header}\n\n----- 원본 시작 -----\n{raw_md}\n----- 원본 끝 -----"

    if provider == "claude":
        # 큰 원본 블록에 cache_control → 같은 문서를 다른 레벨로 호출 시 캐시 적중(비용↓).
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": body, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": cfg["instruction"]},
            ],
        }]
        return _anthropic_generate(_SUM_SHARED_SYSTEM, messages, key,
                                   max_tokens=cfg["max_tokens"], timeout=timeout)
    # Gemini 폴백: 공통 시스템 + 레벨 지시문을 합쳐서.
    system = _SUM_SHARED_SYSTEM + "\n\n" + cfg["instruction"]
    return _gemini_generate(system, body, key, max_tokens=cfg["max_tokens"])


def _slugify(text: str, maxlen: int = 30) -> str:
    text = re.sub(r"\s+", "_", (text or "").strip())
    text = re.sub(r'[\\/:*?"<>|]', "", text).strip("._")
    return text[:maxlen] or "질문"


def save_qa_markdown(question: str, code: str, answer: str) -> Path:
    CODE_QA_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out = CODE_QA_DIR / f"{stamp}_{_slugify(question)}.md"
    lines = [f"# 코드 질문 — {stamp}", "", "## 질문",
             (question.strip() or "_(질문 없음)_"), "", "## 코드"]
    lines += (["```python", code.rstrip(), "```"] if code.strip() else ["_(코드 없음)_"])
    lines += ["", "## 답변", answer.rstrip(), ""]
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


# ════════════════════════════════════════════════════════════════════════════
#  셀프테스트 (UI 없이 핵심 로직 점검)
# ════════════════════════════════════════════════════════════════════════════
def selftest() -> int:
    ok = True

    def check(name: str, cond: bool) -> None:
        nonlocal ok
        print(f"  [{'OK' if cond else 'FAIL'}] {name}")
        ok = ok and cond

    print("== core 셀프테스트 ==")
    # 변환
    nb = {"cells": [{"cell_type": "markdown", "source": ["# 제목"]},
                    {"cell_type": "code", "source": ["print(1+1)"],
                     "outputs": [{"output_type": "stream", "text": ["2\n"]}]}],
          "metadata": {"language_info": {"name": "python"}}}
    md, imgs = notebook_to_markdown(nb, "테스트")
    check("ipynb→md 제목/코드/출력 포함", "# 테스트" in md and "print(1+1)" in md and "출력:" in md)
    check("이미지 없음", imgs == [])
    _h = md_to_html("# 제목\n- 항목\n`코드`\n\n```\nx=1\n```")
    check("md→html(제목/리스트/코드/펜스)", all(t in _h for t in ("<h1>", "<ul>", "<code>", "<pre>")))
    check("md→html 이스케이프", "&lt;" in md_to_html("a < b"))

    # 코드 실행/채점
    k, out, _ = run_user_code("print(1 + 1)")
    check("코드 실행", k == "ok" and outputs_match(out, "2"))
    k2, out2, _ = run_user_code("print('민준')")
    check("한글 UTF-8", k2 == "ok" and outputs_match(out2, "민준"))
    check("빈 코드 감지", run_user_code("")[0] == "empty")
    _, _, e3 = run_user_code("print(x)")
    check("NameError 한국어", "정의하지 않은" in friendly_error(e3))

    # 들여쓰기/힌트
    check("자동들여쓰기 콜론", compute_auto_indent("for i in range(5):") == "    ")
    check("뼈대 힌트", "__" in skeleton_hint("print(2 ** 5)"))
    check("한국어 설계 변환", "반복" in describe_code_korean("for i in range(3):\n    print(i)"))

    # 문제은행 파싱/채점
    _t, _s, _ps = parse_problem_md("# 주제: T\n# 단계: 99\n---\n## 문제\n더하기\n## 풀이\n```python\nprint(1+2)\n```\n")
    check("문제파싱", _t == "T" and _s == 99 and len(_ps) == 1)
    _m = _materialize_md_problem("T", dict(_ps[0]))
    check("자동 채점값(=3)", _m and _m["out"].strip() == "3")

    # 템플릿/출제
    p = make_problem("반복문")
    check("문제 생성 필수키", all(key in p for key in ("topic", "q", "ans", "out")))
    chosen = pick_topics(_default_progress(), 5)
    valid = set(all_topics())
    check("주제 5개 선택", len(chosen) == 5 and all(t in valid for t in chosen))

    # 진행 저장/로드
    global PROGRESS_FILE
    real = PROGRESS_FILE
    PROGRESS_FILE = DATA_DIR / "study_progress.selftest.json"
    try:
        prog = _default_progress()
        record_result(prog, {"ts": "t", "topic": "반복문", "seconds": 5, "solved": True,
                              "saw_answer": False, "mastered": True})
        save_progress(prog)
        check("진행 저장/로드", load_progress()["topics"]["반복문"]["mastered"] == 1)
        try:
            PROGRESS_FILE.unlink()
        except Exception:
            pass
    finally:
        PROGRESS_FILE = real

    # 코드도우미 / 요점정리(키 없이)
    check("키 없을 때 GeminiError", _raises_key_error())
    check("HTTP 429 한국어", "한도" in _explain_http_error(429, "{}"))

    def _sum_empty():
        try:
            summarize_notebook_md("   ")
            return False
        except GeminiError:
            return True
        except Exception:
            return False

    def _claude_nokey():
        try:
            _anthropic_generate("sys", [{"role": "user", "content": "hi"}], api_key="", max_tokens=16)
            return False
        except GeminiError:
            return True
        except Exception:
            return False

    check("요점정리 빈 내용 차단", _sum_empty())
    check("요약 레벨 3종", set(SUMMARY_LEVELS) == {"concise", "standard", "cheatsheet"})
    check("핵심요약 압축 지시(1/4)", "1/4" in SUMMARY_LEVELS["concise"]["instruction"])
    check("복습 체크리스트 포함", "복습 체크리스트" in SUMMARY_LEVELS["standard"]["instruction"])
    check("Claude 키 없으면 오류", _claude_nokey())
    check("Claude 에러 한국어(401)", "키" in _explain_anthropic_error(401, "{}"))
    check("요약 provider 튜플", isinstance(summary_provider(), tuple) and len(summary_provider()) == 2)

    print("== 결과:", "전체 통과 ✅" if ok else "실패 항목 있음 ❌", "==")
    return 0 if ok else 1


def _raises_key_error() -> bool:
    try:
        call_gemini("q", "c", api_key="")
        return False
    except GeminiError:
        return True
    except Exception:
        return False


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if "--list" in sys.argv:
        for t in all_topics():
            src = []
            if t in BANK:
                src.append(f"문제은행 {len(BANK[t])}문제")
            if t in TEMPLATES:
                src.append("기본내장")
            print(f"  단계 {STAGE.get(t, '?'):>2}  {t:<10} ({', '.join(src)})")
        sys.exit(0)
    print("core.py — 학습 올인원 로직 모듈. 단독 실행: --selftest / --list")
