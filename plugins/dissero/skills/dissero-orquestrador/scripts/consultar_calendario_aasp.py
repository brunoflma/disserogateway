#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'consultar_calendario_aasp.py - aponta o ato oficial do calendário forense de um tribunal.'















































from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import re
import socket
import ssl
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from html.parser import HTMLParser

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

SCHEMA = "dsr.calendario_aasp.consulta.v1"
URL_ANO = "https://www.aasp.org.br/produtos-servicos/expediente-forense/feriados-forenses-{ano}/"
HOST_AASP = "www.aasp.org.br"
TIMEOUT = 30
VALIDADE_CACHE_S = 24 * 3600
ENV_CACHE = "DSR_CALENDARIO_AASP_CACHE"
USER_AGENT = ("Dissero (plugin juridico do escritorio; calendario forense: "
              "leitura do indice anual da AASP)")


SUFIXOS_OFICIAIS = (".jus.br", ".gov.br", ".leg.br", ".mp.br", ".def.br")


MINIMO_LINHAS = 20
SITUACOES = ("publicado", "nao_divulgado", "sem_pagina_do_ano", "tribunal_ausente")

AVISO = ("O índice da AASP se declara de caráter meramente supletivo: o que vale é o ato do "
         "tribunal. Abra o ato, confira cada data nele e só então passe a data ao "
         "calcular_prazo.py com --feriado AAAA-MM-DD.")
PROXIMO_PASSO = {
    "publicado": ("Abra o ato pelo link e leia os feriados, pontos facultativos e suspensões de "
                  "expediente do ano. Passe cada dia ao calcular_prazo.py com --feriado "
                  "AAAA-MM-DD. Link com alerta se confere no site do tribunal antes de usar."),
    "nao_divulgado": ("O tribunal não divulgou o calendário do ano em meio oficial. Calcule com o "
                      "que o motor cobre e declare a lacuna. Escale ao advogado antes de "
                      "protocolar."),
    "sem_pagina_do_ano": ("A AASP não tem página do índice para este ano. Se ela publicou o ano "
                          "em outro endereço, rode de novo com --url. Sem índice, calcule com o "
                          "que o motor cobre, declare a lacuna e escale ao advogado antes de "
                          "protocolar."),
    "tribunal_ausente": ("O índice do ano não tem esse tribunal. Confira a sigla em "
                         "`tribunais_no_indice` e rode de novo. Sem ato, declare a lacuna e "
                         "escale ao advogado antes de protocolar."),
}

_RX_SIGLA = re.compile(r"^[A-Z]{2,5}(-\d{1,2})?$")
_RX_ATUALIZADO = re.compile(r"Atualizado em\s+([^\n]+)")
_RX_SUPLETIVO = re.compile(r"car[aá]ter meramente supletivo", re.IGNORECASE)


_urlopen = urllib.request.urlopen


class NaoConsultado(RuntimeError):
    """Não deu para ler o índice. Nunca se confunde com 'o tribunal não tem feriado'."""

    def __init__(self, codigo: str, mensagem: str):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem


def _espaco(texto: str) -> str:
    return re.sub(r"\s+", " ", texto or "").strip()


def _achatar(texto: str) -> str:
    """Minúsculas sem acento, para comparar texto de página sem depender de diacrítico."""
    return "".join(c for c in unicodedata.normalize("NFKD", texto or "")
                   if not unicodedata.combining(c)).lower()


def chave_tribunal(sigla: str) -> str:
    """Forma de comparação da sigla: 'trt 02', 'TRT-2' e 'TRT2' dão 'TRT2'; 'TJ-SP' dá 'TJSP'."""
    k = re.sub(r"[^A-Z0-9]", "", str(sigla or "").upper())
    return re.sub(r"(?<=[A-Z])0+(?=\d)", "", k)


def _contexto_tls() -> ssl.SSLContext:
    """Contexto padrão: certificado e nome do host verificados."""
    return ssl.create_default_context()


def _dir_cache() -> str:
    return os.environ.get(ENV_CACHE) or os.path.join(
        os.path.expanduser("~"), ".config", "dissero", "calendario-aasp")


