// Paleogeografia: linhas de costa reconstruidas por idade (Merdith et al. 2021, CC BY 4.0),
// com controle de tempo e animacao. Os quadros vem de data/paleo/coast_<idade>.geojson,
// carregados sob demanda. Textos do modelo entram so por textContent.

import { ROCK_CLASS_COLORS } from './layerstyles.js';

export const SRC = 'paleo';
export const FILL = 'paleo:fill';
export const LINE = 'paleo:line';

// Proxima idade na animacao: do passado para o presente, e recomeca em maxAge.
export function nextAge(ages, current) {
  const sorted = [...ages].sort((a, b) => b - a);
  const i = sorted.indexOf(current);
  if (i < 0) return sorted[0];
  return sorted[(i + 1) % sorted.length];
}

export function ageLabel(age) {
  return age === 0 ? 'Hoje (0 Ma)' : `${age} milhões de anos atrás`;
}

const EMPTY = { type: 'FeatureCollection', features: [] };

export async function mountPaleo(map, base, root, opts = {}) {
  let index;
  try {
    const res = await fetch(`${base}paleo/index.json`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    index = await res.json();
  } catch (err) {
    console.warn('Paleomapas indisponíveis:', err);
    return null;
  }
  const ages = (index.ages_ma ?? []).filter((a) => Number.isFinite(a));
  if (ages.length === 0) return null;
  ages.sort((a, b) => a - b);

  // espera as camadas de dados existirem, para inserir o paleo logo abaixo delas
  if (!map.getLayer('volcanoes')) {
    await new Promise((resolve) => {
      const check = () => (map.getLayer('volcanoes') ? resolve() : map.once('idle', check));
      check();
    });
  }
  const before = ['geo_units', 'plates:casing', 'plates'].find((id) => map.getLayer(id));
  map.addSource(SRC, { type: 'geojson', data: EMPTY });
  map.addLayer({
    id: FILL, type: 'fill', source: SRC,
    layout: { visibility: 'none' },
    paint: { 'fill-color': '#c9a46a', 'fill-opacity': 0.55 },
  }, before);
  map.addLayer({
    id: LINE, type: 'line', source: SRC,
    layout: { visibility: 'none' },
    paint: { 'line-color': '#f2dcae', 'line-width': 0.8, 'line-opacity': 0.9 },
  }, before);

  // Amostras na posicao de formacao (so se os quadros locais existirem; GEOROC nao e publicado).
  let hasSamples = false;
  try {
    hasSamples = (await fetch(`${base}paleo/samples_0.geojson`, { method: 'HEAD' })).ok;
  } catch { /* sem quadros de amostras */ }
  const SAMPLES = 'paleo-samples';
  if (hasSamples) {
    map.addSource(SAMPLES, { type: 'geojson', data: EMPTY });
    map.addLayer({
      id: 'paleo:samples', type: 'circle', source: SAMPLES,
      layout: { visibility: 'none' },
      paint: {
        'circle-radius': 6,
        'circle-color': ['match', ['get', 'rock_class'],
          ...ROCK_CLASS_COLORS.flatMap(([value, color]) => [value, color]), '#9aa4b8'],
        'circle-stroke-color': '#35c8ff', // contorno ciano: distingue das amostras e vulcoes atuais
        'circle-stroke-width': 2,
      },
    });
    map.on('click', 'paleo:samples', (e) => {
      const f = e.features?.[0];
      if (f && opts.onSelectSample) opts.onSelectSample(f.properties);
    });
    map.on('mouseenter', 'paleo:samples', () => { map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', 'paleo:samples', () => { map.getCanvas().style.cursor = ''; });
  }
  // Lineamentos estruturais girados (so se o pesquisador forneceu os dados e o pipeline os gerou).
  let hasLineaments = false;
  try {
    hasLineaments = (await fetch(`${base}paleo/lineaments_0.geojson`, { method: 'HEAD' })).ok;
  } catch { /* sem lineamentos */ }
  const LINEAMENTS = 'paleo-lineaments';
  if (hasLineaments) {
    map.addSource(LINEAMENTS, { type: 'geojson', data: EMPTY });
    map.addLayer({
      id: 'paleo:lineaments', type: 'line', source: LINEAMENTS,
      layout: { visibility: 'none' },
      paint: { 'line-color': '#ff4fd8', 'line-width': 2.2, 'line-opacity': 0.95 },
    });
    map.on('click', 'paleo:lineaments', (e) => {
      const f = e.features?.[0];
      if (f && opts.onSelectLineament) opts.onSelectLineament(f.properties);
    });
    map.on('mouseenter', 'paleo:lineaments', () => { map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', 'paleo:lineaments', () => { map.getCanvas().style.cursor = ''; });
  }
  const lineamentCache = new Map();
  async function lineamentFrame(a) {
    if (lineamentCache.has(a)) return lineamentCache.get(a);
    const res = await fetch(`${base}paleo/lineaments_${a}.geojson`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const fc = await res.json();
    lineamentCache.set(a, fc);
    return fc;
  }

  const sampleCache = new Map();
  async function sampleFrame(a) {
    if (sampleCache.has(a)) return sampleCache.get(a);
    const res = await fetch(`${base}paleo/samples_${a}.geojson`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const fc = await res.json();
    sampleCache.set(a, fc);
    return fc;
  }

  const cache = new Map();
  let token = 0;
  async function frame(age) {
    if (cache.has(age)) return cache.get(age);
    const res = await fetch(`${base}paleo/coast_${age}.geojson`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const fc = await res.json();
    cache.set(age, fc);
    return fc;
  }

  // controles
  root.hidden = false;
  const toggle = root.querySelector('#paleo-toggle');
  const slider = root.querySelector('#paleo-slider');
  const play = root.querySelector('#paleo-play');
  const label = root.querySelector('#paleo-label');
  const credit = root.querySelector('#paleo-credit');
  const status = root.querySelector('#paleo-status');
  slider.min = '0';
  slider.max = String(ages.length - 1);
  slider.step = '1';
  // o deslizante e invertido: esquerda = passado distante, direita = hoje
  const sliderToAge = (v) => ages[ages.length - 1 - Number(v)];
  const ageToSlider = (a) => ages.length - 1 - ages.indexOf(a);
  let age = ages[ages.length - 1];
  slider.value = String(ageToSlider(age));
  credit.textContent = `Linhas de costa reconstruídas: ${index.model?.name ?? 'modelo'} — ${index.model?.licence ?? ''}. `
    + 'Reconstrução interpretativa, não observação. Os vulcões são levados para onde a placa sob eles estava '
    + '(não existiam nessa idade); placas e zonas continuam nas posições atuais. '
    + 'Amostras (se ligadas): só as com idade medida, na posição da placa nessa idade.';

  // Vulcoes girados (so se o pipeline os gerou): cada ponto vai para onde a sua placa estava.
  const volcSource = index.volcanoes ? map.getSource('volcanoes') : null;
  const volcOriginal = volcSource ? volcSource.serialize().data : null; // URL dos dados atuais
  const volcCache = new Map();
  async function volcFrame(a) {
    if (volcCache.has(a)) return volcCache.get(a);
    const res = await fetch(`${base}paleo/volcanoes_${a}.geojson`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const fc = await res.json();
    volcCache.set(a, fc);
    return fc;
  }

  async function show(a) {
    age = a;
    slider.value = String(ageToSlider(a));
    label.textContent = ageLabel(a);
    const my = ++token;
    try {
      const [fc, vfc, sfc, lfc] = await Promise.all([
        frame(a), volcSource ? volcFrame(a) : null, samplesOn ? sampleFrame(a) : null,
        lineamentsOn ? lineamentFrame(a) : null,
      ]);
      if (my !== token) return; // chegou um quadro mais novo
      map.getSource(SRC).setData(fc);
      if (lfc) map.getSource(LINEAMENTS).setData(lfc);
      if (sfc) {
        map.getSource(SAMPLES).setData(sfc);
        status.textContent = '';
        sampleCount.textContent = `${sfc.features.length} amostra(s) com idade medida perto de ${a} Ma`;
      }
      if (volcSource) volcSource.setData(a === 0 ? volcOriginal : vfc);
      status.textContent = '';
    } catch (err) {
      console.warn('Falha ao carregar quadro paleo', a, err);
      status.textContent = 'Não foi possível carregar este quadro.';
    }
  }

  let timer = null;
  function stop() {
    if (timer) clearInterval(timer);
    timer = null;
    play.textContent = '▶ Animar';
    play.setAttribute('aria-pressed', 'false');
  }
  function start() {
    play.textContent = '⏸ Pausar';
    play.setAttribute('aria-pressed', 'true');
    timer = setInterval(async () => {
      const next = nextAge(ages, age);
      // pre-carrega antes de avancar, para nao piscar
      try { await frame(next); } catch { /* show() avisa */ }
      show(next);
    }, 900);
  }

  // caixa "Amostras na idade" (so existe com quadros locais)
  const samplesBox = root.querySelector('#paleo-samples-toggle');
  const sampleCount = root.querySelector('#paleo-samples-count');
  let samplesOn = false;
  const applySamplesVisibility = (on) => {
    if (!hasSamples) return;
    map.setLayoutProperty('paleo:samples', 'visibility', on && samplesOn ? 'visible' : 'none');
  };
  if (hasSamples) {
    root.querySelector('.paleo-samples-row').hidden = false;
    samplesBox.addEventListener('change', () => {
      samplesOn = samplesBox.checked;
      applySamplesVisibility(toggle.checked);
      if (samplesOn) show(age);
      else sampleCount.textContent = '';
    });
  }

  const lineamentsBox = root.querySelector('#paleo-lineaments-toggle');
  let lineamentsOn = false;
  const applyLineamentsVisibility = (on) => {
    if (!hasLineaments) return;
    map.setLayoutProperty('paleo:lineaments', 'visibility', on && lineamentsOn ? 'visible' : 'none');
  };
  if (hasLineaments) {
    root.querySelector('.paleo-lineaments-row').hidden = false;
    lineamentsBox.addEventListener('change', () => {
      lineamentsOn = lineamentsBox.checked;
      applyLineamentsVisibility(toggle.checked);
      if (lineamentsOn) show(age);
    });
  }

  function setOn(on) {
    applyLineamentsVisibility(on);
    const vis = on ? 'visible' : 'none';
    map.setLayoutProperty(FILL, 'visibility', vis);
    map.setLayoutProperty(LINE, 'visibility', vis);
    applySamplesVisibility(on);
    slider.disabled = !on;
    play.disabled = !on;
    root.classList.toggle('is-on', on);
    if (!on) {
      stop();
      token += 1; // descarta quadros em voo
      if (volcSource) volcSource.setData(volcOriginal);
    } else show(age);
  }

  toggle.addEventListener('change', () => setOn(toggle.checked));
  slider.addEventListener('input', () => { stop(); show(sliderToAge(slider.value)); });
  play.addEventListener('click', () => (timer ? stop() : start()));
  label.textContent = ageLabel(age);
  // o navegador restaura caixas marcadas ao recarregar: alinha a tela com o estado inicial (desligado)
  toggle.checked = false;
  if (samplesBox) samplesBox.checked = false;
  if (lineamentsBox) lineamentsBox.checked = false;
  setOn(false);
  return { show, stop };
}
