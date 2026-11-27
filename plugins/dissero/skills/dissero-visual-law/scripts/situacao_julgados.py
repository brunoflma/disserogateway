#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'Situação dos julgados na banca: a consulta assinada que a ENTREGA exige, além do selo.'


















































from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import sys
from datetime import datetime, timedelta, timezone

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)

import recibo_conferencia as rc
import ed25519_verificar

try:
    import caso_raiz as _caso_raiz
except Exception:
    _caso_raiz = None

TIPO_SITUACAO = "dsr.conferencia.situacao.v1"
ARQUIVO = "SITUACAO_JULGADOS.json"



VALIDADE_CONSULTA_S = 24 * 3600
FERRAMENTA = "situacao_dos_julgados"








_HEX32 = re.compile(r"^[0-9a-f]{32}$")
RESULTADOS = ("confere", "nao_confere", "pendente", "sem_decisao")


CODIGOS_VETO = ("REPROVADO_DEPOIS", "PENDENTE_DEPOIS", "REPROVADO_EM_OUTRA_CONFERENCIA",
                "PENDENTE_EM_OUTRA_CONFERENCIA")
MAX_ITENS = 200
_HEX64 = re.compile(r"^[0-9a-f]{64}$")

_BRASILIA = timezone(timedelta(hours=-3))


class ErroSituacao(Exception):
    def __init__(self, codigo, mensagem):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem


def _texto(valor):
    return str(valor or "").strip()


def _int_ou_none(v):
    return v is None or (isinstance(v, int) and not isinstance(v, bool) and v >= 1)


def _base():
    if _caso_raiz is not None and callable(getattr(_caso_raiz, "base_dir", None)):
        return _caso_raiz.base_dir()
    return os.path.join(os.path.expanduser("~"), ".dissero")


def _arquivo_nonce(pasta):
    """Onde mora o nonce pendente da `pasta` (uma por pasta, pelo caminho absoluto)."""
    chave = hashlib.sha256(os.path.normcase(os.path.abspath(pasta)).encode("utf-8")).hexdigest()[:32]
    return os.path.join(_base(), "sigilo", "situacao", chave + ".json")


def nonce_pendente(pasta, criar=True):
    'O nonce pendente da `pasta`; sem nenhum, gera e grava um novo (com `criar`). None se não há'

    caminho = _arquivo_nonce(pasta)
    try:
        with open(caminho, encoding="utf-8") as fh:
            n = _texto(json.load(fh).get("nonce"))
        if _HEX32.match(n):
            return n
    except Exception:
        pass
    if not criar:
        return None
    n = secrets.token_hex(16)
    try:
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        tmp = caminho + ".%d.tmp" % os.getpid()
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"nonce": n}, fh)
        os.replace(tmp, caminho)
    except OSError:
        return None
    return n


def consumir_nonce(pasta):
    """A entrega liberada consome o nonce: a situação gravada não vale para a próxima."""
    try:
        os.remove(_arquivo_nonce(pasta))
    except OSError:
        pass


def consumir_nonces(pastas):
    'Consome o nonce de TODAS as pastas candidatas da entrega, sem reverificar (revisão adversarial de 27/11: uma'


    for p in dict.fromkeys(os.path.abspath(x) for x in pastas if x):
        consumir_nonce(p)


