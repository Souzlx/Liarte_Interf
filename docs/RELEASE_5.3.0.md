LIARTE 5.3.0 amplia a análise mensal de Estoque e melhora a apresentação e a resposta do aplicativo Windows.

- Gráficos adaptados ao espaço da janela, com ampliação, leitura por cursor/teclado, eixos e rótulos mais claros. Início resume os resultados já carregados de Importações e Estoque.
- Análise mensal de estoque a custo, quantidades, vendas líquidas e giro mediano da fonte. Rankings ajudam a identificar maiores vendas, ausência de venda recente, menor giro e contribuições para as variações entre meses.
- Excel mensal com detalhamento completo do recorte, montagem mais rápida, validação antes de substituir o arquivo anterior e tratamento explícito de valores além da precisão numérica do Excel.
- Cancelamento, ordenação, paginação, recuperação da base local e encerramento do aplicativo aprimorados. Foco e rolagem corrigidos também em janelas compactas.
- Correções dos 29 achados da auditoria, com 84 regressões novas incorporadas à suíte. Os fontes foram consolidados e 101 arquivos residuais retirados; a base integrada e as licenças foram preservadas.

Quantidades continuam separadas por unidade. Meses ausentes e parciais são identificados; tempo sem venda não representa idade física de lote. As contribuições mensais mostram onde o valor variou, sem presumir compras, consumo interno ou outras causas ausentes da fonte. Os critérios estão no [guia da análise mensal](https://github.com/Souzlx/Liarte_Interf/blob/main/docs/ANALISE_MENSAL_530_RC2.md).

Importações mantém a consulta direta ao Comex Stat, os recortes por ano civil e a recuperação de pausas da fonte. Gráficos e filtros usam os resultados carregados. A validação HTTPS permanece ativa; limites e indisponibilidade da API ainda podem exigir espera. Bases válidas e preferências locais são preservadas na atualização.

Para atualizar, feche a versão anterior, extraia **todo o ZIP em uma pasta nova** e abra `LIARTE_Desktop/LIARTE_Desktop.exe`, mantendo `_internal` junto dele. Confira **5.3.0** em Ajuda. O pacote portátil Windows x64 inclui Python e dependências; não é necessário instalar Python. Atalhos antigos continuam apontando para a pasta anterior. O arquivo `SHA256SUMS.txt` permite conferir a integridade do ZIP.

A versão promove a prévia 5.3.0-rc.3, cuja validação foi confirmada pelo usuário. O pacote estável é publicado após os testes e autotestes dos quatro builds Windows. Os ensaios automatizados e seus limites estão documentados no repositório. Esta entrega contém o pacote portátil, sem instalador Setup; a versão 5.2.0 continua disponível no histórico de releases.
