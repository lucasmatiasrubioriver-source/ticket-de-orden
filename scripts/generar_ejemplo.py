#!/usr/bin/env python3
"""Genera ejemplos/snapshot-practica.json: un universo ficticio (simbolos que no
existen en Binance real) con 12 casos plantados a proposito, con la misma forma
exacta que los datos reales de Binance Futures. Lo usa scripts/radar.py --offline
para que el kit se pueda probar sin conexion y sin arriesgar nada.

Se ejecuta una sola vez durante la construccion del kit (Paso 6). No lo usa el
usuario final.
"""

import copy
import json
import random
import time

MS_POR_MIN = 60_000
MS_POR_HORA = 60 * MS_POR_MIN
MS_POR_DIA = 24 * MS_POR_HORA


def generar_velas(n, intervalo_ms, precio_inicial, drift, vol, semilla,
                   ahora_ms, volumen_base=5_000_000, volumen_vol=0.35,
                   desplazamiento_ms=0):
    rnd = random.Random(semilla)
    inicio = ahora_ms - n * intervalo_ms + desplazamiento_ms
    velas = []
    precio = precio_inicial
    for i in range(n):
        open_ = precio
        cambio = rnd.gauss(drift, vol)
        close = max(open_ * (1 + cambio), 0.0001)
        mecha_alta = abs(rnd.gauss(0, vol * 0.4))
        mecha_baja = abs(rnd.gauss(0, vol * 0.4))
        alto = max(open_, close) * (1 + mecha_alta)
        bajo = min(open_, close) * (1 - mecha_baja)
        vol_vela = max(volumen_base * (1 + rnd.gauss(0, volumen_vol)), volumen_base * 0.1)
        open_time = inicio + i * intervalo_ms
        close_time = open_time + intervalo_ms - 1
        quote_volume = vol_vela
        base_volume = quote_volume / close if close else 0
        velas.append([
            open_time, f"{open_:.6f}", f"{alto:.6f}", f"{bajo:.6f}", f"{close:.6f}",
            f"{base_volume:.3f}", close_time, f"{quote_volume:.2f}",
            int(1000 + vol_vela / 5000), f"{base_volume * 0.55:.3f}",
            f"{quote_volume * 0.55:.2f}", "0",
        ])
        precio = close
    return velas


def aplicar_sesgo_reciente(velas, pct_total, n=25):
    """Suma un empuje direccional suave y creciente a las ultimas n velas, para
    que el RSI/MACD/estructura reflejen una tendencia clara y no queden ahogados
    por el ruido normal vela a vela (con drift pequeno frente a la volatilidad,
    RSI(14) se queda cerca de 50 sin importar cuantas velas se generen: hace
    falta que el TRAMO RECIENTE tenga una direccion consistente de verdad).
    Escala las 4 columnas de precio de cada vela por igual, asi que conserva la
    forma relativa de cada vela (mecha alta/baja, cuerpo)."""
    n = min(n, len(velas))
    for i in range(1, n + 1):
        idx = -i
        avance = (n - i + 1) / n  # 0 al principio del tramo, 1 en la ultima vela
        factor = 1 + pct_total * avance
        for campo in (1, 2, 3, 4):
            velas[idx][campo] = f"{float(velas[idx][campo]) * factor:.6f}"
    return velas


def aplicar_salto_ruptura(velas, extra_pct):
    """Convierte la ultima vela en un impulso de ruptura fuerte y extendido, sin
    tocar las velas anteriores (para que el maximo de las ultimas 20 velas -que
    excluye la ultima- siga reflejando el nivel real que se rompio, y no quede
    contaminado por el propio salto)."""
    ultima = velas[-1]
    apertura = float(ultima[1])
    cierre_nuevo = apertura * (1 + extra_pct)
    ultima[4] = f"{cierre_nuevo:.6f}"
    ultima[2] = f"{cierre_nuevo * 1.004:.6f}"
    ultima[3] = f"{apertura * 0.998:.6f}"
    return velas


def desplazar_tiempo(velas, delta_ms):
    for v in velas:
        v[0] += delta_ms
        v[6] += delta_ms
    return velas


