"""근거 밖 주장 검사.

`validation.py` 는 오래 **연락처와 주소만** 근거에 대조했다. 나머지 — 기관 이름,
법령, 기한, 비율, 결과 약속 — 은 아무도 보지 않았고, 그 사실은 문서에도 적혀
있었다("이것은 사실 검증기가 아니다"). 2026-08-27 에 근거에 없는 것을 지어낸 문장
18개를 넣어 봤더니 **18개가 모두 통과했다.**

`CLAUDE.md` 비협상 조항은 "products, rates, eligibility, laws, institutions,
official guidance 를 지어내지 않는다" 이다. 출력 쪽에서 그것을 강제하는 코드가
없었다는 뜻이다.

**정상 문장을 먼저 놓는다.** 이 저장소가 검사를 넓힐 때마다 지키는 순서다.
검사가 잡는 것보다 검사가 부수는 것이 많으면 그 검사는 손해이고, 그 값을 나중에
재면 이미 늦다. 아래 `LEGITIMATE_OUTPUTS` 가 이 회차가 치른 값이고, 지어낸
문장 목록은 그다음이다.
"""

from __future__ import annotations

import pytest

from app.services.llm.outcomes import REJECTION_OUTCOMES, ExplanationOutcome
from app.services.llm.validation import LlmOutputRejected, validate_explanation

MAX_CHARS = 600

# 실제 `medium`·`high` 응답에서 나오는 모양의 근거. 행동 제목은 `policy.py` 의
# 문구를 그대로 옮겼고, 출처 두 줄은 `official_sources.json` 의 다섯 기관 중
# 둘이다. **여기 없는 기관은 카탈로그에 없거나, 이 사건에 딸려 오지 않은 것이다.**
GROUNDED = "\n".join(
    [
        "- 기관을 사칭하는 표현",
        "- 송금을 요구하는 표현",
        "- (1순위) 상대방과의 연락을 중단하세요 — 추가 지시를 따르기 전에 대화를"
        " 멈추면 피해 확대 가능성을 낮출 수 있습니다.",
        "- (2순위) 공식 대표번호로 사실을 확인하세요 — 메시지에 적힌 연락처가"
        " 아니라 해당 기관의 공식 채널을 직접 찾아 확인하세요.",
        "- (3순위) 보이스피싱 통합신고대응센터 1394에 상담하세요 — 링크 클릭,"
        " 정보 제공, 악성 앱 설치 또는 송금 상황의 대응 절차를 안내받을 수 있습니다.",
        "- 금융보안원: 보이스피싱 대응 안내",
        "- 경찰청: 사이버범죄 신고시스템",
    ]
)

# 사용자가 붙여넣은 문자. 압박 기한과 비율과 금액과 **사기범의 번호**가 들어 있다.
# 네 가지가 한 문자열 안에 같이 있는 것이 중요하다 - 앞의 셋은 설명이 되읽어야
# 하고, 마지막 하나는 절대 되읽으면 안 된다.
MESSAGE = (
    "[국세청] 미납 세금이 확인되었습니다. 24시간 이내에 처리하지 않으면 압류가 "
    "진행됩니다. 350만 원을 아래 계좌로 납부하시고, 처리율 100퍼센트 보장되는 "
    "담당자 02-9999-8888 로 연락 주십시오."
)


def _check(output: str, *, grounded: str = GROUNDED, message: str = MESSAGE) -> str:
    return validate_explanation(
        output,
        grounded_text=grounded,
        message_text=message,
        max_chars=MAX_CHARS,
        risk_level="medium",
    )


# --- 값: 살아남아야 하는 문장 ----------------------------------------------

