#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'contar_paginas.py — quantas folhas a peça TEM, medindo; nunca estimando.'












from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import docx_para_pdf

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

_RX_PAGES_PDFINFO = re.compile(r"^Pages:\s*(\d+)", re.M)

_RX_PAGE_OBJ = re.compile(rb"/Type\s*/Page[^s]")


def _por_pdfinfo(pdf):
    exe = shutil.which("pdfinfo")
    if not exe:
        return None
    try:



        r = subprocess.run([exe, pdf], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=60)
        m = _RX_PAGES_PDFINFO.search(r.stdout or "")
        return int(m.group(1)) if m else None
    except Exception:
        return None


def _por_varredura(pdf):
    'Conta objetos de página no próprio PDF. Menos exato que o `pdfinfo` em PDF com fluxos'


    try:
        with open(pdf, "rb") as fh:
            return len(_RX_PAGE_OBJ.findall(fh.read())) or None
    except Exception:
        return None


def _renderizar_e_contar(docx, destino, mostrar_pdf):
    pdf, rota = docx_para_pdf.converter(docx, destino)
    if not pdf:
        raise RuntimeError(
            "nenhuma rota de render disponível (Word/COM ou LibreOffice). Sem render não há "
            "contagem, e ESTIMAR está proibido: a estimativa aritmética sobre a fonte erra "
            "porque a paginação não acompanha o texto. Instale o LibreOffice, ou abra o .docx "
            "no Word e leia a contagem de páginas na barra de status")
    for nome, fn in (("pdfinfo", _por_pdfinfo), ("varredura", _por_varredura)):
        n = fn(pdf)
        if n:
            return n, rota, nome
    gerado = f"PDF gerado ({pdf})" if mostrar_pdf else "PDF gerado"
    raise RuntimeError(f"{gerado} mas a contagem de páginas falhou nas duas rotas")


def contar(docx, manter_pdf=None):
    '(paginas, rota_render, rota_contagem). Levanta RuntimeError sem rota de render ou sem'


    if manter_pdf:
        return _renderizar_e_contar(docx, manter_pdf, mostrar_pdf=True)
    work = tempfile.mkdtemp(prefix="dsr_paginas_")
    try:
        return _renderizar_e_contar(docx, os.path.join(work, "peca.pdf"), mostrar_pdf=False)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(
        description="Conta as folhas de um .docx renderizando — nunca estimando")
    ap.add_argument("docx")
    ap.add_argument("--comparar", metavar="ANTES",
                    help="segundo .docx: mede os dois e devolve a DIFERENÇA real de folhas")
    ap.add_argument("--manter-pdf", metavar="PDF", help="guarda o PDF renderizado")
    a = ap.parse_args()

    try:
        paginas, rota, contagem = contar(a.docx, a.manter_pdf)
    except FileNotFoundError as e:
        print(json.dumps({"ok": False, "erro": f"arquivo não encontrado: {e}"},
                         ensure_ascii=False))
        return 2
    except RuntimeError as e:
        print(json.dumps({"ok": False, "erro": str(e)}, ensure_ascii=False))
        return 2

    saida = {"ok": True, "arquivo": a.docx, "paginas": paginas,
             "rota_render": rota, "rota_contagem": contagem}
    if a.comparar:
        try:
            antes, _r, _c = contar(a.comparar)
        except (FileNotFoundError, RuntimeError) as e:
            print(json.dumps({**saida, "erro_comparacao": str(e)}, ensure_ascii=False))
            return 0
        saida["comparado_com"] = a.comparar
        saida["paginas_antes"] = antes
        saida["diferenca"] = antes - paginas
        saida["resumo"] = (
            f"{antes} → {paginas} folhas: "
            + (f"devolveu {antes - paginas} folha(s)" if antes > paginas
               else (f"acrescentou {paginas - antes} folha(s)" if paginas > antes
                     else "MESMA paginação — o ajuste não devolveu folha alguma"))
            + ". Medido no render, não estimado.")
    else:
        saida["resumo"] = f"{paginas} folha(s), medidas no render ({rota})"
    print(json.dumps(saida, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
