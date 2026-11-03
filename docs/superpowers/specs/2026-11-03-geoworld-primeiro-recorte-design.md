# GeoWorld: primeiro recorte (globo, World Geology e World Rocks)

Data: 2026-11-03
Repositório: `Thubaraleii/geoworld` (pasta local `C:\Users\thuba\Desktop\09_Geo World`)
Projeto independente do painel de geodiversidade (`08_stefany`). Nada é reaproveitado dele.

## 1. Objetivo

Um globo terrestre interativo, publicado como site estático, no estilo dos webmaps (zoom contínuo, controle de camadas). Ele reúne duas camadas de conhecimento:

- **World Geology (camada espacial):** onde estão as unidades geológicas, os vulcões e as zonas tectônicas mais ativas.
- **World Rocks (camada petrográfica):** o catálogo de rochas. Neste recorte contém apenas amostras de rochas máficas e ultramáficas ígneas, geocodificadas a partir de bases geoquímicas.

Sucesso do recorte: o usuário gira o globo, liga e desliga as quatro camadas, filtra as amostras e clica num ponto, numa unidade ou numa litologia, navegando de um para o outro. Todo dado mostrado tem fonte, licença e escala rastreáveis.

## 2. Fora do escopo (specs futuras)

- Mapas geológicos nacionais e continentais (OneGeology, serviços geológicos).
- Banco PostGIS e servidor.
- Fotografias, mineralogia, composição química e textura das rochas.
- Rochas sedimentares e metamórficas, e estratigrafia detalhada.
- Geocodificador externo dentro do navegador.

## 3. Regras de rastreabilidade (valem para todo o projeto)

1. Nunca inventar dado geológico, coordenada, geometria, litologia ou idade.
2. Campo sem informação confirmada fica nulo e aparece como "não informado".
3. Todo registro leva: instituição responsável, `source_id`, `source_url`, licença, data de aquisição e escala original.
4. A nomenclatura original das unidades e rochas é preservada.
5. Dados originais ficam intactos. Camadas harmonizadas são geradas à parte.
6. Mapas de escalas diferentes não são misturados na mesma camada.
7. Dado interpretado e dado observacional são identificados separadamente.
8. Uma unidade geológica não é uma amostra petrográfica documentada.

## 4. Camadas e fontes

### 4.1 Vulcões
- Fonte: lista de vulcões holocênicos do Smithsonian GVP (coordenadas, tipo, última erupção).
- Hotspots no sentido de plumas do manto: o GVP não os traz. Entram como lista curada separada, com referência da literatura registrada. A lista só é incluída depois de localizada uma fonte citável.

### 4.2 Top 30 zonas tectônicas
- Não há ranking pronto. Construímos um: catálogo sísmico do USGS cruzado com os segmentos de limites de placas do modelo PB2002.
- Métrica padrão: momento sísmico liberado por segmento no período escolhido. O popup mostra a métrica e o período. A métrica pode ser trocada (por exemplo, taxa de deslizamento) sem mudar a estrutura.

### 4.3 Amostras máficas e ultramáficas ígneas (World Rocks)
- Fontes: GEOROC e PetDB/EarthChem. Termos e formatos de acesso são verificados antes de cada download.
- Os registros já trazem latitude e longitude. O trabalho principal é validar e normalizar.
- Geocodificação de nome de local para coordenada só ocorre em registros sem coordenada. Esses ficam com `coord_source = geocoded` e a incerteza registrada. Os demais ficam com `coord_source = reported`.
- Classificação: o nome original da rocha é guardado em `rock_name_original`. A classe (`mafic` ou `ultramafic`) vem de uma tabela de mapeamento versionada (basalto, gabro, diabásio, peridotito, dunito, piroxenito, komatiito, entre outros). Nome sem mapeamento fica com classe nula e não entra nos filtros por classe.
- Duplicatas: GEOROC e PetDB se sobrepõem. Os registros equivalentes são ligados por um identificador de grupo e não são apagados.

### 4.4 Base geológica (World Geology)
- Principal: GLiM (Global Lithological Map), que é mundial e vetorial, com classes litológicas. Licença do dado GIS ainda não confirmada. A publicação no GitHub Pages depende dessa confirmação.
- Alternativa visual: CGMW 1:50M via WMS (serviço consumido pelo navegador, sem redistribuir o dado). Termos de uso em site público a confirmar.
- Macrostrat (CC-BY 4.0, cobertura parcial) é complementar. Não é a base.
- Cada amostra recebe o identificador da unidade GLiM que a contém (ponto em polígono). O painel exibe o aviso de que a escala média é cerca de 1:3,75 milhões.

## 5. Modelo de dados

Armazenamento canônico: um GeoPackage em `data/out/`. Dele são gerados os arquivos que o globo consome.

| Entidade | Conteúdo principal |
|---|---|
| `sources` | `source_id`, instituição, `source_url`, licença, atribuição, data de aquisição, escala original |
| `samples` | `id`, `rock_name_original`, `rock_class`, `coord_source`, `coord_uncertainty_m`, `unit_id`, `dup_group`, `source_id`, geometria (ponto) |
| `geo_units` | `unit_id`, nome ou classe litológica original, classe harmonizada, `source_id`, geometria (polígono) |
| `volcanoes` | nome, tipo, última erupção, país, `source_id`, geometria |
| `tectonic_zones` | posição no ranking, nome, métrica, período, `source_id`, geometria |

