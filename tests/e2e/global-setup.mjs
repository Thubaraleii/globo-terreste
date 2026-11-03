// Copia os dados SINTETICOS para web/data/ (git-ignorado) e remove so o que criou.
// Se um arquivo ja existir em web/data/, aborta: nao sobrescreve dados reais.
import { copyFileSync, existsSync, mkdirSync, readdirSync, rmdirSync, rmSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';

const SRC = fileURLToPath(new URL('./data/', import.meta.url));
const DEST = fileURLToPath(new URL('../../web/data/', import.meta.url));
const FILES = ['volcanoes.geojson', 'tectonic_zones.geojson', 'sources.json'];

export default function globalSetup() {
  const madeDir = !existsSync(DEST);
  const clash = FILES.filter((f) => existsSync(join(DEST, f)));
  if (clash.length > 0) {
    throw new Error(`web/data/ ja tem ${clash.join(', ')}; mova-os antes de rodar o e2e (ele usa dados sinteticos).`);
  }
  mkdirSync(DEST, { recursive: true });
  const created = [];
  for (const f of FILES) {
    copyFileSync(join(SRC, f), join(DEST, f));
    created.push(f);
  }
  return () => {
    for (const f of created) rmSync(join(DEST, f), { force: true });
    if (madeDir && readdirSync(DEST).length === 0) rmdirSync(DEST);
  };
}
