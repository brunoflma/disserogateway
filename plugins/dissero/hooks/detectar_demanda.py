#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'detectar_demanda.py — Classificador de demanda jurídica (UserPromptSubmit, Dissero).'





























import sys, os, json, re, unicodedata

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass




DET = r"(?:(?:a|o|as|os|um|uma|uns|umas|ao|aos|na|no|nessa|nesse|numa|num|"
DET += r"esse|essa|este|esta|aquele|aquela|aquilo|isso|meu|minha|meus|minhas|"
DET += r"nosso|nossa|seu|sua|dele|dela|de|da|do|toda|todo)\s+){0,3}"



V_PRODUZIR = (r"redig|redij|escrev|escrit|elabor|minut|prepar|produz|formul|"
              r"rascunh|monta|montar|montei|mont[ae]r|faz|fazer|faca|fez|"
              r"cri[ae]|criar|gera|gerar|desenvolv|construir|constro|"
              r"ajuiz|propor|propoe|propon|proponha|impetr|interpo|interpor|oferec|"
              r"peticion|protocol|distribu|dar entrada|entrar com|bater|manda|"
              r"me (?:da|de|monta|faz|prepar)|quero|queria|preciso de|precisamos de|"
              r"vamos|vou|temos que|tenho que|pode (?:fazer|redigir|montar|preparar)")


O_PECA = (r"peca|pecas|peticao|peticoes|inicial|iniciais|exordial|contestac|contesta|"
          r"defesa|defesas|recurso|recursos|apelac|apela|agravo|embargo|"
          r"impugnac|impugna|replica|treplica|reconvenc|manifestac|"
          r"raz[oo]es|contrarraz[oo]es|contra-?razoes|alegac[oo]es finais|memoriais|"
          r"mandado de seguranca|habeas corpus|habeas data|mandado de injuncao|"
          r"acao|acoes|demanda judicial|processo novo|denuncia|queixa-?crime|"
          r"resposta a acusacao|alegacoes|cumprimento de sentenca|execuc|"
          r"exceca|incidente|reclamac|tutela|liminar|cautelar|monitoria|despejo|"
          r"consignac|usucapiao|inventario|divorcio|alimentos|interdit|"

          r"recurso especial|recurso extraordinario|recurso ordinario|recurso inominado|"
          r"agravo interno|agravo regimental|agravo em recurso|contramin|"
          r"rescisoria|possessoria|reintegracao de posse|manutencao de posse|"
          r"obrigacao de fazer|obrigacao de nao fazer|revisional|renovatoria|"
          r"indenizatoria|arrolamento|adjudicac|imissao (?:na|de) posse|"
          r"busca e apreensao|prestacao de contas|dissolucao|arrematacao|"
          r"alvara|sobrestamento|desconsideracao|embargos de terceiro|"
          r"acao de cobranca|acao anulatoria|acao declaratoria|acao revisional")


V_PESQUISAR = (r"pesquis|busc|procur|levant|encontr|ach[ae]|localiz|garimp|"
               r"consult|verific|confer|valid|checa|checar|conhec|"
               r"me (?:tras|traz|trag)|tem (?:algum|algo)|existe|ha (?:algum|julgado)|"
               r"mapea|compil|rastrei|rastrear|vasculh|sond|investig|apur|"
               r"reun|seleciona|junta|cita|fundamenta|embas|respald|sustent")


O_JURIS = (r"jurisprudenc|precedent|sumula|sumulas|julgado|acordao|acordaos|"
           r"tema repetitiv|repetitiv|repercussao geral|vinculante|"
           r"orientacao jurisprudencial|enunciado|informativo|ementa|"
           r"tese (?:fixada|firmada|juridica)|entendimento (?:do|dos|da)|"
           r"decis[oo]es (?:do|dos|da|sobre)|como (?:o |os )?(?:stj|stf|tst|tribunal)|"
           r"leading case|paradigma|recurso repetitivo|iac\b|irdr\b|"
           r"jurisprudencia (?:dominante|pacifica|consolidada|majoritaria)|"
           r"entendimento (?:atual|pacific|dominante|consolidad|majoritari)|"
           r"precedente (?:vinculante|qualificado)|posicao (?:do|da|dos) (?:stj|stf|tst|trib)|"
           r"como (?:vem |vem se )?(?:decidindo|julgando|entendendo)|"
           r"o que (?:diz|dizem) (?:o|os|a) (?:tribunal|tribunais|stj|stf)")


