#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'comparar_calculos.py - poe duas ou tres memorias de calculo lado a lado e quantifica a'




































































from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext

AQUI = os.path.dirname(os.path.abspath(__file__))


if AQUI not in sys.path:
    sys.path.insert(0, AQUI)

try:
    from schema_mini import validar_schema
except Exception:
    validar_schema = None

SCHEMA_VERSION = "dsr.comparacao_calculos.v1"
PEDIDO_VERSION = "dsr.comparacao_calculos.pedido.v1"
COMPARADOR_VERSION = "dsr.comparar_calculos.v1"
STATUS = "MINUTA_PARA_REVISAO"
VAR_AMBIENTE = "DSR_COMPARAR_CALCULOS_EXPERIMENTAL"
SCHEMA_SAIDA = "comparacao_calculos.schema.json"

INDISPONIVEL_SCHEMA = ("schema_mini.py indisponivel ao lado do comparador - sem validador "
                       "nenhuma memoria e conferida contra o seu contrato, e nada e comparado "
                       "(falha fechada)")





MIN_MEMORIAS = 2
MAX_MEMORIAS = 3






ESCALA_PERCENTUAL_PADRAO = 6
MODO_PERCENTUAL = "ROUND_HALF_EVEN"









PRECISAO_INTERMEDIARIA = 60






LIMIAR_MATERIALIDADE_PCT_PADRAO = None

ESCOPOS = ("tudo", "totais")

NUMERO_RX = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
ID_RX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
COMPETENCIA_RX = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")



MONETARIO = "monetario"
VALOR_POR_HORA = "valor_por_hora"
FATOR = "fator"
TAXA_PERCENTUAL = "taxa_percentual"
GRANDEZAS_COM_MOEDA = (MONETARIO, VALOR_POR_HORA)

CONTRATOS_SEM_PROJECAO = {
    "dsr.memoria_dosimetria_progressao.v1": (
        "a memoria de dosimetria nao tem eixo de competencia e suas grandezas sao dias INTEIROS "
        "e uma fracao TEXTUAL ('2/5'); projeta-la exigiria um segundo tipo de valor e uma "
        "politica de fracao que este comparador nao tem. Fica recusada por declaracao, nunca "
        "comparada em silencio"),
}


class ComparacaoError(RuntimeError):
    def __init__(self, code, errors):
        self.code = code
        self.errors = [errors] if isinstance(errors, str) else list(errors)
        super().__init__("; ".join(self.errors))



def _rejeita_constante(valor):
    raise ValueError("constante JSON invalida: %s" % valor)


def _decimal(valor, onde):
    """Todo valor monetario entra como STRING decimal canonica e vira Decimal. Nunca float."""
    if not isinstance(valor, str) or not NUMERO_RX.fullmatch(valor):
        raise ComparacaoError("valor_invalido",
                              "%s: valor deve ser decimal canonico em string" % onde)
    try:
        resultado = Decimal(valor)
    except InvalidOperation as erro:
        raise ComparacaoError("valor_invalido", "%s: decimal ilegivel" % onde) from erro




    if not resultado.is_finite():
        raise ComparacaoError("valor_invalido", "%s: decimal nao finito" % onde)
    return resultado


def _fmt(valor):
    """Forma canonica sem zeros a direita - MESMA convencao do `_fmt` dos quatro motores."""
    texto = format(valor, "f")
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return "0" if texto in ("", "-0") else texto