def _caminhos_cache(ano: int) -> tuple[str, str]:
    base = os.path.join(_dir_cache(), "feriados-forenses-%d" % ano)
    return base + ".html", base + ".json"


def _ler_cache(ano: int, url: str, agora: float) -> dict | None:
    """A página do ano guardada há menos de 24 horas para a mesma URL, ou None."""
    html_p, meta_p = _caminhos_cache(ano)
    try:
        with open(meta_p, encoding="utf-8") as fh:
            meta = json.load(fh)
        with open(html_p, "rb") as fh:
            corpo = fh.read()
    except (OSError, ValueError):
        return None
    if meta.get("url") != url or hashlib.sha256(corpo).hexdigest() != meta.get("sha256"):
        return None
    coletado = meta.get("coletado_em_epoch")
    if not isinstance(coletado, (int, float)) or not 0 <= agora - coletado < VALIDADE_CACHE_S:
        return None
    try:
        texto = corpo.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return {"html": texto, "url": url, "origem": "cache", "sha256": meta["sha256"],
            "coletado_em": meta.get("coletado_em")}


def _gravar_cache(ano: int, pagina: dict, agora: float) -> None:
    """Grava a página lida. Falha de disco não derruba a consulta: o cache só poupa rede."""
    html_p, meta_p = _caminhos_cache(ano)
    try:
        os.makedirs(os.path.dirname(html_p), exist_ok=True)
        with open(html_p, "wb") as fh:
            fh.write(pagina["html"].encode("utf-8"))
        with open(meta_p, "w", encoding="utf-8") as fh:
            json.dump({"url": pagina["url"], "sha256": pagina["sha256"],
                       "coletado_em": pagina["coletado_em"], "coletado_em_epoch": agora},
                      fh, ensure_ascii=False)
    except OSError:
        pass


def _baixar(url: str) -> tuple[int, str, bytes]:
    """(status, URL final, corpo). 404 volta como status; o resto que não é 200 é erro nomeado."""
    pedido = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                  "Accept": "text/html"})
    try:
        with _urlopen(pedido, timeout=TIMEOUT, context=_contexto_tls()) as resposta:
            return resposta.status, resposta.geturl(), resposta.read()
    except urllib.error.HTTPError as erro:
        if erro.code == 404:
            return 404, url, b""
        raise NaoConsultado("resposta_http_inesperada",
                            "A AASP respondeu HTTP %s para %s. Tente de novo mais tarde. Até lá o "
                            "calendário do tribunal fica sem fonte: escale ao advogado."
                            % (erro.code, url))
    except urllib.error.URLError as erro:
        if isinstance(erro.reason, ssl.SSLCertVerificationError):
            raise NaoConsultado("certificado_nao_validado", _msg_certificado(url, erro.reason))
        raise NaoConsultado("rede_indisponivel", _msg_rede(url, erro.reason))
    except ssl.SSLCertVerificationError as erro:
        raise NaoConsultado("certificado_nao_validado", _msg_certificado(url, erro))
    except (TimeoutError, socket.timeout, OSError) as erro:
        raise NaoConsultado("rede_indisponivel", _msg_rede(url, erro))
    except http.client.HTTPException as erro:


        raise NaoConsultado("rede_indisponivel",
                            _msg_rede(url, "%s: %s" % (type(erro).__name__, erro)))


def _msg_certificado(url: str, erro) -> str:
    return ("O certificado TLS de %s não foi validado (%s). A consulta não segue sem validação. "
            "Atualize os certificados do sistema ou do Python e rode de novo." % (url, erro))


def _msg_rede(url: str, erro) -> str:
    return ("Não foi possível alcançar %s (%s). Confira a conexão e rode de novo. Sem o índice, "
            "o calendário do tribunal fica sem fonte: escale ao advogado." % (url, erro))


def _msg_falha_inesperada(erro: Exception) -> str:
    return ("A consulta ao índice da AASP parou num erro não previsto (%s: %s). Rode de novo. Se "
            "repetir, o calendário do tribunal fica sem fonte: escale ao advogado."
            % (type(erro).__name__, erro))


