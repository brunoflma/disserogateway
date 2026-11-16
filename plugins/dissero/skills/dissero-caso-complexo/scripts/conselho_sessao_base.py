"""Módulo-base do conselho_sessao.py: constantes do rito e funções-folha do produtor.

Mora ao lado do conselho_sessao.py, que importa tudo daqui. Num arquivo só, o script encostava
no teto do conector, que recusa script servido maior que ele (truncado, ele não roda); os dois são
servidos e selados, e `conselho_sessao.py conferir` confere os dois selos. Nada aqui lê o estado do
disco nem resolve a pasta do caso: isso fica no principal, onde os testes o substituem."""
import sys, os, json, copy, time, tempfile  # noqa: F401
from datetime import datetime, timezone  # noqa: F401


CADEIRAS = ("merito", "coerencia", "escrita", "conformidade")


NOMES = {"merito": "Mérito", "coerencia": "Coerência", "escrita": "Escrita", "conformidade": "Conformidade"}


RISCOS = ("alto", "baixo")


MODOS = ("subagentes", "serial")


FASES = ("distribuicao", "debate", "votacao", "apreciacao")


RESULTADOS = ("aprovado", "devolvido")


VOTOS = ("aprovar", "devolver")


ST_CADEIRA = ("aguardando", "analisando", "debatendo", "votou")


ST_RELATOR = ("aguardando", "apreciando", "decidiu")


ST_ATA = {"analisando": "em análise", "debatendo": "em debate", "apreciando": "apreciando"}


ROTULOS = {"distribuicao": "Distribuição", "debate": "Debate", "votacao": "Votação",
           "apreciacao": "Apreciação"}


MODELOS = ("opus", "sonnet", "haiku", "herdado")


PERFIS = ("P-A", "P-O", "P-S", "P-H")


SUPERFICIES_EXIBICAO = ("widget", "artifact", "arquivo")


PASSOS = ("distribuicao", "debate", "votacao", "apreciacao", "fim")


LOTE = ("o voto anterior ainda não foi mostrado ao advogado: emita e mostre o painel depois de "
        "CADA voto, na ordem em que chegam (regimento §3 item 7)")


CONVERSOR = ("o conversor desta cópia é anterior à 3.0.1: mostre o plenário inteiro a cada "
             "movimento e atualize a cópia da conta")


def _painel(state):
    b = os.path.basename(state)
    cap = b[16:-5] if b.startswith("CONSELHO_STATUS_") and b.endswith(".json") else ""
    return f"PAINEL_CONSELHO_{cap}.html" if cap else "PAINEL_CONSELHO.html"


class Contrato(Exception):
    pass


def _is_int(x):   return isinstance(x, int) and not isinstance(x, bool)


def _full_str(x): return isinstance(x, str) and bool(x.strip())


def _d(o, k, t=dict):
    v = o.get(k)
    return v if isinstance(v, t) else t()


def _modelo(valor, rotulo="--modelo"):
    if valor is None:
        return None
    if not _full_str(valor):
        raise Contrato([f"{rotulo} não pode ser vazio (declare o tier ou omita a opção)"])
    return valor.strip()


def _tentar(f, *a):
    for i in range(80):
        try:
            return f(*a)
        except PermissionError:
            if i == 79:
                raise
            time.sleep(0.025)


def _stepkey(fase):
    return "fim" if fase in ("aprovado", "devolvido") else fase


def _snapshot(st):
    key = _stepkey(st.get("fase"))
    if not key:
        return
    st.setdefault("historico", {})[key] = {
        "atualizado": st.get("atualizado", ""),
        "fase": st.get("fase"),
        "cadeiras": [{"id": c.get("id"), "status": c.get("status"), "voto": c.get("voto"),
                      "fundamentacao": c.get("fundamentacao", ""),
                      "argumento_debate": c.get("argumento_debate", ""),
                      "modelo_pedido": c.get("modelo_pedido"), "voto_anterior": c.get("voto_anterior")}
                     for c in st.get("cadeiras", []) if isinstance(c, dict)],
        "relator": {k: st.get("relator", {}).get(k)
                    for k in ("status", "voto", "fundamentacao", "placar", "vencido", "modelo_pedido",
                              "voto_anterior")},
        "eventos_len": len(st.get("eventos", [])),
    }


