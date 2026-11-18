#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'Resumo estruturado do art. 343-A do RISTJ, montado como ANEXO à parte da peça.'






















































from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import sys
import zipfile
from typing import Any

try:
    import ficha_capacidade
except ImportError:
    from . import ficha_capacidade


CAPACIDADE = "resumo_343a"
CHAVE = "DSR_RESUMO_343A_EXPERIMENTAL"
VERSAO_PEDIDO = "dsr.resumo_343a.pedido.v1"
VERSAO_SAIDA = "dsr.resumo_343a.saida.v1"
NOME_ANEXO = "Resumo-estruturado-RISTJ-343-A.txt"
CODIGOS = (
    "capacidade_desabilitada", "pedido_invalido", "peca_ilegivel", "regime_invalido",
) + ficha_capacidade.CODIGOS

ACHADOS = (
    "campo_ausente", "campo_longo", "campo_nao_aplicavel", "remissao_generica",
    "dispositivo_nao_individualizado", "precedente_incompleto", "divergencia_peca_resumo",
    "omissao_no_resumo", "repeticao_integral",
)
CLASSES = (
    "recurso_especial", "agravo_em_recurso_especial", "recurso_ordinario", "agravo_interno",
    "agravo_regimental", "embargos_de_divergencia", "embargos_de_declaracao", "outro_recurso",
    "acao_originaria", "tutela_provisoria_antecedente", "pedido_de_uniformizacao",
)

CLASSES_NA_ORIGEM = ("recurso_especial", "agravo_em_recurso_especial", "recurso_ordinario",
                     "pedido_de_uniformizacao")
SECOES = ("primeira", "segunda", "terceira", "corte_especial", "nao_informada")
CAMPOS = ("I", "II", "III", "IV", "V")
ROTULOS = {
    "I": "I – Síntese dos fatos e da decisão impugnada",
    "II": "II – Fundamentos de direito e dispositivos invocados",
    "III": "III – Pedidos",
    "IV": "IV – Precedentes, súmulas e enunciados invocados",
    "V": "V – Relevância da questão de direito federal",
}



EXTENSAO_RECOMENDADA_POR_CAMPO = 3000



JANELA_EDUCATIVA_DIAS = 90

CONFERIDO_EM = "17/11/2026"
NOTICIA_02092026 = ("https://www.stj.jus.br/sites/portalp/Paginas/Comunicacao/Noticias/2026/"
                    "02092026-Exigencia-de-resumo-em-acoes-originarias-e-recursos-ao-STJ-so-"
                    "valera-apos-publicacao-de-portaria-da-Presidencia.aspx")
IN42_OFICIAL = ("https://bdjur.stj.jus.br/server/api/core/bitstreams/"
                "2a2d9b64-cb89-4c5e-9f19-2902f8b60cf9/content")

REGIME_343A = {"portaria_stj": None, "portaria_origem": None}


_TRIBUNAL_ORIGEM = re.compile(
    r"^(?:TJ(?:AC|AL|AP|AM|BA|CE|DFT|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO)"
    r"|TRF[1-6])$")


def _in42(dispositivo: str, paginas: str) -> str:
    'A base de um achado no texto oficial da IN 42. A página é a do PDF oficial da BDJur (5'


    return ("IN STJ/GP 42/2026, " + dispositivo + "; DJe de 20/08/2026; PDF oficial da BDJur, p. "
            + paginas + "; conferido em " + CONFERIDO_EM)


