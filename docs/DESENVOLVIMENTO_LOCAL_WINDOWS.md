# Continuar o desenvolvimento no Windows

O projeto deve ser aberto a partir de um clone do repositório. A pasta instalada pelo Setup contém o aplicativo distribuído; utilize outra pasta para editar os fontes.

O fluxo recomendado é VS Code com a extensão oficial Codex, publicada pela OpenAI, e um ambiente Python local ao projeto. O GitHub continua guardando o histórico e executando o CI. A confirmação de uso da prévia 5.3.1-rc.1 foi recebida do usuário; isso está registrado no [resumo de continuidade](CONTINUIDADE_LOCAL.md).

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

Os logs ainda utilizam a pasta normal de diagnóstico do aplicativo. Portanto, este comando não equivale a um perfil totalmente isolado. Para desenvolver e testar persistência, backup ou preferências com dados locais, a primeira mudança recomendada é acrescentar um perfil de desenvolvimento separado para cache, configurações e logs.

Para executar a suíte offline:

```powershell
.\.venv\Scripts\python.exe verificar.py --headless --volume
```

O comando executa testes Qt e de domínio com dados sintéticos; não consulta o Comex Stat real. Para avaliar a aparência no seu monitor, utilize também a janela aberta no Windows, além dos resultados automatizados.

## 5. Retomar a conversa no Codex local

Abra o Codex no VS Code com essa pasta aberta e inicie uma sessão local. Acesso ao repositório no GitHub, por si só, não concede acesso aos arquivos do computador. A sessão local precisa ter a pasta clonada como área de trabalho.

Cole esta mensagem inicial:

```text
Estamos continuando o projeto Souzlx/Liarte_Interf no meu Windows.
Leia README.md, docs/CONTINUIDADE_LOCAL.md e docs/DESENVOLVIMENTO_LOCAL_WINDOWS.md.
A instalação 5.3.1-rc.1 foi validada por mim. Estou na branch desenvolvimento-local.
Primeiro confira git status e o ambiente .venv, prepare as dependências se necessário,
abra com --demo --no-settings e execute os testes apropriados.
Preserve minhas alterações locais, a instalação de uso diário e os arquivos de origem.
Para testar persistência, prepare um perfil de desenvolvimento separado antes de
usar cache, preferências ou backups reais.
```

O resumo no repositório fornece à nova sessão o estado do trabalho sem depender de transferência automática deste histórico de chat. Depois dessa preparação, novas alterações podem ser desenvolvidas e observadas diretamente no Windows.

## Compilar quando necessário

Para editar e testar a interface, não é necessário gerar um novo EXE a cada alteração. Reinicie a execução dos fontes para carregar o código atualizado.

Quando precisar conferir o aplicativo congelado, execute no ambiente Windows preparado:

```powershell
.\.venv\Scripts\python.exe tools/build_windows.py
```

Para criar o Setup, instale também Inno Setup 6.3 ou superior e siga o [guia de instalação](INSTALACAO_531_RC1.md). Ele não é necessário para editar os fontes ou executar os testes comuns. O teste destrutivo de instalação/desinstalação do CI recusa perfis normais de usuário e não deve ser adaptado para rodar na sua instalação de uso diário.
