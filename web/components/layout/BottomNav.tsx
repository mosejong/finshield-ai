"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { NAV_ITEMS, isActivePath } from "@/components/layout/nav-items";

/** 모바일·태블릿 하단 네비게이션. lg 이상에서는 SideNav 로 대체된다. */
export function BottomNav() {
  const pathname = usePathname();

  return (
    <nav
      aria-label="주요 메뉴"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-card pb-[env(safe-area-inset-bottom)] lg:hidden"
    >
      <ul className="mx-auto flex max-w-[560px]">
        {NAV_ITEMS.map((item) => {
          const active = isActivePath(pathname, item.href, item.exact);
          const Icon = item.icon;

          return (
            <li key={item.href} className="flex-1">
              <Link
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex min-h-[56px] flex-col items-center justify-center gap-1 text-caption transition-colors",
                  active
                    ? "text-primary font-semibold"
                    : "text-muted-foreground",
                )}
              >
                <Icon
                  aria-hidden
                  className="size-5"
                  strokeWidth={active ? 2.25 : 1.75}
                />
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
