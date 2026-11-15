# Dashboard de tradebot

Next.js 16 (App Router, Cache Components, Server Actions) + Tailwind CSS v4 + Recharts + lightweight-charts.

- **Datos del bot:** lee la tabla `dashboard_snapshots` de Supabase con un usuario de solo lectura. Los datos los publica el bot (`python -m tradebot.publish`) después de cada ciclo.
- **Precios en vivo:** velas y tickers públicos de Binance, pedidos desde el navegador del visitante (sin claves). Los indicadores (EMA, RSI, canal) se calculan ahí mismo con las fórmulas del bot (`lib/indicators.ts`).
- **Panel de control:** server actions (`app/actions.ts`) que verifican la sesión y dejan órdenes pendientes en la tabla `commands`; el bot las ejecuta.

```bash
cp .env.example .env.local   # Windows: copy .env.example .env.local
npm install
npm run dev                  # http://localhost:3000
```

Las variables están explicadas en [`.env.example`](.env.example). Solo `DASHBOARD_DATABASE_URL` es obligatoria; sin las del panel de control, el dashboard es solo de lectura. La instalación completa está en el [README principal](../README.md#dashboard).

| Carpeta | Contenido |
|---|---|
| `app/` | página, layout, estilos y server actions |
| `components/` | paneles del terminal (precio, capital, posiciones, control, resultados…) |
| `lib/` | acceso a datos, sesión del panel, cliente de Binance, indicadores, formatos y tipos |

Antes de subir cambios: `npx tsc --noEmit`, `npm run lint` y `npm run build`.