def _mesma_pagina(pedida: str, final: str) -> bool:
    a, b = urllib.parse.urlsplit(pedida), urllib.parse.urlsplit(final or pedida)
    return (b.hostname or "").lower() == HOST_AASP and a.path.rstrip("/") == b.path.rstrip("/")


def obter_pagina(ano: int, url: str | None = None, atualizar: bool = False,
                 agora: float | None = None) -> dict:
    """A página do ano: do cache válido ou da rede. `html` None quando não há página do ano."""
    url = url or URL_ANO.format(ano=ano)
    agora = time.time() if agora is None else agora
    if not atualizar:
        guardada = _ler_cache(ano, url, agora)
        if guardada:
            return guardada
    status, final, corpo = _baixar(url)
    coletado = datetime.fromtimestamp(agora, timezone.utc).isoformat(timespec="seconds")
    if status == 404:
        return {"html": None, "url": url, "origem": "rede", "coletado_em": coletado,
                "motivo": "a AASP respondeu 404 para o endereço do ano"}
    if not _mesma_pagina(url, final):
        return {"html": None, "url": url, "origem": "rede", "coletado_em": coletado,
                "motivo": "o endereço do ano levou a outra página (%s)" % final}
    if status != 200:
        raise NaoConsultado("resposta_http_inesperada",
                            "A AASP respondeu HTTP %s para %s. Tente de novo mais tarde." % (status, url))
    try:
        texto = corpo.decode("utf-8")
    except UnicodeDecodeError:
        raise NaoConsultado("formato_inesperado",
                            "A página de %s não veio em UTF-8. O índice não foi lido. Abra a "
                            "página no navegador e escale ao advogado." % url)
    return {"html": texto, "url": url, "origem": "rede", "coletado_em": coletado,
            "sha256": hashlib.sha256(corpo).hexdigest()}


class _LeitorIndice(HTMLParser):
    'Recolhe o h1, os trechos de texto visível e as linhas de tabela, com o texto e os links'






    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.h1: list[str] = []
        self.trechos: list[str] = []
        self.linhas: list[list[dict]] = []
        self._em_h1 = False
        self._oculto = 0
        self._linha: list[dict] | None = None
        self._celula: dict | None = None
        self._link: dict | None = None

    def _fechar_link(self):
        if self._link is not None and self._celula is not None:
            self._celula["links"].append((self._link["href"], _espaco("".join(self._link["partes"]))))
        self._link = None

    def _fechar_celula(self):
        self._fechar_link()
        if self._celula is not None and self._linha is not None:
            self._linha.append({"texto": _espaco("".join(self._celula["partes"])),
                                "links": self._celula["links"],
                                "colspan": self._celula["colspan"]})
        self._celula = None

    def _fechar_linha(self):
        self._fechar_celula()
        if self._linha is not None:
            self.linhas.append(self._linha)
        self._linha = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style"):
            self._oculto += 1
        elif tag == "h1":
            self._em_h1 = True
            self.h1.append("")
        elif tag == "tr":
            self._fechar_linha()
            self._linha = []
        elif tag in ("td", "th") and self._linha is not None:
            self._fechar_celula()
            self._celula = {"partes": [], "links": [], "colspan": attrs.get("colspan")}
        elif tag == "a" and self._celula is not None:
            self._fechar_link()
            self._link = {"href": (attrs.get("href") or "").strip(), "partes": []}
        elif tag == "br" and self._celula is not None:
            self._celula["partes"].append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._oculto = max(0, self._oculto - 1)
        elif tag == "h1":
            self._em_h1 = False
        elif tag == "a":
            self._fechar_link()
        elif tag in ("td", "th"):
            self._fechar_celula()
        elif tag in ("tr", "table", "thead", "tbody", "tfoot"):
            self._fechar_linha()

    def close(self):
        super().close()
        self._fechar_linha()

    def handle_data(self, data):
        if self._oculto:
            return
        self.trechos.append(data)
        if self._em_h1:
            self.h1[-1] += data
        if self._celula is not None:
            self._celula["partes"].append(data)
            if self._link is not None:
                self._link["partes"].append(data)


