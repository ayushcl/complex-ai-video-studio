/* VEO Ad Pipeline operator console — guided launch sequence.
 *
 * Safety contract (unchanged from v1, only the presentation moved):
 *  - every FREE action calls the adapter without --run;
 *  - a live run needs: packet allow_live_run=true (explicit authorize action),
 *    a fresh passing dry-run of the exact packet bytes, and the typed SPEND
 *    confirmation in a separate modal. One ambiguous click can never spend.
 *  - voices are never preselected, ranked, or defaulted; the pick button stays
 *    disabled until THAT sample has been played in this session.
 * The server enforces all of this independently; this file is presentation.
 */

"use strict";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const STEPS = ["job", "voice", "preview", "launch"];

const state = {
  mode: "simple",
  step: "job",
  choices: { content_path: "silent_brand", video_source: "existing" },
  packet: null,
  packetPath: null,
  packetSha: null,
  lastDryrun: null,
  selectedRunId: null,
  pollTimer: null,
  playedSamples: new Set(),
  liveStages: null, // stages from a selected/running run (overrides planned in rail)
  health: null,
};

/* ------------------------------------------------------------------ */
/* Mode: simple (default) <-> administrator console                    */
/* ------------------------------------------------------------------ */
function setMode(mode) {
  state.mode = mode;
  document.body.classList.toggle("mode-simple", mode === "simple");
  document.body.classList.toggle("mode-admin", mode === "admin");
  document.getElementById("simple-root").classList.toggle("hidden", mode !== "simple");
  document.getElementById("admin-root").classList.toggle("hidden", mode !== "admin");
  $$(".admin-only").forEach((el) => el.classList.toggle("hidden", mode !== "admin"));
  $("#brand-title").innerHTML = mode === "admin" ? "VEO <em>Ad Pipeline</em>" : "Video <em>Ad Pipeline</em>";
  document.title = mode === "admin" ? "VEO Ad Pipeline — Operator Console" : "Video Ad Pipeline — Operator Console";
  $("#btn-mode").textContent = mode === "admin" ? "← Simple mode" : "Administrator";
  $("#brand-sub").textContent = mode === "admin"
    ? "operator console · packet in, proven command out"
    : "describe it · preview it · finish it";
  renderHealthChips();
}
document.getElementById("btn-mode").addEventListener("click", () => {
  setMode(state.mode === "admin" ? "simple" : "admin");
});

/* ------------------------------------------------------------------ */
/* API helpers                                                         */
/* ------------------------------------------------------------------ */
async function api(path, options = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  let data = null;
  try { data = await res.json(); } catch { /* non-JSON */ }
  if (!res.ok) throw new Error(data && data.error ? data.error : `${res.status} ${res.statusText}`);
  return data;
}
const apiGet = (p) => api(p);
const apiPost = (p, body) => api(p, { method: "POST", body: JSON.stringify(body || {}) });

