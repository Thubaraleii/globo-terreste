import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  esc, NAO_INFORMADO, renderSample, renderUnit, renderVolcano, renderZone,
  renderSourceLink, indexSources,
} from '../js/inspector.js';

const HOSTILE = '<img src=x onerror=1>';

// Nenhuma tag nem atributo vivo vindo do dado: so as tags que os renderizadores criam.
const ALLOWED_TAGS = new Set(['h2', 'dl', 'dt', 'dd', 'p', 'a', 'button', 'section', 'h3', 'strong']);
function assertOnlyOwnTags(html) {
  for (const m of html.matchAll(/<\/?([a-zA-Z][a-zA-Z0-9-]*)/g)) {
    assert.ok(ALLOWED_TAGS.has(m[1].toLowerCase()), `tag inesperada: ${m[0]} em ${html}`);
  }
  assert.ok(!/<script/i.test(html));
  assert.ok(!/<[^>]*\son[a-z]+\s*=/i.test(html), 'atributo de evento em tag');
  assert.ok(!/href="(?!https?:\/\/)/i.test(html), 'href que nao e http(s)');
}

const SOURCE = {
  source_id: 'georoc',
  institution: 'Instituto Sintético',
  source_url: 'https://example.org/dados',
  license: 'CC-BY-4.0',
  attribution: 'Autores Sintéticos (2026)',
  acquisition_date: '2026-01-01',
  original_scale: null,
};

const SAMPLE = {
  id: 's1',
  rock_name_original: 'Basalto',
  rock_class: 'mafic',
  coord_source: 'reported',
  coord_uncertainty_m: 250,
  unit_id: 'u9',
  source_id: 'georoc',
  unit_lith_class: 'basic_volcanic',
};

test('test_esc_escapes_script_and_quotes', () => {
  assert.equal(esc(`<script>alert("x")</script>&'`),
    '&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;&amp;&#39;');
  assert.equal(esc(null), '');
  assert.equal(esc(undefined), '');
  assert.equal(esc(42), '42');
});

test('test_render_sample_escapes_rock_name_with_html', () => {
  const html = renderSample({ ...SAMPLE, rock_name_original: HOSTILE, id: '"><script>x</script>' });
  assert.ok(!html.includes('<img'));
  assert.ok(html.includes('&lt;img src=x onerror=1&gt;'));
  assertOnlyOwnTags(html);
});

test('test_render_sample_null_fields_show_nao_informado', () => {
  const html = renderSample({
    id: null, rock_name_original: null, rock_class: null, coord_source: null,
    coord_uncertainty_m: null, unit_id: null, source_id: null, unit_lith_class: null,
  });
  assert.equal(NAO_INFORMADO, 'não informado');
  // nome, classe, tipo, incerteza, unidade e os 5 detalhes da fonte
  const count = html.split(NAO_INFORMADO).length - 1;
  assert.ok(count >= 10, `esperava >= 10 "não informado", veio ${count}`);
  assert.ok(!html.includes('null'));
  assert.ok(!html.includes('undefined'));
  assertOnlyOwnTags(html);
});

test('test_render_sample_shows_scale_warning_for_unit', () => {
  const html = renderSample(SAMPLE, {
    source: SOURCE,
    unitLithOriginal: 'vb <b>basalt</b>',
    unitSource: { ...SOURCE, source_id: 'glim', original_scale: '1:3.750.000' },
  });
  assert.ok(html.includes('Vulcânica básica'), 'classe da unidade (rotulo)');
  assert.ok(html.includes('vb &lt;b&gt;basalt&lt;/b&gt;'), 'litologia original da unidade, escapada');
  assert.match(html, /aproximad/);
  assert.match(html, /1:3\.750\.000/);
  assert.ok(html.includes('Instituto Sintético'));
  assert.ok(html.includes('CC-BY-4.0'));
  assertOnlyOwnTags(html);
  // sem unidade: o aviso continua e a unidade aparece como nao informado
  const none = renderSample({ ...SAMPLE, unit_id: null, unit_lith_class: null });
  assert.match(none, /aproximad/);
  assert.ok(none.includes(NAO_INFORMADO));
});

test('test_render_unit_zero_samples_shows_0', () => {
  const props = { unit_id: 'u1', lith_class: 'basic_volcanic', lith_original: 'vb', source_id: 'glim' };
  const zero = renderUnit(props, 0);
  assert.match(zero, /<dd>0<\/dd>/);
  assert.ok(zero.includes('Ver amostras desta litologia'));
  for (const bad of [undefined, null, NaN, Infinity, '3']) {
    const html = renderUnit(props, bad);
    assert.ok(!/<dd>0<\/dd>/.test(html), `${String(bad)} nao pode virar 0`);
    assert.ok(html.includes(NAO_INFORMADO));
  }
  assert.match(renderUnit(props, 17), /<dd>17<\/dd>/);
});

test('test_render_unit_without_lith_class_has_no_filter_button', () => {
  const html = renderUnit({ unit_id: 'u1', lith_class: null, lith_original: HOSTILE }, 3);
  assert.ok(!html.includes('Ver amostras desta litologia'));
  assertOnlyOwnTags(html);
});

test('test_source_link_only_for_http_urls', () => {
  const ok = renderSourceLink('https://example.org/a?b=1&c="2"');
  assert.match(ok, /^<a href="https:\/\/example\.org\/a\?b=1&amp;c=%222%22" target="_blank" rel="noopener noreferrer">/);
  assert.match(renderSourceLink('http://example.org/'), /^<a href="http:\/\/example\.org\/"/);
  for (const bad of ['javascript:alert(1)', 'JAVASCRIPT:alert(1)', 'data:text/html,<script>x</script>',
    ' javascript:alert(1)', 'ftp://example.org', '//example.org', 'https//x']) {
    const html = renderSourceLink(bad);
    assert.ok(!html.includes('<a'), `nao deveria virar link: ${bad}`);
    assert.ok(!html.includes('<script'));
  }
  assert.equal(renderSourceLink(null), NAO_INFORMADO);
  assert.equal(renderSourceLink(''), NAO_INFORMADO);
  assert.equal(renderSourceLink(42), NAO_INFORMADO);
  assert.equal(renderSourceLink('javascript:alert(1)'), 'javascript:alert(1)');
});

test('test_index_sources_tolerates_bad_input', () => {
  assert.equal(indexSources(null).size, 0);
  assert.equal(indexSources({ a: 1 }).size, 0);
  const m = indexSources([SOURCE, null, { source_id: 7 }, 'x']);
  assert.equal(m.size, 1);
  assert.equal(m.get('georoc').license, 'CC-BY-4.0');
});

test('test_render_volcano_escapes_and_shows_source', () => {
  const html = renderVolcano({
    name: HOSTILE, kind: 'volcano', type: 'Estratovulcão', last_eruption: null,
    country: null, reference: null, source_id: 'gvp',
  }, { source: SOURCE });
  assert.ok(!html.includes('<img'));
  assert.ok(html.includes('&lt;img'));
  assert.ok(html.includes('Estratovulcão'));
  assert.ok(html.includes(NAO_INFORMADO));
  assert.ok(html.includes('Instituto Sintético'));
  assert.ok(html.includes('rel="noopener noreferrer"'));
  assertOnlyOwnTags(html);
  assert.match(renderVolcano({ kind: 'hotspot' }), /Hotspot/);
});

test('test_render_zone_shows_rank_moment_and_period', () => {
  const html = renderZone({
    rank: 1, name: 'Zona "A" <b>', moment_total: 1.234e21,
    period_start: '1990-01-01', period_end: '2020-12-31', source_id: 'x',
  });
  assert.match(html, /<dd>1<\/dd>/);
  assert.ok(html.includes('1,23 × 10^21 N·m'));
  assert.ok(html.includes('1990-01-01'));
  assert.ok(html.includes('2020-12-31'));
  assert.ok(html.includes('Zona &quot;A&quot; &lt;b&gt;'));
  assertOnlyOwnTags(html);
  const empty = renderZone({ rank: null, moment_total: null, period_start: null, period_end: null });
  assert.ok(!empty.includes('null'));
  assert.ok(empty.includes(NAO_INFORMADO));
});
