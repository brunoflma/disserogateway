#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'escolha_do_metodo.py — a ESCOLHA do advogado entre a minuta rápida e o método completo.'









































import argparse
import datetime
import hashlib
import json
import os
import re
import sys

try:
    import pesquisa_tentada
except Exception:
    pesquisa_tentada = None
try:
    import falas_do_advogado
except Exception:
    falas_do_advogado = None
try:
    import etapa_tentada
except Exception:
    etapa_tentada = None

NOME = "ESCOLHA_DO_METODO.json"
SCHEMA = "dsr.escolha_do_metodo.v1"
MODOS = ("rapida", "completo")



PERGUNTA = (
    "Antes de começar: como prefere receber esta peça?\n"
    "1. Minuta rápida. Entrego agora o Word com as pendências marcadas. O prazo é calculado e nada "
    "é citado de memória, mas não confirmo jurisprudência, não submeto estratégia nem roteiro de "
    "argumentos à sua aprovação e a peça não passa pela revisão do Conselho.\n"
    "2. Método completo. Sigo todas as etapas: prazo, estratégia e roteiro de argumentos (paro para "
    "a sua aprovação nos dois), teste da tese, redação, pesquisa de jurisprudência confirmada com "
    "relação de precedentes, formatação, conferência final e revisão do Conselho. Leva mais de uma "
    "rodada de conversa.\n"
    "Responda 1 ou 2. Se escolher a rápida, pode pedir o método completo depois, sobre a mesma peça.")

O_QUE_FICOU_SEM_FAZER = ("jurisprudência não confirmada, estratégia e roteiro de argumentos sem a "
                         "aprovação do advogado, sem teste da tese e sem revisão do Conselho")




ETAPAS_ANTES_DA_REDACAO = (("briefing", "o levantamento do caso"), ("prazo", "o cálculo do prazo"),
                           ("estrategia", "a estratégia, com a aprovação do advogado"),
                           ("mapa", "o roteiro de argumentos, com a aprovação do advogado"))
ETAPAS_DEPOIS = (("verificacao", "verificação das citações"), ("visual_law", "formatação"),
                 ("lint", "conferência final"), ("conselho", "revisão do Conselho"))
PECA_STATE = "PECA_STATE.json"