LEGITIMATE_OUTPUTS = [
    # 근거 세 칸을 그대로 풀어 쓴 문장들. 이 계층이 하라고 만들어진 일이다.
    "받으신 문자에는 기관을 사칭하는 표현과 송금을 요구하는 표현이 함께 있습니다.",
    "상대방과의 연락을 먼저 중단하시고, 추가 지시를 따르지 마세요.",
    "메시지에 적힌 연락처가 아니라 해당 기관의 공식 대표번호로 직접 확인하시는 것이 안전합니다.",
    "보이스피싱 통합신고대응센터에 상담하시면 대응 절차를 안내받을 수 있습니다.",
    "1순위로 연락을 중단하고, 2순위로 공식 채널을 통해 확인하세요.",
    "공식 창구를 통해 확인하기 전까지는 어떤 정보도 제공하지 마세요.",
    # 근거에 있는 기관을 부르는 문장. **표기가 다르다** - 근거는
    # "- 경찰청: 사이버범죄 신고시스템" 이고 문장은 "경찰청 사이버범죄 신고시스템"
    # 이다. 설계 측정에서 유일하게 죽었던 문장이고, 죽은 이유는 규칙이 아니라
    # 정규화가 콜론을 남겼기 때문이었다.
    "경찰청 사이버범죄 신고시스템에 신고하실 수 있습니다.",
    "금융보안원 안내에 따르면 이런 요청은 정상 절차에 없습니다.",
    # --- 기관 이름 **앞에 보통 낱말이 오는** 문장. 2026-09-04 에 늘었다. ---
    #
    # 위 두 줄과 규칙은 같은데 어순만 다르다. 그런데 이 저장소의 정상 문장 37개는
    # 전부 기관 이름을 절 맨 앞이나 쉼표 뒤에 두고 있었고, 그래서 `_ORG_PATTERN`
    # 이 앞 어절 세 개까지 함께 삼킨다는 사실을 아무 테스트도 묻지 않았다.
    # 운영 공개 URL 에 실제 사칭 문자를 넣어 보니 주 모델과 대체 모델이 **둘 다**
    # 여기서 거부됐다 — 근거에 있는 기관을 부른 문장이었는데도.
    #
    # 셋이 조용한 것은 규칙이 안전하다는 뜻이 아니라 셋이 안 물어봤다는 뜻이다.
    "필요하다면 보이스피싱 통합신고대응센터에 상담하시면 절차를 안내받을 수 있습니다.",
    "안내에 따라 금융보안원 자료를 함께 확인해 보세요.",
    "이미 신고하셨다면 경찰청 사이버범죄 신고시스템 접수 내용을 보관하세요.",
    "먼저 연락을 끊고 보이스피싱 통합신고대응센터에 상담하세요.",
    # 특정 기관을 지목하지 않고 사용자가 이미 아는 창구를 가리키는 문장.
    "거래 금융기관에 즉시 연락해 지급정지가 가능한지 문의하세요.",
    "은행 고객센터에 문의하실 때는 카드 뒷면에 적힌 번호를 이용하세요.",
    "통신사에 문의해 명의도용 여부를 확인해 보실 수 있습니다.",
    "카드사에 연락해 카드 사용을 정지할 수 있는지 확인하세요.",
    "수사기관에 신고하기 전에 이체 내역을 정리해 두세요.",
    "관계기관에 접수하실 때 문자 원문을 함께 제출하세요.",
    # 사칭인지 아닌지를 사용자가 직접 확인하게 만드는 문장.
    "원래 알고 계신 번호로 본인에게 직접 확인해 보세요.",
    "가족을 자칭하는 연락은 이전부터 쓰던 번호로 확인하시는 편이 안전합니다.",
    "지금 대화 중인 창과 문자에 적힌 번호는 확인 수단이 아닙니다.",
    "상대방이 어느 기관인지 밝히지 않았다면 찾아갈 공식 대표번호가 없습니다.",
    "이 요청은 정상적인 금융 절차에서 요구하지 않는 내용입니다.",
    "링크를 누르지 마시고, 앱이나 프로그램도 설치하지 마세요.",
    "비밀번호나 인증번호를 알려 주면 계좌와 자금에 접근할 수 있습니다.",
    "받은 돈을 다른 곳으로 보내지 마시고 먼저 금융기관에 확인하세요.",
    "대화와 거래 기록을 보존해 두시면 신고와 상담에 도움이 됩니다.",
    "이미 송금이 발생했다면 112에 신고하시는 것이 빠릅니다.",
    "은행에 방문하시기 전에 먼저 연락을 멈추시는 것이 좋습니다.",
    # --- 문자에 적힌 숫자를 되읽는 문장. 이 회차가 치른 값의 핵심이다. ---
    #
    # 사기 문자가 기한과 비율로 압박했으면 설명은 그것을 지목해야 한다. 되읽는
    # 것은 지어내는 것이 아니라 **설명해야 할 대상**이다. 근거만 허용 목록에
    # 넣었다면 아래 셋이 죽는다(`test_the_message_is_part_of_the_numeric_allowlist`).
    "문자는 24시간 이내에 처리하지 않으면 압류한다고 압박하고 있습니다.",
    "24시간 이내라는 기한을 앞세워 확인할 시간을 주지 않는 것이 이 수법의 특징입니다.",
    "처리율 100퍼센트를 보장한다는 표현은 정상 안내에서 쓰지 않습니다.",
    "350만 원을 특정 계좌로 납부하라는 요구는 정상 절차에 없습니다.",
    # --- 약속·적격성 낱말을 **인용하거나 유보하는** 문장. ---
    #
    # 같은 낱말을 쓰지만 단정하지 않는다. 종결형을 요구하는 이유가 여기 있고,
    # `_REASSURANCE_PATTERNS` 가 주어를 요구하는 것과 같은 이유다.
    "전액을 돌려받을 수 있는지는 금융회사가 판단할 사안입니다.",
    "은행이 책임을 지는지 여부는 거래 금융기관에 직접 확인하셔야 합니다.",
    "구제 대상 여부는 신고 이후 관계기관이 판단합니다.",
    "피해자로 인정되는지는 이 화면에서 알 수 없습니다.",
    "보장한다는 말이 나오면 오히려 의심하셔야 합니다.",
    "손실을 부담하겠다는 약속은 정상 절차에서 나오지 않습니다.",
    "문자 원문과 통화 기록을 함께 보존해 두세요.",
    "이미 보낸 금액이 있다면 그 내역부터 정리하세요.",
]


