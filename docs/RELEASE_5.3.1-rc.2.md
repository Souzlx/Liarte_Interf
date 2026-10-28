Prévia do LIARTE que reúne as melhorias de análise e organização do Estoque em um novo instalador Windows.

- **Interface por tarefa:** Panorama, Análise mensal e Produtos no Estoque; Resumo, Compras e Registros nas Importações. Filtros e seleções são preservados ao navegar, com detalhes apresentados sob demanda.
- **Filtros e gráficos:** recorte de Estoque aplicado em conjunto, gráficos alternados, leitura mensal por mouse ou teclado e ação explícita para analisar o mês selecionado. As origens do mercado podem ser usadas para filtrar a consulta.
- **Alertas e comparação mensal:** limites configuráveis, investigação por produto/filial/unidade e comparação de dois meses, separando posições comparáveis de mudanças na cobertura dos registros.
- **Desempenho dos produtos:** rankings de vendas por unidade e janelas de 1, 3 ou 6 meses, evolução mensal, cobertura estimada e hipóteses a verificar sobre as variações.
- **Ordenações:** maior ou menor giro mensal da fonte, valor a custo, saldo e cobertura. A lista evidencia o indicador escolhido. As posições são ordenadas antes da paginação, com valores ausentes ao final e quantidades separadas por unidade; o Excel de posições acompanha a ordem aplicada.
- **Instalação e dados locais:** Setup por usuário, atalhos e runtime incluído. Atualizações preservam bases, backups e preferências. O aplicativo mantém a restauração de bases anteriores de Estoque.

Esta é a candidata **5.3.1-rc.2**. O fluxo de publicação disponibiliza Setup, ZIP portátil e `SHA256SUMS.txt` somente após validar os quatro executáveis Windows e o ciclo de instalação, atualização e desinstalação. A versão estável **5.3.0** permanece disponível.

Para atualizar, feche a LIARTE e execute `LIARTE_Desktop_5.3.1-rc.2_Setup.exe` na mesma conta Windows da instalação anterior. Confira **5.3.1-rc.2** em Ajuda. Não é necessário instalar Python. Para usar o portátil, extraia o ZIP inteiro em uma pasta nova.

Giro da fonte, cobertura estimada e tempo sem venda têm definições distintas; não representam a idade física dos lotes. Custo não foi convertido em faturamento. A revisão dos PBIX documenta fórmulas e recortes a conferir e não altera os arquivos originais nem inclui seus dados privados no repositório.

Consulte o [guia de instalação e atualização](https://github.com/Souzlx/Liarte_Interf/blob/main/docs/INSTALACAO_531_RC2.md), o [guia da interface](https://github.com/Souzlx/Liarte_Interf/blob/main/docs/GUIA_INTERFACE_MODULAR.md) e as [definições de desempenho e ordenação](https://github.com/Souzlx/Liarte_Interf/blob/main/docs/DESEMPENHO_PRODUTOS.md).
