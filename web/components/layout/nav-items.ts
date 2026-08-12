import { Home, ShieldCheck, Landmark, Wallet } from "lucide-react";

/**
 * 최상위 4개 영역. IA 는 docs/13-frontend-architecture.md 참고.
 * 경고·사이렌 계열 아이콘은 쓰지 않는다 (공포 유발 방지).
 */
export const NAV_ITEMS = [
  { href: "/", label: "홈", icon: Home, exact: true },
  { href: "/profile", label: "내 금융", icon: Wallet, exact: false },
  { href: "/products", label: "금융상품", icon: Landmark, exact: false },
  { href: "/check", label: "안전 확인", icon: ShieldCheck, exact: false },
] as const;

export function isActivePath(
  pathname: string,
  href: string,
  exact: boolean,
): boolean {
  return exact ? pathname === href : pathname.startsWith(href);
}
