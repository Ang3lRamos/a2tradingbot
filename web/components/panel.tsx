import type { ReactNode } from "react";

/** Panel del terminal: encabezado pequeño en mayúsculas, contenido sin márgenes extra. */
export function Panel({
  title,
  aside,
  children,
  className = "",
}: {
  title: string;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`flex min-w-0 flex-col bg-panel ${className}`}>
      <header className="flex h-8 shrink-0 items-center justify-between border-b border-line px-3">
        <h2 className="text-[11px] font-medium uppercase tracking-[0.08em] text-ink-muted">{title}</h2>
        {aside ? <div className="text-[11px] text-ink-faint">{aside}</div> : null}
      </header>
      <div className="min-h-0 flex-1">{children}</div>
    </section>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="px-3 py-6 text-center text-ink-faint">{children}</p>;
}

/** Celda de métrica: etiqueta arriba, cifra grande abajo. */
export function Stat({ label, value, sub, valueClass = "" }: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  valueClass?: string;
}) {
  return (
    <div className="min-w-0 px-3 py-2">
      <div className="truncate text-[11px] text-ink-muted">{label}</div>
      <div className={`num truncate text-[17px] font-medium leading-6 ${valueClass}`}>{value}</div>
      {sub ? <div className="num text-[11px] leading-4 text-ink-faint">{sub}</div> : null}
    </div>
  );
}
