#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'autorizar_subagentes.py — REGISTRA o aval do advogado para disparar subagentes (§13).'
























import sys, os, json, time, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import caso_raiz
except Exception:
    caso_raiz = None

NOME = "AUTORIZACAO_SUBAGENTES.json"


PADRAO_SIMULTANEOS = 2
PADRAO_ONDAS = 1


def _s(x):
    return isinstance(x, str) and bool(x.strip())


def _saida(payload, code=0):
    print(json.dumps(payload, ensure_ascii=False))
    return code


def destino(raiz=None, session_id=None):
    if _s(raiz):
        return os.path.join(os.path.abspath(raiz.strip()), NOME)
    if caso_raiz is not None:
        try:
            return caso_raiz.arquivo(NOME, session_id=session_id)
        except Exception:
            pass
    return os.path.join(os.getcwd(), NOME)


def montar(session_id, max_simultaneos, ondas, escopo, ts=None):
    if not _s(session_id):
        raise ValueError("--session-id obrigatório: o aval é POR SESSÃO (id do harness, não inventado)")
    if not _s(escopo):
        raise ValueError("--escopo obrigatório: registre PARA QUE o advogado autorizou (ex.: "
                         "'Conselho Revisor — inicial de cobrança')")
    for rotulo, v in (("--max-simultaneos", max_simultaneos), ("--ondas", ondas)):
        if not isinstance(v, int) or isinstance(v, bool) or v < 1:
            raise ValueError(f"{rotulo} deve ser inteiro ≥ 1")
    return {
        "session_id": session_id.strip(),
        "max_simultaneos": max_simultaneos,
        "ondas": ondas,
        "escopo": escopo.strip(),
        "concedido_em": ts.strip() if _s(ts) else time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Registra o aval de disparo de subagentes (Dissero §13)")
    ap.add_argument("--session-id", dest="session_id", required=True)
    ap.add_argument("--max-simultaneos", dest="max_simultaneos", type=int, default=5)
    ap.add_argument("--ondas", type=int, default=1)
    ap.add_argument("--escopo")
    ap.add_argument("--raiz")
    ap.add_argument("--ts")
    ap.add_argument("--mostrar", action="store_true",
                    help="não grava: mostra a autorização vigente e se ela vale para esta sessão")
    args = ap.parse_args(argv)

    alvo = destino(args.raiz, args.session_id)

    if args.mostrar:
        if not os.path.isfile(alvo):
            return _saida({"ok": True, "existe": False, "caminho": alvo,
                           "teto_vigente": PADRAO_SIMULTANEOS * PADRAO_ONDAS,
                           "nota": "sem autorização registrada — vale o padrão §13 (2 agentes, 1 onda)"})
        try:
            d = json.loads(open(alvo, encoding="utf-8").read())
        except Exception as e:
            return _saida({"ok": False, "caminho": alvo, "erro": f"autorização ilegível: {e}"}, 1)
        vale = _s(d.get("session_id")) and d["session_id"].strip() == args.session_id.strip()
        teto = (d.get("max_simultaneos") or 0) * (d.get("ondas") or 0) if vale else PADRAO_SIMULTANEOS * PADRAO_ONDAS
        return _saida({"ok": True, "existe": True, "caminho": alvo, "autorizacao": d,
                       "vale_para_esta_sessao": bool(vale), "teto_vigente": teto,
                       "nota": "" if vale else "autorização de OUTRA sessão: o gate a ignora (vale o padrão §13)"})

    try:
        reg = montar(args.session_id, args.max_simultaneos, args.ondas, args.escopo, args.ts)
    except ValueError as e:
        return _saida({"ok": False, "erro": str(e)}, 2)

    try:
        os.makedirs(os.path.dirname(alvo) or ".", exist_ok=True)
        open(alvo, "w", encoding="utf-8").write(json.dumps(reg, ensure_ascii=False, indent=2))
    except OSError as e:
        return _saida({"ok": False, "caminho": alvo, "erro": f"falha ao gravar: {e}"}, 1)

    return _saida({"ok": True, "caminho": alvo, "autorizacao": reg,
                   "teto_autorizado": reg["max_simultaneos"] * reg["ondas"],
                   "nota": "aval REGISTRADO — vale só para esta sessão; onda adicional exige novo aval"})


if __name__ == "__main__":
    sys.exit(main())