function esc(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

/* ------------------------------------------------------------------ */
/* Stepper                                                             */
/* ------------------------------------------------------------------ */
function voiceNeeded() { return state.choices.content_path === "presenter"; }

function goStep(name) {
  if (name === "voice" && !voiceNeeded()) name = "job";
  state.step = name;
  $$(".step").forEach((s) => s.classList.toggle("active", s.dataset.step === name));
  $$(".step-panel").forEach((p) => p.classList.toggle("active", p.id === `panel-${name}`));
  updateStepper();
  if (name === "voice") $("#btn-voice-continue").disabled = !formEl("prepared_voice_path").value;
  if (name === "launch") updateLaunchPanel();
}

function updateStepper() {
  const voiceStep = $("#step-voice");
  if (voiceNeeded()) {
    voiceStep.classList.remove("skipped");
    voiceStep.disabled = false;
    $("#step-voice-sub").textContent = "human pick";
  } else {
    voiceStep.classList.add("skipped");
    voiceStep.disabled = true;
    $("#step-voice-sub").textContent = "skipped — no voice";
  }
  const dryOk = state.lastDryrun && state.lastDryrun.ok;
  $$(".step").forEach((s) => {
    const name = s.dataset.step;
    if (name === "preview") s.disabled = !state.packetPath;
    if (name === "launch") s.disabled = !dryOk;
    s.classList.toggle("done",
      (name === "job" && !!state.packetPath) ||
      (name === "voice" && voiceNeeded() && !!formEl("prepared_voice_path").value) ||
      (name === "preview" && !!dryOk));
  });
}

$("#stepper").addEventListener("click", (e) => {
  const step = e.target.closest(".step");
  if (step && !step.disabled) goStep(step.dataset.step);
});
document.addEventListener("click", (e) => {
  const nav = e.target.closest("[data-goto]");
  if (nav) goStep(nav.dataset.goto);
});

/* ------------------------------------------------------------------ */
/* Health chips                                                        */
/* ------------------------------------------------------------------ */
async function loadHealth() {
  try {
    state.health = await apiGet("/api/health");
  } catch (err) {
    state.health = null;
  }
  renderHealthChips();
}

function renderHealthChips() {
  const h = state.health;
  const box = $("#health-chips");
  if (!h) {
    box.innerHTML = `<span class="chip off">server unreachable</span>`;
    return;
  }
  if (state.mode === "admin") {
    const chips = [
      ["adapter", h.adapter_exists], ["ffmpeg", h.ffmpeg], ["ffprobe", h.ffprobe],
      ["GEMINI", h.gemini_key_configured], ["11Labs", h.elevenlabs_key_configured],
    ];
    box.innerHTML = chips
      .map(([l, on]) => `<span class="chip ${on ? "on" : "off"}">${esc(l)} ${on ? "✓" : "✗"}</span>`).join("");
    return;
  }
  // Simple mode: friendly capability summary. The app runs either way - these
  // say which PAID stages are ready, and what to add in Admin > Settings.
  const caps = h.capabilities || {};
  const videoReady = caps.veo_generation && caps.music && caps.assemble;
  const chips = [
    [videoReady ? "Video generation ready" : "Video setup needed", videoReady,
     videoReady ? "Draft and high-quality generation are ready." : "Configure in Administrator → Settings. Building jobs and previews stay free meanwhile."],
    [caps.voice_sts ? "Voice ready" : "Voice off (not needed here)", !!caps.voice_sts,
     caps.voice_sts ? "Voice jobs available in the Administrator console." : "Simple mode makes silent videos, so this doesn't block you. Voice setup is available in Administrator settings."],
  ];
  box.innerHTML = chips
    .map(([label, on, tip]) => `<span class="cap-chip ${on ? "on" : "off"}" title="${esc(tip)}">${esc(label)}</span>`).join("");
}

/* ------------------------------------------------------------------ */
/* Step 1 · Job                                                        */
/* ------------------------------------------------------------------ */
function formEl(name) { return $("#packet-form").elements[name]; }

// A presenter reference image puts Veo into asset-reference mode, which FORCES
// a fixed model/resolution/duration regardless of the operator's picks. Mirrors
// run_from_packet.PRESENTER_REFERENCE_* (and the hint text in index.html).
const PRESENTER_REFERENCE_MODEL = "veo-3.1-fast-generate-preview";
const PRESENTER_REFERENCE_RESOLUTION = "720p";

// Reflect that forcing in the form: when a reference image is supplied, show
// the forced model/resolution and LOCK those inputs so the form can't display a
// tier the engine will silently override. The dry-run preview already shows the
// same forced values; this keeps the editable form consistent with it.
function reflectPresenterReferenceOverride() {
  const refField = formEl("presenter_reference_image_path");
  const modelField = formEl("model");
  const resField = formEl("resolution");
  if (!refField || !modelField || !resField) return;
  const active = !$("#fs-presenter-reference").classList.contains("hidden")
    && refField.value.trim() !== "";
  const note = $("#presenter-reference-forced-note");
  if (active) {
    modelField.value = PRESENTER_REFERENCE_MODEL;
    resField.value = PRESENTER_REFERENCE_RESOLUTION;
  }
  modelField.disabled = active;
  resField.disabled = active;
  modelField.classList.toggle("forced-by-reference", active);
  resField.classList.toggle("forced-by-reference", active);
  if (note) note.classList.toggle("hidden", !active);
}

function formValues() {
  const data = { ...state.choices };
  new FormData($("#packet-form")).forEach((value, key) => { data[key] = value; });
  const presenterReference = formEl("presenter_reference_image_path");
  data.presenter_reference_image_path = presenterReference
    ? presenterReference.value.trim()
    : "";
  return data;
}

// Any job mutation invalidates the saved packet + dry-run: the gates must go
// red until the new configuration is saved and dry-run again. Otherwise a
// launch would spend on the OLD on-disk packet while the form shows the new
// one. (Programmatic .value assignments don't fire 'input', so loading a
// packet or picking a voice doesn't self-invalidate.)
function invalidateDryrun() {
  if (!state.packetPath && !state.lastDryrun) return;
  state.packetPath = null;
  state.packetSha = null;
  state.lastDryrun = null;
  state.liveStages = null;
  $("#dryrun-verdict").innerHTML =
    `<div class="banner banner-warn">Job changed since the last save — <strong>Save &amp; preview</strong> again to re-validate before launch.</div>`;
  updateStepper();
  renderRail();
}
$("#packet-form").addEventListener("input", invalidateDryrun);

document.addEventListener("click", (e) => {
  const choice = e.target.closest(".choice");
  if (!choice) return;
  const changed = state.choices[choice.dataset.field] !== choice.dataset.value;
  state.choices[choice.dataset.field] = choice.dataset.value;
  choice.parentElement.querySelectorAll(".choice").forEach((c) => c.classList.toggle("selected", c === choice));
  if (changed) invalidateDryrun();
  updateConditionalForm();
  updateStepper();
});

function updateConditionalForm() {
  const generate = state.choices.video_source === "generate";
  const presenter = state.choices.content_path === "presenter";
  $("#fs-existing").classList.toggle("hidden", generate);
  $("#fs-generate").classList.toggle("hidden", !generate);
  $("#fs-voice").classList.toggle("hidden", !presenter);
  $("#fs-presenter-reference").classList.toggle("hidden", !(generate && presenter));
  $("#experimental-banner").classList.toggle("hidden", !(generate && presenter));
  $("#btn-job-continue").innerHTML = (presenter && !formEl("prepared_voice_path").value)
    ? 'Continue — pick the voice →'
    : 'Save &amp; preview <span class="tag tag-free">FREE</span>';
  if (generate && formEl("scenes_path").value) inspectScenes();
  else $("#scenes-inspect").classList.add("hidden");
  reflectPresenterReferenceOverride();
  renderRailJob();
}

// Typing/clearing the reference path doesn't change a choice, so re-reflect the
// forced model/resolution lock directly on input.
formEl("presenter_reference_image_path").addEventListener("input", reflectPresenterReferenceOverride);

let scenesInspectTimer = null;
["scenes_path", "max_scenes"].forEach((name) => {
  formEl(name).addEventListener("input", () => {
    clearTimeout(scenesInspectTimer);
    scenesInspectTimer = setTimeout(inspectScenes, 500);
  });
});

async function inspectScenes() {
  const v = formValues();
  const box = $("#scenes-inspect");
  if (!v.scenes_path || state.choices.video_source !== "generate") { box.classList.add("hidden"); return; }
  try {
    const info = await apiPost("/api/scenes/inspect", {
      path: v.scenes_path,
      max_scenes: v.max_scenes ? parseInt(v.max_scenes, 10) : null,
    });
    const issues = (info.issues || []).map((i) => `<li class="inspect-issue">${esc(i)}</li>`).join("");
    box.innerHTML = `
      <strong>Scenes check</strong> <span class="mini">(hints — the engine validates authoritatively)</span>
      <ul>
        <li>${info.scene_count ?? "?"} scene(s); spend cap limits live generation to <strong>${info.effective_scenes ?? "?"}</strong></li>
        <li>Seed image: <code>${esc(info.seed_image || "(missing)")}</code> ${info.seed_image_exists ? '<span class="inspect-ok">✓ found</span>' : '<span class="inspect-issue">NOT FOUND</span>'}</li>
        <li>Estimated length: ~${info.estimated_duration_seconds ?? "?"}s</li>
        ${issues}
      </ul>`;
    box.classList.remove("hidden");
  } catch (err) {
    box.innerHTML = `<span class="inspect-issue">${esc(err.message)}</span>`;
    box.classList.remove("hidden");
  }
}

$("#btn-goto-voice-inline").addEventListener("click", () => goStep("voice"));

$("#btn-job-continue").addEventListener("click", async () => {
  const errBox = $("#job-error");
  errBox.classList.add("hidden");
  if (voiceNeeded() && !formEl("prepared_voice_path").value) { goStep("voice"); return; }
  await saveAndPreview(errBox);
});

$("#btn-voice-continue").addEventListener("click", async () => {
  await saveAndPreview($("#audition-error"));
});

async function saveAndPreview(errBox) {
  try {
    const built = await apiPost("/api/packet/build", { form: formValues() });
    if (built.structured && !built.structured.valid) {
      errBox.textContent = "PACKET REJECTED: " + built.structured.error;
      errBox.classList.remove("hidden");
      return;
    }
    await savePacketAndDryrun(built.packet);
  } catch (err) {
    errBox.textContent = err.message;
    errBox.classList.remove("hidden");
  }
}

async function savePacketAndDryrun(packet) {
  const saved = await apiPost("/api/packet/save", { packet });
  state.packet = packet;
  state.packetPath = saved.path;
  state.packetSha = saved.sha256;
  state.lastDryrun = null;
  state.liveStages = null;
  renderRailJob();
  updateStepper();
  goStep("preview");
  await runDryrun();
}

/* ------------------------------------------------------------------ */
/* Step 2 · Voice                                                      */
/* ------------------------------------------------------------------ */
$("#btn-load-auditions").addEventListener("click", loadAuditions);

async function loadAuditions() {
  const dir = $("#audition-dir").value.trim() || "voice_auditions";
  const errBox = $("#audition-error");
  errBox.classList.add("hidden");
  $("#audition-list").innerHTML = "";
  try {
    const data = await apiGet(`/api/auditions?dir=${encodeURIComponent(dir)}`);
    if (!data.samples.length) {
      errBox.textContent = `No audio samples found in ${data.dir}. Place audition files (.mp3/.wav/…) there, optionally with an auditions_manifest.json carrying each sample's workspace_voice_id.`;
      errBox.classList.remove("hidden");
      return;
    }
    $("#audition-list").innerHTML = data.samples.map((s) => `
      <div class="audition-item" data-sample="${esc(s.path)}">
        <div>
          <div class="aud-name">${esc(s.label || s.file)}</div>
          <div class="aud-meta">${esc(s.file)} · ${(s.size_bytes / 1024).toFixed(0)} KB${s.notes ? " · " + esc(s.notes) : ""}</div>
        </div>
        <div class="aud-meta">${s.workspace_voice_id ? "voice id: " + esc(s.workspace_voice_id) : '<span class="not-listened-note">no voice id in metadata — enter manually</span>'}</div>
        <audio controls preload="none" src="/api/media?path=${encodeURIComponent(s.path)}" data-sample-audio="${esc(s.path)}"></audio>
        <div class="aud-pick">
          <input data-voice-id-for="${esc(s.path)}" placeholder="workspace_voice_id" value="${esc(s.workspace_voice_id || "")}">
          <input data-voice-label-for="${esc(s.path)}" placeholder="label (optional)" value="${esc(s.label || "")}" style="max-width:170px">
          <button class="btn btn-small btn-free" data-pick-voice="${esc(s.path)}" disabled title="Listen to this sample first">Use this voice</button>
          <span class="not-listened-note" data-listen-note="${esc(s.path)}">listen first — picking is a human decision</span>
        </div>
      </div>`).join("");
  } catch (err) {
    errBox.textContent = err.message;
    errBox.classList.remove("hidden");
  }
}

// Picking unlocks only after the operator actually plays that sample.
document.addEventListener("play", (e) => {
  const samplePath = e.target.dataset && e.target.dataset.sampleAudio;
  if (!samplePath) return;
  state.playedSamples.add(samplePath);
  const pickBtn = document.querySelector(`[data-pick-voice="${CSS.escape(samplePath)}"]`);
  const note = document.querySelector(`[data-listen-note="${CSS.escape(samplePath)}"]`);
  const item = e.target.closest(".audition-item");
  if (pickBtn) { pickBtn.disabled = false; pickBtn.title = ""; }
  if (note) note.textContent = "listened ✓";
  if (item) item.classList.add("listened");
}, true);

document.addEventListener("click", async (e) => {
  const pick = e.target.closest("[data-pick-voice]");
  if (!pick) return;
  const samplePath = pick.dataset.pickVoice;
  if (!state.playedSamples.has(samplePath)) return; // defense in depth
  const voiceId = document.querySelector(`[data-voice-id-for="${CSS.escape(samplePath)}"]`).value.trim();
  const label = document.querySelector(`[data-voice-label-for="${CSS.escape(samplePath)}"]`).value.trim();
  const errBox = $("#audition-error");
  errBox.classList.add("hidden");
  try {
    const result = await apiPost("/api/voice/select", {
      sample_path: samplePath, workspace_voice_id: voiceId, label, listened: true,
    });
    formEl("prepared_voice_path").value = result.prepared_voice_path;
    $("#btn-voice-continue").disabled = false;
    updateStepper();
    updateConditionalForm();
    pick.closest(".audition-item").insertAdjacentHTML("beforeend",
      `<div class="banner banner-ok" style="grid-column:1/-1">Selected. <code>${esc(result.prepared_voice_path)}</code> written and applied to the job.</div>`);
  } catch (err) {
    errBox.textContent = err.message;
    errBox.classList.remove("hidden");
  }
});

$("#btn-use-existing-voice").addEventListener("click", () => {
  const path = $("#existing-voice-path").value.trim();
  if (!path) return;
  formEl("prepared_voice_path").value = path;
  $("#btn-voice-continue").disabled = false;
  updateStepper();
  updateConditionalForm();
});

/* ------------------------------------------------------------------ */
/* Step 3 · Preview (dry-run)                                          */
/* ------------------------------------------------------------------ */
$("#btn-dryrun-again").addEventListener("click", runDryrun);
$("#btn-engineplan").addEventListener("click", runEnginePlan);
$("#btn-adapter-output").addEventListener("click", () => {
  const r = state.lastDryrun;
  if (!r) return;
  openDrawer("Adapter output (verbatim)",
    `<pre class="code-block tall">${esc((r.stdout || "") + (r.stderr ? "\n--- stderr ---\n" + r.stderr : ""))}</pre>`);
});

async function runDryrun() {
  if (!state.packetPath) return;
  $("#dryrun-running").classList.remove("hidden");
  $("#btn-dryrun-again").disabled = true;
  try {
    const result = await apiPost("/api/dryrun", { path: state.packetPath });
    state.packetSha = result.packet_sha256;
    state.lastDryrun = result;
    state.liveStages = null;
    renderDryrun(result);
  } catch (err) {
    $("#dryrun-verdict").innerHTML = `<div class="banner banner-error">${esc(err.message)}</div>`;
  } finally {
    $("#dryrun-running").classList.add("hidden");
    $("#btn-dryrun-again").disabled = false;
    updateStepper();
    renderRail();
  }
}

function renderDryrun(result) {
  const s = result.structured || {};
  if (!result.ok) {
    $("#dryrun-verdict").innerHTML = `
      <div class="banner banner-error">VALIDATION FAILED — launch is blocked until this is fixed.\n\n${esc(result.stderr || (s.valid === false ? s.error : "unknown error"))}</div>`;
  } else {
    $("#dryrun-verdict").innerHTML = `
      <div class="banner banner-ok">Dry-run passed through the real engine (exit 0 — nothing spent). This exact packet (sha ${esc((result.packet_sha256 || "").slice(0, 12))}…) is eligible to launch${s.allow_live_run ? "" : " once spend is authorized below"}.</div>`;
  }

  const rows = [
    ["job", s.job_id],
    ["route", `${s.content_path ?? "?"} + ${s.video_source ?? "?"}`],
    s.video_path ? ["video", s.video_path] : null,
    s.scenes_path ? ["scenes", s.scenes_path] : null,
    s.presenter_reference_image_path ? ["presenter reference", s.presenter_reference_image_path] : null,
    ["music direction", s.storyboard_path],
    s.prepared_voice_path ? ["voice", s.prepared_voice_path] : ["voice", "(none — silent)"],
    s.model ? ["model", `${s.model} @ ${s.resolution}`] : null,
    s.video_source === "generate" ? ["spend cap", s.max_scenes != null ? `max_scenes = ${s.max_scenes}` : "UNCAPPED — every scene paid"] : null,
    ["start stage", `${s.start_stage ?? "—"} (derived by the adapter)`],
    ["packet file", result.packet_path],
  ].filter(Boolean);
  $("#dryrun-summary").innerHTML = rows
    .map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v ?? "(none)")}</td></tr>`).join("");

  const warnings = (s.warnings || []).map((w) => `<div class="banner banner-warn">WARNING: ${esc(w)}</div>`).join("");
  const experimental = s.experimental
    ? `<div class="banner banner-warn"><strong>Experimental route:</strong> generate + presenter is not validated end to end.</div>` : "";
  const uncapped = (s.video_source === "generate" && s.max_scenes == null)
    ? `<div class="banner banner-warn"><strong>No spend cap:</strong> a live run pays for every scene in the file.</div>` : "";
  $("#dryrun-warnings").innerHTML = experimental + uncapped + warnings;

  $("#dryrun-command").textContent = s.valid
    ? `${s.derived_command}\n(launch appends --run; the adapter only obeys when both of its gates pass)`
    : "(no command — packet rejected)";

  renderSpendGate(result);
}

function renderSpendGate(result) {
  const s = result.structured || {};
  const gate = $("#spend-gate");
  if (!result.ok) {
    gate.classList.remove("authorized");
    gate.innerHTML = `<strong>Live spend</strong><div class="gate-row"><span class="gate-dot fail"></span>Validation must pass before spend can be authorized.</div>`;
    $("#btn-preview-continue").disabled = true;
    return;
  }
  gate.classList.toggle("authorized", !!s.allow_live_run);
  gate.innerHTML = `
    <strong>Spend authorization — gate 1 of 2</strong>
    <div class="gate-row"><span class="gate-dot pass"></span>Dry-run passed for this exact packet</div>
    <div class="gate-row"><span class="gate-dot ${s.allow_live_run ? "pass" : "fail"}"></span>Packet allows live spend (<code>allow_live_run</code> = <strong>${s.allow_live_run}</strong>)</div>
    <div class="actions">
      ${s.allow_live_run
        ? `<button class="btn btn-small" id="btn-deauthorize">Withdraw authorization</button>`
        : `<button class="btn btn-paid" id="btn-authorize">Authorize live spend — writes allow_live_run: true</button>`}
    </div>
    <p class="micro">Authorizing rewrites the packet file, so a fresh dry-run re-runs automatically. Gate 2 is the typed confirmation at launch.</p>`;
  const auth = $("#btn-authorize");
  if (auth) auth.addEventListener("click", () => setAuthorization(true));
  const deauth = $("#btn-deauthorize");
  if (deauth) deauth.addEventListener("click", () => setAuthorization(false));
  $("#btn-preview-continue").disabled = false;
}

$("#btn-preview-continue").addEventListener("click", () => goStep("launch"));

async function setAuthorization(allow) {
  try {
    let path = state.packetPath;
    // Never rewrite packets outside the UI workspace (e.g. repo examples):
    // duplicate them into ui/data first, then authorize the copy.
    if (allow && path && !path.startsWith("ui/data/packets/")) {
      const loaded = await apiGet(`/api/packet?path=${encodeURIComponent(path)}`);
      const saved = await apiPost("/api/packet/save", { packet: loaded.packet, name: (loaded.packet.job_id || "copy") + "-workspace" });
      state.packetPath = saved.path;
      path = saved.path;
    }
    await apiPost("/api/packet/authorize", { path, allow });
    await runDryrun(); // re-validate the exact bytes that would execute
  } catch (err) {
    $("#dryrun-verdict").innerHTML = `<div class="banner banner-error">${esc(err.message)}</div>`;
  }
}

async function runEnginePlan() {
  if (!state.packetPath) return;
  const button = $("#btn-engineplan");
  button.disabled = true;
  try {
    const result = await apiPost("/api/engineplan", { path: state.packetPath });
    openDrawer("Full engine plan — free, plan-only (no --run)",
      `<pre class="code-block tall">$ ${esc(result.command)}\n\n${esc(result.stdout || "")}${result.stderr ? "\n--- stderr ---\n" + esc(result.stderr) : ""}</pre>`);
  } catch (err) {
    openDrawer("Full engine plan", `<div class="banner banner-error">${esc(err.message)}</div>`);
  } finally {
    button.disabled = false;
  }
}

/* ------------------------------------------------------------------ */
/* Step 4 · Launch                                                     */
/* ------------------------------------------------------------------ */
async function updateLaunchPanel() {
  const liveBtn = $("#btn-live");
  const reason = $("#live-blocked-reason");
  const path = state.packetPath;
  if (!path) {
    liveBtn.disabled = true;
    reason.textContent = "No saved job yet — finish steps 1–3 first.";
    return;
  }
  let fresh = { fresh: false, reason: "unknown" };
  try { fresh = await apiGet(`/api/dryrun/state?path=${encodeURIComponent(path)}`); }
  catch (err) { fresh = { fresh: false, reason: err.message }; }
  const allow = state.lastDryrun && state.lastDryrun.structured && state.lastDryrun.structured.allow_live_run;
  liveBtn.disabled = !(fresh.fresh && allow);
  reason.textContent = liveBtn.disabled
    ? (!fresh.fresh ? `Blocked: ${fresh.reason}.` : "Blocked: spend not authorized — gate 1 on the Preview step.")
    : "All gates green. The typed confirmation is the final gate.";
  renderRailGates(fresh.fresh, !!allow);
}

/* The typed-SPEND modal, as a promise: resolves with the typed phrase or null
 * on cancel. Shared by the admin launch and simple-mode generation - every
 * paid action funnels through this one gate UI. */
let spendResolver = null;

function askSpend({ title, summaryHtml, detailHtml }) {
  return new Promise((resolve) => {
    spendResolver = resolve;
    $("#confirm-title").textContent = title || "Run live — this spends money";
    $("#confirm-summary").innerHTML = summaryHtml || "";
    $("#confirm-detail").innerHTML = detailHtml || "";
    $("#confirm-input").value = "";
    $("#btn-confirm-live").disabled = true;
    $("#confirm-modal").classList.remove("hidden");
    if (window.NeonFluid) window.NeonFluid.setCalm(true);
    $("#confirm-input").focus();
  });
}

function settleSpend(value) {
  $("#confirm-modal").classList.add("hidden");
  if (window.NeonFluid) window.NeonFluid.setCalm(false);
  if (spendResolver) { const r = spendResolver; spendResolver = null; r(value); }
}
function closeConfirm() { settleSpend(null); }

$("#confirm-input").addEventListener("input", () => {
  $("#btn-confirm-live").disabled = $("#confirm-input").value !== "SPEND";
});
$("#btn-confirm-cancel").addEventListener("click", () => settleSpend(null));
$("#btn-confirm-live").addEventListener("click", () => {
  const btn = $("#btn-confirm-live");
  if (btn.disabled) return;
  btn.disabled = true; // a double-click must never emit two confirms
  settleSpend($("#confirm-input").value);
});

$("#btn-live").addEventListener("click", async () => {
  const s = (state.lastDryrun && state.lastDryrun.structured) || {};
  const phrase = await askSpend({
    title: "Run live — this spends money",
    summaryHtml: `
      <table class="kv">
        <tr><td>job</td><td>${esc(s.job_id || "?")}</td></tr>
        <tr><td>route</td><td>${esc(s.content_path)} + ${esc(s.video_source)}</td></tr>
        ${s.video_source === "generate" ? `<tr><td>spend cap</td><td>max_scenes = ${esc(s.max_scenes ?? "UNCAPPED")}</td></tr>` : ""}
        <tr><td>packet</td><td>${esc(state.packetPath)}</td></tr>
      </table>`,
    detailHtml: `This executes <code class="inline-code">run_from_packet.py --packet ${esc(state.packetPath)} --run</code>. Paid API calls will be made.`,
  });
  if (!phrase) return;
  const errBox = $("#live-error");
  errBox.classList.add("hidden");
  try {
    const result = await apiPost("/api/run/live", { path: state.packetPath, confirm: phrase });
    state.selectedRunId = result.ui_run_id;
    pollRun();
  } catch (err) {
    errBox.textContent = "Live run refused: " + err.message;
    errBox.classList.remove("hidden");
  }
});

async function pollRun() {
  clearTimeout(state.pollTimer);
  if (!state.selectedRunId) return;
  let run;
  try {
    run = await apiGet(`/api/runs/${encodeURIComponent(state.selectedRunId)}`);
  } catch (err) {
    $("#run-detail").innerHTML = `<div class="banner banner-error">${esc(err.message)}<br><span class="hint">Runs from previous server sessions only have ledger summaries — see ui/data/runs.json and the run directory on disk.</span></div>`;
    return;
  }
  renderRunDetail(run);
  state.liveStages = run.stages || null;
  renderRail();
  if (run.status === "running") state.pollTimer = setTimeout(pollRun, 2500);
}

function renderRunDetail(run) {
  const statusBanner = {
    running: `<div class="banner banner-info">RUNNING — live engine output below, updating every few seconds.</div>`,
    succeeded: `<div class="banner banner-ok">SUCCEEDED — engine exited 0.</div>`,
    failed: `<div class="banner banner-error">FAILED — engine exited ${esc(run.returncode)}. Failure details shown verbatim below.</div>`,
    refused: `<div class="banner banner-warn">REFUSED — the adapter declined to run live (spend gate). Nothing was spent.</div>`,
  }[run.status] || "";

  const failure = run.manifest_failure
    ? `<p class="mini-label">Failure report (from manifest)</p><pre class="code-block">${esc(JSON.stringify(run.manifest_failure, null, 2))}</pre>` : "";
  const stderr = run.stderr && run.stderr.trim()
    ? `<p class="mini-label">stderr</p><pre class="code-block">${esc(run.stderr)}</pre>` : "";
  const musicWarn = run.music_warning
    ? `<div class="banner banner-warn"><strong>Music review needed:</strong> ${esc(run.music_warning)}</div>` : "";

  const reports = (run.reports || []).map((r) => r.exists
    ? `<button class="btn btn-small" data-view-report="${esc(r.path)}" data-report-label="${esc(r.label)}">${esc(r.label)}</button>`
    : `<button class="btn btn-small" disabled title="not produced">${esc(r.label)} (absent)</button>`).join("");

  const video = run.final_video && run.final_video.exists
    ? `<p class="mini-label">Final video — ${esc(run.final_video.path)}</p>
       <video class="preview" controls preload="metadata" src="/api/media?path=${encodeURIComponent(run.final_video.path)}"></video>`
    : (run.status === "succeeded" ? `<div class="banner banner-warn">Run succeeded but final video not found where expected.</div>` : "");

  $("#run-detail").innerHTML = `
    ${statusBanner}
    ${musicWarn}
    <table class="kv">
      <tr><td>UI run</td><td>${esc(run.ui_run_id)}</td></tr>
      <tr><td>engine run</td><td>${esc(run.engine_run_id || "(pending)")}</td></tr>
      <tr><td>run dir</td><td>${esc(run.run_dir || "(pending)")}</td></tr>
      <tr><td>manifest</td><td>${esc(run.manifest_path || "(written at end)")}</td></tr>
      <tr><td>started → finished</td><td>${esc(run.started_at || "?")} → ${esc(run.finished_at || "…")}</td></tr>
    </table>
    <div class="report-links">${reports}</div>
    ${video}
    ${failure}
    ${stderr}
    <div class="actions">
      <button class="btn btn-small" id="btn-engine-log">Engine output</button>
    </div>`;
  const logBtn = $("#btn-engine-log");
  if (logBtn) logBtn.addEventListener("click", () =>
    openDrawer(`Engine output — ${run.ui_run_id}`,
      `<pre class="code-block tall">${esc(run.stdout_tail || "(no output)")}</pre>`));
}

document.addEventListener("click", async (e) => {
  const view = e.target.closest("[data-view-report]");
  if (!view) return;
  try {
    const res = await fetch(`/api/media?path=${encodeURIComponent(view.dataset.viewReport)}`);
    const text = await res.text();
    let body;
    try { body = JSON.stringify(JSON.parse(text), null, 2); } catch { body = text; }
    openDrawer(`${view.dataset.reportLabel} — ${view.dataset.viewReport}`,
      `<pre class="code-block tall">${esc(body)}</pre>`);
  } catch (err) { alert(err.message); }
});

/* ------------------------------------------------------------------ */
/* Status rail                                                         */
/* ------------------------------------------------------------------ */
const STAGE_NAMES = ["video", "extract", "sts", "music", "assemble"];

function renderRail() {
  renderRailJob();
  const dryOk = !!(state.lastDryrun && state.lastDryrun.ok);
  const allow = !!(state.lastDryrun && state.lastDryrun.structured && state.lastDryrun.structured.allow_live_run);
  renderRailGates(dryOk, allow);
  renderRailPipeline();
}

function renderRailJob() {
  const s = (state.lastDryrun && state.lastDryrun.structured) || null;
  const v = formValues();
  const rows = [
    ["job", (s && s.job_id) || v.job_id || "(unnamed)"],
    ["route", `${state.choices.content_path} + ${state.choices.video_source}`],
    state.choices.video_source === "generate" ? ["spend cap", (s && s.max_scenes != null ? s.max_scenes : v.max_scenes || "1") + " scene(s)"] : null,
    ["packet", state.packetPath || "(not saved yet)"],
  ].filter(Boolean);
  $("#rail-job-body").innerHTML = `<table class="kv">${rows.map(([k, val]) =>
    `<tr><td>${esc(k)}</td><td>${esc(val)}</td></tr>`).join("")}</table>`;
}

function renderRailGates(dryFresh, allow) {
  $("#rail-gates-body").innerHTML = `
    <div class="gate-row"><span class="gate-dot ${dryFresh ? "pass" : "fail"}"></span>Dry-run passed (exact bytes)</div>
    <div class="gate-row"><span class="gate-dot ${allow ? "pass" : "fail"}"></span>Spend authorized in packet</div>
    <div class="gate-row"><span class="gate-dot"></span>Typed SPEND confirmation at launch</div>`;
}

function renderRailPipeline() {
  let nodes;
  if (state.liveStages) {
    nodes = state.liveStages.map((st) => ({
      name: st.stage,
      cls: { running: "p-running", ok: "p-ok", failed: "p-failed", skipped: "p-skipped", not_run: "p-skipped", pending: "" }[st.status] || "",
      note: st.detail || st.status,
    }));
  } else if (state.lastDryrun && state.lastDryrun.structured && state.lastDryrun.structured.valid) {
    nodes = state.lastDryrun.structured.stages.map((st) => ({
      name: st.stage,
      cls: st.planned === "active" ? "p-active" : "p-skipped",
      note: st.note,
    }));
  } else {
    nodes = STAGE_NAMES.map((n) => ({ name: n, cls: "", note: "planned after dry-run" }));
  }
  $("#rail-pipeline-body").innerHTML = `<div class="pipe">${nodes.map((n) => `
    <div class="pipe-node ${n.cls}">
      <span class="pipe-dot"></span>
      <span class="pipe-text"><span class="pipe-name">${esc(n.name)}</span><span class="pipe-note">${esc(n.note)}</span></span>
    </div>`).join("")}</div>`;
}

/* ------------------------------------------------------------------ */
/* Drawers: generic, packets, history, packet JSON                      */
/* ------------------------------------------------------------------ */
function openDrawer(title, html) {
  $("#drawer-title").textContent = title;
  $("#drawer-body").innerHTML = html;
  $("#drawer").classList.remove("hidden");
}
function closeDrawer() { $("#drawer").classList.add("hidden"); }
$("#btn-drawer-close").addEventListener("click", closeDrawer);
$("#drawer").addEventListener("click", (e) => { if (e.target.id === "drawer") closeDrawer(); });
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    closeDrawer();
    closeConfirm();
    closeCostConfirm();
    $("#browse-modal").classList.add("hidden");
  }
});

$("#btn-open-packets").addEventListener("click", async () => {
  try {
    const data = await apiGet("/api/packets");
    const render = (items) => items.map((p) => `
      <div class="list-item">
        <div>
          <div class="item-main">${esc(p.path)}</div>
          <div class="item-sub">${esc(p.job_id || "(no job_id)")} · ${esc(p.content_path || "?")} + ${esc(p.video_source || "?")}${p.allow_live_run ? ' · <span class="paid-text">SPEND AUTHORIZED</span>' : ""}</div>
        </div>
        <div class="item-actions">
          <button class="btn btn-small" data-preview-packet="${esc(p.path)}">Preview</button>
        </div>
      </div>`).join("");
    openDrawer("Packets", `
      <p class="mini-label">Saved jobs (ui/data/packets)</p>
      <div class="packet-list">${render(data.saved) || '<p class="hint">None yet.</p>'}</div>
      <p class="mini-label">Repo examples</p>
      <div class="packet-list">${render(data.examples) || '<p class="hint">None found.</p>'}</div>
      <p class="micro">Preview dry-runs the packet as-is (free). Authorizing spend on a repo example automatically duplicates it into the workspace first.</p>`);
  } catch (err) {
    openDrawer("Packets", `<div class="banner banner-error">${esc(err.message)}</div>`);
  }
});

document.addEventListener("click", async (e) => {
  const previewBtn = e.target.closest("[data-preview-packet]");
  if (!previewBtn) return;
  closeDrawer();
  state.packetPath = previewBtn.dataset.previewPacket;
  state.packet = null;
  state.lastDryrun = null;
  state.liveStages = null;
  try {
    const loaded = await apiGet(`/api/packet?path=${encodeURIComponent(state.packetPath)}`);
    state.packet = loaded.packet;
    state.choices.content_path = loaded.packet.content_path || state.choices.content_path;
    state.choices.video_source = loaded.packet.video_source || state.choices.video_source;
    syncChoiceButtons();
    fillFormFromPacket(loaded.packet);
  } catch { /* dry-run will surface problems */ }
  updateStepper();
  goStep("preview");
  await runDryrun();
});

function syncChoiceButtons() {
  $$(".choice").forEach((c) =>
    c.classList.toggle("selected", state.choices[c.dataset.field] === c.dataset.value));
  updateConditionalForm();
}

function fillFormFromPacket(packet) {
  const set = (name, value) => { if (formEl(name)) formEl(name).value = value ?? ""; };
  set("job_id", packet.job_id);
  set("video_path", packet.video_path);
  set("scenes_path", packet.scenes_path);
  set("presenter_reference_image_path", packet.presenter_reference_image_path);
  set("storyboard_path", packet.storyboard_path);
  set("model", packet.model || "veo-3.1-fast-generate-preview");
  set("resolution", packet.resolution || "720p");
  set("max_scenes", packet.max_scenes ?? 1);
  set("prepared_voice_path", (packet.voice || {}).prepared_voice_path);
  set("output_dir", (packet.output_settings || {}).output_dir || "runs");
  set("client", (packet.metadata || {}).client);
  set("campaign", (packet.metadata || {}).campaign);
  set("notes", (packet.metadata || {}).notes);
  set("spend_notes", (packet.spend_controls || {}).notes);
  // The preceding syncChoiceButtons() already set block visibility; now that the
  // reference path is filled, lock model/resolution to the forced values if set.
  reflectPresenterReferenceOverride();
}

$("#btn-history").addEventListener("click", async () => {
  try {
    const data = await apiGet("/api/runs");
    const items = data.runs.map((r) => `
      <div class="list-item">
        <div>
          <div class="item-main">${esc(r.ui_run_id)}${r.engine_run_id ? " · " + esc(r.engine_run_id) : ""}</div>
          <div class="item-sub">${esc(r.job_id || "?")} · ${esc(r.status)} · ${esc(r.started_at || "?")}</div>
        </div>
        <div class="item-actions"><button class="btn btn-small" data-show-run="${esc(r.ui_run_id)}">Details</button></div>
      </div>`).join("");
    openDrawer("Run history", `<div class="packet-list">${items || '<p class="hint">No runs yet.</p>'}</div>`);
  } catch (err) {
    openDrawer("Run history", `<div class="banner banner-error">${esc(err.message)}</div>`);
  }
});

document.addEventListener("click", (e) => {
  const showBtn = e.target.closest("[data-show-run]");
  if (showBtn) {
    closeDrawer();
    state.selectedRunId = showBtn.dataset.showRun;
    goStep("launch");
    pollRun();
  }
});

$("#btn-open-json").addEventListener("click", async () => {
  let text = "";
  if (state.packet) text = JSON.stringify(state.packet, null, 2);
  else {
    try {
      const built = await apiPost("/api/packet/build", { form: formValues() });
      text = JSON.stringify(built.packet, null, 2);
    } catch { text = ""; }
  }
  openDrawer("Packet JSON — edit or paste", `
    <p class="hint">The packet is what the engine consumes. Paste an externally-authored packet here, or hand-edit the built one. <code>start_stage</code> is derived by the adapter — don't add it.</p>
    <textarea id="json-editor" rows="22" spellcheck="false">${esc(text)}</textarea>
    <div id="json-error" class="banner banner-error hidden"></div>
    <div class="actions">
      <button class="btn btn-free" id="btn-json-save">Save this JSON &amp; preview <span class="tag tag-free">FREE</span></button>
    </div>`);
  $("#btn-json-save").addEventListener("click", async () => {
    const errBox = $("#json-error");
    errBox.classList.add("hidden");
    let packet;
    try { packet = JSON.parse($("#json-editor").value); }
    catch (err) { errBox.textContent = "Not valid JSON: " + err.message; errBox.classList.remove("hidden"); return; }
    try {
      state.choices.content_path = packet.content_path || state.choices.content_path;
      state.choices.video_source = packet.video_source || state.choices.video_source;
      syncChoiceButtons();
      fillFormFromPacket(packet);
      closeDrawer();
      await savePacketAndDryrun(packet);
    } catch (err) {
      errBox.textContent = err.message;
      errBox.classList.remove("hidden");
    }
  });
});

/* ------------------------------------------------------------------ */
/* File browser                                                        */
/* ------------------------------------------------------------------ */
let browseTarget = null;

document.addEventListener("click", (e) => {
  const browseBtn = e.target.closest(".browse-btn");
  if (!browseBtn) return;
  browseTarget = browseBtn.dataset.target;
  openBrowser("");
});

async function openBrowser(path) {
  try {
    const data = await apiGet(`/api/fs?path=${encodeURIComponent(path)}`);
    $("#browse-current").textContent = "/" + (data.path || "");
    const up = data.parent !== null && data.parent !== undefined
      ? `<button class="browse-entry" data-browse-dir="${esc(data.parent)}">⬑ ..</button>` : "";
    $("#browse-entries").innerHTML = up + data.entries.map((entry) => entry.type === "dir"
      ? `<button class="browse-entry" data-browse-dir="${esc(entry.path)}">📁 ${esc(entry.name)}/</button>`
      : `<button class="browse-entry" data-browse-file="${esc(entry.path)}" data-browse-size="${esc(entry.size_bytes)}"><span>${esc(entry.name)}</span><span class="e-size">${(entry.size_bytes / 1024).toFixed(0)} KB</span></button>`
    ).join("");
    $("#browse-modal").classList.remove("hidden");
  } catch (err) { alert(err.message); }
}

document.addEventListener("click", (e) => {
  const dir = e.target.closest("[data-browse-dir]");
  if (dir) { openBrowser(dir.dataset.browseDir); return; }
  const file = e.target.closest("[data-browse-file]");
  if (file) {
    const path = file.dataset.browseFile;
    if (browseTarget === "existing-voice-path-direct") $("#existing-voice-path").value = path;
    else if (browseTarget === "s-seed-direct") {
      invalidateSimplePreview("Seed frame changed — build the job again before generating video.");
      setSimpleImage("seed", {
        path,
        name: path.split("/").pop() || path,
        size: Number(file.dataset.browseSize) || null,
        previewUrl: `/api/media?path=${encodeURIComponent(path)}`,
      });
    }
    else if (browseTarget && formEl(browseTarget)) {
      const field = formEl(browseTarget);
      const changed = field.value !== path;
      field.value = path;
      // Programmatic assignments do not emit an input event. Invalidate the
      // saved packet explicitly so launch cannot spend against stale bytes
      // while the form visibly shows a newly selected reference or source.
      if (changed) invalidateDryrun();
      if (browseTarget === "scenes_path") inspectScenes();
      if (browseTarget === "presenter_reference_image_path") reflectPresenterReferenceOverride();
      renderRailJob();
    }
    $("#browse-modal").classList.add("hidden");
  }
});
$("#btn-browse-cancel").addEventListener("click", () => $("#browse-modal").classList.add("hidden"));

/* ================================================================== */
/* SIMPLE MODE: document -> draft video -> high-quality video          */
/* ================================================================== */
const simple = {
  job: null,
  uploadedPath: null,
  inputVersion: 0,
  aspectRatio: "9:16",
  contentPath: "silent_brand",
  images: { reference: null, seed: null },
  voice: { dir: "voice_auditions", playedSamples: new Set(), samples: [], preparedVoicePath: null, pickedLabel: null },
  pollTimers: { draft: null, hq: null },
  running: false,
  // Flat circular auto-rotating reel state. The carousel unit is ONE image
  // (a single scene-moment), not a scene: ALL storyboard images are flattened
  // into one ordered list in scene-then-moment order, so stepping moves image
  // by image in true order and always has a neighbour on each side (it wraps).
  cover: {
    index: 0,             // focused image (0-based, into `frames`)
    frames: [],           // flat ordered list: [{sceneIndex, momentIndex, momentCount, path, prompt, summary}]
    sceneCount: 0,        // number of scenes (for the "no preview yet" empty shell)
    summaries: [],        // friendly per-scene summaries (1 per scene)
    prompts: [],          // raw per-scene technical prompts (behind an affordance)
    negativeApplied: [],  // display-only negative-library summary (1 per scene)
    storyboard: {},       // sceneIndex(1-based) -> [{path, prompt, moment_index}] moment images
    autoTimer: null,      // auto-advance interval (advances one image / 2s)
    resumeTimer: null,    // idle-resume timeout (re-arm auto-rotate 5s after manual nav)
    paused: false,        // manual interaction pauses auto-rotate
    locked: false,        // explicit user lock holds the focused frame indefinitely
    drag: null,           // active pointer-drag bookkeeping
    imagesPerScene: 3,    // moments per scene for a storyboard render (user control)
  },
};

const SIMPLE_ASPECT_RATIOS = new Set(["9:16", "16:9"]);
const SIMPLE_CONTENT_PATHS = new Set(["silent_brand", "presenter"]);

function setSimpleAspectRatio(aspectRatio) {
  if (!SIMPLE_ASPECT_RATIOS.has(aspectRatio)) return;
  simple.aspectRatio = aspectRatio;
  $$(".aspect-btn[data-aspect]").forEach((btn) => {
    const selected = btn.dataset.aspect === aspectRatio;
    btn.classList.toggle("selected", selected);
    btn.setAttribute("aria-pressed", selected ? "true" : "false");
  });
}

function setSimpleContentPath(contentPath) {
  if (!SIMPLE_CONTENT_PATHS.has(contentPath)) return;
  simple.contentPath = contentPath;
  $$(".content-path-btn").forEach((btn) => {
    const selected = btn.dataset.contentPath === contentPath;
    btn.classList.toggle("selected", selected);
    btn.setAttribute("aria-pressed", selected ? "true" : "false");
  });
  const block = $("#s-presenter-block");
  if (contentPath === "presenter") {
    if (block) block.classList.remove("hidden");
    if (typeof window.loadSimpleAuditions === "function") window.loadSimpleAuditions();
  } else {
    if (block) block.classList.add("hidden");
  }
}

async function loadSimpleAuditions() {
  const status = $("#s-voice-status");
  const selected = $("#s-voice-selected");
  simple.voice.playedSamples = new Set();
  simple.voice.samples = [];
  simple.voice.preparedVoicePath = null;
  simple.voice.pickedLabel = null;
  if (selected) {
    selected.classList.add("hidden");
    selected.textContent = "";
  }
  if (status) status.textContent = "Loading presenter voices...";
  try {
    const data = await apiGet(`/api/auditions?dir=${encodeURIComponent(simple.voice.dir)}`);
    const samples = Array.isArray(data.samples) ? data.samples : [];
    simple.voice.samples = samples;
    renderSimpleVoiceList(samples);
    if (status) status.textContent = samples.length ? "" : "No presenter voices are available yet.";
  } catch (err) {
    simple.voice.samples = [];
    renderSimpleVoiceList([]);
    if (status) status.textContent = "No presenter voices are available yet.";
  }
}

function renderSimpleVoiceList(samples) {
  const list = $("#s-voice-list");
  const status = $("#s-voice-status");
  if (!list) return;
  if (!samples.length) {
    list.innerHTML = "";
    if (status) status.textContent = "No presenter voices are available yet.";
    return;
  }
  if (status) status.textContent = "";
  list.innerHTML = samples.map((s, idx) => {
    const label = s.label || `Voice ${idx + 1}`;
    return `
      <div class="s-voice-card">
        <div class="s-voice-copy">
          <strong>${esc(label)}</strong>
          ${s.notes ? `<span class="micro">${esc(s.notes)}</span>` : ""}
        </div>
        <audio controls preload="none" src="/api/media?path=${encodeURIComponent(s.path)}" data-simple-sample-audio="${idx}"></audio>
        <button type="button" class="btn btn-small btn-free" data-simple-pick-voice="${idx}" disabled title="Listen to this sample first">Use this voice</button>
      </div>`;
  }).join("");
  list.querySelectorAll("[data-simple-sample-audio]").forEach((audio) => {
    audio.addEventListener("play", () => {
      const idx = audio.dataset.simpleSampleAudio;
      simple.voice.playedSamples.add(idx);
      const pickBtn = list.querySelector(`[data-simple-pick-voice="${CSS.escape(idx)}"]`);
      if (pickBtn) {
        pickBtn.disabled = false;
        pickBtn.title = "";
      }
    });
  });
}

const sVoiceList = $("#s-voice-list");
if (sVoiceList) {
  sVoiceList.addEventListener("click", async (e) => {
    const pick = e.target.closest("[data-simple-pick-voice]");
    if (!pick) return;
    const idx = pick.dataset.simplePickVoice;
    if (!simple.voice.playedSamples.has(idx)) return;
    const sample = simple.voice.samples[Number(idx)];
    if (!sample) return;
    const status = $("#s-voice-status");
    const selected = $("#s-voice-selected");
    if (status) status.textContent = "";
    try {
      const result = await apiPost("/api/voice/select", {
        sample_path: sample.path,
        workspace_voice_id: sample.workspace_voice_id,
        label: sample.label,
        listened: true,
      });
      simple.voice.preparedVoicePath = result.prepared_voice_path;
      simple.voice.pickedLabel = sample.label || `Voice ${Number(idx) + 1}`;
      if (selected) {
        selected.innerHTML = `Selected voice: ${esc(simple.voice.pickedLabel)}`;
        selected.classList.remove("hidden");
      }
    } catch (err) {
      if (status) status.textContent = "That voice could not be selected. Please try another sample.";
    }
  });
}

window.loadSimpleAuditions = loadSimpleAuditions;

function simpleUserMessage(value) {
  return String(value == null ? "" : value)
    .replace(/veo-[a-z0-9._-]+/gi, "the required video setting")
    .replace(/\bVeo\b/gi, "video generation")
    .replace(/\bGemini\b/gi, "AI assistance")
    .replace(/\bElevenLabs\b/gi, "voice processing")
    .replace(/\bLyria\b/gi, "music generation")
    .replace(/\bpresenter_reference_image_path\b/g, "reference image")
    .replace(/\breference_type\b/g, "reference setting")
    .replace(/\ballow_adult\b/g, "adult-person setting")
    .replace(/\bSDK\b/g, "video system")
    .replace(/\bmodel\b/gi, "quality setting");
}
// Phase-A render tiers (video + image) and the runaway cap. Loaded once from
// /api/simple/tiers; pure data the UI renders into the tier pickers.
let simpleTiers = null;
let appSettings = null;

async function loadAppSettings() {
  try { appSettings = await apiGet("/api/settings"); } catch { appSettings = null; }
}

async function loadSimpleTiers() {
  try { simpleTiers = await apiGet("/api/simple/tiers"); } catch { simpleTiers = null; }
  renderVideoTierPicker();
}

/* The video render tier the operator chose for the final generation. Defaults
 * to the first (cheapest) video tier once tiers load; until then "standard"
 * (the documented cheapest key) so the UI is never in an undefined state. */
let selectedVideoTier = "standard";

function videoTierList() { return (simpleTiers && simpleTiers.video) || []; }
function maxStoryboardImages() {
  return (simpleTiers && Number(simpleTiers.max_storyboard_images)) || 40;
}
function findVideoTier(key) { return videoTierList().find((t) => t.key === key) || null; }

/* Render the final-video quality-tier picker (Standard / Quality / Ultra 4K).
 * Picking only changes which tier the deliberate Generate click will use — it
 * spends nothing and mints no token. The cost dialog (on the Generate click)
 * shows that tier's estimate and mints a tier-bound token. */
function renderVideoTierPicker() {
  const row = $("#s-video-tiers");
  if (!row) return;
  const tiers = videoTierList();
  if (!tiers.length) { row.innerHTML = `<p class="hint">Tier data unavailable.</p>`; return; }
  // Default the selection to the cheapest tier the first time tiers load.
  if (!findVideoTier(selectedVideoTier)) selectedVideoTier = tiers[0].key;
  row.innerHTML = tiers.map((t) => {
    const selected = t.key === selectedVideoTier;
    const rate = Number(t.per_second_rate);
    const rateLabel = Number.isFinite(rate) ? `$${rate.toFixed(2)}/sec` : "";
    return `
      <button type="button" class="tier-card video-tier tier-card-paid ${selected ? "selected" : ""}"
        data-video-tier="${esc(t.key)}"
        title="${esc(t.label)} — ${esc(t.resolution)} · ${esc(rateLabel)} (audio included). Confirmed before any spend.">
        <span class="tier-name">${esc(t.label)}</span>
        <span class="tier-meta">${esc(t.resolution)}</span>
        <span class="tier-price">${esc(rateLabel)} <span class="tag tag-paid">PAID</span></span>
      </button>`;
  }).join("");
}

// Video-tier selection (delegated, survives re-renders). Selection alone never
// spends; the deliberate Generate click + cost dialog do.
document.addEventListener("click", (e) => {
  const card = e.target.closest("[data-video-tier]");
  if (!card) return;
  selectedVideoTier = card.dataset.videoTier;
  const row = $("#s-video-tiers");
  if (row) row.querySelectorAll(".video-tier").forEach((c) =>
    c.classList.toggle("selected", c === card));
});

document.addEventListener("click", (e) => {
  const btn = e.target.closest(".aspect-btn[data-aspect]");
  if (!btn) return;
  const aspectRatio = btn.dataset.aspect;
  if (!SIMPLE_ASPECT_RATIOS.has(aspectRatio)) return;
  if (simple.aspectRatio !== aspectRatio) {
    invalidateSimplePreview("Aspect ratio changed — build the job again before generating video.");
  }
  setSimpleAspectRatio(aspectRatio);
});

document.addEventListener("click", (e) => {
  const btn = e.target.closest(".content-path-btn[data-content-path]");
  if (!btn) return;
  const contentPath = btn.dataset.contentPath;
  if (!SIMPLE_CONTENT_PATHS.has(contentPath)) return;
  if (simple.contentPath !== contentPath) {
    invalidateSimplePreview("Video type changed — build the job again before generating video.");
  }
  setSimpleContentPath(contentPath);
});

/* ---- optional image inputs: one reference OR one seed frame ---- */
const SIMPLE_IMAGE_MAX_BYTES = 10 * 1024 * 1024;
const SIMPLE_IMAGE_EXTENSIONS = new Set(["png", "jpg", "jpeg", "webp"]);

function simpleImageEls(kind) {
  return {
    zone: $(`#s-${kind}-zone`),
    input: $(`#s-${kind}-file`),
    prompt: $(`#s-${kind}-prompt`),
    selection: $(`#s-${kind}-selection`),
    thumb: $(`#s-${kind}-thumb`),
    name: $(`#s-${kind}-name`),
    path: $(`#s-${kind}-path`),
    size: $(`#s-${kind}-size`),
    clear: $(`#s-${kind}-clear`),
    error: $(`#s-${kind}-error`),
    disabled: $(`#s-${kind}-disabled`),
  };
}

