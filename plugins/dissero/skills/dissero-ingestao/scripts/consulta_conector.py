#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'consulta_conector.py — PERGUNTA ao advogado antes de usar o Eluxi ou o Fons, e grava a resposta.'




























import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import caso_raiz
except Exception:
    caso_raiz = None

NOME = "CONSULTA_CONECTORES.json"
AVAL_INGESTAO = "AUTORIZACAO_INGESTAO.json"
CONECTORES = ("eluxi", "fons")
RESPOSTAS = ("sim", "nao")




PERGUNTAS = {
    "eluxi": "O Eluxi está conectado na sua conta. Quer que eu use a leitura dele para este documento?",
    "fons": "O Fons está conectado na sua conta. Quer que eu use o caderno do caso dele para estudar estes autos?",
}
_inv = None
try:
    import inventario_conectores as _inv
    for _c, _d in (getattr(_inv, "CONSULTAR_ANTES", None) or {}).items():
        if _c in PERGUNTAS and isinstance(_d, dict) and isinstance(_d.get("pergunta"), str) \
                and _d["pergunta"].strip():
            PERGUNTAS[_c] = _d["pergunta"].strip()
except Exception:
    pass


def _s(x):
    return isinstance(x, str) and bool(x.strip())


def _saida(payload, code=0):
    print(json.dumps(payload, ensure_ascii=False))
    return code


def _caminho(nome, raiz=None, session_id=None):
    if _s(raiz):
        return os.path.join(os.path.abspath(raiz.strip()), nome)
    if caso_raiz is not None:
        try:
            return caso_raiz.arquivo(nome, session_id=session_id)
        except Exception:
            pass
    return os.path.join(os.getcwd(), nome)


def _ler_json(path):
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    return d if isinstance(d, dict) else {}


def aval_ingestao_vigente(raiz, session_id):
    """O aval de ingestão desta sessão (o "sim" do Eluxi), ou None. Mesma regra do gate."""
    try:
        d = _ler_json(_caminho(AVAL_INGESTAO, raiz, session_id))
    except Exception:
        return None
    if not d or not _s(d.get("session_id")) or d["session_id"].strip() != session_id.strip():
        return None
    return d


def preferencia_perfil(conector, caminho=None, sem_perfil=False):
    """`conectores.<id>` do perfil, pela mesma leitura do inventário; sem perfil, `auto`."""
    if sem_perfil or _inv is None:
        return "auto"
    try:
        perfil, _ = _inv.carregar_perfil(caminho)
        prefs, _ = _inv.preferencias_do_perfil(perfil)
        return prefs.get(conector, "auto")
    except Exception:
        return "auto"


def decidir(conector, conectado, registro, aval=None, preferencia="auto"):
    """Núcleo puro: o que fazer com o conector nesta sessão."""
    if conectado and preferencia == "nao_usar":
        return {"conectado": True, "perguntar": False, "mencionar": False,
                "acao": "rota_embarcada", "resposta": None,
                "nota": "o advogado optou no perfil por não usar este serviço: não pergunte nem "
                        "mencione; siga pela rota embarcada"}
    if not conectado:
        return {"conectado": False, "perguntar": False, "mencionar": False,
                "acao": "rota_embarcada", "resposta": None,
                "nota": "não conectado: não pergunte nem mencione o serviço; siga pela rota embarcada"}
    resposta = (registro or {}).get("resposta")
    if aval is not None and resposta != "nao":
        resposta = "sim"
    elif aval is not None and resposta == "nao":

        if str(aval.get("concedido_em") or "") > str(registro.get("respondido_em") or ""):
            resposta = "sim"
    if resposta == "sim":
        return {"conectado": True, "perguntar": False, "mencionar": True, "acao": "usar",
                "resposta": "sim"}
    if resposta == "nao":
        return {"conectado": True, "perguntar": False, "mencionar": False, "acao": "nao_usar",
                "resposta": "nao",
                "nota": "o advogado já disse que não: siga pela rota embarcada sem perguntar de novo"}
    nota = ("faça a pergunta com este texto, sem acrescentar nada; com o sim, registre o aval "
            "(autorizar_ingestao.py); com o não, registre aqui") if conector == "eluxi" else \
           "faça a pergunta com este texto, sem acrescentar nada, e registre a resposta aqui"
    return {"conectado": True, "perguntar": True, "mencionar": True, "acao": "perguntar",
            "resposta": None, "pergunta": PERGUNTAS[conector], "nota": nota}


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Pergunta antes de usar o Eluxi ou o Fons (Dissero)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pm = sub.add_parser("mostrar")
    pr = sub.add_parser("registrar")
    for p in (pm, pr):
        p.add_argument("--conector", required=True)
        p.add_argument("--session-id", dest="session_id", required=True)
        p.add_argument("--raiz")
    pm.add_argument("--perfil", default=None, help="perfil.json (padrão: o do inventário)")
    pm.add_argument("--sem-perfil", dest="sem_perfil", action="store_true")
    pm.add_argument("--conectado", action="store_true",
                    help="as ferramentas do conector estão na sessão (consultar_antes do inventário)")
    pr.add_argument("--resposta", required=True)
    pr.add_argument("--ts")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return int(e.code or 2)

    conector = (args.conector or "").strip().lower()
    if conector not in CONECTORES:
        return _saida({"ok": False, "erro": f"conector fora da consulta: {conector!r} (só {', '.join(CONECTORES)})"}, 2)
    if not _s(args.session_id):
        return _saida({"ok": False, "erro": "--session-id obrigatório (id do harness, não inventado)"}, 2)
    sid = args.session_id.strip()
    alvo = _caminho(NOME, args.raiz, sid)

    try:
        dados = _ler_json(alvo)
    except Exception as e:
        return _saida({"ok": False, "caminho": alvo, "erro": f"registro ilegível: {e}"}, 1)

    if args.cmd == "mostrar":
        aval = aval_ingestao_vigente(args.raiz, sid) if conector == "eluxi" else None
        out = {"ok": True, "conector": conector, "caminho": alvo}
        pref = preferencia_perfil(conector, args.perfil, args.sem_perfil) if args.conectado else "auto"
        out.update(decidir(conector, args.conectado, dados.get(conector), aval, pref))
        return _saida(out)

    resposta = (args.resposta or "").strip().lower()
    if resposta not in RESPOSTAS:
        return _saida({"ok": False, "erro": "--resposta deve ser sim ou nao"}, 2)
    if conector == "eluxi" and resposta == "sim":
        return _saida({"ok": False, "erro": "o sim do Eluxi é o aval de ingestão: registre com "
                                            "autorizar_ingestao.py --session-id <id> --max-chamadas 1 "
                                            "--escopo \"<o que ele autorizou>\""}, 2)
    dados[conector] = {"resposta": resposta, "session_id": sid,
                       "respondido_em": args.ts.strip() if _s(args.ts) else time.strftime("%Y-%m-%dT%H:%M:%S")}
    try:
        os.makedirs(os.path.dirname(alvo) or ".", exist_ok=True)
        with open(alvo, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(dados, ensure_ascii=False, indent=2))
    except OSError as e:
        return _saida({"ok": False, "caminho": alvo, "erro": f"falha ao gravar: {e}"}, 1)
    return _saida({"ok": True, "conector": conector, "caminho": alvo, "registro": dados[conector]})


if __name__ == "__main__":
    sys.exit(main())
