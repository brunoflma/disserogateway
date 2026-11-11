#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'gate_subagentes.py — hook PreToolUse: APROVAÇÃO ANTES DO DISPARO de subagente (§13).'










































import sys, os, json, re

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


TOOLS_SUBAGENTE = ("Task", "Agent")


PADRAO_SIMULTANEOS = 2
PADRAO_ONDAS = 1

LEDGER_NAME = "PROVENIENCIA.jsonl"
AUTORIZACAO_NAME = "AUTORIZACAO_SUBAGENTES.json"


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
    'Caminho do arquivo de controle na RAIZ DO CASO. Sem o módulo (ou com ele em pane),'

    if caso_raiz is not None:
        try:
            return caso_raiz.arquivo(nome, cwd=cwd, session_id=session_id)
        except Exception:
            pass
    return os.path.join(cwd, nome)


def contar_disparos(ledger_path, session_id):
    'Disparos REAIS já registrados para a sessão. Ledger ausente/ilegível → 0 (fail-open de'

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
                if not isinstance(d, dict) or d.get("evento") != "SubagentStart":
                    continue


                if _full_str(session_id) and _full_str(d.get("session_id")):
                    if d.get("session_id").strip() != session_id.strip():
                        continue
                n += 1
    except Exception:
        return 0
    return n


def ler_autorizacao(path, session_id):
    'Autorização VÁLIDA para esta sessão → dict; senão None. Autorização de outra sessão'

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


def _inteiro(v, padrao):
    return v if isinstance(v, int) and not isinstance(v, bool) and v > 0 else padrao


def teto(autorizacao):
    """Orçamento de subagentes da sessão: max_simultaneos × ondas."""
    if not autorizacao:
        return PADRAO_SIMULTANEOS * PADRAO_ONDAS, PADRAO_SIMULTANEOS, PADRAO_ONDAS, False
    s = _inteiro(autorizacao.get("max_simultaneos"), PADRAO_SIMULTANEOS)
    o = _inteiro(autorizacao.get("ondas"), PADRAO_ONDAS)
    return s * o, s, o, True


_MARCA_SOLTA = re.compile(r"AGENTE DEDICADO do Cap[ií]tulo", re.I)


def conferir_briefing(evento):
    "Briefing do agente de capítulo → ('deny', motivo), ('aviso', texto) ou None."


    entrada = evento.get("tool_input") if isinstance(evento.get("tool_input"), dict) else {}
    prompt = entrada.get("prompt")
    if not (_full_str(prompt) and _MARCA_SOLTA.search(prompt)):
        return None
    try:
        import gate_entrega_subagente as ges
        cap = ges.capitulo_do_briefing(prompt)
        erros = ges.validar_briefing(prompt) if cap else []
    except Exception:
        return None
    if cap is None:
        return ("aviso", "[Dissero · subagentes] O pedido cita o AGENTE DEDICADO do Capítulo, mas não começa pelo "
                "cabeçalho \"# HANDOFF — CAPÍTULO <N>\": se é o agente de capítulo, ele vai sem a "
                "conferência da devolução. Despache o HANDOFF_CAP_<N> inteiro, a começar pelo "
                "cabeçalho. Se o pedido é de verificador ou da turma, siga.")
    if not erros:
        return None
    codigos = ", ".join(dict.fromkeys(e["codigo"] for e in erros))
    detalhes = "; ".join(e["detalhe"] for e in erros)



    novas = [t for t in ("Partes por papel processual", "Devolução") if ges._secao(prompt, t) is None]
    if novas and all(ges._secao(prompt, t) is not None for t in ges.SECOES_BRIEFING if t not in novas):
        return ("deny", f"Briefing do agente de capítulo recusado ({codigos}): {detalhes}. O "
                        f"HANDOFF_CAP_{cap} parece gerado pelo modelo anterior do Template 3, que não "
                        f"tinha {' nem '.join('«' + t + '»' for t in novas)}. Basta acrescentar "
                        + " e ".join(_SECAO_NOVA[t] for t in novas)
                        + " (references/templates-controles.md, Template 3) e despachar de novo; o "
                          "resto do handoff fica como está.")
    return ("deny", f"Briefing do agente de capítulo recusado ({codigos}): {detalhes}. Preencha o "
                    f"HANDOFF_CAP_{cap} pelo Template 3 (partes por papel processual) antes de despachar.")



