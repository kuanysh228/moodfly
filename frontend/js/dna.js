// Pet passport as a genome: a rotating DNA double helix whose gene loci you mutate with level points.
import { drawFlyBody, lookFromStats } from "./flyart.js";

export const GENES = [
  { stat: "strength", sym: "Mhc", name: "Myosin heavy chain", what: "белок мышц ног и полёта", color: "#ff7a59", trainable: true },
  { stat: "speed", sym: "Dll", name: "Distal-less", what: "длина и сила ног", color: "#4cd07d", trainable: true },
  { stat: "agility", sym: "vg", name: "vestigial", what: "размер и мощность крыльев", color: "#4aa8ff", trainable: true },
  { stat: "durability", sym: "e", name: "ebony", what: "твёрдая тёмная кутикула", color: "#e0b03a", trainable: true },
  { stat: "learning", sym: "rut", name: "rutabaga", what: "память грибовидного тела", color: "#b48cff", trainable: false },
  { stat: "temper", sym: "Tk", name: "Tachykinin", what: "нейропептид агрессии", color: "#e06bb0", trainable: false },
  { stat: "courage", sym: "5-HT1A", name: "серотониновый рецептор", what: "тревожность", color: "#8c9bff", trainable: false },
];
const BASES = "ATGC";
const PAIR = { A: "T", T: "A", G: "C", C: "G" };
const SEQ_LEN = 18;
const FONT = "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif";
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

