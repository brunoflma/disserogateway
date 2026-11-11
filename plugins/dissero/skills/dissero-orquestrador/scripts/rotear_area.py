#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'rotear_area.py — sugere o MÓDULO DE ÁREA (e os cenários) para um pedido, respeitando o perfil.'


















from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass



MODO_CONFERENCIA = "conferencia_na_fonte"


def situacao_revisao(er):
    "'revisado' (advogado da área nomeado), 'conferido' (modo conferencia_na_fonte) ou 'pendente'."

    if er.get("revisado_por"):
        return "revisado"
    if er.get("modo") == MODO_CONFERENCIA:
        return "conferido"
    return "pendente"

PREFERENCIAS = ("auto", "ligada", "desligada")
SCHEMA = "dsr.roteamento_area.v1"


def _norm(t):
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", t.casefold()).strip()





_SUFIXOS = ("acoes", "acao", "coes", "cao", "mente", "ados", "adas", "ado", "ada", "idos", "idas", "ido", "ida",
            "ando", "endo", "indo", "aram", "eram", "iram", "ar", "er", "ir", "ou", "eu", "iu", "es", "os", "as", "s")


def _raiz(p):
    if len(p) <= 3 or not p.isalpha():
        return p
    for s in _SUFIXOS:
        if p.endswith(s) and len(p) - len(s) >= 4:
            return p[:-len(s)]
    return p


def _raizes(texto):
    return [_raiz(w) for w in re.findall(r"[a-z0-9]+", _norm(texto))]


_ALNUM = frozenset("abcdefghijklmnopqrstuvwxyz0123456789")


def _frase_em(gn, tn):
    '`gn` aparece em `tn` sem letra ou dígito ASCII colado dos dois lados: o mesmo que a regex'


    i = tn.find(gn)
    while i != -1:
        j = i + len(gn)
        if (i == 0 or tn[i - 1] not in _ALNUM) and (j >= len(tn) or tn[j] not in _ALNUM):
            return True
        i = tn.find(gn, i + 1)
    return False


def _casa(gatilho, tn, raizes_texto):
    """Frase exata (sem acento/caixa) OU sequência de raízes das palavras do gatilho no texto."""
    gn = _norm(gatilho)
    if _frase_em(gn, tn):
        return True
    rg = _raizes(gn)
    if not rg:
        return False
    n = len(rg)
    return any(raizes_texto[i:i + n] == rg for i in range(len(raizes_texto) - n + 1))






INDICE = os.path.join(AQUI, "roteamento_areas.json")
INDICE_SCHEMA = "dsr.roteamento_areas.v1"
MOTIVO_SEM_INDICE = "roteamento_areas.json ausente ou ilegível: nenhuma área pode ser sugerida (reinstale o plugin)"


def _modulo_do_indice_ok(m):
    """Conferência ESTRUTURAL de uma entrada do índice (a de conteúdo foi feita no build)."""
    return (isinstance(m, dict) and isinstance(m.get("id"), str) and m["id"]
            and isinstance(m.get("nome"), str) and isinstance(m.get("gatilhos"), list)
            and all(isinstance(g, str) for g in m["gatilhos"])
            and isinstance(m.get("cenarios"), list)
            and all(isinstance(c, dict) and isinstance(c.get("instituto"), str) and "cenario" in c for c in m["cenarios"])
            and isinstance(m.get("estado_revisao"), dict))


def ler_indice(caminho=None):
    """O índice de roteamento como dict, ou None se ausente/ilegível/de outro formato."""
    try:
        with open(caminho or INDICE, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict) or (d.get("cabecalho") or {}).get("schema_version") != INDICE_SCHEMA:
        return None
    if not isinstance(d.get("modulos"), list) or not isinstance(d.get("roteiros"), list):
        return None
    return d


def carregar_modulos(pasta=None):
    '({id: modulo} só dos módulos VÁLIDOS, [inválidos com o motivo]).'



    if pasta is None:
        d = ler_indice()
        if d is None:
            print(MOTIVO_SEM_INDICE, file=sys.stderr)
            return {}, [{"modulo": "*", "motivo": MOTIVO_SEM_INDICE}]
        mods, invalidos = {}, []
        for m in d["modulos"]:
            if _modulo_do_indice_ok(m):
                mods[m["id"]] = m
            else:
                invalidos.append({"modulo": str((m or {}).get("id") if isinstance(m, dict) else m),
                                  "motivo": "entrada do índice de roteamento fora do formato"})
        return mods, invalidos
    import validar_modulo_area as vma
    mods, invalidos = {}, []
    if not os.path.isdir(pasta):
        return mods, invalidos
    for d in sorted(os.listdir(pasta)):
        cam = os.path.join(pasta, d)
        if not os.path.isdir(cam):
            continue
        erros, _avisos, m = vma.validar(cam)
        if erros or not m:
            invalidos.append({"modulo": d, "motivo": (erros or ["ilegível"])[0]})
            continue
        mods[m["id"]] = m
    return mods, invalidos


def preferencias(perfil):
    prefs, avisos = {}, []
    bloco = (perfil or {}).get("modulos_area") if isinstance(perfil, dict) else None
    if not isinstance(bloco, dict):
        return prefs, avisos
    for k, v in bloco.items():
        if k.startswith("_"):
            continue
        v = str(v or "").strip().lower()
        if v not in PREFERENCIAS:
            avisos.append(f"perfil: preferência inválida '{v}' para {k}; tratada como auto")
            v = "auto"
        prefs[k] = v
    return prefs, avisos


