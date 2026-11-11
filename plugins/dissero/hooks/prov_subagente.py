#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'prov_subagente.py — hook SubagentStart: grava a proveniência REAL do subagente.'























import sys, os, json, time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
RAIZ_PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
try:
    import caso_raiz
except Exception:
    caso_raiz = None


def versao_plugin(raiz):
    'A versão do plugin que produziu esta entrada. None quando não der para saber.'


    try:
        return json.loads((Path(raiz) / ".claude-plugin" / "plugin.json")
                          .read_text(encoding="utf-8"))["version"]
    except Exception:
        return None


def montar_linha(d, raiz=None):
    'A linha do ledger. Separada de main() para ter teste próprio.'



    agent_id = d.get("agent_id")
    return {
        "agent_id": agent_id.strip() if isinstance(agent_id, str) else None,
        "agent_type": d.get("agent_type") if isinstance(d.get("agent_type"), str) else None,
        "session_id": d.get("session_id") if isinstance(d.get("session_id"), str) else None,
        "ts": int(time.time()),
        "evento": "SubagentStart",
        "plugin_versao": versao_plugin(raiz or RAIZ_PLUGIN),
    }


def main():
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""
    try:
        d = json.loads(raw) if raw and raw.strip() else {}
    except Exception:
        d = {}
    if not isinstance(d, dict):
        return 0

    agent_id = d.get("agent_id")

    if not (isinstance(agent_id, str) and agent_id.strip()):
        return 0

    cwd = d.get("cwd") if isinstance(d.get("cwd"), str) and d.get("cwd").strip() else os.getcwd()
    session_id = d.get("session_id") if isinstance(d.get("session_id"), str) else None
    ledger = os.environ.get("DSR_PROV_LEDGER")
    if not (isinstance(ledger, str) and ledger.strip()):
        if caso_raiz is not None:
            try:
                ledger = caso_raiz.arquivo("PROVENIENCIA.jsonl", cwd=cwd, session_id=session_id)
            except Exception:
                ledger = os.path.join(cwd, "PROVENIENCIA.jsonl")
        else:
            ledger = os.path.join(cwd, "PROVENIENCIA.jsonl")

    rec = montar_linha(d)
    try:
        with open(ledger, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