def _lista(st, chave):
    return [e for e in _d(_d(st, "painel"), chave, list) if isinstance(e, dict)]


def _p(e):
    return _stepkey(str(e.get("fase", "")).strip())


def _fases(st, chave):
    return {_p(e) for e in _lista(st, chave)}


def _ult(st, t="proclamacao"):
    return max([i + 1 for i, e in enumerate(_d(st, "eventos", list))
                if isinstance(e, dict) and e.get("tipo") == t], default=0)


def _falta(st, passo):
    """'' em dia; senão 'não EMITIDO' ou 'defasado' (menos votos, ou antes da última revisão ou,
    no fim, da proclamação)."""
    es = [e for e in _lista(st, "emissoes") if _p(e) == passo]
    n, p = sum(_contar_placar(st)), _ult(st, "proclamacao" if passo == "fim" else "revisao_de_voto")
    if any(not (_is_int(e.get("votos")) and e["votos"] < n) and not (
            _is_int(e.get("eventos_len")) and e["eventos_len"] < p) for e in es):
        return ""
    return "defasado (emitido antes do último voto, revisão ou proclamação)" if es else "não EMITIDO"


def _lote(st):
    """Anti-lote (aviso), ANTES do voto; sem `painel.movimentos`, o do conversor."""
    b = _d(st, "painel")
    if "movimentos" not in b:
        if _lista(st, "emissoes") and not b.get("aviso_conversor"):
            b["aviso_conversor"] = True
            return [CONVERSOR]
        return []
    m = (_lista(st, "movimentos") or [{}])[-1]
    v, e = m.get("votos"), m.get("eventos_len")
    return [LOTE] if sum(_contar_placar(st)) > (v if _is_int(v) else 0) or (
        _is_int(e) and e < _ult(st, "revisao_de_voto")) else []


def _arquivar_ciclo(st):
    anteriores = _d(st, "ciclos", list)
    f = st.get("fase")
    anteriores.append({
        "ciclo": st.get("ciclo"), "peca": st.get("peca"), "fase": f, "variante": st.get("variante") or "completo",
        "resultado": f if f in RESULTADOS else None,
        "placar": (st.get("relator") or {}).get("placar", ""),
        "encerrado_em": st.get("atualizado", ""), "session_id": st.get("session_id", ""),
        **{k: copy.deepcopy(st.get(k, [] if k in ("cadeiras", "eventos") else {}))
           for k in ("cadeiras", "relator", "art942", "historico", "eventos", "painel")}})
    return anteriores


def _estado_inicial(peca, risco, ciclo, autor_id, isolamento):
    return {
        "peca": peca, "risco": risco, "fase": "distribuicao", "ciclo": ciclo,
        "autor_id": autor_id, "isolamento": isolamento,
        "relator": {"agente_id": "", "status": "aguardando", "voto": None,
                    "fundamentacao": "", "placar": "", "vencido": False},
        "cadeiras": [{"id": c, "papel": "Vogal — " + NOMES[c], "agente_id": "",
                      "status": "aguardando", "voto": None, "fundamentacao": ""} for c in CADEIRAS],
        "pendencias_jurisprudencia": [], "eventos": [],
    }


def _deliberou(c):
    votos = _d(c, "cadeiras", list) + [c.get("relator")] + _d(_d(c, "art942"), "votos_extra", list)
    return "devolvido" in (c.get("fase"), c.get("resultado")) or any(
        isinstance(v, dict) and v.get("voto") in VOTOS for v in votos)


