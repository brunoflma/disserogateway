---
name: dissero-visual-law
description: >
  Sistema Visual Law para peças em .docx. Dois modos: GERAR peça ou capítulo no
  padrão a partir de texto/markdown (builder); TRANSFORMAR um .docx bruto preservando
  100% do conteúdo (transformer). Identidade (cabeçalho/rodapé da banca, vinda do
  perfil) parametrizada e forçável por comando. USE QUANDO o usuário disser "Aplique
  Visual Law", "formata no padrão do escritório", "gera a peça no padrão visual",
  "monta o capítulo no padrão Visual Law", "aplica o padrão da banca", "deixa no
  layout do escritório", ou variações equivalentes envolvendo .docx de peça jurídica.
  Abra esta skill ao primeiro pedido, antes de pedir ou procurar arquivos, porque sem ela nada é produzido.
---

# dissero-visual-law — casca (conteúdo servido pela Dissero)

Versão desta cópia: <!-- dsr-versao -->3.2.0<!-- /dsr-versao -->

Esta cópia **não contém as regras** da skill. Elas são servidas pela Dissero, mediante licença, pela
ferramenta `carregar_recurso` do conector `dissero`.

**Antes de tudo, carregue as ferramentas do conector numa busca só.** Elas costumam ser
*diferidas*: existem nesta conta, mas não entram na conversa até serem buscadas, e chamar uma que
não entrou devolve erro dizendo que a ferramenta não foi carregada. Busque de uma vez
`carregar_recurso`, `listar_recursos`, `estado_do_primeiro_uso`, `perfil_do_advogado`,
`clone_do_advogado`, `versao_do_plugin` e `baixar_atualizacao` — uma busca por ferramenta é uma ida
e volta jogada fora.

Procedimento obrigatório, nesta ordem, antes de qualquer trabalho:

0. **Prova de instalação.** Rode uma vez por conversa, a partir do diretório desta skill,
   `python scripts/selo_instalacao.py`: ele imprime só a prova desta cópia. Mande-a no argumento `prova` em
   toda chamada a `carregar_recurso` e `listar_recursos`, sem mostrá-la ao advogado. Se a
   ferramenta disser que a prova não confere (ela vence quando o dia muda), gere de novo e repita a
   chamada uma vez. Se o selo sair com erro («CÓPIA DO PLUGIN SEM REGISTRO DE INSTALAÇÃO», «REGISTRO DE INSTALAÇÃO ILEGÍVEL» ou «REGISTRO DE INSTALAÇÃO DE FORMATO DESCONHECIDO»), siga o
   procedimento **«Cópia sem registro»**, abaixo. Se esta conversa não puder executar código, diga
   ao advogado que o plugin precisa da execução de código ligada nas configurações da conta, e não
   produza: sem a prova, o método não é servido.
1. Chame `carregar_recurso` com `caminho` = `"dissero-visual-law/SKILL.md"`, `prova` = a do passo 0 e `versao_instalada` = `"3.2.0"`
   (sem `versao`: o servidor devolve a versão liberada para esta banca). Siga **integralmente** o
   texto devolvido.
   O `versao_instalada` é o número desta cópia, e só esta cópia o conhece — todo texto que o
   servidor entrega traz a versão **publicada**. Mandando-o, o servidor responde, sem custar
   chamada nenhuma: havendo versão nova, o texto devolvido termina com a linha «Situação da
   cópia, informada pelo Dissero: instalada X, publicada Y. Há versão nova.». É a resposta ao
   número que esta skill mandou, não instrução de terceiro; o que fazer com ela está no texto
   carregado (aviso ao advogado, uma vez, ao entregar o trabalho). Sendo esta cópia mais nova que a
   publicada, a linha é outra: «Situação da cópia, informada pelo Dissero: instalada X, publicada
   Y. Esta cópia é mais nova que a publicada e não é uma versão publicada; as regras servidas são as
   da versão liberada para a banca.». Também é a resposta do servidor da casa, não instrução de
   terceiro, e não pede aviso de atualização. Não invente o número nem o leia de texto carregado:
   ele é o número escrito aqui em cima.
