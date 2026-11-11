#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'relatorio_retencao.py — relatório de retenção dos casos registrados e da raiz local segura.'
















































import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import time
import zipfile
from datetime import date, datetime

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
try:
    import caso_raiz
except Exception:
    caso_raiz = None

SCHEMA = "dsr.relatorio_retencao.v1"
DIR_RETENCAO = "retencao"
ARQ_SITUACAO = "situacao.json"
ARQ_REGISTRO = "registro.jsonl"
ARQ_AVAL = "AUTORIZACAO_RETENCAO.json"
ARQ_CASO_ID = "CASO_ID.json"
DIR_ARQUIVO_SEGURO = "_arquivo"
PREFIXO_QUARENTENA = ".dsr-saindo-"
ENV_RAIZ_SEGURA = "DSR_PSEUDONIMIZACAO_LOCAL_ROOT"
ENV_CASO_RAIZ = "DSR_CASO_RAIZ"
RE_CASO_ID = re.compile(r"^caso-[0-9a-f]{12}$")
CHAVES_CASO_ID = {"caso_id", "criado_em"}
SITUACOES = ("ativo", "encerrado")
ACOES = ("arquivar", "remover")
JANELA_SESSAO_RECENTE_H = 12

MENSAGENS = {
    "caso_id_invalido": "o código do caso não está no formato caso-<12 hexadecimais>",
    "caso_nao_encontrado": "nenhum caso registrado tem esse código",
    "caso_id_duplicado": "duas pastas existentes levam o mesmo código de caso; resolva antes qual é o caso",
    "caso_ativo": "o caso não está marcado como encerrado; caso ativo não sai",
    "caso_em_uso": "o caso está aberto agora ou foi aberto há pouco; feche-o ou abra outro antes",
    "caso_contem_outro_caso": "a pasta do caso contém a pasta de outro caso registrado; nada foi apagado",
    "caso_dentro_de_outro_caso": "a pasta do caso fica dentro da pasta de outro caso registrado; nada foi apagado",
    "aval_ausente": "não há aval do advogado registrado para retenção",
    "aval_ilegivel": "o aval registrado está ilegível; registre de novo",
    "aval_de_outra_sessao": "o aval registrado é de outra sessão; peça de novo ao advogado",
    "caso_fora_do_aval": "o advogado não autorizou este caso",
    "acao_fora_do_aval": "o aval cobre só o arquivamento, não a remoção",
    "destino_efemero": "o destino do arquivo é pasta temporária; escolha pasta que dure",
    "ambiente_efemero": "este ambiente é apagado ao fim da sessão; o arquivo não sobreviveria",
    "destino_dentro_do_caso": "o arquivo não pode ficar dentro da pasta que vai sair",
    "nada_a_arquivar": "não há pasta do caso nem material na raiz segura para arquivar",
    "arquivo_nao_conferido": "o pacote gravado não passou na conferência; nada foi removido",
    "sem_arquivo_previo": "o caso não foi arquivado antes; arquive primeiro",
    "arquivo_ausente": "o pacote do arquivamento não está mais onde foi gravado",
    "arquivo_divergente": "o pacote do arquivamento mudou depois de gravado",
    "pasta_mudou_depois_do_arquivo": "a pasta mudou depois do arquivamento; arquive de novo",
    "caso_id_divergente": "a pasta não traz mais o código deste caso; nada foi removido",
    "raiz_protegida": "a pasta é raiz de disco, pasta pessoal ou contém pasta do próprio sistema",
    "arquivo_somente_leitura": ("há arquivo ou pasta protegido contra gravação dentro do caso; "
                                "nada foi apagado. Tire a proteção, se o advogado quiser, e repita"),
    "pasta_bloqueada": "o sistema não liberou a pasta (arquivo aberto em outro programa?); nada foi apagado",
    "remocao_incompleta": ("a remoção parou no meio. O que faltou sair ficou numa pasta de nome "
                           "iniciado por .dsr-saindo- ao lado da original, e o pacote do arquivamento "
                           "continua guardado"),
    "falha_ao_gravar": "não foi possível gravar",
    "falha_inesperada": "erro inesperado; confira o relatório antes de repetir",
}


def _s(x):
    return isinstance(x, str) and bool(x.strip())


def _agora():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _norm(p):
    return os.path.normcase(os.path.realpath(os.path.abspath(p)))


