# Arquitetura — 5.1.0-rc.3

Cliente modular PySide6/Qt Quick, com Início, navegação central e Importações. A composição e as preferências compartilhadas estão descritas em NUCLEO_CENTRAL_510.md. Sem navegador, WebView ou servidor HTTP local. Comex é
a fonte padrão. Dados sintéticos só são usados explicitamente em --demo, testes
e autoteste offline do pacote. Não são apresentados como resultado de consulta real.

| Componente | Responsabilidade |
| --- | --- |
| liarte_core/modules.py | Cadastro dos módulos disponíveis e planejados. |
| liarte_desktop/platform.py e preferences.py | Navegação e preferências compartilhadas. |
| Main.qml, HomePage.qml e ImportsWorkspace.qml | Estrutura central, Início e espaço persistente de Importações. |
| liarte_core/catalog.py e catalog.json | Cadastro interno e proveniência. |
| liarte_core/domain.py | Períodos, seleções, registros geral/municipal, validação e formatos. |
| liarte_core/comex.py | Disponibilidade, extração real, conversão exata e snapshot completo. |
| liarte_core/procurement.py | Agregações históricas por mês/origem, médias ponderadas, variações e completude das janelas. |
| liarte_core/query.py | Filtros, agregações, séries, busca, ordenação e paginação locais. |
| liarte_core/exports.py | Captura de escopo, temporários, publicação e auditoria. |
| liarte_engine/ | Motor extraído da 4.7.2: API, validação, cache e documentos. |
| liarte_desktop/controller.py e jobs.py | Estado desejado/aplicado, workers e sinais Qt. |
| liarte_desktop/table_model.py | QAbstractTableModel, somente a página atual na thread visual. |
| liarte_desktop/qml/ | Layout, filtros, diálogos, foco, ícones e gráficos 2D. |
| branding.py e qt_runtime.py | Marca original e busca restrita das DLLs Qt no Windows. |
| identity.py e windows_identity.py | Título público, AppID estável e IPropertyStore dos atalhos, sem dependência adicional. |
| analytics.py | Formatos e séries da análise, com custo limitado por meses e origens. |
| windows_shell.py | Pastas Windows conhecidas, atalhos próprios e marcador idempotente. |
| tools/preparation.py e assistente.py | Ambiente isolado, trava, autoteste e confirmação de abertura. |
| tools/build_windows.py | Onedir, avisos/licenças, testes, smoke e publicação com backup. |
| build_installer.py e INSTALADOR_LIARTE.iss | Setup por usuário, atualização e desinstalação. |

## Fonte, precisão e cache

Metadados geral/municipal são independentes. POSTs de dados são espaçados, não
disparados em paralelo. Cada mês tem validação/cache próprios. Ambas as bases
devem estar completas antes de publicar o snapshot imutável. O cadastro inteiro
é consultado uma vez por período; filtros/páginas usam o snapshot local.

Availability registra disponibilidade, atualização, horário e uso de metadados
armazenados. Revisão composta geral/municipal participa do cache. Há limite de
tamanho/tempo de leitura, timeout e retentativas limitadas, inclusive para 429.
Esperas cooperam com o Event de cancelamento; socket bloqueado pode aguardar o
timeout. Não há promessa de cancelamento instantâneo de toda operação de rede.

ImportRecord mantém NCM, UF/URF, país, centavos FOB/frete/seguro/CIF e kg.
MunicipalRecord mantém SH4, município fiscal, UF, país, FOB e kg; não fornece
CIF válido nem reconstrói NCM/URF. As 27 siglas, ND e EX têm tratamento explícito.
UF desconhecida, precisão inesperada ou CIF divergente interrompem o lote.

DatasetQuery usa LRU limitado a quatro recortes, seis visões e um índice de busca.
Predicados são preparados uma vez: união dentro da dimensão, interseção entre
dimensões. Ordenação em blocos de 4.096 com merge cooperativo e Fraction para
preços. Agregação/ordenação precedem paginação. Busca não altera indicadores.
Zero kg não provoca divisão por zero. Totais não passam por float.

## Estado e tarefas

