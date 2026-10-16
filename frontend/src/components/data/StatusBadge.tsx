type Tone = "positive" | "waiting" | "negative" | "neutral";

const TONES: Record<string, Tone> = {
  active: "positive",
  posted: "positive",
  approved: "positive",
  paid: "positive",
  sent: "positive",
  pending: "waiting",
  draft: "waiting",
  queued: "neutral",
  sending: "neutral",
  closed: "negative",
  disabled: "negative",
  reversed: "negative",
  rejected: "negative",
  failed: "negative",
  cancelled: "negative",
};

export function StatusBadge({ status, label, className }: { status: string; label?: string; className?: string }) {
  const tone = TONES[status.toLowerCase()] ?? "neutral";
  return <span className={`app-badge badge-${tone} ${className ?? ""}`}>{label ?? status}</span>;
}