function formatSimpleImageSize(bytes) {
  if (!Number.isFinite(Number(bytes)) || Number(bytes) <= 0) return "Size unavailable";
  const value = Number(bytes);
  if (value < 1024) return `${value} bytes`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(2)} MB`;
}

function clearSimpleImageError(kind) {
  const error = simpleImageEls(kind).error;
  error.textContent = "";
  error.classList.add("hidden");
}

function showSimpleImageError(kind, message) {
  const error = simpleImageEls(kind).error;
  error.textContent = message;
  error.classList.remove("hidden");
}

function invalidateSimplePreview(message) {
  simple.inputVersion += 1;
  simple.job = null;
  stopSimplePolls();
  stopCoverFlow();
  setSimpleRunning(false);
  if (!$("#cost-confirm-modal").classList.contains("hidden")) closeCostConfirm();
  ["s-review", "s-draft", "s-final"].forEach((id) => $(`#${id}`).classList.add("hidden"));
  $("#s-review-body").innerHTML = "";
  $("#s-draft-status").innerHTML = "";
  $("#s-draft-video").innerHTML = "";
  $("#s-hq-status").innerHTML = "";
  $("#s-hq-video").innerHTML = "";
  $("#s-gen-draft").disabled = true;
  $("#s-gen-hq").disabled = true;
  $("#s-gen-hq").title = "Build and generate a draft first";
  if (message) $("#s-extract-note").textContent = message;
}

