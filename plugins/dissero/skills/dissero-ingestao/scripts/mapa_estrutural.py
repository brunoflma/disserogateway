#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'mapa_estrutural.py - o MAPA das pecas de um processo convertido: por peca, a ordem, a'




























































































import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from schema_mini import validar_schema

VERSAO = "1.0"
SCHEMA_VERSION = "dsr.mapa_estrutural.v1"
NOME_ARTEFATO = "MAPA-ESTRUTURAL.json"
ENV_LIGA = "DSR_MAPA_ESTRUTURAL"
MODULO_FRONTEIRA = "fronteira_peca"
STATUS = "MINUTA_PARA_REVISAO"

AQUI = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PADRAO = os.path.join(AQUI, "schema_mapa_estrutural.json")





TAMANHO_ID = 12


















FAMILIAS = {
    "pje": {"escopo": "documento", "nomeia_documento": True,
            "nota": "Pag. <n> e pagina DENTRO do documento Num. <id>"},
    "stj": {"escopo": "documento", "nomeia_documento": False,
            "nota": "Pagina <n> de <m> reinicia por documento e nao nomeia o documento"},
    "esaj": {"escopo": "autos", "nomeia_documento": False,
             "nota": "fls. <n> e folha do AUTOS e corre continua"},
}
ESCOPOS = ("documento", "autos")
ESTADOS = ("a_confirmar", "confirmado")






ESCOPO_POR_ESTRUTURAL = {True: "documento", False: "autos"}
















_A_COM_E_SEM_ACENTO = "[\u00e1a]"
LEITORES = (
    {"tipo": "pje",
     "rx": re.compile(r"Num\.\s*(?P<documento>\S+)\s*-\s*P" + _A_COM_E_SEM_ACENTO +
                      r"g\.\s*(?P<pagina>\d+)", re.I)},
    {"tipo": "stj",
     "rx": re.compile(r"P" + _A_COM_E_SEM_ACENTO +
                      r"gina\s+(?P<pagina>\d+)\s+de\s+(?P<total>\d+)", re.I)},
    {"tipo": "esaj",
     "rx": re.compile(r"fls?\.\s*(?P<pagina>\d+)", re.I)},
)








SONDAS_CHAVE = (
    "Num. 700100001 - Pag. 1",
    "Num. 700100001 - P\u00e1g. 12",
    "NUM.   700100002   -   PAG.   3",
    "fls. 45",
    "Pagina 1 de 9",
    "P\u00e1gina 12 de 340",
    "",
)



MOTIVO_SEM_TIPO = ("o relatorio de fronteira nao trouxe tipo nem motivo para este segmento: "
                   "relatorio anterior a proposta de tipo, ou montado a mao. Este mapa NAO "
                   "classifica peca - ele copia o que a fronteira propos, e nada mais")
MOTIVO_TIPO_PROPOSTO = ("tipo PROPOSTO por `taxonomia_pecas` como %r sob o rito %r, e "
                        "proposta nao e classificacao: o estado e `a_confirmar` e quem "
                        "confirma e o advogado. Nenhum caminho deste mapa escreve "
                        "`confirmado`")
MOTIVO_TIPO_ILEGIVEL = ("proposta de tipo com forma inesperada (%s) no relatorio: descartada. "
                        "Copiar o que nao se entende e afirmar sem ler")
MOTIVO_TIPO_ESTADO_INVALIDO = (
    "proposta de tipo com estado %r no relatorio, e o unico estado que uma PROPOSTA pode ter "
    "e `a_confirmar`: descartada. Confirmacao e ato humano registrado em `estado` e "
    "`confirmado_por` da peca, nunca um campo que chega de fora ja preenchido")
MOTIVO_TIPO_INCOMPLETO = ("proposta de tipo sem o essencial (id=%s, rito=%s): descartada. "
                          "Tipo sem identificador ou sem o rito em que vale nao e citavel "
                          "nem conferivel")
MOTIVO_SEM_RESUMO = ("resumo de peca e saida de modelo, nao de codigo, e um resumo errado "
                     "dentro de um mapa parece dado conferido; o campo fica nulo de "
                     "proposito e a leitura da peca continua sendo do advogado")
MOTIVO_SEM_ANCORA = ("segmento sem identificador do tribunal em nenhuma das duas pontas: "
                     "nao ha pagina a ler de dentro de identificador nenhum")
MOTIVO_FAMILIAS_MISTAS = ("pontas em familias diferentes de identificador (%s): converter "
                          "fls. <n> (folha dos AUTOS) em Pag. <n> (pagina DENTRO do "
                          "documento) exigiria saber quantas folhas cada documento anterior "
                          "ocupou, conta que este modulo nao fecha sem inventar")
MOTIVO_FAMILIA_DESCONHECIDA = ("familia de identificador %r desconhecida por este mapa; "
                               "adivinhar a regua da pagina seria pior que nao dar pagina")
MOTIVO_ATRAVESSA_DOCUMENTO = ("segmento atravessa mais de um documento PJe (%s): Pag. <n> e "
                              "pagina DENTRO de cada documento, e nao ha intervalo unico")
MOTIVO_PJE_SEM_DOCUMENTO = ("identificador PJe sem o numero do documento: pagina dentro de "
                            "documento anonimo nao e referencia resolvivel")
MOTIVO_FORA_DE_ORDEM = ("pagina inicial (%s) posterior a final (%s) no mesmo escopo: o "
                        "segmento nao fecha e o intervalo seria falso")
