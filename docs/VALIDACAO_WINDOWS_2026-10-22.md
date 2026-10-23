# Validação Windows — concluída

O workflow manual foi executado na `main`, em Windows Server 2025 x64,
com CPython 3.11, 3.12, 3.13 e 3.14.

Na [execução final 39919861421](https://github.com/Souzlx/Liarte_Interf/actions/runs/39919861421),
o commit `b6bf99d0025481745ba3e4fae7daaeaf06fcc7a7` passou nos quatro jobs.
Cada job executou **588 testes: 587 aprovados, um ignorado e nenhuma falha**.
O teste ignorado simula uma queda de processo POSIX e exige homologação
própria para o mecanismo de bloqueio do Windows.

| Python | Tempo da suíte | Pacote portátil aprovado |
|---|---:|---|
| 3.11 | 210,043 s | [Download](https://github.com/Souzlx/Liarte_Interf/actions/runs/39919861421/artifacts/12486907970) |
| 3.12 | 209,318 s | [Download](https://github.com/Souzlx/Liarte_Interf/actions/runs/39919861421/artifacts/12487181390) |
| 3.13 | 178,587 s | [Download](https://github.com/Souzlx/Liarte_Interf/actions/runs/39919861421/artifacts/12486463190) |
| 3.14 | 205,744 s | [Download](https://github.com/Souzlx/Liarte_Interf/actions/runs/39919861421/artifacts/12486158577) |

Os quatro executáveis compilados passaram no autoteste nativo, com Qt
6.10.3, 50 linhas na página, temas claro/escuro, ícone, diálogo de gravação
e recursos de Excel, PDF e Power BI aprovados. Nenhum aviso QML foi
registrado. O transporte HTTPS usa `windows-cryptoapi-v1`.

Os resultados completos do autoteste, os identificadores dos artefatos e
os hashes informados pelo GitHub estão em
[VALIDACAO_WINDOWS_2026-10-23.json](VALIDACAO_WINDOWS_2026-10-23.json).
O autoteste usa dados sintéticos e não consulta a API pública; a validação
real de Comex Stat em Linux está documentada separadamente em
[VALIDACAO_API_REAL_2026-10-22.json](VALIDACAO_API_REAL_2026-10-22.json).

Os ZIPs não foram baixados neste ambiente porque o host de armazenamento
está fora da política de rede publicada. Os resultados nativos foram
conferidos nos logs; os arquivos internos e seus checksums não foram
recalculados localmente. Os quatro pacotes estão disponíveis nos links acima.

## Histórico do diagnóstico

| Execução | Commit testado | Resultado |
|---|---|---|
| [39877201447](https://github.com/Souzlx/Liarte_Interf/actions/runs/39877201447) | `ec78df0` | Quatro jobs falharam na etapa de testes/compilação, após instalar as dependências. |
| [39878269032](https://github.com/Souzlx/Liarte_Interf/actions/runs/39878269032) | `35a9f23` | Quatro jobs falharam novamente na etapa de testes/compilação. Nenhum pacote foi publicado. |
| [39880901606](https://github.com/Souzlx/Liarte_Interf/actions/runs/39880901606) | `9ac1bed` | Python 3.11–3.13 concluíram 587 testes e revelaram cortes de legendas; 3.11–3.12 também falharam no teste de expiração. Python 3.14 atingiu 300 s próximo ao fim da suíte. |
| [39882702056](https://github.com/Souzlx/Liarte_Interf/actions/runs/39882702056) | `301a459` | As quatro versões concluíram 588 testes. Somente a nova regressão com fontes ampliadas falhou: Limpar ultrapassou a borda de 500 px; um teste POSIX foi ignorado em cada job. |
| [39883707044](https://github.com/Souzlx/Liarte_Interf/actions/runs/39883707044) | `7dbcf72` | Python 3.11, 3.12 e 3.13 passaram e publicaram pacotes com autoteste do executável aprovado. Python 3.14 concluiu 588 testes, com uma falha na medição inicial do layout de navegação. |
| [39919861421](https://github.com/Souzlx/Liarte_Interf/actions/runs/39919861421) | `b6bf99d` | Quatro jobs aprovados, cada um com 587 testes aprovados e um ignorado. Quatro executáveis aprovados no autoteste e pacotes publicados. |

## Correção comprovada durante o diagnóstico

Os leitores de `tests/fixtures/comex_2026-09.json` dependiam da codificação
padrão do sistema. As expressões originais de leitura dos dois testes
falham com `UnicodeDecodeError` ao usar `cp1252`, na posição 1411.

O commit `35a9f23` declara UTF-8 nas leituras de fixtures, fontes e JSON
gerados, em 11 arquivos de testes. O roundtrip de `relationships.tmdl`
também grava UTF-8 para preservar os acentos. Com a correção, os leitores
carregam os 18 registros gerais e 216 municipais da fixture sintética.

A suíte completa, em Linux com codificação padrão de arquivos simulada
como `cp1252`, executou **586 testes em 113,857 s: todos passaram, sem
testes ignorados**. Isso confirma essa correção de portabilidade; não
substitui a validação no Windows.

## Diagnóstico pelos logs do Windows

Depois da publicação da permissão para
`results-receiver.actions.githubusercontent.com`, os logs foram baixados.
A primeira execução confirma `UnicodeDecodeError` na leitura da fixture com
`cp1252`, na posição 1462 no checkout Windows; a diferença para a reprodução
Linux decorre das quebras de linha do checkout.

Na segunda execução, os mocks de `urllib.request.urlopen` não interceptavam
o transporte TLS nativo do Windows. Os testes que deveriam usar fixtures
acessaram a API real, receberam HTTP 429 e provocaram falhas em cascata;
dois jobs atingiram o limite de 300 segundos. Os mocks agora interceptam
`liarte_engine.secure_http.urlopen`, comum às duas plataformas. Uma regressão
bloqueia os dois caminhos reais de rede e confirma o uso da fixture.
O transporte TLS de produção e seus requisitos de certificados permanecem
preservados.

Três testes também comparavam caminhos de maneira incompatível com Windows:
dois ignoravam a expansão do alias `RUNNER~1` por `Path.resolve()`, e um
exigia `/` no argumento de uma chamada COM. As expectativas agora acompanham
os caminhos canônicos e o separador nativo, preservando as verificações.

Nos testes Qt, a navegação por teclado agora aguarda o layout da tabela e
confirma que a linha selecionada está entre as linhas visíveis. O teste do
cabeçalho verifica a largura e a truncagem do texto efetivamente renderizado,
em vez de estimar sua largura com um dispositivo de pintura externo. Esses
ajustes tratam diferenças de agendamento e DPI do runner, mantendo as
exigências de visibilidade e legibilidade.

O teste do texto renderizado revelou cortes reais nas legendas de três
botões no Windows: Preferências, Limpar e Ver valores. As larguras fixas
foram substituídas por mínimos que acompanham as medidas intrínsecas do
conteúdo; os grupos de ações passam a se reorganizar na janela compacta.
Os atalhos de período e os botões de consulta, cancelamento e download
também respeitam o tamanho do conteúdo, preservando o modo somente ícone.
Uma regressão amplia as fontes e exige legendas completas e controles
dentro da janela. Ela falha no QML anterior e passa com a correção.

A execução `39882702056` confirmou os ajustes no tamanho normal das fontes,
mas a nova regressão encontrou um limite adicional: as duas ações dos
filtros ainda não cabiam lado a lado com letras largas. O grupo agora também
admite uma coluna. A opção Ampliar variação pode quebrar sua legenda em
linhas, com altura suficiente para exibi-las. A regressão usa fonte fixa e
medidas de letras para reproduzir esse caso também no Linux.

O teste de modo offline assumia que o instante monotônico `0` sempre
representava uma entrada expirada. Em um runner Windows iniciado há menos
de cinco minutos, a entrada ainda era válida. O teste agora usa
`time.monotonic() - 301`, incluindo a reprodução com relógio em 100 segundos.

O limite da suíte no script de compilação foi ajustado de 300 para 600 s.
Os logs de Python 3.14 mostram progresso contínuo: 581 dos 587 testes
foram iniciados em 297 s, sem um teste bloqueado. Os jobs 3.11–3.13
concluíram a suíte em 203,333 s, 220,176 s e 236,156 s, respectivamente,
com um teste POSIX ignorado em cada job. Os limites individuais dos testes
e o prazo total de 35 minutos do workflow foram preservados.

No commit `301a459`, `python verificar.py --headless --volume` executou
**588 testes em 131,362 s, todos aprovados, sem testes ignorados**, no Linux.
O ensaio de 100 mil registros concluiu a primeira consulta em
1,630 s, processando 92 eventos Qt. Cinco testes direcionados de legendas,
fontes ampliadas e clique do gráfico também passaram. A inspeção das
capturas em 500 e 1380 pixels confirmou o layout, sem avisos QML.
Após o ajuste adicional para uma coluna e quebra da legenda, os **50 testes
das três classes de interface afetadas passaram em 22,241 s**, sem testes
ignorados. A revisão independente também conferiu 760 pixels e as métricas
largas equivalentes às observadas no runner Windows.

Na execução `39883707044`, Python 3.11, 3.12 e 3.13 executaram 588 testes em
309,916 s, 172,560 s e 236,581 s, respectivamente, sem falhas e com um teste
POSIX ignorado por job. Os três executáveis compilados passaram no autoteste
e seus pacotes foram publicados. O job 3.14 teve somente uma falha: o teste
de paginação comparou a altura antes e depois do primeiro layout completo.
O painel passou de 175 para 124 pixels quando o Qt concluiu a remoção do
progresso inicial.

Esse atraso foi reproduzido localmente. A preparação dos testes de navegação
agora aguarda o frame solicitado após a conclusão do worker. As verificações
de altura, rolagem, paginação e ausência de novo worker permanecem intactas;
os **oito testes de navegação passaram em 3,307 s**. O script de compilação
também passa a registrar o JSON do autoteste nos logs, além de incluí-lo no
pacote, para permitir sua conferência sem baixar a distribuição completa.
A execução final confirmou essas correções nas quatro versões do Python.

O workflow gera a pasta portátil e testa o executável congelado. A criação
do instalador Inno Setup e a homologação de instalação, atualização,
atalhos e DPI/GPU na máquina Windows da empresa são etapas separadas.
