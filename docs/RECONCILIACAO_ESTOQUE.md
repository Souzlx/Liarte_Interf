# Conferência numérica do estoque

Ferramenta dos fontes em desenvolvimento, posterior à **5.3.1** publicada. Confere os dados gravados no PBIX, a base normalizada do aplicativo e os cálculos de saldo e análise mensal. Produz um relatório **Excel ou JSON** com totais conferidos, contagens e diferenças detalhadas. Não altera o PBIX, o snapshot, os filtros ou o perfil de uso.

## Referência independente

`read_pbix_reference()` lê as tabelas quantitativas do arquivo por um caminho separado de `read_pbix()`. Não usa o importador, o normalizador ou os analisadores do aplicativo para calcular os valores esperados. O comparador executa os analisadores reais apenas sobre a base do aplicativo e confere seus resultados contra os registros da referência.

| Origem gravada no PBIX | Conferência |
| --- | --- |
| `Dim_Atualizacao` | Data da base e identificação da versão |
| `Fato_EstoqueAtual` | Quantidade e custo por produto, filial, armazém e unidade |
| `Fact_Estoque` | Quantidade, custo, giro e dias por posição e ano-mês |
| `Fato_DocumentoSaida` | Quantidade e custo por produto, filial, unidade e dia; existência de saída positiva normalizada |
| Cálculos do aplicativo | Total a custo e quantidades atuais; posições e totais mensais; vendas líquidas e referências de meses observados ou parciais |

A referência respeita os marcadores de exclusão e registra linhas lidas, aceitas, excluídas e resultantes. Fatos históricos sem cadastro não desaparecem da conferência. Posições duplicadas, datas ou marcadores inválidos impedem aceitar a referência.

Quantidades são normalizadas em milionésimos e custos em centavos, com arredondamento `HALF_UP` **por item antes de somar as vendas diárias**, conforme o contrato de importação. A existência de saída positiva considera a quantidade normalizada de cada item; vendas e devoluções podem produzir líquido zero com saída positiva registrada.

O relatório mantém unidades distintas separadas e diferencia valores ausentes, zero, sinais e presença de registro. Uma posição ausente não equivale a uma posição com saldo zero. Giro e dias são conferidos como campos da fonte, sem somá-los.

## Executar

Use o ambiente de desenvolvimento descrito em [CONTRIBUTING.md](../CONTRIBUTING.md). A ferramenta não é um novo comando do executável instalado da 5.3.1. O comando automatiza a conferência completa; não depende de marcar produtos ou comparar planilhas manualmente.

No Windows, com Python do ambiente preparado:

```powershell
.\.venv\Scripts\python.exe tools\reconcile_inventory.py --pbix "C:\Dados\LiarteBI.pbix" --output "$env:LOCALAPPDATA\LIARTE\conferencias\estoque.xlsx"
```

Sem `--base`, o próprio importador carrega o PBIX para o lado do aplicativo. A referência é extraída separadamente e a ferramenta confere importação e cálculos. Para conferir um snapshot já existente contra sua origem:

```powershell
.\.venv\Scripts\python.exe tools\reconcile_inventory.py --pbix "C:\Dados\LiarteBI.pbix" --base "C:\Dados\empresa.liarte" --output "$env:LOCALAPPDATA\LIARTE\conferencias\estoque.json"
```

No Linux, os argumentos são os mesmos, usando o Python do ambiente e caminhos locais. A extensão de `--output` seleciona `.xlsx` ou `.json`. O destino deve ser diferente dos arquivos de entrada.

### Resultado

| Saída do processo | Significado |
| --- | --- |
| `0` | Conferência concluída sem divergências no escopo verificado |
| `1` | Diferenças numéricas, de presença ou de disponibilidade encontradas |
| `2` | Entradas incompatíveis ou erro; não significa aprovação |
| `130` | Execução cancelada |

Hash ou data da base incompatíveis produzem `not_comparable`. Um PBIX ou snapshot modificado durante a execução impede publicar uma aprovação da versão anterior como se correspondesse à nova. Cancelamento e falhas preservam o relatório anterior; a gravação é atômica por arquivo.

## Ler os relatórios

- **Resumo:** estado, revisões, referências, contagens de conferências e informações de cobertura.
- **Totais:** valores de referência e do aplicativo, diferenças, escalas, unidades e períodos para os totais agregados, inclusive quando iguais.
- **Diferenças:** apenas as divergências, com produto, filial, armazém quando aplicável, unidade, dia ou ano-mês, indicador e presença dos dois lados. O sinal da diferença é **aplicativo − referência** quando os dois valores são conhecidos.
- **Metodologia:** escopo e definições da conferência.

O JSON preserva inteiros com sua escala e valores ausentes como `null`. No Excel, quantidades e custos são apresentados na unidade correspondente; valores que excedem sua precisão numérica ficam em texto decimal exato, identificado por comentário. Textos da origem são literais, não fórmulas. Listas extensas são divididas por abas antes do limite do Excel.

Acertos de cada registro não são repetidos em centenas de milhares de linhas: o relatório inclui contagens, totais agregados e todas as diferenças. Ausências equivalentes de indicadores continuam identificadas como indisponíveis; não comprovam um valor calculado conhecido.

O processamento mantém a referência, a base e as diferenças em memória. A divisão de abas atende aos limites do Excel; volumes com muitas divergências ainda podem exigir memória elevada. O adaptador SQL futuro precisará dimensionar essa capacidade ou adotar processamento em fluxo, preservando a cobertura completa da conferência.

## Alcance e migração

A conferência utiliza o conjunto completo aceito pelo contrato de estoque. Não aplica filtros da sessão de interface nem agrega vendas por armazém, que não existe no contrato de saídas. Produto, filial e unidade acompanham os valores; fechamentos também conservam a chave de armazém e o ano-mês. Histórico longo pode ser processado em janelas consecutivas para respeitar o limite de período dos analisadores, conservando o recorte completo no relatório.

Esta ferramenta confere registros gravados e cálculos do aplicativo. Não executa SQL, M, DAX, atualizações do Power BI ou as 302 medidas do relatório. Uma página do BI pode aplicar recortes diferentes, como exclusão de posições bloqueadas; seus números visuais só podem ser comparados após igualar filtros e definições. Cadastro, descrições, receitas, margens e a correção comercial dos indicadores originais de giro/dias não são certificados por esta conferência.

O mesmo formato de referência pode ser alimentado por um adaptador SQL Server futuro, após validar esquema e consistência. O relatório fica vinculado à versão conferida; não é uma conexão ao vivo nem um processo de sincronização. Veja o [contrato de migração](ANALISE_QUANTITATIVA_E_SQL_SERVER.md).

## Arquivos da empresa

Relatórios reais podem conter identificadores, quantidades e custos da empresa. Guarde-os em diretório privado, fora do repositório. Os testes e exemplos versionados usam exclusivamente dados sintéticos. Os PBIX recebidos são utilizados apenas em conferências locais, sem modificar ou publicar seus registros.
