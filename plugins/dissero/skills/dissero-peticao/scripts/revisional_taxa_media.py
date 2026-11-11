#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'Comparação determinística da taxa contratada com a taxa média do Banco Central.'



































from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from typing import Any, Mapping

try:
    import bcb_sgs_adapter
except ImportError:
    from . import bcb_sgs_adapter
try:
    import ficha_capacidade
except ImportError:
    from . import ficha_capacidade


CAPACIDADE = "revisional_taxa_media"
VERSAO_MOTOR = "dsr.revisional_taxa_media.motor.v1"
VERSAO_PEDIDO = "dsr.revisional_taxa_media.pedido.v1"
VERSAO_MEMORIA = "dsr.revisional_taxa_media.memoria.v1"
FAMILIA_TAXA_MEDIA = "taxa_media_juros_recursos_livres"
UNIDADE_MENSAL = "percentual ao mês"
CODIGOS = (
    "capacidade_desabilitada", "pedido_invalido", "snapshot_ausente", "hash_divergente",
    "snapshot_invalido", "catalogo_series_indisponivel", "serie_nao_e_taxa_media",
    "serie_unidade_incompativel", "modalidade_divergente", "mes_divergente",
    "taxas_incoerentes",
) + ficha_capacidade.CODIGOS
_CHAVES_PEDIDO = {"schema_version", "modalidade", "mes_contratacao", "taxa_contratada",
                  "base_da_comparacao", "snapshot_path", "snapshot_sha256"}
_CHAVES_TAXA = {"mensal_percentual", "anual_percentual"}
_DECIMAL = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_MES = re.compile(r"^[0-9]{4}-(?:0[1-9]|1[0-2])$")
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_MODALIDADE = re.compile(r"^[a-z0-9_]{3,80}$")
_PRECISAO = 50
_CASAS = Decimal("0.0001")
_CASAS_MEMORIA = Decimal("0.0000000001")
_MEIA_UNIDADE_PISO = Decimal("0.005")


_TETO_MENSAL = Decimal("100")
_TETO_ANUAL = Decimal("409500")




MARCADOR_CRITERIO = ("==[JURISPRUDÊNCIA A CONFERIR — tese: critério de comparação da taxa "
                     "contratada com a taxa média de mercado]==")

LIMITES = (
    "A comparação não afirma abusividade. Esse juízo é do advogado, à vista do caso concreto, e "
    "a prova é do perito.",
    "Não há projeção de indébito, de prestação revisada nem de saldo. Esses números vêm do "
    "parecer do assistente técnico contador e, em juízo, da perícia.",
    "Nenhum limiar de abusividade está embutido no cálculo. Critério de tribunal, se o advogado "
    "quiser citá-lo, entra na peça como " + MARCADOR_CRITERIO + " e passa pela pesquisa.",
)


class RevisionalError(RuntimeError):
    def __init__(self, code: str, errors: list[str] | str):
        self.code = code
        self.errors = [errors] if isinstance(errors, str) else list(errors)
        super().__init__("; ".join(self.errors))




def _anual_de_mensal(mensal: Decimal) -> Decimal:
    """Taxa ao ano equivalente composta, em percentual: ((1 + m)^12 - 1)."""
    with localcontext() as ctx:
        ctx.prec = _PRECISAO
        return ((Decimal(1) + mensal / 100) ** 12 - 1) * 100


def _mensal_de_anual(anual: Decimal) -> Decimal:
    """Taxa ao mês equivalente composta, em percentual: ((1 + a)^(1/12) - 1)."""
    with localcontext() as ctx:
        ctx.prec = _PRECISAO
        return ((Decimal(1) + anual / 100) ** (Decimal(1) / Decimal(12)) - 1) * 100


def _meia_unidade(texto: str) -> Decimal:
    """Meia unidade da última casa escrita: a precisão com que a taxa foi declarada."""
    casas = len(texto.split(".", 1)[1]) if "." in texto else 0
    return Decimal(5) / (Decimal(10) ** (casas + 1))


def _meia_unidade_mensal(texto: str) -> Decimal:
    'Precisão da taxa MENSAL: a escrita sem casas decimais vale como de duas casas ("2" é'


    return min(_meia_unidade(texto), _MEIA_UNIDADE_PISO)


