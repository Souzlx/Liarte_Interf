LIARTE 5.2.0 reúne Importações e Estoque no aplicativo Windows.

- Recupera pausas curtas repetidas do Comex Stat, com contagem regressiva e cancelamento.
- Preserva o último resultado completo quando uma nova consulta falha ou é cancelada.
- Consulta períodos que atravessam anos em faixas anuais, reunindo os dados antes de exibi-los.
- Mantém as exportações Excel, PDF e Power BI, a base de estoque e as preferências locais.

Para atualizar, feche a versão anterior, extraia todo o ZIP em uma pasta nova
e abra `LIARTE_Desktop/LIARTE_Desktop.exe`. Confira **5.2.0** em Ajuda.
O pacote portátil inclui Python e dependências. Atalhos antigos continuam
apontando para a pasta anterior.

O arquivo `SHA256SUMS.txt` permite conferir a integridade do ZIP. O programa
mantém a validação HTTPS do Windows. A API oficial ainda pode exigir pausas
prolongadas; o aplicativo respeita o prazo e mantém o resultado anterior.

A versão promove as correções validadas na RC10. O usuário informou que
consultas, exportações, estoque e preferências funcionaram na verificação
inicial. Os ensaios automatizados e seus limites estão documentados no
repositório; esta entrega contém o pacote portátil, sem instalador Setup.
