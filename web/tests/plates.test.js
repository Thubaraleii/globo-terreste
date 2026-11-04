// Camada "Placas tecnicas": estilo, ordem, estado na URL, painel de detalhes e rotulos.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { LAYER_DEFS, LAYER_IDS } from '../js/layer-defs.js';
import { DEFAULT_STATE, decodeState, encodeState } from '../js/urlstate.js';
import { buildSources, buildLayers, legendItems } from '../js/layerstyles.js';
import { renderPlateBoundary, NAO_INFORMADO } from '../js/inspector.js';
import {
  buildLabelSpecs, labelsVisible, labelMinZoom, LABEL_MAX_ZOOM,
} from '../js/platelabels.js';

const BASE = 'http://localhost/data/';

test('plates: camada conhecida, ligada por padrao, entre as unidades e as zonas', () => {
  assert.ok(LAYER_IDS.includes('plates'));
  assert.equal(LAYER_DEFS.find((d) => d.id === 'plates').label, 'Placas tectônicas');
  assert.ok(DEFAULT_STATE.layers.includes('plates'));
  const i = LAYER_IDS.indexOf('plates');
  assert.ok(LAYER_IDS.indexOf('geo_units') < i && i < LAYER_IDS.indexOf('tectonic_zones'));
  assert.deepEqual(decodeState('#layers=plates,volcanoes').layers, ['plates', 'volcanoes']);
  assert.deepEqual(decodeState(encodeState(DEFAULT_STATE)).layers, DEFAULT_STATE.layers);
});

test('plates: fonte GeoJSON e camada de linha abaixo de tectonic_zones', () => {
  assert.deepEqual(buildSources(BASE).plates, { type: 'geojson', data: `${BASE}plate_boundaries.geojson` });
  const layers = buildLayers();
  const ids = layers.map((l) => l.id);
  assert.ok(ids.indexOf('plates') > ids.indexOf('macrostrat:lines'));
  assert.ok(ids.indexOf('plates') < ids.indexOf('tectonic_zones'));
  const l = layers.find((x) => x.id === 'plates');
  assert.equal(l.type, 'line');
  assert.equal(l.source, 'plates');
  // halo escuro logo abaixo da linha (legibilidade sobre mapas-base claros)
  const casing = layers.find((x) => x.id === 'plates:casing');
  assert.equal(ids.indexOf('plates:casing') + 1, ids.indexOf('plates'));
  assert.equal(casing.source, 'plates');
  assert.ok(casing.paint['line-width'][3] > l.paint['line-width'][3]);
});

test('plates: subducao e destacada por expressao case sobre a propriedade type', () => {
  const l = buildLayers().find((x) => x.id === 'plates');
  for (const prop of ['line-color', 'line-width']) {
    const e = l.paint[prop];
    assert.equal(e[0], 'case', prop);
    assert.deepEqual(e[1], ['==', ['get', 'type'], 'subduction']);
    assert.notDeepEqual(e[2], e[3]);
  }
  // linha fina (a zona laranja, mais grossa, continua mandando)
  assert.ok(l.paint['line-width'][3] <= 1.25);
  assert.ok(l.paint['line-width'][2] < 3);
});

test('plates: legenda tem limite, subducao e a nota das zonas', () => {
  const items = legendItems('plates');
  assert.equal(items.length, 3);
  assert.deepEqual(items.map((i) => i.value), ['boundary', 'subduction', 'zones']);
  assert.ok(items.every((i) => i.shape === 'line' && typeof i.color === 'string'));
  assert.match(items[2].label, /zonas mais ativas/);
});

test('renderPlateBoundary: titulo, tipo, fonte e escape', () => {
  const html = renderPlateBoundary({
    name: 'PA-NA', plate_a: 'PA', plate_b: 'NA', plate_a_name: 'Pacific', plate_b_name: 'North America',
    type: 'subduction', source_id: 'pb2002',
  }, { source: { license: 'Open Data Commons Attribution 1.0', source_url: 'https://github.com/x', institution: 'P. Bird' } });
  assert.match(html, /Limite entre Pacific e North America \(PA-NA\)/);
  assert.match(html, /subducção/);
  assert.match(html, /Open Data Commons Attribution 1\.0/);
  assert.match(html, /<a href="https:\/\/github\.com\/x"/);
});

test('renderPlateBoundary: nulo vira nao informado; tipo vazio nao classificado; HTML escapado', () => {
  const html = renderPlateBoundary({ name: null, plate_a_name: '<img src=x onerror=1>', plate_b_name: null, type: null });
  assert.ok(html.includes(NAO_INFORMADO));
  assert.match(html, /não classificado/);
  assert.ok(!html.includes('<img'));
  assert.ok(html.includes('&lt;img'));
  assert.doesNotThrow(() => renderPlateBoundary(null));
});

const fc = (features) => ({ type: 'FeatureCollection', features });
const pt = (code, name, lng, lat, area_km2 = 1e7) => ({
  type: 'Feature', geometry: { type: 'Point', coordinates: [lng, lat] }, properties: { code, name, area_km2, source_id: 'pb2002' },
});

test('buildLabelSpecs: um rotulo por codigo, nome com fallback ao codigo, invalidos descartados', () => {
  const specs = buildLabelSpecs(fc([
    pt('PA', 'Pacific', -140, 0),
    pt('PA', 'Pacific', 150, 10), // codigo repetido: vale o primeiro
    pt('ZZ', null, 10, 10, null),
    pt('BAD', 'x', 'a', 1),
    { type: 'Feature', geometry: null, properties: { code: 'N', name: 'n' } },
    pt('LON', 'Fora', 200, 0),
    pt('', 'Sem codigo', 1, 1),
  ]));
  assert.deepEqual(specs, [
    { code: 'PA', name: 'Pacific', lng: -140, lat: 0, area: 1e7 },
    { code: 'ZZ', name: 'ZZ', lng: 10, lat: 10, area: null },
  ]);
  assert.deepEqual(buildLabelSpecs(null), []);
  assert.deepEqual(buildLabelSpecs({}), []);
});

test('labelsVisible: so com a camada ligada e abaixo do zoom limite', () => {
  assert.equal(LABEL_MAX_ZOOM, 6);
  assert.equal(labelsVisible(true, 1.5), true);
  assert.equal(labelsVisible(true, 6), true);
  assert.equal(labelsVisible(true, 6.1), false);
  assert.equal(labelsVisible(false, 1.5), false);
  assert.equal(labelsVisible(true, Number.NaN), false);
  // zoom minimo do proprio rotulo
  assert.equal(labelsVisible(true, 2, 3), false);
  assert.equal(labelsVisible(true, 3, 3), true);
});

test('labelMinZoom: placas grandes desde o inicio, pequenas so ao aproximar', () => {
  assert.equal(labelMinZoom(104e6), 0);
  assert.equal(labelMinZoom(12e6), 0);
  assert.equal(labelMinZoom(5e6), 2.5);
  assert.equal(labelMinZoom(2e6), 3.5);
  assert.equal(labelMinZoom(5e5), 4.5);
  assert.equal(labelMinZoom(8e3), 5.5);
  assert.equal(labelMinZoom(null), 3.5); // sem area: nem o maior nem o menor
  assert.equal(labelMinZoom(Number.NaN), 3.5);
  assert.ok(labelMinZoom(1) <= LABEL_MAX_ZOOM);
});
