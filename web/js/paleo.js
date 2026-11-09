// Paleogeografia: linhas de costa reconstruidas por idade (Merdith et al. 2021, CC BY 4.0),
// com controle de tempo e animacao. Os quadros vem de data/paleo/coast_<idade>.geojson,
// carregados sob demanda. Textos do modelo entram so por textContent.

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

export async function mountPaleo(map, base, root) {
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
    + 'Reconstrução interpretativa, não observação. As demais camadas (vulcões, placas, amostras, zonas) '
    + 'continuam nas posições atuais.';

  async function show(a) {
    age = a;
    slider.value = String(ageToSlider(a));
    label.textContent = ageLabel(a);
    const my = ++token;
    try {
      const fc = await frame(a);
      if (my !== token) return; // chegou um quadro mais novo
      map.getSource(SRC).setData(fc);
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

  function setOn(on) {
    const vis = on ? 'visible' : 'none';
    map.setLayoutProperty(FILL, 'visibility', vis);
    map.setLayoutProperty(LINE, 'visibility', vis);
    slider.disabled = !on;
    play.disabled = !on;
    root.classList.toggle('is-on', on);
    if (!on) stop();
    else show(age);
  }

  toggle.addEventListener('change', () => setOn(toggle.checked));
  slider.addEventListener('input', () => { stop(); show(sliderToAge(slider.value)); });
  play.addEventListener('click', () => (timer ? stop() : start()));
  label.textContent = ageLabel(age);
  setOn(false);
  return { show, stop };
}
