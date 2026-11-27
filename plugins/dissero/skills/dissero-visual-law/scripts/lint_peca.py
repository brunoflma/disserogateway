#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lint_peca.py — gate determinístico pós-build do Visual Law.

Mede no `.docx` gerado o que a leitura de revisão não conta:
  forma ................ L1–L7, L10, L12, L30, L33 (dialeto, aspas, realce, recuo, negrito de
                         dado, parágrafo numerado)
  lastro ............... L8, L9, L11, L13–L15, L24, CRUZAMENTO-DOC (julgado e documento citados),
                         L34 (percentual sem base, documento ou norma), L36 (valor em algarismo
                         × por extenso), L41 (valor só em algarismo nos pedidos —
                         aviso)
  citação .............. L37 (classe processual × tribunal), L38 (súmula, tema ou OJ acima do
                         maior número publicado), L39 (número a um dígito de precedente
                         conferido), L40 (paráfrase mais forte que a ementa) — só aviso
  mapa ................. L35 (questão, tese descartada e motivo do mapa argumentativo na peça)
  estratégia e tom ..... L25, L26 (linguagem contra a cobertura de precedentes da tese)
  língua do documento .. L16, L19 (vocabulário interno e notação de documentação na peça)
  tratamento ........... L20 (forma de tratamento × grau de jurisdição)
  competência .......... L42 (ente federal endereçado à Justiça Estadual; JEF)
  recurso especial ..... L43 (sem o tópico de relevância, pela entrada do checklist de
                         admissibilidade)
  IA ................... L44 (trecho visível dirigido a ferramenta de IA)
  gratuidade ........... L45 (Súmula 463, I, 40% do teto e ADC 80 × data de ajuizamento — aviso)
  prosa ................ L21 (risca), L22 (repetição de âncora), L28 (padrões de IA)
  estrutura ............ L17, L18 (paginação e caixa), L23 (referência cruzada), L27 (grifo),
                         L29 (assinatura com OAB), F1/F2 (capa)
  leitura .............. E1–E3 (só aviso)
  minuta por ordem ..... L32 (faixa ou marca de MINUTA COM PENDÊNCIAS: nunca APROVADO)

Uso: python3 lint_peca.py peca.docx [--fragmento] [--precedentes achados.json]
          [--juntada JUNTADA_TRACKER.json] [--conferencia CONFERENCIA.json]
          [--grau primeiro|segundo|superior] [--processo CNJ]... [--session-id ID]
          [--competencia COMPETENCIA.json] [--admissibilidade ADMISSIBILIDADE.json]
          [--ajuizamento AAAA-MM-DD] [--json ARQUIVO|-]
  --json ARQUIVO|-   grava também o relatório estruturado: cada erro e pendência com
                «natureza» (texto: a correção é na peça; registro: falta registrar algo fora
                dela, e a linha diz o quê e como) e o resumo {erros_texto, erros_registro}.
                `-` imprime o relatório no lugar do texto. Não muda veredito nem exit code.
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
  --competencia COMPETENCIA.json   resultado `dsr.competencia.v1` do verificador de competência
                (`competencia.py --gravar`). Omitido, o linter lê o COMPETENCIA.json ao lado do
                .docx e na pasta do caso desta sessão, nunca o do diretório corrente (os dois
                divergindo, nenhum vale) e, sem nenhum, infere
                o ente federal pela capa e só AVISA (L42). Ilegível quando passado: REPROVADO.
  --admissibilidade ADMISSIBILIDADE.json   a ENTRADA do checklist de admissibilidade
                (`dsr.admissibilidade.entrada.v1`: `recurso`, `acordao_publicado_em`, critério
                `relevancia_questao_federal`). Governa o L43; omitido, vale o ADMISSIBILIDADE.json
                ao lado do .docx ou na pasta do caso, com a mesma resolução do COMPETENCIA.json.
                Ilegível quando passado: REPROVADO.
  --ajuizamento AAAA-MM-DD   data de ajuizamento da ação. Governa o L45 (marco da ADC 80);
                omitida, peça sem número de processo é inaugural (ajuíza-se agora).
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
import sys, os, re, json, unicodedata, zipfile
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



try:
    import procedencia_literal as _procedencia_literal
except Exception:
    _procedencia_literal = None


def _teor_conferido_sem_liberacao(achado):
    'True quando o achado tem o teor conferido VERBATIM contra o documento do tribunal (registro'


    if _procedencia_literal is None or not isinstance(achado, dict):
        return False
    if achado.get("use_status") in ("allowed", "prohibited"):
        return False
    regs = achado.get("procedencia_literal")
    if not isinstance(regs, list) or not any(
            isinstance(r, dict) and r.get("campo", "syllabus_literal") == "syllabus_literal"
            for r in regs):
        return False
    try:
        nivel, _motivo = _procedencia_literal.conferir_achado(achado)
    except Exception:
        return False
    return nivel == "verbatim"


def _status_efetivo_dos_achados(achados):
    '(achados, rótulos rebaixados): cada achado `allowed` que o contrato não sustenta passa a'







    if not isinstance(achados, list):
        return achados, []
    try:
        import achado_contract as _ac
    except Exception:
        _ac = None
    fontes = None
    if _ac is not None:
        try:
            fontes = _ac.carregar_json(_ac.FONTES_PADRAO)
        except Exception:
            fontes = None
    saida, rebaixados = [], []
    for a in achados:
        if isinstance(a, dict) and a.get("use_status") == "allowed":
            try:
                motivos = _ac.motivos_das_regras(a, fontes) if _ac is not None else ["contrato"]
            except Exception:
                motivos = ["contrato"]
            if motivos:
                a = {**a, "use_status": "pending"}
                rebaixados.append(str(a.get("reference") or a.get("id") or "precedente")[:80])
        saida.append(a)
    return saida, rebaixados





_REMEDIO_ENDERECO_L11 = (
    "indique o endereço oficial do julgado no portal do tribunal e, depois, confira-o no Minha "
    "banca (peça ao Dissero, na conversa, a conferência dos julgados)")





_TECNICO_L11 = ("Para o assistente (não repita ao advogado): use_status≠allowed na Relação; "
                "só o recibo FINAL da conferência no Minha banca libera, também o julgado "
                "conferido pela máquina, que ali aparece para ratificar.")



_PROXIMO_PASSO_L25 = (
    ("exige migração",
     "Próximo passo: migre o registro para v3 — `atestar_literal.py` já migra ao gravar a "
     "atestação, ou `python converter_achados_v2_v3.py achados.json -o achados.json` — e então "
     "faça a pesquisa de precedente contrário (a v3 migrada nasce com ela não iniciada). "
     "ATENÇÃO: enquanto a pesquisa contrária não estiver concluída e a cobertura revisada, a "
     "v3 migrada faz o L25 passar de pendência a ERRO e a peça fica REPROVADA, não mais "
     "minuta; migre junto com a pesquisa contrária, ou ateste o teor com `--manter-v2` até lá."),
    ("pesquisa contrária concluída",
     "Próximo passo: faça a busca de precedente CONTRÁRIO à tese (skill de pesquisa jurídica, com "
     "os termos da tese adversa) e registre no achados.json, em estrategia.pesquisa_contraria, o "
     "estado (concluida_sem_achado ou concluida_com_achado), as consultas feitas (fonte, termos, "
     "data) e os IDs dos contrários achados; depois revise a cobertura_precedente e relinte."),
    ("precedente contrário ainda não foi concluída",
     "Próximo passo: faça a busca de precedente CONTRÁRIO à tese e registre o resultado em "
     "estrategia.pesquisa_contraria (estado, consultas, IDs dos contrários); depois relinte."),
    ("cobertura inexistente não pode manter",
     "Próximo passo: conclua a pesquisa de precedente contrário e revise a cobertura_precedente "
     "(com cobertura_revisada_em e cobertura_valida_ate) antes de manter o precedente favorável."),
)


def _com_proximo_passo_l25(mensagem):
    for chave, passo in _PROXIMO_PASSO_L25:
        if chave in mensagem:
            return f"{mensagem}. {passo}"
    return mensagem












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
    import competencia as _competencia
except Exception:
    _competencia = None




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

















_DOCS_RX = re.compile(r"\(Doc\.\s*([\d,\s]+)\)")







_QUEM_CONFERE = ("Quem resolve: qualquer pessoa da banca confere, entrando com o próprio login; "
                 "quem encerra é o titular da banca ou quem abriu a conferência. Como: "
                 "peça ao Dissero, na conversa, a conferência dos julgados; ela abre na "
                 "página Minha banca, em Conferência dos julgados, com o endereço oficial de "
                 "cada um. Ali, quem confere marca cada julgado como «Confere» ou «Não "
                 "confere», com o motivo, ou o deixa pendente; os que a máquina já conferiu na "
                 "fonte vêm marcados como «Confere», para ratificar. Enquanto a conferência "
                 "estiver aberta nada é liberado: quando estiver tudo certo, o titular da banca "
                 "ou quem abriu a conferência clica Encerrar e liberar, e só esse encerramento "
                 "libera a peça. Julgado copiado dos autos se confere contra a cópia dos autos. "
                 "Depois, confira a peça de novo.")
_LER_DOC = ("Leia o documento pela ingestão do Dissero, para que a leitura fique registrada "
            "na conferência do caso, e marque-o como curado na juntada; anotação sobre o "
            "documento feita fora desse registro não conta. Feito o registro, confira a peça "
            "de novo.")



_REGRAS_REGISTRO = (
    (re.compile(r"^CRUZAMENTO-DOC: --juntada ilegível"),
     "a relação de documentos juntados do caso em formato legível",
     "A relação de documentos do caso está fora do formato esperado. Refaça-a pela etapa de "
     "juntada do Dissero e confira a peça de novo."),
    (re.compile(r"^CRUZAMENTO-DOC: .*AUSENTE do ledger"),
     "o registro de juntada do documento {docs}",
     "Inclua o documento na juntada do caso. " + _LER_DOC),
    (re.compile(r"^CRUZAMENTO-DOC: .*consta no ledger com status"),
     "a curadoria do documento {docs}: ele está na juntada, mas a leitura dele não foi "
     "registrada como concluída",
     _LER_DOC),
    (re.compile(r"^CRUZAMENTO-DOC: .*curado SEM evidence_ids"),
     "o vínculo entre o documento {docs} e a leitura registrada dele",
     _LER_DOC),
    (re.compile(r"^L13 "),
     "a relação de documentos juntados do caso, com cada documento citado lido e curado",
     "Monte a juntada pela etapa de juntada do Dissero, com a leitura de cada documento "
     "citado registrada, e confira a peça de novo apresentando-a."),
    (re.compile(r"^L14 conferencia_contract\.py indisponível"),
     "parte da instalação do Dissero",
     "A cópia instalada do Dissero está incompleta; atualize-a ou reinstale-a. O problema "
     "não é da peça."),
    (re.compile(r"^L14 a peça transcreve prova documental"),
     "a conferência de ingestão do caso, que registra o que foi lido em cada documento",
     "Leia os documentos transcritos pela ingestão do Dissero e confira a peça de novo "
     "apresentando a conferência do caso."),
    (re.compile(r"^L14 conferência de ingestão ilegível"),
     "a conferência de ingestão do caso em formato legível",
     "A conferência do caso está fora do formato esperado. Registre de novo a leitura dos "
     "documentos pela ingestão do Dissero e confira a peça de novo."),
    (re.compile(r"^L14 transcrição atribuída a .*sem teor registrado"),
     "a leitura do documento {docs} registrada na conferência do caso",
     _LER_DOC + " A transcrição só se confere contra o que foi lido e registrado."),
    (re.compile(r"^L11 FAIL-CLOSED"),
     "a Relação de Precedentes do caso",
     "Gere a Relação de Precedentes a partir da pesquisa do caso e confira a peça de novo "
     "com ela."),
    (re.compile(r"^CRUZAMENTO: --precedentes ilegível"),
     "a Relação de Precedentes do caso em formato legível",
     "A Relação de Precedentes está fora do formato esperado. Gere-a de novo a partir da "
     "pesquisa do caso e confira a peça de novo."),
    (re.compile(r"^CRUZAMENTO: .*AUSENTE da Relação"),
     "o registro deste precedente na Relação de Precedentes",
     "Pesquise e confira o precedente pela pesquisa do Dissero, para que ele entre na "
     "Relação, ou tire-o da peça."),
    (re.compile(r"^L24 .*guardou só a ementa"),
     "o inteiro teor do julgado, para conferir a transcrição: a peça transcreve trecho que não "
     "está na ementa, e a Relação de Precedentes guardou só a ementa",
     "Quem resolve: qualquer pessoa da banca. Como: traga à conversa com o Dissero o inteiro "
     "teor do julgado (o PDF baixado do tribunal ou a cópia dos autos), para que a pesquisa o "
     "guarde na Relação; a conferência do julgado continua sendo feita no Minha banca, em "
     "Conferência dos julgados. Depois, confira a peça de novo. A transcrição em si não "
     "precisa mudar; se o trecho for resumo seu, e não transcrição, tire-o das aspas e da "
     "caixa."),
    (re.compile(r"^L24 .*NÃO guardou teor"),
     "o teor do julgado lido na fonte oficial, guardado na Relação de Precedentes",
     "Extraia de novo a ementa da fonte oficial pela pesquisa do Dissero e confira a peça "
     "de novo."),
    (re.compile(r"^L4[23] [A-Z]+ ilegível"),
     "o registro da verificação (competência ou admissibilidade) em formato legível",
     "Refaça a verificação pela etapa própria do Dissero e confira a peça de novo."),

    (re.compile(r"^L11 RELAÇÃO TOTAL PENDENTE"),
     "a conferência, na fonte oficial, dos precedentes da Relação",
     _QUEM_CONFERE),
    (re.compile(r"consta na Relação.*(?:SEM conferência|falta endereço oficial)"),
     "a conferência deste precedente na fonte oficial",
     _QUEM_CONFERE),
)

_CODIGO_RX = re.compile(r"^(CRUZAMENTO-DOC|CRUZAMENTO VETADO|CRUZAMENTO|L\d+|F\d)\b")


def _palavras_l24(texto_):
    sem_acento = unicodedata.normalize("NFKD", str(texto_ or "")).encode("ascii", "ignore")
    return [p for p in re.findall(r"[a-z0-9]+", sem_acento.decode("ascii").lower()) if len(p) >= 4]


def l24_trecho_fora_da_ementa(transcricao, ementa):
    'Verdadeiro quando a transcrição é de OUTRA parte do julgado (o voto), e não uma ementa'













    trans = _palavras_l24(transcricao)
    if len(trans) < 5:
        return False
    base = set(_palavras_l24(ementa))
    return sum(1 for p in trans if p in base) / len(trans) < 0.5


_ORDINAL_RX = re.compile(r"(\d+)\s*\.?\s*[ªº°]")
_DATA_DMA_RX = re.compile(r"\b(\d{1,2})\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*(\d{4})\b")
_DATA_AMD_RX = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_VAZIAS_MOLDURA = frozenset({"de", "do", "da", "dos", "das", "e", "em", "a", "o"})


def _tokens_moldura(texto_):
    s = _ORDINAL_RX.sub(r"\1 ", str(texto_ or ""))
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii").lower()
    return re.findall(r"[a-z]+|\d+", s)


