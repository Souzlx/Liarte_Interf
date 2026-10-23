# RC10 — recuperação de consultas consecutivas

## Problema e comportamento corrigido

Na RC9, a primeira consulta podia concluir e a seguinte, feita logo após
alterar o período, terminava com “Comex Stat solicitou uma pausa (HTTP 429).
Aguarde 11 s”. A recuperação permitia somente duas tentativas. A sequência
controlada `429 → 429 → 200` encerrava a operação antes da terceira resposta.

A RC10 mantém a consulta aberta para recuperar recusas curtas repetidas.
O transporte repete somente o pedido afetado. Se a base geral já foi
obtida, uma recusa na base municipal não provoca outro download da geral.
O resultado completo anterior permanece visível até a nova consulta concluir
e validar ambas as bases. A espera informa a contagem regressiva e permite
cancelar.

## Limites da recuperação

- O desktop permite até quatro tentativas no pedido afetado por HTTP 429,
  com orçamento de 90 segundos por pedido para esperas de recuperação.
  Esses limites valem para cada faixa anual de cada base, não para a consulta
  completa quando ela abrange vários anos.
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
  cache de resultados, central ou alternativa CSV. Para um período no mesmo
  ano, a consulta normal faz um POST geral e outro municipal. Períodos que
  atravessam anos fazem um pedido de cada base por ano civil abrangido.

## Períodos que atravessam anos

Na verificação externa, setembro de 2026 retornou dados, mas o período de
outubro de 2025 a setembro de 2026 retornou listas vazias nas duas bases, com
HTTP 200. Como o intervalo inclui aquele mês, a resposta vazia não representa
corretamente o período. A documentação pública informa o formato `AAAA-MM`,
mas não explica essa diferença; a causa interna do serviço não foi confirmada.

A RC10 divide esses intervalos por ano civil: outubro a dezembro de 2025 e
janeiro a setembro de 2026, no exemplo. Cada resposta é validada dentro da
sua faixa e o resultado completo só é publicado depois de obter ambas as
bases. Isso também cobre intervalos como março de 2025 a setembro de 2026.
Uma recusa repete apenas o pedido daquele ano, sem baixar novamente os
pedidos já concluídos. O exemplo de dois anos faz quatro POSTs quando a
fonte responde sem recusas.

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
**603 testes em 127,136 s, sem falhas nem testes ignorados**. O ensaio de
100 mil registros fez a primeira consulta em 1,700 s e processou 95 eventos Qt.
Os testes direcionados de transporte, interface e versão também passaram.
As regressões anuais cobrem a resposta vazia entre anos, a omissão de meses
em faixas sem inversão do mês inicial/final, a rejeição de linhas fora da
faixa e a preservação do último resultado após falha no segundo ano.

Na API oficial, usando o mesmo provedor e perfil de pausa para duas consultas
consecutivas, setembro de 2026 concluiu em 3,946 s: 920 linhas gerais e 5.306
municipais. Logo depois, outubro de 2025 a setembro de 2026 concluiu em
16,699 s: 10.387 linhas gerais e 60.914 municipais, com os 12 meses presentes
em ambas as bases. As linhas e métricas de setembro coincidiram exatamente
entre a primeira consulta e o recorte da segunda. Os seis pedidos retornaram
HTTP 200; o segundo período usou quatro pedidos, divididos por ano.

Uma tentativa externa anterior encontrou quatro HTTP 429 e encerrou com uma
pausa persistida de 84 segundos, respeitada antes de consultar novamente.
O teste final não forçou novas recusas: a sequência de recuperação
`429 → 429 → 200` foi verificada nos testes controlados. As medições e os
ensaios anteriores estão em
[VALIDACAO_API_RC10_2026-10-23.json](VALIDACAO_API_RC10_2026-10-23.json).
Não houve reconciliação independente de totais oficiais nem homologação da
rede Windows da empresa.

A [compilação Windows RC10](VALIDACAO_WINDOWS_RC10_2026-10-23.md) passou
com Python 3.11, 3.12, 3.13 e 3.14: cada job executou 603 testes, com 602
aprovados, um teste POSIX ignorado e nenhuma falha. Os quatro executáveis
passaram no autoteste nativo. Os links dos pacotes e o escopo da verificação
estão no relatório Windows.

As evidências RC9 são históricas e permanecem em
[NOVO_CLIENTE_API_520_RC9.md](NOVO_CLIENTE_API_520_RC9.md) e
[VALIDACAO_WINDOWS_2026-10-22.md](VALIDACAO_WINDOWS_2026-10-22.md).
