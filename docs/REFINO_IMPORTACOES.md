# Refino da análise de importações

A tela prioriza o período, os indicadores, os filtros e os gráficos. O título passa a ser **Análise de importações**. O resumo recolhido apresenta apenas as datas; nomes técnicos da classificação e da valoração ficam nos contextos correspondentes, sem duplicar o período.

Durante uma consulta com progresso mensurável, o cabeçalho mostra a barra e a porcentagem. Operações sem estimativa não inventam um percentual. Ordenação, paginação e filtros rápidos preservam a posição da tela e o indicador discreto já existente na tabela.

## Atualização automática

O Comex continua sendo verificado automaticamente em segundo plano, com intervalo e coalescimento das tarefas. Consultas usam os dados aceitos sem esperar por uma nova aquisição. A verificação sem novidade não baixa dados novamente; auditorias periódicas mantêm a detecção de correções retroativas. Quando uma auditoria recebe os mesmos dados e referências válidas, a geração, os recibos e o backup existentes são preservados. Conteúdo ou referências danificados continuam sendo reparados.

O controle manual fica em **Preferências → Atualizações de importações → Verificar atualizações**. Cobertura, referências técnicas, pausa e backup aparecem nessa área separada. O diálogo preserva teclado, cancelamento e bloqueio dos atalhos do dashboard.

## Cartões

Os cartões usam altura natural, margem interna consistente e alinhamento vertical do conteúdo. Título, ícone, valor e detalhe permanecem dentro do quadro. Valores monetários, unidades, denominadores, fórmulas, filtros e exportações foram preservados.

## Validação e capturas

Fontes `6b4c4d7`: **1.411 testes em 88 módulos**, sem falhas, erros ou skips no Linux, em 270,059 s. O volume usou 100 mil registros em 1,424 s, com 87 eventos Qt. Os 18 testes de organização também passaram. O [CI Linux](https://github.com/Souzlx/Liarte_Interf/actions/runs/43219471810) e os quatro jobs da [matriz Windows](https://github.com/Souzlx/Liarte_Interf/actions/runs/43219478235) foram aprovados. Cada job Windows exige pré-validação Qt, suíte completa, compilação e autoteste do executável antes do upload.

A revisão adicional reproduziu e corrigiu a preservação indevida de recibos de data inválidos durante uma auditoria idêntica. As duas regressões novas cobrem nove subcasos e a recuperação da consulta após a auditoria. Os [resultados, hashes e limites](EVIDENCIAS_REFINO_IMPORTACOES.json) identificam exatamente os fontes e as capturas.

Os estados dos jobs e etapas Windows foram confirmados pela API. Os logs detalhados ficaram bloqueados no armazenamento do GitHub; não se declara aqui uma contagem nativa de aprovações ou skips sem esses logs.

As capturas abaixo são da aplicação Qt real, com dados sintéticos de teste, sem consultas à API pública ou dados da empresa.

![Resumo em janela ampla, dados sintéticos](images/refino-importacoes/importacoes-summary-sintetico.png)

![Compras em janela ampla, dados sintéticos](images/refino-importacoes/importacoes-buying-sintetico.png)

[Carregamento simulado](images/refino-importacoes/importacoes-carregamento-sintetico.png) · [Cartões em 500×400, tema escuro](images/refino-importacoes/importacoes-compacta-escura-sintetico.png) · [Atualização nas Preferências](images/refino-importacoes/importacoes-preferencias-sintetico.png).

## Pacote de teste

[Baixar o portátil Windows Python 3.12](https://github.com/Souzlx/Liarte_Interf/actions/runs/43219478235/artifacts/13945053893). Se o link não abrir, entre na conta com acesso ao repositório e procure **Artifacts** na [execução](https://github.com/Souzlx/Liarte_Interf/actions/runs/43219478235). Artefatos do Actions têm retenção limitada.

O GitHub informa 94.457.214 bytes e o digest `04181abcbf2efb6a7691702a67886dd9e35f421e237f17ff0c1ecbed18ff5123`. O ZIP e os logs desta execução foram direcionados a `productionresultssa17.blob.core.windows.net`, que recebeu HTTP 403 do proxy. A conferência independente do ZIP permanece pendente. Foi salvo um rascunho de permissão para `*.blob.core.windows.net`; isso requer revisão, salvamento e publicação do ambiente e não comprova liberação na sessão atual.

Entrega no [PR #16](https://github.com/Souzlx/Liarte_Interf/pull/16), com a [relação completa de arquivos alterados](https://github.com/Souzlx/Liarte_Interf/pull/16/files).

Extraia a pasta inteira e abra `LIARTE_Desktop.exe`; o runtime Python está incluído. A consulta, os filtros, as exportações e a retomada continuam usando o mesmo perfil. A conferência visual manual no Windows permanece separada dos testes automatizados. Esta entrega não publica uma nova release nem altera a versão instalada anteriormente.
