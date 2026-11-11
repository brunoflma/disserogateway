#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'jusmanizer.py: detector determinístico de traços de escrita de IA em texto jurídico pt-BR.'




































from __future__ import annotations

import re
from collections import Counter



VERSAO = "1.4.1"






RX_RISCA = re.compile(r"[‒–—―]|-{2,}|(?<=\S) - (?=\S)")

_FORMA = {
    "—": "travessao", "–": "meia_risca", "‒": "meia_risca", "―": "travessao",
}



RX_INTERVALO = re.compile(r"(?<=[\dºª])\s?(?:[‒-―]|-{1,2})\s?(?=(?:R\$\s?)?\d)")



RX_REGUA = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,}|={3,})\s*$")


def riscas(texto):
    """Toda risca do texto, fora de intervalo numérico: [{inicio, fim, forma}]."""
    texto = texto or ""
    isentos = [(m.start(), m.end()) for m in RX_INTERVALO.finditer(texto)]
    saida = []
    for m in RX_RISCA.finditer(texto):
        if any(a <= m.start() and m.end() <= b for a, b in isentos):
            continue
        g = m.group(0)
        if g.strip() == "-":
            forma = "hifen_espacado"
        elif g.startswith("-"):
            forma = "hifen_duplo"
        else:
            forma = _FORMA.get(g, "travessao")
        saida.append({"inicio": m.start(), "fim": m.end(), "forma": forma})
    return saida







_FORMULAS_ANTES = (
    "requer", "requer-se", "requerendo", "requeiro", "requerem", "pede", "pedidos", "pedido",
    "verbis", "in verbis", "litteris", "ipsis litteris", "a saber", "quais sejam", "qual seja",
    "seguinte", "seguintes", "abaixo", "vejamos", "senão vejamos", "confira-se", "veja-se",
    "dispõe", "dispôs", "estabelece", "prevê", "determina", "reza", "assevera", "ensina",
    "leciona", "decidiu", "assim", "ou seja", "isto é", "termos em que", "tais como",
    "como segue", "transcreve-se", "destaca-se", "é o seguinte", "foi o seguinte", "consta",
    "afirmou", "registrou", "consignou", "anotou", "sintetizou", "concluiu", "in casu",
)
RX_DOIS_PONTOS = re.compile(r":(?=\s|$)")


_RX_NUMERAL_ANTES = re.compile(
    r"\b(?:dois|duas|três|tres|quatro|cinco|seis|sete|oito|nove|dez|\d+)\s+[\wÀ-ÿ-]+$", re.I | re.U)
RX_URL = re.compile(r"https?://\S+|www\.\S+")
RX_HORA = re.compile(r"\b\d{1,2}:\d{2}\b")



RX_ROTULO_INICIO = re.compile(
    r"^\s*(?:\*\*)?(?:[\wÀ-ÿ][\wÀ-ÿ./]*\s?){1,3}(?:\*\*)?:\s*(?:\*\*)?\s*", re.U)
_ABRE_CITACAO = ('"', "“", "«", "'", "‘", "*", "(", "[")
_RX_PALAVRA = re.compile(r"\S+")


def dois_pontos_de_emenda(texto):
    """[{inicio, fim, severidade}] de cada dois-pontos que liga duas orações completas."""
    texto = texto or ""
    fora = [(m.start(), m.end()) for m in RX_URL.finditer(texto)]
    fora += [(m.start(), m.end()) for m in RX_HORA.finditer(texto)]
    m_rot = RX_ROTULO_INICIO.match(texto)
    if m_rot:
        fora.append((0, m_rot.end()))
    saida = []
    for m in RX_DOIS_PONTOS.finditer(texto):
        pos = m.start()
        if any(a <= pos < b for a, b in fora):
            continue
        depois = texto[pos + 1:].lstrip()
        if not depois:
            continue
        if depois[0] in _ABRE_CITACAO:
            continue
        antes = re.sub(r"[\s,;]+$", "", texto[:pos].lower())
        if any(antes.endswith(f) for f in _FORMULAS_ANTES):
            continue
        if ";" in depois:
            continue
        if _RX_NUMERAL_ANTES.search(antes):
            continue
        palavras_depois = _RX_PALAVRA.findall(depois)
        if depois[0].islower():
            saida.append({"inicio": pos, "fim": pos + 1, "severidade": "erro"})
        elif len(palavras_depois) >= 6:
            saida.append({"inicio": pos, "fim": pos + 1, "severidade": "aviso"})
    return saida