def _datas_moldura(texto_):
    s = str(texto_ or "")
    datas = {(int(d), int(m), int(a)) for d, m, a in _DATA_DMA_RX.findall(s)}
    datas |= {(int(d), int(m), int(a)) for a, m, d in _DATA_AMD_RX.findall(s)}
    return datas


def l24_moldura_confere(identificacao, achado):
    'Verdadeiro quando a linha de identificação da caixa confere com o julgado guardado na'











    cit = (achado or {}).get("citation") if isinstance(achado, dict) else None
    cit = cit if isinstance(cit, dict) else {}
    orgao = str(cit.get("orgao_julgador") or cit.get("court") or "").strip()
    datas_guardadas = _datas_moldura(cit.get("judgment_date"))
    if not orgao or not datas_guardadas:
        return False
    if not datas_guardadas & _datas_moldura(identificacao):
        return False
    linha = set(_tokens_moldura(identificacao))
    for palavra in _tokens_moldura(orgao):
        if palavra in _VAZIAS_MOLDURA:
            continue
        if palavra.isdigit():
            if palavra.lstrip("0") not in {t.lstrip("0") for t in linha if t.isdigit()}:
                return False
        elif not any(t == palavra or (len(t) >= 3 and not t.isdigit() and palavra.startswith(t))
                     for t in linha):
            return False
    return True


def classificar_achado(mensagem):
    "{'codigo', 'mensagem', 'natureza'} e, no registro, 'o_que_falta' e 'como_resolver'."

    m = str(mensagem or "")
    cod = _CODIGO_RX.match(m)
    saida = {"codigo": cod.group(1) if cod else "", "mensagem": m, "natureza": "texto"}
    for rx, falta, como in _REGRAS_REGISTRO:
        if rx.search(m):
            docs = ", ".join(sorted({d.strip() for g in _DOCS_RX.findall(m)
                                     for d in g.split(",") if d.strip()}))
            saida.update(natureza="registro",
                         o_que_falta=falta.format(docs=(f"(Doc. {docs})" if docs else "citado")),
                         como_resolver=como)
            break
    return saida


def resumo_de_naturezas(erros):
    "{'erros_texto': n, 'erros_registro': m} sobre os ERROS (pendências não entram: elas"

    nat = [classificar_achado(e)["natureza"] for e in erros]
    return {"erros_texto": nat.count("texto"), "erros_registro": nat.count("registro")}


def _linha_de_registro(achado):
    return (f"    FALTA REGISTRAR: {achado['o_que_falta']}. COMO RESOLVER: "
            f"{achado['como_resolver']}")


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









_EXT_UNIDADES = {"zero": 0, "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4,
                 "cinco": 5, "seis": 6, "sete": 7, "oito": 8, "nove": 9}
_EXT_DEZ_A_DEZENOVE = {"dez": 10, "onze": 11, "doze": 12, "treze": 13, "catorze": 14,
                       "quatorze": 14, "quinze": 15, "dezesseis": 16, "dezasseis": 16,
                       "dezessete": 17, "dezassete": 17, "dezoito": 18, "dezenove": 19,
                       "dezanove": 19}
_EXT_DEZENAS = {"vinte": 20, "trinta": 30, "quarenta": 40, "cinquenta": 50, "sessenta": 60,
                "setenta": 70, "oitenta": 80, "noventa": 90}
_EXT_CENTENAS = {"cem": 100, "cento": 100, "duzentos": 200, "duzentas": 200, "trezentos": 300,
                 "trezentas": 300, "quatrocentos": 400, "quatrocentas": 400, "quinhentos": 500,
                 "quinhentas": 500, "seiscentos": 600, "seiscentas": 600, "setecentos": 700,
                 "setecentas": 700, "oitocentos": 800, "oitocentas": 800, "novecentos": 900,
                 "novecentas": 900}
_EXT_ESCALAS = {"mil": 10 ** 3, "milhao": 10 ** 6, "milhoes": 10 ** 6, "bilhao": 10 ** 9,
                "bilhoes": 10 ** 9, "trilhao": 10 ** 12, "trilhoes": 10 ** 12}
_EXT_ESCRITA_UNI = ("", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove",
                    "dez", "onze", "doze", "treze", "catorze", "quinze", "dezesseis", "dezessete",
                    "dezoito", "dezenove")
_EXT_ESCRITA_DEZ = ("", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta",
                    "oitenta", "noventa")
_EXT_ESCRITA_CEM = ("", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos",
                    "seiscentos", "setecentos", "oitocentos", "novecentos")
_EXT_ESCRITA_ESC = ((10 ** 12, "trilhão", "trilhões"), (10 ** 9, "bilhão", "bilhões"),
                    (10 ** 6, "milhão", "milhões"), (10 ** 3, "mil", "mil"))


def _ext_norm(s):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", str(s))
                   if unicodedata.category(c) != "Mn").lower()


def _ext_grupo(n):
    """Extenso de 1 a 999."""
    if n == 100:
        return "cem"
    c, resto = divmod(n, 100)
    partes = [_EXT_ESCRITA_CEM[c]] if c else []
    if resto:
        if resto < 20:
            partes.append(_EXT_ESCRITA_UNI[resto])
        else:
            d, u = divmod(resto, 10)
            partes.append(_EXT_ESCRITA_DEZ[d] + (f" e {_EXT_ESCRITA_UNI[u]}" if u else ""))
    return " e ".join(partes)


def extenso_inteiro(n):
    'Extenso de um inteiro não negativo (masculino), sem moeda: 1250 → "mil duzentos e'



    n = int(n)
    if n == 0:
        return "zero"
    grupos = []
    for valor, sing, plur in _EXT_ESCRITA_ESC:
        q, n = divmod(n, valor)
        if q:
            nome = "mil" if valor == 1000 else (sing if q == 1 else plur)
            grupos.append((q * valor, "mil" if (valor == 1000 and q == 1)
                           else f"{_ext_grupo(q)} {nome}"))
    if n:
        grupos.append((n, _ext_grupo(n)))
    texto = grupos[0][1]
    for i in range(1, len(grupos)):
        resto = grupos[i:]
        q_unico = resto[0][0]
        while q_unico >= 1000 and q_unico % 1000 == 0:
            q_unico //= 1000
        liga = len(resto) == 1 and (q_unico < 100 or q_unico % 100 == 0)
        texto += (" e " if liga else " ") + grupos[i][1]
    return texto


def extenso_de_valor(centavos):
    'Extenso de um valor em reais dado em centavos: 150000050 → "um milhão e quinhentos mil'

    reais, cent = divmod(int(centavos), 100)
    if not reais and not cent:
        return "zero real"
    partes = []
    if reais:
        de = " de" if reais >= 10 ** 6 and reais % 10 ** 6 == 0 else ""
        partes.append(f"{extenso_inteiro(reais)}{de} {'real' if reais == 1 else 'reais'}")
    if cent:
        partes.append(f"{extenso_inteiro(cent)} {'centavo' if cent == 1 else 'centavos'}")
    return " e ".join(partes)


def _ext_ler_inteiro(tokens):
    'Tokens (sem acento, minúsculos, sem pontuação) → inteiro, ou None se não for extenso'


    if not tokens:
        return None
    total = atual = 0
    classe_ant = 9
    escala_ant = 10 ** 15
    tem_numero = False
    for i, tok in enumerate(tokens):
        if tok == "e":
            prox = tokens[i + 1] if i + 1 < len(tokens) else ""
            if i == 0 or not prox or prox in _EXT_ESCALAS or prox == "e":
                return None
            continue
        if tok in _EXT_ESCALAS:
            esc = _EXT_ESCALAS[tok]
            if esc >= escala_ant:
                return None
            if esc == 1000:
                total += (atual or 1) * 1000
            else:
                if not atual:
                    return None
                total += atual * esc
            atual, classe_ant, escala_ant = 0, 9, esc
            tem_numero = True
            continue
        for tabela, classe in ((_EXT_CENTENAS, 3), (_EXT_DEZENAS, 2),
                               (_EXT_DEZ_A_DEZENOVE, 1.5), (_EXT_UNIDADES, 1)):
            if tok in tabela:
                if classe >= classe_ant or (classe_ant == 1.5 and classe == 1):
                    return None
                if tok == "cem" and i + 1 < len(tokens) and tokens[i + 1] == "e":
                    return None
                atual += tabela[tok]
                classe_ant = classe
                tem_numero = True
                break
        else:
            return None
    return total + atual if tem_numero else None


_EXT_TOKEN_RX = re.compile(r"[a-z]+")


def _valor_de_extenso_e_cauda(texto):
    '(centavos, palavras depois da moeda) ou (None, []). A cauda é o que sobra depois de'



    if re.search(r"\d", str(texto or "")):
        return None, []
    toks = _EXT_TOKEN_RX.findall(_ext_norm(texto))
    moedas = ("real", "reais")
    i_moeda = next((i for i, t in enumerate(toks) if t in moedas), None)
    i_cent = next((i for i, t in enumerate(toks) if t in ("centavo", "centavos")), None)
    if i_moeda is None and i_cent is None:
        return None, []
    if i_moeda is None or (i_cent is not None and i_cent < i_moeda):
        cent = _ext_ler_inteiro(toks[:i_cent])
        return (cent, toks[i_cent + 1:]) if cent is not None and cent < 100 else (None, [])
    inteiro = toks[:i_moeda]
    if inteiro and inteiro[-1] == "de":
        inteiro = inteiro[:-1]
    reais = _ext_ler_inteiro(inteiro)
    if reais is None:
        return None, []
    total = reais * 100
    depois = toks[i_moeda + 1:]
    if depois and depois[0] == "e" and "centavo" in "".join(depois[:6]):
        fim = next(i for i, t in enumerate(depois) if t in ("centavo", "centavos"))
        cent = _ext_ler_inteiro(depois[1:fim])
        if cent is None or cent >= 100:
            return None, []
        total += cent
        depois = depois[fim + 1:]
    return total, depois


def valor_de_extenso(texto):
    'Extenso de valor em reais → centavos, ou None se o texto não for extenso legível (ou'


    return _valor_de_extenso_e_cauda(texto)[0]


L36_VALOR_RX = re.compile(
    r"R\$\s*(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{2}))?(?:\s+(mil|milh[ãa]o|milh[õo]es|bilh[ãa]o|bilh[õo]es))?"
    r"\s*\(([^()]{3,240})\)", re.I)
L36_PERC_RX = re.compile(r"(?<![\d,.])(\d{1,3})\s?%\s*\(([^()]{3,120}?por\s+cento)\s*\)", re.I)
_L36_ESCALA_NUM = {"mil": 10 ** 3, "milhao": 10 ** 6, "milhoes": 10 ** 6, "bilhao": 10 ** 9,
                   "bilhoes": 10 ** 9}


def _l36_brl(centavos):
    reais, cent = divmod(int(centavos), 100)
    return "R$ " + f"{reais:,}".replace(",", ".") + f",{cent:02d}"


def _l36_divergencias(texto, mascara=None):
    '[(trecho, algarismo, extenso, percentual, qualificado)]. `qualificado`: o parêntese'


    achados = []
    for m in L36_VALOR_RX.finditer(texto or ""):
        if mascara is not None and mascara[m.start():m.end()] != texto[m.start():m.end()]:
            continue
        extenso = m.group(4)
        if not re.search(r"\b(?:rea(?:l|is)|centavos?)\b", extenso, re.I):
            continue
        lido, cauda = _valor_de_extenso_e_cauda(extenso)
        if lido is None:
            continue
        num = int(m.group(1).replace(".", "")) * 100 + int(m.group(2) or 0)
        if m.group(3):
            num *= _L36_ESCALA_NUM[_ext_norm(m.group(3))]
        if num != lido:
            achados.append((m.group(0), num, lido, False, bool(cauda)))
    for m in L36_PERC_RX.finditer(texto or ""):
        if mascara is not None and mascara[m.start():m.end()] != texto[m.start():m.end()]:
            continue
        if re.search(r"\d", m.group(2)):
            continue
        toks = _EXT_TOKEN_RX.findall(_ext_norm(m.group(2)))[:-2]
        lido = _ext_ler_inteiro(toks)
        if lido is not None and lido != int(m.group(1)):
            achados.append((m.group(0), int(m.group(1)), lido, True, False))
    return achados


def l36_achados(texto, mascara=None):
    '[(trecho, valor_do_algarismo, valor_do_extenso, percentual)] das divergências que'



    return [a[:4] for a in _l36_divergencias(texto, mascara) if not a[4]]


def l36_avisos(texto, mascara=None):
    'Mesmo formato de `l36_achados`, para as divergências com qualificação depois da moeda'

    return [a[:4] for a in _l36_divergencias(texto, mascara) if a[4]]


def l36_mensagem(trecho, algarismo, extenso, percentual=False, qualificado=False):
    if percentual:
        diz_num = f"{extenso_inteiro(algarismo)} por cento"
        diz_ext = f"{extenso}%"
    else:
        diz_num = extenso_de_valor(algarismo)
        diz_ext = _l36_brl(extenso)
    if qualificado:
        return (f"L36 VALOR × EXTENSO A CONFERIR: «{trecho}». O algarismo diz {diz_num}; o "
                f"extenso diz {diz_ext}, com uma qualificação depois da moeda. Se o extenso é de "
                f"propósito outro valor (por parte, por mês, cada), deixe a frase como está; se "
                f"não, confira na fonte e corrija o que estiver errado.")
    return (f"L36 VALOR × EXTENSO DIVERGENTE: «{trecho}». O algarismo diz {diz_num}; o extenso "
            f"diz {diz_ext}. Confira na fonte qual dos dois é o valor certo e corrija o outro: o "
            f"linter não decide qual está errado.")
















_L37_NUM = r"(?=[\s\-]*(?:n[º°o]\.?\s*)?\d)"
L37_CLASSES = (

    ("AREsp", re.compile(r"(?<![\w-])E?AREsp\b" + _L37_NUM), ("STJ",), ()),
    ("REsp", re.compile(r"(?<![\w-])E?R(?:Esp|ESP|esp)\b" + _L37_NUM), ("STJ",), ()),
    ("ARE", re.compile(r"(?<![\w-])ARE\b" + _L37_NUM), ("STF",), ()),
    ("RE", re.compile(r"(?<![\w-])RE\b" + _L37_NUM), ("STF",), ()),
    ("AIRR", re.compile(r"(?<![\w])(?:[A-Z][A-Za-z]{0,3}-)*AIRR\b" + _L37_NUM), ("TST",), ()),
    ("RR", re.compile(r"(?<![\w])(?:[A-Z][A-Za-z]{0,3}-)*RR(?:Ag)?\b" + _L37_NUM), ("TST",), ()),
    ("RHC", re.compile(r"(?<![\w-])RHC\b" + _L37_NUM), ("STJ", "STF", "TST", "TSE", "STM"),
     ("TJ", "TRF", "TRT")),
)
_L37_SIGLA_RX = re.compile(
    r"\b(STF|STJ|TST|TSE|STM|TJ[A-Z]{2}|TJDFT|TRF\s?-?\d|TRT\s?-?\d{1,2}"
    r"|Supremo\s+Tribunal\s+Federal|Superior\s+Tribunal\s+de\s+Justi[çc]a"
    r"|Tribunal\s+Superior\s+do\s+Trabalho|Tribunal\s+de\s+Justi[çc]a"
    r"|Tribunal\s+Regional\s+Federal|Tribunal\s+Regional\s+do\s+Trabalho)\b")
