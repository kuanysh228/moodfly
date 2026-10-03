// Whole-brain point cloud: one point per neuron at its FlyWire position, flashing on spikes.
import * as THREE from "three";
import { OrbitControls } from "three/addons/OrbitControls.js";

const CLASS_COLORS = {
  optic: "#34507a",
  central: "#6f5a9a",
  sensory: "#3f8a74",
  visual_projection: "#4a7fb0",
  visual_centrifugal: "#4a6a90",
  descending: "#b07a40",
  ascending: "#7a8a40",
  sensory_ascending: "#5a8a60",
  motor: "#b05050",
  endocrine: "#a06a90",
};
const CLASS_LABELS = {
  optic: "оптические доли", central: "центральный мозг", sensory: "сенсорные", visual_projection: "зрительные проекционные",
  descending: "нисходящие (к телу)", motor: "моторные",
};
const SPIKE_COLOR = "#8fb8ff";
const DECAY_MS = 140;

const vertexShader = `
  attribute vec3 baseColor;
  attribute float activity;
  attribute float flashKind;
  attribute float isOptic;
  uniform float uSize;
  uniform float uHideOptic;
  uniform vec3 uFlash[6];
  varying vec3 vColor;
  varying float vAlpha;
  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    float a = activity;
    float hidden = uHideOptic * isOptic;
    gl_PointSize = hidden > 0.5 ? 0.0 : uSize * (0.7 + 1.6 * a) / -mv.z;
    vColor = mix(baseColor, uFlash[int(flashKind + 0.5)], clamp(a * 1.3, 0.0, 1.0));
    vAlpha = 0.06 + 0.6 * a;
    gl_Position = projectionMatrix * mv;
  }`;

const fragmentShader = `
  varying vec3 vColor;
  varying float vAlpha;
  void main() {
    float d = length(gl_PointCoord - 0.5);
    if (d > 0.5) discard;
    gl_FragColor = vec4(vColor, vAlpha * smoothstep(0.5, 0.1, d));
  }`;

export class BrainView {
  constructor(container, legendEl) {
    this.container = container;
    this.legendEl = legendEl;
    this.renderer = new THREE.WebGLRenderer({ antialias: false, alpha: false });
    this.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    this.renderer.setClearColor(0x07090c);
    container.prepend(this.renderer.domElement);
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(40, 1, 0.1, 100);
    this.camera.position.set(0, 0.4, 13.5);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.autoRotate = true;
    this.controls.autoRotateSpeed = 0.6;
    this.controls.minDistance = 3;
    this.controls.maxDistance = 30;
    this.activity = null;
    this.last = performance.now();
    new ResizeObserver(() => this.resize()).observe(container);
    this.resize();
  }

  resize() {
    const { clientWidth: w, clientHeight: h } = this.container;
    if (!w || !h) return;
    this.renderer.setSize(w, h);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    if (this.material) this.material.uniforms.uSize.value = 26 * this.renderer.getPixelRatio() * (h / 340);
  }

  load(buffer, hello) {
    const n = new Uint32Array(buffer, 0, 4)[0];
    const pos = new Float32Array(buffer, 16, n * 3);
    const cls = new Uint8Array(buffer, 16 + n * 12, n);
    const emo = new Uint8Array(buffer, 16 + n * 13, n);
    const names = hello.super_classes;

    const positions = new Float32Array(n * 3);
    const base = new Float32Array(n * 3);
    const optic = new Float32Array(n);
    const flash = new Float32Array(n);
    const palette = names.map((s) => new THREE.Color(CLASS_COLORS[s] || "#555a66"));
    const fallback = new THREE.Color("#555a66");
    const opticCode = names.indexOf("optic");
    for (let i = 0; i < n; i++) {
      // FlyWire: x lateral, y ventral, z posterior (µm) -> frontal view
      positions[i * 3] = pos[i * 3] * 0.01;
      positions[i * 3 + 1] = -pos[i * 3 + 1] * 0.01;
      positions[i * 3 + 2] = -pos[i * 3 + 2] * 0.01;
      const col = palette[cls[i]] || fallback;
      base[i * 3] = col.r; base[i * 3 + 1] = col.g; base[i * 3 + 2] = col.b;
      optic[i] = cls[i] === opticCode ? 1 : 0;
      flash[i] = emo[i];
    }
    this.n = n;
    this.activity = new Float32Array(n);
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geo.setAttribute("baseColor", new THREE.BufferAttribute(base, 3));
    geo.setAttribute("isOptic", new THREE.BufferAttribute(optic, 1));
    geo.setAttribute("flashKind", new THREE.BufferAttribute(flash, 1));
    this.actAttr = new THREE.BufferAttribute(this.activity, 1);
    this.actAttr.setUsage(THREE.DynamicDrawUsage);
    geo.setAttribute("activity", this.actAttr);

    const flashColors = [new THREE.Color(SPIKE_COLOR), ...hello.emotions.map((e) => new THREE.Color(e.color))].slice(0, 6);
    while (flashColors.length < 6) flashColors.push(new THREE.Color(SPIKE_COLOR));
    this.material = new THREE.ShaderMaterial({
      vertexShader, fragmentShader,
      uniforms: { uSize: { value: 26 }, uHideOptic: { value: 0 }, uFlash: { value: flashColors } },
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    });
    this.points = new THREE.Points(geo, this.material);
    this.scene.add(this.points);
    this.resize();

    const present = new Set(cls);
    const shown = names.filter((s, i) => CLASS_LABELS[s] && present.has(i));
    this.legendEl.innerHTML =
      shown.map((s) => `<span><i style="background:${CLASS_COLORS[s]}"></i>${CLASS_LABELS[s]}</span>`).join("") +
      hello.emotions.filter((e) => e.neurons > 0).map((e) => `<span><i style="background:${e.color}"></i>${e.label}</span>`).join("");
  }

  spikes(indices) {
    if (!this.activity) return;
    const a = this.activity;
    for (let i = 0; i < indices.length; i++) a[indices[i]] = 1;
  }

  setHideOptic(hide) { if (this.material) this.material.uniforms.uHideOptic.value = hide ? 1 : 0; }
  setRotate(on) { this.controls.autoRotate = on; }

  render() {
    const now = performance.now();
    const dt = now - this.last;
    this.last = now;
    if (this.activity) {
      const f = Math.exp(-dt / DECAY_MS);
      const a = this.activity;
      for (let i = 0; i < a.length; i++) if (a[i] > 0.003) a[i] *= f; else a[i] = 0;
      this.actAttr.needsUpdate = true;
    }
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }
}
