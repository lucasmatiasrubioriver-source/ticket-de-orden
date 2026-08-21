# Ticket de Orden

> Le pedís "dame el ticket" → te da una ficha corta: dirección, entrada, SL y
> TP en dos horizontes, tamaño sugerido, y si el libro de órdenes aguanta ese
> tamaño. **No ejecuta nada**: vos decidís y cargás la orden en Binance si
> querés.

## 4 pasos

1. **Escribe `/setup`.** Comprueba Python y la conexión con Binance, y te pide
   tu equity y tu % de riesgo por operación (una sola vez, se puede cambiar
   después).
2. **Probá el ejemplo de práctica** cuando te lo ofrezca — no gasta nada.
3. **Pedí tu ticket real**: "dame el ticket". Si un día no hay ninguna
   oportunidad que valga la pena, te va a decir "SIN OPERAR" — y eso también
   es información útil.
4. **Decile qué hiciste**: "la tomo" o "paso" (con el motivo si querés) y
   queda guardado — es lo que en un tiempo te va a decir si esto sirve.

## Si querés que se revise solo

Escribí `/loop 1h /vigilancia` con esta ventana abierta. Se revisa cada hora
y solo te interrumpe si apareció algo nuevo de verdad.

## Si algo falla al arrancar

| Pasa esto | Haz esto |
|---|---|
| No aparece `/setup` en la lista de comandos | Cierra y vuelve a abrir esta carpeta como proyecto en VS Code |
| Dice que no encuentra Python | Instalá Python 3 desde python.org y volvé a escribir `/setup` |
| No se puede leer Binance desde tu red | Probá desde otra conexión, o usá el modo práctica mientras tanto |
| Cualquier otro error | Pegá el mensaje literal, tal cual salió |

Este kit no necesita ninguna clave de API y no se conecta con tu cuenta de
Binance. La ficha es un plan para que vos decidas — nunca una orden ya dada.
