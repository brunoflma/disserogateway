#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'verificar_modelo.py — confere o modelo EXECUTADO de cada assento contra o PEDIDO.'



















































import sys, os, json, glob, argparse

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass






FAMILIAS = ("fable", "opus", "sonnet", "haiku")
OK = ("CONFERIDO", "HERDADO", "SEM_PEDIDO", "SEM_AGENTE")




try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import caso_raiz as _caso_raiz
except Exception:
    _caso_raiz = None


class Contrato(Exception):
    """Violação de contrato/uso → exit 2."""


def _full_str(x):
    return isinstance(x, str) and bool(x.strip())


class CaminhoRecusado(Exception):
    '`--state` de nome nu que não se atribui à pasta do caso desta sessão; `resultado` nomeia'


    def __init__(self, resultado, motivo):
        super().__init__(motivo)
        self.resultado = resultado


def pasta_do_caso(session_id=None):
    '(pasta, origem) do caso DESTA sessão, ou (None, origem). Só valem `DSR_CASO_RAIZ` e o'


    if _caso_raiz is None:
        return None, "sem_caso_raiz"
    try:
        raiz, origem = _caso_raiz.resolver(session_id=session_id)
    except Exception:
        return None, "falha"
    return (raiz, origem) if origem in ("env", "sessao") else (None, origem)


def no_caso(caminho, session_id=None):
    '`--state` de nome NU → o da pasta do caso desta sessão. Caminho com diretório fica como'


    if not _full_str(caminho) or os.path.dirname(caminho):
        return caminho
    raiz, origem = pasta_do_caso(session_id)
    if raiz is None:
        motivo = (f"«{caminho}» veio sem pasta, e a pasta do caso desta sessão não foi "
                  f"identificada. ")
        if origem == "sem_caso_raiz":
            motivo += "O caso_raiz.py não está ao lado deste script. "
        elif origem == "atual":
            motivo += ("A última pasta registrada pode ser de outra sessão ou de outro caso, e "
                       "não é usada. ")
        motivo += (f"Passe o caminho completo em --state (\"<pasta do caso>/{caminho}\"). Ou "
                   f"repita o comando com --session-id <id da sessão>, depois de registrar a "
                   f"pasta com `caso_raiz.py registrar --raiz \"<pasta do caso>\" --session-id "
                   f"<id da sessão>`.")
        raise CaminhoRecusado("caso_nao_resolvido", motivo)
    no_raiz = os.path.join(raiz, caminho)
    try:
        dois = (os.path.isfile(no_raiz) and os.path.isfile(caminho)
                and not os.path.samefile(no_raiz, caminho))
    except OSError:
        dois = True
    if dois:
        raise CaminhoRecusado("caminho_ambiguo", (
            f"«{caminho}» existe na pasta corrente ({os.path.abspath(caminho)}) e na pasta "
            f"do caso ({no_raiz}), como arquivos diferentes. Passe o caminho completo do estado "
            f"desta sessão em --state."))
    return no_raiz


def _saida(resultado, motivos, exit_code, extra=None):
    payload = {"ok": exit_code == 0, "resultado": resultado, "motivos": list(motivos)}
    if extra:
        payload.update(extra)
    print(json.dumps(payload, ensure_ascii=False))
    return exit_code


def tier_do_id(model_id):
    'ID do modelo → tier do perfil Dissero. Cobre o formato sem data da geração 4.6+'



    if not _full_str(model_id):
        return None
    partes = model_id.strip().lower().split("-")
    for f in FAMILIAS:
        if f in partes:
            return f
    return None


def _raiz_transcripts(session_id, override):
    'Diretório de transcripts de subagente da sessão. O override (flag ou env'

    if _full_str(override):
        return override.strip()
    padrao = os.path.join(os.path.expanduser("~"), ".claude", "projects", "*",
                          session_id, "subagents")
    achados = sorted(glob.glob(padrao))
    return achados[0] if achados else ""