PADROES = {
    "J01": {"nome": "risca como conector universal", "grupo": "A", "severidade": "erro",
            "remedio": "trocar por vírgula, ponto final, conjunção ou parênteses; zero risca "
                       "no corpo autoral (transcrição e intervalo numérico são isentos)"},
    "J02": {"nome": "dois-pontos de emenda", "grupo": "A", "severidade": "erro",
            "remedio": "dois-pontos só antes de enumeração, de citação ou de fórmula forense "
                       "(requer:, in verbis:, a saber:); ligando duas orações, use ponto final, "
                       "vírgula ou conjunção (porque, pois)"},
    "J03": {"nome": "não X, mas Y", "grupo": "A", "severidade": "erro",
            "remedio": "afirmar Y sem a negação; o contraste só fica quando X é alegação da "
                       "parte contrária ou da decisão recorrida"},
    "J04": {"nome": "âncora repetida", "grupo": "A", "severidade": "aviso",
            "remedio": "depois da primeira menção o nome basta ('a notificação'); o dado volta "
                       "só onde o leitor precisa dele para conferir"},
    "J05": {"nome": "frase de efeito", "grupo": "A", "severidade": "erro",
            "remedio": "dizer o ponto concreto, com fato e dispositivo, sem a fórmula"},
    "J06": {"nome": "preâmbulo encenado", "grupo": "A", "severidade": "aviso",
            "remedio": "tirar o anúncio e deixar a afirmação; uma fórmula isolada se tolera, "
                       "três ou mais no texto são erro"},
    "J08": {"nome": "tríade forçada", "grupo": "B", "severidade": "aviso",
            "remedio": "tantos itens quantos o fato tiver; três só quando o direito enumera "
                       "três"},
    "J09": {"nome": "aberturas repetidas", "grupo": "B", "severidade": "aviso",
            "remedio": "juntar os períodos, mudar o sujeito ou começar pelo verbo"},
    "J10": {"nome": "qualificador empilhado", "grupo": "B", "severidade": "aviso",
            "remedio": "uma ressalva só, direta, quando o direito a exige"},
    "J12": {"nome": "vocabulário de IA no jargão forense", "grupo": "C", "severidade": "aviso",
            "remedio": "um conectivo por parágrafo, e a ligação implícita vale mais; "
                       "'robusto', 'fulcral', 'destarte' e 'diapasão' saem sempre"},
    "J13": {"nome": "significado inflado", "grupo": "C", "severidade": "aviso",
            "remedio": "tirar o adjetivo de virada e deixar o fato e o dispositivo"},
    "J15": {"nome": "gerúndio de fechamento", "grupo": "C", "severidade": "aviso",
            "remedio": "cortar o gerúndio ou convertê-lo em afirmação com fundamento próprio"},
    "J16": {"nome": "atribuição vaga", "grupo": "C", "severidade": "aviso",
            "remedio": "autor, obra e página; tribunal, número e data conferidos. Sem fonte "
                       "confirmada, a afirmação não entra"},
    "J17": {"nome": "evasão de cópula", "grupo": "C", "severidade": "aviso",
            "remedio": "usar 'é', 'são', 'tem'"},
    "J18": {"nome": "conclusão genérica", "grupo": "C", "severidade": "aviso",
            "remedio": "a conclusão nomeia a consequência jurídica específica"},
    "J20": {"nome": "Title Case em título", "grupo": "D", "severidade": "aviso",
            "remedio": "preposição e artigo em minúscula no meio do título (Da Perda da "
                       "Qualidade de Segurado); rótulo forense em versal (DOS FATOS) fica"},
    "J21": {"nome": "aspas curvas", "grupo": "D", "severidade": "aviso",
            "remedio": "aspas retas; corrigível com corrigir_seguro()"},
    "J22": {"nome": "emoji, seta ou régua decorativa", "grupo": "D", "severidade": "aviso",
            "remedio": "tirar a decoração; texto profissional não a leva"},
    "J23": {"nome": "rastro de chat", "grupo": "E", "severidade": "erro",
            "remedio": "cortar o invólucro de conversa e o vocabulário de sistema; pendência "
                       "real se escreve em português de advogado e se resolve antes da entrega"},
    "J24": {"nome": "isenção de corte de conhecimento ou palpite", "grupo": "E",
            "severidade": "aviso",
            "remedio": "dizer o que a fonte mostra, ou cortar; palpite não vira fato"},
    "J25": {"nome": "título repetido na primeira frase", "grupo": "E", "severidade": "aviso",
            "remedio": "cortar a frase que repete o título; o argumento começa na seguinte"},
    "J34": {"nome": "período encaixado", "grupo": "H", "severidade": "aviso",
            "remedio": "dividir em períodos com sujeito e verbo próximos, um fato por período, "
                       "sem perder a relação lógica (porque, por isso, desde que)"},



    "P01": {"nome": "hífen de quebra de linha", "grupo": "língua", "severidade": "aviso",
            "remedio": "juntar a palavra partida na quebra de linha (contra- to vira contrato)"},
    "P02": {"nome": "crase indevida", "grupo": "língua", "severidade": "aviso",
            "remedio": "sem crase antes de verbo, de pronome pessoal ou demonstrativo, de "
                       "'partir' e de pronome de tratamento (a Vossa Excelência)"},
}

