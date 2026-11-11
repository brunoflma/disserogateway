#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'medir_completude.py — medidor determinístico da completude do briefing (Dissero).'






























import sys, os, json, argparse

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))
CENARIOS_PADRAO = os.path.join(AQUI, "cenarios_risco.json")


def carregar_cenarios(caminho):
    with open(caminho, encoding="utf-8") as fh:
        d = json.load(fh)
    if not isinstance(d, dict) or not isinstance(d.get("cenarios"), dict):
        raise ValueError("estrutura inválida (esperado objeto com 'cenarios': {}).")
    cen = d["cenarios"]
    for k, cfg in cen.items():
        if not isinstance(cfg, dict):
            raise ValueError(f"cenário {k}: deve ser objeto.")
        if not isinstance(cfg.get("estrela"), list) or not all(isinstance(x, str) for x in cfg["estrela"]):
            raise ValueError(f"cenário {k}: 'estrela' deve ser lista de strings.")
        if "complementares" in cfg and (not isinstance(cfg["complementares"], list)
                                        or not all(isinstance(x, str) for x in cfg["complementares"])):
            raise ValueError(f"cenário {k}: 'complementares' deve ser lista de strings.")
        calc = cfg.get("calculaveis", [])
        if not isinstance(calc, list) or not all(isinstance(x, str) for x in calc):
            raise ValueError(f"cenário {k}: 'calculaveis' deve ser lista de strings.")
        fora = sorted(set(calc) - set(cfg["estrela"]) - set(cfg.get("complementares", [])))
        if fora:
            raise ValueError(f"cenário {k}: 'calculaveis' com campo que não é do cenário: {fora}")
        if str(cfg.get("risco", "")).strip().lower() not in ("alto", "baixo", ""):
            raise ValueError(f"cenário {k}: 'risco' inválido (use alto|baixo).")
    return cen


def carregar_prosseguimento(caminho, cenarios):
    "Lê e VALIDA o bloco 'prosseguimento_parcial'; devolve (subtarefas, por_cenario)."






    with open(caminho, encoding="utf-8") as fh:
        d = json.load(fh)
    bloco = d.get("prosseguimento_parcial")
    if bloco is None:
        return [], {}
    if not isinstance(bloco, dict):
        raise ValueError("'prosseguimento_parcial' deve ser objeto.")
    subs = bloco.get("subtarefas", [])
    if not isinstance(subs, list) or not all(isinstance(x, str) and x.strip() for x in subs):
        raise ValueError("subtarefas: deve ser lista de strings nao vazias.")
    if len(set(subs)) != len(subs):
        raise ValueError("subtarefas: nome repetido.")
    por_cen = bloco.get("por_cenario", {})
    if not isinstance(por_cen, dict):
        raise ValueError("por_cenario: deve ser objeto.")
    universo = set(subs)
    for ck, mapa in por_cen.items():
        cfg = cenarios.get(str(ck))
        if cfg is None:
            raise ValueError(f"por_cenario[{ck}]: cenario inexistente em 'cenarios'.")
        if not isinstance(mapa, dict):
            raise ValueError(f"por_cenario[{ck}]: deve ser objeto campo -> [subtarefas].")
        campos = set(cfg.get("estrela", [])) | set(cfg.get("complementares", []))
        for campo, lst in mapa.items():
            if campo not in campos:
                raise ValueError(f"por_cenario[{ck}]: campo '{campo}' nao existe nesse cenario.")
            if not isinstance(lst, list) or not all(isinstance(x, str) for x in lst):
                raise ValueError(f"por_cenario[{ck}][{campo}]: deve ser lista de strings.")
            fora = sorted({x for x in lst if x not in universo})
            if fora:
                raise ValueError(f"por_cenario[{ck}][{campo}]: subtarefa fora de 'subtarefas': {fora}")
        sem_pronuncia = sorted(campos - set(mapa.keys()))
        if sem_pronuncia:
            raise ValueError(f"por_cenario[{ck}]: cobertura incompleta, campo sem pronuncia: {sem_pronuncia}")
    return subs, por_cen


