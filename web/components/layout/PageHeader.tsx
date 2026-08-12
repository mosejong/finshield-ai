import Link from "next/link";
import { ChevronLeft } from "lucide-react";

/** 하위 화면 상단. 화면당 display 텍스트는 하나만 쓴다. */
export function PageHeader({
  title,
  description,
  backHref,
}: {
  title: string;
  description?: string;
  backHref?: string;
}) {
  return (
    <header className="mb-6">
      {backHref ? (
        <Link
          href={backHref}
          className="-ml-2 mb-2 inline-flex min-h-11 items-center gap-1 pr-3 pl-2 text-caption text-muted-foreground transition-colors hover:text-foreground"
        >
          <ChevronLeft aria-hidden className="size-4" />
          뒤로
        </Link>
      ) : null}

      <h1 className="text-display text-foreground">{title}</h1>

      {description ? (
        <p className="mt-2 text-body text-muted-foreground">{description}</p>
      ) : null}
    </header>
  );
}