O_DECISAO = (r"sentenca|acordao|decisao|despacho|liminar|interlocutoria|"
             r"deferimento|indeferimento|julgamento|monocratica|"
             r"decisum|provimento|veredicto|dispositivo da sentenca")




INTENCAO = (r"preciso|precisamos|quero|queremos|queria|gostaria|pretendo|pretendemos|"
            r"vou|vamos|irei|iremos|tenho que|temos que|tenho de|preciso muito|"
            r"devo|devemos|decidi|decidimos|resolvi|resolvemos|combinei|fiquei de|"
            r"me ajuda a|me ajude a|preciso que|urgente|favor|por favor")







V_POSTULAR = (r"recorr|apel(?:ar|o|e|em|ando|aremos)|contest(?:ar|o|e|ando|aremos)|"
              r"impugn(?:ar|o|e|ando|aremos)|embarg(?:ar|o|ue|ando)|agrav(?:ar|o|e|ando)|"
              r"replic|reconv[ie]r|excepcion|defender|defende-?la|defende-?lo|"
              r"process(?:ar|o|e)|acion(?:ar|o|e)|demand(?:ar|o|e)|litig|"
              r"peticion|protocol|manifest(?:ar|o|e)|sustentar oralmente|"
              r"responder (?:a|ao|essa|esse|a acao|a acusacao)|rebater|refutar")

def _vo(verbos, objetos):
    'Verbo + (determinantes) + objeto, com até 3 palavras neutras de permeio'


    return r"(?:%s)\w*\s+(?:\w+\s+){0,2}%s(?:%s)" % (verbos, DET, objetos)


def _rx(*partes):
    return re.compile("|".join(partes))












RX_META = _rx(
    r"\.(?:py|sh|ps1|jsonl?|toml|ya?ml|cfg|ini)\b",
    r"skill\.md|handoff\.md|claude\.md|readme\.md|prompt-proximo-agente|plugin\.json",
    r"\bconv-\d|\bv\d+\.\d+\.\d+",
    r"lint_peca|rodar_evals|rodar_testes|validar_plugin|empacotar_plugin|"
    r"detectar_demanda|conselho_gate|conselho_sessao|build_precedentes|"
    r"verificar_citacao|validar_achados|sincronizar_shared|estado_peca",
    r"--[a-z][a-z-]{2,}",
    r"git (?:status|diff|commit|add|push|log|checkout|stash)|working tree|"
    r"\bcommit|\brepositori|\bbranch\b|\bmerge\b",
    r"\bassert|\bregex\b|\bsubprocess\b|\bstdout\b|\bstderr\b|\btraceback\b|"
    r"\bexit code\b|\bhooks?\b|\bsubagente|\beval\b|\bevals\b",
    r"verde falso|misroute|falso positivo",
)



M_VISUAL = ("[Dissero · detecção] Demanda de formatação: acione a skill dissero-visual-law "
            "diretamente. Modelo: Sonnet (formatação determinística).")
M_C2 = ("[Dissero · detecção] Cenário sugerido: 2 — Caso complexo multi-capítulo [RISCO]. "
        "Acione dissero-orquestrador → dissero-caso-complexo (sessão dedicada, um agente por "
        "capítulo em série). Modelo ideal: Opus (estratégia/capítulos) → Sonnet (redação).")
M_C8 = ("[Dissero · detecção] Cenário sugerido: 8 — Prazos [RISCO]. Acione dissero-orquestrador. "
        "Modelo: Sonnet (cálculo determinístico).")
M_C1 = ("[Dissero · detecção] Cenário sugerido: 1 — Peça nova [RISCO]. Acione dissero-orquestrador "
        "e conduza o intake completo antes de redigir. Modelo ideal: Opus (estratégia/mapa) "
        "→ Sonnet (redação).")



M_C3 = ("[Dissero · detecção] Cenário sugerido: 3 — Análise de decisão [RISCO]. Acione "
        "dissero-orquestrador. A leitura segue o roteiro «Decisão recebida» do método "
        "analise-autos: abre pelo RESULTADO, pedido por pedido, e pela ratio decidendi; "
        "viabilidade e redação seguem na dissero-peticao. Modelo ideal: Opus "
        "(análise/viabilidade) → Sonnet só se redigir.")
