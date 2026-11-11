#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'lint_etico.py - lint etico da comunicacao externa do escritorio.'








































































from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import sys
import unicodedata

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))
TABELA_PADRAO = os.path.join(AQUI, "regras-eticas.json")
SCHEMA_VERSION = "dsr.lint_etico.v1"

CAMPOS_REVISAO = ("revisor", "papel", "revisado_em", "review_valid_from", "review_valid_to")
CAMPOS_PENDENCIA = ("bloqueada", "bloqueada_desde", "motivo", "alerta_falso_positivo",
                    "decisoes_do_advogado")
CAMPOS_REGRA = ("id", "rotulo", "alcances", "padrao", "motivo", "fonte",
                "exemplo_apontavel", "exemplo_legitimo")
CAMPOS_FONTE = ("norma", "dispositivo", "url_oficial", "data_extracao", "sha256",
                "valid_from", "valid_to")
EIXOS = ("alcance", "norma", "host_oficial")

HEXA = "0123456789abcdef"
TAMANHO_SHA256 = 64
ESQUEMA_URL = "https://"

















JANELA_TRECHO = 60
MAX_RESUMO = 10
MINIMO_MOTIVO_REGRA = 25
MINIMO_MOTIVO_PENDENCIA = 40



PISO_LIMIAR = 1

NATUREZA_APONTAMENTO = (
    "apontamento para conferencia do advogado - trecho a conferir contra a norma invocada. "
    "NAO e conclusao de infracao etica: quem conclui e o advogado."
)

MOTIVO_SEM_ALCANCE = (
    "alcance da comunicacao nao declarado: sem ele nao ha lint etico possivel. Inferir do "
    "texto se aquilo e peca processual, comunicacao com cliente ou publicidade muda qual "
    "dispositivo se aplica, e essa escolha e juizo juridico - este modulo nao a faz. Declare "
    "o alcance (um dos valores de dominios.alcance da tabela) e chame de novo."
)

MOTIVO_SEM_REGRA = (
    "nenhuma regra carregada: a lista `regras` da tabela esta vazia, entao NAO HOUVE MEDICAO "
    "alguma. Nada a apontar por ausencia de regra nao e o mesmo que estar em conformidade - o "
    "primeiro e silencio do instrumento, o segundo e juizo do advogado, e este modulo nunca "
    "produz o segundo. Ver o bloco `pendencia` da tabela: falta decidir quais dispositivos do "
    "Codigo de Etica e do Provimento 205/2021 devem ser medidos, com a URL oficial de cada um."
)




PEDIDOS_DE_PECA = ("peca_processual", "peca", "peticao", "peca_judicial", "recurso")


PALAVRAS_DE_PECA = ("peca", "peticao", "recurso", "contestacao", "replica", "contrarrazoes",
                    "apelacao", "agravo", "embargos", "memoriais", "impugnacao")


def _pedido_normalizado(alcance):
    sem_acento = "".join(c for c in unicodedata.normalize("NFD", alcance)
                         if unicodedata.category(c) != "Mn")

    return "_".join("".join(c if c.isalnum() else " " for c in sem_acento.lower()).split())


def _pede_peca(alcance):
    norm = _pedido_normalizado(alcance)
    return norm in PEDIDOS_DE_PECA or norm.split("_")[0] in PALAVRAS_DE_PECA

MOTIVO_PECA_PROCESSUAL = (
    "peca processual nao passa por este lint, por construcao: ele mede comunicacao externa do "
    "escritorio (publicidade, site, rede social, material, entrevista), e pedir provimento ou "
    "sustentar tese com firmeza e o oficio, nao promessa de resultado. A peca e conferida pelo "
    "LINT da peca (dissero-visual-law/scripts/lint_peca.py) e pelo Conselho Revisor, no rito "
    "da dissero-peticao. Se o texto for comunicacao externa, declare o alcance dela."
)


def _alcances_para_colar(tabela):
    "'--alcance x, --alcance y': os valores de dominios.alcance, prontos para a linha de"

    try:
        valores = [_texto(v) for v in tabela["dominios"]["alcance"]]
    except Exception:
        return ""
    valores = [v for v in valores if v]
    return ", ".join("--alcance " + v for v in valores)


