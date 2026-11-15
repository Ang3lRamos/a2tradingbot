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
  /** Multiplicador ajustable desde el dashboard; 1 = la estrategia tal como se probó. */
  agresividad?: { rupturas: number; tendencia: number };
};

export type Market = {
  simbolo: string;
  precio: number;
  ts: string;
  cambio_24h: number | null;
  serie_24h: number[];
  /** Distancia al stop que usaría el bot (1,5 ATR de 4h), en % del precio. */
  stop_sugerido_pct?: number | null;
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
  /** Distancia inicial al stop en precio (1 R por unidad). */
  riesgo?: number | null;
  tamano_ia: number;
  estado: "open" | "closed";
  motivo_salida: string | null;
  abierta: string;
  cerrada: string | null;
  /** "manual" = abierta desde el dashboard; no cuenta en las métricas de la estrategia. */
  origen?: "bot" | "manual";
  agresividad?: number;
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

export type TrendWeight = { simbolo: string; cantidad: number; valor: number; peso: number };

export type TrendTrade = {
  fecha: string; simbolo: string; cantidad: number; precio: number; costo: number;
  peso_antes: number; peso_despues: number;
};

/** Bot de tendencia largo/corto en cuenta virtual: rebalancea a diario, sin órdenes en el exchange. */
export type Trend = {
  instancia: string;
  capital_inicial: number;
  capital_actual: number;
  ultimo_dia: string | null;
  curva: CurvePoint[];
  metricas_bot: Metrics | null;
  metricas_btc: Metrics | null;
  dias_en_papel: number;
  pesos: TrendWeight[];
  operaciones: TrendTrade[];
};

export type Summary = { estado: BotState; mercados: Market[]; vivo: Live; tendencia?: Trend | null };

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

export type ProjectionPoint = { t: string; p10: number; p50: number; p90: number };

/** Banda esperable según el backtest (bootstrap por bloques), desde el inicio de cada cuenta. */
export type Projection = { inicio: string; capital_inicial: number; fuente: string; puntos: ProjectionPoint[] };

export type Projections = { rupturas: Projection | null; tendencia: Projection | null };

export type CommandStatus = "pendiente" | "ejecutando" | "hecha" | "rechazada" | "error";

export type Command = {
  id: number;
  kind: "agresividad" | "abrir" | "cerrar";
  payload: Record<string, unknown>;
  status: CommandStatus;
  result: string | null;
  created_at: string;
};

/** Lo que ve el panel de control. `configured`: el despliegue tiene contraseña y usuario operador. */
export type ControlState =
  | { authed: false; configured: boolean }
  | { authed: true; configured: true; commands: Command[] };

export type ActionResult = { ok: true } | { ok: false; error: string };

export type DashboardData = {
  resumen: Summary | null;
  ia: Ai | null;
  backtest_is: Backtest | null;
  backtest_oos: Backtest | null;
  proyeccion: Projections | null;
  actualizado: string | null;
  /** Problema de configuración o conexión, para mostrar en pantalla en vez de fallar. */
  error: string | null;
};
