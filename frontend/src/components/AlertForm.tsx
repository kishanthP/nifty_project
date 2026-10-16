import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { DEFAULT_SYMBOL } from "../config/env";
import { useCreateAlert, useCreateRangeAlert } from "../hooks/queries";
import type { PushState } from "../hooks/usePushNotifications";
import {
  describeAlert,
  describeRange,
  distanceToTarget,
  inferCondition,
  isConditionMet,
  isFarFromPrice,
  parsePriceInput,
  rangeProblem,
  roundPrice,
} from "../lib/alerts";
import { formatPrice } from "../lib/format";
import type { AlertCondition, Quote } from "../types/api";
import { ArrowDownIcon, ArrowUpIcon } from "./icons";

type Mode = "single" | "range";

const SINGLE_STEPS = [-50, -10, 10, 50];
const HIGH_STEPS = [10, 25, 50];
const LOW_STEPS = [-10, -25, -50];

interface Props {
  quote: Quote | null;
  pushState: PushState;
}

function PriceField(props: {
  id: string;
  label: string;
  value: string;
  placeholder: string;
  onChange: (value: string) => void;
}) {
  const invalid = props.value !== "" && !(parsePriceInput(props.value) > 0);
  return (
    <div>
      <label htmlFor={props.id} className="mb-1 block text-sm font-medium">
        {props.label}
      </label>
      <div className="flex items-center rounded-lg border border-line bg-surface-2 focus-within:border-accent">
        <span className="pl-3 text-muted">₹</span>
        <input
          id={props.id}
          inputMode="decimal"
          autoComplete="off"
          value={props.value}
          onChange={(event) => props.onChange(event.target.value)}
          placeholder={props.placeholder}
          className="w-full bg-transparent px-2 py-2 tabular-nums outline-none"
        />
      </div>
      {invalid && <p className="mt-1 text-xs text-down">Enter a price like 22560 or 22560.50</p>}
    </div>
  );
}

function QuickPicks(props: { steps: number[]; disabled: boolean; label: string; onPick: (step: number) => void }) {
  return (
    <div className="flex gap-2" role="group" aria-label={props.label}>
      {props.steps.map((step) => (
        <button
          key={step}
          type="button"
          disabled={props.disabled}
          onClick={() => props.onPick(step)}
          className="flex-1 rounded-md border border-line px-2 py-1 text-sm tabular-nums hover:bg-surface-2 disabled:opacity-50"
        >
          {step > 0 ? `+${step}` : `−${Math.abs(step)}`}
        </button>
      ))}
    </div>
  );
}

