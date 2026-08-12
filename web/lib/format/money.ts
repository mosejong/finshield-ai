/**
 * 금액 표시 전용. 계산은 하지 않는다.
 * 이자·상환액·적격성 같은 금융 계산은 전부 백엔드 몫이다.
 */

const KRW = new Intl.NumberFormat("ko-KR");

/** 2800000 → "2,800,000원" */
export function formatWon(amount: number): string {
  return `${KRW.format(amount)}원`;
}

/** 2800000 → "280만 원" — 요약 자리에서만 쓴다 */
export function formatWonShort(amount: number): string {
  if (amount >= 100_000_000) {
    const eok = amount / 100_000_000;
    return `${Number.isInteger(eok) ? eok : eok.toFixed(1)}억 원`;
  }
  if (amount >= 10_000) {
    const man = Math.round(amount / 10_000);
    return `${KRW.format(man)}만 원`;
  }
  return formatWon(amount);
}
