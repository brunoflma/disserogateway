#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'aviso_completude.py — hook PreToolUse: AVISO de completude (só aviso, nunca bloqueia).'
















import sys, os, json, re

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
try:
    import gate_entrega as _ge
except Exception:
    _ge = None

_MSG = ("[Dissero · completude] Você está redigindo prosa (.md) mas o briefing/intake desta peça ainda "
        "não está concluído no PECA_STATE. Rode o intake do dissero-orquestrador e "
        "medir_completude.py ANTES de redigir — evita retrabalho e peça sobre base fraca. "
        "(Aviso, não bloqueio.)")

_MSG_CAMPOS = ("[Dissero · completude] Você está redigindo prosa (.md) e o briefing desta peça ainda tem "
               "campo obrigatório em branco: {campos}. Preencha no intake do dissero-orquestrador e "
               "rode medir_completude.py ANTES de redigir — hoje um campo em branco bloqueia a "
               "peça inteira, não só a parte que depende dele. (Aviso, não bloqueio.)")



_MSG_PARCIAL_TUDO = ("[Dissero · completude] Você está redigindo prosa (.md) e o briefing desta peça ainda "
                     "tem campo obrigatório em branco: {campos}. O que falta bloqueia TODAS as "
                     "subtarefas declaradas ({bloqueadas}) — aqui não há parada parcial possível. "
                     "Preencha no intake do dissero-orquestrador e rode medir_completude.py ANTES de "
                     "redigir. (Aviso, não bloqueio.)")






_RE_CAMPO = re.compile(r"[a-z0-9_]{1,40}")














_FASE_DA_SUBTAREFA = {
    "calculo_de_prazo": "prazo",
    "estrategia": "estrategia",
    "mapa": "mapa",
    "redacao_fatos": "redacao",
    "redacao_fundamentacao": "redacao",
    "redacao_pedidos": "redacao",
    "verificacao": "verificacao",
    "entrega": "entrega",
    "pesquisa_precedentes": "verificacao",
    "qualificacao_partes": None,
    "juntada_documental": None,
}


def _separar_liberadas(liberadas):
    '(adiantaveis, do_rito). FAIL-CLOSED: nome que a tabela nao classifica cai em `do_rito`.'




    adiantaveis, do_rito = [], []
    for s in liberadas:
        (adiantaveis if _FASE_DA_SUBTAREFA.get(s, "?") is None else do_rito).append(s)
    return adiantaveis, do_rito




_MSG_PARCIAL_ADIANTAVEL = (
    "[Dissero · completude] Você está redigindo prosa (.md) e o briefing desta peça ainda tem campo "
    "obrigatório em branco: {campos}. PARADA PARCIAL: o que falta bloqueia {bloqueadas}. Dá "
    "para adiantar agora, porque não depende do campo nem do rito: {adiantaveis}. ATENÇÃO: "
    "{do_rito} depende(m) do rito, e com briefing fraco o `estado_peca.py` devolve a peça "
    "inteira como BLOQUEADA — não comece por aí. Para destravar, preencha no intake do "
    "dissero-orquestrador SÓ o campo que falta e rode medir_completude.py. (Aviso, não bloqueio.)")



_MSG_PARCIAL_SO_RITO = (
    "[Dissero · completude] Você está redigindo prosa (.md) e o briefing desta peça ainda tem campo "
    "obrigatório em branco: {campos}. O que falta bloqueia {bloqueadas}. O resto ({do_rito}) é "
    "fase do rito, e com briefing fraco o `estado_peca.py` devolve a peça inteira como "
    "BLOQUEADA — não há o que adiantar aqui. Preencha no intake do dissero-orquestrador e rode "
    "medir_completude.py ANTES de redigir. (Aviso, não bloqueio.)")


def _campos_ausentes(briefing):
    'Nomes de campo ausentes declarados na evidência da fase briefing, na ORDEM do intake'

    return _lista_de_nomes(briefing, "estrela_ausentes")


def _lista_de_nomes(briefing, chave):
    'Nomes declarados em `evidencia[chave]`, na ordem, sem repetir e com filtro de FORMA'



    if not isinstance(briefing, dict):
        return []
    ev = briefing.get("evidencia")
    if not isinstance(ev, dict):
        return []
    bruto = ev.get(chave)
    if not isinstance(bruto, list):
        return []
    saida = []
    for nome in bruto:
        if isinstance(nome, str) and _RE_CAMPO.fullmatch(nome.strip()) and nome.strip() not in saida:
            saida.append(nome.strip())
    return saida


