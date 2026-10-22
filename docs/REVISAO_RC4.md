# Revisão RC4 — critérios e homologação

A RC4 aplica o estudo ESTUDO_USABILIDADE_E_DADOS_RC4.md. Critérios: reconhecer o
recorte, encontrar ações, comparar com a mesma unidade, recuperar filtros vazios
e acessar dados sem depender do mouse. O roteiro de uso está em
ROTEIRO_DIRETORIA_RC4.md; EVIDENCIAS_RC4.json e VALIDACAO_RC4.log registram testes.

## Verificado automaticamente

- Preenchimento 3/6/12 meses sem HTTP/sem perda do resultado, limitado aos meses disponíveis.
- Navegação por seções e redução de movimento, inclusive durante rolagem.
- Contexto aplicado e país visíveis, com nome comercial quando há produto único.
- Menu de documentos usa o diálogo e os escopos existentes; atalhos de consulta
  ficam suspensos em menus/diálogos. PDF municipal ou sem registros fica desabilitado.
- Gráfico aceita Home/End/setas e clique; descrição acessível anuncia o valor atual.
- Escala ajustada é sinalizada e cobre todos os pontos. O preenchimento não é usado
  com eixo cortado; valores e filtros permanecem iguais.
- Dados mensais e cópia usam US$/kg, dólares ou kg completos, sem confundir com
  escala gráfica; média mensal de peso preserva a fração exibida.
- Comparador ordena todas as origens por razão exata, mantém ausências ao final,
  permite expansão e informa meses com peso. Não identifica pedidos individuais.
- Recorte vazio oferece recuperação; busca da tabela não altera indicadores.
- Contratos de extração/exportação, formatos e recursos da marca preservados.

## Roteiro para Windows e usuários da LIARTE

1. Executar fontes e distribuição produzida pelo assistente; conferir título,
   ícone/agrupamento na barra de tarefas, atalhos e atualização sem perda de dados.
2. Rodar as cinco tarefas reais descritas no estudo: consulta, comparação, leitura
   por teclado, recuperação de filtro e download. Registrar conclusão/tempo/dúvidas,
   sem orientar previamente onde cada controle se encontra.
3. Repetir com tela reduzida e DPI utilizado, teclado/Narrador e movimento reduzido.
4. Abrir Excel, PDF e PBIP no Power BI Desktop; comparar com o Comex conforme o
   período e a origem dos dados, mantendo NCM/CIF separado de SH4/FOB municipal.
5. Testar erro de rede/429, cancelar e fechar durante tarefa. Dados anteriores
   devem permanecer identificados e arquivos só devem ser publicados completos.
6. Confirmar instalação/atualização/desinstalação e caminhos OneDrive conforme o
   roteiro de identidade Windows preservado em REVISAO_RC3.md.

A execução desta revisão ocorreu em Linux, com Qt offscreen/software. APIs do
Shell Windows permanecem cobertas por simulação e não houve homologação visual
Windows nem ensaio com pessoas. O estudo propõe a avaliação; não atribui a ela
resultados que ainda não foram observados.