MOTIVO_PONTA_ABERTA = ("intervalo aberto de um lado (%s): a ponta sem identificador nao "
                       "tem pagina impressa a ler, e contar em codigo nao sobrevive a uma "
                       "reextracao")
MOTIVO_FRONTEIRA_INDISPONIVEL = ("modulo de fronteira (%s) indisponivel: %s; este mapa "
                                 "consome fronteira e nao segmenta por conta propria")
MOTIVO_RELATORIO_INVALIDO = ("relatorio recebido nao tem a forma de "
                             "fronteira_peca.segmentar() (faltam as chaves %s)")
MOTIVO_ILEGIVEL = ("identificador da ponta %s nao e legivel por este mapa (familia "
                   "declarada: %s): sem leitura do texto impresso nao ha pagina a afirmar")
MOTIVO_FAMILIA_DIVERGE = ("identificador da ponta %s e da familia %r e o relatorio declarou "
                          "%r: a regua da pagina vem do texto impresso, nao do campo")
MOTIVO_PAGINA_DIVERGE = ("pagina declarada (%s) na ponta %s nao e a que o identificador "
                         "imprimiu (%s): pagina que nao esta no texto e contagem de alguem")
MOTIVO_DOCUMENTO_DIVERGE = ("documento declarado na ponta %s nao e o que o identificador "
                            "imprimiu (%s): o documento da juntada vem do texto")
MOTIVO_ATRAVESSA_TOTAL = ("segmento entre documentos de tamanhos diferentes (%s): "
                          "`Pagina <n> de <m>` reinicia a cada documento, e duas pontas com "
                          "`de <m>` diferente nao estao no mesmo documento")
MOTIVO_AUTOCONFERENCIA = ("mapa reprovado pela conferencia do proprio modulo antes de sair "
                          "(%s); registro com ok:true que o validador reprova e o unico "
                          "resultado que este modulo se compromete a nunca produzir")
MOTIVO_RELATORIO_INCOMPATIVEL = ("relatorio de fronteira na versao %s: este mapa consome a "
                                 "familia de versao %s.x e nao adivinha a forma de outra")
MOTIVO_FRONTEIRA_INCONCLUSIVA = "fronteira inconclusiva: %s"
MOTIVO_DESLIGADO = ("capacidade nasce desligada; passe autorizado_experimental=True na "
                    "biblioteca, ou %s=1 no ambiente E --ligar na linha de comando")

CHAVES_ESPERADAS_RELATORIO = ("segmentos", "versao")




VERSAO_RELATORIO_MAIOR = "1"



def _sem_acento(s):
    'Copia sem acento, caractere a caractere, com o MESMO comprimento da entrada.'






    saida = []
    for ch in str(s or ""):
        base = "".join(c for c in unicodedata.normalize("NFD", ch)
                       if unicodedata.category(c) != "Mn")
        saida.append(base if len(base) == 1 else ch)
    return "".join(saida)


def _chave(texto):
    'Identidade de um identificador para efeito de repeticao: sem acento, sem variacao de'


    return re.sub(r"\s+", " ", _sem_acento(unicodedata.normalize("NFC", str(texto or ""))
                                           )).strip().lower()


def _sha(semente):
    return hashlib.sha256(str(semente).encode("utf-8")).hexdigest()


def _texto(valor):
    return str(valor or "").strip()


def _inteiro(valor):
    'int quando for inteiro de verdade; None em qualquer outro caso.'



    if isinstance(valor, bool) or not isinstance(valor, int):
        return None
    return valor


def _digito(valor):
    'int quando o grupo da regex casou digito; None quando o grupo nao existe naquela'

    bruto = str(valor if valor is not None else "").strip()
    return int(bruto) if bruto.isdigit() else None


def _doc_chave(valor):
    'Identidade de um numero de documento PJe para efeito de COMPARACAO entre as pontas.'







    bruto = _chave(valor)
    if not bruto.isdigit():
        return bruto
    return bruto.lstrip("0") or "0"


def _ler_com(tabela, texto):
    'Leitura de UM identificador com uma tabela na forma de `fronteira_peca.ANCORAS`.'










    vazio = {"familia": None, "pagina": None, "documento": None, "total": None}
    alvo = str(texto or "")
    if not alvo.strip():
        return vazio
    melhor = None
    for spec in tabela or ():
        rx = spec.get("rx") if isinstance(spec, dict) else None
        if rx is None:
            continue
        achado = rx.search(alvo)
        if achado is None:
            continue
        if melhor is not None and achado.start() >= melhor[0]:
            continue
        grupos = achado.groupdict()
        melhor = (achado.start(), {
            "familia": _texto(spec.get("tipo")) or None,
            "pagina": _digito(grupos.get("pagina")),
            "documento": _texto(grupos.get("documento")) or None,
            "total": _digito(grupos.get("total")),
        })
    return melhor[1] if melhor else vazio


def ler_identificador(texto, leitores=None):
    '{familia, pagina, documento, total} LIDO do texto literal do identificador.'





    return _ler_com(LEITORES if leitores is None else leitores, texto)


def carregar_json(caminho):
    with open(caminho, encoding="utf-8") as arquivo:
        return json.load(arquivo)



def peca_id_de(ancora_inicial, ancora_final, desempate=0):
    'Identificador da peca = o PAR DE ANCORAS que a delimita, e nao a posicao dela.'







    semente = "%s|%s|%d" % (_chave(ancora_inicial), _chave(ancora_final), int(desempate or 0))
    return _sha(semente)[:TAMANHO_ID]


