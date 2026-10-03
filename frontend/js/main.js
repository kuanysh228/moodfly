import { Arena } from "./arena.js";
import { BattleView } from "./battle.js";
import { BrainView } from "./brain.js";
import { DnaPanel } from "./dna.js";
import { EmotionPanel } from "./emotions.js";
import { FightRenderer } from "./fight.js";
import { lookFromStats } from "./flyart.js";
import { PetPanel } from "./pet.js";

const $ = (id) => document.getElementById(id);
const MODES = {
  walk: "идёт", pause: "стоит", feed: "ест — хоботок вытянут", groom: "чистит голову", backup: "пятится",
  flight: "взлетает!", come: "бежит к вам!", flee: "убегает от вас",
};
const PRESETS = [
  ["DNp01", "гигантское волокно → взлёт"],
  ["CB0701", "MN9 → хоботок"],
  ["MDN", "moonwalker → назад"],
  ["LPLC2", "детектор тени"],
  ["PAM*", "дофамин «награда»"],
  ["PPL1*", "дофамин «наказание»"],
  ["KCg-m", "Кеньон-клетки"],
];
const TOKEN_KEY = "moodfly.token";
const store = {
  get() { try { return localStorage.getItem(TOKEN_KEY); } catch { return null; } },
  set(v) { try { localStorage.setItem(TOKEN_KEY, v); } catch { /* private mode */ } },
};

let socket = null;
let hello = null;
let me = { user: null, pet: null };
let pets = [];
let battles = [];
let view = "pet";
let watching = null;
let roomPetId = null; // pet whose home the pet tab shows (mine, or one I'm visiting)
let battleKey = null;
let focus = 0;
let tool = "sugar";
let background = true;

const send = (msg) => socket?.readyState === WebSocket.OPEN && socket.send(JSON.stringify(msg));
const roomCmd = (cmd) => send({ type: "room", cmd });
const isOwner = () => !!me.pet && roomPetId === me.pet.id;

const arena = new Arena($("arena"), ({ x, y, onFly }) => {
  if (onFly && tool !== "threat" && tool !== "remove") roomCmd({ type: "touch" });
  else if (tool === "threat") roomCmd({ type: "threat", x, y });
  else if (tool === "remove") roomCmd({ type: "remove", x, y });
  else roomCmd({ type: "place", kind: tool, x, y });
});
const fight = new FightRenderer($("battle-canvas"));
const brainPet = new BrainView($("brain-wrap"), $("brain-legend"));
const brainBattle = new BrainView($("battle-brain-wrap"), $("battle-brain-legend"));
const emotions = new EmotionPanel({
  bars: $("bars"), circumplex: $("circumplex"), timeline: $("timeline"), tip: $("tl-tip"),
  domDot: $("dom-dot"), domName: $("dom-name"), domSub: $("dom-sub"),
});
const petPanel = new PetPanel({
  chatForm: $("chat-form"), chatInput: $("chat-input"), reward: $("btn-reward"), punish: $("btn-punish"),
  hearing: $("hearing"), recogFill: $("recog-fill"), recogVal: $("recog-val"), words: $("words"), passport: $("passport"), extra: $("pass-extra"),
}, send);
const dna = new DnaPanel({ helix: $("dna-helix"), portrait: $("dna-portrait"), genes: $("genes") }, send);
const battleView = new BattleView({
  roster: $("roster"), live: $("battles-live"), liveBadge: $("live-badge"), fighters: $("fighters"),
  log: $("battle-log"), empty: $("battle-empty"), title: $("battle-title"), timer: $("battle-timer"),
}, {
  send,
  onVisit: (id) => { roomPetId = id; setView("pet"); },
  onWatch: (key) => { battleKey = key; resetBattleUI(); updateWatch(); },
});

