# GeoWorld, primeiro recorte: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir o globo interativo com as camadas Vulcões, Zonas tectônicas, Unidades geológicas (GLiM) e Amostras máficas/ultramáficas, ligadas pelo clique ponto → unidade → litologia.

**Architecture:** Um pipeline Python normaliza cada fonte para um GeoPackage canônico (`data/out/`), com fonte, licença e escala em todo registro, e exporta GeoJSON e PMTiles. Um site estático em JavaScript puro (MapLibre GL em modo globo) consome esses arquivos. Funções puras (estado na URL, filtros, painéis, busca) ficam separadas do mapa para serem testadas sem navegador.

**Tech Stack:** Python 3.11+, GeoPandas, Shapely, PyProj, pyogrio, Requests, pytest, tippecanoe; MapLibre GL JS, pmtiles (JS), `node:test`, Playwright.

**Spec:** `docs/superpowers/specs/2026-11-03-geoworld-primeiro-recorte-design.md`

## Global Constraints

- Toda geometria sai do pipeline em WGS84 (EPSG:4326). CRS ausente na entrada é erro, nunca é presumido.
- Campo sem informação confirmada é nulo no dado e aparece como `não informado` na interface. Nada é inferido.
- `rock_class` só assume `mafic`, `ultramafic` ou nulo. `coord_source` só assume `reported` ou `geocoded`.
- Todo registro carrega `source_id`, e `sources` guarda instituição, `source_url`, licença, atribuição, data de aquisição e escala original.
- Armazenamento canônico: GeoPackage em `data/out/`. `data/raw/` fica fora do git, exceto `data/raw/manifest.json`.
- Mapas de escalas diferentes não entram na mesma camada. Dados originais não são alterados.
- Ranking tectônico: top 30 zonas, momento sísmico por segmento PB2002, métrica e período exibidos no popup.
- Duplicatas entre GEOROC e PetDB são ligadas por `dup_group`, nunca apagadas.
- Sem geocodificador externo no navegador. JavaScript puro com módulos, sem framework.
- Arquivo publicado no GitHub Pages: máximo de 100 MB. Alertar acima de 95 MB.
- Downloads de dados e chamadas a serviços externos só com autorização do usuário no momento. Publicar (push, Pages) só com decisão do usuário.

## Review Focus

1. Coordenadas inválidas (0,0, latitude fora de ±90, longitude fora de ±180, latitude e longitude trocadas): a amostra é excluída e contada, nunca plotada. (Task 6)
2. Nome de rocha com acento, caixa diferente, espaços extras ou composto ("Olivine basalt, altered"): só casa se o nome normalizado estiver na tabela, caso contrário fica nulo. (Task 5)
3. Texto das fontes com HTML ou aspas nos painéis (`<script>`, `"`): sai escapado, nunca executa. (Task 12)
4. Pontos e segmentos sobre o antimeridiano (±180): a junção ponto-em-polígono e o ranking não perdem nem duplicam registros. (Tasks 4 e 8)
5. Filtro sem resultado, unidade com zero amostras, camada que falha ao carregar: o painel mostra 0 ou aviso e o mapa continua funcionando. (Tasks 11 e 12)

---

### Task 1: Esqueleto, esquema do GeoPackage e manifesto

**Files:**
- Create: `pyproject.toml`, `requirements.txt`, `pipeline/__init__.py`, `pipeline/common/__init__.py`, `pipeline/common/model.py`, `pipeline/common/manifest.py`
- Test: `tests/test_model.py`, `tests/test_manifest.py`

**Interfaces:**
- Produces: `SCHEMAS: dict[str, list[str]]` (colunas de `sources`, `samples`, `geo_units`, `volcanoes`, `tectonic_zones`, conforme spec seção 5); `create_geopackage(path: Path) -> None`; `write_layer(gpkg: Path, name: str, gdf: GeoDataFrame) -> None`; `record_download(manifest: Path, source_id: str, url: str, file: Path, license: str) -> dict`; `verify_manifest(manifest: Path, raw_dir: Path) -> list[str]` (ids com hash divergente).