def esqueleto_de(pecas):
    'Sequencia de pares de ancora do mapa, em ordem. E o que o identifica quando nao ha'

    linhas = []
    for peca in pecas or []:
        cit = peca.get("citacao_ancora") or {}
        linhas.append("%s|%s" % (_chave(cit.get("inicial")), _chave(cit.get("final"))))
    return "\n".join(linhas)


def mapa_id_de(pecas, origem_sha256=None):
    '(mapa_id, base). Prefere o sha do markdown de origem, quando o chamador o conhece -'


    origem = _texto(origem_sha256)
    if len(origem) == 64 and all(c in "0123456789abcdefABCDEF" for c in origem):
        return origem.lower()[:TAMANHO_ID], "origem_sha256"
    return _sha(esqueleto_de(pecas))[:TAMANHO_ID], "esqueleto_de_ancoras"



def derivar_paginacao(ancora_inicial, ancora_final, leitor=None, familias=None):
    'Intervalo de paginas do segmento, LIDO de dentro dos identificadores.'























    base = {"escopo": None, "familia": None, "documento_ref": None,
            "inicial": None, "final": None, "motivo": None}
    tabela = FAMILIAS if familias is None else familias
    ler = ler_identificador if leitor is None else leitor



    pontas = []
    for rotulo, ancora in (("inicio", ancora_inicial), ("fim", ancora_final)):
        if not isinstance(ancora, dict) or not _texto(ancora.get("texto")):
            continue
        pontas.append((rotulo, ancora, ler(_texto(ancora.get("texto")))))
    if not pontas:
        base["motivo"] = MOTIVO_SEM_ANCORA
        return base

    for rotulo, ancora, lido in pontas:
        lida = (lido or {}).get("familia")
        if lida is None:
            base["motivo"] = MOTIVO_ILEGIVEL % (
                rotulo, _texto(ancora.get("tipo"))[:40] or "nenhuma")
            return base
        declarada = _texto(ancora.get("tipo"))
        if declarada and declarada != lida:
            base["motivo"] = MOTIVO_FAMILIA_DIVERGE % (rotulo, lida, declarada[:40])
            return base

    familias_lidas = sorted({lido["familia"] for _, _, lido in pontas})
    if len(familias_lidas) > 1:
        base["motivo"] = MOTIVO_FAMILIAS_MISTAS % ", ".join(familias_lidas)
        return base

    familia = familias_lidas[0]
    spec = tabela.get(familia) if hasattr(tabela, "get") else None
    if spec is None:
        base["motivo"] = MOTIVO_FAMILIA_DESCONHECIDA % familia
        return base

    base["familia"] = familia
    base["escopo"] = spec["escopo"]

    paginas = {"inicio": None, "fim": None}
    for rotulo, ancora, lido in pontas:
        impressa = lido.get("pagina")
        declarada = ancora.get("pagina")
        if declarada is not None and _inteiro(declarada) != impressa:
            base["motivo"] = MOTIVO_PAGINA_DIVERGE % (_inteiro(declarada), rotulo, impressa)
            return base
        paginas[rotulo] = impressa

    if spec["nomeia_documento"]:
        impressos = []
        for rotulo, ancora, lido in pontas:
            impresso = _texto(lido.get("documento"))
            declarado = _texto(ancora.get("documento"))
            if declarado and _doc_chave(declarado) != _doc_chave(impresso):
                base["motivo"] = MOTIVO_DOCUMENTO_DIVERGE % (rotulo, impresso or "nenhum")
                return base
            impressos.append(impresso)
        if len({_doc_chave(d) for d in impressos}) > 1:
            base["motivo"] = MOTIVO_ATRAVESSA_DOCUMENTO % ", ".join(sorted(set(impressos)))
            return base
        base["documento_ref"] = impressos[0] or None
        if not base["documento_ref"]:
            base["motivo"] = MOTIVO_PJE_SEM_DOCUMENTO
            return base

    totais = sorted({lido["total"] for _, _, lido in pontas if lido.get("total") is not None})
    if len(totais) > 1:
        base["motivo"] = MOTIVO_ATRAVESSA_TOTAL % ", ".join(str(t) for t in totais)
        return base

    pagina_i, pagina_f = paginas["inicio"], paginas["fim"]
    if pagina_i is not None and pagina_f is not None and pagina_i > pagina_f:
        base["motivo"] = MOTIVO_FORA_DE_ORDEM % (pagina_i, pagina_f)
        return base

    base["inicial"], base["final"] = pagina_i, pagina_f
    if pagina_i is None or pagina_f is None:
        abertas = []
        if pagina_i is None:
            abertas.append("inicio")
        if pagina_f is None:
            abertas.append("fim")
        base["motivo"] = MOTIVO_PONTA_ABERTA % " e ".join(abertas)
    return base



def _carregar_fronteira(importador=None):
    '(modulo, erro). Importacao PREGUICOSA e injetavel.'







    fabrica = importador
    if fabrica is None:
        def fabrica():
            import importlib
            return importlib.import_module(MODULO_FRONTEIRA)
    try:
        return fabrica(), None
    except Exception as erro:
        return None, "%s: %s" % (erro.__class__.__name__, erro)


