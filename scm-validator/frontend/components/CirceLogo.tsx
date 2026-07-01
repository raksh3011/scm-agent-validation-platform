// Hardcoded brand hex (not CSS variables) — these are fixed brand colors that
// shouldn't shift with the light/dark theme, and inline SVG fill/style attributes
// don't reliably resolve Tailwind v4 theme custom properties in every render path.
const CIRCE_TEAL = "#1B5E54";
const CIRCE_GOLD = "#C4A06B";
const CIRCE_INK = "#15130E";

export function CirceMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 100 100" className={className} fill="none" xmlns="http://www.w3.org/2000/svg">
      {/* thin outer ring, with visible breathing room before the thick C */}
      <circle cx="50" cy="50" r="46" stroke={CIRCE_INK} strokeWidth="2" />
      {/* thick "C" ring, opening toward the right at roughly 2 o'clock / 4 o'clock */}
      <path
        d="M 72.2 29.9 A 30 30 0 1 0 72.2 70.1"
        stroke={CIRCE_INK}
        strokeWidth="16"
        strokeLinecap="round"
      />
      {/* center teal dot */}
      <circle cx="50" cy="50" r="6" fill={CIRCE_TEAL} />
      {/* two gold dots capping the ring opening */}
      <circle cx="72.2" cy="29.9" r="9" fill={CIRCE_GOLD} />
      <circle cx="72.2" cy="70.1" r="9" fill={CIRCE_GOLD} />
    </svg>
  );
}

export function CirceWordmark({ className }: { className?: string }) {
  return (
    <span className={className}>
      <span className="font-serif" style={{ color: CIRCE_INK }}>Circe</span>
      <span className="font-serif" style={{ color: CIRCE_GOLD }}>AI</span>
    </span>
  );
}

export default function CirceLogo({ className, markClassName, wordmarkClassName }: {
  className?: string; markClassName?: string; wordmarkClassName?: string;
}) {
  return (
    <span className={className ?? "flex items-center gap-2.5"}>
      <CirceMark className={markClassName ?? "h-8 w-8"} />
      <CirceWordmark className={wordmarkClassName ?? "text-xl font-semibold tracking-tight"} />
    </span>
  );
}
