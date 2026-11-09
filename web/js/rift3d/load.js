// Carrega e valida os dados da vista 3D. Qualquer problema vira um Error com mensagem para o usuario
// (grade desatualizada, arquivo ausente, indice sem modelo), nunca uma pagina em branco.
import { parseGrid } from './terrain.js';

const HINT = 'Gere de novo com: python -m pipeline.rift3d';

export async function loadRift3d(fetchImpl, base) {
  async function get(name, kind) {
    const res = await fetchImpl(base + name);
    if (!res.ok) throw new Error(`Dados 3D ausentes (${name}: HTTP ${res.status}). ${HINT}`);
    return kind === 'bin' ? res.arrayBuffer() : res.json();
  }
  const [meta, rotations, index] = await Promise.all([get('grid.json'), get('rotations.json'), get('index.json')]);
  const buf = await get('grid.bin', 'bin');
  if (!index?.model?.name || !index.model.licence) throw new Error(`index.json sem model (nome/licença). ${HINT}`);
  let grid;
  try {
    grid = parseGrid(meta, buf);
  } catch (err) {
    throw new Error(`${err.message}. ${HINT}`);
  }
  return { grid, rotations, index };
}
