/* pyodide-worker.js — 학습올인원 '코드연습' 실행 샌드박스 (웹 모드 전용)

   메인 스레드와 분리된 Web Worker 안에서 Pyodide(브라우저용 CPython/WebAssembly)로
   학습자 코드를 실행한다. 설계 원칙:
     · 서버는 사용자 코드를 절대 실행하지 않는다(RCE 방지). 실행은 전부 이 워커.
     · 무한 루프 대비 — 메인 스레드가 제한시간(6초) 초과 시 worker.terminate() 로
       강제 종료한다. 동기 무한 루프는 워커를 막으므로 terminate 가 유일한 탈출구다.
     · 채점 규칙은 데스크톱(core.run_user_code/outputs_match)과 동일하게 메인 스레드가 수행.
       워커는 (stdout, stderr) 만 정확히 돌려준다.

   메시지 프로토콜 (메인 → 워커):
     { type:'warmup' }          : Pyodide 로딩만 미리 수행 → { type:'ready' } | { type:'error', error }
     { id, code }               : code 실행 → { id, kind:'ok'|'launch', stdout, stderr }
*/
'use strict';

// 검증된 안정 버전(2026-06 기준 최신). CDN 경로 실재 확인됨.
var PYODIDE_VERSION = 'v0.29.4';
var PYODIDE_BASE = 'https://cdn.jsdelivr.net/pyodide/' + PYODIDE_VERSION + '/full/';

var _pyReady = null;  // loadPyodide Promise (1회만)

// 학습자 코드를 '깨끗한 전역'에서 실행하고 (stdout, stderr) 를 모아 돌려주는 러너.
// - exec 로 모듈 스크립트처럼 실행( __name__=='__main__' )해 데스크톱과 동작을 맞춘다.
// - 매 실행 새 네임스페이스를 써서 이전 실행의 변수가 새 채점에 새지 않도록 격리(core 의 -I 와 유사).
// - SyntaxError/런타임 예외는 traceback 을 stderr 로 흘려보내 friendly_error 가 마지막 줄을 집게 한다.
var RUNNER = [
  'import sys, io, traceback',
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
].join('\n');

function ensurePyodide() {
  if (!_pyReady) {
    _pyReady = (async function () {
      importScripts(PYODIDE_BASE + 'pyodide.js');
      // indexURL 을 명시해 WASM/패키지 데이터를 같은 CDN 에서 받도록 한다.
      var py = await loadPyodide({ indexURL: PYODIDE_BASE });
      py.runPython(RUNNER);  // __learn_run__ 정의(1회)
      return py;
    })();
  }
  return _pyReady;
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

  // 2) 코드 실행 요청
  var id = msg.id;
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