RESPONSABILIDADE = (
    "O resumo é de responsabilidade exclusiva da parte ou do advogado que peticiona e deve "
    "retratar fielmente a petição, os fatos da causa e as decisões impugnadas (" + _in42(
        "art. 4º", "3") + "). Pelo art. 4º, parágrafo único, a inexatidão deliberada ou a "
    "omissão substancial podem ser consideradas, conforme a gravidade, ato atentatório à "
    "dignidade da justiça, sem prejuízo de comunicação aos órgãos de classe. Confira campo a "
    "campo antes de colar no sistema: a montagem automática não substitui a conferência do "
    "advogado.")

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DATA = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_REMISSAO = re.compile(
    r"\b(?:vide|ver|veja)\s+(?:as\s+|a\s+)?(?:raz[õo]es|peti[çc][ãa]o)\b"
    r"|\bconforme\s+(?:acima|exposto|j[áa]\s+dito|as\s+raz[õo]es|a\s+peti[çc][ãa]o)"
    r"|\bnos\s+termos\s+das\s+raz[õo]es\b|\bcf\.\s*(?:a\s+)?(?:peti[çc][ãa]o|raz[õo]es)\b",
    re.I)
_ARTIGO = re.compile(r"\bart(?:igo)?s?\.?\s*(\d{1,3}(?:\.\d{3})+|\d+)", re.I)
_DIPLOMA = re.compile(
    r"\b(?:CPC|CC|CF|CDC|CLT|CP|CPP|CTN|ECA|LINDB|CR|CRFB|Constitui[çc][ãa]o|C[óo]digo|Lei|"
    r"Decreto|LC|Estatuto|Medida\s+Provis[óo]ria|MP|Emenda|Regimento|RISTJ)\b")
_NUM = r"(?:n[ºo°.]\s*)?(\d{1,3}(?:\.\d{3})+|\d+)"
_CASO = re.compile(r"\b(?:REsp|AREsp|EREsp|AgInt|AgRg|EDcl|RE|ARE|HC|RHC|RMS|MS|Rcl|CC)\b\.?\s*"
                   + _NUM)
_SUMULA = re.compile(r"\bS[úu]mula(?:\s+Vinculante)?\s*" + _NUM, re.I)
_SUMULA_SEM_NUM = re.compile(r"\bS[úu]mula\b(?!(?:\s+Vinculante)?\s*(?:n[ºo°.]\s*)?\d)", re.I)
_TEMA = re.compile(r"\bTema\s*" + _NUM, re.I)
_TEMA_SEM_NUM = re.compile(r"\bTema\b(?!\s*(?:n[ºo°.]\s*)?\d)", re.I)
_ENUNCIADO = re.compile(r"\bEnunciado\s*" + _NUM, re.I)
_ENUNCIADO_SEM_NUM = re.compile(r"\bEnunciado\b(?!\s*(?:n[ºo°.]\s*)?\d)", re.I)
_TRIBUNAL = re.compile(r"\b(?:STJ|STF|TST|TSE|STM|TNU|TRF\d?|TJ[A-Z]{2,3}|TRT\d*)\b")
_ORGAO = re.compile(r"\b(?:STJ|STF|TST|TSE|STM|TNU|TRF\d?|TJ[A-Z]{2,3}|TRT\d*|Turma|Se[çc][ãa]o|"
                    r"Corte\s+Especial|Plen[áa]rio|Pleno|[ÓO]rg[ãa]o\s+Especial|CJF|FPPC|FONAJE|"
                    r"Jornada|F[óo]rum)\b", re.I)
_DATA_CITADA = re.compile(r"\b\d{1,2}[/.]\d{1,2}[/.]\d{4}\b|\b\d{1,2}º?\s+de\s+[a-zç]+\s+de\s+"
                          r"\d{4}\b", re.I)
_NENHUM = re.compile(r"^\s*(?:n[ãa]o\s+h[áa]|nenhum|nenhuma|sem\s+precedente)", re.I)

_ABREVIATURAS = {"rel", "min", "des", "n", "nº", "art", "arts", "p", "j", "dje", "dj", "rel.ª",
                 "sr", "dr", "dra", "fls", "v", "cf", "inc", "al"}


class Resumo343AError(RuntimeError):
    def __init__(self, code: str, errors: list[str] | str):
        self.code = code
        self.errors = [errors] if isinstance(errors, str) else list(errors)
        super().__init__("; ".join(self.errors))




