# Revisão RC3 e roteiro de homologação

## Critérios implementados

| Área | Evidência |
| --- | --- |
| Título e marca | Liarte Importações; mesmo ICO/PNG original; teste real Qt de conteúdo/rasters e dimensões do ícone. |
| Processo Windows | API com assinatura/HRESULT, chamada antes de QGuiApplication; mesmo AppID estável dos atalhos. |
| Atalhos Windows | Known Folders preservadas, inclusive OneDrive; descrição nova; IPropertyStore escreve AppID e confirma Commit; Release/CoUninitialize balanceados. |
| Recuperação | Marcador com esquema e AppID; migração única de marcador legado; falha não gera sucesso; exclusão/movimentação/corrupção continuam cobertas por testes. |
| Tendências | Valor, peso, preços, média móvel, variação mensal e início–fim; sem interpolar preço ausente como zero. |
| Referências | Soma de valores/soma de peso; frete/CIF; países por valor; comparação por origem, mesmo recorte e NCM/SH4 único. |
| Volumes relevantes | Limiar de peso por país ajustável só no comparador; documentos/totais preservados. |
| Desempenho | Agregação por recorte no worker; cache de apresentação; troca de indicador/limiar não consulta a API. |
| Movimento | Mesmo desenho de curva para linhas mensal/móvel; revelação por recorte; sem repintura por quadro; respeita reduzir movimento. |
| Documentos | Bases/formatos idênticos; Excel com 8 abas no exemplo trimestral e E municipal 64; PDF e BI gerados novamente. |

As APIs Windows foram simuladas no ensaio automatizado. A aparência efetiva da
barra de tarefas não foi observada neste ambiente Linux. O instalador e o
executável Windows devem ser produzidos e verificados no Windows, sem usar o
executável Linux de QA como substituto.

## Conferência no Windows antes da implantação

1. Extraia o pacote completo. Abra INICIAR_DESKTOP.cmd; confirme título e ícone
   na janela, Alt+Tab e barra de tarefas, com tema claro/escuro e DPI habitual.
2. Compile pelo assistente. Abra a pasta portátil completa e repita o teste.
   Confira que não aparece o ícone genérico de Python/Qt.
3. Com perfil antigo, abra o executável e confira os dois atalhos. Feche/reabra:
   não deve haver recriação repetida/notificação. Apague um atalho e confira a
   recriação. Repita com Área de Trabalho no OneDrive e caminho com acentos.
4. Compare atalhos fixados antigos e o novo. Se um atalho fixado ainda apontar
   para outra versão/local, remova apenas esse atalho antigo e fixe o novo.
   O aplicativo não fixa ícones automaticamente nem modifica atalhos alheios.
5. Instale/atualize com o mesmo AppId. Confira preservação de configurações,
   cache/relatórios; desinstale mantendo dados e teste a opção de remoção do perfil.
6. Consulte um produto por pelo menos três meses. Confronte valor/peso e preço
   calculado com o Comex; alterne indicadores, filtros e peso mínimo do comparador.
   Confira que meses ausentes não viram preço zero, e SH4 municipal usa FOB.
7. Gere Excel/BI/PDF com filtros ativos: Excel/BI completos; PDF conforme filtros,
   busca e regra comercial. Abra o PBIP no Power BI Desktop e verifique o modelo.
8. Teste indisponibilidade/429, cancelar, fechar durante tarefa, teclado/Narrador,
   dimensões reduzidas e disponibilidade atual da fonte no ambiente da empresa.

## Limites da verificação desta entrega

A verificação numérica usou os dados oficiais previamente capturados, com controles
oficiais independentes aprovados na RC1. A tentativa nova desta revisão recebeu
429 antes da conclusão do período. Isso foi registrado como falha de acesso à
fonte; não como controle aprovado ou consulta substituída por simulação.

Os preços são valores unitários históricos em US$/kg. Origem não identifica
fornecedor; diferenças de mix, qualidade, quantidades, rotas e condições comerciais
podem persistir dentro de um NCM. O comparador não determina sozinho uma decisão
de compra e não estima custo nacionalizado completo.
