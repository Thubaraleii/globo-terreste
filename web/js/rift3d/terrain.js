// Grade de alturas da vista 3D: leitura, consulta, cor e malha por placa (funcoes puras, sem Three.js).
// grid.bin = alturas int16 (norte -> sul, oeste -> leste) seguidas do ID de placa uint32 por celula (0 = sem placa).

import { geoToXYZ } from './rotation.js';

const EARTH_RADIUS_M = 6371000;

export function parseGrid(meta, buffer) {
  const n = meta.width * meta.height;
  if (buffer.byteLength !== n * 6) {
    throw new Error(`grid.bin com tamanho inesperado: ${buffer.byteLength} bytes, esperado ${n * 6}`);
  }
  const heights = new Int16Array(buffer, meta.heights_offset, n);
  // plates_offset pode nao ser multiplo de 4: copia para alinhar
  const plates = new Uint32Array(buffer.slice(meta.plates_offset, meta.plates_offset + n * 4));
  return { meta, heights, plates };
}

export function cellLonLat(meta, i, j) {
  return [meta.bbox.lon_min + i * meta.step_deg, meta.bbox.lat_max - j * meta.step_deg];
}

// Altura (m) da celula mais proxima; null fora da faixa ou sem dado.
export function heightAt(grid, lonDeg, latDeg) {
  const { meta } = grid;
  const i = Math.round((lonDeg - meta.bbox.lon_min) / meta.step_deg);
  const j = Math.round((meta.bbox.lat_max - latDeg) / meta.step_deg);
  if (i < 0 || j < 0 || i >= meta.width || j >= meta.height) return null;
  const h = grid.heights[j * meta.width + i];
  return h === meta.nodata ? null : h;
}

const STOPS = [
  [0, [0.35, 0.55, 0.3]],
  [500, [0.7, 0.7, 0.4]],
  [1500, [0.6, 0.45, 0.3]],
  [3000, [0.5, 0.4, 0.35]],
  [4000, [0.95, 0.95, 0.95]],
];

export function tintForHeight(h) {
  if (h < 0) {
    const d = Math.min(1, -h / 6000);
    return [0.05 + 0.1 * (1 - d), 0.2 + 0.3 * (1 - d), 0.35 + 0.4 * (1 - d)];
  }
  if (h >= STOPS[STOPS.length - 1][0]) return [...STOPS[STOPS.length - 1][1]];
  for (let k = 1; k < STOPS.length; k++) {
    const [h1, c1] = STOPS[k];
    if (h <= h1) {
      const [h0, c0] = STOPS[k - 1];
      const t = (h - h0) / (h1 - h0);
      return c0.map((v, c) => v + (c1[c] - v) * t);
    }
  }
  return [...STOPS[0][1]];
}

// Malha de uma placa: so celulas da placa com altura valida; quad vira 2 triangulos se os 4 cantos servem.
// Raio do vertice = 1 + exag * h / 6371000 (Terra = 1); posicoes no mapeamento de geoToXYZ.
export function buildPlateMesh(grid, plateId, exag) {
  const { meta, heights, plates } = grid;
  const { width: w, height: h } = meta;
  const valid = (i, j) => {
    const k = j * w + i;
    return plates[k] === plateId && heights[k] !== meta.nodata;
  };
  const vertexOf = new Int32Array(w * h).fill(-1);
  const positions = [];
  const colors = [];
  const indices = [];
  const vertex = (i, j) => {
    const k = j * w + i;
    if (vertexOf[k] >= 0) return vertexOf[k];
    const [lon, lat] = cellLonLat(meta, i, j);
    const m = heights[k];
    positions.push(...geoToXYZ(lon, lat, 1 + (exag * m) / EARTH_RADIUS_M));
    colors.push(...tintForHeight(m));
    vertexOf[k] = positions.length / 3 - 1;
    return vertexOf[k];
  };
  for (let j = 0; j < h - 1; j++) {
    for (let i = 0; i < w - 1; i++) {
      if (!(valid(i, j) && valid(i + 1, j) && valid(i, j + 1) && valid(i + 1, j + 1))) continue;
      const a = vertex(i, j);
      const b = vertex(i + 1, j);
      const c = vertex(i, j + 1);
      const d = vertex(i + 1, j + 1);
      indices.push(a, c, b, b, c, d);
    }
  }
  return {
    positions: new Float32Array(positions),
    colors: new Float32Array(colors),
    indices: new Uint32Array(indices),
  };
}
