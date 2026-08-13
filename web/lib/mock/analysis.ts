import type {
  Action,
  AnalysisResult,
  RiskLevel,
  UserState,
} from "@/lib/api/contracts";
import { evidenceByIds } from "@/lib/mock/evidence";
import { isRecoveryState } from "@/lib/format/risk";

/**
 * 백엔드 없이 화면을 확인하는 mock 모드 전용 예시 데이터.
 *
 * 여기 있는 내용은 전부 `source: "mock"` 으로 표시되고 화면에 mock 배지가 붙는다.
 * live 모드의 설명·행동·근거는 Scenario Engine v0.1 응답을 사용한다.
 *
 * 주의: 백엔드 risk_engine 의 키워드 규칙을 여기에 복제하지 않는다.
 * 위험 신호 탐지와 점수 판정은 항상 백엔드 몫이다.
 */

/** 백엔드 risk_engine.py 의 신호 code 에 대응하는 설명 */
const SIGNAL_WHY: Record<string, string> = {
  urgency:
    "생각할 시간을 주지 않으려는 압박입니다. 정상적인 금융·채용 절차는 즉시 결정을 요구하지 않습니다.",
  credential:
    "인증번호와 비밀번호는 어떤 기관도 대신 받아가지 않습니다. 본인 확인 절차를 가로채려는 요구일 수 있습니다.",
  account_access:
    "계좌·체크카드·OTP를 넘기면 본인도 모르게 범죄자금이 지나가는 통로가 될 수 있습니다. 피해자가 아니라 가담자로 조사받는 상황으로 이어질 수 있습니다.",
  remote_app:
    "원격제어 앱이나 출처를 알 수 없는 설치 파일은 기기 화면·문자·금융앱 접근 권한을 통째로 넘기는 것과 같습니다.",
  money_mule:
    "받은 돈을 다시 보내달라는 요구는 자금 세탁 경로에 내 이름을 올리는 전형적인 구조입니다.",
};

export function signalWhy(code: string): string | undefined {
  return SIGNAL_WHY[code];
}

const STATE_SUMMARY: Record<UserState, string> = {
  received_only: "메시지를 받기만 했고 아직 아무것도 하지 않았습니다.",
  clicked_link: "메시지에 있는 링크를 열었습니다.",
  shared_personal_info: "이름·연락처 등 개인정보를 알려주었습니다.",
  shared_account_access:
    "계좌번호·체크카드·인증번호 등 계좌에 접근할 수 있는 수단을 넘겼습니다.",
  installed_app: "상대가 안내한 앱을 설치했습니다.",
  received_unknown_money: "출처를 알 수 없는 돈이 입금되었습니다.",
  transferred_money: "상대가 안내한 곳으로 돈을 보냈습니다.",
};

export function stateSummary(state: UserState): string {
  return STATE_SUMMARY[state];
}

export function headline(level: RiskLevel, state: UserState): string {
  if (isRecoveryState(state)) {
    return "이미 넘어간 것이 있습니다. 지금 순서대로 조치하세요";
  }
  if (level === "high") return "지금 중단해야 하는 요청입니다";
  if (level === "medium") return "확인하기 전에는 진행하지 마세요";
  return "지금 단계에서 뚜렷한 위험 신호는 보이지 않습니다";
}

export function buildWhy(
  level: RiskLevel,
  signalCodes: readonly string[],
): string[] {
  if (signalCodes.length === 0) {
    return [
      "입력한 내용에서는 계좌 요구, 인증정보 요구, 자금 전달 요구 같은 위험 신호가 감지되지 않았습니다.",
      "다만 위험 신호가 없다는 것이 안전하다는 뜻은 아닙니다. 상대가 사칭한 기관이 있다면 그 기관의 공식 대표번호로 직접 확인하세요.",
    ];
  }

  const opener =
    level === "high"
      ? "이 요청은 정상적인 금융·채용 절차에는 없는 요구를 포함하고 있습니다."
      : "이 요청에는 정상 절차인지 확인이 필요한 부분이 있습니다.";

  const details = signalCodes
    .map((code) => SIGNAL_WHY[code])
    .filter((why): why is string => Boolean(why));

  return [opener, ...details];
}