function releaseSimpleImage(selection) {
  if (selection && selection.objectUrl) URL.revokeObjectURL(selection.objectUrl);
}

function renderSimpleImages() {
  const referenceActive = !!(simple.images.reference && simple.images.reference.path);
  const seedActive = !!(simple.images.seed && simple.images.seed.path);
  for (const kind of ["reference", "seed"]) {
    const els = simpleImageEls(kind);
    const selection = simple.images[kind];
    const disabled = kind === "reference" ? seedActive : referenceActive;
    els.zone.classList.toggle("is-disabled", disabled);
    els.zone.setAttribute("aria-disabled", disabled ? "true" : "false");
    els.zone.tabIndex = disabled ? -1 : 0;
    els.input.disabled = disabled;
    els.prompt.classList.toggle("hidden", !!selection || disabled);
    els.selection.classList.toggle("hidden", !selection);
    els.disabled.classList.toggle("hidden", !disabled);
    if (selection) {
      els.thumb.src = selection.previewUrl || `/api/media?path=${encodeURIComponent(selection.path)}`;
      els.name.textContent = selection.name || selection.path.split("/").pop() || "Image";
      els.path.textContent = selection.path;
      els.size.textContent = formatSimpleImageSize(selection.size);
    } else {
      els.thumb.removeAttribute("src");
      els.name.textContent = "";
      els.path.textContent = "";
      els.size.textContent = "";
    }
  }
  const seedDisabled = referenceActive;
  $("#s-seed").disabled = seedDisabled;
  $("#s-seed-browse").disabled = seedDisabled;
  $("#s-seed-advanced").inert = seedDisabled;
  if (seedDisabled) $("#s-seed-advanced").open = false;
}

function setSimpleImage(kind, selection) {
  const other = kind === "reference" ? "seed" : "reference";
  releaseSimpleImage(simple.images[kind]);
  releaseSimpleImage(simple.images[other]);
  simple.images[kind] = selection;
  simple.images[other] = null;
  clearSimpleImageError(kind);
  clearSimpleImageError(other);
  if (kind === "reference") $("#s-seed").value = "";
  else $("#s-seed").value = selection.path;
  renderSimpleImages();
}

function clearSimpleImage(kind, { invalidate = true } = {}) {
  if (invalidate) invalidateSimplePreview("Image cleared — build the job again before generating video.");
  releaseSimpleImage(simple.images[kind]);
  simple.images[kind] = null;
  if (kind === "seed") $("#s-seed").value = "";
  clearSimpleImageError(kind);
  renderSimpleImages();
}

function simpleImageIsDisabled(kind) {
  return kind === "reference" ? !!simple.images.seed : !!simple.images.reference;
}

function openSimpleImagePicker(kind) {
  if (simpleImageIsDisabled(kind)) return;
  invalidateSimplePreview("Image selection changed — build the job again before generating video.");
  clearSimpleImageError(kind);
  simpleImageEls(kind).input.click();
}

async function uploadSimpleImage(kind, file) {
  if (!file || simpleImageIsDisabled(kind)) return;
  invalidateSimplePreview("Image changed — build the job again before generating video.");
  clearSimpleImageError(kind);
  const extension = (file.name.split(".").pop() || "").toLowerCase();
  if (!SIMPLE_IMAGE_EXTENSIONS.has(extension)) {
    showSimpleImageError(kind, "Use a PNG, JPG, JPEG or WEBP image.");
    return;
  }
  if (file.size > SIMPLE_IMAGE_MAX_BYTES) {
    showSimpleImageError(kind, "Image is too large. Maximum size is 10 MB.");
    return;
  }
  try {
    const response = await fetch(`/api/upload/image?name=${encodeURIComponent(file.name)}`, {
      method: "POST",
      headers: { "Content-Type": file.type || "application/octet-stream" },
      body: file,
    });
    const data = await response.json().catch(() => null);
    if (!response.ok) throw new Error((data && data.error) || response.statusText);
    const objectUrl = URL.createObjectURL(file);
    setSimpleImage(kind, {
      path: data.path,
      name: file.name,
      size: file.size,
      previewUrl: objectUrl,
      objectUrl,
    });
  } catch (err) {
    showSimpleImageError(kind, `Upload failed: ${simpleUserMessage(err.message)}`);
  }
}

function bindSimpleImageZone(kind) {
  const els = simpleImageEls(kind);
  els.zone.addEventListener("click", (event) => {
    if (simpleImageIsDisabled(kind)) {
      event.preventDefault();
      event.stopPropagation();
      return;
    }
    if (event.target.closest("button, input, summary, details")) return;
    openSimpleImagePicker(kind);
  });
  els.zone.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    if (event.target.closest("input, summary, details")) return;
    event.preventDefault();
    openSimpleImagePicker(kind);
  });
  els.input.addEventListener("change", async (event) => {
    const file = event.target.files[0];
    event.target.value = "";
    if (file) await uploadSimpleImage(kind, file);
  });
  for (const eventName of ["dragenter", "dragover"]) {
    els.zone.addEventListener(eventName, (event) => {
      event.preventDefault();
      if (!simpleImageIsDisabled(kind)) els.zone.classList.add("is-dragover");
    });
  }
  for (const eventName of ["dragleave", "dragend"]) {
    els.zone.addEventListener(eventName, () => els.zone.classList.remove("is-dragover"));
  }
  els.zone.addEventListener("drop", async (event) => {
    event.preventDefault();
    els.zone.classList.remove("is-dragover");
    if (simpleImageIsDisabled(kind)) return;
    const file = event.dataTransfer && event.dataTransfer.files[0];
    if (file) await uploadSimpleImage(kind, file);
  });
  els.clear.addEventListener("click", (event) => {
    event.stopPropagation();
    clearSimpleImage(kind);
  });
}

function restoreSimpleImagesFromJob(job) {
  releaseSimpleImage(simple.images.reference);
  releaseSimpleImage(simple.images.seed);
  simple.images.reference = null;
  simple.images.seed = null;
  $("#s-seed").value = "";
  if (job && job.reference_image_path) {
    simple.images.reference = {
      path: job.reference_image_path,
      name: job.reference_image_path.split("/").pop() || job.reference_image_path,
      size: null,
      previewUrl: `/api/media?path=${encodeURIComponent(job.reference_image_path)}`,
    };
  } else if (job && job.seed_image && !job.seed_is_placeholder) {
    simple.images.seed = {
      path: job.seed_image,
      name: job.seed_image.split("/").pop() || job.seed_image,
      size: null,
      previewUrl: `/api/media?path=${encodeURIComponent(job.seed_image)}`,
    };
    $("#s-seed").value = job.seed_image;
  }
  renderSimpleImages();
}

bindSimpleImageZone("reference");
bindSimpleImageZone("seed");
renderSimpleImages();

/* ---- document input ---- */
$("#s-file").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  $("#s-file-name").textContent = `Uploading ${file.name}…`;
  try {
    const buffer = await file.arrayBuffer();
    const res = await fetch(`/api/simple/upload?name=${encodeURIComponent(file.name)}`, { method: "POST", body: buffer });
    const data = await res.json().catch(() => null);
    if (!res.ok) throw new Error((data && data.error) || res.statusText);
    simple.uploadedPath = data.path;
    $("#s-doc").value = "";
    $("#s-doc").disabled = true;
    $("#s-doc").placeholder = "Using the uploaded document — remove it to paste text instead.";
    $("#s-file-name").innerHTML =
      `Using <code>${esc(file.name)}</code> (${(data.bytes / 1024).toFixed(0)} KB) <button class="btn btn-small" id="s-file-clear" type="button">remove ✕</button>`;
    $("#s-file-clear").addEventListener("click", clearUpload);
  } catch (err) {
    simple.uploadedPath = null;
    $("#s-file-name").textContent = "Upload failed: " + simpleUserMessage(err.message);
  } finally {
    e.target.value = ""; // same file can be re-picked later
  }
});

function clearUpload() {
  simple.uploadedPath = null;
  $("#s-file-name").textContent = "";
  $("#s-doc").disabled = false;
  $("#s-doc").placeholder = "Scene 1: A dark modern desk, warm copper light drifting through a glass prism…\nScene 2: The camera pulls back slowly to reveal…";
}

$("#s-seed-browse").addEventListener("click", () => {
  if (simpleImageIsDisabled("seed")) return;
  invalidateSimplePreview("Seed frame selection changed — build the job again before generating video.");
  browseTarget = "s-seed-direct";
  openBrowser("");
});

$("#s-seed").addEventListener("input", () => {
  invalidateSimplePreview("Seed frame path changed — build the job again before generating video.");
  const path = $("#s-seed").value.trim();
  if (!path) {
    clearSimpleImage("seed", { invalidate: false });
    return;
  }
  setSimpleImage("seed", {
    path,
    name: path.split("/").pop() || path,
    size: null,
    previewUrl: `/api/media?path=${encodeURIComponent(path)}`,
  });
});