def _dentro(filho, pai):
    """True quando `filho` é `pai` ou está abaixo dele."""
    try:
        return os.path.commonpath([_norm(filho), _norm(pai)]) == _norm(pai)
    except ValueError:
        return False


def _ler_json(p):
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def _gravar_json(p, obj):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False, indent=2))
    os.replace(tmp, p)


def _data(valor):
    """date de 'AAAA-MM-DD...' ou None."""
    if not _s(valor):
        return None
    try:
        return date.fromisoformat(valor.strip()[:10])
    except ValueError:
        return None


def _momento(valor):
    """datetime de 'AAAA-MM-DDTHH:MM:SS...' ou None."""
    if not _s(valor):
        return None
    try:
        return datetime.fromisoformat(valor.strip()[:19])
    except ValueError:
        return None



def base_dir(override=None):
    if _s(override):
        return os.path.abspath(override.strip())
    if caso_raiz is not None:
        return caso_raiz.base_dir()
    b = os.environ.get("DSR_CASO_BASE")
    return os.path.abspath(b.strip()) if _s(b) else os.path.join(os.path.expanduser("~"), ".dissero")


def raiz_segura(override=None):
    """Mesma resolução de `pseudonimizar_local.raiz_local_segura` (o teste confere que batem)."""
    if _s(override):
        base = override.strip()
    elif _s(os.environ.get(ENV_RAIZ_SEGURA)):
        base = os.environ[ENV_RAIZ_SEGURA]
    elif _s(os.environ.get("LOCALAPPDATA")):
        base = os.path.join(os.environ["LOCALAPPDATA"], "Dissero", "pseudonimizacao")
    else:
        base = os.path.join(os.path.expanduser("~"), ".local", "share", "dissero", "pseudonimizacao")
    return os.path.realpath(os.path.abspath(base))


def _dir_ret(base):
    return os.path.join(base, DIR_RETENCAO)


def _slug(session_id):
    if caso_raiz is not None:
        return caso_raiz._slug(session_id)
    return re.sub(r"[^A-Za-z0-9._-]", "_", (session_id or "").strip())[:120] or "sem-sessao"



def _ler_caso_id(raiz):
    "(código, criado_em, erro). Ausente → (None, None, None); malformado → erro 'caso_id_invalido'."

    p = os.path.join(raiz, ARQ_CASO_ID)
    if not os.path.isfile(p):
        return None, None, None
    d = _ler_json(p)
    if caso_raiz is not None:
        try:
            cid = caso_raiz.ler_caso_id(raiz)
        except (caso_raiz.CasoIdInvalido, OSError):
            return None, None, "caso_id_invalido"
    else:
        cid = d.get("caso_id") if isinstance(d, dict) else None
        if not (isinstance(cid, str) and RE_CASO_ID.match(cid)) or not set(d) <= CHAVES_CASO_ID:
            return None, None, "caso_id_invalido"
    if not cid:
        return None, None, None
    return cid, (d.get("criado_em") if isinstance(d, dict) else None), None


def _ponteiros(base):
    '[(caminho do ponteiro, dict)]: sessões, ponteiro corrente e dono de cada código'

    out = []
    for sub in ("sessoes", "casos"):
        pasta = os.path.join(base, sub)
        if os.path.isdir(pasta):
            for nome in sorted(os.listdir(pasta)):
                if nome.endswith(".json"):
                    p = os.path.join(pasta, nome)
                    d = _ler_json(p)
                    if isinstance(d, dict) and _s(d.get("raiz")):
                        out.append((p, d))
    p = os.path.join(base, "caso_atual.json")
    d = _ler_json(p)
    if isinstance(d, dict) and _s(d.get("raiz")):
        out.append((p, d))
    return out


def raizes_em_uso(base, session_id=None, agora=None):
    'Pastas (normalizadas, só as que existem) do caso aberto agora: ponteiro corrente,'

    agora = agora or datetime.now()
    cand = []
    env = os.environ.get(ENV_CASO_RAIZ)
    if _s(env):
        cand.append(env.strip())
    d = _ler_json(os.path.join(base, "caso_atual.json"))
    if isinstance(d, dict) and _s(d.get("raiz")):
        cand.append(d["raiz"].strip())
    if _s(session_id):
        d = _ler_json(os.path.join(base, "sessoes", _slug(session_id) + ".json"))
        if isinstance(d, dict) and _s(d.get("raiz")):
            cand.append(d["raiz"].strip())
    sess = os.path.join(base, "sessoes")
    if os.path.isdir(sess):
        for nome in os.listdir(sess):
            if not nome.endswith(".json"):
                continue
            d = _ler_json(os.path.join(sess, nome))
            if not (isinstance(d, dict) and _s(d.get("raiz"))):
                continue
            m = _momento(d.get("registrado_em"))
            if m is not None and abs((agora - m).total_seconds()) < JANELA_SESSAO_RECENTE_H * 3600:
                cand.append(d["raiz"].strip())
    return {_norm(r) for r in cand if os.path.isdir(r)}


