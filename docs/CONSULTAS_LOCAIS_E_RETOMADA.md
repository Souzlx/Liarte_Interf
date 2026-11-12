# Consultas locais, retomada e cópias de segurança

Melhoria dos fontes em desenvolvimento, posterior à 5.3.1 publicada. Usa o histórico SQLite de Importações e a base local de Estoque já existentes. A conexão SQL Server da empresa continua separada desse armazenamento local.

## Ao fechar e reabrir

Depois de uma consulta concluída, Importações guarda período, base geral ou municipal, filtros, busca, ordenação, página e tamanho da página. A gravação só considera um resultado aceito; escolhas pendentes, cancelamentos e falhas não substituem a última consulta válida.

Ao iniciar com o mesmo perfil, o aplicativo recupera a seleção e consulta a versão aceita do banco local em um worker. A Visão geral recebe os indicadores mesmo sem entrar em Importações. A recuperação não solicita download nem verificação da API. Uma atualização automática da fonte, se iniciada pelo fluxo normal do módulo, continua independente da leitura local.

Se a revisão dos dados mudou, a seleção é recalculada e a interface informa a revisão local atual. O aplicativo não apresenta números antigos como atualização bem-sucedida. Cobertura ausente ou dados inválidos permanecem identificados. A referência de publicação e aquisição acompanha os resultados e exportações.

No Estoque, o perfil recupera a base local e reaplica filtros válidos, mês em análise, unidade e ordenação. As escolhas são validadas contra a base atual antes do cálculo. Opções que deixaram de existir não são reaplicadas; nesse caso, o módulo abre o recorte padrão válido da base atual.

A primeira consulta feita nesta implementação cria o checkpoint. Versões anteriores não registravam todas essas escolhas; o aplicativo não tenta adivinhar uma consulta que nunca foi salva. Perfis novos, demonstração e execução sem configurações não herdam o estado do perfil de uso.

## O que foi otimizado

| Camada | Implementação | Controle de consistência |
| --- | --- | --- |
| SQLite | Um cursor indexado para os fatos do período; gravações em lotes canceláveis de 256 registros | Hashes individuais e mensais, contagens, cobertura e geração aceita preservados |
| Índices | `manifest_by_period`, combinado com `facts_by_month` | Atualização aditiva na próxima transação de escrita; catálogo e versão lógica não mudam |
| Períodos | Até dois snapshots preparados, com limite conjunto de 100 mil fatos | Chave por período e revisão; nova revisão, mudança de origem e fechamento invalidam a reutilização |
| Busca | Até quatro índices de texto normalizado, reutilizados ao alternar recortes | Identidade da coleção imutável; alteração da fonte elimina os índices |
| Dashboard | Formatação de séries, origens e indicadores no worker | Apresentação associada às mesmas coleções aceitas; cancelamento descarta o resultado |
| Páginas e ordenações | Reutilizam recortes e apresentações completos, limitados em memória | Sem reler a fonte nem recalcular métricas quando o resultado preparado é reutilizável |
| Estoque | Opções já preparadas na recuperação são reutilizadas na apresentação | Sem uma segunda varredura apenas para validar os filtros salvos |

O banco mantém catálogos, execuções, etapas, fatos, cobertura mensal, gerações e manifesto separados. A melhoria preserva esse modelo e seus índices; não exige apagar a base, alterar o catálogo ou baixar novamente o histórico. A primeira leitura continua validando o conteúdo; o maior ganho ocorre ao reutilizar períodos e análises já preparados.

Não são feitas somas monetárias em ponto flutuante no SQLite. Valores exatos, lacunas, zero conhecido, NCM/CIF e SH4/FOB conservam os contratos existentes.

## Arquivos do perfil

| Caminho relativo ao perfil | Finalidade |
| --- | --- |
| `dados/historico_comex.sqlite3` | Dados aceitos e etapas de extração retomáveis |
| `dados/ultima-consulta.json` | Seleção aceita, identidade do catálogo, revisão e horário |
| `dados/ultima-consulta.json.previous` | Checkpoint anterior válido, usado se o principal não puder ser lido |
| `estoque/ultima-consulta-estoque.json` | Recorte e apresentação mensal do Estoque |
| `estoque/ultima-consulta-estoque.json.previous` | Checkpoint anterior do Estoque |
| `dados/backups-comex/` | Cópias consistentes do banco e seus manifestos |

Os checkpoints são JSON limitado, versionado, com checksum e publicação por substituição atômica. Um gravador em segundo plano agrupa alterações rápidas e conclui a última gravação no encerramento normal. Não há serialização executável. Esses arquivos e backups não pertencem ao Git.