/* ---- build ---- */
$("#s-build").addEventListener("click", async () => {
  const errBox = $("#s-build-error");
  errBox.classList.add("hidden");
  const text = $("#s-doc").value.trim();
  if (!text && !simple.uploadedPath) {
    errBox.textContent = "Paste a description or upload a document first.";
    errBox.classList.remove("hidden");
    return;
  }
  const referencePath = simple.images.reference && simple.images.reference.path;
  const seedPath = simple.images.seed && simple.images.seed.path;
  if (referencePath && seedPath) {
    errBox.textContent = "Choose either a reference image or a seed frame, not both.";
    errBox.classList.remove("hidden");
    return;
  }
  if (simple.contentPath === "presenter" && !simple.voice.preparedVoicePath) {
    errBox.textContent = "Pick a presenter voice first (listen to a sample, then choose it).";
    errBox.classList.remove("hidden");
    return;
  }
  invalidateSimplePreview("Building the updated job…");
  const inputVersion = simple.inputVersion;
  const btn = $("#s-build");
  btn.disabled = true;
  $("#s-extract-note").textContent = "Reading the document and building the job…";
  try {
    const payload = {
      job_name: $("#s-name").value.trim() || null,
      aspect_ratio: simple.aspectRatio,
    };
    if (referencePath) payload.reference_image_path = referencePath;
    else if (seedPath) payload.seed_image_path = seedPath;
    if (simple.uploadedPath) payload.source_path = simple.uploadedPath;
    else payload.text = text;
    if (simple.contentPath === "presenter") {
      payload.content_path = "presenter";
      payload.prepared_voice_path = simple.voice.preparedVoicePath;
    }
    const result = await apiPost("/api/simple/author", payload);
    if (inputVersion !== simple.inputVersion) {
      throw new Error("The image changed while the job was being built. Build the job again.");
    }
    simple.job = result.job;
    stopSimplePolls();
    renderSimpleReview(result);
    $("#s-review").classList.remove("hidden");
    $("#s-draft").classList.remove("hidden");
    $("#s-final").classList.remove("hidden");
    $("#s-draft-status").innerHTML = "";
    $("#s-draft-video").innerHTML = "";
    $("#s-hq-status").innerHTML = "";
    $("#s-hq-video").innerHTML = "";
    $("#s-gen-hq").disabled = true;
    $("#s-gen-hq").title = "Generate a draft first";
    $("#s-review").scrollIntoView({ behavior: "smooth", block: "start" });
    loadSimpleJobs();
  } catch (err) {
    errBox.textContent = simpleUserMessage(err.message);
    errBox.classList.remove("hidden");
  } finally {
    btn.disabled = false;
    $("#s-extract-note").textContent = "";
  }
});

function methodLabel(method) {
  return { ai: "AI-assisted extraction", heuristic: "basic parser (no AI)", json: "JSON artifact (used as-is)" }[method] || method;
}

function renderSimpleReview(result) {
  const job = result.job;
  const review = result.review || {};
  const warnings = result.warnings || [];
  const prompts = result.scene_prompts || [];
  // Friendly, NON-technical summaries (one per scene). open_job/author both
  // return these; fall back to the job's own copy, then to "" so the cover-flow
  // never shows the raw technical prompt as the headline text.
  const summaries = result.scene_summaries || job.scene_summaries || [];
  const negativeApplied = result.negative_applied || [];

  // Compact validity + warnings badge. Validity is always visible; warnings are
  // never deleted — they collapse into a small count badge that reveals the full
  // list on hover/click (details/summary), so the review isn't a wall of banners.
  const reviewError = simpleUserMessage(review.error || "unknown");
  const userWarnings = warnings.map(simpleUserMessage);
  const validBadge = review.valid
    ? `<span class="validity-badge ok" title="Job is valid — nothing has been generated or spent yet.">✓ Valid</span>`
    : `<span class="validity-badge bad" title="${esc(reviewError)}">✕ Problem</span>`;
  const errorLine = review.valid ? "" :
    `<div class="banner banner-error">Job has a problem: ${esc(reviewError)}</div>`;
  const warnBadge = userWarnings.length
    ? `<details class="warn-badge"><summary title="Click to read ${userWarnings.length} warning(s)">⚠ ${userWarnings.length} warning${userWarnings.length === 1 ? "" : "s"}</summary>
         <div class="warn-badge-list">${userWarnings.map((w) => `<div class="banner banner-warn">${esc(w)}</div>`).join("")}</div>
       </details>`
    : "";
  const seedNote = job.seed_is_placeholder
    ? `<span class="meta-pill" title="No seed image supplied — a generated gradient placeholder seeds scene 1. A real brand image gives far better results.">auto seed</span>`
    : "";

  const sceneCount = Number(job.scene_count) || prompts.length || 0;
  const reviewAspect = (job.aspect_ratio || simple.aspectRatio) === "16:9" ? "16:9" : "9:16";
  const aspectBadge = `<span class="meta-pill" title="Run-level video orientation">${reviewAspect === "16:9" ? "Landscape 16:9" : "Portrait 9:16"}</span>`;
  const referenceNote = job.reference_image_path
    ? `<span class="meta-pill">Reference mode: the reference image anchors the opening of your video, which runs in the selected orientation. Estimate adjusts automatically.</span>`
    : "";

  // Reset the reel state for this job. Images are PAID to the business, so
  // nothing is fetched until the operator deliberately clicks the FREE
  // "Generate storyboard previews" button. The reel starts empty (one shell
  // card per scene) and is rebuilt into a flat ordered list of frames once the
  // storyboard render returns images.
  stopCoverFlow();
  simple.cover.index = 0;
  simple.cover.frames = [];
  simple.cover.sceneCount = sceneCount;
  simple.cover.summaries = summaries;
  simple.cover.prompts = prompts;
  simple.cover.negativeApplied = negativeApplied;
  simple.cover.storyboard = {};
  const sceneCapMax = Math.max(1, Number(job.scene_count) || 1);
  const sceneCapInitial = Math.min(sceneCapMax, Math.max(1, Number(job.max_scenes) || sceneCapMax));
  const sceneCapControl = sceneCapMax <= 1
    ? `
        <input type="hidden" id="s-cap" value="1">
        <span id="s-cap-readout" class="spend-input">1</span>`
    : `
        <input type="hidden" id="s-cap" value="${esc(sceneCapInitial)}">
        <div class="scene-cap-row" aria-label="Scenes to generate">
          ${Array.from({ length: sceneCapMax }, (_, i) => {
            const n = i + 1;
            return `<button type="button" class="scene-cap-btn${n === sceneCapInitial ? " is-active" : ""}" data-cap="${n}">${n}</button>`;
          }).join("")}
        </div>
        <input id="s-cap-slider" type="range" min="1" max="${esc(sceneCapMax)}" value="${esc(sceneCapInitial)}" step="1" class="scene-cap-slider" aria-label="Scenes to generate">
        <span id="s-cap-readout" class="spend-input" aria-live="polite">${esc(sceneCapInitial)}</span>`;

  $("#s-review-body").innerHTML = `
    <div class="review-head">
      <div class="review-badges">
        ${validBadge}
      </div>
      <div class="field spend-cap-field">
        <label class="spend-label">Scenes to generate (spend cap)</label>
        ${sceneCapControl}
      </div>
    </div>
    ${errorLine}
    ${renderStoryboardControls()}
    ${sceneCount ? renderCoverFlowShell() : `<div class="banner banner-warn">No scene prompts to show.</div>`}
    ${renderCharacterPanel(job, prompts.length || sceneCount)}
    ${renderEditPromptSection(job, prompts.length || sceneCount)}
    <div class="review-foot">
      <div class="review-badges">
        ${warnBadge}
        <span class="meta-pill" title="Built with ${esc(methodLabel(job.method))}">${esc(job.scene_count)} scene${job.scene_count === 1 ? "" : "s"} · ~${6 + 7 * (job.scene_count - 1)}s</span>
        ${aspectBadge}
        ${referenceNote}
        ${seedNote}
      </div>
    </div>
    <div class="actions review-actions">
      <button class="btn btn-small" data-view-report="${esc(job.scenes_path)}" data-report-label="Scenes JSON">View scenes JSON</button>
      <button class="btn btn-small" data-view-report="${esc(job.storyboard_path)}" data-report-label="Music direction">View music direction</button>
      ${job.reference_image_path ? `<button class="btn btn-small" id="s-view-reference">View reference image</button>` : ""}
      ${job.seed_image ? `<button class="btn btn-small" id="s-view-seed">View seed image</button>` : ""}
    </div>`;
  $("#s-gen-draft").disabled = !review.valid || simple.running;

  const refBtn = $("#s-view-reference");
  if (refBtn) refBtn.addEventListener("click", () =>
    openDrawer("Reference image — " + job.reference_image_path,
      `<img src="/api/media?path=${encodeURIComponent(job.reference_image_path)}" style="width:100%;border-radius:10px">`));

  const seedBtn = $("#s-view-seed");
  if (seedBtn) seedBtn.addEventListener("click", () =>
    openDrawer("Seed image — " + job.seed_image,
      `<img src="/api/media?path=${encodeURIComponent(job.seed_image)}" style="width:100%;border-radius:10px">`));

  if (sceneCapMax > 1) {
    const capInput = $("#s-cap");
    const capSlider = $("#s-cap-slider");
    const capReadout = $("#s-cap-readout");
    const capButtons = $$(".scene-cap-btn");
    const setCap = (n) => {
      const cap = Math.min(sceneCapMax, Math.max(1, parseInt(n, 10) || sceneCapInitial));
      if (capInput) capInput.value = String(cap);
      if (capSlider) capSlider.value = String(cap);
      if (capReadout) capReadout.textContent = String(cap);
      capButtons.forEach((btn) => btn.classList.toggle("is-active", parseInt(btn.dataset.cap, 10) === cap));
    };
    if (capSlider) capSlider.addEventListener("input", () => setCap(capSlider.value));
    capButtons.forEach((btn) => btn.addEventListener("click", () => setCap(btn.dataset.cap)));
    setCap(sceneCapInitial);
  }

  bindStoryboardControls();
  bindCharacterPanel();
  bindEditPromptSection();
  if (sceneCount) {
    buildCoverFlow();
    startCoverFlow();
  }
}

/* ------------------------------------------------------------------ */
/* Storyboard previews (FREE to the user, one admin-configured model)   */
/* ------------------------------------------------------------------ */
/* The control above the reel: pick images-per-scene, then one FREE
 * "Generate storyboard previews" button. There is NO user-facing image-tier
 * choice and NO cost dialog: the storyboard always renders with the ONE
 * admin-configured image model (Admin → Settings → Storyboard image model),
 * server-side, free to the user. It is still bounded by MAX_STORYBOARD_IMAGES
 * (an engineering safety cap), surfaced in the cap note. */
function renderStoryboardControls() {
  const cover = simple.cover;
  const cap = maxStoryboardImages();
  const perSceneOpts = [1, 2, 3, 4, 5].map((n) =>
    `<option value="${n}" ${n === cover.imagesPerScene ? "selected" : ""}>${n}</option>`).join("");
  return `
    <div class="storyboard-tiers">
      <div class="carousel-bar">
        <span class="mini-label">Storyboard previews</span>
        <span class="info-tip" tabindex="0" role="note"
          aria-label="Generate several still images per scene as a time progression, shown in the rotating reel below. This preview is free to you — we cover its cost — and is bounded by an internal safety cap."
          title="Generate several still images per scene as a time progression, shown in the rotating reel below. This preview is free to you — we cover its cost — and is bounded by an internal safety cap.">?</span>
      </div>
      <div class="storyboard-controls">
        <label class="tier-perscene">Images per scene
          <select id="s-images-per-scene">${perSceneOpts}</select>
        </label>
        <button type="button" class="btn btn-small btn-free" id="s-gen-storyboard">Generate storyboard previews <span class="tag tag-free">FREE</span></button>
        <span class="mini storyboard-cap-note">Free to you · capped at ${esc(cap)} images per job (engineering safety).</span>
      </div>
      <div id="s-storyboard-error" class="banner banner-error hidden"></div>
    </div>`;
}

function bindStoryboardControls() {
  const perScene = $("#s-images-per-scene");
  if (perScene) perScene.addEventListener("change", () => {
    simple.cover.imagesPerScene = Math.max(1, parseInt(perScene.value, 10) || 1);
  });
  const genBtn = $("#s-gen-storyboard");
  if (genBtn) genBtn.addEventListener("click", generateStoryboard);
}

/* Render the storyboard previews. The default user path takes NO image_tier and
 * NO token: the server renders with the admin-configured model, free to the
 * user. ONE deliberate click triggers the work; it is bounded server-side by
 * the runaway cap, never an unbounded loop. */
async function generateStoryboard() {
  if (!simple.job) return;
  const perScene = simple.cover.imagesPerScene;
  const errBox = $("#s-storyboard-error");
  if (errBox) errBox.classList.add("hidden");
  const genBtn = $("#s-gen-storyboard");

  if (genBtn) { genBtn.disabled = true; genBtn.dataset.busy = "1"; }
  setStoryboardLoading(true);
  try {
    // No image_tier, no confirm_token: the FREE admin-configured user path.
    const result = await apiPost("/api/simple/storyboard", {
      job_dir: simple.job.job_dir,
      images_per_scene: perScene,
    });
    ingestStoryboard(result);
  } catch (err) {
    if (errBox) { errBox.textContent = simpleUserMessage(err.message); errBox.classList.remove("hidden"); }
  } finally {
    setStoryboardLoading(false);
    if (genBtn) { genBtn.disabled = false; genBtn.dataset.busy = ""; }
  }
}

function setStoryboardLoading(on) {
  const genBtn = $("#s-gen-storyboard");
  if (!genBtn) return;
  if (on) {
    genBtn.dataset.label = genBtn.innerHTML;
    genBtn.innerHTML = `<span class="cost-loading">Rendering…</span>`;
  } else if (genBtn.dataset.label) {
    genBtn.innerHTML = genBtn.dataset.label;
    genBtn.dataset.label = "";
  }
}

/* Fold a storyboard render result into per-scene moment images, then rebuild
 * the flat reel so the new frames appear in true scene-then-moment order. */
function ingestStoryboard(result) {
  const scenes = result.scenes || [];
  for (const scene of scenes) {
    const idx = Number(scene.scene_index);
    if (!idx) continue;
    simple.cover.storyboard[idx] = (scene.moments || []).map((m) => ({
      path: m.path, prompt: m.prompt, moment_index: m.moment_index,
    }));
    // Keep the friendly summary in sync if the render returned one.
    if (scene.summary != null) simple.cover.summaries[idx - 1] = scene.summary;
  }
  rebuildReel();
}

/* Flatten the per-scene storyboard map into ONE ordered list of frames in
 * scene-then-moment order, then rebuild + (re)start the reel. Keeps the focused
 * frame stable by index where possible so a re-render doesn't jump the reel. */
function rebuildReel() {
  const cover = simple.cover;
  const frames = [];
  for (let s = 1; s <= cover.sceneCount; s++) {
    const moments = cover.storyboard[s] || [];
    const momentCount = moments.length;
    moments.forEach((m, mi) => {
      frames.push({
        sceneIndex: s,
        momentIndex: mi + 1,
        momentCount,
        path: m.path,
        prompt: cover.prompts[s - 1] || "",
        summary: cover.summaries[s - 1] || "",
      });
    });
  }
  cover.frames = frames;
  if (frames.length) cover.index = ((cover.index % frames.length) + frames.length) % frames.length;
  else cover.index = 0;
  buildCoverFlow();
  startCoverFlow();
}

/* ------------------------------------------------------------------ */
/* Character identity blocks (FREE metadata, persisted in job dir)     */
/* ------------------------------------------------------------------ */
const MAX_SIMPLE_CHARACTERS = 8;

function renderCharacterPanel(job, sceneCount) {
  const n = Number(sceneCount) || Number(job.scene_count) || 0;
  return `
    <details class="edit-prompt" id="s-character-panel" data-scene-count="${esc(n)}">
      <summary>Cast Identity Blocks <span class="tag tag-free">FREE</span></summary>
      <p class="hint">Paste exact character identity blocks and choose which scenes use them. Saved blocks are applied without rewriting their text.</p>
      <div id="s-character-rows"></div>
      <div id="s-character-error" class="banner banner-error hidden"></div>
      <div class="actions">
        <button type="button" class="btn btn-small" id="s-character-add">Add character</button>
        <button type="button" class="btn btn-small btn-free" id="s-character-save">Save cast <span class="tag tag-free">FREE</span></button>
        <span class="mini" id="s-character-note">Up to ${MAX_SIMPLE_CHARACTERS} characters.</span>
      </div>
    </details>`;
}

function assignmentMode(value) {
  return value === "all" ? "all" : "specific";
}

function assignmentScenesText(value) {
  return Array.isArray(value) ? value.join(",") : "";
}

function renderCharacterRow(character = {}, assignment = "all") {
  const mode = assignmentMode(assignment);
  const scenesText = assignmentScenesText(assignment);
  return `
    <div class="advanced" data-character-row>
      <div class="fields-grid">
        <div class="field">
          <label>Character name</label>
          <input data-character-name placeholder="Ava" value="${esc(character.name || "")}">
        </div>
        <div class="field">
          <label>Assign to</label>
          <select data-character-assignment>
            <option value="all"${mode === "all" ? " selected" : ""}>All scenes</option>
            <option value="specific"${mode === "specific" ? " selected" : ""}>Specific scenes</option>
          </select>
        </div>
        <div class="field${mode === "all" ? " hidden" : ""}" data-character-scenes-field>
          <label>Specific scenes</label>
          <input data-character-scenes placeholder="1,3,4" value="${esc(scenesText)}">
        </div>
      </div>
      <div class="field">
        <label>Verbatim identity block</label>
        <textarea data-character-block rows="5" spellcheck="false" placeholder="Paste the exact identity block. No rewriting happens here.">${esc(character.block || "")}</textarea>
      </div>
      <div class="actions">
        <button type="button" class="btn btn-small" data-character-remove>Remove</button>
      </div>
    </div>`;
}

function characterRows() {
  return $$("#s-character-rows [data-character-row]");
}

function characterPanelHasUserInput() {
  return characterRows().some((row) =>
    (row.querySelector("[data-character-name]")?.value || "").trim()
    || (row.querySelector("[data-character-block]")?.value || "").trim()
    || (row.querySelector("[data-character-scenes]")?.value || "").trim());
}