M_C4 = ("[Dissero · detecção] Cenário sugerido: 4 — Pesquisa de jurisprudência [RISCO]. Acione "
        "dissero-orquestrador; classificação CONFIRMADO/PARCIAL/NÃO CONFIRMADO obrigatória. "
        "Modelo ideal: Opus (confronto de tese) / Sonnet (compilação).")
M_C12 = ("[Dissero · detecção] Cenário sugerido: 12 — Contrato novo [RISCO]. Acione "
         "dissero-orquestrador (societário → fluxo DREI). Modelo: Sonnet (Opus se societário "
         "complexo).")
M_C14 = ("[Dissero · detecção] Cenário sugerido: 14 — Notificação extrajudicial [RISCO]. "
         "Acione dissero-orquestrador. Modelo: Sonnet.")
M_C10 = ("[Dissero · detecção] Cenário sugerido: 10 — Perícia [RISCO]. Acione dissero-orquestrador. "
         "Modelo ideal: Opus (quesitos/análise de laudo).")
M_C9 = ("[Dissero · detecção] Cenário sugerido: 9 — Audiência / sustentação oral. Acione "
        "dissero-orquestrador. Modelo ideal: Opus (estratégia) → Sonnet (roteiro).")
M_JUNT = ("[Dissero · detecção] Demanda de juntada documental. Acione dissero-orquestrador → "
          "dissero-juntada (nota (g) do catálogo de cenários): contador único por ORDEM DE 1ª "
          "CITAÇÃO e GUIA descritivo como autoridade. Modelo: Sonnet (curadoria "
          "determinística).")
M_GEN = ("[Dissero · detecção] Demanda jurídica genérica. Acione dissero-orquestrador para "
         "classificar e fazer o intake. O orquestrador indicará o modelo ideal após "
         "classificar.")
M_C27 = ("[Dissero · detecção] Cenário sugerido: 27 — Diligência cadastral / qualificação de "
         "parte. Acione dissero-orquestrador (references/diligencia-cadastral.md): rota "
         "GRATUITA `consultar_estabelecimento_cnpj_publico` primeiro; rota paga só com aval "
         "registrado (scripts/autorizar_cnpja.py). Divergência entre a fonte e os autos "
         "escala ao advogado. Modelo: Haiku/Sonnet (consulta determinística).")



M_CADASTRO = ("[Dissero · detecção] Identificador de pessoa jurídica no pedido. ANTES de "
              "qualificar a parte, redigir a peça ou aceitar o caso, rode a diligência "
              "cadastral (cenário 27, governança §2.9): a rota GRATUITA "
              "`consultar_estabelecimento_cnpj_publico` entrega razão social, natureza "
              "jurídica, sede, situação cadastral e quadro de sócios sem consumir crédito. "
              "Rota paga (comprovante em PDF, CCC, Simples/MEI, SUFRAMA, busca por nome) só "
              "com aval registrado por `scripts/autorizar_cnpja.py`. `[COMPLETAR]` só "
              "DEPOIS de a consulta falhar — e a falha se relata ao advogado.")
M_DOC = ("[Dissero · detecção] Documento detectado no pedido. Acione a skill dissero-ingestao ANTES "
         "de ler/analisar/redigir: a sonda decide a rota (Read nativo do Claude para texto e "
         "PDF curto; extração local para Word e PDF com camada de texto, inclusive sigiloso; "
         "o Eluxi, OCR da casa, para escaneado, tabelas ou volume). Ilegível ou baixa confiança de "
         "OCR → escalonar ao advogado; nunca improvisar teor. Modelo: Haiku/Sonnet (OCR/triagem).")



M_DOC_REMOTO = ("[Dissero · detecção] Documento detectado no pedido. Acione a skill dissero-ingestao "
                "ANTES de ler/analisar/redigir: a sonda decide a rota (Read nativo do Claude para "
                "texto e PDF curto; extração no ambiente da sessão para Word e PDF com camada de "
                "texto; o Eluxi, OCR da casa, para escaneado, tabelas ou volume). Esta sessão roda "
                "na nuvem: documento SIGILOSO não se processa aqui (a sonda escala, "
                "`sigiloso_em_nuvem`); indique o Cowork no Desktop ou o Claude Code no computador. "
                "Ilegível ou baixa confiança de OCR → escalonar ao advogado; nunca improvisar teor. "
                "Modelo: Haiku/Sonnet (OCR/triagem).")
