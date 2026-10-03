// Arena tab: roster of pets, live battles, and the battle view.

const MODES = { attack: "наступает", lunge: "выпад!", flee: "отступает", groom: "чистится", flight: "прыжок-уклонение", walk: "идёт" };
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

export class BattleView {
  constructor(els, { send, onVisit, onWatch }) {
    this.els = els;
    this.send = send;
    this.hello = null;
    this.myPetId = null;
    els.roster.addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      if (b.dataset.challenge) send({ type: "challenge", pet_id: +b.dataset.challenge });
      if (b.dataset.visit) onVisit(+b.dataset.visit);
    });
    els.live.addEventListener("click", (e) => {
      const key = e.target.closest("[data-watch]")?.dataset.watch;
      if (key) onWatch(key);
    });
  }

  roster(pets, myPetId) {
    this.myPetId = myPetId;
    const mine = pets.find((p) => p.id === myPetId);
    this.els.roster.innerHTML = pets.length ? pets.map((p) => {
      const s = p.stats, isMine = p.id === myPetId;
      const canFight = mine && !isMine && !p.in_battle && !mine.in_battle;
      return `<div class="pet-card ${isMine ? "mine" : ""}">
        <div class="top"><span class="swatch" style="background:hsl(${p.hue} 70% 60%)"></span>
          <span class="nm">${esc(p.name)}</span><span class="ow">${esc(p.owner)}${isMine ? " (вы)" : ""}</span>
          <span class="rec">ур.${p.level} · ${p.wins}–${p.losses}</span></div>
        <div class="mini"><span>сила ${s.strength}</span><span>скор ${s.speed}</span><span>ловк ${s.agility}</span><span>проч ${s.durability}</span><span>смел ${s.courage}</span><span>вспыл ${s.temper}</span>
          ${p.online ? "<span>● в сети</span>" : ""}${p.in_battle ? "<span>в бою</span>" : ""}${p.learned_name ? "<span>знает имя</span>" : ""}</div>
        <div class="actions">
          ${canFight ? `<button class="btn primary" data-challenge="${p.id}">Вызвать</button>` : ""}
          ${!isMine ? `<button class="btn" data-visit="${p.id}">В гости</button>` : ""}
        </div></div>`;
    }).join("") : `<div class="hint">Пока нет питомцев.</div>`;
  }

  battles(list, watching) {
    const live = list.filter((b) => !b.finished);
    this.els.liveBadge.hidden = !live.length;
    this.els.liveBadge.textContent = live.length;
    this.els.live.innerHTML = list.map((b) => `<div class="live-card">${b.finished ? "" : "<i class='dot'></i>"}${esc(b.names[0])} vs ${esc(b.names[1])}
      ${b.key === watching ? "<span class='hint' style='margin:0 0 0 auto'>смотрите</span>" : `<button class="btn" data-watch="${b.key}">Смотреть</button>`}</div>`).join("");
  }

  clear() {
    this.els.empty.hidden = false;
    this.els.fighters.innerHTML = "";
    this.els.title.firstChild.textContent = "Арена ";
    this.els.timer.textContent = "";
  }

  frame(f) {
    const { els } = this;
    els.empty.hidden = true;
    els.title.firstChild.textContent = `${f.flies[0].name} vs ${f.flies[1].name} `;
    els.timer.textContent = f.finished
      ? (f.winner === null ? "ничья" : `победа: ${f.flies[f.winner].name}`)
      : `осталось ${Math.ceil(f.time_left)} с`;
    const emo = Object.fromEntries((this.hello?.emotions || []).map((e) => [e.key, e]));
    const row = (label, v, color, text) => `<div class="row"><span>${label}</span><span class="track"><span class="fill" style="display:block;width:${Math.min(100, v * 100)}%;background:${color}"></span></span><span class="v">${text}</span></div>`;
    els.fighters.innerHTML = f.flies.map((fl, i) => {
      const st = f.fighters[i], lv = st.emotions.levels, ro = st.readouts;
      return `<div class="fighter"><h3><span class="swatch" style="width:10px;height:10px;border-radius:50%;background:hsl(${fl.hue} 70% 60%)"></span>${esc(fl.name)} <span class="hint" style="margin:0">— ${MODES[fl.mode] || fl.mode}</span></h3>
        <div class="emo-mini">
          ${row("Страх", lv.fear, emo.fear?.color, `${Math.round(lv.fear * 100)}%`)}
          ${row("Раздражение", lv.irritation, emo.irritation?.color, `${Math.round(lv.irritation * 100)}%`)}
          ${row("Гигантское волокно", ro.giant_fiber / 150, "#7d8592", `${Math.round(ro.giant_fiber)}`)}
          ${row("Груминг-DN", ro.groom / 30, "#7d8592", `${Math.round(ro.groom)}`)}
        </div></div>`;
    }).join("");
    for (const ev of f.events) this.log(ev);
  }

  log(ev) {
    const li = document.createElement("li");
    li.innerHTML = `<time>${ev.t.toFixed(1)} с</time><span></span>`;
    li.lastChild.textContent = ev.text;
    this.els.log.prepend(li);
    while (this.els.log.children.length > 150) this.els.log.lastChild.remove();
  }
}
