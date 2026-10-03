// Fighting-game style battle renderer: follow camera, big flies, hit sparks, damage numbers, HUD.
import { drawFlyBody, lookFromStats } from "./flyart.js";

const FONT = "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif";
const rand = (a, b) => a + Math.random() * (b - a);
const lerp = (a, b, u) => a + (b - a) * u;
const ease = (u) => 1 - (1 - u) ** 3;

export class FightRenderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.R = 12;
    new ResizeObserver(() => this.resize()).observe(canvas);
    this.resize();
    this.reset();
  }

  configure(hello) { this.R = hello.arena_r; }

  resize() {
    const dpr = window.devicePixelRatio || 1;
    const { width, height } = this.canvas.getBoundingClientRect();
    this.canvas.width = Math.round(width * dpr);
    this.canvas.height = Math.round(height * dpr);
    this.dpr = dpr; this.w = width; this.h = height;
  }

  reset() {
    this.frame = null; this.prev = null; this.lastT = 0;
    this.cam = { x: 0, y: 0, z: 0 };
    this.particles = []; this.floaters = []; this.rings = [];
    this.shake = 0;
    this.fighters = [0, 1].map(() => ({ flash: 0, hpShown: null, hpLag: null, lagHold: 0, trail: [], look: null }));
    this.banner = null; this.overAt = 0; this.phase = null;
  }

  setFrame(f) {
    const now = performance.now();
    if (this.frame && (this.frame.flies[0].name !== f.flies[0].name || this.frame.flies[1].name !== f.flies[1].name)) this.reset();
    this.prev = this.frame; this.frame = f; this.lastT = now;
    f.flies.forEach((fl, i) => {
      const st = this.fighters[i];
      st.look = lookFromStats(fl.stats, fl.hue);
      if (st.hpShown === null) { st.hpShown = fl.hp; st.hpLag = fl.hp; }
    });
    if (f.phase !== this.phase) {
      if (f.phase === "fight" && this.phase === "intro") this.banner = { text: "БОЙ!", color: "#ffd166", t0: now, dur: 900 };
      if (f.phase === "over") {
        this.overAt = now;
        const ko = (f.fx || []).some((e) => e.k === "ko") || f.flies.some((fl) => fl.hp <= 0);
        this.banner = { text: ko ? "НОКАУТ!" : f.winner === null ? "НИЧЬЯ" : "ВРЕМЯ!", color: "#ff5d5d", t0: now, dur: 1600 };
        if (f.winner !== null) this.confetti(f.flies[f.winner]);
      }
      this.phase = f.phase;
    }
    for (const e of f.fx || []) this.effect(e, f);
  }

  effect(e, f) {
    const me = f.flies[e.who];
    if (!me) return;
    if (e.k === "hit") {
      const tg = f.flies[e.target];
      const st = this.fighters[e.target];
      st.flash = 1;
      const n = e.crit ? 34 : 18;
      for (let i = 0; i < n; i++) {
        const a = rand(0, Math.PI * 2), v = rand(4, e.crit ? 16 : 10);
        this.particles.push({ x: tg.x, y: tg.y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, life: rand(0.3, 0.6), max: 0.6, size: rand(0.08, 0.2), color: i % 3 ? "#ffb347" : "#fff6d5", drag: 4 });
      }
      this.rings.push({ x: tg.x, y: tg.y, t0: performance.now(), dur: 350, color: e.crit ? "#ff5d5d" : "#ffd166" });
      this.float(tg.x, tg.y, e.crit ? `КРИТ! −${e.dmg}` : `−${e.dmg}`, e.crit ? "#ff5d5d" : "#ffd166", e.crit ? 1.6 : 1.15);
      this.shake = Math.max(this.shake, e.crit ? 14 : 7);
    } else if (e.k === "dodge") {
      this.float(me.x, me.y, "УВОРОТ!", "#5ad1ff", 1.0);
      this.rings.push({ x: me.x, y: me.y, t0: performance.now(), dur: 300, color: "#5ad1ff" });
    } else if (e.k === "jump") {
      this.float(me.x, me.y, `DNp01 ${e.hz} Гц`, "#fff27a", 0.95);
      for (let i = 0; i < 14; i++) {
        const a = rand(0, Math.PI * 2), v = rand(1.5, 4);
        this.particles.push({ x: me.x, y: me.y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, life: rand(0.4, 0.8), max: 0.8, size: rand(0.15, 0.35), color: "rgba(200,190,170,0.6)", drag: 3, dust: true });
      }
    } else if (e.k === "lunge") {
      const back = me.heading + Math.PI;
      for (let i = 0; i < 6; i++) {
        const a = back + rand(-0.6, 0.6), v = rand(1, 3);
        this.particles.push({ x: me.x, y: me.y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, life: rand(0.3, 0.5), max: 0.5, size: rand(0.12, 0.25), color: "rgba(200,190,170,0.5)", drag: 3, dust: true });
      }
    } else if (e.k === "flee") {
      this.float(me.x, me.y, "испуг", "#c9a7ff", 1.0);
    } else if (e.k === "groom") {
      this.float(me.x, me.y, "чешется…", "#b4bac4", 0.8);
    } else if (e.k === "ko") {
      this.shake = 22;
      for (let i = 0; i < 40; i++) {
        const a = rand(0, Math.PI * 2), v = rand(3, 14);
        this.particles.push({ x: me.x, y: me.y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, life: rand(0.5, 1.0), max: 1.0, size: rand(0.1, 0.25), color: i % 2 ? "#ff5d5d" : "#fff", drag: 3 });
      }
    }
  }

  float(x, y, text, color, scale) {
    this.floaters.push({ x, y, text, color, scale, t0: performance.now(), dur: 1100, dx: rand(-0.6, 0.6) });
  }

  confetti(fl) {
    for (let i = 0; i < 90; i++) {
      this.particles.push({
        screen: true, x: this.w / 2 + rand(-60, 60), y: this.h * 0.38, vx: rand(-260, 260), vy: rand(-420, -120),
        life: rand(1.4, 2.6), max: 2.6, size: rand(4, 8), color: `hsl(${(fl.hue + rand(-40, 40) + 360) % 360} 85% 62%)`, gravity: 520, spin: rand(-8, 8), rot: rand(0, 6),
      });
    }
  }

  poses(now) {
    const f = this.frame;
    const u = Math.min(1, (now - this.lastT) / 40);
    return f.flies.map((fl, i) => {
      const p = this.prev?.flies?.[i];
      if (!p) return fl;
      let dh = fl.heading - p.heading;
      dh = Math.atan2(Math.sin(dh), Math.cos(dh));
      return { ...fl, x: lerp(p.x, fl.x, u), y: lerp(p.y, fl.y, u), heading: p.heading + dh * u };
    });
  }

  draw() {
    const { ctx, dpr, w, h } = this;
    const now = performance.now();
    const dt = Math.min(0.05, (now - (this.lastDraw || now)) / 1000);
    this.lastDraw = now;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const bg = ctx.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, Math.max(w, h) * 0.7);
    bg.addColorStop(0, "#1a1d24"); bg.addColorStop(1, "#07080b");
    ctx.fillStyle = bg; ctx.fillRect(0, 0, w, h);
    if (!this.frame) return;
    const f = this.frame;
    const P = this.poses(now);

    // camera: frame both fighters, close-up when they clinch
    const cx = (P[0].x + P[1].x) / 2, cy = (P[0].y + P[1].y) / 2;
    const d = Math.hypot(P[0].x - P[1].x, P[0].y - P[1].y);
    const minDim = Math.min(w, h);
    const fit = minDim / (2 * this.R + 2);
    const target = Math.max(fit, Math.min(minDim / 13, minDim / (d + 11)));
    const k = 1 - Math.exp(-dt * 3);
    if (!this.cam.z) Object.assign(this.cam, { x: cx, y: cy, z: target });
    this.cam.x = lerp(this.cam.x, cx, k); this.cam.y = lerp(this.cam.y, cy, k); this.cam.z = lerp(this.cam.z, target, k);
    this.shake *= Math.exp(-dt * 9);
    const sx = (Math.random() - 0.5) * this.shake, sy = (Math.random() - 0.5) * this.shake;
    const Z = this.cam.z;
    const toS = (x, y) => [w / 2 + (x - this.cam.x) * Z + sx, h / 2 - (y - this.cam.y) * Z + sy];

    this.drawFloor(toS, Z);

    // auras, shadows, trails, flies
    P.forEach((p, i) => {
      const st = this.fighters[i];
      const [px, py] = toS(p.x, p.y);
      const alt = p.alt || 0;
      if (p.rage > 0.15 && f.phase !== "over") {
        const r = (1.6 + p.rage * 1.4 + Math.sin(now / 90) * 0.1) * Z;
        const g = ctx.createRadialGradient(px, py, 0, px, py, r);
        g.addColorStop(0, `rgba(255,60,40,${0.32 * p.rage})`); g.addColorStop(1, "rgba(255,60,40,0)");
        ctx.fillStyle = g; ctx.beginPath(); ctx.arc(px, py, r, 0, Math.PI * 2); ctx.fill();
      }
      if (p.fear > 0.25 && f.phase !== "over") {
        ctx.strokeStyle = `rgba(150,120,255,${0.5 * p.fear})`; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(px, py, (1.5 + 0.12 * Math.sin(now / 40)) * Z, 0, Math.PI * 2); ctx.stroke();
      }
      ctx.fillStyle = `rgba(0,0,0,${0.45 - 0.2 * alt})`;
      ctx.beginPath(); ctx.ellipse(px + alt * 0.9 * Z, py + alt * 1.2 * Z, 1.3 * Z, 0.75 * Z, -p.heading, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = `hsla(${p.hue}, 80%, 60%, 0.85)`; ctx.lineWidth = 3;
      ctx.beginPath(); ctx.ellipse(px, py, 1.55 * Z, 1.0 * Z, -p.heading, 0, Math.PI * 2); ctx.stroke();

      const over = f.phase === "over";
      if (over) p.mode = p.hp > 0 ? "pause" : "ko";
      const fast = !over && (p.mode === "lunge" || p.mode === "flight");
      if (fast) st.trail.push({ x: p.x, y: p.y, heading: p.heading, alt, t: now });
      st.trail = st.trail.filter((g) => now - g.t < 160);
      for (const g of st.trail) {
        const [gx, gy] = toS(g.x, g.y);
        ctx.save(); ctx.globalAlpha = 0.25 * (1 - (now - g.t) / 160);
        ctx.translate(gx, gy); ctx.rotate(-g.heading); ctx.scale(Z * (1 + 0.4 * g.alt), Z * (1 + 0.4 * g.alt));
        drawFlyBody(ctx, p, st.look, { t: now, buzz: true });
        ctx.restore();
      }
      if (p.mode === "lunge" && !over) { // speed lines
        ctx.strokeStyle = "rgba(255,255,255,0.35)"; ctx.lineWidth = 1.5;
        for (let j = -2; j <= 2; j++) {
          const a = p.heading + Math.PI, off = j * 0.35;
          const bx = p.x + Math.cos(a) * 1.4 - Math.sin(a) * off, by = p.y + Math.sin(a) * 1.4 + Math.cos(a) * off;
          const [x0, y0] = toS(bx, by), [x1, y1] = toS(bx + Math.cos(a) * 1.6, by + Math.sin(a) * 1.6);
          ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
        }
      }
      st.flash = Math.max(0, st.flash - dt * 5);
      const ko = f.phase === "over" && p.hp <= 0;
      const squash = st.flash > 0 ? 1 - 0.12 * st.flash : 1;
      ctx.save();
      ctx.translate(px, py); ctx.rotate(-p.heading); ctx.scale(Z * (1 + 0.4 * alt) * squash, Z * (1 + 0.4 * alt) * (2 - squash));
      drawFlyBody(ctx, p, st.look, { t: now, flash: st.flash, ko, buzz: p.mode === "lunge" });
      ctx.restore();
    });

    this.drawParticles(toS, Z, dt);
    this.drawFloaters(toS, now);
    this.drawHud(f, now, dt);
    this.drawOverlays(f, now);
  }

  drawFloor(toS, Z) {
    const { ctx } = this;
    const [c0, c1] = toS(0, 0);
    const R = this.R * Z;
    const g = ctx.createRadialGradient(c0 - R * 0.3, c1 - R * 0.3, R * 0.1, c0, c1, R);
    g.addColorStop(0, "#3a372d"); g.addColorStop(1, "#1d1c17");
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(c0, c1, R, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = "rgba(255,255,255,0.05)"; ctx.lineWidth = 1;
    for (let r = 3; r < this.R; r += 3) { ctx.beginPath(); ctx.arc(c0, c1, r * Z, 0, Math.PI * 2); ctx.stroke(); }
    ctx.strokeStyle = "#6d6858"; ctx.lineWidth = Math.max(3, 0.35 * Z);
    ctx.beginPath(); ctx.arc(c0, c1, R, 0, Math.PI * 2); ctx.stroke();
    ctx.strokeStyle = "rgba(255,255,255,0.18)"; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(c0, c1, R - 3, Math.PI * 1.1, Math.PI * 1.6); ctx.stroke();
  }

  drawParticles(toS, Z, dt) {
    const { ctx } = this;
    this.particles = this.particles.filter((p) => (p.life -= dt) > 0);
    for (const p of this.particles) {
      const drag = Math.exp(-(p.drag || 0) * dt);
      p.vx *= drag; p.vy *= drag;
      if (p.gravity) p.vy += p.gravity * dt;
      p.x += p.vx * dt; p.y += p.vy * dt;
      const a = Math.min(1, p.life / (p.max * 0.5));
      if (p.screen) {
        p.rot += p.spin * dt;
        ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.rot); ctx.globalAlpha = a;
        ctx.fillStyle = p.color; ctx.fillRect(-p.size / 2, -p.size / 4, p.size, p.size / 2); ctx.restore();
        continue;
      }
      const [x, y] = toS(p.x, p.y);
      ctx.globalAlpha = a; ctx.fillStyle = p.color;
      ctx.beginPath(); ctx.arc(x, y, Math.max(1, p.size * Z * (p.dust ? 1 + (1 - a) : 1)), 0, Math.PI * 2); ctx.fill();
    }
    ctx.globalAlpha = 1;
    const now = performance.now();
    this.rings = this.rings.filter((r) => now - r.t0 < r.dur);
    for (const r of this.rings) {
      const u = (now - r.t0) / r.dur;
      const [x, y] = toS(r.x, r.y);
      ctx.strokeStyle = r.color; ctx.globalAlpha = 1 - u; ctx.lineWidth = 4 * (1 - u) + 1;
      ctx.beginPath(); ctx.arc(x, y, (0.5 + 2.2 * ease(u)) * Z, 0, Math.PI * 2); ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }

  drawFloaters(toS, now) {
    const { ctx } = this;
    this.floaters = this.floaters.filter((fl) => now - fl.t0 < fl.dur);
    for (const fl of this.floaters) {
      const u = (now - fl.t0) / fl.dur;
      const [x, y] = toS(fl.x + fl.dx * u, fl.y);
      const pop = u < 0.15 ? 0.6 + 2.6 * u : 1;
      ctx.save();
      ctx.translate(x, y - 50 - 60 * ease(u));
      ctx.scale(pop * fl.scale, pop * fl.scale);
      ctx.globalAlpha = u > 0.7 ? (1 - u) / 0.3 : 1;
      ctx.font = `900 22px ${FONT}`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.lineWidth = 5; ctx.strokeStyle = "rgba(0,0,0,0.8)"; ctx.strokeText(fl.text, 0, 0);
      ctx.fillStyle = fl.color; ctx.fillText(fl.text, 0, 0);
      ctx.restore();
    }
  }

  drawHud(f, now, dt) {
    const { ctx, w } = this;
    const barW = Math.max(120, w / 2 - 70), y = 14, bh = 16;
    f.flies.forEach((fl, i) => {
      const st = this.fighters[i];
      if (fl.hp < st.hpShown) { st.hpShown = fl.hp; st.lagHold = 0.45; }
      st.hpShown = fl.hp;
      st.lagHold -= dt;
      if (st.lagHold <= 0) st.hpLag = Math.max(fl.hp, st.hpLag - fl.max_hp * dt * 0.6);
      const frac = Math.max(0, fl.hp / fl.max_hp), lag = Math.max(0, st.hpLag / fl.max_hp);
      const x0 = i === 0 ? 14 : w - 14 - barW;
      const dir = i === 0 ? 1 : -1;
      const fillX = (u) => (i === 0 ? x0 + barW * (1 - u) : x0);
      // frame
      ctx.fillStyle = "rgba(0,0,0,0.55)"; ctx.fillRect(x0 - 3, y - 3, barW + 6, bh + 6);
      ctx.fillStyle = "#2a1215"; ctx.fillRect(x0, y, barW, bh);
      ctx.fillStyle = "#f4f4f4"; ctx.fillRect(fillX(lag), y, barW * lag, bh); // damage chunk
      const grad = ctx.createLinearGradient(x0, y, x0, y + bh);
      const col = frac > 0.5 ? ["#7ee081", "#3fae5a"] : frac > 0.25 ? ["#ffd166", "#c98500"] : ["#ff7b7b", "#e5484d"];
      grad.addColorStop(0, col[0]); grad.addColorStop(1, col[1]);
      ctx.fillStyle = grad; ctx.fillRect(fillX(frac), y, barW * frac, bh);
      ctx.strokeStyle = `hsl(${fl.hue} 80% 60%)`; ctx.lineWidth = 2; ctx.strokeRect(x0 - 1, y - 1, barW + 2, bh + 2);
      // name plate
      ctx.font = `800 15px ${FONT}`; ctx.textBaseline = "top";
      ctx.textAlign = i === 0 ? "left" : "right";
      const nx = i === 0 ? x0 : x0 + barW;
      ctx.lineWidth = 4; ctx.strokeStyle = "rgba(0,0,0,0.8)";
      const label = `${fl.name}  ур.${fl.level}`;
      ctx.strokeText(label, nx, y + bh + 6); ctx.fillStyle = "#fff"; ctx.fillText(label, nx, y + bh + 6);
      ctx.font = `600 11px ${FONT}`; ctx.fillStyle = "#b4bac4";
      ctx.fillText(`${Math.ceil(fl.hp)} HP · ярость ${Math.round(fl.rage * 100)}% · страх ${Math.round(fl.fear * 100)}%`, nx, y + bh + 25);
      void dir;
    });
    // timer
    const tx = w / 2;
    ctx.fillStyle = "rgba(0,0,0,0.6)"; ctx.beginPath(); ctx.arc(tx, y + 12, 24, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = "#ffd166"; ctx.lineWidth = 2; ctx.stroke();
    ctx.font = `900 18px ${FONT}`; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillStyle = "#fff";
    ctx.fillText(f.phase === "intro" ? "VS" : String(Math.ceil(f.time_left)), tx, y + 13);
  }

  drawOverlays(f, now) {
    const { ctx, w, h } = this;
    if (f.phase === "intro") {
      ctx.fillStyle = "rgba(0,0,0,0.45)"; ctx.fillRect(0, 0, w, h);
      const n = Math.max(1, Math.ceil(f.intro_left));
      const u = 1 - (f.intro_left % 1 || 1);
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.font = `900 ${Math.round(Math.min(w, h) * 0.07)}px ${FONT}`;
      f.flies.forEach((fl, i) => {
        const slide = ease(Math.min(1, (3 - f.intro_left) / 0.6));
        const x = i === 0 ? lerp(-w * 0.3, w * 0.27, slide) : lerp(w * 1.3, w * 0.73, slide);
        ctx.lineWidth = 6; ctx.strokeStyle = "rgba(0,0,0,0.85)"; ctx.strokeText(fl.name, x, h * 0.36);
        ctx.fillStyle = `hsl(${fl.hue} 85% 65%)`; ctx.fillText(fl.name, x, h * 0.36);
      });
      ctx.font = `900 ${Math.round(Math.min(w, h) * 0.06)}px ${FONT}`; ctx.fillStyle = "#ffd166"; ctx.fillText("VS", w / 2, h * 0.36);
      ctx.save(); ctx.translate(w / 2, h * 0.58); ctx.scale(1.6 - 0.6 * ease(u), 1.6 - 0.6 * ease(u));
      ctx.font = `900 ${Math.round(Math.min(w, h) * 0.18)}px ${FONT}`;
      ctx.lineWidth = 8; ctx.strokeStyle = "rgba(0,0,0,0.85)"; ctx.strokeText(String(n), 0, 0);
      ctx.fillStyle = "#fff"; ctx.fillText(String(n), 0, 0);
      ctx.restore();
    }
    if (this.banner) {
      const b = this.banner, u = (now - b.t0) / b.dur;
      if (u > 1 && f.phase !== "over") this.banner = null;
      else this.bigText(b.text, b.color, h * 0.42, Math.min(1, u), f.phase === "over");
    }
    if (f.phase === "over" && now - this.overAt > 900) {
      const sub = f.winner === null ? "Ничья" : `Победа: ${f.flies[f.winner].name}`;
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.font = `800 ${Math.round(Math.min(w, h) * 0.05)}px ${FONT}`;
      ctx.lineWidth = 6; ctx.strokeStyle = "rgba(0,0,0,0.85)"; ctx.strokeText(sub, w / 2, h * 0.56);
      ctx.fillStyle = f.winner === null ? "#fff" : `hsl(${f.flies[f.winner].hue} 85% 65%)`; ctx.fillText(sub, w / 2, h * 0.56);
    }
  }

  bigText(text, color, y, u, hold) {
    const { ctx, w, h } = this;
    const s = u < 0.2 ? lerp(2.2, 1, ease(u / 0.2)) : 1;
    const a = hold ? 1 : u > 0.75 ? (1 - u) / 0.25 : 1;
    ctx.save(); ctx.globalAlpha = a; ctx.translate(w / 2, y); ctx.scale(s, s);
    ctx.font = `900 ${Math.round(Math.min(w, h) * 0.12)}px ${FONT}`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.lineWidth = 10; ctx.strokeStyle = "rgba(0,0,0,0.85)"; ctx.strokeText(text, 0, 0);
    ctx.fillStyle = color; ctx.fillText(text, 0, 0);
    ctx.restore();
  }
}
