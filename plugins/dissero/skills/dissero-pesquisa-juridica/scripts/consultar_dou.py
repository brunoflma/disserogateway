#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'consultar_dou.py - PERGUNTA ao Diário Oficial da União, e recusa quando não sabe.'




































































from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://www.in.gov.br/consulta/-/buscar/dou"
HOST_OFICIAL = "www.in.gov.br"



UA_NAVEGADOR = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

BLOCO_RX = re.compile(
    r'<script id="_br_com_seatecnologia_in_buscadou_BuscaDouPortlet_params"'
    r'[^>]*>\s*(\{.*?\})\s*</script>',
    re.S,
)
ISO_RX = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
SECOES = ("DO1", "DO2", "DO3", "todos")


class ConsultaDOU(Exception):
    """Falha de consulta ou de contrato. Nunca vira lista vazia."""


def _data_do_servico(iso: str, rotulo: str) -> str:
    """ISO -> dd-mm-yyyy. A conversão é o ponto: ISO devolve ZERO resultado, em silêncio."""
    m = ISO_RX.match(str(iso or "").strip())
    if not m:
        raise ConsultaDOU("%s deve ser AAAA-MM-DD (recebido: %r)" % (rotulo, iso))
    ano, mes, dia = m.groups()
    try:
        dt.date(int(ano), int(mes), int(dia))
    except ValueError as exc:
        raise ConsultaDOU("%s não é data do calendário: %s" % (rotulo, exc)) from exc
    return "%s-%s-%s" % (dia, mes, ano)


def montar_url(termo: str, *, de=None, ate=None, secao="todos", limite=20) -> str:
    termo = str(termo or "").strip()
    if not termo:
        raise ConsultaDOU("termo de busca vazio")
    if secao not in SECOES:
        raise ConsultaDOU("seção deve ser uma de: %s" % ", ".join(SECOES))
    if not isinstance(limite, int) or not 1 <= limite <= 100:
        raise ConsultaDOU("limite deve ser inteiro entre 1 e 100")
    params = {"q": termo, "s": secao, "sortType": "0", "delta": str(limite)}
    if de or ate:
        if not (de and ate):
            raise ConsultaDOU("informe as DUAS pontas do período (--de e --ate) ou nenhuma")
        inicio, fim = _data_do_servico(de, "--de"), _data_do_servico(ate, "--ate")
        if dt.datetime.strptime(inicio, "%d-%m-%Y") > dt.datetime.strptime(fim, "%d-%m-%Y"):
            raise ConsultaDOU("--de é posterior a --ate")
        params["exactDate"] = "personalizado"
        params["publishFrom"] = inicio
        params["publishTo"] = fim
    else:
        params["exactDate"] = "all"
    return BASE + "?" + urllib.parse.urlencode(params)