def conferir_deriva(familias=None, normalizador=None, sondas=None, importador=None,
                    leitores=None):
    'Divergencias entre este mapa e `fronteira_peca`. Lista vazia = de acordo.'






















    tabela = FAMILIAS if familias is None else familias
    conhecidas = set(tabela)
    normalizar = _chave if normalizador is None else normalizador
    tabela_leitura = LEITORES if leitores is None else leitores
    alvos = SONDAS_CHAVE if sondas is None else tuple(sondas)
    modulo, erro = _carregar_fronteira(importador)
    if modulo is None:
        return [{"tipo": "modulo", "erro": erro}]
    fora = []
    try:
        ancoras_la = tuple(getattr(modulo, "ANCORAS", ()))
        la = {_texto(spec.get("tipo")) for spec in ancoras_la}
        estrutural_la = {_texto(spec.get("tipo")): bool(spec.get("estrutural"))
                         for spec in ancoras_la}
    except Exception as falha:
        return [{"tipo": "modulo", "erro": "ANCORAS ilegivel: %s" % falha}]
    for nome in sorted(la - conhecidas):
        fora.append({"tipo": "familia", "familia": nome, "onde": MODULO_FRONTEIRA})
    for nome in sorted(conhecidas - la):
        fora.append({"tipo": "familia", "familia": nome, "onde": "mapa_estrutural"})
    if hasattr(tabela, "get"):
        for nome in sorted(conhecidas & set(estrutural_la)):
            esperado = ESCOPO_POR_ESTRUTURAL[estrutural_la[nome]]
            achado = (tabela.get(nome) or {}).get("escopo")
            if achado != esperado:
                fora.append({"tipo": "escopo", "familia": nome, "mapa_estrutural": achado,
                             "esperado_por_estrutural": esperado, "onde": MODULO_FRONTEIRA})
    for sonda in alvos:
        try:
            aqui_l, la_l = _ler_com(tabela_leitura, sonda), _ler_com(ancoras_la, sonda)
        except Exception as falha:
            aqui_l, la_l = {"erro": "%s" % falha}, None
        if aqui_l != la_l:
            fora.append({"tipo": "leitura", "sonda": sonda,
                         "mapa_estrutural": aqui_l, MODULO_FRONTEIRA: la_l})
    chave_la = getattr(modulo, "_chave_ancora", None)
    if not callable(chave_la):
        fora.append({"tipo": "chave", "erro": "fronteira_peca._chave_ancora ausente"})
        return fora
    for sonda in alvos:
        try:
            aqui, acola = normalizar(sonda), chave_la(sonda)
        except Exception as falha:
            aqui, acola = "erro: %s" % falha, None
        if aqui != acola:
            fora.append({"tipo": "chave", "sonda": sonda,
                         "mapa_estrutural": aqui, MODULO_FRONTEIRA: acola})
    return fora



def _recusa(motivo, desligado=True):
    'Registro de recusa. SEM a chave `pecas`, de proposito: um chamador que faca'








    return {"ok": False, "desligado": bool(desligado), "schema_version": SCHEMA_VERSION,
            "versao": VERSAO, "status": STATUS, "motivo": motivo}


def _base(fronteira, origem_sha256, gerado_em):
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "versao": VERSAO,
        "status": STATUS,
        "gerado_em": gerado_em,
        "mapa_id": None,
        "base_do_mapa_id": "esqueleto_de_ancoras",
        "origem_sha256": _texto(origem_sha256) or None,
        "fronteira": fronteira,
        "inconclusivo": False,
        "motivo": None,
        "pecas": [],
        "segmentos_descartados": [],
        "avisos": [],
    }


def _bloco_fronteira(relatorio, disponivel=True, erro=None):
    rel = relatorio if isinstance(relatorio, dict) else {}
    return {
        "modulo": MODULO_FRONTEIRA,
        "versao": rel.get("versao"),
        "disponivel": bool(disponivel),
        "erro": erro,
        "parametros": rel.get("parametros"),
        "sistemas": list(rel.get("sistemas") or []),
        "ancoras": rel.get("ancoras"),
        "inconclusivo": bool(rel.get("inconclusivo")),
        "motivo": rel.get("motivo"),
    }


def _fechar(registro):
    'Fecha a identidade do registro e o submete AO PROPRIO VALIDADOR antes de devolver.'







    registro["mapa_id"], registro["base_do_mapa_id"] = mapa_id_de(
        registro["pecas"], registro.get("origem_sha256"))
    achados = validar_regras(registro)
    if achados:
        registro["ok"] = False
        registro["inconclusivo"] = True
        registro["motivo"] = MOTIVO_AUTOCONFERENCIA % "; ".join(achados[:3])
        registro["pecas"] = []
        registro["mapa_id"], registro["base_do_mapa_id"] = mapa_id_de(
            registro["pecas"], registro.get("origem_sha256"))
    return registro


CONFIANCAS = ("baixa", "media", "alta")
AVISO_PAREAMENTO = ("fronteira %d nao casa com o segmento %d pela ancora %s; a confianca "
                    "daquela ponta saiu nula em vez de errada")


def _confianca_da_fronteira(fronteiras, indice, campo_ancora, texto_esperado):
    '(confianca, aviso) da fronteira que delimita um lado do segmento.'








    if not texto_esperado or indice < 0 or indice >= len(fronteiras):
        return None, None
    fronteira = fronteiras[indice] if isinstance(fronteiras[indice], dict) else {}
    ancora = fronteira.get(campo_ancora)
    achado = _texto((ancora or {}).get("texto")) if isinstance(ancora, dict) else ""
    if _chave(achado) != _chave(texto_esperado):
        return None, AVISO_PAREAMENTO % (indice + 1, indice + 2, campo_ancora)
    rotulo = _texto(fronteira.get("confianca"))
    return (rotulo if rotulo in CONFIANCAS else None), None


