# Revisão funcional de Estoque e Importações — 22/10/2026

Revisão do código a partir do commit `8aac32e`, com correções reproduzidas e
testes de regressão para dados de estoque, respostas do Comex Stat, geração
do Power BI e interação com a busca de produtos.

## Correções

| Área | Problema observado | Comportamento corrigido |
|---|---|---|
| Base de estoque | A mesma saída diária podia aparecer duas vezes em um `.liarte`, duplicando o vendido e alterando a cobertura. | A validação rejeita duplicidades de produto, filial, unidade e dia. Uma tentativa de gravação inválida preserva a base anterior. |
| Histórico de vendas | Meses posteriores à data da base eram representados como venda zero. | Meses ainda não observados ficam sem valor; zero continua válido em meses com observação. |
| Respostas do Comex Stat | Objetos, listas, números e booleanos em rótulos eram convertidos em texto e aceitos como dados válidos. | As dimensões textuais das duas bases exigem texto, e uma resposta inválida preserva a última consulta completa. |
| Métricas oficiais | Formatos como `1_000`, `1__2` e dígitos fora do formato publicado eram aceitos pelo conversor decimal. | A sintaxe numérica é validada antes da conversão exata, preservando os formatos decimais e expoentes compatíveis. |
| Power BI | Um mês numérico fracionário, como `1.5`, podia ser tratado como janeiro. | O leitor e a consulta M gerada rejeitam meses numéricos fracionários. O leitor também limita o mês antes de converter expoentes grandes em inteiros. Uma falha conserva o pacote anterior. |
| Busca de estoque | Uma busca extensa podia ficar visível sem corresponder ao filtro aplicado. | O texto editado respeita o limite de 200 caracteres Unicode; nomes extensos de produtos selecionados permanecem completos. |

As regras de unidades, precisão monetária, giro informado pela fonte e distinção
entre NCM/CIF e município fiscal/SH4/FOB continuam cobertas pelos testes existentes.

## Verificações

- Resultado em CPython 3.12.14 / Qt 6.10.3 / Linux x86_64: **586 testes
  passaram em 125,267 s**, sem falhas ou testes ignorados. Inclui os 571 testes
  anteriores, 14 regressões novas e o teste opcional de volume.
- No cenário de 100 mil registros, a primeira consulta levou 1,540 s e a
  interface processou 90 eventos Qt durante a operação. São medições desta
  execução, sem garantia de desempenho em outras máquinas.
- Regressões novas integram o comando padrão `python verificar.py --headless`.
- A validação completa usa `python verificar.py --headless --volume`, incluindo
  o cenário de 100 mil registros.
- O autoteste da aplicação usa `python iniciar.py --smoke-test <resultado.json>`.
  Ele verifica a janela Qt, ícone, temas, diálogo de exportação e geradores
  Excel, PDF e Power BI com dados sintéticos.
  O resultado desta revisão foi `status: ok`, 50 linhas, temas claro/escuro
  verificados e nenhum aviso QML; os três geradores retornaram `ok`.
- As telas de Importações e Estoque foram inspecionadas em 1380×900 e 760×700,
  com dados sintéticos e sem avisos QML.

## Limites da validação externa

A tentativa real de ler os metadados do Comex Stat foi bloqueada pelo proxy
do ambiente antes de alcançar a API: `Tunnel connection failed: 403 Forbidden`.
O domínio `api-comexstat.mdic.gov.br` foi acrescentado ao rascunho da política
de rede. O acesso precisa ser aplicado nas configurações do ambiente antes
de repetir a consulta real.

A validação Linux cobre a geração do pacote Power BI e das expressões M;
a execução dessas expressões no Power BI Desktop e a homologação do instalador
Windows dependem dos respectivos programas no Windows.
