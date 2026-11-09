// Liga dados, cena e controles da vista 3D (rift3d.html).
import { createScene, addPlateMeshes } from './scene.js';
import { parseGrid } from './terrain.js';
import { quatAt } from './rotation.js';
import { ageLabel } from '../paleo.js';

const BASE = 'data/rift3d/';
const $ = (id) => document.getElementById(id);
const status = (msg) => { $('status').textContent = msg; };

async function getJSON(name) {
  const res = await fetch(BASE + name);
  if (!res.ok) throw new Error(`${name}: HTTP ${res.status}`);
  return res.json();
}

async function load() {
  let meta;
  let rotations;
  let index;
  let buf;
  try {
    [meta, rotations, index] = await Promise.all([getJSON('grid.json'), getJSON('rotations.json'), getJSON('index.json')]);
    const res = await fetch(BASE + 'grid.bin');
    if (!res.ok) throw new Error(`grid.bin: HTTP ${res.status}`);
    buf = await res.arrayBuffer();
  } catch (err) {
    console.warn(err);
    status('Dados 3D ausentes. Gere com: python -m pipeline.rift3d');
    return null;
  }
  return { grid: parseGrid(meta, buf), rotations, index };
}

async function main() {
  const data = await load();
  if (!data) return;
  let ctx;
  try {
    ctx = createScene($('stage'));
  } catch (err) {
    status(err.message);
    return;
  }
  const { grid, rotations, index } = data;
  let exag = Number($('exag').value);
  const plates = addPlateMeshes(ctx, grid, exag);
  $('credit').textContent = `Modelo: ${index.model.name} (${index.model.licence}). Relevo: ${index.terrain}`;

  let age = 0;
  function applyAge(a) {
    age = a;
    $('age').value = String(Math.round(a));
    $('age-label').textContent = ageLabel(Math.round(a));
    for (const [pid, g] of plates.groups) {
      const q = quatAt(rotations[String(pid)], a);
      g.quaternion.set(q[0], q[1], q[2], q[3]);
    }
    main.onAge?.(a);
  }
  main.applyAge = applyAge;
  main.ctx = ctx;
  main.data = data;
  main.plates = plates;
  main.getExag = () => exag;

  $('age').addEventListener('input', (e) => { stop(); applyAge(Number(e.target.value)); });
  $('exag').addEventListener('change', (e) => {
    exag = Number(e.target.value);
    plates.rebuild(exag);
    main.onExag?.(exag);
  });
  $('view-oblique').addEventListener('click', () => ctx.setView('oblique'));
  $('view-plan').addEventListener('click', () => ctx.setView('plan'));

  // animacao: do passado (150 Ma) ao presente, 15 Ma por segundo
  let playing = false;
  let last = 0;
  const RATE_MA_PER_S = 15;
  function stop() {
    playing = false;
    $('play').setAttribute('aria-pressed', 'false');
    $('play').textContent = '▶ Animar';
  }
  function tick(now) {
    if (playing) {
      const dt = Math.min(0.1, (now - last) / 1000);
      applyAge(age - dt * RATE_MA_PER_S <= 0 ? 150 : age - dt * RATE_MA_PER_S);
    }
    last = now;
    ctx.render();
    requestAnimationFrame(tick);
  }
  $('play').addEventListener('click', () => {
    if (playing) { stop(); return; }
    playing = true;
    if (age <= 0) applyAge(150);
    $('play').setAttribute('aria-pressed', 'true');
    $('play').textContent = '⏸ Parar';
  });
  applyAge(0);
  requestAnimationFrame(tick);
  main.mountLayers?.();
}

main();
