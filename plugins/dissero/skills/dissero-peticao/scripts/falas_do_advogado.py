#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'falas_do_advogado.py — o que o ADVOGADO escreveu nesta sessão, lido do registro da conversa.'































import glob
import hashlib
import json
import os
import re
import sys
import unicodedata

AQUI = os.path.dirname(os.path.abspath(__file__))

TETO_TRANSCRIPT = 256 * 1024 * 1024


_LEMBRETE = re.compile(r'<system-reminder>.*?(?:</system-reminder>|\Z)', re.S)
_ABRE_COLADO = re.compile(r'<pasted_content\b([^>]*)>', re.I)
_FECHA_COLADO = re.compile(r'</pasted_content\b([^>]*)>', re.I)
_ID_COLADO = re.compile(r'(?<![\w-])id\s*=\s*(?:"([^"]*)"|' + r"'([^']*)')", re.I)
_ASK_USER = re.compile(r'^mcp__(?:plugin_[^_]+_)?dissero-perguntas__ask_user$')
_ASPAS = "\"'`´«»“”‘’„‟‹›"


def normalizar(texto):
    """Texto comparável: sem acento, sem aspas, espaços colapsados, sem caixa."""
    s = unicodedata.normalize("NFKD", texto or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = "".join(" " if c.isspace() else c for c in s if c not in _ASPAS)
    return " ".join(s.split()).casefold()


def sem_colado(texto):
    'Só o que o advogado digitou: sem o colado e sem lembrete do sistema; None quando o colado'

    s = texto or ""
    ids = []
    for m in _ABRE_COLADO.finditer(s):
        mid = _ID_COLADO.search(m.group(1))
        if not mid:
            return None
        ids.append(mid.group(1) if mid.group(1) is not None else mid.group(2))
    if len(ids) != len(set(ids)):
        return None
    fechos = []
    for m in _FECHA_COLADO.finditer(s):
        mid = _ID_COLADO.search(m.group(1))
        fechos.append(None if not mid else (mid.group(1) if mid.group(1) is not None else mid.group(2)))
    if len(fechos) != len(set(fechos)) or any(f not in ids for f in fechos):
        return None
    out, i = [], 0
    while True:
        m = _ABRE_COLADO.search(s, i)
        if not m:
            out.append(s[i:])
            break
        out.append(s[i:m.start()] + " ")
        mid = _ID_COLADO.search(m.group(1))
        x = re.escape(mid.group(1) if mid.group(1) is not None else mid.group(2))
        fecho = re.compile(r'</pasted_content\s+id\s*=\s*(?:"' + x + r'"|' + "'" + x + "'" + r')\s*>', re.I)
        f = fecho.search(s, m.end())
        if not f:
            break
        i = f.end()
    return _LEMBRETE.sub(" ", "".join(out))


class Fala(str):
    'Uma fala do advogado. `marca_n`: quantas vezes o modelo já tinha dito o marcador (a'




    marca_n = 0
    origem = "digitada"
    do_livro = False
    outras_perguntas = 0


class Falas(list):
    'As falas, na ordem, com `marcas`: quantas vezes o modelo disse o marcador na cadeia (None'


    marcas = None
    saida_corte = None


def _fala(texto, marca_n, origem="digitada", do_livro=False):
    f = Fala(texto)
    f.marca_n = marca_n
    f.origem = origem
    f.do_livro = do_livro
    return f




_CITADO = re.compile(r'<(user_quoted_section|previous_session_context)\b[^>]*>.*?(?:</\1\s*>|\Z)', re.S | re.I)


def digitado(texto):
    """Só o digitado: sem colado, lembrete e trecho citado; None quando o colado é ambíguo."""
    t = sem_colado(texto)
    return None if t is None else _CITADO.sub(" ", t)


def _texto_de_conteudo(cont):
    if isinstance(cont, str):
        return cont
    if isinstance(cont, list):
        return "\n".join(b.get("text") for b in cont
                         if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str))
    return ""