/* ------------------------------------------------------------------ */
/* 상황별 대응 행동                                                     */
/* ------------------------------------------------------------------ */

const COMMON_AVOID: Action[] = [
  {
    id: "avoid-credentials",
    title: "계좌번호·체크카드·인증번호를 보내지 마세요",
    detail:
      "정상적인 회사나 기관은 급여 지급이나 대출 심사를 이유로 계좌 접근수단을 요구하지 않습니다.",
    kind: "avoid",
    evidenceIds: [],
  },
  {
    id: "avoid-link-login",
    title: "메시지 속 링크에서 로그인하지 마세요",
    detail:
      "확인이 필요하면 링크 대신 해당 기관 앱이나 공식 홈페이지 주소를 직접 입력해 들어가세요.",
    kind: "avoid",
    evidenceIds: [],
  },
];

const KEEP_RECORDS: Action = {
  id: "keep-records",
  title: "대화 내용과 계좌 정보를 캡처해 두세요",
  detail: "신고할 때 문자·메신저 대화, 상대 연락처, 이체 내역이 증빙이 됩니다.",
  kind: "soon",
  evidenceIds: [],
};

const VERIFY_OFFICIAL: Action = {
  id: "verify-official",
  title: "상대가 말한 기관의 공식 대표번호로 직접 확인하세요",
  detail:
    "메시지에 적힌 번호로 다시 걸지 말고, 검색이나 공식 홈페이지에서 찾은 번호로 거세요.",
  kind: "soon",
  evidenceIds: [],
};

const CONSULT_1332: Action = {
  id: "consult-1332",
  title: "금융감독원 상담으로 판단을 확인하세요",
  detail: "판단이 서지 않을 때 통화로 상황을 설명하고 확인할 수 있습니다.",
  kind: "soon",
  contactPhone: "1332",
  contactLabel: "금융감독원 1332",
  evidenceIds: ["fss_1332"],
};

