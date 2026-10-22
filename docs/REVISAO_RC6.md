# Revisão RC6 — Power BI

## Problemas corrigidos

A referência RC5 tinha sete diagnósticos do CLI oficial de autoria: schema PBIP ausente, metadados de plataforma ausentes, referência byConnection nula junto de byPath, divergência no nome do tema, propriedade de tabela inválida e duas projeções de tooltip usando coluna onde se exigia medida. A RC6 passa na mesma validação sem erros ou avisos.

A organização semântica também foi revista: relação muitos para muitos direta substituída por dimensões e ponte, calendário mensal ordenado, nome comercial associado ao NCM único, município contado por cidade + UF e valores monetários fixed decimal. Campos brutos numéricos ficam ocultos, sem soma implícita de preços por kg.

Máscaras foram testadas com o TmdlSerializer real: as aspas literais de US$, kg, t e /kg usam a sintaxe TMDL correta. O caminho M protege também a sequência `#(` em nomes de pasta, além de aspas, e mantém substituição literal no iniciador PowerShell para não interpretar `$` no caminho como referência regex.

## Refino de leitura

Seis páginas com identidade LIARTE, margens e tipografia regulares, logo proporcional, navegação e filtros separados por universo. Indicadores com valores/escala explícitos e dicas com valores integrais. Rankings limitados dentro da seleção. Séries de CIF, FOB e MM3 diferenciadas por cor/forma, MM3 tracejada e barras com base zero. A descrição oficial continua disponível para auditoria.

A comparação de preços exige um único NCM. MM3 é ponderada, não previsão; meses ausentes não são preenchidos como se fossem observações. A variação mensal usa o valor do último mês em contexto e o anterior selecionado, não a média do período completo. Um valor positivo sem peso publicado impede uma razão incompleta.

## Código e integridade

O gerador foi separado em módulos de modelo semântico, visuais e conferência da fonte, todos somente com biblioteca padrão. O dicionário comercial do PDF foi extraído sem mudar seus 36 valores. O fluxo público de exportação, extração Comex, GUI, instalação e dados embutidos não foi refeito.

Antes da publicação: CRC/XML/cabeçalhos, códigos do cadastro, período, tipos, centavos, kg inteiro, CIF = FOB + frete + seguro e chave estatística única. Depois: TMDL efetivamente declarado, cardinalidades, referências, tipos de projeção, grupos de filtros, recursos, IDs e geometria. SHA-256 liga o Excel ao CONTROLE_FONTE.json. Saída temporária/atômica preserva destino anterior em falha ou cancelamento.

## Ensaios e limites

Consulte EVIDENCIAS_RC6.json e VALIDACAO_RC6.log. O teste Qt usa o contrato público real do controlador: verifica ausência de erro, progresso 100, nome do último arquivo, CRC e leitura dos documentos; a simples existência de um arquivo antigo não é aceita como sucesso. O primeiro ensaio dessa revisão corrigiu uma leitura equivocada do campo lastExport no próprio harness de QA (é texto), sem necessidade de mudar o aplicativo.

Controles SQLite/Decimal verificam fonte e referências matemáticas independentes; não são resultados executados por DAX. As validações PBIR/TOM/M foram aplicadas ao projeto que realmente está no exemplo entregue. Nenhum motor externo ou biblioteca de QA foi adicionado às dependências de execução da LIARTE.

DAX, refresh M e renderização no Desktop continuam como aceitação Windows, com instruções e consulta de conferência incluídas. Homologação do instalador e de APIs do Shell também depende do Windows. Não se afirma ausência absoluta de falhas.
