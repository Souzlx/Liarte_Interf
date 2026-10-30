# Diretriz de análises e fontes

## Dados e indicadores

- Derive produtos, unidades, filiais, períodos e resultados dos dados aceitos. Não fixe códigos, datas ou conclusões comerciais nos cálculos de produção. Fixtures e demonstrações devem ser sintéticas e identificadas.
- Apresente análises por valores, diferenças, percentuais, séries, denominadores e critérios quantitativos. Não gere hipóteses causais, recomendações comerciais ou próximos passos por frases prontas, mesmo quando condicionadas por indicadores.
- Preserve nomes, unidades, fórmulas, períodos, fonte e mensagens de indisponibilidade necessários para interpretar os números. Definições matemáticas não são conclusões comerciais.
- Mantenha políticas de negócio explícitas e configuráveis. Um limite padrão não é um fato aprendido da base. Identifique o limite aplicado; não o apresente como recomendação automática de compra.
- Preserve precisão de centavos e quantidades, sinais e a diferença entre zero e ausência. Não some unidades diferentes, giros ou dias de posições. Custo não é receita; cobertura não mede idade dos lotes.

## Fontes e atualizações

- Separe adaptadores de origem, modelo normalizado, cálculos e apresentação. PBIX e uma futura integração SQL Server devem alimentar os mesmos contratos analíticos.
- Não execute conexões, SQL, M ou DAX encontrados em PBIX. A conexão SQL real depende do mapeamento autorizado das tabelas ou views e de suas transformações.
- Cada análise deve consumir uma versão consistente dos dados. Valide a leitura antes de publicá-la; resultados de gerações antigas ou canceladas não podem substituir os atuais.
- Identifique a revisão da fonte no cache. Inclusões, alterações, exclusões e correções retroativas devem invalidar os resultados afetados; não presuma que a base só acrescenta registros.
- Preserve a última base válida em falhas e identifique sua referência. Não apresente uma versão anterior ou de demonstração como atualização bem-sucedida.
- A integração SQL Server prevista é somente leitura. Não altere dados, esquema, índices, isolamento ou configurações administrativas automaticamente. Não use `NOLOCK` ou `READ UNCOMMITTED` para indicadores consistentes. `rowversion` isolado não detecta exclusões.
- Credenciais devem usar configuração segura, fora de código, documentação, fixtures, logs e capturas.

## Verificação

- Teste resultados com datas e identificadores distintos, alterações e exclusões retroativas, lacunas, unidades diferentes e atualizações concorrentes. Mesmos dados normalizados devem produzir os mesmos indicadores independentemente do adaptador.
- Registre novas classes em `verificar.py`. Antes de concluir mudanças de código, execute `python verificar.py --headless --volume`, além dos checks de organização definidos em [CONTRIBUTING.md](CONTRIBUTING.md).
- Mudanças de interface exigem conferência visual, teclado e janela compacta. Diferencie validação dos fontes, do executável e conferência manual no Windows. Publicar uma release é uma etapa separada de implementar uma melhoria.
