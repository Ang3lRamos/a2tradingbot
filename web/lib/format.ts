// Formatos numéricos. Siempre con signo explícito en retornos y P&L: la dirección no depende del color.

const MINUS = "−";

export function pct(value: number | null | undefined, digits = 2, signed = true): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const text = Math.abs(value * 100).toFixed(digits) + "%";
  if (!signed) return (value < 0 ? MINUS : "") + text;
  return (value > 0 ? "+" : value < 0 ? MINUS : "") + text;
}

export function num(value: number | null | undefined, digits = 2, signed = false): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const text = Math.abs(value).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  if (value < 0) return MINUS + text;
  return (signed && value > 0 ? "+" : "") + text;
}

export function price(value: number): string {
  const digits = value >= 1000 ? 1 : value >= 1 ? 2 : 4;
  return num(value, digits);
}

/** Clase de color por dirección; neutro si es cero o no hay dato. */
export function tone(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value) || value === 0) return "text-ink-muted";
  return value > 0 ? "text-up" : "text-down";
}

export function ago(minutes: number | null | undefined): string {
  if (minutes == null) return "sin ciclos";
  if (minutes < 1) return "hace segundos";
  if (minutes < 60) return `hace ${Math.round(minutes)} min`;
  const hours = minutes / 60;
  return hours < 48 ? `hace ${hours.toFixed(1)} h` : `hace ${Math.round(hours / 24)} días`;
}

export function utc(iso: string | null | undefined, withDate = true): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  const time = `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
  return withDate ? `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${time}` : time;
}
