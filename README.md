# GeoWorld

Pipeline Python + globo web estático para dados geológicos. Este é o **primeiro recorte** do projeto, com duas camadas de assunto:

- **World Geology**: unidades geológicas (litologia), zonas tectônicas ranqueadas por momento sísmico, vulcões e hotspots.
- **World Rocks**: amostras de rocha (máficas e ultramáficas), com filtros por classe, nome da rocha e origem da coordenada.

O pipeline lê as fontes, normaliza, liga as amostras duplicadas entre fontes pelo campo `dup_group` (nunca apaga nenhuma) e exporta GeoJSON e PMTiles. O globo (MapLibre GL) lê esses arquivos de `web/data/`.

> Estado atual: as fontes reais do primeiro recorte foram **baixadas em 2026-11-03**, o build real roda de ponta a ponta e os PMTiles saem pelo fallback do GDAL (veja "PMTiles sem tippecanoe"); o globo foi verificado no navegador com esses dados (round 2). Os testes unitários usam apenas dados sintéticos; um teste de integração opcional usa os arquivos reais quando eles existem em `data/raw/`.

## Estrutura

| Pasta | Conteúdo |
|---|---|
| `pipeline/` | Pipeline Python (`python -m pipeline.build`): leitura das fontes, junção, deduplicação, geocodificação, exportação |
| `data/` | `data/curated/` (tabelas curadas à mão: mapeamento de rochas, hotspots), `data/raw/` (downloads, ignorado pelo git), `data/out/` (saída do pipeline, ignorada pelo git: pode ser grande e conter dados de terceiros) |
| `web/` | Globo estático: `index.html`, `js/`, `css/`, `vendor/` (MapLibre e PMTiles copiados do npm), `tests/` (testes Node), `data/` (dados publicados, ignorado pelo git) |
| `tests/` | Testes Python (pytest), fixtures e o teste de fumaça de ponta a ponta em `tests/e2e/` |
| `docs/` | Especificação e plano de implementação (`docs/superpowers/`) |

## Instalação

```
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt     # Windows
npm install
node scripts/vendor.mjs                                     # copia maplibre-gl e pmtiles para web/vendor/
```

## Rodar o pipeline

```
.venv/Scripts/python -m pipeline.build --raw data/raw --out data/out
```

- As fontes vêm de `pipeline/realsources.py` (`registry()`): GVP, USGS + PB2002, GLiM e um registro por CSV do GEOROC, lidos de `data/raw/` (veja "Fontes de dados"). `pipeline.build.SOURCES` (padrão `None`) substitui esse registro quando é uma lista (os testes usam isso).
- O cache de cada fonte depende só do hash do arquivo em `raw_file`. Mudanças em `data/raw/pb2002/boundaries.json` (lido junto com o catálogo USGS) ou em `data/curated/rock_mapping_v2.csv` **não** invalidam o cache: rode com `--force`.
- Downloads: não há código de download. Os arquivos foram baixados à mão e registrados (hash SHA-256, URL, licença) em `data/raw/manifest.json` com `scripts/register_manifest.py` (sem rede). O campo `file` do manifesto guarda só o nome do arquivo (sem a subpasta) e `downloaded_at` é a hora do registro, não a do download.
- `--allow-network`: deixa rodar as fontes marcadas com `needs_network` (por exemplo, a geocodificação). **Não existe código de download**: os arquivos brutos são colocados à mão em `data/raw/`, e a flag nunca os obtém: com ela, um arquivo bruto ausente é erro, como em qualquer fonte local. Sem a flag, as fontes `needs_network` ficam como `skipped_network` (sem ler o arquivo).
- `--force`: reprocessa todas as fontes, ignorando o cache.
- `--tippecanoe CAMINHO`: caminho do tippecanoe (padrão: o do PATH; `--tippecanoe ""` = sem tippecanoe). Sem ele, os PMTiles não são gerados. A saída `.pmtiles` exige um tippecanoe recente (≥ 2.17, não verificado aqui); versão mais antiga ou ilegível gera um aviso.
- `--keep-intermediate PASTA`: guarda na pasta os GeoJSON de entrada do tippecanoe (`geo_units.geojson`, `samples.geojson`), mesmo sem tippecanoe, para gerar os PMTiles à mão.
- O resumo mostra, por fonte, as contagens do normalizador (por exemplo `dropped_no_coords`), inclusive para fontes reaproveitadas do cache.