- [ ] **Step 1: Verificar ferramentas.** Rodar `python --version`, `node --version`, `tippecanoe --version`. Anotar no `README.md` quais faltam (tippecanoe no Windows costuma exigir WSL ou Docker). Não instalar sem avisar o usuário.
- [ ] **Step 2: Escrever testes que falham.** `test_create_geopackage_has_all_layers` (as cinco camadas existem e as colunas de cada uma são iguais a `SCHEMAS`); `test_write_layer_fills_missing_columns_with_null`; `test_write_layer_rejects_unknown_column`; `test_verify_manifest_detects_changed_file` (grava arquivo, registra, altera, espera `[source_id]`).
- [ ] **Step 3: Rodar** `python -m pytest tests/test_model.py tests/test_manifest.py -v`. Esperado: FAIL (módulos inexistentes).
- [ ] **Step 4: Implementar** os módulos com as assinaturas acima. `write_layer` completa colunas ausentes com nulo e levanta `ValueError` para coluna fora do esquema. Hash SHA-256 em `record_download`. Fixar versões exatas em `requirements.txt` ao instalar.
- [ ] **Step 5: Rodar os testes.** Esperado: PASS.
- [ ] **Step 6: Commit** `git add -A && git commit -m "feat: esqueleto, esquema do geopackage e manifesto"`.

### Task 2: Utilitários de geometria

**Files:**
- Create: `pipeline/common/geom.py`
- Test: `tests/test_geom.py`

**Interfaces:**
- Produces: `to_wgs84(gdf: GeoDataFrame) -> GeoDataFrame` (levanta `ValueError` se `gdf.crs is None`); `repair_geometries(gdf: GeoDataFrame) -> tuple[GeoDataFrame, int]` (corrige com `make_valid`, descarta vazias, devolve quantas foram reparadas).

- [ ] **Step 1: Testes.** `test_to_wgs84_reprojects_from_utm`; `test_to_wgs84_requires_crs`; `test_repair_fixes_bowtie_polygon` (polígono em gravata vira válido e a contagem é 1); `test_repair_drops_empty_geometries`.
- [ ] **Step 2: Rodar** `python -m pytest tests/test_geom.py -v`. Esperado: FAIL.
- [ ] **Step 3: Implementar** com `GeoDataFrame.to_crs` e `shapely.make_valid`.
- [ ] **Step 4: Rodar.** Esperado: PASS.
- [ ] **Step 5: Commit** `git commit -am "feat: utilitarios de geometria"`.

### Task 3: Vulcões (GVP) e lista curada de hotspots

**Files:**
- Create: `pipeline/gvp.py`, `data/curated/hotspots.csv` (cabeçalho: `name,lon,lat,reference`; sem linhas até existir fonte citável), `tests/fixtures/gvp_sample.csv`
- Test: `tests/test_gvp.py`

**Interfaces:**
- Consumes: `to_wgs84`, `write_layer`, `SCHEMAS["volcanoes"]`.
- Produces: `normalize_gvp(df: pd.DataFrame, source_id: str) -> GeoDataFrame` (colunas `name, type, last_eruption, country, source_id, geometry`); `load_hotspots(csv: Path, source_id: str) -> GeoDataFrame` (levanta `ValueError` se alguma linha não tiver `reference`).

- [ ] **Step 1: Obter a amostra do GVP.** Com autorização do usuário, baixar a lista de vulcões holocênicos do Smithsonian GVP, registrar no manifesto (`record_download`) e copiar as 5 primeiras linhas, com os cabeçalhos reais, para `tests/fixtures/gvp_sample.csv`. Definir `GVP_COLUMNS` (nome original → nome da spec) a partir desses cabeçalhos.
- [ ] **Step 2: Testes.** `test_normalize_gvp_keeps_original_name_and_coords`; `test_normalize_gvp_empty_last_eruption_is_null`; `test_normalize_gvp_drops_rows_without_coords_and_reports` ; `test_load_hotspots_requires_reference`; `test_load_hotspots_empty_file_returns_empty_frame`.
- [ ] **Step 3: Rodar** `python -m pytest tests/test_gvp.py -v`. Esperado: FAIL.
- [ ] **Step 4: Implementar** as duas funções. Nenhuma linha de hotspot é criada pelo código.
- [ ] **Step 5: Rodar.** Esperado: PASS.
- [ ] **Step 6: Commit** `git add -A && git commit -m "feat: vulcoes GVP e carregador de hotspots com referencia obrigatoria"`.

