# Revisão RC11 — continuidade da interface

A revisão elimina a impressão de recarregamento nas operações locais, preservando o fluxo e os critérios da RC10.

## Causas reproduzidas

Cada mudança de página criava um worker de consulta, notificava progresso global, mostrava um painel que aumentava a altura da tela e reiniciava o modelo da tabela/colunas. Esses passos ocorriam mesmo com a ordenação e os totais já prontos em memória.

## Alterações

- Uma página pronta é obtida do recorte/ordenação concluídos, sem rede, filtragem ou agregação. O acesso ocorre somente quando não há worker de consulta em execução. A identidade da fonte, período, base, filtros, busca e ordenação precisam corresponder. Cache ausente ou descartado segue pelo worker cancelável existente.
- Clicar em Consultar continua pelo caminho de revalidação da fonte, inclusive ao consultar novamente o mesmo período. Atualização forçada também impede reutilização da página. Solicitações pendentes preservam essa distinção.
- A tabela usa notificações de células e inserção/remoção de linhas para paginação e filtros. Cabeçalhos e colunas continuam existentes. Reset de esquema é reservado à mudança real entre NCM/CIF e SH4/FOB ou à mudança de perfil de colunas.
- Progresso de download/consulta oficial permanece disponível. Operações locais não inserem esse painel. Após 180 ms, uma linha fina indeterminada na tabela informa atividade sem alterar o layout; desaparece ao concluir ou cancelar, sem notificação.
- Transição da tabela de 140 ms, com opacidade entre 90% e 100%; o conteúdo nunca é apagado para animar. Movimento reduzido e janela oculta interrompem o efeito. A seleção das abas recebe uma mudança discreta de cor. Abas continuam operáveis durante cálculos locais canceláveis.
- Seleções rápidas, cancelamento, janela de detalhes e bloqueio de exportação durante filtros pendentes mantêm o comportamento de segurança existente. Excel/BI continuam usando o catálogo/período completos; PDF continua usando os filtros da base geral e suas regras comerciais.

## Validação

24 regressões novas verificam resultado exato das páginas em cache versus consulta normal, mudança de fonte, ausência/expulsão de cache, resultados vazios, revalidação explícita, serialização com worker ativo, cancelamento e cliques rápidos entre bases. A reprodução visual também compara as células com o modelo e a imagem antes/depois de uma reexposição completa da janela. O helper dos testes agora processa DeferredDelete, reproduzindo a limpeza do loop nativo exec() e evitando imagens de delegates que já aguardam destruição; esse helper não integra o aplicativo distribuído. O contrato de inserção/remoção do modelo Qt foi conferido por QAbstractItemModelTester em modo Fatal. Testes Qt verificam posição da rolagem, altura do painel, cabeçalhos estáveis, análises preservadas e movimento reduzido.

O ensaio comparativo usa o mesmo conjunto sintético de 100 mil registros em Linux/Qt offscreen e dez mudanças de página. Na RC10: dez resets de tabela, dez notificações de colunas, progresso global e variação de altura de 126 para 181 px. Na RC11: nenhum reset, nenhuma notificação de colunas e altura constante de 126 px. Mediana observada: aproximadamente 53,5 ms para 10,9 ms por mudança de página. São medições locais de um ensaio, não garantia de latência/FPS em outros equipamentos. Evidências NAVEGACAO_ANTES_RC11.json e NAVEGACAO_DEPOIS_RC11.json.

A suíte completa, os runtimes testados, os layouts e o autoteste do pacote compilado estão registrados em EVIDENCIAS_RC11.json. Os geradores e exemplos foram comparados com a RC10; detalhes em PRESERVACAO_RC11.json.

## Limites

Ensaios executados no Linux, incluindo Qt offscreen, capturas oficiais anteriores e dados sintéticos identificados. Não houve nova conciliação online do Comex. A API, os valores monetários/peso e a geração dos documentos mantêm os critérios anteriores. A primeira preparação de um recorte ainda pode exigir processamento em segundo plano; uma nova consulta de período continua dependendo da fonte e do cache oficial.

Disponibilidade de dependências e teste congelado Linux não equivalem à execução no Windows. Homologação de Setup, atalhos, DPI/GPU e atualização/renderização no Power BI Desktop continuam sendo etapas Windows. O ZIP inclui fontes e assistentes; não contém Setup Windows já compilado.

## Referências Qt

- Modelo e notificações incrementais: https://doc.qt.io/qt-6.10/qabstractitemmodel.html
- Trabalho assíncrono, perfil de execução e preservação do loop de eventos: https://doc.qt.io/qt-6.10/qtquick-performance.html
- TableView e reutilização dos itens: https://doc.qt.io/qt-6.10/qml-qtquick-tableview.html

- Limpeza diferida nos testes Qt: https://doc.qt.io/qt-6.10/qcoreapplication.html#processEvents
