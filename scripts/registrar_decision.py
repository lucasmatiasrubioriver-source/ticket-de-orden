#!/usr/bin/env python3
"""Registra que hiciste con un ticket: lo tomaste o lo dejaste pasar, y por
que. Queda en workspace/decisiones.jsonl -- es el insumo que hace falta para
el futuro kit de journal (sin esto, no hay forma de saber despues si el
sistema realmente ayudo o no).

Uso:
    python registrar_decision.py --symbol ZENUSDT --decision tomado \
        --motivo "estructura limpia y funding a favor" \
        --entrada 6.03 --sl 5.95 --tp1 6.17 --plan medio

    python registrar_decision.py --symbol FUNDEXUSDT --decision pasado \
        --motivo "funding demasiado extremo"
"""

import argparse
import json
import os
from datetime import datetime, timezone

CARPETA_KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVO_DECISIONES = os.path.join(CARPETA_KIT, "workspace", "decisiones.jsonl")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--decision", required=True, choices=["tomado", "pasado"])
    parser.add_argument("--motivo", default=None)
    parser.add_argument("--entrada", type=float, default=None)
    parser.add_argument("--sl", type=float, default=None)
    parser.add_argument("--tp1", type=float, default=None)
    parser.add_argument("--tp2", type=float, default=None)
    parser.add_argument("--plan", choices=["corto", "medio"], default=None)
    args = parser.parse_args()

    try:
        import sys
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    registro = {
        "cuando_utc": datetime.now(timezone.utc).isoformat(),
        "symbol": args.symbol,
        "decision": args.decision,
        "motivo": args.motivo,
        "plan": args.plan,
        "entrada": args.entrada,
        "sl": args.sl,
        "tp1": args.tp1,
        "tp2": args.tp2,
        "resultado": None,
    }

    os.makedirs(os.path.dirname(ARCHIVO_DECISIONES), exist_ok=True)
    with open(ARCHIVO_DECISIONES, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(registro, ensure_ascii=False) + "\n")

    print(json.dumps({"guardado": True, "registro": registro}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
