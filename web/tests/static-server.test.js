// Servidor estatico (tests/e2e/static-server.mjs): comportamento de Range, base do PMTiles.
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createStaticServer } from '../../tests/e2e/static-server.mjs';

const dir = mkdtempSync(join(tmpdir(), 'geoworld-srv-'));
const bytes = Buffer.from(Array.from({ length: 64 }, (_, i) => i));
writeFileSync(join(dir, 'data.bin'), bytes);
let server;
let base;

before(async () => {
  server = createStaticServer(dir);
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  base = `http://127.0.0.1:${server.address().port}`;
});
after(() => {
  server.close();
  rmSync(dir, { recursive: true, force: true });
});

const get = (path, headers = {}, method = 'GET') => fetch(`${base}${path}`, { headers, method });
const buf = async (res) => Buffer.from(await res.arrayBuffer());

test('200 com o arquivo inteiro e Accept-Ranges', async () => {
  const res = await get('/data.bin');
  assert.equal(res.status, 200);
  assert.equal(res.headers.get('accept-ranges'), 'bytes');
  assert.deepEqual(await buf(res), bytes);
});

test('206 para bytes=0-9, bytes=5- e bytes=-4', async () => {
  let res = await get('/data.bin', { Range: 'bytes=0-9' });
  assert.equal(res.status, 206);
  assert.equal(res.headers.get('content-range'), 'bytes 0-9/64');
  assert.equal(res.headers.get('content-length'), '10');
  assert.deepEqual(await buf(res), bytes.subarray(0, 10));

  res = await get('/data.bin', { Range: 'bytes=5-' });
  assert.equal(res.status, 206);
  assert.equal(res.headers.get('content-range'), 'bytes 5-63/64');
  assert.deepEqual(await buf(res), bytes.subarray(5));

  res = await get('/data.bin', { Range: 'bytes=-4' });
  assert.equal(res.status, 206);
  assert.equal(res.headers.get('content-range'), 'bytes 60-63/64');
  assert.deepEqual(await buf(res), bytes.subarray(60));
});

test('416 quando a faixa nao e satisfazivel', async () => {
  const res = await get('/data.bin', { Range: 'bytes=100-200' });
  assert.equal(res.status, 416);
  assert.equal(res.headers.get('content-range'), 'bytes */64');
});

test('faixa malformada ou multipla serve o arquivo inteiro (200)', async () => {
  for (const r of ['bytes=abc', 'items=0-5', 'bytes=0-1,4-5', 'bytes=-', 'bytes=9-3']) {
    const res = await get('/data.bin', { Range: r });
    assert.equal(res.status, 200, r);
    assert.deepEqual(await buf(res), bytes, r);
  }
});

test('HEAD devolve cabecalhos sem corpo', async () => {
  const res = await get('/data.bin', {}, 'HEAD');
  assert.equal(res.status, 200);
  assert.equal(res.headers.get('content-length'), '64');
  assert.equal((await buf(res)).length, 0);
});

test('tentativa de saida da raiz da 404', async () => {
  for (const p of ['/../package.json', '/%2e%2e/package.json', '/..%2f..%2fpackage.json']) {
    const res = await get(p);
    assert.ok([403, 404].includes(res.status), `${p} -> ${res.status}`);
  }
  const res = await get('/nao-existe.txt');
  assert.equal(res.status, 404);
});

test('leitura estilo PMTiles: cabecalho e depois um trecho, por duas faixas', async () => {
  const header = await get('/data.bin', { Range: 'bytes=0-15' });
  assert.equal(header.status, 206);
  const h = await buf(header);
  assert.deepEqual(h, bytes.subarray(0, 16));
  const offset = h[8]; // "offset" lido do cabecalho sintetico
  const chunk = await get('/data.bin', { Range: `bytes=${offset}-${offset + 7}` });
  assert.equal(chunk.status, 206);
  assert.deepEqual(await buf(chunk), bytes.subarray(offset, offset + 8));
});