### Task 4: Ranking das zonas tectônicas

**Files:**
- Create: `pipeline/tectonics.py`
- Test: `tests/test_tectonics.py`

**Interfaces:**
- Consumes: `to_wgs84`.
- Produces: `seismic_moment(mw: float) -> float` (`10 ** (1.5 * mw + 9.1)`, N·m); `rank_zones(boundaries: GeoDataFrame, quakes: pd.DataFrame, buffer_km: float = 100, top_n: int = 30) -> GeoDataFrame`. `quakes` tem colunas `lat, lon, mw, time`. Saída: `rank, name, moment_total, period_start, period_end, source_id, geometry`.

- [ ] **Step 1: Obter dados.** Com autorização do usuário, baixar o modelo de limites PB2002 e o catálogo sísmico do USGS (magnitude mínima e período definidos com o usuário), registrar no manifesto.
- [ ] **Step 2: Testes.** `test_seismic_moment_mw7` (resultado ≈ 3.55e19); `test_segment_with_two_m7_outranks_one_m7`; `test_quake_beyond_buffer_ignored`; `test_each_quake_counted_for_nearest_segment_only`; `test_top_n_limits_output_and_ranks_from_1`; `test_quake_near_antimeridian_assigned_to_segment_across_180` (segmento em lon 179.9 e sismo em lon -179.9 distam menos que `buffer_km`).
- [ ] **Step 3: Rodar** `python -m pytest tests/test_tectonics.py -v`. Esperado: FAIL.
- [ ] **Step 4: Implementar.** Projetar para um CRS métrico adequado (por exemplo, azimutal equidistante por segmento ou distância geodésica via `pyproj.Geod`) para que a distância ao segmento respeite o antimeridiano; atribuir cada sismo ao segmento mais próximo dentro do buffer; somar o momento por segmento.
- [ ] **Step 5: Rodar.** Esperado: PASS.
- [ ] **Step 6: Commit** `git add -A && git commit -m "feat: ranking de zonas tectonicas por momento sismico"`.

### Task 5: Tabela de mapeamento de rochas

**Files:**
- Create: `pipeline/rockmap.py`, `data/curated/rock_mapping_v1.csv` (colunas `name,class`)
- Test: `tests/test_rockmap.py`

**Interfaces:**
- Produces: `normalize_rock_name(s: str | None) -> str | None` (minúsculas, sem acento, espaços colapsados; vazio vira `None`); `load_mapping(csv: Path) -> dict[str, str]`; `classify_rock(name: str | None, mapping: dict[str, str]) -> str | None`.

- [ ] **Step 1: Testes.** `test_basalt_is_mafic`; `test_dunite_is_ultramafic`; `test_accent_case_spaces_normalized` (`"  Diabásio "` casa com `diabasio`); `test_compound_name_not_in_table_is_null` (`"Olivine basalt, altered"` → `None`); `test_granite_and_none_and_empty_are_null`; `test_load_mapping_rejects_class_other_than_mafic_or_ultramafic`.
- [ ] **Step 2: Rodar** `python -m pytest tests/test_rockmap.py -v`. Esperado: FAIL.
- [ ] **Step 3: Implementar** e criar o CSV inicial com os nomes da spec (basalto/basalt, gabro/gabbro, diabásio/diabase/dolerite, peridotito/peridotite, dunito/dunite, piroxenito/pyroxenite, komatiito/komatiite) com a classe correspondente.
- [ ] **Step 4: Rodar.** Esperado: PASS.
- [ ] **Step 5: Commit** `git add -A && git commit -m "feat: mapeamento versionado de nomes de rocha"`.