## Cópias do banco

O worker de atualização cria uma cópia quando há uma geração aceita ainda sem backup, inclusive ao preservar uma base válida após falha de atualização. Usa a API online de backup do SQLite para incluir corretamente dados confirmados no WAL. Não copia isoladamente o arquivo principal de um banco aberto.

Cada cópia contém `historico.sqlite3` e `manifest.json`, com catálogo, revisão, cobertura e SHA-256. A publicação ocorre depois da conferência estrutural e de integridade. A política padrão conserva cinco cópias verificadas por catálogo, removendo excedentes apenas depois de publicar uma nova cópia válida. A mesma revisão não gera cópias repetidas em cada consulta. A tarefa aceita cancelamento e não bloqueia consultas à base aceita.

As cópias são locais à instalação. Sua criação depende de o worker executar e de haver espaço e permissão para gravação. A recuperação de consulta usa o banco persistente; um backup separado serve para recuperar um arquivo perdido ou danificado.

### Conferir e recuperar pelos fontes

```sh
python tools/comex_backup.py /caminho/da/copia
python tools/comex_backup.py /caminho/da/copia --recover-to /caminho/novo/historico_comex.sqlite3
```

A ferramenta verifica o checksum, o catálogo, a revisão e as estruturas SQLite. O destino precisa ser novo: ela recusa substituir um banco existente ou seus arquivos WAL/SHM. Para recuperar o perfil em uso, feche o aplicativo, preserve o banco anterior e seus arquivos auxiliares em outra pasta e só então recupere para o caminho esperado. Os dados originais não são apagados pela ferramenta.

O utilitário é uma ferramenta dos fontes. Uma interface gráfica de recuperação do histórico e a homologação de um novo pacote Windows são etapas separadas. Estoque conserva seu fluxo gráfico de backups e restauração existente.

## Verificação

```sh
python verificar.py --headless --volume --isolate
python tools/check_repository.py
python -m unittest discover -s tests/repository -v
python tools/benchmark_dashboard.py --rows 50000 --output /tmp/benchmark.json
```

Os ensaios usam dados sintéticos e impedem acesso à rede. Incluem reinício da aplicação na Home, recuperação de filtros, revisão alterada, falha de consulta, erro de gravação, corrupção do checkpoint principal, WAL, cancelamento, retenção, recuperação para arquivo novo e conferência dos valores exatos. A medição da camada de consulta é distinta do tempo total de desenho da janela e da primeira aquisição oficial.

## Resultados registrados

Python 3.12.14 e Qt 6.10.3 no Linux: **1.398 testes em 88 módulos**, sem falhas, erros ou skips. Os 18 testes de organização também passaram. Os [resultados, hashes e limites](EVIDENCIAS_CONSULTAS_LOCAIS.json) identificam os fontes e as capturas.

Ensaio sintético com 50 mil fatos gerais, 12 municipais e valores acima da precisão de ponto flutuante: três execuções sequenciais por versão, em processos novos. Medianas da camada de consulta:

| Operação | Antes | Depois |
| --- | ---: | ---: |
| Leitura SQLite de 12 meses | 2,429 s | 2,340 s |
| Consulta fria, incluindo leitura e preparação | 5,297 s | 5,005 s |
| Voltar ao período anterior já preparado | 5,337 s | 0,000836 s |
| SELECTs para ler 12 meses nas duas bases | 26 | 3 |

O digest dos totais exatos, séries e países coincidiu em todas as seis execuções. O ganho de aproximadamente 99,98% no retorno ao período decorre do reaproveitamento por revisão; não é uma promessa sobre download, primeira carga ou tempo total da janela.

A conferência adicional de backup manteve um leitor na geração anterior enquanto novos fatos confirmados permaneciam no WAL. A cópia recuperou exatamente a geração nova e um valor superior a 64 bits, preservando os dados originais.

## Capturas Qt

Dados sintéticos e interface Qt real, incluindo recuperação automática, aviso de backup e uso de teclado. A janela ampla usa 1600×900 e a compacta 500×400.

[Home recuperada](images/dashboard-retomada/home-recuperada-sintetico.png) · [Consulta recuperada e backup](images/dashboard-retomada/consulta-recuperada-backup-sintetico.png) · [Janela compacta escura](images/dashboard-retomada/consulta-recuperada-compacta-sintetico.png).

As capturas e os testes confirmam o período recuperado sem rascunho pendente, deixando a exportação disponível. A compilação e a conferência de um novo pacote Windows não são declaradas por esses ensaios Linux.
