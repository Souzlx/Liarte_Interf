# Central de Consultas — 5.2.0-rc.3

A equipe passa a utilizar uma única fila de acesso ao Comex Stat. Quando vários
computadores solicitam a mesma consulta, a central consulta a fonte uma vez e
entrega a resposta aos interessados. Períodos, bases, códigos, dimensões e revisões
diferentes permanecem separados. As conferências de registros e totais continuam
ativas antes de disponibilizar os resultados.

**É necessário configurar todos os computadores para a mesma central.** Atualizar
o programa, sozinho, não conecta instalações diferentes. Não é necessário abrir
PowerShell para configurar ou utilizar a central.

## 1. Escolher onde a central ficará aberta

Escolha um computador ou servidor Windows acessível pela rede da empresa. A central
precisa permanecer aberta enquanto a equipe consulta importações. Use apenas uma
central para a equipe. O módulo de Estoque não depende dela.

1. Atualize o programa para esta versão e abra **Importações**.
2. Entre em **Preferências → Acesso ao Comex Stat**.
3. Clique em **Abrir central neste computador**. Será aberta uma janela independente.
4. Confira o **IP de escuta** e o **Endereço para a equipe**. Para outros computadores,
   utilize o IP interno ou nome fixo do servidor; `127.0.0.1` atende somente o próprio
   computador. O endereço sugerido usa o primeiro IPv4 interno encontrado: a TI deve
   conferir a placa correta se houver VPN ou mais de uma rede.
5. Mantenha a porta **8767** e o intervalo inicial de **15 s**, salvo orientação da TI.
6. Clique em **Iniciar central** e depois em **Exportar conexão**.

A chave é gerada pelo programa e preservada para o mesmo usuário do Windows. O
arquivo `.liarte-conexao` inclui essa chave para configurar a equipe; distribua-o
somente aos usuários autorizados. A TI pode liberar a porta escolhida no firewall
para os computadores da rede interna. Um endereço fixo evita reconfiguração após
mudanças de IP.

## 2. Conectar cada computador, inclusive o que hospeda a central

1. Abra **Importações → Preferências → Acesso ao Comex Stat**.
2. Clique em **Importar conexão da empresa** e escolha o arquivo exportado. A conexão
   será salva automaticamente para esse usuário do Windows.
3. Abra novamente essa configuração e utilize **Testar conexão**, se desejar.
4. Selecione o período e gere os documentos normalmente.

O teste verifica apenas a central; ele não consome uma consulta à API pública.
Todas as instalações participantes devem usar a versão atualizada e a mesma
conexão. Após alterar a conexão, os arquivos e as bases locais são preservados e a
próxima consulta confere novamente a disponibilidade da fonte.

## 3. Uso diário e encerramento

- Os usuários continuam selecionando o período, aplicando filtros e baixando seus
  documentos no programa. Os filtros sobre os dados carregados não voltam à fonte.
- A janela da central mostra fila, consultas concluídas, reaproveitamentos e pausas.
  Ela pode ficar minimizada. Fechar o cliente LIARTE não fecha essa janela separada.
- **Parar central** encerra o atendimento; fechar sua janela também o encerra. As
  configurações são mantidas. Após reiniciar o computador, abra a central e clique
  em **Iniciar central**. Esta entrega usa um gerenciador nativo, sem serviço Windows
  automático em segundo plano.
- Se a central ficar indisponível, o cliente informa a falha. Ele não passa a
  consultar o Comex diretamente, o que criaria acessos fora da fila da equipe.

## Como a correção reduz os acessos

- Um worker realiza as consultas de origem em sequência; o intervalo padrão é
  de 15 s após a finalização de cada acesso. Não há uma quota pública assumida como
  garantida: o intervalo é uma política conservadora desta aplicação.
- Consultas idênticas em andamento são compartilhadas, inclusive quando se pede
  atualização. A opção de atualizar ignora respostas concluídas em cache.
- Respostas válidas são reaproveitadas na central por até 5 minutos; metadados de
  disponibilidade, por até 60 s. A revisão da fonte faz parte da chave das consultas
  de dados. Respostas com erro, incompletas ou inválidas não são publicadas em cache.
