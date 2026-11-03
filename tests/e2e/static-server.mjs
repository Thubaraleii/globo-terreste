// Servidor estatico minimo, somente loopback (127.0.0.1), com suporte a HTTP Range
// (necessario para PMTiles). Serve web/ por padrao.
// Uso: `npm run serve` (porta 8766; `PORT` sobrescreve) ou importar createStaticServer.
import { createServer } from 'node:http';
import { createReadStream } from 'node:fs';
import { stat } from 'node:fs/promises';
import { extname, join, normalize, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const DEFAULT_ROOT = resolve(fileURLToPath(new URL('../../web', import.meta.url)));
const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.geojson': 'application/geo+json; charset=utf-8',
  '.txt': 'text/plain; charset=utf-8',
};

// Interpreta `Range`. Devolve { start, end } (inclusivo), 'unsatisfiable' ou null
// (ausente, malformado ou multiplas faixas: serve o arquivo inteiro, como a RFC permite).
export function parseRange(header, size) {
  if (typeof header !== 'string') return null;
  const m = /^bytes=(\d*)-(\d*)$/.exec(header.trim());
  if (!m || (m[1] === '' && m[2] === '')) return null;
  let start;
  let end;
  if (m[1] === '') {
    const n = Number(m[2]);
    if (n === 0) return 'unsatisfiable';
    start = Math.max(0, size - n);
    end = size - 1;
  } else {
    start = Number(m[1]);
    end = m[2] === '' ? size - 1 : Math.min(Number(m[2]), size - 1);
    if (m[2] !== '' && Number(m[2]) < start) return null;
  }
  if (start >= size) return 'unsatisfiable';
  return { start, end };
}

export function createStaticServer(root = DEFAULT_ROOT) {
  const base = resolve(root);
  return createServer(async (req, res) => {
    const notFound = () => {
      res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
      res.end('nao encontrado');
    };
    if (req.method !== 'GET' && req.method !== 'HEAD') {
      res.writeHead(405, { Allow: 'GET, HEAD' });
      res.end();
      return;
    }
    let file;
    let size;
    try {
      const path = decodeURIComponent(new URL(req.url, 'http://x').pathname);
      file = normalize(join(base, path));
      if (file !== base && !file.startsWith(base + sep)) return notFound();
      if (path.endsWith('/')) file = join(file, 'index.html');
      const info = await stat(file);
      if (!info.isFile()) return notFound();
      size = info.size;
    } catch {
      return notFound();
    }
    const headers = {
      'Content-Type': TYPES[extname(file)] ?? 'application/octet-stream',
      'Cache-Control': 'no-store',
      'Accept-Ranges': 'bytes',
    };
    const range = parseRange(req.headers.range, size);
    if (range === 'unsatisfiable') {
      res.writeHead(416, { ...headers, 'Content-Range': `bytes */${size}` });
      res.end();
      return;
    }
    let status = 200;
    let start = 0;
    let end = size - 1;
    if (range) {
      status = 206;
      ({ start, end } = range);
      headers['Content-Range'] = `bytes ${start}-${end}/${size}`;
    }
    headers['Content-Length'] = size === 0 ? 0 : end - start + 1;
    if (req.method === 'HEAD' || size === 0) {
      res.writeHead(status, headers);
      res.end();
      return;
    }
    // Le so a faixa pedida, em streaming (nunca o arquivo inteiro na memoria).
    const stream = createReadStream(file, { start, end });
    stream.on('open', () => {
      res.writeHead(status, headers);
      stream.pipe(res);
    });
    stream.on('error', (err) => {
      if (!res.headersSent) {
        const missing = err?.code === 'ENOENT';
        res.writeHead(missing ? 404 : 500, { 'Content-Type': 'text/plain; charset=utf-8' });
        res.end(missing ? 'nao encontrado' : 'erro de leitura');
      } else {
        res.destroy(err);
      }
    });
    res.on('close', () => stream.destroy());
  });
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const port = Number(process.env.PORT ?? 8766);
  createStaticServer().listen(port, '127.0.0.1', () => {
    console.log(`GeoWorld em http://127.0.0.1:${port}/ (Ctrl+C para parar)`);
  });
}