_I = re.I | re.U
_RX = {
    "J03": re.compile(
        r"\bnão\s+(?:se\s+trata\s+)?(?:apenas|somente|só|meramente|tão\s+somente)\b[^.;:]{0,120}?"
        r",?\s+(?:mas|senão|e\s+sim)\b|\bnão\s+é\s+[^.;,]{1,60},\s*é\b", _I),
    "J05": re.compile(
        r"\b(?:em\s+última\s+análise|a\s+questão\s+de\s+fundo|no\s+cerne\s+da\s+controvérsia|"
        r"o\s+cerne\s+da\s+questão|o\s+que\s+realmente\s+importa|a\s+verdadeira\s+questão|"
        r"em\s+essência|no\s+fundo,|busca\s+a\s+tutela\s+do\s+(?:poder\s+)?judiciário|"
        r"todos\s+os\s+fatos\s+(?:aqui\s+)?narrados)", _I),
    "J06": re.compile(
        r"\b(?:cumpre\s+(?:esclarecer|destacar|ressaltar|salientar|registrar|consignar)|"
        r"cabe\s+(?:ressaltar|salientar|destacar)|(?:é\s+)?importante\s+(?:ressaltar|salientar|"
        r"destacar)|é\s+de\s+se\s+(?:ver|notar|registrar|destacar)|insta\s+(?:salientar|destacar|"
        r"consignar|registrar)|vale\s+(?:dizer|ressaltar|destacar|lembrar)|importa\s+"
        r"(?:consignar|destacar|registrar)|não\s+se\s+pode\s+(?:olvidar|perder\s+de\s+vista)|"
        r"impende\s+destacar|urge\s+destacar|mister\s+se\s+faz|forçoso\s+reconhecer|"
        r"passa-se\s+a\s+demonstrar|como\s+se\s+(?:verá|demonstrará)|conforme\s+se\s+verá|"
        r"por\s+fim,?\s+e\s+não\s+menos\s+importante)", _I),
    "J10": re.compile(
        r"\b(?:pode-se|poder-se-ia|potencialmente|possivelmente|eventualmente|talvez|em\s+tese|"
        r"aparentemente|presumivelmente|arguivelmente)\b", _I),
    "J13": re.compile(
        r"\b(?:marco\s+crucial|papel\s+(?:fundamental|central)|divisor\s+de\s+águas|"
        r"constante\s+evolução|prova\s+inequívoca\s+do\s+compromisso|de\s+suma\s+importância|"
        r"extrema\s+relevância|marca\s+indelével|verdadeiro\s+marco|exorbitantes?\b|"
        r"eterna\s+devedora|ciclo\s+vicioso|nítida\s+má-fé|nítido\s+abuso)", _I),



    "P01": re.compile(
        r"\b[a-zà-ÿ]{2,}- (?!(?:e|ou|a|o|as|os|de|da|do|em|no|na|um|uma)\b)[a-zà-ÿ]{2,}\b"),


    "P02": re.compile(
        r"\bà\s+(?:partir\b|el[ea]s?\b|v(?:ossa|\.)\s*(?:excelência|exa\.?|senhoria)|"
        r"(?:este|esse|esta|essa|isto|isso)\b|"
        r"(?:pagar|ser|fazer|ter|dar|receber|cumprir|contar|dizer|ver|haver|apresentar|"
        r"requerer|julgar|proceder|declarar|condenar|restituir|devolver|indenizar)\b)", _I),
    "J15": re.compile(
        r",\s+(?:demonstrando|evidenciando|garantindo|configurando|restando|revelando|"
        r"comprovando|reforçando|corroborando|ressaltando|destacando|refletindo|contribuindo|"
        r"assegurando|caracterizando|ensejando|confirmando|atestando)\b[^.;]*(?:[.;]|$)", _I),
    "J16": re.compile(
        r"\b(?:a\s+(?:melhor\s+)?doutrina(?:\s+(?:majoritária|dominante|pátria))?\s+"
        r"(?:entende|ensina|aponta|é\s+uníssona|é\s+pacífica|é\s+unânime)|"
        r"a\s+jurisprudência(?:\s+(?:pátria|dominante|majoritária))?\s+(?:é\s+pacífica|é\s+uníssona|"
        r"é\s+firme|tem\s+decidido|vem\s+decidindo|se\s+consolidou|consolidou)|"
        r"os\s+tribunais\s+(?:têm|vêm)\s+(?:decidido|entendido|reconhecido)|é\s+cediço|"
        r"é\s+consabido|é\s+de\s+conhecimento\s+geral|segundo\s+os\s+especialistas|"

        r"é\s+pacífic[oa]\b|jurisprudência\s+(?:é\s+)?(?:uníssona|consolidada|assente|"
        r"uniforme|tranquila)|entendimento\s+(?:é\s+)?(?:pacífico|consolidado|assente)|"
        r"(?:matéria|tese|questão)\s+(?:já\s+)?(?:se\s+encontra\s+)?pacificada|"
        r"não\s+há\s+divergência|orientação\s+(?:jurisprudencial\s+)?uniforme|"
        r"todos\s+os\s+tribunais)", _I),
    "J17": re.compile(
        r"\b(?:serve\s+como|atua\s+como|(?:se\s+)?apresenta(?:-se)?\s+como|configura-se\s+como|"
        r"consubstancia(?:-se)?|funciona\s+como|(?:se\s+)?revela(?:-se)?\s+como|"
        r"constitui-se\s+como)\b", _I),
    "J18": re.compile(
        r"\b(?:(?:diante|ante)\s+(?:de\s+)?todo\s+o\s+exposto,\s+resta|por\s+todo\s+o\s+exposto,\s+"
        r"resta|resta\s+(?:evidente|claro|patente|cristalino)\b|não\s+(?:há|restam?)\s+"
        r"dúvidas?\s+de\s+que|é\s+cert[oa]\s+que|é\s+inegáve(?:l|is)\b|indubitavelmente|"
        r"inquestionavelmente|obviamente|evidentemente|[aà]\s+toda\s+evidência|"
        r"sem\s+(?:sombra\s+de\s+)?(?:a\s+menor\s+)?dúvida)", _I),

    "J21": re.compile(r"“[^”\n]{0,400}”|‘[^’\n]{0,400}’|[“”‘’]"),
    "J22": re.compile(r"[←-⇿☀-➿\U0001F300-\U0001FAFF]"),
    "J23": re.compile(
        r"\b(?:espero\s+ter\s+ajudado|segue(?:m)?\s+abaixo|ótima\s+pergunta|você\s+está\s+"
        r"absolutamente\s+certo|me\s+avise\s+se|gostaria\s+que\s+eu|posso\s+ajudar\s+em)\b|"
        r"\b(?:claro|com\s+certeza)!|"

        r"\b(?:placeholders?|(?-i:TODO|FIXME|TBD)|lorem\s+ipsum|nesta\s+sessão|conforme\s+solicitado)\b|"
        r"\b[\w-]+\.(?:py|json|ya?ml|md|ipynb)\b", _I),
    "J24": re.compile(
        r"\b(?:até\s+a\s+data\s+de\s+corte|com\s+base\s+nas\s+informações\s+disponíveis|"
        r"segundo\s+minha\s+última|até\s+onde\s+se\s+sabe|acredita-se\s+que|"
        r"não\s+foi\s+possível\s+confirmar)", _I),
}




