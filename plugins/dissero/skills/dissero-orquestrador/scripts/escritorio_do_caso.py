#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'escritorio_do_caso.py — de qual escritório é a peça, para o advogado que atua por vários.'






























import argparse
import datetime
import json
import os
import sys

try:
    import caso_raiz
except Exception:
    caso_raiz = None

ARQUIVO = "ESCRITORIO.json"
ENV_ESCRITORIO = "DSR_ESCRITORIO"
ENV_SESSAO = "CLAUDE_CODE_SESSION_ID"
ID_PRINCIPAL = "principal"
MIN_ESCOPO = 10

PERGUNTA = "Para qual escritório é esta peça?"

MSG_NAO_ESCOLHIDO = (
    "ESCRITÓRIO NÃO ESCOLHIDO — pergunte ao advogado com escritorio_do_caso.py pergunta e "
    "registre com escritorio_do_caso.py registrar <id>; para peça sem caso registrado, passe "
    "--escritorio <id>")


def _modulo_perfil(modulo=None):
    if modulo is not None:
        return modulo
    import perfil_advogado
    return perfil_advogado


def _ids(pa, perfil):
    return [e.get("id") for e in pa.escritorios(perfil)]


def _nome_curto(pa, perfil, eid):
    for e in pa.escritorios(perfil):
        if e.get("id") == eid:
            return e.get("nome_curto") or eid
    return eid


def _sessao(session_id=None):
    sid = (session_id or os.environ.get(ENV_SESSAO) or "").strip()
    return sid or None


def raiz_do_caso(cwd=None, session_id=None):
    'Raiz do caso REGISTRADO DESTA SESSÃO, ou None. Vale `DSR_CASO_RAIZ` ou o ponteiro da'



    if caso_raiz is None:
        return None
    sid = _sessao(session_id)
    try:
        raiz, origem = caso_raiz.resolver(cwd=cwd, session_id=sid)
        if origem in ("env", "sessao"):
            return raiz
        if origem == "atual" and sid:
            d = caso_raiz._ler_ponteiro(caso_raiz.caminho_ponteiro_atual()) or {}
            if str(d.get("session_id") or "").strip() == sid:
                return raiz
    except Exception:
        return None
    return None


def ler_registro(raiz):
    """O `ESCRITORIO.json` do caso como dict, ou None (ausente ou ilegível)."""
    if not raiz:
        return None
    try:
        with open(os.path.join(raiz, ARQUIVO), encoding="utf-8") as fh:
            dados = json.load(fh)
    except (OSError, ValueError):
        return None
    return dados if isinstance(dados, dict) and dados.get("escritorio") else None


def _caso_id(raiz):
    try:
        return caso_raiz.ler_caso_id(raiz)
    except Exception:
        return None


def _registro_vale(reg, raiz):
    'O registro é DESTE caso: pasta copiada de outro caso leva o arquivo junto, e o código do'

    gravado = reg.get("caso_id")
    atual = _caso_id(raiz)
    return not (gravado and atual and gravado != atual)


