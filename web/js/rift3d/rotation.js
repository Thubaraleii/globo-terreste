// Matematica de rotacao da vista 3D (funcoes puras, sem Three.js).
// Mapeamento geografico -> Three.js (Y para cima): x = cos(lat)cos(lon), y = sin(lat), z = -cos(lat)sin(lon).
// Quaternions como [x, y, z, w]. A interpolacao entre quadros de 5 Ma e por slerp: aproximacao das
// rotacoes finitas do modelo entre dois quadros vizinhos (exata nos quadros).

const RAD = Math.PI / 180;

export function geoToXYZ(lonDeg, latDeg, r = 1) {
  const lon = lonDeg * RAD;
  const lat = latDeg * RAD;
  return [r * Math.cos(lat) * Math.cos(lon), r * Math.sin(lat), -r * Math.cos(lat) * Math.sin(lon)];
}

// Rotacao anti-horaria vista de fora, em torno do polo (lat, lon), pelo angulo dado.
export function quatFromPoleAngle(poleLatDeg, poleLonDeg, angleDeg) {
  const [ax, ay, az] = geoToXYZ(poleLonDeg, poleLatDeg);
  const half = (angleDeg * RAD) / 2;
  const s = Math.sin(half);
  return [ax * s + 0, ay * s + 0, az * s + 0, Math.cos(half)];
}

export function slerp(q0, q1, t) {
  let b = q1;
  let dot = q0[0] * b[0] + q0[1] * b[1] + q0[2] * b[2] + q0[3] * b[3];
  if (dot < 0) {
    b = b.map((c) => -c);
    dot = -dot;
  }
  let k0;
  let k1;
  if (dot > 0.9995) {
    k0 = 1 - t;
    k1 = t;
  } else {
    const theta = Math.acos(dot);
    const sin = Math.sin(theta);
    k0 = Math.sin((1 - t) * theta) / sin;
    k1 = Math.sin(t * theta) / sin;
  }
  const out = q0.map((c, i) => c * k0 + b[i] * k1);
  const n = Math.hypot(...out);
  return out.map((c) => c / n);
}

// frames: [{age, pole_lat, pole_lon, angle_deg}] (qualquer ordem). Fora do intervalo usa o quadro da ponta.
export function quatAt(frames, age) {
  if (!frames || frames.length === 0) return [0, 0, 0, 1];
  const sorted = [...frames].sort((a, b) => a.age - b.age);
  const q = (f) => quatFromPoleAngle(f.pole_lat, f.pole_lon, f.angle_deg);
  if (age <= sorted[0].age) return q(sorted[0]);
  const last = sorted[sorted.length - 1];
  if (age >= last.age) return q(last);
  const i = sorted.findIndex((f) => f.age >= age);
  const a = sorted[i - 1];
  const b = sorted[i];
  return slerp(q(a), q(b), (age - a.age) / (b.age - a.age));
}

export function rotateXYZ(q, v) {
  const [qx, qy, qz, qw] = q;
  const [x, y, z] = v;
  // t = 2 * cross(q.xyz, v); v' = v + w*t + cross(q.xyz, t)
  const tx = 2 * (qy * z - qz * y);
  const ty = 2 * (qz * x - qx * z);
  const tz = 2 * (qx * y - qy * x);
  return [
    x + qw * tx + (qy * tz - qz * ty),
    y + qw * ty + (qz * tx - qx * tz),
    z + qw * tz + (qx * ty - qy * tx),
  ];
}
