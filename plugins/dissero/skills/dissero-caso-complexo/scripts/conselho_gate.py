#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'conselho_gate.py — GATE determinístico de entrega do Conselho Revisor (Dissero).'






























































import sys, os, json, argparse, time

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ASSENTOS = ("merito", "coerencia", "escrita", "conformidade")
VOTOS = ("aprovar", "devolver")




try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import verificar_modelo as _vm
except Exception:
    _vm = None



try:
    import caso_raiz as _caso_raiz
except Exception:
    _caso_raiz = None


class CaminhoRecusado(Exception):
    'Nome nu que não se atribui a um arquivo da pasta do caso desta sessão; `resultado`'


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
    'Arquivo de nome NU → o da pasta do caso desta sessão. Caminho com diretório fica como'


    if not (isinstance(caminho, str) and caminho.strip()) or os.path.dirname(caminho):
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
        motivo += (f"Passe o caminho completo do arquivo (\"<pasta do caso>/{caminho}\"). Ou "
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
            f"do caso ({no_raiz}), como arquivos diferentes. Passe o caminho completo do arquivo "
            f"que deve ser julgado: no `estado_peca.py pode-entregar`, o status por "
            f"`--conselho-status \"{no_raiz}\"` e o registro de trabalho por "
            f"DSR_PROV_LEDGER=\"<pasta do caso>/PROVENIENCIA.jsonl\"; no `conselho_gate.py`, o "
            f"status como argumento e o registro por `--proveniencia`. A cópia da pasta corrente "
            f"costuma nascer de subagente que rodou antes de a pasta do caso ser registrada "
            f"(`caso_raiz.py registrar`): se for desta sessão, confira e apague-a."))
    return no_raiz


def _s(x):
    return str(x).strip() if isinstance(x, (str, int, float)) else ""


def _id(x):

    return x.strip() if isinstance(x, str) and x.strip() else ""


def _d(x):
    return x if isinstance(x, dict) else {}


