#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'gate_cnpja.py — hook PreToolUse: AVAL ANTES DE GASTAR em diligência cadastral (governança §14).'










































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


SUFIXOS_LIVRES = (
    "consultar_estabelecimento_cnpj_publico",
    "consultar_cep_cnpja_publico",
    "consultar_saldo_cnpja",
)


SUFIXOS_HIBRIDOS = (
    "consultar_estabelecimento_cnpj",
    "consultar_cep_cnpja",
)


SUFIXOS_PAGOS = (
    "consultar_empresa_cnpja",
    "consultar_receita_federal_cnpj",
    "consultar_ccc",
    "consultar_simples_mei",
    "consultar_suframa",
    "consultar_pessoa_cnpja",
    "buscar_estabelecimentos_cnpj",
    "buscar_pessoas_cnpja",
    "emitir_comprovante_rfb",
    "emitir_comprovante_ccc",
    "emitir_comprovante_simples_mei",
    "emitir_comprovante_suframa",
    "gerar_mapa_estabelecimento",
    "gerar_visao_rua_estabelecimento",
)


SUFIXOS_VOLUME = ("buscar_estabelecimentos_cnpj", "buscar_pessoas_cnpja")

LEDGER_NAME = "PROVENIENCIA.jsonl"
AUTORIZACAO_NAME = "AUTORIZACAO_CNPJA.json"
EVENTO = "ConsultaCnpjaLiberada"

PADRAO_CONSULTAS = 0


EQUIVALENTE_LIVRE = {
    "consultar_empresa_cnpja": "consultar_estabelecimento_cnpj_publico",
    "consultar_receita_federal_cnpj": "consultar_estabelecimento_cnpj_publico",
    "consultar_estabelecimento_cnpj": "consultar_estabelecimento_cnpj_publico",
    "consultar_cep_cnpja": "consultar_cep_cnpja_publico",
}


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


def sufixo(tool):
    'Nome da ferramenta sem o prefixo `mcp__<servidor>__`. Comparação EXATA depois disso:'


    if not _full_str(tool):
        return ""
    t = tool.strip()
    return t.rsplit("__", 1)[-1] if "__" in t else t


def classificar(tool, tool_input):
    """'livre' | 'paga' | '' (fora do conector cadastral)."""
    s = sufixo(tool)
    if not s:
        return ""
    if s in SUFIXOS_LIVRES:
        return "livre"
    if s in SUFIXOS_HIBRIDOS:
        fonte = (tool_input or {}).get("fonte") if isinstance(tool_input, dict) else None


        if _full_str(fonte) and fonte.strip().lower() == "publica":
            return "livre"
        return "paga"
    if s in SUFIXOS_PAGOS:
        return "paga"
    return ""


def registros_pedidos(tool, tool_input):
    """`limite × max_paginas` das buscas em massa, ou None quando não se aplica."""
    if sufixo(tool) not in SUFIXOS_VOLUME or not isinstance(tool_input, dict):
        return None

    def _int(campo, padrao):
        v = tool_input.get(campo)
        if isinstance(v, bool):
            return padrao
        if isinstance(v, int) and v > 0:
            return v
        if _full_str(v) and str(v).strip().isdigit():
            n = int(str(v).strip())
            if n > 0:
                return n
        return padrao

    return _int("limite", 10) * _int("max_paginas", 1)


def contar_liberadas(ledger_path, session_id):
    """Consultas pagas já liberadas nesta sessão. Ledger ausente/ilegível → 0."""
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


def registrar(ledger_path, session_id, tool, registros):
    'Append no ledger do caso. Fail-safe: falha de escrita nunca bloqueia a chamada.'


    linha = {"evento": EVENTO, "tool": tool, "session_id": session_id or "",
             "registros_pedidos": registros,
             "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
    try:
        os.makedirs(os.path.dirname(ledger_path) or ".", exist_ok=True)
        with open(ledger_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(linha, ensure_ascii=False) + "\n")
    except Exception:
        pass


def decidir(evento, ledger_path=None, autorizacao_path=None):
    """Núcleo: evento PreToolUse → dict de deny OU None (libera, registrando se for paga)."""
    if not isinstance(evento, dict):
        return None
    tool = evento.get("tool_name")
    tool_input = evento.get("tool_input")
    classe = classificar(tool, tool_input)
    if classe != "paga":
        return None

    s = sufixo(tool)
    cwd = _cwd(evento)
    session_id = evento.get("session_id") if _full_str(evento.get("session_id")) else ""
    ledger = ledger_path or os.environ.get("DSR_PROV_LEDGER") or _na_raiz(LEDGER_NAME, cwd, session_id)
    autz = (autorizacao_path or os.environ.get("DSR_AUTORIZACAO_CNPJA")
            or _na_raiz(AUTORIZACAO_NAME, cwd, session_id))

    registros = registros_pedidos(tool, tool_input)
    autorizacao = ler_autorizacao(autz, session_id)

    if autorizacao is None:
        livre = EQUIVALENTE_LIVRE.get(s)
        alternativa = (f" A rota GRATUITA `{livre}` entrega a qualificação completa (razão "
                       f"social, natureza, sede, situação cadastral, sócios) e é o que o rito "
                       f"manda tentar PRIMEIRO." if livre else
                       " Esta ferramenta não tem equivalente gratuito — o aval é a única via.")
        return _deny(
            f"CONSULTA CADASTRAL PAGA BLOQUEADA (governança §14): `{s}` consome créditos "
            f"comerciais e não há aval do advogado registrado para esta sessão.{alternativa} "
            f"Para a rota paga, peça o \"pode\" EXPRESSO e registre ANTES de chamar: "
            f"`python scripts/autorizar_cnpja.py --session-id <id> --max-consultas 1 "
            f"[--max-registros N] --escopo \"...\"` (ele resolve a raiz do caso e carimba "
            f"'concedido_em'). Ver `references/diligencia-cadastral.md` §3-§4.")

    teto = autorizacao.get("max_consultas")
    if not isinstance(teto, int) or isinstance(teto, bool) or teto < 1:
        teto = PADRAO_CONSULTAS
    ja = contar_liberadas(ledger, session_id)
    if ja >= teto:
        return _deny(
            f"CONSULTA CADASTRAL PAGA BLOQUEADA (governança §14): a sessão já liberou {ja} "
            f"consulta(s) paga(s) e o aval vigente cobre {teto} (escopo: "
            f"{autorizacao.get('escopo') or 'não declarado'}). Cada chamada consome crédito. "
            f"Peça novo aval ao advogado e atualize {AUTORIZACAO_NAME} ANTES de chamar.")

    teto_registros = autorizacao.get("max_registros")
    if (isinstance(teto_registros, int) and not isinstance(teto_registros, bool)
            and teto_registros > 0 and registros is not None and registros > teto_registros):
        return _deny(
            f"CONSULTA CADASTRAL PAGA BLOQUEADA (governança §14): `{s}` pede até {registros} "
            f"registro(s) (limite × max_paginas) e o aval autoriza {teto_registros} (escopo: "
            f"{autorizacao.get('escopo') or 'não declarado'}). Reduza `limite`/`max_paginas` ou "
            f"refaça o aval com --max-registros.")

    registrar(ledger, session_id, (tool or "").strip(), registros)
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
