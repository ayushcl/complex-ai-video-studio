/* Neon ocean fluid background — self-contained WebGL Navier-Stokes simulation.
 * The cursor stirs glowing cyan/magenta ink through dark water behind the
 * glass UI. Pure decoration: it never blocks input (pointer-events: none),
 * disables itself under prefers-reduced-motion or without WebGL, pauses when
 * the tab is hidden, and calms while the spend-confirmation modal is open.
 *
 * Classic GPU fluid technique (advection + vorticity confinement + Jacobi
 * pressure solve), compacted. No dependencies, no network.
 */

"use strict";

(() => {
  const canvas = document.getElementById("fluid-canvas");
  if (!canvas) return;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    canvas.remove();
    return;
  }

  const config = {
    SIM_RESOLUTION: 96,
    DYE_RESOLUTION: 512,
    DENSITY_DISSIPATION: 2.1,   // trails fade quickly - subtle, not showy
    VELOCITY_DISSIPATION: 0.8,
    PRESSURE: 0.8,
    PRESSURE_ITERATIONS: 16,
    CURL: 16,
    SPLAT_RADIUS: 0.16,
    SPLAT_FORCE: 2600,
    AMBIENT_INTERVAL_MS: 8000,  // occasional gentle auto-stir while idle
    BRIGHTNESS: 0.55,           // global dim applied at display time
  };

  let calmFactor = 1.0; // NeonFluid.setCalm(true) -> near-still background

  // ----------------------------------------------------------------- //
  // Context                                                             //
  // ----------------------------------------------------------------- //
  const params = { alpha: true, depth: false, stencil: false, antialias: false, premultipliedAlpha: true };
  let gl = canvas.getContext("webgl2", params);
  const isWebGL2 = !!gl;
  if (!gl) gl = canvas.getContext("webgl", params) || canvas.getContext("experimental-webgl", params);
  if (!gl) { canvas.remove(); return; }

  let halfFloat = null;
  let supportLinearFiltering = false;
  if (isWebGL2) {
    gl.getExtension("EXT_color_buffer_float");
    supportLinearFiltering = !!gl.getExtension("OES_texture_float_linear");
  } else {
    halfFloat = gl.getExtension("OES_texture_half_float");
    supportLinearFiltering = !!gl.getExtension("OES_texture_half_float_linear");
  }
  const halfFloatTexType = isWebGL2 ? gl.HALF_FLOAT : (halfFloat && halfFloat.HALF_FLOAT_OES);
  if (!halfFloatTexType) { canvas.remove(); return; }

  function supportRenderTextureFormat(internalFormat, format, type) {
    const texture = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texImage2D(gl.TEXTURE_2D, 0, internalFormat, 4, 4, 0, format, type, null);
    const fbo = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, texture, 0);
    const ok = gl.checkFramebufferStatus(gl.FRAMEBUFFER) === gl.FRAMEBUFFER_COMPLETE;
    gl.deleteFramebuffer(fbo);
    gl.deleteTexture(texture);
    return ok;
  }

  function getFormat(internalFormat, format) {
    if (supportRenderTextureFormat(internalFormat, format, halfFloatTexType)) {
      return { internalFormat, format };
    }
    if (isWebGL2) {
      if (internalFormat === gl.R16F) return getFormat(gl.RG16F, gl.RG);
      if (internalFormat === gl.RG16F) return getFormat(gl.RGBA16F, gl.RGBA);
    }
    return null;
  }

  const formatRGBA = isWebGL2 ? getFormat(gl.RGBA16F, gl.RGBA) : getFormat(gl.RGBA, gl.RGBA);
  const formatRG = isWebGL2 ? getFormat(gl.RG16F, gl.RG) : formatRGBA;
  const formatR = isWebGL2 ? getFormat(gl.R16F, gl.RED) : formatRGBA;
  if (!formatRGBA || !formatRG || !formatR) { canvas.remove(); return; }

  // ----------------------------------------------------------------- //
  // Shaders                                                             //
  // ----------------------------------------------------------------- //
  function compile(type, source) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    return shader;
  }

  const baseVertex = compile(gl.VERTEX_SHADER, `
    precision highp float;
    attribute vec2 aPosition;
    varying vec2 vUv, vL, vR, vT, vB;
    uniform vec2 texelSize;
    void main () {
      vUv = aPosition * 0.5 + 0.5;
      vL = vUv - vec2(texelSize.x, 0.0);
      vR = vUv + vec2(texelSize.x, 0.0);
      vT = vUv + vec2(0.0, texelSize.y);
      vB = vUv - vec2(0.0, texelSize.y);
      gl_Position = vec4(aPosition, 0.0, 1.0);
    }`);

  function program(fragmentSource) {
    const fragment = compile(gl.FRAGMENT_SHADER, fragmentSource);
    const prog = gl.createProgram();
    gl.attachShader(prog, baseVertex);
    gl.attachShader(prog, fragment);
    gl.linkProgram(prog);
    const uniforms = {};
    const count = gl.getProgramParameter(prog, gl.ACTIVE_UNIFORMS);
    for (let i = 0; i < count; i++) {
      const name = gl.getActiveUniform(prog, i).name;
      uniforms[name] = gl.getUniformLocation(prog, name);
    }
    return { prog, uniforms, bind() { gl.useProgram(prog); } };
  }

  const advectionProgram = program(`
    precision highp float; precision highp sampler2D;
    varying vec2 vUv;
    uniform sampler2D uVelocity, uSource;
    uniform vec2 texelSize, dyeTexelSize;
    uniform float dt, dissipation;
    ${supportLinearFiltering ? "" : `
    vec4 bilerp (sampler2D sam, vec2 uv, vec2 tsize) {
      vec2 st = uv / tsize - 0.5;
      vec2 iuv = floor(st), fuv = fract(st);
      vec4 a = texture2D(sam, (iuv + vec2(0.5, 0.5)) * tsize);
      vec4 b = texture2D(sam, (iuv + vec2(1.5, 0.5)) * tsize);
      vec4 c = texture2D(sam, (iuv + vec2(0.5, 1.5)) * tsize);
      vec4 d = texture2D(sam, (iuv + vec2(1.5, 1.5)) * tsize);
      return mix(mix(a, b, fuv.x), mix(c, d, fuv.x), fuv.y);
    }`}
    void main () {
      ${supportLinearFiltering
        ? `vec2 coord = vUv - dt * texture2D(uVelocity, vUv).xy * texelSize;
           vec4 result = texture2D(uSource, coord);`
        : `vec2 coord = vUv - dt * bilerp(uVelocity, vUv, texelSize).xy * texelSize;
           vec4 result = bilerp(uSource, coord, dyeTexelSize);`}
      float decay = 1.0 + dissipation * dt;
      gl_FragColor = result / decay;
    }`);

  const splatProgram = program(`
    precision highp float; precision highp sampler2D;
    varying vec2 vUv;
    uniform sampler2D uTarget;
    uniform float aspectRatio;
    uniform vec3 color;
    uniform vec2 point;
    uniform float radius;
    void main () {
      vec2 p = vUv - point.xy;
      p.x *= aspectRatio;
      vec3 splat = exp(-dot(p, p) / radius) * color;
      vec3 base = texture2D(uTarget, vUv).xyz;
      gl_FragColor = vec4(base + splat, 1.0);
    }`);

  const curlProgram = program(`
    precision mediump float; precision mediump sampler2D;
    varying vec2 vUv, vL, vR, vT, vB;
    uniform sampler2D uVelocity;
    void main () {
      float L = texture2D(uVelocity, vL).y;
      float R = texture2D(uVelocity, vR).y;
      float T = texture2D(uVelocity, vT).x;
      float B = texture2D(uVelocity, vB).x;
      float vorticity = R - L - T + B;
      gl_FragColor = vec4(0.5 * vorticity, 0.0, 0.0, 1.0);
    }`);

  const vorticityProgram = program(`
    precision highp float; precision highp sampler2D;
    varying vec2 vUv, vL, vR, vT, vB;
    uniform sampler2D uVelocity, uCurl;
    uniform float curl, dt;
    void main () {
      float L = texture2D(uCurl, vL).x;
      float R = texture2D(uCurl, vR).x;
      float T = texture2D(uCurl, vT).x;
      float B = texture2D(uCurl, vB).x;
      float C = texture2D(uCurl, vUv).x;
      vec2 force = 0.5 * vec2(abs(T) - abs(B), abs(R) - abs(L));
      force /= length(force) + 0.0001;
      force *= curl * C;
      force.y *= -1.0;
      vec2 velocity = texture2D(uVelocity, vUv).xy + force * dt;
      velocity = min(max(velocity, -1000.0), 1000.0);
      gl_FragColor = vec4(velocity, 0.0, 1.0);
    }`);

  const divergenceProgram = program(`
    precision mediump float; precision mediump sampler2D;
    varying vec2 vUv, vL, vR, vT, vB;
    uniform sampler2D uVelocity;
    void main () {
      float L = texture2D(uVelocity, vL).x;
      float R = texture2D(uVelocity, vR).x;
      float T = texture2D(uVelocity, vT).y;
      float B = texture2D(uVelocity, vB).y;
      vec2 C = texture2D(uVelocity, vUv).xy;
      if (vL.x < 0.0) { L = -C.x; }
      if (vR.x > 1.0) { R = -C.x; }
      if (vT.y > 1.0) { T = -C.y; }
      if (vB.y < 0.0) { B = -C.y; }
      gl_FragColor = vec4(0.5 * (R - L + T - B), 0.0, 0.0, 1.0);
    }`);

  const pressureProgram = program(`
    precision mediump float; precision mediump sampler2D;
    varying vec2 vUv, vL, vR, vT, vB;
    uniform sampler2D uPressure, uDivergence;
    void main () {
      float L = texture2D(uPressure, vL).x;
      float R = texture2D(uPressure, vR).x;
      float T = texture2D(uPressure, vT).x;
      float B = texture2D(uPressure, vB).x;
      float divergence = texture2D(uDivergence, vUv).x;
      float pressure = (L + R + B + T - divergence) * 0.25;
      gl_FragColor = vec4(pressure, 0.0, 0.0, 1.0);
    }`);

  const gradientSubtractProgram = program(`
    precision mediump float; precision mediump sampler2D;
    varying vec2 vUv, vL, vR, vT, vB;
    uniform sampler2D uPressure, uVelocity;
    void main () {
      float L = texture2D(uPressure, vL).x;
      float R = texture2D(uPressure, vR).x;
      float T = texture2D(uPressure, vT).x;
      float B = texture2D(uPressure, vB).x;
      vec2 velocity = texture2D(uVelocity, vUv).xy;
      velocity.xy -= vec2(R - L, T - B);
      gl_FragColor = vec4(velocity, 0.0, 1.0);
    }`);

  const clearProgram = program(`
    precision mediump float; precision mediump sampler2D;
    varying vec2 vUv;
    uniform sampler2D uTexture;
    uniform float value;
    void main () {
      gl_FragColor = value * texture2D(uTexture, vUv);
    }`);

  const displayProgram = program(`
    precision highp float; precision highp sampler2D;
    varying vec2 vUv;
    uniform sampler2D uTexture;
    uniform float brightness;
    void main () {
      vec3 c = texture2D(uTexture, vUv).rgb * brightness;
      float m = max(c.r, max(c.g, c.b));
      if (m > 1.0) { c /= m; }
      float a = clamp(m, 0.0, 1.0);
      gl_FragColor = vec4(c, a);
    }`);

  // ----------------------------------------------------------------- //
  // Framebuffers                                                        //
  // ----------------------------------------------------------------- //
  const quad = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, quad);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, -1, 1, 1, 1, 1, -1]), gl.STATIC_DRAW);
  const quadIndex = gl.createBuffer();
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, quadIndex);
  gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, new Uint16Array([0, 1, 2, 0, 2, 3]), gl.STATIC_DRAW);
  gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
  gl.enableVertexAttribArray(0);

  function blit(target) {
    if (target == null) {
      gl.viewport(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight);
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    } else {
      gl.viewport(0, 0, target.width, target.height);
      gl.bindFramebuffer(gl.FRAMEBUFFER, target.fbo);
    }
    gl.drawElements(gl.TRIANGLES, 6, gl.UNSIGNED_SHORT, 0);
  }

  function createFBO(w, h, internalFormat, format, type, filtering) {
    const texture = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, filtering);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, filtering);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texImage2D(gl.TEXTURE_2D, 0, internalFormat, w, h, 0, format, type, null);
    const fbo = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, texture, 0);
    gl.viewport(0, 0, w, h);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    return {
      texture, fbo, width: w, height: h,
      texelSizeX: 1 / w, texelSizeY: 1 / h,
      attach(id) {
        gl.activeTexture(gl.TEXTURE0 + id);
        gl.bindTexture(gl.TEXTURE_2D, texture);
        return id;
      },
    };
  }

  function createDoubleFBO(w, h, internalFormat, format, type, filtering) {
    let fbo1 = createFBO(w, h, internalFormat, format, type, filtering);
    let fbo2 = createFBO(w, h, internalFormat, format, type, filtering);
    return {
      width: w, height: h, texelSizeX: 1 / w, texelSizeY: 1 / h,
      get read() { return fbo1; },
      get write() { return fbo2; },
      swap() { const t = fbo1; fbo1 = fbo2; fbo2 = t; },
    };
  }

  function getResolution(resolution) {
    let aspect = gl.drawingBufferWidth / gl.drawingBufferHeight;
    if (aspect < 1) aspect = 1 / aspect;
    const min = Math.round(resolution);
    const max = Math.round(resolution * aspect);
    return gl.drawingBufferWidth > gl.drawingBufferHeight
      ? { width: max, height: min }
      : { width: min, height: max };
  }

  let dye, velocity, divergence, curl, pressure;
  const filtering = supportLinearFiltering ? gl.LINEAR : gl.NEAREST;

  function initFramebuffers() {
    const simRes = getResolution(config.SIM_RESOLUTION);
    const dyeRes = getResolution(config.DYE_RESOLUTION);
    dye = createDoubleFBO(dyeRes.width, dyeRes.height, formatRGBA.internalFormat, formatRGBA.format, halfFloatTexType, filtering);
    velocity = createDoubleFBO(simRes.width, simRes.height, formatRG.internalFormat, formatRG.format, halfFloatTexType, filtering);
    divergence = createFBO(simRes.width, simRes.height, formatR.internalFormat, formatR.format, halfFloatTexType, gl.NEAREST);
    curl = createFBO(simRes.width, simRes.height, formatR.internalFormat, formatR.format, halfFloatTexType, gl.NEAREST);
    pressure = createDoubleFBO(simRes.width, simRes.height, formatR.internalFormat, formatR.format, halfFloatTexType, gl.NEAREST);
  }

  function resizeCanvas() {
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    const w = Math.floor(canvas.clientWidth * dpr);
    const h = Math.floor(canvas.clientHeight * dpr);
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
      return true;
    }
    return false;
  }

  resizeCanvas();
  initFramebuffers();

  // ----------------------------------------------------------------- //
  // Simulation step                                                     //
  // ----------------------------------------------------------------- //
  function step(dt) {
    gl.disable(gl.BLEND);

    curlProgram.bind();
    gl.uniform2f(curlProgram.uniforms.texelSize, velocity.texelSizeX, velocity.texelSizeY);
    gl.uniform1i(curlProgram.uniforms.uVelocity, velocity.read.attach(0));
    blit(curl);

    vorticityProgram.bind();
    gl.uniform2f(vorticityProgram.uniforms.texelSize, velocity.texelSizeX, velocity.texelSizeY);
    gl.uniform1i(vorticityProgram.uniforms.uVelocity, velocity.read.attach(0));
    gl.uniform1i(vorticityProgram.uniforms.uCurl, curl.attach(1));
    gl.uniform1f(vorticityProgram.uniforms.curl, config.CURL);
    gl.uniform1f(vorticityProgram.uniforms.dt, dt);
    blit(velocity.write);
    velocity.swap();

    divergenceProgram.bind();
    gl.uniform2f(divergenceProgram.uniforms.texelSize, velocity.texelSizeX, velocity.texelSizeY);
    gl.uniform1i(divergenceProgram.uniforms.uVelocity, velocity.read.attach(0));
    blit(divergence);

    clearProgram.bind();
    gl.uniform1i(clearProgram.uniforms.uTexture, pressure.read.attach(0));
    gl.uniform1f(clearProgram.uniforms.value, config.PRESSURE);
    blit(pressure.write);
    pressure.swap();

    pressureProgram.bind();
    gl.uniform2f(pressureProgram.uniforms.texelSize, velocity.texelSizeX, velocity.texelSizeY);
    gl.uniform1i(pressureProgram.uniforms.uDivergence, divergence.attach(0));
    for (let i = 0; i < config.PRESSURE_ITERATIONS; i++) {
      gl.uniform1i(pressureProgram.uniforms.uPressure, pressure.read.attach(1));
      blit(pressure.write);
      pressure.swap();
    }

    gradientSubtractProgram.bind();
    gl.uniform2f(gradientSubtractProgram.uniforms.texelSize, velocity.texelSizeX, velocity.texelSizeY);
    gl.uniform1i(gradientSubtractProgram.uniforms.uPressure, pressure.read.attach(0));
    gl.uniform1i(gradientSubtractProgram.uniforms.uVelocity, velocity.read.attach(1));
    blit(velocity.write);
    velocity.swap();

    advectionProgram.bind();
    gl.uniform2f(advectionProgram.uniforms.texelSize, velocity.texelSizeX, velocity.texelSizeY);
    if (!supportLinearFiltering) {
      gl.uniform2f(advectionProgram.uniforms.dyeTexelSize, velocity.texelSizeX, velocity.texelSizeY);
    }
    const velocityId = velocity.read.attach(0);
    gl.uniform1i(advectionProgram.uniforms.uVelocity, velocityId);
    gl.uniform1i(advectionProgram.uniforms.uSource, velocityId);
    gl.uniform1f(advectionProgram.uniforms.dt, dt);
    gl.uniform1f(advectionProgram.uniforms.dissipation, config.VELOCITY_DISSIPATION);
    blit(velocity.write);
    velocity.swap();

    if (!supportLinearFiltering) {
      gl.uniform2f(advectionProgram.uniforms.dyeTexelSize, dye.texelSizeX, dye.texelSizeY);
    }
    gl.uniform1i(advectionProgram.uniforms.uVelocity, velocity.read.attach(0));
    gl.uniform1i(advectionProgram.uniforms.uSource, dye.read.attach(1));
    gl.uniform1f(advectionProgram.uniforms.dissipation, config.DENSITY_DISSIPATION);
    blit(dye.write);
    dye.swap();
  }

  function render() {
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    displayProgram.bind();
    gl.uniform1i(displayProgram.uniforms.uTexture, dye.read.attach(0));
    gl.uniform1f(displayProgram.uniforms.brightness, config.BRIGHTNESS);
    blit(null);
  }

  // ----------------------------------------------------------------- //
  // Splats: the neon-vice ink palette (cyan -> violet -> magenta)       //
  // ----------------------------------------------------------------- //
  function HSVtoRGB(h, s, v) {
    const i = Math.floor(h * 6);
    const f = h * 6 - i;
    const p = v * (1 - s), q = v * (1 - f * s), t = v * (1 - (1 - f) * s);
    switch (i % 6) {
      case 0: return [v, t, p];
      case 1: return [q, v, p];
      case 2: return [p, v, t];
      case 3: return [p, q, v];
      case 4: return [t, p, v];
      default: return [v, p, q];
    }
  }

  let hue = 0.5;
  function nextColor(intensity) {
    // Drift around the cyan(0.50) -> violet(0.75) -> magenta(0.92) arc only.
    hue += 0.013;
    const arc = 0.5 + ((hue % 1) * 0.42);
    const [r, g, b] = HSVtoRGB(arc, 0.9, 1.0);
    const k = 0.085 * intensity * calmFactor;
    return [r * k, g * k, b * k];
  }

  function correctRadius(radius) {
    const aspect = canvas.width / canvas.height;
    return aspect > 1 ? radius * aspect : radius;
  }

  function splat(x, y, dx, dy, color) {
    splatProgram.bind();
    gl.uniform1i(splatProgram.uniforms.uTarget, velocity.read.attach(0));
    gl.uniform1f(splatProgram.uniforms.aspectRatio, canvas.width / canvas.height);
    gl.uniform2f(splatProgram.uniforms.point, x, y);
    gl.uniform3f(splatProgram.uniforms.color, dx, dy, 0);
    gl.uniform1f(splatProgram.uniforms.radius, correctRadius(config.SPLAT_RADIUS / 100));
    blit(velocity.write);
    velocity.swap();

    gl.uniform1i(splatProgram.uniforms.uTarget, dye.read.attach(0));
    gl.uniform3f(splatProgram.uniforms.color, color[0], color[1], color[2]);
    blit(dye.write);
    dye.swap();
  }

  // ----------------------------------------------------------------- //
  // Pointer                                                             //
  // ----------------------------------------------------------------- //
  const pointer = { x: 0.5, y: 0.5, dx: 0, dy: 0, moved: false, down: false };

  window.addEventListener("pointermove", (e) => {
    const x = e.clientX / window.innerWidth;
    const y = 1 - e.clientY / window.innerHeight;
    pointer.dx = (x - pointer.x) * config.SPLAT_FORCE * calmFactor;
    pointer.dy = (y - pointer.y) * config.SPLAT_FORCE * calmFactor;
    pointer.x = x;
    pointer.y = y;
    pointer.moved = Math.abs(pointer.dx) > 0 || Math.abs(pointer.dy) > 0;
  }, { passive: true });

  window.addEventListener("pointerdown", (e) => {
    const x = e.clientX / window.innerWidth;
    const y = 1 - e.clientY / window.innerHeight;
    // click ripple: a small burst of slow ink
    for (let i = 0; i < 3; i++) {
      const angle = Math.random() * Math.PI * 2;
      const force = 200 * calmFactor;
      splat(x, y, Math.cos(angle) * force, Math.sin(angle) * force, nextColor(0.9));
    }
  }, { passive: true });

  let lastAmbient = performance.now();
  function ambient(now) {
    if (now - lastAmbient < config.AMBIENT_INTERVAL_MS || calmFactor < 1) return;
    lastAmbient = now + Math.random() * 4000;
    const x = Math.random(), y = Math.random() * 0.7 + 0.15;
    const angle = Math.random() * Math.PI * 2;
    splat(x, y, Math.cos(angle) * 180, Math.sin(angle) * 180, nextColor(0.4));
  }

  // ----------------------------------------------------------------- //
  // Main loop                                                           //
  // ----------------------------------------------------------------- //
  let lastTime = performance.now();
  let running = true;

  function frame(now) {
    if (!running) return;
    const dt = Math.min((now - lastTime) / 1000, 1 / 30);
    lastTime = now;
    if (resizeCanvas()) initFramebuffers();
    if (pointer.moved) {
      pointer.moved = false;
      splat(pointer.x, pointer.y, pointer.dx, pointer.dy, nextColor(1));
    }
    ambient(now);
    step(dt);
    render();
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      running = false;
    } else if (!running) {
      running = true;
      lastTime = performance.now();
      requestAnimationFrame(frame);
    }
  });

  // Tiny public API: the app hushes the ocean during spend confirmation, and
  // tick() lets a smoke test drive one frame in a hidden window where rAF
  // never fires.
  window.NeonFluid = {
    setCalm(calm) { calmFactor = calm ? 0.12 : 1.0; },
    tick() {
      if (resizeCanvas()) initFramebuffers();
      splat(0.5, 0.5, 120, 80, nextColor(1));
      step(1 / 60);
      render();
      return { width: canvas.width, height: canvas.height, glError: gl.getError() };
    },
  };
})();
