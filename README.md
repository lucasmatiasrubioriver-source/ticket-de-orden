# Ticket de Orden

La ficha compacta de la mejor oportunidad de Binance Futures, ahora mismo:
dirección, entrada, SL y TP en dos horizontes, tamaño sugerido según tu
riesgo, si el libro de órdenes aguanta ese tamaño sin deslizamiento, y
titulares recientes que mencionen el activo. Sin párrafos. Sin ejecutar nada.

> **Entra**: le pedís "dame el ticket" → **sale**: una ficha corta con los
> números para que vos decidas si la cargás en Binance — y le decís qué
> hiciste ("la tomo" / "paso") para que quede guardado.

## Qué NO hace

- **No ejecuta ninguna orden.** No se conecta con tu cuenta de Binance, no
  necesita ninguna clave de API.
- **No explica.** Si querés el porqué de cada número —tendencia, momentum,
  Open Interest, régimen de BTC—, usá el kit hermano **Radar de Trading**
  (`../01-radar-trading/`), que sí lo desglosa todo.
- **No corre solo en segundo plano por su cuenta.** Si querés que se revise
  cada cierto tiempo, eso lo hace `/loop` de Claude Code (ver más abajo), y
  solo mientras tengas la ventana abierta.
- **No lee tu equity real.** El número que usa para calcular el tamaño es el
  que vos le diste en `/setup` (o el que le digas en el momento) — no tiene
  acceso a tu cuenta.

## Cómo arma el ticket

Reutiliza el mismo motor del kit Radar de Trading (misma fórmula de score,
mismo régimen de BTC, ya probado ahí). De la mejor candidata calcula **dos
planes**, no uno:

- **Corto (1-4h)**: SL y TP según la estructura de 1H. Pensado como
  referencia de horas — no es una promesa de que se resuelva en ese plazo
  exacto, es de qué temporalidad sale el nivel.
- **Medio (1-3d)**: SL, TP1 y TP2 según la estructura de 4H (TP2 es una
  extensión de TP1, proporción 1.618). Referencia de días.
- Si la estructura es fuerte en **los dos** horizontes a la vez y alineada
  con el régimen de BTC, la ficha lo marca como candidata para evaluar
  tomar parcial en el corto y dejar el resto corriendo con el SL del medio
  (la regla "patrimonial" de tu propio sistema) — es una señal para que lo
  evalúes vos, no una instrucción.
- **Tamaño sugerido de cada plan**: `(equity × riesgo%) / distancia al SL de
  ese plan` — el tamaño nace del riesgo que definiste, nunca al revés.

**Un score por debajo de 55 (B) nunca genera un ticket.** El veredicto pasa a
ser "SIN OPERAR" — quedarte en cash cuando no hay nada bueno es una decisión
válida, no un fallo del kit.

Además, sobre la candidata elegida:

- **Chequea el libro de órdenes real** de Binance: si el tamaño sugerido es
  una porción grande de lo que hay parado cerca del precio, te avisa que
  cargarlo de una vez podría moverte el precio en contra (deslizamiento).
  Solo avisa cuando hay un problema — si el libro aguanta bien, no dice nada.
- **Busca titulares recientes** (últimas 48h, de Cointelegraph) que mencionen
  el activo, y te los muestra tal cual — sin resumirlos ni decirte si son
  buenos o malos para el precio, eso lo interpretás vos.
- Ninguno de los dos corre en modo práctica: un símbolo ficticio no tiene
  libro ni noticias reales, y este kit no fabrica una respuesta para
  completar el hueco.

## Formato de orden (estilo Binance)

Cada plan viene listo para cargar tal cual en Binance Futures, sin traducir
nada vos:

- **Margen: Aislado** — siempre, es la regla fija de tu propio sistema (Cross
  solo si hay una razón explícita, y este kit no la asume por su cuenta).
- **Apalancamiento mínimo**: el piso matemático para que el tamaño entre con
  tu equity (`tamaño nocional / equity`, redondeado hacia arriba). No es una
  recomendación de cuánto usar — si preferís menos apalancamiento (más
  margen puesto), es tu cuenta.
