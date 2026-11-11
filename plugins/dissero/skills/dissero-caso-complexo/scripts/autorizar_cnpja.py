#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'autorizar_cnpja.py — REGISTRA o aval do advogado para GASTAR em diligência cadastral (§14).'
































import sys, os, json, time, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import caso_raiz
except Exception:
    caso_raiz = None

NOME = "AUTORIZACAO_CNPJA.json"


PADRAO_CONSULTAS = 0

ROTA_LIVRE = "consultar_estabelecimento_cnpj_publico"


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


def montar(session_id, max_consultas, max_registros, escopo, ts=None):
    if not _s(session_id):
        raise ValueError("--session-id obrigatório: o aval é POR SESSÃO (id do harness, não inventado)")
    if not _s(escopo):
        raise ValueError("--escopo obrigatório: registre O QUE o advogado autorizou consultar "
                         "(ex.: 'qualificação da ré — CNPJ 00.000.000/0001-00')")
    if not isinstance(max_consultas, int) or isinstance(max_consultas, bool) or max_consultas < 1:
        raise ValueError("--max-consultas deve ser inteiro ≥ 1")
    if max_registros is not None and (not isinstance(max_registros, int)
                                      or isinstance(max_registros, bool) or max_registros < 1):
        raise ValueError("--max-registros deve ser inteiro ≥ 1 (ou ausente, para teto não declarado)")
    return {
        "session_id": session_id.strip(),
        "max_consultas": max_consultas,
        "max_registros": max_registros,
        "escopo": escopo.strip(),
        "concedido_em": ts.strip() if _s(ts) else time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Registra o aval de gasto em diligência cadastral (Dissero §14)")
    ap.add_argument("--session-id", dest="session_id", required=True)
    ap.add_argument("--max-consultas", dest="max_consultas", type=int, default=1)
    ap.add_argument("--max-registros", dest="max_registros", type=int, default=None)
    ap.add_argument("--escopo")
    ap.add_argument("--raiz")
    ap.add_argument("--ts")
    ap.add_argument("--mostrar", action="store_true",
                    help="não grava: mostra o aval vigente e se ele vale para esta sessão")
    args = ap.parse_args(argv)

    alvo = destino(args.raiz, args.session_id)

    if args.mostrar:
        if not os.path.isfile(alvo):
            return _saida({"ok": True, "existe": False, "caminho": alvo,
                           "consultas_autorizadas": PADRAO_CONSULTAS,
                           "rota_gratuita": ROTA_LIVRE,
                           "nota": "sem aval registrado — consulta cadastral PAGA bloqueada (§14); "
                                   f"a rota gratuita `{ROTA_LIVRE}` segue liberada e é a primeira "
                                   "tentativa que o rito manda fazer"})
        try:
            d = json.loads(open(alvo, encoding="utf-8").read())
        except Exception as e:
            return _saida({"ok": False, "caminho": alvo, "erro": f"aval ilegível: {e}"}, 1)
        vale = _s(d.get("session_id")) and d["session_id"].strip() == args.session_id.strip()
        return _saida({"ok": True, "existe": True, "caminho": alvo, "autorizacao": d,
                       "vale_para_esta_sessao": bool(vale),
                       "consultas_autorizadas": (d.get("max_consultas") if vale else PADRAO_CONSULTAS),
                       "rota_gratuita": ROTA_LIVRE,
                       "nota": "" if vale else "aval de OUTRA sessão: o gate o ignora (consulta paga "
                                               "segue bloqueada)"})

    try:
        reg = montar(args.session_id, args.max_consultas, args.max_registros, args.escopo, args.ts)
    except ValueError as e:
        return _saida({"ok": False, "erro": str(e)}, 2)

    try:
        os.makedirs(os.path.dirname(alvo) or ".", exist_ok=True)
        open(alvo, "w", encoding="utf-8").write(json.dumps(reg, ensure_ascii=False, indent=2))
    except OSError as e:
        return _saida({"ok": False, "caminho": alvo, "erro": f"falha ao gravar: {e}"}, 1)

    return _saida({"ok": True, "caminho": alvo, "autorizacao": reg,
                   "nota": "aval REGISTRADO — vale só para esta sessão e para "
                           f"{reg['max_consultas']} consulta(s) PAGA(s); nova rodada exige novo aval"})


if __name__ == "__main__":
    sys.exit(main())
