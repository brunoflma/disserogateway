#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""competencia.py — VERIFICADOR DE COMPETÊNCIA: Justiça Federal ou Estadual, e o JEF.

POR QUE EXISTE
--------------
Peça contra a Caixa, o INSS ou a União endereçada ao juiz de direito da comarca saía do rito
sem que nada notasse: o juízo era escolhido na prosa, e nenhum código lia a natureza jurídica
que a diligência cadastral traz. Este módulo lê o retorno CRU da consulta cadastral de cada
parte (ou a declaração do advogado), diz qual justiça é competente pelo art. 109, I, da CF, se
cabe o Juizado Especial Federal e o que ficou por confirmar. O LINT (L42) confere o
endereçamento da peça contra o COMPETENCIA.json que ele grava.

O QUE ELE NÃO FAZ
-----------------
Não escolhe vara nem subseção (o endereçamento sugerido é modelo com lacunas), não mede a
distância da comarca à sede da vara federal (quem diz isso é a lista do TRF) e não conclui
"federal" por um rótulo de cadastro que a fonte já errou: o Metrô de São Paulo veio rotulado
"União" na medição de 17/11/2026. Na dúvida, a parte vai para `a_confirmar`, que é pergunta
ao advogado, e a justiça sai "indeterminada".

ENTRADA (arquivo JSON do --pedido)
---------------------------------
  partes   lista de {polo: ativo|passivo|assistente|opoente, nome,
                     cadastro: retorno cru da rota pública da CNPJa (o envelope com
                               data.company ou o objeto do estabelecimento direto) — opcional,
                     ente_declarado: uniao|autarquia_federal|fundacao_publica_federal|
                               empresa_publica_federal|sociedade_economia_mista_federal|
                               conselho_profissional|oab|estado|municipio|privada — opcional;
                               a declaração do advogado prevalece sobre o cadastro}
  excecao  falencia|insolvencia_civil|acidente_trabalho|eleitoral|relacao_de_trabalho|
           competencia_delegada_previdenciaria|uniao_intervem (opcional, declarada)
  autor_tipo pessoa_fisica|microempresa|epp|outra; valor_causa e parcela_vincenda_mensal em
           reais, como texto: "97260.00" ou "97.260,00", até duas casas ("150.000" é ambíguo e
           é recusado). valor_causa é o da petição, que soma as vencidas e doze vincendas (CPC,
           art. 292, §§1º e 2º); doze parcelas acima dele tornam o JEF indeterminado.
           tipo_acao: uma chave fechada — nenhuma_exclusao (a ação não cai no art. 3º, §1º),
           mandado_seguranca, desapropriacao, divisao_demarcacao, acao_popular,
           execucao_fiscal, improbidade, coletiva, imovel_federal, anulacao_ato_federal,
           demissao_servidor_sancao_militar, estado_estrangeiro_organismo_internacional,
           tratado_internacional, direitos_indigenas — ou texto livre, que só leva o JEF a
           "nao" (exclusão reconhecida) ou a "indeterminado", nunca a "sim".
           data_referencia AAAA-MM-DD (padrão: hoje) para o salário mínimo — todos opcionais.

