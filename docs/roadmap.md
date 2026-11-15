# Hoja de ruta

Estado a noviembre de 2026: los dos bots corren en papel desde el 9 de noviembre, con dashboard en vivo, panel de control y alertas. Lo que sigue está ordenado por prioridad.

## Meta próxima: 3 meses de paper trading (hasta mediados de febrero de 2027)

El objetivo no es ganar en papel, sino saber si las estrategias en vivo se comportan como en el backtest. Al final del periodo se decide con estos criterios, fijados ahora para no acomodarlos después:

| Criterio | Rupturas | Tendencia L/S |
|---|---|---|
| Tiempo mínimo | 3 meses | 3 meses |
| Muestra mínima | 30 operaciones cerradas del bot | — (se mide por capital) |
| Comportamiento | R promedio y acierto dentro de lo esperable según el backtest | Curva dentro de la banda 10–90% de la ruta proyectada la mayor parte del tiempo |
| Fidelidad | Stops ejecutados donde debían, sin órdenes perdidas ni duplicadas | Prueba de fidelidad del resumen mensual dentro de ±1% |
| Riesgo | Sin activar el kill switch por un error del bot | Peor caída por debajo de la del backtest (−33,6%) |
| Variedad de mercado | Haber pasado por algo distinto a una caída sostenida (rebote fuerte o semanas de lado) | Igual |

Si una estrategia cumple todo, pasa a la etapa de dinero real descrita abajo. Si no, se anota en [investigacion.md](investigacion.md) qué falló y no se ajustan los parámetros para que encaje.

## Corto plazo (antes de terminar el paper trading)

- [ ] **Correr el bot en un servidor 24/7** (VPS con Docker, ver [despliegue.md](despliegue.md)). En un PC, cada apagado pierde entradas del bot de rupturas.
- [ ] **Probar de punta a punta una operación manual** en Binance Demo (abrir, ver el trailing, cerrar desde el panel).
- [ ] **Alerta cuando la curva real sale de la banda proyectada** por varios días seguidos.
- [ ] **Resumen mensual también para rupturas**, con R promedio, acierto y comparación con el backtest.
- [ ] **Registro de cambios de agresividad en el dashboard**, para ver cuándo cambió y qué operaciones se abrieron con cada valor.

## Mediano plazo

- [ ] **IA v3, con pre-registro y 300 señales nuevas.** Dos caminos candidatos:
  - darle información que la estrategia no tiene: libro de órdenes, liquidaciones, flujo hacia exchanges, noticias con hora exacta;
  - cambiar su papel: que clasifique el régimen del mercado (tendencia, lateral, pánico) y decida si conviene operar esa semana, en vez de juzgar cada señal.
  Si tampoco supera al azar, se apaga el filtro de IA en vivo (hoy solo reduce el tamaño de todas las operaciones por igual).
- [ ] **Ejecutor real para la tendencia** en una subcuenta demo propia (Binance permite una posición por moneda por cuenta), y probarlo en demo antes de cualquier dinero real.
- [ ] **Versión solo largo de la tendencia en paralelo**, en otra cuenta virtual: tuvo mejor Sharpe y la mitad de caída en el backtest.
- [ ] **Comandos por Telegram** (`/estado`, `/agresividad`, `/cerrar`), usando la misma cola de órdenes que el panel.
- [ ] **Tests del dashboard** (componentes y acciones del panel de control).

## Ideas de estrategia en cola

Se anotan en [investigacion.md](investigacion.md) antes de probarlas, con su criterio de éxito:

- Momentum relativo entre más monedas (comprar las más fuertes, vender las más débiles).
- Estrategias de funding o basis (cobrar el funding cuando está muy desbalanceado).
- Combinar tendencia y rupturas en una sola cartera con presupuesto de riesgo.

## Si se pasa a dinero real

Solo después de cumplir la meta de 3 meses, y en este orden:

1. Revisar si los futuros de Binance están disponibles en el país y cómo se declaran las ganancias.
2. Empezar con 30–50% del monto pensado (mínimo práctico: ~3.000 USD por estrategia, por los mínimos de orden de Binance) y solo con dinero que se pueda perder.
3. Cambiar el broker para aceptar cuentas reales con una confirmación explícita (hoy se niega a operar fuera de demo, a propósito).
4. Mantener el kill switch y los límites de riesgo; subir el monto solo si los primeros meses salen como se espera.
