import { ArrowDown, ArrowUp, Minus } from "lucide-react";
import { clsx } from "clsx";
import type { KPIValue } from "@/lib/api-client";
import {
  formatCurrency,
  formatDelta,
  formatDuration,
  formatNumber,
  formatPercent,
} from "@/lib/format";

export type KPIFormat = "number" | "percent" | "currency" | "duration";
export type DirectionOfGood = "up" | "down";

interface KPICardProps {
  label: string;
  data: KPIValue;
  format?: KPIFormat;
  directionOfGood?: DirectionOfGood;
  showDelta?: boolean;
  currency?: string;
}

function formatValue(value: number, format: KPIFormat, currency: string): string {
  switch (format) {
    case "percent":
      return formatPercent(value);
    case "currency":
      return formatCurrency(value, currency);
    case "duration":
      return formatDuration(value);
    case "number":
    default:
      return formatNumber(value);
  }
}

export function KPICard({
  label,
  data,
  format = "number",
  directionOfGood = "up",
  showDelta = true,
  currency = "USD",
}: KPICardProps) {
  const delta = data.delta_percent;
  const isZero = data.value === 0;

  let deltaContent: React.ReactNode;
  if (!showDelta) {
    deltaContent = (
      <span className="inline-flex items-center gap-1 text-xs font-medium text-slate-500">
        <Minus className="h-3 w-3" />—
      </span>
    );
  } else if (delta === null) {
    deltaContent = (
      <span className="inline-flex items-center gap-1 text-xs font-medium text-slate-500">
        <Minus className="h-3 w-3" />
        no comparison
      </span>
    );
  } else {
    const isUp = delta > 0;
    const isDown = delta < 0;
    const isFlat = !isUp && !isDown;
    const goodWhenUp = directionOfGood === "up";
    const isGood = isFlat ? false : goodWhenUp ? isUp : isDown;
    const isBad = isFlat ? false : goodWhenUp ? isDown : isUp;

    const Icon = isUp ? ArrowUp : isDown ? ArrowDown : Minus;
    deltaContent = (
      <span
        className={clsx(
          "inline-flex items-center gap-1 text-xs font-medium",
          isGood && "text-green-400",
          isBad && "text-red-400",
          isFlat && "text-slate-400",
        )}
      >
        <Icon className="h-3 w-3" />
        {formatDelta(delta)}
        <span className="text-slate-500">vs prev</span>
      </span>
    );
  }

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
      <p className="mb-1 text-xs font-semibold uppercase tracking-widest text-slate-500">
        {label}
      </p>
      <p
        className={clsx(
          "mb-2 text-3xl font-bold",
          isZero ? "text-slate-600" : "text-white",
        )}
      >
        {formatValue(data.value, format, currency)}
      </p>
      {deltaContent}
    </div>
  );
}