COMO CLASSIFICA CADA PARTE
--------------------------
  1104 Autarquia Federal, órgãos federais (1015, 1040, 1074, 1163) e a União (1341): federal.
  Fundação federal (1139, 1252): provável federal, a confirmar (a equiparação ao art. 109, I
  não foi conferida em fonte). Fundo federal (1287, 1317): a confirmar quem é parte (o fundo
  não tem personalidade).
  2011 Empresa Pública: federal só com esfera "União" (ou "União Federal") E nome que a
  confirme (FEDERAL, BRASIL, BRASILEIRA, NACIONAL, DA UNIÃO) sem o desmentir (DISTRITO FEDERAL,
  ESTADUAL, MUNICIPAL, METROPOLITANO, CAPITAL); "União" com outro nome, esfera ausente ou em
  formato não medido: a confirmar; esfera estadual ou municipal nos formatos medidos ("Rio
  Grande do Sul", "São Paulo - SP"): não federal. Esfera que não é texto: cadastro_ilegivel.
  2038 Sociedade de Economia Mista: nunca federal pela natureza (Súmulas 556 e 517 do STF, 42
  do STJ; Banco do Brasil, Súmula 508), só com a exceção uniao_intervem.
  Administração pública estadual e municipal (grupo 1): não federal; outro código do grupo 1, ou
  natureza de direito privado com esfera "União": a confirmar.
  OAB declarada: federal (Tema 258). Conselho profissional declarado: a confirmar. Declaração
  não federal contra cadastro federal certo: a confirmar (Súmula 150 do STJ).
  Parte sem cadastro nem declaração cujo nome é de ente federal (ou traz FEDERAL ou NACIONAL):
  a confirmar. Pessoa jurídica sem cadastro: não federal, com aviso de diligência não feita.
  Resto: não federal.

JEF: autor pessoa física, ME ou EPP e nenhum ente federal no polo ativo (art. 6º, I); réus
federais (art. 6º, II), e quem não é ente federal ao lado deles só em litisconsórcio
necessário (FONAJEF, Enunciado 21: a pergunta fica em aberto); a OAB ré fica em aberto.

SAÍDA (dsr.competencia.v1)
--------------------------
  justica federal|estadual|trabalho|eleitoral|indeterminada · delegada · jef sim|nao|
  indeterminado|nao_se_aplica e jef_motivo · entes_federais · a_confirmar (perguntas ao
  advogado) · fundamentos [{regra, fonte_url, conferido_em}] · enderecamento_sugerido (com
  lacunas; nunca inventa vara) · foro_uniao (art. 109, §2º, quando a União é ré) · avisos ·
  partes (nome, polo, esfera, origem, natureza) · salario_minimo (o usado no teto do JEF).

Uso: python competencia.py --pedido pedido.json [--gravar <pasta da peça>]
                           [--salario-minimo-tabela tabela.json]
  --pedido ARQ   o pedido acima. Imprime o resultado em JSON.
  --gravar PASTA grava COMPETENCIA.json (UTF-8, LF) na pasta da peça, onde o LINT o lê.
  --salario-minimo-tabela ARQ   lista [{valor, inicio, fim, norma, fonte_url}] que substitui a
                 tabela embutida (salário mínimo de 2026, Decreto 12.797/2025). Fora da vigência
                 da tabela o JEF sai "indeterminado" pedindo a atualização.
Erros nomeados (exit 2, JSON {erro, mensagem}): pedido_invalido, pedido_ilegivel,
cadastro_ilegivel, excecao_incompativel, tabela_invalida, gravacao_falhou.

Stdlib puro (espelhado em skills/*/scripts pelo MANIFESTO_SCRIPTS do sincronizar_shared.py)."""
from __future__ import annotations

import datetime
import json
import os
import re
import sys
import unicodedata
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

SCHEMA = "dsr.competencia.v1"
ARQUIVO = "COMPETENCIA.json"
CONFERIDO_EM = "17/11/2026"
JUSTICAS = ("federal", "estadual", "trabalho", "eleitoral", "indeterminada")
POLOS = ("ativo", "passivo", "assistente", "opoente")
ENTES = ("uniao", "autarquia_federal", "fundacao_publica_federal", "empresa_publica_federal",
         "sociedade_economia_mista_federal", "conselho_profissional", "oab", "estado",
         "municipio", "privada")
EXCECOES = ("falencia", "insolvencia_civil", "acidente_trabalho", "eleitoral", "relacao_de_trabalho",
            "competencia_delegada_previdenciaria", "uniao_intervem")
AUTOR_TIPOS = ("pessoa_fisica", "microempresa", "epp", "outra")

_CF = "https://www.planalto.gov.br/ccivil_03/constituicao/constituicao.htm"
_L5010 = "https://www.planalto.gov.br/ccivil_03/leis/l5010.htm"
_L10259 = "https://www.planalto.gov.br/ccivil_03/leis/leis_2001/l10259.htm"
_STF = "https://jurisprudencia.stf.jus.br/"
_STJ_REV = "https://www.stj.jus.br/docs_internet/revista/eletronica/"
_CONCLA = "https://concla.ibge.gov.br/estrutura/natjur-estrutura/natureza-juridica-2021"


FONTES = {
    "cf109_i": ("CF, art. 109, I: causas em que a União, entidade autárquica ou empresa pública "
                "federal forem autoras, rés, assistentes ou oponentes", _CF),
    "cf109_i_excecoes": ("CF, art. 109, I: exceto falência, acidentes de trabalho e as sujeitas à "
                         "Justiça Eleitoral e à Justiça do Trabalho", _CF),
    "cf109_p2": ("CF, art. 109, §2º: foro das causas contra a União", _CF),
    "cf109_p3": ("CF, art. 109, §3º: competência delegada à justiça estadual nas causas entre "
                 "instituição de previdência social e segurado, autorizada por lei", _CF),
    "cf109_p4": ("CF, art. 109, §4º: recurso sempre para o Tribunal Regional Federal", _CF),
    "cf114_i": ("CF, art. 114, I: ações oriundas da relação de trabalho, na Justiça do Trabalho",
                _CF),
    "l5010_15": ("Lei 5.010/1966, art. 15, III e §2º (Lei 13.876/2019): comarca a mais de 70 km "
                 "de município sede de vara federal, indicada pelo TRF", _L5010),
    "l10259_3": ("Lei 10.259/2001, art. 3º: JEF até sessenta salários mínimos", _L10259),
    "l10259_3_p1": ("Lei 10.259/2001, art. 3º, §1º: causas excluídas do JEF", _L10259),
    "l10259_3_p2": ("Lei 10.259/2001, art. 3º, §2º: doze parcelas vincendas não excedem o teto",
                    _L10259),
    "l10259_3_p3": ("Lei 10.259/2001, art. 3º, §3º: competência absoluta onde instalada a vara do "
                    "JEF", _L10259),
    "l10259_6": ("Lei 10.259/2001, art. 6º: partes no JEF", _L10259),
    "sum556": ("Súmula 556 do STF: Justiça comum nas causas de sociedade de economia mista", _STF),
    "sum517": ("Súmula 517 do STF: sociedade de economia mista só vai à Justiça Federal quando a "
               "União intervém como assistente ou opoente", _STF),
    "sum508": ("Súmula 508 do STF: Justiça Estadual nas causas do Banco do Brasil", _STF),
    "tema859": ("STF, Tema 859 da repercussão geral (RE 678.162): a insolvência civil está entre "
                "as exceções da parte final do art. 109, I; a ação é da Justiça Estadual",
                "https://noticias.stf.jus.br/postsnoticias/competencia-para-julgar-acoes-de-"
                "insolvencia-civil-e-da-justica-estadual/"),
    "sum501": ("Súmula 501 do STF: Justiça Estadual nas causas de acidente do trabalho, ainda que "
               "contra a União, autarquia ou empresa pública", _STF),
    "sum42": ("Súmula 42 do STJ: Justiça Comum Estadual nas causas cíveis de sociedade de "
              "economia mista", "https://scon.stj.jus.br/SCON/sumstj/toc.jsp?livre='42'.num."),
    "sum150": ("Súmula 150 do STJ: compete à Justiça Federal decidir sobre o interesse do ente "
               "federal", _STJ_REV + "stj-revista-sumulas-2010_10_capSumula150.pdf"),
    "sum66": ("Súmula 66 do STJ: execução fiscal de conselho profissional na Justiça Federal",
              _STJ_REV + "stj-revista-sumulas-2006_4_capSumula66.pdf"),
    "tema258": ("STF, RE 595.332, Tema 258 da repercussão geral: Justiça Federal nas ações em que "
                "a OAB figure", _STF),
    "sv22": ("Súmula Vinculante 22 do STF: Justiça do Trabalho na indenização por acidente de "
             "trabalho proposta pelo empregado contra o empregador",
             "https://jurisprudencia.stf.jus.br/pages/search?base=sumulas&queryString="
             "%22S%C3%BAmula%20Vinculante%2022%22"),
    "fonajef21": ("FONAJEF, Enunciado 21: pessoa que não é ente federal pode ser ré no JEF em "
                  "litisconsórcio necessário",
                  "https://www.cjf.jus.br/cjf/corregedoria-da-justica-federal/corregedoria-geral-"
                  "da-justica-federal/enunciados-fonajef/lista-completa-dos-enunciados-do-fonajef"
                  ".pdf"),
    "l5010_15_iii": ("Lei 5.010/1966, art. 15, III: causas entre instituição de previdência social "
                     "e segurado sobre benefícios de natureza pecuniária", _L5010),
    "concla": ("Tabela de natureza jurídica 2021 (CONCLA/IBGE)", _CONCLA),
    "decreto12797": ("Decreto 12.797/2025: salário mínimo de R$ 1.621,00 a partir de 1º/01/2026",
                     "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2025/decreto/D12797.htm"),
}


TABELA_SALARIO_MINIMO = (
    {"valor": "1621.00", "inicio": "2026-01-01", "fim": "2026-12-31",
     "norma": "Decreto 12.797/2025", "fonte_url": FONTES["decreto12797"][1],
     "conferido_em": CONFERIDO_EM},
)


NATUREZA_FEDERAL = {1015: "órgão público federal", 1040: "órgão público federal",
                    1074: "órgão público federal", 1163: "órgão público federal",
                    1104: "autarquia federal", 1341: "União"}
NATUREZA_FEDERAL_A_CONFIRMAR = {1139: "fundação pública federal", 1252: "fundação pública federal",
                                1287: "fundo público federal", 1317: "fundo público federal"}
NAT_EMPRESA_PUBLICA, NAT_ECONOMIA_MISTA = 2011, 2038
UNIAO_NATUREZAS = {1015, 1040, 1074, 1163, 1341}
NATUREZA_FUNDO = {1287, 1317}



NATUREZA_SUBNACIONAL = {1023, 1031, 1058, 1066, 1082, 1112, 1120, 1147, 1155, 1171, 1180, 1236,
                        1244, 1260, 1279, 1295, 1309, 1325, 1333}
_RX_NATUREZA_SUBNACIONAL = re.compile(r"\bESTADUAL\b|\bMUNICIPAL\b|\bMUNICIPIO\b|\bESTADO\b")

_RX_NOME_FEDERAL = re.compile(r"\b(?:FEDERAL|BRASIL|BRASILEIRA|NACIONAL|DA UNIAO)\b")


_RX_NOME_SUBNACIONAL = re.compile(r"\bDISTRITO\s+FEDERAL\b|\bESTADUAL\b|\bMUNICIPAL\b|\bMUNICIPIO\b"
                                  r"|\bDO\s+ESTADO\s+D[EOA]\b|\bMETROPOLITAN[OA]\b|\bCAPITAL\b"
                                  r"|\bPREFEITURA\b")
_UFS = {"ACRE": "AC", "ALAGOAS": "AL", "AMAPA": "AP", "AMAZONAS": "AM", "BAHIA": "BA",
        "CEARA": "CE", "DISTRITO FEDERAL": "DF", "ESPIRITO SANTO": "ES", "GOIAS": "GO",
        "MARANHAO": "MA", "MATO GROSSO": "MT", "MATO GROSSO DO SUL": "MS", "MINAS GERAIS": "MG",
        "PARA": "PA", "PARAIBA": "PB", "PARANA": "PR", "PERNAMBUCO": "PE", "PIAUI": "PI",
        "RIO DE JANEIRO": "RJ", "RIO GRANDE DO NORTE": "RN", "RIO GRANDE DO SUL": "RS",
        "RONDONIA": "RO", "RORAIMA": "RR", "SANTA CATARINA": "SC", "SAO PAULO": "SP",
        "SERGIPE": "SE", "TOCANTINS": "TO"}
_RX_ESFERA_MUNICIPAL = re.compile(r"^\S.* - (" + "|".join(sorted(set(_UFS.values()))) + r")$")






_SIGLAS_FEDERAIS = ("IBAMA", "INCRA", "DNIT", "ICMBIO", "CNEN", "FUNAI", "FUNASA", "INPI",
                    "INMETRO", "IPHAN", "FNDE", "DNOCS", "SUSEP", "IBGE", "CAPES", "CNPQ", "EMGEA",
                    "BNDES", "SERPRO", "DATAPREV", "EBSERH", "CONAB", "EMBRAPA", "FINEP", "ANATEL",
                    "ANVISA", "ANEEL", "ANAC", "ANTT", "ANTAQ", "ANCINE")
ENTES_NOMEADOS = (
    ("União", re.compile(r"\bUNIAO\s+FEDERAL\b|\bFAZENDA\s+NACIONAL\b|^UNIAO$"
                         r"|\b(?:FACE\s+DA|CONTRA\s+A|DESFAVOR\s+DA)\s+UNIAO(?=\s*[,;.)–—-]|\s*$)")),
    ("INSS", re.compile(r"\bINSTITUTO\s+NACIONAL\s+DO\s+SEGURO\s+SOCIAL\b|\bINSS\b")),
    ("Caixa Econômica Federal", re.compile(r"\bCAIXA\s+ECONOMICA\s+FEDERAL\b|\bCEF\b|\bC\.\s?E\.\s?F\.")),
    ("Correios", re.compile(r"\bEMPRESA\s+BRASILEIRA\s+DE\s+CORREIOS\b|\bECT\b|\bCORREIOS\b")),
    ("universidade federal", re.compile(r"\bUNIVERSIDADE\s+FEDERAL\b|\bINSTITUTO\s+FEDERAL\b")),
    ("Banco Central", re.compile(r"\bBANCO\s+CENTRAL\s+DO\s+BRASIL\b|\bBACEN\b")),
    ("agência reguladora federal", re.compile(r"\bAGENCIA\s+NACIONAL\s+D[EOA]S?\b")),
    ("autarquia federal", re.compile(r"\bAUTARQUIA\s+FEDERAL\b")),
    ("empresa pública federal", re.compile(r"\bEMPRESA\s+PUBLICA\s+FEDERAL\b")),
    ("fundação pública federal", re.compile(r"\bFUNDACAO\s+PUBLICA\s+FEDERAL\b")),
    ("conselho profissional", re.compile(r"\bCONSELHO\s+(?:FEDERAL|REGIONAL)\s+D[EOA]S?\b")),
    ("OAB", re.compile(r"\bORDEM\s+DOS\s+ADVOGADOS\s+DO\s+BRASIL\b")),
) + tuple((sg, re.compile(r"\b" + sg + r"\b")) for sg in _SIGLAS_FEDERAIS)


_RX_NEUTRALIZAR = (
    re.compile(r"\b(?:INSCRIT[OA]S?|INSCRICAO|REGISTRAD[OA]S?|REGISTRO)\s+(?:REGULARMENTE\s+)?"
               r"(?:N[AO]S?|PERANTE\s+[AO])\s+(?:ORDEM|CONSELHO)\b"),
    re.compile(r"\b(?:SEGURAD[OA]S?|APOSENTAD[OA]S?|BENEFICIARI[OA]S?|PENSIONISTAS?|FILIAD[OA]S?)"
               r"\s+(?:DO|PELO|JUNTO\s+AO)\s+(?:INSS|INSTITUTO\s+NACIONAL\s+DO\s+SEGURO\s+SOCIAL)\b"),
)


_RX_NOME_PARTE_SINAL = re.compile(r"\bFEDERA(?:L|IS)\b|\bNACIONAL\b|^CAIXA\b")
_RX_NOME_PJ = re.compile(r"\b(?:LTDA|EIRELI|ME|EPP|CIA|COMPANHIA|EMPRESA|BANCO|COOPERATIVA|"
                         r"ASSOCIACAO|FUNDACAO|INSTITUTO|CONDOMINIO|SOCIEDADE|UNIVERSIDADE|AGENCIA|"
                         r"CONSELHO|SINDICATO|MUNICIPIO|ESTADO|AUTARQUIA|SERVICO|DEPARTAMENTO|"
                         r"SECRETARIA|MINISTERIO)\b|\bS\s?/\s?A\b|\bS\.\s?A\b|\bS\.?A\.?$")




TIPO_SEM_EXCLUSAO = "nenhuma_exclusao"
EXCLUSOES_JEF = {
    "estado_estrangeiro_organismo_internacional": (
        "causa entre Estado estrangeiro ou organismo internacional e Município ou pessoa "
        "domiciliada ou residente no País (CF, art. 109, II)",
        r"estado\s+estrangeiro|organismo\s+internacional"),
    "tratado_internacional": ("causa fundada em tratado ou contrato da União com Estado "
                              "estrangeiro ou organismo internacional (CF, art. 109, III)",
                              r"tratado\s+internacional|fundad[ao]\s+em\s+tratado"),
    "direitos_indigenas": ("disputa sobre direitos indígenas (CF, art. 109, XI)", r"indigena"),
    "mandado_seguranca": ("mandado de segurança", r"mandado\s+de\s+seguranca"),
    "desapropriacao": ("desapropriação", r"desapropria"),
    "divisao_demarcacao": ("divisão e demarcação",
                           r"divisao\s+e\s+demarcacao|acao\s+divisoria|demarcatori|\bdemarcacao\b"),
    "acao_popular": ("ação popular", r"acao\s+popular"),
    "execucao_fiscal": ("execução fiscal", r"execucao\s+fiscal"),
    "improbidade": ("improbidade administrativa", r"improbidade"),
    "coletiva": ("direitos difusos, coletivos ou individuais homogêneos",
                 r"acao\s+coletiva|acao\s+civil\s+publica|(?:direitos|interesses)\s+"
                 r"(?:difusos|coletivos|individuais\s+homogeneos)"),
    "imovel_federal": ("bens imóveis da União, autarquias e fundações federais", r"$^"),
    "anulacao_ato_federal": ("anulação ou cancelamento de ato administrativo federal (salvo o "
                             "previdenciário e o de lançamento fiscal)", r"$^"),
    "demissao_servidor_sancao_militar": ("pena de demissão de servidor ou sanção a militar",
                                         r"$^"),
}

ENDERECO_FEDERAL = "AO JUÍZO FEDERAL DA ___ VARA FEDERAL DA SUBSEÇÃO JUDICIÁRIA DE ___"
ENDERECO_JEF = "AO JUIZADO ESPECIAL FEDERAL CÍVEL DA SUBSEÇÃO JUDICIÁRIA DE ___"
ENDERECO_ESTADUAL = "AO JUÍZO DE DIREITO DA ___ VARA ___ DA COMARCA DE ___"
ENDERECO_TRABALHO = "AO JUÍZO DA ___ VARA DO TRABALHO DE ___"
ENDERECO_ELEITORAL = "AO JUÍZO DA ___ ZONA ELEITORAL DE ___"


class ErroCompetencia(Exception):
    'Erro nomeado: `codigo` é um de pedido_invalido, pedido_ilegivel, cadastro_ilegivel,'


    def __init__(self, codigo, mensagem):
        super().__init__(mensagem)
        self.codigo = codigo


def _norm(s):
    t = unicodedata.normalize("NFD", str(s or ""))
    return " ".join("".join(c for c in t if unicodedata.category(c) != "Mn").upper().split())


def entes_nomeados(texto):
    """Rótulos dos entes federais nomeados no texto, em ordem e sem repetição."""
    t = _norm(texto)
    for rx in _RX_NEUTRALIZAR:
        t = rx.sub(" _ ", t)
    return [rotulo for rotulo, rx in ENTES_NOMEADOS if rx.search(t)]


_RX_VALOR_PONTO = re.compile(r"^\d+(?:\.\d{1,2})?$")
_RX_VALOR_VIRGULA = re.compile(r"^(?:\d{1,3}(?:\.\d{3})+|\d+),\d{1,2}$")
_RX_VALOR_AMBIGUO = re.compile(r"^\d{1,3}(?:\.\d{3})+$")


def _decimal(valor, campo, codigo="pedido_invalido"):
    'Decimal de um valor em reais: "97260.00" (ponto decimal) ou "97.260,00" (milhar e'


    if valor is None or valor == "":
        return None
    if isinstance(valor, float):
        raise ErroCompetencia(codigo, f"{campo}: informe o valor como texto decimal "
                                      f"(\"97260.00\"), não como número de ponto flutuante")
    if isinstance(valor, bool) or not isinstance(valor, (str, int)):
        raise ErroCompetencia(codigo, f"{campo}: «{valor}» não é um valor em reais")

    s = re.sub(r"\s", "", str(valor)).replace("R$", "")
    if _RX_VALOR_AMBIGUO.match(s):
        raise ErroCompetencia(codigo, f"{campo}: «{valor}» é ambíguo (ponto de milhar sem "
                                      f"centavos); escreva 150000.00 ou 150.000,00")
    if _RX_VALOR_VIRGULA.match(s):
        s = s.replace(".", "").replace(",", ".")
    elif not _RX_VALOR_PONTO.match(s):
        raise ErroCompetencia(codigo, f"{campo}: «{valor}» não é um valor em reais (use "
                                      f"97260.00 ou 97.260,00, até duas casas decimais)")
    try:
        return Decimal(s)
    except InvalidOperation:
        raise ErroCompetencia(codigo, f"{campo}: «{valor}» não é um valor em reais")


def _reais(d):
    q = d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    inteiro, cent = f"{q:.2f}".split(".")
    grupos = []
    while len(inteiro) > 3:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    grupos.insert(0, inteiro)
    return "R$ " + ".".join(grupos) + "," + cent


def _office(cadastro, nome):
    """O objeto do estabelecimento (com `company`), do envelope ou direto."""
    if not isinstance(cadastro, dict):
        raise ErroCompetencia("cadastro_ilegivel", f"cadastro de «{nome}» não é um objeto JSON")
    if isinstance(cadastro.get("data"), dict):
        cadastro = cadastro["data"]
    company = cadastro.get("company")
    if not isinstance(company, dict):
        raise ErroCompetencia("cadastro_ilegivel",
                              f"cadastro de «{nome}» sem os dados da empresa (company)")
    return company


def _codigo_natureza(company, nome):
    nat = company.get("nature")
    nid = nat.get("id") if isinstance(nat, dict) else None
    if isinstance(nid, bool) or nid is None:
        raise ErroCompetencia("cadastro_ilegivel",
                              f"cadastro de «{nome}» sem a natureza jurídica (nature.id)")
    digitos = re.sub(r"\D", "", str(nid))
    if len(digitos) != 4:
        raise ErroCompetencia("cadastro_ilegivel",
                              f"cadastro de «{nome}»: natureza jurídica «{nid}» ilegível")
    texto = nat.get("text") if isinstance(nat.get("text"), str) else ""
    return int(digitos), texto


def _esfera(company, nome):
    "'uniao' | 'subnacional' | 'ausente' | 'desconhecida' pela chave `jurisdiction`. Só os"

    valor = company.get("jurisdiction")
    if valor is None:
        return "ausente", None
    if not isinstance(valor, str):
        raise ErroCompetencia("cadastro_ilegivel",
                              f"cadastro de «{nome}»: esfera (jurisdiction) «{valor}» ilegível")
    n = _norm(valor)
    if not n:
        return "ausente", None
    if n in ("UNIAO", "UNIAO FEDERAL"):
        return "uniao", valor
    if n in _UFS or _RX_ESFERA_MUNICIPAL.match(n):
        return "subnacional", valor
    return "desconhecida", valor


def _pelo_cadastro(cadastro, nome):
    """(esfera, categoria, base, natureza, mensagem). esfera: federal|nao_federal|a_confirmar."""
    company = _office(cadastro, nome)
    codigo, texto = _codigo_natureza(company, nome)
    natureza = f"{codigo} {texto}".strip()
    razao = _norm(company.get("name") or nome)
    esfera, esfera_txt = _esfera(company, nome)

    def confirmar(cat, msg):
        return "a_confirmar", cat, None, natureza, f"{nome}: {msg}"

    if codigo in NATUREZA_FEDERAL:
        cat = "uniao" if codigo in UNIAO_NATUREZAS else "autarquia_federal"
        return "federal", cat, "CF, art. 109, I", natureza, None
    if codigo in NATUREZA_FUNDO:
        return confirmar("fundo_publico_federal",
                         f"o cadastro indica fundo público federal ({natureza}). Fundo não tem "
                         f"personalidade jurídica: a parte é a União ou a entidade que o gere. "
                         f"Confirme quem é parte e declare-a.")
    if codigo in NATUREZA_FEDERAL_A_CONFIRMAR:
        return confirmar("fundacao_publica_federal",
                         f"o cadastro indica {NATUREZA_FEDERAL_A_CONFIRMAR[codigo]} ({natureza}); a "
                         f"equiparação à autarquia para o art. 109, I, da CF não foi conferida em "
                         f"fonte. Confirme se é fundação de direito público (declare "
                         f"autarquia_federal) ou não.")
    if codigo == NAT_ECONOMIA_MISTA:
        return "nao_federal", "sociedade_economia_mista_federal", None, natureza, None
    if codigo == NAT_EMPRESA_PUBLICA:
        if esfera == "ausente":
            return confirmar("empresa_publica_federal",
                             "empresa pública com a esfera não informada no cadastro; confirme "
                             "se é federal, estadual ou municipal.")
        if esfera == "desconhecida":
            return confirmar("empresa_publica_federal",
                             f"empresa pública com a esfera «{esfera_txt}» em formato não "
                             f"reconhecido; confirme se é federal, estadual ou municipal.")
        if esfera == "uniao":
            if _RX_NOME_FEDERAL.search(razao) and not _RX_NOME_SUBNACIONAL.search(razao):
                return "federal", "empresa_publica_federal", "CF, art. 109, I", natureza, None
            return confirmar("empresa_publica_federal",
                             "o cadastro diz empresa pública da esfera «União», mas o nome não "
                             "confirma a esfera federal (a fonte já rotulou assim empresa "
                             "estadual); confirme se é federal.")
        return "nao_federal", "empresa_publica_nao_federal", None, natureza, None
    publica = 1000 <= codigo < 2000
    if publica and (codigo in NATUREZA_SUBNACIONAL or _RX_NATUREZA_SUBNACIONAL.search(_norm(texto))):
        if esfera == "uniao":
            return confirmar("outra", f"o cadastro indica {natureza} com a esfera «União»; "
                                      f"confirme a esfera.")
        return "nao_federal", "publica_nao_federal", None, natureza, None
    if publica:
        return confirmar("outra", f"natureza da administração pública não reconhecida "
                                  f"({natureza}); confirme se é ente federal.")
    if esfera in ("uniao", "desconhecida"):
        return confirmar("outra", f"o cadastro indica {natureza} com a esfera «{esfera_txt}»; "
                                  f"confirme se é ente federal.")
    return "nao_federal", "outra", None, natureza, None


_PELA_DECLARACAO = {
    "uniao": ("federal", "CF, art. 109, I"),
    "autarquia_federal": ("federal", "CF, art. 109, I"),
    "empresa_publica_federal": ("federal", "CF, art. 109, I"),
    "oab": ("federal", "STF, Tema 258 da repercussão geral"),
    "fundacao_publica_federal": ("a_confirmar", None),
    "conselho_profissional": ("a_confirmar", None),
    "sociedade_economia_mista_federal": ("nao_federal", None),
    "estado": ("nao_federal", None),
    "municipio": ("nao_federal", None),
    "privada": ("nao_federal", None),
}


def classificar_parte(parte):
    'Classificação de uma parte: {nome, polo, esfera, categoria, base, origem, natureza,'

    if not isinstance(parte, dict):
        raise ErroCompetencia("pedido_invalido", "cada parte é um objeto {polo, nome, ...}")
    if parte.get("nome") is not None and not isinstance(parte.get("nome"), str):
        raise ErroCompetencia("pedido_invalido", f"nome de parte «{parte.get('nome')}» não é texto")
    nome = str(parte.get("nome") or "").strip()
    polo = str(parte.get("polo") or "").strip().lower()
    if not nome:
        raise ErroCompetencia("pedido_invalido", "parte sem nome")
    if polo not in POLOS:
        raise ErroCompetencia("pedido_invalido",
                              f"«{nome}»: polo «{parte.get('polo')}» fora de {', '.join(POLOS)}")
    declarado = parte.get("ente_declarado")
    if declarado is not None and declarado not in ENTES:
        raise ErroCompetencia("pedido_invalido",
                              f"«{nome}»: ente_declarado «{declarado}» fora de {', '.join(ENTES)}")
    pelo_cad = None
    if parte.get("cadastro") is not None:
        pelo_cad = _pelo_cadastro(parte["cadastro"], nome)
    r = {"nome": nome, "polo": polo, "natureza": pelo_cad[3] if pelo_cad else None,
         "aviso": None, "mensagem": None, "pj_sem_consulta": False}
    if declarado:
        esfera, base = _PELA_DECLARACAO[declarado]
        r.update(esfera=esfera, categoria=declarado, base=base, origem="declarado")
        if pelo_cad and pelo_cad[0] == "federal" and esfera == "nao_federal":


            r.update(esfera="a_confirmar", base=None, sum150=True,
                     mensagem=f"{nome}: declarado {declarado.replace('_', ' ')}, mas o cadastro "
                              f"indica {pelo_cad[3]}, ente federal. Pela Súmula 150 do STJ, quem "
                              f"decide sobre o interesse do ente federal é a Justiça Federal; "
                              f"confirme a declaração.")
            return r
        if esfera == "a_confirmar":
            r["mensagem"] = (
                f"{nome}: declarado fundação pública federal; a equiparação à autarquia para o "
                f"art. 109, I, da CF não foi conferida em fonte. Se é fundação de direito "
                f"público, declare autarquia_federal." if declarado == "fundacao_publica_federal"
                else f"{nome}: conselho de fiscalização profissional; só a execução fiscal tem "
                     f"súmula (Súmula 66 do STJ). Confirme a competência para esta ação.")
        if pelo_cad and pelo_cad[0] != esfera:
            r["aviso"] = (f"{nome}: a declaração do advogado ({declarado}) prevalece sobre o "
                          f"cadastro, que indicava {pelo_cad[3]} ({pelo_cad[0].replace('_', ' ')}).")
        return r
    if pelo_cad:
        esfera, cat, base, _nat, msg = pelo_cad
        r.update(esfera=esfera, categoria=cat, base=base, origem="cadastro", mensagem=msg)
        return r
    nomeados = entes_nomeados(nome)
    nome_n = _norm(nome)
    sinal = _RX_NOME_PARTE_SINAL.search(re.sub(r"\bDISTRITO\s+FEDERAL\b", " ", nome_n))
    if nomeados or sinal:
        indicio = nomeados[0] if nomeados else sinal.group(0).strip().lower()
        r.update(esfera="a_confirmar", categoria="nomeado", base=None, origem="nome",
                 mensagem=f"{nome}: o nome indica ente federal ({indicio}), sem consulta "
                          f"cadastral nem declaração; confirme a natureza jurídica.")
        return r
    r.update(esfera="nao_federal", categoria="nao_informada", base=None, origem="nenhum",
             pj_sem_consulta=bool(_RX_NOME_PJ.search(nome_n)))
    return r


def _salario_minimo(data, tabela):
    for linha in tabela:
        if linha["inicio"] <= data <= linha["fim"]:
            return linha
    return None


def _validar_tabela(tabela):
    if isinstance(tabela, dict):
        tabela = tabela.get("tabela")
    if not isinstance(tabela, list) or not tabela:
        raise ErroCompetencia("tabela_invalida", "a tabela de salário mínimo é uma lista não vazia")
    out = []
    for linha in tabela:
        try:
            v = _decimal(linha["valor"], "valor", codigo="tabela_invalida")
            ini = _data(linha["inicio"], "inicio", "tabela_invalida")
            fim = _data(linha["fim"], "fim", "tabela_invalida")
        except (KeyError, TypeError, ValueError, ErroCompetencia) as e:
            raise ErroCompetencia("tabela_invalida", f"linha da tabela de salário mínimo ilegível "
                                                     f"({e}); cada linha tem valor, inicio e fim")
        if v is None or v <= 0 or ini > fim:
            raise ErroCompetencia("tabela_invalida", "linha da tabela de salário mínimo com valor "
                                                     "ou vigência inválidos")
        out.append({"valor": str(v), "inicio": ini, "fim": fim,
                    "norma": str(linha.get("norma") or ""),
                    "fonte_url": str(linha.get("fonte_url") or ""),
                    "conferido_em": str(linha.get("conferido_em") or "")})
    ordem = sorted(out, key=lambda x: x["inicio"])
    for a, b in zip(ordem, ordem[1:]):
        if b["inicio"] <= a["fim"]:
            raise ErroCompetencia("tabela_invalida",
                                  f"vigências sobrepostas na tabela de salário mínimo "
                                  f"({a['inicio']} a {a['fim']} e {b['inicio']} a {b['fim']})")
    return out


_RX_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _data(valor, campo, codigo="pedido_invalido"):
    'Data AAAA-MM-DD validada pelo formato antes do fromisoformat: o Python 3.11 aceita'

    s = str(valor).strip()
    try:
        if not _RX_DATA.match(s):
            raise ValueError
        return datetime.date.fromisoformat(s).isoformat()
    except ValueError:
        raise ErroCompetencia(codigo, f"{campo} «{valor}» não é AAAA-MM-DD")


def _tipo_excluido(tipo):
    """(rótulo da exclusão ou None, declarado_sem_exclusao)."""
    t = (tipo or "").strip()
    if not t:
        return None, False
    if t == TIPO_SEM_EXCLUSAO:
        return None, True
    if t in EXCLUSOES_JEF:
        return EXCLUSOES_JEF[t][0], False
    norm = _norm(t).lower()
    for _chave, (rotulo, rx) in EXCLUSOES_JEF.items():
        if re.search(rx, norm):
            return rotulo, False
    return None, False


def _jef(pedido, partes, fund, avisos, tabela, data):
    """(jef, motivo, salario_minimo usado ou None)."""
    nao, faltam = [], []
    autor_tipo = pedido.get("autor_tipo")
    if autor_tipo is not None and autor_tipo not in AUTOR_TIPOS:
        raise ErroCompetencia("pedido_invalido",
                              f"autor_tipo «{autor_tipo}» fora de {', '.join(AUTOR_TIPOS)}")
    fund("l10259_6")
    if autor_tipo is None:
        faltam.append("o tipo do autor (pessoa física, microempresa, EPP ou outra)")
    elif autor_tipo == "outra":
        nao.append("o autor não é pessoa física, microempresa nem empresa de pequeno porte "
                   "(Lei 10.259, art. 6º, I)")
    reu_federal = any(p["polo"] == "passivo" and p["esfera"] == "federal"
                      and p["categoria"] != "oab" for p in partes)
    for p in partes:
        if p["polo"] == "ativo":
            if p["esfera"] == "federal":
                nao.append(f"{p['nome']} é ente federal e não pode ser autor no JEF, que só admite "
                           f"como autores pessoa física, microempresa e empresa de pequeno porte "
                           f"(Lei 10.259, art. 6º, I)")
            elif p["esfera"] == "a_confirmar":
                faltam.append(f"a natureza de {p['nome']}, no polo ativo")
            elif p["origem"] == "cadastro" and autor_tipo == "pessoa_fisica":
                faltam.append(f"o tipo do autor: {p['nome']} tem cadastro de pessoa jurídica, mas "
                              f"autor_tipo diz pessoa física")
            continue
        if p["polo"] != "passivo":
            continue
        if p["esfera"] == "a_confirmar":
            faltam.append(f"a natureza de {p['nome']}")
        elif p["esfera"] == "federal" and p["categoria"] == "oab":
            faltam.append(f"se {p['nome']} pode ser ré no JEF: o art. 6º, II, da Lei 10.259 não "
                          f"nomeia a OAB, e a questão não foi conferida em fonte")
        elif p["esfera"] != "federal":
            if reu_federal:
                fund("fonajef21")
                faltam.append(f"se há litisconsórcio necessário com {p['nome']}: só nele quem não "
                              f"é ente federal figura como réu no JEF (FONAJEF, Enunciado 21)")
            else:
                nao.append(f"{p['nome']} não pode ser ré no JEF, que só admite como rés a União, "
                           f"autarquias, fundações e empresas públicas federais (Lei 10.259, "
                           f"art. 6º, II)")
    tipo = pedido.get("tipo_acao")
    if tipo is not None and not isinstance(tipo, str):
        raise ErroCompetencia("pedido_invalido", f"tipo_acao «{tipo}» não é texto")
    excluido, sem_exclusao = _tipo_excluido(tipo)
    if excluido:
        fund("l10259_3_p1")
        nao.append(f"ação de {excluido} está fora do JEF (Lei 10.259, art. 3º, §1º)")
    elif not (tipo or "").strip():
        faltam.append("o tipo de ação (para conferir as exclusões do art. 3º, §1º)")
    elif not sem_exclusao:
        faltam.append(f"o tipo de ação: «{tipo.strip()}», em texto livre, não confirma que a causa "
                      f"está fora das exclusões do art. 3º, §1º; informe a chave da exclusão ou "
                      f"{TIPO_SEM_EXCLUSAO}")
    valor = _decimal(pedido.get("valor_causa"), "valor_causa")
    parcela = _decimal(pedido.get("parcela_vincenda_mensal"), "parcela_vincenda_mensal")
    sm = _salario_minimo(data, tabela)
    fund("l10259_3")
    if sm is None:
        avisos.append(f"Não há salário mínimo na tabela para {data}: atualize a tabela de "
                      f"salário mínimo (--salario-minimo-tabela) antes de concluir pelo JEF.")
        faltam.append("o salário mínimo vigente na data (tabela desatualizada)")
        teto = None
    else:
        if sm["norma"] == TABELA_SALARIO_MINIMO[0]["norma"]:
            fund("decreto12797")
        teto = Decimal(sm["valor"]) * 60
    if valor is None:
        faltam.append("o valor da causa")
    elif teto is not None and valor > teto:
        nao.append(f"o valor da causa ({_reais(valor)}) passa do teto de 60 salários mínimos "
                   f"({_reais(teto)}; Lei 10.259, art. 3º)")
    if parcela is not None and teto is not None:
        fund("l10259_3_p2")
        if parcela * 12 > teto:
            nao.append(f"doze parcelas vincendas ({_reais(parcela * 12)}) passam do teto "
                       f"({_reais(teto)}; Lei 10.259, art. 3º, §2º)")
    if parcela is not None and valor is not None and parcela * 12 > valor:
        faltam.append(f"o valor da causa: {_reais(valor)} é menor que doze parcelas vincendas "
                      f"({_reais(parcela * 12)}), e ele soma as vencidas e as vincendas (CPC, "
                      f"art. 292, §§1º e 2º); confira o valor")
    if nao:
        return "nao", "Fora do JEF: " + "; ".join(nao) + ".", sm
    if faltam:
        return "indeterminado", "Falta para decidir o JEF: " + "; ".join(faltam) + ".", sm
    return ("sim", f"Cabe o JEF: autor e réus admitidos (art. 6º), ação fora das exclusões do "
                   f"art. 3º, §1º, e valor dentro do teto de {_reais(teto)} (60 salários mínimos de "
                   f"{_reais(Decimal(sm['valor']))}).", sm)


def verificar(pedido, tabela_salario_minimo=None, hoje=None):
    """O resultado `dsr.competencia.v1` do pedido. Função pura (nada lê nem grava)."""
    if not isinstance(pedido, dict):
        raise ErroCompetencia("pedido_invalido", "o pedido é um objeto JSON")
    partes_in = pedido.get("partes")
    if not isinstance(partes_in, list) or not partes_in:
        raise ErroCompetencia("pedido_invalido", "o pedido precisa de ao menos uma parte")
    excecao = pedido.get("excecao")
    if excecao is not None and excecao not in EXCECOES:
        raise ErroCompetencia("pedido_invalido",
                              f"excecao «{excecao}» fora de {', '.join(EXCECOES)}")
    tabela = (_validar_tabela(tabela_salario_minimo) if tabela_salario_minimo is not None
              else [dict(x) for x in TABELA_SALARIO_MINIMO])
    data = _data(pedido.get("data_referencia") or (hoje or datetime.date.today()).isoformat(),
                 "data_referencia")

    partes = [classificar_parte(p) for p in partes_in]
    fundamentos, vistos, avisos = [], set(), []

    def fund(chave):
        if chave not in vistos:
            vistos.add(chave)
            regra, url = FONTES[chave]
            fundamentos.append({"regra": regra, "fonte_url": url, "conferido_em": CONFERIDO_EM})

    for p in partes:
        if p["aviso"]:
            avisos.append(p["aviso"])
        if p.get("sum150"):
            fund("sum150")
        if p["pj_sem_consulta"]:
            avisos.append(f"{p['nome']}: pessoa jurídica sem diligência cadastral nem declaração; "
                          f"a esfera não foi conferida. Rode a consulta cadastral e passe o "
                          f"retorno no campo cadastro.")
        if p["origem"] == "cadastro":
            fund("concla")
        if p["categoria"] == "sociedade_economia_mista_federal":
            fund("sum556")
            fund("sum42")
            if "BANCO DO BRASIL" in _norm(p["nome"]):
                fund("sum508")
    federais = [p for p in partes if p["esfera"] == "federal"]
    duvidas = [p["mensagem"] for p in partes if p["esfera"] == "a_confirmar"]
    entes = [{"nome": p["nome"], "polo": p["polo"], "base": p["base"]} for p in federais]
    delegada = False
    jef, motivo, sm = "nao_se_aplica", "A causa não é da Justiça Federal.", None

    if excecao in ("falencia", "insolvencia_civil", "acidente_trabalho", "eleitoral",
                   "relacao_de_trabalho"):
        fund("cf109_i_excecoes")
        if excecao == "insolvencia_civil":
            fund("tema859")
        justica = {"falencia": "estadual", "insolvencia_civil": "estadual",
                   "acidente_trabalho": "estadual",
                   "eleitoral": "eleitoral", "relacao_de_trabalho": "trabalho"}[excecao]
        if excecao == "acidente_trabalho":
            fund("sum501")
            fund("sv22")
            avisos.append("A Súmula 501 do STF cobre a ação acidentária, contra o ente "
                          "previdenciário. A indenização do empregado contra o empregador por "
                          "acidente do trabalho é da Justiça do Trabalho (Súmula Vinculante 22 do "
                          "STF): se o pedido é contra o empregador, declare relacao_de_trabalho.")
        if excecao == "relacao_de_trabalho":
            fund("cf114_i")
            for p in partes:
                if p["esfera"] in ("federal", "a_confirmar") and p["categoria"] in (
                        "uniao", "autarquia_federal", "fundacao_publica_federal", "oab",
                        "conselho_profissional", "nomeado"):
                    avisos.append(f"{p['nome']} é pessoa de direito público: se o vínculo é "
                                  f"estatutário (servidor), a causa não é da Justiça do Trabalho "
                                  f"(STF, ADI 3395, não conferida em fonte nesta verificação). "
                                  f"Nesse caso, retire a exceção e rode o verificador de novo.")
        avisos.extend(f"Sem efeito na justiça, pela exceção declarada: {m}" for m in duvidas)
        duvidas = []
        motivo = "Exceção declarada: a causa não é da Justiça Federal."
    elif excecao == "competencia_delegada_previdenciaria":
        def _previdencia(p):
            return p["esfera"] == "federal" and (
                "INSS" in entes_nomeados(p["nome"]) or "SEGURO SOCIAL" in _norm(p["nome"]))
        previdencia = [p for p in partes if _previdencia(p) and p["polo"] == "passivo"]
        if not previdencia:
            raise ErroCompetencia(
                "excecao_incompativel",
                "competência delegada previdenciária exige o ente previdenciário (o INSS) no polo "
                "passivo, classificado como autarquia federal, em ação do segurado; nenhuma parte "
                "o é")
        if pedido.get("autor_tipo") not in (None, "pessoa_fisica"):
            raise ErroCompetencia(
                "excecao_incompativel",
                "competência delegada previdenciária é a da ação do segurado, pessoa física; "
                f"autor_tipo «{pedido.get('autor_tipo')}» não cabe nela")
        for c in ("cf109_p3", "cf109_p4", "l5010_15", "l5010_15_iii"):
            fund(c)
        justica, delegada = "estadual", True
        avisos.append("Competência delegada: o recurso vai ao Tribunal Regional Federal (CF, art. "
                      "109, §4º), e não ao Tribunal de Justiça.")
        avisos.append("A delegação cobre as causas entre a instituição de previdência e o segurado "
                      "que se referirem a benefícios de natureza pecuniária (Lei 5.010/1966, art. "
                      "15, III): confira se o pedido é desse tipo.")
        for p in partes:
            if p["esfera"] == "federal" and not _previdencia(p):
                avisos.append(f"{p['nome']} também é ente federal: a delegação do art. 109, §3º, "
                              f"cobre só a causa entre a previdência e o segurado; com essa parte "
                              f"em polo, confira se a causa não vai à Justiça Federal.")
        avisos.append("A comarca do domicílio do segurado tem de constar da lista de comarcas do "
                      "TRF da região (Lei 5.010/1966, art. 15, §2º); sem ela, a ação vai à "
                      "Justiça Federal.")
        motivo = "Competência delegada: a causa corre na justiça estadual, fora do JEF."
        avisos.extend(f"Sem efeito na justiça, pela exceção declarada: {m}" for m in duvidas
                      if m)
        duvidas = []
    elif excecao == "uniao_intervem":
        fund("sum517")
        fund("cf109_i")
        justica = "federal"
        entes.append({"nome": "União (interveniente)", "polo": "assistente",
                      "base": "Súmula 517 do STF"})
    elif federais:
        fund("cf109_i")
        fund("sum150")
        justica = "federal"
    elif duvidas:
        justica = "indeterminada"
        motivo = "A justiça depende do que está a confirmar."
    else:
        justica = "estadual"
        sem_consulta = [p["nome"] for p in partes if p["pj_sem_consulta"]]
        if sem_consulta:
            avisos.append(f"Nenhuma parte classificada como ente federal, mas {len(sem_consulta)} "
                          f"pessoa(s) jurídica(s) sem consulta cadastral nem declaração "
                          f"({', '.join(sem_consulta)}): "
                          f"justiça comum estadual pelo que foi informado, salvo matéria da "
                          f"Justiça do Trabalho ou da Eleitoral (declare a exceção, se for o caso).")
        else:
            avisos.append("Sem ente federal nas partes: justiça comum estadual, salvo matéria da "
                          "Justiça do Trabalho ou da Eleitoral (declare a exceção, se for o caso).")

    if justica == "federal":
        jef, motivo, sm = _jef(pedido, partes, fund, avisos, tabela, data)
        fund("l10259_3_p3")
        avisos.append("Onde houver vara do Juizado Especial Federal instalada, a competência dele "
                      "é absoluta (Lei 10.259, art. 3º, §3º): confira se há na subseção.")

    uniao_re = any(p["polo"] == "passivo" and p["esfera"] == "federal" and p["categoria"] == "uniao"
                   for p in partes)
    foro_uniao = None
    if justica == "federal" and uniao_re:
        fund("cf109_p2")
        foro_uniao = ("CF, art. 109, §2º: a ação contra a União pode ser aforada na seção "
                      "judiciária do domicílio do autor, naquela onde ocorreu o ato ou fato, onde "
                      "está a coisa, ou no Distrito Federal.")
    endereco = {"federal": ENDERECO_JEF if jef == "sim" else ENDERECO_FEDERAL,
                "estadual": ENDERECO_ESTADUAL, "trabalho": ENDERECO_TRABALHO,
                "eleitoral": ENDERECO_ELEITORAL}.get(justica)
    return {
        "schema": SCHEMA,
        "justica": justica,
        "delegada": delegada,
        "excecao": excecao,
        "jef": jef,
        "jef_motivo": motivo,
        "entes_federais": entes,
        "a_confirmar": [m for m in duvidas if m],
        "fundamentos": fundamentos,
        "enderecamento_sugerido": endereco,
        "foro_uniao": foro_uniao,
        "avisos": avisos,
        "partes": [{"nome": p["nome"], "polo": p["polo"], "esfera": p["esfera"],
                    "origem": p["origem"], "natureza": p["natureza"]} for p in partes],
        "salario_minimo": ({"valor": _reais(Decimal(sm["valor"])), "norma": sm["norma"],
                            "vigencia": f"{sm['inicio']} a {sm['fim']}",
                            "fonte_url": sm["fonte_url"]} if sm else None),
        "data_referencia": data,
        "conferido_em": CONFERIDO_EM,
    }


def _ler_json(caminho, codigo, rotulo):
    try:
        with open(caminho, "rb") as f:
            return json.loads(f.read().decode("utf-8-sig"))
    except FileNotFoundError:
        raise ErroCompetencia(codigo, f"{rotulo} não encontrado: {caminho}")
    except (OSError, UnicodeDecodeError, ValueError) as e:
        raise ErroCompetencia(codigo, f"{rotulo} ilegível ({caminho}): {e}")


def gravar(resultado, pasta):
    """Grava COMPETENCIA.json (UTF-8, LF) na pasta da peça. Devolve o caminho."""
    if not pasta or not os.path.isdir(pasta):
        raise ErroCompetencia("gravacao_falhou", f"pasta da peça inexistente: {pasta}")
    destino = os.path.join(pasta, ARQUIVO)
    dados = (json.dumps(resultado, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    try:
        with open(destino, "wb") as f:
            f.write(dados)
    except OSError as e:
        raise ErroCompetencia("gravacao_falhou", f"não foi possível gravar {destino}: {e}")
    return destino


def _opcao(argv, nome):
    if nome in argv:
        i = argv.index(nome)
        if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
            raise ErroCompetencia("pedido_invalido", f"{nome} exige um valor")
        return argv[i + 1]
    return None


def main(argv):
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    try:
        conhecidas = ("--pedido", "--gravar", "--salario-minimo-tabela")
        for a in argv:
            if a.startswith("--") and a not in conhecidas:
                raise ErroCompetencia("pedido_invalido", f"opção desconhecida: {a}")
        caminho = _opcao(argv, "--pedido")
        if not caminho:
            raise ErroCompetencia("pedido_invalido", "uso: competencia.py --pedido pedido.json "
                                                     "[--gravar <pasta>] (veja --help)")
        pasta = _opcao(argv, "--gravar")
        tab_arq = _opcao(argv, "--salario-minimo-tabela")
        pedido = _ler_json(caminho, "pedido_ilegivel", "pedido")
        tabela = _ler_json(tab_arq, "tabela_invalida", "tabela de salário mínimo") if tab_arq else None
        resultado = verificar(pedido, tabela_salario_minimo=tabela)
        if pasta:
            resultado["gravado_em"] = gravar(resultado, pasta)
    except ErroCompetencia as e:
        print(json.dumps({"erro": e.codigo, "mensagem": str(e)}, ensure_ascii=False))
        return 2
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main(sys.argv[1:]))
