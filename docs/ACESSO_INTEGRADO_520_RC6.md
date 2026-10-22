# Acesso integrado — 5.2.0-rc.6

Esta revisão corrige o transporte HTTPS e a retomada automática da central
existente. Os cálculos, contratos de dados e formatos de Excel, PDF e Power BI
continuam os da RC5. Não é necessário abrir a janela da Central de Consultas
para o uso habitual.

## O que motivou a correção

O diagnóstico executado no computador da empresa em 22/10/2026 mostrou:

| Teste | Resultado observado |
| --- | --- |
| Metadados da API | HTTP 200, publicação até setembro/2026 |
| Consulta de dados da API | HTTP 429, mesmo após espera de 66 segundos |
| Arquivo oficial PAIS.csv | Falha TLS: emissor local não encontrado pelo Python |
| Central anteriormente configurada | Conexão recusada, sem resposta HTTP |

Os resultados são distintos. A falha TLS não era HTTP 503; a central recusada
não demonstrava chave inválida; o HTTP 429 não comprova um bloqueio permanente
do IP. O teste em outro computador da mesma rede é uma associação temporal,
não uma demonstração da causa do limite.

## Como funciona agora

1. No Windows, as conexões HTTPS da aplicação usam Truststore 0.10.5 e CryptoAPI.
   Isso permite ao Windows construir a cadeia de confiança, inclusive buscar
   intermediárias quando permitido por suas políticas. Certificado, nome do
   servidor e TLS 1.2 ou superior continuam obrigatórios.
2. O assistente verifica e prepara essa dependência automaticamente, no ambiente
   isolado do aplicativo. A compilação também inclui o pacote e sua licença.
   O autoteste de publicação verifica a construção do contexto TLS sem internet.
3. Sem configuração de servidor, a fila local continua iniciando na primeira
   consulta. Não exige pareamento, serviço Windows ou segunda janela.
4. Se este usuário já configurou uma central neste computador, o programa retoma
   seu atendimento em segundo plano ao abrir. Conserva a porta, a chave protegida,
   os arquivos, os índices e o cache dessa central. Não exige um arquivo adicional
   de conexão no próprio computador hospedeiro.
5. Se essa central já estiver atendendo, ela é reutilizada. Uma instância que
   apenas a reutiliza não a encerra ao sair. Após encerramento do hospedeiro,
   a próxima abertura ou consulta pode retomá-la, preservando os dados em disco.
6. Clientes que já possuem uma conexão de rede conservam seu endereço e sua chave.
   Um cliente remoto nunca assume a função de outro servidor nem acessa a API
   diretamente por causa de falha da central.

O modo automático é privado por padrão: não faz varredura da rede, não distribui
chaves e não abre porta na LAN de um computador sem configuração prévia.
A retomada de uma central de rede exige a configuração local válida já existente,
com endereço de escuta privado e chave legível pelo próprio usuário.

Para atender outros computadores, o programa precisa estar aberto no hospedeiro
previamente configurado e as conexões dos clientes precisam continuar válidas.
Esta revisão não instala um serviço Windows permanente ou um servidor na empresa
à distância. Ela automatiza o atendimento dentro da aplicação. Em máquinas sem
pareamento de rede, os arquivos oficiais e a fila local funcionam independentemente.
As filas locais de computadores diferentes não constituem uma fila única da LAN.

## Cache, pausas e precisão

- A revisão não apaga caches, relatórios, preferências ou pausas anteriores da API.
- Os arquivos oficiais conferidos são a primeira opção. Eles podem ser usados
  mesmo enquanto a API está em pausa, por serem uma fonte independente.
- A API alternativa continua com tentativas limitadas, intervalo conservador
  mínimo de 65 segundos e respeito ao Retry-After. Não é uma afirmação sobre
  qual seria a cota oficial, que não foi demonstrada no diagnóstico.
- Downloads conservam limites, cancelamento, redirecionamentos apenas para
  origens oficiais, tamanho, hash, publicação atômica e conferência de totais.
- Um erro de certificado é identificado no registro do arquivo como
  `TLS_CERTIFICATE`; nunca é convertido em HTTP 429 ou em dado vazio válido.
- Geral usa NCM/CIF; municipal usa SH4/FOB e domicílio fiscal. Não são pedidos
  individuais nem bases com totais diretamente comparáveis.
- Não se desativa SSL, não se instala CA arbitrária, não se troca IP e não se
  muda o contrato de dados para tentar contornar uma recusa da fonte.

## Atualizar sem comandos

1. Feche a versão anterior e a janela antiga da central, se estiver aberta.
2. Extraia todo o ZIP da RC6 em uma pasta nova.
3. Abra **INICIAR_DESKTOP.cmd** com dois cliques. O assistente prepara a dependência
   de certificados e verifica o programa. A primeira preparação usa internet.
4. Selecione o período e consulte. Não abra a central manualmente.

O ZIP contém os fontes e os assistentes, não um Setup Windows já compilado.
Um atalho que ainda aponte para o executável 4.7.2 continua abrindo esse executável;
extrair fontes não substitui uma instalação antiga. Para distribuir sem Python
separado, a TI pode gerar e instalar o novo Setup pelo assistente existente.

## Validação e limites da evidência

Os testes da entrega incluem uma central retomada em segundo plano, dez perfis
clientes concorrentes, eleição entre processos, reaproveitamento de cache,
recuperação após saída do hospedeiro, recusa de configuração inválida e
conexões HTTPS reais contra servidor local com certificados de teste. Certificados
não confiáveis e nomes divergentes precisam falhar durante o handshake.

As massas de importações dos testes são controladas e identificadas como tais.
Consulte os resultados atuais em `EVIDENCIAS_ACESSO_520_RC6.json` e os logs anexos.
Testes Linux não executam a CryptoAPI do Windows nem equivalem a uma consulta
homologada na rede da empresa. A correção se dirige ao erro de emissor confirmado,
mas um certificado que o próprio Windows não confie continuará sendo recusado.
O programa não pode garantir que o Comex deixe de responder com HTTP 429.

Referências técnicas: documentação oficial do Truststore
<https://truststore.readthedocs.io/en/latest/>, certificados HTTPS do pip
<https://pip.pypa.io/en/stable/topics/https-certificates/>, dados abertos MDIC
<https://www.gov.br/mdic/pt-br/assuntos/comercio-exterior/estatisticas/base-de-dados-bruta>
e contrato documentado da API <https://api-comexstat.mdic.gov.br/docs/doc.yaml>.
