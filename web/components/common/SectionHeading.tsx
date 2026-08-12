import type { ReactNode } from "react";

export function SectionHeading({
  children,
  badge,
  action,
}: {
  children: ReactNode;
  badge?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="mb-2 flex items-center justify-between gap-2">
      <h2 className="flex items-center gap-1.5 text-title text-foreground">
        {children}
        {badge}
      </h2>
      {action}
    </div>
  );
}
