// Teste de fumaca com dados SINTETICOS (tests/e2e/data). Nao ha PMTiles aqui:
// as camadas geo_units e samples devem mostrar o aviso sem derrubar o resto.
import { test, expect } from '@playwright/test';

const PMTILES_RE = /(geo_units|samples)\.pmtiles/;
const FAVICON_RE = /\/favicon\.ico$/; // ruido do navegador, nao do app

// Observa erros nao capturados e erros de console, ignorando so a falha esperada
// de carregar os PMTiles inexistentes.
function watch(page) {
  const pageErrors = [];
  const consoleErrors = [];
  page.on('pageerror', (e) => pageErrors.push(String(e)));
  page.on('console', (m) => {
    if (m.type() !== 'error') return;
    // so a falha de carga do recurso, e so dos PMTiles ausentes
    if (PMTILES_RE.test(m.location().url) && /^Failed to load resource/.test(m.text())) return;
    if (FAVICON_RE.test(m.location().url)) return;
    consoleErrors.push(`${m.text()} @ ${m.location().url}`);
  });
  return { pageErrors, consoleErrors };
}

// Espera o mapa, a camada e a fonte de vulcoes prontos e parados.
async function ready(page) {
  await page.waitForFunction(() => {
    const m = window.geoworldMap;
    return !!m && m.loaded?.() && !!m.getLayer('volcanoes') && m.isSourceLoaded('volcanoes') && !m.isMoving();
  });
}

const open = async (page, hash = '') => {
  await page.goto(`/index.html${hash}`);
  await ready(page);
};

const visibility = (page, id) => page.evaluate((i) => window.geoworldMap.getLayoutProperty(i, 'visibility') ?? 'visible', id);

// Clica no centro do mapa (onde a URL centraliza o ponto desejado).
async function clickCenter(page) {
  const box = await page.locator('#map canvas.maplibregl-canvas').boundingBox();
  await page.waitForFunction(() => {
    const c = window.geoworldMap.getCanvas();
    const f = window.geoworldMap.queryRenderedFeatures(
      [[c.clientWidth / 2 - 4, c.clientHeight / 2 - 4], [c.clientWidth / 2 + 4, c.clientHeight / 2 + 4]],
      { layers: ['volcanoes'] },
    );
    return f.length > 0;
  });
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
}

test('a pagina carrega, o globo existe e nao ha erros inesperados', async ({ page }) => {
  const { pageErrors, consoleErrors } = watch(page);
  await open(page);
  await expect(page.locator('#map canvas.maplibregl-canvas')).toBeVisible();
  expect(await page.evaluate(() => window.geoworldMap.getProjection()?.type)).toBe('globe');
  expect(pageErrors).toEqual([]);
  expect(consoleErrors).toEqual([]);
});

test('ligar e desligar Vulcoes pelo painel muda a visibilidade da camada', async ({ page }) => {
  await open(page);
  const cb = page.locator('[data-layer-id="volcanoes"] .layer-head input[type="checkbox"]');
  await expect(cb).toBeChecked();
  expect(await visibility(page, 'volcanoes')).toBe('visible');
  await cb.uncheck();
  await expect.poll(() => visibility(page, 'volcanoes')).toBe('none');
  await cb.check();
  await expect.poll(() => visibility(page, 'volcanoes')).toBe('visible');
});

test('clicar num vulcao abre os detalhes com a fonte; Escape fecha e devolve o foco ao mapa', async ({ page }) => {
  await open(page, '#lng=10&lat=10&zoom=4&layers=volcanoes');
  await clickCenter(page);
  const details = page.locator('#details-panel');
  await expect(details).toBeVisible();
  await expect(details.locator('.details-heading')).toContainText('Vulcão Sintético Alfa');
  // a fonte vem de sources.json (carregada de forma assincrona)
  await expect(details).toContainText('Instituição SINTÉTICA de teste');
  await expect(details).toContainText('LICENÇA-SINTÉTICA');
  await page.keyboard.press('Escape');
  await expect(details).toBeHidden();
  await expect(page.locator('#map canvas.maplibregl-canvas')).toBeFocused();
});

