#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'normas_leg_br.py — o endpoint JSON do normas.leg.br, e as três minas que ele esconde.'










































































from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import date
from typing import Any, Callable, Iterator


ENGINE_VERSION = "dsr.normas_leg_br.engine.v1"
BASE = "https://normas.leg.br/api/public/normas"


TIPOS_DOCUMENTO = {
    "maior-detalhe": "árvore completa, com o texto nas folhas (4,2 MB para o CPC)",
    "simples": "somente metadado da norma, SEM hasPart (3,5 KB para o CPC)",
}



VERSOES_MEDIDAS = (
    "Original_Version", "Insertion_Version", "Text_Change_Version", "Court_Decision_Version",
    "Repeal_Version", "Text_Indirect_Change_Version", "Applicability_Suppression_Version",
    "Suppression_Version", "Renumbering_Version",
)
VERSOES_QUE_NAO_SAO_TEXTO_VIGENTE = ("Repeal_Version", "Suppression_Version")


VERSOES_COM_EFICACIA_A_CONFERIR = {
    "Applicability_Suppression_Version": (
        "indicada_com_aplicabilidade_suspensa",
        "pela linha do tempo da fonte, esta é a versão datada mais recente até a data, e ela "
        "registra SUSPENSÃO DA APLICABILIDADE do dispositivo; confira o ato de suspensão e o "
        "alcance dele na data antes de citar o texto como eficaz"),
    "Court_Decision_Version": (
        "indicada_por_decisao_judicial",
        "pela linha do tempo da fonte, esta é a versão datada mais recente até a data, e ela "
        "decorre de DECISÃO JUDICIAL sobre o dispositivo; confira a decisão (efeitos, modulação, "
        "trânsito) antes de citar o texto como eficaz"),
}


class NormasLegError(RuntimeError):
    def __init__(self, code: str, errors: list[str] | str):
        self.code = code
        self.errors = [errors] if isinstance(errors, str) else list(errors)
        super().__init__("; ".join(self.errors))


def montar_url(urn: Any, tipo_documento: str = "maior-detalhe") -> str:
    if not isinstance(urn, str) or not urn.startswith("urn:lex:"):
        raise NormasLegError("urn_invalida", "urn deve ser URN Lex começando por 'urn:lex:'")
    if "!" in urn:
        raise NormasLegError(
            "urn_de_dispositivo_nao_e_enderecavel",
            "URN com fragmento de dispositivo (!art…) NÃO é endereçável neste endpoint: ele devolve "
            "HTTP 200 ecoando a própria URN, sem texto, e um 200 que espelha o pedido tem cara de "
            "resposta. Baixe a norma inteira e use extrair_dispositivo()")
    if tipo_documento not in TIPOS_DOCUMENTO:
        raise NormasLegError(
            "tipo_documento_nao_medido",
            f"tipo_documento deve ser um de {sorted(TIPOS_DOCUMENTO)}: valor não medido devolve "
            "HTTP 200 com ZERO byte, e resposta vazia é indistinguível de norma sem conteúdo")
    return f"{BASE}?urn={urllib.parse.quote(urn, safe=':;-')}&tipo_documento={tipo_documento}"


