# RC9 — interface discreta e conferência dos relatórios

A revisão parte da RC8 e abrange consultas, cache, contratos de dados, aritmética, exportações, apresentação Qt, empacotamento e metadados de instalação. Cadastro, análises, filtros e escopos de exportação foram preservados.

## Interface

Foram removidas as faixas repetidas sobre vários produtos, a cor de advertência nos títulos e as mensagens de sucesso de download. O indicador passa a se chamar **Média da seleção** quando abrange vários códigos. As referências de compra mantêm títulos constantes. O comparador apresenta uma única instrução para escolher um produto; as explicações ficam em **Como interpretar**.

Valores positivos com peso publicado igual a zero recebem informação discreta no indicador e nos detalhes ao passar o mouse. A indicação considera o intervalo do próprio indicador: último mês, três meses ou período inteiro. Não transforma zero em dado ausente nem estima peso. Erros de fonte, consulta, gravação e preferências continuam apresentados quando ocorrem.

## Extração e precisão

Cada novo lote detalhado é comparado a uma segunda consulta oficial, agrupada apenas por mês e NCM ou SH4. A comparação usa todas as métricas solicitadas e unidades inteiras. Registros omitidos, totais divergentes, identificações fora do período e controles repetidos bloqueiam o lote antes do cache. Falha no controle não equivale a total zero nem libera dados parciais.

O contrato do cache recebeu uma versão de conferência. Parcelas antigas precisam de uma nova consulta uma vez; parcelas conferidas continuam reutilizáveis. Filtros, ordenação, paginação e documentos não repetem essa consulta. São duas requisições adicionais por lote geral/municipal ainda não armazenado. É um custo deliberado de verificação, não uma alegação de que a extração ficou mais rápida.

Dinheiro é validado em centavos e peso em kg inteiros. CIF exige igualdade exata com FOB + frete + seguro. Não aceita divergência de um centavo, peso fracionário ou arredondamento provocado pelo contexto global de Decimal. As assinaturas de duplicidade também usam unidades exatas. Métricas JSON oficiais não são interpretadas como textos com separador de milhar.

## Documentos

O Excel acumula resumos em unidades inteiras. Após salvar, confere registros, identidades, métricas, totais, cadastro, abas mensais e distribuição por NCM e município/UF. Só conferir o total geral não detectava uma transferência indevida de valores entre grupos; essa lacuna foi fechada. Chamadas diretas ao gerador também rejeitam duplicidades na granularidade estatística.

Os formatos anteriores foram preservados. Se uma métrica contiver centavos, a célula monetária recebe duas casas para não escondê-los. Valores inteiros mantêm o formato atual. A coluna E municipal continua com largura 64 e o alinhamento vertical é central em todas as células.

O PDF acumula CIF em centavos e peso em inteiros. Seu agrupamento preserva NCM e URF originais: nomes comerciais ou portos abreviados não são chaves estatísticas. Dois NCMs diferentes chamados “Óleo de silicone”, por exemplo, deixam de ser fundidos pelo nome. Os códigos continuam fora das colunas impressas. Filtros, regras de relevância por observação, nomes comerciais, logo, A4 e cabeçalhos repetidos foram mantidos.

Excel/BI continuam completos para cadastro/período; PDF continua filtrado. A exportação recusa período divergente ou bases desalinhadas, mantém o destino anterior em falhas/cancelamentos e publica por substituição atômica. O progresso não volta de 100 para 99. SHA-256 é calculado em blocos de 1 MB, evitando outra cópia integral em memória. O diagnóstico registra as revisões das duas fontes e o estado da conferência de totais.

## Evidências e alcance

Veja `EVIDENCIAS_RC9.json`, `VALIDACAO_RC9.log`, `DOCUMENTOS_RC9.json` e `LAYOUTS_RC9.json`. Os exemplos reproduzem a captura oficial anterior de julho–setembro/2026. A conferência verifica bases exportadas, o Excel incorporado ao BI e totais históricos conciliados. Identidades e valores econômicos das bases são comparados exatamente; geometria e razões exibidas usam precisão de apresentação.

As tentativas ao vivo nesta revisão encontraram HTTP 429. Os CSVs oficiais consultados responderam HTTP 503. Não foi possível concluir nova conciliação online; nenhum resultado incompleto foi publicado. O novo controle automático é coberto por regressões com respostas capturadas e falhas controladas. A documentação atual da API foi consultada para o contrato das dimensões.

Qt e o pacote congelado foram verificados em Linux. Instalação/atalhos, DPI/GPU no Windows, execução DAX, atualização M e renderização no Power BI Desktop permanecem etapas de homologação na empresa. Não se promete imunidade absoluta a falhas da aplicação, da rede ou da fonte. Evidências anteriores mantêm seus nomes e datas.

## Fontes primárias

- API e dimensões: https://api-comexstat.mdic.gov.br/docs
- Contrato OpenAPI: https://api-comexstat.mdic.gov.br/docs/doc.yaml
- Bases e layouts: https://www.gov.br/mdic/pt-br/assuntos/comercio-exterior/estatisticas/base-de-dados-bruta
- Módulos: https://www.gov.br/mdic/pt-br/assuntos/comercio-exterior/estatisticas/perguntas-frequentes-faq/4-como-realizar-consultas