@pytest.mark.parametrize("output", LEGITIMATE_OUTPUTS)
def test_legitimate_explanations_survive_the_grounding_checks(output: str) -> None:
    """검사가 막으려는 것보다 더 많은 좋은 설명을 지우면 안 된다.

    41건 전부가 통과해야 한다. 하나라도 죽으면 그 규칙은 좁혀야 하고, 좁힐 수
    없으면 넣지 말아야 한다.
    """
    assert _check(output) == output


# --- 잡아야 하는 문장 -------------------------------------------------------

FABRICATED_OUTPUTS = [
    # 법령. **아래 둘은 이 근거(`GROUNDED`)에 법령이 없어서** 걸린다.
    # "조문이 필요한 경우가 없다" 는 전제로 무조건 거부하던 판이 있었고,
    # 그 판이 근거가 법령을 달고 온 사건을 죽였다 — 아래
    # `GROUNDED_WITH_LAW` 묶음이 그 값이다.
    (
        ExplanationOutcome.REJECTED_LAW_CITATION,
        "전기통신금융사기 피해 방지 특별법 제17조에 따라 즉시 지급정지를 신청하실 수 있습니다.",
    ),
    (
        ExplanationOutcome.REJECTED_LAW_CITATION,
        "예금자보호법에 따라 보이스피싱 피해액은 전액 보전됩니다.",
    ),
    # 없는 기관. 사용자가 검색해서 찾아가고, 찾아간 곳이 사기범일 수도 있다.
    (
        ExplanationOutcome.REJECTED_UNGROUNDED_ORG,
        "국가금융안전센터에 신고하시면 피해 구제 절차가 진행됩니다.",
    ),
    (
        ExplanationOutcome.REJECTED_UNGROUNDED_ORG,
        "금융범죄수사대에서 이런 유형의 문자를 집중 단속하고 있습니다.",
    ),
    (
        ExplanationOutcome.REJECTED_UNGROUNDED_ORG,
        "금융소비자보호포털에서 해당 기관의 등록 여부를 조회하실 수 있습니다.",
    ),
    (
        ExplanationOutcome.REJECTED_UNGROUNDED_ORG,
        "카카오톡 금융감독원 채널로 문의하시면 상담을 받으실 수 있습니다.",
    ),
    # 근거에 있는 기관 **이름의 뒤쪽만 빌린** 문장. 앞 어절을 떼어 보는 규칙이
    # 부분 문자열이 아니라 일치인 이유가 이 두 줄이다 — 부분 문자열로 열었다면
    # "신고시스템" 과 "통합신고대응센터" 가 근거의 이름 안에 들어 있으므로 둘 다
    # 통과했을 것이고, 사용자는 국세청이 운영하는 창구가 있다고 읽게 된다.
    (
        ExplanationOutcome.REJECTED_UNGROUNDED_ORG,
        "국세청 신고시스템에서 처리 내역을 조회하실 수 있습니다.",
    ),
    (
        ExplanationOutcome.REJECTED_UNGROUNDED_ORG,
        "국세청 통합신고대응센터로 문의하시면 확인해 드립니다.",
    ),
    # 실재하는 기관이지만 **이 사건의 근거에 딸려 오지 않은** 기관. 공식 출처
    # 카탈로그에 금융감독원이 없다는 사실이 여기서 지켜진다.
    (
        ExplanationOutcome.REJECTED_UNGROUNDED_ORG,
        "금융감독원은 이런 문자를 받으면 48시간 이내에 신고하도록 권고하고 있습니다.",
    ),
    # 숫자. 근거에도 문자에도 없다.
    (
        ExplanationOutcome.REJECTED_UNGROUNDED_NUMBER,
        "피해 신고는 사고 발생 후 72시간 이내에만 접수됩니다.",
    ),
    (
        ExplanationOutcome.REJECTED_UNGROUNDED_NUMBER,
        "지급정지는 신청 후 3영업일 안에 자동으로 해제됩니다.",
    ),
    (
        ExplanationOutcome.REJECTED_UNGROUNDED_NUMBER,
        "이 유형은 전체 신고 건수의 38퍼센트를 차지합니다.",
    ),
    (
        ExplanationOutcome.REJECTED_UNGROUNDED_NUMBER,
        "지난해 같은 수법으로 1만 2천 건의 피해가 접수됐습니다.",
    ),
    (
        ExplanationOutcome.REJECTED_UNGROUNDED_NUMBER,
        "정부 지원 서민 대출은 연 2.5퍼센트 금리로 제공됩니다.",
    ),
    # 결과 약속과 적격성 단정. 엔진이 한 적 없는 말이다.
    (
        ExplanationOutcome.REJECTED_UNGROUNDED_PROMISE,
        "은행 영업점을 방문하시면 즉시 전액 환급받으실 수 있습니다.",
    ),
    (
        ExplanationOutcome.REJECTED_UNGROUNDED_PROMISE,
        "이 경우 피해자로 인정되므로 구제 신청 자격이 있습니다.",
    ),
    (
        ExplanationOutcome.REJECTED_UNGROUNDED_PROMISE,
        "본인 과실이 없으므로 은행이 손실을 부담하게 됩니다.",
    ),
]


