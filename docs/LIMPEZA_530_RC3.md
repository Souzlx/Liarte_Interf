# Limpeza da árvore-fonte — 5.3.0-rc.3

Inventário de referência: commit `e5be36410488dbba306a7b4ce49553213a777531`, auditoria de 24/10/2026. Cada arquivo abaixo foi conferido por tamanho e SHA-256 antes da remoção. Os 101 conteúdos correspondiam integralmente ao inventário; nenhum arquivo alterado foi removido.

Foram retirados **101 arquivos, 7.690.304 bytes (7,33 MiB)** do checkout. O histórico Git foi preservado e permite recuperar os arquivos. Não houve reescrita do histórico. A redução do checkout não implica essa mesma economia no pacote portátil, cujo build já usa `src/` e os recursos canônicos.

| Categoria | Arquivos | Bytes |
|---|---:|---:|
| Ativação e configuração de ambiente | 6 | 35.881 |
| Bytecode CPython 3.13 | 30 | 586.052 |
| Cópias Python antigas na raiz | 22 | 213.745 |
| Estado antigo de execução | 4 | 7.759 |
| Launchers de ambiente Python na raiz | 33 | 3.868.450 |
| Cópias extras da base integrada | 3 | 2.973.231 |
| Metadados e catálogo duplicados | 3 | 5.186 |

Foram preservados `src/liarte_core/data/estoque.liarte`, seu JSON de integridade, o catálogo canônico, todos os arquivos de `third_party/`, exemplos, fixtures, ícones e componentes Qt. As licenças Python por versão permanecem separadas porque seus nomes são usados pelo empacotador. Os módulos Python ativos permanecem em `src/liarte_core`, `src/liarte_desktop` e `src/liarte_engine`; as cópias planas não eram os pontos de entrada suportados.

Os quatro comandos Windows continuam na raiz. A retirada de `python.exe`, `pythonw.exe` e `pyvenv.cfg` herdados elimina a colisão do diretório atual com o Python instalado no computador. Para escolher o interpretador explicitamente, use o comando do assistente descrito no [README](../README.md). Essa mudança na árvore-fonte não retira Python dos pacotes portáteis compilados.

Os seis manifestos históricos foram movidos, sem alteração de conteúdo, para [docs/archive/source_rc9](archive/source_rc9/README.md). Eles descrevem pacotes antigos e não verificam a árvore atual. Os novos manifestos de distribuição são gerados no bundle pelo build.

A `.gitignore` passa a cobrir bytecode, ambientes locais, caches, logs e saídas de compilação. Não há regra global para esconder JSONs, bases `.liarte`, ZIPs de exemplo ou binários de teste. A limpeza não inclui backups de ambientes do usuário nem arquivos fora do repositório.

## Arquivos removidos

Os hashes representam o conteúdo anterior à remoção. O campo canônico identifica o recurso mantido, quando aplicável.