def _buscar_http(url: str, *, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resposta:
        return resposta.read()


def baixar(urn: str, *, tipo_documento: str = "maior-detalhe",
           fetch: Callable[[str], bytes] | None = None) -> dict[str, Any]:
    """Baixa e valida. A guarda do corpo VAZIO é o coração deste módulo."""
    url = montar_url(urn, tipo_documento)
    bruto = (fetch or _buscar_http)(url)
    if not bruto:
        raise NormasLegError(
            "resposta_vazia_com_http_200",
            "a fonte devolveu HTTP 200 com corpo VAZIO. É assim que este endpoint responde a "
            "tipo_documento inválido: sem erro, sem aviso. Tratar isso como 'norma sem conteúdo' "
            "seria propagar o silêncio para dentro de uma peça")
    try:
        arvore = json.loads(bruto)
    except json.JSONDecodeError as exc:
        raise NormasLegError("resposta_nao_e_json", f"corpo não é JSON: {exc}") from exc
    if not isinstance(arvore, dict):
        raise NormasLegError("resposta_inesperada", "a raiz da resposta deveria ser objeto")
    if set(arvore) == {"urn"}:
        raise NormasLegError(
            "resposta_e_eco_da_entrada",
            f"a fonte devolveu apenas um eco da URN pedida ({arvore['urn']}), sem conteúdo")
    return arvore


def _andar(no: Any) -> Iterator[dict[str, Any]]:
    if isinstance(no, dict):
        yield no
        for valor in no.values():
            yield from _andar(valor)
    elif isinstance(no, list):
        for valor in no:
            yield from _andar(valor)


def extrair_dispositivo(arvore: dict[str, Any], sufixo: str) -> list[dict[str, Any]]:
    'Todas as versões de um dispositivo, cada uma com seu rótulo — NUNCA uma só.'






    if not isinstance(sufixo, str) or not sufixo.strip():
        raise NormasLegError("sufixo_invalido", "sufixo de dispositivo obrigatório (ex.: art1007_cpt)")
    alvo = "!" + sufixo.lstrip("!")
    versoes: list[dict[str, Any]] = []
    for no in _andar(arvore):
        ident = no.get("legislationIdentifier")
        if not isinstance(ident, str) or not ident.endswith(alvo):
            continue
        texto = no.get("text")
        if not isinstance(texto, str) or not texto.strip():
            continue


        natureza = no.get("legislationType")
        versoes.append({
            "urn": ident,
            "natureza": natureza if isinstance(natureza, str) else None,
            "data": no.get("legislationDate"),
            "texto": texto,
            "e_texto_vigente": None,
            "alerta": ("esta versão está rotulada como alteração/revogação — NÃO a cite como "
                       "redação vigente sem conferir a linha do tempo do dispositivo"
                       if isinstance(natureza, str) and natureza in VERSOES_QUE_NAO_SAO_TEXTO_VIGENTE
                       else None),
        })
    if not versoes:
        raise NormasLegError(
            "dispositivo_nao_encontrado",
            f"nenhum nó com texto termina em '{alvo}'. Confira o sufixo — o caput do art. 1.007 "
            "do CPC, por exemplo, é 'art1007_cpt' e não 'art1007'")
    return versoes


NAO_VERIFICAVEL = "redação na data não verificável"
RESSALVA_DATA = (
    "Indicação pela regra tempus regit actum, não escolha: a data de cada versão é a do ato que a "
    "introduziu, e o início da vigência (vacatio legis), a modulação de efeitos e a regra de "
    "transição ficam por conferir. A redação aplicável é decisão do advogado")
_RX_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RX_DATA_URN = re.compile(r"@(\d{4}-\d{2}-\d{2})")


def _data_iso(valor: Any) -> date | None:
    if not isinstance(valor, str) or not _RX_DATA.match(valor.strip()):
        return None
    try:
        return date.fromisoformat(valor.strip())
    except ValueError:
        return None


def _data_da_versao(versao: dict[str, Any]) -> date | None:
    """A data que a FONTE deu: `legislationDate`, ou o carimbo @AAAA-MM-DD da URN datada."""
    data = _data_iso(versao.get("data"))
    if data is None:
        m = _RX_DATA_URN.search(str(versao.get("urn") or ""))
        data = _data_iso(m.group(1)) if m else None
    return data


def indicar_redacao_na_data(versoes: list[dict[str, Any]], data_de_referencia: str) -> dict[str, Any]:
    'Qual versão cobria `data_de_referencia` pela linha do tempo da própria fonte.'






    ref = _data_iso(data_de_referencia)
    if ref is None:
        raise NormasLegError("data_de_referencia_invalida",
                             "data_de_referencia deve vir no formato AAAA-MM-DD (ex.: 2019-05-10)")
    saida: dict[str, Any] = {"data_de_referencia": ref.isoformat(), "regra": "tempus regit actum",
                             "versao_indicada": None, "versao_anterior": None,
                             "ressalva": RESSALVA_DATA}

    def nao_verificavel(codigo: str, motivo: str) -> dict[str, Any]:
        saida.update(situacao="nao_verificavel", motivo=codigo, mensagem=f"{NAO_VERIFICAVEL}: {motivo}")
        return saida

    if not versoes:
        return nao_verificavel("sem_versoes", "a fonte não deu versão nenhuma do dispositivo")
    datadas = [(_data_da_versao(v), i) for i, v in enumerate(versoes)]
    if any(d is None for d, _ in datadas):
        return nao_verificavel("versao_sem_data", "a fonte não dá a data de todas as versões do "
                               "dispositivo, então a linha do tempo não se ordena")
    anteriores = sorted((d, i) for d, i in datadas if d <= ref)
    if not anteriores:
        return nao_verificavel("data_anterior_a_toda_versao", "a data é anterior à primeira versão "
                               "que a fonte registra para o dispositivo")
    data_ult = anteriores[-1][0]
    mesmas = [i for d, i in anteriores if d == data_ult]
    if len({(versoes[i].get("natureza"), versoes[i].get("texto")) for i in mesmas}) > 1:
        return nao_verificavel("versoes_concorrentes_na_mesma_data", "a fonte registra mais de uma "
                               "versão do dispositivo na mesma data")
    indicada = versoes[mesmas[0]]
    if not isinstance(indicada.get("natureza"), str):
        return nao_verificavel("natureza_da_versao_ausente", "a fonte não diz de que tipo é a "
                               "versão daquela data (original, alteração, revogação)")
    previas = [(d, i) for d, i in anteriores if d < data_ult]
    saida["versao_indicada"] = {"indice": mesmas[0], "urn": indicada.get("urn"),
                                "data": data_ult.isoformat(), "natureza": indicada["natureza"]}
    if previas:


        data_ant, i_ant = previas[-1]
        anterior = versoes[i_ant]
        saida["versao_anterior"] = {"indice": i_ant, "urn": anterior.get("urn"),
                                    "data": data_ant.isoformat(),
                                    "natureza": anterior.get("natureza")}
    if indicada["natureza"] in VERSOES_QUE_NAO_SAO_TEXTO_VIGENTE:
        saida.update(situacao="sem_texto_na_data", motivo=None,
                     mensagem="pela linha do tempo da fonte, na data o dispositivo estava revogado "
                              "ou suprimido; confira o início da vigência do ato que o revogou")
    elif indicada["natureza"] in VERSOES_COM_EFICACIA_A_CONFERIR:
        situacao, mensagem = VERSOES_COM_EFICACIA_A_CONFERIR[indicada["natureza"]]
        saida.update(situacao=situacao, motivo=None, mensagem=mensagem)
    else:
        saida.update(situacao="indicada", motivo=None,
                     mensagem="pela linha do tempo da fonte, esta é a versão datada mais recente "
                              "até a data; confira o início da vigência antes de citá-la")
    return saida


def consultar(urn: str, sufixo: str | None = None, *, data_de_referencia: str | None = None,
              fetch: Callable[[str], bytes] | None = None) -> dict[str, Any]:
    if data_de_referencia is not None and not sufixo:
        raise NormasLegError("data_de_referencia_sem_dispositivo",
                             "data_de_referencia exige o dispositivo: a linha do tempo é por "
                             "dispositivo, não da norma inteira")
    if data_de_referencia is not None and _data_iso(data_de_referencia) is None:
        raise NormasLegError("data_de_referencia_invalida",
                             "data_de_referencia deve vir no formato AAAA-MM-DD (ex.: 2019-05-10)")
    arvore = baixar(urn, fetch=fetch)
    saida: dict[str, Any] = {
        "engine_version": ENGINE_VERSION,
        "estado": "MINUTA_PARA_REVISAO",
        "urn": urn,
        "fonte": montar_url(urn),
        "headline": arvore.get("headline"),
        "o_que_falta_decidir": [
            "QUAL VERSÃO VIGORA: este motor devolve todas as versões do dispositivo com seu "
            "rótulo e sua data, e não escolhe. Decidir qual redação vigora numa data é raciocínio "
            "jurídico-temporal, e escolher no escuro produz redação revogada citada como vigente",
        ],
    }
    if sufixo:
        versoes = extrair_dispositivo(arvore, sufixo)
        saida["dispositivo"] = {"sufixo": sufixo, "versoes": versoes}
        if data_de_referencia is not None:
            saida["dispositivo"]["na_data_de_referencia"] = indicar_redacao_na_data(
                versoes, data_de_referencia)
    return saida


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):
        raise NormasLegError("uso_invalido", message)


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(description="Consulta o endpoint JSON do normas.leg.br por URN Lex")
    parser.add_argument("--urn", required=True, help="URN Lex da norma (sem fragmento !art)")
    parser.add_argument("--dispositivo", help="sufixo do dispositivo, ex.: art1007_cpt")
    parser.add_argument("--data-referencia", dest="data_referencia",
                        help="AAAA-MM-DD do fato: indica a versão que cobria a data, sem escolher")
    try:
        args = parser.parse_args(argv)
        saida = consultar(args.urn, args.dispositivo, data_de_referencia=args.data_referencia)
    except NormasLegError as exc:
        print(json.dumps({"erro": exc.code, "detalhes": exc.errors}, ensure_ascii=False, indent=2))
        return 2
    except OSError as exc:
        print(json.dumps({"erro": "rede", "detalhes": [str(exc)]}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(saida, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
