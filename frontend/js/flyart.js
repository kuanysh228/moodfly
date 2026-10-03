// Drawing a fly whose body reflects its genes/stats. Units: mm, origin at the thorax, facing +x.

export function lookFromStats(stats, hue = 30) {
  const s = stats || {};
  const n = (v) => (v ?? 50) / 100;
  return {
    body: 0.88 + 0.3 * n(s.strength), // Mhc: bulkier thorax and head
    legs: 0.85 + 0.4 * n(s.speed), // Dll: longer legs
    wings: 0.85 + 0.4 * n(s.agility), // vg: larger wings
    armor: n(s.durability), // ebony: darker, plated cuticle
    hue,
  };
}

export const DEFAULT_LOOK = lookFromStats({}, 30);

function mix(a, b, u) {
  return a.map((x, i) => Math.round(x + (b[i] - x) * u));
}
const rgb = (c, a = 1) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;

// f: {mode, gait, groom, proboscis, alt}; opts: {flash, ko, t, buzz}
export function drawFlyBody(ctx, f, look = DEFAULT_LOOK, opts = {}) {
  const t = opts.t ?? performance.now();
  const alt = f.alt || 0;
  const ko = !!opts.ko;
  const L = look;
  const armor = L.armor;
  const cuticle = mix([176, 138, 79], [70, 52, 34], armor); // tan -> ebony
  const thoraxC = mix([141, 106, 61], [58, 42, 30], armor);
  const headC = mix([122, 90, 51], [62, 46, 32], armor);
  ctx.lineCap = "round";
  ctx.lineJoin = "round";

  // legs
  const phase = (f.gait || 0) * Math.PI * 2;
  const moving = ["walk", "backup", "come", "flee", "attack", "lunge"].includes(f.mode);
  const legs = [
    { ax: 0.55, ex: 1.3, ey: 0.85, grp: 0 }, { ax: 0.35, ex: 0.3, ey: 1.15, grp: 1 }, { ax: 0.15, ex: -0.75, ey: 1.0, grp: 0 },
  ];
  ctx.strokeStyle = rgb(mix([42, 31, 23], [20, 14, 10], armor));
  ctx.lineWidth = 0.09 * (0.9 + 0.3 * armor);
  for (const side of [1, -1]) {
    legs.forEach((leg, i) => {
      const grp = side === 1 ? leg.grp : 1 - leg.grp;
      const swing = moving ? Math.sin(phase + grp * Math.PI) * 0.28 : 0;
      let ex = leg.ax + (leg.ex - leg.ax) * L.legs + swing, ey = leg.ey * side * L.legs;
      if (alt > 0) { ex = leg.ax - 0.4 - i * 0.15; ey = 0.45 * side; }
      if (i === 0 && f.mode === "groom") {
        const g = Math.sin((f.groom || 0) * Math.PI * 2 + (side > 0 ? 0 : Math.PI));
        ex = 1.05 + 0.25 * g; ey = 0.32 * side;
      }
      if (ko) { // on its back: legs curled up and twitching
        const tw = Math.sin(t / 90 + i * 1.7 + side) * 0.08;
        ex = leg.ax + 0.15 + tw; ey = (0.45 + 0.1 * i) * side;
      }
      const kx = (leg.ax + ex) / 2 + 0.1, ky = ey * 0.75;
      ctx.beginPath(); ctx.moveTo(leg.ax, 0.2 * side); ctx.lineTo(kx, ky); ctx.lineTo(ex, ey); ctx.stroke();
    });
  }

  const B = L.body;
  // abdomen with stripes and team markings
  ctx.fillStyle = ko ? rgb(mix(cuticle, [225, 205, 170], 0.5)) : rgb(cuticle);
  ctx.beginPath(); ctx.ellipse(-0.55, 0, 0.78 * B, 0.47 * B, 0, 0, Math.PI * 2); ctx.fill();
  if (!ko) {
    ctx.strokeStyle = `rgba(30,18,8,${0.6 + 0.3 * armor})`; ctx.lineWidth = 0.13;
    for (const x of [-0.25, -0.6, -0.95]) {
      const h = 0.42 * B * Math.sqrt(Math.max(0, 1 - ((x + 0.55) / (0.8 * B)) ** 2)) + 0.02;
      ctx.beginPath(); ctx.ellipse(x, 0, 0.12, h, 0, -Math.PI / 2, Math.PI / 2); ctx.stroke();
    }
    ctx.strokeStyle = `hsla(${L.hue}, 80%, 60%, 0.9)`; ctx.lineWidth = 0.07;
    ctx.beginPath(); ctx.moveTo(-0.15, 0); ctx.lineTo(-1.15 * B, 0); ctx.stroke();
  }
  // thorax (+ armour plates and spines for durable flies)
  ctx.fillStyle = rgb(thoraxC);
  ctx.beginPath(); ctx.ellipse(0.35, 0, 0.5 * B, 0.42 * B, 0, 0, Math.PI * 2); ctx.fill();
  if (armor > 0.45 && !ko) {
    ctx.strokeStyle = `rgba(255,255,255,${0.12 + 0.25 * armor})`; ctx.lineWidth = 0.04;
    ctx.beginPath(); ctx.ellipse(0.35, 0, 0.36 * B, 0.3 * B, 0, 0, Math.PI * 2); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(0.35, -0.3 * B); ctx.lineTo(0.35, 0.3 * B); ctx.stroke();
  }
  if (armor > 0.7 && !ko) {
    ctx.fillStyle = rgb(mix(thoraxC, [20, 14, 10], 0.5));
    for (const side of [1, -1]) for (const x of [0.15, 0.45]) {
      ctx.beginPath();
      ctx.moveTo(x - 0.06, side * 0.38 * B); ctx.lineTo(x, side * 0.56 * B); ctx.lineTo(x + 0.06, side * 0.38 * B);
      ctx.fill();
    }
  }
  ctx.fillStyle = `rgba(255,255,255,${0.06 + 0.14 * armor})`;
  ctx.beginPath(); ctx.ellipse(0.42, -0.1, 0.25 * B, 0.14 * B, 0, 0, Math.PI * 2); ctx.fill();

  // wings
  for (const side of [1, -1]) {
    let ang = 0.13 * side, alpha = 0.38;
    if (alt > 0 || opts.buzz) { ang = (1.1 + 0.35 * Math.sin(t / 18)) * side; alpha = 0.22; }
    if (ko) { ang = 1.4 * side; alpha = 0.3; }
    ctx.save();
    ctx.translate(0.25, 0.1 * side);
    ctx.rotate(Math.PI + ang);
    ctx.fillStyle = `rgba(215,225,235,${alpha})`;
    ctx.strokeStyle = `rgba(120,130,140,${alpha + 0.2})`;
    ctx.lineWidth = 0.03;
    const W = L.wings;
    ctx.beginPath(); ctx.ellipse(0.95 * W, 0, 0.98 * W, 0.3 * W, 0, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    ctx.strokeStyle = `rgba(120,130,140,${alpha})`;
    ctx.beginPath(); ctx.moveTo(0.1, 0); ctx.lineTo(1.7 * W, 0.05); ctx.moveTo(0.3, 0.05); ctx.lineTo(1.4 * W, 0.2); ctx.stroke();
    ctx.restore();
  }

  // proboscis, head, eyes, antennae
  const hx = 0.95 + 0.1 * (B - 1);
  const prob = f.proboscis || 0;
  if (prob > 0.02) {
    ctx.strokeStyle = "#5a3d22"; ctx.lineWidth = 0.12;
    ctx.beginPath(); ctx.moveTo(hx + 0.2, 0); ctx.lineTo(hx + 0.25 + 0.55 * prob, 0); ctx.stroke();
    ctx.fillStyle = "#7a5530";
    ctx.beginPath(); ctx.ellipse(hx + 0.27 + 0.55 * prob, 0, 0.09, 0.13, 0, 0, Math.PI * 2); ctx.fill();
  }
  ctx.fillStyle = rgb(headC);
  ctx.beginPath(); ctx.ellipse(hx, 0, 0.3 * B, 0.36 * B, 0, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = "#c0302a";
  for (const side of [1, -1]) {
    ctx.beginPath(); ctx.ellipse(hx - 0.02, 0.25 * B * side, 0.2 * B, 0.15 * B, 0.25 * side, 0, Math.PI * 2); ctx.fill();
  }
  if (ko) {
    ctx.strokeStyle = "#fff"; ctx.lineWidth = 0.05;
    for (const side of [1, -1]) {
      const ex = hx, ey = 0.25 * B * side;
      ctx.beginPath(); ctx.moveTo(ex - 0.08, ey - 0.08); ctx.lineTo(ex + 0.08, ey + 0.08); ctx.moveTo(ex + 0.08, ey - 0.08); ctx.lineTo(ex - 0.08, ey + 0.08); ctx.stroke();
    }
  } else {
    ctx.fillStyle = "rgba(255,255,255,0.25)";
    for (const side of [1, -1]) { ctx.beginPath(); ctx.arc(hx + 0.03, 0.21 * B * side, 0.05, 0, Math.PI * 2); ctx.fill(); }
  }
  ctx.strokeStyle = "#3a2a1a"; ctx.lineWidth = 0.05;
  for (const side of [1, -1]) {
    ctx.beginPath(); ctx.moveTo(hx + 0.23, 0.07 * side); ctx.lineTo(hx + 0.37, 0.16 * side); ctx.lineTo(hx + 0.47, 0.3 * side); ctx.stroke();
  }

  if (opts.flash > 0) { // hit flash over the silhouette
    ctx.fillStyle = `rgba(255,255,255,${0.7 * opts.flash})`;
    ctx.beginPath(); ctx.ellipse(-0.55, 0, 0.78 * B, 0.47 * B, 0, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.ellipse(0.35, 0, 0.5 * B, 0.42 * B, 0, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.ellipse(hx, 0, 0.3 * B, 0.36 * B, 0, 0, Math.PI * 2); ctx.fill();
  }
}