def _acha_cadeira(st, cid):
    for c in st.get("cadeiras", []):
        if isinstance(c, dict) and c.get("id") == cid:
            return c
    raise Contrato([f"cadeira '{cid}' não existe na sessão (rode 'abrir')"])


def _livre(st, aid, s=None):
    """O autor e o agente de OUTRO assento (cadeiras, relator, ampliação) não ocupam `s`."""
    art = _d(st, "art942")
    if aid == str(st.get("autor_id") or "").strip():
        raise Contrato(["AUTO-CERTIFICAÇÃO: o autor da peça não vota"])
    if aid in [str(x.get("agente_id")).strip() for x in [*st.get("cadeiras", []), st.get("relator"),
               *(art.get("votos_extra") or []), *(art.get("convocados") or [])]
               if isinstance(x, dict) and x is not s]:
        raise Contrato([f"agente_id '{aid}' já ocupa outro assento: um agente, um voto"])


def _ata(nome, args, rev={}):
    v = args.voto and nome + (f" revisou o voto, de {rev['voto_anterior'].upper()} para " if rev.get("tipo")
                              else " votou ") + args.voto.upper()
    if _full_str(args.evento):
        return f"{v}: {args.evento.strip()}" if v else args.evento
    return v or (f"{nome}: {ST_ATA[args.status]}" if args.status in ST_ATA else "")


def _movimento(args):
    return args.voto is not None or args.status not in (None, "aguardando")


def _status_final(args):
    if args.status in ("votou", "decidiu") and args.voto is None:
        raise Contrato([f"--status {args.status} só com --voto: é o voto que o grava"])


def _contar_placar(st):
    vs = [v.get("voto") for v in [*st.get("cadeiras", []), st.get("relator"),
                                  *((st.get("art942") or {}).get("votos_extra") or [])] if isinstance(v, dict)]
    return vs.count("aprovar"), vs.count("devolver")


def _votou(v):
    return (isinstance(v, dict) and v.get("voto") in VOTOS and _full_str(v.get("fundamentacao"))
            and _full_str(v.get("agente_id")))


# ----- REVISÃO LIGHT (decisão do titular, 16/11/2026) -----
# Para conta gratuita ou Pro, onde a turma de cinco agentes esgota o limite: UM revisor percorre em
# SÉRIE os mandatos dos quatro vogais, item a item do catálogo abaixo, e fecha com a síntese do
# relator. Quórum de VETO (qualquer mandato que devolva devolve), sem art. 942. Não é deliberação
# colegiada, e o acórdão diz isso. A escolha é do advogado (escolha_do_conselho.py); o gate conta.
VARIANTES = ("completo", "light")
ITENS_RESULTADO = ("conforme", "nao_conforme", "nao_se_aplica")
# Catálogo fixo: ids estáveis, um bloco por mandato. O 3º campo nomeia o que o GATE confere nos
# artefatos (lint, jurisprudência, versão, prazo, completude), por cima do que o revisor declarar.
CATALOGO_LIGHT = {
    "merito": (("M1", "a tese central tem fundamento legal correto e vigente", None),
               ("M2", "nenhuma jurisprudência a conferir: todo precedente citado está confirmado", "jurisprudencia"),
               ("M3", "cada pedido decorre de um fundamento exposto na peça", None),
               ("M4", "preliminares e prejudiciais cabíveis foram enfrentadas ou afastadas com razão", None)),
    "coerencia": (("C1", "os fatos narrados batem com os documentos citados", None),
                  ("C2", "não há contradição entre partes da peça", None),
                  ("C3", "nomes, datas, valores e números de processo são os mesmos do início ao fim", None),
                  ("C4", "os pedidos correspondem à causa de pedir", None)),
    "escrita": (("E1", "a régua de estilo do escritório foi seguida", None),
                ("E2", "clareza e concisão: um parágrafo, uma ideia", None),
                ("E3", "nenhum nome interno, campo ou marca de ferramenta no texto da peça", "lint"),
                ("E4", "ortografia, concordância e citações formatadas", None)),
    "conformidade": (("F1", "o linter rodou sobre a versão julgada e aprovou (saída 0)", "lint"),
                     ("F2", "o prazo foi calculado e registrado", "prazo"),
                     ("F3", "o levantamento do caso está concluído para esta peça", "completude"),
                     ("F4", "a versão revisada é a mesma que o linter conferiu", "versao"),
                     ("F5", "os documentos citados estão juntados e numerados", None),
                     ("F6", "requisitos formais: endereçamento, qualificação, valor da causa, pedidos e fecho",
                      None)),
}


