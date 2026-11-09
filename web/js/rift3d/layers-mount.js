// Liga as camadas (lineamentos, vulcoes) a cena Three.js: objetos presos ao grupo da placa de cada feicao.
// Posicoes vem de paleo/lineaments_0.geojson e volcanoes_0.geojson (quadro de 0 Ma); sem o arquivo, a caixa some.
import * as THREE from 'three';
import { groupByPlate, lineVertices, pointVertex } from './layers.js';

const $ = (id) => document.getElementById(id);

async function exists(url) {
  try {
    return (await fetch(url, { method: 'HEAD' })).ok;
  } catch {
    return false;
  }
}

// textos do dado entram so por textContent
function showInfo(rows) {
  const box = $('feature-info');
  box.replaceChildren();
  const dl = document.createElement('dl');
  for (const [k, v] of rows) {
    if (v === null || v === undefined || v === '') continue;
    const dt = document.createElement('dt');
    dt.textContent = k;
    const dd = document.createElement('dd');
    dd.textContent = String(v);
    dl.append(dt, dd);
  }
  box.append(dl);
  box.hidden = false;
}

export async function mountLayers(ctx, plates, grid, rotations, exag, paleoBase = 'data/paleo/') {
  const defs = [
    { key: 'lineaments', file: 'lineaments_0.geojson', color: 0xff4fd8, kind: 'line' },
    { key: 'volcanoes', file: 'volcanoes_0.geojson', color: 0xffa040, kind: 'point' },
  ];
  const state = {};
  let currentExag = exag;
  let any = false;
  for (const d of defs) {
    const ok = await exists(paleoBase + d.file);
    $(`row-${d.key}`).hidden = !ok;
    if (ok) any = true;
    state[d.key] = { def: d, ok, fc: null, objects: [], skipped: 0 };
  }
  $('layers').hidden = !any;
  if (!any) return { setExag() {} };

  const raycaster = new THREE.Raycaster();
  raycaster.params.Line.threshold = 0.002;
  raycaster.params.Points.threshold = 0.004;
  const pickables = [];

  function clear(s) {
    for (const o of s.objects) {
      o.parent?.remove(o);
      o.geometry.dispose();
      const k = pickables.indexOf(o);
      if (k >= 0) pickables.splice(k, 1);
    }
    s.objects = [];
  }

  function build(s) {
    clear(s);
    if (!s.fc || !$(`toggle-${s.def.key}`).checked) return;
    const { byPlate, skipped } = groupByPlate(s.fc, rotations);
    s.skipped = skipped;
    for (const [pid, feats] of byPlate) {
      const group = plates.groups.get(pid);
      if (!group) continue;
      if (s.def.kind === 'line') {
        for (const dashed of [false, true]) {
          const pos = [];
          const segFeature = [];
          for (const f of feats) {
            if (Boolean(f.properties.plates_differ) !== dashed) continue;
            for (const line of lineVertices(f, grid, currentExag)) {
              for (let k = 0; k + 1 < line.length / 3; k++) {
                pos.push(...line.slice(3 * k, 3 * k + 6));
                segFeature.push(f);
              }
            }
          }
          if (pos.length === 0) continue;
          const geo = new THREE.BufferGeometry();
          geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
          const mat = dashed
            ? new THREE.LineDashedMaterial({ color: s.def.color, dashSize: 0.004, gapSize: 0.003 })
            : new THREE.LineBasicMaterial({ color: s.def.color });
          const obj = new THREE.LineSegments(geo, mat);
          if (dashed) obj.computeLineDistances();
          obj.userData.segFeature = segFeature;
          group.add(obj);
          s.objects.push(obj);
          pickables.push(obj);
        }
      } else {
        const pos = [];
        const pts = [];
        for (const f of feats) {
          const v = pointVertex(f, grid, currentExag);
          if (v) { pos.push(...v); pts.push(f); }
        }
        if (pts.length === 0) continue;
        const geo = new THREE.BufferGeometry();
        geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
        const obj = new THREE.Points(geo, new THREE.PointsMaterial({ color: s.def.color, size: 7, sizeAttenuation: false }));
        obj.userData.pointFeature = pts;
        group.add(obj);
        s.objects.push(obj);
        pickables.push(obj);
      }
    }
    const total = Object.values(state).reduce((n, x) => n + x.skipped, 0);
    $('layers-note').textContent = total ? `${total} feição(ões) sem placa no modelo foram omitidas.` : '';
  }

  for (const s of Object.values(state)) {
    if (!s.ok) continue;
    $(`toggle-${s.def.key}`).addEventListener('change', async (e) => {
      if (e.target.checked && !s.fc) {
        try {
          s.fc = await (await fetch(paleoBase + s.def.file)).json();
        } catch (err) {
          console.warn(err);
          $('layers-note').textContent = `Falha ao ler ${s.def.file}.`;
          e.target.checked = false;
          return;
        }
      }
      build(s);
    });
  }

  // clique (sem arrastar) mostra nome e fonte da feicao
  const el = ctx.renderer.domElement;
  let down = null;
  el.addEventListener('pointerdown', (e) => { down = [e.clientX, e.clientY]; });
  el.addEventListener('pointerup', (e) => {
    if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4) return;
    const r = el.getBoundingClientRect();
    raycaster.setFromCamera(new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), ctx.camera);
    const hit = raycaster.intersectObjects(pickables, false)[0];
    if (!hit) { $('feature-info').hidden = true; return; }
    const o = hit.object;
    if (o.userData.segFeature) {
      const p = o.userData.segFeature[Math.floor(hit.index / 2)].properties;
      showInfo([['Nome', p.name], ['Tipo', p.kind], ['Comprimento (km)', p.length_km], ['Fonte', p.source],
        ['Placa do modelo', p.plate_id], ['Atravessa placas diferentes', p.plates_differ ? 'sim (girada pela placa do ponto médio)' : null]]);
    } else if (o.userData.pointFeature) {
      const p = o.userData.pointFeature[hit.index].properties;
      showInfo([['Vulcão', p.name], ['Tipo', p.type], ['País', p.country], ['Última erupção (ano)', p.last_eruption],
        ['Fonte', p.source_id], ['Placa do modelo', p.plate_id]]);
    }
  });

  return {
    setExag(v) {
      currentExag = v;
      for (const s of Object.values(state)) if (s.fc) build(s);
    },
  };
}
