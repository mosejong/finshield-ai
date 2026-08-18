/**
 * 공유 시트로 들어온 내용을 확인 화면으로 넘긴다.
 *
 * `/check/shared` 가 POST 로 받은 응답 문서에서만 실행된다. 하는 일은 하나다.
 * 문서에 심어진 JSON 을 sessionStorage 로 옮기고 `/check` 로 바꿔치기한다.
 *
 * 왜 정적 파일인가. 이 스크립트가 다루는 값은 외부에서 들어온 문자 원문이다.
 * 인라인 스크립트로 만들면 그 문자열이 실행되는 코드 안에 직접 박히고, 이스케이프
 * 실수 하나가 곧 스크립트 실행이 된다. 여기서는 값이 실행되지 않는
 * `type="application/json"` 태그에만 있고, 이 파일은 값을 모른 채로 배포된다.
 *
 * 왜 replace 인가. push 로 넘어가면 뒤로 가기가 `/check/shared` 로 돌아오고,
 * 브라우저가 POST 재전송을 물어본다. 주소 기록에 공유 경로를 남기지 않는 것도
 * 겸한다.
 *
 * 이 파일은 어떤 경로로도 내용을 기록하지 않는다. console.log 한 줄이면
 * 문자 원문이 기기 로그로 새어 나간다.
 */
(function () {
  "use strict";

  var TARGET = "/check";

  function go() {
    window.location.replace(TARGET);
  }

  var element = document.getElementById("finshield-share-payload");
  if (!element) {
    go();
    return;
  }

  var payload;
  try {
    payload = JSON.parse(element.textContent || "{}");
  } catch {
    // 내용을 남기지 않는다. 실패하면 빈 입력창으로 보내는 편이 낫다.
    go();
    return;
  }

  // 옮긴 뒤에는 문서에 남길 이유가 없다. 이 문서는 곧 사라지지만, 넘어가기
  // 전에 화면이 잠깐 보이는 동안 원문이 DOM 에 떠 있을 이유도 없다.
  element.remove();

  if (payload && typeof payload.key === "string" && typeof payload.text === "string" && payload.text) {
    try {
      window.sessionStorage.setItem(payload.key, payload.text);
    } catch {
      // 프라이빗 모드 등에서 막힐 수 있다. 확인 화면은 빈 상태로 열린다.
    }
  }

  go();
})();
