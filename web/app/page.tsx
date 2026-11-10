import { Suspense } from "react";

import { BottomTabs } from "@/components/bottom-tabs";
import { EquityPanel } from "@/components/equity-panel";
import { LiveMarketProvider } from "@/components/live-market";
import { Markets } from "@/components/markets";
import { PositionsPanel } from "@/components/positions-panel";
import { PricePanel } from "@/components/price-panel";
import { AccountPanel, AiPanel } from "@/components/side-panels";
import { StatusBar } from "@/components/status-bar";
import { TrendPanel } from "@/components/trend-panel";
import { getDashboardData } from "@/lib/data";

export default function Page() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-bg" />}>
      <Dashboard />
    </Suspense>
  );
}

async function Dashboard() {
  const data = await getDashboardData();
  const state = data.resumen?.estado ?? null;
  const live = data.resumen?.vivo ?? null;
  const markets = data.resumen?.mercados ?? [];
  const trend = data.resumen?.tendencia ?? null;
  const symbols = markets.length ? markets.map((m) => m.simbolo) : ["BTC", "ETH", "SOL"];

  return (
    <LiveMarketProvider symbols={symbols}>
      <div className="flex min-h-screen flex-col">
        <StatusBar state={state} updated={data.actualizado} />

        {data.error ? (
          <div role="alert" className="border-b border-line bg-panel-raised px-3 py-2 text-[12px] text-warn">
            ⚠ {data.error}
          </div>
        ) : null}

        {/* Paneles pegados: el fondo asoma como líneas de 1px entre ellos. */}
        <main className="grid flex-1 grid-cols-[minmax(0,1fr)] gap-px bg-line lg:grid-cols-[260px_minmax(0,1fr)_320px]">
          <div className="flex min-w-0 flex-col gap-px bg-line [&>*:last-child]:flex-1">
            <Markets markets={markets} />
            <AccountPanel live={live} state={state} markets={markets} />
          </div>

          {/* En celular el precio y el capital van primero. */}
          <div className="order-first flex min-w-0 flex-col gap-px bg-line lg:order-none [&>*:last-child]:flex-1">
            <PricePanel symbols={symbols} live={live} trend={trend} />
            <EquityPanel live={live} trend={trend} backtestIs={data.backtest_is} backtestOos={data.backtest_oos} />
            <BottomTabs live={live} backtestIs={data.backtest_is} backtestOos={data.backtest_oos} />
          </div>

          <div className="flex min-w-0 flex-col gap-px bg-line [&>*:last-child]:flex-1">
            <PositionsPanel live={live} trend={trend} />
            <TrendPanel trend={trend} />
            <AiPanel ai={data.ia} />
          </div>
        </main>

        <footer className="flex flex-wrap justify-between gap-2 border-t border-line bg-panel px-3 py-1.5 text-[11px] text-ink-faint">
          <span>Dinero de prueba. No es consejo de inversión.</span>
          <a href="https://github.com/Ang3lRamos/a2tradingbot" className="hover:text-ink">github.com/Ang3lRamos/a2tradingbot</a>
        </footer>
      </div>
    </LiveMarketProvider>
  );
}