### Task 6: Normalização de amostras e geocodificação de pendentes

**Files:**
- Create: `pipeline/samples.py`, `pipeline/geocode.py`
- Test: `tests/test_samples.py`, `tests/test_geocode.py`

**Interfaces:**
- Consumes: `classify_rock`, `to_wgs84`.
- Produces: `@dataclass NormalizeResult(located: GeoDataFrame, pending: pd.DataFrame, dropped_invalid: int, unmapped: collections.Counter)`; `normalize_samples(df: pd.DataFrame, source_id: str, colmap: dict[str, str], mapping: dict[str, str]) -> NormalizeResult` (`colmap` liga as colunas da fonte a `id, rock_name, lat, lon, locality, country`); `geocode_pending(pending: pd.DataFrame, geocoder: Callable[[str], tuple[float, float, float] | None], cache: Path) -> GeoDataFrame` (o `geocoder` devolve `(lat, lon, uncertainty_m)`).
- Saída de `located`/geocodificado segue `SCHEMAS["samples"]`: `rock_name_original` guarda o nome como veio; `rock_class` vem do mapeamento; `coord_source` é `reported` ou `geocoded`; `coord_uncertainty_m` é nulo quando reportada.

- [ ] **Step 1: Obter amostras reais.** Com autorização do usuário e depois de verificar termos de uso, baixar um recorte pequeno de GEOROC e de PetDB/EarthChem; guardar cabeçalhos reais em `tests/fixtures/` e definir os `colmap` de cada fonte.
- [ ] **Step 2: Testes de normalização.** `test_unmapped_rock_names_excluded_and_counted`; `test_invalid_coords_dropped_and_counted` (parametrizado: `(0,0)`, `lat=91`, `lon=181`, `lat=NaN` com `lon` válida); `test_swapped_lat_lon_out_of_range_is_dropped` (lat=120, lon=40); `test_rows_without_coords_but_with_locality_go_to_pending`; `test_rock_name_original_preserved_verbatim`; `test_coord_source_reported_and_uncertainty_null`.
- [ ] **Step 3: Testes de geocodificação.** `test_geocode_marks_source_and_uncertainty`; `test_geocode_uses_cache_and_calls_geocoder_once_per_query`; `test_geocode_no_result_is_dropped_not_guessed`; `test_geocoder_exception_does_not_abort_batch`.
- [ ] **Step 4: Rodar** `python -m pytest tests/test_samples.py tests/test_geocode.py -v`. Esperado: FAIL.
- [ ] **Step 5: Implementar.** Consulta de geocodificação: `"{locality}, {country}"`. O backend real (por exemplo Nominatim, 1 requisição por segundo e `User-Agent` identificado) é plugado como `geocoder` no `build.py` e só roda com autorização do usuário.
- [ ] **Step 6: Rodar.** Esperado: PASS.
- [ ] **Step 7: Commit** `git add -A && git commit -m "feat: normalizacao de amostras e geocodificacao de pendentes"`.

### Task 7: Deduplicação entre fontes

**Files:**
- Create: `pipeline/dedupe.py`
- Test: `tests/test_dedupe.py`

**Interfaces:**
- Produces: `assign_dup_groups(samples: GeoDataFrame, precision: int = 4) -> GeoDataFrame` (preenche `dup_group` quando há registros de `source_id` diferentes com a mesma coordenada arredondada e o mesmo `rock_name_original` normalizado; caso contrário, nulo).

- [ ] **Step 1: Testes.** `test_same_rock_same_place_two_sources_share_group`; `test_same_source_same_place_not_grouped`; `test_different_rock_same_place_not_grouped`; `test_no_rows_removed`; `test_group_id_is_stable_across_runs`.
- [ ] **Step 2: Rodar** `python -m pytest tests/test_dedupe.py -v`. Esperado: FAIL.
- [ ] **Step 3: Implementar.** Chave: `(round(lon, p), round(lat, p), normalize_rock_name(rock_name_original))`; `dup_group` é um hash curto e determinístico da chave.
- [ ] **Step 4: Rodar.** Esperado: PASS.
- [ ] **Step 5: Commit** `git add -A && git commit -m "feat: ligacao de duplicatas entre fontes"`.

