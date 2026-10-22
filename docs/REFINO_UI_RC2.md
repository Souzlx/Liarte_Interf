# Ajustes visuais — 5.1.0-rc.2

Revisão pontual da tela Início, preservando a estrutura central e o módulo de Importações.

- Cartão de Importações com altura de referência reduzida de 174 para 128 px em janelas largas. Em janelas estreitas, o conteúdo se organiza em coluna e cresce conforme o texto.
- Ação de abertura com fundo na cor principal da LIARTE. O cartão continua sendo um único botão, preservando clique, teclado e foco, sem criar botões aninhados.
- Descrição principal de 13 para 14 px; contexto da consulta e descrições dos módulos planejados de 12 para 13 px.
- Peso do texto do menu acompanha a seleção: destaque em Início ou Importações conforme a tela ativa.
- Estoque e Crédito com fundo transparente, borda mais discreta e textos legíveis, mantendo sua identificação como próximos módulos.

Os rótulos Abrir Importações, Retomar consulta e Acompanhar mantêm as mesmas condições. Consultas, filtros, gráficos, cálculos, documentos, preferências e ciclos de vida não foram alterados. O código Python do aplicativo é idêntico à RC1, exceto a constante da versão.

Evidências desta revisão: `EVIDENCIAS_UI_RC2.json`, `PRESERVACAO_UI_RC2.json` e `LAYOUTS_RC2.json`. A verificação é Linux/Qt offscreen. Os testes de volume e demais runtimes da RC1 permanecem documentados como históricos; esta revisão não afirma nova conciliação ao vivo com o Comex ou homologação Windows.