def resolver(perfil, cwd=None, explicito=None, session_id=None, modulo=None):
    """Id do escritório da peça, ou levanta `PerfilError` nomeado (ordem no docstring)."""
    pa = _modulo_perfil(modulo)
    env = (os.environ.get(ENV_ESCRITORIO) or "").strip()
    if not pa.atende_varios(perfil) or len(pa.escritorios(perfil)) < 2:
        if explicito and explicito not in _ids(pa, perfil):
            raise pa.PerfilError(f"ESCRITÓRIO DESCONHECIDO — «{explicito}» não está no perfil. "
                                 f"Este advogado atua por um escritório só: rode sem --escritorio.")
        return ID_PRINCIPAL
    raiz = raiz_do_caso(cwd, session_id)
    reg = ler_registro(raiz)
    if reg and _registro_vale(reg, raiz):
        eid = reg.get("escritorio")
        if eid not in _ids(pa, perfil):
            raise pa.PerfilError(
                f"ESCRITÓRIO DO CASO NÃO EXISTE MAIS — o caso foi registrado para "
                f"«{reg.get('nome_curto') or eid}», que não está mais no perfil. Pergunte ao "
                f"advogado com escritorio_do_caso.py pergunta e troque com escritorio_do_caso.py "
                f"trocar <id> --confirmado --escopo \"<palavras dele>\".")
        pedido = explicito or env
        if pedido and pedido != eid:
            origem = "--escritorio" if explicito else ENV_ESCRITORIO
            raise pa.PerfilError(
                f"ESCRITÓRIO DIFERENTE DO DO CASO — este caso é do escritório "
                f"«{reg.get('nome_curto') or eid}» e {origem} pede "
                f"«{_nome_curto(pa, perfil, pedido)}». Nada foi gerado. Se o advogado quer mesmo "
                f"trocar, com o sim dele: escritorio_do_caso.py trocar {pedido} --confirmado "
                f"--escopo \"<palavras dele>\"; senão, rode sem {origem}.")
        return eid
    if explicito:
        return explicito
    if env:
        return env
    raise pa.PerfilError(MSG_NAO_ESCOLHIDO)




CAMPOS_DO_ESCRITORIO = ("{{ESCRITORIO}}", "{{CIDADE_ASSINATURA}}", "{{LINHA_ENDERECO}}",
                        "{{LINHA_CONTATO}}", "{{EMAIL}}", "{{TELEFONE}}")

_VISUAL_DO_ESCRITORIO = ("layout", "fonte_corpo", "tamanho_corpo_pt", "cor_texto_hex", "timbrado")


def visao_neutra(perfil):
    'Cópia do perfil sem o que é do escritório na identidade visual: o corpo sai no padrão do'

    visao = json.loads(json.dumps(perfil))
    iv = visao.get("identidade_visual")
    if isinstance(iv, dict):
        for chave in _VISUAL_DO_ESCRITORIO:
            iv.pop(chave, None)
    return visao


def visao_sem_recusa(perfil, explicito=None, cwd=None, session_id=None, modulo=None):
    '`(perfil para o corpo, id do escritório ou None)`, sem levantar. Para o FRAGMENTO, que'



    if not isinstance(perfil, dict) or not perfil:
        return perfil, None
    pa = _modulo_perfil(modulo)
    varios = pa.atende_varios(perfil) and len(pa.escritorios(perfil)) >= 2
    if not varios and not explicito and not (os.environ.get(ENV_ESCRITORIO) or "").strip():
        return perfil, ID_PRINCIPAL
    try:
        eid = resolver(perfil, cwd=cwd, explicito=explicito, session_id=session_id, modulo=pa)
        return pa.perfil_do_escritorio(perfil, eid), eid
    except pa.PerfilError:
        return visao_neutra(perfil), None


def texto_da_pergunta(perfil, modulo=None):
    pa = _modulo_perfil(modulo)
    linhas = [PERGUNTA]
    for i, e in enumerate(pa.escritorios(perfil)):
        linhas.append(f"{chr(ord('a') + i)}) {e.get('nome_curto') or e.get('id')}")
    return "\n".join(linhas)


def _gravar(raiz, dados):
    destino = os.path.join(raiz, ARQUIVO)
    tmp = destino + ".novo"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(dados, ensure_ascii=False, indent=2))
    os.replace(tmp, destino)


def _registro(pa, perfil, raiz, eid):
    try:
        cid = caso_raiz.garantir_caso_id(raiz)
    except Exception:
        cid = None
    return {"caso_id": cid, "escritorio": eid, "nome_curto": _nome_curto(pa, perfil, eid),
            "em": datetime.datetime.now().isoformat(timespec="seconds")}