def _ev(st, quem, texto, em, **k):
    st.setdefault("eventos", []).append({"hora": str(em)[11:16], "quem": quem, "texto": texto, "em": em, **k})


def _recusa_se_light(st, quem):
    if st.get("variante") == "light":
        raise Contrato([f"esta sessão é da Revisão Light, e {quem} é do Conselho completo. Na Revisão Light o "
                        f"revisor registra cada mandato com `mandato --id <mandato>` e a síntese com `mandato "
                        f"--id relator`; depois, `proclamar`. Para o completo, `novo-ciclo --variante completo`."],
                       "comando_do_completo_em_light")


def _escolha(pasta):
    """O registro da escolha (ESCOLHA_CONSELHO.json), lido e com o selo conferido AQUI, sem importar
    o escolha_do_conselho.py: o produtor servido roda de `<caso>/.dissero/`, longe da casca. Mesma
    regra do `escolha_do_conselho.ler` (o teste afirma a igualdade)."""
    import hashlib
    cam = os.path.join(pasta or ".", "ESCOLHA_CONSELHO.json")
    if not os.path.isfile(cam):
        return None, "o advogado ainda não escolheu entre o Conselho completo e a Revisão Light"
    try:
        with open(cam, encoding="utf-8") as fh:
            reg = json.load(fh)
        base = {k: v for k, v in reg.items() if k != "selo"}
        selo = hashlib.sha256(json.dumps(base, ensure_ascii=False, sort_keys=True,
                                         separators=(",", ":")).encode("utf-8")).hexdigest()
    except Exception:
        return None, "o registro da escolha do Conselho está ilegível"
    if (reg.get("schema_version") != "dsr.escolha_do_conselho.v1" or reg.get("variante") not in VARIANTES
            or reg.get("gerado_por") != "escolha_do_conselho.py" or not _full_str(reg.get("palavras"))
            or reg.get("selo") != selo):
        return None, "o registro da escolha do Conselho não foi gravado pelo script (ou foi alterado depois)"
    return reg, None


def _bloco_escolha(state, quer="light"):
    """O bloco a gravar na sessão (cópia do registro da escolha, com o selo), ou Contrato nomeado."""
    pasta = os.path.dirname(os.path.abspath(state))
    reg, motivo = _escolha(pasta)
    if reg is None:
        raise Contrato([f"a Revisão Light não abre sem a escolha do advogado gravada em {pasta} ({motivo}). Faça a "
                        f"pergunta (`escolha_do_conselho.py pergunta`), espere a resposta e grave-a com "
                        f"`escolha_do_conselho.py registrar --pasta \"{pasta}\" --variante light --palavras "
                        f"\"<o que ele escreveu>\"`."], "light_sem_escolha")
    if reg.get("variante") != quer:
        raise Contrato([f"o advogado escolheu o {reg.get('variante')} («{reg.get('palavras')}»), não a "
                        f"Revisão Light. Não troque por ele: se ele mudar de ideia, grave a nova escolha."],
                       "variante_contra_escolha")
    return {k: reg.get(k) for k in ("variante", "palavras", "em", "conferencia", "plano_declarado", "selo")}


