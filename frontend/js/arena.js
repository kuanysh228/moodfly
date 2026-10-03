// Top-down arena with the fly. World units are mm, y axis points up.
import { DEFAULT_LOOK, drawFlyBody } from "./flyart.js";

const DROP_STYLE = {
  sugar: { fill: "#f4ead2", edge: "#d9c79a", label: "сахар" },
  bitter: { fill: "#9b7fd6", edge: "#6d55a8", label: "горькое" },
  water: { fill: "#8fc9f0", edge: "#5a9fd0", label: "вода" },
};
const ODOR_STYLE = {
  odor_good: { rgb: "120, 200, 90" },
  odor_bad: { rgb: "150, 120, 80" },
};

export class Arena {
  constructor(canvas, onClick) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.R = 20;
    this.flyLen = 2.6;
    this.state = null;
    this.look = DEFAULT_LOOK; // set from the pet's stats
    this.emotion = null;
    this.prev = null;
    this.lastT = 0;
    new ResizeObserver(() => this.resize()).observe(canvas);
    this.resize();
    canvas.addEventListener("click", (ev) => {
      const r = canvas.getBoundingClientRect();
      const [x, y] = this.toWorld(ev.clientX - r.left, ev.clientY - r.top);
      const fly = this.state?.fly;
      const onFly = !!fly && Math.hypot(fly.x - x, fly.y - y) < this.flyLen * 0.7;
      onClick({ x, y, onFly });
    });
  }

  configure(hello) {
    this.R = hello.arena_r;
    this.flyLen = hello.fly_len;
  }

  resize() {
    const dpr = window.devicePixelRatio || 1;
    const { width, height } = this.canvas.getBoundingClientRect();
    this.canvas.width = Math.round(width * dpr);
    this.canvas.height = Math.round(height * dpr);
    this.dpr = dpr;
    this.size = Math.min(width, height);
  }

  get scale() { return (this.size / 2 - 10) / this.R; }

  toWorld(px, py) {
    const c = this.size / 2;
    return [(px - c) / this.scale, -(py - c) / this.scale];
  }

  update(world, emotion) {
    this.prev = this.state;
    this.state = world;
    this.emotion = emotion;
    this.lastT = performance.now();
  }

  // Interpolate flies between server frames (~25 fps) for smooth motion.
  pose(cur, p) {
    if (!p) return cur;
    const u = Math.min(1, (performance.now() - this.lastT) / 40);
    let dh = cur.heading - p.heading;
    dh = Math.atan2(Math.sin(dh), Math.cos(dh));
    return { ...cur, x: p.x + (cur.x - p.x) * u, y: p.y + (cur.y - p.y) * u, heading: p.heading + dh * u };
  }

  flyPose() { return this.pose(this.state.fly, this.prev?.fly); }

  draw() {
    const { ctx, dpr } = this;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const S = this.size;
    ctx.clearRect(0, 0, S, S);
    if (!this.state) return;
    const st = this.state;
    const c = S / 2, k = this.scale;
    const toS = (x, y) => [c + x * k, c - y * k];

    // floor
    const g = ctx.createRadialGradient(c, c, 0, c, c, this.R * k);
    if (st.light) { g.addColorStop(0, "#3a3a33"); g.addColorStop(1, "#24241f"); }
    else { g.addColorStop(0, "#15161a"); g.addColorStop(1, "#0c0d10"); }
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.arc(c, c, this.R * k, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = st.light ? "#5b5a4e" : "#2b2d33";
    ctx.lineWidth = 3; ctx.stroke();
    ctx.strokeStyle = st.light ? "rgba(255,255,255,0.04)" : "rgba(255,255,255,0.02)";
    ctx.lineWidth = 1;
    for (let r = 5; r < this.R; r += 5) { ctx.beginPath(); ctx.arc(c, c, r * k, 0, Math.PI * 2); ctx.stroke(); }

    // odour clouds (clipped to the arena), then drops
    ctx.save();
    ctx.beginPath(); ctx.arc(c, c, this.R * k, 0, Math.PI * 2); ctx.clip();
    for (const it of st.items) {
      const s = ODOR_STYLE[it.kind];
      if (!s) continue;
      const [x, y] = toS(it.x, it.y);
      const rg = ctx.createRadialGradient(x, y, 0, x, y, 9 * k);
      rg.addColorStop(0, `rgba(${s.rgb}, ${0.35 * it.amount})`);
      rg.addColorStop(1, `rgba(${s.rgb}, 0)`);
      ctx.fillStyle = rg;
      ctx.beginPath(); ctx.arc(x, y, 9 * k, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = `rgb(${s.rgb})`; ctx.strokeStyle = "rgba(0,0,0,0.35)"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.arc(x, y, Math.max(4, 0.45 * k), 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    }
    ctx.restore();
    const contact = new Set(st.contact || []);
    for (const it of st.items) {
      const s = DROP_STYLE[it.kind];
      if (!s) continue;
      const [x, y] = toS(it.x, it.y);
      const r = it.r * k;
      ctx.fillStyle = s.fill; ctx.strokeStyle = contact.has(it.kind) ? "#fff" : s.edge;
      ctx.lineWidth = contact.has(it.kind) ? 2.5 : 1.5;
      ctx.globalAlpha = 0.9;
      ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.fillStyle = "rgba(255,255,255,0.7)";
      ctx.beginPath(); ctx.arc(x - r * 0.35, y - r * 0.35, r * 0.22, 0, Math.PI * 2); ctx.fill();
    }

    if (st.owner) {
      const [ox, oy] = toS(st.owner.x, st.owner.y);
      const u = Math.max(5, 0.5 * k);
      ctx.fillStyle = "#8a93a3";
      ctx.beginPath(); ctx.arc(ox, oy - u * 0.9, u * 0.55, 0, Math.PI * 2); ctx.fill();
      ctx.beginPath(); ctx.ellipse(ox, oy + u * 0.55, u, u * 0.75, 0, Math.PI, 0); ctx.fill();
    }

    if (st.flies) {
      st.flies.forEach((f, i) => {
        const pose = this.pose(f, this.prev?.flies?.[i]);
        this.drawFly(pose, toS, k, false, `hsl(${f.hue} 70% 60%)`);
        this.drawTag(pose, toS, k, f);
      });
      return;
    }
    const fly = this.flyPose();

    // looming shadow: flies from the click point towards the fly and grows
    if (st.threat) {
      const p = st.threat.progress;
      const tx = st.threat.x + (fly.x - st.threat.x) * p * 0.6;
      const ty = st.threat.y + (fly.y - st.threat.y) * p * 0.6;
      const [x, y] = toS(tx, ty);
      const r = (1.5 + 7 * p * p) * k;
      const sg = ctx.createRadialGradient(x, y, r * 0.3, x, y, r);
      sg.addColorStop(0, `rgba(0,0,0,${0.55 + 0.3 * p})`);
      sg.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = sg;
      ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
    }

    // air puff towards the head
    if (st.puff) {
      const t = performance.now() / 120;
      ctx.strokeStyle = "rgba(200,225,255,0.6)"; ctx.lineWidth = 2;
      for (let i = -2; i <= 2; i++) {
        const a = fly.heading + i * 0.15;
        const d0 = 3 + ((t + i) % 3), d1 = d0 + 2.2;
        const [x0, y0] = toS(fly.x + Math.cos(a) * d0, fly.y + Math.sin(a) * d0);
        const [x1, y1] = toS(fly.x + Math.cos(a) * d1, fly.y + Math.sin(a) * d1);
        ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
      }
    }

    this.drawFly(fly, toS, k, st.touch);
    this.drawBubble(fly, toS, k);
  }

  drawFly(f, toS, k, touched, ring) {
    const ctx = this.ctx;
    const [sx, sy] = toS(f.x, f.y);
    const alt = f.alt || 0;
    const sc = k * (1 + 0.45 * alt);
    if (ring) {
      ctx.strokeStyle = ring; ctx.lineWidth = 2; ctx.globalAlpha = 0.8;
      ctx.beginPath(); ctx.arc(sx, sy, 1.5 * sc, 0, Math.PI * 2); ctx.stroke();
      ctx.globalAlpha = 1;
    }

    if (alt > 0) { // shadow on the floor while airborne
      ctx.fillStyle = `rgba(0,0,0,${0.35 * (1 - alt * 0.5)})`;
      ctx.beginPath(); ctx.ellipse(sx + alt * 12, sy + alt * 16, 1.3 * k, 0.7 * k, -f.heading, 0, Math.PI * 2); ctx.fill();
    }

    ctx.save();
    ctx.translate(sx, sy);
    ctx.rotate(-f.heading);
    ctx.scale(sc, sc);
    drawFlyBody(ctx, f, this.look);
    if (touched) {
      ctx.strokeStyle = "rgba(255,255,255,0.8)"; ctx.lineWidth = 0.06;
      ctx.beginPath(); ctx.arc(0.95, 0, 0.55 + 0.1 * Math.sin(performance.now() / 60), 0, Math.PI * 2); ctx.stroke();
    }
    ctx.restore();
  }

  drawTag(f, toS, k, info) {
    const ctx = this.ctx;
    const [sx, sy] = toS(f.x, f.y);
    const w = 56, y = sy - 2.2 * k - 18;
    ctx.font = "600 12px system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif";
    ctx.textAlign = "center"; ctx.textBaseline = "alphabetic";
    ctx.fillStyle = "#eef0f3";
    ctx.fillText(info.name, sx, y - 3);
    const frac = Math.max(0, info.hp / info.max_hp);
    ctx.fillStyle = "#1d222b"; ctx.fillRect(sx - w / 2, y, w, 5);
    ctx.fillStyle = frac > 0.5 ? "#3fae5a" : frac > 0.25 ? "#c98500" : "#e5484d";
    ctx.fillRect(sx - w / 2, y, w * frac, 5);
  }

  drawBubble(f, toS, k) {
    const e = this.emotion;
    if (!e) return;
    const ctx = this.ctx;
    const [sx, sy] = toS(f.x, f.y);
    const text = e.label;
    ctx.font = "600 13px system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif";
    const w = ctx.measureText(text).width + 16;
    let x = Math.min(Math.max(sx - w / 2, 4), this.size - w - 4);
    let y = sy - 2.6 * k - 30;
    if (y < 4) y = sy + 2.4 * k + 6;
    ctx.fillStyle = "rgba(13,15,19,0.82)";
    ctx.strokeStyle = e.color;
    ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.roundRect(x, y, w, 24, 12); ctx.fill(); ctx.stroke();
    ctx.fillStyle = "#eef0f3";
    ctx.textAlign = "left"; ctx.textBaseline = "middle";
    ctx.fillText(text, x + 8, y + 12.5);
  }
}
