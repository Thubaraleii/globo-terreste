import { test } from 'node:test';
import assert from 'node:assert/strict';
import { nextAge, ageLabel } from '../js/paleo.js';

const AGES = [0, 5, 10, 15];

test('test_nextAge_walks_from_past_to_present_and_loops', () => {
  assert.equal(nextAge(AGES, 15), 10);
  assert.equal(nextAge(AGES, 10), 5);
  assert.equal(nextAge(AGES, 5), 0);
  assert.equal(nextAge(AGES, 0), 15);
});

test('test_nextAge_unknown_age_restarts_at_oldest', () => {
  assert.equal(nextAge(AGES, 7), 15);
});

test('test_ageLabel', () => {
  assert.equal(ageLabel(0), 'Hoje (0 Ma)');
  assert.equal(ageLabel(150), '150 milhões de anos atrás');
});
