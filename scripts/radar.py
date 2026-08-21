#!/usr/bin/env python3
"""Motor del Radar de Trading: descarga datos publicos de Binance Futures (o los
lee de un fixture offline), calcula indicadores e imprime un JSON con el resultado
completo (universo, regimen de BTC, candidatas, watchlist, descartadas y huecos
sin datos). No ejecuta ninguna orden, no requiere clave de API.

Uso:
    python radar.py                       -> modo real, llama a Binance
    python radar.py --offline archivo.json -> modo practica, lee el fixture

La skill (SKILL.md) llama a este script, lee el JSON que imprime por stdout y
construye el informe HTML a partir de el. Ningun numero del informe sale de aqui
sin haber pasado por una formula escrita en este archivo.
"""

import argparse
import json
import math
import statistics
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

BASE_URL = "https://fapi.binance.com"
TIMEOUT = 15
MAX_WORKERS = 8

PISO_LIQUIDEZ_USD = 3_000_000
TAMANO_UNIVERSO_ESCANEADO = 40
TAMANO_LISTA_CORTA = 20
MAX_CANDIDATAS = 4
UMBRAL_EMPATE = 1.0

PESOS = {
    "tendencia": 15,
    "estructura": 12,
    "momentum": 10,
    "volumen_relativo": 10,
    "volatilidad": 8,
    "open_interest": 10,
    "funding": 8,
    "regimen_btc": 12,
    "liquidez": 8,
    "risk_reward": 7,
}
assert sum(PESOS.values()) == 100, "los pesos de las dimensiones deben sumar 100"


# ---------------------------------------------------------------------------
# Descarga de datos (modo real)
# ---------------------------------------------------------------------------

def _get(path, params=None, tries=2):
    query = ""
    if params:
        query = "?" + "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{BASE_URL}{path}{query}"
    ultimo_error = None
    for intento in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            ultimo_error = exc
            time.sleep(0.5)
    raise RuntimeError(f"fallo llamando a {url}: {ultimo_error}")


def obtener_ticker_todo():
    return _get("/fapi/v1/ticker/24hr")


def obtener_klines(symbol, interval, limit):
    return _get("/fapi/v1/klines", {"symbol": symbol, "interval": interval, "limit": limit})


def obtener_oi_historico(symbol, period="1h", limit=6):
    try:
        return _get("/futures/data/openInterestHist", {"symbol": symbol, "period": period, "limit": limit})
    except RuntimeError:
        return None


def obtener_funding_historico(symbol, limit=24):
    try:
        return _get("/fapi/v1/fundingRate", {"symbol": symbol, "limit": limit})
    except RuntimeError:
        return None


def obtener_datos_simbolo(symbol):
    """Trae todo lo que hace falta de un simbolo. Se llama en paralelo."""
    return {
        "symbol": symbol,
        "klines_1d": obtener_klines(symbol, "1d", 220),
        "klines_4h": obtener_klines(symbol, "4h", 300),
        "klines_1h": obtener_klines(symbol, "1h", 60),
        "klines_15m": obtener_klines(symbol, "15m", 50),
        "oi_hist": obtener_oi_historico(symbol),
        "funding_hist": obtener_funding_historico(symbol),
    }


def descargar_universo_real():
    ticker_todo = obtener_ticker_todo()
    pares_usdt = [
        t for t in ticker_todo
        if t["symbol"].endswith("USDT") and float(t.get("quoteVolume", 0)) >= PISO_LIQUIDEZ_USD
    ]
    pares_usdt.sort(key=lambda t: float(t["quoteVolume"]), reverse=True)
    universo = pares_usdt[:TAMANO_UNIVERSO_ESCANEADO]
    lista_corta = [t["symbol"] for t in universo[:TAMANO_LISTA_CORTA]]

    simbolos_a_analizar = list(dict.fromkeys(["BTCUSDT"] + lista_corta))

    datos_por_simbolo = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futuros = {pool.submit(obtener_datos_simbolo, s): s for s in simbolos_a_analizar}
        for fut in as_completed(futuros):
            s = futuros[fut]
            try:
                datos_por_simbolo[s] = fut.result()
            except RuntimeError as exc:
                datos_por_simbolo[s] = {"symbol": s, "error": str(exc)}

    return {
        "ticker_todo_usdt": {t["symbol"]: t for t in pares_usdt},
        "universo_completo": [t["symbol"] for t in universo],
        "lista_corta_analizada": simbolos_a_analizar,
        "datos_por_simbolo": datos_por_simbolo,
    }


