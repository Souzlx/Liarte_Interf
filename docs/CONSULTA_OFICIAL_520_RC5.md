# Consulta oficial — 5.2.0-rc.5

Esta revisão concentra as alterações na aquisição e reutilização dos dados.
Interface, filtros comerciais, geradores, catálogo e módulo de estoque seguem
o fluxo anterior. A entrega é candidata: a homologação externa completa ainda
está impedida pelos erros registrados abaixo.

## O que a pesquisa confirmou

A documentação oficial da API informa limites de duração e de quantidade de
linhas e recomenda os dados abertos para consultas grandes. O MDIC identifica
os CSV como a base que alimenta o Comex Stat e publica arquivos de totais para
conferência. Isso permite obter uma vez e consultar localmente vários períodos.

Fontes primárias consultadas em 22/10/2026:

- [Contrato OpenAPI do Comex Stat](https://api-comexstat.mdic.gov.br/docs/doc.yaml).
- [Dados abertos, layouts, tabelas e totais](https://www.gov.br/mdic/pt-br/assuntos/comercio-exterior/estatisticas/base-de-dados-bruta).
- [Lançamento da API, frete, seguro e CIF](https://www.gov.br/mdic/pt-br/assuntos/comercio-exterior/estatisticas/informativos/informativo-2024-086).
- [HTTP 429](https://www.rfc-editor.org/rfc/rfc6585.html#section-4).
- [Retry-After](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3).

Não foi encontrada, nessas fontes, uma cota numérica pública que permita
atribuir a recusa observada a IP, computador ou usuário. Regras do Siscomex,
Duimp ou Integra Comex não são regras desta API estatística.

## Aquisição

1. Confirmar publicação e cobertura separadamente para a base geral e municipal.
2. Tentar os arquivos anuais oficiais e as tabelas auxiliares, com reutilização
   condicional por ETag/Last-Modified, integridade SHA-256 e revisão de publicação.
3. Ler o arquivo anual por inteiro, mantendo em memória somente as agregações do
   catálogo e os controles. Os demais produtos participam da conferência nacional.
4. Conciliar os meses e os totais nacionais de FOB e kg; também frete, seguro e
   contagem de registros quando presentes no arquivo oficial de conferência.
5. Conciliar o detalhamento com outro acumulador dos registros brutos por
   produto/mês. A consulta de controle não é derivada das linhas exibidas.
6. Gravar o índice somente após a conferência completa. Gerar a consulta do
   período a partir desse índice. A origem CSV é preservada na auditoria.
7. Se arquivos não estiverem disponíveis ou não passarem na conferência, usar a
   API oficial, preservando a consulta independente de totais por produto/mês.
8. Publicar um novo snapshot somente após ambas as bases completas e conferidas.

Uma falha de rede não autoriza preencher métricas ausentes com zero, publicar
um período parcial, misturar general/municipal ou usar uma cópia antiga como se
fosse uma consulta nova. A última consulta válida aberta permanece preservada.

A abrangência municipal segue SH4 e domicílio fiscal. Ela não permite atribuir
municípios aos NCMs da base geral, obter frete/CIF municipal ou identificar
pedidos individuais. As duas bases não são somadas.

## Concorrência e retomada

- Uma fila na central atende trabalhos de clientes diferentes; requisições
  idênticas em andamento compartilham o mesmo resultado.
- A base anual serve períodos e produtos diferentes sem um novo download.
- Respostas completas do detalhamento permanecem em cache por até 24 h quando
  vinculadas à revisão publicada. Uma falha na conferência não exige descartar
  esse download. Isso não é permissão para exportar antes da conciliação.
- Revisão e dimensões integram as chaves. Uma nova publicação revalida também
  tabelas auxiliares e controles, mesmo dentro do prazo de cache. Atualização
  forçada revalida todos os recursos e ignora respostas concluídas em cache.
- O padrão mínimo entre chamadas à API passa a 65 s, medido depois da resposta.
  É uma política conservadora local, não uma promessa de aceitação pela origem.
- Até três tentativas; Retry-After permanece soberano. Sem cabeçalho, a mensagem
  genérica de 10 s recebe recuo mínimo de 60/120/240 s. Não há laço infinito.
- A pausa da API não impede leitura dos arquivos oficiais. O servidor de arquivos
  possui uma pausa mínima de 60 s após falha, respeitando também Retry-After
  quando recebido, independente da pausa da API.
- Travas de download são liberadas pelo sistema operacional após a morte do
  processo. Temporários, cancelamento e substituições preservam dados válidos.
- Downloads limitados a 3 GiB por arquivo/20 min; índices até 128 MiB e 500 mil
  agregações por ano. Exceder limites resulta em erro, nunca truncamento.

O modo automático padrão compartilha recursos no mesmo perfil/computador.
Para PCs diferentes, a central deve ser executada em um único servidor/host,
com o pareamento já disponível em Preferências. Não se compartilha SQLite por
SMB, não se descobre um servidor por adivinhação e não se divulga a chave na rede.
A implantação da central na infraestrutura da LIARTE não foi feita neste teste.

## Testes e resultado externo

As suítes sem rede incluem dez clientes por HTTP local, deduplicação, publicação
consistente, cache, revisão, retomada, corrupção, encerramento, precisão e os
geradores Excel/PDF/Power BI. As massas CSV são sintéticas e identificadas como
tal; não substituem os arquivos reais do MDIC.

No teste externo, o detalhamento de 35 NCMs em janeiro–setembro/2026 foi entregue:
7.789 linhas gerais. A chamada seguinte, de controle, recebeu HTTP 429. Uma nova
tentativa completa, com intervalo de 65 s e recuos limitados, continuou recebendo
429. Não foi publicado relatório a partir desse detalhamento isolado.

O servidor `balanca.mdic.gov.br` também não pôde ser alcançado para os CSV nesta
rede de teste: a conexão retornou HTTP 503 com erro de conexão ao upstream.
O domínio oficial anterior, `balanca.economia.gov.br`, apresentou a mesma falha
na verificação de conectividade. Ele não é usado como rotação de acesso.

Logo, a nova aquisição CSV ainda precisa de homologação com os arquivos reais
quando acessíveis. Os testes internos aprovados não permitem declarar o período
completo funcional na fonte real nem garantem disponibilidade futura do serviço.
Os registros exatos e as durações ficam nas evidências incluídas nesta entrega.

## Atualização

Extraia o ZIP completo. Para testar os fontes, abra `INICIAR_DESKTOP.cmd` na
nova pasta. O ZIP não contém um Setup Windows já compilado: um atalho para um
executável antigo continuará abrindo aquela instalação até a TI recompilar e
atualizar o Setup pelo fluxo existente. Preferências, relatórios, estoque e
identidades de instalação permanecem preservados.

Testes Qt em Linux/offscreen e a compilação do wheel não substituem homologação
do instalador, atalhos, DPAPI, bloqueios de arquivo e GPU/DPI em Windows.
