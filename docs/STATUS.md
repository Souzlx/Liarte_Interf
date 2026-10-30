# Estado do projeto

O LIARTE é um aplicativo desktop em Python e Qt Quick para analisar importações pelo Comex Stat e Estoque a partir de uma base local. Os módulos disponíveis são **Importações** e **Estoque**. Crédito permanece cadastrado como planejado, sem funcionalidade publicada.

## Versões disponíveis

| Canal | Versão | Distribuição |
| --- | --- | --- |
| Estável atual | [5.3.1](https://github.com/Souzlx/Liarte_Interf/releases/tag/v5.3.1) | [Setup Windows](https://github.com/Souzlx/Liarte_Interf/releases/download/v5.3.1/LIARTE_Desktop_5.3.1_Setup.exe), [ZIP portátil](https://github.com/Souzlx/Liarte_Interf/releases/download/v5.3.1/LIARTE_Desktop_5.3.1_Windows_x64.zip) e [checksums](https://github.com/Souzlx/Liarte_Interf/releases/download/v5.3.1/SHA256SUMS.txt) |
| Prévia histórica | [5.3.1-rc.2](https://github.com/Souzlx/Liarte_Interf/releases/tag/v5.3.1-rc.2) | Setup Windows, ZIP portátil e checksums |
| Estável anterior | [5.3.0](https://github.com/Souzlx/Liarte_Interf/releases/tag/v5.3.0) | ZIP portátil e checksums |

A tag `v5.3.1` aponta para `73339f650959a81473ab98b6b6f6b58f3023c563`. A RC2 permanece em `c0aa4a49c83e4e5637d51073e19e0faedd62da59`. Commits posteriores de documentação não alteram os pacotes dessa tag. Os arquivos anteriores continuam disponíveis no histórico de releases.

Para instalar ou atualizar, utilize o [guia da 5.3.1](INSTALACAO_531.md). Os pacotes compilados incluem Python, Qt e as dependências; a execução dos fontes exige um ambiente de desenvolvimento separado.

## O que a 5.3.1 inclui

- Vistas por tarefa: Panorama, Análise mensal e Produtos no Estoque; Resumo, Compras e Registros nas Importações.
- Filtros aplicados explicitamente, gráficos interativos e preservação da sessão ao navegar.
- Alertas configuráveis, comparação de dois meses e investigação do desempenho por produto.
- Ordenações crescentes e decrescentes de indicadores, valores ausentes ao final e quantidades separadas por unidade.
- Setup por usuário, atualização com preservação do perfil e restauração de bases anteriores de Estoque.

O [guia da interface](GUIA_INTERFACE_MODULAR.md) e as [notas da versão](RELEASE_5.3.1.md) detalham essas funcionalidades.

## Validação da entrega

| Verificação | Resultado registrado |
| --- | --- |
| CI Linux | 1.070 testes aprovados, sem skips |
| Organização do repositório | 18 testes aprovados e conferência de estrutura e links |
| Windows, Python 3.11–3.14 | Quatro suítes com 1.069 aprovados e um teste exclusivo POSIX ignorado em cada uma |
| Executáveis empacotados | Autotestes de interface, temas, documentos e backups aprovados, sem avisos QML |
| Setup | Instalação, atalhos, atualização da 5.3.0 e do Setup publicado da RC2, preservação de dados e desinstalação aprovados no runner Windows |
| Downloads publicados | SHA-256, CRC e todos os arquivos do manifesto interno conferidos |

Os workflows [Linux 40906447193](https://github.com/Souzlx/Liarte_Interf/actions/runs/40906447193) e [Windows 40907105322](https://github.com/Souzlx/Liarte_Interf/actions/runs/40907105322) registram as execuções. As [evidências da publicação](EVIDENCIAS_INSTALADOR_531.json), a [matriz Windows](VALIDACAO_WINDOWS_531.json) e o [autoteste do instalador](AUTOTESTE_INSTALADOR_531.json) identificam o código, os cenários e os artefatos verificados. Os ensaios usam dados sintéticos e perfil descartável; não equivalem à homologação da rede ou de todas as configurações dos computadores da empresa.

## Fontes e limites dos indicadores

Nos fontes em desenvolvimento, **Produtos → Prioridades** acrescenta uma lista de revisão com cobertura, queda de vendas, saldo sem venda líquida e uma visão por capital no fechamento. A investigação preserva o recorte e a exportação registra os critérios e períodos. Essa melhoria é posterior à 5.3.1 publicada e não modifica seus pacotes; veja os [critérios de Prioridades](PRIORIDADES_PRODUTOS.md).

O desktop consulta diretamente a API do Comex Stat quando uma consulta é solicitada. Navegar, filtrar e ordenar os resultados aceitos usa os dados já carregados. Pausas HTTP 429 são respeitadas e apresentadas na interface; a disponibilidade do serviço externo não é garantida pelo aplicativo.

O Estoque utiliza PBIX ou snapshots `.liarte`, sem executar conexões ou expressões do PBIX. O pacote inclui uma base datada de **21/10/2026**; a última base válida importada localmente pelo usuário tem preferência. Não há conexão ao vivo com o ERP.

Giro da fonte, cobertura estimada e tempo desde a última venda são conceitos distintos. Quantidades de unidades diferentes não são somadas. Custo não representa faturamento, e a base atual não permite determinar a idade física dos lotes. Veja as [definições de desempenho](DESEMPENHO_PRODUTOS.md) e a [análise do BI](ANALISE_BI_E_EXPERIENCIA.md).

## Referências

- [Arquitetura atual](ARQUITETURA.md).
- [Desenvolvimento local no Windows](DESENVOLVIMENTO_LOCAL_WINDOWS.md).
- [Continuidade e decisões registradas](CONTINUIDADE_LOCAL.md).
- [Histórico do acesso automático RC4](ACESSO_AUTOMATICO_520_RC4.md) e [evolução do cliente direto RC9](NOVO_CLIENTE_API_520_RC9.md).

Os documentos com versões antigas no nome registram o estado daquela entrega. Não devem ser interpretados como instruções da versão atual.