_SECAO_NOVA = {
    "Partes por papel processual": (
        "a seção «## 2. Partes por papel processual», uma linha por parte começando pelo papel e "
        "sem nome, CPF ou CNPJ («- Autora: pessoa física; ...», «- Ré: pessoa jurídica; ...»)"),
    "Devolução": (
        "a seção «## 8. Devolução», que manda gravar <temp>/DEVOLUCAO_CAP_<N>.json pelo contrato "
        "dissero.devolucao_capitulo.v1 antes de parar"),
}


def decidir(evento, ledger_path=None, autorizacao_path=None):
    """Núcleo: evento PreToolUse → dict de deny, dict de aviso OU None (sem decisão)."""
    if not isinstance(evento, dict):
        return None
    tool = evento.get("tool_name")
    if not (_full_str(tool) and tool.strip() in TOOLS_SUBAGENTE):
        return None

    briefing = conferir_briefing(evento)
    if briefing and briefing[0] == "deny":
        return _deny(briefing[1])
    negado = _decidir_teto(evento, ledger_path, autorizacao_path)
    if negado or not briefing:
        return negado
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": briefing[1]}}


def _decidir_teto(evento, ledger_path=None, autorizacao_path=None):
    """Teto de disparos da sessão (§13): dict de deny OU None."""

    cwd = _cwd(evento)
    session_id = evento.get("session_id") if _full_str(evento.get("session_id")) else ""
    ledger = ledger_path or os.environ.get("DSR_PROV_LEDGER") or _na_raiz(LEDGER_NAME, cwd, session_id)
    autz = autorizacao_path or os.environ.get("DSR_AUTORIZACAO") or _na_raiz(AUTORIZACAO_NAME, cwd, session_id)

    autorizacao = ler_autorizacao(autz, session_id)
    limite, simult, ondas, tem_aval = teto(autorizacao)
    ja = contar_disparos(ledger, session_id)

    if ja < limite:
        return None

    if tem_aval:
        return _deny(
            f"DISPARO DE SUBAGENTE BLOQUEADO (governança §13): a sessão já disparou {ja} "
            f"agente(s) e a autorização vigente cobre {limite} "
            f"({simult} simultâneos × {ondas} onda(s), escopo: "
            f"{autorizacao.get('escopo') or 'não declarado'}). Peça ao advogado aval EXPRESSO "
            f"para a onda adicional e atualize {AUTORIZACAO_NAME} ANTES de disparar.")
    return _deny(
        f"DISPARO DE SUBAGENTE BLOQUEADO (governança §13): sem aval expresso o teto é "
        f"{PADRAO_SIMULTANEOS} agentes em 1 onda, e a sessão já disparou {ja}. "
        f"{_onde_procurou(autz, session_id)} "
        f"Aprovação vale ANTES do efeito: peça o aval ao advogado e registre "
        f"{AUTORIZACAO_NAME} na RAIZ DO CASO rodando "
        f"`python scripts/autorizar_subagentes.py --session-id {session_id or '<id da sessão>'} "
        f"--max-simultaneos N --ondas N --escopo \"...\"` (ele resolve a raiz e preenche "
        f"'concedido_em'). A turma do Conselho (5 +2 do art. 942) é o caso previsto — "
        f"mas também exige o aval registrado.")


def _onde_procurou(autz, session_id):
    'O que a recusa consultou (E7 do teste do titular, 22/10/2026): a sessão corrente e o'


    sessao = session_id or "(sem id de sessão no evento)"
    try:
        d = json.loads(open(autz, encoding="utf-8").read()) if _full_str(autz) and os.path.exists(autz) else None
    except Exception:
        d = None
    if isinstance(d, dict) and _full_str(d.get("session_id")) and d.get("session_id").strip() != session_id.strip():
        return (f"Há aval em {autz}, mas para a sessão {d.get('session_id').strip()}, e esta sessão é "
                f"{sessao}: o aval vale por sessão.")
    return f"Procurei o aval em {autz or '(raiz do caso não resolvida)'}, para a sessão {sessao}, e não há."


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