def _sha256_json(valor):
    bruto = json.dumps(valor, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(bruto).hexdigest()



def _caminho_schema(nome):
    candidato = os.path.join(AQUI, nome)
    return candidato if os.path.isfile(candidato) else None


def _carregar_schema(nome):
    caminho = _caminho_schema(nome)
    if caminho is None:
        raise ComparacaoError("schema_indisponivel",
                              "contrato %s nao encontrado ao lado do comparador" % nome)
    try:
        with open(caminho, encoding="utf-8") as arquivo:
            return json.load(arquivo)
    except (OSError, ValueError) as erro:
        raise ComparacaoError("schema_indisponivel",
                              "contrato %s ilegivel: %s" % (nome, erro)) from erro


def _texto(valor, onde):
    if not isinstance(valor, str):
        raise ComparacaoError("memoria_invalida", "%s: esperado texto" % onde)
    return valor


def _mapa(valor, onde):
    if not isinstance(valor, dict):
        raise ComparacaoError("memoria_invalida", "%s: esperado objeto" % onde)
    return valor


def _lista(valor, onde):
    if not isinstance(valor, list):
        raise ComparacaoError("memoria_invalida", "%s: esperada lista" % onde)
    return valor


def _competencia(valor, onde):
    texto = _texto(valor, onde)
    if not COMPETENCIA_RX.fullmatch(texto):
        raise ComparacaoError("competencia_invalida",
                              "%s: competencia deve ser data ISO YYYY-MM-DD; nao ha "
                              "normalizacao de formato" % onde)
    return texto


def _poe(destino, rubrica_id, grandeza, valor, onde):
    if not ID_RX.fullmatch(rubrica_id):
        raise ComparacaoError("rubrica_invalida", "%s: rubrica_id fora do formato" % onde)
    if rubrica_id in destino:
        raise ComparacaoError("rubrica_duplicada",
                              "%s: rubrica %s aparece duas vezes na mesma memoria; casamento "
                              "por identificador exige identificador unico" % (onde, rubrica_id))
    _decimal(valor, "%s.%s" % (onde, rubrica_id))
    destino[rubrica_id] = (grandeza, valor)














MOTIVO_PROCEDENCIA = ("bloco de procedencia: fora de `id` e `sha256`, o que ha ali e criterio "
                      "juridico e endereco de fonte, nao grandeza comparavel; o conteudo inteiro "
                      "entra no pin `memoria_sha256` de cada origem e a divergencia dele vira "
                      "aviso, nunca rubrica")
MOTIVO_RECORTE = ("delimita o calculo mas nao e grandeza comparavel: e data, nao numero de "
                  "rubrica; divergencia dele sai como aviso de recorte, nunca como divergencia "
                  "aritmetica")
MOTIVO_SEGMENTO_METADADO = ("metadado do segmento (ordem, serie, operador, politica de fronteira "
                            "e de fracao, base legal, endereco e hash do snapshot): e a "
                            "declaracao do regime, nao numero do calculo; comparar isso seria "
                            "comparar a regra juridica, que este modulo nao faz")

HE_MES_COMPONENTES = ("he_50", "he_100", "night", "interval", "dsr")
HE_COMPONENTES_PROJETADOS = HE_MES_COMPONENTES + ("reflexes",)
HE_COMPONENTES_NAO_PROJETADOS = {}



HE_MES_CRITERIOS = ("natureza_do_intervalo",)
HE_MES_PROJETADOS = ("competencia", "hourly_rate", "components", "month_total") + HE_MES_CRITERIOS
HE_MES_NAO_PROJETADOS = {
    "decision_rule": ("a regra mensal da decisao coletiva (divisor, adicionais, regra noturna, "
                      "cadeia de reflexos) e criterio juridico, nao grandeza; o comparador nao "
                      "confere regra contra regra - isso e o auditor, que nao existe aqui"),
    "dsr_compensado_pela_decisao": ("repete a regra de DSR da decisao (decision_rule.dsr_rule."
                                    "enabled, negada) que o motor grava no mesmo mes; e criterio "
                                    "da decisao, nao grandeza, e o efeito dele aparece na "
                                    "rubrica componente:dsr"),
}

SL_MES_RUBRICAS = ("salario_remuneratorio", "verbas_indenizatorias",
                   "outros_salarios_contribuicao_mes", "outros_descontos_inss_mes",
                   "base_calculo_inss_agregada", "desconto_inss_deste_vinculo",
                   "salario_liquido_apos_inss")
SL_MES_PROJETADOS = ("competencia",) + SL_MES_RUBRICAS
SL_MES_NAO_PROJETADOS = {
    "decomposicao_faixas_agregada": ("e a decomposicao por faixa da tabela externa, e comparar "
                                     "faixa a faixa exigiria casar faixas de tabelas que podem "
                                     "ser de vigencias diferentes"),
}
SL_RESUMO_RUBRICAS = ("total_remuneratorio", "total_indenizatorio", "total_base_inss",
                      "total_desconto_inss", "total_liquido_apos_inss")
SL_RESUMO_NAO_PROJETADOS = {}

AT_PERIODO_PROJETADOS = ("period", "value", "factor")
AT_PERIODO_NAO_PROJETADOS = {}
AT_SEGMENTO_PROJETADOS = ("id", "factor_segment", "periods")
AT_SEGMENTO_NAO_PROJETADOS = {nome: MOTIVO_SEGMENTO_METADADO for nome in
                              ("order", "series_id", "operator", "boundary_policy",
                               "fractional_period_policy", "legal_basis", "snapshot_sha256",
                               "source_url", "source_response_sha256")}


def _fechado(mapa, projetados, nao_projetados, onde):
    """Recusa campo que nao esta declarado nem como projetado nem como nao projetado."""
    desconhecidos = sorted(set(mapa) - set(projetados) - set(nao_projetados))
    if desconhecidos:
        raise ComparacaoError(
            "campo_desconhecido",
            "%s: campo(s) %s nao consta(m) do conjunto declarado deste objeto; campo que o "
            "comparador nao sabe projetar e RECUSADO, nunca descartado em silencio - descartar "
            "esconderia divergencia" % (onde, desconhecidos))
    return mapa


def _declarar(prefixo, nao_projetados):
    return [{"onde": prefixo + campo, "motivo": motivo}
            for campo, motivo in sorted(nao_projetados.items())]


def _projetar_horas_extras(memoria):
    competencias = {}
    criterios = {}
    for indice, mes in enumerate(_lista(memoria.get("months"), "months")):
        mapa = _mapa(mes, "months[%d]" % indice)
        _fechado(mapa, HE_MES_PROJETADOS, HE_MES_NAO_PROJETADOS, "months[%d]" % indice)
        chave = _competencia(mapa.get("competencia"), "months[%d].competencia" % indice)
        if chave in competencias:
            raise ComparacaoError("competencia_duplicada",
                                  "competencia %s aparece duas vezes na mesma memoria" % chave)
        onde = "months[%s]" % chave
        rubricas = {}
        _poe(rubricas, "valor_hora", VALOR_POR_HORA, mapa.get("hourly_rate"), onde)
        componentes = _mapa(mapa.get("components"), onde + ".components")
        _fechado(componentes, HE_COMPONENTES_PROJETADOS, HE_COMPONENTES_NAO_PROJETADOS,
                 onde + ".components")
        for nome in HE_MES_COMPONENTES:
            _poe(rubricas, "componente:" + nome, MONETARIO, componentes.get(nome), onde)
        reflexos = _mapa(componentes.get("reflexes"), onde + ".components.reflexes")
        for nome in sorted(reflexos):
            _poe(rubricas, "reflexo:" + str(nome), MONETARIO, reflexos.get(nome), onde)
        _poe(rubricas, "total_do_mes", MONETARIO, mapa.get("month_total"), onde)
        competencias[chave] = rubricas
        criterios[chave] = {campo: mapa.get(campo) for campo in HE_MES_CRITERIOS}
    totais = {}
    _poe(totais, "principal", MONETARIO, memoria.get("principal"), "totais")
    _poe(totais, "total_horas_extras_e_reflexos", MONETARIO,
         memoria.get("conditional_overtime_and_reflexes"), "totais")
    _poe(totais, "total_com_principal", MONETARIO,
         memoria.get("conditional_total_with_principal"), "totais")
    decisao = _mapa(memoria.get("decision"), "decision")
    vinculo = {"tipo": "decision",
               "id": _texto(decisao.get("decision_id"), "decision.decision_id"),
               "sha256": _texto(decisao.get("decision_sha256"), "decision.decision_sha256")}
    return {"moeda_no_contrato": None, "competencias": competencias, "totais": totais,
            "vinculo_externo": vinculo, "criterios": criterios}


def _projetar_salario_liquido(memoria):
    competencias = {}
    for indice, mes in enumerate(_lista(memoria.get("months"), "months")):
        mapa = _mapa(mes, "months[%d]" % indice)
        _fechado(mapa, SL_MES_PROJETADOS, SL_MES_NAO_PROJETADOS, "months[%d]" % indice)
        chave = _competencia(mapa.get("competencia"), "months[%d].competencia" % indice)
        if chave in competencias:
            raise ComparacaoError("competencia_duplicada",
                                  "competencia %s aparece duas vezes na mesma memoria" % chave)
        onde = "months[%s]" % chave
        rubricas = {}
        for nome in SL_MES_RUBRICAS:
            _poe(rubricas, nome, MONETARIO, mapa.get(nome), onde)
        competencias[chave] = rubricas
    resumo = _mapa(memoria.get("resumo"), "resumo")
    _fechado(resumo, SL_RESUMO_RUBRICAS, SL_RESUMO_NAO_PROJETADOS, "resumo")
    totais = {}
    for nome in SL_RESUMO_RUBRICAS:
        _poe(totais, nome, MONETARIO, resumo.get(nome), "resumo")
    tabela = _mapa(memoria.get("tabela"), "tabela")
    vinculo = {"tipo": "tabela",
               "id": _texto(tabela.get("table_id"), "tabela.table_id"),
               "sha256": _texto(tabela.get("table_sha256"), "tabela.table_sha256")}
    return {"moeda_no_contrato": None, "competencias": competencias, "totais": totais,
            "vinculo_externo": vinculo}


def _projetar_atualizacao(memoria):



    competencias = {}
    totais = {}
    vistos = set()
    for indice, segmento in enumerate(_lista(memoria.get("segments"), "segments")):
        mapa = _mapa(segmento, "segments[%d]" % indice)
        _fechado(mapa, AT_SEGMENTO_PROJETADOS, AT_SEGMENTO_NAO_PROJETADOS,
                 "segments[%d]" % indice)
        segmento_id = _texto(mapa.get("id"), "segments[%d].id" % indice)
        if segmento_id in vistos:
            raise ComparacaoError("segmento_duplicado",
                                  "segmento %s aparece duas vezes na mesma memoria" % segmento_id)
        vistos.add(segmento_id)
        _poe(totais, "fator_do_segmento:" + segmento_id, FATOR,
             mapa.get("factor_segment"), "segments[%s]" % segmento_id)
        for posicao, ponto in enumerate(_lista(mapa.get("periods"),
                                               "segments[%s].periods" % segmento_id)):
            item = _mapa(ponto, "segments[%s].periods[%d]" % (segmento_id, posicao))
            _fechado(item, AT_PERIODO_PROJETADOS, AT_PERIODO_NAO_PROJETADOS,
                     "segments[%s].periods[%d]" % (segmento_id, posicao))
            chave = _competencia(item.get("period"),
                                 "segments[%s].periods[%d].period" % (segmento_id, posicao))
            onde = "segments[%s].periods[%s]" % (segmento_id, chave)
            rubricas = competencias.setdefault(chave, {})
            _poe(rubricas, "fator_do_periodo:" + segmento_id, FATOR, item.get("factor"), onde)
            _poe(rubricas, "taxa_do_periodo:" + segmento_id, TAXA_PERCENTUAL,
                 item.get("value"), onde)
    _poe(totais, "principal", MONETARIO, memoria.get("principal"), "totais")
    _poe(totais, "valor_atualizado_condicional", MONETARIO,
         memoria.get("conditional_updated_value"), "totais")
    _poe(totais, "diferenca_condicional", MONETARIO,
         memoria.get("conditional_difference"), "totais")
    _poe(totais, "fator_total", FATOR, memoria.get("factor_total"), "totais")
    regime = _mapa(memoria.get("regime"), "regime")
    vinculo = {"tipo": "regime",
               "id": _texto(regime.get("regime_id"), "regime.regime_id"),
               "sha256": _texto(regime.get("regime_sha256"), "regime.regime_sha256")}
    return {"moeda_no_contrato": _texto(memoria.get("currency"), "currency"),
            "competencias": competencias, "totais": totais, "vinculo_externo": vinculo}


PROJECOES = {
    "dsr.memoria_horas_extras.v1": ("memoria_horas_extras.schema.json", _projetar_horas_extras),
    "dsr.memoria_salario_liquido_inss.v1": ("memoria_salario_liquido_inss.schema.json",
                                            _projetar_salario_liquido),
    "dsr.memoria_atualizacao.v1": ("memoria_atualizacao.schema.json", _projetar_atualizacao),
}
CONTRATOS_SUPORTADOS = tuple(sorted(PROJECOES))



CAMPOS_NAO_PROJETADOS = {
    "dsr.memoria_horas_extras.v1": (_declarar("months[].", HE_MES_NAO_PROJETADOS)
                                    + _declarar("months[].components.",
                                                HE_COMPONENTES_NAO_PROJETADOS)
                                    + [{"onde": "decision", "motivo": MOTIVO_PROCEDENCIA}]),
    "dsr.memoria_salario_liquido_inss.v1": (_declarar("months[].", SL_MES_NAO_PROJETADOS)
                                            + _declarar("resumo.", SL_RESUMO_NAO_PROJETADOS)
                                            + [{"onde": "tabela",
                                                "motivo": MOTIVO_PROCEDENCIA}]),
    "dsr.memoria_atualizacao.v1": (_declarar("segments[].", AT_SEGMENTO_NAO_PROJETADOS)
                                   + _declarar("segments[].periods[].",
                                               AT_PERIODO_NAO_PROJETADOS)
                                   + [{"onde": "regime", "motivo": MOTIVO_PROCEDENCIA},
                                      {"onde": "rounding",
                                       "motivo": ("o arredondamento de cada memoria e declaracao "
                                                  "do regime de origem; a saida declara o "
                                                  "arredondamento DO COMPARADOR, que e outro e "
                                                  "nao se confunde com o dos motores")},
                                      {"onde": "data_base", "motivo": MOTIVO_RECORTE},
                                      {"onde": "calculation_date", "motivo": MOTIVO_RECORTE}]),
}





CAMPOS_DE_RECORTE = {
    "dsr.memoria_atualizacao.v1": ("data_base", "calculation_date"),
}



def comparar_rubrica(valores, *, escala_percentual=ESCALA_PERCENTUAL_PADRAO,
                     limiar_materialidade_pct=LIMIAR_MATERIALIDADE_PCT_PADRAO):
    'Divergencia de uma rubrica contra a PRIMEIRA origem da lista.'








    if not isinstance(valores, (list, tuple)) or len(valores) < 2:
        raise ComparacaoError("comparacao_invalida", "sao necessarias ao menos duas origens")
    escala = _escala_valida(escala_percentual)
    limiar = _limiar_valido(limiar_materialidade_pct)
    with localcontext() as contexto:
        contexto.prec = PRECISAO_INTERMEDIARIA
        base_id, base_txt = valores[0]
        base = _decimal(base_txt, "referencia %s" % base_id)
        saida = []
        for origem_id, texto in valores[1:]:
            valor = _decimal(texto, "origem %s" % origem_id)
            diferenca = valor - base
            if base == 0:
                percentual = None
                motivo = "base_zero: percentual indefinido porque a origem de referencia vale 0"
            else:






                bruto = (diferenca / abs(base)) * Decimal(100)
                quantum = Decimal(1).scaleb(-escala)
                percentual = format(bruto.quantize(quantum, rounding=ROUND_HALF_EVEN),
                                    "." + str(escala) + "f")
                motivo = None
            acima = None
            if limiar is not None and percentual is not None:






                acima = abs(Decimal(percentual)) > limiar
            saida.append({"origem_id": origem_id,
                          "diferenca_absoluta": _fmt(diferenca),
                          "percentual": percentual,
                          "percentual_indefinido_porque": motivo,
                          "acima_do_limiar": acima})
    return saida


def _escala_valida(valor):
    if isinstance(valor, bool) or not isinstance(valor, int) or not 0 <= valor <= 28:
        raise ComparacaoError("parametro_invalido",
                              "escala_percentual deve ser inteiro entre 0 e 28")
    return valor


def _limiar_valido(valor):
    if valor is None:
        return None
    if isinstance(valor, bool) or not isinstance(valor, str) or not NUMERO_RX.fullmatch(valor):
        raise ComparacaoError("parametro_invalido",
                              "limiar_materialidade_pct deve ser None ou decimal em string")
    limiar = Decimal(valor)
    if limiar < 0:
        raise ComparacaoError("parametro_invalido",
                              "limiar_materialidade_pct nao pode ser negativo")
    return limiar



def validar_pedido(pedido):
    """Erros de FORMA do pedido. Lista vazia = forma aceita (o conteudo e conferido depois)."""
    erros = []
    if not isinstance(pedido, dict):
        return ["pedido deve ser objeto"]
    permitidos = {"schema_version", "memorias", "ausencias_declaradas"}
    for campo in pedido:
        if campo not in permitidos:
            erros.append("pedido contem campo nao permitido: %s" % campo)
    if pedido.get("schema_version") != PEDIDO_VERSION:
        erros.append("schema_version do pedido deve ser %s" % PEDIDO_VERSION)
    memorias = pedido.get("memorias")
    if not isinstance(memorias, list):
        erros.append("memorias deve ser lista")
        return erros
    if not MIN_MEMORIAS <= len(memorias) <= MAX_MEMORIAS:
        erros.append("sao aceitas %d ou %d memorias; vieram %d"
                     % (MIN_MEMORIAS, MAX_MEMORIAS, len(memorias)))
    vistos = set()
    for indice, item in enumerate(memorias):
        prefixo = "memorias[%d]" % indice
        if not isinstance(item, dict):
            erros.append("%s deve ser objeto" % prefixo)
            continue
        permitidos_item = {"origem_id", "rotulo", "moeda_declarada", "memoria"}
        for campo in item:
            if campo not in permitidos_item:
                erros.append("%s contem campo nao permitido: %s" % (prefixo, campo))
        origem_id = item.get("origem_id")
        if not isinstance(origem_id, str) or not ID_RX.fullmatch(origem_id):
            erros.append("%s.origem_id fora do formato" % prefixo)
        elif origem_id in vistos:
            erros.append("%s.origem_id duplicado: %s" % (prefixo, origem_id))
        else:
            vistos.add(origem_id)
        if not isinstance(item.get("memoria"), dict):
            erros.append("%s.memoria deve ser objeto" % prefixo)
        moeda = item.get("moeda_declarada")
        if moeda is not None and (not isinstance(moeda, str) or not moeda.strip()):
            erros.append("%s.moeda_declarada deve ser texto ou ausente" % prefixo)
        rotulo = item.get("rotulo")
        if rotulo is not None and not isinstance(rotulo, str):
            erros.append("%s.rotulo deve ser texto ou ausente" % prefixo)
    ausencias = pedido.get("ausencias_declaradas", [])
    if not isinstance(ausencias, list):
        erros.append("ausencias_declaradas deve ser lista")
        return erros
    for indice, item in enumerate(ausencias):
        prefixo = "ausencias_declaradas[%d]" % indice
        if not isinstance(item, dict):
            erros.append("%s deve ser objeto" % prefixo)
            continue
        permitidos_item = {"origem_id", "competencia", "rubrica_id", "motivo"}
        for campo in item:
            if campo not in permitidos_item:
                erros.append("%s contem campo nao permitido: %s" % (prefixo, campo))
        if item.get("origem_id") not in vistos:
            erros.append("%s.origem_id nao corresponde a nenhuma memoria" % prefixo)
        competencia = item.get("competencia")
        if competencia is not None and (not isinstance(competencia, str)
                                        or not COMPETENCIA_RX.fullmatch(competencia)):
            erros.append("%s.competencia deve ser data ISO ou null" % prefixo)
        rubrica = item.get("rubrica_id")
        if rubrica is not None and (not isinstance(rubrica, str) or not ID_RX.fullmatch(rubrica)):
            erros.append("%s.rubrica_id deve ser identificador ou null" % prefixo)
        if competencia is None and rubrica is None:
            erros.append("%s: declaracao vazia nao declara nada" % prefixo)
        motivo = item.get("motivo")
        if not isinstance(motivo, str) or len(motivo.strip()) < 3:
            erros.append("%s.motivo obrigatorio - ausencia sem razao declarada nao e "
                         "declaracao" % prefixo)
    return erros



def comparar(pedido, *, experimental_authorized=False, escopo="tudo",
             escala_percentual=ESCALA_PERCENTUAL_PADRAO,
             limiar_materialidade_pct=LIMIAR_MATERIALIDADE_PCT_PADRAO,
             validar_schema_fn=None):
    'Compara duas ou tres memorias e devolve a minuta de comparacao.'






    if experimental_authorized is not True:
        raise ComparacaoError("capacidade_desabilitada",
                              "comparador experimental exige autorizacao explicita nesta "
                              "execucao (experimental_authorized=True)")
    if escopo not in ESCOPOS:
        raise ComparacaoError("parametro_invalido", "escopo deve ser um de %s" % (ESCOPOS,))
    escala = _escala_valida(escala_percentual)
    limiar = _limiar_valido(limiar_materialidade_pct)
    validador = validar_schema_fn if validar_schema_fn is not None else validar_schema
    if validador is None:
        raise ComparacaoError("validador_indisponivel", INDISPONIVEL_SCHEMA)

    erros = validar_pedido(pedido)
    if erros:
        raise ComparacaoError("pedido_invalido", erros)

    contratos = set()
    origens = []
    projetadas = []
    recortes = []
    for item in pedido["memorias"]:
        memoria = item["memoria"]
        contrato = memoria.get("schema_version")
        if contrato in CONTRATOS_SEM_PROJECAO:
            raise ComparacaoError("contrato_sem_projecao_declarada",
                                  "%s: %s" % (contrato, CONTRATOS_SEM_PROJECAO[contrato]))
        if contrato not in PROJECOES:
            raise ComparacaoError("contrato_nao_suportado",
                                  "%r nao esta entre os contratos projetaveis %s"
                                  % (contrato, list(CONTRATOS_SUPORTADOS)))
        contratos.add(contrato)
        if len(contratos) > 1:
            raise ComparacaoError("contrato_divergente",
                                  "as memorias sao de contratos diferentes (%s); rubrica de "
                                  "contratos diferentes nao casa por identificador"
                                  % sorted(contratos))
        if memoria.get("status") != STATUS:
            raise ComparacaoError("status_invalido",
                                  "%s: memoria sem status %s" % (item["origem_id"], STATUS))
        nome_schema, projetar = PROJECOES[contrato]
        falhas = validador(memoria, _carregar_schema(nome_schema))
        if falhas:
            raise ComparacaoError("memoria_fora_do_contrato",
                                  ["%s: %s" % (item["origem_id"], f) for f in falhas[:10]])
        projecao = projetar(memoria)
        projecao["origem_id"] = item["origem_id"]
        projecao["moeda_declarada"] = item.get("moeda_declarada")
        projetadas.append(projecao)
        recortes.append({campo: memoria.get(campo)
                         for campo in CAMPOS_DE_RECORTE.get(contrato, ())})
        origens.append({"origem_id": item["origem_id"],
                        "rotulo": item.get("rotulo"),
                        "ordem": len(origens),
                        "engine_version": memoria.get("engine_version"),
                        "memoria_sha256": _sha256_json(memoria),
                        "vinculo_externo": projecao["vinculo_externo"]})

    contrato = contratos.pop()
    moeda = _resolver_moeda(projetadas, escopo)
    ausencias_pedidas = list(pedido.get("ausencias_declaradas", []))
    consumidas = set()

    competencias = []
    if escopo == "tudo":
        competencias = _montar_competencias(projetadas, ausencias_pedidas, consumidas,
                                            escala, limiar)
    totais = _montar_rubricas(
        [(p["origem_id"], p["totais"]) for p in projetadas], None,
        ausencias_pedidas, consumidas, escala, limiar)

    orfas = [a for indice, a in enumerate(ausencias_pedidas) if indice not in consumidas]
    if orfas:
        raise ComparacaoError(
            "declaracao_sem_ausencia",
            ["declaracao de ausencia que nao corresponde a ausencia alguma: %s"
             % json.dumps(a, ensure_ascii=False, sort_keys=True) for a in orfas[:5]])

    avisos = (_avisos(origens, escopo) + _avisos_de_recorte(recortes)
              + _avisos_de_criterio(projetadas))
    return {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS,
        "comparador_version": COMPARADOR_VERSION,
        "contrato_comparado": contrato,
        "moeda": moeda,
        "escopo": escopo,
        "criterio_casamento": "identificador_declarado",
        "referencia": origens[0]["origem_id"],
        "origens": origens,
        "arredondamento": {
            "diferenca_absoluta": "exata_sem_arredondamento",
            "percentual_modo": MODO_PERCENTUAL,
            "percentual_escala": escala,
            "aplicado_uma_vez_no_fim": True,
        },
        "limiar_materialidade_pct": (None if limiar_materialidade_pct is None
                                     else str(limiar_materialidade_pct)),
        "competencias": competencias,
        "totais": totais,
        "campos_nao_projetados": CAMPOS_NAO_PROJETADOS.get(contrato, []),
        "ausencias_declaradas": _relatar_ausencias(ausencias_pedidas),
        "avisos": avisos,
        "warnings": [
            "MINUTA_PARA_REVISAO: comparacao para conferencia do advogado.",
            "O comparador APONTA a divergencia; nao afirma qual memoria esta correta - isso e "
            "juizo do advogado, e a conferencia contra criterio juridico e o auditor, que nao "
            "existe neste modulo.",
            "A origem de referencia e apenas o denominador do percentual; a ordem foi declarada "
            "por quem chamou e nao exprime acerto.",
            "Rubrica casa somente por identificador declarado no contrato de origem; nao ha "
            "casamento por semelhanca de nome.",
            "Competencia casa por igualdade exata da data ISO; nao ha normalizacao de formato, "
            "interpolacao nem conversao de periodicidade.",
            "Ausencia declarada NAO e zero: a rubrica ou a competencia ausente e EXCLUIDA da "
            "comparacao, nunca tratada como valor nulo.",
            "Campo que o comparador nao sabe projetar e RECUSADO, nunca descartado em silencio; "
            "o que ficou fora da comparacao por decisao declarada esta em "
            "`campos_nao_projetados`, com o motivo de cada um.",
        ],
    }


def _avisos_de_criterio(projetadas):
    'Criterio declarado por competencia (a natureza do intervalo) nao e grandeza e nao vira'

    avisos = []
    pares = sorted({(competencia, campo) for p in projetadas
                    for competencia, criterio in (p.get("criterios") or {}).items()
                    for campo in criterio})
    for competencia, campo in pares:
        valores = sorted({json.dumps((p.get("criterios") or {}).get(competencia, {}).get(campo),
                                     ensure_ascii=False, sort_keys=True)
                          for p in projetadas})
        if len(valores) > 1:
            avisos.append("o criterio declarado difere entre as memorias em months[%s].%s: %s; "
                          "parte da divergencia dessa competencia pode vir dele, nao da "
                          "aritmetica" % (competencia, campo, valores))
    return avisos


def _avisos_de_recorte(recortes):
    """Divergencia em campo de recorte (data-base, data de calculo) nao e rubrica, e aviso."""
    avisos = []
    for campo in sorted({campo for recorte in recortes for campo in recorte}):
        valores = sorted({json.dumps(recorte.get(campo), ensure_ascii=False, sort_keys=True)
                          for recorte in recortes})
        if len(valores) > 1:
            avisos.append("o recorte declarado difere entre as memorias em %s: %s; parte da "
                          "divergencia pode vir do recorte, nao da aritmetica"
                          % (campo, valores))
    return avisos


def _resolver_moeda(projetadas, escopo):
    """Moeda unica ou recusa. Contrato que nao declara moeda exige declaracao de quem chama."""
    precisa = False
    for projecao in projetadas:
        grades = [projecao["totais"]]
        if escopo == "tudo":
            grades.extend(projecao["competencias"].values())
        for grade in grades:
            if any(grandeza in GRANDEZAS_COM_MOEDA for grandeza, _ in grade.values()):
                precisa = True
    resolvidas = set()
    for projecao in projetadas:
        no_contrato = projecao["moeda_no_contrato"]
        declarada = projecao["moeda_declarada"]
        if no_contrato and declarada and no_contrato != declarada:
            raise ComparacaoError(
                "moeda_divergente",
                "%s: moeda declarada %r conflita com a do contrato %r"
                % (projecao["origem_id"], declarada, no_contrato))
        efetiva = no_contrato or declarada
        if efetiva is None:
            if precisa:
                raise ComparacaoError(
                    "moeda_indeclarada",
                    "%s: o contrato nao declara moeda e o pedido nao declarou "
                    "`moeda_declarada`; o comparador nao adivinha a unidade monetaria"
                    % projecao["origem_id"])
            continue
        resolvidas.add(efetiva)
    if len(resolvidas) > 1:
        raise ComparacaoError("moeda_divergente",
                              "memorias em moedas distintas: %s" % sorted(resolvidas))
    return resolvidas.pop() if resolvidas else None


def _casa(ausencia, origem_id, competencia, rubrica_id):
    return (ausencia.get("origem_id") == origem_id
            and ausencia.get("competencia") == competencia
            and ausencia.get("rubrica_id") == rubrica_id)


def _montar_competencias(projetadas, ausencias, consumidas, escala, limiar):
    todas = set()
    for projecao in projetadas:
        todas.update(projecao["competencias"])
    saida = []
    for competencia in sorted(todas):
        faltantes = [p["origem_id"] for p in projetadas if competencia not in p["competencias"]]
        if faltantes:


            for origem_id in faltantes:
                indices = [i for i, a in enumerate(ausencias)
                           if _casa(a, origem_id, competencia, None)]
                if not indices:
                    raise ComparacaoError(
                        "competencia_orfa",
                        "competencia %s ausente em %s e nao declarada; competencia que nao "
                        "casa nao e comparada" % (competencia, origem_id))
                consumidas.update(indices)
            continue
        rubricas = _montar_rubricas(
            [(p["origem_id"], p["competencias"][competencia]) for p in projetadas],
            competencia, ausencias, consumidas, escala, limiar)
        saida.append({"competencia": competencia, "rubricas": rubricas})
    return saida


def _montar_rubricas(grades, competencia, ausencias, consumidas, escala, limiar):
    todas = set()
    for _, grade in grades:
        todas.update(grade)
    saida = []
    for rubrica_id in sorted(todas):
        faltantes = [origem_id for origem_id, grade in grades if rubrica_id not in grade]
        if faltantes:
            for origem_id in faltantes:
                indices = [i for i, a in enumerate(ausencias)
                           if _casa(a, origem_id, competencia, rubrica_id)]
                if not indices:
                    raise ComparacaoError(
                        "rubrica_orfa",
                        "rubrica %s ausente em %s%s e nao declarada; rubrica que nao casa nao "
                        "e comparada e nao vale zero"
                        % (rubrica_id, origem_id,
                           " na competencia " + competencia if competencia else " nos totais"))
                consumidas.update(indices)
            continue
        grandezas = {grade[rubrica_id][0] for _, grade in grades}
        if len(grandezas) > 1:
            raise ComparacaoError("grandeza_divergente",
                                  "rubrica %s aparece com grandezas distintas %s"
                                  % (rubrica_id, sorted(grandezas)))
        valores = [(origem_id, grade[rubrica_id][1]) for origem_id, grade in grades]
        saida.append({
            "rubrica_id": rubrica_id,
            "grandeza": grandezas.pop(),
            "valores": [{"origem_id": o, "valor": v} for o, v in valores],
            "divergencias": comparar_rubrica(valores, escala_percentual=escala,
                                             limiar_materialidade_pct=(None if limiar is None
                                                                       else str(limiar))),
        })
    return saida


def _relatar_ausencias(ausencias):
    return [{"origem_id": a.get("origem_id"),
             "competencia": a.get("competencia"),
             "rubrica_id": a.get("rubrica_id"),
             "motivo": a.get("motivo"),
             "efeito": "excluida_da_comparacao_nao_tratada_como_zero"}
            for a in ausencias]


def _avisos(origens, escopo):
    avisos = []
    if len({o["engine_version"] for o in origens}) > 1:
        avisos.append("as memorias vieram de versoes distintas do motor: %s"
                      % sorted({str(o["engine_version"]) for o in origens}))
    pinos = {json.dumps(o["vinculo_externo"], sort_keys=True) for o in origens}
    if len(pinos) > 1:
        avisos.append("as memorias nao repousam sobre a mesma decisao/tabela/regime externo; "
                      "parte da divergencia pode vir do insumo juridico, nao da aritmetica")
    if escopo == "totais":
        avisos.append("escopo 'totais': as rubricas por competencia nao foram comparadas")
    return avisos



def validar_saida(resultado, validar_schema_fn=None):
    validador = validar_schema_fn if validar_schema_fn is not None else validar_schema
    if validador is None:
        return [INDISPONIVEL_SCHEMA]
    return validador(resultado, _carregar_schema(SCHEMA_SAIDA))



def _e_link(caminho):
    'Costura nomeada para a defesa de link, para ela ser TESTAVEL: no Windows sem privilegio'


    return os.path.islink(caminho)


def _carregar_pedido(caminho):
    if not isinstance(caminho, str):
        raise ComparacaoError("arquivo_invalido", "caminho local obrigatorio")
    original = os.path.abspath(caminho)
    resolvido = os.path.realpath(original)
    if _e_link(original) or not os.path.isfile(resolvido):
        raise ComparacaoError("arquivo_invalido", "arquivo local ausente ou inseguro")
    try:
        with open(resolvido, "rb") as arquivo:
            valor = json.loads(arquivo.read().decode("utf-8"),
                               parse_constant=_rejeita_constante)
    except (OSError, UnicodeError, ValueError) as erro:
        raise ComparacaoError("arquivo_invalido", "pedido JSON ilegivel: %s" % erro) from erro
    if not isinstance(valor, dict):
        raise ComparacaoError("arquivo_invalido", "pedido deve ser objeto JSON")
    return valor


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ComparacaoError("argumentos_invalidos", message)


def main(argv=None):
    try:
        parser = _Parser(prog="comparar_calculos.py")
        parser.add_argument("--pedido", required=True)
        parser.add_argument("--escopo", default="tudo", choices=list(ESCOPOS))
        parser.add_argument("--escala-percentual", type=int, default=ESCALA_PERCENTUAL_PADRAO)
        parser.add_argument("--limiar-materialidade-pct", default=LIMIAR_MATERIALIDADE_PCT_PADRAO)
        args = parser.parse_args(argv)


        if os.environ.get(VAR_AMBIENTE, "").strip().lower() in ("0", "false", "nao", "não"):
            raise ComparacaoError("capacidade_desabilitada", "%s=0 desliga a comparacao" % VAR_AMBIENTE)
        pedido = _carregar_pedido(args.pedido)
        resultado = comparar(pedido, experimental_authorized=True, escopo=args.escopo,
                             escala_percentual=args.escala_percentual,
                             limiar_materialidade_pct=args.limiar_materialidade_pct)
        falhas = validar_saida(resultado)
        if falhas:
            raise ComparacaoError("saida_invalida", falhas[:10])
    except (ComparacaoError, OSError, TypeError, ValueError) as erro:
        print(json.dumps({"ok": False, "status": "INCONCLUSIVO",
                          "error_code": getattr(erro, "code", "falha"),
                          "errors": getattr(erro, "errors", [str(erro)])},
                         ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(resultado, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
