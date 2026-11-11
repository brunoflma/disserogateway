#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lint_peca.py — gate determinístico pós-build do Visual Law.

Mede no `.docx` gerado o que a leitura de revisão não conta:
  forma ................ L1–L7, L10, L12, L30, L33 (dialeto, aspas, realce, recuo, negrito de
                         dado, parágrafo numerado)
  lastro ............... L8, L9, L11, L13–L15, L24, CRUZAMENTO-DOC (julgado e documento citados),
                         L34 (percentual sem base, documento ou norma)
  mapa ................. L35 (questão, tese descartada e motivo do mapa argumentativo na peça)
  estratégia e tom ..... L25, L26 (linguagem contra a cobertura de precedentes da tese)
  língua do documento .. L16, L19 (vocabulário interno e notação de documentação na peça)
  tratamento ........... L20 (forma de tratamento × grau de jurisdição)
  prosa ................ L21 (risca), L22 (repetição de âncora), L28 (padrões de IA)
  estrutura ............ L17, L18 (paginação e caixa), L23 (referência cruzada), L27 (grifo),
                         L29 (assinatura com OAB), F1/F2 (capa)
  leitura .............. E1–E3 (só aviso)
  minuta por ordem ..... L32 (faixa ou marca de MINUTA COM PENDÊNCIAS: nunca APROVADO)

Uso: python3 lint_peca.py peca.docx [--fragmento] [--precedentes achados.json]
          [--juntada JUNTADA_TRACKER.json] [--conferencia CONFERENCIA.json]
          [--grau primeiro|segundo|superior] [--processo CNJ]... [--session-id ID]
  --fragmento   capítulo/fragmento sem capa: dispensa as checagens de endereçamento
                e de qualificação das partes (seções F1/F2) e a de assinatura (L29).
  --grau primeiro|segundo|superior   GRAU DE JURISDIÇÃO da peça, derivado da classe
                processual no briefing (`dissero-peticao` §1) e propagado até aqui. Governa o
                L20 (formas de tratamento). Omitido, o linter INFERE do endereçamento e
                DIZ que inferiu; não inferindo, o L20 não roda e isso vira AVISO — regra de
                tratamento sobre grau adivinhado reprovaria peça correta.
  --processo CNJ   número CNJ do PRÓPRIO caso e dos recursos dele derivados (repetível).
                Sai da heurística de julgado (L9/L11) e da contagem de repetição (L22):
                o agravo tirado dos próprios autos não é precedente, e repetir o número dos
                autos é obrigação, não repetição.
  --precedentes achados.json   dataset verificado da Relação de Precedentes. OBRIGATÓRIO
                quando a peça cita julgado (L11): cruza cada julgado citado contra o
                dataset e reprova o que não constar lá. Sem ele, peça com jurisprudência é
                REPROVADA.
  --juntada JUNTADA_TRACKER.json   ledger `dsr.juntada.v1` da juntada. OBRIGATÓRIO quando a
                peça cita documento (L13): cruza cada (Doc. NN) contra o registro curado e
                reprova citação sem lastro (CRUZAMENTO-DOC). É a metade documental do que
                `--precedentes` faz com julgado.
  --conferencia CONFERENCIA.json   dataset `dsr.conferencia.v1` da ingestão. Necessário quando
                a peça TRANSCREVE prova documental (L14 — conferência literal): confere o
                trecho transcrito contra o teor lido. Se o ledger da juntada já aponta o
                dataset no campo `conferencia`, este flag é dispensável.
  --session-id ID   id da sessão do harness: localiza a pasta do caso registrada para ela.
  Nome NU (sem diretório) na peça e nos três artefatos: vale o da pasta do caso DESTA sessão
  (`DSR_CASO_RAIZ` ou a que `caso_raiz.py registrar` gravou para o `--session-id`) quando
  existe lá, senão o do cwd. O último caso registrado (de outra sessão ou antigo) nunca fornece
  arquivo. O linter REPROVA e pede o caminho completo quando o nome existe no cwd e na pasta do
  caso como arquivos diferentes, e quando falta no cwd e só existe na última pasta registrada.

Saída — TRÊS estados, cada um com exit code próprio:
  APROVADO (exit 0)  estrutura limpa e nada a conferir. É o único que libera o protocolo.
  MINUTA   (exit 3)  estrutura LIMPA, com julgado ou marcação ainda por conferir na fonte
                     oficial. É o estado normal de uma peça em elaboração; não libera o
                     protocolo.
  REPROVADO (exit 1) defeito de ESTRUTURA. Corrigir a fonte e regerar.