Somente slots do controlador na thread Qt alteram modelo/apresentação. Workers
emitem progresso/resultado/erro. Disponibilidade, consulta e exportação possuem
ciclos de vida próprios; o fechamento espera seu término. Callbacks de rede e
documento não manipulam QML. Respostas obsoletas são descartadas.

Seleção desejada e aplicada são distintas; debounce consolida alterações rápidas.
O último resultado aceito permanece identificado durante atualização. Cancelamento
restaura seus filtros/controles; falha não publica dados parciais. presentation e
analysis possuem sinais distintos para evitar redesenhar gráficos ao mudar linha.

ExportRequest captura snapshot, período e seleção. Excel/BI usam base completa;
PDF usa filtros e busca de toda a tabela. Temporários ficam no volume do destino;
validação antecede os.replace. Cancelamento/falha preservam arquivo anterior.
Manifesto SHA-256, período e atualização da fonte fica no perfil; falha de auditoria
não invalida um documento que já foi salvo corretamente.

## Documentos, interface e distribuição

Motor da 4.7.2 preservado com imports relativos, cancelamento injetável e ajuste
Decimal no PDF. Organização das planilhas, cabeçalhos curtos, grades, alinhamento
vertical central, UF sigla, Base municipal E=64 e abas mensais foram mantidos.
PDF: título Importações filtradas, nomes comerciais, países diretos, portos,
corte estrito >1.000 kg antes da consolidação e exclusão de aeroportos.
BI gera PBIP/TMDL/PBIR; referências são conferidas, mas renderização requer Desktop.

Janela reorganiza a partir de 500 × 400 lógicos com rolagem. Filtros pesquisáveis
multisseleção têm aplicação explícita/tooltip. Meses cabem por extenso. Ícones
vetoriais e animações curtas respeitam redução de movimento. Texto de dados é
PlainText; Narrador e múltiplos monitores precisam de Windows real.

Preferências QSettings e cache/logs ficam no perfil, fora da instalação. Somente
tema/densidade/movimento são migrados da F1 quando não há preferências novas.
O cliente é local; cache não é banco corporativo nem backup de relatórios.

Assistente usa ambiente filho isolado, verifica versões, testa Qt/documentos e
aguarda confirmação da janela. Reparo automático é limitado. Onedir mantém
bibliotecas separadas e coleta apenas recursos Qt necessários. Licenças e smoke
são obrigatórios antes de publicar. A versão portátil anterior tem backup/rollback.

Inno Setup usa AppId separado da 4.7.2, perfil externo e escolha na desinstalação.
Atalhos usam SHGetKnownFolderPath para Desktop/Programs redirecionados; sucesso
só é registrado depois da existência dos dois arquivos. Recriação protege atalhos
alheios; não há toast recorrente. Testes de Windows são simulados, não execução.

## Reproduzir e evoluir

Ambiente preparado: python verificar.py --headless --volume.
Fonte real: python verificar_comex.py --inicio 2026-07 --fim 2026-09.
A segunda operação usa internet e grava relatório em logs; revisões oficiais
podem alterar atualização e totais. O script respeita espaçamento/limites da fonte.

Serviço central, identidade, permissões, Protheus, SQL Server e tarefas multiusuário
devem ser implementados em camadas próprias nas próximas fases. Não há credenciais
do ERP distribuídas neste cliente.

## Componentes de apresentação RC2

MetricCard exibe valores finais com transição curta de opacidade, sem contagem
numérica artificial. OriginChart desenha participação proporcional ao total de
todas as origens e limita a apresentação a seis. FilterChip remove uma dimensão
sem alterar outras; MultiCombo mantém aplicação explícita e busca.

LinePlot separa grade, curva e guia de hover. O Canvas da curva tem geometria fixa;
o efeito de revelação altera apenas o recorte no scene graph. Hover move itens
simples e não repinta a curva. Redução de movimento interrompe os efeitos em curso.
Reorganização de layout não é animada, preservando foco e leitura durante resize.

A tela inicial omite indicadores/gráficos vazios e não exibe a contagem fictícia
inicial do antigo demonstrador. Informação técnica de versão/fonte/metodologia
fica em Ajuda ou diagnóstico. O texto visual de erros de rede é simplificado;
a mensagem integral continua no controlador/log. Erros de validação de métricas
continuam explícitos, sem esconder divergências.


