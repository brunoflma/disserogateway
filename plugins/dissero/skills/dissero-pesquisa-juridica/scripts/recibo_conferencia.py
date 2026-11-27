#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'Recibo assinado da tela de conferência: a chave fixada, a verificação e a reverificação.'






























from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from datetime import datetime, timezone

import ed25519_verificar

AQUI = os.path.dirname(os.path.abspath(__file__))
CHAVE_PUBLICA_PATH = os.path.join(AQUI, "conferencia_chave_publica.json")
VARIAVEL_CHAVE_TESTE = "DSR_CONFERENCIA_CHAVE_TESTE"


ARQ_APOIO_TESTE = os.path.join(AQUI, "test_apoio_recibo.py")
CHAVE_PRODUCAO_SHA256 = "e420a11924e4a164cf5226913962d64ab799da69c3e404768c9a68a979eeed66"
TIPO_RECIBO = "dsr.conferencia.recibo.v1"



RESULTADOS_RECIBO = ("confere", "nao_confere", "pendente")




ORIGENS = ("maquina", "pessoa")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class ErroRecibo(Exception):
    def __init__(self, codigo, mensagem):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem


def _texto(valor):
    return str(valor or "").strip()


def canonico(obj):
    """Bytes do JSON canônico que o servidor assina: chaves ordenadas, sem espaços, UTF-8."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def de_b64url(valor):
    valor = _texto(valor)
    if not re.fullmatch(r"[A-Za-z0-9_\-]+={0,2}", valor):
        raise ValueError("base64url inválido")
    return base64.urlsafe_b64decode(valor + "=" * (-len(valor) % 4))


_CHAVES_DE_TESTE = {}


def _chave_de_teste():
    'Bytes da chave de teste, ou None. Só com a variável ligada E o apoio de testes ao lado (que'

    if os.environ.get(VARIAVEL_CHAVE_TESTE) != "1" or not os.path.isfile(ARQ_APOIO_TESTE):
        return None
    if ARQ_APOIO_TESTE not in _CHAVES_DE_TESTE:
        import importlib.util
        spec = importlib.util.spec_from_file_location("_dsr_apoio_recibo", ARQ_APOIO_TESTE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _CHAVES_DE_TESTE[ARQ_APOIO_TESTE] = mod.chave_publica()
    return _CHAVES_DE_TESTE[ARQ_APOIO_TESTE]


def carregar_chave(caminho=None):
    "{'bytes', 'id', 'teste'} da chave pública que vale nesta instalação. Arquivo ausente ou"


    teste = _chave_de_teste()
    if teste is not None:
        return {"bytes": teste, "id": hashlib.sha256(teste).hexdigest()[:8], "teste": True}
    try:
        with open(caminho or CHAVE_PUBLICA_PATH, encoding="utf-8") as fh:
            info = json.load(fh)
        chave = de_b64url(info.get("chave"))
        if info.get("formato") != 1 or len(chave) != 32:
            raise ValueError("formato da chave")
    except Exception as erro:
        raise ErroRecibo("CHAVE_INDISPONIVEL",
                         f"a chave pública da conferência não pôde ser lida ({erro}); "
                         f"reinstale o plugin") from None
    inteiro = hashlib.sha256(chave).hexdigest()
    ident = inteiro[:8]
    if _texto(info.get("id")) != ident:
        raise ErroRecibo("CHAVE_INDISPONIVEL",
                         "a chave pública da conferência não confere com o próprio "
                         "identificador; reinstale o plugin")



    if info.get("teste") is True and os.environ.get(VARIAVEL_CHAVE_TESTE) != "1":
        raise ErroRecibo("CHAVE_DE_TESTE",
                         "esta instalação traz só a chave de teste da conferência, que não vale "
                         "para registro real; atualize o plugin")
    if not CHAVE_PRODUCAO_SHA256 or inteiro != CHAVE_PRODUCAO_SHA256:
        raise ErroRecibo("CHAVE_NAO_FIXADA",
                         "a chave pública da conferência desta instalação não é a do servidor do "
                         "Dissero; reinstale o plugin")
    return {"bytes": chave, "id": ident, "teste": False}


def recibo_final(recibo):
    'True só no recibo do ENCERRAMENTO (decisão do titular, 26/11/2026, D1: só vale o recibo'


    return (recibo or {}).get("final") is True


def versao_do_recibo(recibo):
    """Versão do recibo (1 quando ausente: os recibos da primeira rodada não a traziam)."""
    v = (recibo or {}).get("versao", 1)
    return v if isinstance(v, int) and not isinstance(v, bool) else 0


def verificar_envelope(envelope, chave):
    """O `recibo` do envelope, depois de conferida a assinatura e a forma. ErroRecibo se não."""
    if not isinstance(envelope, dict) or not isinstance(envelope.get("recibo"), dict) \
            or not _texto(envelope.get("assinatura")):
        raise ErroRecibo("RECIBO_ILEGIVEL", "o arquivo não é um recibo da tela de conferência "
                                            "(faltam o recibo ou a assinatura)")
    if chave["teste"] and os.environ.get(VARIAVEL_CHAVE_TESTE) != "1":
        raise ErroRecibo("CHAVE_DE_TESTE",
                         "esta instalação traz só a chave de teste da conferência, que não vale "
                         "para registro real; atualize o plugin")
    recibo = envelope["recibo"]
    if _texto(recibo.get("chave")) != chave["id"]:
        raise ErroRecibo("CHAVE_DESCONHECIDA",
                         "o recibo foi assinado com outra chave que não a desta instalação; "
                         "atualize o plugin ou refaça a conferência na tela")
    try:
        assinatura = de_b64url(envelope["assinatura"])
    except ValueError:
        assinatura = b""
    if not ed25519_verificar.verificar(chave["bytes"], canonico(recibo), assinatura):
        raise ErroRecibo("ASSINATURA_INVALIDA",
                         "a assinatura do recibo não confere: ele foi alterado depois de emitido "
                         "ou não veio do servidor; refaça a conferência na tela")
    itens = recibo.get("itens")
    pendentes = recibo.get("pendentes", [])
    final = recibo_final(recibo)
    forma = (recibo.get("formato") == 1 and recibo.get("tipo") == TIPO_RECIBO
             and isinstance(recibo.get("final", False), bool)
             and _texto(recibo.get("conferencia"))
             and versao_do_recibo(recibo) >= 1
             and len(_texto((recibo.get("conferido_por") or {}).get("nome"))) >= 2
             and len(_texto(recibo.get("responsavel"))) >= 2
             and instante(recibo.get("em")) is not None
             and isinstance(itens, list) and isinstance(pendentes, list)

             and (itens or pendentes)
             and all(isinstance(i, dict) and _texto(i.get("id"))
                     and _HEX64.match(_texto(i.get("sha256")))
                     and i.get("resultado") in RESULTADOS_RECIBO
                     and _autoria_bem_formada(i) and _origem_bem_formada(i, final)
                     for i in itens)
             and all(isinstance(i, dict) and _texto(i.get("id"))
                     and _HEX64.match(_texto(i.get("sha256")))
                     and _autoria_bem_formada(i) and _origem_bem_formada(i, final)
                     for i in pendentes))
    if not forma:
        raise ErroRecibo("RECIBO_FORA_DO_FORMATO",
                         "o recibo está assinado, mas fora do formato esperado; atualize o "
                         "plugin")
    return recibo


def _autoria_bem_formada(item):
    'A autoria do item (por, em, versao), quando o servidor a manda, tem de estar inteira: um'

    if "por" not in item:
        return True
    v = item.get("versao")
    return (len(_texto(item.get("por"))) >= 2 and instante(item.get("em")) is not None
            and isinstance(v, int) and not isinstance(v, bool) and v >= 1)


def _origem_bem_formada(item, final):
    '`origem` é "maquina" ou "pessoa"; o da máquina traz `maquina` com a fonte e a data em que a'


    if "origem" not in item:
        return not final
    origem = item.get("origem")
    if origem not in ORIGENS:
        return False
    if origem == "maquina":
        m = item.get("maquina")
        return (isinstance(m, dict) and len(_texto(m.get("fonte"))) >= 3
                and len(_texto(m.get("em"))) >= 10)
    return True


def origem_do_item(item):
    """Origem do item; ausente vale "pessoa" (só em recibo intermediário, que nada confirma)."""
    return "maquina" if (item or {}).get("origem") == "maquina" else "pessoa"


def entradas_do_recibo(recibo):
    'Cada julgado do recibo com a decisão dele, no formato único que o registro aplica.'






    nome = _texto((recibo.get("conferido_por") or {}).get("nome"))
    em = _texto(recibo.get("em"))
    versao = versao_do_recibo(recibo)
    saida = []
    for item, resultado in ([(i, None) for i in recibo.get("itens") or []]
                            + [(i, "pendente") for i in recibo.get("pendentes") or []]):
        e = dict(item)
        if resultado:
            e["resultado"] = resultado
        e["por"] = _texto(item.get("por")) or nome
        e["em"] = _texto(item.get("em")) or em
        e["versao"] = item.get("versao") if "por" in item else versao
        e["origem"] = origem_do_item(item)
        saida.append(e)
    return saida


def instante(valor):
    'datetime com fuso de um ISO-8601, ou None. Só instantes completos (com hora) contam:'

    t = _texto(valor)
    if len(t) < 11:
        return None
    try:
        d = datetime.fromisoformat(t.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def sha256_inteiro_teor(achado):
    """Hash do inteiro teor guardado no achado (`full_text`), ou "" sem inteiro teor."""
    inteiro = _texto((achado or {}).get("full_text"))
    return hashlib.sha256(inteiro.encode("utf-8")).hexdigest() if inteiro else ""


def conteudo(rotulo, citacao, texto_peca, endereco, documento, inteiro_teor=""):
    '(conteúdo, sha256) do item como a tela o mostra; o mesmo cálculo de `conteudoDoItem` no'







    citacao = citacao if isinstance(citacao, dict) else {}
    corpo = {
        "citacao": {"data": _texto(citacao.get("judgment_date")),
                    "numero": _texto(citacao.get("case_number")),
                    "relator": _texto(citacao.get("rapporteur")),
                    "tribunal": _texto(citacao.get("court"))},
        "documento": documento or "",
        "endereco": endereco or "",
        "rotulo": rotulo,
        "texto": _texto(texto_peca),
    }
    if inteiro_teor:
        corpo["inteiro_teor"] = inteiro_teor
    return corpo, hashlib.sha256(canonico(corpo)).hexdigest()


def rotulo_do_documento(rotulo, arquivo):
    """Rótulo do julgado ancorado no inteiro teor dos autos: diz à pessoa qual arquivo comparar."""
    return f"{rotulo} (inteiro teor dos autos: {arquivo})"


def conteudo_da_atestacao(achado):
    'sha256 do conteúdo que a tela mostrou, refeito só com o achado e a atestação gravada (sem o'


    ha = ((achado.get("verification") or {}).get("human_attestation") or {})
    rotulo = _texto(achado.get("reference")) or _texto(achado.get("id"))
    doc = ha.get("documento") if isinstance(ha.get("documento"), dict) else None
    url = _texto(achado.get("official_url"))
    if doc and not url:
        return conteudo(rotulo_do_documento(rotulo, _texto(doc.get("arquivo"))),
                        achado.get("citation"), achado.get("syllabus_literal"), "",
                        _texto(doc.get("sha256")), sha256_inteiro_teor(achado))[1]
    return conteudo(rotulo, achado.get("citation"), achado.get("syllabus_literal"),
                    url if url.lower().startswith("https://") else "", "",
                    sha256_inteiro_teor(achado))[1]




_CACHE = {}


def _envelope_verificado(envelope):


    chave_cache = (hashlib.sha256(canonico(envelope)).hexdigest(), CHAVE_PUBLICA_PATH,
                   CHAVE_PRODUCAO_SHA256, ARQ_APOIO_TESTE, os.environ.get(VARIAVEL_CHAVE_TESTE))
    if chave_cache not in _CACHE:
        try:
            _CACHE[chave_cache] = (verificar_envelope(envelope, carregar_chave()), None)
        except ErroRecibo as erro:
            _CACHE[chave_cache] = (None, erro)
        except Exception as erro:
            _CACHE[chave_cache] = (None, ErroRecibo("RECIBO_FORA_DO_FORMATO", str(erro)))
    return _CACHE[chave_cache]


def envelope_verificado(envelope):
    '(recibo, None) do envelope verificado pela chave fixada, ou (None, ErroRecibo). A situação'

    return _envelope_verificado(envelope)


MOTIVO_SEM_RECIBO = (
    "confirmacao_sem_recibo_da_tela: confirmação humana sem o recibo assinado da tela de "
    "conferência não confirma mais o julgado (só a tela vale, desde 26/11/2026); o julgado volta "
    "a pendente e precisa ser conferido no Minha banca. O registro da conferência rebaixa sozinho a "
    "confirmação antiga a pendente; depois, abra a conferência na tela, revise, clique Encerrar e "
    "liberar e registre o recibo do encerramento")



MOTIVO_FALTA_RATIFICAR = ("teor conferido pela máquina, falta ratificar na conferência do Minha "
                          "banca")


def falta_ratificar(achado):
    'True quando a máquina confirmou o teor na fonte (automatic + confirmed) e ainda não há'

    v = (achado or {}).get("verification") or {}
    return (v.get("method") == "automatic" and v.get("result") == "confirmed"
            and not isinstance(v.get("ratificacao"), dict))


def _motivos_do_selo(achado, selo, origem, quem, responsavel=""):
    'Motivos pelos quais o selo gravado não sustenta a liberação do julgado; vazio quando o'


    envelope = selo.get("envelope") if isinstance(selo, dict) else None
    if not isinstance(envelope, dict):
        return [MOTIVO_SEM_RECIBO]
    recibo, erro = _envelope_verificado(envelope)
    if erro is not None:
        return [f"recibo_da_conferencia_invalido ({erro.codigo}): {erro.mensagem}"]
    erros = []
    assinatura = _texto(envelope.get("assinatura"))
    if (_texto(selo.get("conferencia")) != _texto(recibo.get("conferencia"))
            or _texto(selo.get("chave")) != _texto(recibo.get("chave"))
            or _texto(selo.get("em")) != _texto(recibo.get("em"))
            or _texto(selo.get("assinatura_sha256"))
            != hashlib.sha256(assinatura.encode("ascii", "replace")).hexdigest()):
        erros.append("recibo_da_conferencia_divergente: o selo gravado não é o do envelope "
                     "assinado; registre de novo o recibo da tela")


    if not recibo_final(recibo):
        erros.append("recibo_da_conferencia_em_andamento: o recibo gravado é de uma conferência "
                     "ainda aberta e não libera o julgado; no Minha banca, revise e clique "
                     "Encerrar e liberar, e registre o recibo do encerramento")
    if _texto(responsavel) and _texto(responsavel) != _texto(recibo.get("responsavel")):
        erros.append("recibo_da_conferencia_de_outro_responsavel: o advogado responsável gravado "
                     "não é o do recibo; registre de novo o recibo da tela")
    ident = _texto(achado.get("id"))
    itens = [i for i in entradas_do_recibo(recibo) if _texto(i.get("id")) == ident]



    if itens and _texto(quem) != _texto(itens[-1].get("por")):
        erros.append("recibo_da_conferencia_de_outra_pessoa: quem consta como tendo conferido não "
                     "é quem conferiu na tela; registre de novo o recibo da tela")
    if not itens:
        erros.append("recibo_da_conferencia_sem_este_julgado: o recibo gravado não traz este "
                     "julgado; abra uma conferência na tela que o inclua")
    elif itens[-1].get("resultado") != "confere":
        erros.append("recibo_da_conferencia_nao_confirma: no recibo gravado este julgado não foi "
                     "marcado como confere")
    elif itens[-1].get("origem") != origem:


        erros.append("recibo_da_conferencia_de_outra_origem: no recibo este julgado é de origem "
                     f"{itens[-1].get('origem')}, e o registro diz {origem}; abra uma conferência "
                     "nova na tela")
    elif _texto(itens[-1].get("sha256")) != conteudo_da_atestacao(achado):
        erros.append("recibo_da_conferencia_de_outro_conteudo: o julgado mudou depois de conferido "
                     "na tela (texto, citação, endereço, documento ou inteiro teor); confira de "
                     "novo na tela")
    return erros


def motivos_do_recibo(achado):
    'Motivos pelos quais a liberação do achado NÃO se sustenta no recibo final gravado; lista'




    v = achado.get("verification") or {}
    ha = v.get("human_attestation")
    if isinstance(ha, dict):
        return _motivos_do_selo(achado, ha.get("recibo"), "pessoa", ha.get("actor"),
                                ha.get("responsavel"))
    rat = v.get("ratificacao")
    if isinstance(rat, dict):
        return _motivos_do_selo(achado, rat, "maquina", rat.get("por"))
    return []


def confirmacao_sem_recibo_valido(achado):
    'True quando o achado está liberado (humano, ou da máquina com ratificação gravada) por um'

    v = achado.get("verification") or {}
    if v.get("result") != "confirmed":
        return False
    if v.get("method") == "human" or (v.get("method") == "automatic"
                                      and isinstance(v.get("ratificacao"), dict)):
        return bool(motivos_do_recibo(achado))
    return False