_L37_ORIGEM_RX = re.compile(r"inadmit|negou\s+seguimento|interp|admit|remet|subiu|origem|recorrid"
                            r"|\bcontra\b|oriund|impetr|proferid|na\s+origem", re.I)

_L37_ORIGEM_DEPOIS_RX = re.compile(r"^[^,;.]{0,40}?\b(?:na|de|da)\s+origem\b|^\s*\(\s*origem", re.I)


def _l37_sigla(s):
    s = " ".join(s.split())
    nomes = {"supremo tribunal federal": "STF", "superior tribunal de justica": "STJ",
             "tribunal superior do trabalho": "TST", "tribunal de justica": "TJ",
             "tribunal regional federal": "TRF", "tribunal regional do trabalho": "TRT"}
    n = _ext_norm(s)
    if n in nomes:
        return nomes[n]
    s = s.replace(" ", "").replace("-", "").upper()
    for pref in ("TJ", "TRF", "TRT"):
        if s.startswith(pref):
            return pref
    return s


def _temas_citados(texto):
    '[(número, tribunal|None, de_repercussao_geral, rótulo)] dos temas, com a natureza dita'

    out = []
    for tipo, num, _v, trib, rotulo in citacoes_sumula_tema(texto):
        if tipo != "tema":
            continue
        rg = False
        for m in _RX_TEMA.finditer(texto):
            if m.group(2).replace(".", "") == num:
                perto = texto[m.start():m.end() + 40]
                rg = bool(re.search(r"repercuss[ãa]o\s+geral", perto, re.I))
                break
        out.append((num, trib, rg, rotulo))
    return out


def _l37_tribunal_perto(texto, ini, fim):
    'Tribunal mais perto da classe: primeiro depois dela (até 90 caracteres, sem cruzar'




    depois = re.split(r";|\.\s+(?=[A-ZÀ-Ý])", texto[fim:fim + 90])[0]
    m = _L37_SIGLA_RX.search(depois)
    if m and not (_L37_ORIGEM_RX.search(depois[:m.start()])
                  or _L37_ORIGEM_DEPOIS_RX.search(depois[m.end():])):
        return _l37_sigla(m.group(1))
    antes = re.split(r";|\.\s+(?=[A-ZÀ-Ý])", texto[max(0, ini - 60):ini])[-1]
    ms = list(_L37_SIGLA_RX.finditer(antes))
    if ms and not _L37_ORIGEM_RX.search(antes[ms[-1].end():]):
        return _l37_sigla(ms[-1].group(1))
    return None


def l37_achados(texto):
    '[(trecho, classe, tribunal_citado, esperados)] das citações em que a classe processual'

    texto = texto or ""
    achados, usados = [], []
    for rotulo, rx, esperados, vedados in L37_CLASSES:
        for m in rx.finditer(texto):
            if any(a <= m.start() < b for a, b in usados):
                continue
            usados.append((m.start(), m.end()))
            trib = _l37_tribunal_perto(texto, m.start(), m.end())
            if not trib:
                continue
            ruim = (trib in vedados) if vedados else (trib not in esperados)
            if ruim:
                fim_tr = m.end() + 25
                while fim_tr < len(texto) and not texto[fim_tr].isspace():
                    fim_tr += 1
                trecho = texto[m.start():fim_tr].strip()
                achados.append((trecho, rotulo, trib, esperados))




    for m in _RX_SUMULA.finditer(texto):
        if not m.group(1):
            continue
        num = m.group(2).replace(".", "")
        trib = _l37_tribunal_colado(texto[m.end():])
        if trib and trib != "STF":
            achados.append((f"Súmula Vinculante {num} do {trib}", "Súmula Vinculante", trib,
                            ("STF",)))
    for m in _RX_TEMA.finditer(texto):
        num = m.group(2).replace(".", "")
        resto = texto[m.end():]
        rg = bool(m.group(1) and re.match(r"de\s+repercuss", m.group(1), re.I))
        m_rg = re.match(r"\s+de\s+repercuss[ãa]o\s+geral\b", resto, re.I)
        if m_rg:
            rg, resto = True, resto[m_rg.end():]
        trib = _l37_tribunal_colado(resto)
        if trib and not rg:
            rg = bool(re.match(r"[^,;.]{0,12}?\bde\s+repercuss[ãa]o\s+geral\b",
                               resto[_L37_COLA_RX.match(resto).end():], re.I))
        if rg and trib and trib != "STF":
            achados.append((f"Tema {num}/{trib} (repercussão geral)", "Tema", trib, ("STF",)))
    return achados


_L37_COLA_RX = re.compile(r"\s*(?:/\s*|-\s*|,?\s+d[oa]\s+)(STF|STJ|TST|TSE|STM|TJ[A-Z]{2}|TRF\s?-?\d"
                          r"|TRT\s?-?\d{1,2})\b")


def _l37_tribunal_colado(resto):
    """Sigla de tribunal colada ao número que acaba de ser lido ("/STJ", " do STJ", "-TST")."""
    m = _L37_COLA_RX.match(resto)
    return _l37_sigla(m.group(1)) if m else None


def l37_mensagem(trecho, classe, tribunal, esperados):
    esp = " ou ".join(esperados)
    return (f"L37 CLASSE × TRIBUNAL: «{' '.join(str(trecho).split())}» — {classe} junto de "
            f"{tribunal}, mas {classe} é da competência do {esp}. Confira o tribunal e a classe na "
            f"fonte oficial; se o {tribunal} é o tribunal de origem, deixe isso claro na frase.")












TETOS_PRECEDENTE = {
    "sumula_stf": {"rotulo": "Súmula do STF", "teto": 736, "conferido_em": "16/11/2026",
                   "fonte": "https://portal.stf.jus.br/jurisprudencia/sumariosumulas.asp?base=30"},
    "sumula_vinculante": {"rotulo": "Súmula Vinculante", "teto": 63, "conferido_em": "16/11/2026",
                          "fonte": "https://portal.stf.jus.br/jurisprudencia/sumariosumulas.asp?base=26"},
    "sumula_stj": {"rotulo": "Súmula do STJ", "teto": 676, "conferido_em": "16/11/2026",
                   "fonte": "https://processo.stj.jus.br/SCON/sumstj/toc.jsp"},
    "sumula_tst": {"rotulo": "Súmula do TST", "teto": 463, "conferido_em": "16/11/2026",
                   "fonte": "https://jurisprudencia.tst.jus.br/?tipoJuris=SUM&orgao=TST&pesquisar=1"},
    "tema_stf_rg": {"rotulo": "Tema de Repercussão Geral do STF", "teto": 1501,
                    "conferido_em": "16/11/2026",
                    "fonte": "https://portal.stf.jus.br/jurisprudenciaRepercussao/tema.asp?num=1501"},
    "tema_stj_repetitivo": {"rotulo": "Tema Repetitivo do STJ", "teto": 1474,
                            "conferido_em": "16/11/2026",
                            "fonte": "https://processo.stj.jus.br/repetitivos/temas_repetitivos/"},
    "tema_tst_irr": {"rotulo": "Tema de Recursos Repetitivos do TST (IRR)", "teto": 317,
                     "conferido_em": "16/11/2026",
                     "fonte": "https://www.tst.jus.br/nugep-sp/recursos-repetitivos/tabela-completa"},
    "oj_tst_sbdi1": {"rotulo": "OJ da SBDI-1 do TST", "teto": 421, "conferido_em": "16/11/2026",
                     "fonte": "https://jurisprudencia.tst.jus.br/?tipoJuris=OJ&orgao=TST&pesquisar=1"},
    "oj_tst_sbdi1_transitoria": {"rotulo": "OJ Transitória da SBDI-1 do TST", "teto": 79,
                                 "conferido_em": "16/11/2026",
                                 "fonte": "https://jurisprudencia.tst.jus.br/?tipoJuris=OJ&orgao=TST&pesquisar=1"},
    "oj_tst_sbdi2": {"rotulo": "OJ da SBDI-2 do TST", "teto": 158, "conferido_em": "16/11/2026",
                     "fonte": "https://jurisprudencia.tst.jus.br/?tipoJuris=OJ&orgao=TST&pesquisar=1"},
    "oj_tst_sdc": {"rotulo": "OJ da SDC do TST", "teto": 38, "conferido_em": "16/11/2026",
                   "fonte": "https://jurisprudencia.tst.jus.br/?tipoJuris=OJ&orgao=TST&pesquisar=1"},
    "oj_tst_pleno": {"rotulo": "OJ do Tribunal Pleno do TST", "teto": 13, "conferido_em": "16/11/2026",
                     "fonte": "https://jurisprudencia.tst.jus.br/?tipoJuris=OJ&orgao=TST&pesquisar=1"},
}
_L38_TEMA_RX = re.compile(r"\bTema\s+((?:de\s+Repercuss[ãa]o\s+Geral|Repetitivo)\s+)?"
                          r"(?:n(?:[º°o]\.?|\.)\s*)?(\d{1,3}(?:\.\d{3})+|\d{1,4})\b", re.I)
_L38_IRR_COLA_RX = re.compile(
    r"(?:\s*/\s*|-|,?\s+d[oa]\s+(?:(?:C\.|Col\.|E\.|colendo|egr[eé]gio)\s*)?)"
    r"(?:TST\b|Tribunal\s+Superior\s+do\s+Trabalho\b)"
    r"|\s*(?:,\s*)?(?:d[oe]\s+)?IRR\b", re.I)
L38_OJ_RX = re.compile(
    r"\b(?:OJ|Orienta[çc][ãa]o\s+Jurisprudencial)\s+(Transit[óo]ria\s+)?(?:n(?:[º°o]\.?|\.)\s*)?"


    r"(\d{1,4})\b((?:[^.;\n]|(?<=\b[EC])\.|(?<=\bEg)\.|(?<=\bCol)\.){0,60})", re.I)



_L38_TRT_COLA_RX = re.compile(
    r"(?:\s*,?\s*(?:Transit[óo]ria\b|d[oa]\b|S?E?B?DI\s?-?\s?(?:[12]|II?)\b|SDC\b|SE\b|Pleno\b"
    r"|Se[çc][ãa]o\s+(?:Especializada\s+)?(?:de|em)\s+Diss[íi]dios\s+(?:Individuais|Coletivos)"
    r"(?:\s+\d)?\b|E\.|Eg\.|C\.|Col\.|egr[eé]gio\b|colendo\b))*"
    r"\s*(TRT(?:\s+da\s+\d{1,2}\s*[ªºa°]?\s+Regi[ãa]o|\s*[-/]?\s*(?:\d{1,2}(?:\s*[ªºa°])?|(?-i:[A-Z]{2}))\b"
    r"|\b)|Tribunal\s+Regional\s+do\s+Trabalho(?:\s+da\s+\S+\s+Regi[ãa]o)?)", re.I)


def _l38_trt_colado(perto):
    """O fim do trecho do TRT colado à OJ (índice em `perto`), ou None."""
    m = _L38_TRT_COLA_RX.match(perto or "")
    return m.end() if m else None


def _l38_especie_oj(transitoria, perto):
    if _l38_trt_colado(perto) is not None:
        return None
    p = _ext_norm(perto)
    if re.search(r"\bs?b?di\s?-?\s?(?:2|ii)\b", p):
        return "oj_tst_sbdi2"
    if re.search(r"\bsdc\b", p):
        return "oj_tst_sdc"
    if re.search(r"\bpleno\b", p):
        return "oj_tst_pleno"
    if re.search(r"\bs?b?di\s?-?\s?(?:1|i)\b|\btst\b", p):
        return "oj_tst_sbdi1_transitoria" if transitoria else "oj_tst_sbdi1"
    return None


def l38_achados(texto):
    """[(rótulo citado, número, chave do teto)] dos números acima do teto da espécie."""
    texto = texto or ""
    achados = []
    for tipo, num, vinc, trib, rotulo in citacoes_sumula_tema(texto):
        if tipo != "sumula":
            continue
        chave = ("sumula_vinculante" if vinc else
                 {"STF": "sumula_stf", "STJ": "sumula_stj", "TST": "sumula_tst"}.get(trib))
        if chave and int(num) > TETOS_PRECEDENTE[chave]["teto"]:


            achados.append((f"Súmula Vinculante {num}" if vinc else rotulo, int(num), chave))
    for num, trib, rg, rotulo in _temas_citados(texto):

        chave = ("tema_stf_rg" if (trib == "STF" or (rg and not trib)) else
                 "tema_stj_repetitivo" if trib == "STJ" and not rg else None)
        if chave and int(num) > TETOS_PRECEDENTE[chave]["teto"]:
            achados.append((rotulo, int(num), chave))
    for m in _L38_TEMA_RX.finditer(texto):
        if m.group(1) and re.match(r"de\s+repercuss", m.group(1), re.I):
            continue
        num = int(m.group(2).replace(".", ""))
        if (_L38_IRR_COLA_RX.match(texto, m.end())
                and num > TETOS_PRECEDENTE["tema_tst_irr"]["teto"]):
            achados.append((f"Tema {num}/TST", num, "tema_tst_irr"))
    for m in L38_OJ_RX.finditer(texto):

        transitoria = bool(m.group(1) or re.match(r"\s*,?\s*transit[óo]ria", m.group(3), re.I))
        chave = _l38_especie_oj(transitoria, m.group(3))
        if chave and int(m.group(2)) > TETOS_PRECEDENTE[chave]["teto"]:
            achados.append((m.group(0)[:len(m.group(0)) - len(m.group(3))].strip()
                            + " (" + TETOS_PRECEDENTE[chave]["rotulo"] + ")",
                            int(m.group(2)), chave))
    return achados


def l38_oj_regionais(texto):
    'OJs citadas como de TRT ("OJ 45 da SDI-1 do TRT-2", "Orientação Jurisprudencial 12 do'


    texto = texto or ""
    achados = []
    for m in L38_OJ_RX.finditer(texto):
        fim = _l38_trt_colado(m.group(3))
        if fim is not None:
            rot = re.sub(r"\s+", " ", texto[m.start():m.start(3) + fim]).strip(" ,")
            if rot not in achados:
                achados.append(rot)
    return achados


def l38_mensagem_oj_regional(rotulos):
    return ("L38 OJ REGIONAL SEM TETO CONFERIDO: " + "; ".join(f"«{r}»" for r in rotulos)
            + " — cada TRT numera as próprias orientações, e o número delas não se confere aqui. "
            "Confira número e enunciado no site do TRT de origem.")


def l38_mensagem(rotulo, teto, data):
    return (f"L38 NÚMERO ACIMA DO MAIOR PUBLICADO: «{rotulo}» — em {data} o maior número "
            f"publicado nessa espécie era o {teto}. Confira o número na fonte oficial; se o "
            f"enunciado é posterior a essa data, desconsidere este aviso.")










def l39_vizinhos(numero, conferidos, minimo=3):
    alvo = re.sub(r"\D", "", str(numero))
    if len(alvo) < minimo:
        return []
    out = []
    for c in sorted(conferidos):
        d = re.sub(r"\D", "", str(c))
        if len(d) == len(alvo) and d != alvo and sum(a != b for a, b in zip(d, alvo)) == 1:
            out.append(c)
    return out


