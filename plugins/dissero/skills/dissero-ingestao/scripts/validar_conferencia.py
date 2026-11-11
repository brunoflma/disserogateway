#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'validar_conferencia.py — GATE do Passo 4: contrato + reconciliação nome a nome.'


















import sys, os, json, argparse, re

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import conferencia_contract as conf







_ESP = "[ \t]*"
BEGIN_RX = re.compile("^=====" + _ESP + "BEGIN FILE:" + _ESP + "(.+?)" + _ESP + "=====" + _ESP + "$",
                      re.MULTILINE)
END_RX = re.compile("^=====" + _ESP + "END FILE:" + _ESP + "(.+?)" + _ESP + "=====" + _ESP + "$",
                    re.MULTILINE)


def _saida(payload, code=0):
    print(json.dumps(payload, ensure_ascii=False))
    return code


def nomes_do_manifest(caminho):
    with open(caminho, encoding="utf-8", errors="replace") as fh:
        return [os.path.basename(l.strip()) for l in fh if l.strip()]


def nomes_da_pasta(pasta, exts):
    fora = []
    for nome in sorted(os.listdir(pasta)):
        if not os.path.isfile(os.path.join(pasta, nome)):
            continue
        if exts and os.path.splitext(nome)[1].lower() not in exts:
            continue
        fora.append(nome)
    return fora


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Valida CONFERENCIA.json e reconcilia o lote (§2.8)")
    ap.add_argument("dataset")
    ap.add_argument("--manifest", help="arquivo com a lista de arquivos recebidos (um por linha)")
    ap.add_argument("--pasta", help="pasta de entrada: a lista sai do conteúdo dela")
    ap.add_argument("--ext", default=".pdf,.docx,.docm,.doc,.jpg,.jpeg,.png,.tif,.tiff",
                    help="extensões consideradas em --pasta (vazio = todas)")
    ap.add_argument("--md", help="MD de conferência: confere se os blocos BEGIN/END casam com o dataset")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.dataset):
        return _saida({"ok": False, "erro": f"dataset não encontrado: {args.dataset}"}, 2)
    try:
        dados = json.loads(open(args.dataset, encoding="utf-8").read())
    except Exception as e:
        return _saida({"ok": False, "erro": f"dataset ilegível: {e}"}, 1)

    violacoes = conf.validar_documento(dados)
    avisos = []
    documentos = dados.get("documentos") or []
    presentes = {d.get("arquivo") for d in documentos}

    esperados = None
    if args.manifest:
        if not os.path.isfile(args.manifest):
            return _saida({"ok": False, "erro": f"manifest não encontrado: {args.manifest}"}, 2)
        esperados = nomes_do_manifest(args.manifest)
    elif args.pasta:
        if not os.path.isdir(args.pasta):
            return _saida({"ok": False, "erro": f"pasta não encontrada: {args.pasta}"}, 2)
        exts = {e.strip().lower() for e in args.ext.split(",") if e.strip()}
        esperados = nomes_da_pasta(args.pasta, exts)

    if esperados is None:
        avisos.append("reconciliação NÃO executada (sem --manifest/--pasta): o contrato está "
                      "conforme, mas nada garante que todo arquivo recebido tem bloco de leitura")
    else:
        faltando = [n for n in esperados if n not in presentes]
        for nome in faltando:
            violacoes.append(f"{nome}: arquivo recebido SEM bloco de leitura — proibido finalizar o "
                             f"lote assim (§2.8; documento sem bloco = documento NÃO LIDO)")
        sobrando = [n for n in sorted(presentes) if n not in esperados]
        if sobrando:
            avisos.append(f"documento(s) no dataset fora da lista recebida: {sobrando} "
                          "(confira se o lote é o que você pensa que é)")

    if args.md:
        if not os.path.isfile(args.md):
            return _saida({"ok": False, "erro": f"MD não encontrado: {args.md}"}, 2)
        texto_md = open(args.md, encoding="utf-8", errors="replace").read()
        abertos = BEGIN_RX.findall(texto_md)
        fechados = END_RX.findall(texto_md)
        if sorted(abertos) != sorted(fechados):
            violacoes.append(f"MD com bloco não fechado: BEGIN {sorted(abertos)} × END {sorted(fechados)}")
        for nome in presentes:
            if nome not in abertos:
                violacoes.append(f"{nome}: está no dataset e NÃO tem bloco no MD de conferência")
        for nome in abertos:
            if nome not in presentes:
                violacoes.append(f"{nome}: tem bloco no MD e NÃO está no dataset (registro perdido)")

    por_status = {}
    for d in documentos:
        por_status[d.get("leitura_status")] = por_status.get(d.get("leitura_status"), 0) + 1

    payload = {"ok": not violacoes, "dataset": os.path.abspath(args.dataset),
               "documentos": len(documentos), "por_leitura_status": por_status,
               "trechos": sum(len(d.get("trechos") or []) for d in documentos),
               "reconciliacao": ("manifest" if args.manifest else "pasta" if args.pasta else "nao_executada"),
               "violacoes": violacoes, "avisos": avisos}
    if violacoes:
        payload["nota"] = ("CONFERÊNCIA REPROVADA — corrija antes de numerar ou citar documento; "
                           "documento sem bloco volta à ingestão ou escala ao advogado")
        return _saida(payload, 1)
    payload["nota"] = "conferência conforme — documentos com leitura=lido podem ser curados na juntada"
    return _saida(payload, 0)


if __name__ == "__main__":
    sys.exit(main())