### PMTiles sem tippecanoe (fallback GDAL)

Sem tippecanoe (`--tippecanoe ""` ou binário ausente), `export_web` gera `samples.pmtiles` e `geo_units.pmtiles` com o GDAL 3.12 embutido no pyogrio (driver `PMTiles`, que passa por MVT/MBTiles; nenhuma instalação extra). A camada tem o mesmo nome do arquivo e as mesmas propriedades do caminho tippecanoe (`unit_lith_class`, `sample_count`). O build emite o aviso "PMTiles gerados com GDAL; sem agregação de densidade em zoom baixo; tippecanoe recomendado". Medido nos dados reais (93 220 unidades, 117 761 amostras):

- `samples.pmtiles`: zoom 1–8, ~10 MB, ~150 s. Em zoom 0 o tile único estoura o limite de 500 kB do GDAL (`MAX_SIZE`) e 40% das amostras sumiam, por isso o mínimo é 1; mesmo em zoom 1 o GDAL reduz a resolução das coordenadas, sem descartar amostras (todas as 117 761 estão presentes). Não há agregação por densidade: o heatmap da web (zoom < 8) é desenhado com todos os pontos.
- `geo_units.pmtiles`: zoom 0–6, ~23 MB, ~100 s. O GDAL simplifica e descarta polígonos menores que um pixel do tile: no zoom 0 restam ~21 mil de 93 mil unidades, no zoom 2 ~58 mil, no zoom 4 ~87 mil e no zoom 6 todas. Acima do zoom 6 o MapLibre amplia o tile do zoom 6 (borda grosseira, ~150 m por unidade de tile; a fonte GLiM tem escala ~1:3,75 milhões, então não há detalhe real a perder).

### tippecanoe no Windows (WSL)

Um Python do Windows **não consegue** executar um tippecanoe instalado dentro do WSL via `--tippecanoe`. Há dois caminhos:

1. Rodar o pipeline inteiro dentro do WSL (Python, `.venv` e tippecanoe no Linux).
2. Rodar o pipeline no Windows com `--keep-intermediate data/out/tiles_in` e depois, no WSL, gerar os PMTiles com as mesmas flags que o pipeline usaria:

```
tippecanoe -o geo_units.pmtiles -zg --coalesce-densest-as-needed --extend-zooms-if-still-dropping -l geo_units data/out/tiles_in/geo_units.geojson
tippecanoe -o samples.pmtiles -zg -r1 --drop-densest-as-needed --extend-zooms-if-still-dropping -l samples data/out/tiles_in/samples.geojson
```

## Publicar os dados no globo

Copie a saída do pipeline para `web/data/`:

```
data/out/*.geojson   ->  web/data/
data/out/*.pmtiles   ->  web/data/
data/out/sources.json -> web/data/
```

Arquivos esperados pelo globo: `volcanoes.geojson`, `tectonic_zones.geojson`, `sources.json`, `geo_units.pmtiles`, `samples.pmtiles`. Se algum faltar, a camada correspondente mostra um aviso no painel e o resto do globo continua funcionando. `web/data/` é ignorado pelo git; decida a forma de publicação (veja os limites abaixo) antes de versionar dados.

## Rodar o globo localmente

```
npm run serve
```

Abre um servidor estático **somente em loopback** (`http://127.0.0.1:8766/`; `PORT=1234 npm run serve` muda a porta) servindo `web/`. Ele suporta requisições HTTP Range, que os PMTiles exigem. Qualquer outro servidor ou hospedagem **precisa** suportar Range (o GitHub Pages suporta); o `python -m http.server` **não** serve, porque responde sempre o arquivo inteiro.

O carregamento de PMTiles gerados pelo GDAL foi verificado no navegador com os dados reais (veja "Segundo build"); os PMTiles do tippecanoe não foram testados aqui. O estado (posição, camadas, filtros) fica no hash da URL.

## Testes

```
.venv/Scripts/python -m pytest -q -W error     # pipeline (Python)
npm run test:web                               # = node --test web/tests (módulos puros e validação do estilo)
npm run test:e2e                               # = playwright test (teste de fumaça no navegador)
```

