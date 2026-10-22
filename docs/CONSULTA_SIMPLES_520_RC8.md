# Consulta simples — 5.2.0-rc.8

O botão Consultar baixa o período completo diretamente da API do Comex Stat.
Com o cadastro embutido atual, envia apenas dois POSTs sequenciais:

1. `/general?language=pt`: todos os NCMs, meses, UFs, URFs, países, FOB,
   frete, seguro, CIF e peso líquido solicitados.
2. `/cities?language=pt`: todas as posições SH4 correspondentes, meses,
   municípios fiscais, UFs, países, FOB e peso líquido.

Não existe endpoint único que combine esses dois universos. A base municipal
não é derivada da geral, não possui NCM de oito dígitos/CIF/URF e não é somada
à geral. Todas as linhas continuam agregados estatísticos, não pedidos individuais.

## O que deixou de atrasar a consulta

- Dois GETs de disponibilidade antes do download.
- Um POST adicional de totais por base.
- Verificação automática de publicação ao entrar no módulo.
- Intervalo preventivo de 65 segundos, inclusive o intervalo remanescente de
  uma consulta de versão anterior. Pausas reais da fonte não são apagadas.
- Divisão automática do período em janelas anuais.
- Repetições automáticas: uma tentativa por base, sem repetição escondida.

O socket permite até 120 segundos de espera por resposta. A leitura completa
é limitada a 240 segundos e 100 MiB por resposta, além de observar cancelamento.
Um pedido recusado não abre outra rota, CSV, central ou nova consulta fragmentada.
A última consulta completa permanece disponível se uma nova consulta falhar.

## Precisão e limites da conferência

A validação local continua obrigatória: JSON e estrutura, integridade do
transporte quando Content-Length existe, campos/dimensões, códigos solicitados,
período, números finitos não negativos, centavos sem arredondamento indevido,
peso inteiro conforme o contrato atual, CIF = FOB + frete + seguro e
identidades duplicadas. Duplicatas idênticas contam uma vez; valores conflitantes
interrompem o carregamento. Resumos e arquivos continuam sujeitos às verificações
locais dos geradores. A publicação do novo resultado continua atômica, após ambas
as bases e conversões concluírem.

Sem o POST independente de totais, o sistema não detecta uma eventual omissão
bem formada da própria API. O registro de exportação informa `response_validated`
e `totals_verified` separadamente; na consulta simples, o primeiro é verdadeiro
e o segundo falso. Datas de publicação desconhecidas ficam vazias, sem fingir
que o último mês solicitado seja o último mês publicado.

O período é limitado a meses completos desde 1997. O Comex confirma ou recusa
os meses efetivamente disponíveis. Não se preenche um mês ausente com valores
estimados. Verificar fonte continua disponível manualmente, separado da consulta.
Filtros e exportações não chamam a API.

O ritmo interno simplificado não altera limites externos. Um HTTP 429 continua
possível. O programa registra o erro e a pausa; não muda IP, não desativa TLS e
não faz novas tentativas automáticas depois de uma recusa.

## Atualizar

Feche a versão anterior, extraia todo o ZIP em outra pasta e abra
INICIAR_DESKTOP.cmd. Um atalho de um executável antigo continua abrindo aquele
executável. Este pacote contém fontes e assistentes, sem Setup Windows compilado.
Configurações, relatórios, estoque, identidade visual, regras do PDF e a largura
64 da coluna E da base municipal são preservados.

Os componentes legados de central/cache/CSV e conferência adicional ficam
conservados para regressão e ferramentas administrativas com ativação explícita;
a composição normal do desktop não os usa. O script verificar_comex.py é uma
ferramenta manual de conciliação com chamadas adicionais, não o fluxo de Consultar.

Contrato oficial consultado em 22/10/2026:
https://api-comexstat.mdic.gov.br/docs/doc.yaml

Evidências da entrega: EVIDENCIAS_CONSULTA_SIMPLES_520_RC8.json.
Os documentos RC7 e anteriores registram versões históricas.
