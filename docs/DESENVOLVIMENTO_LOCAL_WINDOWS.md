# Continuar o desenvolvimento no Windows

O projeto deve ser aberto a partir de um clone do repositório. A pasta instalada pelo Setup contém o aplicativo distribuído; utilize outra pasta para editar os fontes.

O fluxo recomendado é VS Code com a extensão oficial Codex, publicada pela OpenAI, e um ambiente Python local ao projeto. O GitHub continua guardando o histórico e executando o CI. Consulte o [estado atual](STATUS.md) para as versões publicadas e o [resumo de continuidade](CONTINUIDADE_LOCAL.md) para o histórico das validações já concluídas.

## 1. Preparar as ferramentas

Instale, se necessário:

- [Visual Studio Code](https://code.visualstudio.com/Download).
- [Git para Windows](https://git-scm.com/download/win).
- [CPython 3.12 de 64 bits](https://www.python.org/downloads/windows/), edição padrão com GIL. O projeto também aceita 3.11, 3.13 e 3.14 padrão de 64 bits.

No VS Code, abra Extensões, procure **Codex** e confira que o publicador é **OpenAI**. Instale a extensão oficial e entre com sua conta ChatGPT. O [repositório oficial do Codex](https://github.com/openai/codex) aponta para a instalação em IDE e descreve o uso com login ChatGPT.

Para esta aplicação Qt, comece com o projeto e o terminal no Windows nativo. O teste da janela será feito no mesmo Windows usado para executar a LIARTE.

## 2. Clonar e abrir o projeto

Escolha uma pasta de desenvolvimento, por exemplo `C:\Projetos`. Abra o PowerShell nessa pasta e execute:

```powershell
git clone https://github.com/Souzlx/Liarte_Interf.git
cd Liarte_Interf
git switch -c desenvolvimento-local
```

O comando cria uma branch local para o trabalho. Se já houver um clone com alterações, confira `git status` e continue nele; não sobrescreva nem descarte essas alterações para repetir os comandos.

No VS Code, use **Arquivo > Abrir Pasta** e selecione a pasta clonada `Liarte_Interf`. Ela deve conter `src`, `tests`, `tools`, `pyproject.toml` e `iniciar.py`.

## 3. Criar o ambiente Python

No terminal PowerShell do VS Code, dentro da pasta do projeto:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
```

Se estiver usando outra versão suportada, substitua `-3.12` pela versão instalada. As dependências estão fixadas no repositório. A primeira preparação precisa de acesso aos gerenciadores de pacotes.

Os comandos usam diretamente o Python da `.venv`; não exigem ativar scripts PowerShell nem alterar a política de execução. Essa pasta é ignorada pelo Git.

Se usar a extensão Python do VS Code, selecione `.venv\Scripts\python.exe` como interpretador do projeto. Para o fluxo manual deste guia, execute os comandos pelo terminal usando esse mesmo caminho.

## 4. Fazer a primeira abertura e os testes

Feche a LIARTE instalada antes da primeira conferência para distinguir as duas janelas. Abra a interface com:

```powershell
.\.venv\Scripts\python.exe iniciar.py --demo --no-settings
```

Essa combinação usa demonstração sintética para Importações, evita a gravação de preferências e desativa o cache persistente de Estoque. O Estoque pode receber uma cópia de uma base para análise em memória; o histórico persistente de backups não funciona com o cache desativado.

`--demo` sozinho não oferece esse isolamento de preferências e cache. `--data-dir` altera apenas o diretório do cliente Comex e também não cria um perfil completo separado.

Os logs desse primeiro comando ainda utilizam a pasta normal de diagnóstico do aplicativo. Portanto, `--demo --no-settings` não equivale a um perfil completo separado.

### Desenvolver com persistência em um perfil separado

Depois da primeira conferência, abra a demonstração com um perfil próprio:

```powershell
.\.venv\Scripts\python.exe iniciar.py --profile-dir .liarte-dev-profile --demo
```

A pasta pode ser informada por caminho relativo ao terminal ou absoluto. A janela fica marcada como **Desenvolvimento**. O perfil guarda suas preferências em `settings.ini`, dados Comex em `dados/`, Estoque em `estoque/base.liarte` e seus backups em `estoque/backups/`, além de logs, pasta padrão de relatórios e configuração da central na mesma pasta de perfil. A pasta `.liarte-dev-profile` no projeto é ignorada pelo Git; não envie seus dados ao repositório.

Um perfil novo começa vazio e não migra preferências antigas, caches ou bases da instalação. O modo `--demo` mantém as consultas sintéticas. Para testar Estoque e restauração, carregue uma cópia de uma base sintética nesse perfil e mantenha os arquivos originais preservados. A execução de desenvolvimento também evita o mutex e os atalhos da instalação de uso diário.

`--profile-dir` não pode ser combinado com `--data-dir`; o programa recusa a combinação para manter os dados dentro do perfil. Se acrescentar `--no-settings`, as preferências e o cache persistente de Estoque serão desativados, e o histórico de backups ficará indisponível; os logs continuarão no perfil escolhido. Não escolha a pasta da instalação nem seu perfil diário como diretório de desenvolvimento.

Para executar a suíte offline:

```powershell
.\.venv\Scripts\python.exe verificar.py --headless --volume
```

O comando executa testes Qt e de domínio com dados sintéticos; não consulta o Comex Stat real. Para avaliar a aparência no seu monitor, utilize também a janela aberta no Windows, além dos resultados automatizados.

Os testes HTTPS locais precisam do executável `openssl` no `PATH`. Se a suíte indicar que essa classe foi ignorada e o Git para Windows estiver instalado no caminho padrão, você pode disponibilizar o OpenSSL já existente somente nesse terminal:

```powershell
$env:PATH = 'C:\Program Files\Git\ucrt64\bin;' + $env:PATH
$env:OPENSSL_CONF = 'C:\Program Files\Git\usr\ssl\openssl.cnf'
.\.venv\Scripts\python.exe verificar.py --headless --volume
```

Confira esses caminhos se o Git estiver em outro local. Não é necessário alterar o `PATH` global. Testes exclusivos de POSIX ou que exigem privilégios de symlink podem ser ignorados no Windows conforme as condições registradas pela suíte.

## 5. Retomar a conversa no Codex local

Abra o Codex no VS Code com essa pasta aberta e inicie uma sessão local. Acesso ao repositório no GitHub, por si só, não concede acesso aos arquivos do computador. A sessão local precisa ter a pasta clonada como área de trabalho.

Cole esta mensagem inicial:

```text
Estamos continuando o projeto Souzlx/Liarte_Interf no meu Windows.
Leia README.md, docs/CONTINUIDADE_LOCAL.md e docs/DESENVOLVIMENTO_LOCAL_WINDOWS.md.
Estou na branch desenvolvimento-local. Mantenha a instalação de uso diário separada.
Primeiro confira git status e o ambiente .venv e prepare as dependências se necessário.
Use iniciar.py --profile-dir .liarte-dev-profile --demo para desenvolver com persistência
separada, e execute os testes apropriados.
Preserve minhas alterações locais, a instalação de uso diário e os arquivos de origem.
Valide a persistência com dados sintéticos no perfil de desenvolvimento e confira
que os arquivos do perfil de uso não foram alterados.
```

O resumo no repositório fornece à nova sessão o estado do trabalho sem depender de transferência automática deste histórico de chat. Depois dessa preparação, novas alterações podem ser desenvolvidas e observadas diretamente no Windows.

## Compilar quando necessário

Para editar e testar a interface, não é necessário gerar um novo EXE a cada alteração. Reinicie a execução dos fontes para carregar o código atualizado.

Quando precisar conferir o aplicativo congelado, execute no ambiente Windows preparado:

```powershell
.\.venv\Scripts\python.exe tools/build_windows.py
```

Para criar o Setup, instale também Inno Setup 6.3 ou superior e siga o [guia de instalação](INSTALACAO_531.md). Ele não é necessário para editar os fontes ou executar os testes comuns. O teste destrutivo de instalação/desinstalação do CI recusa perfis normais de usuário e não deve ser adaptado para rodar na sua instalação de uso diário.