def _validar_portaria(nome: str, valor: Any, *, com_tribunais: bool = False) -> dict | None:
    if valor is None:
        return None
    chaves = {"publicada_em", "url", "sha256"} | ({"tribunais"} if com_tribunais else set())
    if not isinstance(valor, dict):
        raise Resumo343AError("regime_invalido",
                              f"{nome}: objeto com " + ", ".join(sorted(chaves)))
    erros = []
    extras = sorted(set(valor) - chaves)
    if extras:
        erros.append(f"{nome}: chave(s) desconhecida(s): " + ", ".join(extras)
                     + ("" if com_tribunais else " (a portaria do STJ não indica tribunais)"))
    tribunais = valor.get("tribunais")
    if com_tribunais and (not isinstance(tribunais, list) or not tribunais or not all(
            isinstance(t, str) and _TRIBUNAL_ORIGEM.match(t) for t in tribunais)):
        erros.append(f"{nome}.tribunais: lista não vazia de siglas de TJ ou TRF (IN STJ/GP "
                     "42/2026, art. 12, II, e art. 3º, caput)")
    data = valor.get("publicada_em")
    if not isinstance(data, str) or not _DATA.match(data):
        erros.append(f"{nome}.publicada_em: data AAAA-MM-DD")
    if not isinstance(valor.get("url"), str) or not valor["url"].startswith("https://"):
        erros.append(f"{nome}.url: endereço oficial em https")
    if not isinstance(valor.get("sha256"), str) or not _SHA256.match(valor["sha256"]):
        erros.append(f"{nome}.sha256: 64 caracteres hexadecimais minúsculos")
    if erros:
        raise Resumo343AError("regime_invalido", erros)
    try:
        publicada = dt.date.fromisoformat(data)
    except ValueError:
        raise Resumo343AError("regime_invalido", f"{nome}.publicada_em: data inexistente") from None
    saida = {"publicada_em": publicada, "url": valor["url"], "sha256": valor["sha256"]}
    if com_tribunais:
        saida["tribunais"] = list(tribunais)
    return saida


def _portarias_de_origem(valor: Any) -> list[dict]:
    """A portaria da origem do art. 12, II: uma ou várias, cada uma com os tribunais que habilita."""
    if valor is None:
        return []
    lista = valor if isinstance(valor, list) else [valor]
    return [_validar_portaria(f"portaria_origem[{i}]", p, com_tribunais=True)
            for i, p in enumerate(lista)]


def _validar_tribunal(tribunal: Any) -> None:
    if tribunal is not None and (not isinstance(tribunal, str)
                                 or not _TRIBUNAL_ORIGEM.match(tribunal)):
        raise Resumo343AError("pedido_invalido", "tribunal de origem: sigla de TJ ou de TRF "
                              "(IN STJ/GP 42/2026, art. 3º, caput)")


def _publica(portaria: dict) -> dict:
    return dict(portaria, publicada_em=portaria["publicada_em"].isoformat())


