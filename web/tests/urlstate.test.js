import { test } from 'node:test';
import assert from 'node:assert/strict';
import { encodeState, decodeState, DEFAULT_STATE } from '../js/urlstate.js';

test('test_roundtrip_default_state', () => {
  assert.deepEqual(decodeState(encodeState(DEFAULT_STATE)), DEFAULT_STATE);
  assert.deepEqual(decodeState('#' + encodeState(DEFAULT_STATE)), DEFAULT_STATE);
  assert.deepEqual(decodeState(''), DEFAULT_STATE);
});

test('test_roundtrip_state_with_filters_and_odd_characters', () => {
  const state = {
    lng: -46.6333,
    lat: -23.5505,
    zoom: 7.25,
    layers: ['volcanoes', 'samples'],
    filters: {
      classes: ['basalto', 'riólito & co'],
      rock: 'Olivine "tholeiite" #1 = x&y',
      sources: ['GEOROC', 'PetDB'],
      coordSource: 'publicada',
      lithClass: 'vb',
    },
  };
  assert.deepEqual(decodeState('#' + encodeState(state)), state);
});

test('test_decode_garbage_returns_default_state', () => {
  for (const g of ['%%%', '#lng=abc&lat=&zoom=xyz', '====&&&', '#\u0000￿']) {
    assert.deepEqual(decodeState(g), DEFAULT_STATE, g);
  }
});

test('test_decode_clamps_lat_lon_and_zoom', () => {
  const s = decodeState('#lng=500&lat=-123&zoom=99');
  assert.equal(s.lng, 180);
  assert.equal(s.lat, -90);
  assert.equal(s.zoom, 22);
  const t = decodeState('#lng=-500&lat=123&zoom=-4');
  assert.equal(t.lng, -180);
  assert.equal(t.lat, 90);
  assert.equal(t.zoom, 0);
});

test('test_unknown_layer_ids_are_dropped', () => {
  const s = decodeState('#layers=volcanoes,bogus,samples,__proto__');
  assert.deepEqual(s.layers, ['volcanoes', 'samples']);
});
