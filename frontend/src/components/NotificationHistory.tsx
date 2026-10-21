import { useNotifications } from "../hooks/queries";
import { useNow } from "../hooks/useNow";
import { timeAgo } from "../lib/format";

const STATUS_STYLES = {
  sent: "bg-up-soft text-up",
  pending: "bg-warn-soft text-warn",
  failed: "bg-down-soft text-down",
};

export default function NotificationHistory() {
  const { data, isPending } = useNotifications();
  const now = useNow(10_000);

  return (
    <section className="card p-5" aria-labelledby="history-title">
      <h2 id="history-title" className="font-semibold">
        Recent notifications
      </h2>
      <p className="text-xs text-muted">Your latest 10. Older ones are deleted automatically.</p>
      {isPending ? (
        <div className="mt-4 h-10 animate-pulse rounded-lg bg-surface-2" />
      ) : !data || data.length === 0 ? (
        <p className="mt-3 text-sm text-muted">Nothing yet. Triggered alerts show up here.</p>
      ) : (
        <ul className="mt-2 divide-y divide-line">
          {data.map((item) => (
            <li key={item.id} className="py-3">
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm font-medium">{item.title}</p>
                <span
                  className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[item.status]}`}
                >
                  {item.status}
                </span>
              </div>
              <p className="mt-0.5 text-xs text-muted">{item.body}</p>
              <p className="mt-1 text-xs text-muted">
                {timeAgo(item.created_at, now)}
                {item.channel === "log" && " · logged only (Firebase not set up)"}
                {item.error && item.status !== "sent" && ` · ${item.error}`}
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