def _tipo_do_segmento(seg):
    '(tipo_peca, motivo_tipo_peca) COPIADOS do relatorio da fronteira.'










    proposta = seg.get("tipo_peca")
    if proposta is None:
        return None, _texto(seg.get("motivo_tipo_peca")) or MOTIVO_SEM_TIPO
    if not isinstance(proposta, dict):
        return None, MOTIVO_TIPO_ILEGIVEL % type(proposta).__name__
    estado = _texto(proposta.get("estado"))
    if estado != "a_confirmar":
        return None, MOTIVO_TIPO_ESTADO_INVALIDO % (estado or "(ausente)")
    tipo = proposta.get("tipo_proposto")
    ident = _texto(tipo.get("id")) if isinstance(tipo, dict) else ""
    rito = _texto(proposta.get("rito_declarado"))
    if not ident or not rito:
        return None, MOTIVO_TIPO_INCOMPLETO % (ident or "(sem id)", rito or "(sem rito)")
    return proposta, MOTIVO_TIPO_PROPOSTO % (ident, rito)


def mapear_de_relatorio(relatorio, autorizado_experimental=False, origem_sha256=None,
                        gerado_em=None):
    'Registro `dsr.mapa_estrutural.v1` a partir de um relatorio de `fronteira_peca`.'






    if not autorizado_experimental:
        return _recusa(MOTIVO_DESLIGADO % ENV_LIGA)

    if not isinstance(relatorio, dict):
        return _recusa(MOTIVO_RELATORIO_INVALIDO % ", ".join(CHAVES_ESPERADAS_RELATORIO),
                       desligado=False)
    faltando = [c for c in CHAVES_ESPERADAS_RELATORIO if c not in relatorio]
    if faltando or not isinstance(relatorio.get("segmentos"), list):
        alvo = faltando or ["segmentos (nao e lista)"]
        return _recusa(MOTIVO_RELATORIO_INVALIDO % ", ".join(alvo), desligado=False)
    versao_de_la = _texto(relatorio.get("versao"))
    if versao_de_la.split(".")[0] != VERSAO_RELATORIO_MAIOR:
        return _recusa(MOTIVO_RELATORIO_INCOMPATIVEL % (versao_de_la[:20] or "nenhuma",
                                                        VERSAO_RELATORIO_MAIOR),
                       desligado=False)

    registro = _base(_bloco_fronteira(relatorio), origem_sha256, gerado_em)

    if relatorio.get("inconclusivo"):
        registro["inconclusivo"] = True
        registro["motivo"] = MOTIVO_FRONTEIRA_INCONCLUSIVA % _texto(relatorio.get("motivo"))
        return _fechar(registro)

    fronteiras = relatorio.get("fronteiras") if isinstance(relatorio.get("fronteiras"), list) else []
    vistos = {}
    for posicao, segmento in enumerate(relatorio.get("segmentos") or []):
        seg = segmento if isinstance(segmento, dict) else {}
        inicial = seg.get("ancora_inicial") if isinstance(seg.get("ancora_inicial"), dict) else None
        final = seg.get("ancora_final") if isinstance(seg.get("ancora_final"), dict) else None
        texto_i = _texto((inicial or {}).get("texto")) or None
        texto_f = _texto((final or {}).get("texto")) or None



        if texto_i is None:
            inicial = None
        if texto_f is None:
            final = None
        if inicial is None and final is None:





            registro["segmentos_descartados"].append({
                "ordem_no_segmentador": _inteiro(seg.get("ordem")),
                "motivo": MOTIVO_SEM_ANCORA})
            continue
        chave = (_chave(texto_i), _chave(texto_f))
        desempate = vistos.get(chave, 0)
        vistos[chave] = desempate + 1
        ambigua = bool((inicial or {}).get("ambigua") or (final or {}).get("ambigua")
                       or desempate > 0)
        conf_i, aviso_i = _confianca_da_fronteira(
            fronteiras, posicao - 1, "ancora_seguinte", texto_i)
        conf_f, aviso_f = _confianca_da_fronteira(
            fronteiras, posicao, "ancora_anterior", texto_f)
        for aviso in (aviso_i, aviso_f):
            if aviso and aviso not in registro["avisos"]:
                registro["avisos"].append(aviso)
        tipo_peca, motivo_tipo = _tipo_do_segmento(seg)
        registro["pecas"].append({
            "ordem": len(registro["pecas"]) + 1,
            "peca_id": peca_id_de(texto_i, texto_f, desempate),
            "desempate": desempate,
            "citacao_ancora": {"inicial": texto_i, "final": texto_f},
            "paginacao": derivar_paginacao(inicial, final),
            "confianca_fronteira": {"inicial": conf_i, "final": conf_f},
            "ancora_ambigua": ambigua,
            "estado": "a_confirmar",
            "confirmado_por": None,
            "tipo_peca": tipo_peca,
            "motivo_tipo_peca": motivo_tipo,
            "resumo": None,
            "motivo_resumo": MOTIVO_SEM_RESUMO,
        })

    if not registro["pecas"]:
        registro["inconclusivo"] = True
        registro["motivo"] = ("nenhum segmento da fronteira tem identificador em qualquer "
                              "ponta; nao ha peca citavel a mapear")
    if registro["segmentos_descartados"]:
        registro["avisos"].append(
            "%d segmento(s) descartado(s) por falta de identificador nas duas pontas"
            % len(registro["segmentos_descartados"]))
    return _fechar(registro)


