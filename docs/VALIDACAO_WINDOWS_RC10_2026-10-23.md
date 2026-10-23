# RC10 — validação Windows

A [execução 39927732651](https://github.com/Souzlx/Liarte_Interf/actions/runs/39927732651) passou nos quatro jobs
em Windows Server 2025 x64, no commit `c2da61335c71e6803db1d4bdc3cc89a592a61854`.
Cada job executou **603 testes: 602 aprovados, um ignorado e nenhuma falha**.
O teste ignorado exige processos POSIX; esse caso não certifica o mecanismo
de bloqueio nativo do Windows.

| Python | Tempo da suíte | Pacote portátil RC10 |
|---|---:|---|
| 3.11 | 171,017 s | [Baixar ZIP](https://github.com/Souzlx/Liarte_Interf/actions/runs/39927732651/artifacts/12490970257) |
| 3.12 | 229,282 s | [Baixar ZIP](https://github.com/Souzlx/Liarte_Interf/actions/runs/39927732651/artifacts/12490990703) |
| 3.13 | 223,705 s | [Baixar ZIP](https://github.com/Souzlx/Liarte_Interf/actions/runs/39927732651/artifacts/12490382812) |
| 3.14 | 201,770 s | [Baixar ZIP](https://github.com/Souzlx/Liarte_Interf/actions/runs/39927732651/artifacts/12490097510) |

Os quatro executáveis compilados passaram no autoteste nativo, com versão
**5.2.0-rc.10**, Qt 6.10.3, 50 linhas por página, temas claro/escuro, ícone,
diálogo de gravação e recursos de Excel, PDF e Power BI aprovados.
Nenhum aviso QML foi registrado. HTTPS continua usando `windows-cryptoapi-v1`.

O autoteste nativo usa dados sintéticos e não acessa a API pública. O teste
real de duas consultas consecutivas, incluindo outubro de 2025 a setembro
de 2026, está em [VALIDACAO_API_RC10_2026-10-23.json](VALIDACAO_API_RC10_2026-10-23.json).
A correção, os limites e a atualização estão descritos em
[CORRECAO_HTTP_429_RC10.md](CORRECAO_HTTP_429_RC10.md).

Os resultados completos, os identificadores dos artefatos, os hashes e as
validades informadas pelo GitHub estão em
[VALIDACAO_WINDOWS_RC10_2026-10-23.json](VALIDACAO_WINDOWS_RC10_2026-10-23.json).
Os ZIPs não foram baixados neste ambiente porque o host de armazenamento
está fora da política de rede publicada. Os resultados nativos foram lidos
nos logs do CI; os arquivos internos não foram reinspecionados localmente.

Para baixar, entre na sua conta do GitHub e use um link acima. Se o link
abrir 404, abra a execução, selecione **Summary** e baixe o pacote na seção
**Artifacts**. Extraia o ZIP inteiro em uma pasta nova, feche a versão anterior
e abra `LIARTE_Desktop.exe`. Confira **5.2.0-rc.10** em Ajuda; atalhos antigos
continuam apontando para a pasta anterior.

O workflow gera o pacote portátil. Instalador Inno Setup, DPI/GPU e acesso
pela rede da empresa ainda exigem homologação no computador de destino.
As evidências RC9 permanecem históricas, sem substituição por esta execução.
