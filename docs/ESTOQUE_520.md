# Estoque — 5.2.0-rc.2

O módulo Estoque passa a funcionar no mesmo aplicativo de Importações. Os dois
módulos mantêm suas consultas e filtros ao alternar entre eles. Crédito continua
planejado. A identidade da instalação, atalhos, pastas e preferências é preservada.

## Começar a usar

1. Extraia o ZIP inteiro. Na máquina da TI, abra `INICIAR_DESKTOP.cmd`, como antes.
2. Abra **Estoque**. A base extraída do PBIX enviado, com data de 21/10/2026,
   já está integrada e abre automaticamente, sem seleção inicial de arquivos.
3. **Atualizar base** permite abrir um novo **PBIX com dados** do modelo LIARTE
   ou um arquivo `.liarte`. A última base válida importada tem preferência.
   Arquivos que contêm apenas a conexão ao modelo publicado não têm os dados necessários.
4. Selecione produto, filial, armazém, unidade e período. A busca por código,
   descrição ou grupo atualiza **todos** os indicadores, gráficos e posições.
   Mais filtros oferece grupo, tipo, ABC, última venda e situação do saldo.
5. Clique em um produto no gráfico para filtrá-lo. Na tabela, selecione uma linha
   e use **Detalhar produto**, duplo clique ou Enter. Veja vendas e giro por mês,
   estatísticas e cobertura. Use **Analisar este produto** para aplicar o filtro.
6. **Baixar Excel** exporta o recorte atual: Estoque, Fechamentos, Vendas por filial
   e Leitura dos indicadores. Os filtros e a seleção são preservados após salvar.

Panorama e Produtos, no menu lateral, levam diretamente às seções da mesma tela.
Ctrl+1 abre Início; Ctrl+2, Importações; Ctrl+3, Estoque. Ctrl+F busca no módulo
visível. Os temas claro/escuro, animações reduzidas e tabela compacta são compartilhados.

Na execução normal, a última base válida fica armazenada na pasta local de dados
da LIARTE e é retomada ao entrar em Estoque. Atualizar base permite substituí-la por um
PBIX mais recente. Não há consulta automática ao servidor SQL/Protheus nesta entrega.

## Busca e gráficos

A busca reconhece código, nome e grupo sem diferenciar acentos ou maiúsculas.
Todos os termos digitados precisam corresponder ao cadastro. Não há aproximação
automática de nomes químicos. Códigos exatos têm prioridade, incluindo zeros iniciais.
Digite para filtrar todo o módulo; seta para baixo/cima e Enter selecionam uma sugestão.
Enter sem uma sugestão marcada mantém a busca ampla. Esc fecha a lista; Tab segue
para o próximo campo; × limpa produto/busca. Selecionar um produto remove o texto
anterior, evitando filtros incompatíveis. As sugestões incluem saldo por unidade.

A evolução permite linhas ou colunas, média móvel de três meses e rótulos de valores.
Os eixos usam intervalos regulares, começam em zero quando não há valores negativos
e identificam R$, R$ mil ou R$ mi. Rótulos são espaçados conforme a largura; todas as
observações continuam acessíveis pelo mouse ou setas. Não há interpolação de lacunas.
O gráfico exibe o último fechamento disponível e a variação contra o mês imediatamente
anterior, apenas se ambos existem e a base de comparação é positiva. Não é previsão
nem comparação automática com o saldo atual de abrangência diferente.

O ranking mostra até oito produtos, custo em reais, participação individual e acumulada
no capital positivo. Os cartões resumem valores milionários; passe o mouse para ler
o valor integral. Tabelas e Excel mantêm os valores na precisão definida.

## O que os indicadores significam

| Informação | Critério |
|---|---|
| Estoque a custo | Soma do custo atual em reais, preservando saldos negativos. Não soma fechamentos de meses diferentes. |
| Quantidade | Na unidade original. KG, L, UN e outras unidades não são somadas entre si. Passe o mouse sobre o cartão para ver os totais por unidade. |
| Giro mensal | `GiroEstoqueMensalQtd` de `Fact_Estoque`, na mesma posição e no último fechamento da base. É um indicador informado pela fonte; sua fórmula não foi reconstruída. |
| Giro no cartão | Mediana dos giros não negativos de posições com saldo atual positivo e fechamento disponível. O mês e o número de posições aparecem no cartão. Não é o giro consolidado da empresa. |
| Dias fonte | Campo original `DiasEstoqueQtd`, sem transformá-lo em uma previsão de cobertura. |
| Cobertura por vendas | Saldo do produto em todos os armazéns da filial dividido pela média diária das vendas no período, na mesma unidade. Sem cálculo quando o saldo é negativo, não há vendas positivas ou há filtro de armazém. |
| Vendas e última venda | Documentos de saída do produto/filial/unidade. A última venda considera saídas positivas até a data da base. Devoluções líquidas são preservadas no volume vendido. Não representam consumo interno ou todas as movimentações. |
| Média e dispersão | Quantidades vendidas por mês completo. Incluem meses sem venda desde o início das observações da fonte. Meses incompletos não entram no desvio/CV. |
| Coeficiente de variação (CV) | Desvio padrão amostral / média mensal, com pelo menos três meses completos. Indisponível para média nula/negativa ou meses com volume líquido negativo. Quanto maior o CV, maior a irregularidade das vendas observadas. |
| ABC do capital | Capital positivo por produto no recorte anterior aos filtros ABC/atividade/saldo. A até atingir 80%; B até 95%; C restante. O produto que cruza o limite permanece na classe anterior. |
| Capital por última venda | Classes 0–30, 31–90, mais de 90 dias e sem venda registrada. Produtos sem vendas não são automaticamente obsoletos, sobretudo matérias-primas e embalagens. |
| Histórico | Custo dos fechamentos disponíveis no período e no recorte. Mês ausente permanece sem valor; a média móvel só é desenhada quando existem três meses consecutivos. |