def verificar_envelope(envelope, chave, nonce_esperado):
    'O `recibo` da situação, depois de conferidas assinatura, forma e o nonce de uso único'

    if not isinstance(envelope, dict) or not isinstance(envelope.get("recibo"), dict) \
            or not _texto(envelope.get("assinatura")):
        raise ErroSituacao("SITUACAO_ILEGIVEL", "o arquivo não é uma situação assinada dos "
                                                "julgados (faltam o conteúdo ou a assinatura)")
    sit = envelope["recibo"]
    if _texto(sit.get("chave")) != chave["id"]:
        raise ErroSituacao("CHAVE_DESCONHECIDA", "a situação foi assinada com outra chave que não "
                                                 "a desta instalação")
    try:
        assinatura = rc.de_b64url(envelope["assinatura"])
    except ValueError:
        assinatura = b""
    if not ed25519_verificar.verificar(chave["bytes"], rc.canonico(sit), assinatura):
        raise ErroSituacao("ASSINATURA_INVALIDA", "a assinatura da situação não confere: ela foi "
                                                  "alterada depois de emitida ou não veio do "
                                                  "servidor")
    itens = sit.get("itens")
    forma = (sit.get("formato") == 1 and sit.get("tipo") == TIPO_SITUACAO
             and len(_texto(sit.get("banca"))) >= 1
             and rc.instante(sit.get("em")) is not None
             and _HEX32.match(_texto(sit.get("nonce"))) is not None
             and isinstance(itens, list) and 1 <= len(itens) <= MAX_ITENS
             and all(isinstance(i, dict) and _HEX64.match(_texto(i.get("sha256")))
                     and i.get("resultado") in RESULTADOS
                     and (i.get("conferencia") is None or _texto(i.get("conferencia")))
                     and _int_ou_none(i.get("versao"))
                     and (i.get("em") is None or rc.instante(i.get("em")) is not None)

                     and ((i.get("resultado") == "sem_decisao")
                          == (i.get("conferencia") is None and i.get("versao") is None
                              and i.get("em") is None))

                     and ("por_identidade" not in i
                          or (i.get("por_identidade") is True
                              and i.get("resultado") in ("nao_confere", "pendente")))
                     for i in itens))
    if not forma:
        raise ErroSituacao("SITUACAO_FORA_DO_FORMATO", "a situação está assinada, mas fora do "
                                                       "formato esperado; atualize o plugin")


    if not nonce_esperado:
        raise ErroSituacao("SITUACAO_SEM_PEDIDO", "não há pedido de consulta pendente para esta "
                                                  "pasta: a consulta gravada é de antes ou já serviu "
                                                  "a uma entrega")
    if not secrets.compare_digest(_texto(sit.get("nonce")), nonce_esperado):
        raise ErroSituacao("SITUACAO_DE_OUTRO_PEDIDO", "a consulta gravada não responde ao pedido "
                                                       "pendente desta pasta (é antiga, de outra "
                                                       "pasta ou já serviu a uma entrega)")
    return sit


def _selo_envelope(achado):
    v = (achado or {}).get("verification") or {}
    ha = v.get("human_attestation")
    if v.get("method") == "human" and isinstance(ha, dict):
        selo = ha.get("recibo")
    else:
        selo = v.get("ratificacao")
    return selo.get("envelope") if isinstance(selo, dict) else None


def selo_do_achado(achado):
    '{conferencia, versao, em, banca, sha256} do recibo FINAL que liberou o achado, ou'


    envelope = _selo_envelope(achado)
    if not isinstance(envelope, dict):
        raise ErroSituacao("SELO_AUSENTE", "o julgado está liberado sem o recibo da tela que o "
                                           "liberou")
    recibo, erro = rc.envelope_verificado(envelope)
    if erro is not None:
        raise ErroSituacao("SELO_INVALIDO", f"o recibo que liberou o julgado não se verifica "
                                            f"({erro.codigo})")
    if not _texto(recibo.get("banca")):
        raise ErroSituacao("SELO_SEM_BANCA", "o recibo que liberou o julgado não diz de que banca "
                                             "é")
    return {"conferencia": _texto(recibo.get("conferencia")),
            "versao": rc.versao_do_recibo(recibo), "em": rc.instante(recibo.get("em")),
            "banca": _texto(recibo.get("banca")),
            "sha256": rc.conteudo_da_atestacao(achado)}


def _legado(a):
    v = a.get("verification")
    return (isinstance(v, dict) and "result" not in v and "method" not in v)


