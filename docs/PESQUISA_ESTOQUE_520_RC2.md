# Critérios de revisão — Estoque 5.2.0-rc.2

Pesquisa e aplicação realizadas em 21/10/2026. O objetivo foi tornar a leitura
comparável à de gráficos empresariais do Excel, com controles nativos do aplicativo.
As fontes abaixo orientam a implementação; não substituem a conciliação da base.

| Referência primária | Critério aplicado |
|---|---|
| [Microsoft Excel — criar e personalizar gráficos](https://support.microsoft.com/en-us/excel/get-started/create-a-chart-from-start-to-finish) | Título, eixos, unidades, legenda e rótulos de valores explícitos. Linhas para evolução, colunas como alternativa e para vendas mensais no detalhe. |
| [Microsoft — boas práticas de dashboards](https://learn.microsoft.com/en-us/power-bi/create-reports/service-dashboards-design-tips) | Hierarquia de indicadores, pouco ruído, cores consistentes, escalas identificadas e separação de quantidades com unidades diferentes. |
| [Microsoft — exibição de eixos](https://support.microsoft.com/en-us/office/change-the-display-of-chart-axes) | Intervalos regulares e rótulos espaçados segundo a largura disponível. Valor de cada observação acessível mesmo quando o rótulo não cabe. |
| [Qt 6.10 — Popup](https://doc.qt.io/qt-6.10/qml-qtquick-controls-popup.html) | Sugestões sobrepostas, fechamento com Esc/clique externo, sem retirar o foco do campo durante a digitação. Posição/altura limitadas ao espaço disponível. |
| [Qt 6.10 — ListView](https://doc.qt.io/qt-6.10/qml-qtquick-listview.html) | Lista virtualizada e sugestões limitadas; teclado e rolagem, evitando um ComboBox com mais de dois mil produtos. |
| [Qt 6.10 — Canvas](https://doc.qt.io/qt-6.10/qml-qtquick-canvas.html) | Redesenho apenas com mudança de dados, tamanho, tema ou apresentação. Animação por recorte no scene graph; não redesenhar a textura a cada quadro. |
| [NIST — coeficiente de variação](https://www.itl.nist.gov/div898/software/dataplot/refman2/auxillar/coefvari.htm) | CV = desvio padrão amostral / média. Bloqueio para média não positiva e volume líquido mensal negativo; mínimo de três meses completos como política conservadora do módulo. |

## Decisões e verificação

- O catálogo é indexado uma vez por base. Código exato tem prioridade; depois prefixo,
  nome e demais correspondências. Acentos/maiúsculas não alteram o resultado; todos
  os termos precisam corresponder. Não se aproximam automaticamente nomes químicos.
- Filtrar texto é uma busca ampla; selecionar uma sugestão define um produto exato
  e limpa a busca anterior. Gráficos, indicadores, tabela e Excel seguem o mesmo recorte.
- O recurso integrado contém apenas os dados necessários ao estoque, sem o PBIX
  original, clientes, pedidos ou contas. O arquivo e o manifesto entram no pacote
  Python e na compilação Windows. A cópia válida do usuário tem preferência; falhas
  de leitura permitem recuperar o recurso integrado com registro do problema.
- Saldo atual continua sendo saldo da data da base. Período de vendas não reconstrói
  inventários passados. Históricos ausentes não recebem zero nem linha interpolada.
- Variação mensal = (último fechamento / fechamento anterior − 1) × 100, somente
  entre meses consecutivos e com denominador positivo. Não se procura um mês mais
  antigo para preencher uma lacuna. A data do fechamento fica visível.
- Média móvel usa apenas três meses consecutivos presentes. Mudança de capital não
  recebe indicação verde/vermelha de bom/ruim: aumento de estoque não é lucro.
- ABC compara centavos com limites inteiros (80/95%), sem arredondamento binário na
  decisão de classe. O produto que atravessa o limite permanece na classe anterior.
- Médias, desvios e CV excluem meses parciais. Meses observados sem vendas são zero;
  meses anteriores ao início da observação global são indisponíveis. A base não
  informa a data de início de atividade de cada SKU; a janela é a do recorte da fonte.
- Exemplo sintético auditado: vendas mensais de 10, 0 e 30 KG têm média 13,333 KG,
  desvio amostral 15,275 KG e CV de aproximadamente 114,56%. Com 150 KG atuais e
  40 KG vendidos em 90 dias, a cobertura descritiva é 337,5 dias. Não é previsão de
  demanda nem cobertura por consumo industrial.
- Giro e dias fornecidos pelo BI não foram redefinidos. Valores negativos/extremos
  e códigos históricos sem cadastro continuam preservados. Sem acesso à origem SQL,
  conciliar a extração não equivale a certificar a fórmula de origem desses campos.

Resultados da conciliação, ensaios de interface e regressão estão nos arquivos
`CONCILIACAO_ESTOQUE_520_RC2.json`, `INTEGRACAO_ESTOQUE_520_RC2.json`,
`LAYOUTS_ESTOQUE_520_RC2.json` e `EVIDENCIAS_ESTOQUE_520_RC2.json`.
