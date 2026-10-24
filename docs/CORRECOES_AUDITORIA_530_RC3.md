# Correções da auditoria — 5.3.0-rc.3

A RC3 aplica as correções dos 29 achados confirmados na auditoria da revisão `e5be36410488dbba306a7b4ce49553213a777531`. É uma prévia da série 5.3; a versão estável 5.2.0 permanece separada. Os critérios da [análise mensal](ANALISE_MENSAL_530_RC2.md) continuam sendo a referência para estoque, vendas e giro.

## Alterações e regressões

| Achados | Correção | Regressões novas |
|---|---|---|
| A01 | Contadores de linha explícitos e estilos reutilizados eliminam as varreduras repetidas durante a montagem do Excel mensal. | `AuditInventoryExportTests` impede acesso a `Worksheet.max_row` no laço de montagem. |
| A02 | Texto incompatível com XML é recusado; o Excel temporário é validado e reaberto antes de substituir o anterior. | Caracteres de controle, U+FFFE/U+FFFF e surrogate inválido; arquivo anterior preservado. |
| A03 | Cancelamento propagado à análise, validação, preparação e exportação; estatísticas mensais calculadas por momentos esparsos, incluindo meses com zero. | `AuditStockCoreTests` e `InventoryDesktopAuditTests`: interrupção, equivalência estatística e prevalência do filtro mais recente. |
| A04–A05 | Leitura e gravação compartilham limites de registros e tamanho JSON; aridade, deflate inválido e números extremos viram erros de validação recuperáveis. | Cache inválido recupera a base integrada; limites são conferidos antes da publicação. |
| A06–A07 | Fechamento parcial é identificado e não produz comparação mensal completa; ausência de fonte de vendas permanece indisponível também no detalhe. | Meses incompletos e fonte de vendas ausente. |
| A08–A09 | A consulta exige HTTP 200. Travas do sistema operacional serializam requisições e preservam a maior pausa entre processos. | `EndpointStatusTests` e `ProcessPauseTests`, usando processos reais com `spawn`. |
| A10–A11 | Busca, índices, opções, preparação mensal e ordenação de bases grandes passam ao worker. A paginação usa a ordem já calculada. | Preparação fora da thread visual, paginação sem reordenar, cancelamento da ordenação e cabeçalho aplicado coerente. |
| A12–A14, A24 | Retorno de foco respeita a seção visível; Ctrl+F revela a busca; Início e diálogos revelam o controle focado; Produtos é reconhecido no fim da rolagem. | `AuditQmlTests`: teclado e geometria real em janela compacta, incluindo gráfico e leitura. |
| A15–A16 | Validador XLSX/OPC com orçamento de recursos verifica tipos de conteúdo, relacionamentos, referências e índices de texto antes do BI. Linhas esparsas não provocam alocação proporcional à última coluna referenciada. | `AuditSourceWorkbookTests`: referência fora do limite, XFD válido, índice negativo, XML corrompido, DTD/ENTITY e partes ausentes. |
| A17–A20 | Fluxos legados verificam abandono durante a espera; liberação SQLite pode ser repetida após falha; leitura interrompida tem recuperação limitada; falha municipal impede a publicação CLI. | `LegacyWaitAuditTests`, `LeaseReleaseAuditTests`, `InterruptedReadAuditTests` e `MunicipalCliAuditTests`. |
| A21 | Abrangência histórica considera somente os meses selecionados. | Recorte sem fechamento não herda locais de outro período. |
| A22–A23 | Quantidades são formatadas com Decimal. Valores além dos 15 dígitos significativos do Excel são exportados como texto decimal exato, com comentário e regra de leitura. | Arredondamento de 0,0055 e valores extremos reabertos com conteúdo exato. |
| A25–A27 | JSON/cache legado preserva Decimal; manifesto e comparações mantêm unidades inteiras e decimais exatos; ordenação auxiliar reconhece Decimal como número. | `ExactJsonAuditTests` e `AuditExactTotalsTests`, inclusive contexto Decimal reduzido e valores acima de 2⁵³. |
| A28–A29 | Falhas na publicação de ZIP/checksum restauram o par anterior; falha na própria restauração conserva cópias recuperáveis. Mudanças em `qmldir` e na base `.liarte` invalidam a preparação reutilizada. | `BuildAuditTests`: falhas em cada publicação, restauração bloqueada e fingerprint do registro QML. |

A saída programática aguarda a conclusão do worker cancelado antes de destruir a interface. Caso o primeiro prazo de espera expire, o controlador e os arquivos temporários permanecem vivos até a conclusão. Há regressões com QThread real para esse contrato.

As listas enviadas aos rankings visuais ficam limitadas aos 12 primeiros resultados de cada grupo. Totais, participações, filtros e fatos brutos continuam completos; a exportação não usa essa limitação visual. Registros mensais compartilham objetos quando possível para reduzir cópias em memória.

## Compatibilidade e limites

- Números usuais do Excel continuam numéricos. Valores extremos exportados como texto precisam ser tratados explicitamente em fórmulas; a soma automática do Excel ignora texto. O comentário da célula e a aba de critérios explicam essa escolha.
- O manifesto auxiliar da CLI passa ao schema 2. Totais usuais permanecem números JSON; decimais fora da representação segura são strings decimais exatas, acompanhadas do critério de codificação. Isso não altera o formato `.liarte` da base de estoque.
- Cancelamento durante abertura ou leitura bloqueada de socket ainda depende do retorno do transporte ou de seu timeout, de até 120 segundos no cliente nativo. Pausas de recuperação e operações locais verificam cancelamento entre lotes. Cancelar não publica resultados incompletos.
- Os tetos de arquivo e registros protegem a entrada, mas não garantem baixo consumo de RAM no máximo permitido. A análise mensal ainda materializa o histórico do recorte; bases grandes exigem memória compatível.
- Não foram acrescentados serviços, cache de respostas, consultas independentes de totais ou chamadas preventivas à API oficial. HTTP 200 válido não oferece uma conciliação independente de completude da fonte.
- Dias sem venda não representam idade de lote. Explicações para variações permanecem limitadas aos dados recebidos; não se inferem consumo interno, transferências ou causas comerciais ausentes da base.

## Limpeza e manutenção

A [limpeza separada](LIMPEZA_530_RC3.md) retirou 101 arquivos, 7.690.304 bytes do checkout, com hashes conferidos. Fontes canônicos, base integrada, exemplos e licenças foram preservados. Os seis manifestos antigos estão no [arquivo histórico](archive/source_rc9/README.md).

O workflow de testes agora roda em alterações de código por push/PR. A compilação dos quatro pacotes Windows e a publicação estável continuam manuais. As Actions usadas nos workflows estão fixadas por SHA verificado. A publicação de uma RC não substitui a versão estável.

Os resultados finais de testes, desempenho e compilação desta entrega serão registrados em `EVIDENCIAS_CORRECOES_530_RC3.json` e `VALIDACAO_WINDOWS_530_RC3.json`. Resultados Linux/offscreen não equivalem à homologação do Setup, Power BI Desktop, rede corporativa, leitor de tela ou DPI/GPU da empresa.