const STATE_ACTIONS: Record<UserState, Action[]> = {
  received_only: [...COMMON_AVOID, VERIFY_OFFICIAL, CONSULT_1332],

  clicked_link: [
    {
      id: "change-password",
      title: "링크에서 정보를 입력했다면 해당 서비스 비밀번호를 바꾸세요",
      detail: "같은 비밀번호를 쓰는 다른 서비스가 있다면 함께 바꿔야 합니다.",
      kind: "immediate",
      evidenceIds: [],
    },
    ...COMMON_AVOID,
    VERIFY_OFFICIAL,
    CONSULT_1332,
  ],

  shared_personal_info: [
    {
      id: "report-118",
      title: "개인정보 침해·스미싱 상담을 받으세요",
      detail: "어떤 정보가 넘어갔는지 정리해서 상담하면 후속 조치를 안내받습니다.",
      kind: "immediate",
      contactPhone: "118",
      contactLabel: "KISA 118",
      evidenceIds: ["kisa_118"],
    },
    {
      id: "check-msafer",
      title: "내 명의로 개통된 휴대폰이 있는지 확인하세요",
      kind: "immediate",
      evidenceIds: ["msafer"],
    },
    {
      id: "check-payinfo",
      title: "내 명의로 열린 계좌가 있는지 확인하세요",
      kind: "soon",
      evidenceIds: ["payinfo"],
    },
    KEEP_RECORDS,
    CONSULT_1332,
  ],

  shared_account_access: [
    {
      id: "bank-stop",
      title: "거래 은행에 즉시 지급정지를 요청하세요",
      detail:
        "은행 고객센터에 계좌 접근수단이 타인에게 넘어갔다고 알리고 거래 중지를 요청하세요. 가장 먼저 할 일입니다.",
      kind: "immediate",
      evidenceIds: [],
    },
    {
      id: "report-112",
      title: "경찰에 신고하세요",
      detail:
        "내 계좌가 범죄에 쓰이면 명의자도 조사 대상이 됩니다. 먼저 신고한 기록이 중요합니다.",
      kind: "immediate",
      contactPhone: "112",
      contactLabel: "경찰 112",
      evidenceIds: ["police_112"],
    },
    {
      id: "check-payinfo-urgent",
      title: "내 명의로 열린 다른 계좌가 있는지 확인하세요",
      kind: "immediate",
      evidenceIds: ["payinfo"],
    },
    {
      id: "avoid-more-accounts",
      title: "상대 요구로 계좌를 새로 만들거나 추가로 보내지 마세요",
      detail: "이미 넘어간 뒤에도 '해결해 주겠다'며 추가 요구가 이어지는 경우가 많습니다.",
      kind: "avoid",
      evidenceIds: [],
    },
    KEEP_RECORDS,
    CONSULT_1332,
  ],

  installed_app: [
    {
      id: "cut-network",
      title: "그 기기의 인터넷 연결을 끄고 설치한 앱을 삭제하세요",
      detail: "비행기 모드로 전환하면 원격 조작과 문자 가로채기를 우선 끊을 수 있습니다.",
      kind: "immediate",
      evidenceIds: [],
    },
    {
      id: "other-device-password",
      title: "다른 기기에서 금융 비밀번호를 바꾸세요",
      detail: "감염이 의심되는 기기에서 바꾸면 새 비밀번호까지 함께 넘어갈 수 있습니다.",
      kind: "immediate",
      evidenceIds: [],
    },
    {
      id: "avoid-banking-on-device",
      title: "그 기기로 금융앱에 로그인하지 마세요",
      kind: "avoid",
      evidenceIds: [],
    },
    {
      id: "report-118-app",
      title: "악성앱 설치 정황을 상담하세요",
      kind: "soon",
      contactPhone: "118",
      contactLabel: "KISA 118",
      evidenceIds: ["kisa_118"],
    },
    CONSULT_1332,
  ],

  received_unknown_money: [
    {
      id: "do-not-move-money",
      title: "그 돈을 쓰거나 다시 보내지 마세요",
      detail:
        "받은 돈을 다시 보내는 순간 자금 전달 경로에 이름이 남습니다. 계좌에 그대로 둔 채 은행에 알리세요.",
      kind: "immediate",
      evidenceIds: [],
    },
    {
      id: "bank-inquiry",
      title: "거래 은행에 입금 경위 확인을 요청하세요",
      kind: "immediate",
      evidenceIds: [],
    },
    {
      id: "report-112-money",
      title: "경찰에 신고해 기록을 남기세요",
      kind: "immediate",
      contactPhone: "112",
      contactLabel: "경찰 112",
      evidenceIds: ["police_112"],
    },
    KEEP_RECORDS,
    CONSULT_1332,
  ],

  transferred_money: [
    {
      id: "bank-stop-transfer",
      title: "받는 계좌에 대해 즉시 지급정지를 요청하세요",
      detail: "송금 직후일수록 회수 가능성이 있습니다. 은행 고객센터에 가장 먼저 연락하세요.",
      kind: "immediate",
      evidenceIds: [],
    },
    {
      id: "report-112-transfer",
      title: "경찰에 신고하세요",
      kind: "immediate",
      contactPhone: "112",
      contactLabel: "경찰 112",
      evidenceIds: ["police_112"],
    },
    {
      id: "consult-1332-transfer",
      title: "금융감독원에 피해 상담을 받으세요",
      kind: "immediate",
      contactPhone: "1332",
      contactLabel: "금융감독원 1332",
      evidenceIds: ["fss_1332"],
    },
    {
      id: "avoid-recovery-scam",
      title: "'피해금을 되찾아 준다'는 연락에 응하지 마세요",
      detail: "피해자를 다시 노리는 2차 사기가 흔합니다.",
      kind: "avoid",
      evidenceIds: [],
    },
    KEEP_RECORDS,
  ],
};

