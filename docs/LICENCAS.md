# Componentes e distribuição

Bibliotecas de terceiros mantêm seus termos. Esta entrega não atribui licença
open source às regras LIARTE; a empresa define a política de distribuição.

| Componente | Uso |
| --- | --- |
| Python 3.11–3.14 padrão | Runtime; versão exata determinada na compilação. |
| PySide6-Essentials/shiboken6 6.10.3 | Qt Core/Gui/Qml/Quick/Controls Basic/Dialogs. |
| openpyxl 3.1.5, et-xmlfile 2.0.0 | Excel. |
| reportlab 4.4.9, pillow 12.3.0, charset-normalizer 3.5.2 | PDF e dependências. |
| pypdf 6.10.0 | Conferência PDF. |
| PyInstaller 6.22.3 e hooks 2026.8 | Ferramentas de compilação, fora do runtime. |
| Inno Setup 6.3+ | Ferramenta instalada pela TI para gerar o Setup. |

Módulos Qt conservam suas opções e obrigações LGPL/GPL/comerciais conforme o
componente. Isso não declara que todo o produto usa GPL. Onedir mantém bibliotecas
dinâmicas separadas. Não usa Charts, Graphs, WebEngine ou outro framework gráfico.

Build reúne metadados, textos/avisos e licença Python; falha se faltar texto
obrigatório. third_party inclui LGPLv3, GPLv2/GPLv3 e licenças originais CPython
3.11/3.12/3.13/3.14 com URLs/SHA-256. A licença instalada tem precedência; a cópia da
mesma versão é fallback de coleta, sem alterar termos. A cópia 3.14 corresponde
à licença oficial do CPython 3.14.8. A coleta foi verificada no build Linux.

Conferir inventário e condições de todos os arquivos do binário Windows antes da
distribuição, incluindo transitivos/acesso ao código-fonte aplicável.
DEPENDENCIAS_QT_WINDOWS_HISTORICO.json é análise estática anterior da wheel Qt
Windows 6.10.3, não execução desta candidata. Não há certificação jurídica.

Marca LIARTE reaproveitada do projeto original. Tema escuro renderiza letras
brancas mantendo o símbolo colorido; PNG original e ícone foram preservados.

Fontes dos fornecedores:
- https://doc.qt.io/qt-6/licensing.html
- https://doc.qt.io/qtforpython-6/licenses.html
- https://code.qt.io/cgit/pyside/pyside-setup.git/
- https://code.qt.io/cgit/qt/qtbase.git/
- https://pyinstaller.org/en/stable/license.html
- https://github.com/python/cpython/blob/3.13/LICENSE
- https://github.com/python/cpython/blob/v3.14.8/LICENSE
- https://pypi.org/project/openpyxl/3.1.5/
- https://pypi.org/project/reportlab/4.4.9/
- https://pypi.org/project/pypdf/6.10.0/
- https://pypi.org/project/pillow/12.3.0/
