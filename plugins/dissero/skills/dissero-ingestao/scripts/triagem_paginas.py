#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'triagem_paginas.py - decide OCR PAGINA A PAGINA, e nunca toca no original.'





























from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

MINIMO_LETRAS = 40




TIMEOUT = 180


_LETRA = re.compile(r"[0-9A-Za-zÀ-ÖØ-öø-ÿ]")
_PAGINAS = re.compile(r"^Pages:\s+(\d+)\s*$", re.MULTILINE)

FERRAMENTAS = ("pdftotext", "pdfinfo", "pdfseparate", "pdfunite")

REMEDIO = ("instale o poppler-utils (Windows: `winget install oschwartz10612.Poppler`; "
           "Debian/Ubuntu: `apt install poppler-utils`; macOS: `brew install poppler`) ou "
           "informe o caminho por --pdftotext/--pdfinfo/--pdfseparate/--pdfunite")


class Indisponivel(RuntimeError):
    """Binario do poppler ausente. Erro com remedio, nunca stack trace."""


def achar(nome, informado=None):
    'Caminho do binario, ou Indisponivel com o remedio junto.'




    if informado:
        if os.path.isfile(informado):
            return informado
        pelo_path = shutil.which(informado)
        if pelo_path:
            return pelo_path
        raise Indisponivel(f"{nome} informado nao existe ou nao e arquivo: {informado}. "
                           f"{REMEDIO}")
    caminho = shutil.which(nome) or shutil.which(nome + ".exe")
    if not caminho:
        raise Indisponivel(f"{nome} nao encontrado no PATH - sem ele nao ha triagem por "
                           f"pagina, e adivinhar pelo documento inteiro seria chamar de "
                           f"triagem por pagina o que nao e. {REMEDIO}")
    return caminho


