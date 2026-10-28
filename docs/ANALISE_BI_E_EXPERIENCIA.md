# Análise do BI e organização da experiência

## Arquivos analisados e método

Foram examinados os dois PBIX enviados, suas definições de páginas e visuais, o esquema do modelo, os relacionamentos, as expressões DAX e a compatibilidade com o importador atual do aplicativo. A inspeção leu os dados e metadados já gravados nos arquivos, sem executar suas expressões M ou DAX, atualizar as fontes ou enviar consultas ao sistema ou servidor SQL da empresa.

| Arquivo | Tamanho | SHA-256 |
| --- | --- | --- |
| `LiarteBI_v1.pbix` | 28.007.628 bytes | `2a0209da000accc1903314a8c8989e3e329af01c5510c2fc1b0a24a5f408ff52` |
| `LiarteBI_v1 (1).pbix` | 28.007.628 bytes | `588ab9ee8053819bc9bb9ba657f2a8c535b57389327c37a3fb7101fd72c91e7e` |

Os arquivos têm hashes externos diferentes, mas **todos os 644 membros internos são idênticos**, incluindo o modelo de dados e as definições do relatório. Portanto, contêm a mesma versão funcional do BI; a diferença está no invólucro ZIP.

O relatório contém **54 páginas e 519 visuais**, contando botões, filtros, textos, imagens e outros elementos. Há 130 segmentadores, 106 botões e 77 tabelas ou matrizes; 19 páginas são tooltips. Somente Home não está marcada como oculta. As demais são acessadas por navegação, detalhes ou recursos auxiliares: isso não significa que existam 54 opções principais para o usuário.

O esquema extraído contém **64 tabelas com colunas e 556 colunas**, incluindo 24 calendários locais automáticos, um calendário-modelo e parâmetros auxiliares. Há ainda **cinco agrupadores dedicados de medidas sem colunas nesse esquema**. Portanto, 64 não é uma contagem de tabelas de negócio nem de todos os objetos tabulares. Foram inventariadas **302 medidas DAX, 164 colunas calculadas e 32 tabelas calculadas**, além de 51 relacionamentos, dos quais 47 ativos e 12 bidirecionais.

Essas contagens descrevem a estrutura. Não equivalem a uma reconciliação das 302 medidas executadas no Power BI. A análise semântica priorizou os indicadores operacionais e as expressões com risco de interpretação ou agregação incorreta.

## Dados e compatibilidade com o aplicativo

A atualização registrada no modelo é **26/10/2026, às 16:35:43**, conforme o texto original da fonte. O arquivo não informa o fuso desse horário; ele não deve ser convertido como se fosse UTC. O importador utiliza a data, 26/10/2026.

| Conjunto | Grão e cobertura observados |
| --- | --- |
| Saídas | 51.583 linhas de itens, com produto, filial, unidade e emissão; datas de 2019 até 26/10/2026 |
| Entradas | 6.946 linhas, com produto, filial, unidade, emissão e entrada; último registro em 23/10/2026 |
| Fechamentos | 100.119 posições mensais; último fechamento em 30/09/2026 |
| Estoque atual | 1.784 posições; a data individual de estoque varia entre posições e não identifica a idade dos lotes |
| Contas a receber | 102.123 linhas de títulos/parcelas, com emissão, vencimento, status e baixa |
| Contas a pagar | 48.889 linhas de títulos/parcelas, com emissão, vencimento, status e baixa |

O importador atual leu o PBIX, validou o modelo, produziu um snapshot privado e o reabriu sem perda dos dados importados. O resultado contém **2.265 produtos, 1.784 saldos, 100.119 fechamentos e 38.695 agregados diários de vendas**, em três filiais e 15 armazéns. Quatro códigos históricos sem cadastro foram preservados e sinalizados.

A importação e o teste de ida e volta não substituíram a base distribuída com o aplicativo. Os PBIX, os registros da empresa e o snapshot de inspeção permanecem fora do repositório.

A fonte contém valores negativos de giro e dias: 259 registros de giro mensal em quantidade e 854 de dias em quantidade. Esses valores originais não foram inventados pelo aplicativo. Devem permanecer rastreáveis, mas não entrar automaticamente em medianas elegíveis ou alertas que pressupõem indicadores não negativos.

## Definições e problemas encontrados no BI

As referências abaixo identificam medidas ou visuais do arquivo. Algumas mostram inconsistências diretas entre nome e fórmula; outras exigem validar a definição operacional antes de concluir que um resultado está errado.