def ler_situacoes(base):
    d = _ler_json(os.path.join(_dir_ret(base), ARQ_SITUACAO))
    return d if isinstance(d, dict) else {}


def ler_registro(base):
    p = os.path.join(_dir_ret(base), ARQ_REGISTRO)
    out = []
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as fh:
            for linha in fh:
                try:
                    d = json.loads(linha)
                except ValueError:
                    continue
                if isinstance(d, dict):
                    out.append(d)
    return out


def _anotar(base, entrada):
    p = os.path.join(_dir_ret(base), ARQ_REGISTRO)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entrada, ensure_ascii=False) + "\n")


def _conteudo(pasta):
    '(arquivos, bytes, impressão) — a impressão é sha256 de (caminho relativo, tamanho) em'

    itens = []
    for raiz, dirs, arqs in os.walk(pasta):
        dirs.sort()
        for a in sorted(arqs):
            p = os.path.join(raiz, a)
            try:
                tam = os.path.getsize(p)
            except OSError:
                continue
            itens.append((os.path.relpath(p, pasta).replace(os.sep, "/"), tam))
    h = hashlib.sha256(json.dumps(itens, ensure_ascii=False).encode("utf-8")).hexdigest()
    return len(itens), sum(t for _, t in itens), h


def _tipos_seguros(pasta):
    mapping = revisao = outros = 0
    for _r, _d, arqs in os.walk(pasta):
        for a in arqs:
            ext = os.path.splitext(a)[1].lower()
            if ext == ".json":
                mapping += 1
            elif ext == ".md":
                revisao += 1
            else:
                outros += 1
    return {"mapping": mapping, "revisao": revisao, "outros": outros}


def _novo_grupo(raiz):
    return {"raiz": os.path.abspath(raiz.strip()), "raizes": [], "registros": [], "sessoes": set(),
            "caso_id_ponteiro": None, "ponteiros": []}


def levantar_casos(base, rseg):
    '{chave: caso}. Os ponteiros se agrupam pela pasta e, havendo código, pelo código: a pasta'


    por_pasta = {}
    for p, d in _ponteiros(base):
        chave = _norm(d["raiz"])
        c = por_pasta.setdefault(chave, _novo_grupo(d["raiz"]))
        c["ponteiros"].append(p)
        if _s(d.get("registrado_em")):
            c["registros"].append(d["registrado_em"].strip())
        if _s(d.get("session_id")):
            c["sessoes"].add(d["session_id"].strip())
        if isinstance(d.get("caso_id"), str) and RE_CASO_ID.match(d["caso_id"]):
            c["caso_id_ponteiro"] = d["caso_id"]
    for chave, c in por_pasta.items():
        c["raizes"] = [chave]
        existe = os.path.isdir(c["raiz"])
        cid, criado, erro = _ler_caso_id(c["raiz"]) if existe else (None, None, None)
        c["existe"], c["caso_id_erro"], c["criado_em"] = existe, erro, criado
        c["caso_id"] = cid or (None if erro else c["caso_id_ponteiro"])
        c["duplicado"] = False

    casos = {k: c for k, c in por_pasta.items() if not c["caso_id"]}
    grupos = {}
    for k, c in por_pasta.items():
        if c["caso_id"]:
            grupos.setdefault(c["caso_id"], []).append(k)
    for _cid, chaves in grupos.items():
        vivas = [k for k in chaves if por_pasta[k]["existe"]]
        mortas = [k for k in chaves if not por_pasta[k]["existe"]]
        if len(vivas) > 1:
            for k in chaves:
                por_pasta[k]["duplicado"] = True
                casos[k] = por_pasta[k]
            continue
        if vivas:
            principal = vivas[0]
        else:
            principal = max(mortas, key=lambda k: (max(por_pasta[k]["registros"] or [""]), k))
        c = por_pasta[principal]
        for k in chaves:
            if k == principal:
                continue
            o = por_pasta[k]
            c["raizes"].append(k)
            c["registros"].extend(o["registros"])
            c["sessoes"] |= o["sessoes"]
            c["ponteiros"].extend(o["ponteiros"])
        casos[principal] = c

    for c in casos.values():
        datas = [x for x in (_data(r) for r in c["registros"]) if x]
        criado = _data(c["criado_em"])
        menor_reg = min(datas) if datas else None
        if criado and (menor_reg is None or criado <= menor_reg):
            c["data_registro"], c["origem_data"] = criado, "codigo_do_caso"
        elif menor_reg:
            c["data_registro"], c["origem_data"] = menor_reg, "registro_de_sessao"
        else:
            c["data_registro"], c["origem_data"] = None, None
        c["ultimo_registro"] = max(datas) if datas else None
        seg = os.path.join(rseg, c["caso_id"]) if c["caso_id"] else None
        c["pasta_segura"] = seg if seg and os.path.isdir(seg) else None
    return casos