def l39_mensagem(citado, vizinhos):
    return (f"L39 NÚMERO A UM DÍGITO DE PRECEDENTE CONFERIDO: «{citado}», ausente da Relação, "
            f"difere em um só algarismo de {', '.join(f'«{v}»' for v in vizinhos)}, que está "
            f"conferido. Veja se não é erro de digitação (os dois podem existir e ser citados "
            f"juntos); o linter não corrige o número.")












_L40_CATEGORIAS = {
    "quantificador": (
        ("todos", "todas", "sempre", "nunca", "jamais", "nenhum", "nenhuma", "em qualquer caso",
         "em qualquer hipotese", "em todos os casos", "invariavelmente", "necessariamente",
         "automaticamente"),
        ("alguns", "algumas", "em regra", "via de regra", "em geral", "geralmente", "por vezes",
         "eventualmente", "excepcionalmente", "em certos casos", "em determinados casos",
         "nem sempre", "a depender", "conforme as circunstancias")),
    "deontico": (
        ("deve", "devem", "devera", "deverao", "e obrigatorio", "e obrigatoria", "impoe-se",
         "e imperativo", "ha de", "hao de"),
        ("pode", "podem", "podera", "poderao", "e facultado", "e facultada", "faculta-se",
         "e possivel", "admite-se", "e licito", "e admissivel")),
}


def _l40_acha(texto_norm, termos):
    """Termos presentes, fora de negação ("não pode", "nem sempre" conta como termo próprio)."""
    achados = []
    for t in termos:
        for m in re.finditer(r"(?<![\w-])" + re.escape(t) + r"(?![\w-])", texto_norm):
            antes = texto_norm[max(0, m.start() - 5):m.start()]
            if re.search(r"\b(?:nao|nem)\s+$", antes) and not t.startswith("nem "):
                continue
            achados.append(t)
            break
    return achados


def l40_achados(frase_peca, ementa):
    """[(categoria, forte_na_peça, fraco_na_ementa)]."""
    if not (frase_peca and ementa):
        return []
    p, e = _ext_norm(frase_peca), _ext_norm(ementa)
    out = []
    for cat, (fortes, fracos) in _L40_CATEGORIAS.items():
        fp = _l40_acha(p, fortes)
        fe = _l40_acha(e, fracos)
        if fp and fe and not _l40_acha(e, fortes):
            out.append((cat, fp[0], fe[0]))
    return out






_L40_ORGAO = (r"(?:stj|stf|tst|tse|stm|tribunal|corte|turma|secao|plenario|orgao\s+especial"
              r"|colegiado|acordao|julgado|precedente|ementa|superior\s+tribunal|supremo)")
_L40_VERBO = (r"(?:decid|fix|entend|firm|assent|reconhec|consign|estabelec|afirm|conclu|defin"
              r"|julg|declar|proclam|admit|orient|pacific|sediment|enunci|registr)\w*")
_L40_ATRIBUI_RX = re.compile(
    r"\b(?:o|a|os|as|do|da|pelo|pela)\s+" + _L40_ORGAO + r"\b[^.;]{0,80}?\b" + _L40_VERBO
    + r"|\b" + _L40_VERBO + r"\s+(?:o|a|os|as)\s+" + _L40_ORGAO + r"\b"
    + r"|\b(?:segundo|para|conforme|consoante|de\s+acordo\s+com|na\s+linha\s+d[oa])\s+(?:o|a)\s+"
    + _L40_ORGAO + r"\b")


def _l40_frases(paragrafo):
    'Frases do parágrafo. Não parte em abreviatura ("Rel.", "Min.", "art.", "nº"): token de'

    frases, ini = [], 0
    for m in re.finditer(r"[.;!?](?=\s+[A-ZÀ-Ý«\"“])", paragrafo):
        tok = re.search(r"(\S+)$", paragrafo[ini:m.start()])
        tok = tok.group(1) if tok else ""
        if m.group(0) == "." and ((len(tok) <= 3 and not tok.isupper()) or "º" in tok):
            continue
        frases.append(paragrafo[ini:m.end()].strip())
        ini = m.end()
    resto = paragrafo[ini:].strip()
    return frases + ([resto] if resto else [])


def l40_frases_da_tese(paragrafo, numeros):
    'Frases de `paragrafo` que atribuem a tese ao tribunal: citam um dos `numeros` (só'

    out = []
    for f in _l40_frases(paragrafo or ""):
        digitos = {re.sub(r"\D", "", n) for n in NUM_PROC_RX.findall(f)}
        if digitos & {re.sub(r"\D", "", str(n)) for n in numeros} or _L40_ATRIBUI_RX.search(_ext_norm(f)):
            out.append(f)
    return out


def l40_mensagem(categoria, forte, fraco, numero):
    nome = "o quantificador" if categoria == "quantificador" else "a força deôntica"
    return (f"L40 PARÁFRASE MAIS FORTE QUE A EMENTA: a peça diz «{forte}» onde a ementa do "
            f"julgado nº {numero} diz «{fraco}» — mudou {nome}. Releia a ementa e ajuste a "
            f"frase ao que o tribunal decidiu, ou diga que a conclusão é sua.")













L41_VALOR_RX = re.compile(
    r"R\$\s*(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{1,2})?"
    r"(?:\s+(?:mil|milh[ãa]o|milh[õo]es|bilh[ãa]o|bilh[õo]es)\b)?", re.I)
_L41_EXTENSO_DEPOIS_RX = re.compile(r"\s*\(([^()]{3,240})\)")


_L41_NUMERO_EXTENSO_RX = re.compile(
    r"\b(?:dois|duas|tr[eê]s|quatro|cinco|seis|sete|oito|nove|dez|onze|doze|treze|[cq]uatorze"
    r"|catorze|quinze|dezesseis|dezessete|dezoito|dezenove|vinte|trinta|quarenta|cinq[uü]enta"
    r"|sessenta|setenta|oitenta|noventa|cem|cento|duzent[oa]s|trezent[oa]s|quatrocent[oa]s"
    r"|quinhent[oa]s|seiscent[oa]s|setecent[oa]s|oitocent[oa]s|novecent[oa]s|mil"
    r"|milh[ãa]o|milh[õo]es|bilh[ãa]o|bilh[õo]es"
    r"|uma?\s+(?:mil|rea(?:l|is)|centavos?|milh[ãa]o|bilh[ãa]o))\b", re.I)
_L41_PREFIXO = r"(?:(?:[IVXLC]+|\d{1,2})\s*[-–—.)]\s*)?"
_L41_PEDIDOS_RX = re.compile(
    _L41_PREFIXO + r"(?:d[oa]s?\s+)?(?:conclus[ãa]o\s+e\s+)?(?:d[oa]s?\s+)?"
    r"(?:pedidos?|requerimentos?)"
    r"(?:\s+(?:finais|e\s+(?:d[oa]s?\s+)?requerimentos?|e\s+d[oa]\s+valor\s+da\s+causa))?"
    r"\s*[.:]?", re.I)
_L41_SECAO_RX = re.compile(r"(?:CAP[IÍ]TULO\b|" + _L41_PREFIXO + r"D[OA]S?\s)", re.I)

_L41_LIGACAO = frozenset("a o as os e ou de do da dos das em no na nos nas por pelo pela pelos "
                         "pelas para com sem sob sobre entre ao aos à às que".split())


def l41_titulo_de_pedidos(texto):
    """O parágrafo é o título da seção de pedidos (inteiro, curto)."""
    t = " ".join(str(texto or "").split())
    return len(t) <= 90 and bool(_L41_PEDIDOS_RX.fullmatch(t))


def l41_titulo_de_secao(texto):
    'O parágrafo é um título de seção e fecha os pedidos: curto, começando por "CAPÍTULO",'




    t = " ".join(str(texto or "").split())
    if not (0 < len(t) <= 90 and any(c.isalpha() for c in t) and _L41_SECAO_RX.match(t)):
        return False
    if t == t.upper():
        return True
    if t.endswith(".") or len(t.split()) > 10:
        return False
    palavras = re.findall(r"[^\W\d_]+", t)
    return all(p[0].isupper() for p in palavras if p.lower() not in _L41_LIGACAO)


def l41_achados(texto, mascara=None):
    'Valores em reais sem extenso, na ordem do texto. `mascara`: o texto com o itálico'

    texto = texto or ""
    out = []
    for m in L41_VALOR_RX.finditer(texto):
        if mascara is not None and mascara[m.start():m.end()] != texto[m.start():m.end()]:
            continue
        depois = _L41_EXTENSO_DEPOIS_RX.match(texto, m.end())
        if depois and _L41_NUMERO_EXTENSO_RX.search(depois.group(1)):
            continue
        antes = texto[max(0, m.start() - 240):m.start()]
        if re.search(r"\b(?:rea(?:l|is)|centavos?)\s*\(\s*$", antes, re.I):
            continue
        out.append(" ".join(m.group(0).split()))
    return out


def l41_mensagem(valores, trecho):
    vals = ", ".join(f"«{v}»" for v in valores)
    return (f"L41 VALOR SEM EXTENSO NOS PEDIDOS: {vals} em «{' '.join(str(trecho).split())[:160]}». "
            f"Valor em algarismo sem o por extenso nos pedidos: confira se a banca escreve por "
            f"extenso.")
















_L42_SUPERIOR_RX = re.compile(r"\bSUPERIOR\s+TRIBUNAL\b|\bSUPREMO\s+TRIBUNAL\b|\bTRIBUNAL\s+SUPERIOR\b")






_L42_DISTRITO_FEDERAL_RX = re.compile(r"\bDISTRITO\s+FEDERAL\b")
_L42_NAO_JUIZO_FEDERAL_RX = re.compile(
    r"\b(?:COMPETENCIA|JURISDICAO)\s+FEDERAL(?:\s+DELEGADA)?\b"
    r"|\b(?:CAIXA\s+ECONOMICA|RECEITA|POLICIA(?:\s+RODOVIARIA)?|UNIVERSIDADE|UNIAO|AUTARQUIA"
    r"|EMPRESA\s+PUBLICA|FUNDACAO(?:\s+PUBLICA)?|SERVIDORA?\s+PUBLIC[OA]"
    r"|INSTITUTO|CONSELHO|DEPUTADO|SENADO|RODOVIA|FAZENDA|CONSTITUICAO)\s+FEDERA(?:L|IS)\b")
_L42_FEDERAL_FORTE_RX = re.compile(
    r"\bJUIZ[AO]?\s+FEDERA(?:L|IS)\b|\bJUIZO\s+FEDERAL\b|\bJUSTICA\s+FEDERAL\b"
    r"|\b(?:SUB)?SECAO\s+JUDICIARIA\b|\bTRF\b|\bTRIBUNAL\s+REGIONAL\s+FEDERAL\b"
    r"|\bJUIZADOS?\s+ESPECIA(?:L|IS)\s+(?:(?:CIVE(?:L|IS)|CRIMINA(?:L|IS))\s+)?FEDERA(?:L|IS)\b"
    r"|\bJEF\b|\bDESEMBARGADORA?\s+FEDERAL\b|\bTURMA\s+(?:NACIONAL|REGIONAL)\s+DE\s+UNIFORMIZACAO\b")
_L42_FEDERAL_MEDIO_RX = re.compile(r"\bVARAS?\s+(?:[\w-]+\s+){0,4}FEDERA(?:L|IS)\b")
_L42_ESTADUAL_FORTE_RX = re.compile(r"\bJUIZ[AO]?\s+DE\s+DIREITO\b|\bJUIZO\s+DE\s+DIREITO\b|\bCOMARCA\b")
_L42_JEF_RX = re.compile(r"\bJUIZADOS?\s+ESPECIA(?:L|IS)\b|\bTURMAS?\s+RECURSA(?:L|IS)\b"
                         r"|\bTURMA\s+(?:NACIONAL|REGIONAL)\s+DE\s+UNIFORMIZACAO\b|\bJEF\b"
                         r"|\bVARA-?\s?GABINETE\b")
_L42_TRIBUNAL_FEDERAL_RX = re.compile(r"\bTRIBUNAL\s+REGIONAL\s+FEDERAL\b|\bTRF\b")
_L42_TRABALHO_RX = re.compile(r"\bVARA\s+(?:UNICA\s+)?DO\s+TRABALHO\b|\bJUIZ[AO]?\s+DO\s+TRABALHO\b"
                              r"|\bTRIBUNAL\s+REGIONAL\s+DO\s+TRABALHO\b")
_L42_ELEITORAL_RX = re.compile(r"\bZONA\s+ELEITORAL\b|\bJUIZ[AO]?\s+ELEITORAL\b"
                               r"|\bTRIBUNAL\s+REGIONAL\s+ELEITORAL\b")
_L42_ESTADUAL_RX = re.compile(
    r"\bJUIZ[AO]?\s+DE\s+DIREITO\b|\bJUIZO\s+DE\s+DIREITO\b|\bCOMARCA\b|\bVARAS?\s+CIVE(?:L|IS)\b"
    r"|\bFAZENDA\s+PUBLICA\b|\bTRIBUNAL\s+DE\s+JUSTICA\b|\bJUIZADOS?\s+ESPECIA(?:L|IS)\b"
    r"|\bCOLEGIO\s+RECURSAL\b|\bVARAS?\s+D[AE]\s+FAMILIA\b"
    r"|\bFORO\s+(?:CENTRAL|REGIONAL|DISTRITAL)\b|\bFORO\s+D[AEO]S?\b|\bVARA\s+(?:CRIMINAL|DE\s+FALENCIAS"
    r"|DE\s+ACIDENTES?|DE\s+SUCESSOES|DA\s+INFANCIA|DE\s+REGISTROS|DE\s+EXECUCOES|UNICA|JUDICIAL)\b"
    r"|\bVARAS?\s+(?:REGIONA(?:L|IS)\s+)?EMPRESARIA(?:L|IS)\b|\bDIREITO\s+BANCARIO\b")


_L42_CABECALHO_RX = re.compile(
    r"^\s*(?:URGENTE|PRIORIDADE|PROCESSOS?\b|AUTOS\b|REF\b|REFERENCIA|DISTRIBUICAO|PROC\b|N[Oº°]?\s*\d"
    r"|CARTA\s+PRECATORIA|PEDIDO\s+DE\s+TUTELA|COM\s+PEDIDO|SEGREDO\s+DE\s+JUSTICA|TRAMITACAO)")
_L42_JUIZO_RX = re.compile(
    r"\bJUIZ[AO]?\b|\bJUIZO\b|\bVARAS?\b|\bTRIBUNA(?:L|IS)\b|\bTURMAS?\b|\bDESEMBARGADORA?\b|\bFORO\b"
    r"|\bCOMARCA\b|\b(?:SUB)?SECAO\s+JUDICIARIA\b|\bZONA\b|\bMINISTRO\b|\bJUIZADOS?\b|\bCOLEGIO\b"
    r"|\bTRF\b|\bJEF\b|\bJEC\b|\bCAMARA\b|\bRELATORA?\b")
