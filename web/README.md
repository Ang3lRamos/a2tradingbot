# Dashboard de tradebot

Next.js 16 (App Router, Cache Components) + Tailwind + Recharts. Lee la tabla `dashboard_snapshots` de Supabase con un usuario de solo lectura; los datos los publica el bot (`python -m tradebot.publish`).

```bash
npm install
npm run dev      # http://localhost:3000
```

Variable requerida en `.env.local` (y en Vercel): `DASHBOARD_DATABASE_URL`. Ver el README principal.
