# LIARTE

Aplicativo desktop nativo para consultar Importações pelo Comex Stat e analisar estoque, vendas e giro mensal de uma base local. A interface usa Qt. O código ativo está em `src/`.

## Usar o pacote portátil no Windows

Baixe o pacote compilado da versão desejada, feche o aplicativo anterior e extraia **todo o ZIP em uma pasta nova**. Abra `LIARTE_Desktop.exe` e mantenha a pasta `_internal` junto dele. Esse pacote inclui Python e as dependências; o usuário não precisa instalar Python.

O ZIP de fontes oferecido pelo GitHub é diferente do pacote compilado. Veja [LEIA_PRIMEIRO.txt](LEIA_PRIMEIRO.txt) para uso, atualização e limites dos indicadores.

A versão estável **5.3.0** promove a RC3 validada pelo usuário, com gráficos responsivos, análise mensal de estoque e as [correções da auditoria](docs/CORRECOES_AUDITORIA_530_RC3.md). Veja as [notas da versão](docs/RELEASE_5.3.0.md) para atualizar.

[Baixar o pacote portátil Windows 5.3.0](https://github.com/Souzlx/Liarte_Interf/releases/download/v5.3.0/LIARTE_Desktop_5.3.0_Windows_x64.zip) · [Página da release e checksums](https://github.com/Souzlx/Liarte_Interf/releases/tag/v5.3.0).

A candidata **5.3.1-rc.2** consolida alertas, comparação mensal, desempenho por produto, interface por tarefas e ordenações de estoque, mantendo Setup e restauração de bases. A publicação está em preparação e depende da conclusão do [workflow do instalador](.github/workflows/installer.yml). Após a publicação: [Setup 5.3.1-rc.2](https://github.com/Souzlx/Liarte_Interf/releases/download/v5.3.1-rc.2/LIARTE_Desktop_5.3.1-rc.2_Setup.exe) · [ZIP e checksums](https://github.com/Souzlx/Liarte_Interf/releases/tag/v5.3.1-rc.2). Veja o [guia de instalação e atualização](docs/INSTALACAO_531_RC2.md) e as [notas da candidata](docs/RELEASE_5.3.1-rc.2.md).

A prévia anterior [5.3.1-rc.1](https://github.com/Souzlx/Liarte_Interf/releases/tag/v5.3.1-rc.1), seu [guia](docs/INSTALACAO_531_RC1.md) e suas [notas](docs/RELEASE_5.3.1-rc.1.md) permanecem disponíveis como histórico. A versão estável continua sendo a 5.3.0.

Os [alertas configuráveis de estoque](docs/ALERTAS_ESTOQUE.md) permitem investigar produto, filial e unidade e exportar a lista completa em Excel.

Na análise mensal, o [comparador de dois meses](docs/COMPARADOR_MENSAL_ESTOQUE.md) permite investigar a diferença de estoque e vendas por produto ou filial, separando posições comparáveis e mudanças de cobertura dos registros.

Em Produtos, a análise de [desempenho e giro por produto](docs/DESEMPENHO_PRODUTOS.md) acrescenta rankings por unidade, janelas de 1/3/6 meses, histórico e hipóteses a verificar sobre as variações. Giro da fonte e cobertura estimada têm definições separadas; a base não informa idade dos lotes.

A [interface organizada por tarefa](docs/GUIA_INTERFACE_MODULAR.md) separa as vistas de estoque e mercado, mantém filtros aplicados visíveis e apresenta detalhes sob demanda. A [análise dos PBIX enviados](docs/ANALISE_BI_E_EXPERIENCIA.md) documenta fórmulas e recortes que precisam de revisão antes de ampliar os indicadores financeiros.

## Executar os fontes

Para continuar o desenvolvimento na sua máquina com VS Code e Codex, siga o [guia de desenvolvimento local no Windows](docs/DESENVOLVIMENTO_LOCAL_WINDOWS.md). O [resumo de continuidade](docs/CONTINUIDADE_LOCAL.md) registra o estado da instalação validada e os cuidados com o perfil de dados.

No Windows, instale CPython padrão **3.11, 3.12, 3.13 ou 3.14 de 64 bits**, com Tkinter, e abra `INICIAR_DESKTOP.cmd`. O assistente cria `.liarte-desktop-env`, instala as dependências fixadas e verifica a interface. A preparação inicial exige acesso aos gerenciadores de pacotes.

Os comandos `.cmd` procuram o Python instalado no computador. Launchers de um ambiente de outra máquina não fazem parte da árvore-fonte. Para selecionar uma instalação explicitamente, execute no diretório do projeto, por exemplo:

```powershell
py -3.12 tools/assistente.py --mode run
```

Também é possível usar o caminho completo de um `python.exe` compatível. O assistente valida a versão e a arquitetura. Para reparar o ambiente local, use `REPARAR_AMBIENTE.cmd` ou acrescente `--repair` ao comando do assistente.

Em um ambiente de desenvolvimento já preparado:

```sh
python -m venv .venv
# Ative .venv no seu terminal antes dos próximos comandos.
python -m pip install -r requirements.txt
python iniciar.py --profile-dir .liarte-dev-profile --demo
```

`--profile-dir` cria um perfil de desenvolvimento separado, com preferências, dados, Estoque, backups, relatórios e logs próprios. A janela fica marcada como **Desenvolvimento**. Um perfil novo começa vazio, sem copiar preferências ou bases da instalação de uso; a pasta `.liarte-dev-profile` é ignorada pelo Git. O modo `--demo` utiliza consultas sintéticas e permite testar a persistência nesse perfil.

Sem `--profile-dir`, os caminhos da instalação continuam sendo usados. Para uma primeira abertura sem gravar preferências nem cache de Estoque, use `iniciar.py --demo --no-settings`; os logs desse comando ainda usam o perfil normal. Não combine `--profile-dir` com `--data-dir`: essa combinação é recusada para impedir que dados saiam do perfil escolhido. Veja o [guia Windows](docs/DESENVOLVIMENTO_LOCAL_WINDOWS.md) para os comandos completos.

`iniciar.py` configura o acesso a `src/`. Bibliotecas, scripts e integrações devem importar os pacotes `liarte_core`, `liarte_desktop` e `liarte_engine`, por instalação do projeto ou com `src/` no `PYTHONPATH`.

## Testar e compilar

A suíte offline inclui testes de domínio, exportações e interface Qt com dados sintéticos. Não consulta a API real nem equivale à homologação da rede, GPU e instalação da empresa.

```sh
python verificar.py --headless --volume
```

Para produzir o pacote portátil **no Windows**, use `CRIAR_EXECUTAVEL.cmd`. O assistente instala as dependências de compilação, executa a suíte e valida o executável. Em um ambiente Windows preparado, o comando equivalente do empacotador é:

```powershell
python -m pip install -r requirements-build.txt
python tools/build_windows.py
```

O resultado fica em `dist/LIARTE_Desktop/`, incluindo recursos e manifesto de integridade. `CRIAR_INSTALADOR.cmd` acrescenta a geração do Setup com Inno Setup; consulte [INSTALACAO_510.md](docs/INSTALACAO_510.md). O workflow [Windows](.github/workflows/windows.yml) mantém a compilação nas quatro versões Python suportadas; o [CI de alterações](.github/workflows/tests.yml) executa testes em push/PR de código. Publicar uma versão estável é uma etapa separada.

As [evidências da publicação 5.3.0](docs/EVIDENCIAS_RELEASE_530.json) e a [validação Windows](docs/VALIDACAO_WINDOWS_530.json) registram os testes, o código compilado e a conferência independente do ZIP publicado.

## Organização

| Caminho | Responsabilidade |
|---|---|
| `src/liarte_core/` | Domínio, consultas, cálculos, leitura e exportação de estoque. |
| `src/liarte_desktop/` | Controladores Qt, interface QML e recursos visuais. |
| `src/liarte_engine/` | Geradores de documentos/BI e compatibilidade com fluxos anteriores. |
| `src/liarte_core/data/` | Base de estoque integrada e metadados de integridade canônicos. |
| `tools/` | Preparação do ambiente, empacotamento e publicação. |
| `tests/` | Testes e fixtures offline. |
| `docs/` | Critérios, guias e evidências identificadas por versão. |
| `exemplos/` | Documentos de exemplo preservados. |
| `third_party/` | Licenças e avisos das dependências distribuídas. |

A base integrada reflete os dados recebidos em 21/10/2026. Não é uma conexão ao vivo com o ERP. A última base válida importada pelo usuário tem preferência; dados históricos e saldos atuais seguem critérios diferentes. Veja [ESTOQUE_520.md](docs/ESTOQUE_520.md) e [ANALISE_MENSAL_530_RC2.md](docs/ANALISE_MENSAL_530_RC2.md).

Os manifestos recebidos com os fontes antigos foram preservados em [docs/archive/source_rc9/](docs/archive/source_rc9/README.md). Não representam checksums da árvore atual. A [limpeza da RC3](docs/LIMPEZA_530_RC3.md) registra exatamente os arquivos removidos e seus hashes; o histórico Git permanece disponível.
