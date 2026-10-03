// Emotion bars, valence/arousal map and a 60 s timeline with hover read-out.

const CALM = { key: "calm", label: "Спокойствие", color: "#7d8592" };
const WINDOW_S = 60;

function setupCanvas(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const { width, height } = canvas.getBoundingClientRect();
  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, w: width, h: height };
}

export class EmotionPanel {
  constructor(els) {
    this.els = els;
    this.history = []; // {t, levels}
    this.trail = [];
    this.hoverX = null;
    els.timeline.addEventListener("pointermove", (e) => { this.hoverX = e.offsetX; this.drawTimeline(); });
    els.timeline.addEventListener("pointerleave", () => { this.hoverX = null; els.tip.style.display = "none"; this.drawTimeline(); });
    new ResizeObserver(() => { this.drawTimeline(); this.drawCircumplex(); }).observe(els.timeline);
  }

  configure(hello) {
    this.emotions = hello.emotions;
    this.byKey = Object.fromEntries([...hello.emotions, CALM].map((e) => [e.key, e]));
    this.els.bars.innerHTML = [...hello.emotions, CALM]
      .map((e) => `<div class="bar" title="${e.neurons ? e.neurons + " нейронов-сигнатур" : "1 − возбуждение"}">
          <span class="lbl">${e.label}</span>
          <span class="track"><span class="fill" id="fill-${e.key}" style="background:${e.color}"></span></span>
          <span class="val" id="val-${e.key}">0%</span></div>`)
      .join("");
  }

  dominant(state) { return this.byKey?.[state.dominant] || CALM; }

  update(t, state) {
    if (!this.emotions) return;
    const lv = state.levels;
    for (const key of Object.keys(this.byKey)) {
      const v = lv[key] ?? 0;
      document.getElementById(`fill-${key}`).style.width = `${(v * 100).toFixed(1)}%`;
      document.getElementById(`val-${key}`).textContent = `${Math.round(v * 100)}%`;
    }
    const d = this.dominant(state);
    this.els.domDot.style.background = d.color;
    this.els.domName.textContent = d.label;
    this.els.domSub.textContent = `валентность ${state.valence >= 0 ? "+" : ""}${state.valence.toFixed(2)} · возбуждение ${state.arousal.toFixed(2)}`;

    const last = this.history[this.history.length - 1];
    if (last && t < last.t) this.history = []; // simulation was reset
    if (!last || t - last.t >= 0.1) {
      this.history.push({ t, levels: { ...lv } });
      while (this.history.length && t - this.history[0].t > WINDOW_S) this.history.shift();
    }
    this.trail.push({ v: state.valence, a: state.arousal, color: d.color });
    if (this.trail.length > 90) this.trail.shift();
    this.drawCircumplex();
    if (this.hoverX === null) this.drawTimeline();
  }

