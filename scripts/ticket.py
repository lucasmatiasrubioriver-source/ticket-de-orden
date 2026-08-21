#!/usr/bin/env python3
"""Ticket de orden: llama a radar.py (motor de mercado, sin cambios), le agrega
tamano de posicion segun el riesgo del usuario y un segundo objetivo tecnico, y
lo entrega en formato de ficha compacta -- sin parrafos, solo los numeros. No
ejecuta nada ni se conecta con ninguna cuenta.

Dos modos:

  python ticket.py --equity 500 --riesgo-pct 0.5
      Ticket de la mejor candidata ahora mismo (o "SIN OPERAR" si ninguna
      cumple el minimo de calidad).

  python ticket.py --vigilancia --equity 500 --riesgo-pct 0.5
      Compara contra la ultima revision guardada (.claude/ultimo-radar.json) y
      dice si hay algo nuevo que valga la pena mirar. No imprime ticket si no
      cambio nada relevante.

Ambos aceptan --offline archivo.json para el modo practica.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

CARPETA_SCRIPT = os.path.dirname(os.path.abspath(__file__))
CARPETA_KIT = os.path.dirname(CARPETA_SCRIPT)
ARCHIVO_ESTADO = os.path.join(CARPETA_KIT, ".claude", "ultimo-radar.json")
ARCHIVO_HISTORIAL = os.path.join(CARPETA_KIT, "workspace", "historial-vigilancia.jsonl")

BASE_URL_BINANCE = "https://fapi.binance.com"
URL_RSS_NOTICIAS = "https://cointelegraph.com/rss"
TIMEOUT_RED = 10

UMBRAL_TICKET = 55  # B o mejor. Por debajo de esto el veredicto es "sin operar".
# Extensiones de Fibonacci desde TP1 para TP2 y TP3 -- proporciones tecnicas
# estandar, no numeros elegidos al azar.
EXTENSION_TP2 = 1.618
EXTENSION_TP3 = 2.618
HORAS_COOLDOWN_ALERTA = 6  # no volver a avisar del mismo simbolo antes de esto,
                            # para que un mercado picado no mande un aviso por hora

# Vigencia del ticket: cuanto puede pasar desde que se genero hasta que lo
# cargues antes de que los precios ya no reflejen el mercado. El usuario
# tarda ~5-7 minutos en cargar una orden a mano; se deja margen sobre eso,
# mas ajustado cuanto mas corto el horizonte del plan.
VIGENCIA_MINUTOS_SCALP = 3
VIGENCIA_MINUTOS_CORTO = 15
VIGENCIA_MINUTOS_MEDIO = 60

LEVERAGES_A_MOSTRAR = [1, 3, 5]
MERCADO_KIT = "Futuros USDⓈ-M Perpetual"  # este kit solo escanea esto -- nunca Spot

MARGEN_BINANCE = "Aislado"  # regla fija del propio sistema del usuario: nunca
                              # Cross por defecto, salvo razon explicita.


def correr_radar(offline=None):
    cmd = [sys.executable, os.path.join(CARPETA_SCRIPT, "radar.py")]
    if offline:
        cmd += ["--offline", offline]
    resultado = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if resultado.returncode != 0:
        raise RuntimeError(f"radar.py fallo: {resultado.stderr.strip()}")
    return json.loads(resultado.stdout)


# ---------------------------------------------------------------------------
# Profundidad del libro de ordenes (solo para la candidata final del ticket,
# no para todo el universo -- radar.py ya decide cual es la mejor; esto solo
# comprueba si ESA se puede cargar sin mover el precio).
# ---------------------------------------------------------------------------

def obtener_profundidad(symbol):
    url = f"{BASE_URL_BINANCE}/fapi/v1/depth?symbol={symbol}&limit=50"
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_RED) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def evaluar_liquidez_libro(direccion, entrada, tamano_nocional_usdt, profundidad, banda_pct=0.3):
    """Compara el tamano sugerido contra lo que hay realmente parado en el
    libro cerca del precio, del lado que se va a llenar (asks para comprar,
    bids para vender). Si el tamano sugerido es una fraccion grande de esa
    profundidad, cargarlo de una sola vez probablemente mueve el precio."""
    if not profundidad or "bids" not in profundidad or "asks" not in profundidad:
        return None

    lado = profundidad["asks"] if direccion == "long" else profundidad["bids"]
    limite_precio = entrada * (1 + banda_pct / 100) if direccion == "long" else entrada * (1 - banda_pct / 100)

    profundidad_usdt = 0.0
    for precio_str, cantidad_str in lado:
        precio_nivel = float(precio_str)
        if direccion == "long" and precio_nivel > limite_precio:
            break
        if direccion == "short" and precio_nivel < limite_precio:
            break
        profundidad_usdt += precio_nivel * float(cantidad_str)

    mejor_bid = float(profundidad["bids"][0][0]) if profundidad["bids"] else None
    mejor_ask = float(profundidad["asks"][0][0]) if profundidad["asks"] else None
    spread_pct = ((mejor_ask - mejor_bid) / mejor_bid * 100) if (mejor_bid and mejor_ask) else None

    fraccion = (tamano_nocional_usdt / profundidad_usdt) if profundidad_usdt > 0 else None
    alerta = fraccion is not None and fraccion > 0.15

    return {
        "profundidad_usdt_banda": round(profundidad_usdt, 2),
        "banda_pct": banda_pct,
        "spread_pct": round(spread_pct, 4) if spread_pct is not None else None,
        "fraccion_del_tamano_vs_profundidad": round(fraccion, 2) if fraccion is not None else None,
        "alerta_posible_deslizamiento": alerta,
    }


# ---------------------------------------------------------------------------
# Titulares recientes (sin resumir ni interpretar -- solo si el texto literal
# del titular menciona el activo, se muestra tal cual, con su fuente).
# ---------------------------------------------------------------------------

ALIAS_CONOCIDOS = {"BTC": "Bitcoin", "ETH": "Ethereum", "SOL": "Solana", "BNB": "BNB", "XRP": "XRP"}
HORAS_VENTANA_NOTICIAS = 48


def obtener_titulares_recientes():
    # Sin un User-Agent de navegador normal, Cointelegraph devuelve 403 (el
    # User-Agent por defecto de urllib se identifica como "Python-urllib" y
    # varios sitios de noticias lo bloquean, a diferencia de la API de
    # Binance, que no tiene ese problema).
    peticion = urllib.request.Request(
        URL_RSS_NOTICIAS,
        headers={"User-Agent": "Mozilla/5.0 (compatible; ticket-de-orden-kit/1.0)"},
    )
    try:
        with urllib.request.urlopen(peticion, timeout=TIMEOUT_RED) as resp:
            contenido = resp.read()
    except (urllib.error.URLError, TimeoutError):
        return None
    try:
        raiz = ET.fromstring(contenido)
    except ET.ParseError:
        return None

    limite = datetime.now(timezone.utc) - timedelta(hours=HORAS_VENTANA_NOTICIAS)
    titulares = []
    for item in raiz.findall(".//item"):
        titulo = item.findtext("title")
        link = item.findtext("link")
        fecha_txt = item.findtext("pubDate")
        if not titulo or not fecha_txt:
            continue
        try:
            fecha = datetime.strptime(fecha_txt.strip(), "%a, %d %b %Y %H:%M:%S %z")
        except ValueError:
            continue
        if fecha < limite:
            continue
        titulares.append({"titulo": titulo.strip(), "link": (link or "").strip(), "fecha_utc": fecha.isoformat()})
    return titulares


def buscar_menciones(symbol, titulares):
    if not titulares:
        return []
    base = symbol[:-4] if symbol.endswith("USDT") else symbol
    terminos = {base.lower()}
    if base.upper() in ALIAS_CONOCIDOS:
        terminos.add(ALIAS_CONOCIDOS[base.upper()].lower())
    encontrados = []
    for t in titulares:
        titulo_lower = t["titulo"].lower()
        if any(re.search(rf"\b{re.escape(term)}\b", titulo_lower) for term in terminos):
            encontrados.append(t)
    return encontrados[:3]


def redondear_precio(valor, cifras_significativas=6):
    """Los precios calculados (TP2 = entrada + 1.618*...) arrastran ruido de
    punto flotante que no corresponde a ningun tick real de Binance. Se
    redondea a cifras significativas -- no a decimales fijos, porque un precio
    puede ir de 0.00001234 a 68000.5 -- para que el ticket muestre un numero
    que se puede escribir de verdad en una orden."""
    if valor == 0:
        return 0.0
    from math import floor, log10
    digitos = cifras_significativas - 1 - floor(log10(abs(valor)))
    return round(valor, max(digitos, 0))


def calcular_tamano(equity, riesgo_pct, entrada, sl):
    distancia_pct = abs(entrada - sl) / entrada
    if distancia_pct <= 0:
        return None
    capital_arriesgado = equity * (riesgo_pct / 100)
    tamano_nocional = capital_arriesgado / distancia_pct
    return {
        "capital_arriesgado_usdt": round(capital_arriesgado, 2),
        "distancia_sl_pct": round(distancia_pct * 100, 2),
        "tamano_nocional_usdt": round(tamano_nocional, 2),
    }


def calcular_apalancamiento_minimo(tamano_nocional_usdt, equity):
    """El apalancamiento minimo necesario para abrir ese tamano con ese
    margen -- no es una recomendacion de "cuanto usar", es el piso
    matematico: menos que esto, la posicion no entra con ese equity."""
    if not equity or equity <= 0 or not tamano_nocional_usdt:
        return None
    import math
    return max(1, math.ceil(tamano_nocional_usdt / equity))


def calcular_tabla_apalancamiento(tamano_nocional_usdt, equity, apalancamiento_minimo):
    """Margen requerido para el MISMO tamano a cada nivel de apalancamiento
    de LEVERAGES_A_MOSTRAR. A menor apalancamiento, mas margen hace falta;
    si el margen requerido supera el equity, ese nivel no alcanza y se marca
    como tal en vez de mostrar un numero que no cierra."""
    if not tamano_nocional_usdt:
        return None
    tabla = {}
    for lev in LEVERAGES_A_MOSTRAR:
        margen_requerido = round(tamano_nocional_usdt / lev, 2)
        alcanza = equity is None or margen_requerido <= equity
        tabla[f"{lev}x"] = {"margen_requerido_usdt": margen_requerido, "alcanza_con_tu_equity": alcanza}
    return tabla


def calcular_deslizamiento_sugerido(atr_pct):
    """Referencia de tolerancia de deslizamiento para ordenes Stop-Market /
    Take-Profit-Market, proporcional a la volatilidad reciente (ATR). No
    es una garantia de ejecucion -- es un punto de partida razonable: un par
    mas volatil necesita mas margen para no fallar la orden por un
    movimiento normal."""
    if atr_pct is None:
        return None
    return round(min(max(atr_pct * 0.1, 0.05), 1.0), 2)


def _armar_plan(entrada, sl, objetivo, equity, riesgo_pct, atr_pct, vigencia_minutos, reevaluar_si_no_toco_en, num_tps=1):
    tp2 = tp3 = None
    if num_tps >= 2:
        if objetivo >= entrada:
            tp2 = entrada + EXTENSION_TP2 * (objetivo - entrada)
        else:
            tp2 = entrada - EXTENSION_TP2 * (entrada - objetivo)
    if num_tps >= 3:
        if objetivo >= entrada:
            tp3 = entrada + EXTENSION_TP3 * (objetivo - entrada)
        else:
            tp3 = entrada - EXTENSION_TP3 * (entrada - objetivo)

    tamano = calcular_tamano(equity, riesgo_pct, entrada, sl) if equity else None
    deslizamiento = calcular_deslizamiento_sugerido(atr_pct)
    entrada_red = redondear_precio(entrada)
    sl_red = redondear_precio(sl)
    tp1_red = redondear_precio(objetivo)
    tamano_nocional = tamano["tamano_nocional_usdt"] if tamano else None
    apalancamiento_min = calcular_apalancamiento_minimo(tamano_nocional, equity) if tamano else None

    # Estos son los campos EXACTOS del formulario de orden de Binance
    # Futures (pestaña Limite + seccion TP/SL), para que se puedan copiar
    # uno a uno sin traducir nada.
    plan = {
        "sl": sl_red,
        "tp1": tp1_red,
        "tamano": tamano,
        "vigencia_minutos": vigencia_minutos,
        "reevaluar_si_no_toco_en": reevaluar_si_no_toco_en,
        "orden_binance": {
            "mercado": MERCADO_KIT,
            "pestana": "Límite",
            "margen": MARGEN_BINANCE,
            "apalancamiento_minimo": apalancamiento_min,
            "tabla_apalancamiento": calcular_tabla_apalancamiento(tamano_nocional, equity, apalancamiento_min) if tamano_nocional else None,
            "precio": entrada_red,
            "cantidad_usdt": tamano_nocional,
            "tif": "GTC",
            "take_profit": {"precio": tp1_red, "referencia": "Último"},
            "stop_loss": {"precio": sl_red, "referencia": "Marca"},
            "reduce_only": False,
            "deslizamiento_si_usa_mercado_pct": deslizamiento,
        },
    }
    notas_tp_extra = []
    if tp2 is not None:
        tp2_red = redondear_precio(tp2)
        plan["tp2"] = tp2_red
        notas_tp_extra.append(f"TP2 ({tp2_red})")
    if tp3 is not None:
        tp3_red = redondear_precio(tp3)
        plan["tp3"] = tp3_red
        notas_tp_extra.append(f"TP3 ({tp3_red})")
    if notas_tp_extra:
        plan["orden_binance"]["nota_tp_extra"] = (
            f"El campo Take Profit del formulario solo admite un precio a la vez. "
            f"{' y '.join(notas_tp_extra)}: cargalos aparte (Avanzado → agregar otro Take Profit, "
            f"o una segunda/tercera orden Reduce-Only cuando el precio llegue ahí)."
        )
    return plan


def construir_ticket(candidata, equity, riesgo_pct, offline=False):
    rr_dim = candidata["dimensiones"].get("risk_reward")
    horizonte_corto = candidata.get("horizonte_corto")
    horizonte_scalp = candidata.get("horizonte_scalp")

    if rr_dim is None and horizonte_corto is None and horizonte_scalp is None:
        return {"symbol": candidata["symbol"], "sin_ticket": True, "motivo": "sin invalidacion/objetivo calculable en ningun horizonte"}

    entrada = candidata["precio"]
    symbol = candidata["symbol"]
    direccion = candidata["direccion"]
    atr_pct_4h = candidata.get("atr_pct_4h")

    plan_scalp = None
    if horizonte_scalp is not None:
        plan_scalp = _armar_plan(entrada, horizonte_scalp["invalidacion"], horizonte_scalp["objetivo"], equity, riesgo_pct, atr_pct_4h, VIGENCIA_MINUTOS_SCALP, "30 minutos", num_tps=1)

    plan_corto = None
    if horizonte_corto is not None:
        plan_corto = _armar_plan(entrada, horizonte_corto["invalidacion"], horizonte_corto["objetivo"], equity, riesgo_pct, atr_pct_4h, VIGENCIA_MINUTOS_CORTO, "4 horas", num_tps=2)

    plan_medio = None
    if rr_dim is not None and "invalidacion" in rr_dim:
        plan_medio = _armar_plan(entrada, rr_dim["invalidacion"], rr_dim["objetivo"], equity, riesgo_pct, atr_pct_4h, VIGENCIA_MINUTOS_MEDIO, "3 días", num_tps=3)

    # Libro de ordenes y titulares: solo tiene sentido en modo real (un
    # simbolo ficticio de practica no existe en Binance ni en las noticias,
    # y no se va a fabricar una respuesta para que "quede completo").
    liquidez_libro = None
    titulares = []
    if not offline:
        tamano_a_chequear = None
        if plan_medio and plan_medio.get("tamano"):
            tamano_a_chequear = plan_medio["tamano"]["tamano_nocional_usdt"]
        if tamano_a_chequear:
            profundidad = obtener_profundidad(symbol)
            liquidez_libro = evaluar_liquidez_libro(direccion, entrada, tamano_a_chequear, profundidad)
        titulares_recientes = obtener_titulares_recientes()
        titulares = buscar_menciones(symbol, titulares_recientes)

    return {
        "symbol": symbol,
        "sin_ticket": False,
        "mercado": MERCADO_KIT,
        "direccion": direccion,
        "score": candidata["score"],
        "letra": candidata["letra"],
        "nivel_riesgo": candidata["nivel_riesgo"],
        "estado_breakout": candidata["estado_breakout"],
        "entrada": redondear_precio(entrada),
        "generado_utc": datetime.now(timezone.utc).isoformat(),
        "plan_scalp_15a30m": plan_scalp,
        "plan_corto_1a4h": plan_corto,
        "plan_medio_1a3d": plan_medio,
        "candidata_patrimonial": candidata.get("candidata_patrimonial", False),
        "liquidez_libro": liquidez_libro,
        "titulares_recientes": titulares,
    }


def modo_ticket(datos, equity, riesgo_pct, offline=False):
    candidatas = datos["candidatas"]
    if not candidatas or candidatas[0]["score"] < UMBRAL_TICKET:
        return {
            "veredicto": "SIN_OPERAR",
            "motivo": "ninguna candidata alcanza el minimo de calidad (B, score >= 55)" if candidatas else "no hay candidatas en el radar ahora mismo",
            "regimen_btc": datos["regimen_btc"]["regimen"],
        }
    return {
        "veredicto": "TICKET",
        "regimen_btc": datos["regimen_btc"]["regimen"],
        "ticket": construir_ticket(candidatas[0], equity, riesgo_pct, offline=offline),
        "empate_pendiente": datos["empate_pendiente"],
    }


def cargar_estado_anterior():
    if not os.path.exists(ARCHIVO_ESTADO):
        return None
    with open(ARCHIVO_ESTADO, "r", encoding="utf-8") as fh:
        return json.load(fh)


def guardar_estado(datos, alertadas_recientes):
    os.makedirs(os.path.dirname(ARCHIVO_ESTADO), exist_ok=True)
    resumen = {
        "regimen_btc": datos["regimen_btc"]["regimen"],
        "candidatas_ab": sorted([c["symbol"] for c in datos["candidatas"] if c["letra"] in ("A+", "A")]),
        "alertadas_recientes": alertadas_recientes,
    }
    with open(ARCHIVO_ESTADO, "w", encoding="utf-8") as fh:
        json.dump(resumen, fh, indent=2)
    return resumen


def registrar_historial(ahora, datos, hay_novedad, alertados):
    os.makedirs(os.path.dirname(ARCHIVO_HISTORIAL), exist_ok=True)
    linea = {
        "cuando_utc": ahora.isoformat(),
        "regimen_btc": datos["regimen_btc"]["regimen"],
        "hay_novedad": hay_novedad,
        "candidatas_ab_ahora": sorted([c["symbol"] for c in datos["candidatas"] if c["letra"] in ("A+", "A")]),
        "alertados_esta_vez": alertados,
    }
    with open(ARCHIVO_HISTORIAL, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(linea, ensure_ascii=False) + "\n")


def modo_vigilancia(datos, equity, riesgo_pct, offline=False):
    ahora = datetime.now(timezone.utc)
    anterior = cargar_estado_anterior()
    actual_regimen = datos["regimen_btc"]["regimen"]
    actual_ab = sorted([c["symbol"] for c in datos["candidatas"] if c["letra"] in ("A+", "A")])

    if anterior is None:
        guardar_estado(datos, {})
        registrar_historial(ahora, datos, False, [])
        return {"hay_novedad": False, "motivo": "primera revision, sin punto de comparacion todavia"}

    alertadas_recientes = anterior.get("alertadas_recientes", {})
    limite = ahora - timedelta(hours=HORAS_COOLDOWN_ALERTA)
    en_cooldown = set()
    for simbolo, cuando_iso in alertadas_recientes.items():
        try:
            if datetime.fromisoformat(cuando_iso) > limite:
                en_cooldown.add(simbolo)
        except ValueError:
            pass

    nuevas_sin_filtrar = [s for s in actual_ab if s not in anterior["candidatas_ab"]]
    nuevas = [s for s in nuevas_sin_filtrar if s not in en_cooldown]
    en_cooldown_omitidas = [s for s in nuevas_sin_filtrar if s in en_cooldown]
    cambio_regimen = actual_regimen != anterior["regimen_btc"]

    hay_novedad = bool(nuevas or cambio_regimen)

    alertadas_recientes_actualizado = {s: c for s, c in alertadas_recientes.items() if s in en_cooldown}
    for s in nuevas:
        alertadas_recientes_actualizado[s] = ahora.isoformat()

    guardar_estado(datos, alertadas_recientes_actualizado)
    registrar_historial(ahora, datos, hay_novedad, nuevas)

    if not hay_novedad:
        salida = {"hay_novedad": False}
        if en_cooldown_omitidas:
            salida["motivo"] = f"{', '.join(en_cooldown_omitidas)} reaparecio pero ya se habia avisado hace menos de {HORAS_COOLDOWN_ALERTA}h, no se repite el aviso"
        return salida

    salida = {"hay_novedad": True, "candidatas_nuevas_ab": nuevas}
    if cambio_regimen:
        salida["cambio_regimen"] = {"de": anterior["regimen_btc"], "a": actual_regimen}
    if nuevas:
        mejor = next(c for c in datos["candidatas"] if c["symbol"] == nuevas[0])
        salida["ticket_de_la_novedad"] = construir_ticket(mejor, equity, riesgo_pct, offline=offline)
    return salida


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", metavar="ARCHIVO")
    parser.add_argument("--vigilancia", action="store_true")
    parser.add_argument("--equity", type=float, default=None)
    parser.add_argument("--riesgo-pct", type=float, default=0.5)
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    datos = correr_radar(args.offline)
    es_offline = bool(args.offline)

    if args.vigilancia:
        salida = modo_vigilancia(datos, args.equity, args.riesgo_pct, offline=es_offline)
    else:
        salida = modo_ticket(datos, args.equity, args.riesgo_pct, offline=es_offline)

    print(json.dumps(salida, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
