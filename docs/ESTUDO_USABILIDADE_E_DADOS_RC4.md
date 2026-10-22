# Estudo de usabilidade, dados e gráficos — RC4

Estudo aplicado à versão 5.0.0-rc.4, em 16/10/2026. O objetivo é apoiar a leitura
e comparação de importações por gestores e equipe comercial, preservando fonte,
valores, filtros e regras dos documentos. A revisão combina pesquisa primária,
inspeção do código, cenários automatizados e inspeção visual de telas Qt reais.

## 1. Decisões de experiência do usuário

As heurísticas de Nielsen e a aplicação dessas heurísticas a sistemas empresariais
orientaram três critérios: contexto reconhecível, ações encontráveis e recuperação
de escolhas sem perda de trabalho. Uma explicação longa não substitui uma ação
com nome claro ou um resultado visível. O fluxo continua sendo escolher período,
consultar, analisar e baixar; os novos acessos encurtam a navegação nesse fluxo.

| Necessidade observada no código | Aplicação na RC4 | Critério verificável |
| --- | --- | --- |
| Encontrar uma seção numa página extensa | Resumo, Compras e Registros na lateral | Saltos respeitam os limites de rolagem e preservam os filtros. |
| Reconhecer o recorte após rolar | Período, produto comercial e filtros no topo | Contexto permanece visível e identifica período pendente. |
| Preencher intervalos frequentes | Últimos 3, 6 e 12 meses publicados | Preenchimento não consulta a rede; confirmação continua explícita. |
| Baixar sem procurar botões ao final | Menu Baixar no cabeçalho | Mesmo diálogo e mesmos escopos dos botões existentes. |
| Ler valores sem depender de hover | Teclado e Ver valores | Home/End/setas, tabela completa e cópia com unidades corretas. |
| Corrigir um recorte vazio | Orientação e Limpar filtros no comparador | Excel/BI completos permanecem disponíveis; PDF sem linhas fica desabilitado. |
| Comparar países além dos primeiros oito | Ordenação e Mostrar mais | Filtragem/ordenação precedem o limite de exibição. |

A apresentação mantém hierarquia, cores e recursos originais da LIARTE. Animações
servem à orientação espacial ou à entrada de dados; Reduzir animações também
interrompe a rolagem programada em andamento. Menus e diálogos respeitam a navegação
modal e impedem consultas por atalhos enquanto outra escolha está em aberto.

## 2. Estatística: significado do que aparece

Os dados são agregações mensais do Comex Stat. Uma linha não representa um pedido
ou fornecedor identificado. NCM é mais específico que SH4, mas ainda pode reunir
qualidades e apresentações diferentes. A base municipal usa SH4 e domicílio fiscal;
seus valores não são combinados aos da base geral. O manual/FAQ do MDIC sustenta
essa separação conceitual. O estudo do FMI sobre valores unitários alerta que
mudanças de composição podem afetar sua interpretação como preços.

As relações utilizadas são descritivas:

- **Valor unitário:** soma de dólares / soma de kg. Não é média simples dos valores
  por kg de cada linha ou país. O CIF geral soma FOB, frete e seguro; municipal usa FOB.
- **Referência móvel de preço:** soma dos valores dos três meses / soma de seus kg,
  exigindo três meses consecutivos com peso positivo dentro do intervalo selecionado.
- **Média mensal de valor ou peso:** soma dos três meses / 3. O resultado pode conter
  frações, mesmo quando o peso mensal publicado é inteiro.
- **Variação mensal:** `(mês final / mês anterior - 1) × 100`. Base zero ou ausente
  não define percentual. A variação início–fim é identificada separadamente.
- **Concentração:** participação dos até três países de maior valor no total do
  recorte, incluindo países que não aparecem entre as barras visíveis.
- **Cobertura por país:** meses com peso positivo / meses selecionados. Essa informação
  descreve presença temporal; não é tamanho de amostra de pedidos ou grau de confiança.

Médias móveis suavizam a série e ajudam a examinar padrões, como explica o NIST.
Séries temporais podem ter tendência, sazonalidade e dependência entre observações;
essas propriedades exigem tratamento próprio em modelos inferenciais. A RC4 apresenta
referências históricas e cobertura observada, sem atribuir certeza estatística a
agregações heterogêneas. Condições de qualidade, rota e quantidade continuam relevantes
na negociação. CIF não é custo nacionalizado completo.

## 3. Ausências, zeros, pesos e unidades

Preço sem kg total positivo fica indisponível. A série preserva lacunas e não liga
esses pontos como se o preço fosse zero. Valores declarados com kg zero permanecem
nos totais publicados e geram nota de qualidade. Um mês sem importação pode ter valor
ou peso zero; isso tem significado distinto de preço indisponível.

Cálculos usam centavos inteiros, Decimal e razões exatas. A ordenação de países por
US$/kg usa Fraction antes da formatação, para que rótulos arredondados ou floats não
invertam a comparação. A tabela/cópia dos gráficos usa dólares e kg completos,
embora a geometria possa usar US$ milhões ou mil kg. Essa distinção é testada por
valores conhecidos e pela soma dos dados copiados.

