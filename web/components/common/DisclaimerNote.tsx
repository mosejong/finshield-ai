/**
 * 서비스 한계 고지.
 *
 * CLAUDE.md 의 non-negotiable — LLM/규칙 결과가 금융·법률 판단을 대신하지 않는다.
 * 결과 화면 하단에 항상 붙는다.
 */
export function DisclaimerNote({ children }: { children: string }) {
  return (
    <p className="mt-8 border-t border-border pt-4 text-caption text-muted-foreground">
      {children}
    </p>
  );
}
