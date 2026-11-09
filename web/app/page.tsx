import { BottomTabs } from "@/components/bottom-tabs";
import { EquityPanel } from "@/components/equity-panel";
import { Markets } from "@/components/markets";
import { AccountPanel, AiPanel, PositionsPanel } from "@/components/side-panels";
import { StatusBar } from "@/components/status-bar";
import { getDashboardData } from "@/lib/data";

export default async function Page() {
  const data = await getDashboardData();
  const state = data.resumen?.estado ?? null;
  const live = data.resumen?.vivo ?? null;

  return (
    <div className="flex min-h-screen flex-col">
      <StatusBar state={state} updated={data.actualizado} />

      {/* Paneles pegados: el fondo asoma como líneas de 1px entre ellos. */}
      <main className="grid flex-1 grid-cols-[minmax(0,1fr)] gap-px bg-line lg:grid-cols-[260px_minmax(0,1fr)_320px]">
        <div className="flex min-w-0 flex-col gap-px bg-line [&>*:last-child]:flex-1">
          <Markets markets={data.resumen?.mercados ?? []} />
          <AccountPanel live={live} state={state} />
        </div>

        {/* En celular el capital va primero. */}
        <div className="order-first flex min-w-0 flex-col gap-px bg-line lg:order-none [&>*:last-child]:flex-1">
          <EquityPanel live={live} backtestIs={data.backtest_is} backtestOos={data.backtest_oos} />
          <BottomTabs live={live} backtestIs={data.backtest_is} backtestOos={data.backtest_oos} />
        </div>

        <div className="flex min-w-0 flex-col gap-px bg-line [&>*:last-child]:flex-1">
          <PositionsPanel live={live} />
          <AiPanel ai={data.ia} />
        </div>
      </main>

      <footer className="flex flex-wrap justify-between gap-2 border-t border-line bg-panel px-3 py-1.5 text-[11px] text-ink-faint">
        <span>Dinero de prueba. No es consejo de inversión.</span>
        <a href="https://github.com/Ang3lRamos/a2tradingbot" className="hover:text-ink">github.com/Ang3lRamos/a2tradingbot</a>
      </footer>
    </div>
  );
}
