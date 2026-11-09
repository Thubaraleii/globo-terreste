import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseGrid, cellLonLat, heightAt, tintForHeight, buildPlateMesh } from '../js/rift3d/terrain.js';

const NODATA = -32768;
const meta = {
  bbox: { lon_min: -1, lon_max: 1, lat_min: -1, lat_max: 1 },
  step_deg: 1, width: 3, height: 3, nodata: NODATA,
  plates: [201, 701], fixed_plate: 701, heights_offset: 0, plates_offset: 18, plates_dtype: 'uint32',
};

// 3x3: colunas 0-1 = placa 201, coluna 2 = placa 701; alturas dadas por linha (norte -> sul)
function makeBuffer(heights, plates) {
  const buf = new ArrayBuffer(9 * 6);
  new Int16Array(buf, 0, 9).set(heights);
  const dv = new DataView(buf);
  plates.forEach((p, k) => dv.setUint32(18 + k * 4, p, true));
  return buf;
}
const P = [201, 201, 701, 201, 201, 701, 201, 201, 701];
const flat = Array(9).fill(100);

test('parseGrid recusa buffer com tamanho errado', () => {
  assert.throws(() => parseGrid(meta, new ArrayBuffer(10)), /tamanho/);
});

test('parseGrid le alturas e placas (placas desalinhadas a 4 bytes)', () => {
  const g = parseGrid(meta, makeBuffer(flat, P));
  assert.equal(g.heights[0], 100);
  assert.deepEqual(Array.from(g.plates), P);
});

test('cellLonLat: i coluna leste, j linha sul', () => {
  assert.deepEqual(cellLonLat(meta, 0, 0), [-1, 1]);
  assert.deepEqual(cellLonLat(meta, 2, 2), [1, -1]);
});

test('heightAt devolve null fora da faixa e em nodata', () => {
  const h = [...flat];
  h[4] = NODATA;
  const g = parseGrid(meta, makeBuffer(h, P));
  assert.equal(heightAt(g, -100, 0), null);
  assert.equal(heightAt(g, 0, 0), null);
  assert.equal(heightAt(g, -1, 1), 100);
});

test('buildPlateMesh: placa de uma coluna so nao gera triangulos', () => {
  const g = parseGrid(meta, makeBuffer(flat, P));
  assert.equal(buildPlateMesh(g, 701, 1).indices.length, 0);
});

test('buildPlateMesh: 2 colunas x 3 linhas validas = 4 triangulos; nodata no centro pula todos os quads', () => {
  const ok = buildPlateMesh(parseGrid(meta, makeBuffer(flat, P)), 201, 1);
  assert.equal(ok.indices.length, 12);
  const h = [...flat];
  h[4] = NODATA;
  const holed = buildPlateMesh(parseGrid(meta, makeBuffer(h, P)), 201, 1);
  assert.equal(holed.indices.length, 0);
});

test('buildPlateMesh: raio cresce com a altura e o exagero, e afunda em batimetria', () => {
  const up = buildPlateMesh(parseGrid(meta, makeBuffer(Array(9).fill(6371), P)), 201, 1);
  const r = (m, k) => Math.hypot(m.positions[3 * k], m.positions[3 * k + 1], m.positions[3 * k + 2]);
  // 6371 m sobre o raio de 6371000 m = +0,001 na escala Terra = 1
  assert.ok(Math.abs(r(up, 0) - 1.001) < 1e-6);
  const down = buildPlateMesh(parseGrid(meta, makeBuffer(Array(9).fill(-3000), P)), 201, 1);
  assert.ok(Math.abs(r(down, 0) - (1 - 3000 / 6371000)) < 1e-6);
  const exag = buildPlateMesh(parseGrid(meta, makeBuffer(Array(9).fill(6371), P)), 201, 3);
  assert.ok(Math.abs(r(exag, 0) - 1.003) < 1e-6);
});

test('buildPlateMesh: cores e posicoes com o mesmo numero de vertices', () => {
  const m = buildPlateMesh(parseGrid(meta, makeBuffer(flat, P)), 201, 1);
  assert.equal(m.colors.length, m.positions.length);
  assert.equal(m.positions.length, 6 * 3); // 6 vertices (2 colunas x 3 linhas)
});

test('tintForHeight: oceano e azul, terra alta e clara', () => {
  const [r0, , b0] = tintForHeight(-3000);
  assert.ok(b0 > r0);
  const [r1, g1, b1] = tintForHeight(4000);
  assert.ok(r1 > 0.6 && g1 > 0.6 && b1 > 0.6);
});
