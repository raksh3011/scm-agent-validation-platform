function colorFor(pct: number) {
  if (pct >= 80) return "var(--success)";
  if (pct >= 55) return "var(--medium)";
  return "var(--critical)";
}

export default function ScoreBar({ score, max = 100 }: { score: number; max?: number }) {
  const pct = Math.max(0, Math.min(100, (score / max) * 100));
  return (
    <div className="scorebar-track">
      <div className="scorebar-fill" style={{ width: `${pct}%`, background: colorFor(pct) }} />
    </div>
  );
}