def _codigo_completo(c):
    """light_apos_devolucao | light_apos_voto quando `c` é ciclo do COMPLETO que deliberou; senão None."""
    if not isinstance(c, dict) or c.get("variante") == "light" or not _deliberou(c):
        return None
    votos = _d(c, "cadeiras", list) + [c.get("relator")] + _d(_d(c, "art942"), "votos_extra", list)
    dev = "devolvido" in (c.get("fase"), c.get("resultado")) or "devolver" in [
        x.get("voto") for x in votos if isinstance(x, dict)]
    return "light_apos_devolucao" if dev else "light_apos_voto"


def _sessoes_gravadas(pasta):
    """[(arquivo, sessão)] de TODO .json da pasta com forma de sessão do Conselho (cadeiras em lista),
    qualquer que seja o nome: a devolução do completo não se apaga gravando a light em outro arquivo.
    Mesma regra do `escolha_do_conselho._sessoes_da_pasta` (o teste afirma a igualdade)."""
    out = []
    try:
        nomes = sorted(n for n in os.listdir(pasta or ".") if n.lower().endswith(".json"))
    except OSError:
        return out
    for n in nomes:
        cam = os.path.join(pasta or ".", n)
        try:
            if os.path.getsize(cam) > 4_000_000:
                continue
            with open(cam, encoding="utf-8") as fh:
                st = json.load(fh)
        except Exception:
            continue
        if isinstance(st, dict) and isinstance(st.get("cadeiras"), list):
            out.append((cam, st))
    return out


def _recusa_completo_deliberado(antigo, pasta):
    """Contrato nomeado se o completo votou ou devolveu nesta sessão ou em QUALQUER outra da pasta."""
    fontes = [("esta sessão", c) for c in [*_d(antigo, "ciclos", list), antigo]] if isinstance(antigo, dict) else []
    for cam, st in _sessoes_gravadas(pasta):
        fontes += [(os.path.basename(cam), c) for c in [*_d(st, "ciclos", list), st]]
    for onde, c in fontes:
        cod = _codigo_completo(c)
        if cod:
            raise Contrato([f"o Conselho completo já {'devolveu a peça' if cod == 'light_apos_devolucao' else 'votou'} "
                            f"no ciclo {c.get('ciclo')} ({onde}), e a Revisão Light não toma o lugar dele: a "
                            f"ressubmissão volta ao completo."], cod)


def _abrir_light(args):
    """{} no completo; na light, as chaves da sessão (ou Contrato nomeado)."""
    v = getattr(args, "variante", None) or "completo"
    if v not in VARIANTES:
        raise Contrato([f"--variante deve ser um de {VARIANTES}"], "variante_invalida")
    if v == "completo":
        return {}
    if args.risco == "alto" and args.modo == "serial":
        raise Contrato(["em risco alto, a Revisão Light exige um revisor que seja subagente distinto do autor "
                        "(--modo subagentes); a light em série, pelo próprio agente, só em risco baixo"],
                       "light_serial_em_risco_alto")
    bloco = _bloco_escolha(args.state)
    _recusa_completo_deliberado(None, os.path.dirname(os.path.abspath(args.state)))
    return {"variante": "light", "escolha_conselho": bloco}


def _trocar_variante(novo, antigo, args):
    """`novo-ciclo --variante`: ao completo sempre; à light, nunca depois de o completo votar."""
    v = getattr(args, "variante", None)
    if not v:
        return
    if v not in VARIANTES:
        raise Contrato([f"--variante deve ser um de {VARIANTES}"], "variante_invalida")
    if v == "completo":
        novo.pop("variante", None)
        novo.pop("escolha_conselho", None)
        return
    _recusa_completo_deliberado(antigo, os.path.dirname(os.path.abspath(args.state)))
    if (novo.get("risco"), _d(novo, "isolamento").get("modo")) == ("alto", "serial"):
        raise Contrato(["em risco alto, a Revisão Light exige subagente"], "light_serial_em_risco_alto")
    novo.update(variante="light", escolha_conselho=_bloco_escolha(args.state))