function syncCharacterAssignment(row) {
  const mode = row.querySelector("[data-character-assignment]");
  const field = row.querySelector("[data-character-scenes-field]");
  const input = row.querySelector("[data-character-scenes]");
  const specific = mode && mode.value === "specific";
  if (field) field.classList.toggle("hidden", !specific);
  if (input) input.disabled = !specific;
}

function syncCharacterPanelControls() {
  characterRows().forEach(syncCharacterAssignment);
  const addBtn = $("#s-character-add");
  if (addBtn) addBtn.disabled = characterRows().length >= MAX_SIMPLE_CHARACTERS;
}

function setCharacterPanelRows(doc) {
  const rows = $("#s-character-rows");
  if (!rows) return;
  const characters = Array.isArray(doc && doc.characters) ? doc.characters : [];
  const assignments = (doc && doc.assignments) || {};
  const rowHtml = characters.length
    ? characters.map((character) =>
        renderCharacterRow(character, assignments[character.name] || "all")).join("")
    : renderCharacterRow();
  rows.innerHTML = rowHtml;
  syncCharacterPanelControls();
}

async function loadCharacterPanel() {
  if (!simple.job || !simple.job.job_dir) return;
  const note = $("#s-character-note");
  const errBox = $("#s-character-error");
  if (errBox) errBox.classList.add("hidden");
  if (note) note.textContent = "Loading saved cast…";
  const preserveLocalRows = characterPanelHasUserInput();
  try {
    const doc = await apiGet(`/api/simple/characters?dir=${encodeURIComponent(simple.job.job_dir)}`);
    simple.job.characters = doc.characters || [];
    simple.job.assignments = doc.assignments || {};
    if (!preserveLocalRows) setCharacterPanelRows(doc);
    if (note) note.textContent = doc.characters && doc.characters.length
      ? (preserveLocalRows ? "Saved cast loaded; your current edits were left in place." : "Loaded saved cast.")
      : `Up to ${MAX_SIMPLE_CHARACTERS} characters.`;
  } catch (err) {
    setCharacterPanelRows({ characters: [], assignments: {} });
    if (errBox) { errBox.textContent = simpleUserMessage(err.message); errBox.classList.remove("hidden"); }
    if (note) note.textContent = "Could not load saved cast.";
  }
}

function parseCharacterScenes(value) {
  const text = String(value || "").trim();
  if (!text) return [];
  return text.split(",")
    .map((part) => part.trim())
    .filter((part) => part !== "")
    .map((part) => Number(part));
}

function collectCharacterPayload() {
  const characters = [];
  const assignments = {};
  for (const row of characterRows()) {
    const rawName = row.querySelector("[data-character-name]")?.value || "";
    const block = row.querySelector("[data-character-block]")?.value || "";
    if (!rawName.trim() && !block.trim()) continue;
    characters.push({ name: rawName, block });
    const name = rawName.trim();
    const mode = row.querySelector("[data-character-assignment]")?.value || "all";
    assignments[name] = mode === "all"
      ? "all"
      : parseCharacterScenes(row.querySelector("[data-character-scenes]")?.value || "");
  }
  return { characters, assignments };
}

function setCharacterPanelBusy(busy) {
  const panel = $("#s-character-panel");
  if (!panel) return;
  panel.querySelectorAll("input, textarea, select, button").forEach((el) => { el.disabled = busy; });
  panel.classList.toggle("is-busy", busy);
}

function invalidateSimpleGeneratedRuns(message) {
  const draftStatus = $("#s-draft-status");
  const draftVideo = $("#s-draft-video");
  const hqStatus = $("#s-hq-status");
  const hqVideo = $("#s-hq-video");
  const hadRunState = !!(simple.job && simple.job.runs && Object.keys(simple.job.runs).length);
  const hadRunUi = [draftStatus, draftVideo, hqStatus, hqVideo]
    .some((el) => el && el.innerHTML.trim());
  stopSimplePolls();
  if (simple.job) simple.job.runs = {};
  if (!$("#cost-confirm-modal").classList.contains("hidden")) closeCostConfirm();
  if (draftVideo) draftVideo.innerHTML = "";
  if (hqStatus) hqStatus.innerHTML = "";
  if (hqVideo) hqVideo.innerHTML = "";
  if (draftStatus) draftStatus.innerHTML = hadRunState || hadRunUi
    ? `<div class="banner banner-warn">${esc(message)}</div>`
    : "";
  setSimpleRunning(false);
}

function ingestCharacterResult(result) {
  const cover = simple.cover;
  for (const row of result.prompts || []) {
    const idx = Number(row.scene_index);
    if (!idx) continue;
    if (row.prompt != null) cover.prompts[idx - 1] = row.prompt;
  }
  if (result.changed) invalidateSimpleGeneratedRuns("Cast changed — generate a fresh draft before making a final video.");
  rebuildReel();
}

async function saveCharacterPanel() {
  if (!simple.job || !simple.job.job_dir) return;
  const errBox = $("#s-character-error");
  const note = $("#s-character-note");
  const btn = $("#s-character-save");
  const wasLabel = btn ? btn.innerHTML : "";
  if (errBox) errBox.classList.add("hidden");
  if (btn) btn.innerHTML = `<span class="cost-loading">Saving…</span>`;
  if (note) note.textContent = "Saving cast and updating scenes…";
  setCharacterPanelBusy(true);

  try {
    const payload = collectCharacterPayload();
    const result = await apiPost("/api/simple/characters", {
      job_dir: simple.job.job_dir,
      characters: payload.characters,
      assignments: payload.assignments,
    });
    simple.job.characters = result.characters || [];
    simple.job.assignments = result.assignments || {};
    ingestCharacterResult(result);
    setCharacterPanelRows(result);
    if (note) note.textContent = result.changed
      ? "Saved. The reel now uses the updated cast."
      : "Saved. Scenes were already up to date.";
  } catch (err) {
    if (errBox) { errBox.textContent = simpleUserMessage(err.message); errBox.classList.remove("hidden"); }
    if (note) note.textContent = `Up to ${MAX_SIMPLE_CHARACTERS} characters.`;
  } finally {
    setCharacterPanelBusy(false);
    if (btn) btn.innerHTML = wasLabel || `Save cast <span class="tag tag-free">FREE</span>`;
    syncCharacterPanelControls();
  }
}

function bindCharacterPanel() {
  const panel = $("#s-character-panel");
  const rows = $("#s-character-rows");
  if (!panel || !rows) return;
  setCharacterPanelRows({ characters: [], assignments: {} });
  loadCharacterPanel();

  const addBtn = $("#s-character-add");
  if (addBtn) addBtn.addEventListener("click", () => {
    if (characterRows().length >= MAX_SIMPLE_CHARACTERS) return;
    rows.insertAdjacentHTML("beforeend", renderCharacterRow());
    syncCharacterPanelControls();
  });

  const saveBtn = $("#s-character-save");
  if (saveBtn) saveBtn.addEventListener("click", saveCharacterPanel);

  rows.addEventListener("click", (event) => {
    const remove = event.target.closest("[data-character-remove]");
    if (!remove) return;
    const row = remove.closest("[data-character-row]");
    if (row) row.remove();
    if (!characterRows().length) rows.innerHTML = renderCharacterRow();
    syncCharacterPanelControls();
  });

  rows.addEventListener("change", (event) => {
    const select = event.target.closest("[data-character-assignment]");
    if (!select) return;
    const row = select.closest("[data-character-row]");
    if (row) syncCharacterAssignment(row);
  });
}

/* ------------------------------------------------------------------ */
/* Edit prompt (rewrite the prompts that feed the video stage, FREE)   */
/* ------------------------------------------------------------------ */
/* A plain-language edit at the bottom of the review card. Pick "Entire video"
 * or a specific "Scene N", describe the change, and confirm. On confirm we POST
 * /api/simple/edit-scenes {job_dir, scope, instruction}; the server rewrites the
 * affected scene prompt(s) in scenes.json (the SAME artifact that feeds the
 * video stage), refreshes the friendly summaries, and re-renders the affected
 * storyboard images (free, with the admin-configured image model). On success
 * we fold the new prompts/summaries/images back in and rebuild the reel so the
 * preview is always up to date. */
function renderEditPromptSection(job, sceneCount) {
  const n = Number(sceneCount) || Number(job.scene_count) || 0;
  const scenePills = [];
  for (let s = 1; s <= n; s++) {
    scenePills.push(`<button type="button" class="scene-pill" role="radio" aria-checked="false" data-scope="${s}">Scene ${s}</button>`);
  }
  return `
    <details class="edit-prompt" id="s-edit-prompt">
      <summary>Adjust Your Scenes <span class="tag tag-free">FREE</span></summary>
      <p class="hint">Refine what the video will show. This rewrites the scene prompt(s) that feed the video stage and re-renders the affected preview images — it never generates video and never spends your money.</p>
      <textarea id="s-edit-instruction" rows="5" spellcheck="true"
        placeholder="e.g. Make the lighting warmer and add slow drifting dust motes; keep the same subject and framing."></textarea>
      <div class="scene-pills" id="s-edit-scope" role="radiogroup" aria-label="Apply to" data-scope="all">
        <span class="scene-pill-glider" aria-hidden="true"></span>
        <button type="button" class="scene-pill active" role="radio" aria-checked="true" data-scope="all">Entire video</button>
        ${scenePills.join("")}
      </div>
      <div id="s-edit-error" class="banner banner-error hidden"></div>
      <div class="actions">
        <button type="button" class="btn btn-small btn-free" id="s-edit-confirm">Confirm changes <span class="tag tag-free">FREE</span></button>
        <span class="mini" id="s-edit-note">Re-renders the affected preview images.</span>
      </div>
    </details>`;
}

function layoutEditScopeGlider(container) {
  const scopeEl = container || $("#s-edit-scope");
  if (!scopeEl) return;
  const active = scopeEl.querySelector(".scene-pill.active");
  const glider = scopeEl.querySelector(".scene-pill-glider");
  if (!active || !glider) return;
  glider.style.transform = `translateX(${active.offsetLeft}px)`;
  glider.style.width = `${active.offsetWidth}px`;
}

function queueEditScopeGliderLayout(container) {
  requestAnimationFrame(() => requestAnimationFrame(() => layoutEditScopeGlider(container)));
}

function bindEditPromptSection() {
  const btn = $("#s-edit-confirm");
  if (btn) btn.addEventListener("click", confirmEditPrompt);

  const scopeEl = $("#s-edit-scope");
  if (scopeEl) {
    scopeEl.addEventListener("click", (e) => {
      const pill = e.target.closest(".scene-pill");
      if (!pill || !scopeEl.contains(pill)) return;
      scopeEl.querySelectorAll(".scene-pill").forEach((p) => {
        p.classList.remove("active");
        p.setAttribute("aria-checked", "false");
      });
      pill.classList.add("active");
      pill.setAttribute("aria-checked", "true");
      scopeEl.dataset.scope = pill.dataset.scope || "all";
      layoutEditScopeGlider(scopeEl);
    });
  }

  const details = $("#s-edit-prompt");
  if (details) {
    details.addEventListener("toggle", () => {
      if (details.open) queueEditScopeGliderLayout(scopeEl);
    });
    if (details.open) queueEditScopeGliderLayout(scopeEl);
  }
}

async function confirmEditPrompt() {
  if (!simple.job) return;
  const scopeEl = $("#s-edit-scope");
  const instrEl = $("#s-edit-instruction");
  const errBox = $("#s-edit-error");
  const btn = $("#s-edit-confirm");
  const note = $("#s-edit-note");
  if (errBox) errBox.classList.add("hidden");

  const scope = scopeEl ? (scopeEl.dataset.scope || "all") : "all";
  const instruction = instrEl ? instrEl.value.trim() : "";
  if (!instruction) {
    if (errBox) { errBox.textContent = "Describe the change you want first."; errBox.classList.remove("hidden"); }
    return;
  }

  // Disable the whole section during the request so it can't be double-fired.
  const wasLabel = btn ? btn.innerHTML : "";
  if (btn) { btn.disabled = true; btn.innerHTML = `<span class="cost-loading">Applying…</span>`; }
  if (scopeEl) { scopeEl.classList.add("is-busy"); scopeEl.setAttribute("aria-disabled", "true"); }
  if (instrEl) instrEl.disabled = true;
  if (note) note.textContent = "Rewriting prompts and re-rendering the affected images…";

  try {
    const result = await apiPost("/api/simple/edit-scenes", {
      job_dir: simple.job.job_dir,
      scope,
      instruction,
    });
    // Fold the rewritten prompts/summaries + regenerated images back into the
    // reel state, then rebuild it so it is always up to date.
    ingestEditResult(result);
    if (instrEl) instrEl.value = "";
    if (note) note.textContent = "Updated. The reel and prompts now reflect your change.";
  } catch (err) {
    if (errBox) { errBox.textContent = simpleUserMessage(err.message); errBox.classList.remove("hidden"); }
    if (note) note.textContent = "Re-renders the affected preview images.";
  } finally {
    if (btn) { btn.disabled = false; btn.innerHTML = wasLabel || `Confirm changes <span class="tag tag-free">FREE</span>`; }
    if (scopeEl) { scopeEl.classList.remove("is-busy"); scopeEl.setAttribute("aria-disabled", "false"); }
    if (instrEl) instrEl.disabled = false;
  }
}

/* Apply an edit-scenes result: update per-scene technical prompts, summaries,
 * and the regenerated moment images, then rebuild the flat reel. */
function ingestEditResult(result) {
  const cover = simple.cover;
  for (const scene of result.scenes || []) {
    const idx = Number(scene.scene_index);
    if (!idx) continue;
    if (scene.prompt != null) cover.prompts[idx - 1] = scene.prompt;
    if (scene.summary != null) cover.summaries[idx - 1] = scene.summary;
    cover.storyboard[idx] = (scene.moments || []).map((m) => ({
      path: m.path, prompt: m.prompt, moment_index: m.moment_index,
    }));
  }
  invalidateSimpleGeneratedRuns("Scenes changed — generate a fresh draft before making a final video.");
  rebuildReel();
}

/* ------------------------------------------------------------------ */
/* Flat circular auto-rotating reel (one image = one carousel unit)    */
/* ------------------------------------------------------------------ */
/* The reel shows ALL storyboard images flattened into ONE ordered list in
 * scene-then-moment order (scene1 moment1, scene1 moment2, …, scene2 moment1,
 * …). The focused image is ALWAYS centered; the next sits to the right, the
 * previous to the left, and the rest recede AROUND behind it. It is a true RING:
 * the neighbours wrap (after the last image the next is the first), so there is
 * always a card on each side even at the ends. Auto-rotate advances one image
 * every 2s; ANY manual nav pauses it and re-arms 5s after the last interaction.
 * Caption = the focused image's SCENE summary (same across that scene's
 * moments), crossfading only when the SCENE changes. */
const COVER_AUTO_MS = 2000;        // auto-advance: one image every 2 seconds
const COVER_RESUME_MS = 5000;      // re-arm auto-rotate 5s after manual nav
const COVER_NEIGHBOURS = 3;        // how many cards to render each side of focus

function renderCoverFlowShell() {
  return `
    <div class="coverflow" id="s-coverflow" tabindex="0" aria-roledescription="carousel"
         aria-label="Storyboard preview reel">
      <button type="button" class="cover-nav cover-prev" id="s-cover-prev" aria-label="Previous image">‹</button>
      <div class="cover-stage" id="s-cover-stage"></div>
      <button type="button" class="cover-nav cover-next" id="s-cover-next" aria-label="Next image">›</button>
      <div class="cover-caption" id="s-cover-caption">
        <div class="cover-frame-tag" id="s-cover-frame-tag"></div>
        <div class="cover-summary-wrap"><p class="cover-summary" id="s-cover-summary"></p></div>
        <details class="cover-tech"><summary>View technical prompt</summary>
          <p class="cover-tech-text" id="s-cover-tech"></p></details>
      </div>
      <div class="cover-dots" id="s-cover-dots" role="tablist" aria-label="Storyboard images"></div>
    </div>`;
}

/* The signed CIRCULAR offset of frame `i` from the focused index, in
 * [-floor(n/2), +floor(n/2)]. This is what makes the reel a true ring: the frame
 * "just before" focus is at offset -1 even when focus is index 0 (it wraps to
 * the last frame), so there is always a neighbour on each side. */
function circularOffset(i, focus, n) {
  let d = ((i - focus) % n + n) % n; // 0..n-1
  if (d > n / 2) d -= n;             // fold the long way round to the short way
  return d;
}

function negativeAppliedBadge(cover, sceneIndex) {
  const entry = (cover.negativeApplied || [])[Number(sceneIndex) - 1] || {};
  const labels = {
    positive: "positive phrasing (reference scene)",
    library: "negative library applied",
    custom: "custom negative preserved",
  };
  const label = labels[entry.mode];
  return label ? `<span class="cover-scene-tag" style="top:auto;bottom:8px;left:10px;">${esc(label)}</span>` : "";
}

/* Build the reel ONCE per frame set: one card per frame (storyboards are capped
 * at MAX_STORYBOARD_IMAGES, so this is a small, bounded DOM), plus one dot per
 * scene. Navigation then only re-positions cards (layoutCoverFlow) — images
 * persist in the DOM and are never re-fetched on a step. Shows a calm shell
 * before any image exists. */
