#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'gate_entrega_subagente.py — hook SubagentStop: rede de segurança do gate de entrega.'















































import sys, os, json, re, time

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



PRAZO_HOOK_S = 40

FOLGA_S = 5


def _detectar(nome, inp, cwd=None):
    'A entrega de peça desta chamada, pela detecção do gate PreToolUse, com o .docx achado também'


    if _ge is None:
        return None
    with _ge._modo_caminho(nome, inp, cwd if cwd is not None else os.getcwd()):
        return _ge._detectar_entrega(nome, inp)


def _tool_uses(obj):
    'Coleta (nome, input) de TODO tool_use em qualquer estrutura JSON (dict/list, aninhados a'


    out = []

    def walk(o):
        if isinstance(o, dict):
            if o.get("type") == "tool_use" and isinstance(o.get("name"), str):
                inp = o.get("input")
                if not isinstance(inp, dict):
                    inp = (o.get("parameters") if isinstance(o.get("parameters"), dict)
                           else o.get("args") if isinstance(o.get("args"), dict) else {})
                out.append((o.get("name"), inp or {}))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(obj)
    return out


def _coletar(chamadas, out, vistos, cwd=None):
    """Acrescenta a `out` cada chamada que é entrega de peça, sem repetir a mesma chamada."""
    for nome, inp in chamadas:
        alvo = _detectar(nome, inp, cwd)
        if not alvo:
            continue
        try:
            chave = (nome, json.dumps(inp, sort_keys=True, ensure_ascii=False))
        except Exception:
            chave = (nome, repr(inp))
        if chave not in vistos:
            vistos.add(chave)
            out.append((alvo, nome, inp))


def _entregas(path, cwd=None):
    '[(alvo, nome da ferramenta, input)] de cada entrega de peça do transcript, na ordem.'


    return _entregas_de(_chamadas_brutas(path), cwd)


def _entregas_de(chamadas, cwd=None):
    """[(alvo, nome da ferramenta, input)] de cada chamada que é entrega de peça, sem repetir."""
    out, vistos = [], set()
    _coletar(chamadas, out, vistos, cwd)
    return out


def _chamadas(path):
    """(nome, input) de cada tool_use do transcript, como em `_entregas`."""
    if _ge is None:
        return []
    return _chamadas_brutas(path)


def _chamadas_brutas(path):
    '(nome, input) de cada tool_use do transcript: JSONL (uma linha por evento) ou, sem nada'

    if not (isinstance(path, str) and path and os.path.isfile(path)):
        return []
    try:
        raw = open(path, encoding="utf-8").read()
    except Exception:
        return []
    out = []
    for line in raw.splitlines():
        try:
            out += _tool_uses(json.loads(line))
        except Exception:
            continue
    if not out:
        try:
            out = _tool_uses(json.loads(raw))
        except Exception:
            out = []
    return out


def _copia_de_pasta(chamadas, cwd):
    'Motivo do block quando o subagente copiou ou arquivou uma pasta de caso com .docx para fora'


    if isinstance(chamadas, str):
        chamadas = _chamadas(chamadas)
    for nome, inp in chamadas:
        with _ge._modo_caminho(nome, inp, cwd):
            recusa = _ge._recusa_pasta_de_caso(nome, inp, _ge._cwd_da_chamada(nome, inp, cwd))
        if recusa:
            return recusa
    return None


def _leitor_com_transcript(chamadas):
    'Leitor de script que, quando o arquivo já não está em disco, usa o conteúdo do último Write'

    escritas = {}
    for nome, inp in chamadas:
        fp, conteudo = inp.get("file_path"), inp.get("content")
        if nome == "Write" and isinstance(fp, str) and isinstance(conteudo, str):
            try:
                escritas[_ge._chave_caminho(os.path.abspath(_ge._caminho_local(fp)))] = conteudo
            except (OSError, ValueError):
                continue

    def ler(caminho):
        texto, motivo = _ge._ler_script(caminho)
        if texto is None and motivo == "nao_achado":
            k = _ge._chave_caminho(caminho)
            if k in escritas:
                return escritas[k], None
        return texto, motivo
    return ler


def _expandir_scripts(chamadas, cwd):
    '(chamadas do transcript mais uma chamada sintética com o conteúdo de cada script que elas'

    leitor = _leitor_com_transcript(chamadas)
    out, fila, i = list(chamadas), list(chamadas), 0
    while i < len(fila) and len(out) < 500:
        nome, inp = fila[i]
        i += 1
        with _ge._modo_caminho(nome, inp, cwd):
            novas, recusa = _ge._scripts_da_chamada(nome, inp, _ge._cwd_da_chamada(nome, inp, cwd), leitor)
        if recusa:
            return out, recusa
        out += novas
        fila += novas
    return out, None