  drawCircumplex() {
    const { ctx, w, h } = setupCanvas(this.els.circumplex);
    const pad = 16;
    const x = (v) => pad + ((v + 1) / 2) * (w - 2 * pad);
    const y = (a) => h - pad - a * (h - 2 * pad);
    ctx.fillStyle = "#1d222b";
    ctx.beginPath(); ctx.roundRect(0, 0, w, h, 8); ctx.fill();
    ctx.strokeStyle = "#2a303b"; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(x(0), pad); ctx.lineTo(x(0), h - pad); ctx.moveTo(pad, y(0.5)); ctx.lineTo(w - pad, y(0.5)); ctx.stroke();
    ctx.fillStyle = "#7d8592"; ctx.font = "10px system-ui"; ctx.textBaseline = "middle";
    ctx.textAlign = "left"; ctx.fillText("тревога", pad + 2, pad + 4); ctx.fillText("скука", pad + 2, h - pad - 4);
    ctx.textAlign = "right"; ctx.fillText("восторг", w - pad - 2, pad + 4); ctx.fillText("покой", w - pad - 2, h - pad - 4);
    ctx.textAlign = "center";
    ctx.fillText("− валентность +", w / 2, h - 6);
    ctx.save(); ctx.translate(7, h / 2); ctx.rotate(-Math.PI / 2); ctx.fillText("возбуждение", 0, 0); ctx.restore();
    this.trail.forEach((p, i) => {
      ctx.globalAlpha = (i / this.trail.length) * 0.5;
      ctx.fillStyle = p.color;
      ctx.beginPath(); ctx.arc(x(p.v), y(p.a), 2, 0, Math.PI * 2); ctx.fill();
    });
    ctx.globalAlpha = 1;
    const p = this.trail[this.trail.length - 1];
    if (p) {
      ctx.fillStyle = p.color; ctx.strokeStyle = "#1d222b"; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(x(p.v), y(p.a), 6, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    }
  }

  drawTimeline() {
    if (!this.emotions) return;
    const { ctx, w, h } = setupCanvas(this.els.timeline);
    const padL = 30, padR = 28, padT = 8, padB = 18;
    const hist = this.history;
    const tEnd = hist.length ? hist[hist.length - 1].t : 0;
    const tStart = tEnd - WINDOW_S;
    const x = (t) => padL + ((t - tStart) / WINDOW_S) * (w - padL - padR);
    const y = (v) => padT + (1 - v) * (h - padT - padB);

    ctx.font = "10px system-ui"; ctx.fillStyle = "#7d8592"; ctx.strokeStyle = "#232832"; ctx.lineWidth = 1;
    ctx.textAlign = "right"; ctx.textBaseline = "middle";
    for (const v of [0, 0.5, 1]) {
      ctx.beginPath(); ctx.moveTo(padL, y(v)); ctx.lineTo(w - padR, y(v)); ctx.stroke();
      ctx.fillText(`${v * 100}%`, padL - 4, y(v));
    }
    ctx.textAlign = "center"; ctx.textBaseline = "alphabetic";
    for (let s = 0; s <= WINDOW_S; s += 15) ctx.fillText(s === 0 ? "сейчас" : `−${s} с`, x(tEnd - s), h - 4);
    if (hist.length < 2) return;

    ctx.lineWidth = 2; ctx.lineJoin = "round";
    for (const e of this.emotions) {
      ctx.strokeStyle = e.color;
      ctx.beginPath();
      hist.forEach((p, i) => { const px = x(p.t), py = y(p.levels[e.key] ?? 0); i ? ctx.lineTo(px, py) : ctx.moveTo(px, py); });
      ctx.stroke();
    }

    if (this.hoverX !== null && this.hoverX >= padL && this.hoverX <= w - padR) {
      const t = tStart + ((this.hoverX - padL) / (w - padL - padR)) * WINDOW_S;
      let best = hist[0];
      for (const p of hist) if (Math.abs(p.t - t) < Math.abs(best.t - t)) best = p;
      const px = x(best.t);
      ctx.strokeStyle = "#7d8592"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(px, padT); ctx.lineTo(px, h - padB); ctx.stroke();
      for (const e of this.emotions) {
        ctx.fillStyle = e.color; ctx.strokeStyle = "#161a21"; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(px, y(best.levels[e.key] ?? 0), 4, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      }
      const rows = [...this.emotions].sort((a, b) => (best.levels[b.key] ?? 0) - (best.levels[a.key] ?? 0))
        .map((e) => `<div class="row"><span class="sw" style="background:${e.color}"></span>${e.label}<span style="margin-left:auto;padding-left:10px">${Math.round((best.levels[e.key] ?? 0) * 100)}%</span></div>`);
      const tip = this.els.tip;
      tip.innerHTML = `<div style="color:#7d8592;margin-bottom:3px">${(best.t - tEnd).toFixed(1)} с</div>${rows.join("")}`;
      tip.style.display = "block";
      const left = px + 12 + tip.offsetWidth > w ? px - tip.offsetWidth - 12 : px + 12;
      tip.style.left = `${left}px`; tip.style.top = "4px";
    }
  }
}
