# Critérios de modelagem e apresentação — RC6

Revisão de 19/10/2026, aplicada ao gerador do projeto Power BI. As decisões abaixo resultam da documentação primária da Microsoft, da inspeção do código e de testes sobre os documentos realmente produzidos. Não representam certificação da Microsoft nem testes com usuários.

| Critério | Aplicação no projeto | Motivo |
| --- | --- | --- |
| Granularidade explícita | Fato geral mensal por NCM8/UF/URF/país; fato municipal por SH4/município fiscal/UF/país | Impedir cruzamentos que atribuam CIF ou NCM8 ao município |
| Dimensões e medidas | 11 tabelas, 12 relacionamentos muitos para um, 54 medidas explícitas | Organizar filtros e controlar a agregação |
| Cadastro com aliases | Produtos → ponte única Produto/NCM → dimensão NCM → fato | Selecionar a união dos códigos sem multiplicar valores por quantidade de produtos relacionados |
| Filtros direcionais | Uma única relação bidirecional, na ponte; demais unidirecionais | Permitir seleção por produto sem caminhos ambíguos entre fatos |
| Datas mensais | Calendário completo do intervalo, índice ano × 12 + mês e rótulo ordenado | Ordenar anos/meses e preservar meses sem movimento; não declarar tabela diária nem usar DATEADD nessa base |
| Precisão | Moeda fixed decimal no modelo; controles em centavos inteiros; kg em Int64 | Evitar conversões de texto e arredondamentos silenciosos |
| Preços ponderados | Soma do valor ÷ soma do peso; nunca média das razões de cada linha | Operações com pesos distintos não têm o mesmo peso econômico |
| Comparabilidade | Página de preços exige um NCM; MM3 exige três meses consecutivos selecionados e peso em todos | Não interpretar alteração do mix como variação de preço |
| Ausência e zero | Sem dado permanece vazio; valor positivo sem peso suprime a razão afetada | Não gerar preço aparentemente válido com denominador incompleto |
| Concentração | Top 5 usa ALLSELECTED; empates têm desempate estável pelo nome/código | Medir a seleção atual e não um denominador global inesperado |
| Rankings | NCMs únicos, países, UFs e URFs; top 10/8 calculado pela medida e dentro da seleção | Evitar barras de produtos comerciais sobrepostos e excesso de categorias |
| Escalas | US$, US$ mi, kg, t, US$/kg e percentuais explícitos; unidades automáticas desativadas | Evitar dupla divisão por milhões e confusão entre FOB e CIF |
| Integridade | SHA-256 da fonte, valores/mês, duplicação da chave e CIF = FOB + frete + seguro conferidos antes da publicação | Interromper a geração se a fonte não satisfizer o contrato |

## Organização das seis páginas

- **Visão Executiva:** valor CIF, volume, peso da logística, países e evolução; ranking por produto comercial + NCM único.
- **Mercado e Origem:** cobertura, concentração nos cinco principais países, UFs e URFs. País não significa fornecedor.
- **Produtos e NCM:** preço do último mês, MM3 ponderada, variação do último mês frente ao anterior selecionado, frete/kg do período, séries CIF/FOB e comparação entre origens de maior volume.
- **Custos Logísticos:** frete, seguro em US$ integrais, logística/FOB, CIF/FOB, tendência do frete/kg e participação logística por país.
- **Base Detalhada:** medidas integrais, códigos, nomes comerciais, descrições oficiais e produtos relacionados para conferência.
- **Análise Municipal:** universo SH4/FOB independente, municípios identificados também pela UF, evolução, rankings e detalhes. Nunca somar ao fato geral.

As cinco páginas gerais compartilham os segmentadores. A municipal usa outro grupo de sincronização, inclusive para período, país e UF. Isso impede que um filtro de uma página geral deixe a leitura municipal incompreensível. Os 36 nomes comerciais do PDF foram preservados em um módulo comum: 35 NCMs atuais e um código histórico já existente.

## Composição visual

Canvas de 1440 × 900, margens de 24 e espaçamentos regulares de 16. Logo original proporcional no cabeçalho, títulos com 23 pt, navegação consistente, segmentadores em uma faixa e indicadores com 92 px de altura. Até quatro indicadores por faixa, sem ocupar metade da página. Paleta branca, azul LIARTE e azul petróleo, sem sombras pesadas, gradientes decorativos ou gráficos 3D. As páginas têm 85 contêineres visuais no total, incluindo textos, logo, filtros e navegação; esse número não significa 85 gráficos.

Barras partem de zero. Linhas usam marcadores; CIF, FOB e MM3 têm formas distintas, com MM3 tracejada. Texto alternativo e ordem de tabulação foram definidos. Valores integrais ficam disponíveis nas dicas e na base detalhada, mesmo quando um indicador está expresso em milhões. As tabelas permitem a leitura completa com rolagem nativa quando a descrição é longa.

O relatório usa visuais nativos do Power BI. Não adiciona Python, R, visuais personalizados ou dependência de serviços externos para desenhar gráficos. O canvas usa Ajustar à página; não se afirma que este PBIP já tenha layout móvel específico. O aplicativo Qt e seus temas continuam preservados.

## Validação em camadas e limites

1. Conferência do XLSX: estrutura, tipos, códigos, granularidade, identidade CIF e controles exatos.
2. Contrato local: referências reais do TMDL, medidas, cardinalidades, projeções, sincronização, IDs, recursos, geometria finita e ausência de sobreposição.
3. CLI oficial de autoria: schemas públicos PBIR e catálogo de propriedades dos visuais.
4. Microsoft Analysis Services TOM: desserialização e nova serialização do TMDL, formatos, tipos, expressões e relações.
5. Parser Power Query: sintaxe de 11 expressões compartilhadas e 11 partições.
6. SQLite/Decimal: totais independentes da captura, 105 recortes NCM/mês e referências aritméticas de preços, concentração e aliases.
7. Aplicativo real: exportação em worker, suíte de regressão e pacote congelado Linux.

**O TOM valida o modelo, mas não executa DAX. O parser M não atualiza dados. Schemas PBIR não renderizam as páginas.** Essas três etapas finais exigem Power BI Desktop no Windows; o roteiro de aceitação acompanha o pacote. Não foram usados resultados calculados em Python como se fossem resultados executados pelo motor DAX.

## Referências primárias consultadas

- [Esquema estrela](https://learn.microsoft.com/en-us/power-bi/guidance/star-schema)
- [Relações muitos para muitos](https://learn.microsoft.com/en-us/power-bi/guidance/relationships-many-to-many)
- [Filtros bidirecionais](https://learn.microsoft.com/en-us/power-bi/guidance/relationships-bidirectional-filtering)
- [Tabelas de datas](https://learn.microsoft.com/en-us/power-bi/transform-model/desktop-date-tables)
- [Formatos numéricos personalizados](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-custom-format-strings)
- [Acessibilidade dos relatórios](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-accessibility-creating-reports)
- [Projetos PBIP](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-overview)
- [Pasta do relatório PBIP](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-report)
- [Formato aprimorado PBIR](https://learn.microsoft.com/en-us/power-bi/developer/embedded/projects-enhanced-report-format)
- [Schemas públicos](https://github.com/microsoft/json-schemas/tree/main/fabric)
- [CLI oficial de autoria](https://www.npmjs.com/package/@microsoft/powerbi-report-authoring-cli)
- [TmdlSerializer](https://learn.microsoft.com/en-us/dotnet/api/microsoft.analysisservices.tabular.tmdlserializer)
- [Parser Power Query](https://github.com/microsoft/powerquery-parser)
