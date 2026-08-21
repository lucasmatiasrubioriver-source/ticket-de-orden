# Contrato de construcción — Ticket de Orden

## Estado

- [x] Paso 1 — Entrevista
- [x] Paso 2 — Contrato (este documento)
- [x] Paso 3 — Comprobar la vía de datos
- [x] Paso 4 — Criterio de calidad
- [x] Paso 5 — Construir el kit
- [x] Paso 6 — Ejemplo de práctica
- [x] Paso 7 — Correr el kit contra su ejemplo
- [x] Paso 8 — Lista de calidad
- [ ] Paso 9 — Entregar

Fecha: 2026-08-21 · Para: Lucas · Uso: propio.

---

## Contexto: por qué este kit y con este límite

Lucas pidió que el sistema "trabaje solo" — que Claude le diga qué escribir y
en qué momento del día, para que él lo replique en Binance sin pensarlo. Se
explicó por qué eso no es distinto de la ejecución automática que ya se había
descartado (sección 71 de su documento original: "nunca 'el modelo dijo
comprar, entonces compramos'") — el teclado del usuario en el medio no lo
vuelve una decisión humana si no hay criterio propio aplicado. Se acordó en
su lugar:

1. Un **ticket bajo demanda**: el usuario pide la ficha cuando él decide
   mirarla, no cuando el kit se la empuja.
2. Una **vigilancia periódica** que avisa solo si cambió algo real (nueva
   candidata A/A+, cambio de régimen de BTC) — sin decir qué hacer, solo que
   mires. Corre con `/loop` de Claude Code, nunca sola en segundo plano.

Además, el usuario pidió explícitamente que la salida **no explique nada,
solo dé veredictos** — de ahí el formato de ficha compacta (números y
etiquetas fijas, sin párrafos), inspirado en el formato "Ficha
técnica"/"Orden TT" de su propio historial operativo (documento "TT OS —
Historial operativo", secciones 10 y 23).

También se compartió ese historial completo, con datos reales de cuenta
(balances, transferencias en ARS, holdings de INJ/ONDO). Ese archivo **no se
copió a ningún lado de este kit** (ni a `ejemplos/`, ni a ningún documento):
lo único que se usó de ahí fue el diseño de campos de la sección 29, como
referencia para un futuro kit de journal.

## La promesa de una frase

> **Entra**: "dame el ticket" → **sale**: una ficha de 5-6 líneas (símbolo,
> dirección, letra + score, riesgo, entrada, SL, TP1, TP2, tamaño sugerido)
> de la mejor oportunidad ahora mismo — o "SIN OPERAR" si ninguna alcanza el
> mínimo de calidad. Sin ejecutar nada.

## Los cuatro ejes

| Eje | Respuesta |
|---|---|
| **Qué entra** | Nada que el usuario aporte por defecto; opcionalmente su equity y % de riesgo si quiere cambiar el default guardado en `/setup` |
| **Qué sale** | La ficha compacta en el chat (no se guarda archivo en `workspace/`: es una respuesta conversacional corta, pensada para leerse y decidir en el momento, no para archivar) |
| **Qué hay que instalar** | Nada. Mismo motor Python sin dependencias del kit Radar de Trading |
| **Para quién** | Lucas, uso propio |

## Qué queda fuera

- No ejecuta ninguna orden ni se conecta con ninguna clave de API de Binance.
- No lee el equity real de una cuenta: es un número manual que el usuario da.
- No explica el porqué de ningún número (eso lo hace el kit Radar de Trading).
- No corre en segundo plano fuera de una ventana de Claude Code abierta con
  `/loop`.
- No incluye Spot (el motor solo escanea Binance Futures USDT-M, igual que el
  kit Radar de Trading).

## Paso 3 — Comprobación de la vía de datos

Reutiliza el motor `radar.py` del kit `01-radar-trading`, ya comprobado y
corregido ahí (ver su propio `_CONTRATO.md` para el detalle de los 10
endpoints probados). Lo nuevo de este kit (`ticket.py`: tamaño de posición,
TP2, comparación con la última revisión) se probó de punta a punta contra el
fixture offline y con datos sintéticos aislados — ver Paso 7.

## Paso 4 — Criterio de calidad

No es un kit que puntúa (reutiliza el score del Radar); es un kit que
**genera una ficha**. Criterio comprobable:

- La ficha tiene exactamente las etiquetas fijas: símbolo, dirección, letra +
  score, riesgo, Entrada, SL, TP1, TP2, tamaño sugerido, estado de breakout.
- Ningún número de la ficha aparece si no vino del JSON de `ticket.py`.
- Un score < 55 nunca produce ticket: el veredicto pasa a ser "SIN OPERAR".
- El tamaño sugerido nunca aparece sin haber recibido un equity (real o por
  defecto de `/setup`).
- En modo vigilancia, si no cambió nada desde la última revisión, la
  respuesta es únicamente "Sin novedades." — ninguna otra línea.

---

## Paso 6 — Ejemplo de práctica

Reutiliza el mismo `ejemplos/snapshot-practica.json` del kit Radar de
Trading (mismo universo ficticio, mismos 12 casos plantados — ver el
`_CONTRATO.md` de ese kit para el detalle completo). No se plantaron casos
nuevos porque `ticket.py` no agrega ninguna fuente de datos nueva: solo
transforma la salida del mismo motor ya probado.

Casos específicos de este kit, probados por separado (no vienen del fixture,
se probaron con datos sintéticos aislados porque el fixture no genera
naturalmente cada escenario):

1. **Ticket normal**: la mejor candidata (ZENUSDT, score 66.5) genera ficha
   completa con tamaño calculado.
2. **SIN_OPERAR por falta de candidatas**: probado con una lista vacía.
3. **SIN_OPERAR por score bajo el mínimo**: probado con una candidata de 42
   puntos.
4. **Vigilancia, primera vez**: sin punto de comparación, no hay ficha.
5. **Vigilancia, sin cambios**: mismo fixture dos veces seguidas → "Sin
   novedades."
6. **Vigilancia, cambio de régimen**: estado anterior forzado a "Bear",
   detecta el cambio a "Bull" del fixture actual.
7. **Vigilancia, candidata A/A+ nueva**: probado con datos sintéticos (el
   fixture no tiene ninguna A/A+, así que se armó un caso aislado) — genera
   el ticket de la novedad correctamente.

## Paso 7 — Defectos encontrados al ejecutar

1. Los precios calculados (TP2, derivado por multiplicación) salían con
   ruido de punto flotante (15 decimales) — inutilizable como precio real.
   Corregido: se redondea a 6 cifras significativas antes de mostrar (no
   antes de calcular el tamaño, que usa los valores completos).

Todo lo demás salió correcto al primer intento, porque reutiliza el motor ya
probado exhaustivamente en el kit Radar de Trading — la lección de por qué el
Paso 3/7 de ESE kit importaba tanto.

## Ampliaciones posteriores a la entrega inicial (2026-08-21)

A pedido del usuario, después de la primera entrega:

1. **Dos horizontes por ticket**: `plan_corto_1a4h` (estructura 1H) y
   `plan_medio_1a3d` (estructura 4H, con TP1/TP2). Requirió agregar a
   `radar.py` un cálculo de invalidación/objetivo sobre `k1h`, ademas del ya
   existente sobre `k4h` — sin tocar el sistema de puntuación de 10
   dimensiones del kit Radar de Trading (es un dato adicional, no una
   dimensión nueva). Defecto encontrado al probarlo: el fixture generaba el
   cierre de 1H y el de 4H con precios distintos (imposible en datos reales,
   donde ambos representan el mismo instante) — corregido reescalando la
   serie de 1H para que termine en el mismo precio que la de 4H.
2. **Aviso de candidata "patrimonial"**: cuando la estructura es fuerte en
   los dos horizontes a la vez y alineada con el régimen de BTC, la ficha lo
   marca como señal para evaluar (nunca como instrucción).
3. **Historial auditable** (`workspace/historial-vigilancia.jsonl`) y
   **cooldown de 6 horas** para no repetir la misma alerta en un mercado
   picado.
4. **Intento de rutina en la nube** (agente programado vía `schedule`, sin
   depender de tener Claude Code abierto): se armó el repositorio en GitHub
   (`ticket-de-orden`, público — no contiene datos reales del usuario) y la
   rutina, pero **la prueba real reveló dos límites de infraestructura que no
   se pueden resolver desde este kit**: el entorno en la nube no tiene salida
   de red hacia la API de Binance (403 a nivel de túnel), y tampoco tiene
   permiso de escritura de vuelta al repositorio (`git push` también dio
   403, aunque el clonado sí funciona). La rutina quedó creada pero
   **deshabilitada** (`enabled: false`) para no fallar en silencio cada hora
   sin aportar nada. El comportamiento ante el fallo fue correcto: no
   inventó ningún dato ni mandó ninguna notificación falsa. **La vía
   soportada para "que se revise solo" sigue siendo `/loop 1h /vigilancia`**,
   probada y funcionando.

## Segunda ronda de ampliaciones (2026-08-21, misma sesión)

A pedido del usuario ("que vea todo eso" — libro de órdenes y noticias — "y
lo que se te ocurra"):

1. **Libro de órdenes real** (`GET /fapi/v1/depth`, público, sin clave):
   compara el tamaño sugerido del plan medio contra la profundidad real
   parada a 0.3% del precio, del lado que se va a llenar. Si el tamaño supera
   el 15% de esa profundidad, avisa que cargar todo de una vez podría mover
   el precio — si no, no dice nada (solo avisa el problema, no confirma que
   está todo bien).
2. **Titulares recientes** (RSS de Cointelegraph, público, sin clave, últimas
   48h): busca menciones literales del símbolo o su nombre conocido
   (Bitcoin, Ethereum, etc.) y las muestra tal cual, con fuente y fecha —
   nunca las interpreta ni resume. **Defecto real encontrado y corregido**:
   el pedido fallaba con 403 (Cointelegraph bloquea el User-Agent por
   defecto de `urllib`) y el error quedaba silenciado — el kit decía
   "sin titulares" siempre, aunque los hubiera. Se agregó un User-Agent de
   navegador a la petición. Verificado en vivo contra el mercado real: la
   candidata del momento (HYPEUSDT) trajo un titular real y directamente
   relevante ("HYPE jumps 20% as Trump signals legal US path for
   Hyperliquid").
3. **Ninguno de los dos corre en modo práctica** (`--offline`): un símbolo
   ficticio no tiene libro ni noticias reales, y no se fabrica una respuesta
   para rellenar el hueco.
4. **Registro de decisiones** (`scripts/registrar_decision.py` →
   `workspace/decisiones.jsonl`): el usuario dice "la tomo" o "paso" con el
   motivo, y queda guardado — símbolo, fecha, decisión, motivo, y los
   números del plan si corresponde. Es el insumo que le faltaba al futuro
   kit de journal.

Verificado en vivo contra el mercado real de Binance (no solo el ejemplo de
práctica) el 2026-08-21 ~05:44 UTC: régimen "High Volatility", candidata
HYPEUSDT, libro de órdenes sano (deslizamiento 0%), titular real encontrado.

## Tercera ronda de ampliaciones (2026-08-21, misma sesión)

A pedido del usuario: dos preguntas que se convirtieron en dos features.

1. **Vigencia del ticket** ("tardo 5-7 min en cargar una orden"): cada plan
   trae `vigencia_minutos` (15 el corto, 60 el medio — con margen sobre esos
   5-7 minutos reales) y `generado_utc`. Es el concepto `OrderFreshness` de
   la spec original del usuario, nunca antes puesto en números concretos.
2. **Formato de orden estilo Binance**: cada plan agrega `orden_binance` con
   margen (Aislado, fijo — regla propia del usuario), apalancamiento mínimo
   (piso matemático `tamaño / equity`, no una recomendación), tipos de orden
   (LIMIT para la entrada, STOP_MARKET y TAKE_PROFIT_MARKET con Reduce Only
   para SL/TP — la forma estándar y más confiable de cargarlos en Binance) y
   un deslizamiento sugerido proporcional a la volatilidad reciente (ATR 4H,
   expuesto ahora como `atr_pct_4h` en `radar.py`). Estos campos sí están
   disponibles en modo práctica (no dependen de red), a diferencia del libro
   de órdenes y las noticias.

## Cuarta ronda (2026-08-21, misma sesión): calzar exacto con Binance

El usuario mandó capturas reales del formulario de orden de Binance Futures.
Se reescribió `orden_binance` para que sea campo por campo lo mismo que se
ve en pantalla: pestaña (Límite/Mercado), margen, apalancamiento, Precio,
Cantidad (en USDT), Take Profit (referencia Último) y Stop Loss (referencia
Marca) — los mismos nombres y las mismas referencias por defecto que trae
Binance —, Reduce-Only y TIF (GTC). El campo `nota_tp2` explica cómo cargar
el segundo take profit, porque el formulario básico solo admite uno.

También se separaron dos conceptos de vigencia que antes eran uno solo:
`vigencia_minutos` (cuánto puede tardar el usuario en cargar la orden antes
de que los precios del ticket ya no sirvan) y `reevaluar_si_no_toco_en`
("4 horas" / "3 días" — una vez la orden está puesta, hasta cuándo tiene
sentido dejarla esperando antes de asumir que la tesis ya cambió). Salió de
una pregunta directa del usuario sobre cuánto dejar un TP pendiente.

## Quinta ronda (2026-08-21, misma sesión): scalping, TP3, tabla de apalancamiento

A pedido del usuario:

1. **Etiqueta de mercado fija** (`"Futuros USDⓈ-M Perpetual"`), arriba de la
   ficha y dentro de cada plan — este kit nunca escanea Spot, así que es un
   dato cierto, no una suposición.
2. **Plan scalp (15-30 min)**: nuevo horizonte basado en estructura de 15
   minutos. Requirió agregar la vela de 15m al motor (`radar.py` y el
   generador del ejemplo) — no existía antes. Vigencia de 3 minutos (el
   plazo más corto de los tres) y "reevaluar si no tocó en 30 minutos".
3. **TP2 en el plan corto y TP3 en el plan medio** (extensiones de
   Fibonacci 1.618 / 2.618 desde TP1) — antes el corto solo tenía TP1 y el
   medio solo TP1+TP2.
4. **Tabla de apalancamiento (1x/3x/5x)**: margen requerido a cada nivel
   para el mismo tamaño, marcando si alcanza con el equity del usuario o
   no. Reemplaza el "apalancamiento mínimo" como único dato — ahora es un
   dato más dentro de la tabla, no el único.

Al generar el ejemplo de práctica con velas de 15m, el mismo defecto de
consistencia que ya se había encontrado y corregido para 1H (el cierre de
una temporalidad más fina divergiendo del precio de la temporalidad mayor)
se previno desde el diseño: el cierre de 15m se ancla al de 1H con el mismo
mecanismo de reescalado.

Verificado offline y en vivo: los tres planes calculan correctamente: el
plan scalp con un stop muy ajustado puede pedir un tamaño que no alcanza ni
a 5x con la cuenta chica del usuario (93 USDT) — la tabla lo muestra en vez
de ocultarlo.

## Sexta ronda (2026-08-21, misma sesión): apalancamiento decidido + estética

A pedido del usuario:

1. **El kit ya no pregunta ni muestra la tabla de 1x/3x/5x por defecto**: la
   ficha usa directamente `apalancamiento_minimo` (el piso matemático del
   tamaño ya calculado por el % de riesgo) como el apalancamiento a cargar.
   La tabla completa sigue disponible bajo pedido ("mostrame las opciones de
   apalancamiento"). No fue un cambio de código —`ticket.py` ya calculaba
   ambos datos— sino de qué muestra por defecto la skill.
2. **Ficha en Markdown** en vez de texto plano: tablas por plan, encabezados,
   🟢/🔴 para long/short (el mismo código de color que usa el propio Binance
   en sus botones Comprar/Vender), ⚡/🕐/📅 para diferenciar los tres
   horizontes de un vistazo. Sigue siendo sin párrafos — es formato, no
   contenido nuevo.

## Paso 8 — Lista de calidad

- [x] `/setup` completa sin terminal ni edición de código.
- [x] El ejemplo de práctica funciona de principio a fin.
- [x] `EMPIEZA-AQUI.md`, `README.md`, `CLAUDE.md` cuentan la misma historia
      (mismas etiquetas de la ficha, mismo límite de score 55, misma
      explicación de `/loop`).
- [x] Sin referencias rotas: `scripts/radar.py`, `scripts/ticket.py`,
      `ejemplos/snapshot-practica.json` existen.
- [x] Deja claro qué cuesta: nada.
- [x] Funciona igual en Mac y Windows.
- [x] Estado de primer arranque limpio: sin `setup-completado.json`, sin
      `configuracion.json`, sin `ultimo-radar.json`, `workspace/` solo con
      `.gitkeep`.
