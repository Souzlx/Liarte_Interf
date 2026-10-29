# Continuidade do desenvolvimento da LIARTE

Resumo para continuidade do Codex na nuvem ou no computador local. Os arquivos deste guia são contexto de projeto; a instrução atual do usuário define a próxima tarefa.

## Estado confirmado

- Repositório: `Souzlx/Liarte_Interf`.
- A versão estável publicada é `v5.3.1`, no commit `73339f650959a81473ab98b6b6f6b58f3023c563`, com Setup, ZIP portátil e checksums. O CI Linux aprovou 1.070 testes; os quatro builds Windows aprovaram 1.069 e ignoraram um teste POSIX por execução. Os 18 testes de organização também passaram.
- A instalação nova, as atualizações da 5.3.0 e do Setup publicado da RC2, a preservação de diretório e perfil e a desinstalação passaram no runner descartável. Os downloads foram conferidos separadamente. Isso não registra uma nova homologação no computador do usuário; o Setup continua sem assinatura digital de editor.
- A prévia `v5.3.1-rc.1` inclui Setup, backups versionados de Estoque e restauração pela interface. O usuário confirmou que a última instalação está validada e pediu orientação para continuar o desenvolvimento no computador local.
- A tag da prévia aponta para `db77b9517b2af234d02db6927bc3d219a8845ddb`. Commits posteriores de documentação não alteraram o pacote publicado.
- Na validação final da prévia, o CI Linux aprovou 815 testes. Os quatro builds Windows aprovaram 814 testes e ignoraram um teste exclusivo de POSIX em cada execução. Os executáveis e o ciclo real do Setup também passaram.
- O ZIP e o Setup publicados foram baixados e verificados separadamente: SHA-256, CRC/manifesto do ZIP e cabeçalho PE do Setup. O Setup não tem assinatura digital de editor.
- O perfil separado de desenvolvimento foi integrado pelo PR #2, no commit `4d8c9cb`. Depois disso, o usuário pediu explicitamente para continuar o projeto na nuvem.
- Os alertas foram conferidos pelo usuário e o PR #3 foi integrado em `e637efd`. Sua validação final aprovou 883 testes Linux e quatro builds Windows, cada um com 882 testes aprovados e um skip POSIX, além dos autotestes dos executáveis.
- O comparador mensal e o desempenho dos produtos foram acrescentados depois. A organização por tarefas, os filtros e as ordenações do PR #6 também foram aprovados pelo usuário.
- A prévia **5.3.1-rc.2** foi publicada com o novo Setup, ZIP e checksums após integrar o PR #6 em `c0aa4a49c83e4e5637d51073e19e0faedd62da59`. O CI Linux aprovou 1.061 testes; cada build Windows aprovou 1.060 e ignorou um teste POSIX. O ciclo real do Setup e a conferência dos downloads passaram. A confirmação de uso dessa instalação no computador do usuário continua distinta desses testes automatizados.

## Fontes e referências

- `src/liarte_core`: domínio, cálculos, consultas e IO. `inventory_backup.py` contém o histórico de bases.
- `src/liarte_desktop`: controladores Qt e QML. `inventory.py` coordena publicação e restauração; `qml/InventoryWorkspace.qml` contém a ação Restaurar. `runtime_profile.py` define os caminhos do perfil de execução.
- `src/liarte_engine`: documentos e compatibilidade com os fluxos anteriores.
- `verificar.py`: registro explícito da suíte. Registrar novas classes de teste quando necessário.
- `tools/build_windows.py`: suíte, PyInstaller e autoteste nativo do portátil.
- `tools/build_installer.py`: validação integral do bundle e compilação em área temporária.
- `tools/test_installer_windows.py`: ensaio de instalação em runner Windows descartável. Não executar esse ciclo no perfil normal do usuário.
- `.github/workflows/tests.yml`, `windows.yml` e `installer.yml`: CI e distribuição.

Entrega atual: [instalação da 5.3.1](INSTALACAO_531.md), [notas da estável](RELEASE_5.3.1.md), [evidências da publicação](EVIDENCIAS_INSTALADOR_531.json), [matriz Windows](VALIDACAO_WINDOWS_531.json), [autoteste do Setup](AUTOTESTE_INSTALADOR_531.json), [interface](GUIA_INTERFACE_MODULAR.md) e [desempenho/ordenações](DESEMPENHO_PRODUTOS.md).

A publicação é centralizada em `.github/workflows/installer.yml`, com `publish_release=true` para a versão estável e `publish_preview=true` para versões RC. Os dois canais são mutuamente exclusivos. `windows.yml` oferece validação e não publica releases.

Histórico: [instalação RC2](INSTALACAO_531_RC2.md), [notas RC2](RELEASE_5.3.1-rc.2.md), [evidências RC2](EVIDENCIAS_INSTALADOR_531_RC2.json), [instalação e restauração RC1](INSTALACAO_531_RC1.md), [evidências do instalador RC1](EVIDENCIAS_INSTALADOR_531_RC1.json), [matriz Windows RC1](VALIDACAO_WINDOWS_531_RC1.json), [autoteste do Setup RC1](AUTOTESTE_INSTALADOR_531_RC1.json) e [correções da auditoria](CORRECOES_AUDITORIA_530_RC3.md).