def _proporcao_simples(mensal_txt: str, anual_txt: str) -> bool:
    """A anual declarada é doze vezes a mensal, dentro da precisão de escrita das duas."""
    return abs(Decimal(mensal_txt) * 12 - Decimal(anual_txt)) <= (
        _meia_unidade_mensal(mensal_txt) * 12 + _meia_unidade(anual_txt))


def _compativeis(mensal_txt: str, anual_txt: str) -> bool:
    'A anual declarada cabe na equivalente composta da mensal declarada, consideradas as duas'



    m, a = Decimal(mensal_txt), Decimal(anual_txt)
    dm, da = _meia_unidade_mensal(mensal_txt), _meia_unidade(anual_txt)
    menor = _anual_de_mensal(max(m - dm, Decimal(0)))
    maior = _anual_de_mensal(m + dm)
    if not (maior >= a - da and menor <= a + da):
        return False
    if _proporcao_simples(mensal_txt, anual_txt):
        return abs(_anual_de_mensal(m) - a) <= da
    return True


def _q(valor: Decimal, casas: Decimal = _CASAS) -> str:
    with localcontext() as ctx:
        ctx.prec = _PRECISAO
        return str(valor.quantize(casas, rounding=ROUND_HALF_EVEN))


def _br(valor: Decimal, casas: Decimal = _CASAS) -> str:
    return _q(valor, casas).replace(".", ",")




def _validar_pedido(pedido: Any) -> list[str]:
    if not isinstance(pedido, Mapping):
        return ["o pedido deve ser um objeto JSON"]
    erros = []
    sobrando = sorted(set(pedido) - _CHAVES_PEDIDO)
    if sobrando:
        erros.append("campo(s) não previsto(s) no pedido: " + ", ".join(sobrando))
    if pedido.get("schema_version") != VERSAO_PEDIDO:
        erros.append(f"schema_version deve ser {VERSAO_PEDIDO}")
    if not isinstance(pedido.get("modalidade"), str) or not _MODALIDADE.match(pedido["modalidade"]):
        erros.append("modalidade deve ser a chave do catálogo da casa "
                     "(ex.: pf_credito_pessoal_nao_consignado)")
    if not isinstance(pedido.get("mes_contratacao"), str) or not _MES.match(pedido["mes_contratacao"]):
        erros.append("mes_contratacao deve estar no formato AAAA-MM")
    taxa = pedido.get("taxa_contratada")
    if not isinstance(taxa, Mapping) or not taxa:
        erros.append("taxa_contratada deve trazer mensal_percentual, anual_percentual ou as duas")
    else:
        sobra = sorted(set(taxa) - _CHAVES_TAXA)
        if sobra:
            erros.append("campo(s) não previsto(s) em taxa_contratada: " + ", ".join(sobra))
        presentes = [c for c in ("mensal_percentual", "anual_percentual") if c in taxa]
        if not presentes:
            erros.append("taxa_contratada deve trazer mensal_percentual, anual_percentual ou as duas")
        for campo in presentes:
            valor = taxa[campo]
            if not isinstance(valor, str) or not _DECIMAL.match(valor):
                erros.append(f"taxa_contratada.{campo} deve ser texto decimal com ponto "
                             "(ex.: \"3.50\"), sem sinal de percentual")
            elif Decimal(valor) <= 0:
                erros.append(f"taxa_contratada.{campo} deve ser maior que zero")
            elif Decimal(valor) > (_TETO_MENSAL if campo == "mensal_percentual" else _TETO_ANUAL):
                erros.append(f"taxa_contratada.{campo} ({valor}) passa do teto de plausibilidade "
                             "(100% ao mês, ou o equivalente composto ao ano); confira a "
                             "digitação, sem sinal de percentual (ex.: \"3.50\")")
    base = pedido.get("base_da_comparacao")
    if base is not None:
        if base not in ("mensal", "anual"):
            erros.append("base_da_comparacao deve ser mensal ou anual")
        elif isinstance(taxa, Mapping) and f"{base}_percentual" not in taxa:
            erros.append(f"base_da_comparacao {base} exige taxa_contratada.{base}_percentual")
    caminho = pedido.get("snapshot_path")
    if caminho is not None and (not isinstance(caminho, str) or not caminho.strip()):
        erros.append("snapshot_path deve ser o caminho do arquivo do snapshot")
    sha = pedido.get("snapshot_sha256")
    if sha is not None and (not isinstance(sha, str) or not _SHA256.match(sha)):
        erros.append("snapshot_sha256 deve ter 64 dígitos hexadecimais")
    return erros


