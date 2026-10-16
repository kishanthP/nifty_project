import { useState } from "react";
import { toast } from "sonner";

import { useDeleteAlert, useUpdateAlert } from "../hooks/queries";
import { useNow } from "../hooks/useNow";
import { distanceToTarget } from "../lib/alerts";
import { formatDateTime, formatPrice, timeAgo } from "../lib/format";
import type { Alert, Quote } from "../types/api";
import { ArrowDownIcon, ArrowUpIcon, RefreshIcon, TrashIcon } from "./icons";

interface Props {
  alerts: Alert[];
  loading: boolean;
  quote: Quote | null;
}

type Tab = "active" | "history";

function AlertRow({ alert, quote, now }: { alert: Alert; quote: Quote | null; now: number }) {
  const deleteAlert = useDeleteAlert();
  const updateAlert = useUpdateAlert();
  const [confirming, setConfirming] = useState(false);
  const above = alert.condition === "above";
  const current = quote?.symbol === alert.symbol ? quote.ltp : null;

  const onDelete = async () => {
    if (!confirming) {
      setConfirming(true);
      setTimeout(() => setConfirming(false), 3000);
      return;
    }
    try {
      await deleteAlert.mutateAsync(alert.id);
      toast.success("Alert deleted");
    } catch (error) {
      toast.error("Couldn't delete alert", { description: (error as Error).message });
    }
  };

  const onRearm = async () => {
    try {
      await updateAlert.mutateAsync({ id: alert.id, body: { status: "active" } });
      toast.success("Alert re-armed", {
        description: `You'll be notified again when it goes ${alert.condition} ₹${formatPrice(alert.target_price)}.`,
      });
    } catch (error) {
      toast.error("Couldn't re-arm alert", { description: (error as Error).message });
    }
  };

  let detail: string;
  if (alert.status === "active") {
    detail =
      current != null
        ? `${formatPrice(distanceToTarget(alert.condition, alert.target_price, current))} pts away · set ${timeAgo(alert.created_at, now)}`
        : `Set ${timeAgo(alert.created_at, now)}`;
  } else if (alert.status === "triggered" && alert.triggered_at) {
    detail = `Hit ₹${formatPrice(alert.triggered_price)} · ${formatDateTime(alert.triggered_at)}`;
  } else if (alert.one_cancels_other) {
    detail = `Stopped: the other side was hit · ${formatDateTime(alert.updated_at)}`;
  } else {
    detail = `Cancelled · ${formatDateTime(alert.updated_at)}`;
  }

  return (
    <li className="flex items-start gap-3 py-3">
      <span
        className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
          above ? "bg-up-soft text-up" : "bg-down-soft text-down"
        }`}
        aria-hidden="true"
      >
        {above ? <ArrowUpIcon /> : <ArrowDownIcon />}
      </span>
      <div className="min-w-0 flex-1">
        <p className="font-medium tabular-nums">
          {above ? "Above" : "Below"} ₹{formatPrice(alert.target_price)}
          <span className="ml-2 text-xs font-normal text-muted">{alert.instrument_name}</span>
          {alert.group_id && (
            <span
              className="ml-2 rounded-full bg-surface-2 px-2 py-0.5 text-xs font-normal text-muted"
              title={
                alert.one_cancels_other
                  ? "Part of a High & low pair. The first side hit stops the other."
                  : "Part of a High & low pair. Each side notifies once."
              }
            >
              High &amp; low{alert.one_cancels_other ? " · first hit only" : ""}
            </span>
          )}
        </p>
        <p className="text-xs text-muted tabular-nums">{detail}</p>
        {alert.note && <p className="mt-0.5 truncate text-xs text-muted">“{alert.note}”</p>}
      </div>
      <div className="flex shrink-0 items-center gap-1">
        {alert.status !== "active" && (
          <button
            type="button"
            onClick={onRearm}
            disabled={updateAlert.isPending}
            className="rounded-md p-2 text-muted hover:bg-surface-2 hover:text-fg"
            title="Re-arm alert"
            aria-label="Re-arm alert"
          >
            <RefreshIcon />
          </button>
        )}
        <button
          type="button"
          onClick={onDelete}
          disabled={deleteAlert.isPending}
          className={`rounded-md p-2 text-sm ${
            confirming ? "bg-down-soft text-down" : "text-muted hover:bg-surface-2 hover:text-down"
          }`}
          title={confirming ? "Click again to delete" : "Delete alert"}
          aria-label={confirming ? "Confirm delete" : "Delete alert"}
        >
          {confirming ? "Delete?" : <TrashIcon />}
        </button>
      </div>
    </li>
  );
}

export default function AlertList({ alerts, loading, quote }: Props) {
  const [tab, setTab] = useState<Tab>("active");
  const now = useNow(5000);
  // Newest first; the two sides of a High & low pair stay together, high on top.
  const active = alerts
    .filter((a) => a.status === "active")
    .sort(
      (a, b) =>
        b.created_at.localeCompare(a.created_at) ||
        (a.condition === b.condition ? 0 : a.condition === "above" ? -1 : 1),
    );
  const history = alerts
    .filter((a) => a.status !== "active")
    .sort((a, b) => (b.triggered_at ?? b.updated_at).localeCompare(a.triggered_at ?? a.updated_at));
  const shown = tab === "active" ? active : history;

  return (
    <section className="card p-5" aria-labelledby="alerts-title">
      <div className="flex items-center justify-between">
        <h2 id="alerts-title" className="font-semibold">
          Your alerts
        </h2>
        <div className="flex rounded-lg bg-surface-2 p-0.5 text-sm" role="tablist">
          {(
            [
              ["active", `Active (${active.length})`],
              ["history", `History (${history.length})`],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={tab === key}
              onClick={() => setTab(key)}
              className={`rounded-md px-2.5 py-1 ${tab === key ? "bg-surface font-medium shadow-sm" : "text-muted"}`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="mt-4 space-y-2">
          <div className="h-10 animate-pulse rounded-lg bg-surface-2" />
          <div className="h-10 animate-pulse rounded-lg bg-surface-2" />
        </div>
      ) : shown.length === 0 ? (
        <p className="mt-4 text-sm text-muted">
          {tab === "active"
            ? "No active alerts. Create one above — e.g. notify me when NIFTY goes above 22,560."
            : "Triggered and stopped alerts appear here. Re-arm one to use it again."}
        </p>
      ) : (
        <ul className="mt-2 divide-y divide-line">
          {shown.map((alert) => (
            <AlertRow key={alert.id} alert={alert} quote={quote} now={now} />
          ))}
        </ul>
      )}
    </section>
  );
}
