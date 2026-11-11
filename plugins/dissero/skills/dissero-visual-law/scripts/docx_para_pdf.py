#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'docx_para_pdf.py — converte um .docx do padrão Dissero em PDF, preservando hiperlinks.'




















import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


PS_WORD = r"""
$ErrorActionPreference = 'Stop'
$src = $args[0]; $dst = $args[1]
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
  $doc = $word.Documents.Open($src, $false, $true)   # ReadOnly
  try { $doc.ExportAsFixedFormat($dst, 17, $false, 0, 0, 0, 0, 0, $true, $true, 0) }
  finally { $doc.Close($false) }
} finally {
  $word.Quit()
  [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($word)
}
"""


DIAGNOSTICO = []


def _powershell():
    return shutil.which("pwsh") or shutil.which("powershell")


def via_word(src, dst):
    ps = _powershell()
    if not ps or os.name != "nt":
        DIAGNOSTICO.append("Word: fora do Windows ou sem PowerShell no PATH")
        return None
    script = os.path.join(tempfile.gettempdir(), "dsr_docx_pdf.ps1")
    with open(script, "w", encoding="utf-8") as f:
        f.write(PS_WORD)
    proc = subprocess.run([ps, "-NoProfile", "-NonInteractive",
                           "-ExecutionPolicy", "Bypass", "-File", script, src, dst],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode == 0 and os.path.isfile(dst):
        return "Word (COM)"
    DIAGNOSTICO.append("Word: " + ((proc.stderr or proc.stdout or "").strip().splitlines() or
                                   ["exportação não produziu o PDF"])[0][:300])
    return None


def _chave_versao(caminho):
    'Ordena pelo NÚMERO da versão, não pelo texto: por texto, `libreoffice7.6` passaria à frente'

    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", caminho)]


def _soffice_fora_do_path(plataforma=None, achar=glob.glob):
    'Instalações típicas do LibreOffice fora do PATH.'










    plataforma = plataforma or sys.platform
    for var in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "LOCALAPPDATA"):
        base = os.environ.get(var)
        if base:
            yield os.path.join(base, "LibreOffice", "program", "soffice.exe")
    if plataforma == "darwin":
        for base in ("/Applications", os.path.join(os.path.expanduser("~"), "Applications")):
            yield os.path.join(base, "LibreOffice.app", "Contents", "MacOS", "soffice")
    elif plataforma != "win32":
        yield from sorted(achar("/opt/libreoffice*/program/soffice"), key=_chave_versao, reverse=True)
        yield "/snap/bin/libreoffice"


def via_soffice(src, dst):
    exe = (shutil.which("soffice") or shutil.which("soffice.exe")
           or shutil.which("libreoffice"))
    for cand in _soffice_fora_do_path():
        if not exe and os.path.isfile(cand):
            exe = cand
    if not exe:
        DIAGNOSTICO.append("LibreOffice: soffice não encontrado")
        return None
    saida = tempfile.mkdtemp(prefix="dsr_pdf_")
    proc = subprocess.run([exe, "--headless", "--norestore", "--convert-to", "pdf",
                           "--outdir", saida, src],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    gerado = os.path.join(saida, os.path.splitext(os.path.basename(src))[0] + ".pdf")
    if proc.returncode == 0 and os.path.isfile(gerado):
        shutil.copy2(gerado, dst)
        shutil.rmtree(saida, ignore_errors=True)
        return "LibreOffice"
    shutil.rmtree(saida, ignore_errors=True)
    DIAGNOSTICO.append("LibreOffice: " + ((proc.stderr or proc.stdout or "").strip()
                                          .splitlines() or ["conversão falhou"])[0][:300])
    return None


def converter(src_docx, out_pdf=None):
    """Devolve (caminho_pdf, rota) ou (None, None) se nenhuma rota estiver disponível."""
    src = os.path.abspath(src_docx)
    if not os.path.isfile(src):
        raise FileNotFoundError(src)
    dst = os.path.abspath(out_pdf or os.path.splitext(src)[0] + ".pdf")
    if os.path.exists(dst):
        os.remove(dst)
    for rota in (via_word, via_soffice):
        nome = rota(src, dst)
        if nome:
            return dst, nome
    return None, None


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Converte .docx do padrão Dissero em PDF.")
    ap.add_argument("docx")
    ap.add_argument("-o", "--out", default=None)
    a = ap.parse_args()
    pdf, rota = converter(a.docx, a.out)
    if not pdf:
        print("ERRO: nenhuma rota de conversão disponível (Word/COM ou LibreOffice). "
              "O .docx foi mantido; instale o LibreOffice ou converta pelo Word.")
        for d in DIAGNOSTICO:
            print("  ·", d)
        sys.exit(2)
    print(f"OK → {pdf} | rota: {rota}")
