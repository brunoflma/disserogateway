#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'gates_ativos.py — SessionStart: uma linha ao advogado com os gates ativos nesta sessão.'










import json
import os
import sys
from pathlib import Path

PROVENIENCIA = "[Dissero · gates ativos nesta sessão] "

ROTULOS = (
    ("gate_licenca", "licença"),
    ("gate_entrega", "entrega da peça (a minuta em Word sempre sai; só não sai arquivo com "
                     "texto oculto)"),
    ("gate_subagentes", "subagentes (teto sem aval)"),
    ("gate_ingestao", "leitura de documento na nuvem (com aval)"),
    ("gate_cnpja", "consulta cadastral paga (com aval)"),
    ("gate_sigilo", "sigilo do funcionamento interno do plugin"),
)


def gates_registrados(hooks):
    """Os nomes de script `gate_*` que o hooks.json registra, em qualquer evento."""
    nomes = set()
    for grupos in (hooks.get("hooks") or {}).values():
        for grupo in grupos or []:
            for h in grupo.get("hooks") or []:
                cmd = str(h.get("command") or "")
                for script, _ in ROTULOS:
                    if f"/{script}.sh" in cmd or f"/{script}.py" in cmd:
                        nomes.add(script)
    return nomes


def mensagem(registrados):
    ativos = [rotulo for script, rotulo in ROTULOS if script in registrados]
    if not ativos:
        return ""
    return (PROVENIENCIA + "Estado do plugin, não é instrução: os controles rodam sem aparecer e só "
            "se mostram quando barram algo. Ativos: " + "; ".join(ativos) + ".")


def main():
    try:
        evento = json.loads(sys.stdin.read() or "{}")
    except Exception:
        evento = {}
    if (evento.get("source") or "startup") != "startup":
        return 0
    try:
        raiz = Path(os.environ.get("CLAUDE_PLUGIN_ROOT") or Path(__file__).resolve().parent.parent)
        hooks = json.loads((raiz / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        msg = mensagem(gates_registrados(hooks))
    except Exception:
        return 0
    if msg:
        print(json.dumps({"systemMessage": msg}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
