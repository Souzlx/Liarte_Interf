# Indicadores dos produtos

Em desenvolvimento nos fontes, após a publicação da **5.3.1**. Os pacotes dessa release permanecem iguais; esta melhoria exige uma entrega posterior para aparecer no aplicativo instalado.

Em **Estoque → Produtos**, a vista **Indicadores** organiza recortes quantitativos. Ela substitui a apresentação inicial chamada Prioridades, retirando relatos e próximos passos prontos. **Posições** mantém a tabela de saldos atuais e suas ordenações. Trocar entre elas preserva os filtros gerais e a sessão de análise. O nome deste arquivo e da aba Excel foi preservado para compatibilidade de referências.

## Escolher o foco

Selecione a unidade, a janela de **1, 3 ou 6 meses** e o foco; use a busca quando necessário e pressione **Aplicar**. As escolhas do formulário só alteram a lista depois de confirmadas. A lista é ordenada pelo valor a custo do fechamento, com valores desconhecidos ao final, e mostra até oito produtos por página.

| Foco | Critério |
| --- | --- |
| Critérios combinados | União, sem duplicar produto/unidade, das três situações abaixo |
| Cobertura < limite | Cobertura estimada conhecida abaixo do limite configurado, com demanda líquida positiva e posições sem saldo negativo |
| Variação de vendas < 0 | Quantidade líquida menor entre duas janelas completas consecutivas, com base positiva, venda recente não negativa e saldo positivo no fechamento |
| Saldo > 0 · vendas líquidas = 0 | Saldo positivo no fechamento e quantidade líquida recente conhecida igual a zero |
| Estoque a custo | Saldo e custo positivos no fechamento, ordenados por valor |

O limite de cobertura reutiliza o valor aplicado em **Ajustar alertas**, inicialmente 30 dias. É uma política configurável, não um parâmetro aprendido da base nem uma recomendação de compra. O limite é estrito: 30 dias não entra em uma regra de cobertura inferior a 30 dias; zero conhecido pode entrar. A cobertura desta vista usa o fechamento e a janela recente indicados. O painel de alertas do Panorama usa sua própria referência de saldo atual e período de demanda.

Um produto pode satisfazer mais de um critério, mas aparece uma única vez por unidade na lista. As contagens das categorias se sobrepõem e não devem ser somadas. Quantidades de unidades diferentes continuam separadas.

## Referência e interpretação

**Saldo e capital pertencem ao fechamento identificado na tela.** A data da base não transforma esse saldo em saldo atual. A vista Posições continua disponível para consultar a situação atual na referência da base.

As vendas usam a mesma regra do [desempenho dos produtos](DESEMPENHO_PRODUTOS.md): janelas consecutivas de meses completos, sem preencher lacunas com zero nem buscar meses antigos para completar um intervalo. Um mês final parcial fica fora da comparação e permanece identificado no contexto. Janelas com o mesmo número de meses podem ter dias de calendário diferentes.

Histórico anterior insuficiente impede classificar uma queda. Quando a janela recente é conhecida, suas vendas, cobertura e capital podem continuar disponíveis. Um filtro de armazém impede atribuir vendas ou cobertura àquele local; a visão de capital pode continuar disponível.

Zero líquido não comprova ausência de saídas: vendas podem ter sido compensadas por devoluções. Cobertura não confirma ruptura nem determina uma compra. Custo não é faturamento, e a base não informa a idade física dos lotes, consumo interno ou a causa das variações. Saldos e custos negativos permanecem rastreáveis com aviso, sem criar uma estimativa de cobertura válida.

## Investigar sem perder o recorte

Selecione um produto para consultar valores e critérios, com operadores, referências e períodos. A investigação não altera os filtros gerais.

- **Histórico completo** abre o desempenho do produto e da unidade na mesma janela escolhida.
- **Ver posições** aplica explicitamente produto e unidade ao recorte geral e abre a tabela de posições. Os outros critérios são preservados.

Os critérios apresentam comparações numéricas. Hipóteses comerciais e sugestões de conferência foram removidas da interface, dos retornos analíticos e do Excel. Definições e indisponibilidades continuam acessíveis para interpretar os números.

## Excel e processamento

O Excel de Estoque gerado pela interface acrescenta **Prioridades dos produtos**, com todos os produtos/unidades classificados no recorte e na janela aplicada, independentemente do foco, busca, unidade de apresentação ou página da lista. Cada linha reúne critérios, valores, períodos, fechamento e limite de cobertura. Fonte, data da base e filtros acompanham a exportação. As colunas de motivos e próximos passos foram retiradas; definições ficam no comentário do cabeçalho final e na Leitura dos indicadores. Valores desconhecidos ficam vazios e zeros conhecidos continuam numéricos.

Sem abrir Indicadores, a exportação usa a janela padrão de três meses. O desempenho dos produtos mantém sua própria janela: as duas abas registram seus períodos para que uma mudança em uma vista não seja confundida com mudança na outra.

O processamento usa o cache mensal aceito e tarefas canceláveis fora da interface. Trocar foco, unidade, busca ou página reutiliza os cálculos. Navegar e investigar não relê o PBIX nem consulta a internet. Trocar a base ou o recorte invalida a análise anterior antes de apresentar a nova. A exportação inclui os dados completos, com precisão e divisão de abas conforme os limites do Excel.

## Prévia da interface

Capturas do aplicativo Qt no Linux, com dados sintéticos e sem informações da empresa. A lista continua pela rolagem da página; a apresentação compacta reorganiza os controles e mantém a navegação por teclado. Estas imagens não substituem a validação do executável no Windows.

- [Indicadores em janela ampla e tema claro](images/prioridades-produtos.png).
- [Valores e critérios de um produto](images/prioridades-produto-detalhe.png).
- [Janela compacta em tema escuro](images/prioridades-produtos-compacto.png).

A [diretriz de análise e migração](ANALISE_QUANTITATIVA_E_SQL_SERVER.md) registra o contrato compartilhado entre os arquivos atuais e a futura conexão SQL Server.
