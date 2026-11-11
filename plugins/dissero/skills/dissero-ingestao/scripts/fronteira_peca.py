#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'fronteira_peca.py - PROPOE onde uma peca acaba e outra comeca, num markdown ja extraido'

























































































import argparse
import importlib
import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

VERSAO = "1.0"
ENV_LIGA = "DSR_FRONTEIRA_PECA"

















ANCORAS = (
    {
        "tipo": "pje",
        "rx": re.compile(r"Num\.\s*(?P<documento>\S+)\s*-\s*P[áa]g\.\s*(?P<pagina>\d+)", re.I),
        "estrutural": True,
    },
    {
        "tipo": "stj",
        "rx": re.compile(r"P[áa]gina\s+(?P<pagina>\d+)\s+de\s+(?P<total>\d+)", re.I),
        "estrutural": True,
    },
    {
        "tipo": "esaj",
        "rx": re.compile(r"fls?\.\s*(?P<pagina>\d+)", re.I),
        "estrutural": False,
    },
)



SONDAS_DERIVA = (
    "Num. 700100001 - Pag. 1",
    "Num. 700100001 - Pág. 12",
    "num. 700100002 - pag. 3",
    "fls. 45",
    "fl. 7",
    "Pagina 1 de 9",
    "Página 12 de 340",
    "texto corrido sem identificador nenhum",
    "Numero do documento: 12345678901234567890",
    "pagina inicial da peca",



    "Pagina 3",
    "fls 45",
    "Num. 700100003 Pag. 2",
)
























_RX_VOCATIVO = re.compile(
    r"\bexcelent[íi]ssim\w*\b"
    r"|\bexm[oa]?s?\.?\s*sr\w*\.?\s*(?:dr\w*\.?\s*)?ju[íi]z"
    r"|\bmerit[íi]ssim\w*\b"
    r"|\bdouto\s+ju[íi]zo\b"
    r"|\bmm\.?\s*ju[íi]z"
    r"|\begr[ée]gi[oa]\s+(?:tribunal|corte)\b"
    r"|\bcolend[oa]\s+(?:c[âa]mara|turma|corte|superior)\b"
    r"|\b[íi]nclit[oa]s?\s+desembargador\w*\b"
    r"|\bemin[êe]ntes?\s+ministr\w*\b"
    r"|\bem[ée]rit[oa]s?\s+ministr\w*\b",
    re.I)


_RX_PEDIDOS = re.compile(
    r"\bnestes?\s+termos\b|\btermos\s+em\s+que\b|\bpede\s+deferimento\b|\bp\.\s*deferimento\b"
    r"|\baguarda\s+deferimento\b|\bnesses?\s+termos\b", re.I)

_RX_VALOR_CAUSA = re.compile(
    r"\bvalor\s+da\s+causa\b|\bd[áa]-se\s+[àa]\s+causa\b|\batribui(?:-se)?\s+[àa]\s+causa\b",
    re.I)




UFS = ("AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA",
       "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO")
_UF = "(?:%s)" % "|".join(UFS)

_RX_OAB = re.compile(
    r"\bOAB\b\s*[/\-]?\s*" + _UF + r"\b\s*(?:sob\s+)?(?:n[ºo°.]{0,3}\s*)?[\d][\d.]{2,11}"
    r"|\bOAB\b\s*(?:sob\s+)?(?:n[ºo°.]{0,3}\s*)?[\d][\d.]{2,11}\s*[/\-]\s*" + _UF + r"\b",
    re.I)

SINAIS = (
    ("vocativo", "abertura", _RX_VOCATIVO),
    ("pedidos", "fecho", _RX_PEDIDOS),
    ("valor_da_causa", "fecho", _RX_VALOR_CAUSA),
    ("assinatura_oab", "fecho", _RX_OAB),
)









MINIMO_FAMILIAS_FECHO_FORTE = 2





JANELA_GAPS_CORROBORACAO = 1












LIMITE_TRECHO = 120

NIVEIS = ("baixa", "media", "alta")


MOTIVO_SEM_TIPO = ("a FRONTEIRA e um corte, nao uma peca: quem recebe tipo e o segmento entre "
                   "duas fronteiras. Ver `segmentos` na mesma resposta")

MOTIVO_SEM_RITO = ("rito nao declarado por quem chamou. Tipar peca EXIGE o rito, e nem este "
                   "modulo nem `taxonomia_pecas` o inferem do texto: com tabela cheia de tipos "
                   "de um rito, peca de outro casa a abertura e o fecho como qualquer uma e "
                   "sairia rotulada errado com aparencia de acerto. Passe rito= para receber "
                   "proposta de tipo")