def _tem_ato_ou_marca(celula: dict) -> bool:
    """A célula traz link de ato ou a marca de não divulgado: é linha de tribunal do índice."""
    return any(h for h, _ in celula["links"]) or "nao divulgado" in _achatar(celula["texto"])


def _motivo_fora_do_formato(linha: list[dict]) -> str | None:
    'Por que a linha que pode ser de tribunal não se lê, ou None quando não é de tribunal.'




    tem_sigla = bool(_RX_SIGLA.match(linha[0]["texto"]))
    if not tem_sigla and not any(_tem_ato_ou_marca(c) for c in linha):
        return None
    if len(linha) != 2:
        return "%d célula(s), e a linha do índice tem 2" % len(linha)
    return None if tem_sigla else "sigla fora do formato"


def ler_indice(html_texto: str, ano: int) -> dict:
    "O índice do ano: {'tribunais': [{sigla, grupo, celula}], 'nao_reconhecidas': [{texto,"








    leitor = _LeitorIndice()
    leitor.feed(html_texto)
    leitor.close()
    h1 = " / ".join(_espaco(x) for x in leitor.h1 if _espaco(x))
    if not re.search(r"\bferiados forenses\s+%d\b" % ano, _achatar(h1)):
        raise NaoConsultado("formato_inesperado",
                            "A página não se declara do ano %d no título (h1: %r). O índice não "
                            "foi lido. Abra a página no navegador e escale ao advogado." % (ano, h1))
    grupo, tribunais, nao_reconhecidas = None, [], []
    for linha in leitor.linhas:
        if not linha:
            continue
        if len(linha) == 1 and linha[0]["colspan"]:
            grupo = linha[0]["texto"] or grupo
            continue
        if len(linha) == 2 and _RX_SIGLA.match(linha[0]["texto"]):
            tribunais.append({"sigla": linha[0]["texto"], "grupo": grupo, "celula": linha[1]})
            continue
        motivo = _motivo_fora_do_formato(linha)
        if motivo:
            nao_reconhecidas.append({"texto": linha[0]["texto"], "grupo": grupo,
                                     "motivo": motivo})
    if len(tribunais) < MINIMO_LINHAS:
        raise NaoConsultado("formato_inesperado",
                            "A página do ano %d tem %d linha(s) de tribunal, abaixo do piso de %d. "
                            "O formato do índice mudou e ele não foi lido. Escale ao advogado."
                            % (ano, len(tribunais), MINIMO_LINHAS))
    vistos: dict[str, str] = {}
    for t in tribunais:
        k = chave_tribunal(t["sigla"])
        if k in vistos:
            raise NaoConsultado("formato_inesperado",
                                "O índice traz o tribunal %s em duas linhas. Não há como escolher "
                                "entre elas: escale ao advogado." % t["sigla"])
        vistos[k] = t["sigla"]
    atualizado = next((r for r in map(_RX_ATUALIZADO.search, leitor.trechos) if r), None)
    supletivo = next((x for x in leitor.trechos if _RX_SUPLETIVO.search(x)), None)
    return {"tribunais": tribunais, "nao_reconhecidas": nao_reconhecidas,
            "atualizado_em": _espaco(atualizado.group(1)).rstrip(".") if atualizado else None,
            "aviso_da_pagina": _espaco(supletivo) if supletivo else None}


def _ato(rotulo: str, url: str, sigla: str) -> dict:
    partes = urllib.parse.urlsplit(url)
    host = (partes.hostname or "").lower()
    oficial = any(host == s[1:] or host.endswith(s) for s in SUFIXOS_OFICIAIS)
    do_tribunal = chave_tribunal(sigla).lower() in host.split(".")
    alertas = []
    if not oficial:
        alertas.append("O link está fora de host de órgão público (%s). Confira o ato no site do "
                       "tribunal antes de usar a data." % host)
    elif not do_tribunal:
        alertas.append("O link aponta para host de outro órgão (%s). Confira se o ato é mesmo do "
                       "%s antes de usar a data." % (host, sigla))
    return {"rotulo": rotulo, "url": url, "host": host, "host_oficial": oficial,
            "host_do_tribunal": do_tribunal, "alertas": alertas}