### Task 8: Unidades GLiM e ligação amostra-unidade

**Files:**
- Create: `pipeline/glim.py`, `pipeline/join.py`
- Test: `tests/test_glim.py`, `tests/test_join.py`, `tests/fixtures/glim_sample.gpkg`

**Interfaces:**
- Consumes: `to_wgs84`, `repair_geometries`.
- Produces: `normalize_glim(gdf: GeoDataFrame, source_id: str) -> GeoDataFrame` (colunas `unit_id, lith_original, lith_class, source_id, geometry`; `lith_class` vem de `GLIM_CLASSES`, nulo se o código não estiver mapeado); `attach_units(samples: GeoDataFrame, units: GeoDataFrame) -> GeoDataFrame` (preenche `unit_id`; sem unidade, nulo).

- [ ] **Step 1: Obter amostra do GLiM.** Com autorização do usuário, baixar o `.gdb` (informar o tamanho antes) ou a versão em grade, recortar uma região pequena para `tests/fixtures/glim_sample.gpkg` e anotar os nomes reais das colunas e os códigos litológicos. Montar `GLIM_CLASSES` a partir da documentação do GLiM, sem adivinhar códigos.
- [ ] **Step 2: Testes.** `test_normalize_glim_keeps_original_code`; `test_unknown_code_class_is_null`; `test_invalid_polygons_repaired`; `test_sample_inside_unit_gets_unit_id`; `test_sample_outside_all_units_gets_null`; `test_sample_on_shared_boundary_gets_lowest_unit_id` (determinístico); `test_polygon_touching_antimeridian_matches_points_on_both_sides`.
- [ ] **Step 3: Rodar** `python -m pytest tests/test_glim.py tests/test_join.py -v`. Esperado: FAIL.
- [ ] **Step 4: Implementar** com `GeoDataFrame.sjoin(predicate="within")`, ordenando por `unit_id` para resolver empates.
- [ ] **Step 5: Rodar.** Esperado: PASS.
- [ ] **Step 6: Commit** `git add -A && git commit -m "feat: unidades GLiM e juncao amostra-unidade"`.

### Task 9: Orquestrador e exportação para a web

**Files:**
- Create: `pipeline/build.py`, `pipeline/export.py`
- Test: `tests/test_export.py`, `tests/test_build.py`

**Interfaces:**
- Consumes: todos os módulos das Tasks 1 a 8.
- Produces: `@dataclass ExportResult(files: list[Path], warnings: list[str])`; `export_web(gpkg: Path, out_dir: Path, tippecanoe: str | None) -> ExportResult` (escreve `volcanoes.geojson` e `tectonic_zones.geojson`; com `tippecanoe`, gera `geo_units.pmtiles` e `samples.pmtiles`; avisa em `warnings` se qualquer arquivo passar de 95 MB); CLI `python -m pipeline.build --raw data/raw --out data/out`, incremental pelo hash do manifesto (estado em `data/out/build_state.json`).

- [ ] **Step 1: Testes.** `test_export_writes_geojson_for_small_layers`; `test_export_without_tippecanoe_warns_and_skips_pmtiles`; `test_export_warns_when_file_over_95mb` (usar arquivo sintético sobre o limite via monkeypatch do tamanho); `test_build_skips_source_whose_hash_is_unchanged`; `test_build_reprocesses_source_when_hash_changes`; `test_geojson_nulls_stay_null`.
- [ ] **Step 2: Rodar** `python -m pytest tests/test_export.py tests/test_build.py -v`. Esperado: FAIL.
- [ ] **Step 3: Implementar.** PMTiles via `tippecanoe -o <arquivo>.pmtiles -zg --drop-densest-as-needed -l <camada>`, chamado com `subprocess.run` sem shell. O `build.py` só roda etapas de rede (download, geocodificação) quando o usuário passa `--allow-network`.
- [ ] **Step 4: Rodar.** Esperado: PASS.
- [ ] **Step 5: Gerar dados reais** com os arquivos já autorizados e baixados nas Tasks 3, 4, 6 e 8: `python -m pipeline.build --raw data/raw --out data/out`. Conferir o relatório (amostras descartadas, nomes sem mapeamento) e mostrá-lo ao usuário.
- [ ] **Step 6: Commit** `git add -A && git commit -m "feat: orquestrador incremental e exportacao para a web"`.