def _com_alcances(motivo, tabela):
    lista = _alcances_para_colar(tabela) if isinstance(tabela, dict) else ""
    if not lista:
        return motivo
    return "%s Alcances que este lint mede: %s." % (motivo, lista)


LEITURA_INCONCLUSIVO = (
    "INCONCLUSIVO - nao houve medicao. Nao ha apontamento porque o instrumento estava inerte "
    "(sem regra carregada, bloqueado por pendencia juridica, desligado, com revisao vencida ou "
    "sem alcance declarado - o campo `motivos` diz qual), e NAO porque o texto foi aprovado. "
    "Isto NAO e declaracao de conformidade etica. A frase vale para toda causa de inercia: "
    "silencio do instrumento nunca vira juizo do advogado, seja qual for o motivo do silencio."
)


def _texto(valor):
    return str(valor or "").strip()


def _data(valor):
    'Data ISO em TEXTO, ou None. Exige `str` pelo mesmo motivo de `vigencia_fontes._data`:'


    if not isinstance(valor, str):
        return None
    try:
        return _dt.date.fromisoformat(valor[:10])
    except ValueError:
        return None


def _erro_de_piso(nome, valor, piso=PISO_LIMIAR):
    if not isinstance(valor, int) or isinstance(valor, bool) or valor < piso:
        return "%s deve ser inteiro >= %d (recebido %r): limiar zerado aceitaria texto vazio " \
               "e transformaria o parametro de rigor em interruptor de desligar" % (
                   nome, piso, valor)
    return None


def _erros_de_piso(**limiares):
    return [e for e in (_erro_de_piso(n, v) for n, v in sorted(limiares.items())) if e]


def _host(url):
    'Host de uma URL https, por operacao de texto - sem regex e sem `urllib`.'









    bruto = _texto(url)
    if not bruto.lower().startswith(ESQUEMA_URL):
        return None
    resto = bruto[len(ESQUEMA_URL):]
    for corte in ("/", "?", "#"):
        pos = resto.find(corte)
        if pos >= 0:
            resto = resto[:pos]
    if "@" in resto:
        resto = resto.split("@", 1)[1]
    if ":" in resto:
        resto = resto.split(":", 1)[0]
    resto = resto.strip().lower()
    return resto or None


def _e_sha256(valor):
    bruto = _texto(valor)
    return len(bruto) == TAMANHO_SHA256 and all(c in HEXA for c in bruto)


def sha256_arquivo(caminho):
    'SHA-256 do arquivo, ou None se nao der para ler. Nunca levanta: arquivo ilegivel e'

    try:
        digest = hashlib.sha256()
        with open(caminho, "rb") as arquivo:
            for pedaco in iter(lambda: arquivo.read(65536), b""):
                digest.update(pedaco)
        return digest.hexdigest()
    except OSError:
        return None


def carregar_tabela(caminho=TABELA_PADRAO):
    """(tabela, erro). Erro nunca vira excecao - tabela ilegivel e impedimento, nao crash."""
    try:
        with open(caminho, encoding="utf-8-sig") as arquivo:
            return json.load(arquivo), None
    except OSError as erro:
        return None, "tabela de regras eticas nao pode ser lida (%s)" % erro.__class__.__name__
    except UnicodeDecodeError:
        return None, "tabela de regras eticas nao e texto UTF-8"
    except ValueError as erro:
        return None, "tabela de regras eticas nao e JSON valido (%s)" % erro


def _compilar(padrao):
    """(compilado, erro). Sem diferenciar maiusculas de minusculas, como a tabela declara."""
    if not isinstance(padrao, str) or not padrao.strip():
        return None, "ausente ou nao e texto"
    try:
        return re.compile(padrao, re.I), None
    except re.error as erro:
        return None, "nao compila (%s)" % erro


def _limites_da_linha(texto, inicio, fim):
    abre = texto.rfind("\n", 0, inicio) + 1
    fecha = texto.find("\n", fim)
    return abre, (len(texto) if fecha < 0 else fecha)


def _trecho(texto, inicio, fim, janela=JANELA_TRECHO):
    """Recorte legivel em volta do casamento, sem atravessar a quebra de linha."""
    abre, fecha = _limites_da_linha(texto, inicio, fim)
    esq, dir_ = max(abre, inicio - janela), min(fecha, fim + janela)
    recorte = texto[esq:dir_].strip()
    if esq > abre:
        recorte = "..." + recorte
    if dir_ < fecha:
        recorte = recorte + "..."
    return recorte