def _nao_entendido(chamadas, cwd):
    """Motivo do block da primeira chamada que cita .docx e que o gate não lê por inteiro, ou None."""
    for nome, inp in chamadas:
        with _ge._modo_caminho(nome, inp, cwd):
            recusa = _ge._recusa_nao_entendido(nome, inp, _ge._cwd_da_chamada(nome, inp, cwd), depois=True)
        if recusa:
            return recusa
    return None


def _pendencias(chamadas, cwd):
    'Motivo do block quando o subagente pediu a terceira via (`entregar --minuta-com-pendencias`,'



    for nome, inp in chamadas:
        with _ge._modo_caminho(nome, inp, cwd):
            pedidos = _ge._pedidos_de_pendencias(nome, inp, _ge._cwd_da_chamada(nome, inp, cwd))
        if pedidos:
            return ("Subagente pediu a entrega da minuta com pendências, e subagente nunca entrega "
                    "com pendências: a ordem é do advogado, a sessão principal é quem pergunta a "
                    "ele. Diga ao advogado o que saiu e confira com `estado_peca.py pode-entregar "
                    "--state <PECA_STATE do caso> --strict --docx <arquivo>`.")
    return None


def _entrega_no_transcript(path):
    """O .docx da primeira entrega de peça do transcript, ou None."""
    achados = _entregas(path)
    return achados[0][0] if achados else None


def _block(reason):
    return {"decision": "block", "reason": reason}


def _julgar_chamada(alvo, nome, inp, cwd):
    '(PECA_STATE que governa, origens em disco) de uma entrega do transcript, ou o block.'




    cwd = _ge._cwd_da_chamada(nome, inp, cwd)


    state_path, fora, recusa = _ge._state_da_entrega(nome, inp, alvo, cwd, depois=True)
    if recusa:
        return _block(f"Subagente entregou PEÇA ({_ge._nome(alvo)}) {recusa}")
    recusa = _ge._recusa_entre_casos(nome, inp, alvo, cwd, depois=True)
    if recusa:
        return _block(f"Subagente entregou PEÇA ({_ge._nome(alvo)}) {recusa}")
    recusa = _ge._recusa_origem(nome, inp, cwd, depois=True)
    if recusa:
        return _block(f"Subagente entregou PEÇA sem liberação: {recusa}")
    conferir = []
    if fora:


        state_path, conferir, recusa = _ge._state_fora_de_caso(state_path, fora, nome, inp, cwd,
                                                               depois=True)
        if recusa:
            return _block(f"Subagente entregou PEÇA ({_ge._nome(alvo)}) {recusa}")

    origens = _ge._origens_da_entrega(nome, inp, cwd, depois=True) + conferir
    recusa = _ge._recusa_upload(nome, inp, state_path, origens)
    if recusa:
        return _block(f"Subagente entregou PEÇA ({_ge._nome(alvo)}) {recusa}")
    return state_path, origens


