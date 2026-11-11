#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'ficha_capacidade.py — leitura única da ficha de uma capacidade no registro de capacidades.'




















from __future__ import annotations

import datetime as dt
import json
import os
import re

VERSAO_REGISTRO = "dsr.capacidades_juridicas.v1"
NOME_REGISTRO = "capacidades_juridicas.json"
CAMINHO_REGISTRO = "skills/dissero-orquestrador/scripts/" + NOME_REGISTRO
CODIGOS = (
    "registro_ausente", "registro_ilegivel", "ficha_ausente",
    "ficha_desligada", "ficha_sem_validade", "ficha_vencida",
)
_DATA = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
AQUI = os.path.dirname(os.path.abspath(__file__))



_FALTA_POR_ESTADO = {
    "aguardando_revisao": "A ficha aguarda a revisão e a assinatura do advogado responsável.",
    "experimental_desabilitada": "Ainda falta coletar a fonte oficial, com hash e vigência, e a "
                                 "assinatura do advogado responsável.",
}


class FichaRecusada(RuntimeError):
    """A ficha não deixa o motor rodar. `codigo` está em CODIGOS; `mensagem` diz o que fazer."""

    def __init__(self, codigo: str, mensagem: str):
        self.codigo = codigo
        self.mensagem = mensagem
        super().__init__(mensagem)


def _candidatos():
    'Onde o registro pode estar, a partir da pasta deste arquivo.'



    return (
        os.path.normpath(os.path.join(AQUI, os.pardir, os.pardir, "dissero-orquestrador",
                                      "scripts", NOME_REGISTRO)),
        os.path.normpath(os.path.join(AQUI, os.pardir, "skills", "dissero-orquestrador",
                                      "scripts", NOME_REGISTRO)),
    )


def localizar_registro() -> str | None:
    """Caminho do registro instalado, ou None quando nenhum candidato existe."""
    for caminho in _candidatos():
        if os.path.isfile(caminho):
            return caminho
    return None


def _ilegivel(detalhe: str) -> FichaRecusada:
    return FichaRecusada(
        "registro_ilegivel",
        "O registro de capacidades (%s) está ilegível: %s. Restaure o arquivo do plugin "
        "instalado e confira-o com validar_capacidades_juridicas.py. Até lá, nenhum motor com "
        "ficha roda." % (CAMINHO_REGISTRO, detalhe))


def ler_registro(registro=None) -> dict:
    """O registro como dict. `registro` pode ser o dict já lido, um caminho ou None (instalado)."""
    if isinstance(registro, dict):
        dados = registro
    else:
        caminho = localizar_registro() if registro is None else os.fspath(registro)
        if caminho is None or not os.path.isfile(caminho):
            raise FichaRecusada(
                "registro_ausente",
                "O registro de capacidades (%s) não foi encontrado. Reinstale o plugin. Sem o "
                "registro, nenhum motor com ficha roda." % CAMINHO_REGISTRO)
        try:
            with open(caminho, encoding="utf-8") as arquivo:
                dados = json.load(arquivo)
        except (OSError, UnicodeError, ValueError) as erro:
            raise _ilegivel("o JSON não pôde ser lido (%s)" % erro.__class__.__name__) from None
    if not isinstance(dados, dict) or dados.get("schema_version") != VERSAO_REGISTRO:
        raise _ilegivel("schema_version diferente de %s" % VERSAO_REGISTRO)
    if not isinstance(dados.get("capacidades"), list):
        raise _ilegivel("falta a lista `capacidades`")
    return dados


def _data(valor) -> dt.date | None:
    if not isinstance(valor, str) or not _DATA.match(valor):
        return None
    try:
        return dt.date.fromisoformat(valor)
    except ValueError:
        return None


def exigir(capacidade: str, *, hoje: dt.date | None = None, registro=None) -> dict:
    'Devolve a ficha de `capacidade` se ela deixa o motor rodar em `hoje`; senão, recusa.'


    if isinstance(hoje, dt.datetime):
        hoje = hoje.date()
    if hoje is None:
        hoje = dt.date.today()
    if not isinstance(hoje, dt.date):
        raise TypeError("hoje deve ser datetime.date")
    dados = ler_registro(registro)
    fichas = [x for x in dados["capacidades"] if isinstance(x, dict) and x.get("id") == capacidade]
    if len(fichas) > 1:
        raise _ilegivel("a ficha %s aparece %d vezes" % (capacidade, len(fichas)))
    if not fichas:
        raise FichaRecusada(
            "ficha_ausente",
            "A capacidade %s não tem ficha no registro de capacidades (%s). Restaure o "
            "registro do plugin instalado e confira-o com validar_capacidades_juridicas.py. Até "
            "lá, este motor não roda." % (capacidade, CAMINHO_REGISTRO))
    ficha = fichas[0]
    if ficha.get("enabled") is not True:
        falta = _FALTA_POR_ESTADO.get(ficha.get("estado"), "Falta a assinatura do advogado "
                                                           "responsável.")
        raise FichaRecusada(
            "ficha_desligada",
            "A ficha %s está desligada no registro de capacidades (%s). %s Para este motor "
            "rodar, o advogado responsável assina a ficha: fonte oficial, vigência, hash da "
            "fonte, revisor e `enabled: true`. Depois, confira a ficha com "
            "validar_capacidades_juridicas.py." % (capacidade, CAMINHO_REGISTRO, falta))
    fim = _data(ficha.get("valid_to"))
    if fim is None:
        raise FichaRecusada(
            "ficha_sem_validade",
            "A ficha %s está ligada sem data de validade válida (`valid_to`) no registro de "
            "capacidades (%s). O advogado responsável reassina a ficha com a validade. Até lá, "
            "este motor não roda." % (capacidade, CAMINHO_REGISTRO))
    if fim < hoje:
        raise FichaRecusada(
            "ficha_vencida",
            "A ficha %s venceu em %s (`valid_to`) no registro de capacidades (%s). O advogado "
            "responsável reassina a ficha: confere a fonte oficial e fixa a nova validade. Até "
            "lá, este motor não roda." % (capacidade, fim.strftime("%d/%m/%Y"), CAMINHO_REGISTRO))
    return ficha