def julgados_liberados(dados):
    'Os achados que a peça pode citar como confirmados: todo `allowed`, SELECIONADO OU NÃO.'








    achados = dados.get("achados") if isinstance(dados, dict) else None
    return [a for a in achados or [] if isinstance(a, dict) and a.get("use_status") == "allowed"
            and not _legado(a)]


def _rotulo(achado):
    return _texto(achado.get("reference")) or _texto(achado.get("id")) or "julgado sem referência"


def _decisao_mais_nova(decisao, selo):
    """True quando a decisão do servidor é posterior ao selo do achado."""
    em = rc.instante(decisao.get("em"))
    if _texto(decisao.get("conferencia")) == selo["conferencia"]:
        return isinstance(decisao.get("versao"), int) and decisao["versao"] > selo["versao"]
    return em is not None and selo["em"] is not None and em > selo["em"]


def _mesma_decisao(decisao, selo):
    return (_texto(decisao.get("conferencia")) == selo["conferencia"]
            and decisao.get("versao") == selo["versao"])


def avaliar(dados, envelope, nonce=None):
    '{"itens": [hash, ...] a consultar, "geral": ErroSituacao|None (problema da situação'


    liberados = julgados_liberados(dados)
    saida = {"itens": [], "geral": None, "julgados": []}
    selos = []
    for a in liberados:
        try:
            selo = selo_do_achado(a)
        except ErroSituacao as e:
            saida["julgados"].append({"codigo": e.codigo, "rotulo": _rotulo(a), "sha256": "",
                                      "detalhe": e.mensagem})
            continue
        selos.append((a, selo))
    saida["itens"] = list(dict.fromkeys(s["sha256"] for _a, s in selos))
    if not selos:
        return saida
    if envelope is None:
        saida["geral"] = ErroSituacao("SITUACAO_AUSENTE", "não há consulta da situação gravada "
                                                          "na pasta da peça")
        return saida
    try:
        sit = verificar_envelope(envelope, rc.carregar_chave(), nonce)
    except (ErroSituacao, rc.ErroRecibo) as e:
        saida["geral"] = e if isinstance(e, ErroSituacao) else ErroSituacao(e.codigo, e.mensagem)
        return saida
    except Exception as e:
        saida["geral"] = ErroSituacao("SITUACAO_FORA_DO_FORMATO", str(e))
        return saida
    em = rc.instante(sit.get("em"))


    vencida = em is None or (datetime.now(timezone.utc) - em).total_seconds() > VALIDADE_CONSULTA_S
    por_hash = {}
    for i in sit["itens"]:
        por_hash.setdefault(_texto(i.get("sha256")), i)
    banca = _texto(sit.get("banca"))
    for a, selo in selos:
        base = {"rotulo": _rotulo(a), "sha256": selo["sha256"]}
        if selo["banca"] != banca:

            saida["geral"] = ErroSituacao("SITUACAO_DE_OUTRA_BANCA", "a consulta gravada é de "
                                                                     "outra banca que não a do "
                                                                     "recibo do julgado")
            saida["julgados"] = [j for j in saida["julgados"] if j["codigo"].startswith("SELO_")]
            return saida
        d = por_hash.get(selo["sha256"])
        if d is None:
            saida["geral"] = ErroSituacao("SITUACAO_SEM_ESTE_JULGADO", "a consulta gravada não "
                                                                       "traz todos os julgados "
                                                                       "citados")
            continue
        r = d.get("resultado")
        if d.get("por_identidade") is True:


            if r == "nao_confere":
                saida["julgados"].append(dict(base, codigo="REPROVADO_EM_OUTRA_CONFERENCIA",
                                              decisao=d,
                                              detalhe="o mesmo julgado, com outro conteúdo, foi "
                                                      "marcado como não confere numa conferência "
                                                      "encerrada depois"))
            else:
                saida["julgados"].append(dict(base, codigo="PENDENTE_EM_OUTRA_CONFERENCIA",
                                              decisao=d,
                                              detalhe="o mesmo julgado, com outro conteúdo, foi "
                                                      "deixado pendente numa conferência "
                                                      "encerrada depois"))
            continue
        if r == "confere":
            if _mesma_decisao(d, selo) or _decisao_mais_nova(d, selo):
                continue
            saida["julgados"].append(dict(base, codigo="DECISAO_ANTERIOR_AO_SELO", decisao=d,
                                          detalhe="a decisão que o servidor guarda é mais antiga "
                                                  "que o recibo que liberou o julgado"))
        elif r == "nao_confere":
            saida["julgados"].append(dict(base, codigo="REPROVADO_DEPOIS", decisao=d,
                                          detalhe="marcado como não confere numa conferência "
                                                  "encerrada depois"))
        elif r == "pendente":
            saida["julgados"].append(dict(base, codigo="PENDENTE_DEPOIS", decisao=d,
                                          detalhe="deixado pendente numa conferência encerrada "
                                                  "depois"))
        else:
            saida["julgados"].append(dict(base, codigo="SEM_DECISAO", decisao=d,
                                          detalhe="a banca não tem decisão registrada sobre ele"))
    if vencida:
        saida["julgados"] = [j for j in saida["julgados"]
                             if j["codigo"] in CODIGOS_VETO or j["codigo"].startswith("SELO_")]
        saida["geral"] = ErroSituacao("SITUACAO_VENCIDA", "a consulta gravada tem mais de 24 horas; uma "
                                                          "decisão da banca posterior a ela não apareceria")
    return saida


