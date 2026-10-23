# RC10 — recuperação de consultas consecutivas

## Problema e comportamento corrigido

Na RC9, a primeira consulta podia concluir e a seguinte, feita logo após
alterar o período, terminava com “Comex Stat solicitou uma pausa (HTTP 429).
Aguarde 11 s”. A recuperação permitia somente duas tentativas. A sequência
controlada `429 → 429 → 200` encerrava a operação antes da terceira resposta.

A RC10 mantém a consulta aberta para recuperar recusas curtas repetidas.
O transporte repete somente o endpoint afetado. Se a base geral já foi
obtida, uma recusa na base municipal não provoca outro download da geral.
O resultado completo anterior permanece visível até a nova consulta concluir
e validar ambas as bases. A espera informa a contagem regressiva e permite
cancelar.

## Limites da recuperação

- O desktop permite até quatro tentativas no endpoint afetado por HTTP 429,
  com orçamento de 90 segundos por endpoint para esperas de recuperação.
- O primeiro prazo vem de `Retry-After`, quando válido, ou da mensagem do
  MDIC. A margem de 0,5 segundo evita antecipar o prazo. Sem prazo, o recuo
  é de 30 segundos.
- Recusas repetidas ampliam o recuo, respeitando sempre o prazo da fonte.
  Para pausas sucessivas de 10 segundos, as esperas são 10,5, 21 e 42 segundos,
  se couberem no orçamento. A quarta tentativa ainda pode concluir a consulta.
- Uma pausa maior que o orçamento é preservada, inclusive após reabrir o
  aplicativo. Uma recusa persistente termina com o prazo remanescente.
- Erros de conexão e de serviço continuam limitados à recuperação curta de
  até duas ocorrências transitórias, dentro do limite total de tentativas.
  Certificados inválidos, HTTP 403, redirecionamentos e respostas incoerentes
  não recebem novas tentativas.
- Não há intervalo preventivo fixo entre respostas bem-sucedidas, troca de IP,
  cache de resultados, central ou alternativa CSV. A consulta normal continua
  fazendo somente um POST geral e outro municipal quando ambos têm sucesso.

Ao terminar uma pausa sem recuperação, a interface usa o contador vigente.
Depois da expiração, informa que uma nova consulta pode ser feita, sem
conservar uma mensagem estática de “11 segundos”. O diagnóstico técnico
original continua disponível no perfil local.

O limite da API pertence ao serviço externo e pode depender de outros
acessos na mesma rede. A correção trata a recuperação do aplicativo; não
determina nem contorna a quota da fonte.

## Atualização do pacote Windows

Feche a RC9, extraia o ZIP completo da RC10 em uma pasta nova e abra o
`LIARTE_Desktop.exe` dessa pasta. Confira **5.2.0-rc.10** em Ajuda. Um atalho
antigo continua apontando para o executável anterior. O pacote portátil já
inclui Python; as configurações e a base de estoque no perfil local são
preservadas.

## Validação

Os testes controlados cobrem recusas repetidas, prazos longos, orçamento
finito, cancelamento, preservação do primeiro resultado e recuperação da
base municipal sem repetir a geral. A reprodução Qt usa a mesma janela e
a troca de setembro de 2026 para outubro de 2025 a setembro de 2026.

A suíte completa `python verificar.py --headless --volume` passou no Linux:
**599 testes em 124,489 s, sem falhas nem testes ignorados**. O ensaio de
100 mil registros fez a primeira consulta em 1,678 s e processou 92 eventos Qt.
Os testes direcionados de transporte, interface e versão também passaram.

A consulta real consecutiva e os links do novo pacote serão registrados após
concluir a verificação externa e a compilação nativa Windows.

As evidências RC9 são históricas e permanecem em
[NOVO_CLIENTE_API_520_RC9.md](NOVO_CLIENTE_API_520_RC9.md) e
[VALIDACAO_WINDOWS_2026-10-22.md](VALIDACAO_WINDOWS_2026-10-22.md).
