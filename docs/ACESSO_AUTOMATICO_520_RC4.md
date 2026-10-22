# Acesso automático — 5.2.0-rc.4

## Utilização individual

Abra a versão atualizada, selecione o período e clique em **Consultar**.
Não é necessário abrir uma central, exportar ou importar conexão, escolher
porta, executar comandos ou deixar uma segunda janela aberta.

A fila é preparada no próprio processo do programa, em segundo plano, somente
quando necessária. Outras instâncias do mesmo usuário, no mesmo computador,
reutilizam essa fila. Quando a instância hospedeira sai, outra pode assumir,
preservando cache e pausas. O programa encerra os recursos que hospeda ao sair.
Não há um serviço Windows instalado ou um processo separado que precise ser
iniciado ou encerrado manualmente.

O acesso automático utiliza apenas `127.0.0.1` e uma porta local disponível,
escolhida pelo sistema. Não abre atendimento para a rede da empresa. A chave
é gerada automaticamente e protegida por DPAPI no Windows; nenhum segredo é
exibido ou transferido para outros computadores.

## Atualizar e abrir a versão correta

1. Extraia o ZIP completo em uma pasta própria, preservando a versão anterior.
2. Para testar os fontes, abra **INICIAR_DESKTOP.cmd**, dentro da nova pasta,
   com dois cliques. O assistente existente prepara o ambiente necessário.
3. Abra Importações, escolha o intervalo e consulte.

O ZIP contém os fontes e os assistentes de desenvolvimento/compilação.
Não contém um novo Setup Windows já compilado. Substituir os fontes não atualiza
um `.exe` que já tenha sido instalado: a TI deve recompilar e instalar o Setup
atualizado para distribuir essa versão como executável. Um atalho para uma
instalação antiga continuará abrindo aquele executável até sua atualização.

Preferências, relatórios, catálogo, base de estoque e cache existentes são
preservados. A fila utiliza o mesmo arquivo de controle da pausa local da RC3,
para não perder uma espera já registrada antes da atualização.

## Quando o Comex recusar a consulta

Uma única máquina também pode receber HTTP 429. O número de dispositivos ativos,
sozinho, não identifica a causa nem comprova um bloqueio por IP. A organização
dos acessos reduz concorrência e repetições; não pode remover um bloqueio aplicado
pela fonte ou garantir sua disponibilidade.

Esta versão:

- respeita `Retry-After`, tanto em segundos quanto em data HTTP, e mantém a pausa
  em disco, inclusive após fechar e reabrir;
- mostra a contagem regressiva na própria tela e impede uma nova consulta antes
  do prazo registrado, inclusive pelo atalho F5;
- quando falta o cabeçalho HTTP `Retry-After` e a resposta repete um texto genérico
  de 10 s, aguarda no mínimo 60 s, aumentando a espera nas próximas tentativas;
- continua fazendo tentativas automáticas limitadas durante uma consulta ativa,
  com cancelamento disponível, sem insistir indefinidamente;
- distingue HTTP 429 de uma recusa HTTP 403, falha de rede ou resposta inválida;
- registra a resposta efetiva recebida da fonte desde a primeira recusa HTTP,
  com status, rota, horário, trecho limitado e a indicação `Retry-After` recebida;
- preserva a última base válida e não publica resultados incompletos.

Quando as tentativas se esgotam, a tela indica a espera restante. O término da
contagem não dispara consultas ilimitadas. O usuário pode consultar novamente
após o prazo; o cancelamento também não é desfeito por uma retomada oculta.

O diagnóstico fica no `desktop.log`, acessível em **Preferências → Diagnóstico**.
O registro distingue o status HTTP efetivamente recebido (`observed_http_status`)
do código de limitação interpretado na resposta. O registro estruturado da última recusa fica em
`dados/acesso-automatico/dados/ultima_falha_comex.json`, dentro da pasta local de
dados da aplicação. Não registra chave de autenticação, cabeçalhos privados ou
dados do ERP. A evidência mostra o que a fonte respondeu, sem presumir a causa.

## Uso entre computadores

A coordenação automática descrita acima é local ao perfil do usuário. PCs
diferentes precisam de um ponto comum na rede. A opção **Usar central da empresa
na rede** permanece em Preferências, e uma conexão remota já configurada tem
prioridade; ela não é substituída silenciosamente por uma fila local.

O programa não adivinha o servidor da empresa nem divulga sua chave por descoberta
de rede. O guia da central de rede continua em `CENTRAL_COMEX_520_RC3.md`.
Esse guia é necessário apenas para coordenar computadores diferentes. O uso
individual desta revisão dispensa suas etapas de configuração.

## Conferência

Foram exercitados eleição entre dez instâncias, reutilização em outro processo,
troca de hospedeiro, recuperação de registro de um processo encerrado, pausa
persistente, cancelamento, conexão remota prioritária, diagnóstico de HTTP 429 e
403, contagem regressiva e o fluxo completo das bases geral e municipal.

Os cálculos, a conversão e a publicação dos dados, o catálogo, a base de estoque
e os geradores de documentos foram preservados. Veja
`PRESERVACAO_AUTOMATICO_520_RC4.json` e `EVIDENCIAS_AUTOMATICO_520_RC4.json`.

Os testes reais estão documentados em `CONSULTA_REAL_AUTOMATICO_520_RC4.json`.
Uma consulta de setembro/2026 para NCM 29161220 e o universo municipal SH4 2916
terminou com os totais conferidos. O teste com todo o cadastro e janeiro a setembro
recebeu código 429; uma repetição posterior também foi recusada. Uma verificação
adicional confirmou status HTTP 429 real, sem cabeçalho Retry-After, com a mensagem
de tentar novamente em 10 s. Portanto, não se declara a fonte externa desbloqueada
ou todos os recortes homologados ao vivo. Os testes partiram de outra rede e não
comprovam o estado da saída de Internet da empresa. Os testes Qt foram realizados
em Linux/offscreen; instalação, DPAPI, Shell e rede Windows precisam de homologação
no ambiente da empresa.

## Referências

- API oficial: https://api-comexstat.mdic.gov.br/docs
- HTTP 429: https://www.rfc-editor.org/rfc/rfc6585.html#section-4
- `Retry-After`: https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3
- Servidor HTTP local: https://docs.pylonsproject.org/projects/waitress/en/stable/