def _quando(decisao):
    em = rc.instante((decisao or {}).get("em"))
    return em.astimezone(_BRASILIA).strftime("%d/%m/%Y às %H:%M") if em else ""


def _lista(julgados, com_data=False):
    partes = []
    for j in julgados[:6]:
        q = _quando(j.get("decisao")) if com_data else ""
        partes.append(j["rotulo"] + (f", em {q}" if q else ""))
    return "; ".join(partes) + ("…" if len(julgados) > 6 else "")


def _para_o_assistente_consulta(itens, pasta, codigos):
    nonce = nonce_pendente(pasta) or ""
    lista = (json.dumps({"itens": itens, "nonce": nonce}) if len(itens) <= 10 else
             f"os itens e o nonce que `situacao_julgados.py itens <achados.json> --pasta \"{pasta}\"` "
             f"imprime")
    return (f"Para o assistente (não repita ao advogado; códigos: {', '.join(codigos)}): chame "
            f"`{FERRAMENTA}` do conector dissero com {lista} e grave o envelope devolvido, sem "
            f"mexer, como {ARQUIVO} em {pasta}; depois repita a entrega. O nonce é de uso único e "
            f"desta pasta: não reaproveite consulta antiga, de outra pasta nem de outra banca.")


def motivos(dados, envelope, pasta, agora=None):
    'As mensagens de bloqueio da entrega (lista vazia = a situação sustenta a entrega). Cada uma'



    r = avaliar(dados, envelope, nonce_pendente(pasta, criar=False))
    msgs = []
    por = {}
    for j in r["julgados"]:
        por.setdefault(j["codigo"], []).append(j)
    vetados = [j for c in CODIGOS_VETO for j in por.get(c, [])]
    if vetados:
        partes = []
        if por.get("REPROVADO_DEPOIS"):
            partes.append("reprovado(s): " + _lista(por["REPROVADO_DEPOIS"], True))
        if por.get("PENDENTE_DEPOIS"):
            partes.append("deixado(s) pendente(s): " + _lista(por["PENDENTE_DEPOIS"], True))
        if por.get("REPROVADO_EM_OUTRA_CONFERENCIA"):
            partes.append("reprovado(s) em outra conferência, com outro trecho, endereço ou "
                          "ementa do mesmo julgado: "
                          + _lista(por["REPROVADO_EM_OUTRA_CONFERENCIA"], True))
        if por.get("PENDENTE_EM_OUTRA_CONFERENCIA"):
            partes.append("deixado(s) pendente(s) em outra conferência, com outro trecho, "
                          "endereço ou ementa do mesmo julgado: "
                          + _lista(por["PENDENTE_EM_OUTRA_CONFERENCIA"], True))
        msgs.append(
            f"Falta: decidir o que fazer com {len(vetados)} julgado(s) que a banca reprovou ou "
            f"deixou pendente numa conferência encerrada depois da que os liberou ({'; '.join(partes)}). "
            f"Enquanto isso, a peça não é entregue. Quem resolve: o advogado responsável pela peça. "
            f"Como: tirar o julgado da peça (a mudança de texto volta ao rito) ou, se a reprovação "
            f"foi engano, abrir nova conferência no Minha banca com o julgado como está na peça, "
            f"marcar confere e encerrar; a confirmação antiga não vale mais. "
            f"Para o assistente (não repita ao advogado; códigos: "
            f"{', '.join(sorted({j['codigo'] for j in vetados}))}): a decisão mais nova da banca "
            f"prevalece sobre o selo gravado no achados.json; registre o recibo da nova conferência "
            f"com `registrar_confirmacao_manual.py --recibo` ou retire o julgado da peça, e consulte "
            f"de novo `{FERRAMENTA}` com o nonce pendente desta pasta ({nonce_pendente(pasta)}).")
    sem = (por.get("SEM_DECISAO", []) + por.get("DECISAO_ANTERIOR_AO_SELO", [])
           + por.get("SELO_AUSENTE", []) + por.get("SELO_INVALIDO", []) + por.get("SELO_SEM_BANCA", []))
    if sem:
        msgs.append(
            f"Falta: a banca não tem, no servidor do Dissero, a conferência que liberou "
            f"{len(sem)} julgado(s) ({_lista(sem)}). Enquanto isso, a peça não é entregue. Quem "
            f"resolve: confere qualquer pessoa da banca, entrando com o próprio login; encerra o "
            f"titular da banca ou quem abriu a conferência. Como: abrir no Minha banca uma "
            f"conferência com esses julgados, conferir e clicar Encerrar e liberar. "
            f"Para o assistente (não repita ao advogado; códigos: "
            f"{', '.join(sorted({j['codigo'] for j in sem}))}): abra a conferência com "
            f"`preparar_conferencia`, registre o recibo do encerramento com "
            f"`registrar_confirmacao_manual.py --recibo` e consulte de novo `{FERRAMENTA}` com o "
            f"nonce pendente desta pasta ({nonce_pendente(pasta)}).")
    g = r["geral"]
    if g is not None:
        porque = {
            "SITUACAO_AUSENTE": "ela ainda não foi feita para esta peça",
            "SITUACAO_SEM_PEDIDO": "a consulta gravada é de antes deste pedido ou já serviu a uma entrega",
            "SITUACAO_DE_OUTRO_PEDIDO": "a consulta gravada é de antes deste pedido ou já serviu a uma "
                                        "entrega",
            "SITUACAO_SEM_ESTE_JULGADO": "a consulta gravada não traz todos os julgados citados",
            "SITUACAO_DE_OUTRA_BANCA": "a consulta gravada é de outra banca e não serve para esta",
            "SITUACAO_VENCIDA": "a consulta gravada tem mais de 24 horas",
        }.get(g.codigo, "a consulta gravada não pôde ser conferida e é descartada")
        msgs.append(
            f"Falta: confirmar com o servidor do Dissero que a conferência dos julgados citados "
            f"continua valendo na banca; cada consulta serve a uma entrega só, e {porque}. "
            f"Quem resolve: o assistente, sozinho, com o conector do Dissero "
            f"conectado (se não estiver, o advogado o conecta). Como: consultar a situação dos "
            f"julgados e repetir a entrega; não há nada a mudar na peça. "
            + _para_o_assistente_consulta(r["itens"], pasta, [g.codigo])
            + (f" Detalhe: {g.mensagem}." if g.codigo not in ("SITUACAO_AUSENTE",) else ""))
    return msgs


