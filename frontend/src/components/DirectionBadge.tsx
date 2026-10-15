/** Punch direction as a badge: IN green with a down arrow, OUT orange with an up arrow. The word is always shown. */
export function DirectionBadge({ value }: { value?: string | null }) {
  const v = (value || "").trim().toUpperCase();
  if (!v) return <span className="dir-none">—</span>;
  if (v === "IN") return <span className="dir-badge is-in"><span aria-hidden>↓</span>IN</span>;
  if (v === "OUT") return <span className="dir-badge is-out"><span aria-hidden>↑</span>OUT</span>;
  return <span className="dir-badge is-other">{v}</span>;
}
