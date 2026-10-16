import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo } from "react";
import { toast } from "sonner";

import AlertForm from "../components/AlertForm";
import AlertList from "../components/AlertList";
import Header from "../components/Header";
import NiftyCard from "../components/NiftyCard";
import NotificationHistory from "../components/NotificationHistory";
import PriceChart from "../components/PriceChart";
import { DEFAULT_SYMBOL } from "../config/env";
import { queryKeys, useAlerts, useQuote } from "../hooks/queries";
import { useLiveFeed } from "../hooks/useLiveFeed";
import { usePushNotifications } from "../hooks/usePushNotifications";
import { formatPrice } from "../lib/format";
import type { AlertTriggeredEvent } from "../types/api";

export default function Dashboard() {
  const queryClient = useQueryClient();

  const onAlert = useCallback(
    (event: AlertTriggeredEvent) => {
      toast.success(event.title, { description: event.body, duration: 20_000 });
      void queryClient.invalidateQueries({ queryKey: queryKeys.alerts });
      void queryClient.invalidateQueries({ queryKey: queryKeys.notifications });
      // Delivery finishes a moment after the event; refresh again to show "sent".
      setTimeout(() => void queryClient.invalidateQueries({ queryKey: queryKeys.notifications }), 3000);
    },
    [queryClient],
  );

  const connection = useLiveFeed(onAlert);
  const push = usePushNotifications();
  const quoteQuery = useQuote(DEFAULT_SYMBOL, connection === "open");
  const alertsQuery = useAlerts();
  const quote = quoteQuery.data ?? null;

  const activeAlerts = useMemo(
    () => (alertsQuery.data ?? []).filter((a) => a.status === "active" && a.symbol === DEFAULT_SYMBOL),
    [alertsQuery.data],
  );

  // Show the price in the browser tab title.
  useEffect(() => {
    if (!quote) return;
    const arrow = quote.change == null || quote.change === 0 ? "" : quote.change > 0 ? "▲" : "▼";
    document.title = `${formatPrice(quote.ltp)} ${arrow} ${quote.name}`;
  }, [quote]);

  return (
    <div className="min-h-screen">
      <Header push={push} />
      <main className="mx-auto grid max-w-7xl gap-4 px-4 py-4 lg:grid-cols-3 lg:gap-6 lg:py-6">
        <div className="flex min-w-0 flex-col gap-4 lg:col-span-2 lg:gap-6">
          <NiftyCard
            quote={quote}
            loading={quoteQuery.isPending}
            error={quoteQuery.error}
            connection={connection}
          />
          <PriceChart symbol={DEFAULT_SYMBOL} quote={quote} alerts={activeAlerts} />
        </div>
        <div className="flex min-w-0 flex-col gap-4 lg:gap-6">
          <AlertForm quote={quote} pushState={push.state} />
          <AlertList alerts={alertsQuery.data ?? []} loading={alertsQuery.isPending} quote={quote} />
          <NotificationHistory />
        </div>
      </main>
    </div>
  );
}