def generar_oi_hist(symbol, valores, ahora_ms, periodo_ms=MS_POR_HORA):
    n = len(valores)
    salida = []
    for i, v in enumerate(valores):
        ts = ahora_ms - (n - 1 - i) * periodo_ms
        salida.append({
            "symbol": symbol,
            "sumOpenInterest": f"{v:.3f}",
            "sumOpenInterestValue": f"{v * 100:.2f}",
            "timestamp": ts,
        })
    return salida


def generar_funding_hist(symbol, tasas, ahora_ms, periodo_ms=8 * MS_POR_HORA):
    n = len(tasas)
    salida = []
    for i, r in enumerate(tasas):
        ts = ahora_ms - (n - 1 - i) * periodo_ms
        salida.append({
            "symbol": symbol,
            "fundingTime": ts,
            "fundingRate": f"{r:.6f}",
            "markPrice": "0",
            "rateType": "Regular",
        })
    return salida


def construir_simbolo(symbol, ahora_ms, precio_inicial, drift_1d, vol_1d,
                       drift_4h, vol_4h, semilla, volumen_base=8_000_000,
                       oi_valores=None, funding_tasas=None,
                       ruptura_final_pct=None, desplazamiento_4h_ms=0,
                       quote_volume_24h=None, sesgo_1d=None, sesgo_4h=None):
    k1d = generar_velas(220, MS_POR_DIA, precio_inicial, drift_1d, vol_1d, semilla, ahora_ms, volumen_base * 6)
    k4h = generar_velas(300, 4 * MS_POR_HORA, precio_inicial, drift_4h, vol_4h, semilla + 1, ahora_ms, volumen_base)

    if sesgo_1d:
        pct, n = sesgo_1d
        k1d = aplicar_sesgo_reciente(k1d, pct, n)
    if sesgo_4h:
        pct, n = sesgo_4h
        k4h = aplicar_sesgo_reciente(k4h, pct, n)

    k1h = generar_velas(60, MS_POR_HORA, float(k4h[-1][4]), drift_4h / 4, vol_4h / 2, semilla + 2, ahora_ms, volumen_base / 4)
    if sesgo_4h:
        pct, _ = sesgo_4h
        k1h = aplicar_sesgo_reciente(k1h, pct * 0.3, min(20, len(k1h)))

    # El cierre de 1H y el de 4H representan el mismo "ahora": en datos reales
    # de Binance no pueden divergir. El sesgo de 1H (arriba) puede alejar su
    # cierre final del de 4H -- se reescala toda la serie de 1H para que
    # termine exactamente en el precio de 4H, conservando su forma interna.
    factor_ajuste = float(k4h[-1][4]) / float(k1h[-1][4])
    if abs(factor_ajuste - 1) > 1e-9:
        for vela in k1h:
            for campo in (1, 2, 3, 4):
                vela[campo] = f"{float(vela[campo]) * factor_ajuste:.6f}"

    k15m = generar_velas(50, 15 * MS_POR_MIN, float(k1h[-1][4]), drift_4h / 16, vol_4h / 4, semilla + 3, ahora_ms, volumen_base / 16)
    # Mismo motivo que arriba: el cierre de 15m tiene que calzar con el de 1H.
    factor_ajuste_15m = float(k1h[-1][4]) / float(k15m[-1][4])
    if abs(factor_ajuste_15m - 1) > 1e-9:
        for vela in k15m:
            for campo in (1, 2, 3, 4):
                vela[campo] = f"{float(vela[campo]) * factor_ajuste_15m:.6f}"

    if ruptura_final_pct:
        k4h = aplicar_salto_ruptura(k4h, ruptura_final_pct)

    if desplazamiento_4h_ms:
        k4h = desplazar_tiempo(k4h, desplazamiento_4h_ms)

    precio_final = float(k4h[-1][4])

    datos = {
        "symbol": symbol,
        "klines_1d": k1d,
        "klines_4h": k4h,
        "klines_1h": k1h,
        "klines_15m": k15m,
        "oi_hist": generar_oi_hist(symbol, oi_valores, ahora_ms) if oi_valores else None,
        "funding_hist": generar_funding_hist(symbol, funding_tasas, ahora_ms) if funding_tasas else None,
    }

    qv = quote_volume_24h if quote_volume_24h is not None else volumen_base * 24
    ticker = {
        "symbol": symbol,
        "lastPrice": f"{precio_final:.6f}",
        "quoteVolume": f"{qv:.2f}",
        "priceChangePercent": f"{(precio_final / precio_inicial - 1) * 100:.2f}",
    }
    return datos, ticker


