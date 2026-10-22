# Abrir e conferir o Power BI gerado

No aplicativo LIARTE, selecione o período e consulte. **Baixar Power BI** gera um ZIP com o projeto editável e o Excel do período completo. Filtros do aplicativo continuam sendo filtros da análise/PDF; Excel e BI incluem todos os NCMs consultados.

1. Extraia **todo** o ZIP do Power BI para uma **pasta nova** do Windows. Isso evita misturar o projeto com cache/alterações salvas de uma versão anterior. Não abra o projeto de dentro do ZIP.
2. Utilize Power BI Desktop atualizado. Se a versão instalada solicitar, habilite projetos PBIP, armazenamento TMDL e relatórios PBIR em Arquivo → Opções e configurações → Opções → Recursos de visualização. Reinicie o Desktop.
3. Execute **Abrir_PowerBI.cmd**. Ele encontra o Excel dentro de Dados, configura o caminho e abre o projeto. Não é necessário editar código.
4. Clique em **Atualizar** no Desktop. Confirme o nível de privacidade do arquivo local se solicitado. O Desktop lerá o Excel incluído; para buscar dados novos no Comex, consulte novamente pelo aplicativo LIARTE.
5. Para trabalhar em um arquivo único, use **Salvar como → PBIX** no Desktop. O gerador Python entrega PBIP, não um PBIX binário já preenchido.

Ao mudar a pasta de lugar, execute Abrir_PowerBI.cmd novamente para corrigir o caminho. Não separe o PBIP das pastas Report, SemanticModel e Dados.

## Navegação e filtros

A faixa de navegação leva às seis páginas. Os filtros das cinco páginas gerais são sincronizados. Selecione produtos do cadastro, nomes comerciais/NCMs, países, UFs, URFs e meses. A página municipal tem filtros independentes, por município/UF e SH4. Use a borracha nativa do segmentador para limpar uma seleção.

A página **Produtos e NCM** exige um único NCM para apresentar comparação de preços. Vários códigos de produto do cadastro podem compartilhar o mesmo NCM; a seleção usa a união e não duplica o valor desse NCM. O ranking de produtos identifica o NCM para deixar esse limite claro.

**US$/kg** é razão de somas. **MM3** é a razão ponderada dos três meses consecutivos selecionados, com peso em todos eles. Uma lacuna não vira zero. Se existir CIF positivo sem peso publicado, o preço afetado fica indisponível. A variação mensal compara o último mês no contexto ao mês imediatamente anterior, quando ambos estão selecionados e disponíveis. Os indicadores referem-se a valores nominais históricos, não cotações atuais.

Na página municipal, FOB/kg pode misturar mercadorias do mesmo SH4; ele descreve o recorte, não é cotação de um NCM8. Município é o domicílio fiscal do declarante. Não some os totais municipais aos gerais.

## Conferência de aceitação no Desktop

1. Atualize e confirme que não há erro no Power Query ou relacionamento.
2. Abra as seis páginas e confira títulos, logo, navegação, unidades e alinhamentos em Ajustar à página. Confirme especialmente que **Base Detalhada** e **Detalhamento municipal** mostram cabeçalhos e linhas; a RC7 reconstrói essas tabelas em formato plano.
3. Na **Exibição de consulta DAX**, execute `VERIFICAR_MEDIDAS.dax`, incluído no ZIP. A consulta não herda os filtros dos visuais.
4. Compare os totais e os meses com `CONTROLE_FONTE.json`: multiplique US$ por 100 para comparar aos centavos. Peso já está em kg. O JSON contém o SHA-256 do Excel que alimenta o projeto.
5. Selecione um NCM e um país e confira a razão CIF/peso na Base Detalhada. Teste MM3, meses ausentes e a seleção de dois NCMs, que deve ocultar os indicadores comparáveis.
6. No período do exemplo, selecione OL60, OLA3 e OLP40: todos correspondem ao mesmo NCM 27101931. Selecionar os três não deve triplicar o total.
7. Confira que o filtro UF mostra Todos sem truncamento, que o município tem uma única UF e que as URFs começam pelo nome. Navegue entre as páginas gerais e confirme a sincronização. Entre na municipal e confirme que seus filtros são próprios. Cidades homônimas devem aparecer com a UF.
8. Salve, feche e reabra o projeto; se necessário, salve também como PBIX.

Esses passos completam a homologação no ambiente da empresa. O pacote inclui resultados automatizados de estrutura, sintaxe, fonte e regressões, mas a renderização, o refresh M e a execução DAX no Power BI Desktop não foram executados no ambiente Linux desta revisão.

Na página Custos Logísticos, a curva mostra frete mensal em US$ mi e parte de zero. As dicas preservam valores integrais, peso e a razão por kg quando calculável. As tabelas usam preços por linha, sem totais artificiais; os indicadores usam razões de somas.