- O e2e usa o **Microsoft Edge** já instalado (`channel: 'msedge'`); com `GEOWORLD_BROWSER=chrome` usa o Chrome. Ele **não baixa navegador**: não rode `npx playwright install`.
- O e2e sobe esse mesmo servidor estático em `127.0.0.1:8767` (porta diferente da de `npm run serve`), copia dados **sintéticos** de `tests/e2e/data/` para `web/data/` e remove só o que copiou ao terminar. Se `web/data/` já tiver esses arquivos, ele aborta para não sobrescrevê-los.
- Se houver dados **reais** em `web/data/` (por exemplo, depois de copiar a saída do pipeline para ver o globo), o e2e aborta de propósito para não apagá-los: mova esses arquivos para outra pasta antes de rodar o e2e.
- `window.geoworldMap` (usado pelo e2e) só é exposto quando o host é `127.0.0.1` ou `localhost`.
- `web/tests/static-server.test.js` testa o servidor estático (200, 206, 416, HEAD, bloqueio de `..`, leitura por duas faixas no estilo PMTiles e uma faixa num arquivo de ~20 MB; o servidor lê só a faixa pedida, em streaming).
- O teste de estilo (`web/tests/style-validate.test.js`) valida as camadas de `buildLayers()` com `@maplibre/maplibre-gl-style-spec`, com controles negativos que provam que o validador rejeita estilos inválidos.
- Não existem PMTiles nos testes (não há tippecanoe aqui): o e2e verifica justamente que a ausência deles mostra o aviso no painel sem quebrar o resto.

## Fontes de dados

Todos os arquivos abaixo foram baixados em **2026-11-03** para `data/raw/` (fora do controle de versão) e registrados em `data/raw/manifest.json` (URL, SHA-256, licença).

| Fonte | Uso | Arquivo / versão | Licença / situação |
|---|---|---|---|
| GVP (Smithsonian, Global Volcanism Program) | vulcões | `gvp/holocene_volcanoes.geojson` (2,4 MB; WFS `GVP-VOTW:Smithsonian_VOTW_Holocene_Volcanoes`, 1214 vulcões holocênicos) | Termos de uso próprios do GVP (volcano.si.edu); citação obrigatória |
| PB2002 (Bird 2003, GeoJSON de fraxen/tectonicplates) | limites de placas | `pb2002/boundaries.json` (0,2 MB; 241 segmentos, 182 códigos `Name`) | Open Data Commons Attribution 1.0 (`pb2002/LICENSE.md`) |
| Catálogo USGS ComCat (FDSN) | sismos M ≥ 6, 1900-01-01 a 2026-11-03 | `usgs/m6_1900_2026-11-03.csv` (2,5 MB; 14549 eventos) | USGS: domínio público (verificar termos) |
| GLiM (Hartmann & Moosdorf 2012) | unidades litológicas | `glim/LiMW_GIS_2015.gdb.zip` (1,14 GB; camada `GLiM_export`, 1.235.259 polígonos, Eckert IV) | Licença **NÃO declarada** na fonte: uso local; não publicar sem confirmar. A página oficial (`source_url`) foi **verificada** em 2026-11-03: lista o link do Dropbox, ~1,2 milhão de polígonos e escala ~1:3.750.000, sem texto de licença. `glim_extracted/` (1,2 GB) é uma extração **não usada** (o pipeline lê direto do zip) e pode ser apagada. Plano B: WMS da CGMW |
| GEOROC 2.0, conjunto "Rocks" (DOI 10.25625/2JETOA, v15, 2026-09) | amostras de rocha | 35 CSVs `georoc/2026-09-2JETOA_*.csv` (176 MB no total; um por nome de rocha máfica/ultramáfica; codificação cp1252) | CC BY-SA 4.0; citar o conjunto de dados e as referências originais |
| PetDB/EarthChem | amostras de rocha | **Não baixado** (portal interativo) | — |
| CGMW 1:50M (WMS) | plano B para unidades geológicas | Não usado | Termos para uso em site público a confirmar |
| Macrostrat | complemento | Não usado | CC-BY 4.0, cobertura parcial |
| Hotspots de plumas mantélicas | hotspots | **Falta**: nenhuma lista citável encontrada (o código exige `reference` por linha em `data/curated/hotspots.csv`) | — |