| Referência | Evidência e consequência | Tratamento recomendado |
| --- | --- | --- |
| `Medidas[Ticket Medio Bruto por Cliente]` | Divide venda bruta por `Qtd Notas Emitidas`, que conta números distintos de `Documento`. A expressão coincide com a medida de ticket por NFe e não usa o número de clientes compradores. | Separar ticket por cliente e por nota, com denominadores visíveis e uma chave documental validada. |
| `Medidas[Meta Venda Bruta Qtd]` | Multiplica a base anterior por `1.001`, isto é, aumento de 0,1%; o comentário diz aumento de 10%. | Confirmar a meta com o negócio. A fórmula e o comentário não permitem escolher silenciosamente qual intenção prevalece. |
| Visual de `Giro Estoque New` | Os giros mensal, trimestral, semestral e anual em quantidade usam agregação Sum. | Não somar razões entre posições ou meses. Usar valores por posição, distribuição ou mediana identificada; um giro consolidado exige numerador e denominador definidos. |
| `Medidas_Estoques[Dias de Estoque]` | Usa `SUM(Fact_Estoque[DiasEstoque])`. Somar dias de várias posições não produz dias do estoque agregado. | Separar indicador da fonte, cobertura estimada, recência de venda e idade física dos lotes. |
| `Medidas[Media Venda Bruta Mensal R$]` | Conta valores de `Month Short`, uma coluna de texto com 12 valores distintos, em vez de pares ano-mês. O mesmo padrão aparece nas médias mensais de quantidade e lucro bruto. Uma seleção de vários anos pode dividir por apenas 12 meses distintos. | Contar meses ano-mês efetivamente comparáveis e tratar parciais explicitamente. |
| `Medidas_Estoques[Estoque Fechamento Medio]` | Passa uma data final como terceiro argumento de `DATESINPERIOD`, onde se espera um número de intervalos, e percorre o calendário com `AVERAGEX`. | Rever o intervalo e calcular sobre os fechamentos observados apropriados. Não supor saldo diário conhecido entre fechamentos. |
| `Medidas[Margem Bruta %]` | O lucro é venda líquida menos custo, mas o percentual divide por venda bruta. Isso é uma escolha de base, diferente de margem sobre receita líquida. | Indicar o denominador e validar a composição fiscal do valor líquido antes de calcular ou comparar margens. |
| `Medidas_Recebiveis[Total Titulos]` e `Medidas_APagar[Total Titulos (contas a pagar)]` | Usam `DISTINCTCOUNT(Documento)`. Na base, números de documento se repetem entre filiais e contrapartes. | Validar a chave operacional de título e parcela. Documento isolado não identifica globalmente esses registros. |
| `Medidas_Estoques[Data Ultima Venda]` | Usa a maior data de emissão sem exigir quantidade positiva; pode ficar restrita ao período filtrado. | Para recência, procurar a última saída positiva até a data da base, incluindo o histórico anterior ao período. |
| `Medidas_Estoques[Data contexto]` e medidas de saldo financeiro em atraso | Usam `TODAY()`. Quando consultadas, podem avaliar um extrato congelado contra uma data posterior à sua atualização. | Identificar claramente data da base, data de consulta e data de referência do indicador. Para análise do extrato, usar sua data de atualização. |

Os números de documentos não são uma distinção apenas teórica. Em contas a receber, 755 números são reutilizados entre filiais e 475 entre clientes na mesma filial. Em contas a pagar, há 195 entre filiais e 4.635 entre fornecedores na mesma filial. Uma chave composta deve ser validada conforme o grão da operação; contar linhas de itens, parcelas, títulos e notas são operações diferentes.

O comportamento de `TODAY()` também depende do objeto: uma medida é avaliada na consulta, enquanto colunas calculadas de aging ou atraso são recalculadas na atualização do modelo. Misturar essas referências pode produzir classificações com datas diferentes no mesmo relatório.

Há também diferenças importantes de filtros e relacionamentos:

- **Bloqueio:** a página Giro Estoque New exclui `Bloqueado='1'`. O importador atual não importa esse campo e preserva todas as posições. Existem 20.039 registros históricos com esse código e 80.080 com o código `2`. Totais do aplicativo e dessa página não devem ser comparados como se usassem o mesmo recorte.
- **Filtros de outro assunto:** páginas de estoque incluem segmentadores de aging de contas a pagar. Um filtro deve aparecer apenas quando tem efeito e significado para a tarefa atual.
- **Propagação por origem:** existem relações bidirecionais, inclusive várias relações 1:1 por `IdOrigem` entre dimensões. É necessário conferir sua finalidade e linhagem antes de reproduzir filtros cruzados. A estrutura, sozinha, não comprova erro em um valor financeiro.
- **Calendário financeiro:** as relações ativas de contas a receber e pagar usam `DataVenctoReal`. Um período de vencimento não é um período de emissão nem de baixa.
- **Datas sentinela:** há `DataBaixa=1900-01-01` em registros de documentos muito posteriores. Essa data precisa ser interpretada e tratada como ausência, conforme o contrato da origem, em vez de virar pagamento ocorrido em 1900.