_L42_QUALIFICACAO_RX = re.compile(r"\bCPF\b|\bCNPJ\b|\bEM\s+FACE\b|\bVEM\b|,\s*BRASILEIR|\bINSCRIT")
_L42_TJ_RX = re.compile(r"\bTRIBUNAL\s+DE\s+JUSTICA\b")
_L42_CAMPOS = ("justica", "delegada", "jef", "excecao")
_L42_NOME_JUSTICA = {"estadual": "JUSTIÇA ESTADUAL", "trabalho": "JUSTIÇA DO TRABALHO",
                     "eleitoral": "JUSTIÇA ELEITORAL"}
_L42_CAPA_MAX = 12


def _l42_norm(texto):
    return " ".join(_sem_acento(texto or "").upper().split())


def l42_ramo_enderecamento(texto):
    "(ramo, jef) do endereçamento: ramo 'federal' | 'estadual' | 'trabalho' | 'eleitoral' |"




    t = re.sub(r"\((?:A|O|AS|OS)\)", "", _l42_norm(texto))
    if not t or _L42_SUPERIOR_RX.search(t):
        return None, False
    sem_df = _L42_NAO_JUIZO_FEDERAL_RX.sub(" ", _L42_DISTRITO_FEDERAL_RX.sub(" ", t))
    if _L42_FEDERAL_FORTE_RX.search(sem_df) or (
            _L42_FEDERAL_MEDIO_RX.search(sem_df) and not _L42_ESTADUAL_FORTE_RX.search(sem_df)):
        return "federal", bool(_L42_JEF_RX.search(sem_df))
    if _L42_TRABALHO_RX.search(t):
        return "trabalho", False
    if _L42_ELEITORAL_RX.search(t):
        return "eleitoral", False
    if _L42_ESTADUAL_RX.search(t):
        return "estadual", False
    return None, False


def l42_entes_na_capa(paragrafos):
    'Entes federais nomeados nos parágrafos da capa, em ordem e sem repetição. Banco do Brasil'


    if _competencia is None:
        return []
    out = []
    for p in paragrafos:
        for rotulo in _competencia.entes_nomeados(p):
            if rotulo not in out:
                out.append(rotulo)
    return out


def _l42_ler(caminho):
    """O COMPETENCIA.json lido e validado, ou levanta ValueError dizendo por quê."""
    with open(caminho, "rb") as f:
        dados = json.loads(f.read().decode("utf-8-sig"))
    if not isinstance(dados, dict) or dados.get("schema") != "dsr.competencia.v1":
        raise ValueError("não é um resultado dsr.competencia.v1")
    if dados.get("justica") not in ("federal", "estadual", "trabalho", "eleitoral", "indeterminada"):
        raise ValueError(f"justiça «{dados.get('justica')}» desconhecida")
    return dados


def artefatos_do_caso(caminho_docx, nome, session_id=None):
    'Caminhos absolutos de `nome` (COMPETENCIA.json, ADMISSIBILIDADE.json) na pasta do caso'



    candidatos = []
    if _caso_raiz is not None:
        try:
            raiz, origem = _caso_raiz.resolver(session_id=session_id)
            if origem == "atual":


                _pont = _caso_raiz._ler_ponteiro(_caso_raiz.caminho_ponteiro_atual()) or {}
                _dono = str(_pont.get("session_id") or "").strip()
                if _dono and _dono != str(session_id or "").strip():
                    origem = "outra_sessao"
            achado = (os.path.join(raiz, nome)
                      if origem in ("env", "sessao", "atual") else "")
            if achado and os.path.isfile(achado):
                candidatos.append(os.path.abspath(achado))
        except Exception:
            pass
    ao_lado = os.path.join(os.path.dirname(os.path.abspath(caminho_docx or ".")), nome)
    if os.path.isfile(ao_lado) and os.path.abspath(ao_lado) not in candidatos:
        candidatos.append(os.path.abspath(ao_lado))
    return candidatos


def competencia_do_caso(caminho_docx, session_id=None):
    '(dados, arquivo, aviso) do COMPETENCIA.json da peça: o da pasta do caso desta sessão e o'



    candidatos = artefatos_do_caso(caminho_docx, "COMPETENCIA.json", session_id)
    lidos, avisos = {}, []
    for c in candidatos:
        try:
            lidos[c] = _l42_ler(c)
        except Exception as e:
            avisos.append(f"L42 COMPETENCIA.json ilegível e ignorado ({c}): {e}")
    chaves = {tuple(str(d.get(k)) for k in _L42_CAMPOS) for d in lidos.values()}
    if len(chaves) > 1:
        avisos.append("L42 os COMPETENCIA.json da pasta do caso e ao lado do .docx divergem ("
                      + " × ".join(lidos) + "): nenhum é usado. Rode o verificador de novo e "
                      "deixe um só")
        return None, None, avisos
    if not lidos:
        return None, None, avisos
    arquivo, dados = next(iter(lidos.items()))
    return dados, arquivo, avisos


def l42_enderecamento(paragrafos, teto=3):
    '(endereçamento, quantos parágrafos ele ocupa, contando os cabeçalhos pulados). Pula o'




    paras = [str(p) for p in (paragrafos or [])]
    i = 0
    while i < len(paras) - 1 and i < 6 and _L42_CABECALHO_RX.match(_l42_norm(paras[i])):
        i += 1
    if i >= len(paras):
        return "", 0
    partes = [paras[i]]
    if l42_ramo_enderecamento(paras[i])[0] is not None:
        return paras[i], i + 1
    for j in range(i + 1, min(i + teto, len(paras))):
        t = _l42_norm(paras[j])
        if _L42_QUALIFICACAO_RX.search(t) or not _L42_JUIZO_RX.search(t):
            break
        partes.append(paras[j])
        if l42_ramo_enderecamento(" ".join(partes))[0] is not None:
            break
    return " ".join(partes), i + len(partes)


def l42_processos_em_curso(textos, processos_arg=()):
    'Números CNJ da capa (endereçamento, cabeçalho, qualificação) e de `--processo`: a peça é'

    out = []
    for t in textos:
        for m in CNJ_RX.finditer(str(t)):
            if m.group(0) not in out:
                out.append(m.group(0))
    for p in processos_arg or ():
        d = re.sub(r"\D", "", p or "")
        if len(d) == 20:
            cnj = f"{d[:7]}-{d[7:9]}.{d[9:13]}.{d[13]}.{d[14:16]}.{d[16:]}"
            if cnj not in out:
                out.append(cnj)
    return out


def _l42_segmento(cnj):
    """O segmento J do CNJ (4 federal, 5 trabalho, 6 eleitoral, 8 estadual)."""
    d = re.sub(r"\D", "", cnj)
    return d[13] if len(d) == 20 else ""


def _l42_capa_tem_ente(capa, dados):
    """A capa nomeia algum ente federal (o do arquivo, pelo nome, ou qualquer um reconhecido)."""
    if l42_entes_na_capa(capa):
        return True
    t = _l42_norm(" ".join(str(c) for c in capa))
    for e in dados.get("entes_federais") or []:
        nome = _l42_norm(e.get("nome")) if isinstance(e, dict) else ""
        if nome and nome in t:
            return True
    return False


def l42_achados(primeiro, capa, dados=None, arquivo=None, processos=(), explicito=False):
    '[(nível, mensagem)] do L42. `primeiro`: o endereçamento; `capa`: os demais parágrafos'



    ramo, jef_end = l42_ramo_enderecamento(primeiro)
    end = " ".join(str(primeiro).split())[:120]
    t_end = _l42_norm(primeiro)
    if ramo is None:


        if (dados is not None and dados.get("justica") == "federal" and t_end
                and not _L42_SUPERIOR_RX.search(t_end)
                and _L42_JUIZO_RX.search(re.sub(r"\bMINISTRO\b", " ", t_end))):
            return [("AVISO",
                     f"L42 ENDEREÇAMENTO NÃO RECONHECIDO: «{end}», e o verificador de "
                     f"competência ({arquivo}) apontou a Justiça Federal. O lint não reconheceu o "
                     f"juízo como federal nem como estadual; confira-o.")]
        return []
    if dados is None:
        entes = l42_entes_na_capa(capa)
        if not entes or ramo != "estadual":
            return []
        return [("AVISO",
                 f"L42 ENTE FEDERAL NA CAPA COM ENDEREÇAMENTO ESTADUAL (inferido, sem "
                 f"COMPETENCIA.json): a capa nomeia {', '.join(entes)} e a peça se dirige a "
                 f"«{end}». Ente federal em polo leva a causa à Justiça Federal (CF, art. 109, I), "
                 f"salvo falência, insolvência civil, acidente do trabalho, Justiça Eleitoral e do "
                 f"Trabalho, e a "
                 f"competência delegada previdenciária (art. 109, §3º). Rode o verificador de "
                 f"competência (competencia.py --pedido ... --gravar <pasta da peça>) e, havendo "
                 f"exceção, declare-a lá.")]
    justica = dados.get("justica")
    nomes = ", ".join(f"{e.get('nome')} ({e.get('base')})"
                      for e in (dados.get("entes_federais") or []) if isinstance(e, dict))
    sugerido = dados.get("enderecamento_sugerido") or (
        "AO JUÍZO FEDERAL DA ___ VARA FEDERAL DA SUBSEÇÃO JUDICIÁRIA DE ___")
    delegada = bool(dados.get("delegada"))
    segmentos = {_l42_segmento(c) for c in processos or ()}
    if delegada:


        if ramo == "federal" and _L42_TRIBUNAL_FEDERAL_RX.search(t_end):
            return []
        if ramo == "estadual" and _L42_TJ_RX.search(t_end):
            return [("AVISO",
                     f"L42 RECURSO DA COMPETÊNCIA DELEGADA ENDEREÇADO AO TRIBUNAL DE JUSTIÇA: "
                     f"«{end}». Na competência delegada o recurso vai ao Tribunal Regional Federal "
                     f"(CF, art. 109, §4º), segundo o verificador ({arquivo}). Confira o "
                     f"tribunal.")]
    if justica == "federal" and ramo == "estadual" and processos:


        return [("AVISO",
                 f"L42 PROCESSO EM CURSO{' NA JUSTIÇA ESTADUAL' if '8' in segmentos else ''} ({', '.join(list(processos)[:3])}) E "
                 f"O VERIFICADOR APONTOU A FEDERAL ({arquivo}) por {nomes or 'ente federal em polo'}: "
                 f"em peça do processo (contestação, recurso, cumprimento, pedido de remessa) o "
                 f"endereçamento ao juízo onde ele corre («{end}») está certo. Não mude o juízo: "
                 f"argua a incompetência absoluta em preliminar (CPC, arts. 64 e 337, II — "
                 f"dispositivos não conferidos nesta regra) ou peça a remessa à Justiça Federal, a "
                 f"quem cabe decidir sobre o interesse do ente federal (Súmula 150 do STJ).")]
    if justica == "federal" and ramo == "estadual" and not explicito and not _l42_capa_tem_ente(
            capa, dados):
        return [("AVISO",
                 f"L42 COMPETENCIA.json DE OUTRA PEÇA? O arquivo ({arquivo}) aponta a Justiça "
                 f"Federal por {nomes or 'ente federal em polo'}, que a capa não nomeia, e a peça se "
                 f"dirige a «{end}». Se a peça é desta causa, nomeie o ente na qualificação; se é "
                 f"de outra peça, rode o verificador para ela e passe o arquivo com --competencia.")]
    if justica == "federal" and ramo == "estadual":
        return [("ERRO",
                 f"L42 ENTE FEDERAL ENDEREÇADO À JUSTIÇA ESTADUAL: a peça se dirige a «{end}», "
                 f"mas o verificador de competência ({arquivo}) apontou a Justiça Federal por "
                 f"{nomes or 'ente federal em polo'} — CF, art. 109, I. Enderece ao juízo federal "
                 f"(«{sugerido}»). Se a causa é exceção do art. 109, I (falência, insolvência civil, acidente do "
                 f"trabalho, Justiça Eleitoral ou do Trabalho) ou de competência delegada, "
                 f"declare a exceção e rode o verificador de novo. Se a peça é de processo que já "
                 f"corre neste juízo (contestação, recurso, cumprimento), ponha o número dos autos "
                 f"na capa ou passe --processo: aí o L42 só avisa.")]
    if justica == "federal" and ramo in ("trabalho", "eleitoral"):
        return [("AVISO",
                 f"L42 CAUSA FEDERAL ENDEREÇADA À {_L42_NOME_JUSTICA[ramo]}: «{end}», e o "
                 f"verificador ({arquivo}) apontou a Justiça Federal. Confira o juízo, ou declare "
                 f"a exceção e rode o verificador de novo.")]
    if (justica == "federal" and ramo == "federal" and dados.get("jef") == "sim" and not jef_end
            and not _L42_TRIBUNAL_FEDERAL_RX.search(t_end) and "4" not in segmentos):
        return [("AVISO",
                 f"L42 CAUSA DO JEF ENDEREÇADA À VARA FEDERAL COMUM: «{end}». O verificador "
                 f"({arquivo}) apontou o Juizado Especial Federal, cuja competência é absoluta "
                 f"onde houver vara instalada (Lei 10.259/2001, art. 3º, §3º). Confira se a "
                 f"subseção tem JEF e, tendo, enderece a ele.")]
    if justica in _L42_NOME_JUSTICA and ramo == "federal":
        rotulo = " (competência delegada)" if delegada else ""
        return [("AVISO",
                 f"L42 ENDEREÇAMENTO FEDERAL EM CAUSA DA {_L42_NOME_JUSTICA[justica]}{rotulo}: "
                 f"«{end}», e o verificador ({arquivo}) não apontou a Justiça Federal. Ele só mede o "
                 f"ente federal em polo (CF, art. 109, I): crime federal (art. 109, IV) e mandado de "
                 f"segurança contra ato de autoridade federal (art. 109, VIII) ficam fora dele. "
                 f"Confira o juízo.")]
    if justica == "indeterminada" and dados.get("a_confirmar"):
        pend = dados["a_confirmar"]
        pend = [pend] if isinstance(pend, str) else (pend if isinstance(pend, list) else [])
        return [("AVISO",
                 f"L42 COMPETÊNCIA A CONFIRMAR ({arquivo}): "
                 + " ".join(str(m) for m in pend if isinstance(m, str))[:400]
                 + " Pergunte ao advogado e rode o verificador de novo.")]
    if (justica == "estadual" and ramo == "estadual" and not dados.get("excecao") and not delegada):


        partes = [p for p in (dados.get("partes") or []) if isinstance(p, dict)]
        if not any(p.get("esfera") in ("federal", "a_confirmar") for p in partes):
            entes = l42_entes_na_capa(capa)
            if entes:
                return [("AVISO",
                         f"L42 ENTE FEDERAL NA CAPA QUE O VERIFICADOR NÃO RECEBEU: a capa nomeia "
                         f"{', '.join(entes)}, mas o verificador de competência ({arquivo}) não "
                         f"recebeu parte federal e apontou a Justiça Estadual. Confira se o pedido "
                         f"dele trouxe todas as partes e rode-o de novo.")]
    return []















L43_VIGENCIA = "2026-09-03"
L43_SCHEMA = "dsr.admissibilidade.entrada.v1"
L43_ARQUIVO = "ADMISSIBILIDADE.json"


L43_RESP = {"recurso especial", "resp", "recurso especial repetitivo"}
L43_OUTROS_ESPECIAIS = {"agravo em recurso especial", "aresp"}
_L43_NAO_LEEM = ("agravo interno", "embargos", "contrarrazoes", "contraminuta", "resposta")
_L43_TITULO_MAX = 160


