#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'etapa_tentada.py — o registro de que uma etapa do método, DEPOIS da redação, foi tentada e não'





































import argparse
import datetime
import hashlib
import json
import os
import sys

try:
    import pesquisa_tentada
except Exception:
    pesquisa_tentada = None

NOME = "ETAPAS_TENTADAS.json"
SCHEMA = "dsr.etapas_tentadas.v1"
ETAPAS = (("verificacao", "verificação das citações"), ("visual_law", "formatação"),
          ("lint", "conferência final"), ("conselho", "revisão do Conselho"))
NOMES = dict(ETAPAS)
MOTIVOS = ("script_falhou", "sem_subagente", "tempo_esgotado")
_FRASE = {"script_falhou": "a etapa foi tentada e o programa dela falhou",
          "sem_subagente": "esta sessão não tem como abrir os revisores do Conselho",
          "tempo_esgotado": "a etapa foi tentada e não terminou no tempo da sessão"}


class Recusa(Exception):
    pass


def _selo(reg):
    base = {k: v for k, v in reg.items() if k != "selo"}
    return hashlib.sha256(json.dumps(base, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _agora(agora=None):
    return (agora or datetime.datetime.now(datetime.timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _detalhe(detalhe):
    if pesquisa_tentada is not None:
        g = pesquisa_tentada._detalhe_generico(detalhe)
        if g:
            raise Recusa(g.replace("o que foi procurado ou chamado", "o que rodou"))
    elif len((detalhe or "").strip()) < 40:
        raise Recusa("o detalhe tem menos de 40 caracteres: diga o que aconteceu")
    return detalhe.strip()[:600]


PECA_STATE = "PECA_STATE.json"


def pasta_do_estado(pasta):
    """A pasta do registro de andamento da peça (PECA_STATE.json): a da peça ou até duas acima."""
    d = os.path.abspath(pasta or ".")
    for _ in range(3):
        if os.path.isfile(os.path.join(d, PECA_STATE)):
            return d
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    return None


def _estado(pasta):
    d = pasta_do_estado(pasta)
    if not d:
        return None
    try:
        with open(os.path.join(d, PECA_STATE), encoding="utf-8") as fh:
            st = json.load(fh)
        return st if isinstance(st, dict) else None
    except Exception:
        return None


def sha_da_redacao(st):
    'A impressão da redação registrada (sha do artefato, ou o próprio artefato), ou None. A'

    f = ((st or {}).get("fases") or {}).get("redacao") if isinstance((st or {}).get("fases"), dict) else None
    if not isinstance(f, dict):
        return None
    v = f.get("artefato_sha256") or f.get("artefato")
    return str(v) if v else None


def montar_tentativa(etapa, motivo, detalhe=None, codigo_saida=None, agora=None, redacao_sha=None):
    """A tentativa de UMA etapa; levanta Recusa com a frase do que falta."""
    if etapa not in NOMES:
        raise Recusa("--etapa é uma de: " + ", ".join(NOMES))
    if motivo not in MOTIVOS:
        raise Recusa("--motivo é um de: " + ", ".join(MOTIVOS))
    t = {"motivo": motivo, "em": _agora(agora), "redacao_sha": redacao_sha}
    if motivo == "sem_subagente" and etapa != "conselho":
        raise Recusa("sem_subagente só vale para o Conselho: as outras etapas rodam sem revisores")
    t["detalhe"] = _detalhe(detalhe)
    if motivo == "script_falhou":
        try:
            c = int(codigo_saida)
        except (TypeError, ValueError):
            raise Recusa("--codigo-saida é obrigatório quando o script falhou: o número com que ele saiu")
        if c == 0:
            raise Recusa("código de saída 0 não é falha: com o script terminado, registre a etapa no "
                         "registro da peça em vez de declarar a tentativa")
        t["codigo_saida"] = c
    return t


def ler(pasta):
    """(registro, None) ou (None, motivo). Registro editado à mão não vale."""
    caminho = os.path.join(pasta or ".", NOME)
    if not os.path.isfile(caminho):
        return None, "não há etapa tentada registrada na pasta da peça"
    try:
        with open(caminho, encoding="utf-8") as fh:
            reg = json.load(fh)
    except Exception:
        return None, "o registro das etapas tentadas está ilegível"
    if (not isinstance(reg, dict) or reg.get("schema_version") != SCHEMA or reg.get("gerado_por") != "etapa_tentada.py"
            or not isinstance(reg.get("etapas"), dict) or reg.get("selo") != _selo(reg)):
        return None, "o registro das etapas tentadas não foi gravado pelo script (ou foi alterado depois)"
    return reg, None


def gravar_tentativa(pasta, etapa, tentativa):
    anterior, _ = ler(pasta)
    etapas = dict((anterior or {}).get("etapas") or {})
    etapas[etapa] = tentativa
    reg = {"schema_version": SCHEMA, "gerado_por": "etapa_tentada.py", "etapas": etapas}
    reg["selo"] = _selo(reg)
    caminho = os.path.join(pasta, NOME)
    tmp = caminho + ".parcial"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(reg, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, caminho)
    return reg


def tentativa(pasta, etapa):
    """A tentativa registrada da etapa, ou None (registro ausente ou inválido)."""
    reg, _ = ler(pasta)
    t = ((reg or {}).get("etapas") or {}).get(etapa)
    return t if isinstance(t, dict) and t.get("motivo") in MOTIVOS else None


def frase(etapa, t):
    'A pendência em português de advogado. O detalhe fica no arquivo do caso e não vai à minuta:'

    nome = NOMES.get(etapa, etapa)
    return f"{nome} não feita: {_FRASE.get(t.get('motivo'), 'motivo não informado')}"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="etapa_tentada.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("registrar")
    r.add_argument("--pasta", required=True)
    r.add_argument("--etapa", required=True)
    r.add_argument("--motivo", required=True)
    r.add_argument("--detalhe")
    r.add_argument("--codigo-saida")
    c = sub.add_parser("conferir")
    c.add_argument("--pasta", required=True)
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    if not os.path.isdir(a.pasta):
        print(json.dumps({"ok": False, "codigo": "contrato_invalido", "mensagem": "a pasta não existe"},
                         ensure_ascii=False))
        return 2
    if a.cmd == "conferir":
        reg, problema = ler(a.pasta)
        print(json.dumps({"ok": reg is not None, "etapas": sorted((reg or {}).get("etapas") or {}),
                          "mensagem": problema}, ensure_ascii=False))
        return 0 if reg else 1
    try:
        st = _estado(a.pasta)
        if st is None:
            raise Recusa("não há registro de andamento da peça (PECA_STATE.json) na pasta nem acima: a tentativa "
                         "se registra ao lado dele, sobre a redação registrada")
        t = montar_tentativa(a.etapa, a.motivo, a.detalhe, a.codigo_saida, redacao_sha=sha_da_redacao(st))
    except Recusa as e:
        print(json.dumps({"ok": False, "codigo": "tentativa_recusada", "mensagem": str(e)}, ensure_ascii=False))
        return 1
    gravar_tentativa(pasta_do_estado(a.pasta), a.etapa, t)
    print(json.dumps({"ok": True, "etapa": a.etapa, "motivo": a.motivo}, ensure_ascii=False))
    return 0



if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
