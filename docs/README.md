# Documentação da LIARTE

Comece pelo caminho correspondente à sua tarefa. A versão estável atual é **5.3.1**, com Setup, ZIP portátil e checksums. A RC2 e a 5.3.0 permanecem disponíveis como entregas históricas. O [estado do projeto](STATUS.md) registra a referência atual, e as [releases no GitHub](https://github.com/Souzlx/Liarte_Interf/releases) oferecem os pacotes compilados.

[Voltar ao repositório](../README.md) · [Obter suporte](../SUPPORT.md) · [Contribuir](../CONTRIBUTING.md)

## Instalar e usar

| Preciso de… | Documento |
| --- | --- |
| Instalar, atualizar ou usar o portátil | [Instalação e atualização da 5.3.1](INSTALACAO_531.md) |
| Conhecer as mudanças da entrega atual | [Notas da 5.3.1](RELEASE_5.3.1.md) |
| Encontrar filtros, gráficos e tabelas | [Interface organizada por tarefa](GUIA_INTERFACE_MODULAR.md) |
| Consultar instruções distribuídas com o aplicativo | [LEIA_PRIMEIRO.txt](../LEIA_PRIMEIRO.txt) |
| Relatar um problema ou tirar uma dúvida | [Suporte](../SUPPORT.md) |

O Setup e o ZIP portátil incluem o runtime. O código-fonte do GitHub é destinado ao desenvolvimento; não substitui o pacote compilado.

## Estoque e produtos

| Tema | Referência e alcance |
| --- | --- |
| Visão geral, recorte e navegação | [Guia da interface](GUIA_INTERFACE_MODULAR.md#estoque) |
| Desempenho, giro, cobertura e ordenações | [Desempenho dos produtos](DESEMPENHO_PRODUTOS.md) |
| Alertas de estoque e critérios configuráveis | [Alertas de estoque](ALERTAS_ESTOQUE.md) |
| Diferenças entre dois fechamentos | [Comparador mensal](COMPARADOR_MENSAL_ESTOQUE.md) |
| Fechamentos, vendas e meses incompletos | [Análise mensal](ANALISE_MENSAL_530_RC2.md) — documento versionado da introdução do recurso |
| Base local e definições do estoque | [Estoque 5.2.0](ESTOQUE_520.md) — referência de origem; a interface atual está no guia por tarefa |
| Modelo e medidas dos PBIX examinados | [Análise do BI e experiência](ANALISE_BI_E_EXPERIENCIA.md) |
| Bases anteriores e restauração | [Guia da 5.3.1](INSTALACAO_531.md#bases-anteriores-e-remoção) |

Saldo atual e fechamentos históricos têm datas e escopos diferentes. Giro da fonte, cobertura estimada, recência de venda e idade física dos lotes não são equivalentes. As regras de cada guia acompanham os indicadores apresentados.

## Importações, mercado e documentos

| Tema | Onde consultar |
| --- | --- |
| Consulta, período, filtros, origens e registros | [Guia da interface](GUIA_INTERFACE_MODULAR.md#importações-e-mercado) |
| Unidade, moeda, preço médio e leitura dos gráficos | [Indicadores e gráficos](GUIA_INTERFACE_MODULAR.md#ler-os-gráficos-e-indicadores) |
| Excel, PDF e escopo das exportações | [Instruções do aplicativo](../LEIA_PRIMEIRO.txt) |
| Abrir e conferir o projeto Power BI gerado | [Guia Power BI](POWERBI_USO_RC7.md) — mantém as notas da RC7 em que foi escrito |
| Cliente direto e tratamento de HTTP 429 | [Arquitetura atual](ARQUITETURA.md), [estado do projeto](STATUS.md) e [suporte](../SUPPORT.md) |

Os documentos da série 5.2.0 sobre central, acesso automático e clientes anteriores registram etapas distintas da evolução. Para entender o comportamento atual da consulta, consulte primeiro a arquitetura e o estado atuais; os fluxos antigos não devem ser aplicados como configuração obrigatória.

## Desenvolver e manter

| Tarefa | Documento |
| --- | --- |
| Preparar o clone, editar e abrir a aplicação | [Desenvolvimento local no Windows](DESENVOLVIMENTO_LOCAL_WINDOWS.md) |
| Enviar uma alteração e explicar sua validação | [Contribuir](../CONTRIBUTING.md) |
| Entender componentes, dados e tarefas | [Arquitetura](ARQUITETURA.md) |
| Conferir a versão e o estado da entrega | [Estado do projeto](STATUS.md) |
| Retomar o contexto de desenvolvimento | [Continuidade](CONTINUIDADE_LOCAL.md) |
| Testar, compilar e publicar o instalador | [Fluxo da entrega estável](INSTALACAO_531.md#validação-da-distribuição) |
| Conferir termos dos componentes distribuídos | [Licenças e distribuição](LICENCAS.md) |
| Manter branches, CI, issues e configurações do GitHub | [Organização do repositório](GOVERNANCA_REPOSITORIO.md) |

Os testes comuns usam dados sintéticos. O ensaio de instalação/desinstalação foi feito para o perfil descartável do CI; seu guia descreve os limites desse cenário. Dados empresariais, credenciais e perfis de uso não pertencem às contribuições.

## Releases e evidências

As evidências são identificadas por versão e commit. Um resultado antigo não valida automaticamente fontes ou pacotes posteriores.

| Entrega | Uso e notas | Evidências |
| --- | --- | --- |
| **5.3.1 — estável atual** | [Release](https://github.com/Souzlx/Liarte_Interf/releases/tag/v5.3.1) · [Notas](RELEASE_5.3.1.md) · [Instalação](INSTALACAO_531.md) | [Publicação e downloads](EVIDENCIAS_INSTALADOR_531.json) · [Matriz Windows](VALIDACAO_WINDOWS_531.json) · [Ciclo do Setup](AUTOTESTE_INSTALADOR_531.json) |
| 5.3.1-rc.2 — prévia histórica | [Release](https://github.com/Souzlx/Liarte_Interf/releases/tag/v5.3.1-rc.2) · [Notas](RELEASE_5.3.1-rc.2.md) · [Instalação](INSTALACAO_531_RC2.md) | [Publicação e downloads](EVIDENCIAS_INSTALADOR_531_RC2.json) · [Matriz Windows](VALIDACAO_WINDOWS_531_RC2.json) · [Ciclo do Setup](AUTOTESTE_INSTALADOR_531_RC2.json) |
| 5.3.0 — estável anterior | [Release](https://github.com/Souzlx/Liarte_Interf/releases/tag/v5.3.0) · [Notas](RELEASE_5.3.0.md) | [Publicação](EVIDENCIAS_RELEASE_530.json) · [Matriz Windows](VALIDACAO_WINDOWS_530.json) |
| 5.3.1-rc.1 — prévia anterior | [Release](https://github.com/Souzlx/Liarte_Interf/releases/tag/v5.3.1-rc.1) · [Notas](RELEASE_5.3.1-rc.1.md) · [Instalação](INSTALACAO_531_RC1.md) | [Publicação](EVIDENCIAS_INSTALADOR_531_RC1.json) · [Matriz Windows](VALIDACAO_WINDOWS_531_RC1.json) · [Ciclo do Setup](AUTOTESTE_INSTALADOR_531_RC1.json) |
| 5.2.0 — estável anterior | [Release](https://github.com/Souzlx/Liarte_Interf/releases/tag/v5.2.0) · [Notas](RELEASE_5.2.0.md) | [Validação](VALIDACAO_ESTAVEL_520_2026-10-23.md) |

A 5.3.1 foi publicada após 1.070 testes Linux, quatro builds Windows com 1.069 testes aprovados e um skip POSIX em cada um, autotestes dos executáveis e ciclo real do Setup. As atualizações a partir da 5.3.0 e do Setup publicado da RC2 preservaram diretório, bases, backups, preferências e relatórios no ensaio descartável. Os 18 testes de organização do repositório também passaram. Os downloads publicados foram conferidos separadamente por SHA-256, CRC e manifesto interno; o relatório da publicação registra o commit exato. A aparência no monitor, a rede e as políticas da instalação de uso continuam sendo conferências do ambiente do usuário.

## Histórico e referências preservadas

Os caminhos dos documentos anteriores foram mantidos para preservar links, evidências e contexto. A presença de um documento na pasta `docs/` não o torna o procedimento atual de instalação ou consulta.

O [índice histórico](archive/README.md) agrupa as entregas, estudos e registros originais.

- **Entregas e revisões antigas:** arquivos `RELEASE_*`, `INSTALACAO_RC*`, `REVISAO_*`, `EVIDENCIAS_*`, `PRESERVACAO_*` e `VALIDACAO_*` identificam suas próprias versões ou execuções. Consulte-os quando precisar reconstruir uma mudança específica.
- **Auditoria e limpeza da 5.3.0:** [correções](CORRECOES_AUDITORIA_530_RC3.md) e [limpeza](LIMPEZA_530_RC3.md).
- **Evolução do acesso ao Comex:** [cliente RC9](NOVO_CLIENTE_API_520_RC9.md) e [correção do HTTP 429 RC10](CORRECAO_HTTP_429_RC10.md). São registros versionados; detalhes atuais estão na arquitetura e no código.
- **Fontes recebidos na RC9:** [arquivo de manifestos originais](archive/source_rc9/README.md). Esses manifestos descrevem a entrega recebida, não a árvore atual.
- **Capturas:** `images/` reúne imagens usadas pelos guias atuais. Imagens na raiz e diretórios `preview_*`/`validacao_*` preservam a referência das revisões em que foram produzidas.

Para navegar pelos demais arquivos, use a [pasta de documentação no GitHub](https://github.com/Souzlx/Liarte_Interf/tree/main/docs) ou a busca do repositório.
