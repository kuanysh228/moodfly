// Training panel (chat, reward, recognition) and the pet passport (stats, level).

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

export class PetPanel {
  constructor(els, send) {
    this.els = els;
    this.send = send;
    this.hello = null;
    els.chatForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const text = els.chatInput.value.trim();
      if (text) send({ type: "room", cmd: { type: "say", text } });
      els.chatInput.value = "";
    });
    els.reward.onclick = () => send({ type: "room", cmd: { type: "reward" } });
    els.punish.onclick = () => send({ type: "room", cmd: { type: "punish" } });
  }

  setOwner(isOwner) {
    for (const b of [this.els.reward, this.els.punish]) b.disabled = !isOwner;
  }

  learning(l) {
    if (!l) return;
    const { els } = this;
    els.hearing.textContent = l.hearing ? `«${l.hearing}»` : "—";
    const r = l.recognition;
    els.recogFill.style.left = r >= 0 ? "50%" : `${50 + r * 50}%`;
    els.recogFill.style.width = `${Math.abs(r) * 50}%`;
    els.recogFill.style.background = r >= 0 ? "var(--joy)" : "#c98500";
    els.recogVal.textContent = r.toFixed(2);
    els.reward.classList.toggle("flash", l.reward);
    els.punish.classList.toggle("flash", l.punish);
    els.words.innerHTML = l.words.length
      ? l.words.map((w) => {
          const v = Math.max(-1, Math.min(1, w.value));
          const left = v >= 0 ? 50 : 50 + v * 50;
          return `<div class="word" title="узнавание при последнем звучании"><span class="w ${w.word === l.name ? "name" : ""}">${esc(w.word)}</span>
            <span class="recog-track"><span class="recog-mid"></span><span class="recog-fill" style="left:${left}%;width:${Math.abs(v) * 50}%;background:${v >= 0 ? "var(--joy)" : "#c98500"}"></span></span>
            <span class="v">${v.toFixed(2)}</span></div>`;
        }).join("")
      : `<div class="hint">слов пока не было</div>`;
  }

  passport(pet, isOwner) {
    if (!pet || !this.hello) return;
    const c = pet.combat;
    this.els.passport.innerHTML = `
      <div class="pass-head">
        <span class="lvl">ур. ${pet.level}</span>
        <div class="xp"><span>опыт ${pet.xp} / ${pet.xp_next}${pet.unspent && isOwner ? ` · <b style="color:#ffd166">${pet.unspent} очк. мутации</b>` : ""}</span>
          <div class="xp-track"><div class="xp-fill" style="width:${(100 * pet.xp) / pet.xp_next}%"></div></div></div>
        <span class="mono">${pet.wins}–${pet.losses}–${pet.draws}</span>
      </div>`;
    this.els.extra.innerHTML = `
      <div class="hint">${Math.round(c.hp)} HP · урон ${c.damage.toFixed(0)} · броня ${Math.round(c.armor * 100)}% · уклонение ${Math.round(c.dodge * 100)}% · ${c.walk.toFixed(1)} мм/с</div>
      <details class="how"><summary>Медосмотр мозга</summary><ul class="checkup">${pet.checkup.map((s) => `<li>${esc(s)}</li>`).join("")}</ul></details>
      ${pet.learned_name ? `<div class="hint">знает своё имя</div>` : ""}`;
  }
}
