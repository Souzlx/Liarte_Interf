# Validação Windows — correções de portabilidade

O workflow manual foi executado na `main`, em Windows Server 2025 x64,
com CPython 3.11, 3.12, 3.13 e 3.14.

| Execução | Commit testado | Resultado |
|---|---|---|
| [39877201447](https://github.com/Souzlx/Liarte_Interf/actions/runs/39877201447) | `ec78df0` | Quatro jobs falharam na etapa de testes/compilação, após instalar as dependências. |
| [39878269032](https://github.com/Souzlx/Liarte_Interf/actions/runs/39878269032) | `35a9f23` | Quatro jobs falharam novamente na etapa de testes/compilação. Nenhum pacote foi publicado. |

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

Com esses ajustes, `python verificar.py --headless --volume` executou
**587 testes em 127,010 s, todos aprovados, sem testes ignorados**, no Linux.
O ensaio de 100 mil registros concluiu a primeira consulta em 1,775 s,
processando 87 eventos Qt. A matriz Windows será repetida com as correções.
Até uma execução bem-sucedida, o pacote Windows continua sem validação
concluída.

O workflow gera a pasta portátil e testa o executável congelado. A criação
do instalador Inno Setup e a homologação de instalação, atualização,
atalhos e DPI/GPU na máquina Windows da empresa são etapas separadas.