_L43_TITULO_RX = re.compile(
    r"\bRELEVANCIA\b(?:\s+DAS?\s+QUEST(?:AO|OES)\s+(?:DE\s+DIREITO\s+|JURIDICAS?\s+)?FEDERA(?:L|IS)\b"
    r"|\s*\(?\s*(?:CPC\s*,?\s*)?ART(?:IGO)?\.?\s*1\.?035\s*-?\s*A\b)")
_L43_ROMANO = r"(VI|IV|V|I{1,3})(?![IVXLC\w])"
_L43_PAR3 = r"(?:§|par[aá]grafo)\s*3\s*\.?\s*[ºo°]?"
_L43_DISPOSITIVO_RX = (
    re.compile(r"(?i:art(?:igo)?\.?\s*105\s*,?\s*" + _L43_PAR3
               + r"\s*,?\s*(?:inc(?:iso|\.)\s*)?)" + _L43_ROMANO),
    re.compile(r"(?i:inc(?:iso|\.)\s*)" + _L43_ROMANO
               + r"(?i:\s+do\s+" + _L43_PAR3 + r"\s+do\s+art(?:igo)?\.?\s*105)"))
_L43_CAPA_RESP_RX = re.compile(r"\bRECURSO\s+ESPECIAL\b")
_L43_CAPA_OUTRO_RX = re.compile(r"\bCONTRARRAZ|\bAGRAVO\b|\bCONTRAMINUTA\b")


_L43_CAPA_OUTRA_PECA_RX = re.compile(
    r"\bCONTRARRAZ|\bCONTRAMINUTA\b|\bAGRAVO\s+(?:INTERNO|EM\s+RECURSO\s+ESPECIAL)\b"
    r"|\bRESPOSTA\s+AO\s+RECURSO\b")
_L43_INTERPOE_RESP_RX = re.compile(r"\bINTERP\w*\s+(?:O\s+PRESENTE\s+|ESTE\s+)?RECURSO\s+ESPECIAL\b")


def _l43_norm_recurso(s):
    t = _l42_norm(str(s or "")).casefold()
    return " ".join(re.sub(r"[_\-]+", " ", t).split())


def _l43_data(pub):
    """date de `AAAA-MM-DD` estrito, ou None."""
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", pub):
        return None
    try:
        import datetime as _dt43
        return _dt43.date.fromisoformat(pub)
    except ValueError:
        return None


def _l43_titulo_seguinte(texto):
    """Parágrafo que abre outro tópico: curto, sem ponto final, em caixa alta ou numerado."""
    t = " ".join(str(texto or "").split())
    if not t or len(t) > 120 or t.endswith((".", ";", ":", ",")):
        return False
    letras = [c for c in t if c.isalpha() and c not in "ºª"]
    if len(letras) >= 3 and not any(c.islower() for c in letras):
        return True
    return bool(re.match(r"^(?:[IVXLC]+|\d+(?:\.\d+)*)\s*[-–—.)]\s+\S", t))


def l43_titulo_relevancia(texto):
    'O parágrafo é o título do tópico de relevância: curto e com «relevância da questão (de'

    t = " ".join(str(texto or "").split())
    if not t:
        return False
    letras = [c for c in t if c.isalpha() and c not in "ºª"]
    caixa_alta = len(letras) >= 3 and not any(c.islower() for c in letras)


    if not caixa_alta and (len(t) > _L43_TITULO_MAX or t.endswith((".", ";"))):
        return False
    return bool(_L43_TITULO_RX.search(_l42_norm(t[:_L43_TITULO_MAX])))


def _l43_ler(caminho):
    with open(caminho, encoding="utf-8") as f:
        dados = json.load(f)
    if not isinstance(dados, dict) or dados.get("schema_version") != L43_SCHEMA:
        raise ValueError(f"não é a entrada do checklist de admissibilidade (`schema_version` "
                         f"{L43_SCHEMA}, com `recurso` e `acordao_publicado_em`)")
    return dados


def admissibilidade_do_caso(caminho_docx, session_id=None):
    '(dados, arquivo, avisos, achou_algum) do ADMISSIBILIDADE.json da peça, com a mesma'

    candidatos = artefatos_do_caso(caminho_docx, L43_ARQUIVO, session_id)
    lidos, avisos = {}, []
    for c in candidatos:
        try:
            lidos[c] = _l43_ler(c)
        except Exception as e:
            avisos.append(f"L43 {L43_ARQUIVO} ilegível e ignorado ({c}): {e}")
    chaves = {json.dumps([d.get("recurso"), d.get("acordao_publicado_em"),
                          (d.get("criterios") or {}).get("relevancia_questao_federal")],
                         sort_keys=True, ensure_ascii=False) for d in lidos.values()}
    if len(chaves) > 1:
        avisos.append(f"L43 os {L43_ARQUIVO} da pasta do caso e ao lado do .docx divergem ("
                      + " × ".join(lidos) + "): nenhum é usado. Deixe um só, o da entrada que "
                      "o checklist de admissibilidade avaliou")
        return None, None, avisos, True
    if not lidos:
        return None, None, avisos, bool(candidatos)
    arquivo, dados = next(iter(lidos.items()))
    return dados, arquivo, avisos, True


def l43_incisos_citados(texto):
    'Incisos do art. 105, § 3º, da CF citados no texto («art. 105, § 3º, III», «inciso III do'

    achados = set()
    for rx in _L43_DISPOSITIVO_RX:
        achados.update(m.group(1).upper() for m in rx.finditer(str(texto or "")))
    return achados


def l43_achados(paragrafos, dados, arquivo):
    '[(nível, mensagem)] do L43. `paragrafos`: os textos da peça, em ordem; `dados`: a entrada'

    recurso = _l43_norm_recurso(dados.get("recurso"))
    if recurso not in L43_RESP:
        palavras = set(re.split(r"[^a-z0-9]+", recurso))
        if (recurso and recurso not in L43_OUTROS_ESPECIAIS and not recurso.startswith(_L43_NAO_LEEM)
                and palavras & {"especial", "resp", "aresp"}):
            return [("AVISO",
                     f"L43 NÃO MEDIDO: o checklist de admissibilidade ({arquivo}) declara o recurso "
                     f"{dados.get('recurso')!r}, fora do vocabulário (o checklist o recusa). Use "
                     f"«recurso especial» ou «agravo em recurso especial» e rode de novo.")]
        return []
    pub = str(dados.get("acordao_publicado_em") or "").strip()
    if pub and _l43_data(pub) is None:
        return [("ERRO",
                 f"L43 DATA DO ACÓRDÃO ILEGÍVEL: o checklist de admissibilidade ({arquivo}) traz "
                 f"`acordao_publicado_em` {pub!r}, fora de AAAA-MM-DD ou inexistente, e o checklist "
                 f"recusa essa forma. Sem a data o linter não sabe se o tópico de relevância é "
                 f"exigido (acórdãos publicados a partir de {L43_VIGENCIA[8:]}/{L43_VIGENCIA[5:7]}/"
                 f"{L43_VIGENCIA[:4]}); corrija a data e rode de novo.")]
    if not pub:
        return [("AVISO",
                 f"L43 NÃO MEDIDO: o checklist de admissibilidade ({arquivo}) é de recurso "
                 f"especial e não traz `acordao_publicado_em` (AAAA-MM-DD). Sem a data do acórdão "
                 f"recorrido o linter não sabe se o tópico de relevância é exigido (acórdãos "
                 f"publicados a partir de {L43_VIGENCIA[8:]}/{L43_VIGENCIA[5:7]}/"
                 f"{L43_VIGENCIA[:4]}); preencha-a e rode de novo.")]
    if pub < L43_VIGENCIA:
        return []
    item = (dados.get("criterios") or {}).get("relevancia_questao_federal")
    item = item if isinstance(item, dict) else {}
    textos = [str(t) for t in paragrafos]
    idx = next((i for i, t in enumerate(textos) if l43_titulo_relevancia(t)), None)
    data = f"{pub[8:]}/{pub[5:7]}/{pub[:4]}"
    if idx is None:
        msg = (f"L43 RECURSO ESPECIAL SEM O TÓPICO DE RELEVÂNCIA: o acórdão recorrido foi "
               f"publicado em {data}, já sob a Lei 15.484/2026, e a peça não tem título de "
               f"tópico «Da relevância da questão de direito federal» (CPC, art. 1.035-A, § 2º). "
               f"Desatendida a forma, o recurso será inadmitido (§ 3º), e a presunção do art. "
               f"105, § 3º, da CF não dispensa o tópico: ela é o conteúdo dele (notícia oficial do "
               f"STJ de 30/08/2026). Acrescente o tópico depois do cabimento e antes do mérito "
               f"(roteiro em dissero-peticao, references/topico-relevancia-resp.md).")
        if item.get("estado") == "satisfeito":
            msg += (f" O checklist de admissibilidade ({arquivo}) declara o tópico "
                    f"(`satisfeito`): corrija a peça ou o checklist, que não podem divergir.")
        return [("ERRO", msg)]
    pres = item.get("presuncao")
    inciso = str(pres.get("inciso") or "").strip().upper() if isinstance(pres, dict) else ""
    if inciso in ("I", "II", "III", "IV", "V", "VI"):


        fim = next((j for j in range(idx + 1, len(textos))
                    if _l43_titulo_seguinte(textos[j]) and not l43_titulo_relevancia(textos[j])),
                   len(textos))
        citados = l43_incisos_citados("\n".join(textos[idx:fim]))
        if inciso not in citados:
            outros = (f" (o tópico cita o inciso {', '.join(sorted(citados))})"
                      if citados else "")
            return [("ERRO",
                     f"L43 PRESUNÇÃO DECLARADA E AUSENTE DO TÓPICO: o checklist de "
                     f"admissibilidade ({arquivo}) declara a relevância presumida pelo art. 105, "
                     f"§ 3º, {inciso}, da CF, e o tópico «{' '.join(textos[idx].split())[:90]}» não "
                     f"cita esse dispositivo{outros}. A presunção é o conteúdo do tópico: diga a "
                     f"hipótese (CF, art. 105, § 3º, {inciso}) e o fato do caso que a demonstra, ou "
                     f"corrija o inciso no checklist.")]
    return []


def l43_capa_de_resp(capa):
    """A capa fala em recurso especial (e não em contrarrazões, contraminuta ou agravo)."""
    t = _l42_norm(" ".join(str(c) for c in capa))
    return bool(_L43_CAPA_RESP_RX.search(t)) and not _L43_CAPA_OUTRO_RX.search(t)


def l43_capa_de_outra_peca(capa):
    'A capa é de contrarrazões, contraminuta, resposta, agravo interno ou agravo em recurso'


    t = _l42_norm(" ".join(str(c) for c in capa))
    return bool(_L43_CAPA_OUTRA_PECA_RX.search(t)) and not _L43_INTERPOE_RESP_RX.search(t)














_L44_IDS = {"ordem_de_julgamento_a_ia", "nota_oculta_a_ia", "condicional_ia",
            "condicional_leitura_maquina", "dirigido_a_ia"}


_L44_ASPAS_RX = re.compile(r'"[^"\n]{3,}"|“[^”\n]{3,}”|«[^»\n]{3,}»|‘[^’\n]{3,}’'
                           r"|(?<!\w)'[^'\n]{3,}'(?!\w)")
_L44_ESTILO_CITACAO_RX = re.compile(r"cita|quote", re.I)
_L44_RECUO_CITACAO = 1134


def _l44_paragrafo_de_citacao(p):
    'Parágrafo de citação recuada (recuo esquerdo de 2 cm ou mais, fora de lista) ou com'


    try:
        ppr = p.find(W + "pPr")
        if ppr is None or e_item_de_lista(p):
            return False
        st = ppr.find(W + "pStyle")
        if st is not None and _L44_ESTILO_CITACAO_RX.search(st.get(W + "val") or ""):
            return True
        ind = ppr.find(W + "ind")
        if ind is None:
            return False
        recuo = ind.get(W + "left") or ind.get(W + "start") or "0"
        return int(float(recuo)) >= _L44_RECUO_CITACAO
    except (AttributeError, ValueError, TypeError):
        return False
_L44_DETECTOR = []


def _l44_carregar_detector():
    'O módulo `detectar_injecao`, ao lado do linter ou na pasta de scripts da ingestão, ou'

    aqui = os.path.dirname(os.path.abspath(__file__))
    for pasta in (aqui, os.path.join(aqui, os.pardir, os.pardir, "dissero-ingestao", "scripts")):
        alvo = os.path.join(pasta, "detectar_injecao.py")
        if not os.path.isfile(alvo):
            continue
        try:
            import importlib.util as _ilu
            spec = _ilu.spec_from_file_location("_dsr_lint_detectar_injecao", alvo)
            mod = _ilu.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if hasattr(mod, "varrer"):
                return mod
        except Exception:
            continue
    return None


def _l44_detector():
    if not _L44_DETECTOR:
        _L44_DETECTOR.append(_l44_carregar_detector())
    return _L44_DETECTOR[0]


def _l44_da_familia(detector, texto, so_alta=False):
    return [a for a in detector.varrer(texto)
            if a.get("id") in _L44_IDS and (not so_alta or a.get("severidade") == "alta")]


def l44_achados(paragrafos, detector):
    '[(nível, mensagem)] do L44. `paragrafos`: [(texto, em_tabela)]; `detector`: o módulo'


    try:
        if not _l44_da_familia(detector, "\n".join(str(t) for t, _ in paragrafos)):
            return []
    except Exception as e:
        return [("AVISO", f"L44 NÃO MEDIDO: o detector de trecho dirigido a IA falhou ({e}).")]
    out = []
    for texto, em_tbl in paragrafos:
        t = " ".join(str(texto).split())
        if not t:
            continue
        familia = _l44_da_familia(detector, t)
        if not familia:
            continue
        trecho = (t[:160] + "…") if len(t) > 160 else t
        alta = any(a.get("severidade") == "alta" for a in familia)
        if alta and not em_tbl and _l44_da_familia(detector, _L44_ASPAS_RX.sub(" ", t), True):
            out.append(("ERRO",
                        f"L44 TRECHO DIRIGIDO A FERRAMENTA DE IA: «{trecho}». Frase que se dirige "
                        f"à IA e manda decidir sai na peça e responde quem protocola: pode "
                        f"configurar ato atentatório à dignidade da justiça ou litigância de má-fé "
                        f"(CPC, arts. 77 e 80; enquadramento a conferir). No REsp 2.256.731/PB "
                        f"(Sexta Turma, DJEN de 11/09/2026), o STJ decidiu que a inserção oculta de "
                        f"comando destinado a manipular IA caracteriza ato atentatório à dignidade "
                        f"da justiça e mandou oficiar à OAB e ao MPF; noutro processo, aplicou "
                        f"multa por litigância de má-fé (notícia oficial de 03/09/2026; acórdão "
                        f"não lido). Tire a "
                        f"frase e confira de onde veio (modelo, documento do cliente). Se a peça transcreve o comando para discuti-lo, ponha-o "
                        f"entre aspas ou em caixa de citação."))
        elif alta:
            out.append(("AVISO",
                        f"L44 TRECHO DIRIGIDO A IA EM TRANSCRIÇÃO (entre aspas, em caixa ou em citação recuada): "
                        f"«{trecho}». Se a peça cita o comando para discuti-lo, está certo; se ele "
                        f"veio de modelo ou de documento do cliente, tire-o, porque quem protocola "
                        f"responde por ele."))
        else:
            out.append(("AVISO",
                        f"L44 TRECHO QUE SE DIRIGE A IA: «{trecho}». Não manda decidir, mas não é "
                        f"linguagem de peça: confira de onde veio e tire-o, salvo se for citação."))
    if not out:
        out.append(("AVISO",
                    "L44 TRECHO DIRIGIDO A IA ENTRE PARÁGRAFOS: o detector acusou, no texto "
                    "inteiro, recado à IA que nenhum parágrafo sozinho contém (o vocativo num, a "
                    "ordem no seguinte). Leia a peça procurando frase endereçada a ferramenta de "
                    "IA e tire-a."))
    return out