export default function AlertForm({ quote, pushState }: Props) {
  const [mode, setMode] = useState<Mode>("single");
  const [note, setNote] = useState("");
  // "One price"
  const [input, setInput] = useState("");
  const [manualCondition, setManualCondition] = useState<AlertCondition | null>(null);
  // "High & low"
  const [highInput, setHighInput] = useState("");
  const [lowInput, setLowInput] = useState("");
  const [oneCancelsOther, setOneCancelsOther] = useState(false);

  const createAlert = useCreateAlert();
  const createRange = useCreateRangeAlert();

  const name = quote?.name ?? "NIFTY 50";
  const current = quote?.ltp ?? null;
  const nearby = (step: number) => (current == null ? "" : roundPrice(Math.round(current) + step).toFixed(2));

  // One price: direction is picked from the current price unless the user chose one.
  const target = parsePriceInput(input);
  const validTarget = Number.isFinite(target) && target > 0;
  const condition = manualCondition ?? (current != null ? inferCondition(target, current) : null);
  const alreadyMet =
    condition != null && current != null && validTarget && isConditionMet(condition, target, current);

  // High & low
  const high = parsePriceInput(highInput);
  const low = parsePriceInput(lowInput);
  const validRange = high > 0 && low > 0;
  const rangeError = validRange ? rangeProblem(name, high, low, current) : null;
  const rangeFar =
    validRange && current != null && (isFarFromPrice(high, current) || isFarFromPrice(low, current));

  const pending = createAlert.isPending || createRange.isPending;
  const canSubmit =
    !pending &&
    (mode === "single"
      ? validTarget && condition != null && !alreadyMet
      : validRange && rangeError == null);

  const switchMode = (next: Mode) => {
    setMode(next);
    // Pre-fill a range around the price, e.g. 22,560 / 22,540 when NIFTY is at 22,550.
    if (next === "range" && current != null && !highInput && !lowInput) {
      setHighInput(nearby(10));
      setLowInput(nearby(-10));
    }
  };

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!canSubmit) return;
    const trimmedNote = note.trim() || undefined;
    try {
      if (mode === "single" && condition != null) {
        await createAlert.mutateAsync({ symbol: DEFAULT_SYMBOL, target_price: target, condition, note: trimmedNote });
        toast.success("Alert created", { description: describeAlert(name, condition, target) });
        setInput("");
        setManualCondition(null);
      } else {
        await createRange.mutateAsync({
          symbol: DEFAULT_SYMBOL,
          high_price: high,
          low_price: low,
          one_cancels_other: oneCancelsOther,
          note: trimmedNote,
        });
        toast.success("High & low alerts created", { description: describeRange(name, high, low) });
        setHighInput("");
        setLowInput("");
      }
      setNote("");
    } catch (error) {
      toast.error("Couldn't create alert", { description: (error as Error).message });
    }
  };

  return (
    <section className="card p-5" aria-labelledby="alert-form-title">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="alert-form-title" className="font-semibold">
          Create price alert
        </h2>
        <div className="flex rounded-lg bg-surface-2 p-0.5 text-sm" role="tablist" aria-label="Alert type">
          {(
            [
              ["single", "One price"],
              ["range", "High & low"],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={mode === key}
              onClick={() => switchMode(key)}
              className={`rounded-md px-2.5 py-1 ${mode === key ? "bg-surface font-medium shadow-sm" : "text-muted"}`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <p className="mt-1 text-sm text-muted">
        {current != null ? (
          <>
            {name} is at <span className="font-medium text-fg tabular-nums">₹{formatPrice(current)}</span>
          </>
        ) : (
          "Waiting for the live price…"
        )}
      </p>

      <form onSubmit={onSubmit} className="mt-4 space-y-3">
        {mode === "single" ? (
          <>
            <PriceField
              id="target-price"
              label="Target price"
              value={input}
              placeholder={nearby(10) || "22560.00"}
              onChange={(value) => {
                setInput(value);
                setManualCondition(null);
              }}
            />
            <QuickPicks
              steps={SINGLE_STEPS}
              disabled={current == null}
              label="Quick pick relative to current price"
              onPick={(step) => {
                setInput(nearby(step));
                setManualCondition(null);
              }}
            />
            <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="Condition">
              {(["above", "below"] as const).map((option) => {
                const selected = condition === option;
                const color =
                  option === "above" ? "border-up bg-up-soft text-up" : "border-down bg-down-soft text-down";
                return (
                  <button
                    key={option}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    onClick={() => setManualCondition(option)}
                    className={`flex items-center justify-center gap-1.5 rounded-lg border px-3 py-2 text-sm font-medium ${
                      selected ? color : "border-line text-muted hover:bg-surface-2"
                    }`}
                  >
                    {option === "above" ? <ArrowUpIcon /> : <ArrowDownIcon />}
                    Goes {option}
                  </button>
                );
              })}
            </div>
            {validTarget && condition && current != null && (
              <p className={`rounded-lg px-3 py-2 text-sm ${alreadyMet ? "bg-warn-soft text-warn" : "bg-surface-2"}`}>
                {alreadyMet
                  ? `${name} is already ${condition === "above" ? "at or above" : "at or below"} ₹${formatPrice(target)}. Choose a ${condition === "above" ? "higher" : "lower"} price or switch to "${condition === "above" ? "below" : "above"}".`
                  : `${describeAlert(name, condition, target)} — ${formatPrice(distanceToTarget(condition, target, current))} points away.`}
              </p>
            )}
            {validTarget && current != null && !alreadyMet && isFarFromPrice(target, current) && (
              <p className="text-xs text-warn">
                That's more than 10% away from the current price. Double-check the number.
              </p>
            )}
          </>
        ) : (
          <>
            <div className="space-y-2 rounded-lg border border-line p-3">
              <PriceField
                id="high-price"
                label="High — notify when it goes above"
                value={highInput}
                placeholder={nearby(10) || "22560.00"}
                onChange={setHighInput}
              />
              <QuickPicks
                steps={HIGH_STEPS}
                disabled={current == null}
                label="High price relative to current price"
                onPick={(step) => setHighInput(nearby(step))}
              />
            </div>
            <div className="space-y-2 rounded-lg border border-line p-3">
              <PriceField
                id="low-price"
                label="Low — notify when it goes below"
                value={lowInput}
                placeholder={nearby(-10) || "22540.00"}
                onChange={setLowInput}
              />
              <QuickPicks
                steps={LOW_STEPS}
                disabled={current == null}
                label="Low price relative to current price"
                onPick={(step) => setLowInput(nearby(step))}
              />
            </div>
            {validRange && (
              <p className={`rounded-lg px-3 py-2 text-sm ${rangeError ? "bg-warn-soft text-warn" : "bg-surface-2"}`}>
                {rangeError ??
                  (current != null
                    ? `${describeRange(name, high, low)} — ${formatPrice(high - current)} points up or ${formatPrice(current - low)} points down.`
                    : `${describeRange(name, high, low)}.`)}
              </p>
            )}
            {rangeFar && !rangeError && (
              <p className="text-xs text-warn">
                One of these prices is more than 10% away from the current price. Double-check the numbers.
              </p>
            )}
            <label className="flex cursor-pointer items-start gap-2 text-sm">
              <input
                type="checkbox"
                checked={oneCancelsOther}
                onChange={(event) => setOneCancelsOther(event.target.checked)}
                className="mt-0.5 h-4 w-4 accent-[var(--accent)]"
              />
              <span>
                Stop the other alert when one is hit
                <span className="block text-xs text-muted">
                  {oneCancelsOther
                    ? "You'll get only the first breakout, up or down."
                    : "Both stay active: you can be notified for the high and later for the low."}
                </span>
              </span>
            </label>
          </>
        )}

        <input
          aria-label="Note (optional)"
          value={note}
          maxLength={200}
          onChange={(event) => setNote(event.target.value)}
          placeholder="Note (optional), e.g. book profit"
          className="w-full rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm outline-none focus:border-accent"
        />

        <button
          type="submit"
          disabled={!canSubmit}
          className="w-full rounded-lg bg-accent px-4 py-2.5 font-medium text-accent-fg hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {pending ? "Creating…" : mode === "single" ? "Create alert" : "Create high & low alerts"}
        </button>

        {pushState === "off" && (
          <p className="text-xs text-muted">
            Tip: turn on notifications (top right) to get alerts even when this tab is closed.
          </p>
        )}
      </form>
    </section>
  );
}
