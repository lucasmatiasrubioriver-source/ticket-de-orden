---
name: ticket-de-orden
description: "Arma la ficha de la mejor oportunidad de Binance Futures ahora mismo: dirección, entrada, SL, TP1/TP2 en dos horizontes (1-4h y 1-3d), tamaño sugerido según tu % de riesgo, chequeo de libro de órdenes (deslizamiento) y titulares recientes que mencionen el activo — en formato compacto, sin párrafos explicativos. También compara contra la última revisión y avisa solo si apareció algo nuevo, y registra qué decidiste hacer con cada ticket. No ejecuta ninguna orden ni se conecta con ninguna cuenta: vos decidís y cargás. Usa esta skill cuando el usuario quiera el ticket u orden de la mejor oportunidad, quiera que se revise el mercado periódicamente, quiera anotar si tomó o pasó una candidata, o quiera probar el ejemplo de práctica. Triggers: 'dame el ticket', 'dame la orden', 'qué opero ahora', 'cuál es la mejor ahora', 'vigila el mercado', 'avisame si aparece algo', 'revisa si cambió algo', 'la tomo', 'esta paso', 'mostrame el historial de decisiones', 'prueba con el ejemplo'."
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

Si `veredicto` es `"TICKET"`, la ficha trae **dos planes**, cada uno con los
**campos exactos del formulario de orden de Binance Futures** (pestaña
Límite + sección TP/SL), en el mismo orden en que aparecen en la pantalla,
para que se puedan cargar copiando uno a uno sin traducir nada. Copiá los
números tal cual del JSON, no los redondees de nuevo ni los reformules:

```
[symbol] — [LONG/SHORT en mayúsculas]
[letra] ([score]) · Riesgo [nivel_riesgo]
Generado [generado_utc, en hora de Argentina] — vigente [plan.vigencia_minutos] min, si pasó más pedí uno nuevo

CORTO (1-4h, estructura 1H):
  [orden_binance.margen] · [orden_binance.apalancamiento_minimo]x · Pestaña: [orden_binance.pestana]
  Precio: [orden_binance.precio]
  Cantidad: [orden_binance.cantidad_usdt] USDT
  TP/SL → Take Profit: [orden_binance.take_profit.precio] (ref. [orden_binance.take_profit.referencia])
  TP/SL → Stop Loss: [orden_binance.stop_loss.precio] (ref. [orden_binance.stop_loss.referencia])
  Reduce-Only: No · TIF: [orden_binance.tif]
  Si no tocó SL ni TP en [plan_corto_1a4h.reevaluar_si_no_toco_en]: la tesis ya cambió, pedí un ticket nuevo en vez de dejarla puesta

MEDIO (1-3d, estructura 4H):
  [orden_binance.margen] · [orden_binance.apalancamiento_minimo]x · Pestaña: [orden_binance.pestana]
  Precio: [orden_binance.precio]
  Cantidad: [orden_binance.cantidad_usdt] USDT
  TP/SL → Take Profit: [orden_binance.take_profit.precio] (ref. [orden_binance.take_profit.referencia])
  TP/SL → Stop Loss: [orden_binance.stop_loss.precio] (ref. [orden_binance.stop_loss.referencia])
  Reduce-Only: No · TIF: [orden_binance.tif]
  [orden_binance.nota_tp2, si existe]
  Si no tocó SL ni TP en [plan_medio_1a3d.reevaluar_si_no_toco_en]: la tesis ya cambió, pedí un ticket nuevo en vez de dejarla puesta

[estado_breakout]
```

Si alguno de los dos planes viene `null`, ese bloque entero no se escribe (no
inventes un plan que el motor no pudo calcular). Si `apalancamiento_minimo`
es `null` (no se dio equity), esa parte se omite. El **"apalancamiento
mínimo"** es el piso matemático para que el tamaño entre con el equity dado
— no es una recomendación de cuánto usar. El campo `nota_tp2` (solo en el
plan medio) explica cómo cargar el segundo take profit, porque el formulario
básico de Binance solo admite un Take Profit por vez.

Si usa la pestaña **Mercado** en vez de Límite (el usuario lo puede pedir:
"dámelo para cargar a mercado"), reemplazá "Pestaña: Límite" por "Pestaña:
Mercado", sacá la línea de `Precio` (a mercado no se fija precio de entrada)
y agregá `Slippage Tolerance: [orden_binance.deslizamiento_si_usa_mercado_pct]%`.

