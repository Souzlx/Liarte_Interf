# LIARTE 5.2.0 — entrega estável

A [versão 5.2.0](https://github.com/Souzlx/Liarte_Interf/releases/tag/v5.2.0) está publicada como estável e marcada
como Latest. O usuário informou a confirmação inicial de consultas,
exportações e preservação de estoque/preferências na RC10. A promoção preserva
a lógica validada e atualiza a identificação do aplicativo para 5.2.0,
com versão numérica Windows 5.2.0.101 e sem a flag de prévia.

O [workflow 39930596631](https://github.com/Souzlx/Liarte_Interf/actions/runs/39930596631) validou o commit
`35ea46c937491c6e78b6b8429a9bc5532d81458d`, também usado pela tag `v5.2.0`.
Os quatro jobs executaram 610 testes cada, sem falhas. Um caso que exige
processos POSIX foi ignorado em cada job Windows.

| Python | Aprovados | Ignorados | Tempo da suíte |
|---|---:|---:|---:|
| 3.11 | 609 | 1 | 193,697 s |
| 3.12 | 609 | 1 | 230,225 s |
| 3.13 | 609 | 1 | 221,003 s |
| 3.14 | 609 | 1 | 249,235 s |

Os quatro executáveis passaram no autoteste nativo com versão 5.2.0,
Qt 6.10.3, temas claro/escuro, 50 linhas na página, ícone, diálogo de gravação
e recursos de Excel, PDF e Power BI aprovados, sem avisos QML. O transporte
HTTPS continua usando windows-cryptoapi-v1. Os 21 testes direcionados de
versão/distribuição e os sete testes da preparação da release também passaram.

A publicação depende do sucesso dos quatro builds. O job de release baixa
o pacote Python 3.12 do mesmo workflow, confere versão/autoteste e todos os
checksums, prepara o ZIP e publica os anexos. Uma tag existente encerra o
fluxo sem substituição. O modo de publicar é opcional no disparo manual e
exige a branch main.

O [ZIP publicado](https://github.com/Souzlx/Liarte_Interf/releases/download/v5.2.0/LIARTE_Desktop_5.2.0_Windows_x64.zip) foi baixado novamente
neste ambiente: seus 1.394 arquivos de manifesto conferem, assim como o hash
do ZIP no SHA256SUMS.txt e no metadado do GitHub. O pacote tem 1.395 arquivos,
incluindo o próprio manifesto, e executável AMD64. Nenhum executável Windows
foi executado no Linux. O autoteste nativo usa dados sintéticos; as duas
consultas reais consecutivas estão em
[VALIDACAO_API_RC10_2026-10-23.json](VALIDACAO_API_RC10_2026-10-23.json).

Dados completos dos jobs, autotestes, artefatos, release e auditoria estão em
[VALIDACAO_ESTAVEL_520_2026-10-23.json](VALIDACAO_ESTAVEL_520_2026-10-23.json).
As instruções de atualização estão em [RELEASE_5.2.0.md](RELEASE_5.2.0.md).
Esta entrega é portátil; não houve nova compilação ou certificação do Setup.
A RC10 e seus relatórios permanecem no histórico.