L45_MARCO = "2026-09-16"
_L45_S463_RX = re.compile(r"(?i:s[uú]mula)\s*(?i:n\s*[º°o.]?\s*)?463\s*,?\s*(?i:(?:item|inciso)\s+)?"
                          r"I(?![IVX\w])")
_L45_40_RX = re.compile(r"(?:40\s*%|quarenta\s+por\s+cento)[^.;]{0,120}?(?:teto|limite\s+m[aá]ximo)",
                        re.I)
_L45_ADC80_RX = re.compile(r"\bADC\s*(?:n\s*[º°o.]?\s*)?80\b")
_L45_RESSALVA_RX = re.compile(r"inconstitucion|n[aã]o\s+se\s+aplica|ex\s+nunc|modula|afastad",
                              re.I)
_L45_RELATOR_RX = re.compile(r"\bRel(?:\.|ator)\s*(?:Min(?:\.|istro)\s*)?Gilmar\s+Mendes", re.I)
_L45_REDATOR_RX = re.compile(r"p/\s*(?:o\s+)?ac[oó]rd[aã]o|para\s+o\s+ac[oó]rd[aã]o|\bRed(?:\.|ator)",
                             re.I)


def _l45_br(data):
    return f"{data[8:]}/{data[5:7]}/{data[:4]}"


def l45_achados(paragrafos, ajuizamento=None, inaugural=False):
    '[(nível, mensagem)] do L45, todos AVISO. `ajuizamento`: AAAA-MM-DD ou None; `inaugural`:'

    out, sem_data = [], []
    marco = _l45_br(L45_MARCO)
    if ajuizamento:
        depois, origem = ajuizamento >= L45_MARCO, f"ajuizada em {_l45_br(ajuizamento)}"
    elif inaugural:
        depois, origem = True, ("peça inaugural, sem número de processo na capa nem em "
                                "--processo: a ação se ajuíza agora")
    else:
        depois, origem = None, ""
    for texto in paragrafos:
        t = " ".join(str(texto).split())
        if not t:
            continue
        trecho = (t[:140] + "…") if len(t) > 140 else t
        regime_antigo = bool(_L45_S463_RX.search(t) or _L45_40_RX.search(t))
        adc80 = bool(_L45_ADC80_RX.search(t))
        ressalva = bool(_L45_RESSALVA_RX.search(t))
        if adc80 and _L45_RELATOR_RX.search(t) and not _L45_REDATOR_RX.search(t):
            out.append(("AVISO",
                        f"L45 ADC 80 COM O RELATOR NO LUGAR DO REDATOR: «{trecho}». O voto condutor "
                        f"é do Ministro Gilmar Mendes, Redator para o acórdão; o Relator, Ministro "
                        f"Edson Fachin, ficou vencido (decisão de julgamento de 03/09/2026, portal "
                        f"do STF). Cite «Red. p/ acórdão Min. Gilmar Mendes»."))
        if ressalva or not (regime_antigo or adc80):
            continue
        if depois is None:
            sem_data.append(trecho)
        elif depois and regime_antigo:
            out.append(("AVISO",
                        f"L45 GRATUIDADE PELO REGIME ANTERIOR À ADC 80 EM AÇÃO AJUIZADA A PARTIR "
                        f"DE {marco} ({origem}): «{trecho}». O STF declarou inconstitucionais a "
                        f"expressão dos 40% do teto do RGPS do art. 790, § 3º, da CLT (item i) e a "
                        f"Súmula 463, I, do TST (item vii), para os processos ajuizados a partir da "
                        f"publicação da ata de julgamento, em {marco} (item x; acórdão ainda não "
                        f"publicado). Confira o regime pela data de ajuizamento."))
        elif not depois and adc80:
            out.append(("AVISO",
                        f"L45 ADC 80 INVOCADA EM PROCESSO AJUIZADO ANTES DE {marco} ({origem}): "
                        f"«{trecho}». A decisão tem efeitos ex nunc, só para os processos ajuizados "
                        f"a partir da publicação da ata de julgamento, em {marco} (item x). Neste "
                        f"processo vale o regime anterior; confira a data de ajuizamento."))
    if sem_data:
        out.append(("AVISO",
                    f"L45 DATA DE AJUIZAMENTO NÃO INFORMADA: a peça é de processo em curso e trata "
                    f"da gratuidade pela Súmula 463, I, pelos 40% do teto ou pela ADC 80 "
                    f"(«{sem_data[0]}»). O regime depende da data de ajuizamento: a ADC 80 só "
                    f"alcança os processos ajuizados a partir de {marco} (item x). Passe "
                    f"--ajuizamento AAAA-MM-DD."))
    return out


def main(argv):
    '`--json ARQUIVO` grava, além do relatório de sempre, o relatório estruturado (com a'


    argv = list(argv or [])
    if "--json" not in argv:
        return _main(argv, None)
    i = argv.index("--json")
    destino = argv[i + 1] if i + 1 < len(argv) else ""
    resto = argv[:i] + argv[i + 2:]
    if not destino or (destino.startswith("--") and destino != "-"):
        print("REPROVADO: --json exige o caminho do arquivo de saída (ou - para a saída padrão)")
        return 1
    import contextlib
    import io
    relatorio, buf = {}, io.StringIO()
    with contextlib.redirect_stdout(buf):
        codigo = _main(resto, relatorio)
    texto = buf.getvalue()
    if not relatorio:

        motivo = next((l for l in texto.splitlines() if l.strip()), "")
        relatorio = {"formato": 1, "peca": resto[0] if resto else "", "veredito":
                     "REPROVADO" if codigo else "APROVADO", "exit_code": codigo,
                     "erros": [classificar_achado(motivo)] if codigo else [],
                     "pendencias": [], "avisos": [],
                     "resumo": resumo_de_naturezas([motivo] if codigo else [])}
    corpo = json.dumps(relatorio, ensure_ascii=False, indent=2)
    if destino == "-":
        print(corpo)
    else:
        sys.stdout.write(texto)
        with open(destino, "w", encoding="utf-8") as fh:
            fh.write(corpo + "\n")
    return codigo


