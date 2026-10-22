# Revisão RC5

## Mudanças aplicadas

A RC5 refina a preparação, o instalador e os movimentos da interface. A única mudança visual do PDF é a marca original no cabeçalho, com o título deslocado horizontalmente dentro da mesma faixa. Extração, cadastro, filtros, cálculos, escopos de exportação e tabelas permanecem preservados.

- Corrigida a procura incorreta pelo Setup da RC1. A versão vem do literal do aplicativo, lido por AST sem executar código, e define o nome e a versão passada ao Inno.
- Setup compilado em área temporária do mesmo volume. Arquivo antigo não satisfaz a validação da nova execução; erro não substitui a saída anterior. Cabeçalhos DOS/PE, tamanho mínimo e SHA-256 conferidos; isso não equivale a assinatura digital.
- Setup reduzido a apresentação com Instalar e conclusão. Mantidos AppId, diretório anterior, perfil, atalhos, permissões por usuário e opção de manter dados na desinstalação. Logs automáticos e proteções contra instalação simultânea e atualização com a RC5 aberta.
- Assistente redimensionável com erro inline e resultado com Abrir pasta/Concluir. Falta de Inno detectada antes do preparo completo.
- Reutilização limitada da verificação completa, condicionada ao conteúdo do projeto, recursos, runtime e requisitos. Versões das dependências e sinal Qt de abertura continuam obrigatórios a cada execução. Reparo/build/falha não usam o atalho.
- Barra de progresso com interpolação limitada ao intervalo real. A informação percentual não é animada nem fabricada. Animações param ao minimizar/ocultar a janela ou reduzir movimento. A curva mantém uma textura por transição; leitura/hover continuam sem repintar a curva.
- Setas dos seletores indicam abertura com transição breve. Filtros inicializam antes da animação, aceitando as primeiras letras sem reset ao terminar de abrir.
- PDF usa o mesmo PNG original da interface, em 24 mm de largura, no cabeçalho esquerdo de todas as páginas. Carrega uma vez por documento e reutiliza o recurso. Marca ausente/corrompida impede publicar um PDF incompleto, preservando o arquivo anterior.

## Conferências

A suíte da RC5 inclui 263 testes, além dos roteiros complementares. Há regressões para saída antiga de compilador, falha de publicação, versão incorreta do autoteste, cache inválido/expirado, falha no sinal de abertura, tipos da API Windows, digitação durante abertura, atualizações rápidas de série, minimização e redução de movimento.

No PDF sintético de 160 linhas/4 páginas, os **988 fragmentos de texto da tabela e rodapé** têm texto, posição e tamanho idênticos à referência RC4. Logo proporcional e transparência verificadas em cada página; renderização inspecionada. O exemplo real filtrado permanece em uma página.

Os **253.359 valores de células não vazias** do Excel mantêm valores/formatos e alinhamento vertical centralizado; oito abas e E municipal 64. Foram conferidos novamente **218 recortes por SQL** da captura oficial previamente conciliada. São regressões locais, não novas consultas independentes da API. Geração dos três documentos executada pelos workers da interface, com a rede bloqueada nesse roteiro de captura histórica.

Foram conferidos 96 layouts gerais, 36 vistas de análise e 384 aberturas de diálogos, nos dois temas, seis tamanhos e escalas 100/125/150/200% nos layouts gerais. O pacote congelado de teste Linux passou nos dois temas, ícone/título, diálogo Salvar e Excel/PDF com logo/Power BI. Os resultados detalhados ficam em EVIDENCIAS_RC5.json e nos relatórios RC5.

## Limites verificáveis

Não existe garantia absoluta de ausência de bugs. Não houve execução do Setup/COM no Windows real, de Power BI Desktop ou de Narrador, nem teste de usabilidade com pessoas. O ZIP entrega fontes/assistentes, não um EXE Windows. A homologação Windows descrita em INSTALACAO_RC5.md permanece necessária. As APIs do Comex podem revisar dados ou limitar chamadas; as proteções de timeout/cache/cancelamento foram preservadas.

## Critérios de animação

Movimentos curtos explicam resposta e estado; não atrasam a interação e não alteram valores. Não há efeitos contínuos fora de progresso indeterminado ativo. Usa-se `SmoothedAnimation` para acompanhar mudanças do progresso sem saltos abruptos, mantendo o percentual real separado. Não houve inclusão de QtCharts/Graphs/WebEngine ou dependências novas.

Referências Qt consultadas: https://doc.qt.io/qt-6.10/qml-qtquick-smoothedanimation.html e https://doc.qt.io/qt-6.10/qml-qtquick-frameanimation.html. O estudo mais amplo de usabilidade e estatística da RC4 continua válido e acompanha o pacote.
