# Validação Windows — diagnóstico pendente

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

## Bloqueio atual

As anotações acessíveis pela API do GitHub informam apenas
`Process completed with exit code 1`. O download dos logs detalhados foi
bloqueado para `results-receiver.actions.githubusercontent.com`.
A permissão desse domínio está salva no rascunho do ambiente e precisa
ser aplicada/publicada para continuar o diagnóstico.

Ainda não foi confirmada a causa das falhas reais do CI nem quantos testes
concluíram no Windows. A próxima ação é ler os logs da segunda execução,
corrigir a causa comprovada e repetir a matriz.

O workflow gera a pasta portátil e testa o executável congelado. A criação
do instalador Inno Setup e a homologação de instalação, atualização,
atalhos e DPI/GPU na máquina Windows da empresa são etapas separadas.
