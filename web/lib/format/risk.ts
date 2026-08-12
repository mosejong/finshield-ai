import type { RiskLevel, UserState } from "@/lib/api/contracts";

/**
 * 표현 레이어. 백엔드가 이미 판정한 값을 라벨·색 클래스로 바꾸기만 한다.
 * 여기서 위험도를 계산하거나 재판정하지 않는다.
 */

type RiskStyle = {
  label: string;
  /** 좌측 4px 바 + tint 배경. 빨강 전면 채움은 쓰지 않는다. */
  container: string;
  bar: string;
  text: string;
  dot: string;
};

const RISK_STYLES: Record<RiskLevel, RiskStyle> = {
  low: {
    label: "낮음",
    container: "bg-risk-low-bg border-risk-low-border",
    bar: "bg-risk-low",
    text: "text-risk-low",
    dot: "bg-risk-low",
  },
  medium: {
    label: "주의",
    container: "bg-risk-medium-bg border-risk-medium-border",
    bar: "bg-risk-medium",
    text: "text-risk-medium",
    dot: "bg-risk-medium",
  },
  high: {
    label: "위험",
    container: "bg-risk-high-bg border-risk-high-border",
    bar: "bg-risk-high",
    text: "text-risk-high",
    dot: "bg-risk-high",
  },
};

export function riskStyle(level: RiskLevel): RiskStyle {
  return RISK_STYLES[level];
}

/**
 * "현재 상황 위험도 ___"처럼 세기를 설명하는 자리에 붙는 라벨.
 * 여기서는 세기만 말한다.
 */
const RISK_STRENGTH_LABEL: Record<RiskLevel, string> = {
  low: "낮음",
  medium: "주의",
  high: "높음",
};

export function riskStrengthLabel(level: RiskLevel): string {
  return RISK_STRENGTH_LABEL[level];
}

/**
 * 이미 정보·자산이 넘어간 상태.
 *
 * 위험도를 다시 계산하는 것이 아니라, 사용자가 스스로 고른 선택지의 뜻을 그대로
 * 읽는 것이다("돈을 보냈어요" = 이미 벌어진 일). 화면 톤이 예방에서 수습으로 바뀐다.
 */
const RECOVERY_STATES: ReadonlySet<UserState> = new Set<UserState>([
  "shared_personal_info",
  "shared_account_access",
  "installed_app",
  "received_unknown_money",
  "transferred_money",
]);

export function isRecoveryState(state: UserState): boolean {
  return RECOVERY_STATES.has(state);
}

/** 사용자가 고르는 "이미 무엇을 했는지" 선택지 */
export const USER_STATE_OPTIONS: ReadonlyArray<{
  value: UserState;
  label: string;
  description: string;
}> = [
  {
    value: "received_only",
    label: "받기만 했어요",
    description: "아직 아무것도 하지 않았습니다",
  },
  {
    value: "clicked_link",
    label: "링크를 열었어요",
    description: "메시지에 있는 주소로 들어가 봤습니다",
  },
  {
    value: "shared_personal_info",
    label: "개인정보를 알려줬어요",
    description: "이름·연락처·주소 등을 보냈습니다",
  },
  {
    value: "shared_account_access",
    label: "계좌·카드·인증번호를 넘겼어요",
    description: "계좌번호, 체크카드, OTP 등을 전달했습니다",
  },
  {
    value: "installed_app",
    label: "앱을 설치했어요",
    description: "상대가 안내한 앱이나 파일을 설치했습니다",
  },
  {
    value: "received_unknown_money",
    label: "모르는 돈이 들어왔어요",
    description: "출처를 알 수 없는 입금이 있었습니다",
  },
  {
    value: "transferred_money",
    label: "돈을 보냈어요",
    description: "상대가 알려준 곳으로 송금했습니다",
  },
];

const ACTION_KIND_LABEL = {
  immediate: "지금 바로",
  soon: "오늘 안에",
  avoid: "하지 마세요",
} as const;

export function actionKindLabel(kind: keyof typeof ACTION_KIND_LABEL): string {
  return ACTION_KIND_LABEL[kind];
}

export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("ko-KR", {
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}
