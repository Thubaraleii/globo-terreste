// Valida o estilo completo (fontes + camadas de buildLayers) com o validador oficial
// da especificacao de estilos do MapLibre, para pegar expressoes invalidas sem navegador.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { validateStyleMin } from '@maplibre/maplibre-gl-style-spec';
import { buildSources, buildLayers } from '../js/layerstyles.js';
import { buildSampleFilter } from '../js/filters.js';
import { baseStyle } from '../js/basemaps.js';

function fullStyle(sampleFilter) {
  const base = baseStyle();
  return {
    ...base,
    sources: buildSources('http://127.0.0.1:8765/data/'),
    layers: [...base.layers, ...buildLayers(sampleFilter)],
  };
}

const fmt = (errors) => errors.map((e) => e.message).join('\n');

test('estilo completo sem filtro e valido', () => {
  const errors = validateStyleMin(fullStyle(null));
  assert.equal(errors.length, 0, fmt(errors));
});

test('estilo completo com filtro de amostras e valido', () => {
  const filter = buildSampleFilter({
    classes: ['mafic'], rock: 'basalto', sources: ['georoc'], coordSource: 'reported', lithClass: 'basic_volcanic',
  });
  assert.ok(filter, 'o filtro deveria existir');
  const errors = validateStyleMin(fullStyle(filter));
  assert.equal(errors.length, 0, fmt(errors));
});

test('controle negativo: expressao invalida e detectada', () => {
  const style = fullStyle(null);
  const layer = style.layers.find((l) => l.id === 'volcanoes');
  layer.paint['circle-radius'] = ['match', ['get', 'kind'], 'hotspot']; // sem valor padrao
  const errors = validateStyleMin(style);
  assert.ok(errors.length > 0, 'o validador deveria rejeitar a expressao');
});

test('controle negativo: camada apontando para fonte inexistente e detectada', () => {
  const style = fullStyle(null);
  style.layers.find((l) => l.id === 'volcanoes').source = 'nao_existe';
  assert.ok(validateStyleMin(style).length > 0);
});
