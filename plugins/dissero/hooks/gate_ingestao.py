#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'gate_ingestao.py — hook PreToolUse: AVAL ANTES DE GASTAR em ingestão/OCR (governança §14).'












































import sys, os, json, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import caso_raiz
except Exception:
    caso_raiz = None

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


SUFIXOS_INGESTAO = ("iniciar_ingestao",)

LEDGER_NAME = "PROVENIENCIA.jsonl"
AUTORIZACAO_NAME = "AUTORIZACAO_INGESTAO.json"
EVENTO = "IngestaoLiberada"

PADRAO_CHAMADAS = 0
LIMIAR_PAGINAS_LIVRE = 0
CAMPOS_PAGINAS = ("paginas", "paginas_estimadas", "max_paginas", "pages", "page_count")


def _full_str(x):
    return isinstance(x, str) and bool(x.strip())


def _deny(motivo):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "deny",
                                   "permissionDecisionReason": motivo}}


def _cwd(evento):
    c = evento.get("cwd")
    return c if _full_str(c) else os.getcwd()


def _na_raiz(nome, cwd, session_id):
    if caso_raiz is not None:
        try:
            return caso_raiz.arquivo(nome, cwd=cwd, session_id=session_id)
        except Exception:
            pass
    return os.path.join(cwd, nome)


def e_ingestao(tool):
    """True para a tool MCP que inicia ingestão, em qualquer conector."""
    if not _full_str(tool):
        return False
    t = tool.strip()
    return any(t == s or t.endswith("__" + s) or t.endswith("_" + s) for s in SUFIXOS_INGESTAO)


def _limiar():
    bruto = os.environ.get("DSR_OCR_LIMIAR_PAGINAS")
    try:
        v = int(str(bruto).strip())
        return v if v >= 0 else LIMIAR_PAGINAS_LIVRE
    except Exception:
        return LIMIAR_PAGINAS_LIVRE


def paginas_declaradas(tool_input):
    """Estimativa de páginas presente na chamada, ou None (custo desconhecido)."""
    if not isinstance(tool_input, dict):
        return None
    for campo in CAMPOS_PAGINAS:
        v = tool_input.get(campo)
        if isinstance(v, bool):
            continue
        if isinstance(v, int) and v > 0:
            return v
        if _full_str(v) and str(v).strip().isdigit():
            n = int(str(v).strip())
            if n > 0:
                return n
    return None


def contar_liberadas(ledger_path, session_id):
    """Chamadas de ingestão já liberadas nesta sessão. Ledger ausente/ilegível → 0."""
    if not _full_str(ledger_path) or not os.path.exists(ledger_path):
        return 0
    n = 0
    try:
        with open(ledger_path, encoding="utf-8", errors="replace") as fh:
            for linha in fh:
                linha = linha.strip()
                if not linha:
                    continue
                try:
                    d = json.loads(linha)
                except Exception:
                    continue
                if not isinstance(d, dict) or d.get("evento") != EVENTO:
                    continue



                if d.get("sob_aval") is False:
                    continue
                if _full_str(session_id) and _full_str(d.get("session_id")):
                    if d.get("session_id").strip() != session_id.strip():
                        continue
                n += 1
    except Exception:
        return 0
    return n


def ler_autorizacao(path, session_id):
    """Aval VÁLIDO para esta sessão → dict; senão None."""
    if not _full_str(path) or not os.path.exists(path):
        return None
    try:
        d = json.loads(open(path, encoding="utf-8").read())
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    if _full_str(session_id) and _full_str(d.get("session_id")):
        if d.get("session_id").strip() != session_id.strip():
            return None
    elif not _full_str(d.get("session_id")):
        return None
    return d