_VOCAB_IA = {
    "nesse sentido": False, "nesse contexto": False, "neste contexto": False,
    "no que tange": False, "sob essa ótica": False, "à luz de": False, "com efeito": False,
    "outrossim": False, "ademais": False, "além disso": False, "por conseguinte": False,
    "resta demonstrado": False, "inequívoc": False, "cristalin": False, "indiscutíve": False,
    "irrefutáve": False, "insofismáve": False, "incontestáve": False,
    "fundamental": False, "crucial": False,
    "essencial": False, "robust": True, "fulcral": True, "destarte": True, "diapasão": True,
}
_RX_VOCAB = {k: re.compile(r"\b" + re.escape(k), _I) for k in _VOCAB_IA}


_RX_TRIADE = re.compile(
    r"\b([\wÀ-ÿ]{4,14}),\s+([\wÀ-ÿ]{4,14})\s+e\s+([\wÀ-ÿ]{4,14})\b", _I)
_RX_SUFIXO_ADJ = re.compile(r"(?:al|el|ar|ere|az|ez|iz|nte|vel|ur[ao]s?|iv[ao]s?|os[ao]s?|"
                            r"ic[ao]s?|ór[ia][ao]s?|ári[ao]s?|ad[ao]s?|id[ao]s?|ent[ea]s?)$", _I)