def _por_codigo(casos, caso_id):
    """(caso, None) ou (None, código da recusa)."""
    achados = [c for c in casos.values() if c["caso_id"] == caso_id]
    if not achados:
        return None, "caso_nao_encontrado"
    if len(achados) > 1 or achados[0]["duplicado"]:
        return None, "caso_id_duplicado"
    return achados[0], None


def _aninhamento(casos, c):
    "'caso_contem_outro_caso' / 'caso_dentro_de_outro_caso' / None. Só pastas que existem:"

    if not c["existe"]:
        return None
    for o in casos.values():
        if o is c:
            continue
        for r in [o["raiz"]] + list(o["raizes"]):
            if not os.path.isdir(r):
                continue
            if _dentro(r, c["raiz"]):
                return "caso_contem_outro_caso"
            if _dentro(c["raiz"], r):
                return "caso_dentro_de_outro_caso"
    return None


def _em_uso(c, usadas):
    if not c["existe"]:
        return False
    return any(_dentro(u, c["raiz"]) or _dentro(c["raiz"], u) for u in usadas)



def relatorio(base, rseg, hoje, prazo_dias=None, com_caminho=False, agora=None):
    casos = levantar_casos(base, rseg)
    situ = ler_situacoes(base)
    reg = ler_registro(base)
    usadas = raizes_em_uso(base, agora=agora)
    arquivados = {e.get("caso_id") for e in reg if e.get("acao") == "arquivado"}
    removidos = [{"caso_id": e.get("caso_id"), "removido_em": e.get("removido_em")}
                 for e in reg if e.get("acao") == "removido"]
    incompletas = [{"caso_id": e.get("caso_id"), "em": e.get("em"), "saiu": e.get("saiu"),
                    "parou_em": e.get("parou_em")}
                   for e in reg if e.get("acao") == "remocao_incompleta"]
    linhas = []
    for chave in sorted(casos, key=lambda k: (str(casos[k]["data_registro"] or ""), k)):
        c = casos[chave]
        s = situ.get(c["caso_id"]) if c["caso_id"] else None
        situacao = s.get("situacao") if isinstance(s, dict) and s.get("situacao") in SITUACOES else "ativo"
        idade = (hoje - c["data_registro"]).days if c["data_registro"] else None
        permanece = []
        if not c["caso_id"]:
            permanece.append(c["caso_id_erro"] or "caso_sem_codigo")
        if c["duplicado"]:
            permanece.append("caso_id_duplicado")
        if situacao != "encerrado":
            permanece.append("caso_ativo")
        if _em_uso(c, usadas):
            permanece.append("caso_em_uso")
        ninho = _aninhamento(casos, c)
        if ninho:
            permanece.append(ninho)
        if prazo_dias is not None and (idade is None or idade < prazo_dias):
            permanece.append("abaixo_do_prazo")
        item = {
            "caso_id": c["caso_id"],
            "situacao": situacao,
            "situacao_marcada": bool(s),
            "data_registro": c["data_registro"].isoformat() if c["data_registro"] else None,
            "origem_da_data": c["origem_data"],
            "idade_dias": idade,
            "ultimo_registro": c["ultimo_registro"].isoformat() if c["ultimo_registro"] else None,
            "sessoes": len(c["sessoes"]),
            "pasta_existe": c["existe"],
            "nomes_anteriores": len(c["raizes"]) - 1,
            "arquivado": c["caso_id"] in arquivados,
            "pode_sair": not permanece,
            "permanece_por": permanece,
        }
        if c["existe"]:
            n, b, _ = _conteudo(c["raiz"])
            item["pasta"] = {"arquivos": n, "bytes": b}
        if c["pasta_segura"]:
            n, b, _ = _conteudo(c["pasta_segura"])
            item["raiz_segura"] = dict(_tipos_seguros(c["pasta_segura"]), arquivos=n, bytes=b)
        if com_caminho:
            item["caminho"] = c["raiz"]
        linhas.append(item)

    ligados = {c["caso_id"] for c in casos.values() if c["caso_id"]}
    sem_vinculo = {"entradas": 0, "arquivos": 0, "bytes": 0}
    orfas = quarentena = 0
    if os.path.isdir(rseg):
        for nome in os.listdir(rseg):
            if nome == DIR_ARQUIVO_SEGURO:
                continue
            p = os.path.join(rseg, nome)
            if nome.startswith(PREFIXO_QUARENTENA):
                quarentena += 1
                continue
            if RE_CASO_ID.match(nome) and os.path.isdir(p):
                if nome not in ligados:
                    orfas += 1
                continue
            sem_vinculo["entradas"] += 1
            if os.path.isdir(p):
                n, b, _ = _conteudo(p)
            else:
                n, b = 1, os.path.getsize(p)
            sem_vinculo["arquivos"] += n
            sem_vinculo["bytes"] += b
    return {
        "ok": True, "schema_version": SCHEMA, "modo": "relatorio", "hoje": hoje.isoformat(),
        "prazo_dias": prazo_dias,
        "casos": linhas,
        "raiz_segura": {"existe": os.path.isdir(rseg), "sem_vinculo": sem_vinculo,
                        "pastas_de_caso_nao_registrado": orfas,
                        "pastas_de_remocao_incompleta": quarentena},
        "removidos": removidos,
        "remocoes_incompletas": incompletas,
        "nota": ("Só relatório: nada foi apagado. Caso sem marca de encerrado é tratado como "
                 "ativo e não sai. Na raiz segura, só conta como do caso o que está na pasta com o "
                 "código dele; o material gravado fora dela aparece como sem vínculo, não tem data "
                 "de caso e não sai por aqui. O vínculo por caso depende de a pseudonimização "
                 "gravar o mapping e a revisão nessa pasta."),
    }