def registrar(ledger_path, session_id, tool, paginas, sob_aval):
    'Append no ledger do caso. `sob_aval=False` = job barato liberado pelo limiar: fica'


    linha = {"evento": EVENTO, "tool": tool, "session_id": session_id or "",
             "paginas_estimadas": paginas, "sob_aval": bool(sob_aval),
             "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
    try:
        os.makedirs(os.path.dirname(ledger_path) or ".", exist_ok=True)
        with open(ledger_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(linha, ensure_ascii=False) + "\n")
    except Exception:
        pass


def decidir(evento, ledger_path=None, autorizacao_path=None):
    """Núcleo: evento PreToolUse → dict de deny OU None (libera, registrando)."""
    if not isinstance(evento, dict):
        return None
    tool = evento.get("tool_name")
    if not e_ingestao(tool):
        return None

    cwd = _cwd(evento)
    session_id = evento.get("session_id") if _full_str(evento.get("session_id")) else ""
    ledger = ledger_path or os.environ.get("DSR_PROV_LEDGER") or _na_raiz(LEDGER_NAME, cwd, session_id)
    autz = (autorizacao_path or os.environ.get("DSR_AUTORIZACAO_INGESTAO")
            or _na_raiz(AUTORIZACAO_NAME, cwd, session_id))

    paginas = paginas_declaradas(evento.get("tool_input"))
    limiar = _limiar()
    autorizacao = ler_autorizacao(autz, session_id)


    if autorizacao is None and limiar > 0 and paginas is not None and paginas <= limiar:
        registrar(ledger, session_id, tool.strip(), paginas, sob_aval=False)
        return None

    if autorizacao is None:
        estimativa = f"{paginas} página(s)" if paginas is not None else "custo DESCONHECIDO (sem estimativa)"
        return _deny(
            f"INGESTÃO PAGA BLOQUEADA (governança §14): {estimativa} e não há aval do advogado "
            f"registrado para esta sessão. O job roda server-side e cobra; chamada repetida "
            f"REEXECUTA e cobra de novo. Peça o \"pode\" EXPRESSO e registre ANTES de chamar: "
            f"`python scripts/autorizar_ingestao.py --session-id <id> --max-chamadas 1 "
            f"[--max-paginas N] --escopo \"...\"` (ele resolve a raiz do caso e carimba "
            f"'concedido_em'). O limiar sem aval está "
            f"{'desativado' if limiar == 0 else f'configurado em {limiar} páginas'}; "
            f"páginas, sozinhas, não provam custo zero.")

    teto_chamadas = autorizacao.get("max_chamadas")
    if not isinstance(teto_chamadas, int) or isinstance(teto_chamadas, bool) or teto_chamadas < 1:
        teto_chamadas = PADRAO_CHAMADAS
    ja = contar_liberadas(ledger, session_id)
    if ja >= teto_chamadas:
        return _deny(
            f"INGESTÃO PAGA BLOQUEADA (governança §14): a sessão já liberou {ja} chamada(s) de "
            f"ingestão e o aval vigente cobre {teto_chamadas} (escopo: "
            f"{autorizacao.get('escopo') or 'não declarado'}). Cada chamada cria ou REEXECUTA um "
            f"job pago. Peça novo aval ao advogado e atualize {AUTORIZACAO_NAME} ANTES de chamar.")

    teto_paginas = autorizacao.get("max_paginas")
    if (isinstance(teto_paginas, int) and not isinstance(teto_paginas, bool) and teto_paginas > 0
            and paginas is not None and paginas > teto_paginas):
        return _deny(
            f"INGESTÃO PAGA BLOQUEADA (governança §14): a chamada declara {paginas} páginas e o "
            f"aval autoriza até {teto_paginas} (escopo: {autorizacao.get('escopo') or 'não declarado'}). "
            f"Confirme o gasto maior com o advogado e refaça o aval com --max-paginas.")

    registrar(ledger, session_id, tool.strip(), paginas, sob_aval=True)
    return None


def main():
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""
    try:
        ev = json.loads(raw) if raw and raw.strip() else {}
    except Exception:
        ev = {}
    try:
        saida = decidir(ev)
    except Exception:
        saida = None
    if saida:
        print(json.dumps(saida, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