Campos sem confirmação são nulos. Identificadores são estáveis entre execuções do pipeline.

## 6. Pipeline (Python)

Estrutura de pastas:
```
pipeline/    um módulo por fonte (gvp, usgs_pb2002, georoc, petdb, glim)
data/raw/    downloads originais, fora do git; versionado só o manifesto (URL, data, hash, licença)
data/out/    GeoPackage e arquivos finais para o globo
web/         o globo (estático)
tests/       testes do pipeline e do globo
docs/        specs e planos
```

Etapas por fonte: download quando permitido, verificação de integridade (hash), padronização do sistema de referência para WGS84, harmonização de atributos, validação e reparo de geometrias inválidas, identificação de duplicatas, registro de metadados e licença, e geração dos arquivos de saída. Execução incremental: reprocessa apenas fontes cujo arquivo mudou.

Bibliotecas: GeoPandas, Shapely, PyProj, Requests, GDAL/OGR (via Fiona/pyogrio), e `tippecanoe` ou equivalente para gerar PMTiles.

Saídas para o web: `volcanoes.geojson` e `tectonic_zones.geojson` (poucos registros); `geo_units.pmtiles` e `samples.pmtiles` (volume grande).

## 7. O globo (web/)

Tecnologia: MapLibre GL JS em projeção de globo, protocolo PMTiles, JavaScript puro com módulos, sem framework.

Componentes:
- **Mapa:** esfera 3D com zoom contínuo até a escala local, passando a mapa plano em zoom alto. Mapa-base alternável (escuro, relevo, satélite). Escala e coordenadas do cursor.
- **Painel de camadas:** liga/desliga, opacidade, ordem e legenda para Vulcões, Zonas tectônicas, Unidades geológicas e Amostras.
- **Filtros das amostras:** classe, nome original da rocha, fonte e tipo de coordenada. Idade só entra se a fonte trouxer.
- **Busca:** por nome de vulcão, zona ou unidade, e por coordenadas digitadas. Sem geocodificador externo.
- **Estado na URL:** posição, camadas ativas e filtros ficam no link.
- **Clusters:** em zoom baixo, as amostras aparecem agregadas (densidade) e viram pontos ao aproximar.

Fluxo de clique:
1. **Ponto de amostra:** painel com nome original da rocha, classe, fonte, tipo e incerteza da coordenada, licença e link para o dado original. Mostra a unidade GLiM que o contém, com o aviso de escala.
2. **Unidade:** painel com a litologia e o número de amostras dentro dela.
3. **"Ver amostras desta litologia":** aplica o filtro e destaca os pontos correspondentes.

Falhas: camada que não carrega mostra aviso no painel e o resto continua funcionando. Campo nulo aparece como "não informado".

Publicação: GitHub Pages, após confirmação das licenças (seção 9).

## 8. Testes

- **Pipeline (pytest):** amostras pequenas fixas em `tests/fixtures/` cobrindo mapeamento de rochas, deduplicação, ponto em polígono, reparo de geometrias e preservação de nulos.
- **Globo (Playwright):** teste de fumaça: carrega a página, liga e desliga uma camada, clica num ponto e confere o conteúdo do painel.
- Cada fonte nova só é considerada integrada com um teste que comprove a preservação de fonte, licença e escala.

## 9. Riscos e pendências

1. **Licença do GLiM:** o dado GIS não tem licença explícita nos resultados da pesquisa. Precisa ser esclarecida com os autores ou na página de origem antes de publicar. Plano B: servir só o WMS do CGMW como fundo e manter o GLiM apenas local.
2. **Termos do WMS do CGMW em site público:** a confirmar.
3. **Hotspots de plumas:** falta localizar uma lista citável.
4. **Volume e tamanho dos arquivos:** o GitHub Pages limita arquivos a 100 MB. Se `samples.pmtiles` ou `geo_units.pmtiles` passar disso, será dividido ou hospedado em outro lugar.
5. **Termos de uso e acesso programático de GEOROC e PetDB:** a verificar antes de qualquer download em massa.
6. **Escala do GLiM:** a associação amostra-unidade é aproximada. O painel sempre exibe o aviso.
7. **Ranking tectônico:** a métrica é uma escolha metodológica e deve ser documentada no próprio globo.

## 10. Ordem sugerida de implementação (detalhada no plano)

1. Esqueleto do projeto, manifesto de fontes e GeoPackage vazio com o modelo.
2. Camada de vulcões (GVP) e globo mínimo com painel de camadas.
3. Zonas tectônicas (USGS e PB2002).
4. Base geológica (GLiM, após confirmar a licença).
5. Amostras (GEOROC e PetDB), mapeamento de rochas, deduplicação e ligação com as unidades.
6. Filtros, busca, estado na URL e fluxo de clique entre as camadas.
7. Publicação no GitHub Pages.
