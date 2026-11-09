import { test } from 'node:test';
import assert from 'node:assert/strict';
import { geoToXYZ, quatFromPoleAngle, slerp, quatAt, rotateXYZ } from '../js/rift3d/rotation.js';

function assertClose(a, b, tol = 1e-9) {
  assert.equal(a.length, b.length);
  a.forEach((v, i) => assert.ok(Math.abs(v - b[i]) < tol, `indice ${i}: ${v} != ${b[i]}`));
}

test('geoToXYZ: lon 0 lat 0 e +x, polo norte e +y, lon 90 E e -z', () => {
  assertClose(geoToXYZ(0, 0), [1, 0, 0]);
  assertClose(geoToXYZ(0, 90), [0, 1, 0]);
  assertClose(geoToXYZ(90, 0), [0, 0, -1]);
  assertClose(geoToXYZ(0, 0, 2), [2, 0, 0]);
});

test('quat 0 Ma e identidade', () => {
  assert.deepEqual(quatAt([{ age: 0, pole_lat: 10, pole_lon: 20, angle_deg: 0 }], 0), [0, 0, 0, 1]);
});

test('polo norte, 90 graus: lon 0 vai para lon 90 E', () => {
  const q = quatFromPoleAngle(90, 0, 90);
  assertClose(rotateXYZ(q, geoToXYZ(0, 0)), geoToXYZ(90, 0));
});

test('slerp pega o caminho curto', () => {
  const a = quatFromPoleAngle(0, 0, 10);
  const b = a.map((c) => -c);
  assertClose(slerp(a, b, 0.5), a);
});

test('quatAt interpola idade 7 entre 5 e 10 e prende nas pontas', () => {
  const frames = [
    { age: 10, pole_lat: 30, pole_lon: 40, angle_deg: 20 },
    { age: 5, pole_lat: 30, pole_lon: 40, angle_deg: 10 },
  ];
  assertClose(quatAt(frames, 7), quatFromPoleAngle(30, 40, 14));
  assertClose(quatAt(frames, 0), quatFromPoleAngle(30, 40, 10));
  assertClose(quatAt(frames, 200), quatFromPoleAngle(30, 40, 20));
});

test('quatAt lista vazia devolve identidade', () => {
  assert.deepEqual(quatAt([], 50), [0, 0, 0, 1]);
});