def _ocorrencias(compilado, escusas, texto):
    '(apontaveis, escusadas) do padrao de UMA regra sobre um texto.'






    apontaveis, escusadas = [], []
    for casamento in compilado.finditer(texto):
        abre, fecha = _limites_da_linha(texto, casamento.start(), casamento.end())
        linha = texto[abre:fecha]
        motivo = next((p for p, c in escusas if c.search(linha)), None)
        if motivo is None:
            apontaveis.append(casamento)
        else:
            escusadas.append((casamento, motivo))
    return apontaveis, escusadas


def _checar_revisao(tabela, hoje, erros):
    revisao = tabela.get("revisao")
    if not isinstance(revisao, dict):
        erros.append("revisao ausente ou nao e objeto")
        return
    faltando = [c for c in CAMPOS_REVISAO if revisao.get(c) in (None, "")]
    if faltando:
        erros.append("revisao incompleta: falta " + ", ".join(faltando))
        return
    if not _texto(revisao.get("revisor")):
        erros.append("revisao exige revisor identificado")
    if _texto(revisao.get("papel")).lower() != "advogado":
        erros.append("revisao exige papel 'advogado': regra de etica revisada por quem nao e "
                     "advogado nao esta revisada")
    revisado = _data(revisao.get("revisado_em"))
    desde = _data(revisao.get("review_valid_from"))
    ate = _data(revisao.get("review_valid_to"))
    if revisado is None or revisado > hoje:
        erros.append("revisado_em ausente, ilegivel ou futuro")
    if desde is None or ate is None:
        erros.append("par review_valid_from/review_valid_to ilegivel")
    elif desde > ate:
        erros.append("vigencia da revisao com inicio posterior ao fim")
    elif not desde <= hoje <= ate:
        erros.append("vigencia da revisao da tabela fora de prazo em %s" % hoje.isoformat())


def _checar_procedencia(tabela, erros):
    procedencia = tabela.get("procedencia")
    if not isinstance(procedencia, dict) or not _texto(procedencia.get("origem")):
        erros.append("procedencia sem origem declarada: regra de etica sem fonte nao carrega")
        return
    if not _texto(procedencia.get("adaptacao")):
        erros.append("procedencia sem `adaptacao`: e onde fica escrito o que foi absorvido da "
                     "fonte e o que NAO foi")


def _checar_pendencia(tabela, erros, minimo_motivo=MINIMO_MOTIVO_PENDENCIA):
    'A pendencia e o que torna a recusa LEGIVEL. Bloco ausente seria recusa muda.'






    pend = tabela.get("pendencia")
    if not isinstance(pend, dict):
        erros.append("pendencia ausente ou nao e objeto: sem ela a recusa do modulo nao "
                     "explica ao advogado o que falta decidir")
        return
    faltando = [c for c in CAMPOS_PENDENCIA if pend.get(c) in (None, "")]
    if faltando:
        erros.append("pendencia incompleta: falta " + ", ".join(faltando))
        return
    if not isinstance(pend.get("bloqueada"), bool):
        erros.append("pendencia.bloqueada deve ser booleano")
    if _data(pend.get("bloqueada_desde")) is None:
        erros.append("pendencia.bloqueada_desde deve ser data AAAA-MM-DD")
    if len(_texto(pend.get("motivo"))) < minimo_motivo:
        erros.append("pendencia.motivo precisa de %d+ caracteres" % minimo_motivo)
    if len(_texto(pend.get("alerta_falso_positivo"))) < minimo_motivo:
        erros.append("pendencia.alerta_falso_positivo precisa de %d+ caracteres: e a "
                     "advertencia de que peca legitima pede provimento e sustenta tese com "
                     "firmeza, e ela nao pode virar campo vazio" % minimo_motivo)
    decisoes = pend.get("decisoes_do_advogado")
    if not isinstance(decisoes, list) or not decisoes:
        erros.append("pendencia.decisoes_do_advogado deve ser lista nao vazia")
    else:
        for i, item in enumerate(decisoes):
            onde = "pendencia.decisoes_do_advogado[%d]" % i
            if not isinstance(item, dict):
                erros.append("%s nao e objeto" % onde)
            elif not _texto(item.get("pergunta")) or not _texto(item.get("quem_decide")):
                erros.append("%s sem pergunta ou sem quem_decide" % onde)
    if pend.get("bloqueada") is True:
        erros.append("lint etico BLOQUEADO por decisao juridica pendente "
                     "(pendencia.bloqueada=true desde %s): %s"
                     % (_texto(pend.get("bloqueada_desde")), _texto(pend.get("motivo"))))