def _respostas_ask_user(bloco, tur):
    candidatos = [tur] if isinstance(tur, dict) else []
    for fonte in (tur, bloco.get("content")):
        itens = fonte if isinstance(fonte, list) else [fonte] if isinstance(fonte, str) else []
        for item in itens:
            texto = item.get("text") if isinstance(item, dict) else item
            if isinstance(texto, str):
                try:
                    candidatos.append(json.loads(texto))
                except Exception:
                    continue
    out = []
    for c in candidatos:
        if isinstance(c, dict) and isinstance(c.get("structuredContent"), dict):
            c = c["structuredContent"]
        if isinstance(c, dict) and c.get("status") == "answered" and isinstance(c.get("answers"), list):
            out += [a.get("text") for a in c["answers"] if isinstance(a, dict) and isinstance(a.get("text"), str)]
    return out


def _casa(o, pred):
    """A linha é do modelo e chama ferramenta cuja entrada satisfaz `pred`."""
    if not pred or o.get("type") != "assistant":
        return False
    cont = (o.get("message") or {}).get("content") if isinstance(o.get("message"), dict) else None
    for b in cont if isinstance(cont, list) else []:
        if isinstance(b, dict) and b.get("type") == "tool_use":
            try:
                if pred(b.get("input")):
                    return True
            except Exception:
                continue
    return False


def _cadeia(objs, ancora=None):
    'uuids da cadeia `parentUuid` que chega à linha âncora: a última chamada de ferramenta do'



    pai, ultimo, achada = {}, None, None
    for o in objs:
        u = o.get("uuid")
        if not (isinstance(u, str) and u):
            continue
        pai[u] = o.get("parentUuid") or o.get("logicalParentUuid")
        if pai[u] or ultimo is None:
            ultimo = u
        if ancora and o.get("type") == "assistant":
            cont = (o.get("message") or {}).get("content") if isinstance(o.get("message"), dict) else None
            for b in cont if isinstance(cont, list) else []:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    try:
                        if ancora(b.get("input")):
                            achada = u
                    except Exception:
                        continue
    u = achada or ultimo
    if u is None:
        return None
    vistos = set()
    while isinstance(u, str) and u and u not in vistos:
        vistos.add(u)
        u = pai.get(u)
    return vistos


