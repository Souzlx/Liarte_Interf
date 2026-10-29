# Instalação e atualização — 5.3.1

A 5.3.1 reúne a interface por tarefas, alertas, comparação mensal, desempenho e ordenações de Estoque validados na candidata RC2, com identificação final da versão. O Setup e o ZIP portátil incluem Python, Qt e as dependências. O computador do usuário não precisa de Python para executar esses pacotes.

## Arquivos da entrega

A versão estável está publicada com os seguintes arquivos:

- [LIARTE_Desktop_5.3.1_Setup.exe](https://github.com/Souzlx/Liarte_Interf/releases/download/v5.3.1/LIARTE_Desktop_5.3.1_Setup.exe).
- [LIARTE_Desktop_5.3.1_Windows_x64.zip](https://github.com/Souzlx/Liarte_Interf/releases/download/v5.3.1/LIARTE_Desktop_5.3.1_Windows_x64.zip).
- [SHA256SUMS.txt](https://github.com/Souzlx/Liarte_Interf/releases/download/v5.3.1/SHA256SUMS.txt).
- [Notas da 5.3.1](RELEASE_5.3.1.md).

As entregas [5.3.0](https://github.com/Souzlx/Liarte_Interf/releases/tag/v5.3.0) e [5.3.1-rc.2](https://github.com/Souzlx/Liarte_Interf/releases/tag/v5.3.1-rc.2) permanecem disponíveis. Seus arquivos e tags não são substituídos pela versão final.

## Instalar ou atualizar pelo Setup

1. Feche todas as janelas da LIARTE.
2. Execute `LIARTE_Desktop_5.3.1_Setup.exe` na mesma conta Windows da instalação anterior, seja ela 5.3.0 ou 5.3.1-rc.2.
3. Abra a LIARTE pelo atalho criado pelo Setup e confira **5.3.1** em **Ajuda**.

A instalação é por usuário. O diretório padrão é `%LOCALAPPDATA%\Programs\LIARTE Desktop`; uma atualização reutiliza o diretório registrado da instalação anterior. Bases, backups e preferências ficam no perfil do usuário, fora da pasta do programa. Relatórios exportados permanecem nos locais escolhidos.

Quem usava o portátil pode instalar o Setup na mesma conta e continuar usando o perfil existente. Um atalho para uma pasta portátil antiga continua abrindo aquela pasta; use o atalho criado pelo Setup para abrir a versão instalada.

Uma atualização normal não exige desinstalar a versão anterior nem apagar seu perfil. Guarde o PBIX original e mantenha cópias dos arquivos importantes conforme a rotina da empresa.

## Usar o portátil

Extraia **todo o ZIP em uma pasta nova** e abra `LIARTE_Desktop.exe`, mantendo `_internal` ao lado. Não sobreponha parcialmente os arquivos da pasta anterior. O ZIP de fontes oferecido automaticamente pelo GitHub é distinto do portátil compilado.

## Conferir os dados e indicadores

Em Estoque, confira a referência da base carregada. A base integrada tem referência de **21/10/2026**, e a última base válida importada localmente tem preferência. Para atualizar os dados, use **Atualizar base** e selecione um PBIX com dados ou um snapshot `.liarte`. Não há consulta ao vivo ao ERP.

Panorama, Análise mensal e Produtos apresentam tarefas distintas. Ordenações de Produtos são aplicadas antes da paginação e acompanham o Excel de posições. Em Desempenho dos produtos, escolha os critérios e pressione **Aplicar**. Veja o [guia da interface](GUIA_INTERFACE_MODULAR.md) e as [definições de desempenho](DESEMPENHO_PRODUTOS.md).

Giro da fonte, cobertura estimada e tempo desde a última venda não são a mesma medida. Quantidades de unidades distintas não são somadas, custo não representa faturamento e a base não permite calcular a idade física dos lotes. As hipóteses apresentadas exigem investigação; não comprovam causas para variações.

## Bases anteriores e remoção

Antes de substituir uma base local válida de Estoque, o aplicativo guarda uma cópia para restauração. **Restaurar** mostra a data de gravação e a referência dos dados e pede confirmação antes da troca. A base atual válida também é preservada ao restaurar outra. A retenção padrão mantém dez cópias válidas recentes.

Essas cópias ficam no perfil Windows e não substituem a guarda do PBIX original ou de relatórios exportados. Na desinstalação, preservar bases, backups, diagnósticos e preferências é a opção padrão. A exclusão desses dados exige uma escolha explícita.

Na desinstalação silenciosa, o perfil também é preservado por padrão. `/PURGEDATA=1` solicita sua exclusão e não deve ser usado para uma atualização normal. Relatórios fora do perfil permanecem intactos.

## Validação da distribuição

O [workflow do instalador](../.github/workflows/installer.yml) centraliza a publicação de Setup, ZIP e checksums. A publicação estável depende da suíte e do autoteste dos executáveis em Python 3.11–3.14 e do ciclo do Setup com o bundle 3.12 verificado. O [workflow Windows](../.github/workflows/windows.yml) oferece validação dos executáveis sem publicar uma distribuição alternativa.

O ensaio do Setup usa um perfil descartável do runner Windows. Ele cobre instalação, atalhos, atualização com preservação do diretório e do perfil, desinstalação preservando dados e exclusão explícita do perfil com relatório externo preservado. Para a 5.3.1 estável, inclui a versão 5.3.0 e o Setup publicado da 5.3.1-rc.2 como origens de atualização. Os resultados da candidata permanecem identificados como RC2. Os novos pacotes 5.3.1 passaram nas próprias validações, registradas no [workflow 40907105322](https://github.com/Souzlx/Liarte_Interf/actions/runs/40907105322).

O compilador Inno Setup tem versão fixada, checksum e assinatura de fornecedor verificados. **O Setup da LIARTE não tem assinatura digital de editor.** Os testes offline e no runner não substituem a conferência das políticas de instalação, da rede e das configurações de tela dos computadores da empresa.

## Resultados da entrega

A tag `v5.3.1` aponta para `73339f650959a81473ab98b6b6f6b58f3023c563`. O [CI Linux](https://github.com/Souzlx/Liarte_Interf/actions/runs/40906447193) aprovou **1.070 testes**, sem skips. Os 18 testes de organização também passaram. Cada build Windows executou a mesma suíte: **1.069 aprovados e um teste exclusivo POSIX ignorado**. Os quatro executáveis passaram nos autotestes nativos de interface, temas, documentos e backups, sem avisos QML.

O ensaio do Setup aprovou instalação e atalhos, as atualizações da 5.3.0 e do Setup publicado da RC2 com reutilização do diretório e preservação do perfil, remoção preservando dados e exclusão explícita do perfil com relatórios externos intactos. A conferência independente dos downloads validou SHA-256, CRC do ZIP e todos os arquivos do manifesto interno. A base integrada corresponde ao arquivo do commit publicado.

Veja as [evidências da publicação](EVIDENCIAS_INSTALADOR_531.json), a [matriz Windows](VALIDACAO_WINDOWS_531.json) e o [autoteste do instalador](AUTOTESTE_INSTALADOR_531.json). As tags e os arquivos das entregas anteriores foram preservados.