def _mensagem(briefing):
    'A mensagem certa para este briefing, da mais informativa para a genérica.'




    campos = _campos_ausentes(briefing)
    if not campos:
        return _MSG
    bloqueadas = _lista_de_nomes(briefing, "partes_bloqueadas")
    if not bloqueadas:


        return _MSG_CAMPOS.format(campos=", ".join(campos))
    liberadas = _lista_de_nomes(briefing, "partes_liberadas")
    if not liberadas:
        return _MSG_PARCIAL_TUDO.format(campos=", ".join(campos),
                                        bloqueadas=", ".join(bloqueadas))
    adiantaveis, do_rito = _separar_liberadas(liberadas)
    if not adiantaveis:
        return _MSG_PARCIAL_SO_RITO.format(campos=", ".join(campos),
                                           bloqueadas=", ".join(bloqueadas),
                                           do_rito=", ".join(do_rito))
    return _MSG_PARCIAL_ADIANTAVEL.format(
        campos=", ".join(campos), bloqueadas=", ".join(bloqueadas),
        adiantaveis=", ".join(adiantaveis),
        do_rito=", ".join(do_rito) if do_rito else "as demais fases")


def _eh_md(p):
    return isinstance(p, str) and p.strip().strip('"').strip("'").rstrip(". ").lower().endswith(".md")


def _is_tmp(p):
    return _ge._is_tmp(p) if _ge is not None else False


def _localizar_state(alvo, cwd):
    if _ge is not None:
        return _ge._localizar_state(alvo, cwd)
    cand = os.path.join(cwd or os.getcwd(), "PECA_STATE.json")
    return cand if os.path.exists(cand) else None


def aviso(evento):
    """Núcleo: retorna dict de additionalContext (advisory) OU None. Nunca deny."""
    if not isinstance(evento, dict):
        return None
    if evento.get("tool_name") not in ("Write", "Edit"):
        return None
    ti = evento.get("tool_input")
    if not isinstance(ti, dict):
        return None
    fp = ti.get("file_path") or ""
    if not (_eh_md(fp) and not _is_tmp(fp)):
        return None

    cwd = evento.get("cwd") if (isinstance(evento.get("cwd"), str) and evento.get("cwd").strip()) else os.getcwd()
    state_path = _localizar_state(fp, cwd)
    if not state_path:
        return None
    try:
        st = json.loads(open(state_path, encoding="utf-8").read())
        briefing = (st.get("fases") or {}).get("briefing") or {}
        concluido = briefing.get("status") == "concluida"
    except Exception:
        return None
    if concluido:




        return _aviso_de_squad(st, state_path)

    msg = _mensagem(briefing)
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": msg}}



_MSG_SQUAD = ("[Dissero · squad] A redação está começando e esta peça EXIGE squad, mas %s. O squad é "
              "obrigatório por determinação do advogado, para que a leitura dos autos seja "
              "repartida entre agentes e nenhuma página fique sem leitor. Rode `squad.py init --area <área do caso>` "
              "e conclua a etapa `memoria` antes de redigir — a entrega será BARRADA sem isso. "
              "Se esta peça dispensa o squad, declare o motivo em `estado_peca.py init "
              "--sem-squad \"<motivo>\"`.")


def _aviso_de_squad(st, state_path):
    'Lembrete de squad no começo da REDAÇÃO. Só aviso: nunca emite permissionDecision.'










    if st.get("exigir_squad") is not True:
        return None
    caminho = os.path.join(os.path.dirname(os.path.abspath(state_path)), "SQUAD_STATE.json")
    if not os.path.isfile(caminho):
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                "additionalContext": _MSG_SQUAD % "não há SQUAD_STATE.json na pasta do caso"}}
    try:
        squad = json.loads(open(caminho, encoding="utf-8").read())
        memoria = ((squad.get("etapas") or {}).get("memoria") or {})
    except Exception:
        return None
    if memoria.get("status") == "concluida":
        return None
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
            "additionalContext": _MSG_SQUAD % ("a etapa `memoria` do squad ainda está em %r"
                                               % memoria.get("status"))}}


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
        saida = aviso(ev)
    except Exception:
        saida = None
    if saida:


        print(json.dumps(saida, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