- A pausa de HTTP 429 ou 503, quando aplicável, vale para toda a fila e fica gravada
  em disco. `Retry-After` aceita segundos ou uma data HTTP e não é reduzido a 120 s.
  Sem indicação da fonte, a primeira espera conservadora é de 60 s, com recuo
  progressivo e número limitado de tentativas. A pausa continua válida após reiniciar.
- Mesmo sem central, instâncias do mesmo usuário no mesmo computador compartilham
  uma fila local e a pausa. Computadores ou usuários diferentes precisam da central
  para coordenar seus acessos.
- O programa não verifica o Comex ao abrir Início ou Estoque. A verificação automática
  ocorre uma vez ao entrar em Importações; navegar novamente e aplicar filtros não
  reiniciam essa verificação. **Verificar fonte** continua disponível nas preferências.

## Precisão e conservação dos dados

A central devolve os registros originais, sem arredondar, reclassificar ou juntar
bases. A conferência independente por NCM/SH4 permanece no cliente. O cadastro,
as regras numéricas e os geradores de Excel, PDF e Power BI são os da versão anterior.
Excel e BI continuam com o período completo; o PDF continua com os filtros próprios.
Relatórios, configurações, base de estoque e preferências existentes são preservados.

O Comex apresenta agregados estatísticos: as linhas não identificam pedidos
individuais. A base geral e a municipal representam universos distintos; não são
somadas ou cruzadas como se fossem a mesma base.

## Orientações para a TI

O atendimento HTTP usa Waitress 3.0.2, com autenticação por chave, rotas fixas e
limites de conexões, fila e tamanhos. Não aceita URLs de origem arbitrárias.
O cache local da central tem orçamento de 256 MiB de conteúdo comprimido e
verificação de integridade. A chave local é protegida por DPAPI no Windows.

O gerenciador fornece HTTP para a rede interna. Para HTTPS, a TI deve colocar um
proxy reverso corporativo à frente e informar seu endereço no campo publicado.
O cliente valida o certificado normalmente. Não publique a porta diretamente na
Internet. Os bancos SQLite ficam em disco local, nunca em uma pasta de rede/SMB.

Dados e diagnóstico da central ficam em `central-comex`, dentro da pasta local
de dados do aplicativo, no perfil do usuário que a iniciou. O arquivo é `central.log`;
ele não registra a chave de acesso. A conexão do cliente é salva em
`dados/conexao_comex.json`. A identidade da instalação e do menu Iniciar foi mantida.

A central organiza apenas acessos realizados por clientes configurados para ela.
Navegadores, versões antigas e outros sistemas que usam a mesma saída de Internet
podem consumir a quota da fonte. Uma indisponibilidade ou limitação externa ainda
pode ocorrer; esta correção coordena os acessos e respeita a pausa, sem contornar
o limite imposto pelo Comex.

## Verificação desta entrega

Os testes usam capturas identificadas e uma fonte simulada, com HTTP real em
loopback. Dez clientes concorrentes da mesma consulta geraram um único acesso à
fonte simulada. Foram exercitados pausa persistente, cancelamento, reinício,
revisões, consultas distintas, falhas, autenticação, atualização, cache corrompido,
encerramento e conciliação geral/municipal de ponta a ponta.

Consulte `EVIDENCIAS_ACESSOS_520_RC3.json` e `PRESERVACAO_ACESSOS_520_RC3.json`.
A rede corporativa, o firewall, o DPAPI e o Setup Windows devem ser homologados
pela TI no Windows. Os testes Qt desta revisão foram executados em Linux/offscreen.
O ZIP contém os fontes e assistentes de compilação; não inclui um Setup já compilado.

## Referências técnicas

- RFC 9110, seção 10.2.3, `Retry-After`: https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3
- RFC 6585, seção 4, HTTP 429: https://www.rfc-editor.org/rfc/rfc6585.html#section-4
- SQLite, uso por rede: https://sqlite.org/useovernet.html
- SQLite, limitações do WAL em rede: https://sqlite.org/wal.html
- Waitress, configuração: https://docs.pylonsproject.org/projects/waitress/en/stable/arguments.html
- Waitress 3.0.2: https://pypi.org/project/waitress/3.0.2/