def _itens(texto):
    if not _full_str(texto):
        return None
    t = texto.strip()
    if not t.startswith("[") and os.path.isfile(t):
        with open(t, encoding="utf-8") as fh:
            t = fh.read()
    try:
        v = json.loads(t)
    except Exception as e:
        raise Contrato([f"--itens não é JSON legível ({e}): passe a lista [{{id, resultado, trecho}}] ou o "
                        f"caminho de um arquivo com ela"], "itens_invalidos")
    if not isinstance(v, list):
        raise Contrato(["--itens deve ser uma lista [{id, resultado, trecho}]"], "itens_invalidos")
    return v


def conferir_itens(mandato, itens, voto):
    """Motivos (lista vazia = em ordem) da cobertura do catálogo do mandato. Usado pelo produtor e
    pelo gate: catálogo inteiro coberto, id conhecido e único, resultado válido, trecho que diga
    onde/por quê, e nenhuma aprovação por cima de item não conforme."""
    cat = {i for i, _t, _a in CATALOGO_LIGHT.get(mandato, ())}
    m, vistos = [], []
    for it in itens if isinstance(itens, list) else []:
        it = it if isinstance(it, dict) else {}
        i = str(it.get("id") or "").strip()
        if i not in cat:
            m.append(f"item_desconhecido: '{i}' não é item do mandato {mandato} ({sorted(cat)})")
            continue
        if i in vistos:
            m.append(f"item_repetido: '{i}' aparece duas vezes no mandato {mandato}")
        vistos.append(i)
        if it.get("resultado") not in ITENS_RESULTADO:
            m.append(f"item_sem_resultado: '{i}' precisa de resultado {ITENS_RESULTADO}")
        if not _full_str(it.get("trecho")):
            m.append(f"item_sem_trecho: '{i}' precisa do trecho da peça ou da razão do resultado")
        if it.get("resultado") == "nao_conforme" and voto == "aprovar":
            m.append(f"aprovacao_com_item_nao_conforme: o mandato {mandato} aprova com o item '{i}' não "
                     f"conforme; item não conforme devolve a peça")
    falta = sorted(cat - set(vistos))
    if falta:
        m.append(f"checklist_incompleto: o mandato {mandato} não conferiu {falta}; o catálogo inteiro é "
                 f"coberto, item a item")
    return m


def _mandato(st, args, sha):
    """Registra um mandato (ou a síntese do relator) da Revisão Light."""
    if st.get("variante") != "light":
        raise Contrato(["`mandato` é da Revisão Light; no Conselho completo, cada assento vota por `cadeira` e "
                        "`relator`"], "mandato_fora_da_light")
    if st.get("fase") in RESULTADOS:
        raise Contrato([f"a Revisão Light já foi proclamada ({st.get('fase')}); a ressubmissão é o "
                        f"`novo-ciclo`"], "turma_ja_proclamou")
    a = args.id
    if a not in (*CADEIRAS, "relator"):
        raise Contrato([f"--id deve ser um de {(*CADEIRAS, 'relator')}"])
    if args.voto not in VOTOS or not _full_str(args.fundamentacao) or not _full_str(args.agente_id):
        raise Contrato([f"o mandato exige --agente-id, --voto {VOTOS} e --fundamentacao não-vazia"])
    aid, modo = args.agente_id.strip(), _d(st, "isolamento").get("modo")
    if modo != "serial" and aid == str(st.get("autor_id") or "").strip():
        raise Contrato(["AUTO-CERTIFICAÇÃO: com subagente, o revisor da Revisão Light não é o autor da peça"],
                       "revisor_e_o_autor")
    rev = str(_d(st, "revisor").get("agente_id") or "").strip()
    if rev and aid != rev:
        raise Contrato([f"a Revisão Light tem um revisor só ('{rev}'), e o mandato veio de '{aid}'. Para "
                        f"trocar de revisor, abra novo ciclo."], "revisor_trocado")
    alvo = st.setdefault("relator", {}) if a == "relator" else _acha_cadeira(st, a)
    if a == "relator":
        falta = [NOMES[c] for c in CADEIRAS if not _votou(_acha_cadeira(st, c))]
        if falta:
            raise Contrato([f"a síntese do relator fecha a revisão: faltam os mandatos de {', '.join(falta)}"],
                           "mandatos_incompletos")
        itens = []
    else:
        itens = _itens(args.itens)
        m = conferir_itens(a, itens, args.voto) if itens is not None else [
            f"checklist_incompleto: o mandato {a} veio sem --itens"]
        if m:
            raise Contrato(m, m[0].split(":", 1)[0])
    st["revisor"] = {"agente_id": aid, **({"modelo_pedido": args.modelo.strip()} if _full_str(args.modelo) else
                                          {k: v for k, v in _d(st, "revisor").items() if k == "modelo_pedido"})}
    alvo.update(agente_id=aid, voto=args.voto, fundamentacao=args.fundamentacao.strip(),
                status="decidiu" if a == "relator" else "votou", registrado_em=args.ts, docx_sha256=sha)
    if a != "relator":
        alvo["itens_conferidos"] = itens
    if st.get("fase") == "distribuicao":
        st["fase"] = "votacao"
    nome = NOMES.get(a, "Relator (síntese)")
    _ev(st, nome, f"{nome}: {args.voto.upper()} (Revisão Light)", args.ts, assento=a, agente=aid)
    return {"id": a, "voto": args.voto, "itens": len(itens), "revisor": aid}