def _recusa(msg):
    print(msg)
    return 1


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Escritório da peça (advogado de vários escritórios).")
    ap.add_argument("acao", choices=("precisa", "pergunta", "registrar", "trocar"))
    ap.add_argument("id", nargs="?")
    ap.add_argument("--session-id")
    ap.add_argument("--confirmado", action="store_true")
    ap.add_argument("--escopo")
    args = ap.parse_args(argv)

    import perfil_advogado as pa
    try:
        perfil = pa.carregar()
    except pa.PerfilError as e:
        return _recusa(f"PERFIL ILEGÍVEL — {e}")

    if args.acao == "precisa":
        if not perfil:
            print("nao")
            return 0
        try:
            eid = resolver(perfil, session_id=args.session_id, modulo=pa)
        except pa.PerfilError as e:
            print("sim")
            print(str(e), file=sys.stderr)
            return 0
        precisa = pa.atende_varios(perfil) and len(pa.escritorios(perfil)) >= 2
        print(eid if precisa else "nao")
        return 0

    if not perfil:
        return _recusa("PERFIL DO ADVOGADO NÃO RESOLVIDO — confira com perfil_advogado.py --status.")

    if args.acao == "pergunta":
        print(texto_da_pergunta(perfil, pa))
        mapa = ", ".join(f"{chr(ord('a') + i)}={e.get('id')}"
                         for i, e in enumerate(pa.escritorios(perfil)))
        print(f"detalhe para o assistente (não repassar): {mapa}", file=sys.stderr)
        return 0

    if not args.id:
        print("uso: escritorio_do_caso.py registrar|trocar <id>")
        return 2
    try:
        pa.perfil_do_escritorio(perfil, args.id)
    except pa.PerfilError as e:
        return _recusa(str(e))
    raiz = raiz_do_caso(session_id=args.session_id)
    if not raiz:
        return _recusa(
            "CASO NÃO REGISTRADO — nada foi gravado. Registre o caso com caso_raiz.py registrar, "
            f"ou, para peça sem caso registrado, passe --escritorio {args.id} ao gerador.")
    atual = ler_registro(raiz)
    if atual and not _registro_vale(atual, raiz):
        atual = None

    if args.acao == "registrar":
        if atual and atual.get("escritorio") != args.id:
            return _recusa(
                f"ESCRITÓRIO JÁ ESCOLHIDO — este caso é do escritório «{atual.get('nome_curto') or atual.get('escritorio')}». "
                f"Para trocar, com o sim do advogado: escritorio_do_caso.py trocar {args.id} "
                f"--confirmado --escopo \"<palavras dele>\".")
        if not atual:
            _gravar(raiz, _registro(pa, perfil, raiz, args.id))
        print(f"escritório do caso: {_nome_curto(pa, perfil, args.id)}")
        return 0


    escopo = (args.escopo or "").strip()
    if not args.confirmado or len(escopo) < MIN_ESCOPO:
        print("TROCA SEM CONFIRMAÇÃO — trocar o escritório do caso pede --confirmado e --escopo com "
              f"as palavras do advogado (ao menos {MIN_ESCOPO} caracteres). Nada foi trocado.")
        return 2
    if not atual:
        return _recusa("NADA A TROCAR — o caso não tem escritório escolhido; use "
                       f"escritorio_do_caso.py registrar {args.id}.")
    de = atual.get("nome_curto") or atual.get("escritorio")
    if atual.get("escritorio") == args.id:
        print(f"o caso já é do escritório {de}: não há o que trocar. Nada foi gravado.")
        return 0
    novo = _registro(pa, perfil, raiz, args.id)
    trocas = atual.get("trocas") if isinstance(atual.get("trocas"), list) else []
    novo["trocas"] = trocas + [{"de": atual.get("escritorio"), "para": args.id,
                                "escopo": escopo, "em": novo["em"]}]
    _gravar(raiz, novo)
    print(f"escritório do caso trocado de {de} para {_nome_curto(pa, perfil, args.id)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
