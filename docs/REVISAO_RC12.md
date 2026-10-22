# Revisão RC12 — cabeçalho simplificado

Removidos apenas os elementos solicitados nas duas imagens:

- Faixa de contexto abaixo do título: período e resumo de filtros.
- Selo Comex Stat no canto superior direito.

A expressão QML exclusiva da faixa também foi retirada. O layout usa o espaço liberado, mantendo título, marca, download, tema e preferências. Fonte/atualização continuam em Ajuda. Erros reais, escolha do período, filtros ativos, análises e documentos não mudaram.

O código Python de domínio, consulta, cache, cálculos, controladores, modelos de tabela e geradores foi comparado byte a byte com a RC11. Apenas QML e metadados de versão mudaram no aplicativo. Dois testes existentes foram ajustados para acompanhar a remoção do contexto, preservando as verificações de navegação, filtros e nomes de produtos nos registros.

Verificação executada em Linux/Qt offscreen: suíte de 358 testes com Python 3.14.8, incluindo 100 mil registros; 20 cenários de layout com cinco tamanhos, dois temas e duas bases; autoteste de abertura nativa e recursos de documentos. Evidências em EVIDENCIAS_RC12.json, LAYOUTS_RC12.json e PRESERVACAO_RC12.json.

Não houve alteração nas dependências nem nova conciliação online do Comex. O ZIP é de código-fonte e assistentes. Testes Linux não substituem homologação do instalador, DPI/GPU e Power BI Desktop no Windows.
