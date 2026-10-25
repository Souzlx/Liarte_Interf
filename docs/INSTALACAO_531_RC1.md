# Instalação e restauração — 5.3.1-rc.1

Esta prévia acrescenta o Setup Windows e cópias das bases anteriores de Estoque. A versão estável 5.3.0 continua disponível. O Setup e o ZIP portátil incluem Python, Qt e as dependências; o computador do usuário não precisa de Python.

## Instalar e atualizar

Feche a LIARTE e execute `LIARTE_Desktop_5.3.1-rc.1_Setup.exe`. A instalação usa a conta atual, cria atalhos e registra a desinstalação no Windows. O diretório padrão é `%LOCALAPPDATA%\Programs\LIARTE Desktop`.

Para atualizar uma instalação feita por Setup, execute o novo Setup na mesma conta. O diretório registrado da instalação anterior é reutilizado. Bases, cópias anteriores e preferências ficam no perfil do usuário, fora da pasta do programa. Os relatórios continuam no local em que foram exportados. Confira **5.3.1-rc.1** em Ajuda.

Quem usava somente o ZIP pode instalar o Setup na mesma conta e utilizar o perfil já existente. Um atalho antigo para a pasta portátil continua apontando para essa pasta; utilize o atalho criado pelo Setup.

O aplicativo deve estar fechado para instalar ou remover arquivos. As janelas abertas mantêm a sinalização usada pelo instalador; não há encerramento forçado de tarefas pelo programa.

## Cópias das bases de Estoque

Ao atualizar uma base local válida, o aplicativo prepara uma cópia da versão anterior antes de publicar a nova. A retenção padrão é de dez cópias válidas recentes. A limpeza ocorre após a publicação; se for interrompida ou encontrar arquivos bloqueados, as cópias extras são preservadas e a operação pode ser repetida na próxima atualização. A primeira abertura, sem base anterior, não cria uma versão histórica.

Em **Estoque**, abra **Restaurar**. A lista identifica quando a cópia foi gravada e a data de referência dos dados. Selecione a cópia, confira a confirmação e restaure. A base atual válida também é guardada antes da troca. A análise passa a usar os dados da base restaurada; o arquivo original de origem não é alterado.

Cópias com conteúdo inválido ou integridade divergente não são utilizadas. Se uma operação falhar ou for cancelada antes da publicação, a base anterior permanece ativa. Uma falha na preparação do backup impede substituir uma base válida.

As cópias são locais ao perfil Windows e contêm a base de estoque do aplicativo. Não são cópias do PBIX completo nem dos relatórios. A guarda externa desses arquivos continua separada. Se o perfil for apagado, suas cópias locais também serão apagadas.

## Desinstalar

Use Configurações do Windows ou o atalho **Desinstalar**. A opção padrão mantém bases, backups, diagnósticos e preferências, permitindo retomá-los em outra instalação na mesma conta. Apagar esses dados exige a confirmação explícita mostrada na remoção.

Na desinstalação silenciosa, os dados são mantidos por padrão. Para administração e testes controlados, `/PURGEDATA=1` solicita explicitamente a exclusão do perfil do aplicativo. Arquivos exportados fora dessa pasta permanecem intactos. Não utilize essa opção para uma atualização normal.

## Compilar e testar

No Windows com CPython 3.11–3.14 de 64 bits e Inno Setup 6.3 ou superior, `CRIAR_INSTALADOR.cmd` mantém o fluxo completo de preparação, testes e compilação. O compilador é necessário apenas na máquina que gera o Setup.

Em um ambiente Windows já preparado, é possível reutilizar uma pasta portátil validada:

```powershell
python tools/build_installer.py --bundle dist/LIARTE_Desktop --output instalador
```

O empacotador confere a versão do autoteste Windows e todos os checksums do bundle antes de compilar em uma área temporária. Uma falha preserva o Setup anterior. O workflow de instalador executa os testes e produz as evidências de instalação, atualização, atalhos e desinstalação antes de disponibilizar a prévia.

O ensaio automatizado usa uma conta descartável do runner Windows e uma instalação anterior compilada com o pacote e o script da versão 5.3.0. Não equivale à validação de políticas da empresa, de todos os antivírus, do SmartScreen ou de todas as configurações DPI/GPU. O Setup não contém assinatura digital de editor.

## Resultados e download

Código validado e marcado como `v5.3.1-rc.1`: `db77b9517b2af234d02db6927bc3d219a8845ddb`.

- [Baixar o Setup da prévia](https://github.com/Souzlx/Liarte_Interf/releases/download/v5.3.1-rc.1/LIARTE_Desktop_5.3.1-rc.1_Setup.exe).
- [ZIP portátil e checksums](https://github.com/Souzlx/Liarte_Interf/releases/tag/v5.3.1-rc.1).
- [Execução validada no Windows](https://github.com/Souzlx/Liarte_Interf/actions/runs/40190640420).
- [Evidências da entrega](EVIDENCIAS_INSTALADOR_531_RC1.json), [matriz Windows](VALIDACAO_WINDOWS_531_RC1.json) e [autoteste do Setup](AUTOTESTE_INSTALADOR_531_RC1.json).

A suíte final executou **815 testes no CI Linux**, todos aprovados. Em cada um dos quatro builds Windows, foram **814 aprovados e um teste exclusivo de POSIX ignorado**. O total inclui 74 regressões novas de backup, interface e empacotamento em relação à 5.3.0. Os autotestes dos executáveis também confirmaram backup e restauração em diretórios temporários.

O ensaio do Setup aprovou instalação nova, destinos dos atalhos, desinstalação silenciosa preservando dados, reutilização do diretório anterior na atualização, preservação de preferências/base/histórico e exclusão explícita do perfil com um relatório externo intacto. A verificação dos atalhos ocorreu antes de abrir o aplicativo, para conferir o que o próprio Setup criou.

Na conferência de janelas compactas, os botões do cabeçalho passaram a ocupar duas linhas; uma regressão com métricas de fonte ampliadas verifica que a ação Restaurar continua visível e recebe o clique. A prévia foi publicada após todos os bloqueios passarem. A versão estável 5.3.0 continua marcada como a mais recente estável.