def _selo(reg):
    base = {k: v for k, v in reg.items() if k != "selo"}
    return hashlib.sha256(json.dumps(base, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


class Recusa(Exception):
    pass








MARCA_DA_PERGUNTA = "como prefere receber esta peça"







_PREFIXO = (r'(?:(?:quero|prefiro|escolho|pode ser|vai|vou|vamos|fica|fico|com|de|faz|faca|manda|e|eh|mesmo|'
            r'ok|sim|certo|beleza|blz|entao|bom|a|o|na|no|pela|pelo|opcao|alternativa|numero|n|resposta)[\s,:-]+)*')
_OPCOES = (
    ("rapida", r'1(?:a|o)?|primeira(?: opcao| alternativa)?|minuta rapida|rapida|rapido|so a minuta'),
    ("completo", r'2(?:a|o)?|segunda(?![ -]?feira)(?: opcao| alternativa)?|metodo completo|completo|completa'),
)
_SOZINHOS = {"um": "rapida", "dois": "completo"}

_DEPOIS_NEGA = re.compile(r'\s*,?\s*(?:nao|nunca|jamais|nem)(?!\w)(?!\s+(?:tenho|tem|ha|precisa|preciso|e|eh)\b)')
_FATO_DEPOIS = re.compile(r'\s*(?:dias?|horas?|anos?|meses|vara|turma|camara|reais|%|mil)\b')
_ORDINAL = re.compile(r'(?:primeira|segunda)(?: opcao| alternativa)?$')
_DEPOIS_ORDINAL_OK = frozenset(("opcao", "alternativa", "mesmo", "mesma", "por", "pf", "pfv", "ok", "e", "pode",
                                "entao", "so", "sim", "obrigado", "obrigada"))


def escolha_da_resposta(texto):
    '"rapida", "completo" ou None: a opção com que a resposta ABRE. Pergunta dele («a rápida ou'


    n = _norm(texto).replace("º", "o").replace("°", "o")
    n = re.sub(r'^[\W_]+', '', n)
    primeira_frase = re.match(r'[^.!?\n]*[.!?\n]?', n).group(0)
    if primeira_frase.rstrip().endswith("?"):
        return None
    inteira = re.sub(r'[\W_]+', ' ', n).strip()
    if inteira in _SOZINHOS:
        return _SOZINHOS[inteira]
    alvo = re.sub(r'[.](?=\s*\d)', ' ', n)
    for modo, rx in _OPCOES:
        m = re.match(_PREFIXO + r'(?:' + rx + r')(?![\w])', alvo)
        if not m or _DEPOIS_NEGA.match(n, m.end()) or _FATO_DEPOIS.match(n, m.end()):
            continue
        if re.match(r'\s*,?\s*ou(?!\w)', n[m.end():]):
            return None
        prox = re.match(r'\s+([a-z]{2,})', n[m.end():])
        if _ORDINAL.search(m.group(0)) and prox and prox.group(1) not in _DEPOIS_ORDINAL_OK:
            continue
        return modo
    return None


def modos_ditos(texto):
    """{modo} da resposta, ou vazio (compatível com a forma anterior, que devolvia conjunto)."""
    m = escolha_da_resposta(texto)
    return {m} if m else set()


def _norm(texto):
    if falas_do_advogado is not None:
        return falas_do_advogado.normalizar(texto)
    import unicodedata
    t = unicodedata.normalize("NFKD", texto or "")
    return " ".join("".join(c for c in t if not unicodedata.combining(c)).split()).casefold()


TRECHOS_DA_PERGUNTA = (MARCA_DA_PERGUNTA, "Minuta rápida", "Método completo")


_TROCA = (("rapida", re.compile(r'(?<!\w)(?:minuta rapida|so a minuta|manda a minuta|a minuta agora)(?!\w)')),
          ("completo", re.compile(r'(?<!\w)metodo completo(?!\w)')))
_NEGA_ANTES = re.compile(r'(?<!\w)(?:nao|nem|nunca|jamais|sem)(?!\w)')


def troca_dita(texto):
    """O modo que a mensagem pede pelo nome inteiro da opção, ou None (pergunta, negação, as duas)."""
    n = _norm(texto)
    if n.rstrip().endswith("?"):
        return None
    ditos = set()
    for modo, rx in _TROCA:
        for m in rx.finditer(n):
            antes = re.findall(r'\w+', n[max(0, m.start() - 40):m.start()])[-3:]
            if not any(_NEGA_ANTES.fullmatch(w) for w in antes):
                ditos.add(modo)
    return ditos.pop() if len(ditos) == 1 else None


def _ancora_registrar(entrada):
    cmd = entrada.get("command") if isinstance(entrada, dict) else None
    return isinstance(cmd, str) and "escolha_do_metodo" in cmd and "registrar" in cmd


def _nao_conferida(motivo, fonte=None):
    return {"estado": "nao_conferida", "fonte": fonte, "resposta": None, "motivo": motivo}


def conferir_palavras(modo, palavras, env=None, livro=None, ancora=_ancora_registrar, troca=False):
    'A conferência a gravar com a escolha: {"estado": "conferida"|"nao_conferida", "fonte",'











    dito_p = escolha_da_resposta(palavras) or (troca_dita(palavras) if troca else None)
    if dito_p is None:
        raise Recusa("as palavras não abrem por uma das duas opções («1», «a 2», «a rápida», «o completo»"
                     + (", ou «método completo»/«minuta rápida» na troca" if troca else "")
                     + "); grave a resposta dele à pergunta, como ele a escreveu")
    if dito_p != modo:
        raise Recusa(f"as palavras dizem «{dito_p}», e o modo gravado é «{modo}»")
    if falas_do_advogado is None:
        return _nao_conferida("o leitor das mensagens do advogado não está nesta cópia do plugin")
    falas, fonte, motivo = falas_do_advogado.falas_da_sessao(env, TRECHOS_DA_PERGUNTA, ancora, livro)
    if falas is None:
        return _nao_conferida(motivo or "sem registro legível da conversa")
    if fonte == "livro_de_falas":
        ultima = falas[-1]
        dita = escolha_da_resposta(ultima) or troca_dita(ultima)
        if dita and dita != modo:
            raise Recusa(f"a última mensagem do advogado diz «{dita}», e o modo gravado é «{modo}»")
        return _nao_conferida("no Cowork remoto o registro guarda as mensagens dele, mas não a pergunta nem a "
                              "caixa de perguntas" + ("; a última mensagem dele diz a mesma opção" if dita else ""),
                              fonte)
    if troca:
        digitadas = [f for f in falas if f.origem == "digitada"]
        if digitadas and troca_dita(digitadas[-1]) == modo and _norm(palavras).strip(" .,;!") in _norm(digitadas[-1]):
            return {"estado": "conferida", "fonte": fonte, "motivo": None,
                    "resposta": " ".join(digitadas[-1].split())[:300]}
    resp, porque = falas_do_advogado.resposta_a_pergunta(falas, lambda f: escolha_da_resposta(f) is not None)
    if resp is None:
        raise Recusa(f"{porque}. Faça a pergunta com o texto fixo e grave a resposta dele")
    dita = escolha_da_resposta(resp)
    if dita != modo:
        raise Recusa(f"a resposta do advogado à pergunta diz «{dita}», e o modo gravado é «{modo}». Não escolha "
                     "por ele: pergunte de novo, se preciso, e grave a resposta")
    if _norm(palavras).strip(" .,;!") not in _norm(resp):
        raise Recusa("as palavras gravadas não saem da resposta dele à pergunta; grave a resposta como ele a escreveu")
    return {"estado": "conferida", "fonte": fonte, "motivo": None, "resposta": " ".join(resp.split())[:300]}


def _nota_conferencia(reg):
    c = reg.get("conferencia")
    if not isinstance(c, dict):
        return "escolha não conferida: registro anterior à conferência das palavras"
    if c.get("estado") == "conferida":
        return "escolha conferida nas mensagens dele"
    return f"escolha não conferida nas mensagens dele: {c.get('motivo') or 'sem registro legível da conversa'}"


def montar(modo, palavras, agora=None, anterior=None, conferencia=None):
    """O registro da escolha; levanta Recusa quando falta o modo ou as palavras do advogado."""
    if modo not in MODOS:
        raise Recusa("--modo é rapida ou completo")
    p = " ".join((palavras or "").split())
    if not p:
        raise Recusa("--palavras é obrigatório: o que o advogado escreveu ao escolher, como ele escreveu")
    if len(p) > 600:
        raise Recusa("--palavras leva só a frase da escolha (até 600 caracteres), não a conversa")
    reg = {"schema_version": SCHEMA, "gerado_por": "escolha_do_metodo.py", "modo": modo, "palavras": p,
           "em": (agora or datetime.datetime.now(datetime.timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    if isinstance(conferencia, dict):
        reg["conferencia"] = conferencia
    if isinstance(anterior, dict) and anterior.get("modo") in MODOS:
        hist = list(anterior.get("historico") or [])
        hist.append({k: anterior.get(k) for k in ("modo", "palavras", "em")})
        reg["historico"] = hist[-10:]
    reg["selo"] = _selo(reg)
    return reg


def gravar(pasta, reg):
    caminho = os.path.join(pasta, NOME)
    tmp = caminho + ".parcial"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(reg, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, caminho)
    return caminho


def ler(pasta):
    """(registro, None), ou (None, motivo). Registro escrito ou alterado à mão não vale."""
    caminho = os.path.join(pasta or ".", NOME)
    if not os.path.isfile(caminho):
        return None, "o advogado ainda não escolheu entre a minuta rápida e o método completo"
    try:
        with open(caminho, encoding="utf-8") as fh:
            reg = json.load(fh)
    except Exception:
        return None, "o registro da escolha está ilegível"
    if (not isinstance(reg, dict) or reg.get("schema_version") != SCHEMA or reg.get("modo") not in MODOS
            or reg.get("gerado_por") != "escolha_do_metodo.py" or not str(reg.get("palavras") or "").strip()
            or reg.get("selo") != _selo(reg)):
        return None, "o registro da escolha não foi gravado pelo script (ou foi alterado depois)"
    return reg, None


def _estado_da_peca(pasta):
    """O PECA_STATE da pasta da peça ou de até duas pastas acima, ou None."""
    d = os.path.abspath(pasta or ".")
    for _ in range(3):
        cand = os.path.join(d, PECA_STATE)
        if os.path.isfile(cand):
            try:
                with open(cand, encoding="utf-8") as fh:
                    st = json.load(fh)
                return st if isinstance(st, dict) else None
            except Exception:
                return None
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    return None


def _feita(st, fase):
    f = (st.get("fases") or {}).get(fase) if isinstance(st.get("fases"), dict) else None
    return isinstance(f, dict) and f.get("status") == "concluida"


def _status(st, fase):
    f = (st.get("fases") or {}).get(fase) if isinstance(st.get("fases"), dict) else None
    return f.get("status") if isinstance(f, dict) else None


def _tentativa(pasta, fase, st=None):
    'A tentativa registrada da etapa (`etapa_tentada.py`), na pasta do registro de andamento da'


    d = etapa_tentada.pasta_do_estado(pasta) or os.path.abspath(pasta or ".")
    t = etapa_tentada.tentativa(d, fase)
    if not t:
        return None
    if t.get("redacao_sha") != etapa_tentada.sha_da_redacao(st):
        return None
    return t


def _parada_etapa_depois(fase, nome):
    return ("PARADA: o advogado escolheu o MÉTODO COMPLETO, e a minuta com pendências ainda não sai.\n"
            f"  Falta: {nome}, que não foi feita nem tentada.\n"
            "  O que fazer AGORA: faça essa etapa pelo método (a skill de petição diz como) e registre-a no "
            "registro da peça; se ela falhar, o registro guarda a falha e a minuta sai com a pendência.\n"
            "  Se a etapa não puder nem rodar (o programa dela sai com erro antes de registrar, a sessão não tem "
            "como abrir os revisores do Conselho, o tempo da sessão acabou), registre a tentativa: "
            f"`etapa_tentada.py registrar --pasta \"<pasta da peça>\" --etapa {fase} --motivo "
            "script_falhou|sem_subagente|tempo_esgotado [--codigo-saida <n>] --detalhe \"<o que aconteceu>\"`.\n"
            "  A minuta rápida no meio do caminho só por palavra dele: se ele pedir, grave a nova escolha "
            "(`escolha_do_metodo.py registrar --modo rapida --palavras \"<o que ele escreveu>\"`) e gere de novo.")


def _parada_sem_escolha(porque, problema):
    return ("PARADA: a minuta ainda não sai, porque o advogado não escolheu como quer a peça.\n"
            f"  Por quê: {porque}, e {problema}.\n"
            "  O que fazer AGORA: faça ao advogado a pergunta abaixo, com estas palavras, e espere a resposta.\n"
            "  Não escolha por ele, nem por urgência: quem tem pressa é ele, e ele diz.\n\n"
            + "\n".join("    " + linha for linha in PERGUNTA.split("\n")) + "\n\n"
            "  Com a resposta, grave-a com o `escolha_do_metodo.py registrar --pasta \"<pasta da peça>\" "
            "--modo rapida|completo --palavras \"<o que ele escreveu>\"` da skill de petição e siga o modo escolhido.\n"
            "  Pergunte mesmo que o pedido dele fale em pressa ou no método: a escolha vale só como RESPOSTA a esta "
            "pergunta, e o script confere a resposta no registro da conversa. Grave a resposta como ele a escreveu "
            "(«1», «a rápida», «2», «o completo»).")


def _parada_etapa(nome):
    return ("PARADA: o advogado escolheu o MÉTODO COMPLETO, e a minuta com pendências ainda não sai.\n"
            f"  Falta: {nome}.\n"
            "  O que fazer AGORA: faça essa etapa pelo método (a skill de petição diz como) e registre-a. "
            "Onde a etapa pede a aprovação do advogado, pare e espere por ele.\n"
            "  A minuta rápida no meio do caminho só por palavra dele: se ele pedir, grave a nova escolha "
            "(`escolha_do_metodo.py registrar --modo rapida --palavras \"<o que ele escreveu>\"`) e gere de novo.")


def exigir_para_minuta(texto, pasta):
    'Para o gerador da minuta com pendências: (pendências a listar, texto da parada ou None).'




    if pesquisa_tentada is None:
        return [], None
    tem, porque = pesquisa_tentada.tem_tese_juridica(texto)
    if not tem:
        return [], None
    reg, problema = ler(pasta)
    if reg is None:
        return [], _parada_sem_escolha(porque, problema)
    citadas = pesquisa_tentada.pendencia_das_sumulas(texto, None, pasta)
    if reg["modo"] == "rapida":
        pend = [f"minuta rápida, por escolha do advogado («{reg['palavras'][:160]}»; {_nota_conferencia(reg)}): "
                f"{O_QUE_FICOU_SEM_FAZER}. "
                f"Para o método completo sobre esta mesma peça, peça «agora faça o método completo»"]
        return pend + ([citadas] if citadas else []), None
    st = _estado_da_peca(pasta)
    if st is None:
        return [], _parada_etapa("começar o método pela skill de petição (o registro das etapas da peça ainda não existe)")
    for fase, nome in ETAPAS_ANTES_DA_REDACAO:
        if not _feita(st, fase):
            return [], _parada_etapa(nome)
    _reg_p, pend_p, parada_p = pesquisa_tentada.exigir(texto, pasta)
    if parada_p:
        return [], parada_p
    pend = [f"método completo, por escolha do advogado ({_nota_conferencia(reg)}): a minuta sai antes do fim das etapas"]







    faltam = []
    if etapa_tentada is not None and not _feita(st, "redacao"):
        return [], _parada_etapa("a redação registrada no registro de andamento da peça (as etapas depois dela "
                                 "só se registram com ela concluída)")
    travou_em = None
    for fase, nome in ETAPAS_DEPOIS:
        if _feita(st, fase):
            continue
        if etapa_tentada is None:
            faltam.append(nome)
            continue
        if travou_em:
            pend.append(f"{nome} não feita: depende da {travou_em}, que não foi concluída")
            continue
        if _status(st, fase) == "bloqueada":
            pend.append(f"{nome}: tentada e não concluída (o motivo está no registro de andamento da peça)")
            travou_em = nome
            continue
        t = _tentativa(pasta, fase, st)
        if t is None:
            return [], _parada_etapa_depois(fase, nome)
        pend.append(etapa_tentada.frase(fase, t))
        travou_em = nome
    if not _feita(st, "adversarial") and isinstance(st.get("fases"), dict) and "adversarial" in st["fases"]:
        pend.append("teste da tese não concluído")
    if faltam:
        pend.append("etapas do método ainda não concluídas: " + ", ".join(faltam))
    return pend + pend_p, None


def situacao(pasta):
    'O que já vale e o que falta do método completo, na ordem, para a pasta da peça: a retomada'


    reg, _ = ler(pasta)
    hist = (reg or {}).get("historico") or []
    retomada = bool(reg and reg["modo"] == "completo" and any(h.get("modo") == "rapida" for h in hist))
    st = _estado_da_peca(pasta) or {}
    valem, faltam = [], []
    for fase, nome in ETAPAS_ANTES_DA_REDACAO:
        (valem if st and _feita(st, fase) else faltam).append(nome)
    if st and _feita(st, "redacao"):
        valem.append("a redação")
    else:
        faltam.append("a redação, depois do roteiro aprovado")
    pt = pesquisa_tentada.ler(pasta)[0] if pesquisa_tentada is not None else None
    (valem if pt else faltam).append("a pesquisa de jurisprudência" + ("" if pt else ", tentada e registrada"))
    for fase, nome in ETAPAS_DEPOIS:
        if st and _feita(st, fase):
            valem.append(nome)
        elif st and _status(st, fase) == "bloqueada":
            valem.append(nome + " (tentada, não concluída)")
        elif etapa_tentada is not None and _tentativa(pasta, fase, st):
            valem.append(nome + " (tentativa registrada)")
        else:
            faltam.append(nome)
    return {"modo": (reg or {}).get("modo"), "retomada": retomada, "valem": valem, "faltam": faltam,
            "proxima": faltam[0] if faltam else None}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="escolha_do_metodo.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pergunta")
    r = sub.add_parser("registrar")
    r.add_argument("--pasta", required=True)
    r.add_argument("--modo", required=True)
    r.add_argument("--palavras", required=True)
    c = sub.add_parser("conferir")
    c.add_argument("--pasta", required=True)
    c.add_argument("--peca")
    sub.add_parser("situacao").add_argument("--pasta", required=True)
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    if a.cmd == "pergunta":
        print(PERGUNTA)
        return 0
    if not os.path.isdir(a.pasta):
        print(json.dumps({"ok": False, "codigo": "contrato_invalido", "mensagem": "a pasta não existe"},
                         ensure_ascii=False))
        return 2
    if a.cmd == "registrar":
        anterior, _ = ler(a.pasta)
        try:
            montar(a.modo, a.palavras)
            conf = conferir_palavras(a.modo, a.palavras, troca=anterior is not None)
            reg = montar(a.modo, a.palavras, anterior=anterior, conferencia=conf)
        except Recusa as e:
            print(json.dumps({"ok": False, "codigo": "escolha_recusada", "mensagem": str(e)}, ensure_ascii=False))
            return 1
        gravar(a.pasta, reg)
        out = {"ok": True, "modo": reg["modo"], "trocou": bool(anterior and anterior["modo"] != reg["modo"]),
               "conferencia": conf["estado"]}
        if reg["modo"] == "completo":

            sit = situacao(a.pasta)
            out["valem"], out["faltam"], out["proxima"] = sit["valem"], sit["faltam"], sit["proxima"]
        if conf["estado"] != "conferida":
            out["aviso"] = ("escolha gravada SEM conferência nas mensagens do advogado (" + (conf.get("motivo") or "")
                            + "); a minuta dirá isso na primeira pendência")
        print(json.dumps(out, ensure_ascii=False))
        return 0
    if a.cmd == "situacao":
        print(json.dumps(dict(situacao(a.pasta), ok=True), ensure_ascii=False))
        return 0
    texto = ""
    if a.peca:
        try:
            with open(a.peca, encoding="utf-8") as fh:
                texto = fh.read()
        except OSError:
            print(json.dumps({"ok": False, "codigo": "contrato_invalido", "mensagem": "a peça não foi lida"},
                             ensure_ascii=False))
            return 2
    reg, problema = ler(a.pasta)
    if a.peca:
        pend, parada = exigir_para_minuta(texto, a.pasta)
        print(json.dumps({"ok": parada is None, "modo": (reg or {}).get("modo"), "pendencias": pend,
                          "parada": parada}, ensure_ascii=False))
        return 0 if parada is None else 1
    if reg is None:
        print(json.dumps({"ok": False, "codigo": "sem_escolha", "mensagem": problema}, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, "modo": reg["modo"], "palavras": reg["palavras"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
