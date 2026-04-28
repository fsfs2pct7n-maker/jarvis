/**
 * JARVIS Particle Orb — Three.js r128
 *
 * States (uState uniform):
 *   0 = STANDBY   — slow deep breathing, dim cyan
 *   1 = LISTENING — rapid outward pulse + ring expansion, bright white-cyan
 *   2 = THINKING  — sweeping vortex rotation, blue tones
 *   3 = SPEAKING  — radial wave bursts, teal-green glow
 *   4 = FOLLOWUP  — gentle open pulse, warm amber-gold (waiting for follow-up)
 */
(function () {
  const canvas = document.getElementById('orb-canvas');

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setClearColor(0x000008, 1);

  const scene  = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(55, 1, 0.1, 100);
  camera.position.z = 3.2;

  // ── Particle geometry ──────────────────────────────────
  const COUNT     = 3000;
  const positions = new Float32Array(COUNT * 3);
  const aPhase    = new Float32Array(COUNT);
  const aSpeed    = new Float32Array(COUNT);
  const aSize     = new Float32Array(COUNT);
  const aLayer    = new Float32Array(COUNT); // 0.6–1.0: inner vs outer shell

  const PHI = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < COUNT; i++) {
    const y     = 1 - (i / (COUNT - 1)) * 2;
    const r     = Math.sqrt(Math.max(0, 1 - y * y));
    const theta = PHI * i;
    const layer = i < COUNT * 0.3 ? 0.6 + Math.random() * 0.4 : 1.0;
    positions[i * 3]     = r * Math.cos(theta) * layer;
    positions[i * 3 + 1] = y * layer;
    positions[i * 3 + 2] = r * Math.sin(theta) * layer;
    aPhase[i] = Math.random() * Math.PI * 2;
    aSpeed[i] = 0.4 + Math.random() * 0.8;
    aSize[i]  = 0.3 + Math.random() * 0.7;
    aLayer[i] = layer;
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geo.setAttribute('aPhase',   new THREE.BufferAttribute(aPhase,   1));
  geo.setAttribute('aSpeed',   new THREE.BufferAttribute(aSpeed,   1));
  geo.setAttribute('aSize',    new THREE.BufferAttribute(aSize,    1));
  geo.setAttribute('aLayer',   new THREE.BufferAttribute(aLayer,   1));

  // ── Vertex shader ──────────────────────────────────────
  const vertexShader = `
    attribute float aPhase;
    attribute float aSpeed;
    attribute float aSize;
    attribute float aLayer;

    uniform float uTime;
    uniform float uState;    // continuous float — mid-transition blends states
    uniform float uIntensity; // 0..1 extra energy boost per state

    // Helper: smooth step between two float values
    float when_eq(float x, float v) { return 1.0 - abs(sign(x - v)); }

    void main() {
      vec3 pos = position;
      float t  = uTime * aSpeed;

      // ── STANDBY (0): slow deep breathing ─────────────────
      // Amplitude: ±8%, frequency: 0.6 Hz. Very calm.
      float standbyW  = max(0.0, 1.0 - abs(uState - 0.0));
      float breathe   = sin(uTime * 0.6 + aPhase) * 0.08;
      pos += position * breathe * standbyW;

      // ── LISTENING (1): rapid outward pulse + per-particle jitter ──
      // Expands 30%, then fast ring-like vibration (7 Hz). Very energetic.
      float listenW   = max(0.0, 1.0 - abs(uState - 1.0));
      float expand    = 0.30;
      float pulse     = sin(uTime * 7.0 + aPhase * 1.4) * 0.07 * aLayer;
      float ringWave  = sin(uTime * 12.0 - length(position) * 8.0 + aPhase) * 0.04;
      pos += position * (expand + pulse + ringWave) * listenW;

      // ── THINKING (2): vortex rotation + pull-in ──────────
      // Rotates faster (2 Hz), particles pulled toward equator, slight z-squeeze.
      float thinkW    = max(0.0, 1.0 - abs(uState - 2.0));
      if (thinkW > 0.0) {
        float angle = uTime * 2.0 + aPhase * 0.5;
        float cA = cos(angle), sA = sin(angle);
        vec3 vortex = vec3(
          pos.x * cA - pos.z * sA,
          pos.y + sin(uTime * 2.2 + aPhase) * 0.07,
          pos.x * sA + pos.z * cA
        );
        pos = mix(pos, vortex * 0.84, thinkW);
      }

      // ── SPEAKING (3): outward radial wave bursts ─────────
      // Large amplitude waves (±26%) radiating outward at 6.5 Hz.
      float speakW    = max(0.0, 1.0 - abs(uState - 3.0));
      float dist      = length(position);
      float wave1     = sin(uTime * 6.5  - dist * 7.0 + aPhase) * 0.26;
      float wave2     = sin(uTime * 3.2  + aPhase * 0.7) * 0.06;
      float waveBurst = sin(uTime * 14.0 - dist * 12.0) * 0.04;
      pos += position * (wave1 + wave2 + waveBurst + 0.14) * speakW;

      // ── FOLLOWUP (4): gentle open pulse, slightly expanded ─
      // Breathes slower than standby but stays 15% bigger — inviting.
      float followW   = max(0.0, 1.0 - abs(uState - 4.0));
      float followPulse = sin(uTime * 1.1 + aPhase) * 0.10;
      pos += position * (0.15 + followPulse) * followW;

      vec4 mvPos = modelViewMatrix * vec4(pos, 1.0);
      gl_Position = projectionMatrix * mvPos;

      // Point size: base + animated per-particle breathing
      float baseSize = 190.0 * aSize * (1.0 / -mvPos.z);
      float pulseSz  = 1.0 + sin(uTime * 1.5 + aPhase) * 0.18;
      // Listening & speaking: bigger particles
      float stateBoost = 1.0 + listenW * 0.3 + speakW * 0.4;
      gl_PointSize = max(1.0, baseSize * pulseSz * stateBoost);
    }
  `;

  // ── Fragment shader ────────────────────────────────────
  const fragmentShader = `
    uniform vec3  uColorA;
    uniform vec3  uColorB;
    uniform float uAlpha;

    void main() {
      vec2  uv = gl_PointCoord - 0.5;
      float d  = length(uv);
      if (d > 0.5) discard;

      float core  = 1.0 - smoothstep(0.0,  0.15, d);
      float outer = 1.0 - smoothstep(0.15, 0.5,  d);
      float alpha = (core * 0.95 + outer * 0.35) * uAlpha;

      vec3 col = mix(uColorB, uColorA, core);
      gl_FragColor = vec4(col, alpha);
    }
  `;

  const mat = new THREE.ShaderMaterial({
    uniforms: {
      uTime:      { value: 0 },
      uState:     { value: 0 },
      uIntensity: { value: 0 },
      uColorA:    { value: new THREE.Color(0x00d4ff) },
      uColorB:    { value: new THREE.Color(0x003355) },
      uAlpha:     { value: 0.60 },
    },
    vertexShader,
    fragmentShader,
    transparent: true,
    blending:    THREE.AdditiveBlending,
    depthTest:   false,
    depthWrite:  false,
  });

  const orb = new THREE.Points(geo, mat);
  scene.add(orb);

  scene.fog = new THREE.FogExp2(0x000008, 0.07);

  // ── State colors ───────────────────────────────────────
  // Each entry: colorA (bright primary), colorB (dark secondary)
  const stateColors = {
    0: { a: new THREE.Color(0x00b8d9), b: new THREE.Color(0x001a33) }, // standby — muted cyan
    1: { a: new THREE.Color(0x88ffff), b: new THREE.Color(0x004466) }, // listening — bright ice
    2: { a: new THREE.Color(0x3377ff), b: new THREE.Color(0x000d44) }, // thinking — deep blue
    3: { a: new THREE.Color(0x00ffbb), b: new THREE.Color(0x002233) }, // speaking — teal-green
    4: { a: new THREE.Color(0xffcc44), b: new THREE.Color(0x221800) }, // followup — warm amber
  };

  // Alpha per state
  const stateAlpha = { 0: 0.55, 1: 0.88, 2: 0.72, 3: 0.90, 4: 0.70 };

  // Rotation speed per state (orb Y-axis drift)
  const stateRotSpeed = { 0: 0.05, 1: 0.18, 2: 0.28, 3: 0.10, 4: 0.07 };

  // ── State management ───────────────────────────────────
  let targetState = 0;
  let stateFloat  = 0;

  window.setOrbState = function (state) {
    targetState = state;
  };

  // ── Resize ─────────────────────────────────────────────
  function resize() {
    const w = window.innerWidth, h = window.innerHeight;
    renderer.setSize(w, h);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  resize();
  window.addEventListener('resize', resize);

  // ── Render loop ────────────────────────────────────────
  const clock = new THREE.Clock();
  let rotY = 0;

  (function animate() {
    requestAnimationFrame(animate);
    const t = clock.getElapsedTime();

    mat.uniforms.uTime.value = t;

    // Smooth state float — 0.07 per frame ≈ ~4 frames to cross 0.25 units
    stateFloat += (targetState - stateFloat) * 0.07;
    mat.uniforms.uState.value = stateFloat;

    // Lerp colors toward target
    const ts = Math.round(targetState);
    mat.uniforms.uColorA.value.lerp(stateColors[ts].a, 0.04);
    mat.uniforms.uColorB.value.lerp(stateColors[ts].b, 0.04);

    // Alpha
    const tAlpha = stateAlpha[ts];
    mat.uniforms.uAlpha.value += (tAlpha - mat.uniforms.uAlpha.value) * 0.05;

    // Rotation: faster in active states
    const tRotSpeed = stateRotSpeed[ts];
    rotY += tRotSpeed * (1 / 60);
    orb.rotation.y = rotY;
    orb.rotation.x = Math.sin(t * 0.04) * 0.10;

    renderer.render(scene, camera);
  })();
})();