function toast(text, { err = false, action = null } = {}) {
  const el = document.createElement("div");
  el.className = `toast${err ? " err" : ""}`;
  el.textContent = text;
  if (action) {
    const b = document.createElement("button");
    b.className = "btn"; b.textContent = action.label; b.onclick = () => { action.run(); el.remove(); };
    el.append(b);
  }
  $("toasts").append(el);
  setTimeout(() => el.remove(), 7000);
}

function setView(v) {
  view = v;
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.view === v));
  $("view-pet").hidden = v !== "pet";
  $("view-arena").hidden = v !== "arena";
  updateWatch();
}
document.querySelectorAll(".tab").forEach((t) => (t.onclick = () => {
  if (t.dataset.view === "pet" && me.pet) roomPetId = me.pet.id;
  setView(t.dataset.view);
}));

function updateWatch() {
  const want = view === "pet" ? (roomPetId ? `pet:${roomPetId}` : null) : battleKey;
  if (want !== watching) {
    watching = want;
    send({ type: "watch", channel: want });
    $("log").innerHTML = "";
  }
  const owner = isOwner();
  petPanel.setOwner(owner);
  document.querySelectorAll("#tools .tool, #btn-puff, #btn-reset, #btn-bg, #opto-on, #opto-silence, #opto-clear").forEach((b) => (b.disabled = !owner));
  const pet = pets.find((p) => p.id === roomPetId) || me.pet;
  $("pet-title").textContent = pet ? (owner ? pet.name : `В гостях у ${pet.name}`) : "Питомец";
  $("pet-sub").textContent = pet ? (owner ? "ваша муха" : `хозяин: ${pet.owner} · можно позвать по имени`) : "";
  renderPassport();
  battleView.battles(battles, battleKey);
}

function renderPassport() {
  const pet = pets.find((p) => p.id === roomPetId) || me.pet;
  if (pet) {
    petPanel.passport(pet, isOwner());
    dna.setPet(pet, isOwner());
    arena.look = lookFromStats(pet.stats, pet.hue);
    $("pass-sub").textContent = `${pet.name} · ${pet.owner}`;
  }
}

function resetBattleUI() {
  $("battle-log").innerHTML = "";
  battleView.clear();
  fight.reset();
}

document.querySelectorAll(".tool").forEach((b) => b.addEventListener("click", () => {
  document.querySelectorAll(".tool").forEach((x) => x.classList.toggle("active", x === b));
  tool = b.dataset.tool;
}));
$("btn-puff").onclick = () => roomCmd({ type: "puff" });
$("btn-bg").onclick = () => roomCmd({ type: "background", on: !background });
$("btn-reset").onclick = () => roomCmd({ type: "reset" });
let rotate = true;
$("btn-rotate").onclick = () => { rotate = !rotate; brainPet.setRotate(rotate); $("btn-rotate").classList.toggle("active", rotate); };
document.querySelectorAll("[data-focus]").forEach((b) => (b.onclick = () => {
  focus = +b.dataset.focus;
  document.querySelectorAll("[data-focus]").forEach((x) => x.classList.toggle("active", x === b));
}));

