#!/usr/bin/env python3
"""PRODUTOR do estado do Conselho Revisor; o conselho_gate.py conta e libera. Exit 0 ok, 2 recusa
(`resultado` nomeado); só JSON na última linha."""
import sys, os, json, copy, argparse, time, tempfile
from datetime import datetime, timezone

try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import caso_raiz as _caso_raiz
except Exception:
    _caso_raiz = None

# O MÓDULO-BASE (06/11/2026): as constantes do rito e as funções-folha moram em
# `conselho_sessao_base.py`, ao lado deste. Num arquivo só, o script encostava no teto do conector,
# que recusa script servido maior que ele. Os dois são servidos e selados; `conferir` confere os
# dois. Sem o base, nenhum comando roda e o `conferir` diz o que falta.
try:
    from conselho_sessao_base import *  # noqa: F401,F403
    import conselho_sessao_base as _base
except ImportError:
    _base = None

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# Trava: espera e idade de processo morto (s).
ESPERA, VELHA = 5, 30
_SHELL = []


def _q(c):
    if not any(x in c for x in '$`"'):
        return f'"{c}"'
    if "'" not in c:
        return f"'{c}'"
    _SHELL.append(c)
    return '"<caminho: monte à mão>"'


def _cmd_painel(state):
    state = os.path.abspath(state)
    pasta = os.path.dirname(state)
    return (f'painel_fragmento.py --state {_q(state)} '
            f'--saida {_q(os.path.join(pasta, "painel_fragmento.html"))} '
            f'--documento {_q(os.path.join(pasta, _painel(state)))} --registrar')


def _cmd_sessao(state, subcomando, resto):
    return f'conselho_sessao.py {subcomando} --state {_q(os.path.abspath(state))} {resto}'


def _proximo_passo_painel(state):
    return ("Antes de convocar a turma, mostre o painel da distribuição ao advogado: rode "
            f"`{_cmd_painel(state)}`, mostre-o pela via da superfície (regimento §3 item 4: o CONTEÚDO "
            f"do fragmento no widget, ou o {_painel(state)} enviado como arquivo) e registre com "
            f"`{_cmd_sessao(state, 'exibir', '--fase distribuicao --superficie widget|artifact|arquivo')}`. "
            "Sem isso, nenhum assento se registra.")


def _defasado(state, st, f0, extra, votou=False):
    f = st.get("fase")
    passo = (f"Rode `{_cmd_painel(state)}` e mostre ao advogado pela via da superfície "
             "(regimento §3 item 7).")
    if votou and f == "debate":
        passo += (" O debate não tinha painel emitido, e a fase não virou: rode o PLENÁRIO (não o "
                  f"placar), mostre-o e declare `{_cmd_sessao(state, 'fase', '--fase votacao')}`.")
    extra.update(fase=f, virada=f != f0, painel="defasado", proximo_passo=passo)
    return extra


def _saida(resultado, motivos, exit_code, extra=None):
    payload = {"ok": exit_code == 0, "resultado": resultado, "motivos": list(motivos)}
    if extra:
        payload.update(extra)
    if _SHELL:
        payload["aviso_caminho"] = (f"o caminho «{_SHELL[0]}» tem caracteres que o shell "
                                    "interpreta: monte o comando à mão")
    print(json.dumps(payload, ensure_ascii=False))
    return exit_code