RODAPE = (" O modelo indicado é recomendação (avisar e seguir): o plugin não troca o modelo "
          "da sessão — quem decide é o advogado (/model). A governança do plugin "
          "(references/governanca.md §8) se aplica.")













M_PREPARO = ("[Dissero · detecção] Preparo/custas no pedido: use "
             "`skills/dissero-peticao/scripts/preparo_recursal.py` em vez de calcular de "
             "cabeça. Ele monta a memória condicional (custas + porte + depósito) e NÃO "
             "traz valor embutido: tabela e guia vêm do tribunal competente, e o que "
             "faltar sai declarado como pendência, nunca estimado.")
M_COMPARAR = ("[Dissero · detecção] Conferência de cálculo alheio no pedido: use "
              "`skills/dissero-peticao/scripts/comparar_calculos.py`. Ele põe as memórias lado "
              "a lado em Decimal e casa rubrica só por identificador DECLARADO — o que não "
              "casar sai como divergência, não como zero. Auditar de cabeça é onde a "
              "diferença passa.")
M_MAPA = ("[Dissero · detecção] Mapa das peças no pedido: use "
          "`skills/dissero-ingestao/scripts/mapa_estrutural.py`. O intervalo de páginas é LIDO "
          "de dentro do identificador do tribunal, nunca contado — contagem erra em "
          "processo com numeração própria.")
M_FRONTEIRA = ("[Dissero · detecção] Separação de peças no pedido: use "
               "`skills/dissero-ingestao/scripts/fronteira_peca.py`. Ele PROPÕE onde uma peça "
               "acaba e outra começa, ancorado no identificador do tribunal, e devolve tudo "
               "como `a_confirmar` — quem confirma é o advogado, e é assim de propósito.")

FERRAMENTAS = (


    (re.compile(r"\bpreparo\b|\bdeserc|porte de remessa|deposito recursal|"
                r"\bcustas\b[^.]{0,60}(recurs|apelac|agravo|embarg)|"
                r"(recurs|apelac|agravo|embarg)[^.]{0,60}\bcustas\b"), M_PREPARO),


    (re.compile(r"(compar|confer|audit|impugn|refut|contest)\w*[^.]{0,40}"
                r"(calculo|memoria de calculo|planilha|conta d[ao])|"
                r"memoria de calculo|calculo (da|do) (perito|parte|exequente|contrari)|"
                r"divergenc\w*[^.]{0,30}calculo"), M_COMPARAR),
    (re.compile(r"mapa d\w+ peca|indice d\w+ (processo|autos)|estrutura d\w+ autos|"
                r"quais (as )?peca|que pecas (tem|ha|existem)|listar as pecas"), M_MAPA),
    (re.compile(r"onde (comeca|termina|acaba)\w*[^.]{0,20}peca|separar as pecas|"
                r"dividir[^.]{0,25}(pdf|autos)|fronteira d\w+ peca|"
                r"quebrar[^.]{0,20}(autos|pdf) em pecas"), M_FRONTEIRA),
)


RX_VISUAL = _rx(
    r"visual law",
    r"padr(?:ao|oes) (?:do escritorio|dissero|da banca|da casa|visual|nosso)",
    r"(?:no|nosso|do) (?:layout|padrao|formato) (?:do escritorio|dissero|da banca|da casa)",
    r"identidade (?:visual|do escritorio|dissero)",
    r"cabecalho (?:do escritorio|dissero|padrao)",






    _vo(r"formata|padroniz|diagram|estiliz|aplic|deix|coloc|arrum|ajust|"
        r"transform|converte|converter|reformata|embeleza",
        r"(?:visual law|padrao|layout|formatac|peca|capitulo|docx|documento|arquivo)"),
    r"template (?:do escritorio|dissero|da banca|padrao)|"
    r"modelo (?:do escritorio|dissero|da banca)|manual de estilo|"
    r"deixa (?:bonit|apresentav|profission)|"
    r"rodape (?:do escritorio|dissero|padrao)|papel timbrado|timbrado do escritorio",
)