## Regras e limites a preservar

As consultas padrão de Importações são diretas ao Comex Stat, com recortes por ano civil, recuperação limitada de recusas, pausa persistida e validação TLS. Gráficos e filtros usam o resultado já carregado. Não acrescentar chamadas preventivas, serviços ou consultas extras de totais sem uma mudança de escopo solicitada.

No Estoque, saldo atual e histórico mensal são universos distintos. Quantidades de unidades diferentes não são somadas. Vendas não têm atribuição a armazém; tempo sem venda não representa idade de lote. Meses parciais e mudanças de cobertura precisam continuar identificados. A base integrada mantém a referência de 21/10/2026; a inspeção dos PBIX enviados para revisão não substituiu a base distribuída.

Backups são criados antes de substituir uma base local válida. A restauração valida integridade e conteúdo e preserva a base atual válida antes da troca. Retenção alvo: dez cópias, com limpeza posterior à publicação e falhas de manutenção preservando os arquivos. Cancelamento/erro antes da publicação mantém a base anterior. O guard de alteração concorrente do cache usa fingerprint de arquivo e não equivale a uma transação entre processos.

A execução sem `--profile-dir` mantém os caminhos e o comportamento da instalação. Para uma primeira abertura sem persistência de preferências ou Estoque, usar `iniciar.py --demo --no-settings`; os logs desse comando continuam compartilhados. `--data-dir` altera apenas o diretório do cliente Comex e não isola o perfil inteiro.

Para desenvolver persistência, usar `iniciar.py --profile-dir .liarte-dev-profile --demo`. O perfil mantém `settings.ini`, dados Comex, cache de Estoque e seus backups, relatórios, configuração da central e logs na pasta escolhida. Um perfil novo começa vazio, sem migrar preferências antigas nem carregar a base da instalação. A janela é identificada como Desenvolvimento e a execução não usa o mutex nem os atalhos da instalação diária. A pasta `.liarte-dev-profile` é ignorada pelo Git.

`--profile-dir` e `--data-dir` juntos são recusados. `--no-settings` continua prevalecendo: se acrescentado ao perfil de desenvolvimento, desativa preferências e cache persistente de Estoque, enquanto os logs ficam no perfil escolhido. Não use o diretório da instalação ou do perfil diário como pasta de desenvolvimento.

Mantenha os testes de janela compacta e fontes largas. A primeira execução Windows da prévia encontrou a ação Restaurar fora da área visível; o cabeçalho agora distribui os botões em duas linhas. O ensaio do Setup também cobre o retorno de um único atalho pelo PowerShell.

## Entrega concluída e histórico

A **5.3.1** foi publicada como estável a partir de `73339f650959a81473ab98b6b6f6b58f3023c563`, após os workflows [Linux 40906447193](https://github.com/Souzlx/Liarte_Interf/actions/runs/40906447193) e [instalador 40907105322](https://github.com/Souzlx/Liarte_Interf/actions/runs/40907105322) aprovarem as validações. Setup, portátil e checksums estão na [release 5.3.1](https://github.com/Souzlx/Liarte_Interf/releases/tag/v5.3.1). A tag permanece no commit dos pacotes testados; os commits posteriores de documentação não modificam os binários. A RC2 e a 5.3.0 foram preservadas.

As melhorias aprovadas haviam sido consolidadas na **5.3.1-rc.2**, integradas à `main` e publicadas pelo [workflow 40697786809](https://github.com/Souzlx/Liarte_Interf/actions/runs/40697786809). O Setup, o portátil e os checksums estão na [release da RC2](https://github.com/Souzlx/Liarte_Interf/releases/tag/v5.3.1-rc.2). Os três relatórios de evidência registram o commit exato, os testes e a integridade dos arquivos. A tag permanece no commit testado; a documentação posterior não modifica os pacotes. A versão 5.3.0 permanece disponível no histórico de estáveis.

Os [alertas](ALERTAS_ESTOQUE.md) usam limites configuráveis e distinguem tempo sem venda, cobertura estimada e ausência de venda registrada. O painel reutiliza a análise local, agrupa produto/filial/unidade e exporta a lista completa.

O [comparador mensal](COMPARADOR_MENSAL_ESTOQUE.md) reutiliza `stockRows` e `saleRows` do cache mensal completo. A reconciliação de estoque separa variação pareada e registros só em um fechamento; não interpretar ausência como saldo zero nem como prova de movimento físico. Quantidades e vendas ficam separadas por unidade. A tela usa apresentações limitadas; o Excel recebe o resultado completo aceito. Trocar meses não relê a base e não apaga a sessão de análise.

As [ordenações](DESEMPENHO_PRODUTOS.md) usam os dados carregados antes da paginação. Posições agrupam saldo por unidade e mantêm desconhecidos ao final. O Excel de posições acompanha a ordem aplicada; a aba de desempenho mantém todos os produtos/unidades do recorte. Navegação e troca de ordem preservam o contexto aceito, sem consultar o PBIX ou a rede novamente.

Siga o [passo a passo do Windows](DESENVOLVIMENTO_LOCAL_WINDOWS.md) para preparar a sessão.