def classificar(entrada: dict) -> tuple[str, list[dict]]:
    """('publicado', atos) ou ('nao_divulgado', []). Linha fora das duas formas é erro nomeado."""
    celula, sigla = entrada["celula"], entrada["sigla"]
    links = [(h, t) for h, t in celula["links"] if h]
    if links:



        if len(links) == 1:
            rotulos = [celula["texto"] or links[0][1]]
        else:
            rotulos = [t or celula["texto"] for _, t in links]
        return "publicado", [_ato(r, h, sigla) for r, (h, _) in zip(rotulos, links)]
    if "nao divulgado" in _achatar(celula["texto"]):
        return "nao_divulgado", []
    raise NaoConsultado("formato_inesperado",
                        "A linha do %s no índice não traz link de ato nem a marca de não "
                        "divulgado (texto: %r). Abra a página no navegador e escale ao advogado."
                        % (sigla, celula["texto"]))


def _msg_nao_reconhecida(tribunal: str | None, linhas: list[dict]) -> str:
    pedido = (" O tribunal pedido (%s) pode estar nessa linha." % tribunal) if tribunal else ""
    return ("O índice tem linha de tribunal fora do formato (%s).%s Abra a página no navegador e "
            "escale ao advogado."
            % ("; ".join("%r: %s" % (x["texto"], x["motivo"]) for x in linhas), pedido))


def _fonte(pagina: dict, indice: dict | None) -> dict:
    return {"url": pagina["url"], "origem": pagina["origem"],
            "coletado_em": pagina.get("coletado_em"), "sha256": pagina.get("sha256"),
            "atualizado_em_na_pagina": (indice or {}).get("atualizado_em"),
            "aviso_da_pagina": (indice or {}).get("aviso_da_pagina")}


def _indice_da_pagina(ano: int, url: str | None, atualizar: bool, agora: float | None):
    """(página, índice). Cache que não se lê é descartado e a página vem de novo da rede."""
    pagina = obter_pagina(ano, url, atualizar, agora)
    if pagina["html"] is None:
        return pagina, None
    try:
        indice = ler_indice(pagina["html"], ano)
    except NaoConsultado:
        if pagina["origem"] != "cache":
            raise
        pagina = obter_pagina(ano, url, True, agora)
        if pagina["html"] is None:
            return pagina, None
        indice = ler_indice(pagina["html"], ano)
    if pagina["origem"] == "rede":
        _gravar_cache(ano, pagina, time.time() if agora is None else agora)
    return pagina, indice


def consultar(tribunal: str, ano: int, url: str | None = None, atualizar: bool = False,
              agora: float | None = None) -> dict:
    """Situação do tribunal no índice da AASP do ano. Levanta NaoConsultado (erro nomeado)."""
    pagina, indice = _indice_da_pagina(ano, url, atualizar, agora)
    saida = {"schema_version": SCHEMA, "ok": True, "ano": ano, "tribunal_pedido": tribunal,
             "tribunal": None, "grupo": None, "situacao": None, "atos": [],
             "texto_no_indice": None, "fonte": _fonte(pagina, indice), "aviso": AVISO}
    if indice is None:
        saida["situacao"] = "sem_pagina_do_ano"
        saida["motivo"] = pagina.get("motivo")
    else:
        alvo = chave_tribunal(tribunal)
        entrada = next((t for t in indice["tribunais"] if chave_tribunal(t["sigla"]) == alvo), None)


        suspeitas = [t for t in indice["nao_reconhecidas"]
                     if entrada is None or chave_tribunal(t["texto"]) == alvo]
        if suspeitas:
            raise NaoConsultado("formato_inesperado", _msg_nao_reconhecida(tribunal, suspeitas))
        if entrada is None:
            saida["situacao"] = "tribunal_ausente"
            saida["tribunais_no_indice"] = [t["sigla"] for t in indice["tribunais"]]
        else:
            situacao, atos = classificar(entrada)
            saida.update({"tribunal": entrada["sigla"], "grupo": entrada["grupo"],
                          "situacao": situacao, "atos": atos,
                          "texto_no_indice": entrada["celula"]["texto"]})
    saida["proximo_passo"] = PROXIMO_PASSO[saida["situacao"]]
    return saida