### Regras de leitura das fontes reais (`pipeline/realsources.py`)

- **GVP**: propriedades `Volcano_Name`, `Country`, `Primary_Volcano_Type`, `Last_Eruption_Year` (inteiro, negativo = antes da era comum; vira texto, ex. `-8300`; nulo continua nulo), `Latitude`, `Longitude`. As coordenadas vêm das propriedades `Latitude`/`Longitude`.
- **Zonas tectônicas**: os segmentos do PB2002 são dissolvidos por `Name` (código do par de placas, ex. `PA-NA`), uma (Multi)LineString por código; o nome da zona vem de `pb2002/plates.json`: `<placa A> – <placa B> (<código Name>)`, por exemplo `Nazca – South America (NZ\SA)`; placa sem nome conhecido (ou com nomes conflitantes) aparece com o código bruto, nunca com nome inventado. Do catálogo USGS entram só magnitudes de momento (família Mw). `rank_zones` com `top_n=30` e `buffer_km=250` (`pipeline.tectonics.DEFAULT_BUFFER_KM`): epicentros de megathrusts ficam para dentro do continente em relação à linha da fossa (Chile 1960 a 109 km, Tohoku 2011 a 137 km, Alasca 1964 a 196 km). Com 250 km, **94,1%** do momento Mw é atribuído a algum segmento (11768 sismos atribuídos, 1383 não atribuídos de 13151; com 100 km eram 42%).
- **GLiM**: lido direto do zip, com filtro `xx IN ('vb','pb')` aplicado pelo GDAL (cerca de 93 mil polígonos). `unit_id` = `glim:fid:<FID do arquivo>` (o campo `IDENTITY_` não é único e tem nulos).
- **GEOROC** (um registro por CSV, `source_id` = `georoc:<nome do arquivo>`):
  - lido em cp1252; linhas de rodapé (abreviações e lista de referências, sem `UNIQUE_ID`) são ignoradas;
  - `ROCK NAME`, `SAMPLE NAME` e `MATERIAL` perdem só a etiqueta de citação **final** (` [123]`); `rock_name_original` é o nome sem essa etiqueta (nomes compostos como `BASALT [1] / ALKALI BASALT` ficam como vieram e não casam com o mapeamento);
  - só análises de rocha total (`MATERIAL` = `WR`); vidro (`GL`), minerais (`MIN`) e materiais mistos (`WR / MIN` etc.) saem e são contados em `dropped_material`;
  - uma linha por amostra (chave `SAMPLE NAME` + `CITATIONS`; fica a primeira linha do arquivo; as demais são contadas em `dropped_duplicate_rows`); `id` = `georoc:<UNIQUE_ID>` da linha mantida;
  - coordenadas: `LATITUDE/LONGITUDE MIN/MAX` são tratados como dois cantos (no arquivo real MIN > MAX é comum). Cantos iguais: ponto, `coord_source = reported`, incerteza nula. Cantos diferentes: centro da caixa, `coord_source = reported` e `coord_uncertainty_m` = metade da diagonal (grande círculo); a longitude considera o antimeridiano. Caixas com mais de 1° em latitude ou longitude saem (`dropped_box_too_large`). Sem coordenadas: não geocodificadas neste build (`pending_without_coords`).

### Mapeamento de rochas (proposto, revisar com geólogo)

`data/curated/rock_mapping_v2.csv` mantém todas as linhas do v1 e acrescenta:

- **máficas**: alkali basalt, tholeiitic basalt, transitional basalt, subalkali basalt, calc-alkali basalt, picrobasalt, trachybasalt, basanite, ankaramite, gabbronorite, norite (além de basalt, gabbro, diabase, dolerite do v1);
- **ultramáficas**: harzburgite, lherzolite, wehrlite, websterite, clinopyroxenite, orthopyroxenite (além de peridotite, dunite, pyroxenite, komatiite do v1).