def _checar_dominios(tabela, erros):
    """Devolve {eixo: lista}. Eixo ausente e impedimento; eixo vazio e legitimo."""
    dominios = tabela.get("dominios")
    achados = {eixo: [] for eixo in EIXOS}
    if not isinstance(dominios, dict):
        erros.append("dominios ausente ou nao e objeto")
        return achados
    for eixo in EIXOS:
        valores = dominios.get(eixo)
        if not isinstance(valores, list):
            erros.append("dominios.%s ausente ou nao e lista" % eixo)
            continue
        limpos = []
        for valor in valores:
            nome = _texto(valor)
            if not nome:
                erros.append("dominios.%s traz valor vazio" % eixo)
            elif nome in limpos:
                erros.append("dominios.%s repete o valor %s" % (eixo, nome))
            else:
                limpos.append(nome)
        achados[eixo] = limpos
    return achados


def _checar_fonte(regra, onde, normas, hosts, hoje, erros, base_arquivo):
    """Procedencia de UMA regra. Faltando qualquer elo, a regra nao carrega."""
    fonte = regra.get("fonte")
    if not isinstance(fonte, dict):
        erros.append("%s sem `fonte`: regra de etica sem norma, URL oficial, data de extracao, "
                     "SHA-256 e vigencia nao carrega" % onde)
        return
    faltando = [c for c in CAMPOS_FONTE if not _texto(fonte.get(c))]
    if faltando:
        erros.append("%s.fonte incompleta: falta %s" % (onde, ", ".join(faltando)))
        return
    if _texto(fonte.get("norma")) not in normas:
        erros.append("%s.fonte.norma fora de dominios.norma" % onde)
    host = _host(fonte.get("url_oficial"))
    if host is None:
        erros.append("%s.fonte.url_oficial nao e uma URL https com host" % onde)
    elif hosts and host not in hosts:
        erros.append("%s.fonte.url_oficial aponta host '%s', que nao esta em "
                     "dominios.host_oficial" % (onde, host))
    extracao = _data(fonte.get("data_extracao"))
    if extracao is None or extracao > hoje:
        erros.append("%s.fonte.data_extracao ausente, ilegivel ou futura" % onde)
    if not _e_sha256(fonte.get("sha256")):
        erros.append("%s.fonte.sha256 nao tem %d caracteres hexadecimais minusculos"
                     % (onde, TAMANHO_SHA256))
    desde, ate = _data(fonte.get("valid_from")), _data(fonte.get("valid_to"))
    if desde is None or ate is None:
        erros.append("%s.fonte tem par valid_from/valid_to ilegivel" % onde)
    elif desde > ate:
        erros.append("%s.fonte tem vigencia com inicio posterior ao fim" % onde)
    elif not desde <= hoje <= ate:
        erros.append("%s.fonte fora de vigencia em %s: dispositivo revogado ou ainda nao "
                     "vigente nao mede nada, e medir por ele e pior que nao medir"
                     % (onde, hoje.isoformat()))
    local = _texto(fonte.get("arquivo_local"))
    if local:
        caminho = local if os.path.isabs(local) else os.path.join(base_arquivo, local)
        obtido = sha256_arquivo(caminho)
        if obtido is None:
            erros.append("%s.fonte.arquivo_local declarado mas ilegivel (%s)" % (onde, local))
        elif obtido != _texto(fonte.get("sha256")):
            erros.append("%s.fonte.arquivo_local NAO confere com o sha256 declarado: o texto "
                         "guardado mudou desde a extracao" % onde)