def mapear(texto, autorizado_experimental=False, minimo_familias_fecho=None,
           janela_gaps=None, origem_sha256=None, gerado_em=None, importador=None,
           rito=None, hoje=None, autorizado_tipo=False):
    'Registro do mapa a partir do markdown dos autos, via `fronteira_peca.segmentar()`.'















    if not autorizado_experimental:
        return _recusa(MOTIVO_DESLIGADO % ENV_LIGA)
    modulo, erro = _carregar_fronteira(importador)
    if modulo is None:
        registro = _base(_bloco_fronteira(None, disponivel=False, erro=erro),
                         origem_sha256, gerado_em)
        registro["inconclusivo"] = True
        registro["motivo"] = MOTIVO_FRONTEIRA_INDISPONIVEL % (MODULO_FRONTEIRA, erro)
        return _fechar(registro)
    extras = {}




    if rito is not None:
        extras["rito"] = rito


        extras["autorizado_tipo"] = autorizado_tipo is True
    if hoje is not None:
        extras["hoje"] = hoje
    if minimo_familias_fecho is not None:
        extras["minimo_familias_fecho"] = int(minimo_familias_fecho)
    if janela_gaps is not None:
        extras["janela_gaps"] = int(janela_gaps)
    try:
        relatorio = modulo.segmentar(texto, **extras)
    except Exception as falha:
        detalhe = "%s: %s" % (falha.__class__.__name__, falha)
        registro = _base(_bloco_fronteira(None, disponivel=False, erro=detalhe),
                         origem_sha256, gerado_em)
        registro["inconclusivo"] = True
        registro["motivo"] = MOTIVO_FRONTEIRA_INDISPONIVEL % (MODULO_FRONTEIRA, detalhe)
        return _fechar(registro)
    return mapear_de_relatorio(relatorio, autorizado_experimental=True,
                               origem_sha256=origem_sha256, gerado_em=gerado_em)



def validar_regras(dados):
    'As regras que o schema nao expressa. Lista vazia = registro integro.'




























    erros = []
    pecas = dados.get("pecas")
    if not isinstance(pecas, list):
        return ["pecas ausente ou nao e lista"]

    vistos = {}
    for indice, peca in enumerate(pecas):
        p = peca if isinstance(peca, dict) else {}
        marca = "peca[%d]: " % indice

        if _inteiro(p.get("ordem")) != indice + 1:
            erros.append(marca + "ordem deve ser %d (1..N contigua, na ordem de leitura)"
                         % (indice + 1))

        cit = p.get("citacao_ancora") if isinstance(p.get("citacao_ancora"), dict) else {}
        ini, fim = cit.get("inicial"), cit.get("final")
        if ini is None and fim is None:
            erros.append(marca + "peca sem identificador em nenhuma ponta nao e citavel")

        chave = (_chave(ini), _chave(fim))
        esperado = vistos.get(chave, 0)
        vistos[chave] = esperado + 1
        desempate = _inteiro(p.get("desempate"))
        if desempate != esperado:
            erros.append(marca + "desempate deve ser %d (ocorrencias anteriores do mesmo "
                                 "par de ancoras neste mapa)" % esperado)
        elif p.get("peca_id") != peca_id_de(ini, fim, desempate):
            erros.append(marca + "peca_id deve ser derivado do par de ancoras e do "
                                 "desempate (ancora editada depois do registro)")
        if desempate and not p.get("ancora_ambigua"):
            erros.append(marca + "desempate > 0 sem ancora_ambigua: par repetido e ancora "
                                 "repetida")

        erros.extend(_erros_paginacao(p, marca))
        erros.extend(_erros_leitura(p, marca))

        conf = p.get("confianca_fronteira") if isinstance(p.get("confianca_fronteira"), dict) else {}
        for lado in ("inicial", "final"):
            if conf.get(lado) is not None and cit.get(lado) is None:
                erros.append(marca + "confianca_fronteira.%s sem ancora %s: confianca de "
                                     "fronteira que nao existe nao e afirmavel" % (lado, lado))

        tp = p.get("tipo_peca")
        if tp is not None:




            if not isinstance(tp, dict):
                erros.append(marca + "tipo_peca deve ser nulo ou objeto de proposta")
            else:
                if _texto(tp.get("estado")) != "a_confirmar":
                    erros.append(marca + "tipo_peca.estado deve ser 'a_confirmar': tipo que "
                                         "chega confirmado de fora nao passou por conferencia "
                                         "humana nenhuma")
                alvo = tp.get("tipo_proposto")
                if not isinstance(alvo, dict) or not _texto(alvo.get("id")):
                    erros.append(marca + "tipo_peca.tipo_proposto.id ausente: tipo sem "
                                         "identificador nao e conferivel")
                if not _texto(tp.get("rito_declarado")):
                    erros.append(marca + "tipo_peca.rito_declarado ausente: tipo de peca so "
                                         "existe dentro de um rito")
        if not _texto(p.get("motivo_tipo_peca")):
            erros.append(marca + "motivo_tipo_peca vazio: campo nulo sem razao escrita e "
                                 "lacuna disfarcada")
        if p.get("resumo") is not None:
            erros.append(marca + "resumo deve ser nulo: resumo de peca e saida de modelo, "
                                 "nao de codigo")
        if not _texto(p.get("motivo_resumo")):
            erros.append(marca + "motivo_resumo vazio: campo nulo sem razao escrita e "
                                 "lacuna disfarcada")
        if p.get("estado") not in ESTADOS:
            erros.append(marca + "estado %r fora de %s: o ciclo de vida da peca neste "
                                 "contrato tem dois estados" % (p.get("estado"),
                                                                list(ESTADOS)))
        if p.get("estado") == "confirmado" and not _texto(p.get("confirmado_por")):
            erros.append(marca + "estado 'confirmado' exige confirmado_por: confirmacao e "
                                 "ato humano identificado")
        if p.get("estado") != "confirmado" and _texto(p.get("confirmado_por")):
            erros.append(marca + "confirmado_por preenchido com estado %r"
                         % p.get("estado"))

    ids = [(p or {}).get("peca_id") for p in pecas if isinstance(p, dict)]
    if len(set(ids)) != len(ids):
        erros.append("peca_id repetido no mapa")

    esperado_id, esperada_base = mapa_id_de(pecas, dados.get("origem_sha256"))
    if dados.get("base_do_mapa_id") != esperada_base:
        erros.append("base_do_mapa_id deve ser %r para este registro" % esperada_base)
    elif dados.get("mapa_id") != esperado_id:
        erros.append("mapa_id nao confere com o registro (esperado %s)" % esperado_id)

    if dados.get("inconclusivo") and pecas:
        erros.append("registro inconclusivo com %d peca(s): inconclusivo e zero peca"
                     % len(pecas))
    if dados.get("inconclusivo") and not _texto(dados.get("motivo")):
        erros.append("registro inconclusivo sem motivo escrito")
    return erros