`data/curated/rock_mapping_v3.csv` (v1 e v2 ficam intactos; o GEOROC passou a usar o v4, abaixo) = v2 + 505 nomes explícitos `<raiz já mapeada>, <qualificador mineral>` que ocorrem nos dados reais, com a **mesma classe da raiz**. Exemplos: `basalt, olivine`, `gabbro, hornblende`, `basalt, olivine-augite`, `basalt, augite-olivine`, `tholeiitic basalt, quartz`, `basanite, nepheline`, `pyroxenite, feldspar`, `lherzolite, spinel`. Qualificadores aceitos (só minerais/fases primárias): olivine, quartz, hornblende, augite, pyroxene, clinopyroxene, orthopyroxene, hypersthene, pigeonite, plagioclase e variedades (andesine, labradorite, bytownite, oligoclase, albite...), feldspar, nepheline, leucite, analcime, biotite, phlogopite, amphibole, garnet, spinel, magnetite, ilmenite, apatite, mica e variedades semelhantes, também combinados com hífen (`olivine-augite`) e `2-pyroxene`. **Ficam de fora** (listados, nada inferido): nomes com `xenolith`, compostos com ` / ` ou `[...]`, raízes que não estão no v2, qualificadores de alteração (iddingsite, chlorite, serpentine, talc, uralite, epidote...), `oxide`, `transitional`, `alkali`, `carbonate`, erros de digitação (`alivine`, `pgeonite`, `hyperstene`) e `cortlandite`. O v3 acrescenta ~11,7 mil amostras (10174 máficas, 1549 ultramáficas; contagem sobre as linhas `WR`, uma por amostra, com coordenada utilizável, antes de descartar `id` repetidos).

**Decisão do usuário (2026-11-03): nomes com `xenolith` ENTRAM** (`data/curated/rock_mapping_v4.csv`, v3 + 137 nomes com `xenolith` cuja raiz já está mapeada, com a classe da raiz; **usado pelo GEOROC**; v1, v2 e v3 ficam intactos). Cuidado de interpretação: um xenólito é um fragmento do manto/crosta arrastado pelo magma; a posição da amostra é a do vulcão hospedeiro, não a de um afloramento da rocha, e se um xenólito de peridotito do manto é "rocha ígnea" é discutível em petrologia. Por isso a classe vem só da raiz e o nome original (com `xenolith`) fica visível no painel da amostra; use o filtro "nome da rocha contém" para incluir/excluir `xenolith` na leitura. Eram, antes da decisão, 135 nomes e ~8,0 mil amostras (v4 acrescenta ~8,5 mil, 8480 ultramáficas e 10 máficas, linhas `WR`, uma por amostra, antes do descarte de coordenadas inválidas e de `id` repetidos): `lherzolite, spinel, xenolith` 1339; `peridotite, xenolith` 1335; `lherzolite, xenolith` 1111; `harzburgite, xenolith` 894; `peridotite, spinel, xenolith` 527; `harzburgite, spinel, xenolith` 423; `lherzolite, garnet, xenolith` 357; `dunite, xenolith` 306; `pyroxenite, xenolith` 240; `wehrlite, xenolith` 209; `websterite, xenolith` 205; `clinopyroxenite, xenolith` 160 (demais nomes somam o resto).

Build com o v4 (2026-11-03, `--force`): **134423 amostras** (116926 máficas, **17497 ultramáficas**; antes eram 126965 e 10002), 7506 delas com `xenolith` no nome, 34470 dentro de uma unidade básica do GLiM, 3096 `id` repetidos descartados entre fontes. Continuam todas com coordenada `reported`; o aviso do GDAL sobre tiles acima de 500 kB em `geo_units` (resolução reduzida nesses tiles) permanece.

A comparação é por igualdade exata do nome normalizado. Nomes não listados (por exemplo picrite, oceanite, hawaiite, basaltic-andesite e nomes compostos com ` / `) **não** são classificados: saem da camada e são contados em `unmapped` nas notas de cada fonte.

## Primeiro build real

Rodado em 2026-11-03 com `python -m pipeline.build --raw data/raw --out data/out --tippecanoe "" --keep-intermediate data/out/intermediate` (Windows, 226 s, todas as 38 fontes processadas):