### Task 10: Globo base, painel de camadas e estado na URL

**Files:**
- Create: `package.json`, `scripts/vendor.mjs` (copia `maplibre-gl` e `pmtiles` de `node_modules` para `web/vendor/`), `web/index.html`, `web/css/style.css`, `web/js/main.js`, `web/js/map.js`, `web/js/basemaps.js`, `web/js/layers.js`, `web/js/urlstate.js`
- Test: `web/tests/urlstate.test.js`

**Interfaces:**
- Produces: `encodeState(state: AppState) -> string` e `decodeState(hash: string) -> AppState` em `urlstate.js`, onde `AppState = { lng: number, lat: number, zoom: number, layers: string[], filters: { classes: string[], rock: string | null, sources: string[], coordSource: string | null, lithClass: string | null } }`; `createMap(container: HTMLElement, state: AppState) -> maplibregl.Map` em `map.js` (projeção `globe`, escala, coordenadas do cursor); `LAYER_DEFS: {id: string, label: string}[]` e `mountLayerPanel(map, state, onChange) -> void` em `layers.js` (liga/desliga, opacidade, ordem, legenda).

- [ ] **Step 1: Testes que falham.** `test_roundtrip_default_state`; `test_decode_garbage_returns_default_state`; `test_decode_clamps_lat_lon_and_zoom`; `test_unknown_layer_ids_are_dropped`. Rodar `node --test web/tests`. Esperado: FAIL.
- [ ] **Step 2: Implementar `urlstate.js`.** Rodar os testes. Esperado: PASS.
- [ ] **Step 3: Montar a página.** `npm install maplibre-gl pmtiles` (fixar versões exatas), `node scripts/vendor.mjs`, `index.html` com contêiner do mapa e painel. Mapa-base alternável (escuro, relevo, satélite) em `basemaps.js`, com atribuição sempre visível; confirmar os termos de uso de cada provedor com o usuário antes de fixá-los.
- [ ] **Step 4: Conferir no navegador** com um servidor estático (`python -m http.server -d web`): o globo gira, dá zoom até escala local, vira plano em zoom alto, e mover o mapa atualiza a URL.
- [ ] **Step 5: Commit** `git add -A && git commit -m "feat: globo base, painel de camadas e estado na URL"`.

### Task 11: Camadas de dados e filtros

**Files:**
- Create: `web/js/datalayers.js`, `web/js/filters.js`
- Modify: `web/js/main.js`, `web/js/layers.js`
- Test: `web/tests/filters.test.js`

**Interfaces:**
- Consumes: `AppState` e `LAYER_DEFS` (Task 10).
- Produces: `buildSampleFilter(filters: AppState["filters"]) -> unknown[] | null` (expressão MapLibre; `null` quando não há filtro ativo); `addDataLayers(map: maplibregl.Map, base: string, onError: (layerId: string, err: Error) => void) -> void` (registra os protocolos PMTiles; camadas `volcanoes`, `tectonic_zones`, `geo_units`, `samples`; amostras em densidade em zoom baixo e pontos individuais ao aproximar).

- [ ] **Step 1: Testes.** `test_empty_filters_return_null`; `test_class_filter_builds_in_expression`; `test_multiple_filters_combine_with_all`; `test_filter_values_with_quotes_stay_literal`. Rodar `node --test web/tests`. Esperado: FAIL.
- [ ] **Step 2: Implementar `filters.js`.** Rodar. Esperado: PASS.
- [ ] **Step 3: Implementar `datalayers.js`** e ligar ao painel: legenda de cada camada, opacidade, filtro aplicado com `map.setFilter("samples-points", buildSampleFilter(state.filters))`. Falha de carga chama `onError`, que mostra aviso no painel e deixa as demais camadas funcionando.
- [ ] **Step 4: Conferir no navegador** com `data/out` real: ligar e desligar cada camada, aplicar filtros e ver o resultado vazio sem erro no console. Simular falha renomeando temporariamente `samples.pmtiles` e confirmar o aviso.
- [ ] **Step 5: Commit** `git add -A && git commit -m "feat: camadas de dados, filtros e tratamento de falha"`.

