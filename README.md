# Ticket de Orden

La ficha compacta de la mejor oportunidad de Binance Futures USDⓈ-M
Perpetual, ahora mismo: dirección, entrada, SL y TP en tres horizontes
(scalp, corto, medio), tamaño sugerido según tu riesgo con tabla de
apalancamiento, si el libro de órdenes aguanta ese tamaño sin deslizamiento,
y titulares recientes que mencionen el activo. Sin párrafos. Sin ejecutar
nada.

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
mismo régimen de BTC, ya probado ahí). De la mejor candidata calcula **hasta
tres planes**:

- **Scalp (15-30min)**: SL y TP1 según la estructura de 15 minutos. Para
  operativa rápida — vigencia de solo 3 minutos, porque a ese plazo el
  precio se mueve rápido y un ticket viejo ya no sirve.
- **Corto (1-4h)**: SL, TP1 y TP2 según la estructura de 1H.
- **Medio (1-3d)**: SL, TP1, TP2 y TP3 según la estructura de 4H (TP2 y TP3
  son extensiones de Fibonacci de TP1, proporciones 1.618 y 2.618).
- Ninguno es una promesa de que se resuelva en ese plazo exacto — es de qué
  temporalidad sale el nivel, y esa temporalidad suele tardar más o menos en
  jugarse (por eso cada plan también dice hasta cuándo tiene sentido
  dejarlo puesto sin tocar, ver más abajo).
- Si la estructura es fuerte en **corto y medio** a la vez y alineada con el
  régimen de BTC, la ficha lo marca como candidata para evaluar tomar
  parcial en el corto y dejar el resto corriendo con el SL del medio (la
  regla "patrimonial" de tu propio sistema) — es una señal para que lo
  evalúes vos, no una instrucción.
- **Tamaño sugerido de cada plan**: `(equity × riesgo%) / distancia al SL de
  ese plan` — el tamaño nace del riesgo que definiste, nunca al revés.
- Pedí "dame algo para scalping" si solo querés el plan rápido, sin los
  otros dos.

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

Cada plan trae los mismos campos, en el mismo orden, que el formulario real
de Binance Futures (pestaña **Límite** + sección **TP/SL**) — para copiarlos
uno a uno sin traducir nada:

- **Mercado: Futuros USDⓈ-M Perpetual** — siempre, es lo único que este kit
  escanea (nunca Spot).
- **Margen: Aislado** — siempre, es la regla fija de tu propio sistema (Cross
  solo si hay una razón explícita, y este kit no la asume por su cuenta).
- **Apalancamiento**: el kit ya lo decide por vos — es el mínimo matemático
  para que el tamaño calculado según tu riesgo entre con tu equity (menos
  que eso, la posición no entra). No es una elección de cuánto arriesgar,
  ya está definida por tu % de riesgo y tu SL; el apalancamiento es solo la
  consecuencia. Si en algún momento querés comparar contra usar más margen
  (menos apalancamiento), pedile "mostrame las opciones de apalancamiento".
- **Precio** y **Cantidad** (en USDT): los campos de la pestaña Límite.
- **Take Profit** (referencia **Último**) y **Stop Loss** (referencia
  **Marca**): los mismos dos campos y las mismas referencias de precio por
  defecto que trae Binance en la sección TP/SL.
- **Reduce-Only: No** (es una entrada nueva) y **TIF: GTC**.
- Los planes corto y medio traen **TP2** (y el medio, también **TP3**), pero
  el campo Take Profit del formulario básico solo admite un precio — el
  ticket te dice cómo cargar los demás (Avanzado, o una orden Reduce-Only
  aparte por cada uno).
- Si preferís cargar a **Mercado** en vez de Límite, pedíselo así y te da el
  **Slippage Tolerance** sugerido en vez del precio de entrada — calculado
  según la volatilidad reciente del par (ATR), como punto de partida, no
  como garantía de ejecución exacta.

## Dos vigencias distintas (y esto no es un detalle)

- **Antes de cargarla**: cada plan trae `vigencia_minutos` (3 para el scalp,
  15 para el corto, 60 para el medio) y la hora en que se generó. Si tardás
  en cargar la orden más que eso, pedí un ticket nuevo — los precios ya
  cambiaron. Cargar una orden a mano lleva varios minutos reales, y un
  ticket de hace media hora en el plan scalp (pensado para minutos) ya no
  refleja el mercado.
- **Una vez cargada**: el TIF es GTC (Good Till Cancelled) — la orden en
  Binance no vence sola. Pero la *tesis* que la generó sí tiene un plazo: si
  pasan los 30 minutos (scalp), las 4 horas (corto) o los 3 días (medio) sin
  que toque ni el SL ni el TP, la estructura que armó esos números
  probablemente ya no aplica. No tiene sentido dejarla puesta esperando para
  siempre — mejor cancelarla y pedir un ticket nuevo con el mercado como
  está ahora.

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
02-tt-os/
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