| Camada | Linhas | Observações |
|---|---|---|
| `volcanoes` | 1214 | 366 sem `last_eruption`; nenhuma linha sem coordenada; nenhum hotspot (lista curada vazia) |
| `tectonic_zones` | 30 | 13151 sismos Mw usados de 14549 (1398 excluídos por `magType`); 182 códigos PB2002 |
| `geo_units` | 93220 | só `vb` (67180) e `pb` (26040); 178 geometrias reparadas |
| `samples` | 117761 | 109150 máficas, 8611 ultramáficas; todas `reported` (16136 com centro de caixa e incerteza); 30231 dentro de uma unidade básica do GLiM; 2165 grupos `dup_group` |

GEOROC (somando os 35 arquivos): 194569 linhas de dados, 175739 amostras após o filtro `WR` e uma linha por amostra; 49508 sem classe no mapeamento (`basaltic-andesite` sozinho são 15393; nomes com qualificador, como `lherzolite, spinel, xenolith`, são a maior parte do resto), 8205 caixas > 1°, 265 sem coordenadas (não geocodificadas).

### Segundo build (round 2: buffer 250 km, mapeamento v3, ids únicos, PMTiles via GDAL)

`python -m pipeline.build --raw data/raw --out data/out --force --tippecanoe ""` (sem tippecanoe; PMTiles pelo GDAL):

| Camada | Linhas | Observações |
|---|---|---|
| `tectonic_zones` | 30 | 94,1% do momento Mw atribuído (buffer 250 km); nomes `Placa A – Placa B (código)`; top 1: `Nazca – South America (NZ\SA)` |
| `geo_units` | 93220 | igual ao primeiro build |
| `samples` | 126965 | 116963 máficas, 10002 ultramáficas; 32524 dentro de uma unidade básica do GLiM; 18154 com incerteza (caixas); 1944 grupos `dup_group`; `id` único |

2519 amostras com `id` repetido entre fontes foram descartadas (vale a primeira fonte na ordem do registro; contagem por fonte em `dropped_duplicate_ids` e total em `_build` nas notas, impressa no resumo da CLI). Arquivos: `samples.pmtiles` 11,2 MB (zoom 1–8), `geo_units.pmtiles` 22,6 MB (zoom 0–6), `geoworld.gpkg` 186 MB. O GDAL avisa que algum tile de `geo_units` passou de 500 kB e foi codificado com resolução menor (baixo zoom).

Verificado no navegador (Edge no painel do Claude, `npm run serve`): sem erros no console; as quatro camadas aparecem (visão global, Havaí, Islândia); clique numa amostra real mostra nome sem etiqueta de citação, classe, tipo de coordenada, unidade e fonte/licença/link; clique numa unidade mostra `sample_count` e o botão "Ver amostras desta litologia" filtra (`lith=basic_volcanic`); filtros de classe, nome da rocha e fonte funcionam; a busca acha vulcão (Kilauea) e zonas (Nazca); o estado da URL é restaurado. Dois ajustes saíram dessa verificação: intensidade do mapa de calor (sem agregação de densidade tudo saturava) e a grade do painel de detalhes (colunas esmagadas na unidade).

Pendências vistas na verificação: os 35 arquivos do GEOROC aparecem com o mesmo rótulo (instituição) na lista de fontes, então os filtros por fonte ficam indistinguíveis; o painel de uma amostra mostra "Escala original do mapa: não informado" apesar do aviso de 1:3.750.000 (a escala vem do registro da fonte da unidade, e as amostras só carregam o `source_id` da amostra).

Problemas encontrados no primeiro build e situação:

- **Sismos fora do buffer** (corrigido): com `buffer_km=100` só 42% do momento era atribuído; com 250 km são 94,1%.
- **A mesma análise em mais de um arquivo do GEOROC** (corrigido): `id` repetidos entre fontes são descartados na montagem (primeira fonte vence).
- `data/out/intermediate/geo_units.geojson` (360 MB) e `samples.geojson` (43 MB) são só para rodar o tippecanoe à mão (`--keep-intermediate`); `geoworld.gpkg` tem 184 MB.

## Ferramentas (verificadas)

- Python 3.11.9: presente (use `.venv`, dependências em `requirements.txt`)
- Node v24: presente
- tippecanoe: **ausente** (no Windows costuma exigir WSL ou Docker; não instalado); os PMTiles saem pelo fallback do GDAL do pyogrio (3.12.4)
- Microsoft Edge: presente, usado pelo teste e2e (nenhum navegador é baixado)