def _main(argv, relatorio):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__); return 2



    global _disp, _comarca_padrao
    perfil = _perfil_do_ambiente()
    _disp = _dispensas_do_ambiente(perfil)
    _comarca_padrao = _comarca_do_ambiente(perfil)




    definir_tema(perfil)
    caminho = argv[0]
    fragmento = "--fragmento" in argv[1:]
    prec_path = jnt_path = conf_arg = grau_arg = sessao = comp_arg = adm_arg = ajuiz_arg = None
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
        if a == "--competencia" and i + 1 < len(argv):
            comp_arg = argv[i + 1]
        if a == "--admissibilidade" and i + 1 < len(argv):
            adm_arg = argv[i + 1]
        if a == "--ajuizamento" and i + 1 < len(argv):
            ajuiz_arg = argv[i + 1].strip()
    if "--competencia" in argv and (comp_arg is None or comp_arg.startswith("--")):
        print("REPROVADO: --competencia exige o caminho do COMPETENCIA.json gravado pelo "
              "verificador de competência")
        return 1
    if "--admissibilidade" in argv and (adm_arg is None or adm_arg.startswith("--")):
        print("REPROVADO: --admissibilidade exige o caminho da entrada do checklist de "
              "admissibilidade (dsr.admissibilidade.entrada.v1)")
        return 1
    if "--ajuizamento" in argv:
        _aj_ok = bool(ajuiz_arg) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", ajuiz_arg) is not None
        if _aj_ok:
            try:
                import datetime as _dt
                _dt.date.fromisoformat(ajuiz_arg)
            except ValueError:
                _aj_ok = False
        if not _aj_ok:
            print(f"REPROVADO: --ajuizamento exige a data de ajuizamento da ação em AAAA-MM-DD "
                  f"(recebido: {ajuiz_arg!r})")
            return 1
    if grau_arg and grau_arg not in grau_jurisdicao.GRAUS:
        print(f"REPROVADO: --grau '{grau_arg}' inválido — use um de "
              f"{', '.join(grau_jurisdicao.GRAUS)}")
        return 1
    try:
        caminho, prec_path, jnt_path, conf_arg, comp_arg, adm_arg = (
            no_caso(caminho, sessao), no_caso(prec_path, sessao), no_caso(jnt_path, sessao),
            no_caso(conf_arg, sessao), no_caso(comp_arg, sessao), no_caso(adm_arg, sessao))
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



    for txt, em_tbl, _p, rs in textos:
        if em_tbl or ("R$" not in txt and "%" not in txt):
            continue
        _masc = "".join((" " * len(t)) if it else t for t, _b, _hl, it, _u in rs)
        for _tr, _num, _lido, _perc in l36_achados(txt, _masc):
            erros.append(l36_mensagem(_tr, _num, _lido, _perc))
        for _tr, _num, _lido, _perc in l36_avisos(txt, _masc):
            avisos.append(l36_mensagem(_tr, _num, _lido, _perc, qualificado=True))



    _nos_pedidos = _no_banner = False
    for txt, em_tbl, _p, rs in textos:
        if l41_titulo_de_pedidos(txt):
            _nos_pedidos, _no_banner = True, em_tbl
            continue

        _no_banner = _no_banner and em_tbl
        if _nos_pedidos and not _no_banner and l41_titulo_de_secao(txt):
            _nos_pedidos = False
            continue
        if not _nos_pedidos or em_tbl or "R$" not in txt:
            continue
        _masc = "".join((" " * len(t)) if it else t for t, _b, _hl, it, _u in rs)
        _vals = l41_achados(txt, _masc)
        if _vals:
            avisos.append(l41_mensagem(_vals, txt))




    _vistos_l37_38 = set()
    for txt, _em, _p, _rs in textos:
        for _tr, _cl, _tb, _esp in l37_achados(txt):
            _msg = l37_mensagem(_tr, _cl, _tb, _esp)
            if _msg not in _vistos_l37_38:
                _vistos_l37_38.add(_msg)
                avisos.append(_msg)
        for _rot, _n, _ch in l38_achados(txt):
            _msg = l38_mensagem(_rot, TETOS_PRECEDENTE[_ch]["teto"],
                                TETOS_PRECEDENTE[_ch]["conferido_em"])
            if _msg not in _vistos_l37_38:
                _vistos_l37_38.add(_msg)
                avisos.append(_msg)
    _oj_regionais = []
    for txt, _em, _p, _rs in textos:
        for _rot in l38_oj_regionais(txt):
            if _rot not in _oj_regionais:
                _oj_regionais.append(_rot)
    if _oj_regionais:
        avisos.append(l38_mensagem_oj_regional(_oj_regionais))


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
            avisos.append(f"L9 {n_nums} julgados num só parágrafo — UM julgado por parágrafo: "
                          f"«{cite(t)}». A peça não é reprovada por isso.")


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
            f"Para o assistente (não repita ao advogado): gere-a com "
            f"`python build_precedentes.py achados.json` e relinte com "
            f"`--precedentes achados.json`.")
    if julgados_citados and not prec_path:
        erros.append(
            f"L11 FAIL-CLOSED: peça cita {len(julgados_citados)} julgado(s) e a Relação de "
            f"Precedentes NÃO foi apresentada (--precedentes ausente) — artefato OBRIGATÓRIO "
            f"do rito: a peça leva o julgado, a Relação leva a prova (selo, URL e ementa "
            f"literal, que o L9 proíbe na peça). 1º julgado: «{cite(julgados_citados[0])}». "
            f"Para o assistente (não repita ao advogado): gere-a com "
            f"`python build_precedentes.py achados.json -o \"Relação de "
            f"Precedentes — <caso>.docx\"` e relinte com `--precedentes achados.json`.")



    if prec_path:
        try:
            dados = json.load(open(prec_path, encoding="utf-8"))
            if (not isinstance(dados, dict)
                    or dados.get("schema_version") not in ("dsr.achados.v2", "dsr.achados.v3")):
                raise ValueError("o dataset precisa estar em dsr.achados.v2 ou v3; registro em "
                                 "outra versão não tem conversão: refaça a pesquisa e grave em "
                                 "dsr.achados.v3")
            achados, _sem_lastro = _status_efetivo_dos_achados(dados.get("achados", []))
            for _rot in _sem_lastro:
                pendencias.append(
                    f"{_rot}: a Relação o marca como conferido, mas a conferência não se "
                    f"sustenta (falta a confirmação assinada da tela de conferência para o texto "
                    f"atual, ou o registro foi alterado). Ele conta como ainda a conferir. "
                    + _QUEM_CONFERE)
            erros_estrategia, pendencias_estrategia = (
                estrategia_precedentes.avaliar_linguagem(texto_total, dados))
            erros.extend(f"L25 ESTRATÉGIA: {_com_proximo_passo_l25(item)}"
                         for item in erros_estrategia)
            pendencias.extend(
                f"L25 PESQUISA: {_com_proximo_passo_l25(item)}"
                for item in pendencias_estrategia)

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
            prec_teor_conferido = set()
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
                st_registros += [r + (a.get("use_status"), _teor_conferido_sem_liberacao(a))
                                 for r in _regs]






            prec_por_num = {}
            for a in achados:
                if isinstance(a, dict) and a.get("use_status") != "prohibited":
                    for _n in set(NUM_PROC_RX.findall(_num_norm(a.get("reference", "")))):
                        prec_por_num.setdefault(_n, []).append(a)
            prec_por_num = {_n: ([a for a in _l if a.get("use_status") == "allowed"] or _l)
                            for _n, _l in prec_por_num.items()}
            for a in achados:
                if isinstance(a, dict):
                    numeros = set(NUM_PROC_RX.findall(_num_norm(a.get("reference", ""))))
                    prec_nums |= numeros
                    for numero in numeros:
                        prec_status.setdefault(numero, []).append(a.get("use_status"))
                        if _teor_conferido_sem_liberacao(a):
                            prec_teor_conferido.add(numero)
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
                teor_ok = sum(1 for a in (achados or []) if _teor_conferido_sem_liberacao(a))
                _teor_frase = (
                    f" Destes, {teor_ok} com o teor já conferido contra o documento do "
                    f"tribunal — teor conferido; falta endereço oficial e a conferência no "
                    f"Minha banca: {_REMEDIO_ENDERECO_L11}." if teor_ok else "")
                pendencias.append(

                    f"L11 RELAÇÃO TOTAL PENDENTE: a Relação de Precedentes tem {total_achados} "
                    f"precedente(s) e NENHUM conferido ({pendentes} a conferir, {proibidos} "
                    f"vetado(s)) — a Relação ainda não foi conferida. A peça fica em MINUTA e "
                    f"NÃO se protocola. "




                    + _QUEM_CONFERE
                    + _teor_frase)

        if prec_nums is not None:

            _allowed_nums = {n for n, sts in prec_status.items() if "allowed" in sts}
            for rot, cit in st_citadas.items():
                casam = [r for r in st_registros if _casa_sumula_tema(cit, r)]
                if not casam:
                    erros.append(f"CRUZAMENTO: {rot} citada na peça AUSENTE da Relação de "
                                 f"Precedentes — súmula e tema precisam do registro verificado à "
                                 f"parte, como o julgado")
                    _viz = l39_vizinhos(cit[1], {
                        r[1] for r in st_registros
                        if r[5] == "allowed" and r[0] == cit[0] and r[2] == cit[2]
                        and (not cit[3] or not r[3] or cit[3] == r[3])})
                    if _viz:
                        avisos.append(l39_mensagem(rot, _viz))
                elif all(r[5] == "prohibited" for r in casam):
                    erros.append(f"CRUZAMENTO VETADO: {rot} está VETADA na Relação de Precedentes "
                                 f"(use_status=prohibited): a conferência na fonte oficial a negou. "
                                 f"Tire-a da peça e gere a peça de novo")
                elif not any(r[5] == "allowed" for r in casam):
                    if any(len(r) > 6 and r[6] for r in casam):
                        pendencias.append(
                            f"{rot} consta na Relação com o teor conferido verbatim contra o "
                            f"documento oficial — teor conferido; falta endereço oficial e a "
                            f"conferência no Minha banca: pode permanecer na minuta; antes do "
                            f"protocolo, {_REMEDIO_ENDERECO_L11}, ou ela sai da peça. "
                            f"{_TECNICO_L11}")
                    else:
                        pendencias.append(
                            f"{rot} consta na Relação, ainda SEM conferência na fonte "
                            f"oficial — pode permanecer na minuta; antes do protocolo, ou se "
                            f"confere no Minha banca, ou sai da peça. {_TECNICO_L11}")
            for txt, em_tbl, _, _ in textos:
                t = txt.strip()
                if not _eh_entrada_julgado(t, em_tbl):
                    continue
                for n in NUM_PROC_RX.findall(_num_norm(t)):
                    if n not in prec_nums:


                        erros.append(f"CRUZAMENTO: julgado citado na peça AUSENTE da Relação de "
                                     f"Precedentes (nº {n}) — todo precedente da peça precisa do "
                                     f"registro verificado à parte")
                        _viz = l39_vizinhos(n, _allowed_nums, minimo=4)
                        if _viz:
                            avisos.append(l39_mensagem(f"nº {n}", _viz))
                    elif all(s == "prohibited" for s in prec_status.get(n, [])):



                        erros.append(
                            f"CRUZAMENTO VETADO: julgado citado na peça (nº {n}) está VETADO na "
                            f"Relação de Precedentes (use_status=prohibited): a conferência na "
                            f"fonte oficial o negou. Tire-o da peça, ou substitua-o por julgado "
                            f"conferido, e gere a peça de novo")
                    elif "allowed" not in prec_status.get(n, []) and n in prec_teor_conferido:


                        pendencias.append(
                            f"julgado nº {n} consta na Relação com o teor conferido verbatim "
                            f"contra o documento do tribunal — teor conferido; falta endereço "
                            f"oficial e a conferência no Minha banca: pode permanecer na "
                            f"minuta; antes do protocolo, {_REMEDIO_ENDERECO_L11}, ou ele sai "
                            f"da peça. {_TECNICO_L11}")
                    elif "allowed" not in prec_status.get(n, []):


                        pendencias.append(
                            f"julgado nº {n} consta na Relação, ainda SEM conferência na fonte "
                            f"oficial — pode permanecer na minuta; antes do protocolo, ou se "
                            f"confere no Minha banca, ou sai da peça. {_TECNICO_L11}")

















    if prec_path and prec_nums is not None and conferencia_contract is not None:
        for tbl in body.iter(W + "tbl"):
            linhas = [''.join(x for x, _b, _h, _i, _u in runs_do_paragrafo(pp)).strip()
                      for pp in tbl.iter(W + "p")]
            linhas = [t for t in linhas if t]
            if not linhas or not linhas[0].upper().startswith("JURISPRUD"):
                continue
            atual = None
            identificacao = ""
            for linha in linhas[1:]:
                nums = NUM_PROC_RX.findall(_num_norm(linha))
                if nums:
                    atual = next((n for n in nums if n in prec_por_num), nums[0])
                    identificacao = linha
                    continue
                if atual is None or len(linha) < 60:
                    continue
                candidatos = prec_por_num.get(atual)
                if not candidatos:
                    continue
                teores = [(achado, [str(achado.get("syllabus_literal") or ""),
                                    str(achado.get("full_text") or "")])
                          for achado in candidatos]
                teores = [(achado, arm) for achado, arm in teores if any(x.strip() for x in arm)]
                if not teores:
                    erros.append(
                        f"L24 a peça transcreve o julgado nº {atual} e a Relação NÃO guardou "
                        f"teor algum dele (`syllabus_literal` e `full_text` vazios) — não se "
                        f"transcreve o que não foi lido. Reextraia a ementa da fonte oficial "
                        f"confirmada antes de citar: «{cite(linha)}»")
                    continue


                if not any(conferencia_contract.confere_transcricao(linha.strip('"“” '), arm)
                           for _a, arm in teores):
                    if any(not arm[1].strip()
                           and l24_trecho_fora_da_ementa(linha, arm[0])
                           and l24_moldura_confere(identificacao, achado)
                           for achado, arm in teores):















                        erros.append(
                            f"L24 a peça transcreve do julgado nº {atual} trecho que não está "
                            f"na ementa, e a Relação guardou só a ementa, sem o inteiro teor — "
                            f"não há com o que conferir a transcrição. Número, órgão e data "
                            f"conferem; falta o inteiro teor. Se o trecho for síntese sua, e "
                            f"não transcrição, tire-o das aspas e da caixa. «{cite(linha)}»")
                        continue
                    erros.append(
                        f"L24 TRANSCRIÇÃO NÃO CONFERE com o julgado nº {atual} — o texto na "
                        f"peça diverge do teor que a pesquisa leu na fonte oficial. Citação "
                        f"entre aspas é o que o tribunal escreveu, não o que ele deveria ter "
                        f"escrito: erro do original NÃO se corrige em silêncio, e resumo do "
                        f"julgado não ocupa o lugar da transcrição (se for síntese SUA, tire "
                        f"das aspas e diga que é síntese). «{cite(linha)}»")






    if prec_path and prec_nums is not None:
        _ementas = {n: str(_l[0].get("syllabus_literal") or "") for n, _l in prec_por_num.items()
                    if _l and str(_l[0].get("syllabus_literal") or "").strip()}
        _caixa_nums, _na_caixa, _vistos_l40 = [], False, set()
        for txt, em_tbl, _p, _rs in (textos if _ementas else []):
            t = txt.strip()
            if not t:
                continue
            if em_tbl:
                if t.upper().startswith("JURISPRUD"):
                    _na_caixa, _caixa_nums = True, []
                elif _na_caixa:
                    _caixa_nums += [n for n in NUM_PROC_RX.findall(_num_norm(t)) if n in _ementas]
                continue
            _alvo = [n for n in NUM_PROC_RX.findall(_num_norm(t)) if n in _ementas] + _caixa_nums
            _caixa_nums, _na_caixa = [], False
            for n in dict.fromkeys(_alvo):
                _tese = " ".join(l40_frases_da_tese(t, [n]))
                for _cat, _forte, _fraco in l40_achados(_tese, _ementas[n]):
                    if (n, _cat, _forte) not in _vistos_l40:
                        _vistos_l40.add((n, _cat, _forte))
                        avisos.append(l40_mensagem(_cat, _forte, _fraco, n))












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

        if nao_vazios:
            _comp_dados = _comp_arquivo = None
            if comp_arg:
                try:
                    _comp_dados, _comp_arquivo = _l42_ler(comp_arg), comp_arg
                except Exception as _e:
                    erros.append(f"L42 COMPETENCIA ilegível em --competencia ({comp_arg}): {_e}. "
                                 f"Rode o verificador de competência de novo e passe o arquivo "
                                 f"que ele gravou.")
            else:
                _comp_dados, _comp_arquivo, _comp_avisos = competencia_do_caso(caminho, sessao)
                avisos.extend(_comp_avisos)
            if _competencia is None and _comp_dados is None:
                avisos.append("L42 NÃO MEDIDO: competencia.py indisponível ao lado do linter")
            elif not (comp_arg and _comp_dados is None):



                _fim_capa = inicio_corpo if inicio_corpo_achado else len(textos)
                _capa = [t for t, _em, _p, _rs in textos[:_fim_capa]
                         if t.strip() and not _em and not tem_faixa_minuta(t)]
                _end, _n_end = l42_enderecamento(_capa)
                _procs = l42_processos_em_curso(
                    [t for t, _em, _p, _rs in textos[:_fim_capa]][:(None if inicio_corpo_achado
                                                                   else _L42_CAPA_MAX + 6)],
                    processos_arg)
                _capa = _capa[_n_end:]
                if not inicio_corpo_achado:
                    _capa = _capa[:_L42_CAPA_MAX]
                for _nivel, _msg in l42_achados(_end, _capa, _comp_dados, _comp_arquivo,
                                                processos=_procs, explicito=bool(comp_arg)):
                    (erros if _nivel == "ERRO" else avisos).append(_msg)
    elif comp_arg:
        avisos.append("L42 não roda com --fragmento (é regra de capa): --competencia ignorado")



    if not fragmento:
        _adm_dados = _adm_arquivo = None
        _adm_achou = False
        if adm_arg:
            _adm_achou = True
            try:
                _adm_dados, _adm_arquivo = _l43_ler(adm_arg), adm_arg
            except Exception as _e:
                erros.append(f"L43 ADMISSIBILIDADE ilegível em --admissibilidade ({adm_arg}): "
                             f"{_e}. Passe a entrada que o checklist de admissibilidade avaliou.")
        else:
            _adm_dados, _adm_arquivo, _adm_avisos, _adm_achou = admissibilidade_do_caso(
                caminho, sessao)
            avisos.extend(_adm_avisos)
        _fim_capa43 = inicio_corpo if inicio_corpo_achado else min(len(textos), _L42_CAPA_MAX)
        _capa43 = [t for t, _em, _p, _rs in textos[:_fim_capa43] if not tem_faixa_minuta(t)]
        _ach43 = (l43_achados([t for t, _em, _p, _rs in textos], _adm_dados, _adm_arquivo)
                  if _adm_dados is not None else [])
        if _ach43 and l43_capa_de_outra_peca(_capa43):
            avisos.append(
                f"L43 NÃO MEDIDO: o checklist de admissibilidade ({_adm_arquivo}) é de recurso "
                f"especial, e a capa desta peça é de outra (contrarrazões, agravo ou resposta). O "
                f"tópico de relevância é do recurso especial, não desta peça; se o checklist é do "
                f"recurso adversário ou do de origem, deixe-o fora da pasta da peça.")
        elif _adm_dados is not None:
            for _nivel, _msg in _ach43:
                (erros if _nivel == "ERRO" else avisos).append(_msg)
        elif not _adm_achou:
            if l43_capa_de_resp(_capa43):
                avisos.append(
                    f"L43 NÃO MEDIDO: a capa fala em recurso especial e não há a entrada do "
                    f"checklist de admissibilidade ({L43_ARQUIVO} ao lado da peça ou na pasta do "
                    f"caso, ou --admissibilidade). Sem ela o linter não sabe a data do acórdão "
                    f"recorrido e não confere o tópico de relevância (CPC, art. 1.035-A).")
    elif adm_arg:
        avisos.append("L43 não roda com --fragmento (o tópico pode estar noutro capítulo): "
                      "--admissibilidade ignorado")


    _det = _l44_detector()
    if _det is None:
        avisos.append("L44 NÃO MEDIDO: o detector de trecho dirigido a IA (detectar_injecao.py, "
                      "da ingestão) não está ao lado do linter nem na pasta da ingestão")
    else:
        for _nivel, _msg in l44_achados([(t, em or _l44_paragrafo_de_citacao(_p))
                                         for t, em, _p, _rs in textos], _det):
            (erros if _nivel == "ERRO" else avisos).append(_msg)


    _inaugural45 = False
    if not ajuiz_arg and not fragmento:
        _fim_capa45 = inicio_corpo if inicio_corpo_achado else min(len(textos), _L42_CAPA_MAX + 6)
        _inaugural45 = not l42_processos_em_curso(
            [t for t, _em, _p, _rs in textos[:_fim_capa45]], processos_arg)
    for _nivel, _msg in l45_achados([t for t, _em, _p, _rs in textos], ajuiz_arg, _inaugural45):
        avisos.append(_msg)




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


    if relatorio is not None:
        relatorio.update({
            "formato": 1, "peca": caminho, "fragmento": bool(fragmento),
            "veredito": "REPROVADO" if erros else ("MINUTA" if pendencias else "APROVADO"),
            "exit_code": 1 if erros else (3 if pendencias else 0),
            "erros": [classificar_achado(e) for e in erros],
            "pendencias": [classificar_achado(p) for p in pendencias],
            "avisos": list(avisos),
            "resumo": resumo_de_naturezas(erros),


            "dispensas": {"travessao": bool(_disp.get("pular_l21")),
                          "regra_dos_tres": "J08" in _disp.get("excluir", set()),
                          "aspas_curvas": "J21" in _disp.get("excluir", set())},
        })

    def _imprime(prefixo, achado_txt):
        print(f"{prefixo}: {achado_txt}")
        a = classificar_achado(achado_txt)
        if a["natureza"] == "registro":
            print(_linha_de_registro(a))

    if erros:
        print(f"\n== REPROVADO == ({len(erros)} erro(s) de ESTRUTURA"
              + (f" · {len(pendencias)} pendência(s) de conferência" if pendencias else "")
              + ")")
        _res = resumo_de_naturezas(erros)
        if _res["erros_registro"]:
            print(f"Destes, {_res['erros_registro']} são de REGISTRO e {_res['erros_texto']} de "
                  f"TEXTO: o de registro não se resolve reescrevendo a peça; o que falta "
                  f"registrar e como vem logo abaixo de cada um.")
        for e in erros:
            _imprime("ERRO", e)
        for p in pendencias:
            _imprime("PENDENTE", p)
        return 1
    if pendencias:
        print(f"\n== MINUTA == ({len(pendencias)} julgado(s)/marcação(ões) a atestar; "
              f"ESTRUTURA LIMPA — L1–L45"
              + ("" if fragmento else " + F1/F2") + sufixo_cruz + ")")
        for p in pendencias:
            _imprime("PENDENTE", p)
        print("A forma está correta; falta conferir na fonte oficial o que está PENDENTE. "
              "Minuta NÃO se protocola: só o APROVADO (exit 0) libera.")
        return 3
    print("== APROVADO == (L1–L45" + ("" if fragmento else " + F1/F2") + " limpos"
          + sufixo_cruz + ")")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
