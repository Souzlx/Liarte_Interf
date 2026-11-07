# Retomada de consultas e pausas do Comex Stat

Melhoria dos fontes posteriores à **5.3.1** publicada. Os pacotes já distribuídos conservam o comportamento de sua versão; esta correção precisa de uma entrega posterior para aparecer no aplicativo instalado.

## Consulta incompleta

Uma consulta completa reúne as bases geral e municipal. Foi reproduzido um ciclo com uma fonte que permite um pedido por janela: a etapa geral termina, a municipal recebe HTTP 429 e, após aguardar, o próximo clique refaz a geral. Esse pedido pode consumir novamente a janela e impedir a conclusão da municipal.

A correção conserva em memória cada etapa já validada da mesma operação incompleta, identificada pela base e pelo intervalo dentro de um ano. Isso inclui respostas vazias válidas e consultas que atravessam a virada do ano. Quando o prazo permite, **Retomar consulta** continua pelo trecho pendente. O aplicativo publica o novo resultado somente após concluir e validar as duas bases. O último resultado completo permanece preservado durante falhas e cancelamentos.

Uma consulta concluída não serve de cache para a próxima consulta explícita. Cancelamento, troca de período ou fonte, reinício solicitado e falhas que invalidam a operação descartam as partes incompletas. Nenhuma resposta parcial é restaurada do disco ou exibida como consulta concluída.

## Validade e reinício

A operação conserva seus horários de início e recebimento. A validade da retomada é limitada e considera a primeira pausa ativa; novas recusas não renovam indefinidamente essa validade. A expiração descarta somente os dados incompletos e sinaliza a necessidade de reiniciar. O prazo exigido pela API permanece integral.

O prazo é fixado na primeira interrupção: o maior entre 600 segundos e o número de etapas restantes multiplicado pela pausa vigente, mais 120 segundos de margem nessa segunda parcela. Aplica-se ainda o limite absoluto de uma hora desde o recebimento da primeira etapa. Esses parâmetros limitam a retenção da operação; não encurtam a pausa exigida pela fonte. Se o prazo da fonte impedir retomar dentro dessa validade, o aplicativo informa que a retomada não está disponível.

O resultado completo e a auditoria das exportações preservam o início original da aquisição e o recebimento da última etapa validada de cada base. Esses horários não representam uma transação simultânea entre as bases da API.

**Reiniciar consulta** descarta a etapa retida e solicita novamente as duas bases, respeitando a pausa. A retomada só se aplica ao período e à origem da operação pendente. Dados de períodos diferentes não são misturados.

## Significado da espera

O estado distingue:

- **HTTP 429:** limite de consultas informado pela origem.
- **Recuperação local:** espera adicional aplicada pelo cliente após recusas consecutivas.
- **HTTP 500/502/503/504:** indisponibilidade temporária do serviço.
- **Estado legado:** prazo preservado, sem inventar metadados de origem que não foram gravados.

Por exemplo, quatro respostas pedindo cerca de dez segundos podem resultar na sequência de recuperação `10,5 → 21 → 42 → 84 s`. O prazo maior inclui a política de recuperação do cliente; não é apresentado como se a fonte tivesse pedido exatamente 84 segundos. O limite de tentativas e o orçamento de espera continuam limitados.

A leitura do contador usa uma trava de estado separada da operação HTTP. Uma leitura antiga não pode sobrescrever um prazo mais novo ou encurtar a pausa persistida. A interface continua consultando o estado enquanto a rede trabalha.

Um `Retry-After` absoluto considera `Age` válido quando há `Date` válido, para que uma resposta envelhecida não reinicie uma espera já vencida. Metadados opcionais inválidos não apagam um prazo válido. Migrações e formatos anteriores conservam as pausas ativas.

## Diagnóstico

O perfil conserva `ultima_falha_comex.json`, com endpoint, status HTTP observado e efetivo, cabeçalhos relevantes, trecho limitado da resposta e informações de espera. `source_delay`, `recovery_delay` e `pause_reason` distinguem a espera normalizada da fonte e a recuperação local. Isso permite investigar a recusa sem registrar dados completos da consulta.

Uma sondagem pela nuvem confirmou que a API oficial também pode recusar uma consulta mínima: metadados responderam HTTP 200 e, mais de um minuto depois, um POST de um NCM e um mês recebeu HTTP 429 com mensagem de dez segundos. A execução parou nessa recusa. O IP da nuvem difere do computador do usuário; essa evidência não determina sozinha a causa de cada ocorrência no Windows.

Em 7 de novembro de 2026, outra sondagem mínima pela nuvem recebeu respostas válidas das duas bases: 18 registros gerais e 233 municipais, em dois pedidos para um NCM e um mês. Esse resultado confirma disponibilidade naquele recorte e momento; não valida a consulta completa do usuário nem elimina a possibilidade de novas recusas da origem.

## Verificação

Os testes usam respostas sintéticas e relógios controlados para conferir retomada, expiração, reinício, preservação do resultado anterior, cancelamento, concorrência de prazos e as mensagens da interface. Os testes de rede não são necessários para reproduzir o ciclo corrigido.

A disponibilidade e os limites reais do Comex Stat continuam sujeitos à origem. As correções não removem HTTP 429, não reduzem `Retry-After`, não trocam silenciosamente para arquivos ou respostas antigas e não garantem sucesso quando a API continua recusando os pedidos.