## Limitações conhecidas

- **PMTiles via GDAL**: sem agregação de densidade em zoom baixo (o mapa de calor usa todos os pontos) e com simplificação/descarte de polígonos pequenos em baixo zoom; tippecanoe é recomendado (veja "PMTiles sem tippecanoe" e "tippecanoe no Windows (WSL)").
- **Busca por unidades geológicas**: a busca só encontra vulcões, hotspots, zonas tectônicas e coordenadas; unidades geológicas não são pesquisáveis.
- **Mapas de fundo** (escolhidos pelo usuário em 2026-11-03; `web/js/basemaps.js`): **Escuro** (Esri Canvas World Dark Gray Base, zoom até 16), **Relevo** (Esri World Shaded Relief, até 13) e **Satélite** (Esri World Imagery, até 19), além do "Fundo liso" (sem requisições externas). O Escuro é o padrão ao abrir. Pontos de atenção, todos de **terceiros**:
  - **Privacidade:** o navegador de quem abre o globo pede os tiles direto a `server.arcgisonline.com`, que vê o IP e a região visualizada. Para evitar isso, escolha "Fundo liso".
  - **Termos de uso:** valem os da Esri para cada serviço (uso gratuito com atribuição, pensado para fins não comerciais; confirme antes de publicar ou de qualquer uso comercial). A atribuição do fundo ativo aparece sempre no rodapé do mapa.
  - **CARTO `dark_all` não serve:** testado em 2026-11-03, os tiles públicos sem chave de API vêm com a marca d'água "API KEY REQUIRED"; por isso o escuro é o da Esri.
  - Verificado no navegador (Edge/painel do app) com os três fundos e dados reais. O e2e **bloqueia** essas requisições externas e devolve um PNG vazio, então os testes automáticos não dependem desses serviços.
- **GitHub Pages**: limite de 100 MB por arquivo; a exportação avisa quando um arquivo passa de 95 MB.
- **Aviso do maplibre-gl** sobre `Popup.setHTML`: não usamos popups; os detalhes são montados com escape de HTML em `web/js/inspector.js`.
- **Latitude e longitude trocadas**, quando ambas ficam dentro do intervalo válido, não podem ser detectadas.
- **Momento sísmico**: calculado com a fórmula `10^(1,5·Mw + 9,1)` N·m (constante USGS/IASPEI).
- **Filtro por litologia**: o realce das amostras só aparece pelo mapa de calor abaixo do zoom 5.
- **Zonas tectônicas**: o ranking soma o momento sísmico por limite de par de placas do PB2002 (dissolvido por `Name`); limites longos acumulam mais sismos e tendem a ficar mais acima. O mesmo par pode aparecer com códigos diferentes no PB2002 (ex.: `AF-AN` e `AN-AF`, ou `EU-AF` e `EU/AF`, que diferem no separador/ordem), e cada código vira uma zona separada. O tipo do limite (`Type`, "subduction" ou vazio) não é usado no ranking; serve só de conferência.
- **Catálogo sísmico**: só entram magnitudes de momento (`magType` mw, mww, mwc, mwb, mwr, Mw); ms, mb e outras são excluídas e contadas nas notas da fonte `tectonics`.
- **GLiM restrito**: neste build a camada `geo_units` contém só as classes básicas (`xx` = `vb` vulcânicas básicas e `pb` plutônicas básicas), lidas com filtro no GDAL por limite de memória. Uma amostra com `unit_id` nulo significa "fora de uma unidade ígnea básica do GLiM", **não** "sem unidade".
- **Amostras sem coordenada** (GEOROC) não foram geocodificadas neste build (sem rede); ficam contadas em `pending_without_coords`.

## O que foi e o que não foi verificado

Verificado: primeiro build real (veja "Primeiro build real"); testes Python (pytest) com fixtures; testes Node dos módulos puros; validação do estilo do mapa; teste de fumaça no Edge com **dados sintéticos** (carregamento, ligar/desligar camada, clique e painel de detalhes, Escape e foco, restauração de estado pela URL, aviso de PMTiles ausentes, nome com HTML exibido como texto).

Não verificado: PMTiles gerados pelo tippecanoe, desempenho com volumes reais de dados, Chrome/Firefox/Safari e dispositivos móveis.