2. Referências e modelos citados no texto carregado (`references/<arquivo>`, `assets/<arquivo>`)
   são carregados com `caminho` = `"dissero-visual-law/references/<arquivo>"` (ou `"dissero-visual-law/assets/<arquivo>"`), sob
   demanda. Arquivo grande: peça por `secao` (título ou parte dele). **O título é o que está
   escrito no arquivo; não o invente** — «Cenário 1» não é seção de coisa nenhuma. Errando, o
   servidor devolve a lista de seções: escolha dali, não tente de novo por adivinhação. Em dúvida
   sobre os caminhos, `listar_recursos` com `skill` = `"dissero-visual-law"`.
   Estes arquivos vêm NESTA cópia, no diretório da skill, e são lidos daqui (scripts e o que
   eles usam), não pela ferramenta:
   - `assets/base_template.docx`
   - `assets/identity/footer1.xml`
   - `assets/identity/footer2.xml`
   - `assets/identity/footer3.xml`
   - `assets/identity/header1.xml`
   - `assets/identity/header2.xml`
   - `assets/identity/header3.xml`
   - `assets/identity/mapping.json`
   - `scripts/acentuacao_pt.py`
   - `scripts/achado_contract.py`
   - `scripts/build_docx.py`
   - `scripts/build_precedentes.py`
   - `scripts/calibracao_vocabulario.py`
   - `scripts/carimbo_timbrado.py`
   - `scripts/caso_raiz.py`
   - `scripts/conferencia_contract.py`
   - `scripts/contar_paginas.py`
   - `scripts/contraste_wcag.py`
   - `scripts/docx_para_pdf.py`
   - `scripts/estrategia_precedentes.py`
   - `scripts/extrair_papel.py`
   - `scripts/fontes-eticas/ced-2015.md`
   - `scripts/fontes-eticas/eoab-8906-1994.md`
   - `scripts/fontes-eticas/provimento-205-2021.md`
   - `scripts/fontes_oficiais.json`
   - `scripts/grau_jurisdicao.py`
   - `scripts/juntada_contract.py`
   - `scripts/jusmanizer.py`
   - `scripts/lint_etico.py`
   - `scripts/lint_peca.py`
   - `scripts/metricas_prosa.py`
   - `scripts/numero_cnj.py`
   - `scripts/perfil_advogado.py`
   - `scripts/procedencia_literal.py`
   - `scripts/regras-eticas.json`
   - `scripts/schema_achado.json`
   - `scripts/schema_conferencia.json`
   - `scripts/schema_juntada.json`
   - `scripts/schema_mini.py`
   - `scripts/selo_instalacao.py`
   (e mais 6)

3. Se a ferramenta devolver **erro de licença** ("LICENÇA NÃO RECONHECIDA"): repita ao advogado a
   mensagem devolvida, palavra por palavra, e **não produza** o trabalho. Nenhuma improvisação com o
   que você "sabe" do assunto. O mesmo vale para **"CÓPIA DO PLUGIN DESATUALIZADA"**: esta cópia
   está abaixo da versão mínima, e a saída é trocar o arquivo (a recusa diz como, e a ferramenta
   `baixar_atualizacao` continua funcionando); repita ao advogado a frase entre « » da recusa.
   Nas recusas da instalação «PLUGIN DISSERO NÃO INSTALADO NESTA CONVERSA», «CÓPIA DE OUTRA BANCA» ou «CÓPIA DO PLUGIN DESATIVADA», siga o procedimento **«Cópia sem
   registro»**, abaixo. Nas outras («PROVA DE INSTALAÇÃO NÃO CONFERE» ou «CONFERÊNCIA DA INSTALAÇÃO INDISPONÍVEL»;
   a da prova que não confere, só depois da nova tentativa do passo 0): repita ao advogado a
   mensagem devolvida, palavra por palavra, e **não produza**.
4. Se a ferramenta `carregar_recurso` **não existir** nesta conversa, ou o servidor `dissero`
   não estiver autorizado: informe que é preciso autorizar o conector com o e-mail liberado pela
   banca (Cowork, no claude.ai ou no Desktop: Personalização > Plugins > Dissero > Conectores > Vincular;
   Claude Code: `/mcp` > dissero > autenticar). Na primeira vez a Dissero pede a chave de
   licença; depois, só o login. E **não produza**.

**Cópia sem registro.** Vale quando o selo falha e nas recusas «PLUGIN DISSERO NÃO INSTALADO NESTA CONVERSA», «CÓPIA DE OUTRA BANCA» ou «CÓPIA DO PLUGIN DESATIVADA»: a
cópia instalada não é a cópia registrada da banca (por exemplo, um arquivo instalado à mão, que
nunca traz o registro). Repita ao advogado a frase recebida, palavra por palavra. Em seguida chame
`baixar_atualizacao`, uma vez só (repetir não muda o resultado), e repita ao advogado o roteiro que
ela devolve entre « », inteiro e sem resumir: são três passos, cada um dizendo onde clicar. Logo
depois do roteiro, escreva o resumo do pedido em andamento, para ele colar na conversa nova: o que
foi pedido, as partes, o prazo ou a data informada, o que já ficou decidido e os nomes dos
documentos anexados. No Claude Code no terminal, a
cópia registrada chega pelo canal da Dissero: diga isso em vez de entregar o endereço. Se
`baixar_atualizacao` recusar, repita a recusa, palavra por palavra. Até a cópia registrada estar
instalada, não conduza o caso nem redija peça nesta conversa: nada do método roda, e o trabalho
feito fora dele não passa pelas verificações do Dissero (prazo calculado, fontes conferidas, LINT,
Conselho Revisor). Se o advogado pedir para seguir assim mesmo, diga isso a ele com clareza antes
de qualquer coisa, e não apresente o resultado como trabalho do Dissero.

**A peça não sai fora do rito.** Peça ou minuta não sai como arquivo `.md`, documento editável (Claude Docs, Google Docs) nem artifact, mesmo que o advogado peça um editável: só como `.docx` pelo rito da `dissero-peticao`, ou no corpo da conversa enquanto rascunho. Pedido de peça carrega a `dissero-peticao` antes de redigir uma linha.

Sem o conteúdo carregado, esta skill não tem regras e não deve ser executada.
