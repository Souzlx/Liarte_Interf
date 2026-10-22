# Novo cliente direto da API — 5.2.0-rc.9

A camada de consulta do desktop foi escrita novamente em `liarte_core/comex_api.py`.
O adaptador ComexProvider mantém os mesmos registros, modelos, filtros e contratos
de exportação. Os geradores e a interface existentes foram preservados.

## Um pedido por base

O cadastro completo e todo o período são enviados em um POST geral e um municipal.
Não há consulta prévia de metadados, consulta adicional de totais ou divisão em
janelas anuais. NCM/CIF e município fiscal/SH4/FOB são universos distintos e não
são combinados para inventar informações municipais de oito dígitos ou CIF.

O desktop usa ApiClient por padrão. O ComexStatClient legado continua disponível
para ferramentas administrativas e testes, mas não executa a consulta normal.
Centrais, arquivos CSV e cache de resultados não são ativados automaticamente.
Isso preserva a preferência por API direta e instalações independentes.

## Recuperação limitada

Uma consulta sem falhas faz dois pedidos. Somente erros transitórios permitem
mais uma tentativa no endpoint afetado; a base anterior não é baixada novamente
para recuperar a próxima base dentro da mesma operação.

- HTTP 429, 500, 502, 503 e 504: Retry-After válido prevalece. Na ausência dele,
  o prazo em segundos da mensagem do MDIC é utilizado; sem prazo, recuo de 30 s.
- A pequena margem de 0,5 s evita reenviar antes do prazo comunicado.
- Falha de conexão: no máximo uma reconexão, após 2 s.
- Certificado inválido, redirecionamento, erro de parâmetros ou resposta
  incoerente: interrompe sem repetir o pedido.
- Há até duas tentativas por endpoint e orçamento de 45 s para esperas de
  recuperação. Prazos maiores são preservados, e a operação termina com o prazo
  informado. A espera tem contagem regressiva e pode ser cancelada.
- Não há intervalo preventivo de 60/65 s entre respostas bem-sucedidas.
- Reabrir o aplicativo não apaga um Retry-After ainda vigente.

A pausa fica em acesso_api.json no perfil local. Uma pausa real ainda ativa no
estado da versão anterior é migrada; a antiga fila e o intervalo preventivo não
são reutilizados. Há exclusão mútua entre clientes da mesma instalação/processo,
sem servidor local ou novo banco de filas. Computadores diferentes continuam
independentes e podem estar sujeitos aos limites externos da API.

## Transporte e precisão

HTTPS continua com validação de certificados e nomes. No Windows, utiliza-se a
confiança nativa já adotada pelo projeto. Proxies do sistema permanecem respeitados.
Não se instala certificado, não se desativa TLS e não se altera o IP.

A resposta pode usar gzip. Content-Length é conferido em bytes recebidos antes
da descompactação; tamanho expandido, encerramento do gzip, codificação UTF-8,
estrutura JSON e chaves repetidas são verificados. O limite é 100 MiB tanto para
a transferência quanto para a resposta descompactada. O timeout de socket é
120 s e o limite de leitura é 240 s após os cabeçalhos, com cancelamento entre
leituras. Uma operação de socket em andamento pode demorar até seu timeout
para devolver o controle ao cancelamento.

Números decimais são interpretados com Decimal. Centavos e pesos não são
arredondados silenciosamente. O contrato comum confere período, códigos,
dimensões, valores não negativos, CIF e duplicidades. Linhas idênticas contam
uma vez; valores conflitantes interrompem a publicação. O novo resultado é
publicado somente após ambas as bases e conversões concluírem.

Não há reconciliação com outro pedido de totais na consulta normal. Por isso,
uma omissão bem formada da própria API não pode ser detectada localmente.
O registro de exportação continua distinguindo response_validated de
independent totals reconciliation (totals_verified).

## Validação real desta revisão

Em 22/10/2026, na rede de testes Linux, a consulta de janeiro a setembro de
2026 concluiu para os 35 NCMs e 19 posições SH4 incorporados: 7.789 registros
gerais e 46.074 municipais, em 24,796 s. Os dois POSTs receberam HTTP 200/gzip;
nenhuma repetição foi necessária. Não foram usados dados sintéticos nessa
consulta. A evidência contém horários e contagens, sem ampliar o resultado
para garantia de disponibilidade futura ou para a rede Windows da empresa.

O HTTP 429 observado antes é uma recusa externa. A reescrita não garante que a
API aceite todo pedido de qualquer rede ou volume. Sua disponibilidade continua
sendo uma condição necessária para a consulta exclusivamente por API.

## Atualização

Feche a versão anterior, extraia todo o ZIP em outra pasta e abra
INICIAR_DESKTOP.cmd. Fontes e assistentes estão incluídos; não há Setup Windows
compilado neste pacote. Atalhos de executáveis antigos abrem a versão antiga.
Dados de estoque, configurações, relatórios, logo, regras do PDF, tabelas do
Excel, coluna E municipal e geração do BI são preservados.

Documentos RC8 e anteriores são registros históricos. Evidências atuais:
EVIDENCIAS_NOVO_CLIENTE_API_520_RC9.json.

Referências consultadas em 22/10/2026:
- https://api-comexstat.mdic.gov.br/docs/doc.yaml
- https://www.rfc-editor.org/rfc/rfc6585
- https://docs.python.org/3/library/urllib.request.html
- https://docs.python.org/3/library/zlib.html