| Caminho removido | Bytes | SHA-256 | Fonte/recurso mantido |
|---|---:|---|---|
| `__init__.cpython-313.pyc` | 306 | `3b8dc7e958acefb86cda2ae2eafdb1a4badb3f39136ca07353bc66fc7f45adcf` | — |
| `__init__.py` | 68 | `9718864a44f3bf1e3a9dc6d63be24d6c1703d3ee68232183ea3248cd8a637177` | `src/liarte_core/__init__.py` |
| `__pycache__/__init__.cpython-313.pyc` | 291 | `e9da4f2df7d2530f360c67b28a82c85695870a78ea64685830d41644f0bad28a` | — |
| `__pycache__/catalog.cpython-313.pyc` | 1543 | `2c556d23ebfb8c24260aee4a09dbd004518d91c285aacf616590e9cdbcd1f383` | — |
| `__pycache__/comex.cpython-313.pyc` | 29722 | `e78367136191737820dca11a0f149dfca20e9073829823ff4caaea9fbbb46e6b` | — |
| `__pycache__/comex_access.cpython-313.pyc` | 10835 | `24bc4e93f955794952d2c5884cb71d785e3a266038f8ffa52552c077c4e6e70d` | — |
| `__pycache__/comex_api.cpython-313.pyc` | 29885 | `7ab09e3bdedd1cb1ea511067da41dba186a8a2e86817244044c8e121c1d54c47` | — |
| `__pycache__/comex_gateway_client.cpython-313.pyc` | 18286 | `0c2bfaafbf82d8f839dc9f2de5ba03c06b662d7484e2ed4bd98c32fcd3ae0ae6` | — |
| `__pycache__/comexstat_importacoes.cpython-313.pyc` | 128446 | `c6e4f859c7587c4c7875cd9f1e31d19d6c3a70d6967344fe545679e5057b2421` | — |
| `__pycache__/commercial_names.cpython-313.pyc` | 2175 | `f20b06b12cd26fbc55c845fe849ab4aa08032ae1aa3f2f1690189538284d6db2` | — |
| `__pycache__/demo.cpython-313.pyc` | 4382 | `84e5c3fd3464b1959d3d73e3e5b7561229b374ab11f607616930998e6b2c8130` | — |
| `__pycache__/domain.cpython-313.pyc` | 19585 | `273d71da1fa78d02046f925d9c6a447717de3517d8ae59ff0c6e62b6ef562802` | — |
| `__pycache__/exports.cpython-313.pyc` | 9972 | `58cf11662757b74c1dbe542b0bfd5e0fdefdaaf789aad466fb13693002de85de` | — |
| `__pycache__/inventory.cpython-313.pyc` | 29360 | `a670a55a9b33933470093fe30100336f96ab0ff598e4abed76de884e8ce700ec` | — |
| `__pycache__/inventory_assets.cpython-313.pyc` | 1830 | `402e9a00d90bfb3d13d56fffa07a27c61b0de9b4118e3c954ac47cfe7f347a9f` | — |
| `__pycache__/inventory_export.cpython-313.pyc` | 10404 | `1f66d9e91519f5d90a33ea0a194449f9e0ac6b70d9d4682c0817e9ec59affb68` | — |
| `__pycache__/inventory_io.cpython-313.pyc` | 25482 | `20cfc2427378c119d5bf78e8a8942bbf03c29d828415fa303f920efc7afecd54` | — |
| `__pycache__/inventory_search.cpython-313.pyc` | 5191 | `22de7db12541882974f0c09dde069f4574c95a301c98a7ed96dff5e94e580cd6` | — |
| `__pycache__/liarte_analise.cpython-313.pyc` | 8716 | `fa40fe5be8a75b3052d89d545dca67a3f247397858d936661299e89a804b8372` | — |
| `__pycache__/liarte_dados.cpython-313.pyc` | 28451 | `e3aceb4df8e56c7f938f8f269d5c059f1b8c57c2f597794444783857fc329e87` | — |
| `__pycache__/modules.cpython-313.pyc` | 3949 | `2d77501326a49e72bc9704f8a7c9a0047193307198ad4c244d81feb25fd3a459` | — |
| `__pycache__/numeric.cpython-313.pyc` | 3087 | `31f4b1768f82b0290c8e0eb87ea804752a824c63cf9ba222a3cc461c8147aa82` | — |
| `__pycache__/package_checks.cpython-313.pyc` | 2205 | `bfbec30827ce478eb21b7d360d3d26682c723f8d7d5300de774b80bba837fb51` | — |
| `__pycache__/pdf_importacoes.cpython-313.pyc` | 25238 | `a3cd5399e3359d9fb909b38c54ca8a2d84e310b44d329e6ee600593f55c8e053` | — |
| `__pycache__/powerbi_importacoes.cpython-313.pyc` | 50208 | `6209c2c646ced0af9676a3e2f163aa02365054fe503fb2981aa56de1d413d738` | — |
| `__pycache__/powerbi_semantic.cpython-313.pyc` | 37610 | `759d063c032bd44a71e6303c181aa724a6b894510ab2b8d1d087c17bd40e4ece` | — |
| `__pycache__/powerbi_source.cpython-313.pyc` | 12916 | `88f9fbb2fc12d4b0adbda368ce07217cc882198faff9bc928032727cb48f23a8` | — |
| `__pycache__/powerbi_visuals.cpython-313.pyc` | 29698 | `d852d0db4c4ddfa493da702753e65ae6dbaded4d498aa03679120237dce08bd9` | — |
| `__pycache__/procurement.cpython-313.pyc` | 13293 | `2a1ef4f2ff8a9b6ff5a8701fd813bf8551b8a963a8e47a267ddd80d61e9c21fe` | — |
| `__pycache__/query.cpython-313.pyc` | 17748 | `786ffb6d21200ef77b29a411fcae9ae2c208d950ed8b59eba0e846fdf01aa30d` | — |
| `activate` | 2378 | `6e459bd0fc6faf17956289af5659e196c23e71f3c5c3f98c5cce0d54013856c5` | — |
| `activate.bat` | 1113 | `63b5a5785a8508a0f4533c70d3fdb6143108de9ffcfa571fe1b34529c84abc47` | — |
| `activate.fish` | 2372 | `c54db401d721e2779ce605cae9b9bff18184d154529601f644581275d26d99ad` | — |
| `Activate.ps1` | 29029 | `a39a900d74321339695a4efca4813d85a7c7b9561a8f88644a2fd9ea49000f82` | — |
| `ambiente-verificado.json` | 131 | `438d661b78f2ee40d800837ce83738dd818cfc1ffc955af9f93622150fed1a5f` | — |
| `apsw.exe` | 108422 | `bb360ea7f5524b66b6b6b71c23dd4ee71852df815be325b992c34ef5bd2986aa` | — |
| `Base_Estoque_LIARTE_2026-10-21.liarte` | 991077 | `29ca194efa7e713ae54a724ec0924d95b371cb5af5785bfcaeaaeaec515590c8` | `src/liarte_core/data/estoque.liarte` |
| `catalog.json` | 4602 | `a5b77abbdfc95773074942aa4d2ab2b680a2d6f6bdc7fe2d83aa5a4fcd66d2c8` | `src/liarte_core/catalog.json` |
| `catalog.py` | 904 | `7369665b2d7a1f9e7a00828871c99b6925656f9bba3bc5b4241b6b5cfd730917` | `src/liarte_core/catalog.py` |
| `comex.py` | 23713 | `6975d46c36f93f6a40865a1878a0ad94e09144cdd534038de699525846f0108f` | `src/liarte_core/comex.py` |
| `comex_api.py` | 22700 | `a5e91e7db38c968af3f30a4bec9e2efd62600b7471ce30958219c7aeeaa0ebaf` | `src/liarte_core/comex_api.py` |
| `comex_automatic.py` | 10088 | `2df8880c4b083a8d3df2161205e905df3c1cb4f54346f46c66e6b5f7bdabbf30` | `src/liarte_core/comex_automatic.py` |
| `comex_central.py` | 27349 | `32c33b25cb8c930502c647d26e0d001c292c8fe2c2ea243073782d69d18449e2` | `src/liarte_core/comex_central.py` |
| `comex_managed.py` | 2474 | `e945b9c7f1a2ef20368b57498572f608f18cd83e948490d4d8a9a4199d2e5708` | `src/liarte_core/comex_managed.py` |
| `comex_open_data.py` | 32690 | `2d3f91e426e46000bb605f574e279048123bd9c6ae645f140b27f2329c802c05` | `src/liarte_core/comex_open_data.py` |
| `comex_source.py` | 3851 | `0daf047e4ba3fcba626cc80f96f7fa8f5fef8011634d660a1fc76069a8d43ccb` | `src/liarte_core/comex_source.py` |
| `data/estoque.json` | 292 | `5e1720f57e47431dc008a238b1d96b1cc049d392cbd4ce9084fe417e47b12568` | `src/liarte_core/data/estoque.json` |
| `data/estoque.liarte` | 991077 | `29ca194efa7e713ae54a724ec0924d95b371cb5af5785bfcaeaaeaec515590c8` | `src/liarte_core/data/estoque.liarte` |
| `deactivate.bat` | 393 | `fb53ed45866fee40f01c907c1f67555a399f98361722d89120d05a2580e9e563` | — |
| `demo.py` | 2927 | `b8294992fc4c76f0fc843456b9ddbe87ef839ca152f002676d77f8099516cac3` | `src/liarte_core/demo.py` |
| `domain.py` | 9516 | `f4f193ef28afa8b30a43a7f9e74b0bea50dbf9a5dbd679960067b2b1021d9004` | `src/liarte_core/domain.py` |
| `estoque.json` | 292 | `5e1720f57e47431dc008a238b1d96b1cc049d392cbd4ce9084fe417e47b12568` | `src/liarte_core/data/estoque.json` |
| `estoque.liarte` | 991077 | `29ca194efa7e713ae54a724ec0924d95b371cb5af5785bfcaeaaeaec515590c8` | `src/liarte_core/data/estoque.liarte` |
| `exports.py` | 7130 | `855352f4f901cf1fbd0436512038501dd5dd3e1bffc30b826e6864beca5d22c1` | `src/liarte_core/exports.py` |
| `f2py.exe` | 108426 | `120c9324d2c289aede2116d25d40249b465054103cc50a17c3af3df3b4adcbee` | — |
| `inventory.py` | 17108 | `2b0ed83d23874d7c2a9fabbff6d4a656d53328ae6c36660c1386d399733afe98` | `src/liarte_core/inventory.py` |
| `inventory_assets.py` | 963 | `23ca657e732231bec397613284ab1a05acd35d754ec4a12d68c00007b84b1659` | `src/liarte_core/inventory_assets.py` |
| `inventory_export.py` | 7609 | `27bbcacd49a0f9212bac8181958a3e8357016d6c184dc0d78f6ad8e67547713d` | `src/liarte_core/inventory_export.py` |
| `inventory_io.py` | 16575 | `332be91009b431db1e2c1c1cb47381dd319cca32ecfc45b7210cd548c5ef2b4b` | `src/liarte_core/inventory_io.py` |
| `inventory_search.py` | 2648 | `49ae69c48861724af4191b3e37af35165aeeacce5020e47d465765bb3eb5b4eb` | `src/liarte_core/inventory_search.py` |
| `modules.py` | 2214 | `00deaae368ff423bfcfb81129ad2008b4a3a8b14994f4121555ad020437a0b95` | `src/liarte_core/modules.py` |
| `normalizer.exe` | 108443 | `c243bbded0f309b573adee04d67c7a75f85979bdc02d650b320885f3f8c27b01` | — |
| `numpy-config.exe` | 108426 | `ce4be4f7afa9825233db309a06601f59723ed3d4f1b359fc5fcb05bfe8abe883` | — |
| `package_checks.py` | 1977 | `fd9677ab5a4df24bdd5cb0f6b95ae276c96daee0d3ba1ea48534247ef951c4c1` | `src/liarte_core/package_checks.py` |
| `pdf_importacoes.cpython-313.pyc` | 25238 | `a3cd5399e3359d9fb909b38c54ca8a2d84e310b44d329e6ee600593f55c8e053` | — |
| `pip.exe` | 108431 | `9c9d47bb23b030735c807a0bbd3c9a16c23196047d2d269ac5980b65c9a0a296` | — |
| `pip3.13.exe` | 108431 | `9c9d47bb23b030735c807a0bbd3c9a16c23196047d2d269ac5980b65c9a0a296` | — |
| `pip3.exe` | 108431 | `9c9d47bb23b030735c807a0bbd3c9a16c23196047d2d269ac5980b65c9a0a296` | — |
| `preparacao-desktop.log` | 6954 | `accc49e8df75a8ee10968821a0c15df2ae06f5f7a325f71d45cae6b01c0f1c38` | — |
| `preparacao.lock` | 1 | `6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b` | — |
| `procurement.py` | 6387 | `8b9be10e252101511aefa73c0e5670b14738959e195172963c9f9a8bae900278` | `src/liarte_core/procurement.py` |
| `pyside6-assistant.exe` | 108446 | `f22243be7bbfc57f6eb80e91053b76e5e4641f4932ca0ea564f9ab12c8c9c206` | — |
| `pyside6-balsam.exe` | 108440 | `33e2ce608e191a75e645a09fd049eb701892e4061475557b5d75429d092af763` | — |
| `pyside6-balsamui.exe` | 108444 | `16b90767f8e54dbf6b714c161addab5d18f18481edaeba9effd38a56c88d020d` | — |
| `pyside6-deploy.exe` | 108440 | `61320c63838b1cda69d6776a2159bf11501845bc45008cf4378edfe0ab9bb231` | — |
| `pyside6-designer.exe` | 108444 | `0eb3ef3971298a262ffd6e187d3e3f9256562bf05270ed6a9cf8e46948849ffb` | — |
| `pyside6-genpyi.exe` | 108440 | `e56fbe5f97ec88fba04ed05e82b0400abcfbe466daee5fca2b47dbf88d644c18` | — |
| `pyside6-linguist.exe` | 108444 | `7b59e18e23d66d1492300a900b932091951c5ad40c0e8d3cf581299ead24f4a1` | — |
| `pyside6-lrelease.exe` | 108444 | `b9b4d17e155bebe1be9e2f11d190cdc0c9463e013c14f2c90da676b9df445912` | — |
| `pyside6-lupdate.exe` | 108442 | `80a60d19284a1511c24fa833ca5d0a2e949b71f5d0e1da11714b3212887cdcce` | — |
| `pyside6-metaobjectdump.exe` | 108456 | `6d408c3221fa00b4462261321d531c29a73cee4da5bad6b7112101672e4d1b03` | — |
| `pyside6-project.exe` | 108442 | `c969874b5ff6c0d707cc355d66c52112a3790f3b2ab5009a2ed0e8e80eb6234f` | — |
| `pyside6-qml.exe` | 108434 | `686621dbc5ce749a880f1379f3940f936326b225e4e3103b62efbdcb123757f1` | — |
| `pyside6-qmlcachegen.exe` | 108450 | `c23f15dbbaa0fd25b161277e9799ebeb1df1880bb20ee7eb91137397129a9d24` | — |
| `pyside6-qmlformat.exe` | 108446 | `42dbbe97b158dd8d13b102dc05aeca9093f056c638ae0ac05df8b317458034bc` | — |
| `pyside6-qmlimportscanner.exe` | 108460 | `7bf7da897fcfb1520e2a2263ac4f64d407a00bde239a463d62cd92044685153e` | — |
| `pyside6-qmllint.exe` | 108442 | `b54fc93afabf8d4fee01f629ae6e19e2443747936748d5f47ef12895ae880c54` | — |
| `pyside6-qmlls.exe` | 108438 | `0edaec5a895c307c8f2589b8a45b5f6b3e46a12fc1663331b8accc113ee13f8e` | — |
| `pyside6-qmltyperegistrar.exe` | 108460 | `837fc21bcdd22febd0a7efa43a29dbc4350c2fda3fc11bb560a0cddc12f8dbd5` | — |
| `pyside6-qsb.exe` | 108434 | `334c598904ab999d722e31a1a64b990d7b47aa644258f05ccbf4ca9eb557835b` | — |
| `pyside6-qtpy2cpp.exe` | 108444 | `51a6691ce6f8963a1af5a7baa80782a128aa80b5a781f92db6e615a72db5488f` | — |
| `pyside6-rcc.exe` | 108434 | `12b10123e9628aac314c1efb8c5204fed8e123a9d53a71de88fe4e849775d54b` | — |
| `pyside6-svgtoqml.exe` | 108444 | `7c7fb4e7e0c884cc8763c84b999a2f15b432a147e4ad8246c95261eb31bcd001` | — |
| `pyside6-uic.exe` | 108434 | `65bb8120bb255c94f534bb81c230fa72c50459259c837ffb75ef9495837b4631` | — |
| `python.exe` | 255200 | `b70275ad94210fce7548761143be5e177769721045e287bb6c80aac3f928c65b` | — |
| `pythonw.exe` | 251616 | `a52e8eb87e3e930ca66b5861326f110564830dc03b83f2aa76d5d5d7aa6c19de` | — |
| `pyvenv.cfg` | 596 | `9bccdc571221528023598316b6de8df4167f5c4244a58f9ee810c42960dd2b1a` | — |
| `query.py` | 11901 | `0e6c9a9729d6547adc7aac559c525203a7db604b9b6c57f5588700c0bd162136` | `src/liarte_core/query.py` |
| `secure_http.py` | 2953 | `648407b30ba985bdeedc13cdb299ea7afc6e9d7372904e722fd130c5b1a4f3cb` | `src/liarte_engine/secure_http.py` |
| `validacao-qt.json` | 673 | `bb4207fe95aa0a08a122637378a451ac84946d092105490b09ebc61104dfa209` | — |
| `waitress-serve.exe` | 108422 | `27956906dd7e70069c936a1d6006d7afed6ea670af6fa1361949e102bac6f8ee` | — |

## Validação

A conferência local desta limpeza verificou a identidade dos 101 arquivos removidos e a preservação byte a byte dos seis manifestos movidos. Testes funcionais, validação dos comandos e compilação Windows devem ser avaliados pelas evidências da entrega completa RC3; o inventário e os hashes, isoladamente, não equivalem à homologação do aplicativo.