def falas_do_transcript(caminho, marca=None, ancora=None, corte=None):
    'Falas do advogado no transcript (`Falas`), na ordem, ou None quando o arquivo falta, passa'





    if not (isinstance(caminho, str) and caminho.strip()):
        return None
    try:
        if not os.path.isfile(caminho) or os.path.getsize(caminho) > TETO_TRANSCRIPT:
            return None
        with open(caminho, encoding="utf-8", errors="replace") as fh:
            linhas = fh.readlines()
    except (OSError, ValueError):
        return None
    objs = []
    for ln in linhas:
        if '"uuid"' not in ln:
            continue
        try:
            o = json.loads(ln)
        except Exception:
            continue
        if isinstance(o, dict):
            objs.append(o)
    cadeia = _cadeia(objs, ancora)
    if cadeia is None:
        return None
    u_ancora = None
    if ancora:
        for o in objs:
            if _casa(o, ancora):
                u_ancora = o.get("uuid")
    n_corte = [0]
    ids_corte = set()








    marcas_msg = {}
    pendentes = {}



    trechos = [normalizar(x) for x in ((marca,) if isinstance(marca, str) else (marca or ())) if normalizar(x)]
    n = [0]
    outras = [0]
    falas, nomes, entradas = Falas(), {}, {}

    def resultado_de_corte(b):
        tid = b.get("tool_use_id")
        antes = pendentes.pop(tid, None)
        if antes is None:
            return
        for outro in [k for k, v in pendentes.items() if v is antes]:
            pendentes.pop(outro, None)
        if b.get("is_error"):
            depois = list(falas)
            falas[:] = antes["falas"] + depois
            n_corte[0] = antes["n_corte"]
            outras[0] = antes["outras"] + outras[0]
            falas.saida_corte = antes["saida"]
            return
        falas.saida_corte = _texto_de_conteudo(b.get("content"))

    def digitada(texto, origem="digitada"):
        t = digitado(texto)
        if t is not None and t.strip():
            f = _fala(t, n[0], origem)
            f.outras_perguntas = outras[0]
            falas.append(f)

    for o in objs:
        if o.get("uuid") not in cadeia:
            m_fora = o.get("message") if isinstance(o.get("message"), dict) else {}
            c_fora = m_fora.get("content")
            if o.get("type") == "user" and pendentes and isinstance(c_fora, list):
                for b in c_fora:
                    if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id") in pendentes:
                        resultado_de_corte(b)
            continue
        if o.get("isSidechain") or o.get("isMeta") or o.get("isCompactSummary"):
            continue
        tipo = o.get("type")
        if tipo == "attachment":
            a = o.get("attachment")
            if (isinstance(a, dict) and a.get("type") == "queued_command"
                    and isinstance(a.get("origin"), dict) and a["origin"].get("kind") == "human"
                    and a.get("commandMode", "prompt") == "prompt"):

                digitada(_texto_de_conteudo(a.get("prompt")), "enfileirada")
            continue
        msg = o.get("message")
        if not isinstance(msg, dict):
            continue
        cont = msg.get("content")
        if tipo == "assistant":
            mid = msg.get("id") if isinstance(msg.get("id"), str) else None
            if corte and o.get("uuid") != u_ancora and _casa(o, corte):
                antes = {"falas": list(falas), "n_corte": n_corte[0], "outras": outras[0],
                         "saida": falas.saida_corte}
                del falas[:]
                n_corte[0] = n[0] - (marcas_msg.get(mid, 0) if mid else 0)
                outras[0] = 0
                ids_corte = {b.get("id") for b in cont if isinstance(b, dict) and b.get("type") == "tool_use"
                             and _casa({"type": "assistant", "message": {"content": [b]}}, corte)}
                for tid in ids_corte:
                    pendentes[tid] = antes
                falas.saida_corte = None
            visivel = _texto_de_conteudo(cont)
            caixa = ""
            for b in cont if isinstance(cont, list) else []:
                if isinstance(b, dict) and b.get("type") == "tool_use" and isinstance(b.get("id"), str):
                    nomes[b["id"]] = b.get("name")
                    entradas[b["id"]] = b.get("input")
                    if b.get("name") == "AskUserQuestion" or (isinstance(b.get("name"), str) and _ASK_USER.match(b["name"])):
                        try:
                            caixa += "\n" + json.dumps(b.get("input"), ensure_ascii=False)
                        except Exception:
                            pass
            dito = normalizar(visivel + caixa)
            if trechos and all(t in dito for t in trechos):
                n[0] += 1
                outras[0] = 0
                if mid:
                    marcas_msg[mid] = marcas_msg.get(mid, 0) + 1
            elif "?" in visivel or caixa:
                outras[0] += 1
            continue
        if tipo != "user" or msg.get("role", "user") != "user":
            continue
        resultados = ([b for b in cont if isinstance(b, dict) and b.get("type") == "tool_result"]
                      if isinstance(cont, list) else [])
        if resultados:
            tur = o.get("toolUseResult")
            for b in resultados:
                if b.get("tool_use_id") in pendentes:
                    resultado_de_corte(b)
                if b.get("is_error"):
                    continue
                nome = nomes.get(b.get("tool_use_id"))
                respostas = []
                if nome == "AskUserQuestion":


                    if isinstance(tur, dict) and isinstance(tur.get("answers"), dict):
                        for q, v in tur["answers"].items():
                            if isinstance(v, str):
                                da_marca = bool(trechos) and trechos[0] in normalizar(str(q))
                                respostas.append((v, "caixa" if da_marca or not trechos else "caixa_outra"))
                elif isinstance(nome, str) and _ASK_USER.match(nome):
                    lista = _respostas_ask_user(b, tur)


                    try:
                        da_marca = not trechos or trechos[0] in normalizar(
                            json.dumps(entradas.get(b.get("tool_use_id")), ensure_ascii=False))
                    except Exception:
                        da_marca = False
                    respostas = [(r, "caixa" if len(lista) == 1 and da_marca else "caixa_outra") for r in lista]
                for r, orig in respostas:
                    if r.strip():
                        f = _fala(r, n[0], orig)
                        f.outras_perguntas = max(0, outras[0] - 1)
                        falas.append(f)
            continue
        origem = o.get("origin")
        humano = (isinstance(origem, dict) and origem.get("kind") == "human") or (
            origem is None and o.get("turnOrigin") == "human")
        if humano:
            digitada(_texto_de_conteudo(cont))
    falas.marcas = n[0] if n[0] > n_corte[0] else (0 if corte and n_corte[0] else n[0])
    return falas


