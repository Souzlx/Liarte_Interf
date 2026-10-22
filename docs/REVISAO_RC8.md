# RC8 — leitura, navegação e análise na aplicação nativa

Base: ZIP RC7 enviado pelo usuário em 19/10/2026. A revisão aplica a avaliação das capturas da aplicação Qt. As correções de geração do Power BI feitas na RC7 foram preservadas.

## Período e filtros

Os campos de mês mantêm largura suficiente para o nome completo em português. O formulário de consulta tem largura limitada e os atalhos de período deixam de competir com o botão Consultar. A ação Último mês mantém seu comportamento anterior de consulta imediata; os demais atalhos preenchem o período para confirmar em Consultar.

Recolher oculta os seletores sem apagar critérios. Os filtros ativos continuam visíveis em etiquetas removíveis. Selecionar produto, na comparação de origens, expande os filtros e abre o seletor. A alteração dos meses continua pendente até a consulta; documentos não são emitidos para um período ainda não aplicado.

## Navegação e apresentação

Importações identifica o módulo; Resumo, Compras ou Registros recebem o único destaque de seção. O contorno de teclado usa `visualFocus`, separado da seleção de navegação e do foco obtido com o mouse. Contraste de textos secundários, contornos de painéis e tamanho de legendas foram ajustados sem trocar a identidade visual ou os arquivos da logo.

Explicações metodológicas ficam em Como interpretar. Avisos de peso incompleto ficam sempre junto dos indicadores afetados, mesmo com a explicação recolhida. A confirmação de Excel/BI é curta; a confirmação de sucesso do PDF continua suprimida. O atalho Baixar da barra superior e os botões de documentos usam o mesmo diálogo e o mesmo escopo anterior de exportação.

## Tabela para compras

A opção Visão de compras prioriza mês, produto, origem, UF, peso e valor/kg. A ordem e os campos se adaptam à base municipal, que continua em SH4 e FOB. Todas as colunas oferece os campos completos anteriores. NCM, SH4 e valores auxiliares continuam disponíveis nos detalhes e na cópia integral do registro.

Isso é uma projeção visual, implementada no modelo Qt. Cada coluna visível carrega seu índice de origem. Clicar em US$/kg ordena pelo preço exato no motor, não pelo número da posição da coluna na tela. A ordenação continua abrangendo todo o resultado antes de paginar. Os valores monetários permanecem alinhados à direita.

O mês fica compacto na visão de compras e completo na visão integral/detalhes. No porto, o nome aparece antes do código. O texto e a chave oficiais continuam disponíveis e os filtros usam a chave original. Alternar colunas não consulta a API, não altera o recorte e não reduz Excel, BI ou PDF.

## Preços e gráficos

Quando há vários códigos no recorte, o indicador é identificado como Média do conjunto. As referências mensais e de três meses também recebem essa indicação; o comparador de países continua exigindo um código. A regra de cálculo anterior foi preservada, incluindo a razão dos totais publicados quando há valor sem peso. Essa condição recebe aviso explícito; não se estima peso nem se excluem observações silenciosamente.

A nova opção Variação (%) mostra a mudança do valor CIF geral ou FOB municipal em relação ao mês imediatamente anterior dentro da seleção. O primeiro mês não possui base; uma base anterior zero também não produz percentual. Os cálculos usam os centavos inteiros e `Decimal`; apenas a geometria do gráfico usa ponto flutuante. Valores negativos são apresentados abaixo de zero, com a referência zero visível. Não se aplica uma média móvel à série percentual. A cópia e a tabela de valores usam unidade % e duas colunas, sem uma coluna vazia de média móvel.

O indicador do gráfico é preservado por sua chave ao trocar de base, independentemente da posição no seletor. Quando não existe na outra base (por exemplo, frete municipal), a tela retorna ao valor total; ao voltar, restaura a escolha anterior. Mudanças de paginação e preferências não recriam a lista de métricas.

O gráfico original de valores totais continua partindo de zero. Ampliar variação permanece disponível somente para razões por kg, com aviso de eixo ajustado.

## Preservação e evidências

- Os 20 arquivos de domínio e geradores, inclusive Comex, cache, filtros, ordenação e Excel/PDF/BI, são idênticos aos da RC7. Identidades Windows, atalhos, armazenamento e dependências permanecem estáveis.
- 254.490 células do Excel conferidas: nenhum valor alterado; formatos numéricos, alinhamentos e larguras iguais. A coluna E municipal continua com largura 64.
- PDF regenerado com os mesmos filtros comerciais: mesmo texto e número de páginas. Projeto Power BI validado estruturalmente: seis páginas, 85 contêineres visuais e 57 medidas.
- Layouts exercitados nas duas bases e temas, em seis tamanhos e três escalas Qt: 72 combinações sem avisos de QML. A conferência foi feita em Linux/offscreen, não em monitores Windows reais.
- O congelamento Linux abriu a aplicação nos dois temas, conferiu título/ícone, diálogo de salvamento e recursos de Excel, PDF/logo e BI. Esse binário Linux não é distribuído como instalador Windows.
- A suíte completa, incluindo 100 mil registros, é executada novamente a partir de uma extração limpa do ZIP. Resultado em VALIDACAO_RC8.log e EVIDENCIAS_RC8.json.

Os exemplos usam a captura oficial de julho–setembro/2026 já conciliada. Não houve nova extração HTTP nesta revisão. O ZIP contém fontes e assistentes; a compilação do Setup e a homologação de instalação, fontes/DPI/GPU e Power BI Desktop continuam sendo etapas no Windows. As verificações TOM/M/PBIR da RC7 são evidências históricas; a validação estrutural atual não equivale a executar DAX ou atualizar/renderizar o Desktop.

Referências técnicas primárias: [foco visual dos controles Qt 6.10](https://doc.qt.io/qt-6.10/qml-qtquick-controls-control.html#visualFocus-prop) e [larguras, modelos e relayout de TableView Qt 6.10](https://doc.qt.io/qt-6.10/qml-qtquick-tableview.html).