test('uma URL com estado salvo restaura camadas, filtros e posicao', async ({ page }) => {
  await open(page, '#lng=25.5&lat=-12.25&zoom=3.5&layers=volcanoes,tectonic_zones&class=mafic&rock=basalto&coord=reported');
  await expect(page.locator('[data-layer-id="volcanoes"] .layer-head input[type="checkbox"]')).toBeChecked();
  await expect(page.locator('[data-layer-id="tectonic_zones"] .layer-head input[type="checkbox"]')).toBeChecked();
  await expect(page.locator('[data-layer-id="samples"] .layer-head input[type="checkbox"]')).not.toBeChecked();
  await expect(page.locator('[data-layer-id="geo_units"] .layer-head input[type="checkbox"]')).not.toBeChecked();
  expect(await visibility(page, 'samples:points')).toBe('none');
  await expect(page.getByLabel('Máfica', { exact: true })).toBeChecked();
  await expect(page.getByLabel('Ultramáfica', { exact: true })).not.toBeChecked();
  await expect(page.getByLabel('Nome da rocha contém')).toHaveValue('basalto');
  await expect(page.getByLabel('Origem da coordenada')).toHaveValue('reported');
  const view = await page.evaluate(() => {
    const m = window.geoworldMap;
    return { ...m.getCenter(), zoom: m.getZoom(), filter: m.getFilter('samples:points') };
  });
  expect(view.lng).toBeCloseTo(25.5, 2);
  expect(view.lat).toBeCloseTo(-12.25, 2);
  expect(view.zoom).toBeCloseTo(3.5, 2);
  expect(JSON.stringify(view.filter)).toContain('basalto');
});

test('filtros da URL sao validados; filtro de fonte vem de sources.json; Limpar filtros zera tudo', async ({ page }) => {
  await open(page, '#lng=0&lat=0&zoom=2&layers=volcanoes&class=foo&coord=bogus&source=sintetico-vulcoes&source=bogus&rock=x&lith=basic_volcanic');
  const filterOf = () => page.evaluate(() => window.geoworldMap.getFilter('samples:points') ?? null);
  const src = page.getByLabel('Instituição SINTÉTICA de teste', { exact: true });
  await expect(src).toBeChecked();
  await expect(page.getByLabel('Máfica', { exact: true })).not.toBeChecked();
  await expect(page.getByLabel('Origem da coordenada')).toHaveValue('');
  await expect.poll(async () => JSON.stringify(await filterOf())).not.toContain('bogus');
  const f = JSON.stringify(await filterOf());
  expect(f).toContain('sintetico-vulcoes');
  expect(f).not.toContain('foo');
  expect(f).not.toContain('coord_source');
  // atribuicao no mapa vem de sources.json
  await expect(page.locator('.maplibregl-ctrl-attrib')).toContainText('Atribuição sintética');
  await page.getByRole('button', { name: 'Limpar filtros' }).click();
  await expect(src).not.toBeChecked();
  await expect(page.getByLabel('Nome da rocha contém')).toHaveValue('');
  await expect(page.locator('.filter-lith')).toBeHidden();
  await expect.poll(filterOf).toBeNull();
  await expect.poll(() => page.evaluate(() => window.location.hash)).not.toContain('source=');
});

test('PMTiles ausentes mostram o aviso no painel e o resto continua funcionando', async ({ page }) => {
  const { pageErrors } = watch(page);
  await open(page, '#lng=10&lat=10&zoom=3&layers=geo_units,samples,volcanoes,tectonic_zones');
  await expect(page.locator('[data-warning-for="geo_units"]')).toContainText('Camada indisponível');
  await expect(page.locator('[data-warning-for="samples"]')).toContainText('Camada indisponível');
  await expect(page.locator('[data-warning-for="volcanoes"]')).toHaveText('');
  await expect(page.locator('[data-warning-for="tectonic_zones"]')).toHaveText('');
  // vulcoes seguem clicaveis
  await open(page, '#lng=10&lat=10&zoom=4&layers=geo_units,samples,volcanoes');
  await clickCenter(page);
  await expect(page.locator('#details-panel .details-heading')).toContainText('Vulcão Sintético Alfa');
  expect(pageErrors).toEqual([]);
});

test('um nome com HTML aparece como texto e nao executa', async ({ page }) => {
  await open(page, '#lng=-60&lat=-20&zoom=4&layers=volcanoes');
  await clickCenter(page);
  const heading = page.locator('#details-panel .details-heading');
  await expect(heading).toContainText('<img src=x onerror=window.__xss=1>');
  await expect(page.locator('#details-panel img')).toHaveCount(0);
  expect(await page.evaluate(() => window.__xss)).toBeUndefined();
});