def estado_da_exigencia(hoje: dt.date | None = None, regime: Any = None, *,
                        destino: str = "stj", secao: str | None = None,
                        tribunal: str | None = None) -> dict:
    'Se o resumo é exigível, em janela educativa ou não, na data `hoje`.'





    hoje = hoje or dt.date.today()
    regime = REGIME_343A if regime is None else regime
    if not isinstance(regime, dict):
        raise Resumo343AError("regime_invalido", "o regime é um objeto JSON")
    extras = sorted(set(regime) - {"portaria_stj", "portaria_origem"})
    if extras:
        raise Resumo343AError("regime_invalido", "chave(s) desconhecida(s): " + ", ".join(extras))
    _validar_tribunal(tribunal)
    portaria_stj = _validar_portaria("portaria_stj", regime.get("portaria_stj"))
    origens = _portarias_de_origem(regime.get("portaria_origem"))
    base = "RISTJ, art. 343-A (ER 53/2026); " + _in42("arts. 2º, 9º e 12", "2, 4 e 5")
    if secao == "terceira":
        return {"estado": "fora_do_regime", "destino": destino, "base": base, "mensagem": (
            "Processo da Terceira Seção: até ato normativo específico da Presidência do STJ, a "
            "exigência do resumo não se aplica a ele (" + _in42("art. 2º, parágrafo único", "2")
            + "). O resumo pode ser montado, mas não é exigido.")}
    if destino == "stj":
        portaria = portaria_stj
        onde = "no sistema de peticionamento do STJ"
        falta = ("portaria da Presidência que dê por concluída a preparação dos campos " + onde
                 + " (" + _in42("art. 12, I", "4") + ")")
    else:
        onde = ("no sistema do tribunal de origem" if tribunal is None
                else "no sistema do " + tribunal)
        if tribunal is None and origens:
            lista = "; ".join(", ".join(p["tribunais"]) + " (portaria de "
                              + p["publicada_em"].strftime("%d/%m/%Y") + ")" for p in origens)
            return {"estado": "depende_do_tribunal", "destino": destino, "base": base,
                    "mensagem": (
                        "Na origem, o resumo só é exigível nos tribunais que a portaria da "
                        "Presidência indicar como habilitados (" + _in42("art. 12, II", "4")
                        + "). Tribunais indicados: " + lista + ". Informe o tribunal de origem "
                        "para saber o estado.")}
        candidatas = [p for p in origens if tribunal in p["tribunais"]]
        portaria = min(candidatas, key=lambda p: p["publicada_em"]) if candidatas else None
        falta = ("portaria da Presidência que indique " + ("o " + tribunal if tribunal else
                                                          "o tribunal de origem")
                 + " entre os tribunais de justiça e tribunais regionais federais com o sistema "
                 "habilitado para receber o resumo (" + _in42("art. 12, II", "4") + ")")
    if portaria is None or hoje < portaria["publicada_em"]:
        return {"estado": "nao_exigivel", "destino": destino, "base": base, "mensagem": (
            "Hoje o resumo não é exigível " + onde + ": o STJ só passa a exigi-lo depois de "
            + falta + ", e essa portaria não foi localizada até " + CONFERIDO_EM + ".")}
    desde = portaria["publicada_em"].strftime("%d/%m/%Y")
    fim = portaria["publicada_em"] + dt.timedelta(days=JANELA_EDUCATIVA_DIAS)
    if hoje <= fim:
        return {"estado": "exigivel_janela_educativa", "destino": destino, "base": base,
                "janela_ate": fim.isoformat(), "portaria": _publica(portaria),
                "mensagem": (
                    "O resumo é exigível " + onde + " desde a portaria de " + desde + ", em "
                    "período de adaptação de noventa dias corridos, até "
                    + fim.strftime("%d/%m/%Y") + " (contagem sem o dia da portaria; a IN não "
                    "fixa o critério): a falta leva a intimação com instruções, "
                    "sem a intimação para regularizar (" + _in42("art. 12, parágrafo único", "5")
                    + ").")}
    return {"estado": "exigivel", "destino": destino, "base": base, "portaria": _publica(portaria),
            "mensagem": (
                "O resumo é exigível " + onde + " desde a portaria de " + desde + ". A falta, o "
                "campo incompleto ou a incompatibilidade com a petição levam a certidão e a "
                "intimação para regularizar no prazo de dez dias (a IN não diz se são úteis). A "
                "regularização se faz sem reabertura de prazo para alterar as razões e sem "
                "efeito sobre a tempestividade da peça; quem entende o resumo compatível pode, "
                "no mesmo prazo, manifestar a desnecessidade da correção, e os autos vão ao "
                "relator ou ao presidente (" + _in42("art. 5º, §§ 1º, 2º, III, 4º e 5º", "3-4")
                + "). Ficam dispensadas a petição da parte sem advogado, onde a lei autoriza a "
                "postulação direta, e a situação excepcional reconhecida, motivadamente, pelo "
                "relator ou presidente (" + _in42("art. 6º", "4") + ").")}