def sha256_arquivo(caminho):
    digest = hashlib.sha256()
    with open(caminho, "rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1 << 20), b""):
            digest.update(bloco)
    return digest.hexdigest()


def contar_paginas(pdf, pdfinfo=None):
    exe = achar("pdfinfo", pdfinfo)
    proc = subprocess.run([exe, pdf], capture_output=True, timeout=TIMEOUT)
    saida = proc.stdout.decode("utf-8", "replace")
    achado = _PAGINAS.search(saida)
    if not achado:
        raise Indisponivel(f"pdfinfo nao devolveu contagem de paginas para {pdf} - arquivo "
                           "corrompido ou nao e PDF")
    return int(achado.group(1))


def texto_da_pagina(pdf, numero, pdftotext=None):
    'Camada de texto de UMA pagina.'



    exe = achar("pdftotext", pdftotext)
    proc = subprocess.run([exe, "-layout", "-enc", "UTF-8", "-f", str(numero), "-l",
                           str(numero), pdf, "-"], capture_output=True, timeout=TIMEOUT)
    return proc.stdout.decode("utf-8", "replace")


def letras(texto):
    return len(_LETRA.findall(texto or ""))


def classificar_pagina(texto, minimo_letras=MINIMO_LETRAS):
    "('ler'|'ocr', letras). 'ler' = a camada de texto serve; 'ocr' = a pagina precisa de OCR."





    n = letras(texto)
    return ("ler" if n >= minimo_letras else "ocr"), n


def triar(pdf, minimo_letras=MINIMO_LETRAS, pdftotext=None, pdfinfo=None, ler_pagina=None):
    """Relatorio da triagem. `ler_pagina(n)` injetavel para teste sem poppler."""
    total = contar_paginas(pdf, pdfinfo)
    if ler_pagina is None:
        def ler_pagina(n):
            return texto_da_pagina(pdf, n, pdftotext)

    paginas, para_ocr, para_ler = [], [], []
    for numero in range(1, total + 1):
        acao, n = classificar_pagina(ler_pagina(numero), minimo_letras)
        paginas.append({"pagina": numero, "acao": acao, "letras": n})
        (para_ocr if acao == "ocr" else para_ler).append(numero)

    return {
        "arquivo": os.path.basename(pdf),
        "sha256_original": sha256_arquivo(pdf),
        "paginas_total": total,
        "paginas": paginas,
        "paginas_para_ocr": para_ocr,
        "paginas_com_texto": para_ler,
        "economia_paginas": len(para_ler),


        "economia_fracao": round(len(para_ler) / total, 4) if total else 0.0,
        "limiares": {"minimo_letras": minimo_letras},
        "rota_sugerida": ("nativo" if not para_ocr else
                          ("ocr_total" if not para_ler else "ocr_parcial")),
        "aviso": ("Triagem NAO altera o original. Quando houver pagina para OCR, use "
                  "--extrair para gerar um PDF DERIVADO so com elas; o original fica intocado "
                  "e seu sha256 esta neste relatorio."),
    }


def _mesmo_arquivo(a, b):
    'True se os dois caminhos apontam o MESMO arquivo. `os.path.samefile` e o unico jeito'


    try:
        return os.path.samefile(a, b)
    except Exception:
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def extrair_paginas(pdf, paginas, destino, pdfseparate=None, pdfunite=None, forcar=False):
    'PDF NOVO com apenas `paginas`. NUNCA escreve no original.'




    if not paginas:
        raise ValueError("nenhuma pagina a extrair - nada a fazer")
    if _mesmo_arquivo(pdf, destino):
        raise ValueError("RECUSADO: o destino e o proprio original. Este modulo nao reescreve "
                         "o documento de origem em hipotese nenhuma - extraia para um arquivo "
                         "NOVO e mantenha o original intocado")
    if os.path.exists(destino) and not forcar:
        raise ValueError(f"RECUSADO: {destino} ja existe. Use --forcar se a sobrescrita for "
                         "mesmo o que se quer")

    sha_antes = sha256_arquivo(pdf)
    exe_sep = achar("pdfseparate", pdfseparate)
    exe_uni = achar("pdfunite", pdfunite)
    tmp = tempfile.mkdtemp(prefix="triagem-")
    try:
        soltas = []
        for numero in paginas:
            saida = os.path.join(tmp, "p-%05d.pdf" % numero)
            subprocess.run([exe_sep, "-f", str(numero), "-l", str(numero), pdf, saida],
                           capture_output=True, timeout=TIMEOUT, check=True)
            soltas.append(saida)
        subprocess.run([exe_uni] + soltas + [destino], capture_output=True, timeout=TIMEOUT,
                       check=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    sha_depois = sha256_arquivo(pdf)
    if sha_antes != sha_depois:


        raise RuntimeError("O ORIGINAL MUDOU durante a extracao (sha256 antes != depois). "
                           "Pare e confira o arquivo de origem antes de qualquer coisa")
    return {"destino": destino, "paginas": list(paginas), "sha256_original": sha_antes,
            "sha256_destino": sha256_arquivo(destino)}


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(
        description="Decide OCR pagina a pagina e, opcionalmente, extrai so as paginas que "
                    "precisam para um PDF NOVO. Nunca altera o original.")
    ap.add_argument("arquivo", help="caminho do PDF")
    ap.add_argument("--minimo-letras", type=int, default=MINIMO_LETRAS, dest="minimo_letras",
                    help=f"letras na camada de texto para a pagina contar como LIDA (padrao "
                         f"{MINIMO_LETRAS}). Baixar deixa carimbo de scanner passar por "
                         "leitura; subir manda pagina boa para a rota paga.")
    ap.add_argument("--extrair", default=None,
                    help="gera um PDF NOVO com apenas as paginas que precisam de OCR")
    ap.add_argument("--forcar", action="store_true",
                    help="permite sobrescrever o arquivo de --extrair se ele ja existir")
    ap.add_argument("--json", action="store_true", help="imprime o relatorio como JSON")
    for nome in FERRAMENTAS:
        ap.add_argument("--" + nome, default=None, dest=nome,
                        help=f"caminho do binario {nome} (padrao: PATH)")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.arquivo):
        print(f"ERRO {args.arquivo} nao e um arquivo")
        return 2
    try:
        relatorio = triar(args.arquivo, args.minimo_letras, args.pdftotext, args.pdfinfo)
        if args.extrair and relatorio["paginas_para_ocr"]:
            relatorio["extracao"] = extrair_paginas(
                args.arquivo, relatorio["paginas_para_ocr"], args.extrair,
                args.pdfseparate, args.pdfunite, args.forcar)
        elif args.extrair:
            relatorio["extracao"] = None
            print("NADA A EXTRAIR: nenhuma pagina precisa de OCR")
    except (Indisponivel, ValueError) as erro:
        print("ERRO " + str(erro))
        return 2

    if args.json:
        print(json.dumps(relatorio, ensure_ascii=False, indent=2))
        return 0

    print(f"TRIAGEM {relatorio['arquivo']}: {relatorio['paginas_total']} pagina(s), "
          f"{len(relatorio['paginas_para_ocr'])} para OCR, "
          f"{relatorio['economia_paginas']} ja legivel(is) "
          f"({relatorio['economia_fracao']:.0%} do documento) "
          f"[minimo_letras={args.minimo_letras}]")
    print(f"ROTA SUGERIDA: {relatorio['rota_sugerida']}")
    if relatorio["paginas_para_ocr"]:
        print("PARA OCR: " + ", ".join(str(p) for p in relatorio["paginas_para_ocr"]))
    if relatorio.get("extracao"):
        print(f"DERIVADO {relatorio['extracao']['destino']} "
              f"({len(relatorio['extracao']['paginas'])} pagina(s))")
        print(f"ORIGINAL INTOCADO sha256={relatorio['extracao']['sha256_original']}")
    print(relatorio["aviso"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