ENV_TAXONOMIA = "DSR_TAXONOMIA_PECAS"
MOTIVO_TIPO_DESLIGADO = ("proposta de tipo desligada: classificar a peca exige %s=1 no "
                         "ambiente, alem do rito. Capacidade nova nasce desligada nesta casa."
                         % ENV_TAXONOMIA)

MOTIVO_SEM_TAXONOMIA = ("`taxonomia_pecas` nao pode ser importado deste diretorio, entao nao "
                        "ha como propor tipo. Isto e falha de instalacao, nao de decisao "
                        "juridica - o modulo deveria estar ao lado")



def _nfc(s):
    'Forma canonica composta do texto de entrada.'









    return unicodedata.normalize("NFC", str(s or ""))


def _sem_acento(s):
    'Copia sem acento com o MESMO comprimento da entrada, caractere a caractere.'








    saida = []
    for ch in s:
        base = "".join(c for c in unicodedata.normalize("NFD", ch)
                       if unicodedata.category(c) != "Mn")
        saida.append(base if len(base) == 1 else ch)
    return "".join(saida)


def _colapsar(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _trecho(original, i, j, limite=LIMITE_TRECHO):
    t = _colapsar(original[i:j])
    return t if len(t) <= limite else t[:limite].rstrip() + "..."


def _chave_ancora(texto):
    'Identidade do identificador para efeito de repeticao: sem acento, sem variacao de'


    return _colapsar(_sem_acento(texto)).lower()



def localizar_ancoras(texto):
    'Ocorrencias dos identificadores preservados, em ordem do documento.'





    original = _nfc(texto)
    folhado = _sem_acento(original)
    brutas = []
    for spec in ANCORAS:
        for m in spec["rx"].finditer(folhado):
            d = m.groupdict()
            brutas.append({
                "tipo": spec["tipo"],
                "_inicio": m.start(),
                "_fim": m.end(),
                "texto": _colapsar(original[m.start():m.end()]),
                "documento": d.get("documento"),
                "pagina": int(d["pagina"]) if (d.get("pagina") or "").isdigit() else None,
                "total": int(d["total"]) if (d.get("total") or "").isdigit() else None,
                "estrutural": spec["estrutural"],
            })
    brutas.sort(key=lambda a: (a["_inicio"], -a["_fim"]))


    ancoras, fim_anterior = [], -1
    for a in brutas:
        if a["_inicio"] < fim_anterior:
            continue
        a["chave"] = _chave_ancora(a["texto"])
        ancoras.append(a)
        fim_anterior = a["_fim"]
    contagem = {}
    for a in ancoras:
        contagem[a["chave"]] = contagem.get(a["chave"], 0) + 1
    for a in ancoras:
        a["repeticoes"] = contagem[a["chave"]]
        a["ambigua"] = a["repeticoes"] > 1
    return ancoras


def trocas_estruturais(ancoras):
    'Indices de ancora em que o PROPRIO identificador diz que comecou outro documento.'




    trocas, ultimo = set(), {}
    for i, a in enumerate(ancoras):
        if not a.get("estrutural"):
            continue
        tipo = a["tipo"]
        ant = ultimo.get(tipo)
        ultimo[tipo] = a
        if ant is None:
            continue
        if a["tipo"] == "pje":
            if a.get("documento") != ant.get("documento"):
                trocas.add(i)
        else:
            pag, pag_ant = a.get("pagina"), ant.get("pagina")
            if a.get("total") != ant.get("total"):
                trocas.add(i)
            elif pag is not None and pag_ant is not None and pag <= pag_ant:
                trocas.add(i)
    return trocas


def localizar_sinais(texto, limite_trecho=LIMITE_TRECHO):
    """Sinais textuais de abertura e de fecho, em ordem do documento."""
    original = _nfc(texto)
    folhado = _sem_acento(original)
    achados = []
    for familia, lado, rx in SINAIS:
        for m in rx.finditer(folhado):
            achados.append({"familia": familia, "lado": lado, "_inicio": m.start(),
                            "trecho": _trecho(original, m.start(), m.end(), limite_trecho)})
    achados.sort(key=lambda s: s["_inicio"])
    return achados


def _tabelas_de_tarja(*nomes):
    'Constantes de `tarja_processual`, o modulo irmao so de dados.'




    mod = importlib.import_module("tarja_processual")
    return tuple(getattr(mod, nome) for nome in nomes)


def _importar_taxonomia():
    """`taxonomia_pecas`, ou None quando o modulo nao pode ser importado deste diretorio."""
    try:
        return importlib.import_module("taxonomia_pecas")
    except Exception:
        return None







CAMPOS_DO_TIPO = ("estado", "tipo_proposto", "rito_declarado", "avisos")


def _propor_tipo(taxonomia, texto, rito, hoje):
    """Proposta de tipo para UM segmento, ja peneirada. Nunca levanta."""
    if taxonomia is None:
        return None, MOTIVO_SEM_TAXONOMIA
    try:
        r = taxonomia.classificar(texto, rito=rito, hoje=hoje, autorizado=True)
    except Exception as erro:
        return None, "classificador falhou: %s" % str(erro)[:120]
    if r.get("estado") != "a_confirmar":
        motivos = "; ".join(str(m) for m in (r.get("motivos") or []))[:400]
        return None, motivos or "classificador devolveu %s sem motivo" % r.get("estado")
    proposta = {k: r[k] for k in CAMPOS_DO_TIPO if k in r}

    proposta["placar_marcadores"] = [
        {"id": p.get("id"), "casados": p.get("casados")}
        for p in (r.get("placar") or []) if p.get("casados")]
    proposta["marcadores_casados_total"] = len(r.get("marcadores_casados") or [])
    return proposta, None


def sistemas_detectados(texto):
    'Quais sistemas de `tarja_processual.PADROES_TARJA` tem prova de origem no documento.'




    folhado = _sem_acento(_nfc(texto))
    try:
        (padroes_tarja,) = _tabelas_de_tarja("PADROES_TARJA")
    except Exception as erro:
        return [], "tarja_processual indisponivel: %s" % erro
    nomes = [nome for nome, cfg in padroes_tarja.items()
             if cfg.get("deteccao") and cfg["deteccao"].search(folhado)]
    return sorted(nomes), None


def conferir_deriva(ancoras=None, sondas=None):
    'Divergencias entre as ancoras daqui e `tarja_processual.PRESERVAR_SEMPRE`, nas SONDAS.'










    especs = ANCORAS if ancoras is None else tuple(ancoras)
    alvos = SONDAS_DERIVA if sondas is None else tuple(sondas)
    try:
        (preservar_sempre,) = _tabelas_de_tarja("PRESERVAR_SEMPRE")
    except Exception as erro:
        return [{"sonda": None, "erro": "tarja_processual indisponivel: %s" % erro}]
    fora = []
    for sonda in alvos:
        folhado = _sem_acento(sonda)
        aqui = any(spec["rx"].search(folhado) for spec in especs)
        la = any(rx.search(sonda) or rx.search(folhado) for rx in preservar_sempre)
        if aqui != la:
            fora.append({"sonda": sonda, "fronteira_peca": aqui, "tarja_processual": la})
    return fora



def _ref(ancora):
    'Referencia a uma ancora, do jeito que ela sai no relatorio.'





    return None if ancora is None else dict(ancora)


def _gap_de(pos, ancoras):
    'Lacuna em que a posicao cai: o numero de ancoras que ja comecaram antes dela.'




    n = 0
    for a in ancoras:
        if a["_inicio"] <= pos:
            n += 1
        else:
            break
    return n


def _rotulo(estrutural, familias_abertura, familias_fecho, minimo_familias_fecho):
    tem_texto = bool(familias_abertura or familias_fecho)
    if estrutural and tem_texto:
        return "alta"
    if estrutural:
        return "media"
    if familias_abertura and len(familias_fecho) >= minimo_familias_fecho:
        return "media"
    return "baixa"


def _baixar_um_nivel(rotulo):
    i = NIVEIS.index(rotulo) if rotulo in NIVEIS else 0
    return NIVEIS[max(0, i - 1)]


def _limpar(obj):
    "Remove recursivamente toda chave de trabalho (prefixo '_'). E o que garante que"


    if isinstance(obj, dict):
        return {k: _limpar(v) for k, v in obj.items() if not str(k).startswith("_")}
    if isinstance(obj, list):
        return [_limpar(v) for v in obj]
    return obj


def segmentar(texto,
              minimo_familias_fecho=MINIMO_FAMILIAS_FECHO_FORTE,
              janela_gaps=JANELA_GAPS_CORROBORACAO,
              limite_trecho=LIMITE_TRECHO,
              rito=None,
              hoje=None,
              autorizado_tipo=False):
    'Fronteiras PROPOSTAS no markdown, ancoradas em identificador do tribunal.'





    original = _nfc(texto)
    sistemas, aviso_sistema = sistemas_detectados(original)
    parametros = {"minimo_familias_fecho_forte": int(minimo_familias_fecho),
                  "janela_gaps_corroboracao": int(janela_gaps),
                  "limite_trecho": int(limite_trecho),
                  "sao_arbitrarios_e_configuraveis": True}




    base = {"ok": True, "versao": VERSAO, "sistemas": sistemas, "parametros": parametros,
            "rito_declarado": (str(rito).strip() or None) if rito else None,
            "fronteiras": [], "segmentos": [], "inconclusivo": False, "motivo": None}
    if aviso_sistema:
        base["aviso"] = aviso_sistema

    if not original.strip():
        base.update(inconclusivo=True, motivo="documento vazio",
                    ancoras={"total": 0, "por_tipo": {}, "estruturais": 0})
        return _limpar(base)

    ancoras = localizar_ancoras(original)
    por_tipo = {}
    for a in ancoras:
        por_tipo[a["tipo"]] = por_tipo.get(a["tipo"], 0) + 1
    base["ancoras"] = {"total": len(ancoras), "por_tipo": por_tipo,
                       "estruturais": sum(1 for a in ancoras if a["estrutural"])}

    if not ancoras:
        base.update(
            inconclusivo=True,
            motivo=("documento sem identificador preservado do tribunal ('Num. <id> - Pag. "
                    "<n>', 'fls. <n>', 'Pagina <n> de <m>'); fronteira ancorada em posicao "
                    "de caractere nao sobrevive a uma reextracao e por isso nao e proposta"))
        return _limpar(base)

    sinais = localizar_sinais(original, limite_trecho)
    for s in sinais:
        s["_gap"] = _gap_de(s["_inicio"], ancoras)
    trocas = trocas_estruturais(ancoras)

    n_gaps = len(ancoras)
    aberturas_por_gap, fechos_por_gap = {}, {}
    for s in sinais:
        alvo = aberturas_por_gap if s["lado"] == "abertura" else fechos_por_gap
        alvo.setdefault(s["_gap"], []).append(s)

    candidatos = set()

    for i in trocas:
        if i >= 1:
            candidatos.add(i)

    for g in aberturas_por_gap:
        if g >= 1:
            candidatos.add(g)





    for g in fechos_por_gap:
        if 1 <= g + 1 < n_gaps:
            candidatos.add(g + 1)

    fronteiras = []
    for ordem, g in enumerate(sorted(candidatos), start=1):
        anterior = ancoras[g - 1] if g >= 1 else None
        seguinte = ancoras[g] if g < len(ancoras) else None
        aberturas = list(aberturas_por_gap.get(g, []))

        fechos = []
        for atras in range(1, int(janela_gaps) + 1):
            fechos.extend(fechos_por_gap.get(g - atras, []))


        if aberturas:
            corte = aberturas[0]["_inicio"]
            fechos.extend([f for f in fechos_por_gap.get(g, []) if f["_inicio"] < corte])
        fam_abertura = sorted({s["familia"] for s in aberturas})
        fam_fecho = sorted({s["familia"] for s in fechos})
        estrutural = g in trocas
        rotulo = _rotulo(estrutural, fam_abertura, fam_fecho, int(minimo_familias_fecho))
        ambigua = bool((anterior and anterior["ambigua"]) or (seguinte and seguinte["ambigua"]))
        if ambigua:
            rotulo = _baixar_um_nivel(rotulo)
        fronteiras.append({
            "ordem": ordem,
            "ancora_anterior": _ref(anterior),
            "ancora_seguinte": _ref(seguinte),
            "troca_estrutural": estrutural,
            "familias_abertura": fam_abertura,
            "familias_fecho": fam_fecho,
            "fecho_forte": len(fam_fecho) >= int(minimo_familias_fecho),
            "sinais": [dict(s) for s in sorted(aberturas + fechos,
                                               key=lambda x: x["_inicio"])],
            "ancora_ambigua": ambigua,
            "confianca": rotulo,
            "estado": "a_confirmar",
            "tipo_peca": None,
            "motivo_tipo_peca": MOTIVO_SEM_TIPO,
        })

    base["fronteiras"] = fronteiras
    base["segmentos"] = _montar_segmentos(fronteiras, original, rito, hoje,
                                          autorizado_tipo=autorizado_tipo)
    if not fronteiras:
        base["motivo"] = ("ha identificador, mas nenhum sinal de abertura ou fecho e nenhuma "
                          "troca de documento: o markdown parece ser uma peca so")
    return _limpar(base)


def _corte(ancora_inicial, ancora_final, tamanho):
    '(inicio, fim) do segmento no texto, a partir da posicao das ancoras.'




    ini = 0 if not ancora_inicial else int(ancora_inicial.get("_inicio") or 0)
    fim = tamanho if not ancora_final else int(ancora_final.get("_inicio") or tamanho)
    return (ini, fim) if ini < fim else (0, 0)


def _montar_segmentos(fronteiras, original="", rito=None, hoje=None, autorizado_tipo=False):
    'Trechos entre fronteiras, descritos SO por identificador. Nunca por pagina absoluta -'









    taxonomia = _importar_taxonomia() if (rito and autorizado_tipo) else None
    tamanho = len(original)
    segmentos = []
    inicial = None

    def um(ordem, ini_anc, fim_anc):
        seg = {"ordem": ordem, "ancora_inicial": ini_anc, "ancora_final": fim_anc,
               "estado": "a_confirmar", "tipo_peca": None}
        if not rito:
            seg["motivo_tipo_peca"] = MOTIVO_SEM_RITO
            return seg
        if autorizado_tipo is not True:
            seg["motivo_tipo_peca"] = MOTIVO_TIPO_DESLIGADO
            return seg
        i, j = _corte(ini_anc, fim_anc, tamanho)
        recorte = original[i:j]
        if not recorte.strip():
            seg["motivo_tipo_peca"] = ("segmento sem texto entre as ancoras: nao ha o que "
                                       "classificar")
            return seg
        proposta, motivo = _propor_tipo(taxonomia, recorte, rito, hoje)
        if proposta is None:
            seg["motivo_tipo_peca"] = motivo
            return seg
        seg["tipo_peca"] = proposta
        return seg

    for k, f in enumerate(fronteiras, start=1):
        segmentos.append(um(k, inicial, f.get("ancora_anterior")))
        inicial = f.get("ancora_seguinte")
    segmentos.append(um(len(fronteiras) + 1, inicial, None))
    return segmentos



def ligado(argv_ligar=False, ambiente=None):
    'Capacidade nova nasce desligada, por regra de governanca. Duas portas, e qualquer uma'


    env = (ambiente if ambiente is not None else os.environ)
    return bool(argv_ligar) or str(env.get(ENV_LIGA, "")).strip() in ("1", "true", "TRUE")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Propoe fronteiras de peca num markdown de autos, ancoradas em "
                    "identificador do tribunal. Heuristica: propoe, nao decide.")
    ap.add_argument("arquivo", help="markdown ja extraido dos autos")
    ap.add_argument("--ligar", action="store_true",
                    help="liga a capacidade nesta execucao (equivale a %s=1)" % ENV_LIGA)
    ap.add_argument("--minimo-familias-fecho", type=int, default=MINIMO_FAMILIAS_FECHO_FORTE,
                    help="familias de fecho para 'fecho forte' (arbitrario, padrao %d)"
                         % MINIMO_FAMILIAS_FECHO_FORTE)
    ap.add_argument("--janela-gaps", type=int, default=JANELA_GAPS_CORROBORACAO,
                    help="lacunas para tras em que um fecho corrobora (padrao %d)"
                         % JANELA_GAPS_CORROBORACAO)
    ap.add_argument("--limite-trecho", type=int, default=LIMITE_TRECHO)
    try:
        args = ap.parse_args(argv)
    except SystemExit:
        return 2

    if not ligado(args.ligar):
        print(json.dumps({"ok": False, "desligado": True, "versao": VERSAO,
                          "motivo": "capacidade nasce desligada; use --ligar ou %s=1"
                                    % ENV_LIGA}, ensure_ascii=False))
        return 1
    try:
        with open(args.arquivo, encoding="utf-8", errors="replace") as f:
            texto = f.read()
    except OSError as erro:
        print(json.dumps({"ok": False, "versao": VERSAO,
                          "motivo": "arquivo ilegivel: %s" % erro}, ensure_ascii=False))
        return 2

    rel = segmentar(texto, minimo_familias_fecho=args.minimo_familias_fecho,
                    janela_gaps=args.janela_gaps, limite_trecho=args.limite_trecho)
    print(json.dumps(rel, ensure_ascii=False, indent=2, sort_keys=True))
    if rel.get("inconclusivo") or not rel.get("fronteiras"):
        print("escalar: nenhuma fronteira proposta - %s" % rel.get("motivo"), file=sys.stderr)
        return 1
    print("%d fronteira(s) PROPOSTA(S), todas em 'a_confirmar' - nenhuma tipada"
          % len(rel["fronteiras"]), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