## Referências de compra (RC3)

ProcurementBuilder é acumulado no mesmo percurso dos registros selecionados e
finalizado no worker antes da busca/paginação. Procurement e Aggregate são
imutáveis e fazem parte do _Scope LRU. Cancelamento é conferido também na
finalização. Meses e origens vêm exclusivamente do recorte, sem buscar dados
fora do intervalo para completar médias. Alterar busca/ordenação/página reutiliza
a mesma agregação; o controlador mantém uma única apresentação formatada em cache.

Valor/peso móvel usam soma/3 dos três meses; preço móvel usa soma de valores/soma
de kg, exigindo peso positivo nos três meses. Variação é (atual/anterior - 1) × 100;
base zero/ausente não define percentual. A base municipal só fornece FOB, kg e SH4.
Pesos zero mantêm os valores oficiais nos totais e geram sinalização de qualidade;
preço só existe se o peso total do agregado é positivo. Nenhuma previsão é produzida.

As séries QML têm escala e unidade explícitas, nulos preservados, traçado com
lacunas e média móvel no mesmo Canvas. A animação modifica apenas o recorte do
scene graph. O comparador inicia com oito países e permite ordenar/expandir a lista; seu limiar
local não altera o recorte, a referência agregada, tabela ou documentos.

ApplicationName/organização/perfil, AppID de Shell e GUID do instalador não foram
renomeados. ApplicationDisplayName e título usam Liarte Importações. SetIcon é
chamado antes de mostrar a janela. O mesmo ICO é incorporado pelo PyInstaller.
Atalhos WScript são identificados por IPropertyStore com COM inicializado na
thread responsável, HRESULT conferido e limpeza balanceada. O marcador só é
publicado depois de ambos os atalhos e propriedades terem sido gravados.


## Experiência de uso (RC4)

Origin inclui meses com kg positivo; Procurement preserva o nome de um produto
único. A apresentação mantém todas as origens e calcula ranks de preço com
Fraction. QML filtra/ordena esse conjunto antes de exibir oito/mais linhas.
Metadados de cobertura são descritivos e não afetam os totais.

Atalhos de período só alteram o rascunho. Navegação anima contentY sem executar
cálculos de dados por quadro; movimento reduzido interrompe a animação. Baixar
no topo delega à mesma função de diálogo/exportação usada anteriormente.

LinePlot conserva uma pintura por atualização de série; marcador/foco/leitura
usam itens do scene graph. A escala é local, explícita, comum às duas linhas;
eixos cortados não usam área. TrendDialog só instancia linhas ao abrir e usa
unidades completas; copyTrendData copia valores formatados com cabeçalhos corretos.
Acessibilidade Qt oferece nome do valor atual e instruções curtas. Nenhuma dessas
ações lê novamente a fonte ou muda os filtros/escopo dos documentos.


## RC5: preparação, instalação e movimentos

O assistente serializa a preparação por trava do sistema operacional. Um SHA-256 de código/recursos/requisitos/runtime identifica uma verificação completa reutilizável por até sete dias; versões instaladas e handshake da janela são conferidos sempre. Falhas invalidam a marca. Build e reparo sempre repetem o teste. A saída do Setup é compilada/validada em estágio privado e publicada por substituição no mesmo volume. A versão vem do módulo do aplicativo, sem importar Qt.

No Windows, installation_guard mantém um handle CreateMutexW tipado até o fim do processo; o Inno usa o mesmo nome em AppMutex. A referência não restringe múltiplas janelas. SetupMutex impede instalações simultâneas. AppId/perfil/atalhos permanecem estáveis. A validação Windows nativa ainda é uma etapa de homologação.

Theme.motionEnabled considera movimento reduzido e janela visível/não minimizada. Animações terminam no valor final quando inativas; TaskProgress interpola apenas a geometria, preservando value e acessibilidade reais. Os filtros inicializam no aboutToShow, antes de receber digitação. A logo do PDF é o recurso desktop já incluído no bundle, acessado por Path sem dependência de Qt no gerador. Não há alteração na paginação ou geometria da tabela.