def _erros_paginacao(peca, marca):
    pag = peca.get("paginacao") if isinstance(peca.get("paginacao"), dict) else None
    if pag is None:
        return [marca + "paginacao ausente"]
    erros = []
    familia, escopo = pag.get("familia"), pag.get("escopo")
    ref = pag.get("documento_ref")
    p_i, p_f = _inteiro(pag.get("inicial")), _inteiro(pag.get("final"))
    motivo = _texto(pag.get("motivo"))

    if familia is not None and familia not in FAMILIAS:
        erros.append(marca + "familia %r desconhecida" % familia)
    if escopo is not None and escopo not in ESCOPOS:
        erros.append(marca + "escopo %r fora de %s" % (escopo, list(ESCOPOS)))
    if familia is None and (p_i is not None or p_f is not None):
        erros.append(marca + "pagina sem familia de identificador declarada: pagina que nao "
                             "veio de identificador e contagem propria")
    if familia in FAMILIAS:
        certo = FAMILIAS[familia]["escopo"]
        if escopo != certo:
            erros.append(marca + "familia %r tem escopo %r, nao %r - converter folha dos "
                                 "autos em pagina dentro do documento (ou o contrario) e a "
                                 "conta que este contrato proibe" % (familia, certo, escopo))
    if escopo == "autos" and ref is not None:
        erros.append(marca + "escopo 'autos' nao tem documento_ref: fls. e folha do autos "
                             "e nao pertence a documento nenhum")



    if escopo is not None and familia is None:
        erros.append(marca + "escopo %r declarado sem familia de identificador: regua de "
                             "pagina sem fonte nao e afirmavel" % escopo)
    for nome, valor in (("inicial", pag.get("inicial")), ("final", pag.get("final"))):
        if valor is not None and _inteiro(valor) is None:
            erros.append(marca + "pagina %s nao e inteiro" % nome)
        elif _inteiro(valor) is not None and _inteiro(valor) < 1:
            erros.append(marca + "pagina %s deve ser >= 1" % nome)
    if p_i is not None and p_f is not None:
        if p_i > p_f:
            erros.append(marca + "pagina inicial %d posterior a final %d" % (p_i, p_f))
        if familia == "pje" and not _texto(ref):
            erros.append(marca + "intervalo PJe fechado exige documento_ref: Pag. <n> e "
                                 "pagina DENTRO do documento")
    falta_pagina = (p_i is None or p_f is None)
    if falta_pagina and not motivo:
        erros.append(marca + "intervalo incompleto sem motivo escrito")
    if not falta_pagina and motivo:
        erros.append(marca + "intervalo completo com motivo: motivo e a razao de NAO haver "
                             "intervalo")
    return erros


def _erros_leitura(peca, marca):
    'Regra 11: o registro conferido contra o TEXTO das proprias ancoras.'









    pag = peca.get("paginacao") if isinstance(peca.get("paginacao"), dict) else None
    if pag is None:
        return []
    cit = peca.get("citacao_ancora") if isinstance(peca.get("citacao_ancora"), dict) else {}
    erros = []
    lidas = {}
    for lado in ("inicial", "final"):
        texto = _texto(cit.get(lado))
        lidas[lado] = ler_identificador(texto) if texto else None
    legiveis = [lido for lido in lidas.values() if lido and lido.get("familia")]
    familias_lidas = sorted({lido["familia"] for lido in legiveis})

    declarada = pag.get("familia")
    if declarada is not None:
        if not familias_lidas:
            erros.append(marca + "familia %r declarada e nenhuma ponta tem identificador "
                                 "legivel: regua de pagina sem texto impresso nao e "
                                 "afirmavel" % declarada)
        elif len(familias_lidas) > 1:
            erros.append(marca + "familia %r declarada com as pontas em familias diferentes "
                                 "(%s): nao ha regua unica a declarar"
                         % (declarada, ", ".join(familias_lidas)))
        elif declarada != familias_lidas[0]:
            erros.append(marca + "familia declarada %r contra identificador que diz %r: a "
                                 "regua da pagina vem do texto impresso, nao do campo"
                         % (declarada, familias_lidas[0]))

    for lado in ("inicial", "final"):
        numero = _inteiro(pag.get(lado))
        if numero is None:
            continue
        impressa = (lidas.get(lado) or {}).get("pagina")
        if impressa != numero:
            erros.append(marca + "pagina %s %d nao esta impressa no identificador daquela "
                                 "ponta (%s): pagina que nao veio do texto e contagem de "
                                 "alguem" % (lado, numero, impressa))

    documentos = {_doc_chave(lido["documento"]) for lido in legiveis
                  if _texto(lido.get("documento"))}
    ref = _texto(pag.get("documento_ref"))
    if ref and _doc_chave(ref) not in documentos:
        erros.append(marca + "documento_ref nao e o documento impresso nas ancoras da peca")
    if _inteiro(pag.get("inicial")) is not None and _inteiro(pag.get("final")) is not None:
        if len(documentos) > 1:
            erros.append(marca + "intervalo fechado com as pontas em documentos diferentes: "
                                 "Pag. <n> e pagina DENTRO de cada documento")
        totais = {lido["total"] for lido in legiveis if lido.get("total") is not None}
        if len(totais) > 1:
            erros.append(marca + "intervalo fechado com as pontas em documentos de tamanhos "
                                 "diferentes (%s): a contagem reinicia a cada documento"
                         % ", ".join(str(t) for t in sorted(totais)))
    return erros