def _checar_regra(item, onde, dominios, ids, hoje, erros, base_arquivo,
                  minimo_motivo=MINIMO_MOTIVO_REGRA):
    """Uma regra. Devolve (compilado, escusas) ou (None, None) se ja esta reprovada."""
    if not isinstance(item, dict):
        erros.append("%s nao e objeto" % onde)
        return None, None
    faltando = [c for c in CAMPOS_REGRA if item.get(c) in (None, "", [], {})]
    if faltando:
        erros.append("%s incompleta: falta %s" % (onde, ", ".join(faltando)))
        return None, None

    ident = _texto(item.get("id"))
    if ident in ids:
        erros.append("%s repete o id %s" % (onde, ident))
    else:
        ids.add(ident)

    alcances = item.get("alcances")
    if not isinstance(alcances, list) or not alcances:
        erros.append("%s.alcances deve ser lista nao vazia" % onde)
    else:
        for valor in alcances:
            if _texto(valor) not in dominios["alcance"]:
                erros.append("%s declara alcance '%s' fora de dominios.alcance: alcance nao "
                             "aprovado nao e medido, e regra que aponta para ele nunca roda"
                             % (onde, _texto(valor)))

    if len(_texto(item.get("motivo"))) < minimo_motivo:
        erros.append("%s sem motivo legivel para o advogado (minimo %d caracteres): esse "
                     "texto e interpolado no apontamento, e apontamento sem motivo nao "
                     "ensina nada" % (onde, minimo_motivo))

    compilado, erro = _compilar(item.get("padrao"))
    if erro:
        erros.append("%s.padrao %s" % (onde, erro))

    escusas = []
    excecoes = item.get("excecoes", [])
    if not isinstance(excecoes, list):
        erros.append("%s.excecoes deve ser lista" % onde)
    else:
        for i, padrao in enumerate(excecoes):
            compilada, erro = _compilar(padrao)
            if erro:
                erros.append("%s.excecoes[%d] %s" % (onde, i, erro))
            else:
                escusas.append((_texto(padrao), compilada))

    _checar_fonte(item, onde, dominios["norma"], dominios["host_oficial"], hoje, erros,
                  base_arquivo)

    if compilado is None:
        return None, None




    apontaveis, _ = _ocorrencias(compilado, escusas, _texto(item.get("exemplo_apontavel")))
    if not apontaveis:
        erros.append("%s NAO aponta o proprio `exemplo_apontavel`: o padrao e o exemplo "
                     "discordam, entao a regra nao mede o que diz medir" % onde)
    apontaveis, _ = _ocorrencias(compilado, escusas, _texto(item.get("exemplo_legitimo")))
    if apontaveis:
        erros.append("%s APONTA o proprio `exemplo_legitimo`: e falso positivo declarado pela "
                     "propria regra. Peca legitima pede provimento e sustenta tese com "
                     "firmeza; regra que confunde isso com infracao repreende o advogado por "
                     "advogar" % onde)
    return compilado, escusas


def _checar_controle(tabela, compiladas, erros):
    'A prosa de controle da banca: nenhuma regra carregada pode acender em nenhum item.'





    itens = tabela.get("controle_prosa_legitima", [])
    if not isinstance(itens, list):
        erros.append("controle_prosa_legitima deve ser lista")
        return
    for i, item in enumerate(itens):
        onde = "controle_prosa_legitima[%d]" % i
        if not isinstance(item, dict):
            erros.append("%s nao e objeto" % onde)
            continue
        texto = _texto(item.get("texto"))
        if not texto or not _texto(item.get("por_que_e_legitima")):
            erros.append("%s exige texto e por_que_e_legitima" % onde)
            continue
        for ident, compilado, escusas in compiladas:
            apontaveis, _ = _ocorrencias(compilado, escusas, texto)
            if apontaveis:
                erros.append("a regra %s acende na prosa de controle %s (\"%s\"): prosa que a "
                             "banca escreve legitimamente nao pode virar apontamento etico"
                             % (ident, onde, apontaveis[0].group(0)))


