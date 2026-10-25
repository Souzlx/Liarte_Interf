Prévia do LIARTE com instalador Windows e restauração de bases anteriores de Estoque.

- Setup por usuário, com atalhos na Área de Trabalho e no menu Iniciar; Python e dependências incluídos.
- Atualização preserva a base local, os backups e as preferências. O instalador aguarda o encerramento do aplicativo.
- Antes de substituir uma base local válida de Estoque, o aplicativo guarda uma cópia para restauração. As dez cópias válidas mais recentes são mantidas.
- A ação **Restaurar** em Estoque permite escolher uma cópia pela data de gravação e pela referência dos dados, com confirmação antes da troca. A base atual válida também é preservada ao restaurar outra.
- Na desinstalação, manter os dados é a opção padrão. A exclusão de bases, backups e preferências depende de escolha explícita; arquivos exportados fora da pasta de dados do aplicativo são preservados.

O Setup é distribuído somente após a suíte automatizada, os autotestes dos quatro executáveis e o ensaio de instalação, atualização e desinstalação no Windows. Esta é uma **prévia 5.3.1-rc.1**; a versão estável 5.3.0 permanece disponível.

Para instalar, feche a LIARTE e execute `LIARTE_Desktop_5.3.1-rc.1_Setup.exe`. Na atualização, use a mesma conta Windows. Confira **5.3.1-rc.1** em Ajuda. Não é necessário instalar Python. O ZIP portátil também está disponível e deve ser extraído por completo em uma pasta nova.

Backups locais guardam a base de Estoque utilizada pelo aplicativo. Não substituem a guarda do PBIX original ou dos relatórios exportados. O arquivo `SHA256SUMS.txt` permite conferir a integridade dos pacotes. O instalador não tem assinatura digital de editor; nenhuma assinatura foi simulada.

Veja o [guia de instalação e restauração](https://github.com/Souzlx/Liarte_Interf/blob/main/docs/INSTALACAO_531_RC1.md) para uso e limites da validação.