def validar_mapa(dados, schema_path=SCHEMA_PADRAO):
    """[] quando o registro esta integro; lista de erros legiveis quando nao."""
    erros = validar_schema(dados, carregar_json(schema_path))
    if erros:
        return erros
    return validar_regras(dados)



def ligado(argv_ligar=False, ambiente=None):
    'Duas portas, ambas explicitas e AMBAS necessarias.'





    env = (ambiente if ambiente is not None else os.environ)
    por_env = str(env.get(ENV_LIGA, "")).strip() in ("1", "true", "TRUE")
    return bool(argv_ligar) and por_env





ENV_TIPO = "DSR_TAXONOMIA_PECAS"


def _tipo_ligado(ambiente=None):
    env = (ambiente if ambiente is not None else os.environ)
    return str(env.get(ENV_TIPO, "")).strip() == "1"


def _saida(payload):
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Mapa estrutural do processo: ordem, ancora de citacao e intervalo de "
                    "paginas por peca. Nao tipa, nao resume, nao segmenta por conta propria.")
    ap.add_argument("arquivo", nargs="?", help="markdown ja extraido dos autos")
    ap.add_argument("--relatorio", help="JSON ja produzido por fronteira_peca.segmentar()")
    ap.add_argument("--validar", help="valida um MAPA-ESTRUTURAL.json existente e sai")
    ap.add_argument("--ligar", action="store_true",
                    help="liga a capacidade nesta execucao; exige TAMBEM %s=1" % ENV_LIGA)
    ap.add_argument("--origem-sha256", default=None,
                    help="sha256 do markdown de origem, quando conhecido (proveniencia)")
    ap.add_argument("--minimo-familias-fecho", type=int, default=None,
                    help="repassado a fronteira_peca (padrao: o de la)")
    ap.add_argument("--janela-gaps", type=int, default=None,
                    help="repassado a fronteira_peca (padrao: o de la)")


    ap.add_argument("--rito", default=None,
                    help="rito dos autos (civel, trabalhista, penal...); com %s=1 habilita a "
                         "PROPOSTA de tipo por peca. Sem os dois, o tipo sai nulo com o motivo"
                         % ENV_TIPO)
    ap.add_argument("--schema", default=SCHEMA_PADRAO)
    try:
        args = ap.parse_args(argv)
    except SystemExit:
        return 2

    if args.validar:
        try:
            dados = carregar_json(args.validar)
        except (OSError, ValueError) as erro:
            _saida({"ok": False, "versao": VERSAO, "motivo": "arquivo ilegivel: %s" % erro})
            return 2
        erros = validar_mapa(dados, args.schema)
        _saida({"ok": not erros, "versao": VERSAO, "erros": erros})
        return 0 if not erros else 2

    if not ligado(args.ligar):
        _saida(_recusa(MOTIVO_DESLIGADO % ENV_LIGA))
        print("desligado: exige %s=1 no ambiente E --ligar na linha de comando" % ENV_LIGA,
              file=sys.stderr)
        return 1

    if bool(args.arquivo) == bool(args.relatorio):
        _saida({"ok": False, "versao": VERSAO,
                "motivo": "informe UM entre <arquivo> markdown e --relatorio"})
        return 2

    try:
        if args.relatorio:
            registro = mapear_de_relatorio(
                carregar_json(args.relatorio), autorizado_experimental=True,
                origem_sha256=args.origem_sha256)
        else:
            with open(args.arquivo, encoding="utf-8", errors="replace") as f:
                texto = f.read()
            registro = mapear(texto, autorizado_experimental=True,
                              minimo_familias_fecho=args.minimo_familias_fecho,
                              janela_gaps=args.janela_gaps,
                              origem_sha256=args.origem_sha256,
                              rito=args.rito,
                              autorizado_tipo=_tipo_ligado())
    except (OSError, ValueError) as erro:
        _saida({"ok": False, "versao": VERSAO, "motivo": "entrada ilegivel: %s" % erro})
        return 2

    _saida(registro)
    if not registro.get("ok"):
        print("recusado: %s" % registro.get("motivo"), file=sys.stderr)
        return 1
    if not registro.get("pecas"):
        print("escalar: nenhuma peca mapeada - %s" % registro.get("motivo"), file=sys.stderr)
        return 1
    _tipadas = sum(1 for p in registro["pecas"] if p.get("tipo_peca"))
    print("%d peca(s) mapeada(s), todas em 'a_confirmar'; %d com tipo PROPOSTO (a conferir), "
          "nenhuma resumida" % (len(registro["pecas"]), _tipadas), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
