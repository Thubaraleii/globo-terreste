// Rotacao automatica do globo (liga/desliga). Gira em longitude; qualquer interacao do
// usuario com o mapa (arrastar, rolar, tocar) desliga a rotacao.

export const DEG_PER_SECOND = 6;

// Longitude seguinte, normalizada em [-180, 180).
export function nextLng(lng, dtSeconds, degPerSecond = DEG_PER_SECOND) {
  const v = lng + dtSeconds * degPerSecond;
  return ((((v + 180) % 360) + 360) % 360) - 180;
}

export function mountSpin(map, button) {
  let on = false;
  let raf = 0;
  let last = 0;

  function tick(now) {
    if (!on) return;
    const dt = Math.min((now - last) / 1000, 0.1);
    last = now;
    const c = map.getCenter();
    map.jumpTo({ center: [nextLng(c.lng, dt), c.lat] });
    raf = requestAnimationFrame(tick);
  }

  function set(next) {
    on = next;
    button.setAttribute('aria-pressed', String(on));
    button.classList.toggle('is-on', on);
    cancelAnimationFrame(raf);
    if (on) {
      last = performance.now();
      raf = requestAnimationFrame(tick);
    }
  }

  button.addEventListener('click', () => set(!on));
  // interacao do usuario (eventos com originalEvent) para a rotacao
  for (const ev of ['mousedown', 'touchstart', 'wheel']) {
    map.on(ev, () => { if (on) set(false); });
  }
  set(false);
  return { set, isOn: () => on };
}
