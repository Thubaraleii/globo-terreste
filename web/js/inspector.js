// Conteudo do painel de detalhes (amostra, unidade, vulcao, zona). Modulo puro.
//
// Cada funcao devolve uma string HTML para `innerHTML`. Todo valor vindo dos dados
// passa por `esc` (ou vira `não informado`); nada do dado vira nome de atributo,
// evento ou estilo. O unico atributo com valor do dado e o `href` do link da fonte,
// e so quando a URL e http(s) (ver `renderSourceLink`).
import { LITH_COLORS, ROCK_CLASS_COLORS } from './layerstyles.js';

export const NAO_INFORMADO = 'não informado';

// Escala original do GLiM, base das unidades geologicas.
const GLIM_SCALE = '1:3.750.000';

const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

export function esc(s) {
  if (s === null || s === undefined) return '';
  return String(s).replace(/[&<>"']/g, (c) => ESC[c]);
}

const missing = (v) => v === null || v === undefined || (typeof v === 'string' && v.trim() === '')
  || (typeof v === 'number' && !Number.isFinite(v));

// Valor exibivel: escapado, ou `não informado`.
const show = (v) => (missing(v) ? NAO_INFORMADO : esc(v));

const labelFrom = (table) => new Map(table.map(([value, , label]) => [value, label]));
const LITH_LABELS = labelFrom(LITH_COLORS);
const ROCK_LABELS = labelFrom(ROCK_CLASS_COLORS);
const COORD_LABELS = new Map([['reported', 'Reportada'], ['geocoded', 'Geocodificada']]);
const KIND_LABELS = new Map([['volcano', 'Vulcão'], ['hotspot', 'Hotspot']]);

// Rotulo em portugues para um codigo conhecido; senao o proprio valor (escapado).
const showLabel = (labels, v) => (labels.has(v) ? esc(labels.get(v)) : show(v));

// Linhas <dt>/<dd>; `value` ja e HTML seguro.
const row = (term, value) => `<dt>${esc(term)}</dt><dd>${value}</dd>`;
const list = (rows) => `<dl class="details-list">${rows.join('')}</dl>`;
const heading = (text) => `<h2 class="details-heading" tabindex="-1">${text}</h2>`;
const section = (title, body) => `<section class="details-section"><h3>${esc(title)}</h3>${body}</section>`;

// Link para o dado original: <a> so para http(s); senao texto escapado.
export function renderSourceLink(url) {
  if (typeof url !== 'string' || url.trim() === '') return NAO_INFORMADO;
  if (/^https?:\/\//i.test(url)) {
    try {
      const u = new URL(url);
      if (u.protocol === 'https:' || u.protocol === 'http:') {
        return `<a href="${esc(u.href)}" target="_blank" rel="noopener noreferrer">${esc(url)}</a>`;
      }
    } catch {
      // URL invalida: cai no texto simples
    }
  }
  return esc(url);
}

// Mapa source_id -> registro de sources.json. Entrada invalida vira mapa vazio.
export function indexSources(list) {
  const out = new Map();
  if (!Array.isArray(list)) return out;
  for (const s of list) {
    if (s && typeof s === 'object' && typeof s.source_id === 'string') out.set(s.source_id, s);
  }
  return out;
}

function sourceSection(sourceId, source) {
  const s = source ?? {};
  return section('Fonte', list([
    row('Identificador', show(sourceId ?? s.source_id)),
    row('Instituição', show(s.institution)),
    row('Licença', show(s.license)),
    row('Atribuição', show(s.attribution)),
    row('Dado original', renderSourceLink(s.source_url)),
    row('Escala original', show(s.original_scale)),
  ]));
}

function formatMeters(v) {
  return typeof v === 'number' && Number.isFinite(v) ? `${esc(v.toLocaleString('pt-BR'))} m` : show(v);
}

// Momento sismico em N·m, notacao cientifica com virgula decimal.
function formatMoment(v) {
  if (typeof v !== 'number' || !Number.isFinite(v)) return show(v);
  const [mant, exp] = v.toExponential(2).split('e');
  return esc(`${mant.replace('.', ',')} × 10^${Number(exp)} N·m`);
}

// `opts.source`: registro da fonte da amostra; `opts.unitLithOriginal`: litologia
// original da unidade que contem o ponto (se conhecida); `opts.unitSource`: fonte
// da unidade (para a escala original).
export function renderSample(props, opts = {}) {
  const p = props ?? {};
  const hasUnit = !missing(p.unit_id);
  const unitRows = hasUnit
    ? [
      row('Unidade', show(p.unit_id)),
      row('Classe litológica', showLabel(LITH_LABELS, p.unit_lith_class)),
      row('Litologia original', show(opts.unitLithOriginal)),
      row('Escala original do mapa', show(opts.unitSource?.original_scale)),
    ]
    : [row('Unidade', NAO_INFORMADO)];
  const warning = '<p class="details-warning">Aviso: a associação entre a amostra e a unidade '
    + `é aproximada, pois o mapa de unidades (GLiM) tem escala original de cerca de ${GLIM_SCALE}.</p>`;
  return [
    heading(missing(p.rock_name_original) ? 'Amostra' : `Amostra: ${esc(p.rock_name_original)}`),
    list([
      row('Nome original da rocha', show(p.rock_name_original)),
      row('Classe', showLabel(ROCK_LABELS, p.rock_class)),
      row('Tipo de coordenada', showLabel(COORD_LABELS, p.coord_source)),
      row('Incerteza da coordenada', formatMeters(p.coord_uncertainty_m)),
      row('Identificador', show(p.id)),
    ]),
    section('Unidade geológica', list(unitRows) + warning),
    sourceSection(p.source_id, opts.source),
  ].join('');
}

// `sampleCount` nao finito -> `não informado` (nunca um 0 falso).
export function renderUnit(props, sampleCount, opts = {}) {
  const p = props ?? {};
  const count = typeof sampleCount === 'number' && Number.isFinite(sampleCount)
    ? esc(sampleCount) : NAO_INFORMADO;
  const button = typeof p.lith_class === 'string' && p.lith_class !== ''
    ? '<p><button type="button" class="details-action" data-action="filter-lith">Ver amostras desta litologia</button></p>'
    : '';
  return [
    heading('Unidade geológica'),
    list([
      row('Classe litológica', showLabel(LITH_LABELS, p.lith_class)),
      row('Litologia original', show(p.lith_original)),
      row('Número de amostras', count),
      row('Identificador', show(p.unit_id)),
    ]),
    button,
    `<p class="details-warning">A escala original do mapa de unidades (GLiM) é de cerca de ${GLIM_SCALE}; os limites são aproximados.</p>`,
    sourceSection(p.source_id, opts.source),
  ].join('');
}

export function renderVolcano(props, opts = {}) {
  const p = props ?? {};
  const kind = KIND_LABELS.get(p.kind) ?? 'Vulcão';
  return [
    heading(missing(p.name) ? esc(kind) : `${esc(kind)}: ${esc(p.name)}`),
    list([
      row('Nome', show(p.name)),
      row('Categoria', showLabel(KIND_LABELS, p.kind)),
      row('Tipo', show(p.type)),
      row('Última erupção', show(p.last_eruption)),
      row('País', show(p.country)),
      row('Referência', show(p.reference)),
    ]),
    sourceSection(p.source_id, opts.source),
  ].join('');
}

export function renderZone(props, opts = {}) {
  const p = props ?? {};
  return [
    heading(missing(p.name) ? 'Zona tectônica' : `Zona tectônica: ${esc(p.name)}`),
    list([
      row('Nome', show(p.name)),
      row('Posição no ranking', show(p.rank)),
      row('Momento sísmico total', formatMoment(p.moment_total)),
      row('Período dos sismos', `${show(p.period_start)} a ${show(p.period_end)}`),
    ]),
    '<p class="details-note">O ranking ordena as zonas pela soma do momento sísmico dos sismos atribuídos a cada uma no período indicado.</p>',
    sourceSection(p.source_id, opts.source),
  ].join('');
}
