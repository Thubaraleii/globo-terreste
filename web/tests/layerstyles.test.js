import { test } from 'node:test';
import assert from 'node:assert/strict';
import { LAYER_IDS } from '../js/layer-defs.js';
import {
  buildSources, buildLayers, LITH_COLORS, ROCK_CLASS_COLORS, legendItems,
} from '../js/layerstyles.js';

const BASE = 'http://localhost/data/';
const layers = buildLayers();

test('test_layer_ids_follow_convention', () => {
  const ids = layers.map((l) => l.id);
  assert.equal(new Set(ids).size, ids.length);
  for (const id of ids) {
    assert.ok(LAYER_IDS.includes(id.split(':')[0]), `prefixo desconhecido: ${id}`);
  }
  for (const want of ['volcanoes', 'tectonic_zones', 'geo_units', 'geo_units:outline', 'samples:density', 'samples:points']) {
    assert.ok(ids.includes(want), want);
  }
});

test('test_every_layer_has_a_source_and_every_logical_layer_a_source', () => {
  const sources = buildSources(BASE);
  for (const l of layers) assert.ok(sources[l.source], `${l.id} sem fonte`);
  for (const id of LAYER_IDS) assert.ok(sources[id], `fonte ${id}`);
  assert.equal(sources.volcanoes.type, 'geojson');
  assert.equal(sources.geo_units.url, `pmtiles://${BASE}geo_units.pmtiles`);
  assert.equal(sources.samples.type, 'vector');
  for (const l of layers.filter((x) => sources[x.source].type === 'vector')) {
    assert.equal(l['source-layer'], l.source);
  }
});

function matches(expr) {
  const found = [];
  const walk = (e) => {
    if (!Array.isArray(e)) return;
    if (e[0] === 'match') found.push(e);
    e.forEach(walk);
  };
  walk(expr);
  return found;
}

test('test_match_expressions_have_default', () => {
  let n = 0;
  for (const l of layers) {
    for (const group of [l.paint ?? {}]) {
      for (const expr of Object.values(group)) {
        for (const m of matches(expr)) {
          n += 1;
          // ['match', input, (rotulo, saida)*, default] => comprimento impar
          assert.equal(m.length % 2, 1, `${l.id}: match sem default`);
        }
      }
    }
  }
  assert.ok(n >= 3);
});

test('test_hotspots_differ_from_volcanoes_by_kind', () => {
  const v = layers.find((l) => l.id === 'volcanoes');
  assert.ok(JSON.stringify(v.paint).includes('hotspot'));
  assert.ok(JSON.stringify(v.paint).includes('"kind"'));
});

test('test_samples_density_low_zoom_points_high_zoom', () => {
  const d = layers.find((l) => l.id === 'samples:density');
  const p = layers.find((l) => l.id === 'samples:points');
  assert.equal(d.type, 'heatmap');
  assert.equal(p.type, 'circle');
  assert.ok(d.maxzoom > p.minzoom - 1 && p.minzoom > 0 && d.maxzoom <= 10);
  assert.ok(JSON.stringify(p.paint['circle-stroke-width']).includes('geocoded'));
});

test('test_legend_items_match_colour_tables', () => {
  assert.deepEqual(legendItems('geo_units').map((i) => i.value), LITH_COLORS.map(([v]) => v));
  const samples = legendItems('samples');
  for (const [v, c] of ROCK_CLASS_COLORS) {
    assert.ok(samples.some((i) => i.value === v && i.color === c));
  }
  for (const id of LAYER_IDS) {
    const items = legendItems(id);
    assert.ok(items.length > 0, id);
    for (const it of items) assert.ok(it.label && it.color, `${id}: item incompleto`);
  }
});

test('test_samples_layers_accept_filter_and_start_from_given_filter', () => {
  const withF = buildLayers(['==', ['get', 'coord_source'], 'reported']);
  for (const l of withF.filter((x) => x.id.startsWith('samples:'))) {
    assert.deepEqual(l.filter, ['==', ['get', 'coord_source'], 'reported']);
  }
  for (const l of layers.filter((x) => x.id.startsWith('samples:'))) assert.equal(l.filter, undefined);
});
