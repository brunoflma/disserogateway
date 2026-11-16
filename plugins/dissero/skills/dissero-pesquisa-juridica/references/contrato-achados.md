# Contrato `dsr.achados` — estratégia de precedentes

Referência da `dissero-pesquisa-juridica`, carregada ao gravar a `estrategia` do `achados.json`
(SKILL.md, §6.1), e ao ligar o literal à extração (§2). As regras obrigatórias estão resumidas
no SKILL.md; aqui ficam os estados, os campos e os níveis por inteiro.

## §1. Estratégia

É o que faz da Relação de Precedentes um memorando de pesquisa, e não uma lista de julgados.
São duas regras:

- **Todo registro v3 leva `estrategia` na raiz**, com `pesquisa_contraria` e
  `cobertura_precedente` obrigatórios:
  - **`pesquisa_contraria`**: estado `nao_iniciada`, `concluida_sem_achado`,
    `concluida_com_achado` ou `bloqueada`, além das consultas, fontes, datas e IDs
    localizados. Precedente selecionado exige a pesquisa concluída, e
    `concluida_com_achado` exige ao menos um desses IDs com `estrategia_uso.posicao`
    igual a `contrario`.
  - **`cobertura_precedente`**: `confirmada`, `substituivel`, `forcada` ou
    `inexistente`, com data da revisão e data até a qual a cobertura deve ser
    novamente conferida. Cobertura vencida falha fechada. Cobertura forçada exige
    fundamentação analógica explícita; substituível aponta em
    `autoridade_substituta_ids` (lista sempre presente no v3) os IDs das autoridades
    alternativas confirmadas. O linter barra linguagem de certeza incompatível e nunca
    imprime esses nomes de estado na peça.
- **Quando a pesquisa tiver conclusão, preencha os dois campos abaixo**, `estrategia` e
  `estrategia_uso`:
  - na **`estrategia`**, acrescente `tese_central` em prosa, `distinguishing` (lista, na
    ordem em que a peça usará os passos) e `contrarios` (como a peça enfrenta os
    julgados desfavoráveis que você mesmo listou). Viram o parecer de abertura da
    Relação.
  - **`estrategia_uso`** (por achado; opcional no schema e obrigatório nesta skill quando
    há conclusão): objeto `{"posicao": "...", "como_usar": "..."}`, nunca string; o
    schema recusa a string. `posicao` é `favoravel`, `contrario`, `principiologico` ou
    `suporte_fatico`; `como_usar` diz, em uma ou duas frases, onde o precedente entra,
    com que ressalva e que distinguishing exige. Descreva o lugar pelo assunto ("no
    capítulo da via eleita"), não pelo número ("abre o item IV.1"): número de item fica
    obsoleto em silêncio quando a peça é renumerada, e o `validar_achados.py` emite
    AVISO quando encontra a forma numérica. Precedente **contrário** entra na Relação de
    propósito: julgado que sustenta a tese do juízo *a quo* precisa ser ENFRENTADO na
    peça, não descoberto pelo relator.

## §2. Procedência do literal

O `atestar_literal.py` liga o `syllabus_literal` a uma extração da fonte e grava
`procedencia_literal` (SKILL.md, §4, Teor e literalidade). Os níveis:

| Nível | Significa | No `validar_achados.py` |
|---|---|---|
| `verbatim` | substring exata, tolerando só espaço em branco e hifenização de fim de linha do extrator | passa |
| `normalizado` | só bate apagando acento e pontuação — **eles foram alterados** | **violação** |
| `ausente` | não ligado a extração alguma | violação em `allowed` selecionado; aviso em `pending` |

Havendo qualquer divergência, **nada é gravado**: gravar parte deixaria o dataset com uns
achados atestados e outros não. A mensagem nomeia a palavra: *"o tribunal escreveu
«recurso» e o texto diz «recursos»"*. O script não usa OCR, porque OCR adivinha
caractere: PDF só-imagem é recusado; obtenha a versão pesquisável ou copie o trecho da
tela. Editar a ementa depois de atestada invalida a procedência (o registro guarda o hash
do próprio literal).

## §3. Identificação do julgado (`citation`)

Preencha a moldura que a fonte devolver: `court`, `orgao_julgador` (turma, câmara, seção ou
plenário, como o tribunal o nomeia: «Terceira Turma»), `case_number`, `rapporteur` e
`judgment_date`. O `orgao_julgador` é opcional no schema (registro anterior continua válido),
mas, se a fonte o traz, grave-o: sem ele a Relação de Precedentes marca a lacuna para
conferência, e a folha de conferência o pede entre o tribunal e o relator. Não o deduza do
relator nem da classe: o que a fonte não disse fica nulo.