def derivar_partes(cfg, respondidos, subtarefas, mapa_cenario):
    '(partes_liberadas, partes_bloqueadas) por aritmética de conjuntos sobre o mapa.'





    if not mapa_cenario:
        return [], []
    resp = {c for c in respondidos if c}
    relevantes = list(cfg.get("estrela", [])) + list(cfg.get("complementares", []))
    bloq = set()
    for campo in relevantes:
        if campo not in resp:
            bloq |= set(mapa_cenario.get(campo, []))
    return sorted(set(subtarefas) - bloq), sorted(bloq)


def bloqueios_por_parte(cfg, respondidos, mapa_cenario):
    '{subtarefa bloqueada: [campos ausentes que o mapa liga a ela]}. M2 do teste do titular'


    if not mapa_cenario:
        return {}
    resp = {c for c in respondidos if c}
    por = {}
    for campo in list(cfg.get("estrela", [])) + list(cfg.get("complementares", [])):
        if campo not in resp:
            for sub in mapa_cenario.get(campo, []):
                por.setdefault(sub, []).append(campo)
    return {s: sorted(set(c)) for s, c in sorted(por.items())}


def explicar_bloqueios(por):
    """Uma linha para o motivo: 'calculo_de_prazo espera juizo_tribunal; ...'."""
    return "; ".join(f"{s} espera {', '.join(c)}" for s, c in por.items())


def medir(cfg, respondidos):
    """cfg = {estrela:[], complementares:[], risco}; respondidos = set de campos respondidos."""
    estrela = list(cfg.get("estrela", []))
    compl = list(cfg.get("complementares", []))
    relevantes = estrela + compl
    resp = {c for c in respondidos if c}
    n_resp = sum(1 for k in relevantes if k in resp)
    pct = (n_resp / len(relevantes)) if relevantes else 0.0
    estrela_ausentes = [k for k in estrela if k not in resp]
    complementares_ausentes = [k for k in compl if k not in resp]
    if estrela_ausentes:
        nivel = "FRACO"
    elif pct >= 0.75:
        nivel = "FORTE"
    elif pct >= 0.40:
        nivel = "MEDIO"
    else:
        nivel = "FRACO"
    return {"nivel": nivel, "percentual": round(pct, 3), "total_relevantes": len(relevantes),
            "respondidos_relevantes": n_resp, "estrela_total": len(estrela),
            "estrela_ausentes": estrela_ausentes, "complementares_ausentes": complementares_ausentes}


def pode_executar(nivel, risco_alto, ressalva, m=None):
    'O motivo nomeia o que falta (M2 do teste do titular): "MÉDIO" sozinho manda o modelo'

    m = m or {}
    faltam_est = ", ".join(m.get("estrela_ausentes") or [])
    faltam_cpl = ", ".join(m.get("complementares_ausentes") or [])
    if not risco_alto:
        return True, "cenário sem risco — não gated"
    if nivel == "FORTE":
        return True, "FORTE — executa tarefa de risco"
    if nivel == "MEDIO":

        return True, ("MÉDIO — executa: todos os ⭐ respondidos"
                      + (f". Faltam para FORTE: {faltam_cpl} (diga ao advogado o que ficou de fora)"
                         if faltam_cpl else ""))
    return False, ("FRACO — NÃO executa tarefa de risco (peça/prazo/precedente/notificação). Continue o intake ou escale"
                   + (f". ⭐ ausentes: {faltam_est}" if faltam_est else "")
                   + (f". Complementares ausentes: {faltam_cpl}" if faltam_cpl else ""))


A_CALCULAR = "[A CALCULAR]"


def respondidos_de(obj, calculaveis):
    '(respondidos, a_calcular) a partir de {campo: valor}.'





    resp, calc = set(), []
    for k, v in obj.items():
        if not (isinstance(v, str) and v.strip()):
            continue
        t = v.strip()
        if t.startswith("[") and t.endswith("]"):
            if t.upper() == A_CALCULAR and k in calculaveis:
                resp.add(k); calc.append(k)
            continue
        resp.add(k)
    return resp, sorted(calc)