@pytest.mark.parametrize(("outcome", "output"), FABRICATED_OUTPUTS)
def test_fabricated_claims_are_rejected_with_their_own_reason(
    outcome: ExplanationOutcome, output: str
) -> None:
    """거부만 확인하지 않고 **사유까지** 본다.

    사유가 지표의 칸이 된다. 아무 사유로나 거부되어도 초록불이면, 규칙 하나가
    죽어도 이 파일은 그것을 알려 주지 않는다.
    """
    with pytest.raises(LlmOutputRejected) as rejected:
        _check(output)
    assert rejected.value.outcome is outcome


def test_every_new_reason_counts_as_a_rejection() -> None:
    """새 사유가 `REJECTION_OUTCOMES` 밖에 있으면 근거 이탈률에서 사라진다."""
    for outcome, _ in FABRICATED_OUTPUTS:
        assert outcome in REJECTION_OUTCOMES


# --- 잡지 못하는 것 ---------------------------------------------------------

STILL_PASSING = [
    # 실재하는 기관에 지어낸 발표를 붙인 문장. 기관 이름은 근거에 있고, 틀린
    # 것은 **그 기관이 했다고 한 말**이다. 형태로는 정상 문장과 구분되지 않는다.
    "경찰청은 이 수법을 올해 최다 피해 유형으로 지정했습니다.",
    # 지어낸 상품명. `대출` 로 잡으려 하면 "대출을 권유하는 문자" 같은 정상 문장이
    # 같이 죽는다.
    "청년 안심 전환 대출로 갈아타시면 이자 부담을 줄일 수 있습니다.",
    # 지어낸 절차. 숫자도 기관도 법령도 없다.
    "통신사 대리점에서 명의도용 차단 서비스를 무료로 신청할 수 있습니다.",
    # 법률 이름을 **띄어 쓴** 문장. `_LAW_PATTERN` 의 `[가-힣]{2,}` 는 공백을
    # 넘지 못하므로 꼬리가 이름에서 떨어지면 아예 잡히지 않는다. 붙여 쓴
    # "개인정보보호법" 은 잡히고 띄어 쓴 "정보통신망 이용법" 은 안 잡힌다.
    # 꼬리만으로 잡으러 가면 방법·수법·불법이 함께 죽으므로, 지금은 이쪽을
    # 열어 두고 여기 적어 둔다.
    "정보통신망 이용법 위반으로 처벌될 수 있습니다.",
]


