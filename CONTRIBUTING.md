# Contribuir com a LIARTE

Comece pelo [README](README.md), pela [documentação](docs/README.md) e pelas [condições de distribuição](docs/LICENCAS.md). Para dúvidas de instalação ou uso, consulte [Suporte](SUPPORT.md).

## Preparar o desenvolvimento

Use um clone do repositório em uma pasta de desenvolvimento. O Setup e o ZIP portátil são distribuições para executar o aplicativo; mantenha a instalação de uso diário separada dos fontes.

O projeto aceita **CPython padrão 3.11–3.14 de 64 bits** e usa PySide6/Qt Quick. No Windows, o fluxo recomendado utiliza Python 3.12:

```powershell
git status
git switch -c feat/descricao-curta
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe iniciar.py --profile-dir .liarte-dev-profile --demo
```

Confira alterações existentes antes de criar a branch. O perfil `.liarte-dev-profile` mantém preferências, bases e logs de desenvolvimento separados. Use exemplos sintéticos; o modo `--demo` simula as consultas de Importações. Não utilize a pasta da instalação ou o perfil diário como perfil de desenvolvimento.

O [guia de desenvolvimento no Windows](docs/DESENVOLVIMENTO_LOCAL_WINDOWS.md) detalha os pré-requisitos, os comandos auxiliares e a preparação do ambiente. Para compilar, utilize `requirements-build.txt`; os empacotadores Windows e o Inno Setup são necessários somente nessa etapa.

## Fazer uma alteração

Mantenha cada alteração concentrada em um problema ou melhoria. A [arquitetura](docs/ARQUITETURA.md) descreve as responsabilidades de `liarte_core`, `liarte_desktop` e `liarte_engine`.

Ao modificar indicadores, registre o período, a unidade, o recorte e a regra de cálculo. Preserve a distinção entre zero e informação ausente, entre unidades de medida e entre giro da fonte, cobertura estimada e idade física dos lotes. Os [guias de análise](docs/README.md) documentam os contratos atuais.

Siga a [diretriz de análises e fontes](AGENTS.md): apresentação quantitativa, sem hipóteses comerciais ou recomendações por frases prontas. A [preparação para SQL Server](docs/ANALISE_QUANTITATIVA_E_SQL_SERVER.md) descreve o contrato compartilhado das fontes, as atualizações consistentes e o mapeamento ainda necessário para a conexão real.

Novos exemplos e fixtures devem usar dados sintéticos. Bases da empresa, PBIX, caches, logs completos, credenciais, ambientes virtuais e binários gerados não devem acompanhar a contribuição. Arquivos compilados são distribuídos pelos fluxos de build e releases.

## Validar

Durante uma mudança de código, execute os testes relacionados ao comportamento alterado. Antes de concluir, execute a suíte offline pelo registro oficial:

```powershell
.\.venv\Scripts\python.exe verificar.py --headless --volume
```

A suíte exercita domínio, documentos e interface Qt com dados sintéticos, incluindo o ensaio de volume. Novas classes de teste devem ser registradas em `verificar.py`. Informe os resultados e os testes ignorados, com seus motivos; execução sem testes não demonstra validação.

Mudanças de interface também precisam de conferência visual, teclado e janela compacta. Os testes headless não substituem a observação da janela no Windows. Para alterações somente de documentação, confira links, exemplos e consistência com a versão descrita.

Depois de revisar e adicionar os arquivos da alteração ao índice Git, confira a estrutura e os links locais:

```powershell
.\.venv\Scripts\python.exe tools/check_repository.py
.\.venv\Scripts\python.exe -m unittest discover -s tests/repository -v
```

Os checks `tests` e `repository` estão presentes em todos os PRs, inclusive os de documentação. As [regras de organização](docs/GOVERNANCA_REPOSITORIO.md) descrevem branches, labels e a configuração administrativa desejada.

## Abrir o pull request

Descreva o problema, o comportamento resultante e a validação realizada. Inclua capturas com dados sintéticos quando ajudarem a avaliar a interface. Indique limitações que afetem a revisão, como um teste que não pôde ser executado.

Prefira commits com descrições claras e evite misturar reorganização, comportamento e arquivos gerados sem relação. A aprovação de um pull request e a publicação de um pacote são etapas distintas; os workflows de distribuição verificam o executável e o instalador antes da entrega.

As licenças das dependências e a política de distribuição do projeto estão em [Componentes e distribuição](docs/LICENCAS.md). Este guia mantém essas condições.