_RX_FRASES = re.compile(r"(?<=[.!?])\s+")



_RX_PENDENCIA = re.compile(
    r"\[[^\]]{0,80}\b(?:a\s+inserir|inserir|preencher|completar|pendente)\b[^\]]*\]", _I)




LIMITE_ANCORA = 6
_ANCORAS = (
    ("valor", re.compile(r"R\$\s?\d{1,3}(?:\.\d{3})*,\d{2}")),
    ("data", re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b")),
    ("ID dos autos", re.compile(r"\bID\s?\d{6,}\b")),
    ("conta", re.compile(r"\b\d{4,10}-\d\b")),

    ("dispositivo", re.compile(
        r"\bart(?:igo)?\.?\s?\d+(?:\.\d{3})*[ºo]?(?:\s?,\s?§\s?\d+[ºo]?)?"
        r"(?:\s?,\s?(?:inciso\s+)?[IVXLC]{1,6}\b)?", re.I)),
)


def ancoras_repetidas(paragrafos, limite=LIMITE_ANCORA, ignorar=()):
    '[{classe, valor, ocorrencias, indice}] das âncoras repetidas `limite` vezes ou mais.'




    fora = {str(x).strip() for x in ignorar if str(x).strip()}
    saida = []
    for classe, rx in _ANCORAS:
        contagem, primeiro = Counter(), {}
        for i, txt in enumerate(paragrafos):
            for m in rx.finditer(txt):
                v = m.group(0).strip()
                contagem[v] += 1
                primeiro.setdefault(v, (i, m.start(), m.end()))
        for valor, n in contagem.items():
            if n >= limite and valor not in fora:
                saida.append({"classe": classe, "valor": valor, "ocorrencias": n,
                              "indice": primeiro[valor][0], "pos": primeiro[valor][1:]})
    saida.sort(key=lambda d: (-d["ocorrencias"], d["classe"], d["valor"]))
    return saida





LIMITE_PERIODO = 60
_RX_PERIODO = re.compile(r"(?<=[.!?;])\s+")
_RX_ITEM_LISTA = re.compile(r"^\s*(?:[a-zA-Z]\)|\(?[a-zA-Z0-9]{1,3}\)|\d+[.)]|[-*•])\s")


_RX_FONTE = re.compile(
    r"\b(?:STJ|STF|TST|TSE|TNU|TJ[A-Z]{2}|TRF\d?|TRT\d{0,2}|REsp|AREsp|AgInt|AgRg|EDcl|HC|RE|ARE|"
    r"ADI|ADC|ADPF|Tema|Súmula|Rel\.|Min\.|Des\.|apud|op\.\s?cit|fls?\.|p\.\s?\d|Ed\.)\b")


def _tem_fonte(txt):
    return bool(_RX_FONTE.search(txt))


def _e_adjetivo(palavra):
    return bool(_RX_SUFIXO_ADJ.search(palavra)) and not palavra.isupper()







_FUNCAO = {"da", "de", "do", "das", "dos", "e", "em", "no", "na", "nos", "nas", "a", "o",
           "as", "os", "para", "com", "por", "sem", "sob", "ao", "aos", "à", "às", "ou"}





_RX_NUMERACAO = re.compile(r"^\s*[IVXLCDM\d]+(?:\.[IVXLCDM\d]+)*\.?\s*[·|)\-–—.]?\s+")


def _titulo_em_title_case(txt):
    s = _RX_NUMERACAO.sub("", txt.strip(), count=1)
    if s.isupper():
        return False
    palavras = re.findall(r"[\wÀ-ÿ]+", s)
    if len(palavras) < 3:
        return False
    meio = palavras[1:]
    funcao_capitalizada = [w for w in meio if w.lower() in _FUNCAO and w[0].isupper()]
    return len(funcao_capitalizada) >= 1


def _contexto(texto, ini, fim, raio=60):
    return texto[max(0, ini - raio):fim + raio].strip().replace("\n", " ")


def _ocorrencia(padrao, indice, texto, ini, fim, severidade=None):
    p = PADROES[padrao]
    return {"padrao": padrao, "nome": p["nome"], "grupo": p["grupo"],
            "severidade": severidade or p["severidade"], "indice": indice,
            "trecho": texto[ini:fim], "contexto": _contexto(texto, ini, fim),
            "remedio": p["remedio"]}


def _padroes_regex(paras, titulos, excluir):
    ocs = []
    contagem_vocab = Counter()
    for i, txt in enumerate(paras):
        if RX_REGUA.match(txt):
            if "J22" not in excluir:
                ocs.append(_ocorrencia("J22", i, txt, 0, len(txt)))
            continue
        for pid in ("J03", "J05", "J06", "J13", "J15", "J16", "J17", "J18", "J21", "J22",
                    "J23", "J24", "P01", "P02"):
            if pid in excluir:
                continue
            for m in _RX[pid].finditer(txt):
                if pid == "J16" and _tem_fonte(txt):
                    continue
                if pid == "J15" and m.start() > 0 and txt[:m.start()].rstrip().endswith(":"):
                    continue
                ocs.append(_ocorrencia(pid, i, txt, m.start(), m.end()))
        if "J23" not in excluir:
            for m in _RX_PENDENCIA.finditer(txt):
                ocs.append(_ocorrencia("J23", i, txt, m.start(), m.end(), "aviso"))
        if "J10" not in excluir:
            for frase in _RX_FRASES.split(txt):
                hits = list(_RX["J10"].finditer(frase))
                if len(hits) >= 2:
                    base = txt.find(frase)
                    ocs.append(_ocorrencia("J10", i, txt, base + hits[0].start(),
                                           base + hits[-1].end()))
        if "J08" not in excluir:
            for m in _RX_TRIADE.finditer(txt):
                if all(_e_adjetivo(m.group(k)) for k in (1, 2, 3)):
                    ocs.append(_ocorrencia("J08", i, txt, m.start(), m.end()))
        if "J09" not in excluir:
            frases = [f for f in _RX_FRASES.split(txt) if f.strip()]
            aberturas = [re.findall(r"[\wÀ-ÿ]+", f)[:2] for f in frases]
            for k in range(len(aberturas) - 2):
                trio = [" ".join(a).lower() for a in aberturas[k:k + 3]]
                if trio[0] and trio[0] == trio[1] == trio[2]:
                    ini = txt.find(frases[k])
                    ocs.append(_ocorrencia("J09", i, txt, ini, ini + len(frases[k])))
                    break
        if "J34" not in excluir and i not in titulos:
            for frase in _RX_PERIODO.split(txt):
                if len(_RX_PALAVRA.findall(frase)) > LIMITE_PERIODO:
                    ini = txt.find(frase)
                    ocs.append(_ocorrencia("J34", i, txt, ini, ini + len(frase)))
        if "J12" not in excluir:
            for k, rx in _RX_VOCAB.items():
                for m in rx.finditer(txt):
                    contagem_vocab[k] += 1
                    if _VOCAB_IA[k] or contagem_vocab[k] >= 2:
                        ocs.append(_ocorrencia("J12", i, txt, m.start(), m.end()))
        if i in titulos and "J20" not in excluir and _titulo_em_title_case(txt):
            ocs.append(_ocorrencia("J20", i, txt, 0, len(txt)))
        if i in titulos and "J25" not in excluir and i + 1 < len(paras):
            prox = paras[i + 1]
            primeira = _RX_FRASES.split(prox)[0]
            pt = {w.lower() for w in re.findall(r"[\wÀ-ÿ]{3,}", txt)}
            pf = {w.lower() for w in re.findall(r"[\wÀ-ÿ]{3,}", primeira)}
            if pt and len(pf) <= 12 and len(pt & pf) >= 0.6 * len(pt):
                ocs.append(_ocorrencia("J25", i + 1, prox, 0, len(primeira)))


    if "J09" not in excluir:
        def abertura(k):
            if k in titulos or _RX_ITEM_LISTA.match(paras[k]):
                return ""
            return " ".join(re.findall(r"[\wÀ-ÿ]+", paras[k])[:2]).lower()
        k = 0
        while k + 2 < len(paras):
            a = abertura(k)
            if a and a == abertura(k + 1) == abertura(k + 2):
                ocs.append(_ocorrencia("J09", k, paras[k], 0, len(a)))
                k += 3
            else:
                k += 1

    if sum(1 for o in ocs if o["padrao"] == "J06") >= 3:
        for o in ocs:
            if o["padrao"] == "J06":
                o["severidade"] = "erro"
    return ocs


def analisar(paragrafos, *, titulos=frozenset(), excluir=frozenset(), ignorar_ancoras=()):
    'Analisa uma lista de parágrafos de PROSA AUTORAL (o chamador já tirou a transcrição).'








    paras = [str(p or "") for p in paragrafos]
    titulos = set(titulos)
    excluir = set(excluir)
    ocs = []
    for i, txt in enumerate(paras):
        if RX_REGUA.match(txt):
            continue
        if "J01" not in excluir:
            for r in riscas(txt):
                ocs.append(_ocorrencia("J01", i, txt, r["inicio"], r["fim"]))
        if "J02" not in excluir:
            for d in dois_pontos_de_emenda(txt):
                ocs.append(_ocorrencia("J02", i, txt, d["inicio"], d["fim"], d["severidade"]))
    ocs.extend(_padroes_regex(paras, titulos, excluir))
    if "J04" not in excluir:
        for a in ancoras_repetidas(paras, ignorar=ignorar_ancoras):
            o = _ocorrencia("J04", a["indice"], paras[a["indice"]], *a["pos"])
            o["contexto"] = f"{a['ocorrencias']}× {a['valor']} ({a['classe']})"
            ocs.append(o)
    ocs.sort(key=lambda o: (o["indice"], 0 if o["severidade"] == "erro" else 1, o["padrao"]))
    por_padrao = Counter(o["padrao"] for o in ocs)
    if any(o["severidade"] == "erro" for o in ocs):
        veredito = "erro"
    elif ocs:
        veredito = "aviso"
    else:
        veredito = "limpo"
    return {"ocorrencias": ocs, "por_padrao": dict(por_padrao),
            "palavras": sum(len(_RX_PALAVRA.findall(t)) for t in paras), "veredito": veredito}






_ASPAS = {"“": '"', "”": '"', "‘": "'", "’": "'"}
_RX_ASPAS = re.compile("[" + "".join(_ASPAS) + "]")
_RX_HIFEN_DUPLO = re.compile(r"(?<!-)-{2,}(?!-)")


def corrigir_seguro(texto):
    """(texto_corrigido, {"aspas": n, "hifen_duplo": n})."""
    texto = texto or ""
    n = {"aspas": 0, "hifen_duplo": 0}
    linhas = []
    for linha in texto.split("\n"):
        if RX_REGUA.match(linha):
            linhas.append(linha)
            continue
        linha, k = _RX_ASPAS.subn(lambda m: _ASPAS[m.group(0)], linha)
        n["aspas"] += k
        linha, k = _RX_HIFEN_DUPLO.subn("—", linha)
        n["hifen_duplo"] += k
        linhas.append(linha)
    return "\n".join(linhas), n








_BLOCOS_EXCLUIDOS = ("capa", "cita", "juris", "fecho", "tabela", "timeline")
_RX_ITALICO_INTEGRAL = re.compile(r"^\*(?!\*)[^*].*[^*]\*$")


def paragrafos_prosa_markdown(src):
    """(paragrafos, indices_de_titulo) da prosa autoral de um markdown."""
    paras, titulos = [], set()
    bloco = None
    for bruto in (src or "").splitlines():
        s = bruto.strip()
        if s.startswith(":::"):
            tipo = s[3:].strip().lower()
            if bloco is None and tipo and not tipo.startswith("quebra"):
                bloco = tipo
            elif tipo == "":
                bloco = None
            continue
        if not s:
            continue
        if bloco and any(bloco.startswith(t) for t in _BLOCOS_EXCLUIDOS):
            continue
        if s.startswith(("~", "&", ">>", "achado:", "```", "|")):
            continue
        if _RX_ITALICO_INTEGRAL.match(s):
            continue
        if s.startswith("#"):
            titulos.add(len(paras))
            paras.append(s.lstrip("#").strip())
            continue
        paras.append(s)
    return paras, titulos



def _relatorio(res, maximo=40):
    linhas = [f"== {res['veredito'].upper()} == {len(res['ocorrencias'])} ocorrência(s) em "
              f"{res['palavras']} palavras"]
    for pid, n in sorted(res["por_padrao"].items()):
        linhas.append(f"  {pid} {PADROES[pid]['nome']}: {n}")
    for o in res["ocorrencias"][:maximo]:
        linhas.append(f"{o['severidade'].upper():5} {o['padrao']} §{o['indice'] + 1} "
                      f"«{o['contexto']}»")
    if len(res["ocorrencias"]) > maximo:
        linhas.append(f"… e mais {len(res['ocorrencias']) - maximo}")
    if res["ocorrencias"]:
        linhas.append("Remédios: " + " · ".join(
            f"{pid}: {PADROES[pid]['remedio']}" for pid in sorted(res["por_padrao"])))
    return "\n".join(linhas)


def main(argv=None):
    import argparse
    import json
    ap = argparse.ArgumentParser(
        prog="jusmanizer", description="Lista traços de escrita de IA em texto jurídico pt-BR.")
    ap.add_argument("arquivo", help="markdown ou texto puro (UTF-8)")
    ap.add_argument("--json", action="store_true", help="saída em JSON")
    ap.add_argument("--corrigir-seguro", action="store_true",
                    help="reescreve o arquivo com aspas retas e hífen duplo normalizado, depois analisa")
    ap.add_argument("--excluir", default="", help="ids de padrão a ignorar, separados por vírgula")
    ap.add_argument("--ignorar-ancora", action="append", default=[],
                    help="literal que não conta como âncora repetida (ex.: número dos autos); "
                         "pode repetir")
    a = ap.parse_args(argv)
    with open(a.arquivo, encoding="utf-8") as f:
        src = f.read()
    if a.corrigir_seguro:
        src, n = corrigir_seguro(src)
        with open(a.arquivo, "w", encoding="utf-8") as f:
            f.write(src)
        if not a.json:
            print(f"corrigido: {n['aspas']} aspas, {n['hifen_duplo']} hífen(s) duplo(s)")
    paras, titulos = paragrafos_prosa_markdown(src)
    excluir = {x.strip().upper() for x in a.excluir.split(",") if x.strip()}
    res = analisar(paras, titulos=titulos, excluir=excluir, ignorar_ancoras=a.ignorar_ancora)
    print(json.dumps(res, ensure_ascii=False, indent=1) if a.json else _relatorio(res))
    return 1 if res["veredito"] == "erro" else 0


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
