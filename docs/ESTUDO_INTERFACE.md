# Estudo de interface — 16/10/2026

Objetivo: uma área de trabalho corporativa para analisar importações, com conteúdo
legível, ações previsíveis e identidade LIARTE. A pesquisa usou fontes primárias;
nenhum código, imagem ou tema de outro software foi copiado. O frontend continua
PySide6/Qt Quick 6.10.3, separado das regras Python já testadas.

## Referências e aplicação

| Referência | Decisão aplicada à LIARTE |
| --- | --- |
| Qt Quick, boas práticas | Controles Qt existentes estilizados sobre Basic; componentes reutilizáveis; eventos de interação explícitos. |
| Qt Quick, desempenho/Canvas | Evitar JavaScript e upload da textura por quadro; curva estática com revelação pelo recorte, guia de hover independente. |
| Qt Quick, layouts responsivos | Reorganizar a composição conforme a largura; meses por extenso; rolagem e diálogos limitados à janela. |
| Qt, acessibilidade | Nomes acessíveis nos ícones, foco, teclado, contraste e opção de reduzir movimento. |
| MuseScore Studio, manual da interface | Área central de trabalho e separação entre tarefas e opções secundárias; ajuda disponível sob demanda. Referência visual/organizacional. |
| QGroundControl, UI e múltiplos dispositivos | Componentes consistentes e separação QML/controlador, com layout adaptativo. Referência de estrutura Qt/QML. |

O resultado é uma interpretação própria para análise mercadológica, não uma cópia
de editor de partituras ou estação de controle. Tipografia, cores e hierarquia
seguem a marca já existente, com os arquivos originais preservados.

## Critérios

- Período e filtros aparecem antes dos resultados. O período aplicado fica junto
  dos indicadores; alterar meses ainda exige aplicação explícita.
- Valor principal recebe contraste; peso, preço ponderado e códigos mantêm
  alinhamento e formato. Valores exibidos são finais, sem animação de contagem.
- Evolução mensal usa eixo com zero e curva sem suavização que invente valores.
  A faixa de preenchimento é discreta; hover e acessibilidade expõem os pontos.
- Origens mostram participação real no total; barra e percentual são coerentes.
- Somente avisos relevantes aparecem no fluxo: tarefa, falha, resultado anterior,
  seleção pendente e uso de dados armazenados. Textos sobre cache, arquitetura,
  módulos futuros e tempo interno não ocupam a área de análise.
- Escopos de exportação continuam claros em Ajuda/tooltips; com filtros ativos,
  uma nota curta distingue período completo (Excel/BI) e seleção atual (PDF).
- Movimento é curto, finito e restrito ao feedback. Não há animação decorativa
  permanente ou deslocamento de controles enquanto se navega.

## Evidência e limites

O teste de oito transições com doze pontos mediu 16 pinturas Canvas por transição
na RC1 e uma na RC2. A duração passou de 230 para 260 ms. Isso reduz trabalho de
pintura, não significa dezesseis vezes mais FPS. Redução de movimento e guia de
hover foram testados separadamente. Contraste de texto normal e cartões foi
calculado nos dois temas, com razão mínima 4,5:1 nos pares avaliados. Isso não é
certificação completa de acessibilidade.

Foram verificados 96 layouts em Qt real offscreen; teclado, filtros, busca, botões
e documentos fazem parte da suíte automatizada. Leitores de tela, GPU, monitores
e desempenho de renderização Windows ainda precisam de homologação no ambiente
da empresa. Não é possível provar imunidade absoluta a falhas com testes finitos.

## Fontes

- https://doc.qt.io/qt-6.10/qtquick-bestpractices.html
- https://doc.qt.io/qt-6.10/qtquick-performance.html
- https://doc.qt.io/qt-6.10/qtquicklayouts-responsive.html
- https://doc.qt.io/qt-6.10/qml-qtquick-canvas.html
- https://doc.qt.io/qt-6.10/qml-qtquick-animator.html
- https://doc.qt.io/qt-6.10/accessible-qtquick.html
- https://handbook.musescore.org/navigation/the-user-interface
- https://docs.qgroundcontrol.com/Stable_V5.0/en/qgc-dev-guide/user_interface_design/index.html
- https://docs.qgroundcontrol.com/Stable_V5.0/en/qgc-dev-guide/user_interface_design/multi_device_pattern.html


## Continuação RC3 — identidade e referências de compra (16/10/2026)

- [Microsoft: AppUserModelIDs](https://learn.microsoft.com/en-us/windows/win32/shell/appids):
  o mesmo identificador deve unir processo e atalhos; omitir a versão preserva
  o agrupamento em atualizações. Aplicado antes de mostrar a interface.
- [Microsoft: SetCurrentProcessExplicitAppUserModelID](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nf-shobjidl_core-setcurrentprocessexplicitappusermodelid)
  e [SHGetPropertyStoreFromParsingName](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nf-shobjidl_core-shgetpropertystorefromparsingname):
  assinaturas, HRESULT e repositório de propriedades implementados sem pywin32.
- [Qt 6.10: QWindow::setIcon](https://doc.qt.io/qt-6.10/qwindow.html#setIcon)
  e [QGuiApplication](https://doc.qt.io/qt-6.10/qguiapplication.html):
  ícone padrão, ícone efetivo da janela e display name são atribuições distintas.
- [Inno Setup: Icons](https://jrsoftware.org/is6help/topic_iconssection.htm):
  AppUserModelID também definido nos dois atalhos instalados.
- [MDIC: FAQ](https://www.gov.br/mdic/pt-br/assuntos/comercio-exterior/estatisticas/perguntas-frequentes-faq)
  e [layout oficial](https://www.gov.br/mdic/pt-br/assuntos/comercio-exterior/estatisticas/base-de-dados-bruta):
  NCM e SH4/município possuem granularidades distintas. Valor unitário observado
  não equivale a preço de produto/qualidade identificados. As fórmulas de média
  móvel/variação desta aplicação são escolhas analíticas documentadas, não um
  índice de preços oficial calculado pelo MDIC.

Escolhas: um gráfico com indicador alternável e unidade explícita; mesmo eixo
para a linha mensal e sua média; nenhum eixo secundário ambíguo ou projeção.
Comparador usa volume, preço e referência ponderada, sem rotular um país como
fornecedor mais rentável. O mínimo por país ajuda a examinar volumes relevantes,
com escopo local explicado. Informações metodológicas ficam junto ao comparador
ou em tooltips, com interface principal preservada. Janelas pequenas mostram
preço/peso essenciais e mantêm os outros dados nos detalhes.