## Indicadores que a base permite desenvolver

O PBIX contém mais informações do que o contrato de estoque atualmente importado pelo aplicativo. Isso permite expansão, mas não autoriza trocar o significado dos campos existentes.

| Área | Já suportado no aplicativo | Expansão possível após validar o contrato |
| --- | --- | --- |
| Estoque e produtos | Capital a custo, saldos por unidade, vendas em quantidade, alertas, fechamento, comparação mensal, giro da fonte e cobertura estimada | Bloqueio/disponibilidade das posições e contexto de compras fiscais |
| Vendas | Quantidades líquidas por produto, filial, unidade e período | Venda bruta/líquida em reais, preço realizado ponderado, margem e concentração de receita |
| Compras | Análise externa do mercado importador via Comex | Entradas fiscais por produto/filial, com escolha explícita entre emissão e entrada |
| Financeiro | Não faz parte do contrato de estoque atual | Carteira aberta, vencidos e a vencer, aging, baixas e estimativas de prazo financeiro |
| Mercado | Valores CIF/FOB, peso, origens e preço unitário no recorte Comex comparável | Comparação com produtos da empresa após criar um mapeamento de classificação e bases equivalentes |

`Fato_DocumentoSaida` contém `ValorTotal`, `ValorTotalLiquido`, `PrecoUnitario`, `CustoTotal`, impostos, comissão, frete e embalagem. Os campos examinados de valor total, valor líquido, preço unitário, custo, frete, comissão e embalagem não têm nulos no extrato. Há, porém, itens com quantidade zero, custo zero e valor líquido negativo: seu significado deve ser preservado e investigado, sem divisão por zero ou exclusão automática. O `Sale.cost` atual representa **custo**, não faturamento. Receita e margem exigem extensão explícita e versionada da importação, do cache, dos cálculos e da exportação.

Antes de calcular margem, é necessário validar quais despesas e tributos já estão incluídos no valor líquido. Custo médio de estoque, custo atribuído à saída e preço de venda também não são indicadores intercambiáveis.

Os documentos de entrada não têm lote ou armazém e não abrangem produção, consumo interno, transferências e ajustes. Eles podem ajudar a investigar compras fiscais, mas não explicam integralmente a variação física do estoque nem a idade das unidades armazenadas.

As medidas de prazo financeiro do BI usam saldo dividido por fluxo anual, multiplicado por 365. São estimativas semelhantes a DSO/DPO, não a média efetiva dos dias de pagamento de cada parcela. Uma interface deve distinguir essas leituras.

## Empresa e mercado precisam de bases compatíveis

Não existe NCM ou SH4 no cadastro de produtos examinado, nem uma tabela de mapeamento entre os códigos internos e as classificações do Comex. Também não há uma base cambial e fiscal comum que permita comparar diretamente vendas em reais com CIF/FOB em dólares.

As saídas da empresa usam KG, L e UN. Quantidades dessas unidades não podem ser somadas; litros não podem ser convertidos em quilogramas sem um fator válido para o produto. A quantidade de uma compra fiscal também não comprova que a operação seja uma importação própria da empresa.

Portanto, não é possível inferir participação de mercado, custo de importação da empresa ou vantagem de preço apenas unindo os totais. Um cruzamento futuro precisa de mapeamento produto–NCM, unidade, moeda, período, origem e escopo equivalentes e rastreáveis.

## Aplicação à experiência do usuário

A reorganização deve permitir perguntas claras, sem transformar as 302 medidas em cartões simultâneos:

1. **Panorama:** poucos indicadores prioritários, período e escopo claros, mais os principais pontos que merecem atenção.
2. **Evolução:** um indicador por gráfico, leitura mensal interativa, comparação explícita e distinção de meses incompletos.
3. **Produtos:** busca, rankings pertinentes, investigação individual e ações separadas para aplicar um produto aos filtros gerais.
4. **Mercado:** classificação do produto, valor, peso, preço unitário e origens no recorte comparável, preservando as diferenças entre CIF e FOB.
5. **Dados e documentos:** tabelas completas e exportações acessíveis quando o usuário precisa conferir a origem de um resultado.

Filtros precisam mostrar o recorte aplicado e distinguir escolhas ainda não aplicadas. Navegar entre tarefas deve trocar o conteúdo apresentado, manter os dados e formulários e evitar releituras do PBIX ou novas chamadas de rede.

Receita, margem, entradas e financeiro são próximos módulos possíveis, sujeitos aos contratos descritos acima. A revisão atual não altera os PBIX originais nem incorpora seus dados financeiros ou pessoais ao repositório.

O [guia da interface modular](GUIA_INTERFACE_MODULAR.md) descreve as tarefas e os controles dessa reorganização.
