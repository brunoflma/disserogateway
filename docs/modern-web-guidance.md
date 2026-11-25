# Modern Web Guidance e as superfícies do Dissero

## Separação de responsabilidades

Este repositório distribui o plugin pelo catálogo do Claude. A referência
[Modern Web Guidance](https://developer.chrome.com/docs/modern-web-guidance) é
consultiva para manutenção de páginas e instruções; não é uma nova capacidade
jurídica, dependência ou requisito de instalação do plugin.

- **Site público e `/setup`**: a alteração deve ocorrer no checkout que realmente
  contém a fonte e o pipeline da página, depois de confirmar essa origem. Não
  reconstrua a página a partir de HTML publicado nem presuma que este catálogo é
  seu backend. Esta adoção não atesta acesso a esse checkout ou publicação.
- **DisseroHub**: aplicativo local independente no repositório
  [disserohub](https://github.com/brunoflma/disserohub), com seu próprio fluxo de
  desenvolvimento. O hub público do ecossistema não é esse aplicativo.
- **Plugin e gateway**: preserve pacote, assinatura, permissões, licença e OAuth.
  Os guias web não substituem testes desses contratos.

## Padrão de revisão para o site e guia de instalação

Use **Baseline Widely Available** como meta inicial; verifique compatibilidade
com a matriz efetiva e ofereça alternativa funcional a recursos mais recentes.
Consulte apenas os guias pertinentes, sem refatoração automática ou mudança do
visual aprovado. A [instalação oficial opcional](https://developer.chrome.com/docs/modern-web-guidance/get-started)
exige revisão prévia de pacote, versão e escopo: esta referência não instala
skills, não executa `npx @latest` e não habilita ferramenta global ou gate de CI.

Antes de qualquer mudança de interface, registre:

| Entrada | Verificação com dados sintéticos |
| --- | --- |
| Landing e convite | Teclado, labels, autofill e erro associado ao campo; carregamento legível; retomada distinguível de novo convite; nunca enviar um cadastro real durante teste visual. |
| `/setup` | Ordem dos quatro passos compreensível; comando e catálogo intactos; ação de copiar anuncia resultado. Simular área de transferência bloqueada e conferir seleção/cópia manual. |
| Retomada | Convite confirmado, plugin instalado e conta conectada aparecem como estados distintos; não confundir interface concluída com licença concedida. |
| Layout | Janela de 360 px e zoom de 200%; foco visível; nenhum botão encoberto; contraste e preferência por menos movimento. |
| Navegadores | Chrome/Edge e Firefox no Windows; Safari no iPhone e Chrome no Android quando disponíveis. Identificar emulação e aparelhos reais separadamente. |

Não execute comandos de instalação copiados, login, envio de convite ou mudança
de licença só para verificar a página. Não use documentos de clientes, tokens,
cookies ou nomes reais em capturas. Depois de confirmar o checkout responsável,
use a prévia local e seus testes existentes; preserve as proteções de conteúdo e
assinatura. Relate versão do navegador, cenário, resultado e itens pendentes.

A adoção é documental e não afirma que a navegação ou acessibilidade passaram.
Não foram alterados o site em produção, a distribuição, dependências nem CI.
