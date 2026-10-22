# Ajuste da tela Início — 5.1.0-rc.3

Removida a superfície azul de ação no cartão Importações, incluindo os rótulos Abrir Importações, Retomar consulta e Acompanhar. O cartão inteiro permanece clicável e acessível pelo teclado. O item Importações no menu lateral continua disponível.

O conteúdo usa uma única linha de layout com ícone e textos. A altura mínima é de 128 px e cresce quando necessário para acomodar o texto. O estado da consulta, foco visível e efeito ao passar o mouse permanecem.

Não há alteração de consultas, filtros, cálculos, relatórios, preferências, dependências ou identidade da instalação. Main.qml e todos os arquivos Python funcionais são idênticos à RC2; apenas a constante da versão foi atualizada.

Validação desta revisão: 45 testes existentes de plataforma, identidade e metadados de instalação, em Python 3.14.8/Qt 6.10.3, e 30 cenários de layout. Os testes de instalação utilizam simulações; não foi produzido Setup Windows. As verificações de layout usam respostas oficiais capturadas, sem consulta ao vivo. A suíte integral da RC2 permanece como evidência histórica e não foi repetida nesta alteração pontual.

Veja EVIDENCIAS_UI_RC3.json, PRESERVACAO_UI_RC3.json e LAYOUTS_RC3.json.
