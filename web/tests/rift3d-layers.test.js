import { test } from 'node:test';
import assert from 'node:assert/strict';
import { groupByPlate, lineVertices, pointVertex } from '../js/rift3d/layers.js';
import { parseGrid } from '../js/rift3d/terrain.js';

const NODATA = -32768;
const meta = {
  bbox: { lon_min: -1, lon_max: 1, lat_min: -1, lat_max: 1 },
  step_deg: 1, width: 3, height: 3, nodata: NODATA,
  plates: [201], fixed_plate: 701, heights_offset: 0, plates_offset: 18, plates_dtype: 'uint32',
};
const buf = new ArrayBuffer(54);
new Int16Array(buf, 0, 9).fill(100);
const grid = parseGrid(meta, buf);
const radius = (v, k = 0) => Math.hypot(v[3 * k], v[3 * k + 1], v[3 * k + 2]);
const terrainR = 1 + (40 * 100) / 6371000;

const feat = (plate, extra = {}) => ({ type: 'Feature', properties: { name: 'x', source: 's', plate_id: plate }, geometry: null, ...extra });

test('groupByPlate separa por placa e descarta placa sem rotacao', () => {
  const fc = { features: [feat(201), feat(701), feat(201), feat(555)] };
  const { byPlate, skipped } = groupByPlate(fc, { 201: [], 701: [] });
  assert.equal(byPlate.get(201).length, 2);
  assert.equal(byPlate.get(701).length, 1);
  assert.equal(skipped, 1);
});

test('groupByPlate descarta feicao sem plate_id', () => {
  const fc = { features: [feat(201), { type: 'Feature', properties: { name: 'y' }, geometry: null }, feat('201')] };
  const { byPlate, skipped } = groupByPlate(fc, { 201: [] });
  assert.equal(byPlate.get(201).length, 1);
  assert.equal(skipped, 2);
});

test('lineVertices fica acima do relevo e usa 0 m fora da grade', () => {
  const f = feat(201, { geometry: { type: 'MultiLineString', coordinates: [[[-1, 1], [0, 0], [1.4, -1]]] } });
  const [line] = lineVertices(f, grid, 40);
  assert.ok(radius(line, 0) > terrainR);
  assert.ok(radius(line, 0) - terrainR < 0.001);
  // (1.4, -1) arredonda para a coluna 1 (dentro): usa a altura da celula; um ponto bem fora usa 0 m
  const far = feat(201, { geometry: { type: 'MultiLineString', coordinates: [[[0, 0], [5, 0]]] } });
  const [l2] = lineVertices(far, grid, 40);
  assert.ok(Math.abs(radius(l2, 1) - 1.0004) < 1e-6);
});

test('lineVertices descarta linha toda fora da faixa', () => {
  const f = feat(201, { geometry: { type: 'MultiLineString', coordinates: [[[50, 50], [51, 51]]] } });
  assert.deepEqual(lineVertices(f, grid, 40), []);
});

test('pointVertex devolve null para ponto sem coordenada valida ou fora da faixa', () => {
  assert.equal(pointVertex({ geometry: { type: 'Point', coordinates: [null, 3] } }, grid, 40), null);
  assert.equal(pointVertex({ geometry: null }, grid, 40), null);
  assert.equal(pointVertex({ geometry: { type: 'Point', coordinates: [50, 50] } }, grid, 40), null);
  const v = pointVertex({ geometry: { type: 'Point', coordinates: [0, 0] } }, grid, 40);
  assert.ok(Math.hypot(...v) > terrainR);
});
