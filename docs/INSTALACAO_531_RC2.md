# Instalação e atualização — 5.3.1-rc.2

A candidata reúne alertas, comparação mensal, análise de desempenho, interface por tarefas e ordenações de Estoque, mantendo o instalador e a restauração de bases. O Setup e o ZIP portátil incluem Python, Qt e as dependências. O computador do usuário não precisa de Python.

## Disponibilidade

A versão está preparada para o fluxo de validação e publicação. Os links abaixo passam a fornecer os arquivos após a conclusão desse fluxo:

- [Setup 5.3.1-rc.2](https://github.com/Souzlx/Liarte_Interf/releases/download/v5.3.1-rc.2/LIARTE_Desktop_5.3.1-rc.2_Setup.exe).
- [ZIP portátil e SHA256SUMS.txt](https://github.com/Souzlx/Liarte_Interf/releases/tag/v5.3.1-rc.2).
- [Notas da candidata](RELEASE_5.3.1-rc.2.md).

A versão estável [5.3.0](https://github.com/Souzlx/Liarte_Interf/releases/tag/v5.3.0) e a prévia anterior [5.3.1-rc.1](https://github.com/Souzlx/Liarte_Interf/releases/tag/v5.3.1-rc.1) permanecem disponíveis. Os arquivos dessas publicações não são substituídos pela candidata.

## Instalar e atualizar

1. Feche todas as janelas da LIARTE.
2. Execute `LIARTE_Desktop_5.3.1-rc.2_Setup.exe` usando a mesma conta Windows da instalação anterior.
3. Abra a LIARTE pelo atalho criado pelo Setup e confira **5.3.1-rc.2** em **Ajuda**.

A instalação é por usuário. O diretório padrão é `%LOCALAPPDATA%\Programs\LIARTE Desktop`; uma atualização reutiliza o diretório registrado da instalação anterior. Bases, backups e preferências ficam no perfil do usuário, fora da pasta do programa. Relatórios exportados permanecem nos locais escolhidos.

Quem usava somente o portátil pode instalar o Setup na mesma conta e continuar usando o perfil existente. Atalhos antigos para uma pasta portátil continuam abrindo aquela pasta; use o atalho criado pelo novo Setup.

Para continuar com o portátil, extraia **todo o ZIP em uma pasta nova** e abra `LIARTE_Desktop.exe`, mantendo `_internal` ao lado. O ZIP de fontes oferecido pelo GitHub é distinto do portátil compilado.

## Conferir a nova interface

Em **Estoque**, use Panorama, Análise mensal ou Produtos conforme a tarefa. Em **Produtos**, o seletor **Ordenar por** e o botão de direção compartilham a ordem dos cabeçalhos. **Desempenho dos produtos** oferece rankings, maior/menor giro, capital, saldo e cobertura; as escolhas dessa janela são aplicadas ao pressionar **Aplicar**.

Período, ordenação e avisos essenciais continuam visíveis. **Contexto e critérios** revela os detalhes da comparação. Veja as capturas e regras no [guia da interface](GUIA_INTERFACE_MODULAR.md), nas [ordenações de desempenho](DESEMPENHO_PRODUTOS.md) e no [comparador mensal](COMPARADOR_MENSAL_ESTOQUE.md).

## Bases anteriores e remoção

Antes de substituir uma base local válida de Estoque, o aplicativo guarda uma cópia para restauração. A ação **Restaurar** identifica a data de gravação e a referência dos dados e pede confirmação antes da troca. A base atual válida também é preservada ao restaurar outra. A retenção padrão mantém dez cópias válidas recentes.

Essas cópias ficam no perfil Windows e não substituem a guarda do PBIX original ou dos relatórios exportados. Uma atualização normal não exige desinstalar nem apagar o perfil.

Na desinstalação, manter bases, backups, diagnósticos e preferências é a opção padrão. A remoção desses dados exige uma escolha explícita. Na desinstalação silenciosa, o perfil é preservado por padrão; `/PURGEDATA=1` solicita sua exclusão e não deve ser usado para uma atualização normal. Relatórios fora do perfil permanecem intactos.

## Como a entrega é validada

O [workflow do instalador](../.github/workflows/installer.yml) executa a suíte e o autoteste dos executáveis nas quatro versões Python suportadas. O Setup usa o bundle 3.12 verificado, com versão e checksums conferidos. O compilador Inno Setup tem versão fixada, checksum e assinatura de fornecedor verificados pelo workflow.

O ciclo de instalação roda em um perfil descartável do runner Windows e cobre instalação nova, atualização, atalhos, preservação de dados, desinstalação e exclusão explícita do perfil. A instalação anterior desse ensaio é produzida com o pacote e o script da versão **5.3.0**; isso descreve o cenário automatizado, não um ensaio de todas as instalações existentes da empresa.

O Setup da LIARTE não tem assinatura digital de editor. A suíte offline e o runner não substituem a conferência da rede, das políticas de instalação e das configurações de tela do computador de uso. As evidências desta candidata devem ser registradas após a conclusão da execução, sem reutilizar os resultados históricos da RC1 como validação da RC2.
