"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { NAV_ITEMS, isActivePath } from "@/components/layout/nav-items";

/** lg 이상에서만 보이는 좌측 네비게이션 */
export function SideNav() {
  const pathname = usePathname();

  return (
    <aside className="hidden w-60 shrink-0 border-r border-border lg:block">
      <div className="sticky top-0 flex h-dvh flex-col gap-6 px-4 py-6">
        <Link href="/" className="px-2">
          <span className="text-title text-primary">FinShield</span>
          <span className="mt-0.5 block text-caption text-muted-foreground">
            금융 안전 코파일럿
          </span>
        </Link>

        <nav aria-label="주요 메뉴">
          <ul className="flex flex-col gap-1">
            {NAV_ITEMS.map((item) => {
              const active = isActivePath(pathname, item.href, item.exact);
              const Icon = item.icon;

              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "flex min-h-11 items-center gap-3 rounded-md px-3 text-body transition-colors",
                      active
                        ? "bg-secondary font-semibold text-primary"
                        : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                    )}
                  >
                    <Icon aria-hidden className="size-4.5" strokeWidth={1.75} />
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
      </div>
    </aside>
  );
}