def ler_envelope(pasta):
    'O envelope gravado em <pasta>/SITUACAO_JULGADOS.json, None se o arquivo não existe, ou'

    caminho = os.path.join(pasta, ARQUIVO)
    if not os.path.isfile(caminho):
        return None
    try:



        with open(caminho, encoding="utf-8-sig") as fh:
            dados = json.load(fh)
        return dados if isinstance(dados, dict) else {}
    except Exception:
        return {}


def consumir_da_entrega(achados_path, pastas):
    'Depois da entrega liberada: consome o nonce da pasta cuja consulta a sustentou, para que a'

    try:
        with open(achados_path, encoding="utf-8") as fh:
            dados = json.load(fh)
        pastas = [p for p in dict.fromkeys(os.path.abspath(p) for p in pastas if p)] or [
            os.path.dirname(os.path.abspath(achados_path))]
        for p in pastas:
            env = ler_envelope(p)
            if env is not None and not motivos(dados, env, p):
                consumir_nonce(p)
                return p
    except Exception:
        pass
    return None


def motivos_da_entrega(achados_path, pastas, agora=None):
    'Mensagens de bloqueio da entrega para o `achados.json` em `achados_path`, com a situação'



    try:
        with open(achados_path, encoding="utf-8") as fh:
            dados = json.load(fh)
    except Exception:
        return []
    pastas = [p for p in dict.fromkeys(os.path.abspath(p) for p in pastas if p)]
    if not pastas:
        pastas = [os.path.dirname(os.path.abspath(achados_path))]
    primeira = None
    for p in pastas:
        env = ler_envelope(p)
        if env is None:
            continue
        m = motivos(dados, env, p, agora)
        if not m:
            return []
        if primeira is None:
            primeira = m
    return primeira if primeira is not None else motivos(dados, None, pastas[0], agora)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Situação dos julgados na banca, exigida na entrega")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pi = sub.add_parser("itens", help="hashes a pedir à ferramenta, no formato que ela recebe")
    pi.add_argument("achados")
    pi.add_argument("--pasta", default=None,
                    help="a pasta onde a consulta será gravada (padrão: a do achados.json); "
                         "o nonce de uso único é dela")
    pc = sub.add_parser("conferir", help="confere a situação gravada contra o achados.json")
    pc.add_argument("achados")
    pc.add_argument("--situacao", default=None,
                    help=f"o envelope gravado (padrão: {ARQUIVO} ao lado do achados.json)")
    a = ap.parse_args(argv)
    try:
        with open(a.achados, encoding="utf-8") as fh:
            dados = json.load(fh)
    except Exception as e:
        print(json.dumps({"ok": False, "erro": f"achados.json ilegível: {e}"}, ensure_ascii=False))
        return 2
    if a.cmd == "itens":
        r = avaliar(dados, None)
        pasta = a.pasta or os.path.dirname(os.path.abspath(a.achados))
        print(json.dumps({"itens": r["itens"], "nonce": nonce_pendente(pasta) if r["itens"] else None},
                         ensure_ascii=False))
        return 0
    if a.situacao:
        pasta = os.path.dirname(os.path.abspath(a.situacao))
        try:
            with open(a.situacao, encoding="utf-8-sig") as fh:
                env = json.load(fh)
        except FileNotFoundError:
            env = None
        except Exception:
            env = {}
    else:
        pasta = os.path.dirname(os.path.abspath(a.achados))
        env = ler_envelope(pasta)
    m = motivos(dados, env, pasta)
    print(json.dumps({"ok": not m, "motivos": m}, ensure_ascii=False))
    return 0 if not m else 1


if __name__ == "__main__":
    sys.exit(main())
