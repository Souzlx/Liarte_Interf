# Prévia 5.3.0-rc.1 — interface e gráficos

Esta revisão melhora a apresentação de Importações e Estoque. A página Início
resume os resultados já carregados e identifica o período, o recorte, a base
e a moeda de cada módulo. Os atalhos abrem o módulo preservando a consulta.

Os painéis dos gráficos usam a largura disponível e a altura do conteúdo,
com títulos alinhados, valores de referência destacados e textos que podem
quebrar linha. Os rótulos mensais reduzem a densidade em janelas pequenas,
mantendo o primeiro e o último mês acessíveis. A margem dos eixos considera
a largura dos números, incluindo sinais negativos e valores grandes.

**Ampliar** abre o gráfico com os mesmos pontos, unidade, escala e opções
de apresentação. A leitura por cursor e teclado continua disponível. O
gráfico de origens apresenta valores monetários e participação; o ranking
de capital reorganiza nomes, valores e percentuais conforme o espaço.

O resumo, a troca de indicador e a ampliação usam os dados já carregados.
Não iniciam consultas adicionais. Os cálculos financeiros, a cobertura e o
giro da fonte, os denominadores, as unidades e a separação NCM/CIF de
SH4/FOB foram preservados. Meses ausentes continuam sem valor; a média móvel
continua exigindo os meses correspondentes. A animação usa revelação visual,
sem repintar a curva a cada frame ou a cada movimento do cursor.

As regressões verificam os eixos, lacunas, teclado, movimento reduzido,
cartões iniciais, preservação de filtros, abertura e redimensionamento dos
gráficos e ausência de novas chamadas de rede nesses controles.

As capturas desta revisão usam exclusivamente dados sintéticos. Elas servem
para avaliar o layout e não representam resultados reais da empresa ou da
API. A versão estável 5.2.0 permanece disponível no GitHub Releases.

## Capturas com dados sintéticos

Resumo inicial, com resultados de exemplo dos dois módulos:

![Início com dados sintéticos](preview_530_rc1/inicio.png)

Importações, com série mensal e participação das origens de exemplo:

![Gráficos de importações com dados sintéticos](preview_530_rc1/importacoes.png)

Estoque, com fechamentos e oito produtos de exemplo:

![Gráficos de estoque com dados sintéticos](preview_530_rc1/estoque.png)

Importações em uma janela de 500 pixels, usando dados sintéticos:

![Importações em janela compacta com dados sintéticos](preview_530_rc1/importacoes_compacto.png)

Estoque em tema escuro, usando dados sintéticos:

![Estoque em tema escuro com dados sintéticos](preview_530_rc1/estoque_escuro.png)