RX_C2 = _rx(
    r"caso (?:grande|complexo|gigante|enorme|pesado|volumoso|extenso|monstro)",
    r"peca (?:grande|longa|extensa|gigante|enorme|monstruosa)",
    r"multi-?capitulo|varios capitulos|em capitulos|por capitulos|capitulo por capitulo",
    r"varias sess[oo]es|varias etapas|em etapas|por partes|aos poucos",
    _vo(r"mont|estrutur|divid|quebr|separ|organiz", r"(?:caso|peca|inicial) (?:em|por) capitulos"),
    _vo(r"mont|estrutur|arm", r"caso"),
    _vo(r"unific|consolid|junt|cost|reun|fech", r"(?:peca|capitulos)"),
    _vo(r"continu|retom|segu|volt", r"caso"),
)

RX_C8 = _rx(
    r"(?:calcul|cont|confer|verific|checa)\w*\s+" + DET + r"prazo",
    r"qual (?:e )?(?:o )?prazo|que prazo|quanto (?:tempo|prazo)",
    r"prazo (?:processual|recursal|fatal|final|em dobro|em curso)",
    r"prazo (?:pra|para|de|do|da) (?:apel|recorr|contest|embarg|agrav|recurso|"
    r"manifest|cumpri|pag|junt|impugn|responder|resposta|defesa|alegac)",
    r"tempestiv|intempestiv|preclus|perdi o prazo|perdeu o prazo|deixei passar",
    r"quando vence|vence quando|vencimento do prazo|fim do prazo|data limite|"
    r"prazo (?:vence|venceu|acaba|termina)",
    r"tenho ate quando|ate quando (?:tenho|posso|da|vai)|"
    r"quantos dias (?:tenho|temos|falta|restam|sobra|ainda|uteis)",
    r"dias uteis|contagem (?:do |de )?prazo|suspensao (?:do )?prazo|"
    r"feriado forense|recesso forense|suspensao dos prazos",
    r"intimacao publicada|fui intimado (?:hoje|ontem|na)|publicou (?:hoje|ontem)",
    r"tenho um prazo|tem um prazo|temos um prazo|prazo (?:correndo|apertado|curto)",


    r"prazo (?:pra|para) (?:interpor|protocolar|peticionar|apresentar|opor|falar|"
    r"emendar|sanear|especificar|recolher)",
    r"prazo (?:em dobro|dobrado|em quadruplo|diferenciado)|prerrogativa de prazo|"
    r"prazo (?:da|do) (?:fazenda|defensoria|mp|ministerio publico)",
    r"ainda (?:da|de) tempo|ja (?:passou|venceu|perdeu) o prazo|"
    r"quando (?:comeca|inicia|conta) o prazo|termo inicial do prazo|dies a quo",
)

RX_JUNTADA = _rx(
    r"juntada|junt(?:a|ar) (?:os |as )?documentos",
    _vo(r"organiz|monta|numer|cur|revis|confer|refaz|atualiz",
        r"(?:juntada|guia de documentos|relacao de documentos|tracker|numeracao)"),
    r"guia de documentos|relacao de documentos|tracker da juntada|"
    r"numera(?:r|cao) (?:d|os )?(?:os )?documentos|renumer",
    r"doc\. ?\d+ (?:esta|ficou|virou)|contador de documentos",
)


RX_C4_EXPLICITA = re.compile(_vo(V_PESQUISAR, O_JURIS))

RX_C1 = _rx(
    _vo(V_PRODUZIR, O_PECA),


    r"peticao inicial|mandado de seguranca|habeas corpus|recurso inominado|"
    r"tutela (?:de )?(?:urgencia|evidencia|provisoria|antecipada)|"
    r"alegac[oo]es finais|resposta a acusacao|queixa-?crime|contrarraz[oo]es",
    r"(?:entrar|dar entrada|ingressar) (?:com|na|no) " + DET + r"(?:acao|despejo|execuc|"
    r"processo|demanda|reclamac|monitoria|inventario|divorcio)",
    r"vou (?:processar|acionar|demandar)|quero (?:processar|acionar|demandar)|"
    r"processar (?:o|a|essa|esse|meu|minha)",
)





RX_C1_NOMINAL = _rx(
    r"contesta[cr]|impugnac|apelac|agravo de instrumento|embargos (?:de|a|infringentes)",
)










RX_C1_POSTULAR = re.compile(r"(?:%s)\s+(?:\w+\s+){0,2}(?:%s)\w*" % (INTENCAO, V_POSTULAR))