## 4. Gráficos e percepção

A orientação do ONS para eixos e linhas levou às seguintes escolhas:

- Escala completa com base zero permanece como padrão. Barras continuam com base zero.
- Para pequenas diferenças de preço, Ampliar variação oferece eixo ajustado, com
  indicação explícita. A área preenchida é removida quando a base do eixo é cortada.
- Marcadores ajudam a identificar observações em séries curtas. Lacunas permanecem
  visíveis; não há interpolação de valores ausentes.
- Linha mensal e média móvel usam traço e legenda distintos, além de cor. Ambas
  compartilham a mesma unidade/eixo.
- A leitura selecionada continua visível; teclado e tabela oferecem caminhos
  alternativos à interação com o mouse.

A diretriz do ONS para gráficos interativos reforçou que controles devem ajudar a
responder perguntas concretas. O comparador, por isso, oferece peso mínimo, ordenação
por volume/valor unitário e mais origens, mantendo a média de referência claramente
associada ao recorte principal. Alterar esses controles não muda o documento gerado.

## 5. Decisão técnica em PySide6/Qt

Foram consultadas as APIs Qt 6.10 de acessibilidade e gráficos, as recomendações
de desempenho Qt Quick e a documentação Qt Graphs. O módulo Qt Charts foi marcado como obsoleto (deprecated)
a partir de Qt 6.10. A aplicação já usa Qt Quick com um renderizador
2D apropriado às séries mensais e mantém essa arquitetura e suas dependências.

Curva, média e marcadores são pintados juntos. A revelação modifica o recorte no
scene graph; mover foco/seleção não repinta o Canvas. A tabela de valores só cria
linhas quando o diálogo abre. O núcleo agrega no worker, o controlador reaproveita
a apresentação e os controles de leitura não fazem novas consultas HTTP.

Papéis, nomes, descrições e foco são expostos ao framework de acessibilidade Qt.
O gráfico anuncia o valor selecionado e instruções de navegação, enquanto a tabela
oferece todos os meses. Os testes verificam a interface QAccessible, o teclado e
os dados copiados; a experiência com Narrador exige conferência no Windows real.

## 6. Validação e avaliação com usuários

A entrega contém logs, conciliação por SQL, conferência dos documentos e imagens
Qt. O ensaio de volume usa 100 mil linhas sintéticas e conta eventos da interface.
As análises numéricas adicionais usam captura oficial previamente reconciliada.
Os resultados detalham sua origem e não são apresentados como teste com pessoas.

Para avaliação na LIARTE, usar tarefas reais e registrar conclusão, tempo, erros,
retornos e dúvidas: consultar três meses de um produto; comparar origens com volume
mínimo; ler um mês pelo teclado; recuperar um recorte vazio; gerar os documentos
com filtros ativos. Observar se o usuário reconhece CIF/FOB, referência ponderada,
base municipal e escopos de Excel/PDF sem orientação prévia. Não foram inventados
resultados de participantes ou tempos de uso humano.

## Fontes consultadas

1. [NN/g — heurísticas de usabilidade](https://www.nngroup.com/articles/ten-usability-heuristics/).
2. [NN/g — aplicações complexas](https://www.nngroup.com/articles/usability-heuristics-complex-applications/).
3. [NN/g — divulgação progressiva](https://www.nngroup.com/articles/progressive-disclosure/).
4. [ONS — eixos e grades](https://service-manual.ons.gov.uk/data-visualisation/guidance/axes-and-gridlines).
5. [ONS — gráficos de linha](https://service-manual.ons.gov.uk/data-visualisation/chart-types/line-chart).
6. [ONS — interação e animação](https://service-manual.ons.gov.uk/data-visualisation/guidance/interactive-charts-and-animations).
7. [NIST — séries temporais](https://www.itl.nist.gov/div898/handbook/pmc/section4/pmc4.htm).
8. [NIST — médias móveis e suavização](https://www.itl.nist.gov/div898/handbook/pmc/section4/pmc42.htm).
9. [FMI — valores unitários e índices de preços](https://www.imf.org/en/publications/wp/issues/2016/12/31/do-unit-value-export-import-and-terms-of-trade-indices-represent-or-misrepresent-price-20943).
10. [MDIC — FAQ](https://www.gov.br/mdic/pt-br/assuntos/comercio-exterior/estatisticas/perguntas-frequentes-faq) e [manuais](https://www.gov.br/mdic/pt-br/assuntos/comercio-exterior/estatisticas/manuais-e-notas-metodologicas).
11. [Qt 6.10 — desempenho Qt Quick](https://doc.qt.io/qt-6.10/qtquick-performance.html).
12. [Qt 6.10 — acessibilidade QML](https://doc.qt.io/qt-6.10/qml-qtquick-accessible.html).
13. [Qt 6.10 — Qt Graphs](https://doc.qt.io/qt-6.10/qtgraphs-index.html) e [Qt for Python](https://doc.qt.io/qtforpython-6.10/PySide6/QtGraphs/index.html).

14. [Qt 6.10 — situação do Qt Charts](https://doc.qt.io/qt-6.10/qtcharts-overview.html).
