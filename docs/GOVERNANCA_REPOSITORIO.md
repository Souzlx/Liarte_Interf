# Organização e manutenção do GitHub

Este guia descreve o fluxo do repositório e a configuração administrativa proposta em [repository-settings.json](../.github/repository-settings.json). O arquivo declara a política desejada; sua presença não altera configurações do GitHub automaticamente.

## Código e integração

- `main` reúne alterações concluídas. Desenvolvimento ocorre em branches curtas, como `feat/`, `fix/`, `docs/` e `chore/`, com pull request explicando o resultado e a validação.
- O check **tests** executa a suíte da aplicação em todos os PRs e pushes da `main`. O check **repository** confere a estrutura e os links locais da documentação, além de padrões conhecidos de arquivos que não devem ser versionados.
- Os fluxos usam actions fixadas por commit e permissões limitadas. Builds Windows e instaladores são iniciados manualmente; execuções da mesma branch são serializadas sem cancelar uma publicação em andamento.
- Uma branch só pode ser removida quando não tem commits exclusivos em relação à `main` e não sustenta um PR aberto. Releases, tags, evidências e bases canônicas não são arquivos temporários.

A proteção desejada para `main` exige PR, os checks **tests** e **repository** aprovados e atualizados, e conversas resolvidas. Não exige uma segunda pessoa para aprovar o próprio trabalho: o projeto permite manutenção por um único responsável. Force push, exclusão da `main` e bypass administrativo ficam bloqueados nessa política.

Em **29/10/2026**, o proprietário criou a regra pela interface do GitHub. A API confirmou `main` protegida e os checks `tests` e `repository` exigidos para todos, inclusive administradores. As demais opções administrativas ainda precisam de conferência separada.

## Documentação e arquivos

O [README](../README.md) apresenta o produto e os downloads. O [portal](README.md) organiza os guias; [Estado atual](STATUS.md) e [Arquitetura](ARQUITETURA.md) descrevem o código vigente. O [índice histórico](archive/README.md) mantém acesso às versões anteriores sem mudar suas URLs.

`build/`, `dist/`, `instalador/`, ambientes virtuais e perfis locais são gerados, não fazem parte dos fontes. PBIX de trabalho e arquivos de segredos não devem ser adicionados. A base integrada em `src/liarte_core/data/`, exemplos intencionais e evidências históricas têm função própria e foram preservados. As convenções de texto e fim de linha estão em [.editorconfig](../.editorconfig) e [.gitattributes](../.gitattributes).

## Issues e rótulos

Os formulários distinguem problemas e propostas de melhoria; detalhes técnicos são opcionais quando o usuário não os conhece. [SUPPORT.md](../SUPPORT.md) explica como obter ajuda e compartilhar exemplos sem expor dados empresariais.

Use um rótulo de natureza, como `bug`, `enhancement`, `documentation` ou `question`, e uma área quando ajudar: `area: estoque`, `area: importacoes`, `area: interface`, `area: distribuicao` ou `area: ci`. `maintenance` identifica manutenção do repositório. Os nomes convencionais existentes foram preservados; descrições em português explicam seu uso.

## Releases

Downloads ficam em [Releases](https://github.com/Souzlx/Liarte_Interf/releases), com notas, versão e checksums. O canal estável e a prévia são identificados separadamente. Uma reorganização de documentação não substitui binários nem muda tags publicadas.

O workflow de [Windows](../.github/workflows/windows.yml) permite validar os executáveis separadamente. A publicação de prévias e versões estáveis fica centralizada no workflow de [instalador](../.github/workflows/installer.yml), que exige os quatro builds e o ensaio do Setup antes de disponibilizar ZIP, Setup e checksums. A entrega estável também exige a atualização do Setup publicado da RC2, além da versão 5.3.0, em perfil descartável. As [evidências da RC2](EVIDENCIAS_INSTALADOR_531_RC2.json) exemplificam o registro do commit e dos arquivos realmente distribuídos.

## Aplicar a configuração administrativa

A integração usada nesta organização recebeu **HTTP 403 — Resource not accessible by integration** ao tentar alterar About, tópicos e a opção de relato privado de vulnerabilidades. Isso é uma restrição de permissão da integração; não significa que a configuração desejada já esteja ativa.

Em uma máquina de desenvolvimento com Python e GitHub CLI, o administrador pode consultar as diferenças usando sua própria autenticação:

```sh
gh auth status
python tools/configure_repository.py --check
```

O comando padrão é somente leitura. Para aplicar a política revisada, use uma conta/autenticação que tenha permissão administrativa neste repositório:

```sh
python tools/configure_repository.py --apply
```

O utilitário não recebe tokens como argumentos, não altera a visibilidade, não remove branches ou labels e informa se uma seção falhou. Um resultado com pendências ou permissão negada não deve ser registrado como configuração concluída.

As mesmas opções podem ser ajustadas pela interface do GitHub:

| Local | Configuração |
| --- | --- |
| **About**, na página inicial | Descrição, link de releases e tópicos definidos no JSON |
| **Settings → General** | Exclusão automática de branches integradas, sugestão de atualização de PRs e métodos de merge |
| **Settings → General → Features** | Documentação no repositório; Wiki e Projects vazios não são usados |
| **Settings → Branches** | Regra clássica para `main`, com os checks `tests` e `repository` e as restrições acima |
| **Settings → Code security** | Relato privado de vulnerabilidades, quando a permissão do administrador permitir |

Confirme o estado com `--check` depois das alterações. Formulários, documentação e CI são arquivos versionados; About, proteção da branch e demais opções administrativas são configurações externas e têm validação separada.