def _decidir_entrega_sub(evento, runner=None, relogio=time.monotonic):
    """Entregas de peça do subagente: dict de block OU None (sem bloqueio)."""
    inicio = relogio()
    if not isinstance(evento, dict):
        return None
    cwd = evento.get("cwd") if (isinstance(evento.get("cwd"), str) and evento.get("cwd").strip()) else os.getcwd()
    chamadas = _chamadas(evento.get("agent_transcript_path"))
    if not chamadas:
        return None

    chamadas, recusa = _expandir_scripts(chamadas, cwd)
    if recusa:
        return _block(f"Subagente rodou um script que o gate de entrega não leu, e a peça pode ter "
                      f"saído sem conferência: {recusa} Diga ao advogado e confira o que saiu com "
                      f"`estado_peca.py pode-entregar --state <PECA_STATE do caso> --strict --docx "
                      f"<arquivo>`.")
    recusa = _pendencias(chamadas, cwd)
    if recusa:
        return _block(recusa)
    recusa = _nao_entendido(chamadas, cwd)
    if recusa:
        return _block(f"Subagente rodou um comando com .docx que o gate de entrega não lê por "
                      f"inteiro, e a peça pode ter saído sem conferência: {recusa} Diga ao advogado "
                      f"e confira o que saiu com `estado_peca.py pode-entregar --state <PECA_STATE "
                      f"do caso> --strict --docx <arquivo>`.")
    recusa = _copia_de_pasta(chamadas, cwd)
    if recusa:
        return _block(f"Subagente: {recusa}")
    entregas = _entregas_de(chamadas, cwd)
    if not entregas:
        return None

    runner = runner or _ge._runner_default



    grupos = {}
    for alvo, nome, inp in entregas:
        with _ge._modo_caminho(nome, inp, cwd):

            if _ge._arquivamento_em_versoes(nome, inp, alvo, _ge._cwd_da_chamada(nome, inp, cwd),
                                            depois=True):
                continue
            r = _julgar_chamada(alvo, nome, inp, cwd)
        if isinstance(r, dict):
            return r
        state_path, origens = r
        g = grupos.setdefault(state_path, {"origens": [], "hashes": set(), "sem_origem": False})
        if not origens:
            g["sem_origem"] = True
        for o in origens:
            try:
                h = _ge._sha256_arquivo(o)
            except OSError:
                continue
            if h not in g["hashes"]:
                g["hashes"].add(h)
                g["origens"].append(o)

    for state_path, g in grupos.items():
        recusa = _ge._recusa_canonico(state_path, g["origens"])
        if recusa:
            return _block(f"Subagente entregou PEÇA sem liberação: {recusa}")

    julgar = [(sp, o) for sp, g in grupos.items()
              for o in g["origens"] + ([None] if g["sem_origem"] else [])]
    for i, (state_path, origem) in enumerate(julgar):
        if relogio() - inicio + _ge.PRAZO_PODE_ENTREGAR_S + FOLGA_S > PRAZO_HOOK_S:
            faltam = ", ".join(os.path.basename(o) if o else "a peça registrada no PECA_STATE"
                               for _sp, o in julgar[i:])
            return _block(f"Subagente entregou {len(julgar)} peças, e o prazo deste hook "
                          f"({PRAZO_HOOK_S} s) só comportou julgar {i}. Ficaram sem julgamento: "
                          f"{faltam}. Rode `estado_peca.py pode-entregar --state <PECA_STATE do "
                          f"caso> --strict --docx <arquivo>` em cada uma e diga ao advogado o "
                          f"resultado.")
        recusa = _ge._julgar_uma(state_path, origem, runner)
        if recusa:
            return _block(f"Subagente entregou PEÇA sem liberação: {recusa}")
    return None

















SCHEMA_DEVOLUCAO = "dissero.devolucao_capitulo.v1"
_NUM_CAP = r"([0-9IVXLCDMivxlcdm]+(?:\.[0-9]+)?)\b"

MARCA_CAPITULO = re.compile(r"^[ \t>*_]*(?:Voc[eê] [eé] o\s+)?AGENTE DEDICADO do Cap[ií]tulo\s+" + _NUM_CAP, re.M)
CABECALHO_HANDOFF = re.compile(r"^#\s*HANDOFF\s*[—–-]+\s*CAP[IÍ]TULO\s+" + _NUM_CAP, re.I)
NOME_DEVOLUCAO = "DEVOLUCAO_CAP_{}.json"
NIVEIS_CONFIANCA = ("alta", "media", "baixa")
ESTADOS_FUNDAMENTO = ("confirmado", "pendente")
TIPOS_FUNDAMENTO = ("dispositivo", "julgado", "sumula", "prova", "doutrina")
MARCA_PENDENCIA = re.compile(r"==\[[^\]\n]+\]==")
VALOR_MONETARIO = re.compile(r"R\$\s*(\d[\d.,]*)")
MOTOR = re.compile(r"^[a-z0-9_]+\.py$")


MOTORES_SEM_FICHA = ("calcular_prazo.py", "calcular_prescricao.py", "calcular_verbas_rescisorias.py",
                     "honorarios_sucumbencia.py", "preparo_recursal.py")
REGISTRO_CAPACIDADES = ("skills", "dissero-orquestrador", "scripts", "capacidades_juridicas.json")

_ALVO_CONF = r"(?:confian[cç]a|chances?|probabilidade|[eê]xito|sucesso|certeza|acerto|vit[oó]ria|ganho)"
_PCT = r"\d+(?:[.,]\d+)?\s*(?:%|por\s*cento)"
PERCENTUAL_CONFIANCA = re.compile(
    _PCT + r"\s*(?:de\s+|da\s+|na\s+)?" + _ALVO_CONF
    + r"|" + _ALVO_CONF + r"\s*(?:de|em|é|e|:|=|estimad[ao]s?\s+em|de\s+cerca\s+de|de\s+aproximadamente)?\s*"
    + r"(?:cerca\s+de\s+|aproximadamente\s+|uns\s+)?" + _PCT, re.I)

