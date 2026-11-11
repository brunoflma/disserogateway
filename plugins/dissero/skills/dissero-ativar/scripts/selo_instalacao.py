#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selo_instalacao.py: a prova de instalação que esta cópia do plugin manda ao Dissero.

Cada cópia baixada do Dissero traz, ao lado deste script, o arquivo `instalacao.json` (o
carimbo): o número da instalação e um segredo próprio dela. Este script lê o carimbo e imprime
SÓ a prova do dia (`<instalação>.<AAAAMMDD>.<código>`), que vai no argumento `prova` de toda
chamada a `carregar_recurso` e `listar_recursos`. O servidor aceita a prova de hoje e a de
ontem, no relógio UTC; vencida, gera-se de novo.

A cópia que chega pelo marketplace é igual para todas as contas e traz o carimbo de CANAL
(formato 2: `{"formato": 2, "canal": "mkt", "chave": ...}`), com a prova `mkt.<AAAAMMDD>.<código>`.
A chave do canal não é segredo: a prova só mostra que a conversa passou por este script; quem
confere a licença é o login no conector, a cada chamada.

O segredo nunca é impresso. Falha tem código de saída e frase próprios:
  3  carimbo ausente (cópia sem registro de instalação)
  4  carimbo ilegível (arquivo danificado ou fora da forma)
  5  carimbo de formato desconhecido (formato mais novo que este script)

Só biblioteca padrão, Python 3.9 ou mais novo. Uso: python scripts/selo_instalacao.py
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

FORMATO = 1
FORMATO_CANAL = 2
CANAL = "mkt"
CARIMBO = "instalacao.json"
RE_ID = re.compile(r"^ins_[A-Z2-7]{20}$")
RE_SEGREDO = re.compile(r"^[A-Za-z0-9_-]{43}$")
RE_PROVA = re.compile(r"^(ins_[A-Z2-7]{20})\.(\d{8})\.([A-Za-z0-9_-]{22})$")

SAIDA_AUSENTE = 3
SAIDA_ILEGIVEL = 4
SAIDA_FORMATO = 5

MSG_AUSENTE = ("CÓPIA DO PLUGIN SEM REGISTRO DE INSTALAÇÃO. Esta cópia não traz o arquivo que a identifica "
               "junto ao Dissero, e sem ele o método do plugin não é servido. Arquivo do plugin instalado à "
               "mão não traz esse registro. A cópia da banca se obtém pela ferramenta baixar_atualizacao do "
               "conector; no Claude Code, ela chega pelo canal da Dissero.")
MSG_ILEGIVEL = ("REGISTRO DE INSTALAÇÃO ILEGÍVEL. O arquivo que identifica esta cópia junto ao Dissero está "
                "danificado. A cópia precisa ser baixada de novo, pela ferramenta baixar_atualizacao; no "
                "Claude Code, ela chega pelo canal da Dissero.")
MSG_FORMATO = ("REGISTRO DE INSTALAÇÃO DE FORMATO DESCONHECIDO. O arquivo que identifica esta cópia é de um "
               "formato que este programa não lê. A cópia atual se obtém pela ferramenta baixar_atualizacao; "
               "no Claude Code, ela chega pelo canal da Dissero.")


class CarimboRuim(Exception):
    """Falha nomeada da leitura. Leva só o código: a mensagem nunca carrega conteúdo do carimbo."""

    def __init__(self, codigo):
        super().__init__(codigo)
        self.codigo = codigo


def _b64url(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados).rstrip(b"=").decode("ascii")


def _de_b64url(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def dia_utc(agora: datetime) -> str:
    return agora.astimezone(timezone.utc).strftime("%Y%m%d")


def ler_carimbo(caminho: Path) -> dict:
    """O carimbo conferido na forma, ou CarimboRuim com o código da falha."""
    if not caminho.is_file():
        raise CarimboRuim(SAIDA_ILEGIVEL if caminho.exists() else SAIDA_AUSENTE)
    try:
        dados = json.loads(caminho.read_bytes().decode("utf-8"))
    except Exception:
        raise CarimboRuim(SAIDA_ILEGIVEL) from None
    if not isinstance(dados, dict):
        raise CarimboRuim(SAIDA_ILEGIVEL)
    formato = dados.get("formato")
    if type(formato) is not int:
        raise CarimboRuim(SAIDA_ILEGIVEL)
    if formato == FORMATO_CANAL:
        canal, chave = dados.get("canal"), dados.get("chave")
        if not (canal == CANAL and isinstance(chave, str) and RE_SEGREDO.match(chave)):
            raise CarimboRuim(SAIDA_ILEGIVEL)
        try:
            if len(_de_b64url(chave)) != 32:
                raise ValueError
        except Exception:
            raise CarimboRuim(SAIDA_ILEGIVEL) from None
        return {"formato": formato, "canal": canal, "chave": chave}
    if formato != FORMATO:
        raise CarimboRuim(SAIDA_FORMATO)
    ident, chave, segredo = dados.get("instalacao"), dados.get("chave"), dados.get("segredo")
    if not (isinstance(ident, str) and RE_ID.match(ident) and type(chave) is int and chave >= 1
            and isinstance(segredo, str) and RE_SEGREDO.match(segredo)):
        raise CarimboRuim(SAIDA_ILEGIVEL)
    try:
        if len(_de_b64url(segredo)) != 32:
            raise ValueError
    except Exception:
        raise CarimboRuim(SAIDA_ILEGIVEL) from None
    return {"formato": formato, "instalacao": ident, "chave": chave, "segredo": segredo}


def gerar_prova(carimbo: dict, agora: datetime) -> str:
    """`<id>.<AAAAMMDD UTC>.<b64url dos 16 primeiros bytes do HMAC-SHA256>`, como o servidor confere."""
    dia = dia_utc(agora)
    if carimbo.get("formato") == FORMATO_CANAL:
        mac = hmac.new(_de_b64url(carimbo["chave"]), f"dissero-prova-canal|v1|{dia}".encode("utf-8"),
                       hashlib.sha256).digest()[:16]
        return f"{CANAL}.{dia}.{_b64url(mac)}"
    ident = carimbo["instalacao"]
    mac = hmac.new(_de_b64url(carimbo["segredo"]), f"dissero-prova|v1|{ident}|{dia}".encode("utf-8"),
                   hashlib.sha256).digest()[:16]
    return f"{ident}.{dia}.{_b64url(mac)}"


FRASES = {SAIDA_AUSENTE: MSG_AUSENTE, SAIDA_ILEGIVEL: MSG_ILEGIVEL, SAIDA_FORMATO: MSG_FORMATO}





FOLGA_RELOGIO = timedelta(minutes=15)


def prova_de_agora(carimbo: dict, agora: datetime) -> str:
    """A prova que o script imprime: a do dia de `agora - FOLGA_RELOGIO`, em UTC."""
    return gerar_prova(carimbo, agora - FOLGA_RELOGIO)


def main(argv=None) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8")
        except Exception:
            pass
    argv = sys.argv[1:] if argv is None else argv
    if argv in (["--help"], ["-h"]):
        print((__doc__ or "").strip())
        return 0
    if argv:
        print("uso: python scripts/selo_instalacao.py (sem argumentos)", file=sys.stderr)
        return 2
    try:
        carimbo = ler_carimbo(Path(__file__).resolve().parent / CARIMBO)
    except CarimboRuim as e:
        print(FRASES[e.codigo], file=sys.stderr)
        return e.codigo
    print(prova_de_agora(carimbo, datetime.now(timezone.utc)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
