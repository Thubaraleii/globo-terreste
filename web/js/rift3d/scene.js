// Cena Three.js da vista 3D: Terra de raio 1, camera orbital sobre a faixa, malhas por placa.
import * as THREE from 'three';
import { OrbitControls } from '../../vendor/three/OrbitControls.js';
import { geoToXYZ } from './rotation.js';
import { buildPlateMesh } from './terrain.js';

const CENTER = [-10, -30]; // lon, lat do alvo da camera (meio do Atlantico Sul)

export function createScene(container) {
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true });
  } catch (err) {
    throw new Error('WebGL indisponível neste navegador');
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  container.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x07121f);
  const camera = new THREE.PerspectiveCamera(45, 1, 1e-4, 20);

  const target = new THREE.Vector3(...geoToXYZ(CENTER[0], CENTER[1]));
  const normal = target.clone().normalize();
  const north = new THREE.Vector3(0, 1, 0).sub(normal.clone().multiplyScalar(normal.y)).normalize();

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.copy(target);
  controls.enableDamping = true;
  controls.minDistance = 0.01;
  controls.maxDistance = 6;

  scene.add(new THREE.AmbientLight(0xffffff, 0.75));
  const sun = new THREE.DirectionalLight(0xffffff, 1.4);
  sun.position.copy(normal.clone().multiplyScalar(3).add(north.clone().multiplyScalar(-1)).add(new THREE.Vector3(1, 1, 0)));
  scene.add(sun);

  // nivel do mar (0 m): casca translucida de raio 1, empurrada para tras para nao brigar com a costa
  const sea = new THREE.Mesh(
    new THREE.SphereGeometry(1, 128, 96),
    new THREE.MeshBasicMaterial({ color: 0x14486f, transparent: true, opacity: 0.32, depthWrite: false,
      polygonOffset: true, polygonOffsetFactor: 2, polygonOffsetUnits: 2 }),
  );
  scene.add(sea);

  function resize() {
    const w = container.clientWidth || window.innerWidth;
    const h = container.clientHeight || window.innerHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  window.addEventListener('resize', resize);
  resize();

  function setView(name) {
    const south = north.clone().negate();
    const pos = name === 'plan'
      ? target.clone().add(normal.clone().multiplyScalar(1.9))
      : target.clone().add(normal.clone().multiplyScalar(1.2)).add(south.multiplyScalar(1.1));
    camera.position.copy(pos);
    camera.up.set(0, 1, 0);
    controls.target.copy(target);
    controls.update();
  }
  setView('oblique');

  function render() {
    controls.update();
    renderer.render(scene, camera);
  }

  function dispose() {
    window.removeEventListener('resize', resize);
    renderer.dispose();
  }

  return { scene, camera, renderer, controls, render, setView, dispose, sea };
}

// Um grupo por placa (a rotacao do quadro atual vai no quaternion do grupo). rebuild(exag) refaz as malhas.
// plateIds: todas as placas com rotacao (placas sem malha tambem tem grupo, para as camadas girarem com elas).
export function addPlateMeshes(ctx, grid, exag, plateIds = grid.meta.plates) {
  const groups = new Map();
  const material = new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide });
  for (const pid of plateIds) {
    const g = new THREE.Group();
    groups.set(pid, g);
    ctx.scene.add(g);
  }
  function rebuild(newExag) {
    for (const [pid, g] of groups) {
      for (const child of [...g.children]) {
        if (child.userData.terrain) {
          child.geometry.dispose();
          g.remove(child);
        }
      }
      if (!grid.meta.plates.includes(pid)) continue;
      const m = buildPlateMesh(grid, pid, newExag);
      if (m.indices.length === 0) continue;
      const geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.BufferAttribute(m.positions, 3));
      geo.setAttribute('color', new THREE.BufferAttribute(m.colors, 3));
      geo.setIndex(new THREE.BufferAttribute(m.indices, 1));
      geo.computeVertexNormals();
      const mesh = new THREE.Mesh(geo, material);
      mesh.userData.terrain = true;
      g.add(mesh);
    }
  }
  rebuild(exag);
  return { groups, rebuild };
}
