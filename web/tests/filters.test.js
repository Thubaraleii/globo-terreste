import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildSampleFilter } from '../js/filters.js';

const NONE = { classes: [], rock: null, sources: [], coordSource: null, lithClass: null };
const f = (over) => buildSampleFilter({ ...NONE, ...over });

test('test_empty_filters_return_null', () => {
  assert.equal(buildSampleFilter(NONE), null);
  assert.equal(buildSampleFilter({}), null);
  assert.equal(buildSampleFilter(undefined), null);
});

test('test_class_filter_builds_in_expression', () => {
  assert.deepEqual(f({ classes: ['mafic', 'ultramafic'] }), [
    'in', ['get', 'rock_class'], ['literal', ['mafic', 'ultramafic']],
  ]);
});

test('test_multiple_filters_combine_with_all', () => {
  const expr = f({ classes: ['mafic'], coordSource: 'reported' });
  assert.equal(expr[0], 'all');
  assert.equal(expr.length, 3);
  assert.deepEqual(expr[1], ['in', ['get', 'rock_class'], ['literal', ['mafic']]]);
  assert.deepEqual(expr[2], ['==', ['get', 'coord_source'], 'reported']);
});

test('test_filter_values_with_quotes_stay_literal', () => {
  const nasty = `x"] ), ['get','id'] \\ & é 日本 '`;
  const expr = f({ rock: nasty, sources: [nasty], coordSource: nasty, lithClass: nasty });
  assert.equal(expr[0], 'all');
  const [, rock, sources, coord, lith] = expr;
  // o texto do usuario so aparece como literal, nunca como operador ou parte de um
  assert.deepEqual(rock[1], nasty.trim().toLowerCase());
  assert.deepEqual(sources, ['in', ['get', 'source_id'], ['literal', [nasty]]]);
  assert.deepEqual(coord, ['==', ['get', 'coord_source'], nasty]);
  assert.deepEqual(lith, ['==', ['get', 'unit_lith_class'], nasty]);
  // sobrevive ao round trip JSON (o que o MapLibre recebe)
  assert.deepEqual(JSON.parse(JSON.stringify(expr)), expr);
  // todo operador e uma das palavras conhecidas
  const ops = new Set(['all', 'in', '==', 'get', 'literal', 'downcase', 'to-string', 'coalesce']);
  const walk = (e) => {
    if (!Array.isArray(e)) return;
    if (e[0] === 'literal') return;
    assert.ok(ops.has(e[0]), `operador inesperado: ${e[0]}`);
    e.slice(1).forEach(walk);
  };
  walk(expr);
});

test('test_rock_name_is_case_insensitive_contains', () => {
  assert.deepEqual(f({ rock: '  Basalt ' }), [
    'in', 'basalt',
    ['downcase', ['to-string', ['coalesce', ['get', 'rock_name_original'], '']]],
  ]);
});

test('test_whitespace_only_rock_is_no_filter', () => {
  assert.equal(f({ rock: '' }), null);
  assert.equal(f({ rock: '   \t' }), null);
});

test('test_sources_coord_and_lith_expressions', () => {
  assert.deepEqual(f({ sources: ['a', 'b'] }), ['in', ['get', 'source_id'], ['literal', ['a', 'b']]]);
  assert.deepEqual(f({ coordSource: 'geocoded' }), ['==', ['get', 'coord_source'], 'geocoded']);
  assert.deepEqual(f({ lithClass: 'basic_volcanic' }), ['==', ['get', 'unit_lith_class'], 'basic_volcanic']);
});
