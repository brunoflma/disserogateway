#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'checklist_protocolo.py — conferência da peça contra a juntada antes do protocolo.'










































import argparse
import json
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import juntada_contract as jc



DOC_RX = re.compile(r"\(Doc\.\s*0*(\d+)")

ARQUIVO_DOC_RX = re.compile(r"^Doc\.?\s*0*(\d{1,3})(?!\d)", re.I)
VALOR_RX = re.compile(r"^(?:R\$\s*)?(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{2}))?$")
FASES_ESTADO = ("briefing", "estrategia", "mapa")
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class Entrada(Exception):
    def __init__(self, codigo, mensagem, exit_code=1, erros=None):
        super().__init__(mensagem)
        self.codigo, self.mensagem, self.exit_code, self.erros = codigo, mensagem, exit_code, erros


def _pendencia(codigo, mensagem, **extra):
    p = {"codigo": codigo, "mensagem": mensagem, "bloqueia": False}
    p.update(extra)
    return p


def texto_da_peca(caminho):
    if not os.path.isfile(caminho):
        raise Entrada("peca_nao_encontrada", f"a peça não foi encontrada: {caminho}", 2)
    try:
        if caminho.lower().endswith(".docx"):
            partes = []
            with zipfile.ZipFile(caminho) as z:
                for nome in ("word/document.xml", "word/footnotes.xml", "word/endnotes.xml"):
                    try:
                        xml = z.read(nome)
                    except KeyError:
                        if nome == "word/document.xml":
                            raise
                        continue
                    raiz = ET.fromstring(xml)
                    partes.extend("".join(t.text or "" for t in p.iter(W + "t"))
                                  for p in raiz.iter(W + "p"))
            return "\n".join(partes)
        with open(caminho, encoding="utf-8") as fh:
            return fh.read()
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError, UnicodeDecodeError):
        raise Entrada("peca_ilegivel", "a peça não pôde ser lida; salve-a de novo como .docx, "
                                       ".md ou .txt")


def citados_na_ordem(texto):
    ordem = []
    for m in DOC_RX.finditer(texto or ""):
        n = int(m.group(1))
        if n not in ordem:
            ordem.append(n)
    return ordem


def carregar_juntada(caminho):
    if not os.path.isfile(caminho):
        raise Entrada("juntada_nao_encontrada", f"o registro da juntada não foi encontrado: {caminho}", 2)
    try:
        with open(caminho, encoding="utf-8") as fh:
            tracker = json.load(fh)
    except (OSError, ValueError):
        raise Entrada("juntada_ilegivel", "o registro da juntada não pôde ser lido")
    erros = (["o arquivo não é um objeto JSON"] if not isinstance(tracker, dict)
             else jc.validar_documento(tracker))
    if erros:
        raise Entrada("juntada_fora_do_contrato",
                      "o registro da juntada não está no formato esperado; valide de novo o "
                      "registro da juntada antes desta conferência", erros=erros[:3])
    return tracker


def arquivos_da_pasta(pasta):
    if not os.path.isdir(pasta):
        raise Entrada("pasta_nao_encontrada", f"a pasta de juntada não foi encontrada: {pasta}", 2)
    por_numero = {}
    for nome in sorted(os.listdir(pasta)):
        m = ARQUIVO_DOC_RX.match(nome)
        if m and os.path.isfile(os.path.join(pasta, nome)):
            por_numero.setdefault(int(m.group(1)), []).append(nome)
    return por_numero


def centavos(valor):
    """Centavos inteiros de "R$ 1.234,56", "1234,56" ou "R$ 1.000"; None se não for valor legível."""
    if not isinstance(valor, str):
        return None
    m = VALOR_RX.match(valor.strip())
    if not m:
        return None
    return int(m.group(1).replace(".", "")) * 100 + int(m.group(2) or 0)


def reais(c):
    inteiro = f"{c // 100:,}".replace(",", ".")
    return f"R$ {inteiro},{c % 100:02d}"