def _ler(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def _lerv(p):
    try:
        return _ler(p)
    except ValueError:
        return None


def _carregar(path):
    if not _full_str(path):
        raise Contrato(["--state (caminho do CONSELHO_STATUS.json) obrigatório"])
    try:
        st = json.loads(_tentar(_ler, path))
    except FileNotFoundError:
        raise Contrato([f"sessão não encontrada em {path}. Se a sessão já existe em outro lugar, "
                        f"passe o caminho completo em --state ou mova o CONSELHO_STATUS.json para a "
                        f"raiz do caso. Se ainda não existe, rode 'abrir'."])
    except Exception as e:
        raise Contrato([f"CONSELHO_STATUS.json ilegível: {e}"])
    if not isinstance(st, dict):
        raise Contrato(["raiz do CONSELHO_STATUS deve ser objeto JSON"])
    return st


def _travar(state):
    if not _full_str(state):
        return None
    t, fim = state + ".lock", time.time() + ESPERA
    while True:
        try:
            fd = os.open(t, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            _velha(t)
        except FileNotFoundError:
            return None
        except PermissionError:
            if os.name != "nt":
                raise
        else:
            meu = json.dumps({"pid": os.getpid(), "em": time.time()})
            try:
                os.write(fd, meu.encode())
            except OSError:
                os.close(fd)
                os.remove(t)
                raise
            os.close(fd)
            return t, meu
        if time.time() > fim:
            raise Contrato([f"o estado {state} está ocupado por outro comando há {ESPERA} s "
                            f"(trava {t}): nada foi gravado. Rode um comando do Conselho por vez; "
                            f"se nenhum outro estiver rodando, a trava é de um comando "
                            f"interrompido e vence sozinha em {VELHA} s: repita depois disso."],
                           "estado_ocupado")
        time.sleep(0.025)


def _velha(t):
    try:
        txt = _lerv(t)
        try:
            em = float(json.loads(txt)["em"])
        except Exception:
            em = os.path.getmtime(t)
        if time.time() - em > VELHA:
            lixo = f"{t}.velha-{os.getpid()}-{time.time_ns()}"
            os.rename(t, lixo)
            if _lerv(lixo) == txt:
                os.remove(lixo)
            else:
                os.rename(lixo, t)
    except (OSError, ValueError):
        pass


def _soltar(trava):
    t, meu = trava
    try:
        if _ler(t) == meu:
            _tentar(os.remove, t)
    except OSError:
        pass


def pasta_do_caso(session_id=None):
    if _caso_raiz is None:
        return None, "sem_caso_raiz"
    try:
        raiz, origem = _caso_raiz.resolver(session_id=session_id)
    except Exception:
        return None, "falha"
    return (raiz, origem) if origem in ("env", "sessao") else (None, origem)


def _resolver_state(path, session_id=None):
    if not _full_str(path) or os.path.dirname(path):
        return path
    raiz, origem = pasta_do_caso(session_id)
    if raiz is None:
        motivo = (f"«{path}» veio sem pasta, e a pasta do caso desta sessão não foi "
                  f"identificada. ")
        if origem == "sem_caso_raiz":
            motivo += "O caso_raiz.py não está ao lado deste script. "
        elif origem == "atual":
            motivo += ("A última pasta registrada pode ser de outra sessão ou de outro caso, e "
                       "não é usada. ")
        motivo += (f"Passe o caminho completo em --state (\"<pasta do caso>/{path}\"). Ou "
                   f"repita o comando com --session-id <id da sessão>, depois de registrar a "
                   f"pasta com `caso_raiz.py registrar --raiz \"<pasta do caso>\" --session-id "
                   f"<id da sessão>`. Sem pasta do caso conectada, use uma pasta de trabalho pelo "
                   f"caminho completo e declare a entrega por download, com o "
                   f"CONSELHO_STATUS.json e o PAINEL_CONSELHO.html junto do .docx.")
        raise Contrato([motivo], "caso_nao_resolvido")
    no_raiz = os.path.join(raiz, path)
    try:
        dois = (os.path.isfile(no_raiz) and os.path.isfile(path)
                and not os.path.samefile(no_raiz, path))
    except OSError:
        dois = True
    if dois:
        raise Contrato([
            f"«{path}» existe na pasta corrente ({os.path.abspath(path)}) e na pasta do caso "
            f"({no_raiz}), como arquivos diferentes. Passe o caminho completo da sessão desta "
            f"turma em --state."], "caminho_ambiguo")
    return no_raiz


def _gravar(path, st):
    _snapshot(st)
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(".tmp", ".CONSELHO_", os.path.dirname(os.path.abspath(path)))
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(st, ensure_ascii=False, indent=2))
            f.flush()
            os.fsync(f.fileno())
        _tentar(os.replace, tmp, path)
        tmp = None
    except OSError as e:
        raise Contrato([f"a gravação de {path} falhou ({e}): nada foi gravado, e o arquivo "
                        f"anterior está intacto. Libere espaço ou permissão e repita."], "gravacao_falhou")
    finally:
        if tmp:
            try:
                os.remove(tmp)
            except OSError:
                pass


def _agora():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _inst(ts):
    if not _full_str(ts):
        return _agora()
    try:
        d = datetime.fromisoformat(ts.strip().replace("Z", "+00:00"))
        if ts.strip()[10:11] not in ("T", " "):
            raise ValueError
    except ValueError:
        raise Contrato([f"--ts '{ts}' não é data e hora ISO 8601 (ex.: 2026-10-27T10:33:00-03:00)"],
                       "ts_invalido")
    return (d if d.tzinfo else d.astimezone()).isoformat(timespec="seconds")


def _evento(st, quem, texto, ts, **k):
    if not _full_str(texto):
        return
    em = _inst(ts)
    st.setdefault("eventos", []).append({"hora": em[11:16], "quem": quem, "texto": texto.strip(),
                                         "em": em, **k})


def _toca(st, ts):
    st["atualizado"] = _inst(ts)


def _mexe(st, args):
    """Antes do movimento: aviso de lote e virada (para o debate e para a votação)."""
    lote = _lote(st) if args.voto is not None else []
    if _movimento(args) and st.get("fase") == "distribuicao" and "distribuicao" in _fases(st, "emissoes"):
        st["fase"] = "debate"
        _evento(st, "Relator", "Fase: Debate", args.ts)
    if args.voto is not None and st.get("fase") == "debate" and not _falta(st, "debate"):
        st["fase"] = "votacao"
        _evento(st, "Relator", "Fase: Votação", args.ts)
    return lote


def _recusa_se_proclamada(st, state, quem, reab=0):
    """Proclamada (com `reab`, também uma vez, na apreciação reaberta), nada entra."""
    f = st.get("fase")
    if f in RESULTADOS or reab and _ult(st, "reabertura"):
        raise Contrato([f"a turma já proclamou ({f}), e {quem} não entra. Nada a refazer: emita e "
                        f"mostre a decisão" + (". A decisão está tomada: voto, fase e ampliação "
                        "tardios não entram." if f == "aprovado" else "; a ressubmissão é o ciclo seguinte, "
                        f"`{_cmd_sessao(state, 'novo-ciclo', '').rstrip()}`.")], "turma_ja_proclamou")


def cmd_novo_ciclo(args):
    st = _carregar(args.state)
    atual = st.get("ciclo")
    novo = args.ciclo if args.ciclo is not None else ((atual + 1) if _is_int(atual) else 2)
    if not _is_int(novo) or novo < 1:
        raise Contrato(["--ciclo deve ser inteiro >= 1"])
    if _is_int(atual) and novo <= atual:
        raise Contrato([f"--ciclo {novo} não avança: a sessão está no ciclo {atual}"])
    if st.get("fase") not in ("aprovado", "devolvido"):
        raise Contrato([f"o ciclo {atual} não foi proclamado (fase '{st.get('fase')}') — "
                        f"proclame antes de abrir o ciclo seguinte, senão o arquivo guarda "
                        f"uma deliberação pela metade"])
    if args.session_id is not None and not _full_str(args.session_id):
        raise Contrato(["--session-id não pode ser vazio"])
    ciclos = _arquivar_ciclo(st)
    peca = args.peca if _full_str(getattr(args, "peca", None)) else st.get("peca")
    novo_st = _estado_inicial(peca, st.get("risco"), novo, st.get("autor_id"),
                              st.get("isolamento", {}))
    novo_st["ciclos"] = ciclos
    for k in ("session_id", "perfil_modelo", "modelo_autor_pedido"):
        if st.get(k):
            novo_st[k] = st[k]
    if args.session_id is not None:
        novo_st["session_id"] = args.session_id.strip()
    _toca(novo_st, args.ts)
    _evento(novo_st, "Relator",
            f"Ciclo {novo} aberto — ciclo {atual} arquivado ({st.get('fase')}"
            + (f", {(st.get('relator') or {}).get('placar')}" if (st.get("relator") or {}).get("placar") else "")
            + ").", args.ts)
    _gravar(args.state, novo_st)
    return _saida("ciclo_aberto", [f"ciclo {atual} arquivado; ciclo {novo} aberto em {args.state}"], 0,
                  extra={"ciclo": novo, "ciclos_arquivados": len(ciclos), "fase": "distribuicao",
                         "proximo_passo": _proximo_passo_painel(args.state)})


def _recusa_se_dispensado(st, state, quem):
    if st.get("conselho_dispensado") is not True:
        return
    resto = (f'--peca "{st.get("peca")}" --risco {st.get("risco")} --autor-id '
             f'"{st.get("autor_id")}"'
             + (f' --session-id "{st["session_id"]}"' if _full_str(st.get("session_id")) else ""))
    raise Contrato([
        f"o conselho foi dispensado nesta sessão, e {quem} não se registra depois da dispensa. "
        f"Para a turma deliberar, abra a sessão de novo sem a dispensa: remova "
        f"{_q(os.path.abspath(state))} e rode `{_cmd_sessao(state, 'abrir', resto)}`."])


def cmd_dispensar(args):
    st = _carregar(args.state)
    if st.get("risco") != "baixo":
        raise Contrato([f"o conselho só se dispensa em peça de risco baixo, e esta sessão é de "
                        f"risco '{st.get('risco')}'. Em risco alto, a turma delibera."])
    if not _full_str(args.justificativa):
        raise Contrato(["--justificativa obrigatória: diga por que o risco da peça é baixo"])
    for c in [*_d(st, "ciclos", list), st]:
        if isinstance(c, dict) and _deliberou(c):
            raise Contrato([f"a turma já votou ou devolveu a peça no ciclo {c.get('ciclo')}, e "
                            f"isso não se apaga com a dispensa: o ciclo {st.get('ciclo')} segue "
                            f"com a turma até a proclamação, e a ressubmissão volta a ela."])
    st["conselho_dispensado"] = True
    st["conselho_dispensado_justificativa"] = args.justificativa.strip()
    _toca(st, args.ts)
    _gravar(args.state, st)
    return _saida("conselho_dispensado", [f"dispensa registrada em {args.state}"], 0,
                  extra={"justificativa": st["conselho_dispensado_justificativa"]})


def cmd_abrir(args):
    if args.risco not in RISCOS:
        raise Contrato([f"--risco deve ser um de {RISCOS}"])
    if args.modo not in MODOS or (args.risco, args.modo) == ("alto", "serial"):
        raise Contrato([f"--modo deve ser um de {MODOS}; em risco alto, 'subagentes' (no 'serial' "
                        f"um agente encena a turma)"])
    if not _full_str(args.peca):
        raise Contrato(["--peca (string não-vazia) obrigatória"])
    if not _full_str(args.autor_id):
        raise Contrato(["--autor-id obrigatório (agente que redigiu a peça; anti auto-certificação)"])
    ciclo = args.ciclo if args.ciclo is not None else 1
    if not _is_int(ciclo) or ciclo < 1:
        raise Contrato(["--ciclo deve ser inteiro >= 1"])
    if args.session_id is not None and not _full_str(args.session_id):
        raise Contrato(["--session-id não pode ser vazio"])
    if args.perfil is not None and (not _full_str(args.perfil) or args.perfil.strip() not in PERFIS):
        raise Contrato([f"--perfil deve ser um de {PERFIS} (ver dissero-orquestrador/references/perfis_modelo.json)"])
    modelo_autor = _modelo(args.modelo_autor, "--modelo-autor")
    if os.path.basename(args.state).lower() == "peca_state.json":
        raise Contrato([
            f"{args.state} é o PECA_STATE da peça, não a sessão do conselho, e `abrir` o apagaria. O "
            f"`--state` do conselho é o CONSELHO_STATUS.json do caso; o PECA_STATE.json entra só como "
            f"`--peca-state`."], "state_nao_e_do_conselho")
    if os.path.exists(args.state):
        try:
            antigo = json.loads(open(args.state, encoding="utf-8").read())
        except Exception:
            antigo = None
        # 09/11/2026 (achado D): `--state` do conselho apontado para o PECA_STATE gravava a sessão
        # por cima dele, em silêncio, e apagava o rito. O `--state` daqui é o CONSELHO_STATUS.json;
        # o PECA_STATE é o `--peca-state`. Arquivo existente que não é sessão do conselho não se
        # sobrescreve.
        if (antigo is not None and not (isinstance(antigo, dict) and "cadeiras" in antigo)) or (
                isinstance(antigo, dict) and ("fases" in antigo or "modo_execucao" in antigo)):
            raise Contrato([
                f"{args.state} não é sessão do conselho, e `abrir` o apagaria. O `--state` do "
                f"conselho é o CONSELHO_STATUS.json do caso; o PECA_STATE.json entra só como "
                f"`--peca-state`. Abra a sessão num CONSELHO_STATUS.json novo."], "state_nao_e_do_conselho")
        if isinstance(antigo, dict) and antigo.get("cadeiras") is not None:
            raise Contrato([
                f"já existe sessão em {args.state} (ciclo {antigo.get('ciclo')}, "
                f"fase '{antigo.get('fase')}') — `abrir` a APAGARIA. Para o ciclo seguinte use "
                f"`{_cmd_sessao(args.state, 'novo-ciclo', '--ciclo ' + str((antigo.get('ciclo') or 1) + 1))}`, que "
                f"arquiva o anterior em 'ciclos'. Para recomeçar do zero, remova o arquivo à mão."])
    st = _estado_inicial(args.peca, args.risco, ciclo, args.autor_id, {"modo": args.modo})
    if args.session_id:
        st["session_id"] = args.session_id.strip()
    if args.perfil:
        st["perfil_modelo"] = args.perfil.strip()
    if modelo_autor:
        st["modelo_autor_pedido"] = modelo_autor
    _toca(st, args.ts)
    _evento(st, "Relator", f"Sessão aberta — distribuição da peça '{args.peca}' (risco {args.risco}).", args.ts)
    _gravar(args.state, st)
    extra = {"fase": "distribuicao", "cadeiras": len(CADEIRAS), "state": args.state,
             "proximo_passo": _proximo_passo_painel(args.state)}
    return _saida("aberta", [f"sessão criada em {args.state}"], 0, extra=extra)


def _exige_distribuicao_exibida(st, quem, state):
    if "distribuicao" not in _fases(st, "exibicoes"):
        raise Contrato([f"o painel da distribuição não foi EXIBIDO ao advogado, e {quem} não se "
                        f"registra antes disso. " + _proximo_passo_painel(state)])


def _prov(f, *a):
    try:
        import conselho_gate
        return getattr(conselho_gate, f)(*a)
    except Exception:
        return None


def _assento(st, args, s):
    """Sem voto, o redespacho; com voto, antes da proclamação, a correção do id (o voto não muda)."""
    aid, a = args.agente_id, s.get("id") or "relator"
    if not _full_str(aid):
        raise Contrato(["--agente-id não pode ser vazio"])
    aid, ant, nome = aid.strip(), str(s.get("agente_id") or "").strip(), NOMES.get(a, "Relator")
    if aid != ant:
        if s.get("voto") in VOTOS:
            _recusa_se_proclamada(st, args.state, f"a troca de agente ({nome})", 1)
            p = _prov("provado", st, args.state, ant)
            if p is not False or _prov("conferivel", st, args.state) is not True:
                raise Contrato([f"{nome} votou como '{ant}', " + ("que tem proveniência real: o voto "
                                "é dele" if p else "e a proveniência não se confere aqui: falta o "
                                "conselho_gate.py ao lado, o registro do harness ou o transcript")],
                               "assento_ja_votou" if p else "proveniencia_nao_conferida")
            if args.voto or args.status or args.fundamentacao:
                raise Contrato([f"a correção do id não muda voto nem andamento: só --agente-id"])
            _evento(st, nome, f"{nome}: id do agente corrigido, de {ant} para {aid}; o voto não muda",
                    args.ts, tipo="correcao_de_agente", assento=a, agente_anterior=ant, agente_novo=aid)
        elif not ant:
            _exige_distribuicao_exibida(st, nome, args.state)
    _livre(st, aid, s)
    s["agente_id"] = aid


def _revisao(st, s, args):
    """Art. 942, § 2º: na apreciação reaberta, quem votou revê o voto (vale o último)."""
    if args.voto is None:
        return {}
    a, k = s.get("id") or "relator", {"agente": s.get("agente_id")}
    k["assento"] = a
    if _votou(s) and args.voto != s["voto"] and _ult(st, "reabertura"):
        if not args.agente_id or _prov("ativo", st, args.state, s) is not True:
            raise Contrato([f"a revisão é de quem votou: --agente-id '{s['agente_id']}', com trabalho "
                            f"dele depois da reabertura no registro ou no transcript"], "revisao_sem_autoria")
        s["voto_anterior"] = s["voto"]
        k.update(tipo="revisao_de_voto", voto_anterior=s["voto"], voto=args.voto)
    return k


def cmd_cadeira(args):
    st = _carregar(args.state)
    f0 = st.get("fase")
    if args.id not in CADEIRAS:
        raise Contrato([f"--id deve ser um de {CADEIRAS}"])
    _recusa_se_dispensado(st, args.state, f"a cadeira '{args.id}'")
    c = _acha_cadeira(st, args.id)
    modelo = _modelo(args.modelo)
    if args.status is not None and args.status not in ST_CADEIRA:
        raise Contrato([f"--status deve ser um de {ST_CADEIRA}"])
    _status_final(args)
    if modelo:
        c["modelo_pedido"] = modelo
    if args.agente_id is not None:
        _assento(st, args, c)
    if args.voto is not None:
        _recusa_se_proclamada(st, args.state, f"o voto da cadeira '{args.id}'")
        if args.voto not in VOTOS:
            raise Contrato([f"--voto deve ser um de {VOTOS}"])
        if not _full_str(args.fundamentacao):
            raise Contrato(["--voto exige --fundamentacao não-vazia (voto sem fundamento não conta)"])
        if not _full_str(c.get("agente_id")):
            raise Contrato([f"cadeira '{args.id}' sem agente_id — atribua --agente-id antes de votar (proveniência)"])
    lote, rev = _mexe(st, args), _revisao(st, c, args)
    if args.voto is not None:
        c.update(voto=args.voto, fundamentacao=args.fundamentacao.strip(), status="votou",
                 registrado_em=_agora(), docx_sha256=_prov("hash_julgado", st, args.state))
    elif args.status is not None:
        c["status"] = args.status
        if _full_str(args.fundamentacao):
            c["argumento_debate"] = args.fundamentacao.strip()
    _toca(st, args.ts)
    _evento(st, NOMES[args.id], _ata(NOMES[args.id], args, rev), args.ts, **rev)
    _gravar(args.state, st)
    return _saida("cadeira_atualizada", [], 0, extra=_defasado(args.state, st, f0, {
        "id": args.id, "status": c["status"], "voto": c["voto"],
        "avisos": (_prov("aviso_proveniencia", st, args.state, args.agente_id) or []) + lote},
        args.voto))


def cmd_relator(args):
    st = _carregar(args.state)
    f0 = st.get("fase")
    _recusa_se_dispensado(st, args.state, "o relator")
    r = st.setdefault("relator", {})
    modelo = _modelo(args.modelo)
    if modelo:
        r["modelo_pedido"] = modelo
    if args.agente_id is not None:
        _assento(st, args, r)
    if args.voto is not None:
        _recusa_se_proclamada(st, args.state, "o voto do relator")
        if args.voto not in VOTOS:
            raise Contrato([f"--voto deve ser um de {VOTOS}"])
        if not _full_str(args.fundamentacao):
            raise Contrato(["--voto do relator exige --fundamentacao não-vazia"])
        if not _full_str(r.get("agente_id")):
            raise Contrato(["relator sem agente_id — atribua --agente-id antes de votar"])
    if args.status is not None and args.status not in ST_RELATOR:
        raise Contrato([f"--status do relator deve ser um de {ST_RELATOR}"])
    _status_final(args)
    lote, rev = _mexe(st, args), _revisao(st, r, args)
    if args.voto is not None:
        r.update(voto=args.voto, fundamentacao=args.fundamentacao.strip(), status="decidiu",
                 registrado_em=_agora(), docx_sha256=_prov("hash_julgado", st, args.state))
    elif args.status is not None:
        r["status"] = args.status
    _toca(st, args.ts)
    _evento(st, "Relator", _ata("Relator", args, rev), args.ts, **rev)
    _gravar(args.state, st)
    return _saida("relator_atualizado", [], 0, extra=_defasado(args.state, st, f0, {
        "status": r.get("status"), "voto": r.get("voto"),
        "avisos": (_prov("aviso_proveniencia", st, args.state, args.agente_id) or []) + lote},
        args.voto))


def _exige_painel_emitido(st, quem, state):
    if st.get("risco") != "alto":
        return
    atual = _stepkey(str(st.get("fase", "")).strip())
    falta = _falta(st, atual)
    if falta:
        raise Contrato([f"painel da fase '{atual}' {falta}, e {quem} sai dela. Rode "
                        f"`{_cmd_painel(state)}`, mostre ao advogado e repita."],
                       "painel_defasado" if falta[0] == "d" else "painel_nao_emitido")


def cmd_fase(args):
    st = _carregar(args.state)
    f0 = st.get("fase")
    if args.fase not in FASES:
        raise Contrato([f"--fase deve ser um de {FASES} (para o resultado final use 'proclamar')"])
    _recusa_se_proclamada(st, args.state, f"a fase '{args.fase}'")
    mudou = _stepkey(str(f0 or "").strip()) != _stepkey(args.fase)
    if mudou:
        _exige_painel_emitido(st, f"a virada para '{args.fase}'", args.state)
    st["fase"] = args.fase
    _toca(st, args.ts)
    _evento(st, "Relator", args.evento or ("Fase: " + ROTULOS[args.fase] if mudou else ""), args.ts)
    _gravar(args.state, st)
    return _saida("fase_atualizada", [], 0, extra=_defasado(args.state, st, f0, {}))


def cmd_lint(args):
    """O lint_peca.py REEXECUTADO sobre a peça julgada (conselho_gate.lint_real), nunca o relatado."""
    st = _carregar(args.state)
    r = _prov("lint_real", st, args.state, args) or {"codigo": "lint_nao_reexecutado",
                                                      "recusa": "falta o conselho_gate.py ao lado"}
    if "lint" not in r:
        raise Contrato([r["recusa"]], r["codigo"])
    st["lint"] = r["lint"]
    _toca(st, args.ts)
    _gravar(args.state, st)
    return _saida("lint_registrado", [], 0, extra={k: r["lint"][k] for k in ("resultado", "exit_code", "docx")})


def cmd_art942(args):
    """Sem voto, convoca; o voto vai a `votos_extra`. Reabre o estado antigo (`reabre`)."""
    st = _carregar(args.state)
    f0 = st.get("fase")
    _recusa_se_dispensado(st, args.state, "o voto da ampliação do art. 942")
    if _prov("reabre", st) is not True:
        _recusa_se_proclamada(st, args.state, "a ampliação do art. 942")
    if args.voto is None:
        if args.status != "analisando":
            raise Contrato(["sem --voto, o art942 registra a convocação do assento: --status analisando"])
    elif args.voto not in VOTOS:
        raise Contrato([f"--voto deve ser um de {VOTOS}"])
    elif not _full_str(args.fundamentacao):
        raise Contrato(["--voto do art. 942 exige --fundamentacao não-vazia"])
    modelo = _modelo(args.modelo)
    if not _full_str(args.agente_id):
        raise Contrato(["--agente-id obrigatório (proveniência do voto da ampliação)"])
    if not _full_str(args.assento):
        raise Contrato(["--assento obrigatório (rótulo do assento da ampliação, ex.: vogal5)"])
    a, aid = args.assento.strip(), args.agente_id.strip()
    art = st.setdefault("art942", {"acionado": True, "motivo": "", "novos": [], "votos_extra": []})
    art["acionado"] = True
    extras = art.setdefault("votos_extra", [])
    if a in [x.get("assento") for x in extras if isinstance(x, dict)]:
        raise Contrato([f"o assento {a} já votou na ampliação"], "ampliacao_ja_votou")
    art["convocados"] = conv = [x for x in art.get("convocados") or [] if isinstance(x, dict)
                                and x.get("assento") != a]
    _livre(st, aid)
    if len(extras) + len(conv) >= 2:
        raise Contrato(["a ampliação do art. 942 comporta 2 votos extras; já há 2 assentos registrados"])
    lote = _lote(st) if args.voto else []
    novos = art.setdefault("novos", [])
    if a not in novos:
        novos.append(a)
    quem = f"Art. 942 ({novos.index(a) + 1})"
    if args.voto:
        x = {"assento": a, "agente_id": aid, "voto": args.voto,
             "fundamentacao": args.fundamentacao.strip(), "registrado_em": _agora(),
             "docx_sha256": _prov("hash_julgado", st, args.state)}
        extras.append(x)
    else:
        x = {"assento": a, "agente_id": aid, "status": "analisando", "convocado_em": _agora()}
        conv.append(x)
    if modelo:
        x["modelo_pedido"] = modelo
    _toca(st, args.ts)
    if st.get("fase") in RESULTADOS:
        st["fase"] = "apreciacao"
        st.setdefault("relator", {}).update(placar="", status="apreciando")
        b = st.get("painel")
        for k in ("emissoes", "exibicoes"):
            if isinstance(b, dict) and k in b:
                b[k] = [e for e in _lista(st, k) if _p(e) != "fim"]
        _evento(st, "Relator", "Ampliação do art. 942: a apreciação é reaberta", None,
                tipo="reabertura")
    _evento(st, quem, _ata(quem, args) if args.evento or not args.voto
            else f"Voto da ampliação (art. 942): {args.voto.upper()}", args.ts)
    _gravar(args.state, st)
    return _saida("art942_registrado", [], 0, extra=_defasado(args.state, st, f0, {
        "assento": a, "voto": args.voto, "votos_extra": len(extras), "convocados": len(conv),
        "avisos": (_prov("aviso_proveniencia", st, args.state, aid) or []) + lote}))


def cmd_proclamar(args):
    st = _carregar(args.state)
    f0 = st.get("fase")
    _recusa_se_dispensado(st, args.state, "a proclamação")
    _recusa_se_proclamada(st, args.state, "outra proclamação")
    if args.resultado not in RESULTADOS:
        raise Contrato([f"--resultado deve ser um de {RESULTADOS}"])
    r = st.setdefault("relator", {})
    cad = {c.get("id"): c for c in st.get("cadeiras", []) if isinstance(c, dict)}
    falta = [NOMES[k] for k in CADEIRAS if not _votou(cad.get(k))] + ([] if _votou(r) else ["Relator"])
    if falta:
        raise Contrato([f"a turma não votou inteira: falta o voto de {', '.join(falta)}. Espere o "
                        f"retorno desses assentos e registre e mostre cada voto quando chegar; só "
                        f"então proclame. Se um não voltar, redespache-o e diga isso ao advogado: `"
                        + _cmd_sessao(args.state, "cadeira", "--id <assento> --agente-id <novo id> "
                                      "--status analisando") + "`."], "turma_incompleta")
    art = _d(st, "art942")
    ext = [e for e in art.get("votos_extra") or [] if _votou(e)]
    vs = [cad[k]["voto"] for k in CADEIRAS] + [r["voto"]]
    if len(set(vs)) > 1 or _ult(st, "reabertura"):
        if not art.get("acionado") or len(ext) < 2:
            livre = "vogal6" if "vogal5" in (art.get("novos") or []) else "vogal5"
            raise Contrato([f"votação não unânime ou reaberta: o art. 942 pede a ampliação, com dois votos, antes "
                            f"da proclamação ({len(ext)} registrado(s)). Convoque cada assento "
                            f"(`{_cmd_sessao(args.state, 'art942', f'--assento {livre} --agente-id <id> --status analisando')}`), "
                            f"registre e mostre cada voto quando chegar e proclame."], "ampliacao_pendente")
        vs += [e["voto"] for e in ext[:2]]
    apro, dev = vs.count("aprovar"), vs.count("devolver")
    certo = RESULTADOS[dev >= apro]
    if args.resultado != certo:
        raise Contrato([f"os votos contados dão {apro}×{dev}: a turma proclama {certo}, não "
                        f"{args.resultado}. Proclame com "
                        f"`{_cmd_sessao(args.state, 'proclamar', '--resultado ' + certo)}`."],
                       "resultado_contra_placar")
    if st.get("fase") != "apreciacao":
        raise Contrato([f"proclama-se da fase 'apreciacao' (está em '{st.get('fase')}'): declare-a com "
                        f"`{_cmd_sessao(args.state, 'fase', '--fase apreciacao')}`, emita e mostre o painel e proclame."])
    _exige_painel_emitido(st, "a proclamação", args.state)
    r.update(status="decidiu", placar=f"{apro}×{dev}", vencido=r["voto"] != VOTOS[dev >= apro])
    _toca(st, args.ts)
    st["fase"] = args.resultado
    _evento(st, "Relator", args.evento if _full_str(args.evento) else (
        f"Resultado proclamado por maioria: {args.resultado.upper()} (placar {r['placar']})."), args.ts,
        tipo="proclamacao")
    _gravar(args.state, st)
    return _saida("proclamado", [], 0, extra=_defasado(args.state, st, f0, {"placar": r["placar"]}))


def cmd_exibir(args):
    st = _carregar(args.state)
    if args.superficie not in SUPERFICIES_EXIBICAO:
        raise Contrato([f"--superficie deve ser um de {SUPERFICIES_EXIBICAO} (sem widget, envie o "
                        f"{_painel(args.state)} ao advogado como arquivo e use 'arquivo'; "
                        f"'artifact' é o live artifact do Cowork)"])
    if not _full_str(args.fase):
        raise Contrato(["--fase obrigatória (a exibição é POR FASE, nunca só no fim)"])
    passo = _stepkey(args.fase.strip())
    if passo not in PASSOS:
        raise Contrato([f"--fase desconhecida: '{args.fase}' — use uma de {FASES} "
                        f"ou o resultado ('aprovado'/'devolvido', que cobrem o passo 'fim')"])
    if passo not in _d(st, "historico"):
        raise Contrato([f"fase '{passo}' NÃO ABERTA nesta sessão — declare-a com "
                        f"`{_cmd_sessao(args.state, 'fase', '--fase ' + args.fase.strip())}` "
                        f"antes de exibir; "
                        f"exibição de fase que a turma não virou seria registro de uma tela que "
                        f"não existiu"])
    bloco = st.setdefault("painel", {})
    if not isinstance(bloco, dict):
        raise Contrato(["'painel' no CONSELHO_STATUS.json deve ser objeto"])
    falta = _falta(st, passo)
    if falta == "não EMITIDO":
        raise Contrato([f"fase '{passo}' sem painel EMITIDO — rode `{_cmd_painel(args.state)}` "
                        f"antes de mostrar. Não se declara exibição de painel que não foi "
                        f"produzido"], "painel_nao_emitido")
    if falta and passo in (_stepkey(st.get("fase")), "fim"):
        raise Contrato([f"o painel da fase '{passo}' está {falta}, e o advogado veria outro "
                        f"estado. Rode `{_cmd_painel(args.state)}`, mostre-o e declare de novo."],
                       "painel_defasado")
    primeira = passo not in _fases(st, "exibicoes")
    exibicoes = bloco.get("exibicoes")
    if not isinstance(exibicoes, list):
        exibicoes = []
    reg = {"fase": passo, "superficie": args.superficie, "em": _inst(args.ts)}
    if _full_str(args.detalhe):
        reg["detalhe"] = args.detalhe.strip()
    for i, e in enumerate(exibicoes):
        if isinstance(e, dict) and _p(e) == passo:
            exibicoes[i] = reg
            break
    else:
        exibicoes.append(reg)
    bloco["exibicoes"] = exibicoes
    _toca(st, args.ts)
    if primeira:
        _evento(st, "Relator",
                f"Painel da fase '{passo}' exibido ao advogado ({args.superficie}).", args.ts)
    _gravar(args.state, st)
    return _saida("exibicao_registrada", [], 0,
                  extra={"fase": passo, "superficie": args.superficie,
                         "exibicoes": len(exibicoes)})


SELO_PREFIXO = "# selo dsr: sha256="


def selo_de(texto):
    """(declarado, medido): sha256 de tudo acima da última linha, em LF (`build/selar_scripts.py`)."""
    import hashlib
    linhas = texto.replace("\r\n", "\n").split("\n")
    while linhas and linhas[-1] == "":
        linhas.pop()
    if not linhas or not linhas[-1].startswith(SELO_PREFIXO):
        return None, hashlib.sha256(("\n".join(linhas) + "\n").encode("utf-8")).hexdigest()
    corpo = "\n".join(linhas[:-1]) + "\n"
    return linhas[-1][len(SELO_PREFIXO):].strip(), hashlib.sha256(corpo.encode("utf-8")).hexdigest()


def cmd_conferir(args):
    caminho = os.path.abspath(__file__)
    try:
        texto = open(caminho, encoding="utf-8").read()
    except Exception as e:
        return _saida("ilegivel", [f"nao consegui ler {caminho}: {e}"], 2)
    declarado, medido = selo_de(texto)
    if declarado is None:
        return _saida("sem_selo", [f"{caminho} nao termina com o selo: copia truncada ou anterior "
                                   f"a ele. Carregue o script de novo e grave-o inteiro."], 2,
                      extra={"sha256": medido})
    if declarado != medido:
        return _saida("selo_divergente", [f"{caminho} difere do publicado: copia alterada ou "
                                          f"truncada. Carregue o script de novo e grave-o tal e "
                                          f"qual, sem editar nada."], 2,
                      extra={"sha256": medido, "selo": declarado})
    pasta = os.path.dirname(caminho)
    base = os.path.join(pasta, "conselho_sessao_base.py")
    if _base is None or not os.path.isfile(base):
        return _saida("sem_modulo_base", [f"{caminho} está íntegro, mas o conselho_sessao_base.py "
                                          f"não está ao lado dele. Carregue-o pelo conector (mesma "
                                          f"pasta scripts/ da skill, nome conselho_sessao_base.py), "
                                          f"grave-o inteiro e tal e qual em {pasta} e rode conferir "
                                          f"de novo."], 2, extra={"sha256": medido, "arquivo": caminho})
    try:
        declarado_b, medido_b = selo_de(open(base, encoding="utf-8").read())
    except Exception as e:
        return _saida("ilegivel", [f"nao consegui ler {base}: {e}"], 2)
    if declarado_b is None or declarado_b != medido_b:
        return _saida("selo_divergente" if declarado_b else "sem_selo",
                      [f"{base} difere do publicado ou não termina com o selo: cópia alterada ou "
                       f"truncada. Carregue-o de novo e grave-o tal e qual, sem editar nada."], 2,
                      extra={"sha256": medido_b, "selo": declarado_b, "arquivo": base})
    if _caso_raiz is None or not hasattr(_caso_raiz, "resolver"):
        return _saida("sem_caso_raiz", [f"{caminho} está íntegro, mas o caso_raiz.py não está ao "
                                        f"lado dele. Copie o caso_raiz.py da pasta scripts/ da "
                                        f"skill (a mesma de onde rodam o painel_fragmento.py e o "
                                        f"conselho_gate.py) para {pasta} e rode conferir de "
                                        f"novo."], 2,
                      extra={"sha256": medido, "arquivo": caminho})
    return _saida("integro", [], 0, extra={"sha256": medido, "arquivo": caminho})


def main():
    ap = argparse.ArgumentParser(description="Produtor de estado incremental do Conselho Revisor (Dissero)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("conferir")
    p = {}
    for n in ("abrir", "novo-ciclo", "dispensar", "cadeira", "relator", "fase", "lint", "art942",
              "proclamar", "exibir"):
        p[n] = sub.add_parser(n)
        p[n].add_argument("--state", default="CONSELHO_STATUS.json")
        p[n].add_argument("--session-id")
        p[n].add_argument("--ts")

    def opc(n, *nomes, **kw):
        for o in nomes:
            p[n].add_argument("--" + o, **kw)
    opc("abrir", "peca", "risco", "autor-id", required=True)
    opc("abrir", "perfil", "modelo-autor")
    opc("abrir", "modo", default="subagentes")
    opc("abrir", "ciclo", type=int)
    opc("novo-ciclo", "ciclo", type=int)
    opc("novo-ciclo", "peca")
    opc("dispensar", "justificativa", default="")
    for n in ("cadeira", "relator", "art942"):
        opc(n, "agente-id", "status", "voto", "fundamentacao", "modelo", "evento")
    opc("cadeira", "id", required=True)
    opc("art942", "assento")
    opc("fase", "fase", required=True)
    opc("fase", "evento")
    opc("lint", "resultado", "peca-state")
    opc("lint", "exit-code", type=int)
    opc("proclamar", "resultado", required=True)
    opc("proclamar", "evento")
    opc("exibir", "superficie", "fase", required=True)
    opc("exibir", "detalhe")

    args = ap.parse_args()
    _SHELL.clear()
    if args.cmd == "conferir":
        return cmd_conferir(args)
    if _base is None:
        return _saida("sem_modulo_base", ["o conselho_sessao_base.py não está ao lado deste script: "
                                          "rode conferir, que diz de onde trazê-lo. Nada foi gravado."], 2)
    trava = None
    try:
        args.ts = _inst(args.ts)
        args.state = _resolver_state(args.state, args.session_id)
        trava = _travar(args.state)
        return globals()["cmd_" + args.cmd.replace("-", "_")](args)
    except Contrato as e:
        return _saida(e.args[1] if len(e.args) > 1 else "contrato_invalido", e.args[0], 2)
    except OSError as e:
        return _saida("gravacao_falhou", [f"falha de disco ao travar ou gravar {args.state} ({e}): "
                                          f"nada foi gravado."], 2)
    finally:
        if trava:
            _soltar(trava)


if __name__ == "__main__":
    sys.exit(main())
# selo dsr: sha256=729887a62c177f883180468e83f74f6c4cf4f13779faf155b37139a18d51b4a1
