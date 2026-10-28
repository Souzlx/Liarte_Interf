# LIARTE

[![Testes da aplicação](https://github.com/Souzlx/Liarte_Interf/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/Souzlx/Liarte_Interf/actions/workflows/tests.yml)
[![Organização do repositório](https://github.com/Souzlx/Liarte_Interf/actions/workflows/repository.yml/badge.svg?branch=main)](https://github.com/Souzlx/Liarte_Interf/actions/workflows/repository.yml)

Aplicativo desktop para analisar estoque, vendas e giro de produtos a partir de uma base local e consultar o mercado de importações pelo Comex Stat. Interface nativa em Qt Quick, com filtros, gráficos interativos e exportações para Excel, PDF e projeto Power BI.

[Documentação](docs/README.md) · [Instalação e atualização](docs/INSTALACAO_531_RC2.md) · [Suporte](SUPPORT.md) · [Contribuir](CONTRIBUTING.md)

## Downloads para Windows

| Canal | Versão | Pacotes | Notas |
| --- | --- | --- | --- |
| Prévia atual | **5.3.1-rc.2** | [Instalador Setup](https://github.com/Souzlx/Liarte_Interf/releases/download/v5.3.1-rc.2/LIARTE_Desktop_5.3.1-rc.2_Setup.exe) · [ZIP portátil](https://github.com/Souzlx/Liarte_Interf/releases/download/v5.3.1-rc.2/LIARTE_Desktop_5.3.1-rc.2_Windows_x64.zip) | [Mudanças e validação](docs/RELEASE_5.3.1-rc.2.md) |
| Estável | **5.3.0** | [ZIP portátil](https://github.com/Souzlx/Liarte_Interf/releases/download/v5.3.0/LIARTE_Desktop_5.3.0_Windows_x64.zip) | [Notas da versão](docs/RELEASE_5.3.0.md) |

**Os pacotes compilados incluem Python, Qt e as dependências.** Não é necessário instalar Python para usar o aplicativo. Os arquivos e `SHA256SUMS.txt` estão nas [releases](https://github.com/Souzlx/Liarte_Interf/releases); o ZIP de código-fonte do GitHub não é o portátil compilado.

Para instalar ou atualizar pelo Setup, feche a LIARTE, execute o instalador na mesma conta Windows da instalação anterior e confira a versão em **Ajuda**. Bases, backups e preferências ficam no perfil do usuário. Para usar o portátil, extraia **todo o ZIP em uma pasta nova**, abra `LIARTE_Desktop.exe` e mantenha `_internal` junto dele. Veja o [guia de instalação](docs/INSTALACAO_531_RC2.md).

![Panorama do estoque na interface nativa da LIARTE](docs/images/interface-estoque-panorama.png)

*Interface Qt real com dados sintéticos. Outras vistas e capturas estão no [guia da interface](docs/GUIA_INTERFACE_MODULAR.md).*

## O que o aplicativo oferece

- **Estoque:** panorama a custo, filtros por produto e posição, alertas configuráveis, fechamento mensal e comparação entre meses.
- **Produtos:** rankings de vendas por unidade e período, evolução mensal e ordenações por giro, saldo, capital e cobertura.
- **Mercado de importações:** consulta ao Comex Stat, análise por período, classificação e origem, com referências por kg no recorte comparável.
- **Conferência e documentos:** tabelas e investigação de produtos; Excel do Estoque e Excel, PDF e projeto Power BI das Importações, com escopo e critérios identificados.
- **Uso diário:** temas claro/escuro, navegação por teclado, layout adaptável e restauração de bases locais anteriores.

O estoque usa uma base local; não há sincronização automática com o ERP. Saldo atual, giro da fonte, cobertura estimada e tempo desde a última venda têm definições próprias. A base não informa a idade física dos lotes. Consulte os [guias de análise](docs/README.md#estoque-e-produtos) antes de comparar indicadores.

## Desenvolver

O código ativo está em `src/`. O ambiente de desenvolvimento usa CPython **3.11–3.14 padrão de 64 bits**. No Windows, o assistente `INICIAR_DESKTOP.cmd` prepara o ambiente; o [guia de desenvolvimento local](docs/DESENVOLVIMENTO_LOCAL_WINDOWS.md) detalha ferramentas e comandos.

Para preparar uma `.venv` e abrir uma demonstração com perfil separado, execute no PowerShell, a partir da raiz do clone:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe iniciar.py --profile-dir .liarte-dev-profile --demo
```

O perfil de desenvolvimento começa vazio e guarda seus próprios dados e preferências. Use dados sintéticos nesse perfil e preserve a instalação de uso diário. Veja [CONTRIBUTING.md](CONTRIBUTING.md) para o fluxo de alterações e pull requests.

### Verificar e empacotar

```powershell
.\.venv\Scripts\python.exe verificar.py --headless --volume
```

A suíte exercita domínio, documentos e interface Qt sem consultar a API real. Os workflows de [testes](.github/workflows/tests.yml), [compilação Windows](.github/workflows/windows.yml) e [instalador](.github/workflows/installer.yml) registram as validações de cada entrega. A [RC2 publicada](docs/EVIDENCIAS_INSTALADOR_531_RC2.json) inclui os testes dos quatro executáveis e o ciclo do Setup.

A compilação de distribuição ocorre **no Windows**: `CRIAR_EXECUTAVEL.cmd` produz o portátil e `CRIAR_INSTALADOR.cmd` acrescenta o Setup com Inno Setup. As etapas de publicação estão separadas das verificações comuns; consulte o [guia da entrega](docs/INSTALACAO_531_RC2.md#como-a-entrega-é-validada).

## Estrutura do repositório

| Caminho | Responsabilidade |
| --- | --- |
| `src/liarte_core/` | Domínio, consultas, indicadores, leitura e exportação de estoque. |
| `src/liarte_desktop/` | Controladores Qt, interface QML e recursos visuais. |
| `src/liarte_engine/` | Geradores de documentos/BI e compatibilidade do motor. |
| `tests/` | Testes e dados sintéticos de regressão. |
| `tools/` | Preparação, validação, empacotamento e publicação. |
| `docs/` | Guias atuais, decisões e evidências por versão. |
| `exemplos/` e `third_party/` | Exemplos preservados, licenças e avisos de terceiros. |

O [portal de documentação](docs/README.md) reúne os caminhos de leitura. A [arquitetura](docs/ARQUITETURA.md) explica as camadas; o [estado do projeto](docs/STATUS.md) identifica a entrega atual. Documentos históricos permanecem disponíveis com suas versões e evidências.

## Licenças e distribuição

Os termos e avisos dos componentes estão em [docs/LICENCAS.md](docs/LICENCAS.md) e `third_party/`. Este repositório não atribui uma licença open source às regras LIARTE; a política de distribuição é definida pela empresa.
