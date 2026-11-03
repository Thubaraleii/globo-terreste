import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseCoords, searchIndex, buildSearchItems } from '../js/search.js';

test('test_parse_coords_accepts_lat_lon_and_rejects_out_of_range', () => {
  assert.deepEqual(parseCoords('-22.95, -43.21'), { lng: -43.21, lat: -22.95 });
  assert.deepEqual(parseCoords('  19.4 -155.3 '), { lng: -155.3, lat: 19.4 });
  assert.deepEqual(parseCoords('10,20'), { lng: 20, lat: 10 });
  assert.deepEqual(parseCoords('+90 180'), { lng: 180, lat: 90 });
  assert.deepEqual(parseCoords('-90, -180'), { lng: -180, lat: -90 });
  assert.deepEqual(parseCoords('.5 -.5'), { lng: -0.5, lat: 0.5 });
  assert.equal(parseCoords('90.0001, 0'), null);
  assert.equal(parseCoords('-91 0'), null);
  assert.equal(parseCoords('0 180.5'), null);
  assert.equal(parseCoords('0, -181'), null);
});

test('test_parse_coords_garbage_returns_null', () => {
  for (const bad of ['', '   ', 'abc', 'Etna', '10', '10 20 30', '10, 20, 30', '10,,20',
    'NaN NaN', 'Infinity 0', '1e1 2', '0x10 5', '-22,5 -43,2', '10 20abc', '10;20',
    '- 10 20', null, undefined, 42, {}]) {
    assert.equal(parseCoords(bad), null, `deveria rejeitar ${JSON.stringify(bad)}`);
  }
});

const ITEMS = [
  { name: 'Teide', kind: 'volcano', lng: -16.6, lat: 28.3 },
  { name: 'Monte Sintético Ãçé', kind: 'volcano', lng: 1, lat: 1 },
  { name: 'Etna', kind: 'volcano', lng: 15, lat: 37.7 },
  { name: 'Zona de Subducção Andina', kind: 'tectonic_zone', lng: -70, lat: -20 },
  { name: 'Grande Etnia', kind: 'volcano', lng: 2, lat: 2 },
  { name: 'Etnaville', kind: 'hotspot', lng: 3, lat: 3 },
];

test('test_search_is_case_and_accent_insensitive', () => {
  assert.deepEqual(searchIndex(ITEMS, 'sintetico aCE').map((i) => i.name), ['Monte Sintético Ãçé']);
  assert.deepEqual(searchIndex(ITEMS, 'SUBDUCCAO').map((i) => i.name), ['Zona de Subducção Andina']);
  assert.deepEqual(searchIndex(ITEMS, 'ZONA').map((i) => i.name), ['Zona de Subducção Andina']);
});

test('test_search_prefix_before_substring_and_stable', () => {
  // prefixo primeiro (na ordem original), depois substring
  assert.deepEqual(searchIndex(ITEMS, 'etn').map((i) => i.name), ['Etna', 'Etnaville', 'Grande Etnia']);
  assert.deepEqual(searchIndex(ITEMS, 'etn', 2).map((i) => i.name), ['Etna', 'Etnaville']);
  assert.deepEqual(searchIndex(ITEMS, 'zzz'), []);
});

test('test_search_empty_query_returns_empty', () => {
  assert.deepEqual(searchIndex(ITEMS, ''), []);
  assert.deepEqual(searchIndex(ITEMS, '   '), []);
  assert.deepEqual(searchIndex(ITEMS, null), []);
  assert.deepEqual(searchIndex(null, 'etna'), []);
  // itens sem nome texto sao ignorados
  assert.deepEqual(searchIndex([{ name: null, kind: 'volcano', lng: 0, lat: 0 }], 'n'), []);
});

test('test_build_search_items_from_geojson', () => {
  const volcanoes = {
    type: 'FeatureCollection',
    features: [
      { type: 'Feature', properties: { name: 'Etna', kind: 'volcano' }, geometry: { type: 'Point', coordinates: [15, 37.7] } },
      { type: 'Feature', properties: { name: null, kind: 'volcano' }, geometry: { type: 'Point', coordinates: [1, 1] } },
      { type: 'Feature', properties: { name: 'Sem geometria' }, geometry: null },
      { type: 'Feature', properties: { name: 'Havaí', kind: 'hotspot' }, geometry: { type: 'Point', coordinates: [-155, 19] } },
    ],
  };
  const zones = {
    type: 'FeatureCollection',
    features: [
      { type: 'Feature', properties: { name: 'Zona A', rank: 1 },
        geometry: { type: 'MultiLineString', coordinates: [[[0, 0], [10, 4]], [[2, -2], [4, 6]]] } },
    ],
  };
  const items = buildSearchItems(volcanoes, zones);
  assert.equal(items.length, 3);
  assert.deepEqual(items.map((i) => [i.name, i.kind, i.layer]), [
    ['Etna', 'volcano', 'volcanoes'], ['Havaí', 'hotspot', 'volcanoes'], ['Zona A', 'tectonic_zone', 'tectonic_zones'],
  ]);
  assert.deepEqual([items[0].lng, items[0].lat], [15, 37.7]);
  assert.deepEqual(items[2].bbox, [0, -2, 10, 6]);
  assert.deepEqual([items[2].lng, items[2].lat], [5, 2]);
  assert.equal(items[2].props.rank, 1);
  assert.deepEqual(buildSearchItems(null, { features: 'x' }), []);
});

const line = (name, coords) => ({ type: 'Feature', properties: { name }, geometry: { type: 'LineString', coordinates: coords } });

test('test_zone_centre_wraps_across_antimeridian', () => {
  const zones = { type: 'FeatureCollection', features: [line('Tonga', [[178, -20], [179.5, -21], [-179.5, -22], [-178, -23]])] };
  const [item] = buildSearchItems(null, zones);
  assert.ok(Math.abs(Math.abs(item.lng) - 180) < 1, `centro ${item.lng} deveria ficar perto de ±180`);
  assert.ok(item.lng >= -180 && item.lng <= 180);
  assert.equal(item.lat, -21.5);
  // trecho so a oeste do antimeridiano visto do leste: 175..-170 -> centro 182.5 -> -177.5
  const [b] = buildSearchItems(null, { features: [line('B', [[175, 0], [-170, 1]])] });
  assert.equal(b.lng, -177.5);
});

test('test_zone_centre_unchanged_for_normal_zone', () => {
  const zones = { type: 'FeatureCollection', features: [line('Andes', [[-75, -40], [-70, -20], [-65, 0]])] };
  const [item] = buildSearchItems(null, zones);
  assert.equal(item.lng, -70);
  assert.equal(item.lat, -20);
  // linha larga que nao cruza ±180 (nenhum salto > 180 entre vertices, nao toca ±180)
  const [w] = buildSearchItems(null, { features: [line('W', [[-100, 0], [0, 0], [100, 0]])] });
  assert.equal(w.lng, 0);
});

test('test_zone_split_at_antimeridian_centre_near_180', () => {
  const split = {
    type: 'Feature',
    properties: { name: 'Fiji' },
    geometry: { type: 'MultiLineString', coordinates: [[[176, -15], [180, -16]], [[-180, -16], [-176, -17]]] },
  };
  const [item] = buildSearchItems(null, { features: [split] });
  assert.ok(Math.abs(Math.abs(item.lng) - 180) < 1e-9, `centro ${item.lng}`);
});
