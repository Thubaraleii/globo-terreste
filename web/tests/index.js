// Node 24 nao expande diretorios em `node --test web/tests`: ele tenta carregar o
// diretorio como modulo e cai neste index.js, que importa todos os *.test.js.
import { readdirSync } from 'node:fs';

for (const f of readdirSync(new URL('.', import.meta.url)).sort()) {
  if (f.endsWith('.test.js')) await import(`./${f}`);
}