def cargar_universo_offline(ruta_fixture):
    with open(ruta_fixture, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Indicadores (stdlib puro)
# ---------------------------------------------------------------------------

def cierres(klines):
    return [float(k[4]) for k in klines]


def maximos(klines):
    return [float(k[2]) for k in klines]


def minimos(klines):
    return [float(k[3]) for k in klines]


def volumenes_quote(klines):
    return [float(k[7]) for k in klines]


def ema(valores, periodo):
    if len(valores) < periodo:
        return None
    k = 2 / (periodo + 1)
    e = sum(valores[:periodo]) / periodo
    for v in valores[periodo:]:
        e = v * k + e * (1 - k)
    return e


def ema_serie(valores, periodo):
    """Devuelve la serie completa de EMA (para medir pendiente), no solo el ultimo valor."""
    if len(valores) < periodo:
        return []
    k = 2 / (periodo + 1)
    serie = [sum(valores[:periodo]) / periodo]
    for v in valores[periodo:]:
        serie.append(v * k + serie[-1] * (1 - k))
    return serie


def rsi(valores, periodo=14):
    if len(valores) < periodo + 1:
        return None
    ganancias, perdidas = [], []
    for i in range(1, len(valores)):
        delta = valores[i] - valores[i - 1]
        ganancias.append(max(delta, 0))
        perdidas.append(max(-delta, 0))
    avg_gan = sum(ganancias[:periodo]) / periodo
    avg_per = sum(perdidas[:periodo]) / periodo
    for i in range(periodo, len(ganancias)):
        avg_gan = (avg_gan * (periodo - 1) + ganancias[i]) / periodo
        avg_per = (avg_per * (periodo - 1) + perdidas[i]) / periodo
    if avg_per == 0:
        return 100.0
    rs = avg_gan / avg_per
    return 100 - (100 / (1 + rs))


def macd(valores, rapida=12, lenta=26, senal=9):
    if len(valores) < lenta + senal:
        return None
    ema_r = ema_serie(valores, rapida)
    ema_l = ema_serie(valores, lenta)
    recorte = min(len(ema_r), len(ema_l))
    linea_macd = [ema_r[-recorte:][i] - ema_l[-recorte:][i] for i in range(recorte)]
    if len(linea_macd) < senal:
        return None
    linea_senal = ema_serie(linea_macd, senal)
    if not linea_senal:
        return None
    return {"macd": linea_macd[-1], "senal": linea_senal[-1], "histograma": linea_macd[-1] - linea_senal[-1]}


def atr(klines, periodo=14):
    if len(klines) < periodo + 1:
        return None
    trs = []
    for i in range(1, len(klines)):
        alto = float(klines[i][2])
        bajo = float(klines[i][3])
        cierre_prev = float(klines[i - 1][4])
        tr = max(alto - bajo, abs(alto - cierre_prev), abs(bajo - cierre_prev))
        trs.append(tr)
    if len(trs) < periodo:
        return None
    valor = sum(trs[:periodo]) / periodo
    for tr in trs[periodo:]:
        valor = (valor * (periodo - 1) + tr) / periodo
    return valor


def bollinger_bandwidth(valores, periodo=20, mult=2):
    if len(valores) < periodo:
        return None
    ventana = valores[-periodo:]
    media = sum(ventana) / periodo
    desv = statistics.pstdev(ventana)
    superior = media + mult * desv
    inferior = media - mult * desv
    if media == 0:
        return None
    return (superior - inferior) / media


def serie_bandwidth(valores, periodo=20, mult=2, dias=60):
    """Bandwidth en cada punto de los ultimos `dias` velas, para calcular percentil."""
    salida = []
    inicio = max(periodo, len(valores) - dias)
    for i in range(inicio, len(valores) + 1):
        bw = bollinger_bandwidth(valores[:i], periodo, mult)
        if bw is not None:
            salida.append(bw)
    return salida


def percentil(valor, serie):
    if not serie:
        return None
    menores = sum(1 for v in serie if v <= valor)
    return round(100 * menores / len(serie), 1)


def estructura_por_bloques(klines, n=40, bloque=5):
    """Divide las ultimas `n` velas en bloques de `bloque` y mide que fraccion de
    las transiciones entre bloques confirma estructura alcista (bloques con cierre
    medio cada vez mas alto) o bajista. Promediar por bloques evita que una sola
    vela con ruido normal decida la estructura, que es lo que le pasaba a un
    detector de pivotes vela a vela."""
    velas = klines[-n:]
    cierres_v = cierres(velas)
    if len(cierres_v) < bloque * 3:
        return {"alcista": 0.0, "bajista": 0.0, "bloques": 0}
    promedios = [
        sum(cierres_v[i:i + bloque]) / bloque
        for i in range(0, len(cierres_v) - bloque + 1, bloque)
    ]
    if len(promedios) < 3:
        return {"alcista": 0.0, "bajista": 0.0, "bloques": 0}
    total = len(promedios) - 1
    subidas = sum(1 for i in range(1, len(promedios)) if promedios[i] > promedios[i - 1])
    bajadas = sum(1 for i in range(1, len(promedios)) if promedios[i] < promedios[i - 1])
    return {
        "alcista": round(subidas / total, 2),
        "bajista": round(bajadas / total, 2),
        "bloques": total,
    }


def frescura(klines, minutos_esperados, ahora_ms, tolerancia=2.0):
    if not klines:
        return {"fresco": False, "motivo": "sin velas"}
    ultimo_cierre_ms = klines[-1][6]
    edad_min = (ahora_ms - ultimo_cierre_ms) / 60000
    limite = minutos_esperados * tolerancia
    return {"fresco": edad_min <= limite, "edad_minutos": round(edad_min, 1), "limite_minutos": limite}


# ---------------------------------------------------------------------------
# Regimen de BTC (MarketRegimeEngine)
# ---------------------------------------------------------------------------

def calcular_regimen_btc(datos_btc):
    k1d = datos_btc["klines_1d"]
    k4h = datos_btc["klines_4h"]
    cierres_1d = cierres(k1d)
    cierres_4h = cierres(k4h)

    ema20_1d, ema200_1d = ema(cierres_1d, 20), ema(cierres_1d, 200)
    ema20_4h, ema200_4h = ema(cierres_4h, 20), ema(cierres_4h, 200)
    rsi_1d = rsi(cierres_1d, 14)
    precio = cierres_1d[-1]

    retornos = [
        math.log(cierres_1d[i] / cierres_1d[i - 1])
        for i in range(1, len(cierres_1d)) if cierres_1d[i - 1] > 0
    ]
    vol_14 = statistics.pstdev(retornos[-14:]) if len(retornos) >= 14 else None
    serie_vol_90 = [
        statistics.pstdev(retornos[i - 14:i])
        for i in range(14, len(retornos) + 1)
    ][-90:]
    vol_percentil = percentil(vol_14, serie_vol_90) if vol_14 is not None else None

    cambio_24h = (cierres_1d[-1] / cierres_1d[-2] - 1) * 100 if len(cierres_1d) >= 2 else 0
    cambio_7d = (cierres_1d[-1] / cierres_1d[-8] - 1) * 100 if len(cierres_1d) >= 8 else 0

    pendiente_ema20_1d = None
    serie_ema20_1d = ema_serie(cierres_1d, 20)
    if len(serie_ema20_1d) >= 5:
        pendiente_ema20_1d = (serie_ema20_1d[-1] / serie_ema20_1d[-5] - 1) * 100

    factores = {
        "precio": precio,
        "ema20_1d": ema20_1d,
        "ema200_1d": ema200_1d,
        "ema20_4h": ema20_4h,
        "ema200_4h": ema200_4h,
        "rsi_1d": round(rsi_1d, 1) if rsi_1d is not None else None,
        "vol_14d": round(vol_14, 5) if vol_14 is not None else None,
        "vol_percentil_90d": vol_percentil,
        "cambio_24h_pct": round(cambio_24h, 2),
        "cambio_7d_pct": round(cambio_7d, 2),
        "pendiente_ema20_1d_pct": round(pendiente_ema20_1d, 2) if pendiente_ema20_1d is not None else None,
    }

    if ema200_1d is None or vol_percentil is None:
        return {"regimen": "Neutral", "motivo": "datos insuficientes para el árbol completo (menos de 200 velas 1D)", "factores": factores}

    if cambio_24h <= -6 and vol_percentil >= 85:
        return {"regimen": "Risk-Off", "motivo": f"caída de {cambio_24h:.1f}% en 24h con volatilidad en percentil {vol_percentil}", "factores": factores}

    if vol_percentil >= 85:
        return {"regimen": "High Volatility", "motivo": f"volatilidad realizada 14d en percentil {vol_percentil} de los últimos 90 días", "factores": factores}

    diferencia_emas_1d = (ema20_1d / ema200_1d - 1) * 100

    if precio > ema20_1d > ema200_1d and pendiente_ema20_1d is not None and pendiente_ema20_1d > 0 and rsi_1d is not None and rsi_1d > 55 and cambio_7d > 5:
        return {"regimen": "Strong Bull", "motivo": "precio y EMA20 sobre EMA200 en 1D, pendiente positiva, RSI>55 y +7d fuerte", "factores": factores}

    if precio > ema200_1d and ema20_1d >= ema200_1d:
        return {"regimen": "Bull", "motivo": "precio y EMA20 por encima de EMA200 en 1D", "factores": factores}

    if precio < ema20_1d < ema200_1d and pendiente_ema20_1d is not None and pendiente_ema20_1d < 0 and rsi_1d is not None and rsi_1d < 35 and cambio_7d < -12:
        return {"regimen": "Strong Bear", "motivo": "precio y EMA20 bajo EMA200 en 1D, pendiente negativa, RSI<35 y -7d fuerte", "factores": factores}

    if precio < ema200_1d and ema20_1d <= ema200_1d:
        return {"regimen": "Bear", "motivo": "precio y EMA20 por debajo de EMA200 en 1D", "factores": factores}

    if abs(diferencia_emas_1d) <= 1.5:
        return {"regimen": "Range", "motivo": f"EMA20 y EMA200 en 1D separadas solo {diferencia_emas_1d:.2f}%, sin tendencia clara", "factores": factores}

    return {"regimen": "Neutral", "motivo": "no se cumple ninguna condición clara de tendencia ni de rango", "factores": factores}


IMPLICA_REGIMEN = {
    "Strong Bull": {"favorece": "long", "fuerza": 2},
    "Bull": {"favorece": "long", "fuerza": 1},
    "Neutral": {"favorece": None, "fuerza": 0},
    "Range": {"favorece": None, "fuerza": 0},
    "Bear": {"favorece": "short", "fuerza": 1},
    "Strong Bear": {"favorece": "short", "fuerza": 2},
    "High Volatility": {"favorece": None, "fuerza": 0},
    "Risk-Off": {"favorece": None, "fuerza": -1},
}


# ---------------------------------------------------------------------------
# Puntuacion por simbolo
# ---------------------------------------------------------------------------

def _interp(valor, x0, y0, x1, y1):
    if x1 == x0:
        return y0
    t = (valor - x0) / (x1 - x0)
    t = max(0.0, min(1.0, t))
    return y0 + t * (y1 - y0)


def evaluar_simbolo(symbol, datos, regimen_btc, ticker_info, ahora_ms):
    if "error" in datos:
        return {"symbol": symbol, "descartado": True, "motivo": f"error de datos: {datos['error']}"}

    quote_vol_24h_temprano = float(ticker_info["quoteVolume"]) if ticker_info else None
    if quote_vol_24h_temprano is not None and quote_vol_24h_temprano < PISO_LIQUIDEZ_USD:
        return {"symbol": symbol, "descartado": True, "motivo": f"liquidez insuficiente: {quote_vol_24h_temprano:,.0f} USD en 24h, por debajo del piso de {PISO_LIQUIDEZ_USD:,.0f}"}

    k1d, k4h, k1h = datos["klines_1d"], datos["klines_4h"], datos["klines_1h"]
    k15m = datos.get("klines_15m") or []
    if len(k1d) < 30 or len(k4h) < 30 or len(k1h) < 20:
        return {"symbol": symbol, "descartado": True, "motivo": "historial insuficiente de velas"}

    fresh_4h = frescura(k4h, 240, ahora_ms)
    if not fresh_4h["fresco"]:
        return {"symbol": symbol, "descartado": True, "motivo": f"datos no frescos: última vela 4H con {fresh_4h['edad_minutos']} min de antigüedad"}

    c1d, c4h, c1h = cierres(k1d), cierres(k4h), cierres(k1h)
    precio = c4h[-1]

    ema20_1d, ema200_1d = ema(c1d, 20), ema(c1d, 200)
    ema20_4h, ema200_4h = ema(c4h, 20), ema(c4h, 200)
    if None in (ema20_1d, ema200_1d, ema20_4h, ema200_4h):
        return {"symbol": symbol, "descartado": True, "motivo": "historial insuficiente para EMA200"}

    tendencia_1d = "alcista" if ema20_1d > ema200_1d else "bajista"
    tendencia_4h = "alcista" if ema20_4h > ema200_4h else "bajista"

    if tendencia_1d != tendencia_4h:
        direccion = None
    else:
        direccion = "long" if tendencia_1d == "alcista" else "short"

    dimensiones = {}
    sin_datos = []

    # 1. Tendencia multi-temporalidad
    if direccion is None:
        dimensiones["tendencia"] = {"valor": 20, "detalle": f"1D {tendencia_1d} contradice 4H {tendencia_4h}"}
    else:
        alineacion_total = (precio > ema20_1d and precio > ema200_1d) if direccion == "long" else (precio < ema20_1d and precio < ema200_1d)
        nota = 100 if alineacion_total else 80
        dimensiones["tendencia"] = {"valor": nota, "detalle": f"1D y 4H alineadas en {direccion} (EMA20 vs EMA200)"}

    # 2. Estructura tecnica
    piv = estructura_por_bloques(k4h)
    if piv["bloques"] < 3:
        dimensiones["estructura"] = None
        sin_datos.append("estructura")
    else:
        favor = piv["alcista"] if direccion == "long" else piv["bajista"] if direccion == "short" else max(piv["alcista"], piv["bajista"])
        nota = _interp(favor, 0.4, 20, 0.9, 90)
        dimensiones["estructura"] = {"valor": round(nota, 1), "detalle": f"{int(favor*100)}% de los bloques de 4H confirman la estructura ({piv['bloques']} transiciones)"}

    # 3. Momentum
    rsi_4h = rsi(c4h, 14)
    rsi_1h = rsi(c1h, 14)
    macd_4h = macd(c4h)
    if rsi_4h is None or macd_4h is None:
        dimensiones["momentum"] = None
        sin_datos.append("momentum")
    else:
        macd_favor = (macd_4h["histograma"] > 0) if direccion != "short" else (macd_4h["histograma"] < 0)
        if direccion == "short":
            rsi_favor_fuerte = 30 <= rsi_4h <= 45
            rsi_extremo = rsi_4h < 20
        else:
            rsi_favor_fuerte = 55 <= rsi_4h <= 70
            rsi_extremo = rsi_4h > 80
        if rsi_extremo:
            nota = 40
        elif rsi_favor_fuerte and macd_favor:
            nota = 85
        elif rsi_favor_fuerte or macd_favor:
            nota = 55
        else:
            nota = 25
        rsi_1h_txt = f"{rsi_1h:.1f}" if rsi_1h is not None else "sin datos"
        dimensiones["momentum"] = {"valor": nota, "detalle": f"RSI(4H)={rsi_4h:.1f}, RSI(1H)={rsi_1h_txt}, MACD histograma={'a favor' if macd_favor else 'en contra'}"}

    # 4. Volumen relativo (quote volume 1D vs media de 20 dias)
    vols_1d = volumenes_quote(k1d)
    if len(vols_1d) < 21:
        dimensiones["volumen_relativo"] = None
        sin_datos.append("volumen_relativo")
    else:
        media_20 = sum(vols_1d[-21:-1]) / 20
        ratio = vols_1d[-1] / media_20 if media_20 > 0 else 1.0
        if ratio < 0.8:
            nota = _interp(ratio, 0, 10, 0.8, 20)
        elif ratio < 1.3:
            nota = _interp(ratio, 0.8, 50, 1.3, 55)
        elif ratio < 1.5:
            nota = _interp(ratio, 1.3, 55, 1.5, 80)
        elif ratio < 2.5:
            nota = _interp(ratio, 1.5, 80, 2.5, 100)
        else:
            nota = 100
        dimensiones["volumen_relativo"] = {"valor": round(nota, 1), "detalle": f"volumen 24h es {ratio:.2f}x la media de 20 días"}

    # 5. Volatilidad / compresion
    bw_serie = serie_bandwidth(c4h)
    bw_actual = bw_serie[-1] if bw_serie else None
    if bw_actual is None or len(bw_serie) < 10:
        dimensiones["volatilidad"] = None
        sin_datos.append("volatilidad")
    else:
        pctl = percentil(bw_actual, bw_serie)
        if pctl <= 25:
            nota = _interp(pctl, 0, 90, 25, 80)
        elif pctl <= 40:
            nota = _interp(pctl, 25, 80, 40, 55)
        elif pctl <= 80:
            nota = _interp(pctl, 40, 55, 80, 40)
        else:
            nota = _interp(pctl, 80, 40, 100, 15)
        dimensiones["volatilidad"] = {"valor": round(nota, 1), "detalle": f"Bollinger bandwidth 4H en percentil {pctl} de los últimos 60 días"}

    # 6. Open Interest
    oi_hist = datos.get("oi_hist")
    if not oi_hist or len(oi_hist) < 2:
        dimensiones["open_interest"] = None
        sin_datos.append("open_interest")
    else:
        oi_valores = [float(x["sumOpenInterest"]) for x in oi_hist]
        oi_actual, oi_prev = oi_valores[-1], oi_valores[0]
        cambio_oi_pct = (oi_actual / oi_prev - 1) * 100 if oi_prev > 0 else 0
        # Comparar dos velas sueltas (o dos promedios cortos) es comparar ruido:
        # en una caminata con pasos aleatorios, la incertidumbre entre dos puntos
        # crece con la raiz del numero de velas de separacion, y para una ventana
        # de pocas horas eso supera facilmente el movimiento real. El histograma
        # del MACD ya es una diferencia de dos medias moviles (12 y 26 velas):
        # una medida suavizada de si el momentum reciente es alcista o bajista,
        # y es coherente con lo que ya se muestra en la dimension de momentum.
        if macd_4h is not None:
            cambio_precio_pct = (macd_4h["histograma"] / precio) * 100
            precio_sube = macd_4h["histograma"] > 0
        elif len(c4h) >= 13:
            reciente = sum(c4h[-3:]) / 3
            anterior = sum(c4h[-10:-7]) / 3
            cambio_precio_pct = (reciente / anterior - 1) * 100 if anterior else 0
            precio_sube = cambio_precio_pct > 0
        else:
            cambio_precio_pct = 0
            precio_sube = False
        oi_sube = cambio_oi_pct > 0.5
        oi_baja = cambio_oi_pct < -0.5
        if precio_sube and oi_sube:
            interpretacion, favor_long = "entrada de posiciones nuevas (precio y OI suben)", True
        elif precio_sube and oi_baja:
            interpretacion, favor_long = "short covering (precio sube, OI baja)", False
        elif not precio_sube and oi_sube:
            interpretacion, favor_long = "shorts nuevos (precio baja, OI sube)", False
        elif not precio_sube and oi_baja:
            interpretacion, favor_long = "cierre de posiciones (precio y OI bajan)", None
        else:
            interpretacion, favor_long = "OI estable, sin señal clara", None

        if direccion == "long":
            a_favor = favor_long is True
            en_contra = favor_long is False
        elif direccion == "short":
            a_favor = favor_long is False and oi_sube
            en_contra = favor_long is True
        else:
            a_favor = en_contra = False

        if en_contra:
            nota = 20
        elif favor_long is None:
            nota = 50
        elif a_favor and abs(cambio_oi_pct) >= 3:
            nota = 80
        elif a_favor:
            nota = 65
        else:
            nota = 50
        dimensiones["open_interest"] = {"valor": nota, "detalle": f"OI cambio {cambio_oi_pct:.1f}% — {interpretacion}"}

    # 7. Funding
    funding_hist = datos.get("funding_hist")
    if not funding_hist:
        dimensiones["funding"] = None
        sin_datos.append("funding")
    else:
        tasas = [float(f["fundingRate"]) for f in funding_hist]
        actual = tasas[-1]
        extremo_positivo = actual > 0.0005
        extremo_negativo = actual < -0.0005
        if direccion == "long":
            if extremo_positivo:
                nota = 20
            elif -0.0001 <= actual <= 0.0001:
                nota = 55
            elif actual < 0:
                nota = 80
            else:
                nota = 45
        elif direccion == "short":
            if extremo_negativo:
                nota = 20
            elif -0.0001 <= actual <= 0.0001:
                nota = 55
            elif actual > 0:
                nota = 80
            else:
                nota = 45
        else:
            nota = 50
        dimensiones["funding"] = {"valor": nota, "detalle": f"funding actual {actual*100:.4f}% ({'extremo' if (extremo_positivo or extremo_negativo) else 'normal'})"}

    # 8. Alineacion con regimen BTC
    info_regimen = IMPLICA_REGIMEN.get(regimen_btc["regimen"], {"favorece": None, "fuerza": 0})
    if direccion is None:
        dimensiones["regimen_btc"] = {"valor": 30, "detalle": f"sin dirección propia definida; régimen BTC es {regimen_btc['regimen']}"}
    elif info_regimen["favorece"] == direccion:
        nota = 100 if info_regimen["fuerza"] == 2 else 80
        dimensiones["regimen_btc"] = {"valor": nota, "detalle": f"candidata {direccion} alineada con régimen BTC {regimen_btc['regimen']}"}
    elif info_regimen["favorece"] is None:
        nota = 20 if regimen_btc["regimen"] == "Risk-Off" else 50
        dimensiones["regimen_btc"] = {"valor": nota, "detalle": f"régimen BTC {regimen_btc['regimen']} no da contexto direccional claro"}
    else:
        dimensiones["regimen_btc"] = {"valor": 20, "detalle": f"candidata {direccion} va contra el régimen BTC {regimen_btc['regimen']}"}

    # 9. Liquidez
    quote_vol_24h = float(ticker_info["quoteVolume"]) if ticker_info else vols_1d[-1]
    if quote_vol_24h < 5_000_000:
        nota = _interp(quote_vol_24h, PISO_LIQUIDEZ_USD, 15, 5_000_000, 20)
    elif quote_vol_24h < 20_000_000:
        nota = _interp(quote_vol_24h, 5_000_000, 20, 20_000_000, 50)
    elif quote_vol_24h < 100_000_000:
        nota = _interp(quote_vol_24h, 20_000_000, 50, 100_000_000, 80)
    else:
        nota = min(100, 80 + (quote_vol_24h - 100_000_000) / 20_000_000)
    dimensiones["liquidez"] = {"valor": round(nota, 1), "detalle": f"volumen 24h = {quote_vol_24h:,.0f} USD"}

    # 10. Risk/Reward tecnico
    ventana_corta = k4h[-10:]
    ventana_larga = k4h[-40:]
    atr_4h = atr(k4h, 14)
    # Una mecha diminuta apenas por encima del precio no es una resistencia real,
    # es ruido. Solo cuenta como objetivo si esta a una distancia minima (medida
    # en ATR); si no, se usa la proyeccion tecnica basada en volatilidad.
    distancia_minima = 2.0 * atr_4h if atr_4h else 0
    if direccion == "long":
        invalidacion = min(minimos(ventana_corta))
        objetivos = [m for m in maximos(ventana_larga) if m - precio >= distancia_minima]
        objetivo = min(objetivos) if objetivos else (precio + 2 * atr_4h if atr_4h else None)
        riesgo = precio - invalidacion
        recompensa = (objetivo - precio) if objetivo else None
    elif direccion == "short":
        invalidacion = max(maximos(ventana_corta))
        objetivos = [m for m in minimos(ventana_larga) if precio - m >= distancia_minima]
        objetivo = max(objetivos) if objetivos else (precio - 2 * atr_4h if atr_4h else None)
        riesgo = invalidacion - precio
        recompensa = (precio - objetivo) if objetivo else None
    else:
        invalidacion = objetivo = riesgo = recompensa = None

    if direccion is None or not riesgo or riesgo <= 0 or recompensa is None:
        dimensiones["risk_reward"] = None
        sin_datos.append("risk_reward")
        rr = None
    else:
        rr = recompensa / riesgo
        if rr < 1.5:
            nota = _interp(rr, 0, 5, 1.5, 20)
        elif rr < 2:
            nota = _interp(rr, 1.5, 20, 2, 50)
        elif rr < 3:
            nota = _interp(rr, 2, 50, 3, 80)
        else:
            nota = min(100, 80 + (rr - 3) * 10)
        dimensiones["risk_reward"] = {
            "valor": round(nota, 1),
            "detalle": f"RR ~{rr:.2f} (invalidación {invalidacion:.4f}, objetivo {objetivo:.4f})",
            "invalidacion": invalidacion,
            "objetivo": objetivo,
        }

    # Puntuacion global con reparto de peso de lo que quedo "sin datos"
    peso_disponible = sum(PESOS[d] for d in PESOS if dimensiones.get(d) is not None)
    if peso_disponible == 0:
        return {"symbol": symbol, "descartado": True, "motivo": "ninguna dimensión pudo calcularse"}

    score = 0.0
    for d, peso in PESOS.items():
        info = dimensiones.get(d)
        if info is not None:
            peso_ajustado = peso * (100 / peso_disponible)
            score += info["valor"] * peso_ajustado / 100
    score = round(score, 1)

    if score >= 85:
        letra = "A+"
    elif score >= 70:
        letra = "A"
    elif score >= 55:
        letra = "B"
    elif score >= 40:
        letra = "C"
    else:
        letra = "D"

    # Nivel de riesgo, independiente de la nota de calidad
    atr_pct = (atr_4h / precio * 100) if atr_4h else None
    funding_extremo = dimensiones["funding"] is not None and dimensiones["funding"]["valor"] == 20
    riesgo_alto = (atr_pct is not None and atr_pct > 4) or dimensiones["liquidez"]["valor"] <= 20 or funding_extremo
    riesgo_bajo = (atr_pct is not None and atr_pct < 2) and dimensiones["liquidez"]["valor"] >= 80 and not funding_extremo
    nivel_riesgo = "Alto" if riesgo_alto else ("Bajo" if riesgo_bajo else "Medio")

    # Estado de breakout (regla: extendido nunca es candidata)
    maximo_20 = max(maximos(k4h[-21:-1])) if len(k4h) >= 21 else None
    minimo_20 = min(minimos(k4h[-21:-1])) if len(k4h) >= 21 else None
    estado_breakout = "sin ruptura reciente"
    breakout_extendido = False
    if direccion == "long" and maximo_20:
        extension_pct = (precio / maximo_20 - 1) * 100
        if precio > maximo_20 and extension_pct > 6:
            estado_breakout, breakout_extendido = f"breakout extendido (+{extension_pct:.1f}% sobre el máximo de 20 velas, sin retest)", True
        elif precio > maximo_20:
            estado_breakout = "breakout confirmado"
    elif direccion == "short" and minimo_20:
        extension_pct = (minimo_20 / precio - 1) * 100
        if precio < minimo_20 and extension_pct > 6:
            estado_breakout, breakout_extendido = f"breakout extendido (+{extension_pct:.1f}% bajo el mínimo de 20 velas, sin retest)", True
        elif precio < minimo_20:
            estado_breakout = "breakout confirmado"

    # Horizonte corto (estructura 1H, referencia de horas) -- ademas del
    # horizonte de la dimension Risk/Reward (estructura 4H, referencia de
    # dias). No es una promesa de cuanto va a tardar en resolverse: es de que
    # temporalidad sale el nivel, y esa temporalidad suele tardar mas o menos
    # en jugarse.
    horizonte_corto = None
    if direccion is not None and len(c1h) >= 24:
        ventana_corta_1h = k1h[-8:]
        ventana_larga_1h = k1h[-24:]
        atr_1h = atr(k1h, 14)
        distancia_minima_1h = 2.0 * atr_1h if atr_1h else 0
        if direccion == "long":
            inval_1h = min(minimos(ventana_corta_1h))
            obj_cand_1h = [m for m in maximos(ventana_larga_1h) if m - precio >= distancia_minima_1h]
            obj_1h = min(obj_cand_1h) if obj_cand_1h else (precio + 2 * atr_1h if atr_1h else None)
            riesgo_1h = precio - inval_1h
            recompensa_1h = (obj_1h - precio) if obj_1h else None
        else:
            inval_1h = max(maximos(ventana_corta_1h))
            obj_cand_1h = [m for m in minimos(ventana_larga_1h) if precio - m >= distancia_minima_1h]
            obj_1h = max(obj_cand_1h) if obj_cand_1h else (precio - 2 * atr_1h if atr_1h else None)
            riesgo_1h = inval_1h - precio
            recompensa_1h = (precio - obj_1h) if obj_1h else None
        if riesgo_1h and riesgo_1h > 0 and recompensa_1h is not None:
            rr_1h = recompensa_1h / riesgo_1h
            horizonte_corto = {
                "invalidacion": inval_1h,
                "objetivo": obj_1h,
                "rr": round(rr_1h, 2),
                "detalle": f"estructura 1H (referencia horas): RR ~{rr_1h:.2f} (invalidación {inval_1h:.4f}, objetivo {obj_1h:.4f})",
            }

    # Horizonte scalp (estructura 15m, referencia de 15-30 minutos) -- para
    # operativa rapida. Ventanas mucho mas cortas que el horizonte corto: 1
    # hora de historial para la invalidacion, 4 horas para buscar objetivo.
    horizonte_scalp = None
    c15m = cierres(k15m) if k15m else []
    if direccion is not None and len(c15m) >= 20:
        ventana_corta_15m = k15m[-4:]
        ventana_larga_15m = k15m[-16:]
        atr_15m = atr(k15m, 14)
        distancia_minima_15m = 1.5 * atr_15m if atr_15m else 0
        if direccion == "long":
            inval_15m = min(minimos(ventana_corta_15m))
            obj_cand_15m = [m for m in maximos(ventana_larga_15m) if m - precio >= distancia_minima_15m]
            obj_15m = min(obj_cand_15m) if obj_cand_15m else (precio + 1.5 * atr_15m if atr_15m else None)
            riesgo_15m = precio - inval_15m
            recompensa_15m = (obj_15m - precio) if obj_15m else None
        else:
            inval_15m = max(maximos(ventana_corta_15m))
            obj_cand_15m = [m for m in minimos(ventana_larga_15m) if precio - m >= distancia_minima_15m]
            obj_15m = max(obj_cand_15m) if obj_cand_15m else (precio - 1.5 * atr_15m if atr_15m else None)
            riesgo_15m = inval_15m - precio
            recompensa_15m = (precio - obj_15m) if obj_15m else None
        if riesgo_15m and riesgo_15m > 0 and recompensa_15m is not None:
            rr_15m = recompensa_15m / riesgo_15m
            horizonte_scalp = {
                "invalidacion": inval_15m,
                "objetivo": obj_15m,
                "rr": round(rr_15m, 2),
                "detalle": f"estructura 15m (referencia 15-30 min): RR ~{rr_15m:.2f} (invalidación {inval_15m:.4f}, objetivo {obj_15m:.4f})",
            }

    # Candidata "patrimonial": estructura fuerte tanto en 1H como en 4H y
    # alineada con el regimen de BTC -- el tipo de caso donde, si el corto
    # plazo llega a objetivo, tiene sentido evaluar tomar parcial ahi y dejar
    # el resto corriendo con el horizonte de 4H. Es una senal para que el
    # usuario lo evalue, no una instruccion de que hacerlo.
    candidata_patrimonial = bool(
        horizonte_corto is not None
        and dimensiones.get("risk_reward") is not None
        and dimensiones.get("tendencia") and dimensiones["tendencia"]["valor"] >= 100
        and dimensiones.get("estructura") and dimensiones["estructura"]["valor"] >= 70
        and dimensiones.get("regimen_btc") and dimensiones["regimen_btc"]["valor"] >= 80
    )

    return {
        "symbol": symbol,
        "descartado": False,
        "direccion": direccion,
        "precio": precio,
        "score": score,
        "letra": letra,
        "nivel_riesgo": nivel_riesgo,
        "estado_breakout": estado_breakout,
        "breakout_extendido": breakout_extendido,
        "dimensiones": dimensiones,
        "sin_datos": sin_datos,
        "peso_disponible_pct": round(peso_disponible, 1),
        "horizonte_corto": horizonte_corto,
        "horizonte_scalp": horizonte_scalp,
        "candidata_patrimonial": candidata_patrimonial,
        "atr_pct_4h": round(atr_pct, 3) if atr_pct is not None else None,
    }


# ---------------------------------------------------------------------------
# Orquestacion
# ---------------------------------------------------------------------------

def construir_radar(universo):
    datos_por_simbolo = universo["datos_por_simbolo"]
    ticker = universo.get("ticker_todo_usdt", {})

    if "BTCUSDT" not in datos_por_simbolo or "error" in datos_por_simbolo.get("BTCUSDT", {}):
        raise RuntimeError("no se pudieron obtener los datos de BTCUSDT: sin esto no hay régimen de mercado")

    regimen_btc = calcular_regimen_btc(datos_por_simbolo["BTCUSDT"])
    ahora_ms = universo.get("ahora_ms") or (time.time() * 1000)

    evaluaciones = []
    for symbol in universo["lista_corta_analizada"]:
        if symbol == "BTCUSDT":
            continue
        datos = datos_por_simbolo.get(symbol, {"symbol": symbol, "error": "sin datos descargados"})
        ev = evaluar_simbolo(symbol, datos, regimen_btc, ticker.get(symbol), ahora_ms)
        evaluaciones.append(ev)

    descartadas = [e for e in evaluaciones if e.get("descartado")]
    validas = [e for e in evaluaciones if not e.get("descartado")]

    direccionales = [e for e in validas if e["direccion"] is not None]
    no_direccionales = [e for e in validas if e["direccion"] is None]

    elegibles = [e for e in direccionales if not e["breakout_extendido"]]
    excluidas_por_extension = [e for e in direccionales if e["breakout_extendido"]]

    elegibles.sort(key=lambda e: e["score"], reverse=True)

    candidatas = []
    empate_pendiente = None
    if len(elegibles) > MAX_CANDIDATAS:
        corte = elegibles[MAX_CANDIDATAS - 1]["score"]
        siguiente = elegibles[MAX_CANDIDATAS]["score"]
        if abs(corte - siguiente) < UMBRAL_EMPATE:
            # Solo los que compiten de verdad por el ultimo puesto abierto (desde
            # la posicion del corte en adelante). Los que ya entraron con holgura
            # en el top no se mezclan en la pregunta aunque su nota ronde la misma
            # zona.
            empatados = [e for e in elegibles[MAX_CANDIDATAS - 1:] if abs(e["score"] - corte) < UMBRAL_EMPATE]
            candidatas = elegibles[: MAX_CANDIDATAS - 1]
            empate_pendiente = empatados
        else:
            candidatas = elegibles[:MAX_CANDIDATAS]
    else:
        candidatas = elegibles

    en_candidatas = {c["symbol"] for c in candidatas}
    watchlist = [e for e in elegibles if e["symbol"] not in en_candidatas and e["score"] >= 40]
    resto_d = [e for e in elegibles if e["symbol"] not in en_candidatas and e["score"] < 40]

    return {
        "generado_en_utc": datetime.now(timezone.utc).isoformat(),
        "regimen_btc": regimen_btc,
        "universo_escaneado": len(universo["universo_completo"]),
        "lista_corta_analizada": len(universo["lista_corta_analizada"]) - 1,
        "candidatas": candidatas,
        "empate_pendiente": empate_pendiente,
        "watchlist": sorted(watchlist, key=lambda e: e["score"], reverse=True),
        "conteo_d_tier": len(resto_d) + len(no_direccionales),
        # El informe solo muestra el conteo de D-tier (para no inflarlo), pero
        # estas dos listas quedan en el JSON de respaldo para poder auditar
        # cualquier caso concreto sin tener que releer de cero.
        "resto_d_tier_detalle": sorted(
            [{"symbol": e["symbol"], "score": e["score"], "direccion": e["direccion"]} for e in resto_d],
            key=lambda e: e["score"], reverse=True,
        ),
        "sin_direccion_detalle": [
            {"symbol": e["symbol"], "motivo": "1D y 4H en tendencias opuestas, sin ventaja direccional clara"}
            for e in no_direccionales
        ],
        "excluidas_por_extension": excluidas_por_extension,
        "descartadas": descartadas,
        "pesos": PESOS,
    }


def main():
    # En Windows, si la salida se redirige a un archivo, Python puede elegir la
    # codificacion de la consola (cp1252) en vez de UTF-8 y romper los acentos.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", metavar="ARCHIVO", help="ruta a un fixture JSON en vez de llamar a Binance")
    args = parser.parse_args()

    if args.offline:
        universo = cargar_universo_offline(args.offline)
    else:
        universo = descargar_universo_real()

    resultado = construir_radar(universo)
    print(json.dumps(resultado, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
