// Copia os arquivos de distribuicao de maplibre-gl e pmtiles de node_modules para web/vendor/.
// A pagina carrega esses arquivos com tags script/link simples (sem etapa de build).
import { copyFileSync, mkdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const out = join(root, 'web', 'vendor');
mkdirSync(out, { recursive: true });

const files = [
  ['node_modules/maplibre-gl/dist/maplibre-gl.js', 'maplibre-gl.js'],
  ['node_modules/maplibre-gl/dist/maplibre-gl.css', 'maplibre-gl.css'],
  ['node_modules/maplibre-gl/LICENSE.txt', 'maplibre-gl.LICENSE.txt'],
  ['node_modules/pmtiles/dist/pmtiles.js', 'pmtiles.js'],
  // vista 3D (rift3d.html): Three.js como modulo ES + OrbitControls
  ['node_modules/three/build/three.module.js', 'three/three.module.js'],
  ['node_modules/three/examples/jsm/controls/OrbitControls.js', 'three/OrbitControls.js'],
  ['node_modules/three/LICENSE', 'three/three.LICENSE.txt'],
];

for (const [from, to] of files) {
  mkdirSync(dirname(join(out, to)), { recursive: true });
  copyFileSync(join(root, from), join(out, to));
  console.log(`vendor: ${from} -> web/vendor/${to}`);
}

const version = (name) => JSON.parse(readFileSync(join(root, 'node_modules', name, 'package.json'), 'utf8')).version;
console.log(`maplibre-gl ${version('maplibre-gl')}, pmtiles ${version('pmtiles')}`);