def raiz_por_ids(ids, session_id=None, override=None):
    'Raiz de transcripts que contém `agent-<id>.jsonl` para TODOS os `ids` — ou "".'















    alvos = [str(x).strip() for x in (ids or []) if _full_str(x)]
    if not alvos:
        return ""

    def _serve(raiz):
        if not raiz or not os.path.isdir(raiz):
            return False
        return all(os.path.isfile(os.path.join(raiz, "agent-%s.jsonl" % i)) for i in alvos)

    direta = _raiz_transcripts(session_id or "", override)
    if _serve(direta):
        return direta
    if _full_str(override):


        return ""
    varredura = os.path.join(os.path.expanduser("~"), ".claude", "projects", "*", "*",
                             "subagents")
    servem = [r for r in sorted(glob.glob(varredura)) if _serve(r)]
    return servem[0] if len(servem) == 1 else ""


def ler_execucao(raiz, agente_id):
    'Lê o transcript do subagente → modelos e efforts observados, em ordem de 1ª'


    modelos, efforts = [], []
    if not _full_str(raiz) or not _full_str(agente_id):
        return modelos, efforts, ""
    caminho = os.path.join(raiz, f"agent-{agente_id.strip()}.jsonl")
    if not os.path.exists(caminho):
        return modelos, efforts, caminho
    try:
        with open(caminho, encoding="utf-8", errors="replace") as fh:
            for linha in fh:
                linha = linha.strip()
                if not linha:
                    continue
                try:
                    d = json.loads(linha)
                except Exception:
                    continue
                if not isinstance(d, dict) or d.get("type") != "assistant":
                    continue
                m = (d.get("message") or {}).get("model") if isinstance(d.get("message"), dict) else None
                if _full_str(m) and m not in modelos:
                    modelos.append(m)
                e = d.get("effort")
                if _full_str(e) and e not in efforts:
                    efforts.append(e)
    except Exception:
        return [], [], caminho
    return modelos, efforts, caminho


def conferir(pedido, modelos, agente_id=None):
    'Pedido × modelos observados → (estado, tiers). Assento que trocou de modelo no meio'



    tiers = [tier_do_id(m) for m in modelos]
    if not modelos:
        return ("SEM_AGENTE" if not _full_str(agente_id) else "NAO_VERIFICAVEL"), tiers
    if not _full_str(pedido):
        return "SEM_PEDIDO", tiers
    if pedido.strip() == "herdado":
        return "HERDADO", tiers
    return ("CONFERIDO" if all(t == pedido.strip() for t in tiers) else "DIVERGENTE"), tiers






ESFORCO_ESPERADO = {"relator": "high", "merito": "high", "coerencia": "high", "escrita": "high",
                    "conformidade": "high", "art942": "high", "autor": "medium"}


def conferir_esforco(assento, efforts):
    '(esperado, estado): CONFERIDO, DIVERGENTE, NAO_REGISTRADO (transcript sem effort) ou'

    esperado = ESFORCO_ESPERADO.get(assento) or (ESFORCO_ESPERADO["art942"]
                                                  if str(assento).startswith("art942") else None)
    if not esperado:
        return None, "SEM_EXPECTATIVA"
    vistos = [e for e in efforts if _full_str(e)]
    if not vistos:
        return esperado, "NAO_REGISTRADO"
    return esperado, ("CONFERIDO" if all(e == esperado for e in vistos) else "DIVERGENTE")


def _assentos(st):
    'Assentos auditáveis do estado: relator, 4 cadeiras, ampliação do art. 942 e o AUTOR'

    out = []
    r = st.get("relator") if isinstance(st.get("relator"), dict) else {}
    out.append(("relator", r.get("agente_id"), r.get("modelo_pedido"), r))
    for c in st.get("cadeiras", []) or []:
        if isinstance(c, dict):
            out.append((c.get("id") or "cadeira", c.get("agente_id"), c.get("modelo_pedido"), c))
    for v in (st.get("art942") or {}).get("votos_extra", []) or []:
        if isinstance(v, dict):
            out.append((v.get("assento") or "art942", v.get("agente_id"), v.get("modelo_pedido"), v))
    if _full_str(st.get("autor_id")):
        out.append(("autor", st.get("autor_id"), st.get("modelo_autor_pedido"), None))
    return out