def texto_da_peca(caminho: str) -> str:
    """O texto da peça: o corpo do .docx, parágrafo por linha, ou o arquivo de texto como está."""
    try:
        if caminho.lower().endswith(".docx"):
            with zipfile.ZipFile(caminho) as z:
                xml = z.read("word/document.xml").decode("utf-8")
            paragrafos = re.findall(r"<w:p[ >].*?</w:p>", xml, flags=re.S)
            linhas = ["".join(re.findall(r"<w:t(?: [^>]*)?>(.*?)</w:t>", p, flags=re.S))
                      for p in paragrafos]
            return "\n".join(html.unescape(x) for x in linhas)
        with open(caminho, encoding="utf-8") as arquivo:
            return arquivo.read()
    except (OSError, KeyError, UnicodeError, zipfile.BadZipFile) as exc:
        raise Resumo343AError("peca_ilegivel", "a peça não pôde ser lida ("
                              + exc.__class__.__name__ + ")") from None




def _validar_pedido(pedido: Any) -> list[str]:
    if not isinstance(pedido, dict):
        return ["o pedido é um objeto JSON"]
    erros = []
    extras = sorted(set(pedido) - {"schema_version", "classe", "secao", "tribunal_origem",
                                   "campos"})
    if extras:
        erros.append("chave(s) desconhecida(s): " + ", ".join(extras))
    trib = pedido.get("tribunal_origem")
    if trib is not None and (not isinstance(trib, str) or not _TRIBUNAL_ORIGEM.match(trib)):
        erros.append("tribunal_origem: sigla de TJ ou de TRF (IN STJ/GP 42/2026, art. 3º, "
                     "caput)")
    if pedido.get("schema_version") != VERSAO_PEDIDO:
        erros.append("schema_version: " + VERSAO_PEDIDO)
    if pedido.get("classe") not in CLASSES:
        erros.append("classe: uma de " + ", ".join(CLASSES))
    if "secao" in pedido and pedido["secao"] not in SECOES:
        erros.append("secao: uma de " + ", ".join(SECOES))
    campos = pedido.get("campos")
    if not isinstance(campos, dict):
        erros.append("campos: objeto com os campos I a V")
    else:
        fora = sorted(set(campos) - set(CAMPOS))
        if fora:
            erros.append("campos fora da lista I a V: " + ", ".join(fora))
        for chave, valor in campos.items():
            if chave in CAMPOS and valor is not None and not isinstance(valor, str):
                erros.append(f"campos.{chave}: texto")
    return erros




def _achado(codigo: str, campo: str | None, severidade: str, mensagem: str, base: str) -> dict:
    return {"codigo": codigo, "campo": campo, "severidade": severidade, "mensagem": mensagem,
            "base": base}


def _itens(texto: str) -> list[str]:
    'O campo IV em itens: quebra de linha, ponto e vírgula e ponto final que não fecha'

    itens = []
    for bloco in re.split(r"[\n;]+", texto):
        atual = ""
        for pedaco in re.split(r"(?<=\.)\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ])", bloco):
            atual = (atual + " " + pedaco).strip() if atual else pedaco
            ultima = re.findall(r"([\wº.ª]+)\.$", atual)
            if ultima and ultima[0].lower().rstrip(".") in _ABREVIATURAS:
                continue
            itens.append(atual)
            atual = ""
        if atual:
            itens.append(atual)
    return [x.strip() for x in itens if x.strip()]


def _num(texto: str) -> str:
    return texto.replace(".", "")


def _chaves_de_precedente(texto: str) -> set[tuple[str, str]]:
    chaves = {("caso", _num(m.group(1))) for m in _CASO.finditer(texto)}
    chaves |= {("sumula", _num(m.group(1))) for m in _SUMULA.finditer(texto)}
    chaves |= {("tema", _num(m.group(1))) for m in _TEMA.finditer(texto)}
    return chaves