def impedimentos(tabela, hoje=None, minimo_motivo_regra=MINIMO_MOTIVO_REGRA,
                 minimo_motivo_pendencia=MINIMO_MOTIVO_PENDENCIA, base_arquivo=AQUI):
    'Tudo que impede USAR esta tabela agora. Lista vazia = tabela utilizavel.'








    hoje = hoje or _dt.date.today()
    if not isinstance(tabela, dict):
        return ["tabela de regras eticas nao e objeto"]

    erros = _erros_de_piso(minimo_motivo_regra=minimo_motivo_regra,
                           minimo_motivo_pendencia=minimo_motivo_pendencia)
    if erros:
        return erros

    if tabela.get("schema_version") != SCHEMA_VERSION:
        erros.append("schema_version deve ser %s" % SCHEMA_VERSION)

    _checar_procedencia(tabela, erros)
    _checar_pendencia(tabela, erros, minimo_motivo=minimo_motivo_pendencia)
    dominios = _checar_dominios(tabela, erros)

    regras = tabela.get("regras")
    compiladas = []
    if not isinstance(regras, list):
        erros.append("regras ausente ou nao e lista")
    elif not regras:
        erros.append(MOTIVO_SEM_REGRA)
    else:
        ids = set()
        for i, item in enumerate(regras):
            compilado, escusas = _checar_regra(item, "regras[%d]" % i, dominios, ids, hoje,
                                               erros, base_arquivo,
                                               minimo_motivo=minimo_motivo_regra)
            if compilado is not None:
                compiladas.append((_texto(item.get("id")), compilado, escusas))

    _checar_controle(tabela, compiladas, erros)

    if tabela.get("habilitado") is not True:
        erros.append("capacidade DESLIGADA: regras-eticas.json traz habilitado=false. "
                     "Capacidade nova nasce desligada; ligar exige resolver a pendencia, "
                     "carregar as regras com fonte oficial e declarar revisao humana vigente "
                     "na propria tabela")
    else:
        _checar_revisao(tabela, hoje, erros)
    return erros


