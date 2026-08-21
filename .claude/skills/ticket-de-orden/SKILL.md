---
name: ticket-de-orden
description: "Arma la ficha de la mejor oportunidad de Binance Futures ahora mismo: dirección, entrada, SL, TP1/TP2 y tamaño sugerido según tu % de riesgo — en formato compacto, sin párrafos explicativos. También compara contra la última revisión y avisa solo si apareció algo nuevo (candidata A/A+ o cambio de régimen de BTC), pensado para usarse con /loop. No ejecuta ninguna orden ni se conecta con ninguna cuenta: vos decidís y cargás. Usa esta skill cuando el usuario quiera el ticket u orden de la mejor oportunidad, quiera que se revise el mercado periódicamente, o quiera probar el ejemplo de práctica. Triggers: 'dame el ticket', 'dame la orden', 'qué opero ahora', 'cuál es la mejor ahora', 'vigila el mercado', 'avisame si aparece algo', 'revisa si cambió algo', 'prueba con el ejemplo'."
---

# Ticket de Orden

Arma la ficha de la mejor oportunidad ahora mismo, con tamaño de posición según
el riesgo del usuario — o compara contra la última revisión y avisa solo si
cambió algo real. **Salida compacta: números, sin párrafos explicando cada
factor.** No ejecuta nada, no se conecta con ninguna cuenta.

## Paso 0 — ¿Caso real o de práctica?

"prueba con el ejemplo" / "modo práctica" → usa
`ejemplos/snapshot-practica.json` con `--offline`, y avisa en una línea que es
ficticio. Si no, modo real.

## Paso 1 — Reunir el riesgo y el equity

Lee `.claude/configuracion.json` (la escribió `/setup`) para el % de riesgo y
el equity de referencia por defecto. Si el usuario menciona un número distinto
en su mensaje ("con 300 de equity", "arriesgando 1%"), usa ese en vez del
default, solo para esta corrida — no lo guardes salvo que el usuario diga
explícitamente "ahora mi equity es X" (ver tabla de decisión del `CLAUDE.md`).

## Paso 2 — Correr el motor

Modo ticket (una sola foto, ahora):

```
python scripts/ticket.py --equity <N> --riesgo-pct <P>
```

Modo vigilancia (comparar contra la última vez, pensado para `/loop`):

```
python scripts/ticket.py --vigilancia --equity <N> --riesgo-pct <P>
```

Con `--offline ejemplos/snapshot-practica.json` añadido en modo práctica.

## Paso 3 — Traducir el JSON a la ficha (sin párrafos)

### Modo ticket

Si `veredicto` es `"SIN_OPERAR"`:

```
SIN OPERAR — [motivo]. Régimen BTC: [regimen_btc].
```

Una sola línea. No expliques por qué el kit no encontró nada: el motivo del
JSON ya lo dice.

Si `veredicto` es `"TICKET"`, la ficha exacta (copia los números tal cual del
JSON, no los redondees de nuevo ni los reformules):

```
[symbol] — [LONG/SHORT en mayúsculas]
[letra] ([score]) · Riesgo [nivel_riesgo]
Entrada [entrada] · SL [sl] · TP1 [tp1] · TP2 [tp2]
Tamaño sugerido: [tamano_nocional_usdt] USDT (arriesgás [capital_arriesgado_usdt] USDT · SL a [distancia_sl_pct]%)
[estado_breakout]
```

Si `tamano` es `null` (no se dio equity), omite esa línea y en su lugar:
`Tamaño: decime tu equity para calcularlo.`

Si `empate_pendiente` no viene vacío, una línea final:
`(pendiente sin resolver en el puesto 4: [symbol1] / [symbol2])`

### Modo vigilancia

Si `hay_novedad` es `false`: una sola línea, **`Sin novedades.`** — y nada más.
No repitas el estado del mercado si no cambió nada; el usuario pidió
vigilancia, no un resumen cada vez.

Si `hay_novedad` es `true`: antes que nada di qué cambió, en una línea:

- Si trae `cambio_regimen`: `Régimen BTC: [de] → [a].`
- Si trae `candidatas_nuevas_ab`: `Nueva candidata A/A+: [symbol].`

Y si trae `ticket_de_la_novedad`, la misma ficha compacta del modo ticket
justo debajo.

## Paso 4 — Guardar y comprobar

- El script ya actualiza `.claude/ultimo-radar.json` solo (no lo edites a mano).
- Antes de mostrar la ficha, comprueba que los números que vas a escribir
  existen tal cual en el JSON que imprimió el script — no inventes un TP ni un
  tamaño que el script no calculó.
- Si el modo es vigilancia y se llama por primera vez (`motivo`: "primera
  revision..."), dilo en una línea: "Primera revisión guardada, la próxima ya
  compara." No hay ficha que mostrar todavía.

## Reglas

- **Nunca agregues la palabra "ejecutá", "comprá" ni ninguna instrucción de
  acción.** La ficha muestra el plan; cargarlo en Binance lo decide el
  usuario, siempre.
- **Sin párrafos.** Si te encontrás escribiendo una oración explicando por qué
  el RSI está en tal valor, parate: eso no va en este kit. Para ver el porqué
  completo de cada número, el usuario tiene el kit Radar de Trading.
- **El dato manda.** Todo número de la ficha sale del JSON de `ticket.py`, que
  a su vez sale de `radar.py`. Nunca se estima ni se redondea distinto a como
  viene.
- **Un score por debajo de 55 nunca genera ticket.** El veredicto es SIN
  OPERAR — quedarse en cash es una posición válida, no un fallo del kit.
- Español sin jerga en las etiquetas fijas (Entrada, SL, TP1, TP2, Riesgo,
  Tamaño sugerido) — son siempre las mismas palabras, no varían de corrida a
  corrida.