def _carregar_ledger(path, session_id=None):
    'Ledger de proveniência (PROVENIENCIA.jsonl) escrito pelo hook SubagentStart.'


    if not path or not os.path.isfile(path):
        return None
    ids = set()
    try:
        with open(path, encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if not linha:
                    continue
                try:
                    r = json.loads(linha)
                except Exception:
                    continue
                if not isinstance(r, dict):
                    continue
                if session_id and r.get("session_id") != session_id:
                    continue
                aid = r.get("agent_id")
                if isinstance(aid, str) and aid.strip():
                    ids.add(aid.strip())
    except Exception:
        return None
    return ids


def _prova_por_transcript(session_id, agente_id, override):
    'SEGUNDA VIA de proveniência.'














    if _vm is None:
        return False
    try:
        raiz = _vm._raiz_transcripts(session_id or "", override)
        if not raiz:
            return False
        modelos, _efforts, _cam = _vm.ler_execucao(raiz, agente_id)
        return bool(modelos)
    except Exception:
        return False


def _raiz_da_turma(ids_votantes, session_id, override):
    'Resolve UMA raiz de transcripts para a turma inteira, antes de olhar assento por assento.'














    if _vm is None:
        return ""
    try:
        return _vm.raiz_por_ids(ids_votantes, session_id, override) or ""
    except Exception:
        return ""


NOME_LEDGER = "PROVENIENCIA.jsonl"


def _ledgers(st, state_path):
    'Os registros do harness que o `conselho_sessao.py` consulta: o de DSR_PROV_LEDGER; sem ele,'




    env = os.environ.get("DSR_PROV_LEDGER")
    if _s(env):
        return [env.strip()]
    ls = [os.path.join(os.path.dirname(os.path.abspath(state_path)), NOME_LEDGER)]
    raiz, _origem = pasta_do_caso(_s(_d(st).get("session_id")) or None)
    c = os.path.join(raiz, NOME_LEDGER) if raiz else ""
    return ls + ([c] if c and os.path.abspath(c) != os.path.abspath(ls[0]) else [])


def provado(st, state_path, agente_id):
    'O id tem proveniência real (registro do harness ou transcript), pela mesma conferência da'





    if not isinstance(st, dict) or not _s(agente_id):
        return False
    transc = os.environ.get("DSR_TRANSCRIPTS_DIR") or None
    return any(not _verificar_proveniencia(led, [_s(agente_id)], st.get("session_id"), transc)[0]
               for led in _ledgers(st, state_path))


def conferivel(st, state_path):
    'Há onde conferir a proveniência: um dos registros de `_ledgers` existe, ou o diretório de'



    if not isinstance(st, dict):
        return False
    if any(os.path.isfile(led) for led in _ledgers(st, state_path)):
        return True
    if _vm is None:
        return False
    try:
        import glob
        raiz = _vm._raiz_transcripts(_s(st.get("session_id")) or "",
                                     os.environ.get("DSR_TRANSCRIPTS_DIR") or None)
        return bool(raiz) and bool(glob.glob(os.path.join(raiz, "agent-*.jsonl")))
    except Exception:
        return False


def _eventos(st):
    ev = st.get("eventos") if isinstance(st, dict) and isinstance(st.get("eventos"), list) else []
    return [_d(e) for e in ev]


def _epoch(x):
    'Instante em segundos: número (o `ts` do registro) ou ISO 8601 (o `em` da ata, o `timestamp`'

    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return float(x)
    try:
        from datetime import datetime
        d = datetime.fromisoformat(_s(x).replace("Z", "+00:00"))
        return (d if d.tzinfo else d.astimezone()).timestamp()
    except Exception:
        return None


def _jsonl(caminho):
    """Os objetos de um .jsonl; ausente ou ilegível, lista vazia (linha ruim não derruba as outras)."""
    try:
        with open(caminho, encoding="utf-8", errors="replace") as f:
            linhas = f.read().splitlines()
    except Exception:
        return []
    out = []
    for linha in linhas:
        try:
            r = json.loads(linha)
        except Exception:
            continue
        if isinstance(r, dict):
            out.append(r)
    return out


def estado_novo(st):
    'A sessão foi aberta por produtor que grava `em` em cada linha da ata (3.0.1 em diante): a'



    ev = _eventos(st)
    return bool(ev) and bool(ev[0].get("em")) and ev[0].get("tipo") != "reabertura"


def reabre(st):
    'O art. 942 reabre a decisão proclamada (quem chama é o `conselho_sessao.py`): só o estado'


    if not isinstance(st, dict) or estado_novo(st):
        return False
    if any(e.get("tipo") == "proclamacao" for e in _eventos(st)):
        return False
    cad = st.get("cadeiras") if isinstance(st.get("cadeiras"), list) else []
    return len({_d(v).get("voto") for v in [*cad, st.get("relator")]}) > 1


def _reaberta_em(st):
    """Instante (epoch) da última linha `tipo: reabertura`, ou None."""
    em = [e.get("em") for e in _eventos(st) if e.get("tipo") == "reabertura"]
    return _epoch(em[-1]) if em else None


def _ativo(st, ledgers, agente_id, t0, transcritos=None):
    'O agente trabalhou no instante `t0` ou depois: entrada dele no registro do harness com `ts`'



    aid, sid = _s(agente_id), _s(_d(st).get("session_id")) or None
    if not aid or t0 is None:
        return False
    for led in ledgers or []:
        for r in _jsonl(led):
            if (_s(r.get("agent_id")) == aid and (not sid or r.get("session_id") == sid)
                    and (_epoch(r.get("ts")) or -1) >= t0):
                return True
    if _vm is None:
        return False
    try:
        raiz = (_vm.raiz_por_ids([aid], sid, transcritos)
                or _vm._raiz_transcripts(sid or "", transcritos))
        return bool(raiz) and any(
            d.get("type") == "assistant" and (_epoch(d.get("timestamp")) or -1) >= t0
            for d in _jsonl(os.path.join(raiz, f"agent-{aid}.jsonl")))
    except Exception:
        return False


def ativo(st, state_path, assento):
    'Para o `conselho_sessao.py`, na revisão do voto: o agente gravado no assento trabalhou'

    return _ativo(st, _ledgers(st, state_path), _d(assento).get("agente_id"), _reaberta_em(st),
                  os.environ.get("DSR_TRANSCRIPTS_DIR") or None)


def _ata_confere(st, ledger=None, transcritos=None, estado="<caso>/CONSELHO_STATUS.json"):
    'O que a ata diz contra o estado: por estrutura, sempre; com o registro (`ledger`, sob'











    ev, m = _eventos(st), []
    novo = f'Submeta a peça de novo à turma com `conselho_sessao.py novo-ciclo --state "{estado}"`.'
    tipos = [e.get("tipo") for e in ev]
    if estado_novo(st) and ("reabertura" in tipos or "revisao_de_voto" in tipos):
        m.append("reabertura_em_estado_novo: a ata tem reabertura ou revisão de voto do art. 942 "
                 "numa sessão aberta pelo produtor atual, que proclama com a linha `tipo: "
                 "proclamacao` e não reabre a decisão. " + novo)
    elif "revisao_de_voto" in tipos and (
            "reabertura" not in tipos or tipos.index("revisao_de_voto") < tipos.index("reabertura")):
        m.append("revisao_sem_reabertura: a ata tem revisão de voto antes de qualquer reabertura da "
                 "apreciação pelo art. 942; só na apreciação reaberta quem votou revê o voto. " + novo)
    cad = st.get("cadeiras") if isinstance(st.get("cadeiras"), list) else []
    atual = {_s(_d(c).get("id")): _d(c) for c in cad}
    atual["relator"] = _d(st.get("relator"))
    for a, s in sorted(atual.items()):
        idx = [i for i, e in enumerate(ev) if _s(e.get("assento")) == a and "agente" in e]
        if not idx or s.get("voto") not in VOTOS:
            continue
        quem = _s(ev[idx[-1]].get("agente"))
        for e in ev[idx[-1] + 1:]:
            if (e.get("tipo") == "correcao_de_agente" and _s(e.get("assento")) == a
                    and _s(e.get("agente_anterior")) == quem):
                quem = _s(e.get("agente_novo"))
        if quem != _s(s.get("agente_id")):
            m.append(f"votante_trocado: pela ata, o voto do assento {a} é de '{quem}', e o id "
                     f"gravado é '{_s(s.get('agente_id'))}', sem a linha `correcao_de_agente` da "
                     f"troca. " + novo)
    if ledger is not None:
        t0 = None
        for e in ev:
            if e.get("tipo") == "reabertura":
                t0 = _epoch(e.get("em"))
            elif e.get("tipo") == "revisao_de_voto" and not _ativo(
                    st, [ledger], e.get("agente"), t0, transcritos):
                m.append(f"revisao_sem_autoria: a revisão do voto do assento "
                         f"{_s(e.get('assento'))} não tem trabalho do agente "
                         f"'{_s(e.get('agente'))}' depois da reabertura, no registro do harness nem "
                         f"no transcript: a revisão é de quem votou. " + novo)
    return m


def aviso_proveniencia(st, state_path, agente_id):
    'Aviso no REGISTRO do assento quando o id não tem proveniência real (E2 do teste do titular,'


    if not isinstance(st, dict) or st.get("risco") != "alto" or not _s(agente_id):
        return []
    if provado(st, state_path, agente_id):
        return []
    return [f"o agente_id '{_s(agente_id)}' não tem proveniência no registro do harness nem transcript de "
            f"subagente desta sessão: o voto dele será recusado na entrega. Use o id que o harness deu "
            f"ao subagente que ocupa o assento."]







class PecaRecusada(Exception):
    def __init__(self, codigo, motivo):
        super().__init__(motivo)
        self.codigo = codigo


def _sha256(caminho):
    import hashlib
    h = hashlib.sha256()
    with open(caminho, "rb") as fh:
        for bloco in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def peca_julgada(st, state_path, peca_state=None, conferir=True):
    '(docx, sha256, origem, PECA_STATE lido ou {}, pasta do caso). A peça é o `arquivo_canonico`'



    pasta = os.path.dirname(os.path.abspath(state_path))
    ps = os.path.abspath(peca_state) if _s(peca_state) else os.path.join(pasta, "PECA_STATE.json")
    remedio = ("Registre a peça no PECA_STATE.json da pasta do caso (`estado_peca.py canonico "
               "--arquivo <peça>.docx`) ou passe-o com --peca-state.")
    if _s(peca_state) and not os.path.isfile(ps):
        raise PecaRecusada("peca_nao_localizada", f"o PECA_STATE indicado não existe: {ps}. " + remedio)
    if os.path.isfile(ps):
        try:
            pst = json.loads(open(ps, encoding="utf-8").read())
        except Exception as e:
            raise PecaRecusada("peca_nao_localizada", f"PECA_STATE ilegível em {ps} ({e}). " + remedio)
        pst, base = _d(pst), os.path.dirname(ps)
        canon = _s(pst.get("arquivo_canonico"))
        if canon:
            alvo = canon if os.path.isabs(canon) else os.path.join(base, canon)
            if not os.path.isfile(alvo):
                raise PecaRecusada("peca_nao_localizada", f"a peça canônica do PECA_STATE não existe: {alvo}")
            sha = _sha256(alvo)
            if conferir and sha != _s(pst.get("hash_canonico")):
                raise PecaRecusada("canonico_divergente", (
                    f"a peça canônica ({alvo}) não é a que o PECA_STATE carimbou (hash_canonico "
                    f"{'ausente' if not _s(pst.get('hash_canonico')) else 'diferente'}): ela mudou "
                    f"depois do carimbo. Confira a versão com o advogado e recarimbe com "
                    f"`estado_peca.py canonico --arquivo \"{alvo}\"` antes de lintear."))
            return alvo, sha, "arquivo_canonico", pst, base
        art = _s(_d(_d(pst.get("fases")).get("visual_law")).get("artefato"))
        alvo = art if os.path.isabs(art) else os.path.join(base, art)
        if art.lower().endswith(".docx") and os.path.isfile(alvo):
            return alvo, _sha256(alvo), "visual_law", pst, base
        raise PecaRecusada("peca_nao_localizada", f"o PECA_STATE ({ps}) não aponta a peça. " + remedio)
    peca = _s(st.get("peca"))
    alvo = peca if os.path.isabs(peca) else os.path.join(pasta, peca)
    if peca.lower().endswith(".docx") and os.path.isfile(alvo):
        return alvo, _sha256(alvo), "peca_da_sessao", {}, pasta
    raise PecaRecusada("peca_nao_localizada", (
        f"não há PECA_STATE.json em {pasta} nem a sessão nomeia um .docx existente (peça: «{peca}»), "
        f"e o linter só roda sobre a peça real. " + remedio))


def hash_julgado(st, state_path):
    """sha256 da peça que o assento julga no instante do voto, ou None se ela não se localiza."""
    try:
        return peca_julgada(st, state_path, _d(st.get("lint")).get("peca_state"), conferir=False)[1]
    except Exception:
        return None


def _lint_peca():
    aqui = os.path.dirname(os.path.abspath(__file__))
    for alvo in (os.path.join(aqui, "lint_peca.py"),
                 os.path.join(aqui, "..", "..", "dissero-visual-law", "scripts", "lint_peca.py")):
        if os.path.isfile(alvo):
            return os.path.abspath(alvo)
    return None


def lint_real(st, state_path, args):
    "{'lint': bloco} com o resultado REEXECUTADO, ou {'codigo', 'recusa'}. O que vier declarado"

    import subprocess
    try:
        docx, sha, origem, pst, pasta = peca_julgada(st, state_path, getattr(args, "peca_state", None))
    except PecaRecusada as e:
        return {"codigo": e.codigo, "recusa": str(e)}
    linter = _lint_peca()
    if not linter:
        return {"codigo": "lint_nao_reexecutado", "recusa": (
            "o lint_peca.py não está ao alcance (ao lado do conselho_gate.py ou na skill "
            "dissero-visual-law), e o lint do Conselho é o resultado da reexecução, não o relatado.")}
    cmd = [sys.executable, linter, docx]
    jnt = os.path.join(pasta, "JUNTADA_TRACKER.json")
    for flag, nome in (("--precedentes", "achados.json"), ("--juntada", "JUNTADA_TRACKER.json"),
                       ("--conferencia", "CONFERENCIA.json")):
        alvo = os.path.join(pasta, nome)
        if flag == "--conferencia" and os.path.isfile(jnt):
            try:
                if _s(_d(json.loads(open(jnt, encoding="utf-8").read())).get("conferencia")):
                    continue
            except Exception:
                pass
        if os.path.isfile(alvo):
            cmd += [flag, alvo]
    if _s(pst.get("grau_jurisdicao")):
        cmd += ["--grau", _s(pst.get("grau_jurisdicao"))]
    for numero in (pst.get("processos") if isinstance(pst.get("processos"), list) else []):
        if _s(numero):
            cmd += ["--processo", _s(numero)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=60)
    except Exception as e:
        return {"codigo": "lint_nao_reexecutado", "recusa": f"o linter não rodou sobre {docx} ({e})."}
    resultado = "APROVADO" if r.returncode == 0 else "REPROVADO"
    dres, dec = getattr(args, "resultado", None), getattr(args, "exit_code", None)
    if (dres is not None and dres != resultado) or (dec is not None and dec != r.returncode):
        return {"codigo": "lint_divergente", "recusa": (
            f"o declarado (resultado={dres}, exit={dec}) não é o que o linter devolveu agora sobre "
            f"{docx} (resultado={resultado}, exit={r.returncode}). Vale a reexecução: rode `lint` "
            f"sem --resultado e --exit-code.")}
    bloco = {"resultado": resultado, "exit_code": r.returncode,
             "saida": (r.stdout or "")[-2000:], "reexecutado": True, "docx": docx,
             "docx_sha256": sha, "origem": origem}
    if _s(getattr(args, "peca_state", None)):
        bloco["peca_state"] = os.path.abspath(args.peca_state)
    return {"lint": bloco}


_NOMES_ASSENTO = {"merito": "Mérito", "coerencia": "Coerência", "escrita": "Escrita",
                  "conformidade": "Conformidade", "relator": "Relator"}


def versoes_divergentes(st):
    'Motivos de bloqueio quando os votos e o lint não falam da MESMA peça: voto com hash de'

    lint, motivos = _d(st.get("lint")), []
    alvo = _s(lint.get("docx_sha256"))
    if not alvo:
        return motivos
    art = _d(st.get("art942"))
    votos = ([("relator", st.get("relator"))]
             + [(_s(_d(c).get("id")), c) for c in (st.get("cadeiras") if isinstance(st.get("cadeiras"), list) else [])]
             + [(_s(_d(v).get("assento")) or "ampliação do art. 942", v)
                for v in (art.get("votos_extra") if isinstance(art.get("votos_extra"), list) else [])])
    for assento, v in votos:
        h = _s(_d(v).get("docx_sha256"))
        if _d(v).get("voto") in VOTOS and not h:
            motivos.append(f"voto_sem_versao: o voto de {_NOMES_ASSENTO.get(assento, assento)} não "
                           f"registra qual versão da peça julgou (a peça não se localizava no "
                           f"instante do voto), e o lint conferiu uma versão certa. Registre o voto "
                           f"de novo, depois do `lint`, para ele ficar ligado à versão linteada "
                           f"(com a sessão já proclamada, pelo `novo-ciclo`).")
        elif _d(v).get("voto") in VOTOS and h != alvo:
            motivos.append(f"voto_sobre_outra_versao: o voto de {_NOMES_ASSENTO.get(assento, assento)} "
                           f"foi dado sobre outra versão da peça, não a que o linter conferiu. A turma "
                           f"julga de novo a versão atual (`conselho_sessao.py novo-ciclo`).")
    docx = _s(lint.get("docx"))
    if docx and os.path.isfile(docx) and _sha256(docx) != alvo:
        motivos.append(f"peca_mudou_depois_do_lint: {docx} mudou depois do lint e dos votos. Rode o "
                       f"`lint` de novo e submeta a versão atual à turma (`novo-ciclo`).")
    return motivos


def _verificar_proveniencia(ledger_path, ids_votantes, session_id, transcritos=None):
    'Cada agente_id de voto DEVE ter proveniência REAL do harness (fail-closed).'



    lido = _carregar_ledger(ledger_path, session_id)
    reais = lido or set()
    sem_ledger = "" if lido is not None else " (ledger PROVENIENCIA.jsonl ausente/ilegível)"
    raiz_turma = _raiz_da_turma(ids_votantes, session_id, transcritos)
    rotas, faltando = {}, []
    for i in ids_votantes:
        if i in reais:
            rotas[i] = "ledger"
        elif _prova_por_transcript(session_id, i, raiz_turma or transcritos):
            rotas[i] = "transcript"
        else:
            faltando.append(i)
    if faltando:
        return ([f"agente_id sem proveniência real{sem_ledger} — não consta no ledger do harness "
                 f"nem tem transcript de subagente legível: {sorted(set(faltando))}. Identidade "
                 f"auto-declarada não é aceita sob --proveniencia"], rotas)
    return ([], rotas)


def _correcoes(st, ledger_path, session_id, transcritos, estado):
    'A correção de id (`conselho_sessao.py`, linha `tipo: correcao_de_agente` da ata) é só de id'







    ev = st.get("eventos") if isinstance(st.get("eventos"), list) else []
    orig = {}
    for e in ev:
        e = _d(e)
        if e.get("tipo") == "correcao_de_agente" and _s(e.get("assento")):
            orig.setdefault(_s(e.get("assento")), _s(e.get("agente_anterior")))
    cad = st.get("cadeiras") if isinstance(st.get("cadeiras"), list) else []
    atual = {_s(_d(c).get("id")): _s(_d(c).get("agente_id")) for c in cad}
    atual["relator"] = _s(_d(st.get("relator")).get("agente_id"))
    m = []
    for a, o in sorted(orig.items()):
        n = atual.get(a, "")
        if o and o != n and not _verificar_proveniencia(ledger_path, [o], session_id, transcritos)[0]:
            m.append(f"correcao_de_agente: o assento {a} votou como '{o}', que tem proveniência "
                     f"real, e o id gravado passou a '{n}'. A correção é só de id gravado errado; "
                     f"trocar o id troca quem votou. Submeta a peça de novo à turma com "
                     f"`conselho_sessao.py novo-ciclo --state \"{estado}\"`.")
    return m


def _stepkey(fase):
    "Fase → passo do painel (aprovado/devolvido são o mesmo passo 'fim'). Espelha o"

    return "fim" if fase in ("aprovado", "devolvido") else fase


PASSOS_CANONICOS = ("distribuicao", "debate", "votacao", "apreciacao", "fim")


def _int(x):
    return isinstance(x, int) and not isinstance(x, bool)


def _votos_registrados(st):
    'Votos registrados (cadeiras, relator e `art942.votos_extra` com voto), a conta que o'


    art = _d(st.get("art942"))
    cad = st.get("cadeiras") if isinstance(st.get("cadeiras"), list) else []
    ext = art.get("votos_extra") if isinstance(art.get("votos_extra"), list) else []
    return sum(1 for v in [*cad, st.get("relator"), *ext] if _d(v).get("voto") in VOTOS)


def _fim_defasado(st, emissoes):
    "O painel da decisão mostra outro estado: TODA emissão do passo 'fim' tem menos votos que os"



    ev = st.get("eventos") if isinstance(st.get("eventos"), list) else []
    proc = max([i + 1 for i, e in enumerate(ev) if _d(e).get("tipo") == "proclamacao"], default=0)
    n = _votos_registrados(st)
    fim = [_d(e) for e in emissoes if _stepkey(_s(_d(e).get("fase"))) == "fim"]
    return bool(fim) and not any(
        not (_int(e.get("votos")) and e["votos"] < n)
        and not (_int(e.get("eventos_len")) and e["eventos_len"] < proc) for e in fim)


def _verificar_painel(st, estado="<caso>/CONSELHO_STATUS.json"):
    'Regimento §3: o painel é por fase, e reexibido a cada movimento. O gate confere uma'












    hist = st.get("historico") if isinstance(st.get("historico"), dict) else {}
    declaradas = {k for k in hist.keys() if isinstance(k, str) and k.strip()}
    nunca_declaradas = [p for p in PASSOS_CANONICOS if p not in declaradas]
    if nunca_declaradas:
        return [f"painel (§3): fase(s) do rito NUNCA DECLARADAS: {', '.join(nunca_declaradas)} — "
                f"sem o snapshot no histórico o passo do stepper fica INERTE (o advogado clica e "
                f"nada acontece). Declare cada fase com `conselho_sessao.py fase "
                f"--state \"{estado}\" --fase …` e emita o painel: ele é por "
                f"fase, e reexibido a cada movimento"]
    passos = list(PASSOS_CANONICOS)

    painel = _d(st.get("painel"))
    emissoes = painel.get("emissoes") if isinstance(painel.get("emissoes"), list) else []
    cobertas = {_stepkey(_s(e.get("fase"))) for e in emissoes if isinstance(e, dict) and _s(e.get("fase"))}
    if not cobertas:
        return ["painel (§3) NÃO EMITIDO: o advogado precisa VER a turma deliberando, não só o "
                f"resultado. Rode `painel_fragmento.py --state \"{estado}\" "
                "--registrar` e exiba a saída pela via da superfície: o painel é por fase, e "
                "reexibido a cada movimento (regimento §3 item 7)"]

    faltando = [p for p in passos if p not in cobertas]
    if faltando:
        return [f"painel (§3): fase(s) sem emissão registrada: {', '.join(sorted(faltando))} — "
                f"o painel é por fase, e reexibido a cada movimento, não só no fim"]



    if _fim_defasado(st, emissoes):
        return ["painel_defasado: o painel da decisão (passo 'fim') foi emitido antes do estado "
                "atual, com menos votos que os registrados ou antes da última proclamação, e o "
                "advogado viu outro placar. Reemita-o com `painel_fragmento.py --state "
                f"\"{estado}\" --registrar`, mostre-o e declare com "
                f"`conselho_sessao.py exibir --state \"{estado}\" --superficie "
                "widget|artifact|arquivo --fase fim`"]









    exibicoes = painel.get("exibicoes") if isinstance(painel.get("exibicoes"), list) else []
    vistas = {_stepkey(_s(e.get("fase"))) for e in exibicoes if isinstance(e, dict) and _s(e.get("fase"))}
    nao_exibidas = [p for p in passos if p not in vistas]
    if nao_exibidas:
        return [f"painel (§3): fase(s) EMITIDAS e não EXIBIDAS: {', '.join(sorted(nao_exibidas))} — "
                f"emitir o painel não é mostrá-lo ao advogado. Exiba o painel de cada fase (pela "
                f"ferramenta de widget da superfície; sem ela, enviando o PAINEL_CONSELHO.html ao "
                f"advogado pela ferramenta de arquivo da sessão, declarado na conversa, que se "
                f"registra como 'arquivo'; no Cowork, o live artifact, como 'artifact') e registre "
                f"com `conselho_sessao.py exibir --state \"{estado}\" "
                f"--superficie widget|artifact|arquivo --fase <fase>`"]
    return []


def _ler_status(caminho):
    'O status, relido no PermissionError do Windows: quem grava troca o arquivo atômico'

    for i in range(40):
        try:
            with open(caminho, encoding="utf-8") as f:
                return f.read()
        except PermissionError:
            if i == 39:
                raise
            time.sleep(0.025)


def _erro(motivos, exit_code=1, resultado="bloqueado"):
    print(json.dumps({"ok": True, "liberado": False, "resultado": resultado, "motivos": motivos}, ensure_ascii=False))
    return exit_code


def validar_contrato(st):
    if not isinstance(st, dict):
        return ["raiz do CONSELHO_STATUS.json não é um objeto JSON"]
    m = []
    for k in ("peca", "risco", "fase", "relator", "cadeiras", "lint"):
        if k not in st:
            m.append(f"campo obrigatório ausente: {k}")
    if st.get("risco") not in ("alto", "baixo"):
        m.append("risco inválido (use alto|baixo)")
    if not isinstance(st.get("lint"), dict) or "resultado" not in _d(st.get("lint")):
        m.append("bloco 'lint' ausente/inválido (precisa de resultado + exit_code)")
    if "relator" in st and not isinstance(st.get("relator"), dict):
        m.append("'relator' deve ser objeto")
    if "cadeiras" in st and not isinstance(st.get("cadeiras"), list):
        m.append("'cadeiras' deve ser lista")
    if st.get("isolamento") is not None and not isinstance(st.get("isolamento"), dict):
        m.append("'isolamento' deve ser objeto")
    if st.get("art942") is not None and not isinstance(st.get("art942"), dict):
        m.append("'art942' deve ser objeto")

    if st.get("pendencias_jurisprudencia") is not None and not isinstance(st.get("pendencias_jurisprudencia"), list):
        m.append("'pendencias_jurisprudencia' deve ser lista (tipo inválido não é tratado como vazio)")
    lb = _d(st.get("lint")).get("exit_code")
    if lb is not None and (isinstance(lb, bool) or not isinstance(lb, int)):
        m.append("lint.exit_code deve ser inteiro (bool/float/str não contam como 0)")
    if st.get("conselho_dispensado") is not None and not isinstance(st.get("conselho_dispensado"), bool):
        m.append("conselho_dispensado deve ser booleano (string 'false'/1/'yes' são truthy e dispensariam o conselho indevidamente)")

    if not st.get("conselho_dispensado") and not _id(st.get("autor_id")):
        m.append("autor_id OBRIGATÓRIO (anti auto-certificação) — quem redigiu a peça não pode votar")
    return m


def _ciclo_devolvido(st):
    'Número do ciclo (o corrente ou um arquivado em `ciclos`) em que a turma devolveu a peça:'




    anteriores = st.get("ciclos") if isinstance(st.get("ciclos"), list) else []
    for c in [*anteriores, st]:
        c = _d(c)
        art = _d(c.get("art942"))
        cad = c.get("cadeiras") if isinstance(c.get("cadeiras"), list) else []
        ext = art.get("votos_extra") if isinstance(art.get("votos_extra"), list) else []
        if "devolvido" in (c.get("fase"), c.get("resultado")) or any(
                _d(v).get("voto") == "devolver" for v in [*cad, c.get("relator"), *ext]):
            return c.get("ciclo") if c.get("ciclo") is not None else "corrente"
    return None


def _voto_registrado(st):
    '(ciclo, assento) do primeiro voto registrado no ciclo corrente ou num arquivado em'




    anteriores = st.get("ciclos") if isinstance(st.get("ciclos"), list) else []
    for c in [*anteriores, st]:
        c = _d(c)
        art = _d(c.get("art942"))
        cad = c.get("cadeiras") if isinstance(c.get("cadeiras"), list) else []
        ext = art.get("votos_extra") if isinstance(art.get("votos_extra"), list) else []
        assentos = ([("relator", c.get("relator"))]
                    + [(_s(_d(v).get("id")) or "vogal", v) for v in cad]
                    + [(_s(_d(v).get("assento")) or "ampliação do art. 942", v) for v in ext])
        for assento, v in assentos:
            voto = _d(v).get("voto")
            if voto is not None and not (isinstance(voto, str) and not voto.strip()):
                return (c.get("ciclo") if c.get("ciclo") is not None else "corrente"), assento
    return None


def coletar_votos(st):
    motivos, votos = [], []
    rel = _d(st.get("relator"))
    if rel.get("voto") in VOTOS and _s(rel.get("fundamentacao")) and _id(rel.get("agente_id")):
        votos.append({"assento": "relator", "agente_id": _id(rel.get("agente_id")),
                      "voto": rel.get("voto"), "fundamentacao": _s(rel.get("fundamentacao"))})
    else:
        motivos.append("voto do relator ausente/incompleto (agente_id + voto + fundamentação)")
    cadeiras = st.get("cadeiras") if isinstance(st.get("cadeiras"), list) else []
    vistos = {_d(c).get("id") for c in cadeiras}
    for a in ASSENTOS:
        if a not in vistos:
            motivos.append(f"assento ausente: {a}")
    for c in cadeiras:
        c = _d(c)
        if c.get("id") not in ASSENTOS:
            motivos.append(f"assento desconhecido/ inválido: {c.get('id')}"); continue
        if c.get("voto") in VOTOS and _s(c.get("fundamentacao")) and _id(c.get("agente_id")):
            votos.append({"assento": c["id"], "agente_id": _id(c.get("agente_id")),
                          "voto": c.get("voto"), "fundamentacao": _s(c.get("fundamentacao"))})
        else:
            motivos.append(f"voto incompleto no assento {c.get('id')} (agente_id + voto + fundamentação)")
    return votos, motivos


def main():
    ap = argparse.ArgumentParser(description="Gate de entrega do Conselho Revisor (Dissero)")
    ap.add_argument("status")
    ap.add_argument("--painel", action="store_true",
                    help="exige que o PAINEL do Conselho tenha sido emitido E exibido em cada fase "
                         "(regimento §3: por fase, e reexibido a cada movimento). Emissão pelo "
                         "painel_fragmento.py --registrar; exibição pelo conselho_sessao.py exibir. "
                         "Sem esta flag, o painel não é exigido pelo gate.")
    ap.add_argument("--proveniencia", dest="proveniencia", default=None,
                    help="ledger PROVENIENCIA.jsonl: exige que cada agente_id de voto conste no "
                         "ledger real do harness (hook SubagentStart). Ausência/ID faltante = fail-closed. "
                         "Sem esta flag, a proveniência não é exigida.")
    ap.add_argument("--transcritos", dest="transcritos", default=None,
                    help="diretório de transcripts de subagente (SEGUNDA VIA de proveniência, "
                         "usada só para o que faltar no ledger — onde o ledger não nasce; o "
                         "SubagentStart no Cowork remoto do claude.ai está a medir). Omitido, resolve pelo caminho padrão do harness a partir do "
                         "session_id do CONSELHO_STATUS.")
    ap.add_argument("--session-id", dest="session_id", default=None,
                    help="id da sessão do harness. Com status de nome nu, localiza a pasta do "
                         "caso registrada para esta sessão; sem ele (e sem DSR_CASO_RAIZ), o "
                         "nome nu é recusado com caso_nao_resolvido.")
    args = ap.parse_args()
    try:
        args.status = no_caso(args.status, args.session_id)
    except CaminhoRecusado as e:
        return _erro([str(e)], 2, e.resultado)
    try:
        st = json.loads(_ler_status(args.status))
    except Exception as e:
        return _erro([f"CONSELHO_STATUS.json ilegível/JSON inválido: {e}"], 2, "contrato_invalido")

    cm = validar_contrato(st)
    if cm:
        return _erro(cm, 2, "contrato_invalido")

    risco = st["risco"]
    lint = _d(st.get("lint"))
    _ec = lint.get("exit_code")
    lint_ok = (lint.get("resultado") == "APROVADO" and isinstance(_ec, int)
               and not isinstance(_ec, bool) and _ec == 0)
    pend = st.get("pendencias_jurisprudencia") if isinstance(st.get("pendencias_jurisprudencia"), list) else []


    if st.get("conselho_dispensado"):
        motivos = []
        if risco == "alto":
            return _erro(["risco ALTO não dispensa o conselho (conselho_dispensado inválido)"])
        devolvido = _ciclo_devolvido(st)
        if devolvido is not None:
            return _erro([f"dispensa_com_devolucao: o conselho está dispensado, mas a turma "
                          f"devolveu a peça no ciclo {devolvido}. A devolução não se apaga com a "
                          f"dispensa (o `conselho_sessao.py dispensar` a recusa). Corrija a peça "
                          f"e submeta-a de novo à turma pelo `conselho_sessao.py novo-ciclo`."],
                         1, "dispensa_com_devolucao")
        votado = _voto_registrado(st)
        if votado is not None:
            estado = os.path.abspath(args.status)
            abrir = (f'conselho_sessao.py abrir --state "{estado}" --peca "{st.get("peca")}" '
                     f'--risco {risco} --autor-id "{st.get("autor_id")}"'
                     + (f' --session-id "{_s(st.get("session_id"))}"'
                        if _s(st.get("session_id")) else ""))
            return _erro([f"dispensa_com_voto: o conselho está dispensado, mas há voto registrado "
                          f"no ciclo {votado[0]} (assento {votado[1]}). Esse estado não sai do "
                          f"`conselho_sessao.py`: o `dispensar` recusa sessão votada, e voto não "
                          f"se registra depois da dispensa. Para a turma deliberar, abra a "
                          f"sessão de novo sem a dispensa: remova \"{estado}\" e rode "
                          f"`{abrir}`."],
                         1, "dispensa_com_voto")
        if not _s(st.get("conselho_dispensado_justificativa")):
            motivos.append("conselho_dispensado exige 'conselho_dispensado_justificativa' "
                           "(registro de por que o risco é baixo)")
        if not lint_ok:
            motivos.append(f"lint não APROVADO (resultado={lint.get('resultado')}, exit={lint.get('exit_code')})")
        motivos += versoes_divergentes(st)
        if pend:
            motivos.append(f"{len(pend)} pendência(s) de jurisprudência: {pend}")
        if motivos:
            return _erro(motivos)
        acordao = ("ENTREGA LIBERADA (risco baixo, conselho dispensado/opt-in): lint APROVADO e sem "
                   "pendência de jurisprudência. ATENÇÃO: dispensa sob risco baixo AUTODECLARADO — "
                   f"confirme a classificação ('{_s(st.get('conselho_dispensado_justificativa'))[:80]}'). Minuta para revisão do advogado.")
        print(json.dumps({"ok": True, "liberado": True, "resultado": "liberado_optin",
                          "placar": "n/a (opt-in)", "motivos": [], "acordao": acordao}, ensure_ascii=False))
        return 0


    votos, motivos = coletar_votos(st)
    autor = _id(st.get("autor_id"))
    ids = [v["agente_id"] for v in votos]
    if autor and autor in ids:
        motivos.append(f"AUTO-CERTIFICAÇÃO: o autor da peça (autor_id={autor}) está entre os votantes")
    if len(set(ids)) != len(ids):
        motivos.append("agente_id repetido entre assentos — um agente não pode ocupar dois assentos (um agente, um voto)")
    modo = _d(st.get("isolamento")).get("modo")
    if risco == "alto" and modo != "subagentes":
        motivos.append("risco ALTO exige isolamento.modo='subagentes' (cada assento um agente dedicado); "
                       "'serial' (um agente encenando os papéis) é auto-certificação e está PROIBIDO")
    if (sum(1 for v in votos if v["assento"] == "relator") != 1
            or sum(1 for v in votos if v["assento"] in ASSENTOS) != 4):
        motivos.append("a turma exige exatamente 5 votos: relator + 4 vogais (Mérito, Coerência, Escrita, Conformidade)")
        return _erro(motivos)

    base = [v["voto"] for v in votos]
    unanime = len(set(base)) == 1


    reaberta = any(e.get("tipo") == "reabertura" for e in _eventos(st))
    todos = list(base)
    ids_extra = []
    if not unanime or reaberta:
        art = _d(st.get("art942"))
        extra = [e for e in (art.get("votos_extra") if isinstance(art.get("votos_extra"), list) else [])
                 if isinstance(e, dict) and e.get("voto") in VOTOS and _s(e.get("fundamentacao")) and _id(e.get("agente_id"))]
        if not art.get("acionado") or len(extra) < 2:
            motivos.append("votação NÃO UNÂNIME em ponto relevante (ou apreciação reaberta) exige a "
                           "ampliação do art. 942 CPC: art942.acionado=true + 2 votos_extra (agente_id "
                           "+ voto + fundamentação)")
        else:
            ass = [_s(e.get("assento")) for e in extra[:2]]
            if all(ass) and ass[0] == ass[1]:
                motivos.append(f"ampliacao_ja_votou: os dois votos da ampliação do art. 942 são do "
                               f"mesmo assento ({ass[0]}); cada voto extra é de um assento")
            ids_extra = [_id(e.get("agente_id")) for e in extra[:2]]
            if autor and autor in ids_extra:
                motivos.append("AUTO-CERTIFICAÇÃO na ampliação: autor_id entre os votos do art. 942")
            if len(set(ids + ids_extra)) != len(ids + ids_extra):
                motivos.append("agente_id repetido na ampliação do art. 942")
            todos += [e.get("voto") for e in extra[:2]]



    rotas_prov = {}
    if args.proveniencia:
        _sid = st.get("session_id") if isinstance(st.get("session_id"), str) else None
        try:
            ledger = no_caso(args.proveniencia, _sid or args.session_id)
        except CaminhoRecusado as e:
            motivos.append(f"proveniência não conferida: {e}")
        else:
            _m, rotas_prov = _verificar_proveniencia(ledger, ids + ids_extra, _sid,
                                                     args.transcritos)
            motivos += _m + _correcoes(st, ledger, _sid, args.transcritos,
                                       os.path.abspath(args.status))
            motivos += _ata_confere(st, ledger, args.transcritos, os.path.abspath(args.status))




    estado = os.path.abspath(args.status)
    if not args.proveniencia:
        motivos += _ata_confere(st, estado=estado)
    if args.painel:
        motivos += _verificar_painel(st, estado)




    fase = st.get("fase")
    if fase in ("distribuicao", "debate", "votacao", "apreciacao"):
        motivos.append(f"turma_nao_proclamou: a sessão está na fase '{fase}', sem resultado proclamado; "
                       "registre os votos que faltarem e rode `conselho_sessao.py proclamar`, mostrando o "
                       "painel da decisão, antes de pedir a entrega")

    if motivos:
        return _erro(motivos)

    aprovar, devolver = todos.count("aprovar"), todos.count("devolver")
    placar = f"{aprovar} aprovar × {devolver} devolver (em {len(todos)} votos)"


    contado = "devolvido" if devolver >= aprovar else "aprovado"
    if fase in ("aprovado", "devolvido") and fase != contado:
        return _erro([f"resultado_contra_placar: a turma proclamou '{fase}', mas os votos contados "
                      f"dão {placar}, que é {contado}. A decisão gravada não vale: submeta a peça "
                      f"de novo à turma com `conselho_sessao.py novo-ciclo --state \"{estado}\"`."],
                     1, "resultado_contra_placar")
    if devolver >= aprovar:
        devs = [f"[{v['assento']}] {v['fundamentacao']}" for v in votos if v["voto"] == "devolver"]
        print(json.dumps({"ok": True, "liberado": False, "resultado": "devolvido", "placar": placar,
                          "motivos": ["DEVOLVIDA por maioria — redator corrige e ressubmete (novo ciclo)"] + devs},
                         ensure_ascii=False)); return 1

    bloqueios = versoes_divergentes(st)
    if not lint_ok:
        bloqueios.append(f"lint não APROVADO (resultado={lint.get('resultado')}, exit={lint.get('exit_code')})")
    if pend:
        bloqueios.append(f"{len(pend)} pendência(s) de jurisprudência impede(m) protocolo: {pend}")
    if bloqueios:
        print(json.dumps({"ok": True, "liberado": False, "resultado": "aprovado_mas_bloqueado",
                          "placar": placar, "motivos": bloqueios}, ensure_ascii=False)); return 1


    venc = " (relator vencido)" if _d(st.get("relator")).get("voto") == "devolver" else ""


    por_transcript = sorted(i for i, r in rotas_prov.items() if r == "transcript")
    via = ""
    if por_transcript:
        via = (f"Proveniência por TRANSCRIPT do harness (ledger ausente nesta superfície) em "
               f"{len(por_transcript)} assento(s): {por_transcript}. ")
    acordao = (f"ACÓRDÃO DE ENTREGA — peça «{st['peca']}» APROVADA por maioria: {placar}{venc}. "
               f"LINT APROVADO (exit 0, "
               f"{'reexecutado sobre a peça julgada' if lint.get('reexecutado') is True else 'registrado sem reexecução'}); "
               f"sem pendência de jurisprudência. "
               f"{'Ampliação do art. 942 registrada. ' if ids_extra else ''}{via}"
               f"Minuta liberada para revisão final do advogado responsável.")
    print(json.dumps({"ok": True, "liberado": True, "resultado": "aprovado", "placar": placar,
                      "motivos": [], "acordao": acordao}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
