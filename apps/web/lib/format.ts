const numberFormatter = new Intl.NumberFormat("en-US");

const percentFormatter = new Intl.NumberFormat("en-US", {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

const currencyFormatters = new Map<string, Intl.NumberFormat>();

function getCurrencyFormatter(currency: string): Intl.NumberFormat {
  const key = currency.toUpperCase();
  let f = currencyFormatters.get(key);
  if (!f) {
    f = new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: key,
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    });
    currencyFormatters.set(key, f);
  }
  return f;
}

export function formatNumber(value: number): string {
  return numberFormatter.format(Math.round(value));
}

export function formatPercent(value: number): string {
  // Backend returns engagement_rate / bounce_rate as 0..1 fractions.
  return percentFormatter.format(value);
}

export function formatCurrency(value: number, currency = "USD"): string {
  return getCurrencyFormatter(currency).format(value);
}

export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

export function formatDelta(deltaPercent: number): string {
  const sign = deltaPercent > 0 ? "+" : deltaPercent < 0 ? "-" : "";
  return `${sign}${Math.abs(deltaPercent).toFixed(1)}%`;
}
