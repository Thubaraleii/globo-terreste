# GeoWorld — vista 3D da abertura do Atlântico Sul (design)

Data: 2026-11-09. Estado: proposta, aguardando revisão.

## 1. Objetivo

Uma segunda página do GeoWorld, `web/rift3d.html`, que continua o Panorama 3D
(https://thubaraleii.github.io/PANORAMA/panorama_3d_taio.html) e mostra em 3D,
de forma interativa, a costa sul do Brasil e a costa sul da África com relevo e
batimetria reais. Um slider e um botão de animar (150 Ma até hoje) juntam e
separam os dois continentes, usando as rotações do modelo de placas já usado no
globo (Merdith et al. 2021, v1.2.4, CC BY 4.0).

Uso: pesquisa científica pessoal, não comercial, sobre a relação tectônica das
rochas máficas e ultramáficas do Brasil e da África com a abertura do Atlântico.
O usuário vai produzir lineamentos em escala continental, que esta página deve
poder receber sem mudança de código.

Critério de sucesso:
- abrir `rift3d.html`, arrastar para girar, aplicar zoom e mover o slider de 0 a 150 Ma
  com os dois continentes se juntando e separando sem travar;
- a rotação aplicada é a mesma do globo (mesmo modelo, mesmos IDs de placa);
- um arquivo de lineamentos novo colocado em `data/curated/lineaments/` aparece na
  vista 3D depois de rodar o pipeline, girando junto com a placa dele;
- nada de terceiros sem licença confirmada vai para o repositório.

## 2. Escopo

Dentro:
- faixa de 20°S a 40°S, da costa brasileira (aprox. 60°W a 40°W) à costa africana
  (aprox. 5°E a 35°E), incluindo a margem continental e o oceano entre elas;
- relevo e batimetria atuais, movidos como blocos rígidos;
- camadas: lineamentos (SGB, CGMW-BRGM e os do usuário) e vulcões (GVP), nas mesmas
  regras de dados locais do globo;
- exagero vertical, vistas oblíqua e planta, link de ida e volta com o globo.

Fora (não será feito agora):
- reconstruir o relevo do passado (o relevo é o atual, só movido);
- amostras GEOROC (a posição delas depende da idade de cada uma, não de um corpo
  rígido contínuo; ficam para uma segunda etapa);
- satélite Esri no repositório (opcional, só carregado ao vivo);
- perfis W→E e S→N, rosetas de direção, poços (existem no Panorama; ficam para depois);
- outras faixas além do Atlântico Sul.

## 3. Dados (pipeline Python)

Novo módulo `pipeline/rift3d.py`, no mesmo estilo de `pipeline/paleo.py`.

1. **Relevo.** Baixa os tiles AWS Terrain Tiles (formato terrarium, zoom 5) que cobrem
   a faixa e monta uma grade de alturas de 0,05° (cerca de 5 km; metros, batimetria
   negativa). Os tiles baixados ficam em `data/raw/` (fora do git). A cor do relevo
   (hipsometria e batimetria) é calculada na página a partir da altura, sem textura
   assada.
2. **Placa por célula.** Cada célula recebe o ID de placa pelos polígonos estáticos
   do modelo (`StaticPolygons/shapes_static_polygons_Merdith_etal.gpml`), como já
   é feito para os vulcões em `plate_ids`. Células sem placa ficam com ID nulo e
   não entram em nenhuma malha.
3. **Rotações.** Para cada placa presente e cada idade de 0 a 150 Ma, de 5 em 5,
   grava o polo (lat, lon) e o ângulo em graus, relativos à placa fixa. A placa fixa
   é a África (o ID é conferido nos polígonos estáticos, não assumido). Se a África
   estiver dividida em mais de uma placa no modelo, a placa fixa é aquela que
   contém a maior área da faixa, e as demais giram em relação a ela.
4. **Saída.** `web/data/rift3d/`:
   - `grid.bin` + `grid.json` (altura em int16, tamanho, origem, passo, ID de placa
     por célula);
   - `rotations.json` (placa, idade, polo, ângulo);
   - `index.json` (crédito e licença do modelo e do relevo, data de geração).

Rastreabilidade: nada inferido; células sem dado ficam nulas; cada arquivo traz
fonte e licença. A licença do AWS Terrain Tiles (SRTM, GEBCO, ETOPO1, entre
outros) deve ser conferida e registrada em `sources.json` antes de publicar.

## 4. Página (`web/rift3d.html` + `web/js/rift3d/`)

Unidades pequenas, com uma função cada:

- `rotation.js`: funções puras. Converte polo e ângulo em quaternion e interpola
  entre quadros de 5 Ma (slerp). É testável com `node --test`.
- `terrain.js`: lê `grid.bin` e monta uma malha por placa, curvada sobre uma esfera
  de raio fixo, com a elevação multiplicada pelo exagero vertical.
- `scene.js`: cena Three.js, câmera orbital, luz, vistas oblíqua e planta.
- `layers.js`: camadas de pontos e linhas (vulcões, amostras, lineamentos) como
  objetos presos ao quaternion da placa de cada feição.
- `controls.js`: slider, botão de animar, exagero vertical, caixas de camadas.

A rotação de cada malha e de cada camada vem do quaternion da placa dela na idade
atual. A África fica parada e a América do Sul se move. Three.js é copiado para
`web/vendor/` (sem CDN), como já é feito com MapLibre.

## 5. Lineamentos do usuário

O formato é o que `pipeline/paleo_lineaments.py` já lê: GeoJSON com
`LineString` ou `MultiLineString`, e `name` e `source` obrigatórios em cada
feição. O usuário coloca os arquivos em `data/curated/lineaments/` e roda o
pipeline; os arquivos saem como `lineaments_<idade>.geojson`, git-ignorados por
padrão, como os do SGB e do BRGM. Cada feição gira pela placa do ponto médio dela.
Feições que cruzam duas placas ficam marcadas com `plates_differ`, e a vista 3D as
mostra com estilo tracejado.

## 6. Publicação e licenças

- Vai para o repositório só código, o modelo e o relevo (depois de confirmar a
  licença do relevo).
- GEOROC (CC BY-SA 4.0, a confirmar), SGB e BRGM continuam locais; a camada
  some sozinha quando o arquivo não existe, como no globo.
- Os lineamentos do usuário seguem a decisão dele: local por padrão.
- O GVP é de uso educacional e não comercial, com citação.

## 7. Limites conhecidos

- O relevo é o atual, só movido; não é paleotopografia.
- Onde o modelo separa a África em várias placas, as malhas podem se sobrepor ou
  deixar vãos. A página mostra isso e não corrige.
- O exagero vertical muda a aparência, não os dados.
- A grade de 5 km é só visual; não serve para medições.

## 8. Testes

- `pytest`: rotações iguais às de `paleo.py` para as mesmas placas e idades; grade
  com dimensões coerentes; células sem placa viram nulo.
- `node --test`: `rotation.js` (identidade em 0 Ma, composição, slerp) e leitura de
  `grid.bin`.
- Conferência visual no navegador: abrir a página, mover o slider de 0 a 150 Ma,
  checar que não há erros no console e que as camadas ligam e desligam.
- `README`: seção nova sobre a vista 3D e o formato dos lineamentos.

## 9. Perguntas em aberto

- Licença exata do relevo (AWS Terrain Tiles) para a publicação no Pages.
- Qual placa do modelo representa a África do Sul e a Namíbia na faixa (a decidir
  depois de olhar os polígonos estáticos).