def _baixar(url: str, timeout: int) -> str:
    if urllib.parse.urlsplit(url).hostname != HOST_OFICIAL:
        raise ConsultaDOU("URL fora do host oficial %s" % HOST_OFICIAL)
    req = urllib.request.Request(url, headers={
        "User-Agent": UA_NAVEGADOR,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "pt-BR,pt;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            bruto = resp.read()
    except urllib.error.HTTPError as exc:
        raise ConsultaDOU("DOU respondeu HTTP %s" % exc.code) from exc
    except (urllib.error.URLError, OSError) as exc:
        raise ConsultaDOU("falha de rede: %s" % exc) from exc
    if not bruto:


        raise ConsultaDOU(
            "o DOU respondeu com CORPO VAZIO. É o que o WAF faz quando não reconhece a "
            "assinatura do cliente, e não indisponibilidade da fonte. Confira o User-Agent "
            "enviado.")
    return bruto.decode("utf-8", errors="replace")


def extrair(pagina: str) -> list:
    """Lê o bloco JSON embutido. Bloco ausente é FALHA, nunca lista vazia."""
    m = BLOCO_RX.search(pagina)
    if not m:
        raise ConsultaDOU(
            "formato_mudou: o bloco `...BuscaDouPortlet_params` não está na página. Os "
            "resultados do DOU vêm embutidos nela, e não por API — se o bloco sumiu, a "
            "página mudou. NÃO devolvo lista vazia, que seria lida como 'nada publicado'.")
    try:
        dados = json.JSONDecoder().raw_decode(html.unescape(m.group(1)))[0]
    except ValueError as exc:
        raise ConsultaDOU("formato_mudou: bloco ilegível (%s)" % exc) from exc
    itens = dados.get("jsonArray")
    if not isinstance(itens, list):
        raise ConsultaDOU("formato_mudou: `jsonArray` ausente ou não é lista")
    return itens


def _limpar(texto) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", str(texto or ""))).strip()


def consultar(termo: str, *, de=None, ate=None, secao="todos", limite=20, timeout=45) -> dict:
    url = montar_url(termo, de=de, ate=ate, secao=secao, limite=limite)
    itens = extrair(_baixar(url, timeout))
    resultados = []
    for it in itens:
        slug = str(it.get("urlTitle") or "").strip()
        resultados.append({
            "titulo": _limpar(it.get("title")),
            "especie": _limpar(it.get("artType")),
            "publicado_em": _limpar(it.get("pubDate")),

            "secao": _limpar(it.get("pubName")),
            "orgao": _limpar(it.get("hierarchyStr")),
            "edicao": _limpar(it.get("editionNumber")),
            "pagina": _limpar(it.get("numberPage")),
            "url": ("https://www.in.gov.br/web/dou/-/" + slug) if slug else None,
            "trecho": _limpar(it.get("content")),

            "confirmado": False,
        })
    return {
        "ok": True,
        "consultado_em": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "url_consultada": url,
        "termo": termo,
        "secao": secao,
        "periodo": {"de": de, "ate": ate} if de else None,
        "resultados": resultados,

        "total_desconhecido": True,
        "pode_haver_mais": len(resultados) >= limite,
        "aviso": (
            "DESCOBERTA, não confirmação: `trecho` é excerto marcado pelo buscador, não "
            "teor. Para citar, abra a URL e confirme o inteiro teor. O DOU não devolve "
            "total de ocorrências — este resultado não diz quantas existem."
        ),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Consulta o Diário Oficial da União (descoberta).")
    ap.add_argument("termo")
    ap.add_argument("--de", help="início do período, AAAA-MM-DD (exige --ate)")
    ap.add_argument("--ate", help="fim do período, AAAA-MM-DD (exige --de)")
    ap.add_argument("--secao", default="todos", choices=list(SECOES))
    ap.add_argument("--limite", type=int, default=20)
    ap.add_argument("--timeout", type=int, default=45)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--url", action="store_true", help="só imprime a URL montada; não consulta")
    a = ap.parse_args(argv)
    try:
        if a.url:
            print(montar_url(a.termo, de=a.de, ate=a.ate, secao=a.secao, limite=a.limite))
            return 0
        saida = consultar(a.termo, de=a.de, ate=a.ate, secao=a.secao,
                          limite=a.limite, timeout=a.timeout)
    except ConsultaDOU as exc:
        print(json.dumps({"ok": False, "erro": str(exc)}, ensure_ascii=False))
        return 2
    if a.json:
        print(json.dumps(saida, ensure_ascii=False, indent=2))
        return 0
    if not saida["resultados"]:
        print("Nenhum resultado para %r no período consultado." % a.termo)
        print("ATENÇÃO: o DOU não informa total, então isto significa 'a busca não trouxe "
              "nada', e não 'nada foi publicado'. Confira o termo e o período.")
        return 0
    for r in saida["resultados"]:
        print("- %s" % r["titulo"])
        print("  %s | seção %s | edição %s | pág. %s | %s"
              % (r["especie"], r["secao"], r["edicao"], r["pagina"], r["publicado_em"]))
        print("  órgão: %s" % r["orgao"])
        if r["url"]:
            print("  %s" % r["url"])
    print("\n%d resultado(s) exibido(s). %s"
          % (len(saida["resultados"]),
             "PODE HAVER MAIS: o limite foi atingido e o DOU não informa total."
             if saida["pode_haver_mais"] else "O DOU não informa total de ocorrências."))
    print(saida["aviso"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
