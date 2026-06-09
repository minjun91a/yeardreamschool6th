/* pyodide-worker.js — 학습올인원 '코드연습' 실행 샌드박스 (웹 모드 전용)

   메인 스레드와 분리된 Web Worker 안에서 Pyodide(브라우저용 CPython/WebAssembly)로
   학습자 코드를 실행한다. 설계 원칙:
     · 서버는 사용자 코드를 절대 실행하지 않는다(RCE 방지). 실행은 전부 이 워커.
     · 무한 루프 대비 — 메인 스레드가 제한시간(6초) 초과 시 worker.terminate() 로
       강제 종료한다. 동기 무한 루프는 워커를 막으므로 terminate 가 유일한 탈출구다.
     · 채점 규칙은 데스크톱(core.run_user_code/outputs_match)과 동일하게 메인 스레드가 수행.
       워커는 (stdout, stderr) 만 정확히 돌려준다.

   SQL 트랙(SELECT 연습)도 같은 워커에서 처리한다:
     · Pyodide 표준 라이브러리의 sqlite3 로 데이터셋(.db)을 읽기전용 조회한다.
     · 결과 result set 은 core._fmt_resultset 과 '글자 그대로' 같은 규칙으로 정규 텍스트화 →
       채점은 파이썬 stdout 과 동일한 문자열 비교로 흐른다.

   메시지 프로토콜 (메인 → 워커):
     { type:'warmup' }                       : Pyodide 로딩만 → { type:'ready' } | { type:'error', error }
     { id, code }                            : 파이썬 code 실행 → { id, kind:'ok'|'launch', stdout, stderr }
     { id, kind:'loaddb', dataset }          : 데이터셋(.db) 미리 적재 → { id, kind:'ok'|'launch', ... }
     { id, kind:'sql', sql, dataset, ordered}: SQL 실행 → { id, kind:'ok'|'launch', stdout, stderr }
*/
'use strict';

// 검증된 안정 버전(2026-06 기준 최신). CDN 경로 실재 확인됨.
var PYODIDE_VERSION = 'v0.29.4';
var PYODIDE_BASE = 'https://cdn.jsdelivr.net/pyodide/' + PYODIDE_VERSION + '/full/';

var _pyReady = null;          // loadPyodide Promise (1회만)
var _loadedDatasets = {};     // dataset 이름 → Pyodide FS 경로(중복 적재 방지)

// 파이썬 측 정의:
//  __learn_run__ : 학습자 코드를 '깨끗한 전역'에서 실행하고 (stdout, stderr) 수집.
//  _fmt_resultset: SQL result set → 정규 텍스트(⚠️ core._fmt_resultset 과 동일해야 함).
//  __learn_sql__ : 데이터셋 파일에 SQL 을 읽기전용 실행하고 (정규결과, 에러) 반환.
var RUNNER = [
  'import sys, io, traceback, sqlite3',
  '',
  'def __learn_run__(src):',
  '    buf, ebuf = io.StringIO(), io.StringIO()',
  '    old_o, old_e = sys.stdout, sys.stderr',
  '    sys.stdout, sys.stderr = buf, ebuf',
  '    try:',
  "        exec(compile(src, '<연습>', 'exec'), {'__name__': '__main__'})",
  '    except SystemExit:',
  '        pass',
  '    except BaseException:',
  '        traceback.print_exc()',
  '    finally:',
  '        sys.stdout, sys.stderr = old_o, old_e',
  '    return [buf.getvalue(), ebuf.getvalue()]',
  '',
  'def _fmt_resultset(cols, rows, ordered=False):',
  '    def cell(v):',
  '        if v is None:',
  '            return "NULL"',
  '        if isinstance(v, float):',
  '            return str(int(v)) if v == int(v) else repr(round(v, 6))',
  '        return str(v)',
  '    lines = ["\\t".join(cell(v) for v in row) for row in rows]',
  '    if not ordered:',
  '        lines.sort()',
  '    return "\\n".join(lines)',
  '',
  'def __learn_sql__(path, sql, ordered):',
  '    try:',
  '        con = sqlite3.connect(path)',
  '        try:',
  '            con.execute("PRAGMA query_only = ON")',
  '            cur = con.cursor()',
  '            cur.execute(sql)',
  '            rows = cur.fetchall()',
  '            cols = [d[0] for d in (cur.description or [])]',
  '            return [_fmt_resultset(cols, rows, bool(ordered)), ""]',
  '        finally:',
  '            con.close()',
  '    except BaseException as e:',
  '        return ["", "SQLError: " + str(e)]',
].join('\n');

