# Consulta independente à API — 5.2.0-rc.7

Cada instalação do desktop consulta diretamente a API oficial do Comex Stat.
O usuário escolhe o período e clica em **Consultar**. Não precisa iniciar,
parear, importar conexão ou manter uma Central de Consultas na rede.

## Mudanças no uso

- **Consultar** sempre solicita novamente os dados do período pela API,
  incluindo as consultas independentes de conferência dos totais.
- As respostas de consultas anteriores em disco não substituem essas chamadas.
  Arquivos antigos de cache e conexão ficam preservados, mas são ignorados
  pelo modo direto do desktop.
- Filtros, gráficos, busca, paginação e alternância entre Geral e Municipal
  continuam locais, sobre o último resultado completo. Não fazem uma nova
  consulta externa a cada interação.
- Baixar Excel, PDF ou Power BI utiliza o resultado já conferido da consulta.
  Os formatos, filtros aplicáveis a cada documento e regras comerciais
  permanecem os mesmos.
- As opções de central e o seletor de reutilização de cache não aparecem nas
  preferências do modo direto. **Verificar fonte** e **Diagnóstico** continuam
  disponíveis.
- A verificação da publicação mostra atividade e pode ser cancelada na tela.

## Fluxo de uma consulta

1. Confirma a publicação geral por `/general/dates/updated`.
2. Confirma a publicação municipal por `/cities/dates/updated`.
3. Solicita o detalhamento por NCM em `/general?language=pt`.
4. Confere esse detalhamento com outra consulta agregada por mês e NCM.
5. Solicita o detalhamento municipal por SH4 em `/cities?language=pt`.
6. Confere essa base com outra consulta agregada por mês e SH4.
7. Publica o novo resultado somente depois que ambas as bases estão completas
   e as conferências de valores e pesos passaram.

As verificações de publicação ao entrar no módulo ou pelo botão Verificar fonte
podem acrescentar chamadas antes da consulta do período.

Períodos longos continuam divididos em janelas de até 12 meses e lotes de NCMs
compatíveis com o motor. Um período maior pode exigir mais chamadas.
Uma divergência, interrupção ou resposta incompleta não é convertida em dados
vazios válidos. A última consulta completa permanece preservada.

## Ritmo, cancelamento e independência

O acesso direto usa intervalo conservador mínimo de **65 segundos entre
chamadas**, com até três tentativas para falhas recuperáveis. Esse intervalo é
uma política do programa; não representa uma cota oficial documentada pelo MDIC.
Um lote de um ano que caiba nas seis chamadas acima exige vários minutos,
mesmo com respostas rápidas. A interface continua disponível durante a espera.

`Retry-After` e respostas HTTP 429 continuam respeitados. O registro local de
pausas evita que reabrir o aplicativo provoque uma sequência imediata de novas
tentativas. Essa coordenação é um arquivo local, não um servidor ou uma porta
HTTP em execução. Instalações de computadores diferentes não compartilham fila
nem respostas.

A opção por acessos independentes elimina a dependência de um hospedeiro da
empresa. Ela não garante que a API aceite todos os acessos simultâneos. A causa
ou o critério de identificação do HTTP 429 observado não foi demonstrado; não
se presume que o problema anterior fosse um bloqueio permanente do IP.

O desktop não usa os arquivos CSV como alternativa nesta revisão. A validação
HTTPS do Windows introduzida na RC6 continua ativa para a API. Não se desativa
a conferência de certificados, não se muda o IP e não se contorna uma recusa.

## Atualizar sem comandos

1. Feche a versão anterior do aplicativo e qualquer central antiga que tenha
   ficado aberta durante os testes anteriores.
2. Extraia **todo** o ZIP da RC7 em uma pasta nova.
3. Abra **INICIAR_DESKTOP.cmd** com dois cliques e aguarde o assistente.
4. Entre em **Importações**, escolha o período e clique em **Consultar**.

Não configure uma central nem importe arquivos de conexão para esta versão.
Os dados de estoque, configurações visuais e relatórios anteriores continuam
preservados. Um atalho de um executável antigo continua abrindo esse executável;
extrair fontes não substitui a instalação antiga.

O ZIP contém fontes e assistentes; não inclui um Setup Windows compilado.
A geração do instalador com Python e dependências incluídos continua no
assistente de compilação existente.

## Validação

Os testes da política direta verificam chamadas exclusivamente ao host da API,
ausência de central e CSV, desconsideração de pareamentos e caches inválidos,
atualização real do mesmo período, independência entre perfis, respostas 429,
conferência de totais e manutenção do resultado anterior em caso de falha.
Os testes Qt verificam nova consulta, filtros locais, preferências e
cancelamento da verificação da publicação. As massas controladas não são uma
consulta real ao Comex nem um ensaio com computadores físicos da empresa.

Os componentes de acesso compartilhado anteriores permanecem nos fontes para
compatibilidade e testes de regressão, com ativação explícita por código. A
composição normal do desktop não os ativa, mesmo havendo configuração antiga.

Resultados atuais: `EVIDENCIAS_API_DIRETA_520_RC7.json`. Preservação das regras e
dos arquivos: `PRESERVACAO_API_DIRETA_520_RC7.json`. A evidência do ensaio externo
registra o escopo e o resultado efetivamente obtido; não deve ser ampliada para
todos os NCMs, períodos ou para a rede Windows da empresa.

Contrato oficial consultado em 22/10/2026:
<https://api-comexstat.mdic.gov.br/docs/doc.yaml>.

### Resultado real desta entrega

Em 22/10/2026, o motor direto concluiu setembro/2026 para o NCM 29161220 e
o SH4 municipal correspondente: 18 linhas gerais e 216 municipais, seis
respostas HTTP 200, com conferências aprovadas, sem CSV, central ou cache de
respostas. O ensaio levou 368,717 segundos na rede de teste Linux. Isso não
representa homologação de todos os NCMs nem da rede Windows da empresa.