def pasta_config(env=None):
    env = os.environ if env is None else env
    c = str(env.get("CLAUDE_CONFIG_DIR") or "").strip()
    return os.path.abspath(c) if c else os.path.join(os.path.expanduser("~"), ".claude")


def localizar_transcript(env=None):
    '(caminho, None) ou (None, motivo). Só um arquivo com o id da sessão, dentro de'

    env = os.environ if env is None else env
    sid = str(env.get("CLAUDE_CODE_SESSION_ID") or "").strip()
    if not sid:
        return None, "a sessão não informa o próprio id (sem CLAUDE_CODE_SESSION_ID)"
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", sid):
        return None, "o id da sessão tem forma inesperada"
    achados = glob.glob(os.path.join(glob.escape(pasta_config(env)), "projects", "*", sid + ".jsonl"))
    if len(achados) != 1:
        return None, ("o registro desta sessão não foi achado no disco" if not achados
                      else "há mais de um registro com o id desta sessão")
    return achados[0], None


def _registro_falas():
    """O módulo do livro de falas (hooks/registro_falas.py da mesma cópia do plugin), ou None."""
    for cand in (os.path.join(AQUI, "..", "..", "..", "hooks"), os.path.join(AQUI, "..", "hooks")):
        cand = os.path.abspath(cand)
        if os.path.isfile(os.path.join(cand, "registro_falas.py")):
            if cand not in sys.path:
                sys.path.append(cand)
            try:
                import registro_falas
                return registro_falas
            except Exception:
                return None
    return None


def _superficie_remota(env):
    remoto = str(env.get("CLAUDE_CODE_REMOTE") or "").strip().lower() in ("true", "1")
    entrada = str(env.get("CLAUDE_CODE_ENTRYPOINT") or "").strip().lower().startswith("remote")
    return remoto or entrada


def falas_do_livro(session_id, livro=None):
    '(falas, None) ou (None, motivo), do livro de falas da sessão. O livro não guarda o que o'

    rf = livro if livro is not None else _registro_falas()
    if rf is None:
        return None, "o leitor do livro de falas não está nesta cópia do plugin"
    try:
        estado, linhas = rf.ler_livro(session_id)
    except Exception:
        return None, "o livro de falas não se lê"
    if estado != "ok":
        return None, ("o livro de falas desta sessão não existe ou está vazio" if estado == "ausente"
                      else "o livro de falas desta sessão está ilegível")
    falas = Falas(_fala(digitado(l["texto"]) or "", None, do_livro=True) for l in linhas
                  if isinstance(l.get("texto"), str) and l["texto"].strip())
    return Falas(f for f in falas if f.strip()), None


def falas_da_sessao(env=None, marca=None, ancora=None, livro=None, corte=None):
    """(falas, fonte, motivo). fonte: "transcript", "livro_de_falas" ou None (motivo diz por quê)."""
    env = os.environ if env is None else env
    try:
        caminho, motivo = localizar_transcript(env)
        if caminho:
            falas = falas_do_transcript(caminho, marca, ancora, corte)
            if falas is not None:
                return falas, "transcript", None
            motivo = "o registro desta sessão não se lê"
        if _superficie_remota(env):
            sid = str(env.get("CLAUDE_CODE_SESSION_ID") or "").strip()
            if sid:
                falas, m2 = falas_do_livro(sid, livro)
                if falas is not None:
                    return falas, "livro_de_falas", None
                motivo = m2
    except Exception as e:
        return None, None, f"a leitura do registro da conversa falhou ({type(e).__name__})"
    return None, None, motivo


def resposta_a_pergunta(falas, escolhe=None):
    '(fala, None) ou (None, motivo): a RESPOSTA do advogado à pergunta.'








    if not falas:
        return None, "não há mensagem do advogado nesta sessão"
    if falas.marcas is None:
        return falas[-1], None
    if not falas.marcas:
        return None, "a pergunta da escolha não foi feita nesta sessão com o texto fixo e as duas opções"
    for f in falas:
        if f.marca_n != falas.marcas or f.origem not in ("digitada", "caixa"):
            continue
        if f.outras_perguntas:
            break
        if escolhe is None or escolhe(f):
            return f, None
    return None, "a pergunta da escolha foi feita e o advogado ainda não respondeu com uma das opções"
