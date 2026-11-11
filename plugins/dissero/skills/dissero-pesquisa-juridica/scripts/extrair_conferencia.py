#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'extrair_conferencia.py — o código de conferência costuma estar num arquivo que o escritório JÁ TEM.'
























import argparse
import io
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

CNJ = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")




COD_ESAJ = re.compile(r"informe\s+o\s+processo\s+([\d.\-]{20,25})\s+e\s+(?:o\s+)?"
                      r"c[óo]digo\s+([A-Za-z0-9]{6,12})", re.I)
COD_AUTDOC = re.compile(r"code_document=(\d{6,12})", re.I)
URL_ESAJ_DOC = re.compile(r"https?://[\w.\-]*esaj[\w.\-]*/cjsg/getArquivo\.do\?[^\s\"'<>]+", re.I)


URL_PJE_PROC = re.compile(r"https?://[\w.\-]*pje[\w.\-]*/[^\s\"'<>]*ConsultaPublica/[^\s\"'<>]*"
                          r"listView\.seam\?ca=[0-9a-f]{16,}", re.I)


PAGINAS = 8


def _texto(pdf, paginas=PAGINAS):
    try:
        from pypdf import PdfReader
    except ImportError:
        raise SystemExit("ERRO: pypdf ausente. Instale com: pip install pypdf")
    try:
        r = PdfReader(pdf)
        bruto = " ".join((p.extract_text() or "") for p in r.pages[:paginas])
        return re.sub(r"\s+", " ", bruto), len(r.pages)
    except Exception:
        return "", 0








_BANNER = "documentointernonaoprotocolar"


def _eh_artefato_do_plugin(texto):
    import unicodedata
    t = unicodedata.normalize("NFD", (texto or "")[:4000])
    t = "".join(c for c in t if unicodedata.category(c) != "Mn").lower()
    return _BANNER in re.sub(r"[^a-z]", "", t)


def varrer(pasta, paginas=PAGINAS):
    """Devolve lista de achados por arquivo: processos citados, códigos e URLs oficiais."""
    out = []
    for raiz, _dirs, arqs in os.walk(pasta):
        for nome in sorted(arqs):
            if not nome.lower().endswith(".pdf"):
                continue
            caminho = os.path.join(raiz, nome)
            texto, n_pag = _texto(caminho, paginas)
            if _eh_artefato_do_plugin(texto):
                out.append({"arquivo": os.path.relpath(caminho, pasta), "paginas": n_pag,
                            "artefato_do_plugin": True, "processos": [], "codigos_esaj": [],
                            "codigos_autdoc": [], "urls_oficiais": []})
                continue
            reg = {"arquivo": os.path.relpath(caminho, pasta), "paginas": n_pag,
                   "processos": sorted(set(CNJ.findall(texto))),
                   "codigos_esaj": [{"processo": p, "codigo": c} for p, c in
                                    dict.fromkeys(COD_ESAJ.findall(texto))],
                   "codigos_autdoc": sorted(set(COD_AUTDOC.findall(texto))),
                   "urls_oficiais": sorted(set(URL_ESAJ_DOC.findall(texto))
                                           | set(URL_PJE_PROC.findall(texto)))}
            if not texto.strip():
                reg["sem_texto"] = True
            out.append(reg)
    return out


def casar(varredura, dados):
    """Casa a varredura com os achados do dataset, por número de processo."""
    achados = dados.get("achados", []) if isinstance(dados, dict) else (dados or [])
    usados = [a for a in achados if isinstance(a, dict) and a.get("selected_for_use") is True
              and a.get("use_status") in ("allowed", "pending")]
    por_proc = {}
    for i, a in enumerate(usados, 1):
        m = CNJ.search(a.get("reference") or "")
        if m:
            por_proc.setdefault(m.group(0), []).append((i, a))
    casados = []
    for reg in varredura:
        for c in reg["codigos_esaj"]:
            for i, a in por_proc.get(c["processo"], []):
                casados.append({"i": i, "processo": c["processo"], "codigo": c["codigo"],
                                "tipo": "codigo_esaj", "arquivo": reg["arquivo"],
                                "paginas": reg["paginas"], "achado": a})
        for proc in reg["processos"]:
            for cod in reg["codigos_autdoc"]:
                for i, a in por_proc.get(proc, []):
                    casados.append({"i": i, "processo": proc, "codigo": cod,
                                    "tipo": "codigo_autdoc", "arquivo": reg["arquivo"],
                                    "paginas": reg["paginas"], "achado": a})
            if len(reg["processos"]) > 1:
                continue
            for url in reg["urls_oficiais"]:
                for i, a in por_proc.get(proc, []):
                    casados.append({"i": i, "processo": proc, "url": url,
                                    "tipo": "url_oficial", "arquivo": reg["arquivo"],
                                    "paginas": reg["paginas"], "achado": a})
    return usados, casados