def _rotulo_da_chave(chave: tuple[str, str]) -> str:
    tipo, numero = chave
    return {"caso": "o julgado nº ", "sumula": "a Súmula ", "tema": "o Tema ",
            "art": "o art. "}[tipo] + numero


def _achados_do_campo_iv(texto: str) -> list[dict]:


    base = _in42("art. 3º, § 1º, IV", "2")
    if _NENHUM.match(texto):
        return []
    achados = []
    for item in _itens(texto):
        falta = []
        caso = _CASO.search(item) or _TEMA.search(item)
        if caso:
            if not _ORGAO.search(item):
                falta.append("o órgão julgador")
            if not _DATA_CITADA.search(item):
                falta.append("a data do julgamento")
        if _SUMULA.search(item) or _SUMULA_SEM_NUM.search(item):
            if not _TRIBUNAL.search(item):
                falta.append("o tribunal da súmula")
            if not _DATA_CITADA.search(item):
                falta.append("a data de aprovação da súmula")
        if _ENUNCIADO.search(item) or _ENUNCIADO_SEM_NUM.search(item):
            if not _ORGAO.search(item):
                falta.append("o órgão do enunciado")
            if not _DATA_CITADA.search(item):
                falta.append("a data do enunciado")
        if (_SUMULA_SEM_NUM.search(item) or _TEMA_SEM_NUM.search(item)
                or _ENUNCIADO_SEM_NUM.search(item)):
            falta.append("o número")
        if falta:
            achados.append(_achado(
                "precedente_incompleto", "IV", "corrigir",
                "No campo IV, «" + item[:120] + "» está sem " + ", ".join(falta) + ".", base))
    return achados


_MINIMO_REPETICAO = 600
_FRACAO_REPETICAO = 0.8