def avaliar(texto, alcance, tabela=None, hoje=None, caminho=TABELA_PADRAO,
            janela=JANELA_TRECHO, minimo_motivo_regra=MINIMO_MOTIVO_REGRA,
            minimo_motivo_pendencia=MINIMO_MOTIVO_PENDENCIA):
    'Aponta trechos da comunicacao externa que a tabela manda CONFERIR contra a norma.'














    hoje = hoje or _dt.date.today()
    base = {"schema_version": SCHEMA_VERSION,
            "alcance": alcance if isinstance(alcance, str) else None}

    def inconclusivo(motivos):
        saida = dict(base)
        saida["estado"] = "inconclusivo"
        saida["motivos"] = list(dict.fromkeys(str(m) for m in motivos))
        saida["leitura"] = LEITURA_INCONCLUSIVO
        return saida

    sem_alcance = not isinstance(alcance, str) or not alcance.strip()
    de_disco = tabela is None
    base_arquivo = os.path.dirname(os.path.abspath(caminho)) if de_disco else AQUI
    if de_disco:
        tabela, erro = carregar_tabela(caminho)
        if erro:
            return inconclusivo([MOTIVO_SEM_ALCANCE] if sem_alcance else [erro])

    if sem_alcance:
        return inconclusivo([_com_alcances(MOTIVO_SEM_ALCANCE, tabela)])

    try:
        no_dominio = [_texto(v) for v in tabela["dominios"]["alcance"]]
    except Exception:
        no_dominio = []
    if _pede_peca(alcance) and alcance.strip() not in no_dominio:
        return inconclusivo([_com_alcances(MOTIVO_PECA_PROCESSUAL, tabela)])

    erros = impedimentos(tabela, hoje=hoje, minimo_motivo_regra=minimo_motivo_regra,
                         minimo_motivo_pendencia=minimo_motivo_pendencia,
                         base_arquivo=base_arquivo)
    if erros:
        return inconclusivo(erros)

    if not isinstance(texto, str):
        return inconclusivo(["texto da comunicacao deve ser string para o lint etico"])

    alvo = alcance.strip()
    permitidos = [_texto(v) for v in tabela["dominios"]["alcance"]]
    if alvo not in permitidos:
        return inconclusivo(["alcance declarado '%s' nao esta em dominios.alcance (%s); nao "
                             "ha lint para alcance que o advogado nao aprovou"
                             % (alvo, ", ".join(sorted(permitidos)))])

    no_alcance = [r for r in tabela["regras"]
                  if alvo in [_texto(v) for v in r.get("alcances", [])]]
    if not no_alcance:
        return inconclusivo(["nenhuma das %d regras carregadas cobre o alcance '%s': nao "
                             "houve medicao. Silencio por ausencia de regra aplicavel nao e "
                             "conformidade" % (len(tabela["regras"]), alvo)])

    apontamentos, escusadas = [], []
    for item in no_alcance:
        ident = _texto(item.get("id"))
        compilado = re.compile(item["padrao"], re.I)
        escusas = [(_texto(p), re.compile(p, re.I)) for p in item.get("excecoes", [])]
        fonte = item.get("fonte", {})
        norma = {
            "norma": _texto(fonte.get("norma")),
            "dispositivo": _texto(fonte.get("dispositivo")),
            "url_oficial": _texto(fonte.get("url_oficial")),
            "data_extracao": _texto(fonte.get("data_extracao")),
            "sha256": _texto(fonte.get("sha256")),
            "vigencia": "%s a %s" % (_texto(fonte.get("valid_from")),
                                     _texto(fonte.get("valid_to"))),
        }
        achados, escusas_desta = _ocorrencias(compilado, escusas, texto)
        for casamento in achados:
            apontamentos.append({
                "regra_id": ident,
                "rotulo": _texto(item.get("rotulo")),
                "alcance": alvo,
                "termo": casamento.group(0),
                "trecho": _trecho(texto, casamento.start(), casamento.end(), janela=janela),
                "linha": texto.count("\n", 0, casamento.start()) + 1,
                "inicio": casamento.start(),
                "fim": casamento.end(),
                "motivo": _texto(item.get("motivo")),
                "norma_invocada": norma,
                "natureza": NATUREZA_APONTAMENTO,
            })
        for casamento, padrao in escusas_desta:

            escusadas.append({
                "regra_id": ident,
                "termo": casamento.group(0),
                "linha": texto.count("\n", 0, casamento.start()) + 1,
                "excecao": padrao,
            })

    apontamentos.sort(key=lambda a: (a["inicio"], a["regra_id"]))
    ids_no_alcance = [_texto(r.get("id")) for r in no_alcance]
    if apontamentos:
        leitura = ("AVALIADO com %d apontamento(s) sob alcance '%s', medidos pelas %d regras "
                   "carregadas para esse alcance. Cada apontamento e trecho A CONFERIR contra "
                   "a norma invocada, e nao conclusao de infracao etica - quem conclui e o "
                   "advogado." % (len(apontamentos), alvo, len(ids_no_alcance)))
    else:
        leitura = ("AVALIADO sem apontamento: nenhuma das %d regras carregadas para o alcance "
                   "'%s' acendeu. Isso NAO afirma conformidade etica - afirma apenas que "
                   "estas %d regras nao foram acionadas; a conclusao e do advogado."
                   % (len(ids_no_alcance), alvo, len(ids_no_alcance)))
    revisao = tabela.get("revisao", {})
    return {
        "schema_version": SCHEMA_VERSION,
        "estado": "avaliado",
        "alcance": alvo,
        "regras_consideradas": ids_no_alcance,
        "apontamentos": apontamentos,
        "escusas_aplicadas": escusadas,
        "leitura": leitura,
        "tabela": {
            "caminho": caminho if de_disco else None,
            "revisor": _texto(revisao.get("revisor")),
            "review_valid_to": revisao.get("review_valid_to"),
        },
    }