def main():
    ap = argparse.ArgumentParser(description="Extrai código de conferência dos PDFs do caso.")
    ap.add_argument("pasta")
    ap.add_argument("--achados", default=None, help="dataset dsr.achados (v2 ou v3) para casar por processo")
    ap.add_argument("--gravar", action="store_true", help="grava `conferencia` nos achados casados")
    ap.add_argument("--paginas", type=int, default=PAGINAS, help=f"páginas por PDF (default {PAGINAS})")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if not os.path.isdir(a.pasta):
        print(f"ERRO: pasta inexistente: {a.pasta}")
        return 2
    varredura = varrer(a.pasta, a.paginas)
    com_codigo = [r for r in varredura if r["codigos_esaj"] or r["codigos_autdoc"]]
    sem_texto = [r for r in varredura if r.get("sem_texto")]

    casados = []
    if a.achados:
        dados = json.load(io.open(a.achados, encoding="utf-8"))
        _usados, casados = casar(varredura, dados)
        if a.gravar:
            n = 0
            for c in casados:
                if c["tipo"] != "codigo_esaj":
                    continue
                alvo = c["achado"]
                if alvo.get("conferencia", {}).get("codigo"):
                    continue
                alvo["conferencia"] = {
                    "processo": c["processo"], "codigo": c["codigo"],
                    "origem_do_codigo": (f"rodapé de autenticidade do arquivo "
                                         f"'{c['arquivo']}' ({c['paginas']} páginas), na pasta do caso"),
                    "extraido_por": "extrair_conferencia.py", "registrado_em": None,
                }
                n += 1
            json.dump(dados, io.open(a.achados, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            io.open(a.achados, "a", encoding="utf-8").write("\n")
            print(f"`conferencia` gravada em {n} achado(s).")

    if a.json:
        print(json.dumps({"pdfs": len(varredura), "com_codigo": len(com_codigo),
                          "sem_texto": len(sem_texto),
                          "casados": [{k: v for k, v in c.items() if k != "achado"}
                                      for c in casados]}, ensure_ascii=False))
        return 0

    artefatos = [r for r in varredura if r.get("artefato_do_plugin")]
    print(f"== VARREDURA == {len(varredura)} PDF(s) · {len(com_codigo)} com código · "
          f"{len(sem_texto)} sem texto extraível · {len(artefatos)} artefato(s) do plugin ignorado(s)")
    for r in com_codigo:
        print(f"\n  {r['arquivo'][:78]} ({r['paginas']} pág)")
        for c in r["codigos_esaj"]:
            print(f"      código e-SAJ  · processo {c['processo']} · {c['codigo']}")
        for c in r["codigos_autdoc"]:
            print(f"      código AutDoc · {c}")
        for u in r["urls_oficiais"][:2]:
            print(f"      URL oficial   · {u[:80]}")
    if casados:
        print(f"\n== CASADOS COM O DATASET == {len(casados)}")
        for c in casados:
            chave = c.get("codigo") or c.get("url", "")
            print(f"  #{c['i']:2} {c['tipo']:14} {str(chave)[:60]}  ←  {c['arquivo'][:46]}")
    elif a.achados:
        print("\nnenhum achado do dataset casou com código encontrado nos PDFs.")
    if sem_texto:
        print(f"\nSEM TEXTO EXTRAÍVEL (imagem pura — 'não achei' não é 'não tem'): {len(sem_texto)}")
        for r in sem_texto[:5]:
            print("   ·", r["arquivo"][:78])
    return 0


if __name__ == "__main__":
    sys.exit(main())
