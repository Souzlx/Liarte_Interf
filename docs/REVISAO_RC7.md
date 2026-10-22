# RC7 — ajustes após as seis capturas do Power BI

As capturas de 19/10/2026 mostram que o modelo carregou os dados e as páginas gerais estão calculando valores. Também mostram tabelas sem conteúdo visível, UF truncada, município com UF repetida e indicadores por kg indisponíveis. São observações do Power BI Desktop da empresa; os validadores da RC6 não tinham detectado o comportamento das tabelas.

## Tabelas detalhadas

A Base Detalhada e o Detalhamento municipal foram reconstruídos no padrão plano de `tableEx`: todas as projeções ficam em Values e usam exclusivamente colunas do fato correspondente. Essa alteração reduz a complexidade da consulta visual e elimina a combinação, nessas tabelas, de atributos de várias dimensões com medidas DAX. As dimensões continuam filtrando os fatos pelos mesmos relacionamentos.

Cada tabela inclui todos os campos da chave estatística original, sem limitar aos maiores registros ou remover linhas sem peso. Os nomes comerciais foram materializados no fato geral para essa finalidade. CIF/kg e FOB/kg de cada observação são recalculados no Power Query a partir dos valores e kg da própria linha. O cálculo ignora a coluna de preço já exibida no Excel, não arredonda o dado no modelo e retorna vazio se kg = 0. As colunas de preço têm `summarizeBy: none`, ficam ocultas para autoria e não são somadas em um total. Medidas agregadas continuam explícitas e ponderadas.

O preset de estilo nativo foi definido como None para permitir que o cabeçalho e as cores de linhas configuradas sejam respeitados. A validação interna passou a rejeitar tabelas detalhadas com medidas, fontes misturadas, níveis de drill ativos ou totais de preços.

**Limite da investigação:** não houve execução do Power BI Desktop neste ambiente. A reconstrução é um ajuste de compatibilidade e de complexidade da consulta. Não se afirma que a causa exata da renderização vazia foi reproduzida ou que a nova tabela já foi vista funcionando no Desktop. O roteiro de aceitação exige conferir as duas páginas após Atualizar.

## Indicadores por kg

O espaço vazio na página Produtos e NCM, quando todos os produtos estão selecionados, decorre da exigência de um único NCM para comparações de preço. A mensagem agora apresenta essa orientação antes do aviso de dados sem peso.

A regra de precisão foi mantida: se houver valor positivo sem peso no recorte, a razão agregada afetada não é apresentada. Não se estima peso nem se excluem essas linhas silenciosamente. A tabela detalhada mantém a observação com seu valor e peso zero; o preço dessa linha fica vazio.

O gráfico de Custos Logísticos agora apresenta o frete mensal integral em US$ mi. Assim, o panorama continua útil mesmo com registros sem peso. Frete/kg e contagem de registros sem peso permanecem nas dicas; a análise comparável continua disponível com um NCM e cobertura adequada.

## Apresentação

- UF nas páginas gerais: largura de 88 para 124, redistribuindo a faixa de filtros sem sobreposição.
- Município/UF: reutiliza a sigla já presente no nome; não produz mais rótulos como São Luís - MA · MA. Chave composta e contagem de municípios preservadas.
- URF: apresenta o nome antes do código, mantendo o identificador ao final para distinguir unidades. O valor original permanece na tabela detalhada e na chave da dimensão.
- Indicadores: contornos nativos removidos e fundo neutro discreto.
- Eixos em milhões: números compactos no eixo, unidade explícita no título e valores completos nas dicas/cartões. As três medidas auxiliares de apresentação não mudam os valores econômicos.
- Curvas de valores totais CIF, FOB municipal e frete partem de zero. A curva de preço mantém escala automática, indicada no título. A variação mensal CIF também fica disponível na dica da curva executiva.

## Preservação e verificação

Cadastro de 35 NCMs/54 relações, extração Comex, interface Qt, instalação/atalhos, filtros e escopo das exportações foram preservados. Excel e BI continuam abrangendo o período/cadastro completos. O PDF continua usando os filtros e regras comerciais anteriores. A largura E municipal permanece 64 e o alinhamento vertical do Excel não mudou.

A revisão inclui 31 testes próprios de Power BI, incorporados à suíte completa. Resultados executados estão em EVIDENCIAS_RC7.json e VALIDACAO_RC7.log. TMDL/TOM, sintaxe M, schemas PBIR, totais SQL/Decimal, exportações Qt e preservação de arquivos são verificações distintas; nenhuma delas é apresentada como execução DAX ou renderização Desktop.

Referências primárias usadas na revisão: [tabelas e matrizes PBIR](https://github.com/microsoft/skills-for-fabric/blob/main/skills/powerbi-report-cli/references/authoring/table.md), [modelagem estrela](https://learn.microsoft.com/en-us/power-bi/guidance/star-schema) e [cache/dados do projeto PBIP](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-dataset).
