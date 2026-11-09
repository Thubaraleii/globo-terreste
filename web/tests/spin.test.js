import { test } from 'node:test';
import assert from 'node:assert/strict';
import { nextLng } from '../js/spin.js';

test('test_nextLng_advances_by_rate_times_dt', () => {
  assert.equal(nextLng(0, 1, 6), 6);
  assert.equal(nextLng(10, 0.5, 6), 13);
});

test('test_nextLng_wraps_at_antimeridian', () => {
  assert.equal(nextLng(179, 1, 6), -175);
  assert.equal(nextLng(-180, 0, 6), -180);
});