function ensurePyodide() {
  if (!_pyReady) {
    _pyReady = (async function () {
      importScripts(PYODIDE_BASE + 'pyodide.js');
      // indexURL 을 명시해 WASM/패키지 데이터를 같은 CDN 에서 받도록 한다.
      var py = await loadPyodide({ indexURL: PYODIDE_BASE });
      py.runPython(RUNNER);  // __learn_run__ / _fmt_resultset / __learn_sql__ 정의(1회)
      return py;
    })();
  }
  return _pyReady;
}

// 데이터셋(.db)을 같은 출처(/sql/<파일>)에서 받아 Pyodide FS 에 쓴다. 한 번 받으면 캐시.
async function ensureDataset(py, dataset) {
  if (_loadedDatasets[dataset]) return _loadedDatasets[dataset];
  var url = new URL('sql/' + dataset, self.location.href).href;
  var resp = await fetch(url);
  if (!resp.ok) throw new Error('데이터 파일을 불러오지 못했어요 (' + resp.status + '): ' + dataset);
  var buf = new Uint8Array(await resp.arrayBuffer());
  var path = '/ds_' + dataset.replace(/[^A-Za-z0-9_.-]/g, '_');
  py.FS.writeFile(path, buf);
  _loadedDatasets[dataset] = path;
  return path;
}

self.onmessage = async function (e) {
  var msg = e.data || {};

  // 1) 워밍업: Pyodide 다운로드/초기화만 미리 끝내 둔다(첫 실행 지연 제거).
  if (msg.type === 'warmup') {
    try {
      await ensurePyodide();
      self.postMessage({ type: 'ready' });
    } catch (err) {
      self.postMessage({ type: 'error', error: String((err && err.message) || err) });
    }
    return;
  }

  var id = msg.id;

  // 2) 데이터셋 미리 적재(SQL 세션 진입 시). 다운로드 지연을 실행 제한시간과 분리하기 위함.
  if (msg.kind === 'loaddb') {
    try {
      var pyd = await ensurePyodide();
      await ensureDataset(pyd, msg.dataset || '');
      self.postMessage({ id: id, kind: 'ok', stdout: 'LOADED', stderr: '' });
    } catch (err) {
      self.postMessage({ id: id, kind: 'launch', stdout: '', stderr: String((err && err.message) || err) });
    }
    return;
  }

  // 3) SQL 실행
  if (msg.kind === 'sql') {
    var pys;
    try {
      pys = await ensurePyodide();
      await ensureDataset(pys, msg.dataset || '');
    } catch (err) {
      self.postMessage({ id: id, kind: 'launch', stdout: '', stderr: String((err && err.message) || err) });
      return;
    }
    try {
      var path = _loadedDatasets[msg.dataset || ''];
      var fnq = pys.globals.get('__learn_sql__');
      var resq = fnq(path, msg.sql || '', !!msg.ordered);
      var arrq = resq.toJs();
      resq.destroy();
      fnq.destroy();
      self.postMessage({ id: id, kind: 'ok', stdout: arrq[0] || '', stderr: arrq[1] || '' });
    } catch (err) {
      self.postMessage({ id: id, kind: 'launch', stdout: '', stderr: String((err && err.message) || err) });
    }
    return;
  }

  // 4) 파이썬 코드 실행 요청(기본)
  var code = msg.code || '';
  var py;
  try {
    py = await ensurePyodide();
  } catch (err) {
    self.postMessage({ id: id, kind: 'launch', stdout: '', stderr: 'Pyodide 로드 실패: ' + String((err && err.message) || err) });
    return;
  }

  try {
    var fn = py.globals.get('__learn_run__');
    var res = fn(code);          // 파이썬 list [stdout, stderr]
    var arr = res.toJs();        // → JS 배열
    res.destroy();
    fn.destroy();
    self.postMessage({ id: id, kind: 'ok', stdout: arr[0] || '', stderr: arr[1] || '' });
  } catch (err) {
    // 파이썬 사용자 코드 예외가 아니라 브릿지/러너 수준 오류(이례적)만 여기로 온다.
    self.postMessage({ id: id, kind: 'launch', stdout: '', stderr: String((err && err.message) || err) });
  }
};