RX_C3 = _rx(
    _vo(r"analis|avali|examin|estud|le|ler|leia|interpret|resum|destrinch|"
        r"da uma olhada|olha|ve|vej", O_DECISAO),
    r"cabe (?:recurso|apelac|agravo|embargo)|cabe(?:ria)? (?:algum )?recurso",
    r"vale a pena recorrer|viabilidade recursal|chance de (?:reverter|exito|sucesso|ganhar)",
    r"da (?:pra|para) recorrer|tem como recorrer|"
    r"o que (?:essa|a|esse|o) (?:sentenca|decisao|acordao|despacho) (?:diz|decidiu|significa)",
    r"(?:perdemos|ganhamos|perdi|ganhei) (?:a acao|em primeira|o caso|essa)",

    r"julgou (?:improcedente|procedente|extinto|extinta)|"
    r"(?:foi |fomos )?(?:indeferid|negad|rejeitad|desprovid|improvid)|"
    r"(?:o juiz|o juizo|a juiza|o desembargador|o relator) (?:negou|indeferiu|extinguiu|"
    r"julgou|entendeu|decidiu)|"
    r"sentenca (?:contraria|desfavoravel|ruim|terminativa)|"
    r"extinguiu (?:o feito|o processo|sem resolucao)|"
    r"o que (?:eu )?faco (?:com|agora|nesse caso)|quais (?:as )?(?:minhas )?opcoes|"
    r"vale (?:a pena|apena) (?:o recurso|insistir|seguir)|risco de (?:perder|sucumbencia)",
)

RX_C4 = re.compile("|".join([O_JURIS, r"(?:stj|stf|tst) (?:entende|decidiu|firmou|fixou)"]))

RX_C12 = _rx(


    _vo(V_PRODUZIR + r"|revis|analis|confer|ajust",
        r"(?:minuta|contrato|distrato|acordo|termo|procuracao|estatuto|"
        r"contrato social|alteracao contratual)"),
    r"contrato (?:social|de \w+)|minuta contratual|distrato|"
    r"alteracao contratual|acordo extrajudicial|termo de \w+",
)

RX_C9 = _rx(
    _vo(r"prepar|organiz|monta|ensai|treinar|treina|simul",
        r"(?:audiencia|sustentacao|oitiva|depoimento|instrucao|inquiric)"),
    r"audiencia (?:de |una|previa|conciliac|instrucao|justificac)|preparar audiencia|"
    r"sustentacao oral|perguntas (?:para|pra) (?:a )?testemunha|"
    r"rol de testemunhas|contradita|acareacao|"
    r"(?:vou|tenho) audiencia|audiencia (?:amanha|semana|marcada|designada)",
)

RX_C14 = _rx(
    r"notificacao extrajudicial|constitui(?:r|cao) (?:em|de) mora|interpela",
    _vo(r"notific", r"(?:o |a )?(?:inquilino|devedor|cliente|locatario|reu|parte|extrajudicial)"),
    r"carta de cobranca|cobranca extrajudicial",
)

RX_C10 = _rx(
    r"quesito|laudo pericial|pericia|perit[oa]\b|assistente tecnico|parecer tecnico",
    _vo(r"impugn|contest|critic|analis", r"laudo"),
)

RX_GEN = _rx(
    r"preciso de ajuda|ajuda juridica|o que (?:faco|fazer|eu faco) com|me ajuda|me socorr",
    r"nao sei (?:como|o que|por onde)|por onde (?:comeco|comecar)|me da uma luz",
    r"tenho um problema (?:juridico|com|na)|"
    r"(?:o |a )?client[ea] (?:chegou|trouxe|me procurou|apareceu|ligou)",
    r"caso novo|demanda nova|analisa isso|analise isso|da uma olhada nisso|olha isso",
    r"me orienta|qual (?:e )?(?:a )?estrategia|como (?:devo )?proceder|"
    r"o que voce (?:sugere|recomenda|acha)|preciso de (?:uma )?(?:opiniao|orientacao)|"
    r"da uma forca|to perdido|estou perdido|surgiu (?:um|uma) (?:caso|demanda|questao)",
)






RX_CADERNO = _rx(
    r"notebook\s+(?:do|do caso|de|da)|caderno\s+(?:do|do caso|de|da)",
    _vo(r"consult|busc|embas|us|pergunt",
        r"(?:notebook|caderno)"),
    _vo(r"pergunt|consult",
        r"(?:o|ao|nesse|neste) (?:notebook|caderno)"),
)

