# Estado atual — 5.2.0-rc.4

O acesso individual ao Comex Stat passou a ser **automático**. Ao consultar, o
programa prepara e reutiliza uma fila local, sem abrir outra janela ou exigir
arquivo de conexão, porta, comandos ou serviço Windows. Instâncias do mesmo
usuário no computador compartilham a fila; outra pode assumir quando o hospedeiro
sai. O atendimento automático é restrito ao loopback, com chave local protegida
por DPAPI no Windows. Conexão remota já configurada continua prioritária.

Uma pausa real da fonte fica em disco e aparece como contagem regressiva na tela.
Novas consultas são impedidas durante o prazo. As tentativas permanecem limitadas
e canceláveis. Quando falta Retry-After HTTP e o corpo repete uma orientação curta
como 10 segundos, o programa aplica recuo conservador de pelo menos 60 segundos.
O diagnóstico registra status HTTP observado, código interpretado e trecho limitado
da resposta, sem presumir um limite por IP.

**470 testes passaram em Python 3.14; 469, em Python 3.12**, incluindo 17 regressões
da automação, eleição entre dez instâncias, reutilização em outro processo,
recuperação de hospedeiro, 429/403, cancelamento, pausa e um ensaio com 100 mil
registros. Quatro layouts novos sem avisos QML. Wheel construído e conferido com
fontes, recursos e base integrada.

Na validação real, setembro/2026 para NCM 29161220 e SH4 municipal 2916 terminou
com os totais conferidos (18 e 216 registros, em universos estatísticos distintos).
O teste de janeiro a setembro com os 35 NCMs recebeu 429, e outra tentativa foi
recusada. Uma observação direta confirmou HTTP 429 da API, sem Retry-After HTTP,
com mensagem de tentar novamente em 10 segundos. Portanto, **a restrição da fonte
não é declarada removida**. O comportamento cliente foi corrigido; a disponibilidade
externa e a rede da empresa não são garantidas por esses testes.

Cálculos, conversão, conciliação, catálogo, estoque e geradores de Excel/PDF/Power BI
foram preservados. A base de 21/10/2026 permanece idêntica, com 1.784 posições e
R$ 14.088.617,67. Importações e Estoque continuam integrados; Crédito é planejado.

Uso: [ACESSO_AUTOMATICO_520_RC4.md](ACESSO_AUTOMATICO_520_RC4.md).
Evidências: [EVIDENCIAS_AUTOMATICO_520_RC4.json](EVIDENCIAS_AUTOMATICO_520_RC4.json).
Fonte real: [CONSULTA_REAL_AUTOMATICO_520_RC4.json](CONSULTA_REAL_AUTOMATICO_520_RC4.json).
Preservação: [PRESERVACAO_AUTOMATICO_520_RC4.json](PRESERVACAO_AUTOMATICO_520_RC4.json).

Computadores diferentes ainda precisam de um ponto comum de rede. O guia RC3 é
histórico para a central remota; suas etapas não são necessárias no uso individual
desta revisão. O programa não descobre servidores corporativos por suposição.

O ZIP contém código, testes, base e assistentes, sem novo Setup Windows compilado.
Teste os fontes abrindo INICIAR_DESKTOP.cmd na pasta nova. O executável instalado
só muda após recompilar e instalar o Setup atualizado. Testes Qt feitos em Linux/
offscreen; instalação, DPAPI, Shell e rede Windows precisam de homologação local.
