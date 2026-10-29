# Suporte

Use os guias abaixo para instalar, atualizar e consultar a LIARTE. Para descrever um problema ou sugerir uma melhoria, utilize as [issues do repositório](https://github.com/Souzlx/Liarte_Interf/issues/new/choose).

| Necessidade | Referência |
| --- | --- |
| Baixar o aplicativo | [Releases e arquivos compilados](https://github.com/Souzlx/Liarte_Interf/releases) |
| Instalar ou atualizar a versão estável | [Instalação e atualização — 5.3.1](docs/INSTALACAO_531.md) |
| Entender a interface e os filtros | [Interface por tarefa](docs/GUIA_INTERFACE_MODULAR.md) |
| Consultar giro, rankings e ordenações | [Desempenho dos produtos](docs/DESEMPENHO_PRODUTOS.md) |
| Entender alertas e variações mensais | [Alertas](docs/ALERTAS_ESTOQUE.md) e [comparador mensal](docs/COMPARADOR_MENSAL_ESTOQUE.md) |
| Desenvolver ou compilar os fontes | [Contribuição](CONTRIBUTING.md) e [desenvolvimento no Windows](docs/DESENVOLVIMENTO_LOCAL_WINDOWS.md) |

## Conferências rápidas

- **Instalação:** feche a LIARTE e execute o novo Setup na mesma conta Windows. Abra pelo atalho criado pelo instalador e confira a versão em **Ajuda**.
- **Pacote portátil:** extraia todo o ZIP em uma pasta nova e mantenha `_internal` junto de `LIARTE_Desktop.exe`. O ZIP de fontes do GitHub é outra distribuição. Setup e portátil incluem Python.
- **Consulta pausada:** se o Comex Stat solicitar uma pausa, aguarde o intervalo informado pelo aplicativo antes de consultar novamente.
- **Indicadores diferentes:** confira período, unidade, filtros, data da base e fonte do indicador. As bases geral e municipal do Comex têm escopos e valores CIF/FOB diferentes; giro da fonte e cobertura estimada também têm definições próprias.

## Relatar um problema

Abra o formulário [Relatar um problema](https://github.com/Souzlx/Liarte_Interf/issues/new?template=bug_report.yml). Basta descrever o que aconteceu; as demais informações podem ser acrescentadas quando disponíveis:

- O que você tentava fazer e qual resultado esperava.
- Versão exibida em **Ajuda** e uso por Setup, ZIP portátil ou fontes.
- Passos para reproduzir e mensagem exata do erro.
- Versão do Windows; escala da tela quando a falha for visual. Para execução dos fontes, informe a versão do Python se souber.
- Captura ou exemplo sintético que ajude a mostrar o comportamento.

Use somente o trecho de diagnóstico necessário. Remova dados da empresa e credenciais de mensagens ou capturas. Não anexe PBIX, bases de estoque, exportações empresariais ou logs completos; descreva o caso ou reproduza-o com dados sintéticos.

## Sugerir uma melhoria ou tirar uma dúvida

No formulário [Sugerir uma melhoria](https://github.com/Souzlx/Liarte_Interf/issues/new?template=feature_request.yml), explique qual tarefa ou decisão quer facilitar. Para indicadores, descreva o período, a unidade e o nível de análise desejado, por exemplo produto, filial ou mês.

Se a dúvida continuar após consultar os guias, abra uma [issue](https://github.com/Souzlx/Liarte_Interf/issues/new) com a tarefa que deseja realizar e o ponto em que encontrou dificuldade. Não é necessário conhecer os detalhes técnicos do aplicativo.
