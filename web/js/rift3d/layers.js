// Camadas da vista 3D (lineamentos, vulcoes): partes puras, sem Three.js.
// As feicoes vem dos quadros de 0 Ma (posicoes atuais, com properties.plate_id) e acompanham o quaternion
// da placa delas; so entram as que caem na faixa da grade.

import { geoToXYZ } from './rotation.js';
import { heightAt } from './terrain.js';

const EARTH_RADIUS_M = 6371000;
export const LINE_LIFT = 0.0004;
export const POINT_LIFT = 0.0008;

// Agrupa por placa; sem plate_id inteiro ou com placa ausente de `rotations`, a feicao e descartada e contada.
export function groupByPlate(fc, rotations) {
  const byPlate = new Map();
  let skipped = 0;
  for (const f of fc.features ?? []) {
    const pid = f.properties?.plate_id;
    if (!Number.isInteger(pid) || !(String(pid) in rotations)) {
      skipped += 1;
      continue;
    }
    if (!byPlate.has(pid)) byPlate.set(pid, []);
    byPlate.get(pid).push(f);
  }
  return { byPlate, skipped };
}

function inBbox(meta, lon, lat) {
  const b = meta.bbox;
  return lon >= b.lon_min && lon <= b.lon_max && lat >= b.lat_min && lat <= b.lat_max;
}

function lift(grid, lon, lat, exag, extra) {
  const h = heightAt(grid, lon, lat) ?? 0;
  return geoToXYZ(lon, lat, 1 + (exag * h) / EARTH_RADIUS_M + extra);
}

// Uma lista de vertices (x,y,z achatados) por linha; linhas sem nenhum vertice na faixa ficam de fora.
export function lineVertices(feature, grid, exag) {
  const g = feature.geometry;
  if (!g) return [];
  const lines = g.type === 'LineString' ? [g.coordinates] : g.type === 'MultiLineString' ? g.coordinates : [];
  const out = [];
  for (const line of lines) {
    if (!line.some((c) => inBbox(grid.meta, c[0], c[1]))) continue;
    const v = new Float32Array(line.length * 3);
    line.forEach((c, k) => v.set(lift(grid, c[0], c[1], exag, LINE_LIFT), 3 * k));
    out.push(v);
  }
  return out;
}

export function pointVertex(feature, grid, exag) {
  const c = feature.geometry?.type === 'Point' ? feature.geometry.coordinates : null;
  if (!c || !Number.isFinite(c[0]) || !Number.isFinite(c[1])) return null;
  if (!inBbox(grid.meta, c[0], c[1])) return null;
  return lift(grid, c[0], c[1], exag, POINT_LIFT);
}
