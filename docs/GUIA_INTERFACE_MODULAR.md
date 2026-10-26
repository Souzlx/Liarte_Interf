# Usar a interface por tarefa

O aplicativo organiza **Estoque** e **Importações** em vistas próprias. Escolher uma vista muda o conteúdo apresentado; não percorre uma única página com todos os painéis. Os dados carregados, os filtros e as seleções continuam na mesma sessão.

![Panorama com indicadores principais e um gráfico por vez](images/interface-estoque-panorama.png)

[Filtros aplicados em conjunto](images/interface-estoque-filtros.png) · [Análise mensal](images/interface-estoque-mensal.png) · [Mercado e origens](images/interface-mercado-origens.png) · [Resumo do mercado](images/interface-mercado-resumo.png) · [Registros em janela compacta](images/interface-registros-compacta.png). As capturas usam dados sintéticos e a interface Qt real em Linux; fontes e escala podem variar no Windows.

## Estoque

| Vista | Para que serve |
| --- | --- |
| Panorama | Conferir capital a custo, produtos com saldo e giro da fonte; alternar entre evolução do estoque e capital por produto |
| Análise mensal / Mês a mês | Consultar um fechamento, escolher o indicador do gráfico, comparar meses e explorar produtos do mês |
| Produtos | Consultar as posições de estoque, ordenar e paginar a tabela, abrir detalhes e investigar o desempenho de um produto |

O Panorama mostra três indicadores principais. Alertas e capital por última venda ficam acessíveis sob demanda. O giro apresentado como mediana da fonte não é uma soma de giros nem um giro consolidado da empresa.

A busca de produto e a filial permanecem próximas do recorte aplicado. Para escolher período, unidade, armazém, grupo, tipo, curva ABC, última venda e sinal do saldo, abra **Refinar recorte**. Faça as escolhas e pressione **Aplicar recorte**: o conjunto é validado antes de uma atualização da análise. **Cancelar** ou fechar o diálogo descarta as escolhas provisórias.

**Limpar opções**, dentro do diálogo, limpa os critérios adicionais, preservando período e busca de produto. O período seleciona vendas e fechamentos históricos; o saldo atual continua associado à data da base. Filtros ABC, última venda e sinal do saldo selecionam a coorte pela situação atual, sem reconstituir sua classificação histórica.

Na análise mensal, use o cursor ou as setas para consultar o gráfico. **Analisar este mês** aplica explicitamente o mês selecionado à investigação; mover o cursor sozinho não altera os filtros. **Explorar produtos deste mês** abre os rankings e as variações quando forem necessários. **Comparar meses** mantém suas próprias escolhas de mês-base e mês comparado.

Em Produtos, **Desempenho dos produtos** oferece rankings por unidade, janelas consecutivas de 1, 3 ou 6 meses e investigação individual. A seleção nessa lista não altera os filtros gerais. Use **Filtrar este produto** para aplicar essa mudança explicitamente. Veja as definições no [guia de desempenho](DESEMPENHO_PRODUTOS.md).

## Importações e mercado

| Vista | Para que serve |
| --- | --- |
| Resumo | Conferir os indicadores principais e alternar entre evolução mensal e participação das origens |
| Compras | Examinar referências por kg, concentração e comparação de origens no recorte compatível |
| Registros | Consultar os dados da tabela, buscar registros, escolher colunas e abrir o detalhe de uma linha |

Depois de concluir uma consulta, os campos do período podem ficar recolhidos. Use **Período** para escolher outro intervalo e consultar novamente. O período efetivamente carregado continua identificado; escolher meses no formulário não transforma os resultados anteriores em uma consulta nova. Erros, andamento e pausas solicitadas pelo Comex permanecem visíveis.

**Filtros** abre produto ou classificação, país e as demais dimensões disponíveis para a base selecionada. A seleção provisória de cada campo só é aplicada ao confirmar esse campo. Diferentemente do formulário de estoque, esses filtros mantêm a confirmação individual já utilizada nas Importações.

No gráfico de origens, clique ou use o teclado para selecionar um país e aplicar seu filtro. A participação considera todas as origens do recorte, mesmo quando a apresentação mostra apenas as seis principais. A busca de Registros restringe a tabela; não deve ser interpretada como mudança nos indicadores do mercado.

O menu de documentos mantém acesso a Excel, PDF e projeto Power BI conforme a disponibilidade da consulta. A exportação informa sua abrangência; uma página visível da tabela não limita automaticamente todo o arquivo exportado.

## Ler os gráficos e indicadores

- **Unidade e moeda:** estoque a custo é apresentado em reais. O mercado Comex usa valores nominais em dólares, com CIF na base geral e FOB na municipal. Quantidades de unidades diferentes não são somadas.
- **Preço e composição:** com vários códigos, uma média em US$/kg descreve o mix observado. Uma mudança pode decorrer da composição dos produtos. Comparar origens como referência de um produto exige o recorte compatível indicado na tela.
- **Tempo e cobertura:** dias estimados de cobertura, última venda, giro e idade física dos lotes são conceitos distintos. A base importada não permite afirmar a idade das unidades em estoque.
- **Lacunas e parciais:** ausência de fechamento não é saldo zero. Meses sem observação ou parciais não devem gerar uma comparação como se estivessem completos.
- **Escala:** quando a escala é ajustada para ampliar pequenas diferenças, o gráfico identifica que o eixo não começa em zero. O ajuste não altera os valores.
- **Acesso ao detalhe:** gráficos permitem leitura por cursor e teclado; indicadores oferecem sua descrição completa também por foco, quando disponível. Ampliar o gráfico e consultar seus valores preserva o mesmo recorte.

Navegar entre as vistas, alternar gráficos e consultar detalhes usa os dados já carregados. Uma nova consulta é necessária quando o usuário solicita outro período à fonte; trocar somente a apresentação não deve realizar chamadas de rede ou reler o PBIX.

## O que a análise dos PBIX acrescenta

Os dois arquivos enviados têm o mesmo conteúdo funcional. A [análise do BI](ANALISE_BI_E_EXPERIENCIA.md) registra suas tabelas, medidas, diferenças de recorte e fórmulas que precisam de revisão.

Receita, margem, entradas fiscais e carteira financeira são expansões possíveis porque existem campos correspondentes no BI. Esses módulos exigem contratos próprios antes de integrar o aplicativo. O custo já importado não é faturamento, e o cadastro examinado ainda não fornece o mapeamento produto–NCM necessário para cruzar diretamente empresa e mercado.

Esta reorganização pertence aos fontes em desenvolvimento. Os pacotes e instaladores anteriormente publicados não recebem as mudanças automaticamente; a disponibilidade deve ser conferida no pacote de teste ou release correspondente.