def main():
    ahora_ms = int(time.time() * 1000)
    datos_por_simbolo = {}
    ticker_todo = {}

    # BTCUSDT: regimen "Bull" moderado (no "Strong Bull") para verificar a mano
    # el arbol de decision en el Paso 7.
    btc, btc_ticker = construir_simbolo(
        "BTCUSDT", ahora_ms, precio_inicial=45_000,
        drift_1d=0.0016, vol_1d=0.018,
        drift_4h=0.0007, vol_4h=0.011,
        semilla=1001,
        oi_valores=[210_000, 211_500, 212_800, 213_100, 214_000, 215_200],
        funding_tasas=[0.00005] * 20 + [0.00008, 0.00009, 0.0001, 0.00012],
        volumen_base=900_000_000, quote_volume_24h=28_000_000_000,
    )
    datos_por_simbolo["BTCUSDT"] = btc
    ticker_todo["BTCUSDT"] = btc_ticker

    # 1. ZENUSDT — tendencia limpia alcista, todo alineado (caso de control positivo).
    # Volatilidad baja a proposito: una tendencia limpia de verdad es asi (poco
    # ruido vela a vela), no una caminata aleatoria con deriva que por casualidad
    # termina arriba.
    zen, zen_t = construir_simbolo(
        "ZENUSDT", ahora_ms, precio_inicial=4.20,
        drift_1d=0.0032, vol_1d=0.009,
        drift_4h=0.0013, vol_4h=0.007,
        semilla=2001,
        oi_valores=[8_200_000, 8_260_000, 8_310_000, 8_450_000, 8_600_000, 8_800_000],
        funding_tasas=[0.00006] * 20 + [0.00001, -0.00012, -0.00016, -0.00018],
        volumen_base=14_000_000, quote_volume_24h=310_000_000,
        sesgo_1d=(0.10, 25), sesgo_4h=(0.07, 24),
    )
    datos_por_simbolo["ZENUSDT"] = zen
    ticker_todo["ZENUSDT"] = zen_t

    # 2. KAIROSUSDT — tendencia limpia bajista (control: sin sesgo permanente a largos)
    kairos, kairos_t = construir_simbolo(
        "KAIROSUSDT", ahora_ms, precio_inicial=18.50,
        drift_1d=-0.0028, vol_1d=0.009,
        drift_4h=-0.0011, vol_4h=0.007,
        semilla=2101,
        oi_valores=[5_100_000, 5_180_000, 5_260_000, 5_390_000, 5_500_000, 5_650_000],
        funding_tasas=[0.00004] * 22 + [0.00025, 0.0003],
        volumen_base=9_500_000, quote_volume_24h=190_000_000,
        sesgo_1d=(-0.10, 25), sesgo_4h=(-0.07, 24),
    )
    datos_por_simbolo["KAIROSUSDT"] = kairos
    ticker_todo["KAIROSUSDT"] = kairos_t

    # 3. NORTEUSDT — breakout extendido, debe excluirse de candidatas (regla #19)
    norte, norte_t = construir_simbolo(
        "NORTEUSDT", ahora_ms, precio_inicial=2.10,
        drift_1d=0.0026, vol_1d=0.021,
        drift_4h=0.0011, vol_4h=0.013,
        semilla=2201,
        oi_valores=[3_100_000, 3_150_000, 3_400_000, 3_800_000, 4_200_000, 4_700_000],
        funding_tasas=[0.00005] * 22 + [0.0002, 0.00025],
        volumen_base=7_000_000, quote_volume_24h=95_000_000,
        sesgo_1d=(0.08, 20), sesgo_4h=(0.05, 20),
        ruptura_final_pct=0.11,
    )
    datos_por_simbolo["NORTEUSDT"] = norte
    ticker_todo["NORTEUSDT"] = norte_t

    # 4. VELUSUSDT — 1D alcista contra 4H bajista (contradiccion), no debe ser candidata
    velus, velus_t = construir_simbolo(
        "VELUSUSDT", ahora_ms, precio_inicial=0.85,
        drift_1d=0.0022, vol_1d=0.020,
        drift_4h=-0.0016, vol_4h=0.014,
        semilla=2301,
        oi_valores=[2_800_000, 2_820_000, 2_790_000, 2_810_000, 2_795_000, 2_805_000],
        funding_tasas=[0.00002] * 24,
        volumen_base=6_500_000, quote_volume_24h=68_000_000,
        sesgo_1d=(0.08, 20), sesgo_4h=(-0.08, 20),
    )
    datos_por_simbolo["VELUSUSDT"] = velus
    ticker_todo["VELUSUSDT"] = velus_t

    # 5. ORBIXUSDT — sin datos de Open Interest (oi_hist=None), tendencia moderada
    orbix, orbix_t = construir_simbolo(
        "ORBIXUSDT", ahora_ms, precio_inicial=1.35,
        drift_1d=0.0014, vol_1d=0.022,
        drift_4h=0.0005, vol_4h=0.015,
        semilla=2401,
        oi_valores=None,
        funding_tasas=[0.00003] * 24,
        volumen_base=5_500_000, quote_volume_24h=52_000_000,
        sesgo_1d=(0.05, 20), sesgo_4h=(0.03, 18),
    )
    datos_por_simbolo["ORBIXUSDT"] = orbix
    ticker_todo["ORBIXUSDT"] = orbix_t

    # 6. FUNDEXUSDT — tendencia alcista pero funding extremo (crowding), debe penalizar
    fundex, fundex_t = construir_simbolo(
        "FUNDEXUSDT", ahora_ms, precio_inicial=6.80,
        drift_1d=0.0030, vol_1d=0.009,
        drift_4h=0.0012, vol_4h=0.007,
        semilla=2501,
        oi_valores=[4_200_000, 4_260_000, 4_350_000, 4_500_000, 4_650_000, 4_800_000],
        funding_tasas=[0.0004] * 20 + [0.0009, 0.0012, 0.0015, 0.0016],
        volumen_base=11_000_000, quote_volume_24h=140_000_000,
        sesgo_1d=(0.09, 25), sesgo_4h=(0.06, 24),
    )
    datos_por_simbolo["FUNDEXUSDT"] = fundex
    ticker_todo["FUNDEXUSDT"] = fundex_t

    # 7. TENUEUSDT — liquidez por debajo del piso (3M), debe quedar fuera del universo
    tenue, tenue_t = construir_simbolo(
        "TENUEUSDT", ahora_ms, precio_inicial=0.045,
        drift_1d=0.0018, vol_1d=0.025,
        drift_4h=0.0008, vol_4h=0.016,
        semilla=2601,
        oi_valores=[400_000, 405_000, 410_000, 408_000, 412_000, 415_000],
        funding_tasas=[0.0001] * 24,
        volumen_base=70_000, quote_volume_24h=1_800_000,
    )
    datos_por_simbolo["TENUEUSDT"] = tenue
    ticker_todo["TENUEUSDT"] = tenue_t

    # 8. STALEUSDT — vela 4H vieja (10h), debe excluirse por DataFreshnessGuard
    stale, stale_t = construir_simbolo(
        "STALEUSDT", ahora_ms, precio_inicial=3.10,
        drift_1d=0.0020, vol_1d=0.020,
        drift_4h=0.0009, vol_4h=0.013,
        semilla=2701,
        oi_valores=[1_900_000, 1_920_000, 1_950_000, 1_980_000, 2_000_000, 2_050_000],
        funding_tasas=[0.00005] * 24,
        volumen_base=8_000_000, quote_volume_24h=85_000_000,
        desplazamiento_4h_ms=-10 * MS_POR_HORA,
    )
    datos_por_simbolo["STALEUSDT"] = stale
    ticker_todo["STALEUSDT"] = stale_t

    # 9. RANGOUSDT — sin ventaja direccional (EMA20~EMA200, RSI~50), debe ser D
    rango, rango_t = construir_simbolo(
        "RANGOUSDT", ahora_ms, precio_inicial=12.0,
        drift_1d=0.0001, vol_1d=0.016,
        drift_4h=0.00003, vol_4h=0.011,
        semilla=2801,
        oi_valores=[3_300_000, 3_305_000, 3_295_000, 3_310_000, 3_298_000, 3_302_000],
        funding_tasas=[0.00001] * 24,
        volumen_base=6_000_000, quote_volume_24h=58_000_000,
    )
    datos_por_simbolo["RANGOUSDT"] = rango
    ticker_todo["RANGOUSDT"] = rango_t

    # 10. PLVXUSDT — candidata B intermedia, mitad del empate del puesto 4
    plvx, plvx_t = construir_simbolo(
        "PLVXUSDT", ahora_ms, precio_inicial=2.65,
        drift_1d=0.0030, vol_1d=0.020,
        drift_4h=0.0014, vol_4h=0.013,
        semilla=2905,
        oi_valores=[2_600_000, 2_630_000, 2_600_000, 2_610_000, 2_590_000, 2_605_000],
        funding_tasas=[0.00004] * 24,
        volumen_base=7_200_000, quote_volume_24h=64_000_000,
        sesgo_1d=(0.02, 20), sesgo_4h=(0.015, 18),
    )
    datos_por_simbolo["PLVXUSDT"] = plvx
    ticker_todo["PLVXUSDT"] = plvx_t

    # 11. ARDENUSDT — clon casi identico de PLVXUSDT (empate exacto a proposito):
    # el kit debe preguntar cual priorizar, no decidir solo.
    arden = copy.deepcopy(plvx)
    arden["symbol"] = "ARDENUSDT"
    factor = 1.00004
    for serie in ("klines_1d", "klines_4h", "klines_1h", "klines_15m"):
        for vela in arden[serie]:
            for campo in (1, 2, 3, 4):
                vela[campo] = f"{float(vela[campo]) * factor:.6f}"
    for entrada in arden["oi_hist"]:
        entrada["symbol"] = "ARDENUSDT"
    for entrada in arden["funding_hist"]:
        entrada["symbol"] = "ARDENUSDT"
    datos_por_simbolo["ARDENUSDT"] = arden
    arden_t = dict(plvx_t)
    arden_t["symbol"] = "ARDENUSDT"
    arden_t["lastPrice"] = f"{float(plvx_t['lastPrice']) * factor:.6f}"
    ticker_todo["ARDENUSDT"] = arden_t

    lista_corta = [
        "BTCUSDT", "ZENUSDT", "KAIROSUSDT", "NORTEUSDT", "VELUSUSDT",
        "ORBIXUSDT", "FUNDEXUSDT", "TENUEUSDT", "STALEUSDT", "RANGOUSDT",
        "PLVXUSDT", "ARDENUSDT",
    ]

    # Simbolos "de relleno": aparecieron en el escaneo (FILTER) pero no llegaron
    # al analisis en profundidad (ANALYZE). Solo existen como ticker, ilustran
    # el embudo OBSERVE -> FILTER -> ANALYZE del kit.
    relleno = ["PIVOTUSDT", "MESETAUSDT", "DERIVAUSDT", "CUANTOUSDT"]
    for i, sym in enumerate(relleno):
        ticker_todo[sym] = {
            "symbol": sym,
            "lastPrice": "1.0000",
            "quoteVolume": f"{(4_500_000 - i * 300_000):.2f}",
            "priceChangePercent": "0.50",
        }

    universo = {
        "ahora_ms": ahora_ms,
        "ticker_todo_usdt": ticker_todo,
        "universo_completo": lista_corta[1:] + relleno,
        "lista_corta_analizada": lista_corta,
        "datos_por_simbolo": datos_por_simbolo,
    }

    with open("ejemplos/snapshot-practica.json", "w", encoding="utf-8") as fh:
        json.dump(universo, fh, indent=2)

    print(f"Generado ejemplos/snapshot-practica.json con {len(lista_corta) - 1} simbolos ficticios + BTCUSDT (contexto), ahora_ms={ahora_ms}")


if __name__ == "__main__":
    main()
