// Forma de los JSON que publica `python -m tradebot.publish` en la tabla dashboard_snapshots.

export type Metrics = {
  retorno_neto: number | null;
  max_drawdown: number | null;
  sharpe: number | null;
  sortino: number | null;
  operaciones: number;
  tasa_acierto?: number | null;
  ganancia_promedio?: number | null;
  perdida_promedio?: number | null;
  profit_factor?: number | null;
  r_promedio?: number | null;
  comisiones?: number | null;
  funding?: number | null;
};

export type CurvePoint = { t: string; bot: number; btc: number };

export type BotState = {
  instancia: string;
  variante: string;
  riesgo_por_operacion: number;
  kill_switch_pct: number;
  limite_ia_diario: number;
  ahora: string;
  modo: "operar" | "solo_cierre" | "kill_switch" | null;
  motivo?: string | null;
  ultimo_ciclo?: string | null;
  minutos_desde_ciclo?: number | null;
  activo: boolean;
  llamadas_ia_hoy?: number;
};

export type Market = {
  simbolo: string;
  precio: number;
  ts: string;
  cambio_24h: number | null;
  serie_24h: number[];
};

export type Position = {
  id: number;
  simbolo: string;
  lado: "long" | "short";
  cantidad: number;
  entrada: number;
  stop: number;
  salida: number | null;
  pnl: number | null;
  comisiones: number | null;
  tamano_ia: number;
  estado: "open" | "closed";
  motivo_salida: string | null;
  abierta: string;
  cerrada: string | null;
};

export type Alert = { fecha: string; nivel: "info" | "warning" | "critical"; mensaje: string };

export type Live = {
  curva: CurvePoint[];
  metricas_bot: Metrics | null;
  metricas_btc: Metrics | null;
  capital_actual: number | null;
  dias_en_papel: number;
  posiciones_abiertas: Position[];
  operaciones_cerradas: Position[];
  alertas: Alert[];
};

export type Summary = { estado: BotState; mercados: Market[]; vivo: Live };

export type AiSummary = {
  revisadas: number;
  habilidad: number;
  intervalo: [number, number];
  veredicto: "mejor" | "peor" | "indistinguible";
  r_sin_ia: number;
  r_con_ia: number | null;
  tamano_medio: number;
  por_decision: { decision: string; senales: number; r_medio: number; acierto: number; tamano_medio: number }[];
  tokens_entrada: number;
  tokens_salida: number;
  segundos: number;
};

export type Ai = { evaluacion: AiSummary | null; muestra: number; en_vivo: AiSummary | null };

export type Backtest = {
  periodo: "is" | "oos";
  variante: string;
  descripcion: string;
  desde: string;
  hasta: string;
  kill_switch: string | null;
  metricas_bot: Metrics;
  metricas_btc: Metrics;
  curva: CurvePoint[];
};

export type DashboardData = {
  resumen: Summary | null;
  ia: Ai | null;
  backtest_is: Backtest | null;
  backtest_oos: Backtest | null;
  actualizado: string | null;
};