function buildCoverFlow() {
  const stage = $("#s-cover-stage");
  if (!stage) return;
  const cover = simple.cover;
  const hasFrames = cover.frames.length > 0;

  if (!hasFrames) {
    // No images yet: one tasteful "generate previews" shell so the reel has
    // presence before the FREE storyboard render is run.
    stage.innerHTML = `
      <div class="cover-card focused" aria-hidden="true">
        <div class="cover-face">
          <span class="cover-scene-tag">${esc(cover.sceneCount)} scene${cover.sceneCount === 1 ? "" : "s"}</span>
          <span class="cover-empty">Generate storyboard previews to fill the reel</span>
        </div>
      </div>`;
    const dotsEmpty = $("#s-cover-dots");
    if (dotsEmpty) dotsEmpty.innerHTML = "";
    bindCoverHoverPause();
    updateCoverCaption();
    return;
  }

  // One card per frame, in flat scene-then-moment order. Each carries its frame
  // index; clicking a side card focuses THAT image. Images are filled lazily in
  // layoutCoverFlow (only the visible band paints) and then persist.
  stage.innerHTML = cover.frames.map((frame, i) => `
    <div class="cover-card" data-frame-index="${esc(i)}" aria-hidden="true">
      <div class="cover-face">
        <img class="cover-img" loading="lazy" src="/api/media?path=${encodeURIComponent(frame.path)}"
          alt="Scene ${esc(frame.sceneIndex)} frame ${esc(frame.momentIndex)}">
        <span class="cover-scene-tag">Scene ${esc(frame.sceneIndex)} · ${esc(frame.momentIndex)}/${esc(frame.momentCount)}</span>
        ${negativeAppliedBadge(cover, frame.sceneIndex)}
      </div>
    </div>`).join("");

  // Dots: one per scene (not per image) so a long reel stays readable; the
  // active dot reflects the focused frame's scene.
  const dots = $("#s-cover-dots");
  if (dots) {
    dots.innerHTML = "";
    for (let s = 1; s <= cover.sceneCount; s++) {
      const dot = document.createElement("button");
      dot.type = "button";
      dot.className = "cover-dot";
      dot.setAttribute("role", "tab");
      dot.setAttribute("aria-label", `Scene ${s}`);
      dot.dataset.coverDotScene = String(s);
      dots.appendChild(dot);
    }
  }

  bindCoverHoverPause();
  layoutCoverFlow();
}

/* Hover-pause bound directly to the carousel root (mouseenter/leave don't bubble,
 * so they fire only for the root — no flicker over inner elements). Bound once. */
function bindCoverHoverPause() {
  const cf = $("#s-coverflow");
  if (cf && !cf.dataset.hoverBound) {
    cf.dataset.hoverBound = "1";
    cf.addEventListener("mouseenter", () => manualPause());
    cf.addEventListener("mouseleave", () => { if (!simple.cover.drag) scheduleResume(); });
  }
}

/* Position every card in 3D around the centered focus using its CIRCULAR offset,
 * so the focused image is always centered, the next sits to the right, the
 * previous to the left, and the rest recede/loop AROUND behind. Far cards hide.
 * Only transforms change on a step — images stay put (no re-fetch). */
function layoutCoverFlow() {
  const stage = $("#s-cover-stage");
  if (!stage) return;
  const cover = simple.cover;
  const n = cover.frames.length;
  if (!n) return;
  const stageW = stage.getBoundingClientRect().width || 920;
  const step = Math.max(150, stageW * 0.20);
  const cards = stage.querySelectorAll(".cover-card[data-frame-index]");
  cards.forEach((card) => {
    const i = parseInt(card.dataset.frameIndex, 10) || 0;
    const offset = circularOffset(i, cover.index, n);
    const abs = Math.abs(offset);
    const focused = offset === 0;
    const hidden = abs > COVER_NEIGHBOURS;
    const clamped = Math.max(-COVER_NEIGHBOURS - 1, Math.min(COVER_NEIGHBOURS + 1, offset));
    const translateX = clamped * step;
    const translateZ = focused ? 60 : -120 - (abs - 1) * 60;
    const rotateY = focused ? 0 : (offset > 0 ? -42 : 42);
    const scale = focused ? 1 : Math.max(0.6, 0.85 - (abs - 1) * 0.08);
    card.style.transform =
      `translateX(${translateX}px) translateZ(${translateZ}px) rotateY(${rotateY}deg) scale(${scale})`;
    card.style.opacity = hidden ? "0" : (focused ? "1" : String(Math.max(0.32, 0.85 - (abs - 1) * 0.18)));
    card.style.zIndex = String(100 - abs);
    card.style.pointerEvents = hidden ? "none" : "auto";
    card.classList.toggle("focused", focused);
  });
  // Dots track the focused frame's scene.
  const focusedScene = (cover.frames[cover.index] || {}).sceneIndex;
  const dots = $("#s-cover-dots");
  if (dots) dots.querySelectorAll(".cover-dot").forEach((dot) =>
    dot.classList.toggle("active", Number(dot.dataset.coverDotScene) === focusedScene));
  updateCoverCaption();
  if (isReelLocked()) syncScopeToLockedFrame();
}

/* Crossfade the focused frame's SCENE summary (same text across a scene's
 * moments), and update the "SCENE N · frame k/m" tag + the technical prompt
 * behind its expander. The summary text only crossfades when it actually
 * changes (i.e. when the SCENE changes), so stepping moment-to-moment within a
 * scene doesn't flicker the caption. */
let coverCaptionToken = 0;
function updateCoverCaption() {
  const cover = simple.cover;
  const summaryEl = $("#s-cover-summary");
  const techEl = $("#s-cover-tech");
  const tagEl = $("#s-cover-frame-tag");
  if (!summaryEl) return;

  const frame = cover.frames[cover.index];
  if (!frame) {
    // Pre-render shell: caption reflects scene 1's summary if known.
    const s0 = cover.summaries[0] || cover.prompts[0] || "";
    if (tagEl) tagEl.textContent = cover.sceneCount ? `${cover.sceneCount} scene${cover.sceneCount === 1 ? "" : "s"} ready` : "";
    if (techEl) techEl.textContent = cover.prompts[0] || "(no technical prompt available)";
    setCoverSummary(s0);
    return;
  }
  if (tagEl) tagEl.textContent = `SCENE ${frame.sceneIndex} · frame ${frame.momentIndex}/${frame.momentCount}`;
  const tech = frame.prompt || cover.prompts[frame.sceneIndex - 1] || "(no technical prompt available)";
  if (techEl) techEl.textContent = tech;
  const summary = frame.summary || cover.summaries[frame.sceneIndex - 1] || cover.prompts[frame.sceneIndex - 1] || `Scene ${frame.sceneIndex}`;
  setCoverSummary(summary);
}

/* Crossfade the caption summary text to `summary` (no-op if unchanged). */
function setCoverSummary(summary) {
  const summaryEl = $("#s-cover-summary");
  if (!summaryEl) return;
  if (summaryEl.textContent === summary) return; // no change → no flicker
  const token = ++coverCaptionToken;
  summaryEl.classList.add("fading");
  setTimeout(() => {
    if (token !== coverCaptionToken) return; // a newer change superseded us
    summaryEl.textContent = summary;
    summaryEl.classList.remove("fading");
  }, 220);
}

/* Move the focus by `delta` images around the ring (wrapping) and re-position
 * the cards. Cards persist in the DOM; only their transforms change, so the wrap
 * is seamless and images are never re-fetched on a step. */
function coverShift(delta) {
  const cover = simple.cover;
  const n = cover.frames.length;
  if (!n) return;
  cover.index = ((cover.index + delta) % n + n) % n;
  layoutCoverFlow();
}
function coverNext() { coverShift(1); }
function coverPrev() { coverShift(-1); }

/* Focus a specific frame index directly (clicking a side card). */
function coverGoFrame(frameIndex) {
  const n = simple.cover.frames.length;
  if (!n) return;
  simple.cover.index = ((frameIndex % n) + n) % n;
  layoutCoverFlow();
}

/* Focus a specific scene's FIRST frame (used by the dots). */
function coverGoScene(sceneIndex) {
  const at = simple.cover.frames.findIndex((f) => f.sceneIndex === sceneIndex);
  if (at < 0) return;
  coverGoFrame(at);
}

function isReelLocked() {
  return !!(simple.cover && simple.cover.locked);
}

function syncScopeToLockedFrame() {
  const cont = $("#s-edit-scope");
  if (!cont) return;
  const locked = isReelLocked();
  const cover = simple.cover || {};
  const frame = locked && Array.isArray(cover.frames) ? cover.frames[cover.index] : null;
  let scope = frame && frame.sceneIndex != null ? String(frame.sceneIndex) : "all";
  const pills = Array.from(cont.querySelectorAll(".scene-pill"));
  let pill = pills.find((p) => p.dataset.scope === scope);
  if (!pill && scope !== "all") {
    scope = "all";
    pill = pills.find((p) => p.dataset.scope === scope);
  }
  if (!pill) return;
  cont.dataset.scope = scope;
  pills.forEach((p) => {
    const active = p === pill;
    p.classList.toggle("active", active);
    p.setAttribute("aria-checked", active ? "true" : "false");
  });
  cont.classList.toggle("scope-locked", locked);
  layoutEditScopeGlider(cont);
}