QUALIFICACAO = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b|\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b"
                          r"|\bCPF\b|\bCNPJ\b|\bRG\b|\bLtda\b|\bS\.?/?A\.?(?=\s|$|[,;])|\bEIRELI\b", re.M)
DOC_NUMERO = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b")
_LINHA_LISTA = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$", re.M)
CAMPOS_DEVOLUCAO = ("schema", "capitulo", "dados_usados", "achados", "fundamentos", "ha_calculo",
                    "calculos", "confianca", "proximo_passo")

SECOES_BRIEFING = ("Tarefa", "Partes por papel processual", "Conteúdo-fonte", "Devolução")
PAPEIS = (
    "autor", "autora", "autores", "réu", "ré", "réus", "rés", "requerente", "requerido",
    "requerida", "reclamante", "reclamado", "reclamada", "exequente", "executado", "executada",
    "embargante", "embargado", "embargada", "apelante", "apelado", "apelada", "recorrente",
    "recorrido", "recorrida", "agravante", "agravado", "agravada", "impetrante", "impetrado",
    "autoridade coatora", "paciente", "terceiro", "terceira", "terceiros", "assistente",
    "litisconsorte", "denunciado", "denunciada", "chamado ao processo", "opoente", "interessado",
    "interessada", "ministério público", "querelante", "querelado", "querelada", "acusado",
    "acusada", "vítima", "credor", "devedor", "administrador judicial", "inventariante",
)



_PAPEL_LINHA = re.compile(
    r"^\s*[-*]\s*(?:\*\*)?(?:[oa]s?\s+)?(?:\d+\s*[ºª°o]?\.?\s+)?(?:(?:partes?|polos?)\s+(?:d[oa]s?\s+)?)?("
    + "|".join(sorted((re.escape(p) for p in PAPEIS + ("ativo", "passivo")), key=len, reverse=True))
    + r")(?:a|s|as|es)?\b", re.I | re.M)

EXEMPLO_PARTES = "«- Autora: pessoa física; ...» ou «- Ré: pessoa jurídica; ...»"


def _erro(codigo, detalhe):
    return {"codigo": codigo, "detalhe": detalhe}


def _texto_da_mensagem(msg):
    """Texto de uma mensagem do transcript: string, ou os blocos `text` de uma lista."""
    conteudo = msg.get("content") if isinstance(msg, dict) else None
    if isinstance(conteudo, str):
        return conteudo
    if isinstance(conteudo, list):
        return "\n".join(b.get("text", "") for b in conteudo
                         if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str))
    return ""


def _primeiro_pedido(path):
    """O texto do primeiro pedido (mensagem de usuário) do transcript do subagente, ou ''."""
    if not (isinstance(path, str) and path and os.path.isfile(path)):
        return ""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for linha in fh:
                try:
                    ev = json.loads(linha)
                except Exception:
                    continue
                if not isinstance(ev, dict):
                    continue
                msg = ev.get("message") if isinstance(ev.get("message"), dict) else ev
                if ev.get("type") == "user" or msg.get("role") == "user":
                    return _texto_da_mensagem(msg)
    except OSError:
        return ""
    return ""


def _mesmo_cap(a, b):
    return str(a).strip().upper() == str(b).strip().upper()


def capitulo_do_briefing(texto):
    'O número do capítulo quando o texto É o briefing do agente de capítulo, ou None.'




    texto = (texto or "").lstrip("﻿")
    primeira = next((ln for ln in texto.splitlines() if ln.strip()), "")
    m = MARCA_CAPITULO.match(primeira)
    if m:
        return m.group(1)
    c = CABECALHO_HANDOFF.match(primeira.strip())
    if not c:
        return None
    if any(_mesmo_cap(mm.group(1), c.group(1)) for mm in MARCA_CAPITULO.finditer(texto)):
        return c.group(1)
    return None


def _secao(texto, titulo):
    """O corpo da seção `## <n>. <titulo>` (ou `## <titulo>`) do briefing, ou None."""
    m = re.search(r"^#{2,3}\s*(?:\d+[A-Za-z-]*\.\s*)?" + re.escape(titulo) + r"[^\n]*\n(.*?)(?=^#{1,3}\s|\Z)",
                  texto or "", re.M | re.S | re.I)
    return m.group(1) if m else None


