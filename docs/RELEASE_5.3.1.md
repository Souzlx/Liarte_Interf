# LIARTE 5.3.1

A 5.3.1 consolida as funcionalidades da candidata 5.3.1-rc.2 no canal estável, com identificação final no aplicativo e no instalador. O escopo funcional da candidata foi mantido.

- **Interface por tarefa:** Panorama, Análise mensal e Produtos no Estoque; Resumo, Compras e Registros nas Importações. Filtros e seleções são preservados ao navegar, com detalhes apresentados sob demanda.
- **Filtros e gráficos:** aplicação conjunta do recorte de Estoque, gráficos alternados, leitura mensal por mouse ou teclado e ação explícita para analisar o mês selecionado. As origens do mercado permitem filtrar a consulta.
- **Alertas e comparação mensal:** limites configuráveis, investigação por produto, filial e unidade e comparação de dois meses, distinguindo posições comparáveis de mudanças na cobertura dos registros.
- **Desempenho e ordenações:** rankings de vendas por unidade em janelas de 1, 3 ou 6 meses, evolução mensal, maior ou menor giro da fonte, valor a custo, saldo e cobertura estimada. A ordenação antecede a paginação; valores ausentes ficam ao final e o Excel de posições acompanha a ordem aplicada.
- **Instalação e dados locais:** Setup por usuário, atalhos e runtime incluído. Atualizações preservam bases, backups e preferências; bases anteriores de Estoque podem ser restauradas pelo aplicativo.

## Instalar ou atualizar

Os arquivos desta entrega são o [Setup 5.3.1](https://github.com/Souzlx/Liarte_Interf/releases/download/v5.3.1/LIARTE_Desktop_5.3.1_Setup.exe), o [ZIP portátil](https://github.com/Souzlx/Liarte_Interf/releases/download/v5.3.1/LIARTE_Desktop_5.3.1_Windows_x64.zip) e [SHA256SUMS.txt](https://github.com/Souzlx/Liarte_Interf/releases/download/v5.3.1/SHA256SUMS.txt). Os três arquivos estão publicados na [release estável 5.3.1](https://github.com/Souzlx/Liarte_Interf/releases/tag/v5.3.1).

Feche a LIARTE e execute o Setup na mesma conta Windows usada pela 5.3.0 ou pela 5.3.1-rc.2. Abra o atalho criado pelo Setup e confira **5.3.1** em **Ajuda**. Os pacotes incluem Python, Qt e as dependências; o usuário não precisa instalar Python. Para o portátil, extraia o ZIP inteiro em uma pasta nova.

A atualização normal mantém o perfil existente. Não é necessário desinstalar a versão anterior nem apagar bases, backups ou preferências. A [5.3.0](https://github.com/Souzlx/Liarte_Interf/releases/tag/v5.3.0) e a [RC2](https://github.com/Souzlx/Liarte_Interf/releases/tag/v5.3.1-rc.2) permanecem como entregas históricas.

## Validação e limites

A tag `v5.3.1` aponta para `73339f650959a81473ab98b6b6f6b58f3023c563`. O [CI Linux](https://github.com/Souzlx/Liarte_Interf/actions/runs/40906447193) aprovou **1.070 testes**, sem skips, e os **18 testes de organização** também passaram. Os [quatro builds Windows](https://github.com/Souzlx/Liarte_Interf/actions/runs/40907105322) aprovaram 1.069 testes e ignoraram um teste exclusivo POSIX em cada execução. Os executáveis passaram nos autotestes nativos, sem avisos QML.

O ciclo real do Setup aprovou instalação nova, atalhos, atualização a partir da 5.3.0 e do Setup publicado da RC2, preservação de diretório, bases, backups, preferências e relatórios, desinstalação preservando o perfil e exclusão explícita dos dados com relatório externo intacto. Os downloads publicados passaram na conferência independente de SHA-256, CRC e manifesto interno. Consulte as [evidências da publicação](https://github.com/Souzlx/Liarte_Interf/blob/main/docs/EVIDENCIAS_INSTALADOR_531.json), a [matriz Windows](https://github.com/Souzlx/Liarte_Interf/blob/main/docs/VALIDACAO_WINDOWS_531.json) e o [autoteste do Setup](https://github.com/Souzlx/Liarte_Interf/blob/main/docs/AUTOTESTE_INSTALADOR_531.json).

O Setup da LIARTE não tem assinatura digital de editor. Os ensaios automatizados não substituem a conferência da rede, das políticas de instalação e das configurações de tela nos computadores de uso.

A base integrada de Estoque tem referência de **21/10/2026**; a última base válida importada localmente pelo usuário tem preferência. Não há conexão ao vivo com o ERP. Giro da fonte, cobertura estimada e tempo desde a última venda têm definições distintas e não representam a idade física dos lotes. Custo não representa faturamento. As hipóteses de variação ajudam a investigar os dados e não estabelecem suas causas.

Consulte o [guia de instalação e atualização](https://github.com/Souzlx/Liarte_Interf/blob/main/docs/INSTALACAO_531.md), o [guia da interface](https://github.com/Souzlx/Liarte_Interf/blob/main/docs/GUIA_INTERFACE_MODULAR.md), as [definições de desempenho e ordenação](https://github.com/Souzlx/Liarte_Interf/blob/main/docs/DESEMPENHO_PRODUTOS.md) e a [análise dos PBIX](https://github.com/Souzlx/Liarte_Interf/blob/main/docs/ANALISE_BI_E_EXPERIENCIA.md).
