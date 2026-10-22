# Núcleo central — 5.1.0-rc.1

Esta entrega inicia a plataforma integrada da LIARTE. Importações continua sendo o módulo operacional. Estoque e Crédito aparecem em **Próximos módulos**, sem botões ativos, indicadores ou dados simulando uma implementação concluída.

## Uso

1. Abra o aplicativo. A primeira abertura começa em **Início**.
2. Clique em **Abrir Importações**, no cartão ou no menu lateral.
3. Consulte o período, aplique filtros e gere os documentos como antes.
4. Volte para **Início** e use **Retomar consulta** para continuar a mesma sessão.
5. Em **Preferências**, escolha **Início**, **Importações** ou **Última tela utilizada** para as próximas aberturas. A restauração se refere à tela, não ao carregamento automático dos dados de uma sessão encerrada.

As consultas e exportações em andamento continuam ao voltar para Início. O cartão mostra a atividade e permite acompanhá-la. Uma pendência é indicada sem duplicar mensagens técnicas. O fechamento ainda solicita a decisão do usuário quando há uma tarefa em andamento.

Atalhos: **Ctrl+1** abre Início; **Ctrl+2** abre Importações. Os atalhos do módulo, como **F5** e **Ctrl+F**, só funcionam quando ele está visível e não há um diálogo aberto. Os atalhos centrais também respeitam os diálogos.

## Organização

| Arquivo | Responsabilidade |
| --- | --- |
| `src/liarte_core/modules.py` | Cadastro imutável: identificador, título, descrição, ícone e disponibilidade. Não importa Qt nem se conecta ao ERP. |
| `src/liarte_desktop/platform.py` | Rotas válidas, módulo ativo, título da janela e escolha da tela inicial. Recusa módulos planejados ou sem página montada. |
| `src/liarte_desktop/preferences.py` | Preferências comuns; preserva as chaves históricas e informa falhas de gravação sem impedir o uso na sessão. |
| `src/liarte_desktop/app.py` | Composição e propriedade dos serviços Qt; serviços centrais têm vida independente do controlador de Importações. |
| `src/liarte_desktop/qml/Main.qml` | Janela, marca, menu, cabeçalho, preferências e fechamento. |
| `src/liarte_desktop/qml/HomePage.qml` | Acesso aos módulos e retomada da sessão. |
| `src/liarte_desktop/qml/ImportsWorkspace.qml` | Interface de Importações, filtros, indicadores, gráficos, registros e diálogos dos documentos. |

O `StackLayout` mantém as páginas instanciadas. Trocar de tela altera a página visível; não recria controlador, modelo ou consulta. A transição usa apenas opacidade, sem deslocar controles, bloquear cliques ou alterar valores. Movimento reduzido e minimização interrompem animações. O menu lateral possui rolagem independente para manter os controles acessíveis em janelas baixas.

Preferências ficam no mesmo perfil local da versão anterior. Tema, densidade, movimento e abas mensais continuam usando as chaves existentes. Apenas a navegação acrescenta `platform/startupPage` e `platform/lastPage`. Rotas desconhecidas ou indisponíveis são ignoradas; uma preferência inválida volta a Início. Os objetos de preferências e navegação pertencem à composição central, e não ao módulo de Importações.

## Preservação de Importações

O motor Comex, cache, validação, cálculos, geradores e exemplos são idênticos à 5.0.0-rc.12. A conferência é registrada em `PRESERVACAO_510.json`. No controlador, apenas a construção e a delegação de preferências mudaram; os demais métodos existentes e o worker de consulta mantêm a mesma árvore sintática.

Os testes históricos de Importações entram explicitamente nesse módulo. Os novos testes entram pela tela Início, como o aplicativo normal. Não há ramo especial de navegação para testes na composição do aplicativo.

Os escopos continuam: Excel/Power BI usam o período e cadastro completos; PDF usa filtros/busca da base geral, com as regras de peso, aeroportos e apresentação já existentes. Bases geral e municipal continuam separadas. O nome público é **Liarte** em Início e **Liarte Importações** dentro do módulo. AppID, GUID do instalador, executável, perfil, pastas e nomes dos atalhos existentes permanecem estáveis.

## Acrescentar um módulo

1. Implementar domínio e serviços próprios, com dependências recebidas na composição. Não colocar consultas ou gravações de negócio no QML.
2. Criar uma página Qt própria, com estado e ciclo de vida dos seus workers.
3. Montar os serviços em `app.py`, a página na navegação de `Main.qml` e registrar seu identificador em `MOUNTED_MODULES` de `platform.py`.
4. Cadastrar o módulo em `modules.py`. Marcar como disponível somente quando a página e os serviços estiverem montados e verificados. Uma disponibilidade sem página registrada interrompe a composição, evitando mostrar dados de outro módulo com o título errado.
5. Integrar as tarefas ao fechamento central e acrescentar testes de navegação, isolamento de dados, cancelamento e documentos.

Autenticação, permissões corporativas, servidor multiusuário, banco compartilhado e conectores Protheus/Power BI pertencem às próximas etapas. O cadastro de disponibilidade desta versão não é um controle de acesso. Não há integração corporativa simulada nem credenciais novas no cliente.

## Validação

Resultados efetivos estão em `EVIDENCIAS_510.json` e nos respectivos logs. A suíte cobre os contratos anteriores, troca de telas sem nova consulta, preservação de filtros/página/rolagem, consulta em andamento, fechamento pela tela Início, preferências, rotas inválidas, teclado e movimento reduzido. A revisão de layout inclui Início e as duas bases de Importações, cinco tamanhos e dois temas.

Os ensaios usam Linux/Qt offscreen e respostas oficiais capturadas ou dados sintéticos identificados nos testes. Não constituem nova conciliação ao vivo com o Comex, homologação do instalador Windows ou execução do Power BI Desktop.

## Referências técnicas

- Qt 6, `StackLayout`: https://doc.qt.io/qt-6/qml-qtquick-layouts-stacklayout.html
- Qt for Python 6.10, `QSettings`: https://doc.qt.io/qtforpython-6.10/PySide6/QtCore/QSettings.html
- A implementação conserva Qt/PySide6 6.10.3 e os demais requisitos fixados da versão anterior.