def declarado_no_estado(caminho):
    '{campo: valor} das evidências do briefing, da estratégia e do mapa (a fase posterior'

    if not os.path.isfile(caminho):
        raise Entrada("estado_nao_encontrado", f"o estado da peça não foi encontrado: {caminho}", 2)
    try:
        with open(caminho, encoding="utf-8") as fh:
            st = json.load(fh)
    except (OSError, ValueError):
        raise Entrada("estado_ilegivel", "o estado da peça não pôde ser lido")
    fases = st.get("fases") if isinstance(st, dict) else None
    if not isinstance(fases, dict):
        raise Entrada("estado_ilegivel", "o estado da peça não tem o registro das fases")
    fonte = {}
    for nome in FASES_ESTADO:
        ev = (fases.get(nome) or {}).get("evidencia") if isinstance(fases.get(nome), dict) else None
        if isinstance(ev, dict):
            fonte.update({k: ev[k] for k in ("valor_causa", "pedidos_liquidos", "classe", "assunto")
                          if k in ev})
    return fonte


def conferir_documentos(citados, tracker, pasta_por_numero):
    pend, lint = [], []
    registro = jc.indexar_por_numero(tracker) if tracker is not None else None
    if registro is None:
        if citados:
            lint.append({"codigo": "citado_sem_registro", "regra": "L13", "documentos": citados,
                         "mensagem": "a peça cita documento e o registro da juntada não foi "
                                     "apresentado; a revisão automática da peça já a recusa por isso"})
        return pend, lint
    for n in citados:
        doc = registro.get(n)
        if doc is None:
            lint.append({"codigo": "citado_sem_registro", "regra": "CRUZAMENTO-DOC", "documentos": [n],
                         "mensagem": f"o Doc. {n:02d} é citado na peça e não consta do registro da "
                                     "juntada; a revisão automática da peça já a recusa por isso"})
        elif doc.get("status") != "curado":
            lint.append({"codigo": "citado_nao_curado", "regra": "CRUZAMENTO-DOC", "documentos": [n],
                         "mensagem": f"o Doc. {n:02d} é citado na peça e ainda não está pronto na "
                                     "juntada; a revisão automática da peça já a recusa por isso"})
        elif pasta_por_numero is not None and doc.get("status") == "curado" and n not in pasta_por_numero:
            pend.append(_pendencia(
                "citado_sem_arquivo_na_pasta",
                f"O Doc. {n:02d} ({doc.get('descricao')}) é citado na peça e não há arquivo "
                f"\"Doc. {n:02d} - ...\" na pasta de juntada. Copie o arquivo curado para a pasta "
                "antes do protocolo.", documento=n))
    for n, doc in sorted(registro.items()):
        status = doc.get("status")
        if status == "gerado" or n in citados:
            continue
        if status == "curado":
            pend.append(_pendencia(
                "juntado_nao_citado",
                f"O Doc. {n:02d} ({doc.get('descricao')}) está na juntada e a peça não o cita. "
                "Cite-o no ponto em que ele prova o fato, ou retire-o da juntada e renumere os "
                "seguintes.", documento=n))
        else:


            pend.append(_pendencia(
                "juntado_pendente_de_curadoria",
                f"O Doc. {n:02d} ({doc.get('descricao')}) está registrado e ainda não pode ser "
                "citado (ilegível ou não curado). Obtenha cópia legível e cure-o, ou retire-o da "
                "juntada e renumere os seguintes.", documento=n, status=status))
    for n, nomes in sorted((pasta_por_numero or {}).items()):
        if n not in registro:
            pend.append(_pendencia(
                "arquivo_sem_registro",
                f"Há na pasta de juntada o arquivo {', '.join(nomes)}, e o Doc. {n:02d} não consta do "
                "registro da juntada. Registre-o ou retire-o da pasta antes do protocolo.",
                documento=n))
    return pend, lint