def validar_briefing(texto):
    'Erros do briefing do agente de capítulo: lista vazia quando ele vale sozinho.'









    texto = texto or ""
    erros = []
    if not capitulo_do_briefing(texto):
        erros.append(_erro("briefing_sem_marca",
                           "o briefing não começa por \"# HANDOFF — CAPÍTULO <N>\" com a linha "
                           "\"Você é o AGENTE DEDICADO do Capítulo <N>\""))
    faltam = [t for t in SECOES_BRIEFING if _secao(texto, t) is None]
    if faltam:
        erros.append(_erro("briefing_incompleto", "faltam as seções: " + ", ".join(faltam)))
    restantes = re.findall(r"\{\{[^}\n]*\}?\}?", texto)
    if restantes:
        erros.append(_erro("briefing_incompleto",
                           f"{len(restantes)} campo(s) do template sem preencher, como {restantes[0]}"))
    partes = _secao(texto, "Partes por papel processual")
    if partes is not None:
        linhas = [m.group(0) for m in _LINHA_LISTA.finditer(partes)]
        sem_papel = [ln.strip() for ln in linhas if not _PAPEL_LINHA.match(ln)]
        if not linhas or sem_papel:
            erros.append(_erro("briefing_sem_partes",
                               "cada parte vem numa linha de lista que começa pelo papel processual, "
                               "com ou sem artigo, no singular ou no plural (autor, réu, requerentes, "
                               f"credora, terceiro...), como no Template 3: {EXEMPLO_PARTES}"
                               + (f"; linha não reconhecida: {sem_papel[0][:60]}" if sem_papel else
                                  "; a seção não tem nenhuma linha de lista")))
        if any(QUALIFICACAO.search(ln) for ln in linhas):
            erros.append(_erro("briefing_com_qualificacao",
                               "a seção de partes traz documento pessoal ou razão social; nome e "
                               "qualificação ficam nas REGRAS do caso"))



    cabecalho = re.split(r"^#{2,3}\s", texto, maxsplit=1, flags=re.M)[0]
    if (QUALIFICACAO.search(cabecalho) or DOC_NUMERO.search(texto)) and not any(
            e["codigo"] == "briefing_com_qualificacao" for e in erros):
        erros.append(_erro("briefing_com_qualificacao",
                           "o cabeçalho ou o corpo do briefing traz documento pessoal ou razão social; "
                           "identifique o caso pelo código opaco (caso-…) e deixe nome e qualificação "
                           "nas REGRAS do caso"))
    return erros


def _nao_vazio(v):
    return isinstance(v, str) and bool(v.strip())


def motores_de_conta(raiz=None):
    'Nomes dos motores de conta do plugin: os sem ficha (lista fixa) mais o `entrypoint` de cada'

    raiz = raiz or os.path.dirname(AQUI)
    nomes = set(MOTORES_SEM_FICHA)
    try:
        with open(os.path.join(raiz, *REGISTRO_CAPACIDADES), encoding="utf-8") as fh:
            reg = json.load(fh)
        for cap in reg.get("capacidades") or []:
            ep = cap.get("entrypoint") if isinstance(cap, dict) else None
            if isinstance(ep, str) and ep.endswith(".py"):
                nomes.add(os.path.basename(ep.replace("\\", "/")))
    except (OSError, ValueError, AttributeError):
        pass
    return nomes


def _motor_existe(motor, raiz=None):
    """O motor é motor de conta do plugin (lista fechada) e está em `skills/<skill>/scripts/`?"""
    if motor not in motores_de_conta(raiz):
        return False
    skills = os.path.join(raiz or os.path.dirname(AQUI), "skills")
    try:
        nomes = os.listdir(skills)
    except OSError:
        return False
    return any(os.path.isfile(os.path.join(skills, n, "scripts", motor)) for n in nomes)


def _memoria_existe(memoria, pasta, devolucao=None):
    'A memória é arquivo existente e não vazio (caminho absoluto ou relativo à pasta da'

    p = memoria.strip()
    p = p if os.path.isabs(p) else os.path.join(pasta or os.getcwd(), p)
    try:
        if not (os.path.isfile(p) and os.path.getsize(p) > 0) or p.lower().endswith(".py"):
            return False
        return not (devolucao and os.path.samefile(p, devolucao))
    except OSError:
        return False


def _valores(texto):
    """Os valores em reais do texto, pelos dígitos (`R$ 50.000,00` → '5000000')."""
    return {re.sub(r"\D", "", m.group(1)) for m in VALOR_MONETARIO.finditer(texto or "")} - {""}


def _valor_de_conta(dados):
    'Valor em reais nos achados que não veio de um dado lido com fonte (`dados_usados`): esse é'


    achados = dados.get("achados") if isinstance(dados.get("achados"), list) else []
    lidos = set()
    for d in dados.get("dados_usados") if isinstance(dados.get("dados_usados"), list) else []:
        if isinstance(d, dict) and _nao_vazio(d.get("fonte")):
            lidos |= _valores(str(d.get("uso") or ""))
    return bool(_valores("\n".join(a for a in achados if isinstance(a, str))) - lidos)


