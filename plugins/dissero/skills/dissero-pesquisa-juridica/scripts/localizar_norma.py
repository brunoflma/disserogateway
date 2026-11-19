#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""localizar_norma.py — a URL oficial de uma norma federal no Portal da Legislação, sem adivinhar.

POR QUE EXISTE
--------------
O Portal da Legislação da Presidência (https://portaldalegislacao.presidencia.gov.br/) organiza as
normas por tipo e por ano, e a URL final NÃO se monta pelo número: ela muda de pasta conforme o
período (`leis/l9784.htm`, `leis/2002/l10406.htm`, `_ato2019-2022/2021/lei/l14133.htm`,
`leis/lcp/lcp101.htm`, `decreto-lei/del2848.htm`, `mpv/antigas_2001/2200-2.htm`). URL montada de
memória é a falha que a governança proíbe: dispositivo citado com endereço que não existe, ou que
existe e é de outra norma.

A ESTRATÉGIA
------------
Este módulo nunca monta a URL do ato. Ele lê a página de LISTAGEM que o portal publica (índice do
tipo -> página do ano ou da faixa), acha a linha cujo número bate e devolve o link que o próprio
portal publica, resolvido contra a página (`urljoin`). Funciona para qualquer padrão de pasta,
inclusive os ~390 decretos antigos que o portal liga direto a `www.planalto.gov.br`, cujo link é
devolvido como está.

Os pontos de entrada (índices) são os únicos endereços fixos: `pages/leis-ordinarias.html`,
`pages/decretos.html`, `pages/decretos-leis.html`, `pages/medidas-provisorias.html`, as páginas
únicas de lei complementar, lei delegada e emenda constitucional, e `pages/codigos.html` /
`pages/estatutos.html` para busca por nome. Se o portal mudar um deles, a falha é nomeada
(`formato_mudou`), nunca lista vazia.

AS ARMADILHAS MEDIDAS NO PORTAL (19/11/2026)
--------------------------------------------
1. DEFESA ANTIRROBÔ (F5). Sem User-Agent de navegador completo E cabeçalho `Accept`, o portal
   derruba a conexão (ConnectionReset) ou devolve, com HTTP 200, um desafio JavaScript de ~16 KB
   (`TSPD`/`bobcmn`) no lugar da listagem. Os dois casos têm erro próprio
   (`portal_recusou_conexao`, `desafio_antirrobo`) e nenhum vira "norma não encontrada". O plano B
   é `--html-dir`: a página obtida por outra ferramenta (navegador, wigolo) entra pelo disco.
2. TEXTO DE LINK IRREGULAR. Exemplos reais: `Lei nº 14.939, de 30.7.2024`, `7.273, de 10.12.84`,
   `Lei no 10.213, de 27 de março de 2001`, `8.2 45 , de 18 .10.91` (espaço dentro do número),
   `7.454 de 30.12.85` (sem vírgula), `9.561de 18.12.97`, `22.12.8 8` (ano com espaço), `4.950A`,
   `5.467-A`, e o ponto da data dentro de `<span class="data-ponto">`. O parser tolera todos.
3. ANO COM DOIS DÍGITOS ("99" vale 1999): resolvido pelo período da página.
4. LINKS DE MENU (`/pages/...`, inclusive "2004", "2005" que parecem número de lei) e
   REFERÊNCIAS CRUZADAS na ementa ("Decreto-lei nº 6.016"): só conta o link da PRIMEIRA célula
   da linha, e um prefixo de outro tipo ("Lei nº" numa página de MP) é recusado. Na MP, as
   reedições das outras células só valem com link de MP (`/mpv/`, sem `#art`): a ementa linka
   o número do ARTIGO de outra lei ('art. 44' -> l4771.htm#art44), que viraria uma MP 44.
5. MP: "2.200-2" é o número 2.200, reedição 2. Sem reedição, vale a mais recente da série. A
   numeração de MP reiniciou com a EC 32/2001 (há MP 98 de 1989 e de 2002): séries distantes no
   tempo saem como lista, nunca como escolha silenciosa. MP antiga que só aparece como reedição
   de outra série ('1.154,' com a vírgula dentro do link) entra; MP sem ano achada só na série
   nova, com número que a antiga também teve, sai com `observacao`.
6. NUMERAÇÃO DE DECRETO reiniciou em 1991; a de lei, em 1946 (Lei 4.984 de 1925 e de 1966); a de
   lei complementar tem LC 1 e 2 de 1962 e de 1967.
7. LINK TROCADO PELO PORTAL: 44 linhas ligam a outra norma ('5.969, de 11.12.73' -> l5968.htm,
   página intitulada 'Lei nº 5.968'). O número do rótulo é conferido contra o nome do arquivo;
   havendo na mesma célula um link que confere, vale ele; senão, `link_diverge_do_rotulo`, nunca
   o endereço de outra norma.

BUSCA SEM ANO
-------------
Lei ordinária: busca binária entre as páginas de ano (≈6 acessos), mais a página anterior a
1960, onde moram as leis de antes do reinício de 1946 com o mesmo número. Decreto:
binária de 1992 em diante, depois 1991, e só varre tudo se não achar (decreto antigo). Decreto-lei
e MP: varre todas as páginas; mais de um resultado sai como lista com o período de cada um.

O QUE ESTE MÓDULO NÃO FAZ
-------------------------
Não diz se a norma está vigente nem qual redação vigora: isso é do `normas_leg_br.py` e do
advogado. Não confirma teor: localizar o endereço oficial não é ler o dispositivo.

Uso:
    python localizar_norma.py "9.784/1999"
    python localizar_norma.py "lc 101/2000"            # também: decreto, dl, mp, ec, lei delegada
    python localizar_norma.py "mp 2.200-2/2001"
    python localizar_norma.py "Código Penal"            # nome, sigla (CPC, CLT...) ou apelido
    python localizar_norma.py "9.784" --tipo lei        # sem ano: busca binária
    python localizar_norma.py "9.784/1999" --html-dir <pasta>   # plano B, sem rede
    python localizar_norma.py --auditar                 # parser contra todas as listagens

Saída: JSON. Exit: 0 = localizada · 1 = não encontrada, ambígua (lista) ou link do portal
trocado (`link_diverge_do_rotulo`) · 2 = rede, desafio antirrobô ou formato do portal · 3 =
entrada não reconhecida · 4 = erro interno não previsto. Stdlib apenas.
"""
from __future__ import annotations

import argparse
import hashlib
import html as htmllib
import http.client
import json
import os
import re
import socket
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ENGINE_VERSION = "dsr.localizar_norma.v2"
HOST = "portaldalegislacao.presidencia.gov.br"
BASE = "https://%s/" % HOST
HOST_PLANALTO = "www.planalto.gov.br"


INDICES = {
    "lei": "pages/leis-ordinarias.html",
    "decreto": "pages/decretos.html",
    "dl": "pages/decretos-leis.html",
    "mp": "pages/medidas-provisorias.html",
}
PAGINAS_UNICAS = {
    "lc": "pages/leis-complementares.html",
    "ldl": "pages/leis-delegadas.html",
    "ec": "ccivil_03/constituicao/emendas/emc/quadro_emc.htm",
}
PAGINAS_DE_NOMES = ("pages/codigos.html", "pages/estatutos.html")

ROTULO_TIPO = {
    "lei": "Lei", "lc": "Lei Complementar", "ldl": "Lei Delegada", "decreto": "Decreto",
    "dl": "Decreto-Lei", "mp": "Medida Provisória", "ec": "Emenda Constitucional",
    "cf": "Constituição Federal",
}



PREFIXOS_ACEITOS = {
    "lei": ("lei", "lei ordinaria"),
    "lc": ("lei complementar",),
    "ldl": ("lei delegada",),
    "decreto": ("decreto", "dec", "d"),
    "dl": ("decreto-lei", "decreto lei"),
    "mp": ("medida provisoria",),
    "ec": ("emenda constitucional", "emenda"),
}



CABECALHOS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9",
}

MP_MAIOR_ANTIGA = 2225
CACHE_TTL = 2 * 60 * 60
CHAVE_CACHE = "portal-legislacao.v1"
VAR_CACHE = "DSR_CACHE_PORTAL_LEGISLACAO"




SIGLAS = {
    "cc": ("lei", 10406, 2002), "cpc": ("lei", 13105, 2015), "cp": ("dl", 2848, 1940),
    "cpp": ("dl", 3689, 1941), "clt": ("dl", 5452, 1943), "cdc": ("lei", 8078, 1990),
    "ctn": ("lei", 5172, 1966), "eca": ("lei", 8069, 1990), "lgpd": ("lei", 13709, 2018),
    "lindb": ("dl", 4657, 1942), "lep": ("lei", 7210, 1984), "lrf": ("lc", 101, 2000),
    "lai": ("lei", 12527, 2011), "lacp": ("lei", 7347, 1985), "eaoab": ("lei", 8906, 1994),
}
APELIDOS = {
    "maria da penha": ("lei", 11340, 2006),
    "lei maria da penha": ("lei", 11340, 2006),
    "lei de licitacoes": ("lei", 14133, 2021),
    "nova lei de licitacoes": ("lei", 14133, 2021),
    "lei do inquilinato": ("lei", 8245, 1991),
    "lei de improbidade": ("lei", 8429, 1992),
    "lei de improbidade administrativa": ("lei", 8429, 1992),
    "lei de execucao penal": ("lei", 7210, 1984),
    "marco civil da internet": ("lei", 12965, 2014),
    "lei dos juizados especiais": ("lei", 9099, 1995),
    "lei de falencias": ("lei", 11101, 2005),
    "lei de recuperacao judicial": ("lei", 11101, 2005),
    "lei do mandado de seguranca": ("lei", 12016, 2009),
    "lei de arbitragem": ("lei", 9307, 1996),
    "lei anticorrupcao": ("lei", 12846, 2013),
    "lei do processo administrativo": ("lei", 9784, 1999),
    "lei de drogas": ("lei", 11343, 2006),
    "lei de abuso de autoridade": ("lei", 13869, 2019),
    "lei da acao civil publica": ("lei", 7347, 1985),
    "lei de responsabilidade fiscal": ("lc", 101, 2000),
    "lei de acesso a informacao": ("lei", 12527, 2011),
    "estatuto da oab": ("lei", 8906, 1994),
}
NOMES_DA_CONSTITUICAO = {"cf", "cf/88", "cf 88", "cf88", "crfb", "crfb/88", "constituicao",
                         "constituicao federal", "constituicao da republica"}


class ErroPortal(Exception):
    """Falha nomeada. Nunca vira lista vazia nem 'norma não encontrada'."""

    def __init__(self, codigo: str, mensagem: str, url: str | None = None):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem
        self.url = url





def sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def texto_limpo(fragmento: str) -> str:
    'HTML -> texto: tira as tags (o ponto da data vem num <span>), decodifica entidades'

    t = re.sub(r"<[^>]+>", "", fragmento or "")
    t = htmllib.unescape(t).replace("\xa0", " ")
    return re.sub(r"\s+", " ", t).strip()


def chave_nome(s: str) -> str:
    s = sem_acento(s).lower()
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"[^a-z0-9/ ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()




_PREFIXO_RX = re.compile(
    r"^(?P<tipo>[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\- ]*?)\s*(?:[nN]\s*\.?\s*[º°oO]\s*\.?|[nN]\.)?\s*(?=\d)")


_NUMERO_RX = re.compile(
    r"^(?P<num>\d(?:[\d.\s]*\d)?)\s*(?:-?\s*(?P<suf>[A-Z])(?![A-Za-zÀ-ÿ]))?"
    r"\s*(?:-+\s*(?P<reed>\d+))?")
_DATA_EXTENSO_RX = re.compile(r"\bde\s+[a-zç]+\s+de\s+(\d{4})\b", re.I)
_DATA_TRECHO_RX = re.compile(r"[\d][\d\s.º°/]*")


def ano_da_data(resto: str) -> tuple[int | None, int | None]:
    '(ano de 4 dígitos, ano de 2 dígitos) do trecho de data depois do número.'





    m = _DATA_EXTENSO_RX.search(resto)
    if m:
        return int(m.group(1)), None
    m = re.match(r"\s*(?:,+\s*)?(?:d\s*e\b\.?|de\.?|d\b)?\s*(?:,\s*)?", resto, re.I)
    trecho = resto[m.end():] if m else resto
    d = _DATA_TRECHO_RX.match(trecho)
    if not d:
        return None, None
    agora = time.localtime().tm_year
    compacto = re.sub(r"[\sº°]", "", d.group(0)).rstrip("./")
    m = re.fullmatch(r"\d{1,2}[./]\d{1,2}[./](\d+)", compacto)
    if m:
        ano = m.group(1)
        if len(ano) == 4 and 1800 <= int(ano) <= agora:
            return int(ano), None
        if len(ano) == 2:
            return None, int(ano)
        return None, None
    if re.fullmatch(r"\d{4}", compacto) and 1800 <= int(compacto) <= agora:
        return int(compacto), None
    digitos = re.sub(r"\D", "", compacto)
    if len(digitos) >= 6 and 1800 <= int(digitos[-4:]) <= agora:
        return int(digitos[-4:]), None
    if len(digitos) >= 3:
        return None, int(digitos[-2:])
    return None, None


def ler_rotulo(texto: str, tipo: str) -> dict | None:
    'Número, sufixo, reedição e ano do texto de um link de listagem; None se não é rótulo de'

    t = texto_limpo(texto)
    if not t or not t[0].isalnum():
        return None
    if not t[0].isdigit():
        m = _PREFIXO_RX.match(t)
        if not m:
            return None
        prefixo = sem_acento(m.group("tipo")).lower().strip(" -")
        prefixo = re.sub(r"\s+", " ", prefixo)
        if prefixo not in PREFIXOS_ACEITOS.get(tipo, ()):
            return None
        t = t[m.end():]
    m = _NUMERO_RX.match(t)
    if not m:
        return None
    numero = re.sub(r"\D", "", m.group("num"))
    if not numero:
        return None
    ano, ano_2 = ano_da_data(t[m.end():])
    return {
        "numero": int(numero),
        "sufixo": (m.group("suf") or "").upper(),
        "reedicao": int(m.group("reed")) if m.group("reed") else None,
        "ano": ano,
        "ano_2": ano_2,
    }


def resolver_ano(rot: dict, periodo: tuple[int, int] | None) -> int | None:
    """Ano completo: o de 4 dígitos, ou o de 2 dígitos posto no século que cai no período."""
    if rot.get("ano"):
        return rot["ano"]
    yy = rot.get("ano_2")


    unico = periodo[0] if periodo and periodo[0] == periodo[1] else None
    if yy is None:
        return unico
    candidatos = (1900 + yy, 2000 + yy, 1800 + yy)
    if periodo:
        for c in candidatos:
            if periodo[0] <= c <= periodo[1]:
                return c
        if unico:
            return unico
    return 2000 + yy if yy <= time.localtime().tm_year % 100 else 1900 + yy


def ler_periodo(texto: str) -> tuple[int, int] | None:
    "'2021' -> (2021, 2021); '1981 a 1987' / '1979 a 1970' / '2000 e 2001' -> faixa;"

    t = sem_acento(texto_limpo(texto)).lower()
    anos = [int(a) for a in re.findall(r"\b(1[5-9]\d\d|20\d\d)\b", t)]
    if re.fullmatch(r"anteriores? a \d{4}", t) and anos:
        return (0, anos[0] - 1)
    if re.fullmatch(r"\d{4}", t):
        return (anos[0], anos[0])
    if re.fullmatch(r"\d{4} (a|e|-) \d{4}", t) and len(anos) == 2:
        return (min(anos), max(anos))
    return None





def _corpo(html: str) -> str:
    """O conteúdo depois do salto 'main-content', quando houver (o menu lateral fica fora)."""
    i = html.find('id="main-content"')
    return html[i:] if i >= 0 else html


_A_RX = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.S | re.I)
_HREF_RX = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.I)
_TR_RX = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.S | re.I)
_TD_RX = re.compile(r"<td\b[^>]*>(.*?)</td>", re.S | re.I)


def _ancoras(fragmento: str, url_pagina: str):
    for attrs, inner in _A_RX.findall(fragmento):
        h = _HREF_RX.search(attrs)
        if not h:
            continue
        href = htmllib.unescape(h.group(1)).strip()
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue
        yield urllib.parse.urljoin(url_pagina, href), inner


def _ancoras_unidas(fragmento: str, url_pagina: str) -> list[tuple[str, str]]:
    'Âncoras, com as VIZINHAS de mesmo endereço unidas. O portal parte o rótulo em dois links'


    unidas: list[list[str]] = []
    for url, inner in _ancoras(fragmento, url_pagina):
        if unidas and unidas[-1][0] == url:
            unidas[-1][1] += inner
        else:
            unidas.append([url, inner])
    return [(u, i) for u, i in unidas]


def _e_menu(url: str) -> bool:
    return "/pages/" in urllib.parse.urlsplit(url).path


def arquivo_confere(url: str, numero: int) -> bool:
    'O nome do arquivo do link traz o número do rótulo? Medido em 19/11/2026: o portal tem 45'



    base = urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1]
    base = re.sub(r"\.[A-Za-z]+$", "", base)


    blocos = {int(b) for b in re.findall(r"\d+", base)} | \
        {int(b) for b in re.findall(r"\d+", base.replace(".", ""))}
    return not blocos or numero in blocos


def _link_de_mp(url: str) -> bool:
    'Reedição fora da 1ª célula só vale se o link é de MP: pasta `/mpv/`, sem âncora de'


    partes = urllib.parse.urlsplit(url)
    return "/mpv/" in partes.path and not partes.fragment


def ler_indice(html: str, url_pagina: str) -> list[dict]:
    "Páginas de ano/faixa de um índice: o texto do link é o período ('2021', '1981 a 1987',"

    vistos, paginas = set(), []
    for url, inner in _ancoras(_corpo(html), url_pagina):
        periodo = ler_periodo(inner)
        if periodo is None or url in vistos:
            continue
        vistos.add(url)
        paginas.append({"url": url.split("#")[0], "periodo": periodo,
                        "rotulo": texto_limpo(inner)})
    paginas.sort(key=lambda p: (p["periodo"][0], p["periodo"][1]))
    return paginas



_NAO_E_ATO_RX = re.compile(
    r"(?i)(mensagem|veto|exposi|retifica|republica|anexo|texto|vide|ato\b|convertid|prorroga|"
    r"decis|comunicado|encerrament|revogad|vigencia|estatuto|publicad|regulament|errata)")


_REEDICAO_NUA_RX = re.compile(r"\d[\d.\s]*(?:-+\s*\d+)?(?:\s*,?\s*de\s+[\d.\sº]+)?")


def ler_listagem(html: str, url_pagina: str, tipo: str,
                 periodo: tuple[int, int] | None = None) -> dict:
    'Atos de uma página de listagem, e os links de ato que o parser não entendeu (auditoria).'




    corpo = _corpo(html)
    atos, nao_entendidos = [], []
    linhas = _TR_RX.findall(corpo)
    for linha in linhas:
        celulas = _TD_RX.findall(linha)
        if not celulas:
            continue
        ementa = texto_limpo(celulas[1]) if len(celulas) > 1 else ""
        ementa = re.sub(r"(?i)\s*Mensagem de veto\s*$", "", ementa)[:400]
        alvos = [(0, celulas[0])]
        if tipo == "mp":
            alvos += [(i, c) for i, c in enumerate(celulas[1:], start=1)]
        for indice, celula in alvos:
            ancoras = _ancoras_unidas(celula, url_pagina)
            for posicao, (url, inner) in enumerate(ancoras):
                if _e_menu(url):
                    continue
                if indice > 0 and not _link_de_mp(url):
                    continue
                rot = ler_rotulo(inner, tipo)
                rotulo = texto_limpo(inner)
                if rot is None and indice == 0 and posicao == 0 \
                        and not _NAO_E_ATO_RX.match(sem_acento(rotulo)):

                    celula_txt = re.split(r"(?i)publicad", texto_limpo(celula))[0]
                    rot = ler_rotulo(celula_txt, tipo)
                    if rot:
                        rotulo = celula_txt.strip()
                if rot is None:
                    if indice == 0 and rotulo and not _NAO_E_ATO_RX.match(sem_acento(rotulo)):
                        nao_entendidos.append({"rotulo": rotulo, "url": url})
                    continue
                if indice > 0:
                    rotulo = rotulo.rstrip(" ,;.")
                    if not (_REEDICAO_NUA_RX.fullmatch(rotulo) or not rotulo[:1].isdigit()):
                        continue

                ano = resolver_ano(rot, periodo) if indice == 0 else rot.get("ano")
                diverge = not arquivo_confere(url, rot["numero"])
                if diverge:

                    outro = next((u for u, i in ancoras if u != url and not _e_menu(u)
                                  and re.search(r"\.html?$", urllib.parse.urlsplit(u).path, re.I)
                                  and not _NAO_E_ATO_RX.match(sem_acento(texto_limpo(i)))
                                  and re.search(r"\d", urllib.parse.urlsplit(u).path.rsplit(
                                      "/", 1)[-1]) and arquivo_confere(u, rot["numero"])), None)
                    if outro:
                        url, diverge = outro, False
                atos.append({**rot, "ano": ano, "url": url, "rotulo": rotulo,
                             "ementa": ementa if indice == 0 else "",
                             "principal": indice == 0, "link_diverge": diverge})
    if not linhas:
        for url, inner in _ancoras(corpo, url_pagina):
            if _e_menu(url):
                continue
            rot = ler_rotulo(inner, tipo)
            if rot:
                atos.append({**rot, "ano": resolver_ano(rot, periodo), "url": url,
                             "rotulo": texto_limpo(inner), "ementa": "", "principal": True,
                             "link_diverge": not arquivo_confere(url, rot["numero"])})
    return {"atos": atos, "nao_entendidos": nao_entendidos, "linhas": len(linhas)}


_CARD_RX = re.compile(r"<a\b([^>]*codigo-item-card[^>]*)>(.*?)</a>", re.S | re.I)
_SPAN_RX = re.compile(r'<span[^>]*class="codigo-card-(title|subtitle)"[^>]*>(.*?)</span>',
                      re.S | re.I)


def ler_cartoes(html: str, url_pagina: str) -> list[dict]:
    """Itens de Códigos e Estatutos: título ('Código Penal') e subtítulo ('Decreto-Lei nº...')."""
    itens = []
    for attrs, inner in _CARD_RX.findall(html):
        h = _HREF_RX.search(attrs)
        if not h:
            continue
        partes = {k.lower(): texto_limpo(v) for k, v in _SPAN_RX.findall(inner)}
        titulo = partes.get("title") or texto_limpo(inner)
        itens.append({"nome": titulo, "norma": partes.get("subtitle", ""),
                      "url": urllib.parse.urljoin(url_pagina, htmllib.unescape(h.group(1)))})
    return itens





class Portal:
    """Leitor de páginas do portal: rede (com cache de 2 h) ou pasta de HTML (plano B)."""

    def __init__(self, html_dir: str | None = None, cache_dir: str | None = None,
                 usar_cache: bool = True, timeout: int = 30, baixar=None):
        self.html_dir = html_dir
        self.cache_dir = cache_dir or os.environ.get(VAR_CACHE) or os.path.join(
            os.path.expanduser("~"), ".cache", "dissero", "portal-legislacao")
        self.usar_cache = usar_cache and not html_dir
        self.timeout = timeout
        self._baixar = baixar or self._baixar_rede
        self.acessos_rede = 0
        self.lidas: list[str] = []
        self._memoria: dict[str, str] = {}

    @staticmethod
    def nome_arquivo(url: str) -> str:
        """Nome da página na pasta do plano B: o caminho, com '/' trocado por '__'."""
        return urllib.parse.urlsplit(url).path.lstrip("/").replace("/", "__")

    def ler(self, url: str) -> str:
        url = url.split("#")[0]
        if url in self._memoria:
            return self._memoria[url]
        if urllib.parse.urlsplit(url).hostname != HOST:
            raise ErroPortal("fora_do_portal", "endereço fora do portal: %s" % url, url)
        if self.html_dir:
            caminho = os.path.join(self.html_dir, self.nome_arquivo(url))
            if not os.path.isfile(caminho):
                raise ErroPortal(
                    "pagina_ausente_no_html",
                    "a pasta do plano B não tem esta página. Obtenha %s (navegador ou wigolo) e "
                    "salve como %s" % (url, caminho), url)
            with open(caminho, "rb") as f:
                texto = _decodificar(f.read())
        else:
            texto = self._do_cache(url)
            if texto is not None:
                try:
                    _conferir_desafio(texto, url)
                except ErroPortal:
                    texto = None
            if texto is None:
                texto = _decodificar(self._baixar(url, self.timeout))
                self.acessos_rede += 1
                _conferir_desafio(texto, url)
                self._para_cache(url, texto)
        _conferir_desafio(texto, url)
        self._memoria[url] = texto
        self.lidas.append(url)
        return texto

    def _arquivo_cache(self, url: str) -> str:
        h = hashlib.sha256((CHAVE_CACHE + "|" + url).encode("utf-8")).hexdigest()[:32]
        return os.path.join(self.cache_dir, h + ".json")

    def _do_cache(self, url: str) -> str | None:
        if not self.usar_cache:
            return None
        try:
            with open(self._arquivo_cache(url), encoding="utf-8") as f:
                dado = json.load(f)
            if dado.get("url") == url and time.time() - float(dado.get("t", 0)) < CACHE_TTL \
                    and isinstance(dado.get("html"), str):
                return dado["html"]
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return None
        return None

    def _para_cache(self, url: str, texto: str) -> None:
        if not self.usar_cache:
            return
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            tmp = self._arquivo_cache(url) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"url": url, "t": time.time(), "html": texto}, f, ensure_ascii=False)
            os.replace(tmp, self._arquivo_cache(url))
        except OSError:
            pass

    @staticmethod
    def _baixar_rede(url: str, timeout: int) -> bytes:
        ultimo = None
        for _tentativa in range(2):
            req = urllib.request.Request(url, headers=CABECALHOS)
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    bruto = resp.read()
                if not bruto:
                    raise ErroPortal("corpo_vazio", "o portal respondeu sem corpo em %s" % url, url)
                return bruto
            except urllib.error.HTTPError as exc:
                raise ErroPortal("http_%s" % exc.code,
                                 "o portal respondeu HTTP %s em %s" % (exc.code, url), url) from exc
            except http.client.IncompleteRead:
                ultimo = ErroPortal("resposta_incompleta",
                                    "o portal cortou a resposta no meio em %s" % url, url)
                continue
            except http.client.HTTPException as exc:
                raise ErroPortal("falha_de_rede", "falha de rede em %s: %s" % (url, exc),
                                 url) from exc
            except (urllib.error.URLError, OSError) as exc:
                motivo = getattr(exc, "reason", exc)
                if isinstance(motivo, ConnectionResetError) or isinstance(exc, ConnectionResetError):
                    ultimo = ErroPortal(
                        "portal_recusou_conexao",
                        "o portal derrubou a conexão (defesa antirrobô do portal, não "
                        "indisponibilidade). Use o plano B: --html-dir com a página %s" % url, url)
                elif isinstance(motivo, (socket.timeout, TimeoutError)) or isinstance(
                        exc, (socket.timeout, TimeoutError)):
                    ultimo = ErroPortal("portal_sem_resposta",
                                        "o portal não respondeu em %ss: %s" % (timeout, url), url)
                else:
                    raise ErroPortal("falha_de_rede", "falha de rede em %s: %s" % (url, motivo),
                                     url) from exc
        raise ultimo


def _decodificar(bruto: bytes) -> str:
    try:
        return bruto.decode("utf-8")
    except UnicodeDecodeError:
        return bruto.decode("cp1252", errors="replace")


def _conferir_desafio(texto: str, url: str) -> None:
    cabeca = texto[:4000]
    if ("TSPD" in cabeca or "bobcmn" in cabeca) and "<table" not in texto.lower() \
            and "codigo-item-card" not in texto:
        raise ErroPortal(
            "desafio_antirrobo",
            "o portal devolveu o desafio JavaScript da defesa antirrobô no lugar da página. Não "
            "é 'norma inexistente'. Use o plano B: --html-dir com a página %s" % url, url)




_TIPOS_PEDIDO = (
    ("lc", r"lei\s+complementar|lcp?"),
    ("ldl", r"lei\s+delegada|ldl"),
    ("dl", r"decreto[\s-]*lei|dl|del"),
    ("decreto", r"decreto|dec"),
    ("mp", r"medida\s+provisoria|mpv?"),
    ("ec", r"emenda\s+constitucional|emenda|ec|emc"),
    ("lei", r"lei\s+ordinaria|lei"),
)
_PEDIDO_RX = re.compile(
    r"^(?:(?P<tipo>%s)\b\.?\s*)?(?:n\s*[.ºo°]*\s*)?(?P<num>\d[\d.]*)"
    r"\s*(?:-?\s*(?P<suf>[a-z])(?![a-z]))?\s*(?:-\s*(?P<reed>\d+))?"
    r"(?P<resto>.*)$" % "|".join("(?:%s)" % p for _, p in _TIPOS_PEDIDO))


def interpretar(texto: str, tipo_forcado: str | None = None) -> dict:
    "Texto digitado -> pedido. Aceita '9.784/1999', '9784/99', '9.784 de 1999',"

    bruto = (texto or "").strip()
    t = re.sub(r"\s+", " ", sem_acento(bruto).lower()).strip(" .")
    if not t:
        raise ErroPortal("entrada_nao_reconhecida", "texto vazio")
    if t in NOMES_DA_CONSTITUICAO:
        return {"modo": "constituicao", "tipo": "cf", "texto": bruto}
    chave = chave_nome(t)
    if chave in SIGLAS or chave in APELIDOS:
        tipo, numero, ano = SIGLAS.get(chave) or APELIDOS[chave]
        return {"modo": "numero", "tipo": tipo, "numero": numero, "sufixo": "",
                "reedicao": None, "ano": ano, "apelido": bruto, "texto": bruto}
    m = _PEDIDO_RX.match(t)
    if m and re.search(r"\d", m.group("num")):
        tipo = tipo_forcado
        if not tipo and m.group("tipo"):
            g = m.group("tipo")
            tipo = next(k for k, p in _TIPOS_PEDIDO if re.fullmatch(p, g))
        tipo = tipo or "lei"
        resto = m.group("resto") or ""
        ano = None
        a = re.search(r"(?:/|\bde\b|,)\s*(?:\d{1,2}\s*(?:de\s+[a-z]+\s+de|[./]\s*\d{1,2}\s*[./])\s*)?"
                      r"(\d{4}|\d{2})\b", resto)
        if a:
            ano = int(a.group(1))
            if ano < 100:
                hoje = time.localtime().tm_year % 100
                ano += 1900 if ano > hoje else 2000
        elif resto.strip():
            raise ErroPortal("entrada_nao_reconhecida",
                             "não entendi o que vem depois do número: %r" % resto.strip())
        if m.group("reed") and tipo != "mp":
            raise ErroPortal("entrada_nao_reconhecida",
                             "reedição ('-%s') só existe em medida provisória" % m.group("reed"))
        return {"modo": "numero", "tipo": tipo, "numero": int(re.sub(r"\D", "", m.group("num"))),
                "sufixo": (m.group("suf") or "").upper(),
                "reedicao": int(m.group("reed")) if m.group("reed") else None,
                "ano": ano, "texto": bruto}
    if re.search(r"[a-z]{3,}", t) and not re.search(r"\d", t):
        return {"modo": "nome", "tipo": None, "texto": bruto, "chave": chave}
    raise ErroPortal("entrada_nao_reconhecida",
                     "não reconheci norma em %r. Exemplos: '9.784/1999', 'lc 101/2000', "
                     "'decreto 10.000/2019', 'mp 2.200-2/2001', 'Código Penal', 'CLT'" % bruto)





def _casa(ato: dict, pedido: dict) -> bool:
    if ato["numero"] != pedido["numero"] or ato["sufixo"] != pedido["sufixo"]:
        return False
    if pedido.get("reedicao") is not None and (ato["reedicao"] or 0) != pedido["reedicao"]:
        return False
    return True


def _no_ano(ato: dict, ano: int | None, periodo: tuple[int, int]) -> bool:
    if ano is None:
        return True
    if ato.get("ano") is not None:
        return ato["ano"] == ano
    return periodo[0] <= ano <= periodo[1]


class Localizador:
    def __init__(self, portal: Portal):
        self.portal = portal


    def paginas_do_tipo(self, tipo: str) -> list[dict]:
        if tipo in PAGINAS_UNICAS:
            return [{"url": BASE + PAGINAS_UNICAS[tipo], "periodo": (0, 9999),
                     "rotulo": ROTULO_TIPO[tipo]}]
        url = BASE + INDICES[tipo]
        paginas = ler_indice(self.portal.ler(url), url)
        if not paginas:
            raise ErroPortal("formato_mudou",
                             "o índice %s não trouxe nenhuma página de ano ou faixa; o portal "
                             "mudou. Não devolvo 'não encontrada'." % url, url)
        return paginas

    def atos_da_pagina(self, pagina: dict, tipo: str) -> list[dict]:
        html = self.portal.ler(pagina["url"])
        lido = ler_listagem(html, pagina["url"], tipo, pagina["periodo"])
        if not lido["atos"]:
            raise ErroPortal("formato_mudou",
                             "a listagem %s não trouxe nenhum ato legível; o portal mudou." %
                             pagina["url"], pagina["url"])
        for a in lido["atos"]:
            a["pagina"] = pagina["url"]
            a["periodo"] = pagina["periodo"]
        return lido["atos"]

    def faixa(self, pagina: dict, tipo: str) -> tuple[int, int] | None:
        'Faixa de numeração da página, só com linhas cujo ano está no período (as referências'

        nums = [a["numero"] for a in self.atos_da_pagina(pagina, tipo)
                if a["principal"] and a["ano"] is not None
                and pagina["periodo"][0] <= a["ano"] <= pagina["periodo"][1]]
        return (min(nums), max(nums)) if nums else None


    def _procurar(self, paginas: list[dict], pedido: dict) -> list[dict]:
        achados = []
        for p in paginas:
            achados += [a for a in self.atos_da_pagina(p, pedido["tipo"])
                        if _casa(a, pedido) and _no_ano(a, pedido.get("ano"), p["periodo"])]
        return achados

    def _binaria(self, paginas: list[dict], pedido: dict) -> list[dict]:
        lo, hi = 0, len(paginas) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            f = self.faixa(paginas[mid], pedido["tipo"])
            if f is None:

                return self._procurar(paginas[lo:hi + 1], pedido)
            if pedido["numero"] < f[0]:
                hi = mid - 1
            elif pedido["numero"] > f[1]:
                lo = mid + 1
            else:
                achados = self._procurar([paginas[mid]], pedido)
                if achados:
                    return achados

                viz = [paginas[i] for i in (mid - 1, mid + 1) if 0 <= i < len(paginas)]
                return self._procurar(viz, pedido)
        return []

    def localizar(self, pedido: dict) -> dict:
        if pedido["modo"] == "constituicao":
            return self._constituicao(pedido)
        if pedido["modo"] == "nome":
            return self._por_nome(pedido)
        tipo = pedido["tipo"]
        paginas = self.paginas_do_tipo(tipo)
        observacao = None
        if pedido.get("ano"):
            alvo = [p for p in paginas if p["periodo"][0] <= pedido["ano"] <= p["periodo"][1]]
            if not alvo:
                return self._falha(pedido, "ano_sem_listagem",
                                   "o portal não tem listagem de %s que cubra %s" %
                                   (ROTULO_TIPO[tipo], pedido["ano"]), paginas)
            achados = self._procurar(alvo, pedido)
            if not achados:
                dica = None
                if tipo == "lei":
                    outros = self._binaria(paginas, {**pedido, "ano": None})
                    if outros:
                        dica = "há %s; confira o ano digitado" % ", ".join(
                            sorted({a["rotulo"] for a in outros}))
                return self._falha(pedido, "nao_encontrada_no_ano",
                                   "%s nº %s não está na listagem de %s%s" % (
                                       ROTULO_TIPO[tipo], _numero_fmt(pedido), pedido["ano"],
                                       " (" + dica + ")" if dica else ""), alvo)
        elif tipo == "lei" and len(paginas) > 1:
            achados = self._binaria(paginas, pedido)


            antigas = [p for p in paginas if p["periodo"][0] == 0]
            achados += [a for a in self._procurar(antigas, pedido)
                        if a.get("ano") is not None and a["ano"] < 1946]
        elif tipo == "decreto":
            novos = [p for p in paginas if p["periodo"][0] >= 1992]
            achados = self._binaria(novos, pedido) if novos else []
            if not achados:
                achados = self._procurar([p for p in paginas if p["periodo"] == (1991, 1991)],
                                         pedido)
            if not achados:
                velhos = [p for p in paginas if p["periodo"][1] < 1991]
                achados = self._procurar(velhos, pedido)
            else:
                observacao = ("sem ano, vale a numeração de decreto reiniciada em 1991; para "
                              "decreto anterior, informe o ano")
        else:
            achados = self._procurar(paginas, pedido)
        if not achados:
            return self._falha(pedido, "nao_encontrada",
                               "%s nº %s não está nas listagens do portal" %
                               (ROTULO_TIPO[tipo], _numero_fmt(pedido)), paginas)
        escolhido, candidatos = _escolher(achados, pedido)
        if escolhido is None:
            return {"ok": False, "erro": "ambigua",
                    "mensagem": "mais de uma norma com este número; informe o ano",
                    "pedido": _pedido_publico(pedido), "candidatos": candidatos,
                    **self._rastro()}
        if escolhido.get("link_diverge"):
            return {"ok": False, "erro": "link_diverge_do_rotulo",
                    "mensagem": ("a linha '%s' do portal liga a um arquivo com outro número (%s). "
                                 "O portal trocou o link; não devolvo endereço de outra norma. "
                                 "Abra a listagem e confira a norma pelo título da página."
                                 % (escolhido["rotulo"], escolhido["url"])),
                    "url_publicada": escolhido["url"],
                    "pagina_de_listagem": escolhido["pagina"],
                    "pedido": _pedido_publico(pedido), **self._rastro()}
        if tipo == "mp" and not pedido.get("ano") and pedido["numero"] <= MP_MAIOR_ANTIGA \
                and all((a.get("ano") or a["periodo"][0]) >= 2001 for a in achados):
            observacao = ("sem ano: a numeração de MP reiniciou com a EC 32/2001 e há MP %s "
                          "anterior possível; para a série antiga, informe o ano"
                          % _numero_fmt(pedido))
        return self._sucesso(pedido, escolhido, observacao)

    def _constituicao(self, pedido: dict) -> dict:
        url = BASE + PAGINAS_DE_NOMES[0]
        for u, inner in _ancoras(self.portal.ler(url), url):
            if chave_nome(texto_limpo(inner)) == "constituicao" and not _e_menu(u):
                return {"ok": True, "url": u, "equivalente_planalto": equivalente_planalto(u),
                        "norma": {"tipo": "cf", "rotulo": "Constituição Federal de 1988"},
                        "pagina_de_listagem": url, "pedido": _pedido_publico(pedido),
                        **self._rastro()}
        return self._falha(pedido, "formato_mudou",
                           "a página %s não traz mais o link da Constituição" % url, [])

    def _por_nome(self, pedido: dict) -> dict:
        itens = []
        for caminho in PAGINAS_DE_NOMES:
            url = BASE + caminho
            for it in ler_cartoes(self.portal.ler(url), url):
                itens.append({**it, "pagina": url})
        if not itens:
            raise ErroPortal("formato_mudou", "Códigos e Estatutos sem nenhum item legível")
        chave = pedido["chave"]
        exatos = [i for i in itens if chave_nome(i["nome"]) == chave]
        if len(exatos) == 1:
            i = exatos[0]
            return {"ok": True, "url": i["url"], "equivalente_planalto": equivalente_planalto(i["url"]),
                    "norma": {"nome": i["nome"], "rotulo": i["norma"]},
                    "pagina_de_listagem": i["pagina"], "pedido": _pedido_publico(pedido),
                    **self._rastro()}
        palavras = chave.split()
        parciais = [i for i in itens if all(p in chave_nome(i["nome"]).split()
                                            or p in chave_nome(i["nome"]) for p in palavras)]
        lista = exatos or parciais
        if not lista:
            return self._falha(pedido, "nao_encontrada",
                               "nenhum código ou estatuto com o nome %r; tente o número da norma"
                               % pedido["texto"], [{"url": BASE + c} for c in PAGINAS_DE_NOMES])
        return {"ok": False, "erro": "ambigua",
                "mensagem": "mais de um item com este nome; escolha um",
                "pedido": _pedido_publico(pedido),
                "candidatos": [{"nome": i["nome"], "norma": i["norma"], "url": i["url"]}
                               for i in lista], **self._rastro()}


    def _rastro(self) -> dict:
        return {"acessos_rede": self.portal.acessos_rede, "paginas_lidas": len(self.portal.lidas),
                "fonte": BASE, "motor": ENGINE_VERSION}

    def _sucesso(self, pedido: dict, ato: dict, observacao: str | None) -> dict:
        out = {"ok": True, "url": ato["url"], "equivalente_planalto": equivalente_planalto(ato["url"]),
               "norma": {"tipo": pedido["tipo"], "numero": ato["numero"], "sufixo": ato["sufixo"],
                         "reedicao": ato["reedicao"], "ano": ato.get("ano"),
                         "rotulo_no_portal": ato["rotulo"], "ementa": ato.get("ementa", "")},
               "pagina_de_listagem": ato["pagina"], "pedido": _pedido_publico(pedido),
               **self._rastro()}
        if observacao:
            out["observacao"] = observacao
        return out

    def _falha(self, pedido: dict, codigo: str, mensagem: str, paginas: list) -> dict:
        return {"ok": False, "erro": codigo, "mensagem": mensagem,
                "pedido": _pedido_publico(pedido),
                "listas_do_portal": [p["url"] for p in paginas][:12] or
                [BASE + INDICES.get(pedido.get("tipo") or "", PAGINAS_UNICAS.get(
                    pedido.get("tipo") or "", "pages/leis-ordinarias.html"))],
                **self._rastro()}


def _numero_fmt(pedido: dict) -> str:
    n = "{:,}".format(pedido["numero"]).replace(",", ".")
    if pedido.get("sufixo"):
        n += "-" + pedido["sufixo"]
    if pedido.get("reedicao") is not None:
        n += "-%s" % pedido["reedicao"]
    return n


def _pedido_publico(pedido: dict) -> dict:
    return {k: v for k, v in pedido.items() if k not in ("chave",)}


def _escolher(achados: list[dict], pedido: dict):
    'Uma norma ou lista. Mesma URL é o mesmo ato. Em MP sem reedição pedida, vale a reedição'

    unicos = list({a["url"]: a for a in achados}.values())
    if len(unicos) == 1:
        return unicos[0], None
    if pedido["tipo"] == "mp" and pedido.get("reedicao") is None:
        def ano_de(a):
            return a["ano"] if a.get("ano") is not None else a["periodo"][1]
        anos = sorted(ano_de(a) for a in unicos)
        if anos[-1] - anos[0] <= 3:
            return max(unicos, key=lambda a: ((a["reedicao"] or 0), a["principal"])), None
    candidatos = [{"rotulo": a["rotulo"], "ano": a.get("ano"), "url": a["url"],
                   "periodo_da_pagina": "%s–%s" % a["periodo"] if a["periodo"][0] else
                   "até %s" % a["periodo"][1], "ementa": a.get("ementa", "")[:160],
                   **({"link_diverge_do_rotulo": True} if a.get("link_diverge") else {})}
                  for a in unicos]
    return None, candidatos


def equivalente_planalto(url: str) -> str | None:
    'O mesmo caminho `ccivil_03/...` em www.planalto.gov.br (medido: o planalto antigo serve o'

    partes = urllib.parse.urlsplit(url)
    if partes.hostname == HOST_PLANALTO:
        return url
    if partes.hostname == HOST and partes.path.startswith("/ccivil_03/"):
        return "https://%s%s" % (HOST_PLANALTO, partes.path)
    return None





def auditar(portal: Portal) -> dict:
    """Passa o parser por TODAS as listagens e conta os links de ato que ele não entende."""
    loc = Localizador(portal)
    relatorio = {"paginas": [], "atos": 0, "nao_entendidos": 0}
    for tipo in ("lei", "decreto", "dl", "mp", "lc", "ldl", "ec"):
        for p in loc.paginas_do_tipo(tipo):
            lido = ler_listagem(portal.ler(p["url"]), p["url"], tipo, p["periodo"])
            fora = [a for a in lido["atos"] if a["principal"] and a["ano"] is not None
                    and not p["periodo"][0] <= a["ano"] <= p["periodo"][1]]
            sem_ano = [a for a in lido["atos"] if a["principal"] and a["ano"] is None]
            diverge = [{"rotulo": a["rotulo"], "url": a["url"]} for a in lido["atos"]
                       if a.get("link_diverge")]
            relatorio["paginas"].append({
                "tipo": tipo, "url": p["url"], "linhas": lido["linhas"],
                "atos": len(lido["atos"]), "nao_entendidos": lido["nao_entendidos"],
                "ano_fora_do_periodo": [a["rotulo"] for a in fora],
                "sem_ano": len(sem_ano), "link_diverge": diverge})
            relatorio["atos"] += len(lido["atos"])
            relatorio["nao_entendidos"] += len(lido["nao_entendidos"])
            relatorio["link_diverge"] = relatorio.get("link_diverge", 0) + len(diverge)
    relatorio.update(acessos_rede=portal.acessos_rede, motor=ENGINE_VERSION)
    return relatorio





def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("norma", nargs="?", help="'9.784/1999', 'lc 101/2000', 'Código Penal', 'CLT'...")
    ap.add_argument("--tipo", choices=sorted(PREFIXOS_ACEITOS), help="força o tipo da norma")
    ap.add_argument("--html-dir", help="plano B: pasta com as páginas do portal já obtidas "
                    "(nome = caminho com '/' trocado por '__')")
    ap.add_argument("--sem-cache", action="store_true", help="ignora o cache de 2 horas")
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--auditar", action="store_true",
                    help="passa o parser por todas as listagens e relata o que ele não entende")
    args = ap.parse_args(argv)
    portal = Portal(html_dir=args.html_dir, usar_cache=not args.sem_cache, timeout=args.timeout)

    def emitir(obj):
        print(json.dumps(obj, ensure_ascii=False, indent=2))

    try:
        if args.auditar:
            rel = auditar(portal)
            emitir(rel)
            return 0 if rel["nao_entendidos"] == 0 else 1
        if not args.norma:
            ap.error("informe a norma, ou --auditar")
        pedido = interpretar(args.norma, args.tipo)
        res = Localizador(portal).localizar(pedido)
        emitir(res)
        return 0 if res["ok"] else (2 if res["erro"] == "formato_mudou" else 1)
    except ErroPortal as exc:
        emitir({"ok": False, "erro": exc.codigo, "mensagem": exc.mensagem, "url": exc.url,
                "acessos_rede": portal.acessos_rede, "motor": ENGINE_VERSION})
        return 3 if exc.codigo == "entrada_nao_reconhecida" else 2
    except Exception as exc:
        emitir({"ok": False, "erro": "erro_interno",
                "mensagem": "falha não prevista (%s: %s); não é 'norma inexistente'"
                % (type(exc).__name__, exc),
                "acessos_rede": portal.acessos_rede, "motor": ENGINE_VERSION})
        return 4


if __name__ == "__main__":
    sys.exit(main())