function prefersReducedMotion() {
  return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/* Start (or restart) the auto-rotate loop: advance one image every 2s, forever.
 * Respects prefers-reduced-motion (no auto-rotate; manual still works). */
function startCoverFlow() {
  stopCoverFlow();
  if (simple.cover.frames.length <= 1) return;
  if (prefersReducedMotion()) return;
  simple.cover.paused = false;
  simple.cover.autoTimer = setInterval(() => {
    if (!simple.cover.paused) coverNext();
  }, COVER_AUTO_MS);
}
function stopCoverFlow() {
  if (simple.cover.autoTimer) { clearInterval(simple.cover.autoTimer); simple.cover.autoTimer = null; }
  if (simple.cover.resumeTimer) { clearTimeout(simple.cover.resumeTimer); simple.cover.resumeTimer = null; }
}

/* Manual interaction pauses auto-rotate and cancels any pending resume. */
function manualPause() {
  simple.cover.paused = true;
  if (simple.cover.resumeTimer) { clearTimeout(simple.cover.resumeTimer); simple.cover.resumeTimer = null; }
}

/* Schedule auto-rotate to RESUME after COVER_RESUME_MS of no further interaction.
 * Each call resets the countdown, so continuous interaction keeps it paused.
 * Never resumes under reduced-motion. */
function scheduleResume() {
  if (simple.cover.locked) { simple.cover.paused = true; return; }
  if (simple.cover.resumeTimer) { clearTimeout(simple.cover.resumeTimer); }
  if (prefersReducedMotion()) { simple.cover.paused = true; return; }
  simple.cover.resumeTimer = setTimeout(() => {
    simple.cover.resumeTimer = null;
    simple.cover.paused = false;
  }, COVER_RESUME_MS);
}

/* Any manual navigation: step, pause auto-rotate, then schedule idle-resume. */
function manualNav(fn) {
  manualPause();
  fn();
  scheduleResume();
}

function lockCover(frameIndex) {
  if (frameIndex != null && frameIndex !== simple.cover.index) coverGoFrame(frameIndex);
  simple.cover.locked = true;
  simple.cover.paused = true;
  if (simple.cover.resumeTimer) { clearTimeout(simple.cover.resumeTimer); simple.cover.resumeTimer = null; }
  const cf = $("#s-coverflow");
  if (cf) {
    cf.classList.add("cover-locked");
    const sc = (simple.cover.frames[simple.cover.index] || {}).sceneIndex || "";
    cf.setAttribute("aria-label", "Storyboard preview reel (locked on scene " + sc + ")");
  }
  if (typeof syncScopeToLockedFrame === "function") syncScopeToLockedFrame();
}

function unlockCover() {
  simple.cover.locked = false;
  const cf = $("#s-coverflow");
  if (cf) {
    cf.classList.remove("cover-locked");
    cf.setAttribute("aria-label", "Storyboard preview reel");
  }
  scheduleResume();
  if (typeof syncScopeToLockedFrame === "function") syncScopeToLockedFrame();
}

/* Delegated reel interaction: nav buttons, dots, clicking a side card to focus
 * it. All handlers are on document so they survive re-renders. */
document.addEventListener("click", (e) => {
  if (e.target.closest("#s-cover-next")) { manualNav(coverNext); return; }
  if (e.target.closest("#s-cover-prev")) { manualNav(coverPrev); return; }
  const dot = e.target.closest("[data-cover-dot-scene]");
  if (dot) { manualNav(() => coverGoScene(parseInt(dot.dataset.coverDotScene, 10))); return; }
  const card = e.target.closest("[data-frame-index]");
  if (card && card.closest("#s-cover-stage")) {
    const frameIndex = parseInt(card.dataset.frameIndex, 10);
    if (simple.cover.locked && frameIndex === simple.cover.index) {
      unlockCover();
    } else {
      lockCover(frameIndex);
    }
    return;
  }
});

// Pause auto-advance on keyboard focus inside the reel; resume on blur.
document.addEventListener("focusin", (e) => {
  if (e.target.closest && e.target.closest("#s-coverflow")) manualPause();
});
document.addEventListener("focusout", (e) => {
  if (e.target.closest && e.target.closest("#s-coverflow")) scheduleResume();
});

// Keyboard: arrow keys advance when the reel has focus.
document.addEventListener("keydown", (e) => {
  const cf = e.target.closest && e.target.closest("#s-coverflow");
  if (!cf) return;
  if (e.key === "ArrowRight") { e.preventDefault(); manualNav(coverNext); }
  else if (e.key === "ArrowLeft") { e.preventDefault(); manualNav(coverPrev); }
});

// Pointer drag to spin the ring. Dragging pauses auto-advance; a drag past a
// threshold advances one image. Pointer events cover mouse + touch + pen.
document.addEventListener("pointerdown", (e) => {
  const stage = e.target.closest("#s-cover-stage");
  if (!stage || !simple.cover.frames.length) return;
  simple.cover.drag = { startX: e.clientX, moved: false };
  manualPause();
});
document.addEventListener("pointermove", (e) => {
  const drag = simple.cover.drag;
  if (!drag) return;
  // Drag may visually spin a locked reel, but lock intent persists until click.
  const dx = e.clientX - drag.startX;
  if (Math.abs(dx) > 6) drag.moved = true;
  if (Math.abs(dx) > 70) {
    if (dx < 0) coverNext(); else coverPrev();
    drag.startX = e.clientX; // continue from the new position for multi-step drags
  }
});
document.addEventListener("pointerup", () => {
  if (!simple.cover.drag) return;
  simple.cover.drag = null;
  // Resume on idle unless still hovering (the mouseleave handler will then
  // schedule the resume when the pointer eventually leaves).
  const hovering = document.querySelector("#s-coverflow:hover");
  if (!hovering) scheduleResume();
});

/* ---- generate (draft preview / final video at a chosen tier) ---- */
// The draft step keeps the legacy "draft" quality (the cheap/fast model from
// Admin Settings). The final step lets the operator pick a VIDEO render tier
// (Standard / Quality / Ultra 4K); that tier key is passed straight through as
// the existing `quality` field — the server resolves it to model+resolution and
// mints a tier-bound token. Either way it is a deliberate second click.
$("#s-gen-draft").addEventListener("click", () => simpleGenerate("draft"));
$("#s-gen-hq").addEventListener("click", () => simpleGenerate(selectedVideoTier));

/* Group every concrete tier run under one "hq" slot in job.runs / polling, so
 * the final-step UI and the draft-first unlock keep working regardless of which
 * tier was chosen. "draft" stays its own slot. */
function runSlotFor(quality) { return quality === "draft" ? "draft" : "hq"; }

async function simpleGenerate(quality) {
  if (!simple.job || simple.running) return;
  const capInput = $("#s-cap");
  const cap = capInput ? Math.max(1, parseInt(capInput.value, 10) || simple.job.max_scenes) : simple.job.max_scenes;
  const slot = runSlotFor(quality);
  const errBox = $(slot === "draft" ? "#s-draft-error" : "#s-hq-error");
  errBox.classList.add("hidden");

  // Resolve a human-readable model label + dialog title for the chosen selector.
  // A legacy quality (draft/hq) maps via Admin Settings; a video tier key maps
  // via the loaded tier table.
  let modelLabel = quality;
  let title;
  const vt = findVideoTier(quality);
  if (vt) {
    modelLabel = `${vt.label} · ${vt.resolution}`;
    title = `Generate final video — ${vt.label}`;
  } else {
    const q = appSettings && appSettings.settings ? appSettings.settings[quality] : null;
    title = quality === "draft" ? "Generate draft preview" : "Generate high quality";
    modelLabel = q ? `${title} · ${q.resolution}` : title;
  }

  // Simple mode: a one-click, cost-aware confirm REPLACES the typed-SPEND modal
  // (which the Administrator console still uses). Opening the dialog mints the
  // token but spends nothing; the distinct second click on its primary button
  // sends that token to /api/simple/generate. A passing validation run still
  // happens server-side before any paid call.
  const confirmed = await askCostConfirm({ quality, cap, modelLabel, title });
  if (!confirmed) return; // cancelled — nothing minted was used, nothing spent

  setSimpleRunning(true);
  try {
    const result = await apiPost("/api/simple/generate", {
      job_dir: simple.job.job_dir, quality,
      confirm_token: confirmed.token, max_scenes: cap,
    });
    simple.job = result.job;
    pollSimpleRun(slot, result.ui_run_id);
  } catch (err) {
    setSimpleRunning(false);
    errBox.textContent = simpleUserMessage(err.message);
    errBox.classList.remove("hidden");
  }
}

/* The simple-mode cost-aware confirm, as a promise: resolves with {token} on a
 * deliberate Generate click, or null on cancel/close. The flow is two distinct
 * clicks by construction — clicking "Generate draft/high quality" opens this
 * dialog (which mints a single-use token bound to the costed action but spends
 * NOTHING), and only the dialog's own primary button sends the token onward.
 * NO typing. Distinct from askSpend() (the admin typed-SPEND gate). */
let costConfirmResolver = null;

function moneyLabel(estimate) {
  if (!estimate || estimate.total == null) return null;
  const currency = estimate.currency || "USD";
  const amount = Number(estimate.total);
  const formatted = Number.isFinite(amount) ? amount.toFixed(2) : String(estimate.total);
  return currency === "USD" ? `$${formatted}` : `${formatted} ${currency}`;
}

function askCostConfirm({ quality, cap, modelLabel, title }) {
  return new Promise(async (resolve) => {
    costConfirmResolver = resolve;
    const confirmBtn = $("#btn-cost-confirm");
    const costBox = $("#cost-confirm-cost");
    const errBox = $("#cost-confirm-error");
    confirmBtn.disabled = true;
    confirmBtn.dataset.token = "";
    confirmBtn.textContent = "Generate";
    errBox.classList.add("hidden");
    errBox.textContent = "";
    $("#cost-confirm-title").textContent = `${title} — this spends money`;
    $("#cost-confirm-summary").innerHTML = `
      <table class="kv">
        <tr><td>video</td><td>${esc(simple.job.slug)}</td></tr>
        <tr><td>scenes</td><td>${esc(cap)} paid video generation${cap === 1 ? "" : "s"}</td></tr>
        <tr><td>quality</td><td>${esc(modelLabel)}</td></tr>
        <tr><td>plus</td><td>music generation + assembly</td></tr>
      </table>`;
    costBox.innerHTML = `<span class="cost-loading">Fetching estimate…</span>`;
    $("#cost-confirm-modal").classList.remove("hidden");
    if (window.NeonFluid) window.NeonFluid.setCalm(true);

    // First click already happened (Generate draft/HQ). Minting the token here
    // is free and authorizes nothing; the SECOND deliberate click sends it.
    try {
      const minted = await apiPost("/api/simple/confirm-token", {
        job_dir: simple.job.job_dir, quality, max_scenes: cap,
      });
      // The dialog may have been cancelled while the request was in flight.
      if (costConfirmResolver !== resolve) return;
      const cost = moneyLabel(minted.estimate);
      const costText = cost ? `about ${cost}` : "an unknown amount";
      costBox.innerHTML = `
        <span class="cost-amount">${esc(cost || "?")}</span>
        <span class="cost-approx">approximate</span>
        <p class="cost-sub">Estimated spend for this generation, using the published Gemini API rates (verify they are current) — or your own rates if set in Admin → Settings.</p>`;
      confirmBtn.dataset.token = minted.confirm_token;
      confirmBtn.textContent = `Generate — costs ${costText}`;
      confirmBtn.disabled = false;
    } catch (err) {
      if (costConfirmResolver !== resolve) return;
      costBox.innerHTML = "";
      errBox.textContent = simpleUserMessage(err.message);
      errBox.classList.remove("hidden");
      confirmBtn.disabled = true; // no token ⇒ no spend possible
    }
  });
}

function settleCostConfirm(value) {
  $("#cost-confirm-modal").classList.add("hidden");
  if (window.NeonFluid) window.NeonFluid.setCalm(false);
  if (costConfirmResolver) { const r = costConfirmResolver; costConfirmResolver = null; r(value); }
}
function closeCostConfirm() { settleCostConfirm(null); }

$("#btn-cost-cancel").addEventListener("click", () => settleCostConfirm(null));
$("#btn-cost-confirm").addEventListener("click", () => {
  const btn = $("#btn-cost-confirm");
  if (btn.disabled) return;
  const token = btn.dataset.token;
  if (!token) return; // never resolve a spend without a minted token
  btn.disabled = true; // a double-click must never emit two generates
  settleCostConfirm({ token });
});

/* A "final video" run lives under whichever VIDEO tier key the operator chose
 * (standard/quality/ultra4k), never literally "hq" in the new flow — but legacy
 * jobs may still carry an "hq" run. Treat any non-draft run as a final run. */
function anyFinalRun(job) {
  const runs = (job && job.runs) || {};
  return Object.keys(runs).some((k) => k !== "draft");
}

function setSimpleRunning(running) {
  simple.running = running;
  $("#s-gen-draft").disabled = running || !simple.job;
  const draftDone = simple.job && simple.job.runs && simple.job.runs.draft;
  $("#s-gen-hq").disabled = running || !draftDone;
  if (!running && draftDone) $("#s-gen-hq").title = "";
}

function stopSimplePolls() {
  for (const quality of ["draft", "hq"]) {
    clearTimeout(simple.pollTimers[quality]);
    simple.pollTimers[quality] = null;
  }
  simple.running = false;
}

function simpleStageBar(stages) {
  return `<div class="s-stagebar">${(stages || []).map((st) =>
    `<span class="s-stage s-${esc(st.status)}" title="${esc(st.detail || "")}">${esc(st.stage)}</span>`).join("")}</div>`;
}

async function pollSimpleRun(quality, runId) {
  clearTimeout(simple.pollTimers[quality]);
  const statusBox = $(quality === "draft" ? "#s-draft-status" : "#s-hq-status");
  const videoBox = $(quality === "draft" ? "#s-draft-video" : "#s-hq-video");
  let run;
  try {
    run = await apiGet(`/api/runs/${encodeURIComponent(runId)}`);
  } catch (err) {
    statusBox.innerHTML = `<div class="banner banner-warn">This run belongs to a previous server session — its files are still on disk (see ui/data and the runs folder), but live status isn't available.</div>`;
    setSimpleRunning(false);
    return;
  }

  const banner = {
    running: `<div class="banner banner-info">Generating… the engine reports each stage below.</div>`,
    succeeded: `<div class="banner banner-ok">Done.</div>`,
    failed: `<div class="banner banner-error">FAILED — engine exited ${esc(run.returncode)}. Details below, shown verbatim.</div>`,
    refused: `<div class="banner banner-warn">The engine refused to run (spend gate). Nothing was spent.</div>`,
  }[run.status] || "";
  const musicWarn = run.music_warning
    ? `<div class="banner banner-warn"><strong>Music review needed:</strong> ${esc(simpleUserMessage(run.music_warning))}</div>` : "";
  const failure = run.status === "failed"
    ? `${run.manifest_failure ? `<pre class="code-block">${esc(JSON.stringify(run.manifest_failure, null, 2))}</pre>` : ""}
       ${run.stderr && run.stderr.trim() ? `<pre class="code-block">${esc(run.stderr)}</pre>` : ""}` : "";
  statusBox.innerHTML = `
    <div class="s-status">
      ${banner}${musicWarn}
      ${simpleStageBar(run.stages)}
      ${failure}
      <div class="actions">
        <button class="btn btn-small" data-simple-log="${esc(runId)}">Engine output</button>
        ${(run.reports || []).filter((r) => r.exists).map((r) =>
          `<button class="btn btn-small" data-view-report="${esc(r.path)}" data-report-label="${esc(r.label)}">${esc(r.label)}</button>`).join("")}
      </div>
    </div>`;
  const logBtn = statusBox.querySelector("[data-simple-log]");
  if (logBtn) logBtn.addEventListener("click", () =>
    openDrawer(`Engine output — ${runId}`, `<pre class="code-block tall">${esc(run.stdout_tail || "(no output)")}</pre>`));

  if (run.status === "running") {
    simple.pollTimers[quality] = setTimeout(() => pollSimpleRun(quality, runId), 2500);
    return;
  }
  setSimpleRunning(false);
  if (run.status === "succeeded" && run.final_video && run.final_video.exists) {
    videoBox.innerHTML = `
      <p class="mini-label">${quality === "draft" ? "Draft" : "Final"} video — ${esc(run.final_video.path)}</p>
      <video class="preview" controls preload="metadata" src="/api/media?path=${encodeURIComponent(run.final_video.path)}"></video>`;
    if (quality === "draft") {
      $("#s-gen-hq").disabled = false;
      $("#s-gen-hq").title = "";
      $("#s-final").scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  } else if (run.status === "succeeded") {
    videoBox.innerHTML = `<div class="banner banner-warn">Run succeeded but the final video was not found where expected.</div>`;
  }
}

/* ---- recent jobs ---- */
async function loadSimpleJobs() {
  try {
    const data = await apiGet("/api/simple/jobs");
    if (!data.jobs.length) { $("#s-recent").innerHTML = ""; return; }
    $("#s-recent").innerHTML = `<span class="mini-label">Recent</span>` + data.jobs.slice(0, 6).map((j) =>
      `<button class="btn btn-small" data-open-job="${esc(j.job_dir)}">${esc(j.slug)}</button>`).join("");
  } catch { $("#s-recent").innerHTML = ""; }
}

document.addEventListener("click", async (e) => {
  const openBtn = e.target.closest("[data-open-job]");
  if (!openBtn) return;
  try {
    const data = await apiGet(`/api/simple/job?dir=${encodeURIComponent(openBtn.dataset.openJob)}`);
    restoreSimpleImagesFromJob(data.job);
    setSimpleAspectRatio(data.job.aspect_ratio === "16:9" ? "16:9" : "9:16");
    simple.job = data.job;
    stopSimplePolls();
    renderSimpleReview(data); // real review from the server, not a fabricated valid:true
    $("#s-review").classList.remove("hidden");
    $("#s-draft").classList.remove("hidden");
    $("#s-final").classList.remove("hidden");
    $("#s-draft-status").innerHTML = "";
    $("#s-draft-video").innerHTML = "";
    $("#s-hq-status").innerHTML = "";
    $("#s-hq-video").innerHTML = "";
    const runs = data.job.runs || {};
    if (runs.draft) pollSimpleRun("draft", runs.draft.ui_run_id);
    // Poll the most recent FINAL (non-draft) run into the final-step slot,
    // whichever video tier produced it.
    const finalKeys = Object.keys(runs).filter((k) => k !== "draft");
    if (finalKeys.length) {
      const latest = finalKeys
        .map((k) => runs[k])
        .sort((a, b) => String(b.started_at || "").localeCompare(String(a.started_at || "")))[0];
      if (latest) pollSimpleRun("hq", latest.ui_run_id);
    }
    setSimpleRunning(false);
  } catch (err) { alert(simpleUserMessage(err.message)); }
});

/* ================================================================== */
/* SETTINGS (admin): API keys + draft/HQ models                        */
/* ================================================================== */
$("#btn-settings").addEventListener("click", openSettings);

// Registered ONCE (not per openSettings call) to avoid accumulating duplicate
// listeners that would multi-POST key saves. Acts only on the settings drawer's
// own controls, so it's inert in other drawers.
$("#drawer-body").addEventListener("click", async (e) => {
  const save = e.target.closest("[data-save-key]");
  const clear = e.target.closest("[data-clear-key]");
  if (!save && !clear) return;
  const feedback = $("#key-feedback");
  try {
    if (save) {
      const name = save.dataset.saveKey;
      const input = $(`#key-${CSS.escape(name)}`);
      await apiPost("/api/settings/key", { name, value: input ? input.value : "" });
    } else {
      await apiPost("/api/settings/key", { name: clear.dataset.clearKey, clear: true });
    }
    await loadHealth();
    openSettings(); // re-render with fresh presence chips
  } catch (err) {
    if (feedback) feedback.innerHTML = `<div class="banner banner-error">${esc(err.message)}</div>`;
  }
});

async function openSettings() {
  let data;
  try { data = await apiGet("/api/settings"); }
  catch (err) { openDrawer("Settings", `<div class="banner banner-error">${esc(err.message)}</div>`); return; }
  const s = data.settings;
  // The allow-list the storyboard image-model dropdown renders from (the backend
  // exposes it alongside the configured s.image_model). Fall back to the
  // configured model alone so the dropdown is never empty if the list is absent.
  const imageModelOptions = (Array.isArray(data.image_model_options) && data.image_model_options.length)
    ? data.image_model_options
    : [s.image_model].filter(Boolean);
  const keyRow = (name, label, purpose) => `
    <div class="key-row">
      <span class="key-name">${esc(label)}</span>
      <span class="cap-chip ${data.keys[name] ? "on" : "off"}">${data.keys[name] ? "configured" : "not set"}</span>
      <input type="password" id="key-${esc(name)}" placeholder="paste new key value" autocomplete="off">
      <button class="btn btn-small" data-save-key="${esc(name)}">Save</button>
      ${data.keys[name] ? `<button class="btn btn-small" data-clear-key="${esc(name)}">Clear</button>` : ""}
      <p class="micro" style="width:100%;margin:2px 0 0">${esc(purpose)}</p>
    </div>`;
  const dep = (label, on) => `<span class="cap-chip ${on ? "on" : "off"}">${esc(label)} ${on ? "✓" : "missing"}</span>`;
  openDrawer("Settings", `
    <div class="settings-section">
      <p class="mini-label">API keys</p>
      <p class="hint">Keys are stored in the server's <code>.env</code> and are <strong>write-only</strong>: this panel never displays a stored value, only whether one is set. The app runs without them — they unlock the paid stages.</p>
      ${keyRow("GEMINI_API_KEY", "Gemini", "Veo video generation, Lyria music, and AI document extraction.")}
      ${keyRow("ELEVENLABS_API_KEY", "ElevenLabs", "Voice conversion (presenter jobs only - optional).")}
      <div id="key-feedback"></div>
    </div>
    <div class="settings-section">
      <p class="mini-label">Engine python packages</p>
      <div class="key-row">
        ${dep("requests", data.python_deps.requests)}
        ${dep("python-dotenv", data.python_deps.dotenv)}
        ${dep("google-genai", data.python_deps.google_genai)}
      </div>
      <p class="micro">Live runs need these installed once: <code>pip install requests python-dotenv google-genai</code> (plus ffmpeg on PATH).</p>
    </div>
    <div class="settings-section">
      <p class="mini-label">Generation models (simple mode)</p>
      <div class="fields-grid">
        <div class="field"><label>Draft model</label><input id="set-draft-model" value="${esc(s.draft.model)}"></div>
        <div class="field"><label>Draft resolution</label>
          <select id="set-draft-res">${["720p", "1080p", "4k"].map((r) => `<option ${r === s.draft.resolution ? "selected" : ""}>${r}</option>`).join("")}</select></div>
        <div class="field"><label>High-quality model</label><input id="set-hq-model" value="${esc(s.hq.model)}"></div>
        <div class="field"><label>High-quality resolution</label>
          <select id="set-hq-res">${["720p", "1080p", "4k"].map((r) => `<option ${r === s.hq.resolution ? "selected" : ""}>${r}</option>`).join("")}</select></div>
        <div class="field"><label>Storyboard image model</label>
          <select id="set-image-model">${imageModelOptions.map((m) =>
            `<option ${m === s.image_model ? "selected" : ""}>${esc(m)}</option>`).join("")}</select></div>
      </div>
      <p class="micro">The storyboard image model renders the FREE preview reel in simple mode (free to the user — the business absorbs the cost). The user never picks an image tier.</p>
      <label style="display:flex;gap:8px;align-items:center;margin:10px 0;font-size:13px">
        <input type="checkbox" id="set-ai-extract" ${s.ai_extraction ? "checked" : ""}>
        Use AI (Gemini) to read documents in simple mode — one small text call per build
      </label>
      <div class="actions"><button class="btn btn-free btn-small" id="btn-save-models">Save settings</button><span id="models-feedback" class="mini"></span></div>
    </div>`);

  $("#btn-save-models").addEventListener("click", async () => {
    try {
      await apiPost("/api/settings/models", {
        draft: { model: $("#set-draft-model").value, resolution: $("#set-draft-res").value },
        hq: { model: $("#set-hq-model").value, resolution: $("#set-hq-res").value },
        image_model: $("#set-image-model").value,
        ai_extraction: $("#set-ai-extract").checked,
      });
      $("#models-feedback").textContent = "Saved.";
      await loadAppSettings();
    } catch (err) {
      $("#models-feedback").textContent = err.message;
    }
  });
}

/* ------------------------------------------------------------------ */
/* Init                                                                */
/* ------------------------------------------------------------------ */
setMode("simple");
loadHealth();
loadAppSettings();
loadSimpleTiers();
loadSimpleJobs();
updateConditionalForm();
updateStepper();
renderRail();
setInterval(loadHealth, 60000);
