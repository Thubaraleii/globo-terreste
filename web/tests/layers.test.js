import { test } from 'node:test';
import assert from 'node:assert/strict';
import { moveItem, raiseAbove } from '../js/layer-defs.js';

test('test_raise_above_moves_only_when_below', () => {
  assert.deepEqual(raiseAbove(['s', 'a', 'g', 'v'], 's', 'g'), ['a', 'g', 's', 'v']);
  assert.deepEqual(raiseAbove(['g', 'a', 's', 'v'], 's', 'g'), ['g', 'a', 's', 'v']);
  assert.deepEqual(raiseAbove(['a', 'b'], 'zz', 'a'), ['a', 'b']);
  const o = ['s', 'g'];
  raiseAbove(o, 's', 'g');
  assert.deepEqual(o, ['s', 'g']);
});

test('test_move_item_up_and_down', () => {
  assert.deepEqual(moveItem(['a', 'b', 'c'], 'a', +1), ['b', 'a', 'c']);
  assert.deepEqual(moveItem(['a', 'b', 'c'], 'c', -1), ['a', 'c', 'b']);
});

test('test_move_item_at_edges_or_unknown_returns_same_order', () => {
  assert.deepEqual(moveItem(['a', 'b'], 'b', +1), ['a', 'b']);
  assert.deepEqual(moveItem(['a', 'b'], 'a', -1), ['a', 'b']);
  assert.deepEqual(moveItem(['a', 'b'], 'zz', +1), ['a', 'b']);
});

test('test_move_item_does_not_mutate_input', () => {
  const o = ['a', 'b'];
  moveItem(o, 'a', +1);
  assert.deepEqual(o, ['a', 'b']);
});