def listar(ano: int, url: str | None = None, atualizar: bool = False,
           agora: float | None = None) -> dict:
    """O índice inteiro do ano, tribunal a tribunal, com a situação de cada um."""
    pagina, indice = _indice_da_pagina(ano, url, atualizar, agora)
    saida = {"schema_version": SCHEMA, "ok": True, "ano": ano, "fonte": _fonte(pagina, indice),
             "aviso": AVISO}
    if indice is None:
        saida.update({"situacao": "sem_pagina_do_ano", "motivo": pagina.get("motivo"),
                      "tribunais": [], "proximo_passo": PROXIMO_PASSO["sem_pagina_do_ano"]})
        return saida
    tribunais = []
    for entrada in indice["tribunais"]:
        try:
            situacao, atos = classificar(entrada)
        except NaoConsultado as erro:
            situacao, atos = "formato_inesperado", []
            entrada = dict(entrada, erro=erro.mensagem)
        tribunais.append({"tribunal": entrada["sigla"], "grupo": entrada["grupo"],
                          "situacao": situacao, "atos": atos,
                          **({"erro": entrada["erro"]} if "erro" in entrada else {})})
    for linha in indice["nao_reconhecidas"]:
        tribunais.append({"tribunal": linha["texto"], "grupo": linha["grupo"],
                          "situacao": "formato_inesperado", "atos": [],
                          "erro": _msg_nao_reconhecida(None, [linha])})
    saida.update({"situacao": "publicado", "tribunais": tribunais})
    return saida


def _ano(valor: str) -> int:
    try:
        ano = int(valor)
    except ValueError:
        raise argparse.ArgumentTypeError("ano inválido: %r (use AAAA)" % valor)
    if not 2000 <= ano <= 2100:
        raise argparse.ArgumentTypeError("ano fora do intervalo 2000-2100: %d" % ano)
    return ano


def _url_aasp(valor: str) -> str:
    partes = urllib.parse.urlsplit(valor)
    if partes.scheme != "https" or (partes.hostname or "").lower() != HOST_AASP:
        raise argparse.ArgumentTypeError("--url tem de ser https em %s" % HOST_AASP)
    return valor


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Aponta, pelo índice anual da AASP, o ato oficial do calendário forense "
                    "de um tribunal. Não lê o ato e não calcula prazo.")
    alvo = ap.add_mutually_exclusive_group(required=True)
    alvo.add_argument("--tribunal", help="sigla como no índice: STF, TRF-3, TRT-2, TJSP")
    alvo.add_argument("--listar", action="store_true", help="lista o índice inteiro do ano")
    ap.add_argument("--ano", type=_ano, default=date.today().year,
                    help="ano do calendário (padrão: o ano corrente)")
    ap.add_argument("--url", type=_url_aasp,
                    help="página da AASP do ano, quando ela não está no endereço padrão")
    ap.add_argument("--atualizar", action="store_true", help="ignora o cache local")
    a = ap.parse_args(argv)
    try:
        if a.listar:
            saida = listar(a.ano, a.url, a.atualizar)
        else:
            saida = consultar(a.tribunal, a.ano, a.url, a.atualizar)
        codigo = 0 if saida["situacao"] == "publicado" else 1
    except Exception as erro:


        if isinstance(erro, NaoConsultado):
            nome, mensagem = erro.codigo, erro.mensagem
        else:
            nome, mensagem = "falha_inesperada", _msg_falha_inesperada(erro)
        saida = {"schema_version": SCHEMA, "ok": False, "erro": nome,
                 "mensagem": mensagem, "ano": a.ano,
                 "tribunal_pedido": a.tribunal, "url": a.url or URL_ANO.format(ano=a.ano)}
        codigo = 2
    print(json.dumps(saida, ensure_ascii=False, indent=2))
    return codigo


if __name__ == "__main__":
    sys.exit(main())