def main():
    ap = argparse.ArgumentParser(description="Confere o modelo executado × pedido (auditoria, não gate)")
    ap.add_argument("--state", default="CONSELHO_STATUS.json")
    ap.add_argument("--transcripts")
    ap.add_argument("--gravar", action="store_true")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--session-id", dest="session_id")
    args = ap.parse_args()
    try:
        args.state = no_caso(args.state, args.session_id)
    except CaminhoRecusado as e:
        return _saida(e.resultado, [str(e)], 2)
    try:
        if not _full_str(args.state):
            raise Contrato(["--state (caminho do CONSELHO_STATUS.json) obrigatório"])
        try:
            st = json.loads(open(args.state, encoding="utf-8").read())
        except FileNotFoundError:
            raise Contrato([f"sessão não encontrada: {args.state}"])
        except Exception as e:
            raise Contrato([f"CONSELHO_STATUS.json ilegível: {e}"])
        if not isinstance(st, dict):
            raise Contrato(["raiz do CONSELHO_STATUS deve ser objeto JSON"])

        session_id = st.get("session_id")
        raiz = _raiz_transcripts(session_id if _full_str(session_id) else "",
                                 args.transcripts or os.environ.get("DSR_TRANSCRIPTS_DIR"))
        motivos = []
        if not _full_str(session_id):
            motivos.append("sessão sem session_id — abra com 'conselho_sessao.py abrir --session-id' "
                           "para tornar a execução conferível")
        if not _full_str(raiz):
            motivos.append("diretório de transcripts do harness não localizado "
                           "(--transcripts ou DSR_TRANSCRIPTS_DIR)")

        assentos, divergentes, naoverif, esf_div = [], 0, 0, 0
        for nome, aid, pedido, alvo in _assentos(st):
            modelos, efforts, caminho = ler_execucao(raiz, aid)
            estado, tiers = conferir(pedido, modelos, aid)
            if estado == "DIVERGENTE":
                divergentes += 1
            elif estado == "NAO_VERIFICAVEL":
                naoverif += 1
            esperado, esf_estado = (conferir_esforco(nome, efforts) if modelos else (None, "SEM_AGENTE"))
            if esf_estado == "DIVERGENTE":
                esf_div += 1
                motivos.append(f"{nome}: esforço esperado '{esperado}' e executou {efforts}")
            reg = {"assento": nome, "agente_id": aid or "", "modelo_pedido": pedido or "",
                   "modelo_executado": modelos, "tier_executado": tiers,
                   "effort": efforts, "conferencia": estado,
                   "esforco_esperado": esperado, "esforco_conferencia": esf_estado}
            assentos.append(reg)
            if args.gravar and isinstance(alvo, dict):
                alvo["modelo_executado"] = modelos
                alvo["modelo_conferencia"] = estado
                alvo["esforco_conferencia"] = esf_estado
        if args.gravar:

            for reg in assentos:
                if reg["assento"] == "autor":
                    st["modelo_autor_executado"] = reg["modelo_executado"]
                    st["modelo_autor_conferencia"] = reg["conferencia"]
            st["modelo_auditoria"] = {"assentos": len(assentos), "divergentes": divergentes,
                                      "nao_verificaveis": naoverif, "esforco_divergentes": esf_div, "raiz_transcripts": raiz}
            open(args.state, "w", encoding="utf-8").write(json.dumps(st, ensure_ascii=False, indent=2))

        if divergentes:
            motivos = [f"{r['assento']}: pediu '{r['modelo_pedido']}' e executou {r['modelo_executado']}"
                       for r in assentos if r["conferencia"] == "DIVERGENTE"] + motivos
            return _saida("divergencia", motivos, 1,
                          extra={"assentos": assentos, "divergentes": divergentes,
                                 "nao_verificaveis": naoverif, "esforco_divergentes": esf_div, "raiz_transcripts": raiz})
        if naoverif and args.strict:
            motivos = [f"{r['assento']}: execução não verificável (agente_id "
                       f"'{r['agente_id']}' sem transcript legível)"
                       for r in assentos if r["conferencia"] == "NAO_VERIFICAVEL"] + motivos
            return _saida("nao_verificavel", motivos, 1,
                          extra={"assentos": assentos, "divergentes": 0,
                                 "nao_verificaveis": naoverif, "esforco_divergentes": esf_div, "raiz_transcripts": raiz})
        return _saida("conferido", motivos, 0,
                      extra={"assentos": assentos, "divergentes": 0,
                             "nao_verificaveis": naoverif, "esforco_divergentes": esf_div, "raiz_transcripts": raiz})
    except Contrato as e:
        return _saida("contrato_invalido", e.args[0], 2)


if __name__ == "__main__":
    sys.exit(main())