M_CADERNO = ("[Dissero · detecção] Cenário sugerido: 25 — Estudo de autos no caderno [BAIXO]. "
             "O caderno do caso funciona pelo conector Fons: com ele conectado, a consulta é "
             "dele. A resposta é apoio não validado e não vai à peça sem conferência nos autos.")







RX_C27 = _rx(
    r"\bcnpj\b",
    r"razao social|nome empresarial|nome fantasia",
    r"situacao cadastral|ficha cadastral|cartao cnpj",
    r"quadro societario|quadro de socios|composicao societaria",
    r"comprovante (?:de inscricao|da receita|de situacao cadastral)",
    r"simples nacional|optante do simples|\bmei\b|suframa|inscricao estadual",
    r"quem s[ao]o os socios|quem e (?:o|a) (?:socio|socia|dono|dona)|"
    r"de quem e (?:a|essa) empresa",
    r"empresa (?:esta|ainda esta|continua|foi|ja foi)\s+(?:\w+\s+)?"
    r"(?:ativa|baixada|encerrada|dissolvida|inapta|suspensa)",
    r"(?:endereco|sede) (?:da|do|dessa|desse) "
    r"(?:empresa|sociedade|re|autora|requerida|executada)",
    r"grupo economico",
    _vo(r"consult|verific|confer|checa|busc|pesquis|levant|descobr|identific|valid",
        r"(?:cnpj|razao social|situacao cadastral|socios|sede da empresa|dados da empresa)"),
)


PRAZO_EXPLICITO = re.compile(
    r"(?:calcul|cont|confer|verific|checa|diz|informa|qual|que)\w*\s+(?:\w+\s+){0,3}prazo|"
    r"\bprazo (?:pra|para|de|do|da)\s+(?:\w+\s+){0,1}(?:apel|recorr|contest|embarg|agrav|"
    r"interpo|protocol|peticion|impugn|manifest|junt|cumpri|pag|respond|apresent|opor)|"
    r"quantos dias|ate quando|quando vence|tenho ate")

RAMOS = (
    (RX_VISUAL, M_VISUAL),
    (RX_C2, M_C2),
    (RX_C8, M_C8),
    (RX_C4_EXPLICITA, M_C4),
    (RX_JUNTADA, M_JUNT),
    (RX_C1, M_C1),
    (RX_C1_NOMINAL, M_C1),
    (RX_C1_POSTULAR, M_C1),
    (RX_C3, M_C3),
    (RX_C4, M_C4),
    (RX_C12, M_C12),
    (RX_C14, M_C14),
    (RX_C10, M_C10),
    (RX_C9, M_C9),
    (RX_C27, M_C27),
    (RX_CADERNO, M_CADERNO),
    (RX_GEN, M_GEN),
)





RAMOS_FRACOS = (RX_C4, RX_GEN, RX_C1_POSTULAR, RX_C1_NOMINAL, RX_C27, RX_CADERNO)

DOC_RX = re.compile(
    r"\.(pdf|docx?|docm|odt|rtf|pptx?|pptm|odp|xlsx?|xlsm|ods|png|jpe?g|tiff?|bmp|webp)"
    r"([^a-z0-9]|$)", re.I)









CADASTRO_RX = re.compile(
    r"\bcnpj\b|\d{2}\.?\d{3}\.?\d{3}/\d{4}-?\d{2}|\b\d{14}\b|\brazao social\b")


def normalizar(texto):
    'minúsculas + sem acento — o casamento não depende de locale nem de acentuação'

    t = (texto or "").lower()
    return "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))


def classificar(prompt):
    """Devolve a mensagem de cenário (str) ou "" — primeira regra da ORDEM que casar."""
    p = normalizar(prompt)
    if not p.strip():
        return ""






    tem_producao = re.search(_vo(V_PRODUZIR, O_PECA), p) is not None




    if PRAZO_EXPLICITO.search(p):
        tem_producao = False




    meta = RX_META.search(p) is not None
    for rx, msg in RAMOS:
        if tem_producao and rx in (RX_C8, RX_C4_EXPLICITA):
            continue
        if meta and rx in RAMOS_FRACOS:
            continue
        if rx.search(p):
            return msg
    return ""






PASTA_ROTEADOR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "skills", "dissero-orquestrador", "scripts")