const optoInput = $("opto-type"), suggest = $("opto-suggest"), hzInput = $("opto-hz");
hzInput.oninput = () => ($("opto-hz-val").textContent = `${hzInput.value} Гц`);
$("opto-on").onclick = () => optoInput.value && roomCmd({ type: "opto", mode: "activate", cell_type: optoInput.value.trim(), hz: +hzInput.value });
$("opto-silence").onclick = () => optoInput.value && roomCmd({ type: "opto", mode: "silence", cell_type: optoInput.value.trim() });
$("opto-clear").onclick = () => roomCmd({ type: "opto", mode: "clear" });
$("opto-presets").innerHTML = PRESETS.map(([ct, what]) => `<span class="chip" data-ct="${ct}" title="${what}">${ct} · ${what}</span>`).join("");
$("opto-presets").onclick = (e) => {
  const ct = e.target.closest(".chip")?.dataset.ct;
  if (ct) { optoInput.value = ct; suggest.style.display = "none"; }
};
$("opto-active").onclick = (e) => {
  const ct = e.target.closest(".chip")?.dataset.ct;
  if (ct && isOwner()) roomCmd({ type: "opto", mode: "off", cell_type: ct });
};
optoInput.addEventListener("input", () => {
  const q = optoInput.value.trim().toLowerCase();
  if (!q || !hello) { suggest.style.display = "none"; return; }
  const hits = hello.cell_types.filter(([t]) => t.toLowerCase().includes(q))
    .sort((a, b) => (b[0].toLowerCase().startsWith(q) - a[0].toLowerCase().startsWith(q)) || a[0].localeCompare(b[0]))
    .slice(0, 40);
  suggest.innerHTML = hits.map(([t, n]) => `<div data-ct="${t}"><span>${t}</span><span style="color:#7d8592">${n}</span></div>`).join("");
  suggest.style.display = hits.length ? "block" : "none";
  suggest.style.top = `${optoInput.offsetTop + optoInput.offsetHeight + 4}px`;
  suggest.style.left = `${optoInput.offsetLeft}px`;
});
suggest.onclick = (e) => {
  const ct = e.target.closest("[data-ct]")?.dataset.ct;
  if (ct) { optoInput.value = ct; suggest.style.display = "none"; }
};
document.addEventListener("click", (e) => { if (e.target !== optoInput) suggest.style.display = "none"; });

$("nick-form").addEventListener("submit", (e) => { e.preventDefault(); send({ type: "register", nick: $("nick").value.trim() }); });
$("pet-form").addEventListener("submit", (e) => {
  e.preventDefault();
  send({ type: "create_pet", name: $("pet-name").value.trim() });
  $("pet-form").querySelector("button").disabled = true;
  $("auth-error").style.color = "var(--text-2)";
  $("auth-error").textContent = "Рождение и медосмотр мозга… (~2 с)";
});

function onMe(msg) {
  me = msg;
  if (msg.token) store.set(msg.token);
  const authEl = $("auth");
  if (!msg.user) {
    authEl.hidden = false; $("auth-nick").hidden = false; $("auth-pet").hidden = true;
  } else if (!msg.pet) {
    authEl.hidden = false; $("auth-nick").hidden = true; $("auth-pet").hidden = false;
  } else {
    authEl.hidden = true;
    if (!roomPetId) roomPetId = msg.pet.id;
  }
  $("me-chip").textContent = msg.user ? `${msg.user.nick}${msg.pet ? ` · ${msg.pet.name}` : ""}` : "";
  battleView.roster(pets, me.pet?.id);
  updateWatch();
}

function onHello(msg) {
  hello = msg;
  arena.configure(msg);
  fight.configure(msg);
  dna.labels = msg.stat_labels;
  emotions.configure(msg);
  petPanel.hello = msg;
  battleView.hello = msg;
  $("readouts").innerHTML = msg.readouts.map((r) =>
    `<tr><td>${r.label}</td><td class="meter"><div class="meter-track"><div class="meter-fill" id="ro-${r.key}"></div></div></td><td class="hz" id="hz-${r.key}">0</td></tr>`).join("");
  if (!brainPet.points) {
    fetch("api/brain.bin").then((r) => r.arrayBuffer()).then((buf) => { brainPet.load(buf, msg); brainBattle.load(buf, msg); });
  }
  const token = store.get();
  if (token) send({ type: "auth", token });
  else onMe({ user: null, pet: null });
}