def main():
    ap = argparse.ArgumentParser(description="Medidor de completude do briefing (Dissero)")
    ap.add_argument("--cenario", required=True)
    ap.add_argument("--respondidos", help="lista de campos respondidos, separados por vírgula")
    ap.add_argument("--respostas", help="JSON {campo: valor} (valor não-vazio = respondido); '-' = stdin")
    ap.add_argument("--ressalva", action="store_true",
                    help="aceita por compatibilidade; desde 23/10/2026 o MÉDIO não exige ressalva")
    ap.add_argument("--gate", action="store_true", help="exit 1 se NÃO pode executar tarefa de risco")
    ap.add_argument("--strict", action="store_true",
                    help="com --gate: cenário desconhecido (fora de cenarios_risco.json) é BLOQUEADO (exit 1)")
    ap.add_argument("--cenarios", default=CENARIOS_PADRAO)
    args = ap.parse_args()

    try:
        cenarios = carregar_cenarios(args.cenarios)
    except Exception as e:
        print(json.dumps({"ok": False, "erro": f"cenarios_risco.json: {e}"}, ensure_ascii=False)); return 2
    try:
        subtarefas, por_cenario = carregar_prosseguimento(args.cenarios, cenarios)
    except Exception as e:
        print(json.dumps({"ok": False, "erro": f"prosseguimento_parcial: {e}"}, ensure_ascii=False)); return 2

    cfg = cenarios.get(str(args.cenario))
    respondidos, a_calcular = set(), []
    if args.respondidos:
        respondidos |= {c.strip() for c in args.respondidos.split(",") if c.strip()}
    if args.respostas:
        try:
            raw = sys.stdin.read() if args.respostas == "-" else open(args.respostas, encoding="utf-8").read()
            obj = json.loads(raw)
            if not isinstance(obj, dict):
                raise ValueError("esperado objeto {campo: valor}")
            r, a_calcular = respondidos_de(obj, set((cfg or {}).get("calculaveis", [])))
            respondidos |= r
        except Exception as e:
            print(json.dumps({"ok": False, "erro": f"--respostas inválido: {e}"}, ensure_ascii=False)); return 2

    if cfg is None:

        bloq = bool(args.strict)
        out = {"ok": True, "cenario": args.cenario, "risco": False, "nivel": "N/A",
               "partes_liberadas": [], "partes_bloqueadas": [],
               "pode_executar": not bloq,
               "motivo": ("--strict: cenário desconhecido tratado como risco — classifique antes" if bloq
                          else "cenário não está em cenarios_risco.json — sem gate de risco")}
        print(json.dumps(out, ensure_ascii=False))
        return 1 if (args.gate and bloq) else 0

    risco_alto = str(cfg.get("risco", "")).strip().lower() == "alto"
    m = medir(cfg, respondidos)
    pode, motivo = pode_executar(m["nivel"], risco_alto, args.ressalva, m)
    mapa = por_cenario.get(str(args.cenario)) or {}
    liberadas, bloqueadas = derivar_partes(cfg, respondidos, subtarefas, mapa)
    por = bloqueios_por_parte(cfg, respondidos, mapa)
    if pode and por:
        motivo += (". Pode começar; estas partes esperam o campo: " + explicar_bloqueios(por))

    calc_ausentes = [c for c in m.get("estrela_ausentes") or []
                     if c in set(cfg.get("calculaveis", []))]
    if not pode and calc_ausentes:
        motivo += (". Se " + ", ".join(calc_ausentes) + " ainda vai ser calculado pelo rito "
                   "(fase prazo), responda \"" + A_CALCULAR + "\" nesse campo, pelo --respostas")
    out = {"ok": True, "cenario": args.cenario, "nome": cfg.get("nome"), "risco": risco_alto,
           "ressalva": bool(args.ressalva), **m, "a_calcular": a_calcular,
           "partes_liberadas": liberadas, "partes_bloqueadas": bloqueadas,
           "bloqueios_por_parte": por,
           "pode_executar": pode, "motivo": motivo}
    print(json.dumps(out, ensure_ascii=False))
    if args.gate and not pode:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