def validar_devolucao(dados, capitulo=None, raiz=None, pasta=None, devolucao=None):
    'Erros da devolução do agente de capítulo pelo contrato `dissero.devolucao_capitulo.v1`;'










    if not isinstance(dados, dict):
        return [_erro("devolucao_incompleta", "a devolução não é um objeto JSON")]
    erros = []
    faltam = [c for c in CAMPOS_DEVOLUCAO if c not in dados]
    if faltam:
        erros.append(_erro("devolucao_incompleta", "faltam os campos: " + ", ".join(faltam)))
    if "schema" in dados and dados.get("schema") != SCHEMA_DEVOLUCAO:
        erros.append(_erro("devolucao_incompleta", f"schema deve ser {SCHEMA_DEVOLUCAO}"))
    cap = dados.get("capitulo")
    if "capitulo" in dados and not (isinstance(cap, (str, int)) and str(cap).strip()):
        erros.append(_erro("devolucao_incompleta", "capitulo vazio"))
    elif capitulo is not None and cap is not None and str(cap).strip().upper() != str(capitulo).strip().upper():
        erros.append(_erro("capitulo_divergente",
                           f"a devolução é do Capítulo {cap}, e o briefing é do Capítulo {capitulo}"))

    usados = dados.get("dados_usados")
    if "dados_usados" in dados:
        if not isinstance(usados, list) or not usados:
            erros.append(_erro("devolucao_incompleta", "dados_usados tem de ser lista não vazia"))
        else:
            sem = [i + 1 for i, d in enumerate(usados)
                   if not (isinstance(d, dict) and _nao_vazio(d.get("fonte")) and _nao_vazio(d.get("uso")))]
            if sem:
                erros.append(_erro("dado_sem_fonte", "itens de dados_usados sem fonte ou uso: "
                                   + ", ".join(map(str, sem))))

    achados = dados.get("achados")
    if "achados" in dados and not (isinstance(achados, list) and achados
                                   and all(_nao_vazio(a) for a in achados)):
        erros.append(_erro("devolucao_incompleta", "achados tem de ser lista de textos não vazia"))

    fundamentos = dados.get("fundamentos")
    if "fundamentos" in dados:
        if not isinstance(fundamentos, list):
            erros.append(_erro("devolucao_incompleta", "fundamentos tem de ser lista"))
        else:
            for i, f in enumerate(fundamentos, 1):
                if not (isinstance(f, dict) and f.get("tipo") in TIPOS_FUNDAMENTO
                        and _nao_vazio(f.get("referencia")) and f.get("estado") in ESTADOS_FUNDAMENTO):
                    erros.append(_erro("fundamento_invalido",
                                       f"fundamento {i}: tipo ({'/'.join(TIPOS_FUNDAMENTO)}), "
                                       f"referencia e estado ({'/'.join(ESTADOS_FUNDAMENTO)}) obrigatórios"))
                elif f["estado"] == "pendente" and not MARCA_PENDENCIA.search(str(f.get("marca") or "")):
                    erros.append(_erro("fundamento_sem_marca",
                                       f"fundamento {i} está pendente e não traz a marca ==[...]== "
                                       f"que ficou no capítulo"))

    ha_calculo = dados.get("ha_calculo")
    calculos = dados.get("calculos")
    if "ha_calculo" in dados and not isinstance(ha_calculo, bool):
        erros.append(_erro("devolucao_incompleta", "ha_calculo tem de ser true ou false"))
    if "calculos" in dados and not isinstance(calculos, list):
        erros.append(_erro("devolucao_incompleta", "calculos tem de ser lista (vazia sem número)"))
    calculos = calculos if isinstance(calculos, list) else []
    if ha_calculo is False and calculos:
        erros.append(_erro("calculo_incoerente",
                           "ha_calculo é false e a lista calculos está preenchida; sem conta, calculos fica []"))
    if (ha_calculo is True or _valor_de_conta(dados)) and not calculos:
        erros.append(_erro("calculo_sem_motor",
                           "há número de conta no capítulo e nenhum cálculo aponta o motor e a memória"))
    for i, c in enumerate(calculos, 1):
        if not (isinstance(c, dict) and _nao_vazio(c.get("motor")) and _nao_vazio(c.get("memoria"))):
            erros.append(_erro("calculo_sem_motor", f"cálculo {i} sem motor ou sem memória"))
        elif not MOTOR.match(c["motor"].strip()) or not _motor_existe(c["motor"].strip(), raiz):
            erros.append(_erro("motor_desconhecido",
                               f"cálculo {i}: {c['motor']!r} não é motor de conta do plugin"))
        elif not _memoria_existe(c["memoria"], pasta, devolucao):
            erros.append(_erro("memoria_inexistente",
                               f"cálculo {i}: a memória {c['memoria']!r} não é arquivo gravado pelo "
                               f"motor (caminho relativo à pasta da devolução)"))

    conf = dados.get("confianca")
    if "confianca" in dados:
        if not (isinstance(conf, dict) and conf.get("nivel") in NIVEIS_CONFIANCA
                and _nao_vazio(conf.get("motivo"))):
            erros.append(_erro("confianca_invalida",
                               "confianca precisa de nivel (alta, media ou baixa) e motivo"))
        else:
            outros = {k: v for k, v in conf.items() if k not in ("nivel", "motivo")}
            if PERCENTUAL_CONFIANCA.search(conf["motivo"]) \
                    or re.search(r"%|por\s*cento", json.dumps(outros, ensure_ascii=False), re.I):
                erros.append(_erro("confianca_invalida",
                                   "a confiança não se exprime em percentual (chance, êxito, certeza)"))

    if "proximo_passo" in dados and not _nao_vazio(dados.get("proximo_passo")):
        erros.append(_erro("devolucao_incompleta", "proximo_passo vazio"))
    return erros


