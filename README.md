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

Arquivos esperados pelo globo: `volcanoes.geojson`, `tectonic_zones.geojson`, `plate_boundaries.geojson`, `plate_labels.geojson`, `sources.json`, `geo_units.pmtiles`, `samples.pmtiles`. Se algum faltar, a camada correspondente mostra um aviso no painel e o resto do globo continua funcionando. `web/data/` é ignorado pelo git; decida a forma de publicação (veja os limites abaixo) antes de versionar dados.

## Camada de placas tectônicas (PB2002)

A camada **Placas tectônicas** (`plates`, **ligada por padrão**) desenha todos os 241 segmentos de limite de placa do PB2002 (Bird, 2003) junto com as zonas do top 30, e escreve o nome de cada placa.

- **Linhas**: `plate_boundaries.geojson`, um segmento por feição, **sem dissolver** (propriedades `name`, `plate_a`, `plate_b`, `plate_a_name`, `plate_b_name`, `type`, `source_id`). Linha fina cinza-clara; segmentos `type = subduction` ficam mais grossos e em cinza quente (expressão `case` do MapLibre). A camada fica **abaixo** de `tectonic_zones`, então o laranja grosso das zonas mais ativas continua por cima. O nome da placa vem de `pb2002/plates.json`; código sem nome conhecido aparece com o código bruto, nunca com nome inventado. Clique em um limite: "Limite entre A e B (código)", tipo (subducção / não classificado) e a fonte.
- **Nomes**: `plate_labels.geojson`, um ponto por código de placa (`code`, `name`, `area_km2`, `source_id`), tirado de `representative_point` do **maior** polígono da placa (placas cortadas no antimeridiano, como a Pacífica, ficam com o rótulo dentro da maior metade). Os nomes são **rótulos DOM** (`maplibregl.Marker` com `textContent`, `pointer-events: none`, `web/js/platelabels.js`), **não** uma camada de texto do estilo: o estilo não tem servidor de glifos e não queremos depender de um serviço externo de fontes. Os rótulos do lado oculto do globo ficam invisíveis (`opacityWhenCovered: 0`), somem acima do zoom 6 e as placas pequenas só aparecem ao aproximar (zoom mínimo pela `area_km2` da placa: a partir de 10 milhões de km² desde o globo inteiro, depois 2,5; 3,5; 4,5; 5,5), para os nomes não se sobreporem. Seguem a visibilidade e a opacidade da camada `plates`. Se o carregamento falhar, o aviso da camada aparece e nenhum nome é criado.
- **Fontes**: dois arquivos brutos, duas fontes no registro: `pb2002` (`boundaries.json`, camada `plate_boundaries`) e `pb2002_plates` (`plates.json`, camada `plate_labels`), cada uma com o hash do seu arquivo no cache. Os nomes das placas nos limites vêm do `plates.json`, que não entra no hash de `pb2002`: se ele mudar, rode com `--force`.
- **Licença e atribuição**: Open Data Commons Attribution 1.0 (`data/raw/pb2002/LICENSE.md`); citar Bird, P. (2003) An updated digital model of plate boundaries, G-cubed 4(3), 1027, doi:10.1029/2001GC000252, e o repositório [fraxen/tectonicplates](https://github.com/fraxen/tectonicplates) que distribui os GeoJSON. Aparece no controle de atribuição do mapa e no painel de detalhes.

## Camada de geologia pública (Macrostrat)

A camada **Geologia (Macrostrat)** (`macrostrat`, desligada por padrão) é a alternativa **pública** ao GLiM. Usa os tiles vetoriais `carto` do [Macrostrat](https://macrostrat.org) (`https://tiles.macrostrat.org/carto/{z}/{x}/{y}.mvt`), que o site declara livres sob **CC BY 4.0**: é preciso **citar o Macrostrat e os provedores originais dos mapas** (a referência de cada `source_id`). A atribuição aparece no controle do mapa e, ao clicar numa unidade, o painel traz o crédito, o link para macrostrat.org e os dados do mapa original (nome, título, autores, publicação, ano, endereço).

- **Privacidade**: os tiles vêm direto de `tiles.macrostrat.org` para o navegador do visitante (como os mapas-base), sem passar pelo nosso servidor; o servidor deles vê o IP e o navegador de quem liga a camada. Nada é pedido enquanto a camada estiver desligada.
- **Cobertura e escala** (observadas em 2026-11-03): o servidor mistura mapas de várias escalas conforme o zoom (no zoom 2 a fonte é a "Generalized Geology of the World" (Geological Survey of Canada); ao aproximar entram mapas mais detalhados, como os do Serviço Geológico do Brasil). Os oceanos não têm polígonos (aparece o mapa-base) e a Antártida tem uma unidade única. Os tiles de baixo zoom são pesados (~170–240 kB cada). A fonte usa `maxzoom` 12; acima disso o MapLibre amplia o tile.
- **Propriedades lidas** (camada `units`; o contrato do lado web está em `web/js/contract.json`, entrada externa `macrostrat`, fora do pipeline): `color` (cor da unidade, validada: texto que não for cor vira cinza), `name`, `lith`, `age`, `t_int`, `b_int`, `best_age_top`, `best_age_bottom`, `descrip`, `comments`, `map_id`, `source_id`, `ref_name`, `ref_title`, `ref_authors`, `ref_source`, `ref_year`, `ref_url`. `descrip` e `comments` são quase sempre vazios; `lith_class1`, `lith_type*` e `lith_class2/3` existem mas não são usados. A camada `lines` (falhas) é desenhada fina, sem clique.
- Prioridade do clique (ordem de empilhamento padrão): amostras > vulcões > zonas tectônicas > placas > unidades GLiM > Macrostrat.

**GLiM**: a camada **Unidades GLiM (uso local)** (`geo_units`) só é usada localmente, porque o GLiM não declara licença; **não publique** `geo_units.pmtiles`. Sem o arquivo o globo funciona e o painel mostra o aviso de camada indisponível. Pedir permissão aos autores do GLiM continua sendo uma opção para publicá-lo.

## Paleomapas (linhas de costa de 0 a 150 Ma)

Barra "Linhas de costa antigas" na base do globo: deslizante de idade (passos de 5 Ma) e botão Animar.

- **Fonte:** Merdith et al. (2021), *Extending full-plate tectonic models into deep time*, Earth-Science
  Reviews 214, 103477 — modelo v1.2.4, Zenodo 10.5281/zenodo.13635864, licença **CC BY 4.0**.
  Usamos o arquivo de rotações e as linhas de costa do próprio modelo; nada é inferido por nós.
- **Gerar:** baixe `Merdith_etal_2021_ESR_v1.2.4.zip` do Zenodo, extraia em `data/raw/paleo/merdith/`
  (ignorado pelo git) e rode `python pipeline/paleo.py` (requer `pygplates`). Saída em `web/data/paleo/`
  (~2 MB por idade, carregada sob demanda; ignorada pelo git).
- **Vulcões girados:** cada vulcão recebe a placa dos polígonos estáticos do modelo e é levado para onde
  essa placa estava na idade escolhida (`web/data/paleo/volcanoes_<idade>.geojson`). Os vulcões não
  existiam nessa idade: a posição mostra onde estava a crosta que hoje os sustenta. Pontos sem placa
  seriam omitidos (na geração atual: 0 de 1.214).
- **Amostras na posição de formação (local):** `python -m pipeline.paleo_samples` lê a idade **numérica medida**
  do GEOROC (`MIN. AGE`/`MAX. AGE`, ponto médio; períodos em texto como "CRETACEOUS" **não** viram número) e gira cada
  amostra pela placa dela até o quadro de 5 Ma mais próximo. Entram só amostras com idade ≤ 152,5 Ma e
  semi-intervalo ≤ 5 Ma (as demais são descartadas e contadas). Na geração atual: 17.375 amostras com idade
  numérica, 8.808 giradas (130 Ma: 195; 135 Ma: 95). Os quadros `samples_<idade>.geojson` ficam **fora do git**
  (GEOROC é CC BY-SA 4.0, atribuição + mesma licença; confirmar antes de publicar). Caixa "Amostras (GEOROC)…"
  na barra, só aparece se os quadros existirem.
- **Lineamentos estruturais (dados do pesquisador):** não achei conjunto aberto contínuo (Brasil + África) com
  licença clara; o SGB/CPRM tem camadas no GeoSGB e o repositório RIGEO, mas sem licença explícita encontrada. Por isso o
  pipeline aceita seus GeoJSON em `data/curated/lineaments/` (cada feição com `name` e `source` obrigatórios; feição sem
  fonte é recusada) e os gira (`python -m pipeline.paleo_lineaments`). Cada lineamento gira como corpo rígido pela placa
  do ponto médio; se as pontas caem em placas diferentes do modelo, ele é marcado (`plates_differ`). Nada é desenhado
  por nós. Caixa "Lineamentos estruturais…" aparece quando há quadros `lineaments_<idade>.geojson`.
- **Lineamentos do Brasil (SGB/CPRM, local):** `scripts/fetch_sgb_structures.py` baixa as 32.323 estruturas do SIG
  *Geologia, Tectônica e Recursos Minerais do Brasil* (2004, 1:1.000.000; servidor ArcGIS do SGB, sem licença declarada, uso de
  pesquisa com citação). `scripts/make_sgb_lineaments.py` seleciona **falhas e zonas de cisalhamento** de segmento
  ≥ 50 km (sem fraturas e sem traços de foliação) — critério nosso, não interpretação: 1.328 segmentos. Os arquivos
  derivados ficam **fora do git**.
- **Lineamentos da África (CGMW–BRGM, local):** `scripts/make_brgm_lineaments.py` converte a camada de **falhas**
  (`AFR_CGMW_BRGM_10M_Faults`, 2.644 linhas, 1:10.000.000, 3ª edição 2016) do WFS do BRGM/OneGeology. Termos do serviço:
  uso pessoal, de ensino, de pesquisa ou **não comercial**; copyright CGMW/BRGM; citar
  "Geological Map of Africa at 1:10 M scale, CGMW-BRGM 2016". É camada de falhas (Fault, Thrust, Normal e as
  "Inferred"): **não** há classe "zona de cisalhamento". O Brasil (1:1 M) e a África (1:10 M) têm escalas e
  critérios diferentes: não compare densidade entre os dois lados. A África é dividida em vários blocos pelo modelo
  (placas 701, 714, 715...); 264 falhas cruzam blocos e são giradas pela placa do ponto médio (marcadas
  `plates_differ`), então a posição delas em idades antigas é aproximada.
- **Botão "Girar globo":** rotação automática (liga/desliga); arrastar, rolar ou tocar no mapa a desliga.
- **Limites:** é uma reconstrução interpretativa. Zonas, placas e amostras continuam nas
  posições atuais (não são girados ainda). O Scotese/PALEOMAP (usado pelo dinosaurpictures.org) não foi
  incluído por ter licença de uso menos clara.

## Vista 3D da abertura do Atlântico Sul (`rift3d.html`)

Página 3D interativa (Three.js) da faixa de 20°S a 40°S, da costa sul do Brasil à costa sul da África, com
relevo e batimetria **atuais** movidos como blocos rígidos pelo modelo de placas (Merdith et al. 2021,
CC BY 4.0), de 150 Ma até hoje. A África (placa fixa escolhida automaticamente) fica parada e a América
do Sul se move. Abra `http://127.0.0.1:8766/rift3d.html` (`npm run serve`) ou use o link "Vista 3D" do globo.

Gerar os dados (precisa do modelo em `data/raw/paleo/merdith`, como nos paleomapas; baixa 30 tiles do AWS
Terrain Tiles):

```bash
.\.venv\Scripts\python.exe -m pipeline.rift3d
```

Saída em `web/data/rift3d/` (`grid.bin`, `grid.json`, `rotations.json`, `index.json`), **git-ignorada** até a
licença do relevo ser confirmada (AWS Terrain Tiles junta SRTM, GEBCO, ETOPO1 e outras fontes). Sem esses
arquivos a página mostra a mensagem de dados ausentes.

Lineamentos e vulcões entram como camadas presas à placa de cada feição (posições atuais de
`web/data/paleo/lineaments_0.geojson` e `volcanoes_0.geojson`); sem esses arquivos a caixa some. **Para usar
lineamentos próprios**: coloque GeoJSON (`LineString`/`MultiLineString`, lon/lat, com `properties.name` e
`properties.source` obrigatórios) em `data/curated/lineaments/` e rode, nesta ordem:

```bash
.\.venv\Scripts\python.exe -m pipeline.paleo_lineaments
.\.venv\Scripts\python.exe -m pipeline.rift3d
```

(o segundo passo inclui na tabela de rotações as placas dos lineamentos novos; feição cuja placa não está
na tabela é omitida, e a página avisa quantas). Clicar numa linha ou vulcão mostra nome e fonte.

Limites, para ler os resultados com cuidado:
- o relevo é o atual, só movido: não é paleotopografia nem reconstrução do relevo antigo;
- os polígonos estáticos do modelo cobrem também o fundo oceânico, mas ele não existia nas idades antigas:
  células mais fundas que −2500 m ficam sem placa (corte de exibição, gravado em `grid.json`), restando
  plataforma e talude superior;
- as margens atuais se sobrepõem perto de 150 Ma (as duas margens estiradas voltam a se encostar): é o que o
  modelo e o relevo atual dão, não um erro de desenho;
- a África está dividida em várias placas no modelo (701, 77030 e outras): blocos vizinhos podem se
  sobrepor ou deixar vãos em idades antigas;
- a grade é de 0,05° (cerca de 5 km): serve para ver, não para medir; o exagero vertical (10 a 80×) muda só
  a aparência;
- as amostras GEOROC ainda não entram na vista 3D (a posição delas depende da idade de cada uma).

## Publicação no GitHub Pages

O Pages serve a raiz da `main`; `index.html` na raiz redireciona para `web/`.
Vão no repositório (via exceções no `.gitignore`) só os dados de `web/data/` que podem ser publicados:
vulcões (GVP), zonas tectônicas (USGS + PB2002), limites e nomes de placas (PB2002) e os paleomapas
(Merdith 2021). **Não** vão `samples.pmtiles` (GEOROC) nem `geo_units.pmtiles` (GLiM): sem esses arquivos
o globo esconde as camadas "Amostras" e "Unidades GLiM" e tira GEOROC/GLiM da atribuição, sem erros.
Localmente, com os arquivos presentes, tudo aparece como antes.

- **GVP:** os termos do Smithsonian convidam ao uso educacional e não comercial, com citação; não é
  licença aberta. Não use o site publicado de forma comercial sem consultar o GVP (gvp@si.edu).
- **Mapas de fundo e Macrostrat:** continuam sendo pedidos direto do navegador de quem abre o site
  (o IP fica visível para esses provedores) — ver "Mapas de fundo".
- **Testes e2e:** o e2e recusa rodar com dados reais em `web/data`; mova a pasta antes (ver `tests/e2e`).

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
