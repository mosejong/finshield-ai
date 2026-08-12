/** 왜 위험한지. 단정하지 않고 "정상 절차와 무엇이 다른가"로 설명한다. */
export function WhyRiskyPanel({ paragraphs }: { paragraphs: string[] }) {
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4">
      {paragraphs.map((paragraph, index) => (
        <p key={index} className="text-body text-foreground">
          {paragraph}
        </p>
      ))}
    </div>
  );
}