def carregar_perfil(caminho=None):
    'Perfil para as preferências de área: o `caminho` dado ou, sem ele, $DSR_PERFIL → ~/.config/dissero/perfil.json.'




    cands = [caminho] if caminho else [os.environ.get("DSR_PERFIL"), os.path.join(os.path.expanduser("~"), ".config", "dissero", "perfil.json")]
    for c in cands:
        if c and os.path.isfile(c):
            try:
                with open(c, encoding="utf-8") as f:
                    return json.load(f), c
            except (OSError, json.JSONDecodeError):
                return None, c
    return None, None


def _squad_da_area(area):
    'O squad da área, pela MESMA ponte do `squad.py init --area`. Falha de leitura não derruba'

    try:
        import squad
        return squad.squad_da_area(area)[0]
    except Exception:
        return None


def rotear(texto, modulos, prefs):
    tn = " " + _norm(texto) + " "
    rt = _raizes(texto)
    cands, descartadas = [], []
    for mid, m in modulos.items():
        pref = prefs.get(mid, "auto")
        acertos = [g for g in m["gatilhos"] if _casa(g, tn, rt)]
        if pref == "desligada":
            if acertos:
                descartadas.append({"area": mid, "motivo": "desligada no perfil", "gatilhos": acertos})
            continue
        if not acertos and pref != "ligada":
            continue
        cen = []
        for c in m["cenarios"]:
            palavras = list(c.get("palavras") or []) + [c["instituto"]]
            bate = any(_casa(p, tn, rt) for p in palavras if p)
            cen.append({"instituto": c["instituto"], "cenario": c["cenario"], "casou": bate})
        cen.sort(key=lambda x: (not x["casou"], x["cenario"]))


        pontos = sum(max(1, len(_norm(g).split())) for g in acertos) + (2 if pref == "ligada" else 0)
        situacao = situacao_revisao(m["estado_revisao"])
        cands.append({"area": mid, "nome": m["nome"], "squad": _squad_da_area(mid),
                      "preferencia": pref, "pontos": pontos,
                      "gatilhos": acertos, "cenarios_sugeridos": [c for c in cen if c["casou"]][:5] or cen[:3],
                      "revisado_por_advogado": situacao == "revisado",
                      "situacao_revisao": situacao,
                      "modo_revisao": m["estado_revisao"].get("modo"),
                      "aviso_revisao": None if situacao != "pendente" else
                      "módulo não revisado por advogado da área: base legal com fonte, jurisprudência [A CONFIRMAR]"})
    cands.sort(key=lambda x: (-x["pontos"], x["area"]))
    return cands, descartadas


def main(argv=None):
    ap = argparse.ArgumentParser(description="Sugere módulo de área e cenários para um pedido, respeitando o perfil")
    ap.add_argument("--texto", help="texto do pedido do advogado")
    ap.add_argument("--listar", action="store_true", help="lista módulos válidos e preferências")
    ap.add_argument("--perfil"); ap.add_argument("--sem-perfil", dest="sem_perfil", action="store_true")
    ap.add_argument("--areas", help="pasta de módulos (padrão: o índice roteamento_areas.json, gerado do acervo)")
    ap.add_argument("--resumo", action="store_true")
    a = ap.parse_args(argv)
    modulos, invalidos = carregar_modulos(a.areas)


    sem_indice = any(i.get("modulo") == "*" for i in invalidos)
    perfil, origem = (None, None) if a.sem_perfil else carregar_perfil(a.perfil)
    prefs, avisos = preferencias(perfil)
    if a.listar or not a.texto:
        out = {"schema_version": SCHEMA, "modulos": [{"id": k, "nome": m["nome"], "preferencia": prefs.get(k, "auto"),
                                                       "gatilhos": len(m["gatilhos"]), "cenarios": len(m["cenarios"]),
                                                       "situacao_revisao": situacao_revisao(m["estado_revisao"])} for k, m in modulos.items()],
               "invalidos": invalidos, "perfil": origem, "avisos": avisos}
        if not a.texto and not a.listar:
            out["erro"] = "informe --texto ou --listar"
        elif sem_indice:
            out.update({"codigo": "indice_ausente", "erro": MOTIVO_SEM_INDICE})
        print(json.dumps(out, ensure_ascii=False))
        return (1 if sem_indice else 0) if (a.listar or a.texto) else 2
    cands, descartadas = rotear(a.texto, modulos, prefs)
    out = {"schema_version": SCHEMA, "sugestao": True, "areas": cands, "descartadas_pelo_perfil": descartadas,
           "sem_area": (not cands) and not sem_indice, "invalidos": invalidos, "perfil": origem, "avisos": avisos,
           "regra": "sugestão: o advogado confirma a área; módulo desligado no perfil nunca é sugerido; jurisprudência do módulo vai como [A CONFIRMAR] até a verificação"}
    if sem_indice:
        out.update({"codigo": "indice_ausente", "erro": MOTIVO_SEM_INDICE})
    if a.resumo:
        if sem_indice:
            print(f"Roteamento por área indisponível: {MOTIVO_SEM_INDICE}.")
        elif not cands:
            print("Nenhum módulo de área casou com o pedido (o rito segue pelo catálogo geral).")
        for c in cands:
            print(f"- {c['nome']} ({c['area']}, {c['preferencia']}): gatilhos {', '.join(c['gatilhos']) or '—'} → cenários "
                  + ", ".join(f"{x['cenario']} ({x['instituto']})" for x in c["cenarios_sugeridos"])
                  + (f" · squad: squad.py init --area {c['area']}" if c.get("squad") else "")
                  + (" · NÃO REVISADO" if c["situacao_revisao"] == "pendente" else ""))
    print(json.dumps(out, ensure_ascii=False))
    return 1 if sem_indice else 0


if __name__ == "__main__":
    sys.exit(main())