def _compacto(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip().lower()


def _repete_a_peca(campo: str, texto_peca: str) -> bool:
    'O campo copia a peça em frases inteiras (IN 42, art. 3º, § 2º: vedada "a repetição da'

    campo = _compacto(campo)
    if len(campo) < _MINIMO_REPETICAO:
        return False
    peca = _compacto(texto_peca)
    frases = [f for f in re.split(r"(?<=[.;:])\s+", campo) if len(f) >= 40]
    copiado = sum(len(f) for f in frases if f in peca)
    return copiado >= _FRACAO_REPETICAO * len(campo)


def _achados(pedido: dict, texto_peca: str | None) -> list[dict]:
    classe = pedido["classe"]
    campos = {k: (pedido["campos"].get(k) or "") for k in CAMPOS}
    exigidos = CAMPOS if classe == "recurso_especial" else CAMPOS[:4]
    achados = []
    for c in exigidos:
        if not campos[c].strip():
            achados.append(_achado(
                "campo_ausente", c, "corrigir",
                "O campo " + ROTULOS[c] + " está vazio. Todos os campos são preenchidos "
                "integralmente.", _in42("art. 3º, §§ 1º e 2º", "2-3")))
    if classe != "recurso_especial" and campos["V"].strip():
        achados.append(_achado(
            "campo_nao_aplicavel", "V", "aviso",
            "O campo V (relevância) só se aplica ao recurso especial e não vai para o anexo.",
            _in42("art. 3º, § 1º, V", "2")))
    for c in exigidos:
        if len(campos[c]) > EXTENSAO_RECOMENDADA_POR_CAMPO:
            achados.append(_achado(
                "campo_longo", c, "aviso",
                f"O campo {c} tem {len(campos[c])} caracteres; a extensão máxima recomendada é "
                f"de {EXTENSAO_RECOMENDADA_POR_CAMPO} por campo, contados os espaços, observado "
                "o limite global do sistema.", _in42("art. 3º, § 3º", "3")))
        if _REMISSAO.search(campos[c]):
            achados.append(_achado(
                "remissao_generica", c, "corrigir",
                f"O campo {c} remete à petição («{_REMISSAO.search(campos[c]).group(0)}»). O "
                "resumo diz o conteúdo, sem remissão genérica.", _in42("art. 3º, § 2º", "3")))
    ii = campos["II"]
    if ii.strip() and (not _ARTIGO.search(ii) or not _DIPLOMA.search(ii)):
        achados.append(_achado(
            "dispositivo_nao_individualizado", "II", "corrigir",
            "O campo II não individualiza os dispositivos de cada tese (diploma, artigo, "
            "parágrafo, inciso ou alínea).", _in42("art. 3º, § 1º, II", "2")))
    if campos["IV"].strip():
        achados += _achados_do_campo_iv(campos["IV"])
    if texto_peca is not None:
        for c in exigidos:
            if _repete_a_peca(campos[c], texto_peca):
                achados.append(_achado(
                    "repeticao_integral", c, "aviso",
                    f"O campo {c} repete a petição quase por inteiro. O resumo sintetiza: a "
                    "repetição da integralidade dos fundamentos é vedada.",
                    _in42("art. 3º, § 2º", "3")))
        base = _in42("arts. 3º, § 2º, e 4º", "3")
        no_resumo = set()
        for c in exigidos:
            no_resumo |= _chaves_de_precedente(campos[c])
        na_peca = _chaves_de_precedente(texto_peca)
        arts_resumo = {("art", _num(m.group(1))) for m in _ARTIGO.finditer(ii)}
        arts_peca = {("art", _num(m.group(1))) for m in _ARTIGO.finditer(texto_peca)}
        for chave in sorted((no_resumo - na_peca) | (arts_resumo - arts_peca)):
            achados.append(_achado(
                "divergencia_peca_resumo", "IV" if chave[0] != "art" else "II", "corrigir",
                "O resumo cita " + _rotulo_da_chave(chave) + ", que a peça não cita. O resumo "
                "retrata a petição; tire do resumo ou acrescente na peça.", base))
        for chave in sorted(na_peca - no_resumo):
            achados.append(_achado(
                "omissao_no_resumo", "IV", "aviso",
                "A peça cita " + _rotulo_da_chave(chave) + ", que o resumo não traz. Se a peça "
                "o invoca como aplicável, inclua-o no campo IV.", base))
    return achados




def _anexo(pedido: dict) -> str:
    campos = pedido["campos"]
    usados = CAMPOS if pedido["classe"] == "recurso_especial" else CAMPOS[:4]
    partes = ["RESUMO ESTRUTURADO (RISTJ, art. 343-A)",
              "Texto para o campo próprio do sistema de peticionamento, campo a campo.", ""]
    for c in usados:
        partes += [ROTULOS[c], (campos.get(c) or "").strip(), ""]
    return "\n".join(partes).rstrip("\n") + "\n"


def _travas(experimental_authorized: bool, hoje: dt.date, registro: Any) -> None:
    if experimental_authorized is not True:
        raise Resumo343AError(
            "capacidade_desabilitada",
            "A montagem do resumo do art. 343-A é experimental e exige autorização explícita "
            "nesta execução.")
    try:
        ficha_capacidade.exigir(CAPACIDADE, hoje=hoje, registro=registro)
    except ficha_capacidade.FichaRecusada as exc:
        raise Resumo343AError(exc.codigo, exc.mensagem) from None


def gerar(pedido: Any, *, texto_peca: str | None = None, hoje: dt.date | None = None,
          experimental_authorized: bool = False, registro_capacidades: Any = None,
          regime: Any = None) -> dict:
    'O anexo do resumo, os achados (a corrigir ou aviso) e o estado da exigência.'



    hoje = hoje or dt.date.today()
    _travas(experimental_authorized, hoje, registro_capacidades)
    erros = _validar_pedido(pedido)
    if erros:
        raise Resumo343AError("pedido_invalido", erros)
    destino = "origem" if pedido["classe"] in CLASSES_NA_ORIGEM else "stj"
    estado = estado_da_exigencia(hoje, regime, destino=destino, secao=pedido.get("secao"),
                                 tribunal=pedido.get("tribunal_origem") if destino == "origem"
                                 else None)
    achados = _achados(pedido, texto_peca)
    avisos = [RESPONSABILIDADE, estado["mensagem"]]
    if destino == "origem":
        avisos.append("No recurso especial, no agravo em recurso especial, no recurso ordinário "
                      "e no pedido de uniformização, o resumo é apresentado no ato da "
                      "interposição, no tribunal de origem (" + _in42("art. 3º, § 5º", "3")
                      + ").")
    return {
        "schema_version": VERSAO_SAIDA,
        "status": "MINUTA PARA REVISÃO",
        "capacidade": CAPACIDADE,
        "classe": pedido["classe"],
        "anexo": _anexo(pedido),
        "nome_sugerido": NOME_ANEXO,
        "achados": achados,
        "validado": not any(a["severidade"] == "corrigir" for a in achados),
        "bloqueia": False,
        "estado_da_exigencia": estado,
        "avisos": avisos,
        "fontes": {"conferidas": ["IN STJ/GP 42/2026, texto oficial (DJe 20/08/2026; "
                                  + IN42_OFICIAL + "), conferido em " + CONFERIDO_EM,
                                  NOTICIA_02092026],
                   "nao_conferido": "publicação das portarias do art. 12 da IN STJ/GP 42/2026 "
                                    "no DJe"},
    }


def gravar_anexo(resultado: dict, caminho: str) -> dict:
    """Grava o anexo em UTF-8 com LF e devolve {arquivo, sha256}."""
    dados = resultado["anexo"].replace("\r\n", "\n").encode("utf-8")
    with open(caminho, "wb") as arquivo:
        arquivo.write(dados)
    return {"arquivo": os.path.abspath(caminho), "sha256": hashlib.sha256(dados).hexdigest()}




class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Resumo343AError("pedido_invalido", message)


def _ler_json(caminho: str, codigo: str, o_que: str):
    try:
        with open(caminho, encoding="utf-8") as arquivo:
            return json.load(arquivo)
    except (OSError, UnicodeError, ValueError):
        raise Resumo343AError(codigo, o_que + " não pôde ser lido como JSON") from None


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(description="Resumo estruturado do art. 343-A do RISTJ, como anexo")
    sub = parser.add_subparsers(dest="comando", required=True, parser_class=_Parser)
    for nome in ("gerar", "validar"):
        p = sub.add_parser(nome)
        p.add_argument("--pedido", required=True)
        p.add_argument("--peca")
        p.add_argument("--regime")
        if nome == "gerar":
            p.add_argument("--saida")
    e = sub.add_parser("estado")
    e.add_argument("--destino", choices=("stj", "origem"), default="stj")
    e.add_argument("--secao", choices=SECOES)
    e.add_argument("--tribunal")
    e.add_argument("--regime")
    try:
        args = parser.parse_args(argv)
        regime = _ler_json(args.regime, "regime_invalido", "o regime") if args.regime else None
        if args.comando == "estado":
            saida = estado_da_exigencia(None, regime, destino=args.destino, secao=args.secao,
                                        tribunal=args.tribunal)
            print(json.dumps(dict(saida, ok=True), ensure_ascii=False, indent=2))
            return 0
        pedido = _ler_json(args.pedido, "pedido_invalido", "o pedido")
        texto = texto_da_peca(args.peca) if args.peca else None
        resultado = gerar(pedido, texto_peca=texto, regime=regime,
                          experimental_authorized=os.environ.get(CHAVE) == "1")
        if args.comando == "validar":
            resultado = {k: v for k, v in resultado.items() if k != "anexo"}
        elif args.saida:
            resultado["gravado"] = gravar_anexo(resultado, args.saida)
    except Resumo343AError as exc:
        print(json.dumps({"ok": False, "error_code": exc.code, "errors": exc.errors},
                         ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(dict(resultado, ok=True), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