def _superficie_remota_local(env=None):
    'Réplica da regra de `caso_raiz.superficie_remota` (a mesma do registro_falas), para cópia'


    env = os.environ if env is None else env
    remoto = str(env.get("CLAUDE_CODE_REMOTE") or "").strip().lower() in ("true", "1")
    entrada = str(env.get("CLAUDE_CODE_ENTRYPOINT") or "").strip().lower().startswith("remote")
    return remoto or entrada


def superficie_remota(env=None):
    'A sessão é remota (Cowork remoto do claude.ai, Claude Code na nuvem)? Usa a função única'


    try:
        pasta = os.path.dirname(os.path.abspath(__file__))
        if pasta not in sys.path:
            sys.path.insert(0, pasta)
        import caso_raiz
        f = getattr(caso_raiz, "superficie_remota", None)
        if callable(f):
            return bool(f(env) if env is not None else f())
    except Exception:
        pass
    try:
        return _superficie_remota_local(env)
    except Exception:
        return False


def _roteador():
    """Importa o roteador da dissero-orquestrador (exceção declarada em test_imports_do_pacote)."""
    if PASTA_ROTEADOR not in sys.path:
        sys.path.insert(0, PASTA_ROTEADOR)
    import rotear_area
    return rotear_area


def sugerir_area(prompt, cenario_casou=False):
    'Frase curta com a(s) área(s) sugerida(s) ou "". Só fala quando o cenário casou ou quando a'

    try:
        p = normalizar(prompt)
        if not p.strip() or RX_META.search(p):
            return ""
        ra = _roteador()
        perfil, _cam = ra.carregar_perfil()
        prefs, _av = ra.preferencias(perfil)
        mods, _inv = ra.carregar_modulos()
        cands, descartadas = ra.rotear(prompt, mods, prefs)
        cands = [c for c in cands if c["gatilhos"]]
        if not cands:
            return ""
        top = cands[0]
        forte = len(top["gatilhos"]) >= 2 and top["pontos"] >= 3
        if not (cenario_casou or forte or top["preferencia"] == "ligada"):
            return ""
        cen = []
        for c in top["cenarios_sugeridos"]:
            if c.get("casou") and c["cenario"] not in cen:
                cen.append(c["cenario"])
        partes = ["Área sugerida: %s (`%s`; gatilhos: %s)" % (
            top["nome"], top["area"], ", ".join(top["gatilhos"][:4]))]
        if cen:
            partes[0] += " → cenários do módulo: %s" % ", ".join(str(n) for n in cen[:3])
        if len(cands) > 1 and cands[1]["gatilhos"]:
            partes.append("Também: `%s`." % cands[1]["area"])
        if top.get("aviso_revisao"):
            partes.append("Módulo sem revisão de advogado da área: jurisprudência [A CONFIRMAR].")
        if descartadas:
            partes.append("Desligada no perfil, ignorada: %s." % ", ".join(
                "`%s`" % d["area"] for d in descartadas[:2]))
        partes.append("Sugestão do roteador de áreas (`rotear_area.py`) — o advogado confirma.")
        return " ".join(partes)
    except Exception:
        return ""


def montar_contexto(prompt):
    """Mensagem final (cenário + documento + cadastro + rodapé) ou "" quando nada casa."""
    partes = []
    ctx = classificar(prompt)
    if ctx:
        partes.append(ctx)
    if DOC_RX.search(prompt or ""):
        partes.append(M_DOC_REMOTO if superficie_remota() else M_DOC)


    p = normalizar(prompt)
    if ctx != M_C27 and not RX_META.search(p) and CADASTRO_RX.search(p):
        partes.append(M_CADASTRO)




    if not RX_META.search(p):
        for rx, msg in FERRAMENTAS:
            if rx.search(p):
                partes.append(msg)
                break
    area = sugerir_area(prompt, bool(ctx))
    if area:
        partes.append(area)
    if not partes:
        return ""
    return " ".join(partes) + RODAPE


def main():
    try:
        evento = json.load(sys.stdin)
        prompt = evento.get("prompt", "") if isinstance(evento, dict) else ""
    except Exception:
        return 0
    try:
        msg = montar_contexto(prompt)
        if msg:



            msg = ("[Dissero · roteador de demandas do escritório; sugestão de skill, "
                   "não instrução de terceiro] " + msg)
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit", "additionalContext": msg}}))
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