### Task 12: Painéis, fluxo de clique e busca

**Files:**
- Create: `web/js/inspector.js`, `web/js/search.js`
- Modify: `web/js/main.js`
- Test: `web/tests/inspector.test.js`, `web/tests/search.test.js`

**Interfaces:**
- Consumes: `AppState`, `buildSampleFilter`.
- Produces: `esc(s: unknown) -> string` (escapa `& < > " '`); `renderSample(props: object) -> string` e `renderUnit(props: object, sampleCount: number) -> string` (HTML; campo nulo vira `não informado`); `parseCoords(text: string) -> { lng: number, lat: number } | null`; `searchIndex(items: { name: string, kind: string, lng: number, lat: number }[], query: string, limit?: number) -> typeof items`.

- [ ] **Step 1: Testes.** `test_esc_escapes_script_and_quotes`; `test_render_sample_escapes_rock_name_with_html` (`<img src=x onerror=1>` não aparece como tag); `test_render_sample_null_fields_show_nao_informado`; `test_render_sample_shows_scale_warning_for_unit`; `test_render_unit_zero_samples_shows_0`; `test_parse_coords_accepts_lat_lon_and_rejects_out_of_range`; `test_parse_coords_garbage_returns_null`; `test_search_is_case_and_accent_insensitive`; `test_search_empty_query_returns_empty`. Rodar `node --test web/tests`. Esperado: FAIL.
- [ ] **Step 2: Implementar** `inspector.js` e `search.js`. Rodar. Esperado: PASS.
- [ ] **Step 3: Ligar o fluxo de clique em `main.js`.** Clique em ponto abre `renderSample` com fonte, licença e link original; clique em unidade abre `renderUnit` com a contagem de amostras; o botão "ver amostras desta litologia" define `filters.lithClass` e destaca os pontos. Conferir no navegador.
- [ ] **Step 4: Commit** `git add -A && git commit -m "feat: paineis, fluxo de clique e busca"`.

### Task 13: Teste de fumaça, README e verificação final

**Files:**
- Create: `tests/e2e/smoke.spec.js`, `playwright.config.js`, `README.md` (atualizar)
- Modify: `package.json` (scripts `test:web` e `test:e2e`)

**Interfaces:**
- Consumes: tudo acima.

- [ ] **Step 1: Escrever `smoke.spec.js`.** Carrega a página; liga e desliga a camada Vulcões e confere a visibilidade; clica num ponto de amostra e confere que o painel traz o nome original da rocha e a fonte; abre uma URL com estado salvo e confere que as camadas e filtros voltam.
- [ ] **Step 2: Rodar** `npx playwright test`. Esperado: PASS. Se falhar, corrigir a causa antes de seguir.
- [ ] **Step 3: Rodar toda a suíte:** `python -m pytest -v` e `node --test web/tests`. Esperado: tudo PASS.
- [ ] **Step 4: README.** Como instalar, como rodar o pipeline e o globo, tabela de fontes com licença e situação (GLiM pendente, CGMW pendente), ferramentas faltantes da Task 1 e o aviso dos 100 MB.
- [ ] **Step 5: Commit** `git add -A && git commit -m "test: fumaca e2e e documentacao"`.

### Task 14 (condicional): Publicação no GitHub Pages

Só começa quando o usuário confirmar por escrito (1) a licença do GLiM para redistribuição ou a decisão de usar apenas o WMS do CGMW, (2) os termos dos mapas-base e (3) que `git push` e a publicação estão autorizados. Nesse momento: adicionar o workflow de Pages, conferir o tamanho de cada arquivo contra o limite de 100 MB e publicar.