function onPetFrame(f) {
  background = f.background;
  $("btn-bg").classList.toggle("active", background);
  $("st-t").textContent = f.t.toFixed(1);
  $("st-sps").textContent = f.spikes_per_s.toLocaleString("ru-RU");
  $("st-active").textContent = f.active.toLocaleString("ru-RU");
  const dom = emotions.dominant(f.emotions);
  arena.update(f.world, dom);
  emotions.update(f.t, f.emotions);
  petPanel.learning(f.learning);
  $("behavior").innerHTML = `поведение: <b>${MODES[f.world.fly.mode] || f.world.fly.mode}</b>`;
  for (const r of hello.readouts) {
    const hz = f.readouts[r.key] ?? 0;
    $(`hz-${r.key}`).textContent = hz.toFixed(hz < 10 ? 1 : 0);
    $(`ro-${r.key}`).style.width = `${Math.min(100, (Math.log1p(hz) / Math.log1p(200)) * 100)}%`;
  }
  $("opto-active").innerHTML = f.opto.map((o) =>
    `<span class="chip ${o.mode === "activate" ? "on" : "off"}" data-ct="${o.cell_type}" title="снять">${o.mode === "activate" ? "+" : "−"} ${o.cell_type} (${o.n}) ${o.mode === "activate" ? o.hz + " Гц" : ""} ✕</span>`).join("");
  const log = $("log");
  for (const ev of f.events) {
    const li = document.createElement("li");
    li.innerHTML = `<time>${ev.t.toFixed(1)} с</time><span></span>`;
    li.lastChild.textContent = ev.text;
    log.prepend(li);
  }
  while (log.children.length > 120) log.lastChild.remove();
}

function onBattleFrame(f) {
  fight.setFrame(f);
  battleView.frame(f);
  $("focus-0").textContent = f.flies[0].name;
  $("focus-1").textContent = f.flies[1].name;
}

function onMessage(msg) {
  switch (msg.type) {
    case "hello": onHello(msg); break;
    case "me": onMe(msg); break;
    case "pets":
      pets = msg.pets;
      if (me.pet) me.pet = pets.find((p) => p.id === me.pet.id) || me.pet;
      battleView.roster(pets, me.pet?.id);
      renderPassport();
      break;
    case "battles": battles = msg.battles; battleView.battles(battles, battleKey); break;
    case "battle_started":
      battleKey = msg.channel; resetBattleUI(); setView("arena"); break;
    case "notice":
      toast(msg.text, msg.battle && msg.battle !== battleKey
        ? { action: { label: "Смотреть", run: () => { battleKey = msg.battle; resetBattleUI(); setView("arena"); } } }
        : {});
      break;
    case "error":
      if (!$("auth").hidden) {
        $("auth-error").style.color = "var(--bad)";
        $("auth-error").textContent = msg.text;
        $("pet-form").querySelector("button").disabled = false;
      } else toast(msg.text, { err: true });
      break;
    case "frame":
      if (msg.channel !== watching) break;
      $("st-speed").textContent = `×${msg.speed.toFixed(1)}`;
      if (msg.kind === "pet") onPetFrame(msg);
      else onBattleFrame(msg);
      break;
  }
}

function connect() {
  const url = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}${location.pathname.replace(/[^/]*$/, "")}ws`;
  socket = new WebSocket(url);
  socket.binaryType = "arraybuffer";
  socket.onopen = () => { $("conn").textContent = "на связи"; $("conn-dot").classList.add("on"); $("overlay").classList.add("hidden"); watching = null; };
  socket.onclose = () => {
    $("conn").textContent = "нет связи"; $("conn-dot").classList.remove("on");
    $("overlay").classList.remove("hidden"); $("overlay").textContent = "Связь с сервером потеряна, переподключаюсь…";
    setTimeout(connect, 1500);
  };
  socket.onmessage = (ev) => {
    if (typeof ev.data !== "string") {
      const tag = new Uint32Array(ev.data, 0, 1)[0];
      const spikes = new Uint32Array(ev.data, 4);
      if (watching?.startsWith("pet:")) brainPet.spikes(spikes);
      else if (tag === focus) brainBattle.spikes(spikes);
      return;
    }
    onMessage(JSON.parse(ev.data));
  };
}

function loop() {
  if (view === "pet") { arena.draw(); brainPet.render(); dna.draw(); }
  else { fight.draw(); brainBattle.render(); }
  requestAnimationFrame(loop);
}

window.moodfly = { send, get state() { return { me, pets, battles, watching, view }; } }; // devtools helper

connect();
loop();