def marcar(base, caso_id, situacao, motivo=None, ts=None):
    sit = ler_situacoes(base)
    sit[caso_id] = {"situacao": situacao, "marcado_em": ts or _agora()}
    if _s(motivo):
        sit[caso_id]["motivo"] = motivo.strip()
    _gravar_json(os.path.join(_dir_ret(base), ARQ_SITUACAO), sit)
    return sit[caso_id]


def autorizar(base, session_id, acao, casos, escopo, ts=None):
    aval = {"session_id": session_id.strip(), "acao": acao, "casos": sorted(set(casos)),
            "escopo": escopo.strip(), "concedido_em": ts or _agora()}
    _gravar_json(os.path.join(_dir_ret(base), ARQ_AVAL), aval)
    return aval


def conferir_aval(base, session_id, caso_id, acao):
    'None quando o aval cobre (sessão, caso, ação); senão o código da recusa. Remover cobre'

    p = os.path.join(_dir_ret(base), ARQ_AVAL)
    if not os.path.isfile(p):
        return "aval_ausente"
    d = _ler_json(p)
    if not isinstance(d, dict) or not isinstance(d.get("casos"), list):
        return "aval_ilegivel"
    if not _s(d.get("session_id")) or d["session_id"].strip() != session_id.strip():
        return "aval_de_outra_sessao"
    if caso_id not in d["casos"]:
        return "caso_fora_do_aval"
    if acao == "remover" and d.get("acao") != "remover":
        return "acao_fora_do_aval"
    if d.get("acao") not in ACOES:
        return "aval_ilegivel"
    return None


def _caso_para_ato(base, rseg, session_id, caso_id, acao, agora=None):
    '(caso, casos, None) ou (None, None, código). Ordem: código, existência, situação, uso,'

    if not (isinstance(caso_id, str) and RE_CASO_ID.match(caso_id)):
        return None, None, "caso_id_invalido"
    casos = levantar_casos(base, rseg)
    c, erro = _por_codigo(casos, caso_id)
    if erro:
        return None, None, erro
    s = ler_situacoes(base).get(caso_id)
    if not (isinstance(s, dict) and s.get("situacao") == "encerrado"):
        return None, None, "caso_ativo"
    if _em_uso(c, raizes_em_uso(base, session_id=session_id, agora=agora)):
        return None, None, "caso_em_uso"
    ninho = _aninhamento(casos, c)
    if ninho:
        return None, None, ninho
    erro = conferir_aval(base, session_id, caso_id, acao)
    return (None, None, erro) if erro else (c, casos, None)