def _devolucao_pelo_shell(chamadas, nome_arq, cwd):
    'Caminho da devolução gravada por comando de shell: o arquivo com o nome dela, citado num'


    padrao = re.compile(r"""([^\s'"`<>|;&()=]*""" + re.escape(nome_arq) + r")", re.I)
    achado = None
    for nome, inp in chamadas:
        cmd = inp.get("command") if isinstance(inp, dict) else None
        if not isinstance(cmd, str) or nome_arq.casefold() not in cmd.casefold():
            continue
        base = inp.get("cwd") if _nao_vazio(inp.get("cwd")) else cwd
        for m in padrao.finditer(cmd):
            fp = m.group(1)
            if _ge is not None:
                try:
                    fp = _ge._caminho_local(fp)
                except Exception:
                    pass
            p = fp if os.path.isabs(fp) else os.path.join(base, fp)
            if os.path.isfile(p):
                achado = p
    return achado


def _devolucao_do_transcript(chamadas, capitulo, cwd):
    '(dados, erro, caminho) da devolução que o agente gravou: a do disco, ou o conteúdo do'


    nome_arq = NOME_DEVOLUCAO.format(capitulo)
    caminho, conteudo = None, None
    for nome, inp in chamadas:
        fp = inp.get("file_path") if isinstance(inp, dict) else None
        if nome in ("Write", "Edit", "MultiEdit") and isinstance(fp, str) \
                and os.path.basename(fp.replace("\\", "/")).casefold() == nome_arq.casefold():
            caminho = fp if os.path.isabs(fp) else os.path.join(cwd, fp)
            if nome == "Write" and isinstance(inp.get("content"), str):
                conteudo = inp["content"]
    if caminho is None:
        caminho = _devolucao_pelo_shell(chamadas, nome_arq, cwd)
    if caminho is None:
        return None, _erro("devolucao_ausente", f"o agente não gravou {nome_arq}"), None
    try:
        with open(caminho, encoding="utf-8") as fh:
            conteudo = fh.read()
    except OSError:
        pass
    try:
        return json.loads(conteudo), None, caminho
    except Exception:
        return None, _erro("devolucao_ilegivel", f"{nome_arq} não é JSON legível"), caminho


def _decidir_devolucao(evento):
    """Block quando o subagente é agente de capítulo e a devolução falta ou está incompleta."""
    path = evento.get("agent_transcript_path")
    capitulo = capitulo_do_briefing(_primeiro_pedido(path))
    if capitulo is None or evento.get("stop_hook_active") is True:
        return None
    cwd = evento.get("cwd") if _nao_vazio(evento.get("cwd")) else os.getcwd()
    dados, erro, caminho = _devolucao_do_transcript(_chamadas_brutas(path), capitulo, cwd)
    erros = [erro] if erro else validar_devolucao(dados, capitulo, pasta=os.path.dirname(caminho),
                                                  devolucao=caminho)
    if not erros:
        return None
    lista = "; ".join(f"{e['codigo']}: {e['detalhe']}" for e in erros)
    return _block(f"Agente do Capítulo {capitulo}: devolução recusada ({erros[0]['codigo']}). {lista}. "
                  f"Grave {NOME_DEVOLUCAO.format(capitulo)} com o Write pelo contrato do briefing "
                  f"(seção Devolução) e só então pare. Fundamento sem lastro fica no capítulo como "
                  f"pendência marcada ==[...]== e entra na devolução como pendente; número só com a "
                  f"memória do motor de cálculo. Não preencha lacuna para fechar a devolução.")


