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
import subprocess
import sys

CARPETA_SCRIPT = os.path.dirname(os.path.abspath(__file__))
CARPETA_KIT = os.path.dirname(CARPETA_SCRIPT)
ARCHIVO_ESTADO = os.path.join(CARPETA_KIT, ".claude", "ultimo-radar.json")

UMBRAL_TICKET = 55  # B o mejor. Por debajo de esto el veredicto es "sin operar".
EXTENSION_TP2 = 1.618  # TP2 = entrada + EXTENSION_TP2 * (TP1 - entrada)


def correr_radar(offline=None):
    cmd = [sys.executable, os.path.join(CARPETA_SCRIPT, "radar.py")]
    if offline:
        cmd += ["--offline", offline]
    resultado = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if resultado.returncode != 0:
        raise RuntimeError(f"radar.py fallo: {resultado.stderr.strip()}")
    return json.loads(resultado.stdout)


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


def _armar_plan(entrada, sl, objetivo, equity, riesgo_pct, con_tp2=False):
    if con_tp2:
        if objetivo >= entrada:
            tp2 = entrada + EXTENSION_TP2 * (objetivo - entrada)
        else:
            tp2 = entrada - EXTENSION_TP2 * (entrada - objetivo)
    else:
        tp2 = None
    tamano = calcular_tamano(equity, riesgo_pct, entrada, sl) if equity else None
    plan = {
        "sl": redondear_precio(sl),
        "tp1": redondear_precio(objetivo),
        "tamano": tamano,
    }
    if tp2 is not None:
        plan["tp2"] = redondear_precio(tp2)
    return plan


def construir_ticket(candidata, equity, riesgo_pct):
    rr_dim = candidata["dimensiones"].get("risk_reward")
    horizonte_corto = candidata.get("horizonte_corto")

    if rr_dim is None and horizonte_corto is None:
        return {"symbol": candidata["symbol"], "sin_ticket": True, "motivo": "sin invalidacion/objetivo calculable en ningun horizonte"}

    entrada = candidata["precio"]

    plan_corto = None
    if horizonte_corto is not None:
        plan_corto = _armar_plan(entrada, horizonte_corto["invalidacion"], horizonte_corto["objetivo"], equity, riesgo_pct, con_tp2=False)

    plan_medio = None
    if rr_dim is not None and "invalidacion" in rr_dim:
        plan_medio = _armar_plan(entrada, rr_dim["invalidacion"], rr_dim["objetivo"], equity, riesgo_pct, con_tp2=True)

    return {
        "symbol": candidata["symbol"],
        "sin_ticket": False,
        "direccion": candidata["direccion"],
        "score": candidata["score"],
        "letra": candidata["letra"],
        "nivel_riesgo": candidata["nivel_riesgo"],
        "estado_breakout": candidata["estado_breakout"],
        "entrada": redondear_precio(entrada),
        "plan_corto_1a4h": plan_corto,
        "plan_medio_1a3d": plan_medio,
        "candidata_patrimonial": candidata.get("candidata_patrimonial", False),
    }


def modo_ticket(datos, equity, riesgo_pct):
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
        "ticket": construir_ticket(candidatas[0], equity, riesgo_pct),
        "empate_pendiente": datos["empate_pendiente"],
    }


def cargar_estado_anterior():
    if not os.path.exists(ARCHIVO_ESTADO):
        return None
    with open(ARCHIVO_ESTADO, "r", encoding="utf-8") as fh:
        return json.load(fh)


def guardar_estado(datos):
    os.makedirs(os.path.dirname(ARCHIVO_ESTADO), exist_ok=True)
    resumen = {
        "regimen_btc": datos["regimen_btc"]["regimen"],
        "candidatas_ab": sorted([c["symbol"] for c in datos["candidatas"] if c["letra"] in ("A+", "A")]),
    }
    with open(ARCHIVO_ESTADO, "w", encoding="utf-8") as fh:
        json.dump(resumen, fh, indent=2)
    return resumen


def modo_vigilancia(datos, equity, riesgo_pct):
    anterior = cargar_estado_anterior()
    actual_regimen = datos["regimen_btc"]["regimen"]
    actual_ab = sorted([c["symbol"] for c in datos["candidatas"] if c["letra"] in ("A+", "A")])

    if anterior is None:
        guardar_estado(datos)
        return {"hay_novedad": False, "motivo": "primera revision, sin punto de comparacion todavia"}

    nuevas = [s for s in actual_ab if s not in anterior["candidatas_ab"]]
    cambio_regimen = actual_regimen != anterior["regimen_btc"]

    resultado_guardado = guardar_estado(datos)

    if not nuevas and not cambio_regimen:
        return {"hay_novedad": False}

    salida = {"hay_novedad": True, "candidatas_nuevas_ab": nuevas}
    if cambio_regimen:
        salida["cambio_regimen"] = {"de": anterior["regimen_btc"], "a": actual_regimen}
    if nuevas:
        mejor = next(c for c in datos["candidatas"] if c["symbol"] == nuevas[0])
        salida["ticket_de_la_novedad"] = construir_ticket(mejor, equity, riesgo_pct)
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

    if args.vigilancia:
        salida = modo_vigilancia(datos, args.equity, args.riesgo_pct)
    else:
        salida = modo_ticket(datos, args.equity, args.riesgo_pct)

    print(json.dumps(salida, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
