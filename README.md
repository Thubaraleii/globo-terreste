# GeoWorld

Pipeline Python + globo web estático para dados geológicos. Este é o **primeiro recorte** do projeto, com duas camadas de assunto:

- **World Geology**: unidades geológicas (litologia), zonas tectônicas ranqueadas por momento sísmico, vulcões e hotspots.
- **World Rocks**: amostras de rocha (máficas e ultramáficas), com filtros por classe, nome da rocha e origem da coordenada.

O pipeline lê as fontes, normaliza, remove duplicatas e exporta GeoJSON e PMTiles. O globo (MapLibre GL) lê esses arquivos de `web/data/`.

> Estado atual: o código está pronto, mas **nenhuma fonte real foi baixada ainda**. Os testes usam apenas dados sintéticos e fixtures pequenas (veja "O que foi e o que não foi verificado").

## Estrutura

| Pasta | Conteúdo |
|---|---|
| `pipeline/` | Pipeline Python (`python -m pipeline.build`): leitura das fontes, junção, deduplicação, geocodificação, exportação |
| `data/` | `data/curated/` (tabelas curadas à mão: mapeamento de rochas, hotspots), `data/raw/` (downloads, ignorado pelo git), `data/out/` (saída do pipeline) |
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

- A lista `SOURCES` em `pipeline/build.py` está **vazia**: sem fontes registradas o comando só avisa e sai. A ligação das fontes reais (URLs, colunas, licenças) faz parte da fase de aquisição de dados.
- `--allow-network`: permite as etapas de rede (download e geocodificação). Sem a flag, nada acessa a rede.
- `--force`: reprocessa todas as fontes, ignorando o cache.
- `--tippecanoe CAMINHO`: caminho do tippecanoe (padrão: o do PATH). Sem ele, os PMTiles não são gerados.

## Publicar os dados no globo

Copie a saída do pipeline para `web/data/`:

```
data/out/*.geojson   ->  web/data/
data/out/*.pmtiles   ->  web/data/
data/out/sources.json -> web/data/
```

Arquivos esperados pelo globo: `volcanoes.geojson`, `tectonic_zones.geojson`, `sources.json`, `geo_units.pmtiles`, `samples.pmtiles`. Se algum faltar, a camada correspondente mostra um aviso no painel e o resto do globo continua funcionando. `web/data/` é ignorado pelo git; decida a forma de publicação (veja os limites abaixo) antes de versionar dados.

## Rodar o globo localmente

Qualquer servidor estático servindo `web/` serve, por exemplo:

```
.venv/Scripts/python -m http.server 8765 -d web --bind 127.0.0.1
```

e abra `http://127.0.0.1:8765/`. O estado (posição, camadas, filtros) fica no hash da URL.

## Testes

```
.venv/Scripts/python -m pytest -q -W error     # pipeline (Python)
npm run test:web                               # = node --test web/tests (módulos puros e validação do estilo)
npm run test:e2e                               # = playwright test (teste de fumaça no navegador)
```

- O e2e usa o **Microsoft Edge** já instalado (`channel: 'msedge'`); com `GEOWORLD_BROWSER=chrome` usa o Chrome. Ele **não baixa navegador**: não rode `npx playwright install`.
- O e2e sobe um servidor estático próprio em `127.0.0.1:8765`, copia dados **sintéticos** de `tests/e2e/data/` para `web/data/` e remove só o que copiou ao terminar. Se `web/data/` já tiver esses arquivos, ele aborta para não sobrescrevê-los.
- O teste de estilo (`web/tests/style-validate.test.js`) valida as camadas de `buildLayers()` com `@maplibre/maplibre-gl-style-spec`, com controles negativos que provam que o validador rejeita estilos inválidos.
- Não existem PMTiles nos testes (não há tippecanoe aqui): o e2e verifica justamente que a ausência deles mostra o aviso no painel sem quebrar o resto.

## Fontes de dados

| Fonte | Uso | Licença / situação |
|---|---|---|
| GVP (Smithsonian, Global Volcanism Program) | vulcões | Ainda não baixada |
| PB2002 (limites de placas) + catálogo USGS | zonas tectônicas e momento sísmico | Ainda não baixados |
| GEOROC e PetDB/EarthChem | amostras de rocha | Termos de uso a verificar antes de qualquer download em massa |
| GLiM (unidades litológicas) | unidades geológicas | Licença dos dados GIS **não confirmada**: só publicar depois de confirmar. Plano B: apenas o WMS da CGMW |
| CGMW 1:50M (WMS) | plano B para unidades geológicas | Termos para uso em site público a confirmar |
| Macrostrat | complemento | CC-BY 4.0, cobertura parcial, ainda não usado |
| Hotspots de plumas mantélicas | hotspots | Nenhuma lista citável encontrada ainda (o código exige `reference` por linha em `data/curated/hotspots.csv`) |

## Ferramentas (verificadas)

- Python 3.11.9: presente (use `.venv`, dependências em `requirements.txt`)
- Node v24: presente
- tippecanoe: **ausente** (no Windows costuma exigir WSL ou Docker; não instalado), portanto os PMTiles não são gerados aqui
- Microsoft Edge: presente, usado pelo teste e2e (nenhum navegador é baixado)

## Limitações conhecidas

- **Sem tippecanoe**: `geo_units.pmtiles` e `samples.pmtiles` não foram gerados. Instale o tippecanoe via WSL ou Docker para produzi-los.
- **Mapas de fundo**: só o "Fundo liso" está habilitado, até que se escolham provedores de tiles (cujos termos precisam ser confirmados). Os demais ficam ocultos.
- **GitHub Pages**: limite de 100 MB por arquivo; a exportação avisa quando um arquivo passa de 95 MB.
- **Aviso do maplibre-gl** sobre `Popup.setHTML`: não usamos popups; os detalhes são montados com escape de HTML em `web/js/inspector.js`.
- **Latitude e longitude trocadas**, quando ambas ficam dentro do intervalo válido, não podem ser detectadas.
- **Momento sísmico**: calculado com a fórmula `10^(1,5·Mw + 9,1)` N·m (constante USGS/IASPEI).
- **Filtro por litologia**: o realce das amostras só aparece pelo mapa de calor abaixo do zoom 5.
- **Nomes de colunas e códigos do GLiM** são provisórios e devem ser verificados na aquisição; o mesmo vale para `GVP_COLUMNS`.

## O que foi e o que não foi verificado

Verificado: testes Python (pytest) com fixtures; testes Node dos módulos puros; validação do estilo do mapa; teste de fumaça no Edge com **dados sintéticos** (carregamento, ligar/desligar camada, clique e painel de detalhes, Escape e foco, restauração de estado pela URL, aviso de PMTiles ausentes, nome com HTML exibido como texto).

Não verificado: qualquer fonte real (nada foi baixado), geração de PMTiles, desempenho com volumes reais de dados, Chrome/Firefox/Safari e dispositivos móveis.