def decidir_sub(evento, runner=None, relogio=time.monotonic):
    'Núcleo: dado o evento SubagentStop, retorna dict de block OU None (sem bloqueio). A entrega'




    if _ge is not None and _ge._rito_estrito():
        saida = _decidir_entrega_sub(evento, runner=runner, relogio=relogio)
        if saida:
            return saida
    if not isinstance(evento, dict):
        return None
    return _decidir_devolucao(evento)


def _cli(argv):
    '`--validar-devolucao <arquivo> [--capitulo N]` ou `--validar-briefing <arquivo>`: imprime'


    import argparse
    ap = argparse.ArgumentParser(prog="gate_entrega_subagente.py")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--validar-devolucao")
    g.add_argument("--validar-briefing")
    ap.add_argument("--capitulo")
    a = ap.parse_args(argv)
    arquivo = a.validar_devolucao or a.validar_briefing
    try:
        with open(arquivo, encoding="utf-8") as fh:
            texto = fh.read()
    except OSError:
        erros = [_erro("devolucao_ausente" if a.validar_devolucao else "briefing_incompleto",
                       "arquivo não encontrado")]
    else:
        if a.validar_briefing:
            erros = validar_briefing(texto)
        else:
            try:
                erros = validar_devolucao(json.loads(texto), a.capitulo,
                                          pasta=os.path.dirname(os.path.abspath(arquivo)),
                                          devolucao=os.path.abspath(arquivo))
            except ValueError:
                erros = [_erro("devolucao_ilegivel", "o arquivo não é JSON legível")]
    print(json.dumps({"ok": not erros, "erros": erros}, ensure_ascii=False, indent=2))
    return 0 if not erros else 1


def _transcript_pode_ter_peca(raw):
    'O transcript do evento menciona `.docx` ou o tipo MIME do Word? Evento ou transcript'

    try:
        caminho = json.loads(raw).get("agent_transcript_path")
        if not (isinstance(caminho, str) and os.path.isfile(caminho)):
            return False
        with open(caminho, encoding="utf-8", errors="replace") as fh:
            texto = fh.read()
    except Exception:
        return False
    return (_ge.pode_ser_peca(texto) if _ge is not None
            else bool(re.search(r'\.docx|wordprocessingml|google-apps\.document', texto, re.I)))


def _block_falha(erro, ausente=False, repetida=False):
    'Block da falha do próprio gate. Nomeia só o tipo do erro: a mensagem dele pode trazer o'



    if repetida:
        if ausente:
            motivo = "o arquivo do gate de entrega (hooks/gate_entrega.py) não carregou"
            remedio = "atualize ou reinstale o plugin"
        else:
            motivo = f"o gate de entrega falhou ao conferir as entregas deste subagente ({erro})"
            remedio = ("confira se o Python 3 roda (python --version) e atualize ou reinstale "
                       "o plugin")
        return _block(f"Gate de entrega do plugin: Pare de tentar concluir a entrega. Avise o "
                      f"advogado que a peça não foi conferida porque {motivo} e diga o que "
                      f"instalar ou consertar: {remedio}. A entrega não é liberada.")
    return _block(f"Subagente: o gate de entrega falhou ao conferir as entregas deste subagente "
                  f"({erro}) e não as libera sem a conferência. Diga ao advogado que a peça "
                  f"entregue por este subagente não foi conferida pelo gate, e rode "
                  f"`estado_peca.py pode-entregar --state <PECA_STATE do caso> --strict --docx "
                  f"<arquivo>` em cada peça entregue.")


def main():
    'Lê o evento do stdin e imprime o block, quando há. A falha do gate (exceção interna, ou o'


    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""
    ev = {}
    try:
        ev = json.loads(raw) if raw and raw.strip() else {}
        if _ge is None:
            raise ImportError("gate_entrega")
        saida = decidir_sub(ev)
    except Exception as e:
        repetida = isinstance(ev, dict) and ev.get("stop_hook_active") is True

        estrito = os.environ.get("DSR_GATE_RITO_ESTRITO", "").strip() == "1"
        saida = (_block_falha(type(e).__name__, ausente=_ge is None, repetida=repetida)
                 if estrito and _transcript_pode_ter_peca(raw) else None)
    if saida:
        print(json.dumps(saida, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]) if len(sys.argv) > 1 else main())