**O saldo é atual na data da base.** O período altera vendas e evolução histórica,
sem reconstruir saldos atuais a partir de vendas passadas. Giro/dias da fonte
continuam associados ao último fechamento informado, identificado na tela.

O PBIX recebido contém saldos atuais em duas filiais e 13 armazéns; os fechamentos
cobrem somente Filial 01 / armazém 01. Essa abrangência fica visível no gráfico.
Portanto, não se trata de uma conciliação entre o estoque atual total e o histórico.

Há quatro códigos históricos sem cadastro de produto e indicadores de giro/dias
negativos ou extremos no modelo. Os códigos e valores são mantidos, com descrição
de cadastro indisponível quando necessário. Não são inventados nomes de produto,
nem estimativas para substituir esses valores. Veja a conciliação incluída.

## Dados, precisão e funcionamento

- A leitura do PBIX é local, somente leitura. Não executa consultas SQL, M ou DAX,
  não atualiza o BI e não precisa do Power BI Desktop para extrair o modelo importado.
- Do modelo são extraídos cadastro de produtos/locais, saldo atual, um único conjunto
  de fechamentos e saídas agrupadas por dia/produto/filial/unidade. Não são copiados
  clientes, fornecedores, pedidos, documentos, vendedores ou contas a pagar/receber.
- Quantidades são armazenadas em milionésimos da unidade; custos em centavos de real,
  com arredondamento decimal explícito. Os indicadores de giro/dias mantêm o ponto
  flutuante original da fonte. Formatação visual não altera os valores armazenados.
- O recurso integrado tem manifesto SHA-256 verificado antes da leitura e da compilação.
  É incluído tanto no pacote Python quanto nos recursos PyInstaller. Uma base local
  inválida é recuperada a partir do recurso integrado; o problema fica registrado.
- Há validação de chaves, duplicidades, exclusões, datas, números finitos, formato e
  limites de tamanho. A leitura utiliza nomes de colunas, respeitando a ordem variável
  em que o modelo as devolve. A mudança do PBIX durante a extração invalida a leitura.
- Leitura, filtros e Excel rodam em tarefas fora da interface. Somente a solicitação
  mais recente pode publicar resultados. Cancelar conserva a base anterior. Base e
  exportação são publicadas por substituição atômica, sem sobrescrever o PBIX.
- Falhas de fonte ou período preservam os últimos resultados válidos. Uma seleção
  ainda não aplicada não pode ser exportada com dados de um recorte anterior.
- Selecionar linha, ordenar, paginar e baixar o Excel não reinicia as animações dos
  gráficos. A troca de módulo não recria a página ou a consulta de Importações.

## Validação e limites da entrega

Veja `CONCILIACAO_ESTOQUE_520_RC2.json`, `EVIDENCIAS_ESTOQUE_520_RC2.json` e os testes incluídos.
Os testes automatizados Qt usam renderização offscreen em Linux. A instalação,
Shell, DPI e GPU precisam da homologação habitual no Windows. As rodas binárias
das dependências foram verificadas para CPython 3.14 / Windows x64; isso não equivale
a ter executado o Setup no Windows.

Este é um pacote de fontes e assistentes de preparação, sem Setup Windows já
compilado. O fluxo de compilação existente foi mantido e passou a incluir o leitor
de PBIX e suas dependências/licenças. Não foi implementado login, serviço corporativo
multiusuário, escrita no ERP ou conector SQL de produção.

As regras e geradores de Importações (Comex, Excel, Power BI e PDF) não foram alterados.

## Referências técnicas consultadas

- [PBIXRay: API e limites do leitor](https://www.pbixray.com/docs/).
- [Qt 6.10: QAbstractTableModel e acesso pela thread do modelo](https://doc.qt.io/qt-6.10/qabstracttablemodel.html).
- [Qt for Python: sinais, slots e conexões entre threads](https://doc.qt.io/qtforpython-6/tutorials/basictutorial/signals_and_slots.html).

Referências adicionais de interface, gráficos e estatística: [PESQUISA_ESTOQUE_520_RC2.md](PESQUISA_ESTOQUE_520_RC2.md).
