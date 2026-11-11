#!/usr/bin/env python3
'Migração explícita e fail-closed de dsr.achados.v2 para v3.'






from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import estrategia_precedentes as estrategia


def main():
    p = argparse.ArgumentParser()
    p.add_argument("arquivo")
    p.add_argument("-o", "--saida", required=True)
    args = p.parse_args()
    with open(args.arquivo, encoding="utf-8") as f:
        dados = json.load(f)
    convertido = estrategia.migrar_v2(dados)
    with open(args.saida, "w", encoding="utf-8") as f:
        json.dump(convertido, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps({
        "ok": True,
        "schema_version": estrategia.VERSAO_V3,
        "saida": args.saida,
        "aviso": "migração fail-closed: pesquisa contrária não iniciada e cobertura inexistente até revisão",
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
