# Revisão 5.0.0-rc.2

Esta revisão concentra mudanças no uso e na apresentação da aplicação nativa.
A lógica dos 22 arquivos de domínio, motor e controlador foi preservada, com
somente a versão dos geradores atualizada. Recursos da marca são idênticos.

## O que mudou

- Cabeçalho e navegação mais discretos, sem textos de arquitetura ou módulos futuros.
- Período compacto, meses inteiros e preferências secundárias reunidas no diálogo.
- Indicadores com hierarquia, valores finais e formatos preservados.
- Gráfico mensal mais amplo, preenchimento discreto e hover sem repintar a curva.
- Barras proporcionais ao total das origens; seis maiores em destaque.
- Filtros ativos com remoção individual e limpeza própria da busca da tabela.
- Documentos junto à tabela, mantendo os escopos originais.
- Informações sobre metodologia em Ajuda; avisos relevantes permanecem no fluxo.
- Erros comuns da fonte apresentam orientação em português; detalhes ficam no log.
- Ícones vetoriais, contraste, foco e animações com redução de movimento.

## Verificação

178 testes automatizados: 162 regressões existentes e 16 cenários novos de
interface/contraste, incluindo Canvas, barras, preferências e mensagens de erro.
96 combinações de duas bases, dois temas, seis tamanhos e quatro escalas, com
288 aberturas de diálogos, sem avisos QML. Artefatos do estudo e resultados
estão em EVIDENCIAS_RC2.json, VALIDACAO_RC2.log e ESTUDO_INTERFACE.md.

Consulta real nesta revisão: setembro/2026, 920 registros gerais e 5.306 municipais;
fonte atualizada em 06/10/2026. Todos os campos recebidos coincidiram com o mesmo
mês da captura oficial RC1, que integra o trimestre conciliado.
A API limitou a primeira tentativa e os controles agregados adicionais (429).
Após espera, a consulta principal e os três documentos foram concluídos.
Não são alegadas duas novas conciliações: as duas aprovadas são as da RC1.

Também foi repetida a geração, pelo controlador Qt, dos documentos do trimestre
julho–setembro a partir da captura oficial previamente validada. Os exemplos
incluídos são estes snapshots históricos, com metadados da RC2, não dados novos
de cache. Nenhum exemplo é sintético; o PDF é filtrado por três acrilatos e por
China/Estados Unidos. Excel/BI são completos, mesmo com os filtros na tela.

No benchmark, pinturas Canvas caíram de 16 para uma por transição. Não é medição
de FPS real. Tempos de consulta/exportação são locais e não constituem SLA.

## Abrir e homologar

Extraia todo o ZIP e abra INICIAR_DESKTOP.cmd no computador de desenvolvimento,
com Python compatível. Depois de compilado por CRIAR_EXECUTAVEL.cmd, o runtime é
incluído e o computador que recebe o pacote não precisa de Python separado.
CRIAR_INSTALADOR.cmd usa Inno Setup já instalado pela TI.

Antes de declarar estável, conferir no Windows 10/11 x64: preparação, execução,
GPU/DPI, teclado/Narrador, redirecionamento de pastas, criação/recriação dos dois
atalhos, atualização preservando dados e desinstalação nas duas opções. Abrir
Excel no Microsoft Excel sem reparação e abrir/atualizar o PBIP no Power BI Desktop.
Essas validações nativas permanecem pendentes; o binário de teste é Linux.

Testes finitos e validações de contrato não tornam o produto imune à indisponibilidade
ou revisão da fonte. Protheus, servidor, identidade e multiusuário não foram
introduzidos nesta revisão. O fluxo de documentos e a organização das planilhas
permanecem os da proposta aprovada.