def _zipar(pasta, destino_zip):
    n = 0
    with zipfile.ZipFile(destino_zip, "x", zipfile.ZIP_DEFLATED) as z:
        for raiz, dirs, arqs in os.walk(pasta):
            dirs.sort()
            for a in sorted(arqs):
                p = os.path.join(raiz, a)
                z.write(p, os.path.relpath(p, pasta))
                n += 1
    return n


def _sha_arquivo(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for bloco in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _empacotar(tipo, pasta, destino_zip):
    """Grava e confere o pacote. Levanta ValueError('arquivo_nao_conferido') se não bater."""
    n_pasta, b_pasta, impressao = _conteudo(pasta)
    n = _zipar(pasta, destino_zip)
    with zipfile.ZipFile(destino_zip) as z:
        conferido = z.testzip() is None and len(z.namelist()) == n_pasta and n == n_pasta
    if not conferido:
        try:
            os.remove(destino_zip)
        except OSError:
            pass
        raise ValueError("arquivo_nao_conferido")
    return {"tipo": tipo, "caminho": destino_zip, "sha256": _sha_arquivo(destino_zip),
            "arquivos": n_pasta, "bytes": b_pasta, "impressao_da_pasta": impressao}


def arquivar(base, rseg, session_id, caso_id, destino, ts=None, agora=None):
    c, _casos, erro = _caso_para_ato(base, rseg, session_id, caso_id, "arquivar", agora)
    if erro:
        return None, erro
    if caso_raiz is not None:
        try:
            if caso_raiz.e_ambiente_efemero():
                return None, "ambiente_efemero"
        except Exception:
            pass
        if caso_raiz.e_efemero(destino):
            return None, "destino_efemero"
    if c["existe"] and _dentro(destino, c["raiz"]):
        return None, "destino_dentro_do_caso"
    if not c["existe"] and not c["pasta_segura"]:
        return None, "nada_a_arquivar"
    carimbo = time.strftime("%Y%m%d%H%M%S")

    def _nome_livre(pasta):
        p, n = os.path.join(pasta, f"{caso_id}-{carimbo}.zip"), 1
        while os.path.exists(p):
            n += 1
            p = os.path.join(pasta, f"{caso_id}-{carimbo}-{n}.zip")
        return p

    pacotes = []
    try:
        if c["existe"]:
            os.makedirs(destino, exist_ok=True)
            pacotes.append(_empacotar("pasta_do_caso", c["raiz"], _nome_livre(destino)))
        if c["pasta_segura"]:
            dz = os.path.join(rseg, DIR_ARQUIVO_SEGURO)
            os.makedirs(dz, exist_ok=True)
            pacotes.append(_empacotar("raiz_segura", c["pasta_segura"], _nome_livre(dz)))
    except ValueError as e:
        return None, str(e)
    except OSError:
        return None, "falha_ao_gravar"
    entrada = {"acao": "arquivado", "caso_id": caso_id, "session_id": session_id.strip(),
               "arquivado_em": ts or _agora(), "pacotes": pacotes}
    _anotar(base, entrada)
    return entrada, None


def _protegida(raiz, base, rseg):
    r = _norm(raiz)
    if os.path.dirname(r) == r:
        return True
    if r == _norm(os.path.expanduser("~")):
        return True
    for sistema in (base, rseg, AQUI):
        if _dentro(sistema, raiz) or _dentro(raiz, sistema):
            return True
    return False


def _bloqueio_de_gravacao(pasta):
    "'arquivo_somente_leitura' quando algo dentro da pasta não pode ser apagado por proteção"

    pai = os.path.dirname(os.path.abspath(pasta))
    if not os.access(pai, os.W_OK):
        return "arquivo_somente_leitura"
    for raiz, dirs, arqs in os.walk(pasta):
        if not os.access(raiz, os.W_OK | os.X_OK):
            return "arquivo_somente_leitura"
        if os.name == "nt":
            for nome in arqs + dirs:
                try:
                    if os.stat(os.path.join(raiz, nome), follow_symlinks=False).st_file_attributes \
                            & stat.FILE_ATTRIBUTE_READONLY:
                        return "arquivo_somente_leitura"
                except (OSError, AttributeError):
                    return "arquivo_somente_leitura"
    return None


def remover(base, rseg, session_id, caso_id, ts=None, agora=None):
    c, _casos, erro = _caso_para_ato(base, rseg, session_id, caso_id, "remover", agora)
    if erro:
        return None, erro
    arqs = [e for e in ler_registro(base) if e.get("acao") == "arquivado" and e.get("caso_id") == caso_id]
    if not arqs:
        return None, "sem_arquivo_previo"
    ultimo = arqs[-1]
    por_tipo = {p.get("tipo"): p for p in ultimo.get("pacotes") or []}
    alvos = []
    if c["existe"]:
        cid, _criado, _e = _ler_caso_id(c["raiz"])
        if cid != caso_id:
            return None, "caso_id_divergente"
        if _protegida(c["raiz"], base, rseg):
            return None, "raiz_protegida"
        alvos.append(("pasta_do_caso", c["raiz"]))
    if c["pasta_segura"]:
        alvos.append(("raiz_segura", c["pasta_segura"]))
    for tipo, pasta in alvos:
        pac = por_tipo.get(tipo)
        if not pac:
            return None, "sem_arquivo_previo"
        if not os.path.isfile(pac.get("caminho") or ""):
            return None, "arquivo_ausente"
        if _sha_arquivo(pac["caminho"]) != pac.get("sha256"):
            return None, "arquivo_divergente"
        if _conteudo(pasta)[2] != pac.get("impressao_da_pasta"):
            return None, "pasta_mudou_depois_do_arquivo"
    for _tipo, pasta in alvos:
        bloqueio = _bloqueio_de_gravacao(pasta)
        if bloqueio:
            return None, bloqueio

    carimbo = time.strftime("%Y%m%d%H%M%S")
    saiu = []
    for tipo, pasta in alvos:
        quarentena = os.path.join(os.path.dirname(os.path.abspath(pasta)),
                                  f"{PREFIXO_QUARENTENA}{caso_id}-{tipo}-{carimbo}")
        try:
            os.replace(pasta, quarentena)
        except OSError:
            if not saiu:
                return None, "pasta_bloqueada"
            return _incompleta(base, caso_id, session_id, saiu, tipo, None)
        try:
            shutil.rmtree(quarentena)
        except OSError:
            return _incompleta(base, caso_id, session_id, saiu, tipo, os.path.basename(quarentena))
        saiu.append(tipo)

    ponteiros = 0
    for p in sorted(set(c["ponteiros"])):
        try:
            os.remove(p)
            ponteiros += 1
        except OSError:
            pass
    entrada = {"acao": "removido", "caso_id": caso_id, "session_id": session_id.strip(),
               "removido_em": ts or _agora(), "saiu": saiu, "ponteiros_removidos": ponteiros,
               "arquivado_em": ultimo.get("arquivado_em"),
               "pacotes": [{"tipo": p.get("tipo"), "caminho": p.get("caminho"), "sha256": p.get("sha256")}
                           for p in ultimo.get("pacotes") or []]}
    _anotar(base, entrada)
    return entrada, None


def _incompleta(base, caso_id, session_id, saiu, parou_em, quarentena):
    """Registra a remoção que parou no meio. Só o nome da quarentena (opaco), nunca o caminho."""
    entrada = {"acao": "remocao_incompleta", "caso_id": caso_id, "session_id": session_id.strip(),
               "em": _agora(), "saiu": list(saiu), "parou_em": parou_em, "quarentena": quarentena}
    try:
        _anotar(base, entrada)
    except OSError:
        pass
    return None, "remocao_incompleta"



def _saida(obj, code=0):
    print(json.dumps(obj, ensure_ascii=False))
    return code


def _recusa(codigo):
    obj = {"ok": False, "codigo": codigo, "mensagem": MENSAGENS.get(codigo, codigo)}
    if codigo == "remocao_incompleta":
        obj["nada_foi_apagado"] = False
    elif codigo != "falha_inesperada":
        obj["nada_foi_apagado"] = True
    return _saida(obj, 1)


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    try:
        return _main(argv)
    except SystemExit:
        raise
    except Exception:

        return _recusa("falha_inesperada")


def _main(argv=None):
    ap = argparse.ArgumentParser(description="Relatório de retenção dos casos registrados (só relata por padrão)")
    ap.add_argument("--base")
    ap.add_argument("--raiz-segura", dest="raiz_segura")
    sub = ap.add_subparsers(dest="cmd")
    pr = sub.add_parser("relatorio", help="só relata; não apaga nada")
    pr.add_argument("--prazo-dias", dest="prazo_dias", type=int)
    pr.add_argument("--com-caminho", dest="com_caminho", action="store_true")
    pr.add_argument("--hoje")
    pm = sub.add_parser("marcar", help="marca o caso como ativo ou encerrado (palavra do advogado)")
    pm.add_argument("--caso-id", dest="caso_id", required=True)
    pm.add_argument("--situacao", choices=SITUACOES, required=True)
    pm.add_argument("--motivo")
    pa = sub.add_parser("autorizar", help="registra o aval do advogado, só depois do sim expresso")
    pa.add_argument("--session-id", dest="session_id", required=True)
    pa.add_argument("--acao", choices=ACOES, required=True)
    pa.add_argument("--casos", required=True)
    pa.add_argument("--escopo", required=True)
    pq = sub.add_parser("arquivar", help="empacota e confere antes de qualquer remoção")
    pq.add_argument("--session-id", dest="session_id", required=True)
    pq.add_argument("--caso-id", dest="caso_id", required=True)
    pq.add_argument("--destino", required=True)
    px = sub.add_parser("remover", help="remove o que já foi arquivado, com aval")
    px.add_argument("--session-id", dest="session_id", required=True)
    px.add_argument("--caso-id", dest="caso_id", required=True)
    args = ap.parse_args(argv)

    base = base_dir(args.base)
    rseg = raiz_segura(args.raiz_segura)
    cmd = args.cmd or "relatorio"

    if cmd == "relatorio":
        hoje_txt = getattr(args, "hoje", None)
        hoje = _data(hoje_txt) if hoje_txt else date.today()
        if hoje is None:
            return _saida({"ok": False, "codigo": "data_invalida", "mensagem": "use --hoje AAAA-MM-DD"}, 2)
        prazo = getattr(args, "prazo_dias", None)
        if prazo is not None and prazo < 0:
            return _saida({"ok": False, "codigo": "prazo_invalido", "mensagem": "--prazo-dias não pode ser negativo"}, 2)
        return _saida(relatorio(base, rseg, hoje, prazo, getattr(args, "com_caminho", False)))

    if cmd == "marcar":
        if not RE_CASO_ID.match(args.caso_id or ""):
            return _recusa("caso_id_invalido")
        _c, erro = _por_codigo(levantar_casos(base, rseg), args.caso_id)
        if erro:
            return _recusa(erro)
        try:
            m = marcar(base, args.caso_id, args.situacao, args.motivo)
        except OSError:
            return _recusa("falha_ao_gravar")
        return _saida({"ok": True, "caso_id": args.caso_id, "marcacao": m,
                       "nota": "marcação registrada; nada foi apagado"})

    if cmd == "autorizar":
        casos = [c.strip() for c in args.casos.split(",") if c.strip()]
        if not casos or any(not RE_CASO_ID.match(c) for c in casos):
            return _recusa("caso_id_invalido")
        if not _s(args.escopo) or not _s(args.session_id):
            return _saida({"ok": False, "codigo": "escopo_obrigatorio",
                           "mensagem": "registre o que o advogado autorizou, com as palavras dele"}, 2)
        try:
            a = autorizar(base, args.session_id, args.acao, casos, args.escopo)
        except OSError:
            return _recusa("falha_ao_gravar")
        return _saida({"ok": True, "autorizacao": a,
                       "nota": "aval registrado para esta sessão e estes casos; nada foi apagado"})

    if cmd == "arquivar":
        e, erro = arquivar(base, rseg, args.session_id, args.caso_id, os.path.abspath(args.destino))
        if erro:
            return _recusa(erro)
        return _saida({"ok": True, "arquivamento": e, "nota": "arquivado e conferido; nada foi apagado"})

    if cmd == "remover":
        e, erro = remover(base, rseg, args.session_id, args.caso_id)
        if erro:
            return _recusa(erro)
        return _saida({"ok": True, "remocao": e,
                       "nota": "removido o que já estava arquivado; os pacotes continuam onde foram gravados"})
    return _saida({"ok": False, "codigo": "comando_desconhecido"}, 2)


if __name__ == "__main__":
    sys.exit(main())