Conferência pendente não se chama REPROVADO: com o mesmo nome para os dois estados, o
operador aprende que "REPROVADO às vezes é normal" e passa a ignorar o gate.
No conselho, a peça só é submetida com APROVADO, e a cadeira Conformidade roda este script e
anexa a saída ao voto (regimento: `references/conselho-revisor.md`).
Stdlib apenas (importa `visual_law_core.py` e os módulos irmãos que ficam ao lado)."""
import sys, os, re, json, zipfile
import xml.etree.ElementTree as ET



try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass





sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from visual_law_core import (autobold_matches, MAX_CAIXA_ATOMICA,
                                     W_FULL, _tema, definir_tema,
                                     l30_lead_in_longo, l30_mensagem,
                                     l33_paragrafos_numerados, l33_mensagem,
                                     signatarios_sem_inscricao, tem_faixa_minuta)
except Exception as _e:
    print(f"REPROVADO: visual_law_core.py indisponível ao lado do linter "
          f"({_e}) — L12 (auto-negrito) e L17/L18 (paginação e estrutura) não podem ser medidos")
    sys.exit(1)


PARTE_CARIMBO_MINUTA = "docProps/custom.xml"
PROP_MINUTA_PENDENCIAS = "DSRMinutaPendencias"



try:
    import juntada_contract
    JUNTADA_SCHEMA = juntada_contract.SCHEMA_VERSION
except Exception:
    juntada_contract = None
    JUNTADA_SCHEMA = "dsr.juntada.v1"



try:
    import vocabulario_interno
except Exception as _e:
    print(f"REPROVADO: vocabulario_interno.py indisponível ao lado do linter "
          f"({_e}) — L16 (vocabulário interno) não pode ser medido")
    sys.exit(1)
try:
    import estrategia_precedentes
except Exception as _e:
    print(f"REPROVADO: estrategia_precedentes.py indisponível ao lado do linter "
          f"({_e}) — a pesquisa de contrário e a aderência da tese não podem ser medidas")
    sys.exit(1)












COBERTURA_SEM_PROVA = "inexistente"
CLASSE_TRAVADA = "estado_da_jurisprudencia"
try:
    import calibracao_vocabulario
except Exception as _e:
    print(f"REPROVADO: calibracao_vocabulario.py indisponível ao lado do linter "
          f"({_e}) — a calibração do tom contra a força da tese não pode ser medida")
    sys.exit(1)




try:
    import conferencia_contract
    CONFERENCIA_SCHEMA = conferencia_contract.SCHEMA_VERSION
except Exception:
    conferencia_contract = None
    CONFERENCIA_SCHEMA = "dsr.conferencia.v1"



try:
    import grau_jurisdicao
    import metricas_prosa
    import jusmanizer
except Exception as _e:
    print(f"REPROVADO: grau_jurisdicao.py/metricas_prosa.py/jusmanizer.py indisponíveis ao lado "
          f"do linter ({_e}) — L20 (tratamento por grau), L21 (risca), L22 (repetição) e L28 "
          f"(padrões de IA) não podem ser medidos")
    sys.exit(1)




try:
    import perfil_advogado as _pa
except Exception:
    _pa = None




try:
    import caso_raiz as _caso_raiz
except Exception:
    _caso_raiz = None


class CaminhoRecusado(Exception):
    """Nome nu que não se atribui a um arquivo só deste caso."""


def no_caso(caminho, session_id=None):
    'Arquivo de entrada com nome NU: o da pasta do caso desta sessão, quando existe lá; senão,'







    if not caminho or os.path.dirname(caminho) or _caso_raiz is None:
        return caminho
    try:
        raiz, origem = _caso_raiz.resolver(session_id=session_id)
    except Exception:
        return caminho
    if origem == "cwd":
        return caminho
    no_raiz = os.path.join(raiz, caminho)
    na_raiz, no_cwd = os.path.isfile(no_raiz), os.path.isfile(caminho)
    if origem in ("env", "sessao"):
        try:
            dois = na_raiz and no_cwd and not os.path.samefile(caminho, no_raiz)
        except OSError:
            dois = True
        if dois:
            raise CaminhoRecusado(
                f"«{caminho}» existe na pasta corrente ({os.path.abspath(caminho)}) e na pasta "
                f"do caso ({no_raiz}), como arquivos diferentes. Passe o caminho completo do que "
                f"deve ser conferido.")
        return no_raiz if na_raiz else caminho
    if na_raiz and not no_cwd:
        raise CaminhoRecusado(
            f"«{caminho}» não está na pasta corrente e só existe na última pasta de caso "
            f"registrada, que pode ser de outra sessão ou de outro caso e por isso não é usada. "
            f"Passe o caminho completo do que deve ser conferido, ou --session-id com o id "
            f"desta sessão.")
    return caminho


def grau_do_estado(caminho_docx, session_id=None):
    '(grau, arquivo) do `grau_jurisdicao` gravado no PECA_STATE.json da peça, ou (None, None).'


    candidatos = []
    try:
        achado = no_caso("PECA_STATE.json", session_id)
        if achado and os.path.isfile(achado):
            candidatos.append(achado)
    except Exception:
        pass
    ao_lado = os.path.join(os.path.dirname(os.path.abspath(caminho_docx or ".")),
                           "PECA_STATE.json")
    if os.path.isfile(ao_lado):
        candidatos.append(ao_lado)
    graus = {}
    for c in candidatos:
        try:
            with open(c, encoding="utf-8") as f:
                g = (json.load(f) or {}).get("grau_jurisdicao")
        except Exception:
            continue
        if isinstance(g, str) and g.strip().lower() in grau_jurisdicao.GRAUS:
            graus[os.path.abspath(c)] = g.strip().lower()
    if len(set(graus.values())) != 1:
        return None, None
    arquivo, grau = next(iter(graus.items()))
    return grau, arquivo







RX_COMARCA = re.compile(r"(?:COMARCA|VARA\s+(?:[ÚU]NICA\s+)?DO\s+TRABALHO)\s+DE\s+"
                        r"([^,;/–—\-\n]+)", re.I)


def _sem_acento(s):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", str(s))
                   if unicodedata.category(c) != "Mn").upper().strip()


def comarca_divergente(primeiro_paragrafo, comarca_padrao):
    'A comarca do enderecamento, quando ela NAO e a que a banca declarou. PURA.'









    if not primeiro_paragrafo or not str(comarca_padrao or "").strip():
        return None
    achado = RX_COMARCA.search(str(primeiro_paragrafo))
    if not achado:
        return None
    nome = achado.group(1).strip()
    return None if _sem_acento(nome) == _sem_acento(comarca_padrao) else nome


def l28_duplica_l16(ocorrencia):
    'True quando a ocorrência do jusmanizer repete um erro que o L16 já dá. PURA.'






    return (ocorrencia.get("padrao") == "J23"
            and bool(vocabulario_interno.residuos(ocorrencia.get("trecho", ""))))


def dispensas_de_estilo(overrides):
    'O que `estilo_escrita.overrides` do perfil dispensa na regua. PURA.'
















    o = overrides if isinstance(overrides, dict) else {}
    excluir = set()
    pular_l21 = o.get("permitir_travessao") is True
    if pular_l21:
        excluir.add("J01")
    if o.get("proibir_regra_dos_tres") is False:
        excluir.add("J08")
    if o.get("aspas") == "curvas":
        excluir.add("J21")
    return {"excluir": excluir, "pular_l21": pular_l21}


def _perfil_do_ambiente():
    'O perfil resolvido, ou None. `main()` o resolve uma vez por execucao e o repassa:'

    if _pa is None:
        return None
    try:
        caminho = _pa.resolver_caminho()
        return _pa.carregar(caminho) if caminho else None
    except Exception:
        return None


def _comarca_do_ambiente(perfil):
    return (_pa._get(perfil, "foro.comarca_padrao", "") or "") if (perfil and _pa) else ""


def _dispensas_do_ambiente(perfil):
    """As dispensas do perfil resolvido, ou nenhuma. Nao ha perfil? A regua fica inteira."""
    if _pa is None or not perfil:
        return dispensas_de_estilo(None)
    try:
        return dispensas_de_estilo(_pa.estilo_overrides(perfil))
    except Exception:
        return dispensas_de_estilo(None)


_disp = dispensas_de_estilo(None)
_comarca_padrao = ""

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"




FECHO_RX = re.compile(r"(?i)\b(?:termos em que|nestes termos|pede\w* e espera|"
                      r"espera(?:ndo)? deferimento|pede deferimento)")




FORMULA_FECHO_MAX = 120






DATA_LINHA_RX = re.compile(r"(?i)(?:\b\d{1,2}\s+de\s+[a-zà-ÿ]+\s+de\s+\d{4}\b"
                           r"|\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b"
                           r"|\[[^\]\n]*\bDATA\b[^\]\n]*\])")


def e_formula_de_fecho(t):
    t = (t or "").strip()
    m = FECHO_RX.search(t)
    return bool(m) and m.start() == 0 and len(t) <= FORMULA_FECHO_MAX


def bloco_e_assinatura(textos, ini, e_ultimo):
    'O grupo de parágrafos centrados que começa em `textos[ini]` é um bloco de ASSINATURA?'













    ancorado = e_formula_de_fecho(textos[ini][0])
    j = ini - 1
    while not ancorado and j >= 0:
        t = textos[j][0].strip()
        if not t or DATA_LINHA_RX.search(t):
            j -= 1
            continue
        if not e_formula_de_fecho(t):
            return False
        ancorado = True
    if not ancorado:
        return False
    if e_ultimo:
        return True
    k = ini - 1
    while k >= 0 and not textos[k][0].strip():
        k -= 1
    return k >= 0 and bool(DATA_LINHA_RX.search(textos[k][0]))



OAB_RX = re.compile(r"\bOAB\b", re.IGNORECASE)

PLACEHOLDER_RX = re.compile(r"\[[^\]\n]{0,400}\]")


PLACEHOLDER_KEYS = ("A INSERIR", "A CONFERIR", "COMPLETAR", "PENDENTE", "DATA", "AGUARD",
                    "VERIFICA")




L8_VERBOS_RX = re.compile(r"INSERIR|CONFERIR|PENDENTE|AGUARD|VERIFICAR|N[ÃA]O\s+VERIFICAD")
L8_SUMULA_RX = re.compile(r"\bS[ÚU]MULAS?\b")
L8_NORMA_RX = re.compile(
    r"\b(?:DISPOSITIVOS?|VIG[ÊE]NCIA|ARTIGOS?|LEIS?|NORMAS?|REDA[ÇC][ÃA]O|REGULAMENTOS?)\b"
    r"|\bARTS?\.")
ENTIDADE_RX = re.compile(r"&#?[A-Za-z0-9]{2,10};")
ITEM_RX = re.compile(r"(?:^|[;.]\s+)\d{1,2}\.\s+\S")
LISTA_INICIO_RX = re.compile(r"^\s*(?:\d{1,2}[.)]\s|[a-z][.)]\s|\([a-z0-9]{1,3}\)\s|[+•–-]\s)")
QUALIFICACAO_RX = re.compile(r"^[A-ZÀ-Ü][A-ZÀ-Ü0-9&./\- ]{6,},")




DOC_RX = re.compile(r"\(Doc\.\s*0*(\d+)")





DOC_AMPLO_RX = re.compile(
    r"\b(?:(docs)\.|doc\.|(documentos)|documento)\s*(?:n[º°]s?\.?|n\.\s*[º°]|no\.)?\s*"
    r"(\d{1,3})(?!\d)((?:\s*(?:,|/|\be\b)\s*\d{1,3}(?!\d))*)", re.I)





DOC_DE_TERCEIRO_RX = re.compile(
    r"\s*\)?\s*,?\s*(?:d[aoe]s?|na|no)\s+(?:peti[çc][ãa]o\s+inicial|inicial|contesta[çc][ãa]o|"
    r"r[ée]plica|reconven[çc][ãa]o|defesa|impugna[çc][ãa]o|apela[çc][ãa]o|recurso|"
    r"parte\s+contr[áa]ria)",
    re.I)


def numeros_doc(txt):
    """Números de documento citados na forma CANÔNICA "(Doc. NN)", na ordem (com repetição)."""
    return [int(m.group(1)) for m in DOC_RX.finditer(txt or "")]


def numeros_doc_amplo(txt):
    'Números de documento PRÓPRIO citados em qualquer das formas reconhecidas pelo L14'

    txt = txt or ""
    saida = []
    for m in DOC_AMPLO_RX.finditer(txt):
        if DOC_DE_TERCEIRO_RX.match(txt, m.end()):
            continue
        saida.append(int(m.group(3)))
        if m.group(1) or m.group(2):
            saida += [int(x) for x in re.findall(r"\d+", m.group(4) or "")]
    return saida



FOLHA_RX = re.compile(r"\bfls?\.\s?(\d{1,5}(?:\s?[/\-–]\s?\d{1,5})*)", re.I)







ASPAS_RX = re.compile(r'"([^"\n]+)"|“([^”\n]+)”|«([^»\n]+)»|„([^“”"\n]+)[“”"]|”([^”\n]+)”'
                      r"|‹([^›\n]+)›|(?<!\w)‘(.+?)’(?!\w)|(?<!\w)'(.+?)'(?!\w)")






_TRIBUNAL_EXTENSO = (r"\bsupremo\s+tribunal\s+federal\b|\bsuperior\s+tribunal\s+de\s+justi[çc]a\b|"
                     r"\btribunal\s+superior\s+(?:do\s+trabalho|eleitoral)\b|"
                     r"\btribunal\s+(?:de\s+justi[çc]a|regional\s+(?:federal|do\s+trabalho|eleitoral))\b")
FONTE_NORMATIVA_RX = re.compile(
    r"\bart(?:igo)?s?\.?\s*\d|\blei\b|\bs[úu]mula|\bc[óo]digo\b|\bdecreto\b|\bconstitui[çc]|"
    r"\b(?:CPC|CC|CLT|CDC|CF|CTN|ECA|STF|STJ|TST|TSE|STM|TRF\d?|TRT\d*|TJ[A-Z]{2})\b|§|"
    r"\btema\s+\d|\bresp\b|\bagint\b|\bagrg\b|\bhc\b|\bms\b|" + _TRIBUNAL_EXTENSO
    + r"|\bjurisprud[êe]ncia\b", re.I)


DOUTRINA_RX = re.compile(
    r"\bensina|\blecion|\bna\s+li[çc][ãa]o\s+de|\bdoutrina|\bapud\b|\bin:\s|\bp\.\s*\d|\bpp\.\s*\d|"
    r"\bcurso\s+de\b|\btratado\s+de\b|\bmanual\s+de\b|\bcoment[áa]rios\s+a|\bed\.\s*\d|\beditora\b",
    re.I)






NORMA_ANTES_RX = re.compile(
    r"\bart(?:igo)?s?\.?\s*\d|\blei\b|\bs[úu]mula|\bc[óo]digo\b|\bdecreto\b|\bconstitui[çc]|"
    r"(?-i:\b(?:CPC|CC|CLT|CDC|CTN|ECA|STF|STJ|TST|TSE|STM|TRF\d?|TRT\d*|TJ[A-Z]{2})\b|\bCF\b(?!\.))|"
    r"§|\btema\s+\d|\bresp\b|\bagint\b|\bagrg\b|\bhc\b|\bms\b|"
    r"\bementa\b|\benunciado\b|\bverbete\b|\bensina|\blecion|"
    r"\bna\s+li[çc][ãa]o\s+de|\bapud\b|\bdoutrina", re.I)


ARTIGO_PROPRIO_RX = re.compile(
    r"\b(?:em\s+|n[oa]\s+)?(?:seu|sua|seus|suas)\s+(?:art(?:igo)?s?\.?\s*\d+[º°ª]?|§\s*\d+[º°ª]?|"
    r"par[áa]grafo\s+\S+|cl[áa]usula\s+\S+|item\s+\S+)"
    r"|\b(?:art(?:igo)?s?\.?\s*\d+[º°ª]?|§\s*\d+[º°ª]?|par[áa]grafo\s+\S+)"
    r"(?:\s*,\s*§\s*\d+[º°ª]?)?\s+d[oa]s?\s+(?:pr[óo]pri[oa]\s+|mesm[oa]\s+|referid[oa]\s+)?"
    r"(?:contrato|estatuto|termo|instrumento|regimento|regulamento|acordo|ata|escritura|"
    r"conven[çc][ãa]o|aditivo|pacto|ajuste|distrato)\b", re.I)






_DOC_ESPECIE = (r"(?:contrato|termo|instrumento|estatuto|cl[áa]usula|escritura|recibo|aditivo|"
                r"nota\s+promiss[óo]ria|ata|acordo|documento|declara[çc][ãa]o|confiss[ãa]o|"
                r"regulamento|regimento|distrato|pacto|aven[çc]a|ajuste)")
_DOC_DIZER = (r"(?:diz|dizia|disp[õo]e|dispunha|prev[êe]|previa|estabelece|estabelecia|estipula|"
              r"estipulava|determina|determinava|reza|rezava|registra|registrava|consigna|"
              r"consignava|prescreve|cont[ée]m|continha|enuncia|traz|trazia|expressa|"
              r"textualmente)")






_DOC_SUJEITO_ART = (r"(?<!sobre\s)(?<!quanto\s)(?<!tocante\s)(?<!relativamente\s)(?<!referente\s)"
                    r"(?<!atinente\s)(?<!concernente\s)"
                    r"\b(?:[ao]s?|est[ea]s?|ess[ea]s?|aquel[ea]s?|seus?|suas?)\s+"
                    r"(?:(?:mesm[oa]|referid[oa]|pr[óo]pri[oa]|aludid[oa]|citad[oa])\s+)?")
_DOC_SUJEITO_VAO = (r"(?:[^.;:,\"“”«»]{0,40}?"
                    r"|[^.;:,\"“”«»]{0,15}?,[^.;:,\"“”«»]{1,30},[^.;:,\"“”«»]{0,10}?)")
VOLTA_AO_DOCUMENTO_RX = re.compile(
    r"\b(?:declarou|declararam|confessou|confessaram|consignou|consignaram|assinou|assinaram|"
    r"subscreveu|subscreveram|pactuaram|ajustaram|avençaram)\b"
    r"|\bassinad[oa]s?\s+pel[oa]s?\b"
    r"|" + _DOC_SUJEITO_ART + _DOC_ESPECIE + r"\b" + _DOC_SUJEITO_VAO + r"\b" + _DOC_DIZER + r"\b",
    re.I)



_CONSTA_RX = re.compile(r"\b(?:consta|l[êe]-se|se\s+l[êe])\b", re.I)
_DOC_LUGAR_RX = re.compile(r"\b(?:n[oa]s?|d[oa]s?|em)\s+(?:referid[oa]\s+|pr[óo]pri[oa]\s+|mesm[oa]\s+)?"
                           + _DOC_ESPECIE + r"\b", re.I)










_FONTE_PROC_NOME = (r"(?:peti[çc][ãa]o\s+inicial|inicial|contesta[çc][ãa]o|r[ée]plica|tr[ée]plica|"
                    r"defesa|impugna[çc][ãa]o|apela[çc][ãa]o|contrarraz[õo]es|"
                    r"raz[õo]es\s+recursais|memoriais|senten[çc]a|ac[óo]rd[ãa]o|decis[ãa]o|"
                    r"despacho|depoimento|interrogat[óo]rio|testemunha|depoente|perito|laudo\s+pericial)")
_FONTE_PROC_DICCAO = (r"(?:afirma|afirmou|afirmam|afirmaram|diz|disse|dizem|disseram|declara|declarou|"
                      r"declararam|consigna|consignou|assenta|assentou|registra|registrou|"
                      r"reconhece|reconheceu|admite|admitiu|alega|alegou|sustenta|sustentou|aduz|"
                      r"aduziu|argumenta|argumentou|narra|narrou|relata|relatou|transcreve|"
                      r"transcreveu|conclui|concluiu|decide|decidiu|fundamenta|fundamentou|"
                      r"assevera|asseverou|pontua|pontuou|destaca|destacou|menciona|mencionou|"
                      r"dep[ôo]s|respondeu|informou|esclareceu|confirmou|negou|nega|"
                      r"escreve|escreveu|observa|observou|pondera|ponderou|anota|anotou|"
                      r"entende|entendeu|salienta|salientou|ressalta|ressaltou|frisa|frisou|"
                      r"assinala|assinalou|opina|opinou|opinaram|"
                      r"l[êe]-se|se\s+l[êe]|consta)")



_FONTE_PROC_SUJEITO = (r"(?:ju[íi]z[ao]?|magistrad[oa]|relator[a]?|desembargador[a]?|"
                       r"minist[ée]rio\s+p[úu]blico|parquet|(?-i:MP)|[óo]rg[ãa]o\s+julgador|"

                       r"supremo\s+tribunal\s+federal|superior\s+tribunal\s+de\s+justi[çc]a|"
                       r"tribunal\s+superior\s+(?:do\s+trabalho|eleitoral)|"
                       r"tribunal\s+(?:de\s+justi[çc]a|regional\s+(?:federal|do\s+trabalho|eleitoral)))")


_FONTE_PROC_LUGAR = (r"(?:peti[çc][ãa]o\s+inicial|inicial|contesta[çc][ãa]o|r[ée]plica|tr[ée]plica|"
                     r"defesa|impugna[çc][ãa]o|apela[çc][ãa]o|contrarraz[õo]es|"
                     r"raz[õo]es\s+recursais|memoriais|senten[çc]a|ac[óo]rd[ãa]o|decis[ãa]o|"
                     r"despacho|depoimento|interrogat[óo]rio|laudo\s+pericial)")


_FONTE_PROC_NAO_LUGAR = r"(?!(?:presen[çc]a|perante|diante|frente|depois|ap[óo]s|antes|vista)\b)"


_FONTE_PROC_MEIO = r"(?:\s+(?!(?:e|ou|mas|que|se)\b)[\wÀ-ÿº°ª]+){0,3}?"
_FONTE_PROC_ARTIGO = (r"\b(?:[ao]s?|esta|este|essa|esse|aquela|aquele)\s+"
                      r"(?:r\.\s*|douta\s+|nobre\s+|culta\s+|mm\.\s*|eminente\s+|i\.\s*)?")



_FONTE_PROC_FOLHA = r"(?:\s+d[eoa]s?\s+fls?\.\s*\d{1,5}(?:\s*[/\-–]\s*\d{1,5})?)?"
_FONTE_PROC_APOSTO = r"(?:\s*,[^,.;:\"“”«»]{1,30},)?"
FONTE_PROCESSUAL_RX = re.compile(
    _FONTE_PROC_ARTIGO + r"(?:" + _FONTE_PROC_NOME + r"|" + _FONTE_PROC_SUJEITO + r")"
    + _FONTE_PROC_FOLHA + _FONTE_PROC_MEIO + _FONTE_PROC_APOSTO + r"\s*,?\s+"
    + _FONTE_PROC_DICCAO + r"\b"
    r"|" + _FONTE_PROC_ARTIGO + r"(?:" + _FONTE_PROC_NOME + r"|" + _FONTE_PROC_SUJEITO + r")"
    + _FONTE_PROC_MEIO + r"\s+julg(?:a|ou|aram|am)\b[^.;:\"“”«»]{0,80}?\bpor\s+entender\b"
    r"|\b" + _FONTE_PROC_DICCAO + r"(?:\s+" + _FONTE_PROC_NAO_LUGAR + r"[\wÀ-ÿ]+){0,2}?\s+"
    r"(?:n[ao]|d[ao]|pel[ao])\s+"
    r"(?:r\.\s*|douta\s+|pr[óo]pri[ao]\s+)?" + _FONTE_PROC_LUGAR + r"\b"
    r"|\b(?:n[ao]|em)\s+(?:r\.\s*|seu\s+|sua\s+|douta\s+)?" + _FONTE_PROC_NOME
    + r"(?:\s+[\wÀ-ÿ]+){0,3}?\s*,\s*(?:l[êe]-se|se\s+l[êe]|consta)\b"
    r"|\bn[ao]\s+(?:r\.\s*|douta\s+)?" + _FONTE_PROC_LUGAR
    + r"(?:\s+[\wÀ-ÿ]+){0,3}?\s*,\s*(?:[\wÀ-ÿ.]+\s+){1,4}?" + _FONTE_PROC_DICCAO + r"\b"
    r"|\bem\s+(?:seu|sua)\s+(?:depoimento|interrogat[óo]rio|contesta[çc][ãa]o|defesa|"
    r"r[ée]plica|impugna[çc][ãa]o|apela[çc][ãa]o)\b"
    r"|\b(?:a\s+r[ée]|o\s+r[ée]u|a\s+autora|o\s+autor|a\s+parte\s+contr[áa]ria|"
    r"[oa]s?\s+apelad[oa]s?|[oa]s?\s+apelantes?|[oa]\s+recorrid[oa]|[oa]\s+recorrente)"
    r"(?:\s*,\s*[^,\"“«]{1,30},)?"
    r"\s+(?:alega|alegou|alegam|sustenta|sustentou|aduz|aduziu|argumenta|argumentou)\b", re.I)


_ANTES_DE_DOC_RX = re.compile(r"[\s,;:.—–-]{0,4}\(?\s*(?:(?:conforme|cf\.|v\.|vide|ver)\s*)?\(?\s*",
                              re.I)


_PONTUACAO_FRASE_RX = re.compile(r"[.!?;:](?=\s|$)")
_ABREVIACAO_RX = re.compile(r"\b(?:ltda|s\.\s?a|cia|eireli|epp|inc|n[º°o]|arts?|fls?|pp?|drs?|"
                            r"dras?|srs?|sras?|exmos?|exmas?|av|c/c)\.", re.I)


def tem_pontuacao_de_frase(trecho):
    return bool(_PONTUACAO_FRASE_RX.search(_ABREVIACAO_RX.sub("", (trecho or "").strip())))




VALOR_OU_DATA_RX = re.compile(r"R\$|\d[\d.]*[.,/]\d|\d\s*%|\b\d{1,2}\s+de\s+[a-zç]+\s+de\s+\d{4}\b",
                              re.I)
DECLARACAO_1P_RX = re.compile(
    r"\b(?:confesso|declaro|reconhe[çc]o|assumo|obrigo-me|me\s+obrigo|prometo|autorizo|recebi|"
    r"devo|pagarei|comprometo-me|me\s+comprometo|renuncio|outorgo|cedo|vendo|transfiro)\b", re.I)




DECLARACAO_3P_RX = re.compile(
    r"\b(?:confessa|declara|reconhece|assume|obriga-se|se\s+obriga|promete|autoriza|recebeu|"
    r"deve|pagar[áa]|compromete-se|se\s+compromete|renuncia|outorga|cede|vende|transfere|"
    r"quita|d[áa]\s+quita[çc][ãa]o)\b", re.I)




TITULO_DOCUMENTO_RX = re.compile(
    r"(?:contrato|termo|ata|instrumento|escritura|recibo|procura[çc][ãa]o|aditivo|estatuto|"
    r"certid[ãa]o|notifica[çc][ãa]o|laudo|carta|acordo|conven[çc][ãa]o|distrato|nota\s+fiscal|"
    r"nota\s+promiss[óo]ria|duplicata|c[ée]dula|fatura|declara[çc][ãa]o|"
    r"boletim\s+de\s+ocorr[êe]ncia|requerimento|of[íi]cio|relat[óo]rio|memorando|proposta|"
    r"ordem\s+de\s+servi[çc]o|altera[çc][ãa]o\s+contratual)\b", re.I)


def tem_valor_ou_data(trecho):
    return bool(VALOR_OU_DATA_RX.search(trecho or ""))


def tem_declaracao(trecho):
    """Verbo de declaração, obrigação ou reconhecimento, em 1ª ou 3ª pessoa."""
    return bool(DECLARACAO_1P_RX.search(trecho or "") or DECLARACAO_3P_RX.search(trecho or ""))


def _titulo_de_documento(trecho):
    'Começa pela espécie documental, até 12 palavras, sem valor monetário, percentual,'


    t = (trecho or "").strip()
    if not t or not t[0].isupper() or not TITULO_DOCUMENTO_RX.match(t):
        return False
    return (len(t.split()) <= 12 and not tem_pontuacao_de_frase(t)
            and not re.search(r"R\$|\d\s*%", t) and not tem_declaracao(t))


def parece_nome(trecho):
    'Trecho entre aspas com até 8 palavras e sem pontuação de frase é nome ou descrição'




    trecho = trecho or ""
    if _titulo_de_documento(trecho):
        return True
    return (len(trecho.split()) <= 8 and not tem_pontuacao_de_frase(trecho)
            and not tem_valor_ou_data(trecho) and not tem_declaracao(trecho))


def _janela_antes(txt, inicio):
    """Os 100 caracteres antes de `inicio`, a contar da última referência a documento."""
    janela = txt[max(0, inicio - 100):inicio]
    ultima = None
    for ultima in DOC_AMPLO_RX.finditer(janela):
        pass
    if ultima is not None:
        janela = janela[ultima.end():]
    return janela


def doc_logo_depois(txt, fim):
    'Logo depois das aspas que terminam em `fim` vem referência a documento PRÓPRIO'

    m = _ANTES_DE_DOC_RX.match(txt, fim)
    pos = m.end() if m else fim
    d = DOC_AMPLO_RX.match(txt, pos)
    return bool(d) and not DOC_DE_TERCEIRO_RX.match(txt, d.end())


def aspas_de_norma(txt, inicio, fim=None):
    'O trecho entre aspas que começa em `inicio` vem precedido de perto (100 caracteres, a'




    if fim is not None and doc_logo_depois(txt, fim):
        return False


    janela = ARTIGO_PROPRIO_RX.sub(lambda m: " " * len(m.group(0)), _janela_antes(txt, inicio))
    ultima = primeira = None
    for ultima in NORMA_ANTES_RX.finditer(janela):
        primeira = primeira or ultima
    if ultima is None:
        return False
    depois = janela[ultima.end():]
    if VOLTA_AO_DOCUMENTO_RX.search(depois):
        return False
    if _CONSTA_RX.search(depois):


        inicio_norma = inicio - len(janela) + primeira.start()
        antes_norma = txt[max(0, inicio - 160):max(0, inicio_norma)]
        frase = re.split(r"[.;!?]\s+(?=[A-ZÀ-Ü])", antes_norma)[-1]
        if _DOC_LUGAR_RX.search(frase):
            return False
    return True






_FONTE_PROC_CIRCUNSTANCIA_RX = re.compile(
    r"(?:\bcuj[oa]s?\s+[\wÀ-ÿ]+|\bap[óo]s|\bantes\s+d[eoa]s?|\bdepois\s+d[eoa]s?|\bperante|"
    r"\bdiante\s+d[eoa]s?|\bpresen[çc]a\s+d[eoa]s?)\s*$", re.I)


def fonte_processual(txt):
    'O texto nomeia fonte processual do trecho (`FONTE_PROCESSUAL_RX`) fora de circunstância'

    for m in FONTE_PROCESSUAL_RX.finditer(txt or ""):
        if not _FONTE_PROC_CIRCUNSTANCIA_RX.search(txt[max(0, m.start() - 30):m.start()]):
            return True
    return False


def aspas_de_outra_fonte(txt, inicio, fim=None):
    'O trecho entre aspas vem precedido de perto, sem referência a documento no meio, por'


    if fim is not None and doc_logo_depois(txt, fim):
        return False
    return fonte_processual(_janela_antes(txt, inicio))


def nomeia_outra_fonte(txt):
    """O parágrafo nomeia norma, julgado, doutrina ou peça/ato processual?"""
    return bool(FONTE_NORMATIVA_RX.search(txt) or DOUTRINA_RX.search(txt)
                or fonte_processual(txt))



ENDERECAMENTO_PREFIXOS = (
    "AO ", "AOS ", "À ", "AS ", "A O", "A EXCEL", "A MERIT",
    "EXCELENT", "EXMO", "EXMA", "EXM.", "EXA.", "EXAS",
    "MERITISSIM", "MERITÍSSIM", "MM.", "MM ", "M.M.",
    "EGREGIO", "EGRÉGIO", "COLENDO", "COLENDA", "SENHOR", "SENHORA",
)
URL_RX = re.compile(r"https?://[^\s)\]]+", re.I)

TRIB_ANY_RX = re.compile(r"\b(STF|STJ|TST|TSE|STM|CNJ|TJ[A-Z]{2}|TRF\d?|TRT\d?)\b", re.I)
IND_JULGADO_RX = re.compile(r"\bRel\.|\brelator|\bj\.\s*\d|julgad[oa]\s+em", re.I)
DATA_RX = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")
DATA_HIFEN_RX = re.compile(r"\b\d{1,2}-\d{1,2}-\d{4}\b")
NUM_PROC_RX = re.compile(r"\d[\d.\-]{5,}\d")




_RX_SUMULA = re.compile(r"\bS[úu]mula\s+(Vinculante\s+)?(?:n[º°o]\.?\s*)?(\d{1,3}(?:\.\d{3})+|\d{1,4})\b", re.I)
_RX_TEMA = re.compile(r"\bTema\s+((?:de\s+Repercuss[ãa]o\s+Geral|Repetitivo)\s+)?(?:n[º°o]\.?\s*)?"
                      r"(\d{1,3}(?:\.\d{3})+|\d{1,4})\b", re.I)
_RX_SIGLA = re.compile(r"\b(STF|STJ|TST|TSE|STM|TNU|TRF\d|TRT\d{1,2}|TJ[A-Z]{2})\b")


def citacoes_sumula_tema(t):
    """[(tipo, número, vinculante, tribunal|None, rótulo)] das súmulas e temas citados em `t`."""
    out = []
    for tipo, rx in (("sumula", _RX_SUMULA), ("tema", _RX_TEMA)):
        for m in rx.finditer(t or ""):
            num = m.group(2).replace(".", "")
            perto = t[m.end():m.end() + 40]
            sigla = _RX_SIGLA.search(perto) or _RX_SIGLA.search(t[max(0, m.start() - 20):m.start()])
            trib = sigla.group(1).upper() if sigla else None
            if (tipo == "tema" and not trib and not m.group(1)
                    and not re.search(r"repercuss|repetitiv", perto, re.I)):
                continue
            vinc = bool(tipo == "sumula" and m.group(1))
            nome = "Súmula Vinculante" if vinc else ("Súmula" if tipo == "sumula" else "Tema")
            out.append((tipo, num, vinc, trib, f"{nome} {num}" + (f"/{trib}" if trib else "")))
    return out


def _casa_sumula_tema(citada, registrada):
    'Mesmo tipo e número (e mesma natureza vinculante); tribunal só desempata quando os dois o'

    return (citada[0] == registrada[0] and citada[1] == registrada[1] and citada[2] == registrada[2]
            and (not citada[3] or not registrada[3] or citada[3] == registrada[3]))


CNJ_RX = re.compile(r"\b\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b")




AUTOS_PROPRIOS_RX = re.compile(
    r"\bdest[ea]s?\s+(?:mesm[oa]s?\s+)?autos\b|\bnest[ea]s?\s+autos\b"
    r"|\bd[oa]s?\s+pr[óo]pri[oa]s?\s+autos\b|\bpresentes\s+autos\b"
    r"|\btirad[oa]\s+dest|\bd[eo]ste\s+(?:mesmo\s+)?processo\b|\bfeito\s+origin[áa]rio\b",
    re.I)


CAP_TITULO_RX = re.compile(r"^CAP[ÍI]TULO\s+([IVXLC]+)\b", re.I)
ITEM_TITULO_RX = re.compile(r"^([IVXLC]+)\.(\d{1,2})\b")

REF_CAP_RX = re.compile(r"\bcap[íi]tulos?\s+([IVXLC]+)\b", re.I)
REF_ITEM_RX = re.compile(r"\b(?:item|t[óo]pico|subitem)\s+([IVXLC]+)\.(\d{1,2})\b", re.I)



REF_ALHEIA_RX = re.compile(
    r"\bd[aoe]s?\s+(?:sua\s+|respectiv[ao]s?\s+)?(?:resposta|contesta[çc][ãa]o|r[ée]plica"
    r"|impugna[çc][ãa]o|contrarraz[õo]es|embargos|peti[çc][ãa]o|parecer|laudo|senten[çc]a"
    r"|ac[óo]rd[ãa]o|decis[ãa]o|manifesta[çc][ãa]o|recurso|inicial)\b", re.I)

def runs_do_paragrafo(p):
    '[(texto, negrito, realce, itálico, sublinhado)] por run; texto do'



    out = []
    for r in p.iter(W + "r"):
        t = "".join(n.text or "" for n in r.iter(W + "t"))
        if t == "":
            continue
        rpr = r.find(W + "rPr")
        b = hl = it = u = False
        if rpr is not None:
            bn = rpr.find(W + "b")
            b = bn is not None and bn.get(W + "val", "1") not in ("0", "false", "none")
            hn = rpr.find(W + "highlight")
            hl = hn is not None and hn.get(W + "val", "yellow") != "none"
            in_ = rpr.find(W + "i")
            it = in_ is not None and in_.get(W + "val", "1") not in ("0", "false", "none")
            un = rpr.find(W + "u")
            u = un is not None and un.get(W + "val", "single") not in ("0", "false", "none")
        out.append((t, b, hl, it, u))
    return out

def _so_dado_objetivo(t):
    'Run cujo texto é exatamente UM dado objetivo do L12 (data, valor, fls.,'

    s = t.strip()
    return bool(s) and any(trecho == s for _i, _f, trecho, _c in autobold_matches(s))

def area_util_do_documento(body):
    """Largura da página menos as margens esquerda e direita, lidas do ÚLTIMO sectPr."""
    sects = list(body.iter(W + "sectPr"))
    if sects:
        pg, mg = sects[-1].find(W + "pgSz"), sects[-1].find(W + "pgMar")
        try:
            return int(pg.get(W + "w")) - int(mg.get(W + "left")) - int(mg.get(W + "right"))
        except (AttributeError, TypeError, ValueError):
            pass
    return AREA_UTIL


def recuo_do_escritorio(perfil):
    """Recuo de 1ª linha do layout do escritório (twips), ou None se o perfil não diz."""
    if not perfil or _pa is None:
        return None
    try:
        return (_pa.layout(perfil).get("paragrafo") or {}).get("recuo_primeira")
    except Exception:
        return None


def first_line_recuo(p, minimo=700):
    ppr = p.find(W + "pPr")
    if ppr is None:
        return False
    ind = ppr.find(W + "ind")
    if ind is None:
        return False
    fl = ind.get(W + "firstLine")
    if fl:
        try:
            return int(fl) >= minimo
        except ValueError:
            return False
    return ind.get(W + "firstLineChars") not in (None, "0")





AREA_UTIL = W_FULL
TOLERANCIA_LARGURA = 40
LISTA_STYLE_RX = re.compile(r"List|Lista", re.I)

def flag_ligada(ppr, nome):
    '`<w:keepLines/>`, `<w:cantSplit/>`, `<w:keepNext/>` — presente E não desligada'

    if ppr is None:
        return False
    n = ppr.find(W + nome)
    return n is not None and (n.get(W + "val") or "1") not in ("0", "false", "off")

def texto_de(el):
    """Texto visível de qualquer elemento (parágrafo, linha, tabela)."""
    return "".join(t.text or "" for t in el.iter(W + "t"))

def e_item_de_lista(p):
    'Parágrafo de lista — `numPr` ou estilo List*/Lista*. A regra de proteção 1 do'


    ppr = p.find(W + "pPr")
    if ppr is None:
        return False
    if ppr.find(W + "numPr") is not None:
        return True
    st = ppr.find(W + "pStyle")
    return st is not None and bool(LISTA_STYLE_RX.search(st.get(W + "val") or ""))

def _regua(tcpr, aresta):
    '(val, sz) de uma aresta (`top`/`bottom`/...) do `tcBorders` da célula.'


    borders = tcpr.find(W + "tcBorders") if tcpr is not None else None
    edge = borders.find(W + aresta) if borders is not None else None
    if edge is None:
        return "none", 0
    val = edge.get(W + "val") or "none"
    try:
        sz = int(edge.get(W + "sz") or 0)
    except ValueError:
        sz = 0
    return val, sz


def _classifica_pela_regua(tcpr, cap):
    "'banner' | 'legenda' | 'elemento' sob as variantes `filete`/`contornado`, em que"









    topo_val, topo_sz = _regua(tcpr, "top")
    base_val, base_sz = _regua(tcpr, "bottom")
    if topo_val == "single" and topo_sz == cap["filete_sup_sz"]:
        return "banner"
    if topo_val == "none" and base_val == "single" and base_sz == cap["filete_inf_sz"]:
        return "legenda"
    return "elemento"


def classifica_elemento(tbl):
    "'banner' | 'legenda' | 'elemento' — pelo TEMA em vigor. Banner e legenda são"














    linhas = tbl.findall(W + "tr")
    if len(linhas) != 1 or len(linhas[0].findall(W + "tc")) != 1:
        return "elemento"
    tc = next(iter(tbl.iter(W + "tc")), None)
    if tc is None:
        return "elemento"
    tcpr = tc.find(W + "tcPr")
    tema = _tema()
    cap = tema["capitulo"]
    if cap["variante"] != "preenchido":
        return _classifica_pela_regua(tcpr, cap)



    fichas = tema["fichas"]
    shd = tcpr.find(W + "shd") if tcpr is not None else None
    fill = ((shd.get(W + "fill") or "") if shd is not None else "").upper()
    if fill == fichas["tinta"].upper():
        return "banner"
    borders = tcpr.find(W + "tcBorders") if tcpr is not None else None
    esq = borders.find(W + "left") if borders is not None else None
    tem_barra = esq is not None and (esq.get(W + "val") or "none") != "none"
    if fill == fichas["legenda"].upper() and tem_barra:
        return "legenda"
    return "elemento"

def largura_declarada(tbl):
    'Largura em twips da tabela: `tblW` quando dxa, senão a soma dos `gridCol`.'

    tblpr = tbl.find(W + "tblPr")
    tw = tblpr.find(W + "tblW") if tblpr is not None else None
    if tw is not None and (tw.get(W + "type") or "") == "dxa":
        try:
            return int(tw.get(W + "w") or 0)
        except ValueError:
            pass
    grid = tbl.find(W + "tblGrid")
    if grid is None:
        return None
    total = 0
    for gc in grid.findall(W + "gridCol"):
        try:
            total += int(gc.get(W + "w") or 0)
        except ValueError:
            return None
    return total or None

def colunas_da_linha(tr):
    """Colunas que a linha realmente ocupa: cada célula vale seu `gridSpan`."""
    n = 0
    for tc in tr.findall(W + "tc"):
        tcpr = tc.find(W + "tcPr")
        gs = tcpr.find(W + "gridSpan") if tcpr is not None else None
        try:
            n += int(gs.get(W + "val")) if gs is not None else 1
        except (TypeError, ValueError):
            n += 1
    return n

def coleta(body, dentro_tabela=False, acc=None):
    """Parágrafos em ordem do documento, marcando os que vivem dentro de tabela."""
    if acc is None:
        acc = []
    for el in list(body):
        tag = el.tag
        if tag == W + "p":
            acc.append((el, dentro_tabela))
        elif tag == W + "tbl":
            coleta(el, True, acc)
        else:
            coleta(el, dentro_tabela, acc)
    return acc

def _paragrafos_de_jurisprudencia(body):
    '`id()` de todo parágrafo de caixa de jurisprudência (tabela cuja primeira linha não'


    ids = set()
    for tbl in body.iter(W + "tbl"):
        linhas = [(pp, "".join(x for x, _, _, _, _ in runs_do_paragrafo(pp)).strip())
                  for pp in tbl.iter(W + "p")]
        primeira = next((t for _pp, t in linhas if t), "")
        if primeira.upper().startswith("JURISPRUD"):
            ids.update(id(pp) for pp, _t in linhas)
    return ids










L34_PERCENTUAL_RX = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)*\s?(?:%|por\s+cento\b)", re.I)
L34_EXTENSO_RX = re.compile(r"\bpor\s+cento\b", re.I)
L34_ASPAS_RX = re.compile(r'"[^"\n]*"|«[^»\n]*»|“[^”\n]*”')
L34_NORMA_RX = re.compile(
    r"\bart(?:igo)?s?\.?\s*\d|§|(?-i:\bLeis?\b)|\bleis?\s+(?:complementar\s+|federal\s+)?"
    r"(?:n[º°o.]*\s*)?\d|\bLC\b|\bDecreto|\bC[óo]digo\b"
    r"|\b(?:CPC|CC|CLT|CTN|CDC|CF|CRFB|ECA|LINDB|LEF|CP|CPP|EOAB|RICMS)\b"
    r"|Constitui[çc][ãa]o|Resolu[çc][ãa]o|S[úu]mula|(?-i:\bTemas?\b)|Instru[çc][ãa]o\s+Normativa"
    r"|Medida\s+Provis[óo]ria|Portaria|Provimento|Enunciado|Orienta[çc][ãa]o\s+Jurisprudencial"
    r"|\bOJ\b|\binciso|al[íi]quota|taxa\s+legal|\bSELIC\b|\bIPCA|\bINPC|\bIGP-?M|\bCDI\b"
    r"|juros\s+legais|tabela\s+(?:progressiva|do\s+INSS|do\s+IR)"

    r"|\bFGTS\b|\bINSS\b|\bIRP?F\b|imposto|\bICMS\b|\bISS\b|\bPIS\b|\bCOFINS\b"
    r"|\bIPI\b|\bITBI\b|\bITCMD\b|\bIPTU\b|\bIOF\b|\bCSLL\b|contribui[çc][ãa]o\s+previdenci"
    r"|taxa\s+judici[áa]ria|emolumentos|horas?\s+extras?|\bhoras\s+a\s+\d"

    r"|\b(?:STF|STJ|TST|TSE|TRF\d?|TJ[A-Z]{2})\b"
    r"|\b(?:ADI|ADC|ADO|ADPF|RE|REsp|AREsp|RR|IRDR|IAC)\s*(?:n[º°o]\.?\s*)?\d", re.I)


L34_LIGADO_ANTES_RX = re.compile(r"\b(?:custas|preparo|adicional)\b[^,;]{0,60}$", re.I)
L34_LIGADO_DEPOIS_RX = re.compile(
    r"\s*(?:\([^)]{0,60}\)\s*)?(?:de|a\s+t[íi]tulo\s+de)\s+(?:custas|preparo|adicional)\b", re.I)
L34_FONTE_RX = re.compile(
    r"cl[áa]usula|\bcontrat(?:os?|uais?|ua(?:l|is)|ad[oa]s?|a[çc][ãa]o)\b|aditivo|instrumento"
    r"|conven[çc][ãa]o\s+coletiva|acordo\s+coletivo"
    r"|\b(?:CCT|ACT)\b|laudo|per[íi]cia|perit[oa]"
    r"|\b(?:o|no|do|ao|pelo|em)\s+parecer\b|\bparecer\s+(?:t[ée]cnico|cont[áa]bil|pericial"
    r"|jur[íi]dico|d[oa]\s+(?:perit|assistente|Minist))"
    r"|edital|estatuto|regulamento|ap[óo]lice"
    r"|nota\s+fiscal|extrato|planilha|mem[óo]ria\s+de\s+c[áa]lculo|demonstrativo|c[áa]lculo"
    r"|tabela|\bdocs?\.|\bdocumento|\bfls?\.|\bID\s*\d|\banex[oa]s?\b|senten[çc]a|ac[óo]rd[ãa]o"
    r"|decis[ãa]o|despacho|holerite|contracheque|recibo|boleto|fatura|balan[çc]o|\bIBGE\b"
    r"|Banco\s+Central|\bBACEN\b|\bBCB\b|DIEESE|\bIPEA\b|segundo\s+[oa]s?\b"
    r"|\bfonte\b|previst|fixad|pactuad|ajustad|convencionad|estipulad", re.I)

_L34_GRANDEZAS = (
    r"(?:valor|montante|total|d[ée]bito|cr[ée]dito|condena[çc][ãa]o|causa|proveito|sal[áa]rio"
    r"|remunera[çc][ãa]o|parcela|principal|capital|saldo|faturamento|pre[çc]o|base|quantia"
    r"|import[âa]ncia|benef[íi]cio|renda|receita|lucro|patrim[ôo]nio|mensalidade|aluguel"
    r"|diferen[çc]a|d[íi]vida|excedente|dep[óo]sito|indeniza[çc][ãa]o|quota|cota)")
L34_BASE_RX = re.compile(
    r"(?:sobre|incidente\s+sobre|calculad[oa]s?\s+sobre|aplicad[oa]s?\s+sobre)\s+(?:o|a|os|as)\s+"
    + _L34_GRANDEZAS +
    r"|R\$\s*[\d.,]+.{0,120}?R\$\s*[\d.,]+"
    r"|\b\d+\s+(?:de|dos|das|em|entre)\s+(?:um\s+total\s+de\s+)?\d+\b"
    r"|\b\d+/\d+\s*\(\s*\d+(?:[.,]\d+)?\s?%", re.I | re.S)

_L34_NAO_GRANDEZA = (
    r"(?:(?:[úu]ltim[oa]s?\s+)?(?:per[íi]odo|m[êe]s|meses|anos?|exerc[íi]cio|semestre|trimestre"
    r"|bimestre|prazo|intervalo|interregno|dias?|semanas?)|m[ée]dia|geral|tese|tempo|pouc[oa]s?"
    r"|apenas|menos|mais|torno|seguida|raz[ãa]o|virtude|decorr[êe]ncia|face|fun[çc][ãa]o|que"
    r"|casos?|hip[óo]teses?|situa[çc][ãa]o|qualquer|todos?|todas?|ju[íi]zo|aberto"
    r"|janeiro|fevereiro|mar[çc]o|abril|maio|junho|julho|agosto|setembro|outubro|novembro"
    r"|dezembro)\b")

_L34_CONTAGEM = (
    r"(?:casos|vezes|processos|demandas|recursos|julgados|decis[õo]es|hip[óo]teses"
    r"|situa[çc][õo]es|lit[íi]gios|senten[çc]as|a[çc][õo]es\s+(?:semelhantes|similares|an[áa]logas"
    r"|id[êe]nticas|judiciais|ajuizadas|propostas|julgadas))\b")



L34_GRANDEZA_DEPOIS_RX = re.compile(
    r"\s*(?:\([^)]{0,60}\)\s*)?"

    r"(?:(?:a|e|até|ou)\s+\d+(?:[.,]\d+)?\s?%\s*(?:\([^)]{0,60}\)\s*)?)?"
    r",?\s*(?:(?:ou\s+mais|ou\s+menos|no\s+m[íi]nimo|no\s+m[áa]ximo|maiores|menores)\s+)?"
    r"(?:sobre\b|incidente|calculad|aplicad|em\s+rela[çc][ãa]o|(?:acima|abaixo|al[ée]m)\s+d"
    r"|(?:superior|inferior)\s+a"
    r"|d[oa]s?\s+(?!" + _L34_CONTAGEM + r")[A-Za-zÀ-ú]"
    r"|n[oa]s?\s+(?!" + _L34_NAO_GRANDEZA + r")[A-Za-zÀ-ú]"


    r"|(?:à|às|ao|aos)\s+" + _L34_GRANDEZAS + r"\b"
    r"|em\s+(?:(?:sua|seu|suas|seus|o|a|os|as)\s+)?(?!" + _L34_NAO_GRANDEZA + r")[A-Za-zÀ-ú])",
    re.I)




L34_CONSECTARIO_ANTES_RX = re.compile(
    r"\b(?:juros|multas?|honor[áa]rios|corre[çc][ãa]o\s+monet[áa]ria)\b[^.;:]{0,50}$", re.I)


L34_GRANDEZA_ANTES_RX = re.compile(
    r"\b(?:redu[çc][ãa]o|reajuste|aumento|majora[çc][ãa]o|desconto|abatimento|acr[ée]scimo"
    r"|eleva[çc][ãa]o|diminui[çc][ãa]o|reduz\w*|reajust\w*|aument\w*|major\w*|elev\w*|diminu\w*)"
    r"\s+(?:d[oa]s?|[oa]s?|sua|seu|suas|seus)\s+(?!" + _L34_NAO_GRANDEZA + r")[A-Za-zÀ-ú]+"
    r"(?:\s+[A-Za-zÀ-ú]+)?\s+em\s+(?:pelo\s+menos\s+|no\s+m[íi]nimo\s+|at[ée]\s+|cerca\s+de\s+"
    r"|mais\s+de\s+|menos\s+de\s+)?$", re.I)
L34_CADA_UM_RX = re.compile(r"\ba\s+cada\s+(?:um|uma)\b(?:\s+del[ea]s)?\s*,?\s*$", re.I)
L34_CARDINAL_RX = re.compile(
    r"\b(?:dois|duas|tr[êe]s|quatro|cinco|seis|sete|oito|nove|dez|\d+)\b", re.I)


L34_PROGNOSTICO_RX = re.compile(
    r"\bchances?\b|\bprobabilidades?\b|\bprov[áa]ve(?:l|is)\b|\bprogn[óo]stic\w*"
    r"|\b(?:possibilidade|expectativa|perspectiva|taxa|[íi]ndice|percentual)\s+de\s+"
    r"(?:[êe]xito|sucesso|vit[óo]ria|revers[ãa]o|provimento|ganho)", re.I)
L34_PERDA_CHANCE_RX = re.compile(r"perda\s+d[ae]\s+(?:uma\s+)?chance", re.I)
L34_DOC_FORTE_RX = re.compile(
    r"laudo|per[íi]cia|perit[oa]|parecer\s+(?:t[ée]cnico|cont[áa]bil|pericial)|\bdocs?\.\s*\d"
    r"|\bfls?\.\s*\d|\bID\s*\d|\bIBGE\b", re.I)


L34_FIM_FRASE_RX = re.compile(r"[.!?…]+(?=\s+[\"“«'(]?[A-ZÀ-ÖØ-Ý])|;")
L34_ABREVIATURAS = {
    "art", "arts", "inc", "incs", "al", "fl", "fls", "doc", "docs", "n", "nº", "no", "nr",
    "núm", "num", "min", "rel", "des", "dr", "dra", "drs", "sr", "sra", "srs", "exmo", "exma",
    "ilmo", "ilma", "mm", "p", "pp", "pág", "págs", "cf", "v", "vs", "c", "ex", "ed", "ltda",
    "cia", "prof", "profa", "etc", "s.a", "sa", "id", "cap", "tít", "tit", "par", "proc",
    "resp", "rec", "ag", "agr", "emb", "decl"}
L34_MIN_LETRAS_TRANSCRICAO = 15

def _l34_abreviatura(texto, pos):
    m = re.search(r"([\wºª.]+)$", texto[:pos])
    tok = (m.group(1) if m else "").strip(".").lower()
    return tok in L34_ABREVIATURAS or (len(tok) == 1 and tok.isalpha())

def _l34_frase(texto, ini, fim):
    'Texto da frase que contém texto[ini:fim] e seu início. Na enumeração com ponto e'


    a = a_frase = 0
    b = len(texto)
    for m in L34_FIM_FRASE_RX.finditer(texto):
        if m.group(0) != ";" and _l34_abreviatura(texto, m.start()):
            continue

        if m.group(0) == ";" and texto.count("(", 0, m.start()) > texto.count(")", 0, m.start()):
            continue
        if m.end() <= ini:
            a = m.end()
            if m.group(0) != ";":
                a_frase = a
        elif m.start() >= fim:
            b = m.end()
            break
    abertura = ""
    if a > a_frase:
        dois_pontos = texto.find(":", a_frase, a)
        if dois_pontos >= 0:
            abertura = texto[a_frase:dois_pontos + 1] + " "
    return abertura + texto[a:b], a

def _l34_letras_alem_do_numero(trecho):
    return sum(c.isalpha() for c in L34_PERCENTUAL_RX.sub(" ", trecho))

def _l34_mascara_curta_desfeita(texto, mascara):
    """Itálico que cobre só o número (ou quase) não é transcrição: o trecho volta a ser medido."""
    out = list(mascara)
    n, i = len(texto), 0
    while i < n:
        if mascara[i] == texto[i]:
            i += 1
            continue
        j = k = i
        while k < n and (mascara[k] != texto[k] or texto[k].isspace()):
            if mascara[k] != texto[k]:
                j = k + 1
            k += 1
        if _l34_letras_alem_do_numero(texto[i:j]) < L34_MIN_LETRAS_TRANSCRICAO:
            out[i:j] = texto[i:j]
        i = j
    return "".join(out)

def _l34_apagar_aspas(alvo):
    def _sub(m):
        if _l34_letras_alem_do_numero(m.group(0)) < L34_MIN_LETRAS_TRANSCRICAO:
            return m.group(0)
        return " " * len(m.group(0))
    alvo = L34_ASPAS_RX.sub(_sub, alvo)

    ini = len(alvo) - len(alvo.lstrip())
    if alvo[ini:ini + 1] in ("“", "«", '"'):
        fecha = {"“": "”", "«": "»", '"': '"'}[alvo[ini]]
        if fecha not in alvo[ini + 1:] and \
                _l34_letras_alem_do_numero(alvo[ini:]) >= L34_MIN_LETRAS_TRANSCRICAO:
            alvo = alvo[:ini] + " " * (len(alvo) - ini)
    for abre, fecha in (("“", "”"), ("«", "»")):
        pos = alvo.find(fecha)
        if pos >= 0 and abre not in alvo[:pos] and \
                _l34_letras_alem_do_numero(alvo[:pos]) >= L34_MIN_LETRAS_TRANSCRICAO:
            alvo = " " * (pos + 1) + alvo[pos + 1:]
    return alvo

def _l34_tem_lastro(texto, ini, fim):
    frase, a = _l34_frase(texto, ini, fim)
    if L34_PROGNOSTICO_RX.search(L34_PERDA_CHANCE_RX.sub(" ", frase)):
        return bool(L34_DOC_FORTE_RX.search(frase))
    if L34_GRANDEZA_DEPOIS_RX.match(texto, fim) or L34_LIGADO_DEPOIS_RX.match(texto, fim):
        return True
    antes = texto[a:ini]
    if L34_GRANDEZA_ANTES_RX.search(antes) or L34_LIGADO_ANTES_RX.search(antes[-80:]):
        return True
    if L34_CADA_UM_RX.search(antes) and \
            L34_CARDINAL_RX.search(L34_PERCENTUAL_RX.sub(" ", frase)):
        return True
    return bool(L34_NORMA_RX.search(frase) or L34_FONTE_RX.search(frase)
                or L34_BASE_RX.search(frase))

def l34_percentuais_sem_base(texto, mascara=None):
    'Percentuais de `texto` sem lastro. `mascara` (mesmo tamanho) é o texto com a'


    return [t for t, _c in l34_achados(texto, mascara)]

def l34_achados(texto, mascara=None):
    'Os mesmos achados de `l34_percentuais_sem_base`, cada um como (trecho, consectario):'


    if not texto or not re.search(r"%|por\s+cento", texto, re.I):
        return []
    alvo = texto
    if mascara is not None and len(mascara) == len(texto):
        alvo = _l34_mascara_curta_desfeita(texto, mascara)
    alvo = _l34_apagar_aspas(alvo)
    achados = []
    ocorrencias = [(m.start(), m.end()) for m in L34_PERCENTUAL_RX.finditer(alvo)]
    for m in L34_EXTENSO_RX.finditer(alvo):


        if not re.search(r"\d\s?%|\d\s+por\s+cento", alvo[max(0, m.start() - 60):m.end()], re.I):
            ocorrencias.append((max(0, m.start() - 30), m.end()))
    for ini, fim in ocorrencias:
        if _l34_tem_lastro(texto, ini, fim):
            continue
        frase, a = _l34_frase(texto, ini, fim)
        consectario = bool(L34_CONSECTARIO_ANTES_RX.search(texto[a:ini]))
        achados.append((texto[max(0, ini - 50):min(len(texto), fim + 30)].strip(), consectario))
    return achados

def l34_mensagem(trecho):
    return (f"L34 PERCENTUAL SEM BASE: «{trecho}». Diga de onde vem o percentual: a base "
            f"(sobre que valor, quantos de quantos), o documento que o traz (cláusula, laudo, "
            f"decisão, memória de cálculo) ou a norma que o fixa (artigo, lei, súmula).")

def l34_pendencia_mensagem(trecho):
    return (f"L34 CONSECTÁRIO SEM BASE: «{trecho}». Juros, multa, honorários ou correção com "
            f"percentual e sem a norma ou a base: cite o fundamento na frase (art. 406 do CC, "
            f"art. 523, § 1º, ou art. 85 do CPC, a cláusula do contrato) ou a base (sobre o valor "
            f"da condenação, da causa, do débito) e relinte.")







_L35_ITEM = r"^\s*(?:[-*+•–]\s+|\d+[.)]\s+)?"
_L35_QUESTAO = re.compile(_L35_ITEM + r"QUESTAO(?:\s+\(?\d+\)?)?\s*:")
_L35_DESCARTADA = re.compile(_L35_ITEM + r"(?:TESES?\s+)?DESCARTADAS?(?:\s+\(?\d+\)?)?\s*:")
_L35_MOTIVO = re.compile(_L35_ITEM + r"MOTIVO\s*:")


def l35_trechos_do_mapa(paragrafos):
    achados, apos_descartada = [], False
    for t in paragrafos:
        n = _sem_acento(t)
        if not n:
            continue
        if _L35_DESCARTADA.match(n):
            achados.append(t.strip())
            apos_descartada = True
            continue
        if _L35_QUESTAO.match(n) or (apos_descartada and _L35_MOTIVO.match(n)):
            achados.append(t.strip())
        apos_descartada = False
    return achados


def l35_mensagem(trecho):
    t = " ".join(str(trecho).split())
    t = (t[:70] + "…") if len(t) > 70 else t
    return (f"L35 TRECHO DO MAPA ARGUMENTATIVO NA PEÇA: «{t}». Questão, tese descartada "
            f"e motivo do descarte são controle do advogado e ficam no mapa; retire-os da peça.")

def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__); return 2



    global _disp, _comarca_padrao
    perfil = _perfil_do_ambiente()
    _disp = _dispensas_do_ambiente(perfil)
    _comarca_padrao = _comarca_do_ambiente(perfil)




    definir_tema(perfil)
    caminho = argv[0]
    fragmento = "--fragmento" in argv[1:]
    prec_path = jnt_path = conf_arg = grau_arg = sessao = None
    processos_arg = []
    for i, a in enumerate(argv):
        if a == "--precedentes" and i + 1 < len(argv):
            prec_path = argv[i + 1]
        if a == "--juntada" and i + 1 < len(argv):
            jnt_path = argv[i + 1]
        if a == "--conferencia" and i + 1 < len(argv):
            conf_arg = argv[i + 1]
        if a == "--grau" and i + 1 < len(argv):
            grau_arg = argv[i + 1].strip().lower()
        if a == "--processo" and i + 1 < len(argv):
            processos_arg.append(argv[i + 1].strip())
        if a == "--session-id" and i + 1 < len(argv):
            sessao = argv[i + 1].strip()
    if grau_arg and grau_arg not in grau_jurisdicao.GRAUS:
        print(f"REPROVADO: --grau '{grau_arg}' inválido — use um de "
              f"{', '.join(grau_jurisdicao.GRAUS)}")
        return 1
    try:
        caminho, prec_path, jnt_path, conf_arg = (
            no_caso(caminho, sessao), no_caso(prec_path, sessao), no_caso(jnt_path, sessao),
            no_caso(conf_arg, sessao))
    except CaminhoRecusado as e:
        print(f"REPROVADO: {e}")
        return 1


    grau_do_estado_lido = None
    if not grau_arg:
        grau_arg, grau_do_estado_lido = grau_do_estado(caminho, sessao)
    try:
        with zipfile.ZipFile(caminho) as z:
            xml = z.read("word/document.xml").decode("utf-8")
            try:
                _custom = z.read(PARTE_CARIMBO_MINUTA).decode("utf-8", "replace")
            except KeyError:
                _custom = ""
    except Exception as e:
        print(f"REPROVADO: .docx ilegível — {e}"); return 1

    marca_minuta = bool(re.search(
        r'name="' + PROP_MINUTA_PENDENCIAS + r'"[^>]*>\s*<[^>]*>\s*1\s*<', _custom))
    try:
        body = ET.fromstring(xml).find(W + "body")
    except ET.ParseError as e:
        print(f"REPROVADO: XML malformado — {e}"); return 1
    if body is None:
        print("REPROVADO: estrutura inesperada — <body> ausente no document.xml"); return 1
    paras = coleta(body)






    erros, pendencias, avisos = [], [], []

    def cite(t):
        t = t.strip().replace("\n", " ")
        return (t[:70] + "…") if len(t) > 70 else t

    def _so_imagem(registro):
        'O registro não fornece fonte literal: lido só por imagem (regra 8), ou todo o teor'

        if conferencia_contract.lido_so_por_imagem(registro):
            return True
        return bool(registro.get("trechos")) and not conferencia_contract.trechos_de_texto(registro)

    def _l14_imagem(numeros, trecho):
        'L14 IMAGEM: transcrição literal atribuída a documento lido só por imagem (regra 8'


        rotulo = ", ".join(f"{n:02d}" for n in numeros)
        return (f"L14 IMAGEM transcrição literal atribuída a (Doc. {rotulo}), documento lido só "
                f"por imagem: a leitura visual permite descrever o documento e remeter a ele, "
                f"não reproduzir o texto dele entre aspas (governança §3). Troque a transcrição "
                f"pela descrição do que o documento mostra, com a referência (Doc. {rotulo}), ou "
                f"obtenha cópia com texto (OCR) e registre de novo a leitura: «{cite(trecho)}»")

    def _l14_imagem_parcial(numeros, trecho):
        'L14 IMAGEM de documento com PARTE das páginas sem camada de texto (regra 9): a'

        rotulo = ", ".join(f"{n:02d}" for n in numeros)
        return (f"L14 IMAGEM transcrição literal atribuída a (Doc. {rotulo}), documento com "
                f"página(s) sem camada de texto, lidas só por imagem, e ela não confere com o texto "
                f"extraído das demais páginas: o que se viu na página digitalizada se descreve, não "
                f"se reproduz entre aspas (governança §3). Troque a transcrição pela descrição, com "
                f"a referência (Doc. {rotulo}), ou obtenha cópia com texto (OCR) e registre de novo "
                f"a leitura: «{cite(trecho)}»")

    textos = []
    for p, em_tbl in paras:
        rs = runs_do_paragrafo(p)
        txt = "".join(t for t, _, _, _, _ in rs)
        textos.append((txt, em_tbl, p, rs))
    texto_total = "\n".join(t for t, _, _, _ in textos)


    for txt, _, _, _ in textos:
        if "\\n" in txt:
            erros.append(f"L1 \\n literal no texto: «{cite(txt)}»")


    for txt, _, _, _ in textos:
        for m in ENTIDADE_RX.finditer(txt):
            if m.group(0) not in ("&amp;",):
                erros.append(f"L2 entidade HTML crua «{m.group(0)}» em: «{cite(txt)}»")



    for txt, em_tbl, _, _ in textos:
        if em_tbl:
            continue
        curvas = [c for c in txt if c in "“”‘’"]
        if curvas:
            erros.append(f"L3 {len(curvas)} aspas tipográficas em: «{cite(txt)}»")



    for txt, _, p, rs in textos:
        offs, pos = [], 0
        for t, _b, hl, _i, _u in rs:
            offs.append((pos, pos + len(t), hl)); pos += len(t)
        for m in PLACEHOLDER_RX.finditer(txt):
            conteudo = m.group(0).upper()
            if any(k in conteudo for k in PLACEHOLDER_KEYS):
                realce = next((hl for a, b2, hl in offs if a <= m.start() < b2), False)
                if not realce:
                    erros.append(f"L4 placeholder SEM realce amarelo: «{cite(m.group(0))}»")


    for txt, _, _, _ in textos:
        marcas = ITEM_RX.findall(txt)
        if len(marcas) >= 3 and len(txt) > 300:
            erros.append(f"L5 {len(marcas)} itens aglutinados num único parágrafo: «{cite(txt)}»")



    def _eh_inicio_corpo(t):
        t = t.strip()
        return (t.upper().startswith("CAPÍTULO")
                or bool(re.match(r"^[IVX]+\s*[-–.)]\s", t))
                or t.upper().startswith(("DOS FATOS", "DO DIREITO", "DOS FATOS E")))
    inicio_corpo = next((i for i, (t, _, _, _) in enumerate(textos) if _eh_inicio_corpo(t)), None)
    inicio_corpo_achado = inicio_corpo is not None
    inicio_corpo = inicio_corpo or 0


    recuo_esc = recuo_do_escritorio(perfil)
    minimo = 700 if not recuo_esc else min(700, recuo_esc - 8)
    for txt, em_tbl, p, _ in ([] if recuo_esc == 0 else textos[inicio_corpo:]):
        t = txt.strip()
        if em_tbl or len(t) < 250 or LISTA_INICIO_RX.match(t):
            continue
        if not first_line_recuo(p, minimo):
            erros.append(f"L6 corpo sem recuo de 1ª linha (~{recuo_esc or 708}): «{cite(t)}»")









    if recuo_esc != 0 and inicio_corpo_achado:
        for txt, em_tbl, p, _ in textos[inicio_corpo:]:
            t = txt.strip()
            if (em_tbl or not t or len(t) >= 250 or LISTA_INICIO_RX.match(t)
                    or e_item_de_lista(p) or first_line_recuo(p, minimo)):
                continue
            _ppr = p.find(W + "pPr")
            _jc = _ppr.find(W + "jc") if _ppr is not None else None
            if _jc is not None and _jc.get(W + "val") in ("center", "centro", "right", "end"):
                continue
            if l30_lead_in_longo(t):
                avisos.append(l30_mensagem(t))




    if _pa is not None:
        try:
            _marcas = _pa.marcas_proibidas()
        except Exception:
            _marcas = []
        if _marcas:
            for _termo, _n in _pa.achar_marcas("\n".join(t for t, _, _, _ in textos), _marcas):
                avisos.append(f"L31 MARCA PROIBIDA pela Voz do advogado: «{_termo}» ({_n}×). Troque a "
                              f"expressão ou confirme com o advogado que, aqui, ela fica.")






    _itens_l33 = []
    for txt, em_tbl, p, rs in textos:
        _marc = rs[0][0].strip() if rs else ""


        _pedido = (bool(rs) and rs[0][1] and not first_line_recuo(p, minimo=1)
                   and bool(re.fullmatch(r"\(?[0-9]{1,3}(?:\.[0-9]{1,3})*[.)]?", _marc)))
        _itens_l33.append((txt, "outro" if (em_tbl or _pedido or e_item_de_lista(p)) else "corpo"))
    _achados_l33 = l33_paragrafos_numerados(_itens_l33)
    if _achados_l33:
        erros.append(l33_mensagem(_achados_l33))



    for txt, em_tbl, _p, rs in textos:
        if em_tbl or "%" not in txt and "cento" not in txt.lower():
            continue
        _masc = "".join((" " * len(t)) if it else t for t, _b, _hl, it, _u in rs)
        for _trecho, _consectario in l34_achados(txt, _masc):
            if _consectario:
                pendencias.append(l34_pendencia_mensagem(_trecho))
            else:
                erros.append(l34_mensagem(_trecho))



    for _trecho in l35_trechos_do_mapa([txt for txt, em_tbl, _p, _rs in textos if not em_tbl]):
        erros.append(l35_mensagem(_trecho))


    ordem, vistos = [], set()
    for txt, _, _, rs in textos:
        for n in numeros_doc(txt):
            if n not in vistos:
                vistos.add(n); ordem.append(n)
        for t, b, _, _, _ in rs:
            if "(Doc." in t and not b:
                erros.append(f"L7 referência (Doc. XX) fora de negrito em: «{cite(txt)}»")
                break
    if ordem:

        inicio = min(ordem)
        esperado = list(range(inicio, inicio + len(ordem)))
        if inicio not in (1, 2) or sorted(ordem) != esperado:
            erros.append(f"L7 numeração de documentos com salto/lacuna — 1ª citação na ordem {ordem}; "
                         f"esperado contador contínuo a partir de 01 (ou 02 com GUIA) — regra dissero-juntada")
        elif ordem != esperado:
            avisos.append(f"L7 1ª citação fora de ordem crescente: {ordem} (confira contra o tracker "
                          f"com `--juntada JUNTADA_TRACKER.json` — o cruzamento abre o ledger)")









    tracker = por_numero = None
    if jnt_path:
        docs_citados = sorted(vistos)
        try:
            tracker = json.load(open(jnt_path, encoding="utf-8"))
            if not isinstance(tracker, dict) or tracker.get("schema_version") != JUNTADA_SCHEMA:
                raise ValueError(f"contrato {JUNTADA_SCHEMA} obrigatório; gere o ledger com a "
                                 "dissero-juntada em vez de converter à mão")
            erros_contrato = juntada_contract.validar_documento(tracker)
            if erros_contrato:
                raise ValueError("ledger fora do contrato — rode `validar_juntada.py` antes: "
                                 + "; ".join(erros_contrato[:3]))
            por_numero = juntada_contract.indexar_por_numero(tracker)
        except Exception as e:
            erros.append(f"CRUZAMENTO-DOC: --juntada ilegível — {e}")
            por_numero = None
        if por_numero is not None:
            for n in docs_citados:
                doc = por_numero.get(n)
                if doc is None:
                    erros.append(f"CRUZAMENTO-DOC: (Doc. {n:02d}) citado na peça e AUSENTE do ledger da "
                                 f"juntada — todo documento citado precisa do registro curado "
                                 f"(governança §2.8)")
                    continue
                status = doc.get("status")
                if status != "curado":
                    erros.append(f"CRUZAMENTO-DOC: (Doc. {n:02d}) consta no ledger com status "
                                 f"{status!r} — só documento CURADO pode ser citado na peça "
                                 f"(«{cite(str(doc.get('descricao')))}»)")
                elif not (doc.get("evidence_ids") or []):
                    erros.append(f"CRUZAMENTO-DOC: (Doc. {n:02d}) curado SEM evidence_ids — citação sem "
                                 f"bloco de leitura na conferência de ingestão (§2.8)")







    if vistos and not jnt_path:
        erros.append(
            f"L13 peça cita {len(vistos)} documento(s) — (Doc. "
            + ", ".join(f"{n:02d}" for n in sorted(vistos))
            + ") — e o ledger da juntada NÃO foi apresentado (--juntada ausente): artefato "
              "OBRIGATÓRIO do rito (governança §2.8/§3). Sem ele nada prova que o documento "
              "citado existe, foi lido e está curado. Monte/valide o ledger com "
              "`python validar_juntada.py JUNTADA_TRACKER.json --conferencia CONFERENCIA.json` "
              "(skill dissero-juntada) e relinte com `--juntada JUNTADA_TRACKER.json`.")


















    _idx_de = {id(p): i for i, (_t, _e, p, _r) in enumerate(textos)}
    _corpo_idx = [i for i, (t, e, _p, _r) in enumerate(textos) if not e and t.strip()]

    def _ponte(t):
        t = t.strip()
        return t.endswith(":") or len(t) < 40

    def _refs_vizinhas(i, j, so_transcricao=False, distante=None):
        import bisect
        nums = set()
        k = bisect.bisect_left(_corpo_idx, i) - 1
        if k >= 0:
            idx = _corpo_idx[k]
            antes = set(numeros_doc_amplo(textos[idx][0]))










            if not antes and so_transcricao and not nomeia_outra_fonte(textos[idx][0]):
                passos = 0
                longe = 0 if _ponte(textos[idx][0]) else 1
                for q in range(idx - 1, -1, -1):
                    tq, em_q, _pq, _rq = textos[q]
                    if not tq.strip():
                        continue
                    if em_q or passos >= 4:
                        break
                    passos += 1
                    antes = set(numeros_doc_amplo(tq))
                    if antes or nomeia_outra_fonte(tq):
                        break
                    if not _ponte(tq):
                        longe += 1
                if antes and longe >= 2 and distante is not None:
                    distante.append(True)
            elif not antes and _ponte(textos[idx][0]):
                for q in range(idx - 1, -1, -1):
                    tq, em_q, _pq, _rq = textos[q]
                    if not tq.strip():
                        continue
                    if em_q:
                        break
                    antes = set(numeros_doc_amplo(tq))
                    if antes or not _ponte(tq):
                        break




                if antes and distante is not None and nomeia_outra_fonte(textos[idx][0]):
                    distante.append(True)
            nums |= antes
        k = bisect.bisect_right(_corpo_idx, j)
        if k < len(_corpo_idx):
            nums |= set(numeros_doc_amplo(textos[_corpo_idx[k]][0]))
        return sorted(nums)

    citacoes_de_prova = []


    citacoes_de_corpo = []
    for tbl in body.iter(W + "tbl"):
        linhas = [(pp, runs_do_paragrafo(pp)) for pp in tbl.iter(W + "p")]
        textos_tbl = ["".join(t for t, _b, _h, _i, _u in rs) for _pp, rs in linhas]
        primeira = next((t.strip() for t in textos_tbl if t.strip()), "")
        if primeira.upper().startswith("JURISPRUD"):
            continue
        caixa = "\n".join(textos_tbl)
        numeros = sorted(set(numeros_doc(caixa)))
        trechos = []
        for (_pp, rs), t in zip(linhas, textos_tbl):
            if not t.strip() or not rs:
                continue


            if all(it for _t, _b, _h, it, _u in rs if _t.strip()):
                trechos.append(t)
        if not trechos:
            continue
        if numeros:
            citacoes_de_prova.append((numeros, trechos, caixa))
            continue



        _ids = [_idx_de[id(pp)] for pp, _rs in linhas if id(pp) in _idx_de]
        if _ids and conferencia_contract is not None:
            longos = [(t, "literal") for t in trechos
                      if len(conferencia_contract.normalizar_trecho(t)) >= 25]
            proprios = sorted(set(numeros_doc_amplo(caixa)))
            if longos and proprios:
                citacoes_de_corpo.append((proprios, longos, False, caixa))
                continue
            _dist = []
            vizinhos = _refs_vizinhas(min(_ids), max(_ids), True, _dist)
            if longos and vizinhos:
                if _dist:
                    longos = [(t, "distante") for t, _tp in longos]
                citacoes_de_corpo.append((vizinhos, longos, True, caixa))



















    if conferencia_contract is not None:
        _norm = conferencia_contract.normalizar_trecho
        for i, (txt, em_tbl, _par, rs) in enumerate(textos):
            if em_tbl or not txt.strip():
                continue
            cands = []
            for m in ASPAS_RX.finditer(txt):
                a = next(g for g in m.groups() if g is not None)
                if aspas_de_norma(txt, m.start(), m.end()):
                    tipo_a = "norma"
                elif aspas_de_outra_fonte(txt, m.start(), m.end()):
                    tipo_a = "processual"
                else:
                    tipo_a = None
                cands.append((a, tipo_a, True))
            italicos, seg = [], []
            for _t, _b, _h, it, _u in rs:
                if it or (seg and not _t.strip()):
                    seg.append(_t)
                elif seg:
                    italicos.append("".join(seg))
                    seg = []
            if seg:
                italicos.append("".join(seg))
            for a in italicos:
                n_pal = len(a.split())
                if n_pal >= 12 or (n_pal >= 6 and (tem_pontuacao_de_frase(a)
                                                   or tem_valor_ou_data(a)
                                                   or tem_declaracao(a))):



                    tipo_i = None
                    ini = txt.find(a.strip())
                    if ini >= 0:
                        fim_i = ini + len(a.strip())
                        if aspas_de_norma(txt, ini, fim_i):
                            tipo_i = "norma"
                        elif aspas_de_outra_fonte(txt, ini, fim_i):
                            tipo_i = "processual"
                    cands.append((a, tipo_i, False))
                elif n_pal >= 6:



                    cands.append((a, "italico", False))
            if txt.lstrip().startswith(">"):
                cands.append((txt.lstrip().lstrip(">").strip(), None, False))
            vistos_c, aspas, curtos = set(), [], []
            for a, tipo, entre_aspas in cands:
                chave = _norm(a)
                if not chave or chave in vistos_c:
                    continue
                vistos_c.add(chave)
                if len(chave) >= 25:
                    if tipo is None and entre_aspas and parece_nome(a):
                        tipo = "nome"
                    aspas.append((a, tipo or "literal"))
                elif entre_aspas and tipo is None:
                    curtos.append(a)
            if len(curtos) >= 2 and sum(len(_norm(c)) for c in curtos) >= 25:
                aspas.append((" […] ".join(curtos),
                              "literal" if any(tem_pontuacao_de_frase(c) or tem_valor_ou_data(c)
                                               for c in curtos)
                              else "nome"))
            if not aspas:
                continue
            numeros = sorted(set(numeros_doc_amplo(txt)))
            vizinho = not numeros
            if vizinho:
                _limpo = txt.strip().rstrip(".;,").strip()
                so_transcricao = (bool(ASPAS_RX.fullmatch(_limpo))
                                  or txt.lstrip().startswith(">")
                                  or (bool(rs) and all(it for _t, _b, _h, it, _u in rs
                                                       if _t.strip())))
                _dist = []
                numeros = _refs_vizinhas(i, i, so_transcricao, _dist)
                if _dist:
                    aspas = [(a, "distante" if tp == "literal" else tp) for a, tp in aspas]
            if numeros:
                citacoes_de_corpo.append((numeros, aspas, vizinho, txt))

    conf_path = None
    if citacoes_de_prova or citacoes_de_corpo:
        conf_path = conf_arg
        if not conf_path and isinstance(tracker, dict):
            declarado = str(tracker.get("conferencia") or "").strip()
            if declarado:
                conf_path = declarado
                if not os.path.isabs(conf_path):
                    vizinho = os.path.join(os.path.dirname(os.path.abspath(jnt_path)), conf_path)
                    conf_path = vizinho if os.path.isfile(vizinho) else conf_path
    dados_conf = None
    if not citacoes_de_prova and citacoes_de_corpo and conf_path:


        try:
            dados_conf = json.load(open(conf_path, encoding="utf-8"))
            if (not isinstance(dados_conf, dict)
                    or dados_conf.get("schema_version") != CONFERENCIA_SCHEMA):
                raise ValueError(f"contrato {CONFERENCIA_SCHEMA} obrigatório")
        except Exception as e:
            dados_conf = None
            avisos.append(f"L14 conferência de ingestão ilegível ({conf_path}) — {e}; as "
                          "transcrições entre aspas no corpo ficaram sem conferência")

    if citacoes_de_prova:
        if conferencia_contract is None:
            erros.append(
                "L14 conferencia_contract.py indisponível ao lado do linter — a conferência "
                "literal de prova não pode ser medida, e linter que não mede não aprova")
            conf_path = None
        if conferencia_contract is not None and not conf_path:
            erros.append(
                f"L14 a peça transcreve prova documental em {len(citacoes_de_prova)} caixa(s) de "
                "citação e a conferência de ingestão NÃO está disponível: sem ela não há contra o "
                "que conferir a transcrição palavra a palavra (governança §3). Aponte o dataset "
                "com `--conferencia CONFERENCIA.json` ou grave o caminho no campo `conferencia` "
                "do ledger da juntada.")
        elif conf_path:
            try:
                dados_conf = json.load(open(conf_path, encoding="utf-8"))
                if (not isinstance(dados_conf, dict)
                        or dados_conf.get("schema_version") != CONFERENCIA_SCHEMA):
                    raise ValueError(f"contrato {CONFERENCIA_SCHEMA} obrigatório")
            except Exception as e:
                dados_conf = None
                erros.append(f"L14 conferência de ingestão ilegível ({conf_path}) — {e}")
        if dados_conf is not None:
            por_sha = {d.get("sha256_arquivo"): d for d in (dados_conf.get("documentos") or [])}
            for numeros, trechos, caixa in citacoes_de_prova:



                armazenados, sem_registro, registros, por_imagem = [], [], [], []
                for n in numeros:
                    doc = (por_numero or {}).get(n)
                    sha = str((doc or {}).get("sha256_arquivo") or "")
                    registro = por_sha.get(sha) if sha else None
                    if registro is None:
                        sem_registro.append(n)
                        continue
                    if _so_imagem(registro):
                        por_imagem.append(n)
                        continue
                    registros.append((n, registro))
                    armazenados += [t.get("trecho_literal") or ""
                                    for t in conferencia_contract.trechos_de_texto(registro)]
                rotulo = ", ".join(f"{n:02d}" for n in numeros)
                if not armazenados and por_imagem:


                    for trecho in trechos:
                        if len(conferencia_contract.normalizar_trecho(trecho)) >= 25:
                            erros.append(_l14_imagem(por_imagem, trecho))
                    continue
                if not armazenados:
                    falta = ", ".join(f"{n:02d}" for n in sem_registro) or rotulo
                    erros.append(
                        f"L14 transcrição atribuída a (Doc. {rotulo}) sem teor registrado na "
                        f"conferência (documento {falta} não lido ou fora do dataset): não se "
                        f"transcreve o que não foi lido (§2.8)")
                    continue
                for trecho in trechos:
                    if not conferencia_contract.confere_transcricao(trecho, armazenados):
                        if por_imagem and len(conferencia_contract.normalizar_trecho(trecho)) >= 25:


                            erros.append(_l14_imagem(por_imagem, trecho))
                            continue
                        erros.append(
                            f"L14 transcrição NÃO confere com o documento lido (Doc. {rotulo}) — "
                            f"conferência literal palavra a palavra falhou (§3): "
                            f"«{cite(trecho)}»")
                    elif not conferencia_contract.confere_transcricao(trecho, armazenados,
                                                                        manter_acento=True):

                        avisos.append(
                            f"L14 grafia divergente do original (Doc. {rotulo}): a transcrição confere "
                            f"palavra a palavra, mas o acento difere do documento lido; transcrição "
                            f"literal reproduz a grafia do original: «{cite(trecho)}»")









                folhas = set()
                for m in FOLHA_RX.finditer(caixa):
                    folhas |= {int(d) for d in re.findall(r"\d{1,5}", m.group(1))}
                if not folhas or not registros:
                    continue
                nao_declarados = [(n, conferencia_contract.numeracao_de(reg))
                                  for n, reg in registros
                                  if conferencia_contract.numeracao_de(reg) != "autos"]
                if nao_declarados:




                    detalhe = ", ".join(
                        f"Doc. {n:02d}: {(num or 'não declarada')}" for n, num in nao_declarados)
                    avisos.append(
                        f"L15 folha {', '.join(str(f) for f in sorted(folhas))} SEM conferência — "
                        f"a numeração do dataset não permite conferi-la ({detalhe}). Para que o "
                        f"L15 confira, reingira com `--numeracao autos --pagina-inicial <folha da "
                        f"1ª página>`; sem isso a folha citada é responsabilidade da revisão (§3)")
                    continue
                for trecho in trechos:
                    paginas = set()
                    for _n, reg in registros:
                        paginas |= conferencia_contract.paginas_do_trecho(trecho, reg)
                    if not paginas:



                        avisos.append(
                            f"L15 folha não localizada para a transcrição de (Doc. {rotulo}) — "
                            f"trecho atravessa página ou não tem página registrada; a folha "
                            f"{', '.join(str(f) for f in sorted(folhas))} ficou SEM conferência: "
                            f"«{cite(trecho)}»")
                        continue
                    if not (folhas & paginas):
                        erros.append(
                            f"L15 folha citada NÃO corresponde à do documento lido "
                            f"(Doc. {rotulo}) — a peça aponta "
                            f"{', '.join(str(f) for f in sorted(folhas))} e o trecho foi lido na "
                            f"folha {', '.join(str(p) for p in sorted(paginas))}: "
                            f"«{cite(trecho)}»")














    if dados_conf is not None and citacoes_de_corpo:
        por_sha_corpo = {d.get("sha256_arquivo"): d for d in (dados_conf.get("documentos") or [])}
        sem_registro_corpo = set()
        for numeros, aspas, vizinho, contexto in citacoes_de_corpo:
            por_imagem, parcial, fonte = [], [], []
            for n in numeros:
                doc_ledger = (por_numero or {}).get(n)
                sha = str((doc_ledger or {}).get("sha256_arquivo") or "")
                registro = por_sha_corpo.get(sha) if sha else None
                if registro is None:
                    if doc_ledger is not None:
                        sem_registro_corpo.add(n)
                    continue
                if _so_imagem(registro):
                    por_imagem.append(n)
                    continue
                fonte += [t.get("trecho_literal") or ""
                          for t in conferencia_contract.trechos_de_texto(registro)]
                if registro.get("paginas_sem_texto"):
                    parcial.append(n)
            if not por_imagem and not parcial:
                continue
            outra_fonte = vizinho and bool(nomeia_outra_fonte(contexto)
                                           or FOLHA_RX.search(contexto))
            alvo = sorted(set(por_imagem) | set(parcial))
            rotulo_img = ", ".join(f"{n:02d}" for n in alvo)
            for trecho, tipo in aspas:
                if fonte and conferencia_contract.confere_transcricao(trecho, fonte):
                    continue
                if outra_fonte:
                    avisos.append(
                        f"L14 IMAGEM confira a transcrição: o parágrafo vizinho remete a documento "
                        f"lido só por imagem (Doc. {rotulo_img}) e este nomeia outra fonte; se o "
                        f"trecho vem do documento, troque a transcrição por descrição: "
                        f"«{cite(trecho)}»")
                elif tipo == "nome":
                    avisos.append(
                        f"L14 IMAGEM confira o trecho entre aspas atribuído a (Doc. {rotulo_img}), "
                        f"documento lido só por imagem: parece nome ou título do documento, não "
                        f"transcrição; se for texto do documento, troque por descrição: "
                        f"«{cite(trecho)}»")
                elif tipo == "processual":
                    avisos.append(
                        f"L14 IMAGEM confira o trecho entre aspas: vem precedido da peça, da "
                        f"decisão ou do depoimento de onde foi tirado, e o parágrafo remete a "
                        f"(Doc. {rotulo_img}), documento lido só por imagem; se o trecho for do "
                        f"documento, troque a transcrição por descrição: «{cite(trecho)}»")
                elif tipo == "italico":
                    avisos.append(
                        f"L14 IMAGEM confira o trecho em itálico atribuído a (Doc. {rotulo_img}), "
                        f"documento lido só por imagem: se for texto do documento, e não título "
                        f"de obra ou expressão, troque a transcrição por descrição: "
                        f"«{cite(trecho)}»")
                elif tipo == "distante":
                    avisos.append(
                        f"L14 IMAGEM confira a transcrição: a referência a (Doc. {rotulo_img}), "
                        f"documento lido só por imagem, está mais de um parágrafo acima, e os "
                        f"parágrafos entre ela e o trecho podem introduzir outra fonte; se o "
                        f"trecho vem do documento, troque a transcrição por descrição: "
                        f"«{cite(trecho)}»")
                elif tipo == "norma":
                    avisos.append(
                        f"L14 IMAGEM confira o trecho entre aspas: vem precedido de norma, julgado "
                        f"ou doutrina, e o parágrafo remete a (Doc. {rotulo_img}), documento lido "
                        f"só por imagem; se o trecho for do documento, troque a transcrição por "
                        f"descrição: «{cite(trecho)}»")
                else:
                    msg = (_l14_imagem(por_imagem, trecho) if por_imagem
                           else _l14_imagem_parcial(parcial, trecho))
                    erros.append(msg + (" [a referência ao documento está no parágrafo vizinho]"
                                        if vizinho else ""))
        if sem_registro_corpo:
            rot = ", ".join(f"{n:02d}" for n in sorted(sem_registro_corpo))
            avisos.append(
                f"L14 sem registro na conferência: (Doc. {rot}) recebe transcrição na peça e não "
                f"consta da conferência de ingestão apontada — não se sabe se foi lido só por "
                f"imagem, caso em que a transcrição literal não tem fonte (L14 IMAGEM). Registre a "
                f"leitura do documento na conferência antes de transcrevê-lo.")






    if (citacoes_de_corpo and dados_conf is None and not conf_path
            and conferencia_contract is not None and por_numero is not None):
        _docs = sorted({n for numeros, _a, _v, _c in citacoes_de_corpo for n in numeros})
        avisos.append(
            f"L14 sem conferência: {sum(len(a) for _n, a, _v, _c in citacoes_de_corpo)} "
            f"transcrição(ões) atribuída(s) a (Doc. {', '.join(f'{n:02d}' for n in _docs)}) e o "
            f"ledger da juntada não aponta a conferência de ingestão — não se sabe se o documento "
            f"foi lido só por imagem, caso em que a transcrição literal não tem fonte (L14 "
            f"IMAGEM). Aponte `--conferencia CONFERENCIA.json` ou grave o campo `conferencia` "
            f"do ledger.")












    for m in PLACEHOLDER_RX.finditer(texto_total):
        c = m.group(0).upper()
        if not L8_VERBOS_RX.search(c):
            continue
        if "JURISPRUD" in c or L8_SUMULA_RX.search(c):



            pendencias.append(f"L8 jurisprudência assinalada e ainda por substituir pelo julgado "
                              f"real — impede o protocolo: «{cite(m.group(0))}»")
        elif L8_NORMA_RX.search(c):
            pendencias.append(f"L8 dispositivo legal assinalado e ainda por conferir na redação "
                              f"e na vigência da data que rege o fato ou o ato — impede o "
                              f"protocolo: «{cite(m.group(0))}»")



    if marca_minuta or any(tem_faixa_minuta(t) for t, _, _, _ in textos):
        pendencias.append("L32 MINUTA COM PENDÊNCIAS: documento gerado por ordem do advogado "
                          "antes da conclusão da revisão; não é a peça liberada e não se "
                          "protocola como está")
    for i, (txt, em_tbl, _, _) in enumerate(textos):
        if em_tbl and txt.strip().upper().startswith("JURISPRUD"):
            nxt = textos[i + 1] if i + 1 < len(textos) else None
            if (nxt is None or not nxt[1] or not nxt[0].strip()
                    or nxt[0].strip().upper().startswith("JURISPRUD")):
                erros.append("L8 caixa de jurisprudência VAZIA — só o cabeçalho, sem julgado; impede protocolo")








    def _num_norm(t):
        return re.sub(r"(?<=\d)\s+(?=\d)", "", DATA_RX.sub(" ", t))





    def _so_digitos(s):
        return re.sub(r"\D", "", s or "")
    proc_proprios = {_so_digitos(p) for p in processos_arg if _so_digitos(p)}




    if not proc_proprios and not fragmento:
        capa = "\n".join(t for t, _e, _p, _r in textos[:30])
        auto = {_so_digitos(m.group(0)) for m in CNJ_RX.finditer(capa)}
        if auto:
            proc_proprios = auto
            avisos.append(
                f"CALIBRAÇÃO: `--processo` não foi passado; o número dos autos foi INFERIDO da "
                f"capa ({', '.join(sorted(CNJ_RX.findall(capa))[:3])}) e sai da heurística de "
                f"julgado e da contagem de repetição. Recursos DERIVADOS destes autos (agravo, "
                f"embargos) não são inferíveis — passe-os com `--processo` para que também "
                f"saiam")

    def _eh_entrada_julgado(t, em_tbl=False):
        'Parágrafo que IDENTIFICA um precedente — não qualquer prosa com número e relator.'













        norm = _num_norm(t)
        if not NUM_PROC_RX.search(norm):
            return False
        nums = {_so_digitos(n) for n in NUM_PROC_RX.findall(norm)}
        if nums and nums <= proc_proprios:
            return False
        if AUTOS_PROPRIOS_RX.search(t):
            return False
        forte = bool(TRIB_ANY_RX.search(t)) and bool(IND_JULGADO_RX.search(t))
        if forte:
            return True
        fraco = bool(TRIB_ANY_RX.search(t)) or bool(IND_JULGADO_RX.search(t))
        if not fraco:
            return False
        return bool(em_tbl) or len(t.strip()) <= 320
    for txt, em_tbl, _, _ in textos:
        t = txt.strip()
        if not em_tbl and t.upper().startswith("JURISPRUD") and len(t) < 40:
            erros.append("L9 banner 'JURISPRUDÊNCIA' FORA de tabela — jurisprudência deve ir na caixa "
                         "(::: jurisprudencia)")
            continue
        if not _eh_entrada_julgado(t, em_tbl):
            continue
        up = t.upper()
        n_nums = len(NUM_PROC_RX.findall(_num_norm(t)))
        if n_nums > 1:
            erros.append(f"L9 {n_nums} julgados num só parágrafo — UM julgado por parágrafo: «{cite(t)}»")


        if ("CONFIRMADO" in up or "PARCIAL" in up):
            erros.append(f"L9 selo de verificação ('CONFIRMADO'/'PARCIAL') na peça protocolável — "
                         f"o selo pertence à Relação de Precedentes, não à peça: «{cite(t)}»")
        if URL_RX.search(t):
            erros.append(f"L9 URL de fonte na identificação do julgado na peça — o link vai para a "
                         f"Relação de Precedentes (build_precedentes.py), não para a peça: «{cite(t)}»")




    for txt, em_tbl, _, _ in textos:
        if em_tbl:
            continue
        for m in DATA_HIFEN_RX.finditer(txt):
            erros.append(f"L10 data com hífen no texto autoral (use DD/MM/AAAA): «{m.group(0)}» em «{cite(txt)}»")













    julgados_citados = [t.strip() for t, _em, _p, _rs in textos
                        if _eh_entrada_julgado(t.strip(), _em)]
    st_citadas = {}
    for _t, _em, _p, _rs in textos:
        for _c in citacoes_sumula_tema(_t):
            st_citadas.setdefault(_c[4], _c)
    if st_citadas and not prec_path:
        erros.append(
            f"L11 FAIL-CLOSED: peça cita súmula ou tema ({', '.join(list(st_citadas)[:6])}) e a "
            f"Relação de Precedentes NÃO foi apresentada (--precedentes ausente). Súmula e tema "
            f"são precedentes como o julgado: a tese literal e o status vão conferidos na Relação. "
            f"Gere-a com `python build_precedentes.py achados.json` e relinte com "
            f"`--precedentes achados.json`.")
    if julgados_citados and not prec_path:
        erros.append(
            f"L11 FAIL-CLOSED: peça cita {len(julgados_citados)} julgado(s) e a Relação de "
            f"Precedentes NÃO foi apresentada (--precedentes ausente) — artefato OBRIGATÓRIO "
            f"do rito: a peça leva o julgado, a Relação leva a prova (selo, URL e ementa "
            f"literal, que o L9 proíbe na peça). Gere-a com "
            f"`python build_precedentes.py achados.json -o \"Relação de "
            f"Precedentes — <caso>.docx\"` e relinte com `--precedentes achados.json`. "
            f"1º julgado: «{cite(julgados_citados[0])}»")



    if prec_path:
        try:
            dados = json.load(open(prec_path, encoding="utf-8"))
            if (not isinstance(dados, dict)
                    or dados.get("schema_version") not in ("dsr.achados.v2", "dsr.achados.v3")):
                raise ValueError("o dataset precisa estar em dsr.achados.v2 ou v3; registro em "
                                 "outra versão não tem conversão: refaça a pesquisa e grave em "
                                 "dsr.achados.v3")
            achados = dados.get("achados", [])
            erros_estrategia, pendencias_estrategia = (
                estrategia_precedentes.avaliar_linguagem(texto_total, dados))
            erros.extend(f"L25 ESTRATÉGIA: {item}" for item in erros_estrategia)
            pendencias.extend(
                f"L25 PESQUISA: {item}" for item in pendencias_estrategia)

            if dados.get("schema_version") == "dsr.achados.v3":
                _estr = (dados.get("estrategia")
                         if isinstance(dados.get("estrategia"), dict) else {})
                _pesq = _estr.get("pesquisa_contraria")
                _pesquisa_concluida = (
                    isinstance(_pesq, dict)
                    and _pesq.get("estado") in ("concluida_sem_achado",
                                                "concluida_com_achado"))
                _cob_declarada = _estr.get("cobertura_precedente")






                _cob_efetiva = (_cob_declarada if _pesquisa_concluida
                                else COBERTURA_SEM_PROVA)
                _cal = calibracao_vocabulario.calibrar(texto_total, _cob_efetiva)
                if _cal.get("estado") != "calibrado":




                    pendencias.append("L26 CALIBRAÇÃO INCONCLUSIVA: "
                                      + calibracao_vocabulario.resumo(_cal))
                else:
                    _porque = "" if _pesquisa_concluida else (
                        f" A cobertura declarada é «{_cob_declarada}», mas a pesquisa "
                        f"de precedente contrário NÃO foi concluída: cobertura "
                        f"declarada e não provada calibra como "
                        f"«{COBERTURA_SEM_PROVA}».")
                    for _ap in _cal.get("apontamentos") or []:
                        _trecho_ap = " ".join(str(_ap.get("trecho") or "").split())
                        _onde = (f"linha {_ap.get('linha')}: «{_ap.get('termo')}» — "
                                 f"{_trecho_ap}")
                        if _ap.get("classe") == CLASSE_TRAVADA:
                            erros.append(f"L26 JURISPRUDÊNCIA: {_onde} — "
                                         f"{_ap.get('motivo')}.{_porque}")
                        else:
                            pendencias.append(f"L26 TOM: {_onde} — {_ap.get('motivo')}")
                    for _isen in _cal.get("isencoes_aplicadas") or []:

                        avisos.append(
                            f"L26 ISENÇÃO: {_isen.get('expressao_id')} isento por "
                            f"{_isen.get('autorizado_por')} — {_isen.get('razao')}")
            prec_nums = set()
            prec_status = {}
            st_registros = []
            for a in achados:
                if not isinstance(a, dict):
                    continue
                _cit = a.get("citation") if isinstance(a.get("citation"), dict) else {}
                _txt = " ".join(str(v) for v in (a.get("reference"), _cit.get("identifier"),
                                                  _cit.get("court")) if v)
                _regs = citacoes_sumula_tema(_txt)
                _ident = str(_cit.get("identifier") or "").replace(".", "").strip()
                if not _regs and a.get("nature") in ("sumula", "tema") and _ident.isdigit():
                    _s = _RX_SIGLA.search(str(_cit.get("court") or ""))
                    _regs = [(a["nature"], _ident, "vinculante" in _txt.lower(),
                              _s.group(1).upper() if _s else None, _ident)]
                st_registros += [r + (a.get("use_status"),) for r in _regs]
            prec_por_num = {}
            for a in achados:
                if isinstance(a, dict):
                    for _n in NUM_PROC_RX.findall(_num_norm(a.get("reference", ""))):
                        prec_por_num.setdefault(_n, a)
                    numeros = set(NUM_PROC_RX.findall(_num_norm(a.get("reference", ""))))
                    prec_nums |= numeros
                    for numero in numeros:
                        prec_status.setdefault(numero, []).append(a.get("use_status"))
        except Exception as e:
            erros.append(f"CRUZAMENTO: --precedentes ilegível — {e}")
            prec_nums = None
            prec_por_num = {}





        if prec_nums is not None and (julgados_citados or st_citadas):
            total_achados = len(achados) if isinstance(achados, list) else 0
            total_allowed = sum(
                1 for a in (achados or [])
                if isinstance(a, dict) and a.get("use_status") == "allowed")
            if total_achados > 0 and total_allowed == 0:
                pendentes = sum(
                    1 for a in (achados or [])
                    if isinstance(a, dict) and a.get("use_status") == "pending")
                proibidos = sum(
                    1 for a in (achados or [])
                    if isinstance(a, dict) and a.get("use_status") == "prohibited")
                pendencias.append(
                    f"L11 RELAÇÃO TOTAL PENDENTE: a Relação de Precedentes tem {total_achados} "
                    f"achado(s) e NENHUM com `use_status=allowed` ({pendentes} pending, "
                    f"{proibidos} prohibited) — a Relação entregue é uma lista de placeholders, "
                    f"não uma Relação liberada. A peça fica em MINUTA e NÃO se protocola. "
                    f"Feche o ciclo de confirmação — mostre ao advogado a lista de conferência "
                    f"(`python scripts/folha_atestacao.py achados.json -o "
                    f"CONFERENCIA_PENDENTE.json`) e registre o PDF que ele trouxer "
                    f"(`atestar_literal.py --documentos --atestar`) ou a resposta dele "
                    f"(`registrar_confirmacao_manual.py --lista`) — antes de relintar.")

        if prec_nums is not None:
            for rot, cit in st_citadas.items():
                casam = [r for r in st_registros if _casa_sumula_tema(cit, r)]
                if not casam:
                    erros.append(f"CRUZAMENTO: {rot} citada na peça AUSENTE da Relação de "
                                 f"Precedentes — súmula e tema precisam do registro verificado à "
                                 f"parte, como o julgado")
                elif all(r[5] == "prohibited" for r in casam):
                    erros.append(f"CRUZAMENTO VETADO: {rot} está VETADA na Relação de Precedentes "
                                 f"(use_status=prohibited): a conferência na fonte oficial a negou. "
                                 f"Tire-a da peça e gere a peça de novo")
                elif not any(r[5] == "allowed" for r in casam):
                    pendencias.append(f"{rot} consta na Relação, ainda SEM conferência na fonte "
                                      f"oficial (use_status≠allowed) — pode permanecer na minuta; "
                                      f"antes do protocolo, ou se confere, ou sai da peça")
            for txt, em_tbl, _, _ in textos:
                t = txt.strip()
                if not _eh_entrada_julgado(t, em_tbl):
                    continue
                for n in NUM_PROC_RX.findall(_num_norm(t)):
                    if n not in prec_nums:


                        erros.append(f"CRUZAMENTO: julgado citado na peça AUSENTE da Relação de "
                                     f"Precedentes (nº {n}) — todo precedente da peça precisa do "
                                     f"registro verificado à parte")
                    elif all(s == "prohibited" for s in prec_status.get(n, [])):



                        erros.append(
                            f"CRUZAMENTO VETADO: julgado citado na peça (nº {n}) está VETADO na "
                            f"Relação de Precedentes (use_status=prohibited): a conferência na "
                            f"fonte oficial o negou. Tire-o da peça, ou substitua-o por julgado "
                            f"conferido, e gere a peça de novo")
                    elif "allowed" not in prec_status.get(n, []):


                        pendencias.append(
                            f"julgado nº {n} consta na Relação, ainda SEM conferência na fonte "
                            f"oficial (use_status≠allowed) — pode permanecer na minuta; antes do "
                            f"protocolo, ou se confere, ou sai da peça")

















    if prec_path and prec_nums is not None and conferencia_contract is not None:
        for tbl in body.iter(W + "tbl"):
            linhas = [''.join(x for x, _b, _h, _i, _u in runs_do_paragrafo(pp)).strip()
                      for pp in tbl.iter(W + "p")]
            linhas = [t for t in linhas if t]
            if not linhas or not linhas[0].upper().startswith("JURISPRUD"):
                continue
            atual = None
            for linha in linhas[1:]:
                nums = NUM_PROC_RX.findall(_num_norm(linha))
                if nums:
                    atual = next((n for n in nums if n in prec_por_num), nums[0])
                    continue
                if atual is None or len(linha) < 60:
                    continue
                achado = prec_por_num.get(atual)
                if achado is None:
                    continue
                armazenados = [str(achado.get("syllabus_literal") or ""),
                               str(achado.get("full_text") or "")]
                if not any(a.strip() for a in armazenados):
                    erros.append(
                        f"L24 a peça transcreve o julgado nº {atual} e a Relação NÃO guardou "
                        f"teor algum dele (`syllabus_literal` e `full_text` vazios) — não se "
                        f"transcreve o que não foi lido. Reextraia a ementa da fonte oficial "
                        f"confirmada antes de citar: «{cite(linha)}»")
                    continue
                if not conferencia_contract.confere_transcricao(linha.strip('"“” '),
                                                                armazenados):
                    erros.append(
                        f"L24 TRANSCRIÇÃO NÃO CONFERE com o julgado nº {atual} — o texto na "
                        f"peça diverge do teor que a pesquisa leu na fonte oficial. Citação "
                        f"entre aspas é o que o tribunal escreveu, não o que ele deveria ter "
                        f"escrito: erro do original NÃO se corrige em silêncio, e resumo do "
                        f"julgado não ocupa o lugar da transcrição (se for síntese SUA, tire "
                        f"das aspas e diga que é síntese). «{cite(linha)}»")












    isentos_juris = _paragrafos_de_jurisprudencia(body)
    for txt, em_tbl, p, rs in textos:
        if not rs or id(p) in isentos_juris:
            continue
        offs, pos = [], 0
        for t, b, _hl, it, _u in rs:
            offs.append((pos, pos + len(t), b, it)); pos += len(t)
        for ini, fim, trecho, classe in autobold_matches(txt):
            cobertos = [(b, it) for a, b2, b, it in offs if a < fim and b2 > ini]
            if not cobertos or all(it for _b, it in cobertos):
                continue
            if not all(b for b, _it in cobertos):
                erros.append(f"L12 {classe} «{trecho}» fora de negrito — dado objetivo "
                             f"(data/valor/documento/contrato/processo) vai SEMPRE em "
                             f"negrito: «{cite(txt)}»")

















    for txt, _, _, _ in textos:
        for r in vocabulario_interno.residuos(txt):
            erros.append(f"L16 {r['classe']} «{r['termo']}» impresso no documento — "
                         f"peça e Relação são lidas pelo advogado e pelo juízo; escreva a "
                         f"pendência em linguagem de advogado: «{cite(txt)}»")















    RX_NOTACAO = re.compile(r"\[[^\]\n]{0,60}—\s*do perfil\s*\]")
    for txt, _, _, _ in textos:
        for m in RX_NOTACAO.finditer(txt):
            erros.append(f"L19 notação de documentação «{m.group(0)}» impressa no documento "
                         f"— é o marcador de 'preencha com o dado do perfil', não texto de "
                         f"peça. Substitua pelo dado real (ou deixe o builder resolver, se "
                         f"for um campo do perfil): «{cite(txt)}»")






    transcricao = set()
    for i, (txt, _em, p, rs) in enumerate(textos):
        if id(p) in isentos_juris:
            transcricao.add(i)
        elif rs and txt.strip() and all(it for _t, _b, _h, it, _u in rs if _t.strip()):
            transcricao.add(i)





















    grau = grau_arg
    if grau and grau_do_estado_lido:
        avisos.append(f"L20 grau de jurisdição lido do estado da peça ({grau_do_estado_lido}): "
                      f"{grau_jurisdicao.descrever(grau)}. `--grau` explícito prevalece")
    if not grau:
        grau = grau_jurisdicao.detectar_no_texto([t for t, _e, _p, _r in textos])
        if grau:
            avisos.append(
                f"L20 grau de jurisdição NÃO declarado (`--grau` ausente) — INFERIDO do "
                f"endereçamento como {grau_jurisdicao.descrever(grau)}. A inferência lê a capa; "
                f"a fonte certa é a classe processual do briefing, propagada pelo "
                f"`estado_peca.py`. Declare com `--grau {grau}` para que o L20 não dependa de "
                f"leitura de capa")
        else:
            avisos.append(
                "L20 NÃO MEDIDO: grau de jurisdição não declarado (`--grau`) e não inferível do "
                "endereçamento. As formas de tratamento ficam SEM conferência. "
                "Passe `--grau primeiro|segundo|superior`")
    if grau:
        _paras_l20 = [t for t, _e, _p, _r in textos]
        _fronteira = grau_jurisdicao.fronteira_interposicao(
            _paras_l20, e_fecho=e_formula_de_fecho,
            e_data=lambda t: bool(DATA_LINHA_RX.search(t)))
        for oc in grau_jurisdicao.vocativos_indevidos(
                _paras_l20, grau, indices_isentos=transcricao, fronteira=_fronteira):
            if oc.get("folha") == "interposição":
                destino = grau_jurisdicao.DESTINATARIO_INTERPOSICAO.get(
                    grau, "ao juízo de origem")
                onde = f"na folha de interposição, dirigida {destino}"
            elif oc.get("folha") == "razões":
                onde = f"na folha de razões, de {grau} grau"
            else:
                onde = f"em peça de {grau} grau"
            erros.append(
                f"L20 {oc['rotulo']} {onde} — «{oc['trecho']}»: {oc['remedio']}. "
                f"Contexto: «{cite(oc['contexto'])}»")



















    corpo_autoral = [PLACEHOLDER_RX.sub("", t) for i, (t, em, _p, _r) in enumerate(textos)
                     if not em and i not in transcricao and not _eh_entrada_julgado(t)]
    m_trav = metricas_prosa.medir_travessoes(corpo_autoral)
    if m_trav["total"]:
        regra = ("REGRA: zero risca no corpo autoral. `—`, `–`, `--`, `----` e ` - ` espaçado que "
                 "possam virar vírgula, ponto final, conjunção ou parênteses não se usam, "
                 "inclusive no aposto. Hífen `-` de palavra composta e de número é livre; "
                 "intervalo numérico (2019–2021, arts. 1º–5º) é isento")
        conta = (f"{m_trav['total']} travessão(ões) no corpo autoral, {m_trav['emenda']} de "
                 f"EMENDA e {m_trav['aposto']} de aposto")
        if m_trav["palavras"] >= metricas_prosa.MINIMO_PALAVRAS:
            conta += f"; densidade {m_trav['densidade']} por mil em {m_trav['palavras']} palavras"
        remedio = ("Aplique o catálogo jusmanizer (J01, `references/estilo-escrita.md` §2) "
                   "antes do Conselho Revisor; o §6 do mesmo arquivo traz o antes e depois de "
                   "cada padrão")
        lista = metricas_prosa.resumo_travessoes(m_trav)
        if _disp["pular_l21"]:
            avisos.append(f"L21 DISPENSADO pelo perfil (estilo_escrita.overrides."
                          f"permitir_travessao): {conta}")
        else:
            erros.append(f"L21 risca no corpo autoral: {conta}. {regra}. {remedio}. {lista}")









    ancoras = metricas_prosa.ancoras_repetidas(
        [t for i, (t, _em, _p, _r) in enumerate(textos) if i not in transcricao],
        ignorar=list(processos_arg) + [p for p in proc_proprios])
    if ancoras:
        avisos.append(
            f"L22 {len(ancoras)} âncora(s) repetida(s) acima de "
            f"{metricas_prosa.LIMITE_ANCORA}× no texto autoral: "
            f"{metricas_prosa.resumo_ancoras(ancoras)}. Repetição de valor, data e ID é o que o "
            f"leitor sente primeiro como 'já li isso'. Confira se a âncora precisa ser reposta "
            f"ou se o item pode remeter ao capítulo em que ela já foi fixada")















    r_jm = jusmanizer.analisar(corpo_autoral, excluir={"J01", "J04"} | _disp["excluir"])
    for oc in r_jm["ocorrencias"]:
        if l28_duplica_l16(oc):
            continue
        msg = (f"L28 {oc['padrao']} {oc['nome']}: «{cite(oc['contexto'])}». "
               f"Remédio: {oc['remedio']}")
        (erros if oc["severidade"] == "erro" else avisos).append(msg)












    caps_peca, itens_peca = set(), set()
    for txt, em_tbl, _p, _rs in textos:
        t = txt.strip()
        mc = CAP_TITULO_RX.match(t)
        if mc:
            caps_peca.add(mc.group(1).upper())
            continue
        mi = ITEM_TITULO_RX.match(t)
        if mi:
            itens_peca.add(f"{mi.group(1).upper()}.{int(mi.group(2))}")
            caps_peca.add(mi.group(1).upper())
    if caps_peca:
        for i, (txt, em_tbl, _p, _rs) in enumerate(textos):
            t = txt.strip()
            if i in transcricao or CAP_TITULO_RX.match(t) or ITEM_TITULO_RX.match(t):
                continue
            alheia = bool(REF_ALHEIA_RX.search(t))
            for m in REF_CAP_RX.finditer(t):
                alvo = m.group(1).upper()
                if alvo in caps_peca or alheia:
                    continue
                erros.append(
                    f"L23 referência a «Capítulo {alvo}», que NÃO existe nesta peça (capítulos: "
                    f"{', '.join(sorted(caps_peca, key=len))}) — referência cruzada quebrada, o "
                    f"rastro clássico de renumeração de capítulo: «{cite(t)}»")
            if alheia:
                continue
            for m in REF_ITEM_RX.finditer(t):
                alvo = f"{m.group(1).upper()}.{int(m.group(2))}"
                if alvo in itens_peca:
                    continue
                avisos.append(
                    f"L23 referência ao «item {alvo}», que não existe nesta peça — confira se "
                    f"aponta para item de OUTRO documento (resposta, embargos, decisão), caso em "
                    f"que a redação deve dizê-lo, ou se é referência quebrada por renumeração: "
                    f"«{cite(t)}»")


















    topo = [el for el in list(body) if el.tag in (W + "p", W + "tbl")]
    for i, el in enumerate(topo):
        if el.tag == W + "p":
            t = texto_de(el).strip()
            if not t or flag_ligada(el.find(W + "pPr"), "keepLines"):
                continue
            if e_item_de_lista(el):


                avisos.append(f"L17 item de lista sem keepLines — pode partir entre páginas; "
                              f"a regra de proteção 1 proíbe a máquina reformatar lista: "
                              f"«{cite(t)}»")
            else:
                erros.append(f"L17 parágrafo de conteúdo SEM keepLines — parte entre páginas "
                             f"(§1: keepLines em todo parágrafo; a quebra só cai nos "
                             f"espaçadores): «{cite(t)}»")
            continue

        linhas = el.findall(W + "tr")
        uma_linha = len(linhas) == 1
        for tr in linhas:
            visivel = len(texto_de(tr))
            atomica = flag_ligada(tr.find(W + "trPr"), "cantSplit")
            amostra = cite(texto_de(tr).strip()) or "(elemento sem texto)"
            if visivel > MAX_CAIXA_ATOMICA and atomica:
                msg = (f"L17 caixa LONGA ({visivel} caracteres, limiar {MAX_CAIXA_ATOMICA}) "
                       f"com cantSplit — não cabe na sobra da página, salta inteira e deixa "
                       f"buraco do próprio tamanho: «{amostra}»")
                (erros if uma_linha else avisos).append(msg)
            elif visivel <= MAX_CAIXA_ATOMICA and not atomica:
                erros.append(f"L17 elemento SEM cantSplit — a caixa racha entre páginas "
                             f"(§2: cantSplit em toda linha de tabela-elemento): «{amostra}»")

        if classifica_elemento(el) in ("banner", "legenda"):
            prox = topo[i + 1] if i + 1 < len(topo) else None
            if (prox is not None and prox.tag == W + "p" and not texto_de(prox).strip()
                    and not flag_ligada(prox.find(W + "pPr"), "keepNext")):
                erros.append(f"L17 espaçador depois de título SEM keepNext — o título fica "
                             f"sozinho no pé da página e o corpo vai para a seguinte; o elo "
                             f"é o espaçador, porque o keepNext do banner não atravessa a "
                             f"tabela: título «{cite(texto_de(el).strip())}»")








    area_util = area_util_do_documento(body)
    for tbl in body.iter(W + "tbl"):
        grid = tbl.find(W + "tblGrid")
        n_grid = len(grid.findall(W + "gridCol")) if grid is not None else 0
        rotulo = cite(texto_de(tbl).strip()) or "(elemento sem texto)"
        if n_grid == 0:
            erros.append(f"L18 caixa sem grade declarada (tblGrid ausente ou vazio) — "
                         f"largura indefinida no Word: «{rotulo}»")
        for k, tr in enumerate(tbl.findall(W + "tr"), 1):
            n_cel = colunas_da_linha(tr)
            if n_cel == 0:
                erros.append(f"L18 caixa com linha {k} SEM célula alguma — estrutura "
                             f"inválida: «{rotulo}»")
            elif n_grid and n_cel != n_grid:
                erros.append(f"L18 caixa DESBALANCEADA — linha {k} ocupa {n_cel} coluna(s) "
                             f"e a grade declara {n_grid} (o Word desenha torto sem avisar): "
                             f"«{rotulo}»")
        larg = largura_declarada(tbl)
        if larg and larg > area_util + TOLERANCIA_LARGURA:
            erros.append(f"L18 caixa de {larg} twips mais larga que a área útil "
                         f"({area_util}) — invade a margem do gabarito: «{rotulo}»")

















    if not fragmento:
        grupos, atual, ini_atual = [], [], None
        for i, (txt, em_tbl, p, _rs) in enumerate(textos):
            ppr = p.find(W + "pPr")
            jc = ppr.find(W + "jc") if ppr is not None else None
            centrado = (jc is not None
                        and jc.get(W + "val") in ("center", "centro"))
            if centrado and not em_tbl and txt.strip():
                if not atual:
                    ini_atual = i
                atual.append(txt.strip())
            elif atual:
                grupos.append((ini_atual, atual))
                atual = []
        if atual:
            grupos.append((ini_atual, atual))
        ini_ultimo = grupos[-1][0] if grupos else None
        blocos_ass = [b for ini, b in grupos
                      if bloco_e_assinatura(textos, ini, ini == ini_ultimo)]
        for bloco in blocos_ass:
            if not any(OAB_RX.search(l) for l in bloco):
                erros.append(
                    "L29 assinatura sem a inscrição na OAB — a peça final vai assinada com o "
                    "nome e com a inscrição do subscritor. Acrescente a linha da inscrição "
                    f"logo abaixo do nome: «{cite(bloco[0])}»")
                continue


            for nome in signatarios_sem_inscricao(bloco):
                erros.append(
                    "L29 signatário sem a inscrição na OAB — cada advogado que assina vai "
                    "com a própria inscrição. Acrescente a linha da inscrição logo abaixo "
                    f"do nome: «{cite(nome)}»")


    if not fragmento:


        nao_vazios = [(t, em, p, rs) for t, em, p, rs in textos
                      if t.strip() and not tem_faixa_minuta(t)]
        if nao_vazios:
            primeiro = nao_vazios[0][0].strip().upper()
            if not primeiro.startswith(ENDERECAMENTO_PREFIXOS):
                avisos.append(f"F1 primeiro parágrafo não parece endereçamento: «{cite(primeiro)}»")
            outra = comarca_divergente(primeiro, _comarca_padrao)
            if outra:
                avisos.append(
                    f"F1 comarca do endereçamento «{cite(outra)}» difere da padrão da banca "
                    f"«{_comarca_padrao}» (perfil, foro.comarca_padrao). Peticionar fora da "
                    f"comarca é legítimo e por isso isto é AVISO; confira se a capa não veio "
                    f"de outro processo")
        idx_cap = next((i for i, (t, _, _, _) in enumerate(textos) if t.strip().upper().startswith("CAPÍTULO")), len(textos))
        for txt, em_tbl, p, rs in textos[:idx_cap]:
            t = txt.strip()
            if QUALIFICACAO_RX.match(t):
                if not any(b for _, b, _, _, _ in rs):
                    erros.append(f"F2 parte/qualificação SEM negrito na capa: «{cite(t)}»")




    CANONICAL_LABELS = {
        "DOS FATOS", "DO DIREITO", "DOS PEDIDOS", "DA SÍNTESE", "DA SINTESE",
        "DAS PRELIMINARES", "DO MÉRITO", "DO MERITO", "DOS REQUERIMENTOS",
        "DO CABIMENTO", "DAS RAZÕES", "DAS RAZOES", "DA FUNDAMENTAÇÃO", "DA FUNDAMENTACAO",
    }
    for txt, em_tbl, p, rs in textos[inicio_corpo:]:
        t = txt.strip()

        if not em_tbl and len(t) > 750 and not LISTA_INICIO_RX.match(t):
            avisos.append(f"E1 (Ethos) parágrafo longo ({len(t)} caracteres) — 'muro de texto' "
                          f"eleva a carga cognitiva; considere dividir: «{cite(t)}»")





        if not em_tbl:
            n_bold = sum(1 for tt, b, _, _, _ in rs
                         if b and tt.strip() and "(Doc." not in tt
                         and not _so_dado_objetivo(tt))
            if n_bold > 3:
                avisos.append(f"E2 (Ethos) {n_bold} trechos em negrito num só parágrafo — "
                              f"negrito em excesso perde a função de destaque: «{cite(t)}»")






    for tbl in body.iter(W + "tbl"):
        linhas = [t.strip() for t in
                  ("".join(x for x, _, _, _, _ in runs_do_paragrafo(p)) for p in tbl.iter(W + "p"))
                  if t.strip()]
        if not linhas or linhas[-1].upper() not in CANONICAL_LABELS:
            continue
        titulo = linhas[-1]
        avisos.append(f"E3 (Ethos) título só com rótulo canônico «{titulo}» — considere "
                      f"título híbrido (rótulo como eyebrow + título informativo), na forma "
                      f"«{titulo} | <o que o capítulo sustenta, em poucas palavras>»")

















    _RX_DECL_NOSSA = re.compile(
        r"(?:grif|destaqu|negrit|sublinh)\w*\s+(?:nosso|nossos|nossa|nossas|acrescid\w+)"
        r"|sem\s+(?:grifo|grifos|destaque|destaques)\s+(?:no|do)\s+original"
        r"|\b(?:grifei|grifamos|grifou|destaquei|destacamos|destacou|sublinhei|sublinhamos)\b",
        re.IGNORECASE)



    _RX_DECL_ORIGINAL = re.compile(
        r"(?:grifo|grifos|destaque|destaques|negrito|sublinhado)s?\s*(?:do|no|da|na)\s+"
        r"original|(?:grifos?|destaques?)\s+origina\w+", re.IGNORECASE)
    _RX_SO_DOC = re.compile(r"^\(?(?:Docs?\.|DOC\.)\s?[^()]{1,40}\)?[\s.,;:]*$", re.IGNORECASE)

    def _classe_decl(t):
        if _RX_DECL_NOSSA.search(t):
            return "nossa"
        if _RX_DECL_ORIGINAL.search(t):
            return "original"
        return None

    def _texto_p(pp):
        return "".join(t for t, _b, _h, _i, _u in runs_do_paragrafo(pp))

    def _e_caixa_de_transcricao(tbl):
        'A caixa TRANSCREVE? Só nelas o L27 mede.'






        for pp in tbl.iter(W + "p"):
            rs = [x for x in runs_do_paragrafo(pp) if x[0].strip()]
            if not rs:
                continue
            if "".join(t for t, _b, _h, _i, _u in rs).strip().upper().startswith("JURISPRUD"):
                return True
            if all(it for _t, _b, _h, it, _u in rs):
                return True
        return False

    def _e_forma(t):
        'Run sem nenhum caractere alfanumérico é FORMA, nunca grifo.'




        return not any(c.isalnum() for c in t)

    def _grifo_na_caixa(tbl):
        """(tem_grifo, amostra_da_transcricao). amostra=None quando a caixa não transcreve."""
        if not _e_caixa_de_transcricao(tbl):
            return False, None
        tem_grifo, amostra = False, None
        for pp in tbl.iter(W + "p"):
            rs = runs_do_paragrafo(pp)
            if not rs:
                continue
            txt = "".join(t for t, _b, _h, _i, _u in rs).strip()
            if not txt or txt.upper().startswith("JURISPRUD"):
                continue
            if all(b for _t, b, _hl, _it, _u in rs):
                continue
            if _classe_decl(txt):
                continue
            if amostra is None:
                amostra = txt
            for t, b, hl, _it, u in rs:
                if _e_forma(t):
                    continue
                if hl or u or (b and not _RX_SO_DOC.match(t.strip())):
                    tem_grifo = True
        return tem_grifo, amostra

    _blocos = [(("tbl" if el.tag == W + "tbl" else "p"), el) for el in list(body)
               if el.tag in (W + "tbl", W + "p")]
    for _k, (_tipo, _el) in enumerate(_blocos):
        if _tipo != "tbl":
            continue
        _tem_grifo, _amostra = _grifo_na_caixa(_el)
        if _amostra is None:
            continue



        _decl = _decl_txt = None
        for _pp in _el.iter(W + "p"):
            _t = _texto_p(_pp)
            _c = _classe_decl(_t)
            if _c:
                _decl, _decl_txt = _c, _t
                break
        if _decl is None:
            for _tipo2, _el2 in _blocos[_k + 1:_k + 3]:
                if _tipo2 != "p":
                    break
                _t = _texto_p(_el2)
                _c = _classe_decl(_t)
                if _c:
                    _decl, _decl_txt = _c, _t
                    break
        if _decl == "nossa" and not _tem_grifo:
            erros.append(
                f"L27 GRIFO DECLARADO E AUSENTE: «{cite(_decl_txt)}» fecha uma caixa de "
                f"transcrição que não tem UMA marca de ênfase acrescentada. Declarar grifo "
                f"que não existe é afirmar ato não praticado: o julgador procura o trecho "
                f"que você quis destacar e encontra bloco uniforme. CORRIJA MARCANDO, não "
                f"apagando a frase — no dialeto, __trecho__ sublinha, ==trecho== realça em "
                f"amarelo e **trecho** põe em negrito, e o builder preserva os três dentro "
                f"de `::: citacao` e `::: jurisprudencia`. Marque o que sustenta a tese e "
                f"mantenha a declaração. Caixa: «{cite(_amostra)}»")
        elif _decl is None and _tem_grifo:
            erros.append(
                f"L27 GRIFO NÃO DECLARADO: a caixa tem ênfase acrescentada ao texto "
                f"transcrito e nada diz que ela é nossa — o leitor a atribui ao tribunal "
                f"(governança §3: destaque acrescentado a texto transcrito só entra se "
                f"declarado). Acrescente a declaração logo após a caixa («Grifei e "
                f"destaquei.», «Destacamos.», «Grifo nosso.»), ou «Grifos do original.» se "
                f"a ênfase for da fonte. Caixa: «{cite(_amostra)}»")





    print(f"lint_peca — {caminho}" + (" (fragmento)" if fragmento else " (peça final)")
          + (f" · grau {grau}" if grau else " · grau não declarado"))
    for a in avisos:
        print(f"AVISO: {a}")
    cruzados = [n for n, ativo in (("precedentes", bool(prec_path)), ("juntada", bool(jnt_path)),
                                   ("conferência", bool(citacoes_de_prova))) if ativo]
    sufixo_cruz = (" · cruzado contra " + " e ".join(cruzados)) if cruzados else ""
    if erros:
        print(f"\n== REPROVADO == ({len(erros)} erro(s) de ESTRUTURA"
              + (f" · {len(pendencias)} pendência(s) de conferência" if pendencias else "")
              + ")")
        for e in erros:
            print(f"ERRO: {e}")
        for p in pendencias:
            print(f"PENDENTE: {p}")
        return 1
    if pendencias:
        print(f"\n== MINUTA == ({len(pendencias)} julgado(s)/marcação(ões) a atestar; "
              f"ESTRUTURA LIMPA — L1–L35"
              + ("" if fragmento else " + F1/F2") + sufixo_cruz + ")")
        for p in pendencias:
            print(f"PENDENTE: {p}")
        print("A forma está correta; falta conferir na fonte oficial o que está PENDENTE. "
              "Minuta NÃO se protocola: só o APROVADO (exit 0) libera.")
        return 3
    print("== APROVADO == (L1–L35" + ("" if fragmento else " + F1/F2") + " limpos"
          + sufixo_cruz + ")")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
