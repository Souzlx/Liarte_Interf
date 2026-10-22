# Instalação da LIARTE - RC10

O destinatário do **Setup compilado** não precisa instalar Python, Qt ou dependências. O ZIP atual contém os fontes e assistentes para a TI gerar essa distribuição no Windows; não é um Setup já compilado.

## Para quem vai usar

1. Abra `LIARTE_Desktop_5.0.0-rc.10_Setup.exe` fornecido pela TI.
2. Clique em **Instalar**. A instalação usa sua conta e não solicita administrador por definição do aplicativo.
3. Clique em **Concluir**, mantendo **Abrir Liarte Importações** marcado se desejar abrir agora.

Atalhos na Área de Trabalho e menu Iniciar são automáticos. O Setup não exige escolher linguagem, pasta ou grupo de programas. A pasta padrão é `%LOCALAPPDATA%\Programs\LIARTE Desktop`; atualizações reutilizam a pasta registrada da instalação anterior. A TI ainda pode definir `/DIR` no processo de distribuição quando necessário. Políticas corporativas podem exigir liberação pela TI.

## Atualizar

Feche a LIARTE normalmente, aguardando ou cancelando as tarefas em andamento, e abra o novo Setup na mesma conta. A identidade da instalação e o perfil não mudam. O aplicativo mantém uma sinalização de processo aberto que o Setup/desinstalador verifica; versões anteriores ainda podem ser detectadas pelo Restart Manager do Windows. Não é usado fechamento forçado (`force`). Instalações simultâneas são bloqueadas. Configurações e cache ficam fora da pasta instalada; os relatórios permanecem na pasta em que você os salvou.

## Desinstalar

Use **Configurações > Aplicativos** do Windows ou o atalho **Desinstalar**. Após a remoção, a pergunta permite apagar cache, diagnósticos e preferências; **Não**, a opção padrão, mantém esses dados. Relatórios exportados são preservados. Em desinstalação silenciosa os dados pessoais também são mantidos. Não é preciso usar comandos.

## Para a TI: criar a distribuição

1. Extraia o ZIP completo no Windows x64, com Python 3.11, 3.12, 3.13 ou 3.14 padrão de 64 bits, com Tkinter.
2. Instale Inno Setup **6.3 ou superior** a partir de https://jrsoftware.org/isdl.php. Essa ferramenta só é necessária na máquina que compila.
3. Abra **CRIAR_INSTALADOR.cmd**. O assistente confere o compilador, prepara um ambiente isolado, verifica os documentos/interface, executa os testes e compila o aplicativo/Setup.
4. Ao concluir, clique em **Abrir pasta**. A saída fica em `instalador/LIARTE_Desktop_5.0.0-rc.10_Setup.exe`.
5. Homologue em uma conta/máquina Windows de teste antes da distribuição: instalação nova sem Python, atualização mantendo dados, atalhos, abertura de Excel/PDF/BI e desinstalação com as duas opções de dados.

A geração lê a versão do próprio aplicativo e passa essa versão ao compilador. Só aceita um arquivo novo da área temporária, com tamanho mínimo e cabeçalhos DOS/PE coerentes, depois de um autoteste do executável da mesma versão. Essa checagem não substitui execução no Windows ou assinatura digital. Uma falha mantém o Setup anterior. O SHA-256 da saída é registrado no diagnóstico. Nenhuma assinatura/certificado foi criado ou simulado.

O assistente de desenvolvimento permite redimensionar a janela, mostra fases claras e oferece reparo/diagnóstico sem abrir avisos de sucesso sobre a janela. A verificação completa pode ser reutilizada por até sete dias quando código, recursos, runtime e requisitos forem idênticos. Toda abertura continua verificando as versões e confirmando a resposta da janela Qt. Reparo, mudança ou falha invalidam a reutilização; compilar sempre repete a verificação completa.

## Código-fonte com Python 3.14

Extraia o ZIP completo e abra **INICIAR_DESKTOP.cmd**. O assistente usa o Python padrão encontrado no Windows. A preparação admite CPython 3.11 a 3.14, edição padrão com GIL e de 64 bits. Qt e as demais bibliotecas permanecem nas mesmas versões fixadas da RC9. A edição sem GIL não faz parte dos alvos das dependências deste pacote.

Ao detectar outro Python, o assistente recria apenas `.liarte-desktop-env`, instala as dependências e repete a verificação. A pasta anterior fica em `.liarte-desktop-env.anterior-<identificador>`; não é removida automaticamente. Se a criação do novo ambiente falhar, o anterior é restaurado. A preparação não altera relatórios ou preferências. Feche o aplicativo antes de trocar o Python ou reparar o ambiente. Uma abertura seguinte com o mesmo runtime reutiliza o ambiente existente.

Quem utiliza o **Setup compilado** continua sem precisar instalar Python. O compilador da TI deve usar uma das versões aceitas; os assistentes de compilação também aceitam 3.14. A licença correspondente foi incluída na coleta do empacotamento.

## Diagnóstico

O Setup gera log automaticamente na pasta temporária do Windows. A preparação registra `logs/preparacao-desktop.log` e o resultado do autoteste Qt na pasta extraída. Depois de instalado, use **Abrir diagnóstico** no aplicativo. Não apague relatórios ou configurações para reparar uma instalação.

## Fontes consultadas

- Inno Setup 6, páginas e botão de instalação: https://jrsoftware.org/is6help/topic_setup_disablereadypage.htm
- Reutilização do diretório: https://jrsoftware.org/is6help/topic_setup_usepreviousappdir.htm
- Processo em uso: https://jrsoftware.org/is6help/topic_setup_appmutex.htm
- Instalações simultâneas: https://jrsoftware.org/is6help/topic_setup_setupmutex.htm
- Fechamento de versões antigas: https://jrsoftware.org/is6help/topic_setup_closeapplications.htm
- Log: https://jrsoftware.org/is6help/topic_setup_setuplogging.htm
- Win32 `CreateMutexW`, assinatura e vida do handle: https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-createmutexw