@pytest.mark.parametrize("output", STILL_PASSING)
def test_what_the_grounding_checks_still_do_not_catch(output: str) -> None:
    """**이것은 여전히 사실 검증기가 아니다.**

    이 테스트는 통과를 요구한다 - 즉 통과가 정상이라고 주장하는 것이 아니라,
    **무엇이 남아 있는지를 코드 안에 적어 두는 것**이다. 나중에 규칙을 더 넣어
    이 셋 중 하나가 잡히면 이 테스트가 실패하고, 그때 이 목록에서 지우면 된다.
    실패가 곧 진전인 테스트다.
    """
    assert _check(output) == output


# --- 허용 목록의 비대칭 -----------------------------------------------------


@pytest.mark.parametrize(
    "output",
    [
        "문자는 24시간 이내에 처리하지 않으면 압류한다고 압박하고 있습니다.",
        "24시간 이내라는 기한을 앞세워 확인할 시간을 주지 않는 것이 이 수법의 특징입니다.",
        "처리율 100퍼센트를 보장한다는 표현은 정상 안내에서 쓰지 않습니다.",
    ],
)
def test_the_message_is_part_of_the_numeric_allowlist(output: str) -> None:
    """숫자의 허용 목록은 근거 + 문자다. 문자를 빼면 정상 문장이 죽는다.

    두 방향을 한 테스트에서 본다. 문자가 있으면 통과하고 없으면 거부된다는 것을
    같이 보여야, 이 인자가 **왜 필수인지**가 테스트로 남는다.
    """
    assert _check(output) == output

    with pytest.raises(LlmOutputRejected) as rejected:
        _check(output, message="")
    assert rejected.value.outcome is ExplanationOutcome.REJECTED_UNGROUNDED_NUMBER


def test_the_contact_check_deliberately_ignores_the_message() -> None:
    """연락처만은 문자에 적혀 있어도 되읽으면 안 된다.

    사기범이 문자에 적어 둔 번호를 우리 화면이 다시 찍어 주면, 검증기가 그
    번호에 **정당성을 붙여 주는** 꼴이 된다. 숫자 허용 목록에 문자를 넣은 것과
    정반대 방향이고, 그 비대칭이 실수가 아니라는 것을 여기서 지킨다.
    """
    assert "02-9999-8888" in MESSAGE

    with pytest.raises(LlmOutputRejected) as rejected:
        _check("확인이 필요하시면 02-9999-8888 로 문의해 보세요.")
    assert rejected.value.outcome is ExplanationOutcome.REJECTED_INVENTED_CONTACT


def test_evidence_punctuation_does_not_hide_a_grounded_organization() -> None:
    """근거의 표기와 문장의 표기가 달라도 같은 기관이면 같은 기관이다.

    근거 줄은 목록 기호와 콜론을 달고 온다. 공백만 지우던 첫 판이 실재하는 공식
    창구를 안내한 문장을 거부했고, 이 검사에서 나온 유일한 오거부였다.
    """
    assert "- 경찰청: 사이버범죄 신고시스템" in GROUNDED
    assert _check("경찰청 사이버범죄 신고시스템에 신고하실 수 있습니다.")

    with pytest.raises(LlmOutputRejected):
        _check(
            "경찰청 사이버범죄 신고시스템에 신고하실 수 있습니다.",
            grounded="- 송금을 요구하는 표현",
        )


