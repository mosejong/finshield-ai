"""설명이 없는 이유의 닫힌 어휘.

이 계층은 지금까지 실패를 **문장으로** 들고 다녔다. `LlmUnavailable("google_ai_studio
stopped early: SAFETY")` 처럼. 그 문장은 아무도 읽지 않는다 — `explain_analysis` 가
전부 `None` 으로 접고, 라우트는 `explanation: null` 을 내려보내고, 거기서 끝난다.
그래서 `docs/34` 9절이 두 줄을 적어 뒀다: **안전 필터 차단율을 모른다**, 그리고
**이 계층은 아무것도 기록하지 않는다.** 두 줄은 같은 줄이다. 세는 것이 없어서
모르는 것이다.

세려면 이름이 필요하고, **이름은 닫힌 목록이어야 한다.**

사유를 문자열로 남기면 언젠가 본문이 그 문자열에 실린다. 400 응답은 요청 일부를
되돌려 주고, 그 요청 안에는 사용자가 붙여넣은 문자가 들어 있다. 프로바이더가
`finishReason` 에 새 값을 넣으면 그 값이 그대로 라벨이 되고, Prometheus 라벨은
한 번 늘어나면 줄지 않는다. `ADR 0006` 이 허용 목록으로 관측을 짜는 이유가
그것이다 — 마스킹은 빠뜨린 것을 흘리고, 허용 목록은 모르는 것을 버린다.

그래서 여기 있는 값들만 로그와 지표에 나간다. 응답 본문에서 온 문자열은 하나도
없고, 앞으로도 없다. 새 사유가 필요하면 **이 파일을 고쳐야 한다** — 그것이 검토를
거치는 유일한 자리다.

`UNSPECIFIED` 가 어휘 안에 있는 것도 그 규율이다. `LlmProvider` 는 Protocol 이고,
우리가 쓰지 않은 구현이 사유 없이 `LlmUnavailable` 을 던질 수 있다. 그때 값을
지어내면 안 된다. **어휘가 닫혀 있으려면 모르는 것을 담는 칸도 어휘 안에 있어야
한다.** 반대로 `LlmOutputRejected` 는 사유를 **요구한다** — 그쪽은 전부
`validation.py` 안에서 우리가 던진다. 남이 던질 수 있는 예외는 사유를 요구할 수
없고, 우리만 던지는 예외는 요구할 수 있다.

거부 사유를 한 칸으로 뭉치지 않은 이유도 적어 둔다. `validation.py` 는 여섯 가지를
잡는데, 그중 **없는 연락처를 지어낸 경우**는 이 서비스가 낼 수 있는 가장 나쁜
출력이다(사용자가 그 번호로 전화를 건다). 여섯을 `output_rejected` 하나로 세면
그 숫자가 길이 초과에 묻힌다. 나눠 두면 `rejected_invented_contact` 하나만 보고도
경보를 걸 수 있다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ExplanationOutcome(StrEnum):
    """설명 시도 하나의 결과. 로그와 지표에 나가는 값은 이 목록뿐이다."""

    # --- 성공 ---
    OK = "ok"

    # --- 우리 쪽 조립이 틀렸다. 배포 직후에 보여야 하는 값들이다. ---
    #
    # 이 둘이 운영에서 0 이 아니면 설정이나 계약이 틀린 것이고, 재시도로 나아지지
    # 않는다. 프로바이더 장애와 섞어 세면 "왜 항상 대체 모델이 답하는가" 를
    # 영영 못 찾는다.
    PROVIDER_MISCONTRACTED = "provider_miscontracted"
    UNSUPPORTED_MODEL = "unsupported_model"

    # --- 프로바이더에 닿지 못했다 ---
    #
    # 타임아웃을 따로 세는 이유는 이 값이 **우리 예산 이야기**이기 때문이다.
    # 실측 7.7~8.2초에 14초를 줬다(`runtime.py`). 이 칸이 오르면 모델이 느려진
    # 것이고, 예산을 올릴지 대체 모델을 앞세울지 결정할 근거가 된다. 다른 전송
    # 오류와 뭉치면 그 신호가 사라진다.
    TIMEOUT = "timeout"
    TRANSPORT_ERROR = "transport_error"
    HTTP_ERROR = "http_error"

    # --- 응답이 왔지만 쓸 수 없다 ---
    MALFORMED_BODY = "malformed_body"

    # 요청이 막힌 것과 응답이 막힌 것은 다르다.
    #
    # `PROMPT_BLOCKED` 는 우리가 보낸 것이 거부된 경우다(`promptFeedback.blockReason`).
    # 사기 문자를 그대로 다루는 서비스라 **정상 입력이 여기서 막힐 수 있고**, 그것이
    # `docs/34` 9절이 걱정한 바로 그 경우다. `SAFETY_BLOCKED` 는 모델이 답을 만들다
    # 스스로 멈춘 경우다. 앞은 우리 프롬프트 설계 문제이고 뒤는 모델 쪽 문제다.
    PROMPT_BLOCKED = "prompt_blocked"
    SAFETY_BLOCKED = "safety_blocked"
    TRUNCATED = "truncated"
    RECITATION_BLOCKED = "recitation_blocked"
    # 우리가 모르는 `finishReason`. 값 자체는 버리고 이 칸으로 센다.
    STOPPED_EARLY = "stopped_early"
    EMPTY_TEXT = "empty_text"

    # --- 모델이 답했지만 출력 검증이 버렸다 ---
    #
    # 여기부터가 `docs/34` 가 말한 "근거 이탈률" 이다. 위의 값들은 프로바이더
    # 사정이고, 아래 값들은 **모델이 우리 계약을 어긴 비율**이다.
    REJECTED_EMPTY = "rejected_empty"
    REJECTED_TOO_LONG = "rejected_too_long"
    REJECTED_URL = "rejected_url"
    REJECTED_RRN = "rejected_rrn"
    REJECTED_CONTRADICTS_VERDICT = "rejected_contradicts_verdict"
    REJECTED_INVENTED_CONTACT = "rejected_invented_contact"

    # --- 모르는 것을 담는 칸 ---
    #
    # 사유 없이 올라온 `LlmUnavailable`. `app/` 안의 코드는 이 값을 만들지 않고,
    # 그 사실은 테스트가 지킨다.
    UNSPECIFIED = "unspecified"


# 프로바이더 사정이 아니라 **모델 출력의 품질**인 결과들. 근거 이탈률을 계산하는
# 쪽에서 이 집합을 쓴다.
REJECTION_OUTCOMES = frozenset(
    {
        ExplanationOutcome.REJECTED_EMPTY,
        ExplanationOutcome.REJECTED_TOO_LONG,
        ExplanationOutcome.REJECTED_URL,
        ExplanationOutcome.REJECTED_RRN,
        ExplanationOutcome.REJECTED_CONTRADICTS_VERDICT,
        ExplanationOutcome.REJECTED_INVENTED_CONTACT,
    }
)

# 안전 필터에 막힌 결과들. `docs/34` 9절이 요구한 차단율의 분자다.
BLOCKED_OUTCOMES = frozenset(
    {
        ExplanationOutcome.PROMPT_BLOCKED,
        ExplanationOutcome.SAFETY_BLOCKED,
    }
)


@dataclass(frozen=True)
class ExplanationAttempt:
    """설명 시도 하나의 결과 - 문장과, 왜 그 문장인지.

    `text` 와 `outcome` 은 한쪽이 정해지면 다른 쪽도 정해진다: `OK` 면 문장이 있고,
    나머지 전부는 `None` 이다. 그래도 둘을 함께 들고 다니는 이유는, `None` 하나만
    돌려주던 앞의 설계가 **이유를 지우는 자리**였기 때문이다. 설명이 없는 이유를
    모르면 그 이유를 고칠 수 없다.
    """

    text: str | None
    outcome: ExplanationOutcome

    def __post_init__(self) -> None:
        if (self.text is None) is (self.outcome is ExplanationOutcome.OK):
            raise ValueError(
                "ExplanationAttempt.text must be present exactly when outcome is OK"
            )