function rng(seed) { // mulberry32
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Gene sequence for a pet, with one point mutation per invested point. */
export function sequence(seed, gi, points) {
  const r = rng((seed % 2147483647) * 31 + gi * 7919);
  const seq = Array.from({ length: SEQ_LEN }, () => BASES[Math.floor(r() * 4)]);
  const mutated = new Set();
  const m = rng((seed % 2147483647) * 17 + gi * 104729 + 1);
  for (let k = 0; k < points; k++) {
    const pos = Math.floor(m() * SEQ_LEN);
    const choices = BASES.replace(seq[pos], "");
    seq[pos] = choices[Math.floor(m() * 3)];
    mutated.add(pos);
  }
  return { seq, mutated };
}

export class DnaPanel {
  constructor(els, send) {
    this.els = els; // {helix, portrait, genes}
    this.send = send;
    this.pet = null;
    this.owner = false;
    this.phase = 0;
    this.mutating = null; // {gi, t0}
    this.hover = -1;
    this.pulse = 0;
    this.look = null;
    this.particles = [];
    els.helix.addEventListener("pointermove", (e) => (this.hover = this.geneAt(e.offsetX)));
    els.helix.addEventListener("pointerleave", () => (this.hover = -1));
    els.helix.addEventListener("click", (e) => this.mutate(this.geneAt(e.offsetX)));
    els.genes.addEventListener("click", (e) => {
      const gi = e.target.closest("[data-gene]")?.dataset.gene;
      if (gi !== undefined) this.mutate(+gi);
    });
  }

  geneAt(x) {
    const w = this.els.helix.getBoundingClientRect().width;
    return Math.max(0, Math.min(GENES.length - 1, Math.floor((x / w) * GENES.length)));
  }

  canMutate(gi) {
    return this.owner && this.pet && this.pet.unspent > 0 && GENES[gi]?.trainable;
  }

  mutate(gi) {
    if (!this.canMutate(gi)) return;
    this.mutating = { gi, t0: performance.now() };
    this.pulse = 1;
    this.send({ type: "allocate", stat: GENES[gi].stat });
  }

  setPet(pet, owner) {
    const prev = this.pet;
    this.pet = pet;
    this.owner = owner;
    const target = lookFromStats(pet.stats, pet.hue);
    if (!this.look || !prev || prev.id !== pet.id) this.look = { ...target };
    this.targetLook = target;
    if (prev && prev.id === pet.id && pet.level > prev.level) this.pulse = 1;
    this.renderCards();
  }

  renderCards() {
    const p = this.pet;
    if (!p) return;
    this.els.genes.innerHTML = GENES.map((g, gi) => {
      const pts = p.points?.[g.stat] || 0;
      const { seq, mutated } = sequence(p.seed || 1, gi, pts);
      const letters = seq.map((b, i) => `<span class="${mutated.has(i) ? "mut" : ""}">${b}</span>`).join("");
      const can = this.canMutate(gi);
      return `<div class="gene ${g.trainable ? "" : "locked"} ${can ? "can" : ""}" data-gene="${gi}" style="--gc:${g.color}">
        <div class="g-top"><i class="g-sym">${esc(g.sym)}</i><span class="g-stat">${esc(this.statLabel(g.stat))}</span><b class="g-val">${p.stats[g.stat]}</b></div>
        <div class="g-what">${esc(g.name)} — ${esc(g.what)}</div>
        <div class="g-seq">${letters}</div>
        <div class="g-foot">${g.trainable
          ? `${pts ? `${pts} мутац.` : "дикий тип"}${can ? ` · <span class="g-cta">мутировать</span>` : ""}`
          : "измерено при медосмотре"}</div>
      </div>`;
    }).join("");
  }

  statLabel(k) { return this.labels?.[k] || k; }

  draw() {
    this.drawHelix();
    this.drawPortrait();
  }

  drawHelix() {
    const cv = this.els.helix;
    const dpr = window.devicePixelRatio || 1;
    const { width: w, height: h } = cv.getBoundingClientRect();
    if (!w) return;
    if (cv.width !== Math.round(w * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
    const ctx = cv.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const now = performance.now();
    this.phase += 0.012;
    const p = this.pet;
    const cy = h / 2 - 6, A = h * 0.3;
    const rungs = GENES.length * 9;
    const mut = this.mutating && now - this.mutating.t0 < 1400 ? this.mutating : null;
    if (!mut) this.mutating = null;
    const items = [];
    for (let i = 0; i < rungs; i++) {
      const gi = Math.floor(i / 9);
      const x = ((i + 0.5) / rungs) * w;
      const ang = i * 0.55 + this.phase;
      items.push({ i, gi, x, y1: cy + A * Math.sin(ang), y2: cy - A * Math.sin(ang), z: Math.cos(ang) });
    }
    // gene region backgrounds
    GENES.forEach((g, gi) => {
      const x0 = (gi / GENES.length) * w, x1 = ((gi + 1) / GENES.length) * w;
      const hi = gi === this.hover || (mut && mut.gi === gi);
      ctx.fillStyle = hi ? `${g.color}22` : "transparent";
      ctx.fillRect(x0, 4, x1 - x0, h - 26);
      ctx.font = `italic 700 12px ${FONT}`; ctx.textAlign = "center"; ctx.textBaseline = "alphabetic";
      ctx.fillStyle = g.trainable ? g.color : `${g.color}aa`;
      ctx.fillText(g.sym, (x0 + x1) / 2, h - 6);
    });
    // back strand, rungs, front strand
    const strand = (key, front) => {
      ctx.lineWidth = 3; ctx.strokeStyle = front ? "#d8dee9" : "#4b5263";
      ctx.beginPath();
      let started = false;
      for (const it of items) {
        const y = it[key];
        const zf = key === "y1" ? it.z : -it.z;
        if ((zf >= 0) !== front) { started = false; continue; }
        if (!started) { ctx.moveTo(it.x, y); started = true; } else ctx.lineTo(it.x, y);
      }
      ctx.stroke();
    };
    strand("y1", false); strand("y2", false);
    for (const it of items) {
      const g = GENES[it.gi];
      const pts = p?.points?.[g.stat] || 0;
      const seqInfo = p ? sequence(p.seed || 1, it.gi, pts) : { seq: [], mutated: new Set() };
      const local = it.i % 9;
      const mutated = seqInfo.mutated.has(local * 2) || seqInfo.mutated.has(local * 2 + 1);
      let color = g.color;
      let base = seqInfo.seq[local * 2] || "A";
      if (mut && mut.gi === it.gi) { // scrambling letters + flicker during a mutation
        base = BASES[Math.floor(Math.random() * 4)];
        color = Math.random() < 0.5 ? "#ffffff" : g.color;
      }
      const depth = 0.35 + 0.65 * (Math.abs(it.z));
      ctx.globalAlpha = depth * (mutated ? 1 : 0.75);
      ctx.strokeStyle = color; ctx.lineWidth = mutated ? 4 : 2.5;
      ctx.beginPath(); ctx.moveTo(it.x, it.y1); ctx.lineTo(it.x, it.y2); ctx.stroke();
      if (mutated) {
        ctx.fillStyle = color; ctx.globalAlpha = 0.25 + 0.2 * Math.sin(now / 200 + it.i);
        ctx.beginPath(); ctx.arc(it.x, cy, 6, 0, Math.PI * 2); ctx.fill();
      }
      if (Math.abs(it.z) > 0.75) {
        ctx.globalAlpha = 0.9; ctx.fillStyle = "#0d0f13";
        ctx.font = `700 9px ${FONT}`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
        const top = it.y1 < it.y2 ? it.y1 : it.y2, bot = it.y1 < it.y2 ? it.y2 : it.y1;
        ctx.fillStyle = "#e8ecf2";
        ctx.fillText(base, it.x, top - 8);
        ctx.fillText(PAIR[base], it.x, bot + 8);
      }
    }
    ctx.globalAlpha = 1;
    strand("y1", true); strand("y2", true);
    if (mut) {
      const g = GENES[mut.gi];
      const x0 = (mut.gi / GENES.length) * w, x1 = ((mut.gi + 1) / GENES.length) * w;
      for (let k = 0; k < 3; k++) this.particles.push({ x: rand(x0, x1), y: cy + rand(-A, A), vy: rand(-60, -20), life: 0.8, color: g.color });
    }
    this.particles = this.particles.filter((q) => (q.life -= 1 / 60) > 0);
    for (const q of this.particles) {
      q.y += q.vy / 60;
      ctx.globalAlpha = q.life; ctx.fillStyle = q.color;
      ctx.beginPath(); ctx.arc(q.x, q.y, 2.2, 0, Math.PI * 2); ctx.fill();
    }
    ctx.globalAlpha = 1;
    if (this.owner && p?.unspent > 0) {
      ctx.font = `700 12px ${FONT}`; ctx.textAlign = "left"; ctx.textBaseline = "top";
      ctx.fillStyle = "#ffd166";
      ctx.fillText(`${p.unspent} очк. мутации`, 8, 6);
    }
  }

  drawPortrait() {
    const cv = this.els.portrait;
    const dpr = window.devicePixelRatio || 1;
    const { width: w, height: h } = cv.getBoundingClientRect();
    if (!w || !this.look) return;
    if (cv.width !== Math.round(w * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
    const ctx = cv.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    for (const k of ["body", "legs", "wings", "armor"]) this.look[k] += (this.targetLook[k] - this.look[k]) * 0.04;
    this.pulse *= 0.96;
    const now = performance.now();
    const g = ctx.createRadialGradient(w / 2, h / 2, 4, w / 2, h / 2, w / 2);
    g.addColorStop(0, `hsla(${this.look.hue}, 70%, 55%, ${0.18 + 0.3 * this.pulse})`); g.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = g; ctx.fillRect(0, 0, w, h);
    ctx.save();
    ctx.translate(w / 2 + 6, h / 2);
    ctx.rotate(-Math.PI / 2 + Math.sin(now / 1500) * 0.08);
    const s = (Math.min(w, h) / 4.2) * (1 + 0.08 * this.pulse);
    ctx.scale(s, s);
    drawFlyBody(ctx, { mode: "walk", gait: now / 900, alt: 0 }, this.look, { t: now, buzz: this.pulse > 0.3 });
    ctx.restore();
  }
}

function rand(a, b) { return a + Math.random() * (b - a); }