# --- 근거가 법령을 달고 온 사건 ---------------------------------------------
#
# 실제 응답 모양이다. 계좌·인증 접근권을 넘긴 사건에 엔진이 붙이는 출처 줄이고,
# `build_grounded_text` 가 이 줄을 그대로 프롬프트에 넣는다. 즉 **모델은 이
# 법령을 읽고 답한다.** 무조건 거부하던 판은 그 답을 거부했다.

GROUNDED_WITH_LAW = "\n".join(
    [
        "- 인증정보 요구",
        "- (1순위) 인증정보와 금융 접근수단을 공유하지 마세요 — 비밀번호, OTP,"
        " 통장, 카드를 넘기면 계좌와 자금에 접근할 수 있습니다.",
        "- 경찰청: 보이스피싱 통합신고대응센터 1394 안내",
        "- 국가법령정보센터: 전자금융거래법 제6조 접근매체의 선정과 사용 및 관리",
    ]
)


@pytest.mark.parametrize(
    "output",
    [
        # 근거가 준 법률 이름과 조문 번호를 그대로 되읽는다.
        "전자금융거래법 제6조는 접근매체를 남에게 넘기지 않도록 정하고 있습니다.",
        "비밀번호와 OTP 를 넘기는 것은 전자금융거래법이 다루는 접근매체 양도입니다.",
        # 법률 이름만, 조문 번호만 되읽는 경우도 각각 통과해야 한다.
        "제6조가 말하는 접근매체에 통장과 카드가 포함됩니다.",
    ],
)
def test_a_statute_the_evidence_supplied_survives(output: str) -> None:
    """`fh-1135` 가 이것으로 죽었다 (홀드아웃 v1.3, 2026-09-04).

    주 모델과 대체 모델이 **같은 이유로** 걸렸으므로 그 사건은 설명이 아예
    없었다. 대체 모델은 다른 모델일 뿐 다른 규칙이 아니라서, 규칙이 틀리면
    둘을 세워 둔 것이 아무 도움이 되지 않는다.
    """
    assert _check(output, grounded=GROUNDED_WITH_LAW) == output


@pytest.mark.parametrize(
    "output",
    [
        # 조문 번호만 빌렸다. 법률 이름이 근거에 없다.
        "예금자보호법 제6조에 따라 피해액이 보전됩니다.",
        # 법률 이름만 빌렸다. 조문 번호가 근거에 없다.
        "전자금융거래법 제9조에 따라 금융회사가 손해를 배상합니다.",
        # 이름을 줄여 썼다. 부분 문자열 대조라 붙지 않는다.
        "전기통신금융사기특별법에 따라 지급정지를 신청할 수 있습니다.",
        # 근거에 있는 법령과 아무 상관이 없다.
        "개인정보보호법 위반으로 처벌될 수 있습니다.",
    ],
)
def test_a_statute_the_evidence_never_supplied_is_still_rejected(output: str) -> None:
    """넓힌 것은 **근거가 준 것**까지다. 빌려 쓰는 길은 열지 않았다.

    법률 이름과 조문 번호를 따로 보는 이유가 위 두 줄이다. 하나만 봤다면 둘 중
    하나는 통과했을 것이고, 사용자는 없는 조항을 근거로 읽게 된다.
    """
    with pytest.raises(LlmOutputRejected) as rejected:
        _check(output, grounded=GROUNDED_WITH_LAW)
    assert rejected.value.outcome is ExplanationOutcome.REJECTED_LAW_CITATION


def test_the_law_check_widened_and_never_narrowed() -> None:
    """근거에 법령이 없으면 예전과 똑같이 전부 거부된다.

    이 변경으로 **거부가 늘어나는 입력은 없다.** 통과하던 문장은 전부 그대로
    통과하고, 죽던 문장 중 근거가 준 법령을 되읽은 것만 살아난다. 안전 검사를
    넓힐 때 이 방향을 확인해 두지 않으면, 넓힌 값을 나중에 재게 된다.
    """
    quoting = "전자금융거래법 제6조는 접근매체를 남에게 넘기지 않도록 정하고 있습니다."

    assert _check(quoting, grounded=GROUNDED_WITH_LAW) == quoting

    with pytest.raises(LlmOutputRejected) as rejected:
        _check(quoting, grounded=GROUNDED)
    assert rejected.value.outcome is ExplanationOutcome.REJECTED_LAW_CITATION