- **Entrada**: orden LIMIT al precio mostrado.
- **SL**: STOP_MARKET, Reduce Only.
- **TP (1 y 2 si aplica)**: TAKE_PROFIT_MARKET, Reduce Only.
- **Deslizamiento sugerido**: un margen de tolerancia para las órdenes Stop
  y Take Profit, calculado a partir de la volatilidad reciente del par (ATR
  4H) — más volátil, más margen. Es una referencia de partida, no una
  garantía de que la orden va a ejecutar exactamente ahí.

## La vigencia importa (y esto no es un detalle)

Cada plan trae `vigencia_minutos` (15 para el corto, 60 para el medio) y la
hora en que se generó. Si tardás en cargar la orden más que eso, pedí un
ticket nuevo antes de cargarlo — los precios ya cambiaron. Esto no es
paranoia: cargar una orden a mano lleva varios minutos reales, y un ticket
de hace media hora en el plan corto (pensado para horas) ya no refleja el
mercado.

## Registrar qué decidiste

Después de un ticket, decile "la tomo" o "paso" (con el motivo si querés) y
queda guardado en `workspace/decisiones.jsonl` — símbolo, fecha, qué
decidiste y por qué. No es un lujo: sin esto, dentro de un mes no hay forma
de saber si el sistema realmente ayudó. Es también el primer insumo del
futuro kit de journal.

## Modo vigilancia (opcional)

Si querés que el mercado se revise solo cada cierto tiempo y te avise **solo
cuando cambia algo real** (una candidata nueva de calidad A/A+, o un cambio de
régimen de BTC) — sin decirte qué hacer, solo que mires:

1. Abrí esta carpeta en Claude Code.
2. Escribí `/loop 1h /vigilancia` (podés cambiar `1h` por el intervalo que
   quieras).
3. Mientras la ventana esté abierta, se revisa solo. Si no hay nada nuevo,
   responde solo "Sin novedades." — no te va a llenar el chat de resúmenes.

Esto **no es un servicio corriendo en la nube**: es Claude Code repitiendo el
comando mientras tu ventana está abierta. Si la cerrás, se detiene.

Dos cosas más de la vigilancia:

- **Queda un registro**: cada revisión (haya novedad o no) agrega una línea a
  `workspace/historial-vigilancia.jsonl` — fecha, régimen, si avisó y de qué.
  Es tu forma de auditar después si el sistema anduvo bien.
- **No repite el mismo aviso dos veces en 6 horas**: si una candidata entra y
  sale de A/A+ varias veces en un mercado picado, te avisa una sola vez, no
  una por hora.

## Qué hay en el kit

```
02-ticket-de-orden/
├── EMPIEZA-AQUI.md
├── README.md
├── CLAUDE.md
├── .claude/
│   ├── commands/setup.md
│   ├── commands/ticket.md
│   ├── commands/vigilancia.md
│   └── skills/ticket-de-orden/SKILL.md
├── scripts/
│   ├── radar.py                ← el mismo motor del kit Radar de Trading
│   ├── ticket.py                ← tamaño de posición + ficha + libro de órdenes + noticias
│   └── registrar_decision.py    ← guarda qué hiciste con cada ticket
├── ejemplos/          ← caso de práctica ficticio, sin conexión
└── workspace/
```

## Cómo se usa

1. `/setup`: comprueba Python y la conexión con Binance, te pide tu equity y
   tu % de riesgo una sola vez, y te explica `/loop` si querés vigilancia.
2. "Dame el ticket" cuando quieras la foto de ahora.
3. `/loop 1h /vigilancia` si querés que se revise solo.

## Windows y Mac

Igual en los dos: Python 3, librería estándar, sin paquetes que instalar.

## Seguridad

Sin claves de API, sin conexión con tu cuenta. El equity y el riesgo son
números que vos le das, y podés cambiarlos cuando quieras diciendo "mi equity
ahora es X".

## Qué cuesta usarlo

Nada, aparte de tu cuenta de Claude Code. La API de Binance que usa es
pública y gratuita.
