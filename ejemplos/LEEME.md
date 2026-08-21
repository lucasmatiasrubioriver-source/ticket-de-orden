# Ejemplo de práctica — es ficticio

Es el mismo mercado ficticio del kit Radar de Trading (`snapshot-practica.json`):
símbolos inventados que no existen en Binance real. Sirve para ver cómo sale
el ticket sin conexión y sin arriesgar nada.

## Cómo se usa

Dile al kit: **"prueba con el ejemplo"**. Va a pedirte (o usar el valor por
defecto de tu `/setup`) un equity y un % de riesgo, y te va a armar el ticket
de la mejor candidata de ese mercado inventado.

## Qué debería salir, más o menos

- La mejor candidata del ejemplo ronda los 65-67 puntos (letra B, riesgo
  Bajo) — suficiente para generar ticket (el mínimo es 55).
- La ficha trae dos planes: uno corto (1-4h, estructura 1H) y uno medio
  (1-3d, estructura 4H, con TP1 y TP2). El tamaño de cada uno depende del
  equity y el riesgo % que uses.
- Si probás el **modo vigilancia** dos veces seguidas sin que cambie nada, la
  segunda vez tiene que decir **"Sin novedades."** y nada más — no repetir el
  ticket ni el estado del mercado.

Si el kit te da un tamaño inventado sin que le hayas dado un equity, o te dice
"ejecutá esto" en vez de mostrarte la ficha para que decidas vos, es un
defecto: repórtalo tal cual.
