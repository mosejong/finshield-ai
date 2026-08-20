import type {
  DepositCheck,
  DepositRatioBand,
  LeaseStage,
} from "@/lib/api/contracts";
import { MAX_KRW } from "@/lib/api/contracts";

/**
 * 전세보증금 점검의 표현 레이어.
 *
 * 위험 판정, 부채비율, 대항력 발생일은 전부 백엔드가 낸다. 여기에는 라벨과
 * 입력 단위 변환만 있다. 구간을 다시 나누거나 금액을 비교하지 않는다.
 */

/**
 * 단계 라벨은 백엔드 `app/services/housing_deposit.py` 의 `STAGE_LABELS` 와
 * 같은 문자열을 쓴다. 응답 요약문이 "잔금 지급·입주 단계입니다" 라고 말하는데
 * 폼에서 고른 항목 이름이 다르면 사용자는 다른 것을 고른 줄 안다.
 */
export const LEASE_STAGE_OPTIONS: ReadonlyArray<{
  value: LeaseStage;
  label: string;
  description: string;
}> = [
  {
    value: "before_contract",
    label: "계약 전",
    description: "집을 보고 있거나 계약을 앞두고 있습니다",
  },
  {
    value: "contract_signed",
    label: "계약 체결 후 잔금 전",
    description: "계약금은 냈고 잔금은 아직 남았습니다",
  },
  {
    value: "balance_paid",
    label: "잔금 지급·입주",
    description: "잔금을 치르고 들어갔습니다",
  },
  {
    value: "moved_in",
    label: "전입신고·확정일자 이후",
    description: "입주 절차를 마치고 지내는 중입니다",
  },
  {
    value: "lease_ending",
    label: "계약 종료 예정",
    description: "계약이 곧 끝나거나 나갈 예정입니다",
  },
  {
    value: "deposit_unreturned",
    label: "보증금 미반환",
    description: "계약이 끝났는데 보증금을 돌려받지 못했습니다",
  },
];

/**
 * 문구는 사용자를 탓하지 않는 평서문으로 쓴다. 하지 않은 확인이 곧 위험 신호가
 * 되지만, 그것을 알리는 방식이 비난일 필요는 없다.
 */
export const DEPOSIT_CHECK_OPTIONS: ReadonlyArray<{
  value: DepositCheck;
  label: string;
  description: string;
}> = [
  {
    value: "registry_checked",
    label: "등기부등본을 확인했습니다",
    description: "소유자와 근저당권·압류 여부를 직접 봤습니다",
  },
  {
    value: "owner_identity_verified",
    label: "임대인이 등기부상 소유자인지 확인했습니다",
    description: "계약 상대와 등기부의 소유자가 같은 사람인지 봤습니다",
  },
  {
    value: "move_in_reported",
    label: "전입신고를 마쳤습니다",
    description: "주민센터나 정부24에서 신고를 끝냈습니다",
  },
  {
    value: "confirmed_date_obtained",
    label: "확정일자를 받았습니다",
    description: "계약서에 확정일자 도장을 받았습니다",
  },
  {
    value: "deposit_guarantee_joined",
    label: "전세보증금 반환보증에 가입했습니다",
    description: "HUG 등 보증기관의 반환보증에 들었습니다",
  },
];

/**
 * 구간 이름.
 *
 * "안전" 이라는 말을 쓰지 않는다. 부채비율이 낮다는 것과 그 계약이 안전하다는
 * 것은 다른 말이고, 이 서비스는 뒤쪽을 말할 수 없다.
 */
const RATIO_BAND_LABEL: Record<DepositRatioBand, string> = {
  unknown: "확인 전",
  low: "낮은 편",
  elevated: "높은 편",
  high: "매우 높은 편",
};

export function ratioBandLabel(band: DepositRatioBand): string {
  return RATIO_BAND_LABEL[band];
}

/** 구간별 색. 위험색은 텍스트에만 쓰고 배경을 붉게 덮지 않는다. */
const RATIO_BAND_TEXT: Record<DepositRatioBand, string> = {
  unknown: "text-muted-foreground",
  low: "text-risk-low",
  elevated: "text-risk-medium",
  high: "text-risk-high",
};

export function ratioBandTextClass(band: DepositRatioBand): string {
  return RATIO_BAND_TEXT[band];
}

/**
 * 만원 단위 입력을 원으로 바꾼다.
 *
 * 금융 계산이 아니라 단위 변환이다. 이자·상환액·적격성처럼 판단이 걸린 계산은
 * 여전히 백엔드만 한다. 사회초년생에게 `200000000` 을 세어 넣게 하는 것보다
 * `20000만원` 을 받는 편이 오타가 적다.
 *
 * 빈 값은 0 이 아니라 `null` 이다. "모른다" 와 "0원" 을 같은 값으로 보내면
 * 백엔드가 모르는 값을 0 으로 채우지 않으려고 만든 구분이 화면에서 무너진다.
 */
export function manwonToKrw(raw: string): number | null {
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  if (!/^\d+$/.test(trimmed)) return null;

  const krw = Number(trimmed) * 10_000;
  if (!Number.isSafeInteger(krw) || krw > MAX_KRW) return null;
  return krw;
}

/** 입력이 비어 있지 않은데 숫자로 읽히지 않는 경우를 화면이 구분해야 한다. */
export function isBlankAmount(raw: string): boolean {
  return raw.trim() === "";
}