export function buildActions(state: UserState, level: RiskLevel): Action[] {
  if (level === "low" && !isRecoveryState(state)) {
    return [VERIFY_OFFICIAL, CONSULT_1332];
  }
  return STATE_ACTIONS[state];
}

export function collectEvidence(actions: readonly Action[]) {
  const ids = new Set<string>();
  for (const action of actions) {
    for (const id of action.evidenceIds) ids.add(id);
  }
  // 공식 상품정보 출처는 결과 화면에서 항상 함께 노출한다.
  return evidenceByIds([...ids]);
}

/* ------------------------------------------------------------------ */
/* 분석 서버가 꺼져 있을 때 보여주는 예시 결과                          */
/* ------------------------------------------------------------------ */

/**
 * mock 모드 전용 고정 예시.
 *
 * 입력 문구에 따라 결과가 달라지지 않는다. 백엔드 규칙 엔진을 프론트에
 * 복제하지 않기 위한 의도적인 제약이며, 화면에 예시라고 명시한다.
 */
export function demoAnalysis(id: string, state: UserState): AnalysisResult {
  const codes = ["urgency", "account_access", "money_mule"];
  const actions = buildActions(state, "high");

  return {
    id,
    createdAt: new Date().toISOString(),
    level: "high",
    headline: headline("high", state),
    headlineSource: "mock",
    signals: [
      {
        code: "urgency",
        label: "긴급한 행동 요구",
        why: SIGNAL_WHY.urgency,
        weight: 12,
        source: "mock",
      },
      {
        code: "account_access",
        label: "계좌·접근수단 요구",
        why: SIGNAL_WHY.account_access,
        weight: 35,
        source: "mock",
      },
      {
        code: "money_mule",
        label: "자금 수취·재전달 요구",
        why: SIGNAL_WHY.money_mule,
        weight: 35,
        source: "mock",
      },
    ],
    fraudTypes: ["account_access_request", "money_mule_transfer"],
    why: buildWhy("high", codes),
    whySource: "mock",
    state,
    stateSummary: stateSummary(state),
    stateSource: "mock",
    actions,
    actionsSource: "mock",
    evidence: collectEvidence(actions),
    evidenceSource: "mock",
    score: 82,
    scoreSource: "mock",
    engine: "예시 데이터 (분석 서버 미연결)",
    disclaimer:
      "분석 서버에 연결하지 않은 예시 결과입니다. 실제 위험 판정이 아닙니다.",
  };
}

/** mock 모드에서 뚜렷한 위험 신호가 없을 때의 예시 */
function demoLowAnalysis(id: string, createdAt: string): AnalysisResult {
  const actions = buildActions("received_only", "low");

  return {
    id,
    createdAt,
    level: "low",
    headline: headline("low", "received_only"),
    headlineSource: "mock",
    signals: [],
    fraudTypes: [],
    why: buildWhy("low", []),
    whySource: "mock",
    state: "received_only",
    stateSummary: stateSummary("received_only"),
    stateSource: "mock",
    actions,
    actionsSource: "mock",
    evidence: collectEvidence(actions),
    evidenceSource: "mock",
    score: 0,
    scoreSource: "mock",
    engine: "예시 데이터 (분석 서버 미연결)",
    disclaimer:
      "분석 서버에 연결하지 않은 예시 결과입니다. 실제 위험 판정이 아닙니다.",
  };
}

/**
 * 예시 id 로 열린 결과 화면.
 *
 * 분석 결과는 sessionStorage 에만 있어서 새로고침·다른 기기에서는 사라진다.
 * 그때 아무 결과나 대신 보여주면 사용자가 남의 분석을 자기 것으로 오해한다.
 * 그래서 예시 id 일 때만 예시를 돌려주고, 나머지는 null 로 "찾을 수 없음"을 알린다.
 */
export function demoAnalysisFor(id: string): AnalysisResult | null {
  const createdAt = new Date().toISOString();

  if (id === "demo-2") return demoLowAnalysis(id, createdAt);
  if (id === "demo" || id === "demo-1") {
    return { ...demoAnalysis(id, "received_only"), createdAt };
  }
  return null;
}