def _ler_snapshot(pedido: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    caminho = pedido.get("snapshot_path")
    if not caminho or not os.path.isfile(caminho):
        raise RevisionalError(
            "snapshot_ausente",
            "Falta o snapshot da série de taxa média do mês da contratação. Capture-o com o "
            "bcb_sgs_adapter.py (start_period e end_period iguais ao mês da contratação) e informe "
            "snapshot_path e snapshot_sha256 no pedido.")
    if not pedido.get("snapshot_sha256"):
        raise RevisionalError("pedido_invalido", "snapshot_sha256 é obrigatório com o snapshot")
    with open(caminho, "rb") as arquivo:
        bruto = arquivo.read()
    hash_lido = hashlib.sha256(bruto).hexdigest()
    if hash_lido.casefold() != pedido["snapshot_sha256"].casefold():
        raise RevisionalError(
            "hash_divergente",
            "O sha256 do snapshot não confere com o informado no pedido: o arquivo mudou depois "
            "de registrado, ou o pedido aponta outro arquivo.")
    try:
        snapshot = json.loads(bruto.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise RevisionalError("snapshot_invalido", "o snapshot não é JSON legível") from None
    if not isinstance(snapshot, dict):
        raise RevisionalError("snapshot_invalido", "o snapshot deve ser um objeto JSON")
    return snapshot, hash_lido


def _conferir_serie(snapshot: Mapping[str, Any], modalidade: str) -> Mapping[str, Any]:
    """A série do snapshot é de taxa média, ao mês, e da modalidade declarada."""
    serie = snapshot.get("series_id")
    if not isinstance(serie, int) or isinstance(serie, bool):
        raise RevisionalError("snapshot_invalido", "o snapshot não traz series_id numérico")
    try:
        catalogo = bcb_sgs_adapter._catalogo_series()
    except bcb_sgs_adapter.AdapterError as exc:
        raise RevisionalError("catalogo_series_indisponivel", str(exc)) from None
    entrada = catalogo.get(str(serie))
    if not isinstance(entrada, Mapping) or entrada.get("familia") != FAMILIA_TAXA_MEDIA:
        raise RevisionalError(
            "serie_nao_e_taxa_media",
            f"A série {serie} não está no catálogo da casa como taxa média de juros por "
            "modalidade. A comparação só se faz contra a taxa média do Banco Central da mesma "
            "modalidade; escolha a série na tabela do roteiro da revisional.")
    if entrada.get("unidade") != UNIDADE_MENSAL:
        par = entrada.get("par_na_outra_unidade")
        raise RevisionalError(
            "serie_unidade_incompativel",
            f"A série {serie} é a taxa média em {entrada.get('unidade')}. O motor compara na "
            "série ao mês e converte a taxa anual do contrato por equivalência composta"
            + (f"; use a série {par}." if par else "."))
    if entrada.get("modalidade") != modalidade:
        raise RevisionalError(
            "modalidade_divergente",
            f"A série {serie} é da modalidade {entrada.get('modalidade')}, e o pedido declara "
            f"{modalidade}. Confira a modalidade do contrato e a série escolhida.")
    return entrada


def _nome_legivel(serie: Mapping[str, Any], snapshot: Mapping[str, Any]) -> str:
    'Nome da série como o Banco Central a declara, para a memória que vai ao advogado. A'

    for nome in (serie.get("nome_declarado"), snapshot.get("series_name")):
        if isinstance(nome, str) and nome.strip():
            return nome.strip()
    return "taxa média da modalidade"


def _taxa_media_do_mes(snapshot: Mapping[str, Any], mes: str) -> Decimal:
    periodo = mes + "-01"
    cobertura = snapshot.get("coverage") or {}
    inicio, fim = cobertura.get("requested_start"), cobertura.get("requested_end")
    if inicio != periodo or fim != periodo:
        raise RevisionalError(
            "mes_divergente",
            f"O snapshot cobre de {str(inicio)[:7]} a {str(fim)[:7]}, e a contratação é de {mes}. "
            "A comparação usa a taxa média de um mês só, o da contratação: capture o snapshot "
            "com start_period e end_period iguais a esse mês.")
    pontos = [p for p in snapshot.get("points") or [] if isinstance(p, Mapping)
              and p.get("period") == periodo]
    if len(pontos) != 1:
        raise RevisionalError("snapshot_invalido", f"o snapshot não traz um valor único para {mes}")
    valor = Decimal(str(pontos[0]["value"]))
    if valor <= 0:
        raise RevisionalError("snapshot_invalido",
                              f"a taxa média de {mes} no snapshot não é positiva ({valor})")
    return valor




def calcular(pedido: Any, *, hoje: dt.date | None = None, experimental_authorized: bool = False,
             registro_capacidades: Any = None) -> dict[str, Any]:
    'Memória da comparação; desabilitado por padrão.'



    if experimental_authorized is not True:
        raise RevisionalError(
            "capacidade_desabilitada",
            "A comparação com a taxa média é experimental e exige autorização explícita nesta "
            "execução.")
    hoje = hoje or dt.date.today()
    try:
        ficha_capacidade.exigir(CAPACIDADE, hoje=hoje, registro=registro_capacidades)
    except ficha_capacidade.FichaRecusada as exc:
        raise RevisionalError(exc.codigo, exc.mensagem) from None
    erros = _validar_pedido(pedido)
    if erros:
        raise RevisionalError("pedido_invalido", erros)
    snapshot, hash_snapshot = _ler_snapshot(pedido)
    serie = _conferir_serie(snapshot, pedido["modalidade"])
    erros = bcb_sgs_adapter.validar_snapshot(snapshot, hoje=hoje)
    if erros:
        raise RevisionalError("snapshot_invalido", erros)
    mes = pedido["mes_contratacao"]
    media_m = _taxa_media_do_mes(snapshot, mes)

    taxa = pedido["taxa_contratada"]
    mensal_txt, anual_txt = taxa.get("mensal_percentual"), taxa.get("anual_percentual")
    base = pedido.get("base_da_comparacao")
    avisos: list[str] = []
    memoria: list[str] = []
    if mensal_txt and anual_txt:
        conferida = _compativeis(mensal_txt, anual_txt)
        composta = _anual_de_mensal(Decimal(mensal_txt))
        if not conferida:
            relacao = (f"A taxa anual declarada ({_br(Decimal(anual_txt))}%) não é a equivalente "
                       f"composta da mensal declarada ({_br(Decimal(mensal_txt))}% ao mês, que "
                       f"equivale a {_br(composta)}% ao ano)")
            if _proporcao_simples(mensal_txt, anual_txt):
                relacao += "; ela corresponde a doze vezes a mensal, por proporção simples"
            if base is None:
                raise RevisionalError(
                    "taxas_incoerentes",
                    relacao + ". O motor não escolhe qual das duas vale: declare "
                    "base_da_comparacao (mensal ou anual), ou informe só a taxa a comparar.")
            avisos.append(relacao + f". A comparação usa a taxa {base}, por declaração do "
                          "advogado no pedido.")
        memoria.append(
            "Equivalência composta conferida entre a taxa mensal e a anual declaradas: "
            + ("confere, dentro da precisão com que foram escritas." if conferida
               else "não confere (ver avisos)."))
    else:
        base = "mensal" if mensal_txt else "anual"
    if base is None:
        base = "mensal"

    if base == "mensal":
        contr_m = Decimal(mensal_txt)
        contr_a = _anual_de_mensal(contr_m)
        memoria.append(f"Taxa contratada ao mês, como declarada: {_br(contr_m)}%.")
        memoria.append(f"Taxa contratada ao ano, equivalente composta ((1 + m)^12 - 1): "
                       f"{_br(contr_a, _CASAS_MEMORIA)}%.")
    else:
        contr_a = Decimal(anual_txt)
        contr_m = _mensal_de_anual(contr_a)
        memoria.append(f"Taxa contratada ao ano, como declarada: {_br(contr_a)}%.")
        memoria.append(f"Taxa contratada ao mês, equivalente composta ((1 + a)^(1/12) - 1): "
                       f"{_br(contr_m, _CASAS_MEMORIA)}%.")
    media_a = _anual_de_mensal(media_m)
    memoria.append(f"Taxa média do Banco Central em {mes[5:]}/{mes[:4]}, série "
                   f"{snapshot['series_id']} ({_nome_legivel(serie, snapshot)}): {_br(media_m)}% ao mês.")
    memoria.append(f"Taxa média ao ano, equivalente composta: {_br(media_a, _CASAS_MEMORIA)}%.")
    with localcontext() as ctx:
        ctx.prec = _PRECISAO
        razao_m = contr_m / media_m
        razao_a = contr_a / media_a
        desvio_m = contr_m - media_m
        desvio_a = contr_a - media_a
    memoria.append(f"Razão ao mês (contratada / média): {_br(contr_m, _CASAS_MEMORIA)} / "
                   f"{_br(media_m)} = {_br(razao_m)}.")
    memoria.append(f"Desvio ao mês: {_br(desvio_m)} ponto(s) percentual(is).")
    memoria.append(f"Razão ao ano (equivalentes compostas): {_br(razao_a)}; desvio ao ano: "
                   f"{_br(desvio_a)} ponto(s) percentual(is).")
    memoria.append("Arredondamento só na apresentação: quatro casas, meia unidade para o par "
                   "(arredondamento bancário); as contas correm com 50 dígitos significativos.")

    return {
        "schema_version": VERSAO_MEMORIA,
        "status": "MINUTA PARA REVISÃO",
        "capacidade": CAPACIDADE,
        "motor": VERSAO_MOTOR,
        "modalidade": pedido["modalidade"],
        "mes_contratacao": mes,
        "serie": {
            "series_id": snapshot["series_id"],
            "series_name": snapshot.get("series_name"),
            "unidade": UNIDADE_MENSAL,
            "snapshot_sha256": hash_snapshot,
            "source_url": snapshot.get("source_url"),
            "source_response_sha256": snapshot.get("source_response_sha256"),
            "retrieved_at": snapshot.get("retrieved_at"),
        },
        "taxa_contratada": {
            "declarada": {k: taxa[k] for k in ("mensal_percentual", "anual_percentual") if k in taxa},
            "base_da_comparacao": base,
            "mensal_percentual": _q(contr_m),
            "anual_percentual": _q(contr_a),
        },
        "taxa_media": {"mensal_percentual": _q(media_m), "anual_percentual": _q(media_a)},
        "comparacao": {
            "razao_mensal": _q(razao_m),
            "desvio_mensal_pontos_percentuais": _q(desvio_m),
            "razao_anual": _q(razao_a),
            "desvio_anual_pontos_percentuais": _q(desvio_a),
        },
        "memoria": memoria,
        "avisos": avisos,
        "limites": list(LIMITES),
    }


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise RevisionalError("pedido_invalido", message)


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(description="Comparação da taxa contratada com a taxa média do Banco Central")
    parser.add_argument("--pedido", required=True, help="caminho do JSON do pedido")
    try:
        args = parser.parse_args(argv)
        try:
            with open(args.pedido, encoding="utf-8") as arquivo:
                pedido = json.load(arquivo)
        except (OSError, UnicodeError, ValueError):
            raise RevisionalError("pedido_invalido", "o pedido não pôde ser lido como JSON") from None
        autorizado = os.environ.get("DSR_REVISIONAL_EXPERIMENTAL") == "1"
        memoria = calcular(pedido, experimental_authorized=autorizado)
    except RevisionalError as exc:
        print(json.dumps({"ok": False, "error_code": exc.code, "errors": exc.errors,
                          "status": "INCONCLUSIVO"}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps({"ok": True, "memoria": memoria}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