Si `candidata_patrimonial` es `true`, agregá una línea aparte, corta:
`Estructura fuerte en 1H y 4H — si el corto llega a TP, evaluar parcial ahí y dejar el resto con el SL del plan medio.` Es una señal para que el usuario lo evalúe, no una instrucción de que lo haga.

Si `tamano` de un plan es `null` (no se dio equity), en esa línea escribí
`Tamaño: decime tu equity para calcularlo` en vez del número.

Si `liquidez_libro` no es `null` y `alerta_posible_deslizamiento` es `true`,
una línea: `Cuidado: el tamaño sugerido es [fraccion_del_tamano_vs_profundidad × 100]% de lo que hay parado cerca del precio — considerá partir la entrada.` Si `alerta_posible_deslizamiento` es `false`, no digas nada sobre el libro
(no hace falta confirmar que algo está bien, solo avisar cuando no lo está).

Si `titulares_recientes` no viene vacío, una línea por titular (máximo 3):
`Titular reciente: "[titulo]" — [link]`. Es el texto literal del feed, no lo
resumas ni le agregues tu interpretación de qué significa para el precio.

Si `empate_pendiente` no viene vacío, una línea final:
`(pendiente sin resolver en el puesto 4: [symbol1] / [symbol2])`

### Modo vigilancia

Si `hay_novedad` es `false`: una sola línea, **`Sin novedades.`** — y nada más,
**incluso si viene un `motivo`** (por ejemplo, que una candidata reapareció
pero ya se había avisado hace menos de 6 horas: ese campo es para auditar el
`workspace/historial-vigilancia.jsonl`, no para el usuario cada vez — si lo
repetís cada hora, es el mismo ruido que el cooldown existe para evitar). No
repitas el estado del mercado si no cambió nada; el usuario pidió vigilancia,
no un resumen cada vez.

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

## Paso 5 — Registrar la decisión (cuando el usuario la dé)

Después de mostrar un ticket, si el usuario dice algo como "la tomo", "esta
la cargo", "paso", "esta no me convence" (con o sin decir por qué): registrá
la decisión, no lo dejes pasar sin guardar.

```
python scripts/registrar_decision.py --symbol <SYMBOL> --decision tomado|pasado --motivo "<lo que haya dicho>" --entrada <N> --sl <N> --tp1 <N> --plan corto|medio
```

Usa el symbol y los números del **último ticket que mostraste** en esta
conversación (no le vuelvas a preguntar el precio). Si no dijo un motivo, no
inventes uno — mandá `--motivo` vacío o directamente omitilo. Confirmá en una
línea: `Guardado: [symbol] — [tomado/pasado].` Nada más, no repitas el motivo
que ya dijo.

Si te pregunta "mostrame el historial de decisiones" o similar: leé
`workspace/decisiones.jsonl` y armá una tabla corta (fecha, símbolo, decisión,
motivo) — sin interpretar si acertó o no, eso es trabajo del futuro kit de
journal, no de este.

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
- **Los titulares se citan tal cual, nunca se interpretan.** No agregues "esto
  es alcista/bajista" ni ninguna lectura propia de una noticia — el kit no
  tiene forma de comprobar eso, y sería inventar.
- **El chequeo de libro y noticias no existe en modo práctica.** Un símbolo
  ficticio no tiene libro real ni noticias reales — no fabriques una
  respuesta "para que quede completo".
- **Toda decisión que el usuario cuente se registra**, no queda solo en el
  chat — es el dato que hace falta para saber, con el tiempo, si esto sirve.
- **La vigencia del ticket es real, no un adorno**: el usuario tarda varios
  minutos en cargar una orden a mano. Si te dice que va a cargar un ticket
  que mostraste hace rato (más de `vigencia_minutos`), decile en una línea
  que pida uno nuevo — los precios ya pueden haber cambiado.
- **El apalancamiento y el tipo de orden son referencia técnica, no una
  ejecución.** "Apalancamiento mínimo" es el piso matemático, no un consejo
  de cuánto usar; los tipos de orden (LIMIT / STOP_MARKET / TAKE_PROFIT_MARKET)
  son la forma estándar de cargar ese plan en Binance, para que el usuario no
  tenga que traducir el plan al lenguaje de la plataforma él solo.
- Español sin jerga en las etiquetas fijas (Entrada, SL, TP1, TP2, Riesgo,
  Tamaño sugerido) — son siempre las mismas palabras, no varían de corrida a
  corrida.