def resumo(resultado, maximo=MAX_RESUMO):
    """UM bloco de texto para quem opera. Nunca devolve texto de peca reescrito."""
    if resultado.get("estado") != "avaliado":
        motivos = resultado.get("motivos") or ["motivo nao declarado"]
        return (str(resultado.get("leitura") or LEITURA_INCONCLUSIVO) + "\n  Motivo: "
                + "; ".join(str(m) for m in motivos))
    itens = resultado.get("apontamentos") or []
    linhas = []
    for a in itens[:maximo]:
        norma = a.get("norma_invocada") or {}
        linhas.append("linha %s: \"%s\" (%s) - %s\n    invoca %s, %s - %s\n    trecho: %s" % (
            a.get("linha"), a.get("termo"), a.get("regra_id"), a.get("motivo"),
            norma.get("norma"), norma.get("dispositivo"), norma.get("url_oficial"),
            a.get("trecho")))
    if len(itens) > maximo:
        linhas.append("... e mais %d apontamento(s)" % (len(itens) - maximo))
    for e in resultado.get("escusas_aplicadas") or []:
        linhas.append("ESCUSADO na linha %s: \"%s\" (regra %s) - excecao da tabela: %s" % (
            e.get("linha"), e.get("termo"), e.get("regra_id"), e.get("excecao")))
    cabeca = str(resultado.get("leitura") or "")
    if not linhas:
        return cabeca
    return cabeca + "\n  " + "\n  ".join(linhas)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Lint etico da comunicacao externa: APONTA trecho para conferencia "
                    "humana contra a norma invocada. Nao reescreve e nao conclui infracao.")
    ap.add_argument("--alcance", help="alcance DECLARADO (valor de dominios.alcance da tabela)")
    ap.add_argument("--texto", help="texto da comunicacao, literal")
    ap.add_argument("--arquivo", help="arquivo .txt/.md com o texto da comunicacao")
    ap.add_argument("--tabela", default=TABELA_PADRAO, help="tabela de regras eticas")
    ap.add_argument("--hoje", help="relogio injetado AAAA-MM-DD")
    ap.add_argument("--validar", action="store_true",
                    help="so valida a tabela e lista os impedimentos")
    ap.add_argument("--json", action="store_true", dest="como_json", help="saida estruturada")


    ap.add_argument("--janela-trecho", type=int, default=JANELA_TRECHO,
                    help="contexto de cada lado do casamento (padrao %d)" % JANELA_TRECHO)
    ap.add_argument("--max-resumo", type=int, default=MAX_RESUMO,
                    help="apontamentos listados antes do 'e mais N' (padrao %d)" % MAX_RESUMO)
    ap.add_argument("--minimo-motivo-regra", type=int, default=MINIMO_MOTIVO_REGRA,
                    help="caracteres minimos do motivo de cada regra (padrao %d); baixar "
                         "afrouxa o gate em silencio" % MINIMO_MOTIVO_REGRA)
    ap.add_argument("--minimo-motivo-pendencia", type=int, default=MINIMO_MOTIVO_PENDENCIA,
                    help="caracteres minimos do motivo e do alerta da pendencia (padrao %d)"
                         % MINIMO_MOTIVO_PENDENCIA)
    args = ap.parse_args(argv)

    hoje = _data(args.hoje) if args.hoje else None
    if args.hoje and hoje is None:
        print("--hoje deve ser AAAA-MM-DD")
        return 2

    if args.validar:
        tabela, erro = carregar_tabela(args.tabela)
        erros = [erro] if erro else impedimentos(
            tabela, hoje=hoje, minimo_motivo_regra=args.minimo_motivo_regra,
            minimo_motivo_pendencia=args.minimo_motivo_pendencia,
            base_arquivo=os.path.dirname(os.path.abspath(args.tabela)))
        if args.como_json:
            print(json.dumps({"schema_version": SCHEMA_VERSION, "caminho": args.tabela,
                              "impedimentos": erros}, ensure_ascii=False, indent=2))
        elif erros:
            print("tabela INUTILIZAVEL agora - %d impedimento(s):" % len(erros))
            for e in erros:
                print("  - %s" % e)
        else:
            print("tabela utilizavel: nenhum impedimento")
        return 2 if erros else 0

    texto = args.texto
    if args.arquivo:
        try:
            with open(args.arquivo, encoding="utf-8-sig") as arquivo:
                texto = arquivo.read()
        except OSError as erro:
            print("nao foi possivel ler %s (%s)" % (args.arquivo, erro.__class__.__name__))
            return 2
    if texto is None:
        texto = ""

    resultado = avaliar(texto, args.alcance, hoje=hoje, caminho=args.tabela,
                        janela=args.janela_trecho,
                        minimo_motivo_regra=args.minimo_motivo_regra,
                        minimo_motivo_pendencia=args.minimo_motivo_pendencia)
    if args.como_json:
        print(json.dumps(resultado, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(resumo(resultado, maximo=args.max_resumo))
    if resultado.get("estado") != "avaliado":
        return 2
    return 1 if resultado.get("apontamentos") else 0


if __name__ == "__main__":
    sys.exit(main())
