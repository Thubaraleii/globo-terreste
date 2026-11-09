import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadRift3d } from '../js/rift3d/load.js';

const meta = {
  bbox: { lon_min: -1, lon_max: 1, lat_min: -1, lat_max: 1 },
  step_deg: 1, width: 3, height: 3, nodata: -32768,
  plates: [201], fixed_plate: 701, heights_offset: 0, plates_offset: 18, plates_dtype: 'uint32',
};
const index = { model: { name: 'm', licence: 'l' }, terrain: 't' };

function fakeFetch(files) {
  return async (url) => {
    const name = url.split('/').pop();
    if (!(name in files)) return { ok: false, status: 404 };
    const body = files[name];
    return { ok: true, status: 200, json: async () => body, arrayBuffer: async () => body };
  };
}

test('loadRift3d devolve grade, rotacoes e indice quando tudo bate', async () => {
  const f = fakeFetch({ 'grid.json': meta, 'rotations.json': { 201: [] }, 'index.json': index, 'grid.bin': new ArrayBuffer(54) });
  const d = await loadRift3d(f, 'data/rift3d/');
  assert.equal(d.grid.heights.length, 9);
  assert.deepEqual(Object.keys(d.rotations), ['201']);
});

test('loadRift3d rejeita grid.bin desatualizado com mensagem clara (nao pagina em branco)', async () => {
  const f = fakeFetch({ 'grid.json': meta, 'rotations.json': {}, 'index.json': index, 'grid.bin': new ArrayBuffer(10) });
  await assert.rejects(loadRift3d(f, 'data/rift3d/'), /tamanho inesperado.*pipeline\.rift3d/s);
});

test('loadRift3d rejeita index.json sem model', async () => {
  const f = fakeFetch({ 'grid.json': meta, 'rotations.json': {}, 'index.json': {}, 'grid.bin': new ArrayBuffer(54) });
  await assert.rejects(loadRift3d(f, 'data/rift3d/'), /index\.json/);
});

test('loadRift3d rejeita arquivo ausente citando o arquivo', async () => {
  const f = fakeFetch({ 'grid.json': meta, 'rotations.json': {}, 'index.json': index });
  await assert.rejects(loadRift3d(f, 'data/rift3d/'), /grid\.bin/);
});
