#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'autorizar_ingestao.py — REGISTRA o aval do advogado para GASTAR em ingestão/OCR (§14).'



























import sys, os, json, time, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import caso_raiz
except Exception:
    caso_raiz = None

NOME = "AUTORIZACAO_INGESTAO.json"


PADRAO_CHAMADAS = 0




LIMIAR_PAGINAS_LIVRE = 0


def _limiar():
    """O limiar que o gate aplica: DSR_OCR_LIMIAR_PAGINAS quando é inteiro >= 0; senão, 0."""
    bruto = os.environ.get("DSR_OCR_LIMIAR_PAGINAS")
    try:
        v = int(str(bruto).strip())
        return v if v >= 0 else LIMIAR_PAGINAS_LIVRE
    except Exception:
        return LIMIAR_PAGINAS_LIVRE


def _nota_limiar(limiar):
    """A frase do limiar, com a redação do gate."""
    if limiar == 0:
        return "o limiar sem aval está desativado; páginas, sozinhas, não provam custo zero"
    return (f"o limiar sem aval está configurado em {limiar} páginas: job com estimativa de "
            f"até {limiar} páginas passa sem aval, e sem estimativa o aval é exigido")


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


def montar(session_id, max_chamadas, max_paginas, escopo, ts=None):
    if not _s(session_id):
        raise ValueError("--session-id obrigatório: o aval é POR SESSÃO (id do harness, não inventado)")
    if not _s(escopo):
        raise ValueError("--escopo obrigatório: registre O QUE o advogado autorizou ingerir "
                         "(ex.: 'autos 1234567-89.2026.8.26.0100 — ingestão integral')")
    if not isinstance(max_chamadas, int) or isinstance(max_chamadas, bool) or max_chamadas < 1:
        raise ValueError("--max-chamadas deve ser inteiro ≥ 1")
    if max_paginas is not None and (not isinstance(max_paginas, int) or isinstance(max_paginas, bool)
                                    or max_paginas < 1):
        raise ValueError("--max-paginas deve ser inteiro ≥ 1 (ou ausente, para teto não declarado)")
    return {
        "session_id": session_id.strip(),
        "max_chamadas": max_chamadas,
        "max_paginas": max_paginas,
        "escopo": escopo.strip(),
        "concedido_em": ts.strip() if _s(ts) else time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Registra o aval de gasto em ingestão/OCR (Dissero §14)")
    ap.add_argument("--session-id", dest="session_id", required=True)
    ap.add_argument("--max-chamadas", dest="max_chamadas", type=int, default=1)
    ap.add_argument("--max-paginas", dest="max_paginas", type=int, default=None)
    ap.add_argument("--escopo")
    ap.add_argument("--raiz")
    ap.add_argument("--ts")
    ap.add_argument("--mostrar", action="store_true",
                    help="não grava: mostra o aval vigente e se ele vale para esta sessão")
    args = ap.parse_args(argv)

    alvo = destino(args.raiz, args.session_id)

    if args.mostrar:
        if not os.path.isfile(alvo):
            limiar = _limiar()
            return _saida({"ok": True, "existe": False, "caminho": alvo,
                           "chamadas_autorizadas": PADRAO_CHAMADAS,
                           "limiar_paginas_livre": limiar,
                           "nota": "sem aval registrado — ingestão paga BLOQUEADA (§14); "
                                   + _nota_limiar(limiar)})
        try:
            d = json.loads(open(alvo, encoding="utf-8").read())
        except Exception as e:
            return _saida({"ok": False, "caminho": alvo, "erro": f"aval ilegível: {e}"}, 1)
        vale = _s(d.get("session_id")) and d["session_id"].strip() == args.session_id.strip()
        return _saida({"ok": True, "existe": True, "caminho": alvo, "autorizacao": d,
                       "vale_para_esta_sessao": bool(vale),
                       "chamadas_autorizadas": (d.get("max_chamadas") if vale else PADRAO_CHAMADAS),
                       "nota": "" if vale else "aval de OUTRA sessão: o gate o ignora (ingestão paga "
                                               "segue bloqueada)"})

    try:
        reg = montar(args.session_id, args.max_chamadas, args.max_paginas, args.escopo, args.ts)
    except ValueError as e:
        return _saida({"ok": False, "erro": str(e)}, 2)

    try:
        os.makedirs(os.path.dirname(alvo) or ".", exist_ok=True)
        open(alvo, "w", encoding="utf-8").write(json.dumps(reg, ensure_ascii=False, indent=2))
    except OSError as e:
        return _saida({"ok": False, "caminho": alvo, "erro": f"falha ao gravar: {e}"}, 1)

    return _saida({"ok": True, "caminho": alvo, "autorizacao": reg,
                   "nota": "aval REGISTRADO — vale só para esta sessão e para "
                           f"{reg['max_chamadas']} chamada(s) de ingestão; nova rodada exige novo aval"})


if __name__ == "__main__":
    sys.exit(main())
