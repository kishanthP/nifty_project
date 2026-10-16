import type { FeedBadge } from "../lib/feed";

const TONES = {
  live: "bg-up-soft text-up",
  warn: "bg-warn-soft text-warn",
  muted: "bg-surface-2 text-muted",
};

export default function StatusBadge({ badge }: { badge: FeedBadge }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${TONES[badge.tone]}`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full bg-current ${badge.tone === "live" ? "live-dot" : ""}`}
      />
      {badge.label}
    </span>
  );
}