def _proclamar_light(st, args):
    """Veto: qualquer mandato (ou a síntese) que devolva devolve; sem art. 942."""
    falta = [NOMES[c] for c in CADEIRAS if not _votou(_acha_cadeira(st, c))] + (
        [] if _votou(st.get("relator")) else ["Relator (síntese)"])
    if falta:
        raise Contrato([f"a Revisão Light não terminou: falta {', '.join(falta)}"], "revisao_incompleta")
    vs = [_acha_cadeira(st, c)["voto"] for c in CADEIRAS] + [st["relator"]["voto"]]
    dev = vs.count("devolver")
    certo = "devolvido" if dev else "aprovado"
    if args.resultado != certo:
        raise Contrato([f"na Revisão Light vale o veto: {dev} mandato(s) devolveu(ram), e o resultado é "
                        f"{certo}, não {args.resultado}"], "resultado_contra_placar")
    st["relator"].update(placar=f"veto: {dev} devolução(ões) em 5", vencido=False)
    st["fase"] = certo
    _ev(st, "Relator", f"Revisão Light proclamada: {certo.upper()} ({dev} devolução(ões) em 5; não é "
        f"deliberação colegiada).", args.ts, tipo="proclamacao")
    return {"placar": st["relator"]["placar"], "decisao": certo + "_light"}


def _proximo_light(state, painel="painel_fragmento.py --registrar"):
    return (f'Mostre ao advogado o painel da Revisão Light (`{painel}`, pela via da superfície, e `exibir --fase '
            f'distribuicao`). Despache UM revisor (subagente distinto do autor; sem a ferramenta, o próprio agente '
            f'em série, só em risco baixo), rode `conselho_sessao.py lint --state "{os.path.abspath(state)}"` e '
            f'registre cada mandato na ordem (merito, coerencia, escrita, conformidade) com `mandato --id <mandato> '
            f'--agente-id <id> --voto aprovar|devolver --fundamentacao "..." --itens <lista do catálogo>`, depois a '
            f'síntese (`mandato --id relator`) e `proclamar`, emitindo e mostrando o painel a cada um.')

# Tudo o que o principal usa, inclusive os nomes com sublinhado (o `import *` os pularia).
__all__ = [_n for _n, _v in list(globals().items())
           if not _n.startswith("__") and type(_v) is not type(sys)]
# selo dsr: sha256=c3bd7f9b0240856a6b393b67829a3cbe8b47cbb2a32314030a24afb43666a608
