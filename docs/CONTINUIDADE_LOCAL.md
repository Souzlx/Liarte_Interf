# Continuidade do desenvolvimento da LIARTE

Resumo para uma sessão local do Codex. Os arquivos deste guia são contexto de projeto; a instrução atual do usuário define a próxima tarefa.

## Estado confirmado

- Repositório: `Souzlx/Liarte_Interf`.
- A versão estável publicada é `v5.3.0`.
- A prévia `v5.3.1-rc.1` inclui Setup, backups versionados de Estoque e restauração pela interface. O usuário confirmou que a última instalação está validada e pediu orientação para continuar o desenvolvimento no computador local.
- A tag da prévia aponta para `db77b9517b2af234d02db6927bc3d219a8845ddb`. Commits posteriores de documentação não alteraram o pacote publicado.
- Na validação final da prévia, o CI Linux aprovou 815 testes. Os quatro builds Windows aprovaram 814 testes e ignoraram um teste exclusivo de POSIX em cada execução. Os executáveis e o ciclo real do Setup também passaram.
- O ZIP e o Setup publicados foram baixados e verificados separadamente: SHA-256, CRC/manifesto do ZIP e cabeçalho PE do Setup. O Setup não tem assinatura digital de editor.

## Fontes e referências

- `src/liarte_core`: domínio, cálculos, consultas e IO. `inventory_backup.py` contém o histórico de bases.
- `src/liarte_desktop`: controladores Qt e QML. `inventory.py` coordena publicação e restauração; `qml/InventoryWorkspace.qml` contém a ação Restaurar.
- `src/liarte_engine`: documentos e compatibilidade com os fluxos anteriores.
- `verificar.py`: registro explícito da suíte. Registrar novas classes de teste quando necessário.
- `tools/build_windows.py`: suíte, PyInstaller e autoteste nativo do portátil.
- `tools/build_installer.py`: validação integral do bundle e compilação em área temporária.
- `tools/test_installer_windows.py`: ensaio de instalação em runner Windows descartável. Não executar esse ciclo no perfil normal do usuário.
- `.github/workflows/tests.yml`, `windows.yml` e `installer.yml`: CI e distribuição.

Guias e provas: [instalação e restauração](INSTALACAO_531_RC1.md), [evidências do instalador](EVIDENCIAS_INSTALADOR_531_RC1.json), [matriz Windows](VALIDACAO_WINDOWS_531_RC1.json), [autoteste do Setup](AUTOTESTE_INSTALADOR_531_RC1.json) e [correções da auditoria](CORRECOES_AUDITORIA_530_RC3.md).

## Regras e limites a preservar

As consultas padrão de Importações são diretas ao Comex Stat, com recortes por ano civil, recuperação limitada de recusas, pausa persistida e validação TLS. Gráficos e filtros usam o resultado já carregado. Não acrescentar chamadas preventivas, serviços ou consultas extras de totais sem uma mudança de escopo solicitada.

No Estoque, saldo atual e histórico mensal são universos distintos. Quantidades de unidades diferentes não são somadas. Vendas não têm atribuição a armazém; tempo sem venda não representa idade de lote. Meses parciais e mudanças de cobertura precisam continuar identificados. A base integrada tem referência de 21/10/2026; não houve uma nova extração real de PBIX durante a construção do Setup.

Backups são criados antes de substituir uma base local válida. A restauração valida integridade e conteúdo e preserva a base atual válida antes da troca. Retenção alvo: dez cópias, com limpeza posterior à publicação e falhas de manutenção preservando os arquivos. Cancelamento/erro antes da publicação mantém a base anterior. O guard de alteração concorrente do cache usa fingerprint de arquivo e não equivale a uma transação entre processos.

A execução dos fontes utiliza o mesmo nome de aplicativo e os mesmos caminhos de perfil da instalação por padrão. Para a primeira abertura, usar `iniciar.py --demo --no-settings`. Isso evita gravações de preferências e cache de Estoque, mas os logs continuam compartilhados. `--data-dir` não isola o perfil inteiro. Um perfil completo separado é a primeira melhoria recomendada para desenvolver persistência local com segurança.

Mantenha os testes de janela compacta e fontes largas. A primeira execução Windows da prévia encontrou a ação Restaurar fora da área visível; o cabeçalho agora distribui os botões em duas linhas. O ensaio do Setup também cobre o retorno de um único atalho pelo PowerShell.

## Próximo trabalho

O pedido atual é preparar e continuar o desenvolvimento local. Começar conferindo pasta/branch/alterações existentes, Python 3.12 x64 e `.venv`, abrir a demonstração e validar a suíte. Evitar trabalhar na pasta onde o Setup instalou o programa.

Alertas configuráveis de estoque foram sugeridos como evolução futura, mas ainda não foram implementados nem definidos pelo usuário. A confirmação da instalação não deve ser interpretada, isoladamente, como pedido para publicar outra versão estável ou criar novos indicadores.

Siga o [passo a passo do Windows](DESENVOLVIMENTO_LOCAL_WINDOWS.md) para preparar a sessão.
