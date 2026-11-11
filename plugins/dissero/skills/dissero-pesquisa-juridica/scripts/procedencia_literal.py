#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'procedencia_literal.py — o teor transcrito VEIO DE UMA EXTRAÇÃO, ou foi digitado?'



































from __future__ import annotations

import hashlib
import re
import unicodedata

NIVEIS = ("verbatim", "normalizado", "ausente")


_ELIPSES = ("[...]", "[…]", "(...)", "(…)", "...", "…")



MINIMO_LITERAL = 25


def sha256_texto(s):
    return hashlib.sha256(str(s or "").encode("utf-8")).hexdigest()


def _so_espacos(s):
    'Colapso de espaço em branco, e NADA MAIS.'





    s = str(s or "")
    s = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", s)
    return re.sub(r"\s+", " ", s).strip()


def _agressiva(s):
    'Apaga acento e pontuação. Só serve para DIAGNOSTICAR o que foi alterado.'






    s = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", str(s or ""))
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s.lower())).strip()


def _partes(literal):
    """Divide pela elipse: corte é prática legítima, inventar no meio não é."""
    partes = [str(literal or "")]
    for marca in _ELIPSES:
        novas = []
        for p in partes:
            novas += p.split(marca)
        partes = novas
    return [p for p in partes if len(_so_espacos(p)) >= 12]


def _contido_em_ordem(partes, alvo, transformar):
    pos = 0
    for parte in partes:
        p = transformar(parte)
        if not p:
            continue
        i = alvo.find(p, pos)
        if i < 0:
            return False
        pos = i + len(p)
    return True


def nivel(literal, extracao):
    """'verbatim' | 'normalizado' | 'ausente' do `literal` dentro da `extracao`."""
    if not str(extracao or "").strip():
        return "ausente"
    bruto = str(literal or "")
    if len(_so_espacos(bruto)) < MINIMO_LITERAL:
        return "verbatim"
    partes = _partes(bruto) or [bruto]
    if _contido_em_ordem(partes, _so_espacos(extracao), _so_espacos):
        return "verbatim"
    if _contido_em_ordem(partes, _agressiva(extracao), _agressiva):
        return "normalizado"
    return "ausente"


def diferenca(literal, extracao, maximo=4):
    'Descreve a divergência PALAVRA A PALAVRA, para a mensagem do gate.'





    import difflib
    lit = _so_espacos(literal).split()
    ext = _so_espacos(extracao).split()
    if not lit or not ext:
        return "não há texto a comparar"
    bloco = difflib.SequenceMatcher(None, ext, lit).find_longest_match(0, len(ext), 0, len(lit))
    if bloco.size < 3:
        return ("o trecho não foi localizado na extração — não é corte nem adaptação de "
                "detalhe: é outro texto")
    ini = max(0, bloco.a - bloco.b)
    janela = ext[ini:ini + len(lit) + 12]
    achados = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, janela, lit).get_opcodes():
        if op == "equal":
            continue
        fonte = " ".join(janela[i1:i2]) or "(nada)"
        peca = " ".join(lit[j1:j2]) or "(nada)"
        achados.append(f"o tribunal escreveu «{fonte[:60]}» e o texto diz «{peca[:60]}»")
        if len(achados) >= maximo:
            break
    return "; ".join(achados) if achados else "diverge da extração apenas em espaçamento"


def registrar(literal, extracao, origem, em=None, campo="syllabus_literal"):
    'O registro de procedência a gravar no achado. Não decide nada: descreve.'





    n = nivel(literal, extracao)
    reg = {
        "campo": campo,
        "nivel": n,
        "origem": str(origem or ""),
        "sha256_extracao": sha256_texto(_so_espacos(extracao)),
        "sha256_literal": sha256_texto(_so_espacos(literal)),
        "em": em,
    }
    if n != "verbatim":
        reg["divergencia"] = diferenca(literal, extracao)
    return reg


def conferir_achado(achado):
    '(nivel, motivo) da procedência declarada no achado.'






    if not isinstance(achado, dict):
        return "ausente", "achado ilegível"
    literal = str(achado.get("syllabus_literal") or "")
    if len(_so_espacos(literal)) < MINIMO_LITERAL:
        return "verbatim", "sem transcrição a conferir"
    regs = achado.get("procedencia_literal")
    if not isinstance(regs, list) or not regs:
        return "ausente", ("nenhuma procedência declarada — o teor não foi ligado a extração "
                           "alguma da fonte oficial")
    reg = next((r for r in regs if isinstance(r, dict)
                and r.get("campo", "syllabus_literal") == "syllabus_literal"), None)
    if reg is None:
        return "ausente", "procedência declarada não cobre o `syllabus_literal`"
    if reg.get("sha256_literal") != sha256_texto(_so_espacos(literal)):
        return "ausente", ("a ementa MUDOU depois de registrada a procedência (hash não "
                           "confere) — reextraia e registre de novo; texto alterado a "
                           "posteriori não herda a conferência anterior")
    n = reg.get("nivel")
    if n == "verbatim":
        return "verbatim", f"conferido contra {reg.get('origem') or 'extração registrada'}"
    if n == "normalizado":
        return "normalizado", (
            "o teor só confere com a fonte DEPOIS de apagar acento e pontuação — ou seja, "
            "acento ou pontuação foram ALTERADOS em relação ao original. "
            + str(reg.get("divergencia") or ""))
    return "ausente", str(reg.get("divergencia") or "procedência sem nível reconhecível")
