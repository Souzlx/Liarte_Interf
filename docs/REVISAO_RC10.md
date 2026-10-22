# Revisão RC10 — Python 3.14

A revisão acrescenta suporte ao CPython 3.14 padrão de 64 bits, preservando 3.11–3.13 e o fluxo da RC9. Não altera a interface nem as regras de obtenção, cálculo, filtragem ou exportação dos dados.

## Alterações

- Metadados aceitam Python `>=3.11,<3.15`; assistentes e mensagens incluem 3.14.
- Antes de preparar, o assistente verifica versão, implementação, GIL e tamanho do runtime Windows. Runtimes incompatíveis são recusados antes de mudar o ambiente ou baixar bibliotecas.
- O ambiente de dependências é comparado com o runtime selecionado: versão, instalação-base, arquitetura e GIL. A chamada isolada impede interferência de caminhos externos. `python.exe` e `pythonw.exe` da mesma instalação compartilham a identidade e não provocam recriações repetidas.
- Na troca de Python, o ambiente anterior é guardado ao lado do novo. Uma falha na criação restaura o original. O bloqueio de preparação continua evitando duas operações simultâneas. Relatórios e preferências não são movidos nem removidos.
- Bibliotecas fixadas permanecem iguais. PySide6 6.10.3 já suporta Python 3.14; não foi necessário ampliar a alteração para atualizações de Qt ou dos geradores.
- Licença oficial do CPython 3.14.8 incluída, com origem e SHA-256. Versão do aplicativo/Setup atualizada para RC10; identidade da instalação preservada.
- Workflow Windows preparado para executar e compilar com Python 3.11, 3.12, 3.13 e 3.14. O workflow não foi executado remotamente nesta entrega.

## Verificação executada

| Runtime real | Testes | Resultado |
| --- | ---: | --- |
| CPython 3.11.17 | 334 | Aprovado |
| CPython 3.12.14 | 334 | Aprovado |
| CPython 3.13.16 | 334 | Aprovado |
| CPython 3.14.8 | 334 | Aprovado |

Cada suíte incluiu Qt em modo offscreen, consulta paginada de 100 mil registros, testes dos geradores Excel/PDF/Power BI, cancelamento, falhas controladas e preparação. Foram acrescentadas 11 regressões para identidade, migração, restauração e reutilização do ambiente. Uma migração real de ambiente 3.13.16 para 3.14.8 preservou os arquivos sentinela externos de relatórios e preferências; a segunda preparação reutilizou o novo ambiente.

Compilação PyInstaller com Python 3.14 concluída no Linux. O executável congelado passou pelo autoteste: janela/ícone, temas claro e escuro, diálogo de exportação, Excel, PDF com logo e projeto Power BI com 6 páginas/85 visuais. Foi construída também a wheel do próprio projeto. As wheels binárias das dependências Windows x64/Python 3.14 foram baixadas e seus metadados verificados, incluindo dependências condicionais de compilação.

A comparação com o ZIP RC9 confirma a preservação byte a byte de `liarte_core`, `liarte_engine`, QML, recursos visuais e exemplos. `liarte_desktop` só mudou sua constante de versão. Requisitos fixados também continuam idênticos. Consulte PRESERVACAO_RC10.json e EVIDENCIAS_RC10.json.

## Limites da validação

Os ensaios foram executados no Linux com CPython padrão e Qt offscreen. Disponibilidade de wheels Windows e testes simulados de integração Windows não equivalem à execução do aplicativo ou do Setup no Windows. Instalação, atalhos, DPI/GPU e Power BI Desktop continuam sujeitos à homologação Windows da TI. O ZIP contém fontes e assistentes, sem um Setup Windows já compilado.

A alteração é de compatibilidade. Não houve nova consulta de conciliação online do Comex nesta revisão. Os testes usam capturas e dados sintéticos identificados; os exemplos oficiais e sua proveniência permanecem os da RC9. Não se promete imunidade absoluta a falhas de ambiente, serviço externo ou dados futuros.

## Referências dos fornecedores

- Qt: suporte ao Python 3.14 (PYSIDE-3147, Qt for Python 6.10.1): https://doc.qt.io/qtforpython-6/release_notes/pyside6_release_notes.html
- Distribuição fixada do Qt: https://pypi.org/project/PySide6-Essentials/6.10.3/
- PyInstaller fixado: https://pypi.org/project/pyinstaller/6.22.3/
- Notas PyInstaller: https://pyinstaller.org/en/stable/CHANGES.html
- Mudanças Python 3.14: https://docs.python.org/3.14/whatsnew/3.14.html
- Identidade e recriação de ambientes: https://docs.python.org/3.14/library/venv.html
- Licença CPython 3.14.8: https://github.com/python/cpython/blob/v3.14.8/LICENSE