def conferir_estado(fonte):
    pend, nao = [], []
    valor_causa, liquidos = fonte.get("valor_causa"), fonte.get("pedidos_liquidos")
    if valor_causa is None or liquidos is None:
        falta = " e ".join(x for x, v in (("o valor da causa", valor_causa),
                                           ("os pedidos líquidos com valor", liquidos)) if v is None)
        nao.append({"codigo": "valor_causa_nao_conferido",
                    "mensagem": f"o valor da causa não foi confrontado com os pedidos: o estado da "
                                f"peça não declara {falta}."})
    else:
        alvo = centavos(valor_causa)
        if alvo is None:
            pend.append(_pendencia("valor_ilegivel", f"O valor da causa declarado ({valor_causa!r}) "
                                   "não é um valor legível. Escreva-o como \"R$ 50.000,00\"."))
        if isinstance(liquidos, list) and not liquidos:


            nao.append({"codigo": "valor_causa_sem_pedido_liquido",
                        "mensagem": "não há pedido líquido declarado; o valor da causa não foi "
                                    "confrontado com soma de pedidos."})
        elif not isinstance(liquidos, list):
            pend.append(_pendencia("valor_ilegivel", "Os pedidos líquidos declarados não formam uma "
                                   "lista de pedidos com valor."))
            liquidos = []
        soma, legiveis = 0, True
        for i, item in enumerate(liquidos, 1):
            pedido = item.get("pedido") if isinstance(item, dict) else None
            c = centavos(item.get("valor")) if isinstance(item, dict) else None
            if c is None:
                legiveis = False
                pend.append(_pendencia("valor_ilegivel", f"O {i}º pedido líquido "
                                       f"({pedido or 'sem descrição'}) não traz valor legível. "
                                       "Escreva-o como \"R$ 10.000,00\"."))
            else:
                soma += c
        if alvo is not None and liquidos and legiveis and soma != alvo:
            pend.append(_pendencia(
                "valor_causa_diverge_soma",
                f"O valor da causa ({reais(alvo)}) difere da soma dos pedidos líquidos declarados "
                f"({reais(soma)}). Na cumulação, o valor da causa é a soma dos pedidos (CPC, art. "
                "292, VI); confira se há pedido alternativo, subsidiário ou ilíquido que explique "
                "a diferença.", valor_causa=reais(alvo), soma_pedidos=reais(soma)))
    for campo, codigo, rotulo in (("classe", "classe_vazia", "a classe processual"),
                                  ("assunto", "assunto_vazio", "o assunto")):
        if campo not in fonte:
            nao.append({"codigo": f"{campo}_nao_conferido",
                        "mensagem": f"o estado da peça não declara {rotulo}; não foi conferido."})
        elif not isinstance(fonte[campo], str) or not fonte[campo].strip():
            pend.append(_pendencia(codigo, f"O estado da peça registra {rotulo} em branco. "
                                   f"Preencha {rotulo} antes do protocolo."))
    return pend, nao


def conferir(peca, juntada=None, pasta=None, state=None):
    citados = citados_na_ordem(texto_da_peca(peca))
    tracker = carregar_juntada(juntada) if juntada else None
    pasta_por_numero = arquivos_da_pasta(pasta) if pasta else None
    pend, lint = conferir_documentos(citados, tracker, pasta_por_numero)
    nao = []
    if tracker is None:
        nao.append({"codigo": "juntada_nao_conferida",
                    "mensagem": "o registro da juntada não foi informado; documentos juntados e "
                                "não citados não foram conferidos."})
    if pasta is None:
        nao.append({"codigo": "pasta_nao_conferida",
                    "mensagem": "a pasta de juntada não foi informada; a presença dos arquivos "
                                "não foi conferida."})
    if state:
        p2, n2 = conferir_estado(declarado_no_estado(state))
        pend += p2
        nao += n2
    else:
        nao.append({"codigo": "estado_nao_conferido",
                    "mensagem": "o estado da peça não foi informado; valor da causa, classe e "
                                "assunto não foram conferidos."})
    registrados = sorted(jc.indexar_por_numero(tracker)) if tracker is not None else []
    return {"ok": True, "pendencias": pend, "ja_apontado_pelo_lint": lint, "nao_conferido": nao,
            "citados": citados, "registrados": registrados}


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Confere a peça contra a juntada antes do protocolo")
    ap.add_argument("--peca", required=True, help="a peça (.docx, .md ou .txt)")
    ap.add_argument("--juntada", help="JUNTADA_TRACKER.json do caso")
    ap.add_argument("--pasta-juntada", help="pasta com os arquivos \"Doc. NN - ...\"")
    ap.add_argument("--state", help="PECA_STATE.json da peça (valor da causa, classe, assunto)")
    args = ap.parse_args(argv)
    try:
        saida, code = conferir(args.peca, args.juntada, args.pasta_juntada, args.state), 0
    except Entrada as e:
        saida, code = {"ok": False, "codigo": e.codigo, "mensagem": e.mensagem}, e.exit_code
        if e.erros:
            saida["erros_do_registro"] = e.erros
    print(json.dumps(saida, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
