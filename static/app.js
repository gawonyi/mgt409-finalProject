/* Hand Up! front end: Home → Classroom. Voice (TTS/STT) comes from voice.js; typing mode has full parity. */
const $ = (id) => document.getElementById(id);
const esc = (t) => String(t ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const ROLES = {
  consultant: ["Priya", "Consultant", "Structured, uses frameworks"],
  skeptic: ["Ben", "Skeptic", "Challenges assumptions"],
  practitioner: ["Carlos", "Practitioner", "Execution and real customers"],
  quant: ["Lena", "Quant", "Goes to the numbers"],
};
const ROLE_CHAR = ["brown", "dark", "blonde"];
const CUTS = {
  shared_prefix: "Same prompt + pack prefix first (cache-friendly)",
  batched_hands: "One batched hand-raise call per turn",
  recent_turns_only: "Send recent turns only",
  output_caps: "Output caps (prof ≤60, classmate ≤80 words)",
  compact_prev_summary: "Coach reads a compact previous summary",
};

const S = {
  courses: [], course: null, roles: ["consultant", "skeptic"], packId: null, confBefore: null,
  snap: null, played: 0, playing: false, advancedAt: null, handsTimer: null, typing: true,
};

async function api(path, body, isForm) {
  const opt = body === undefined ? {} : isForm
    ? { method: "POST", body }
    : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const r = await fetch(path, opt);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) {
    const d = j.detail;
    const err = new Error(typeof d === "string" ? d : d?.message || `HTTP ${r.status}`);
    err.gate = d?.gate;
    throw err;
  }
  return j;
}

/* ============================ Home ============================ */
async function loadCourses(selectId) {
  S.courses = await api("/api/courses");
  const keep = selectId || S.course?.id || S.courses[0]?.id;
  selectCourse(S.courses.find((c) => c.id === keep) || S.courses[0]);
}

function renderCourses() {
  $("courseList").innerHTML = S.courses.map((c) => `
    <div class="course-card ${c.id === S.course?.id ? "sel" : ""}" data-id="${esc(c.id)}">
      <span class="ic">📚</span>
      <div><b>${esc(c.name)}</b> · ${esc(c.professor?.name || "")}
        <small>${c.builtin ? "Sample course · " : ""}${(c.schedule || []).length} session(s)</small></div>
    </div>`).join("");
  $("courseList").querySelectorAll(".course-card").forEach((el) =>
    (el.onclick = () => selectCourse(S.courses.find((c) => c.id === el.dataset.id))));
}

function selectCourse(c) {
  S.course = c;
  S.packId = null;
  renderCourses();
  const sched = c?.schedule || [];
  $("sessionSel").innerHTML = sched.map((s, i) => `<option value="${i}">${esc(s.title)}</option>`).join("")
    || `<option value="">(no sessions — add one in Edit course)</option>`;
  onSession();
  const pol = c?.ai_policy || { state: "not_confirmed" };
  const label = { not_confirmed: "Not confirmed — case files are blocked", allowed: "Allowed (your statement, not verified approval)", not_allowed: "Not allowed — only your notes are used" }[pol.state];
  $("policyLine").innerHTML = `Course AI policy: <b>${label}</b>${pol.source_note ? ` · source: ${esc(pol.source_note)}` : ""}`;
  updateStart();
}

function currentSession() {
  return (S.course?.schedule || [])[+$("sessionSel").value];
}

function onSession() {
  const s = currentSession();
  $("questions").value = (s?.questions || []).join("\n");
  S.packId = null;
  $("gateOut").innerHTML = "";
  $("prepStatus").textContent = "";
  updateStart();
}
$("sessionSel").onchange = onSession;

function renderRoles() {
  $("roleList").innerHTML = Object.entries(ROLES).map(([k, [name, role, desc]]) => {
    const i = S.roles.indexOf(k);
    const ch = ROLE_CHAR[i >= 0 ? i : S.roles.length] || "brown";
    return `<div class="role ${i >= 0 ? "sel" : ""}" data-k="${k}">
      <img src="/static/img/sprites/${ch}_front.png" alt="">
      <div><b>${name}</b> · ${role}<small>${desc}</small></div></div>`;
  }).join("");
  $("roleList").querySelectorAll(".role").forEach((el) => (el.onclick = () => {
    const k = el.dataset.k;
    if (S.roles.includes(k)) { if (S.roles.length > 1) S.roles = S.roles.filter((r) => r !== k); }
    else if (S.roles.length < 3) S.roles.push(k);
    renderRoles();
  }));
}

function renderConfidence(id, onPick) {
  $(id).innerHTML = Array.from({ length: 10 }, (_, i) => `<button type="button" data-v="${i + 1}">${i + 1}</button>`).join("");
  $(id).querySelectorAll("button").forEach((b) => (b.onclick = () => {
    $(id).querySelectorAll("button").forEach((x) => x.classList.toggle("sel", x === b));
    onPick(+b.dataset.v);
  }));
}

function updateStart() {
  $("startClass").disabled = !(S.packId && S.confBefore);
  $("startClass").title = !S.packId ? "Prepare the session first" : !S.confBefore ? "Tap your confidence first" : "";
}

async function prepare({ notesOnly = false } = {}) {
  const s = currentSession();
  const fd = new FormData();
  fd.append("course", JSON.stringify(S.course));
  fd.append("questions", JSON.stringify($("questions").value.split("\n").map((q) => q.trim()).filter(Boolean)));
  fd.append("notes", $("notes").value);
  fd.append("use_demo", String(!!s?.case_file && !!S.course?.builtin));
  if (!notesOnly) {
    if ($("slidesFile").files[0]) fd.append("slides", $("slidesFile").files[0]);
    if ($("caseFile").files[0]) fd.append("case", $("caseFile").files[0]);
  }
  S.packId = null;
  updateStart();
  $("prepare").disabled = true;
  $("gateOut").innerHTML = "";
  $("prepStatus").className = "status-text";
  $("prepStatus").textContent = "Checking course AI policy… building Session Pack (≈10 s)";
  try {
    const p = await api("/api/prepare", fd, true);
    S.packId = p.pack_id;
    showGate(p.gate);
    $("prepStatus").textContent = `✓ Pack ready: ${p.pack.frameworks.length} frameworks · ${p.pack.questions.length} questions · ${p.pack.facts.length} facts · ${p.pack.takeaways.length} takeaways`;
  } catch (e) {
    showGate(e.gate);
    $("prepStatus").className = "status-text err";
    $("prepStatus").innerHTML = `${esc(e.message)} <button class="btn small" id="retryPrep">Retry</button>
      <button class="btn small" id="notesOnly">Continue with notes only</button>`;
    $("retryPrep").onclick = () => prepare();
    $("notesOnly").onclick = () => prepare({ notesOnly: true });
  } finally {
    $("prepare").disabled = false;
    updateStart();
  }
}

function showGate(gate) {
  $("gateOut").innerHTML = (gate || []).map((g) =>
    `<div class="${g.allowed ? "ok" : "no"}">${g.allowed ? "✓" : "⛔"} ${esc(g.label)}: ${esc(g.reason)}</div>`).join("");
}

$("prepare").onclick = () => prepare();
$("tryDemo").onclick = async () => {
  const demo = S.courses.find((c) => c.builtin) || S.courses[0];
  selectCourse(demo);
  $("sessionSel").value = String(demo.schedule.findIndex((s) => s.case_file));
  onSession();
  await prepare();
};

/* ---------- Course Editor ---------- */
function openEditor(course) {
  const f = $("courseForm");
  const c = course || { name: "", professor: { name: "", style: "", signature_moves: "", sliders: {} }, schedule: [], ai_policy: { state: "not_confirmed", source_note: "" } };
  f.dataset.id = course && !course.builtin ? course.id : "";
  f.name.value = c.name + (course?.builtin ? " (my copy)" : "");
  f.prof_name.value = c.professor?.name || "";
  f.style.value = c.professor?.style || "";
  f.signature_moves.value = c.professor?.signature_moves || "";
  for (const k of ["cold_call", "follow_up_pressure", "framework_emphasis", "evidence_demand", "warmth"])
    f[k].value = c.professor?.sliders?.[k] ?? 3;
  f.schedule.value = (c.schedule || []).map((s) => [s.title, ...(s.questions || [])].join("\n")).join("\n\n");
  f.querySelectorAll("[name=policy]").forEach((r) => (r.checked = r.value === (c.ai_policy?.state || "not_confirmed")));
  f.source_note.value = c.ai_policy?.source_note || "";
  f._base = c;
  $("courseEditor").showModal();
}
$("addCourse").onclick = () => openEditor(null);
$("editCourse").onclick = () => openEditor(S.course);
$("courseForm").onsubmit = async (e) => {
  const f = e.target;
  if (e.submitter?.value !== "save") return;
  const policy = f.querySelector("[name=policy]:checked")?.value || "not_confirmed";
  if (policy === "allowed" && !f.source_note.value.trim()) {
    e.preventDefault();
    alert("Policy 'Allowed' needs a source note (who said so, and where).");
    return;
  }
  const base = f._base || {};
  const schedule = f.schedule.value.split(/\n\s*\n/).map((b) => b.split("\n").map((x) => x.trim()).filter(Boolean))
    .filter((l) => l.length).map(([title, ...questions], i) => {
      const old = (base.schedule || []).find((s) => s.title === title) || {};
      return { ...old, session: old.session || `s${i + 1}`, title, questions };
    });
  const course = {
    id: f.dataset.id || undefined,
    name: f.name.value.trim(),
    professor: {
      name: f.prof_name.value.trim(), style: f.style.value.trim(), signature_moves: f.signature_moves.value.trim(),
      sliders: Object.fromEntries(["cold_call", "follow_up_pressure", "framework_emphasis", "evidence_demand", "warmth"].map((k) => [k, +f[k].value])),
    },
    schedule,
    ai_policy: { state: policy, source_note: f.source_note.value.trim() },
  };
  const saved = await api("/api/courses", course);
  await loadCourses(saved.id);
};

/* ============================ Classroom ============================ */
$("startClass").onclick = async () => {
  $("startClass").disabled = true;
  try {
    setMode(!!S.homeTyping, S.homeReason || "");
    const cost_cuts = Object.fromEntries(Object.keys(CUTS).map((k) => [k, $("cut_" + k).checked]));
    const snap = await api("/api/session", { pack_id: S.packId, roles: S.roles, confidence_before: S.confBefore,
      typing_mode: S.typing, cost_cuts });
    $("home").hidden = true;
    $("classroom").hidden = false;
    $("chipCourse").hidden = $("chipSession").hidden = $("chipTurn").hidden = false;
    $("chipCourse").innerHTML = `<b>${esc(S.course.name)}</b> · ${esc(S.course.professor?.name || "")}`;
    $("chipSession").textContent = currentSession()?.title || "Session";
    await Scene.build($("scene"), {
      prof: { name: snap.prof_name },
      me: { name: "You", character: "brunette" },
      classmates: snap.classmates.map((c) => ({ id: c.id, name: c.name, character: c.character })),
    });
    S.played = 0;
    render(snap);
  } catch (e) {
    alert(e.message);
    updateStart();
  }
};

let chain = Promise.resolve();
function act(action, extra = {}) {
  chain = chain.then(async () => {
    if (!S.snap || S.snap.waiting === "end" && action !== "end") return;
    try { render(await api(`/api/session/${S.snap.id}/act`, { action, ...extra })); }
    catch (e) { showError(e.message); }
  });
  return chain;
}

function showError(msg) {
  $("whoName").textContent = "Hand Up!";
  $("say").textContent = "Something went wrong: " + msg;
}

const nameOf = (snap, id) => id === "me" ? "You" : id === "prof" ? snap.prof_name
  : snap.classmates.find((c) => c.id === id)?.name || id;
const charOf = (snap, id) => id === "me" ? "brunette" : id === "prof" ? "prof"
  : snap.classmates.find((c) => c.id === id)?.character;

function roleLabel(snap, line) {
  if (line.speaker === "prof") {
    const t = line.meta?.target ? nameOf(snap, line.meta.target) : "";
    return { ask: "asks", rephrase: "rephrases", follow_up: `follows up with ${t}`, call_on: `calls on ${t}`,
      wrap_up: "wraps up" }[line.kind] || "";
  }
  if (line.speaker === "me") return "";
  const c = snap.classmates.find((x) => x.id === line.speaker);
  return c ? ROLES[c.role][1] : "";
}

function render(snap) {
  S.snap = snap;
  $("chipTurn").innerHTML = `Turn <b>${snap.turn}</b> / ${snap.turn_cap}`;
  const pct = Math.min(100, (snap.spent_usd / 0.5) * 100);
  $("costText").textContent = `$${snap.spent_usd.toFixed(3)} / $0.50`;
  $("costBar").style.width = pct + "%";
  $("costBar").classList.toggle("warn", snap.spent_usd >= 0.4);
  renderHistory(snap);
  renderTrace(snap);
  if (!$("costPanel").hidden) loadCosts();
  Scene.setHands(snap.hands, snap.my_hand);
  $("hand").classList.toggle("on", snap.my_hand);
  $("hand").textContent = snap.my_hand ? "✋ Hand is up" : "✋ Hand Up!";
  const up = Object.values(snap.hands).filter(Boolean).length + (snap.my_hand ? 1 : 0);
  $("pillHands").hidden = !up;
  $("pillHands").textContent = `✋ ${up} hand${up === 1 ? "" : "s"} up`;
  const flag = snap.flags.no_hands ? "No hands, so…" : snap.flags.cold_call ? "Cold call!" : snap.flags.starvation ? "Your turn — you waited" : "";
  $("pillFlag").hidden = !flag;
  $("pillFlag").textContent = flag;
  if (!S.playing) playQueue();
}

async function playQueue() {
  S.playing = true;
  while (S.played < S.snap.lines.length) {
    const line = S.snap.lines[S.played++];
    if (line.speaker === "me") { renderHistory(S.snap); continue; } // my own lines are already on screen
    renderHistory(S.snap);
    if (line.kind === "call_on" && line.meta?.reason === "cold_call") Scene.coldCall();
    await playLine(S.snap, line);
  }
  S.playing = false;
  onIdle();
}

/* One line: dialogue box typed out in sync with TTS; the next step starts on the TTS end, error,
   cancel or safety timeout (voice.js), or after a short reading pause when voice output is off. */
function playLine(snap, line) {
  setDialog("npc");
  Scene.setSpeaker(line.speaker);
  const character = charOf(snap, line.speaker);
  $("face").src = Scene.portrait(character);
  $("whoName").textContent = line.name;
  $("whoRole").textContent = roleLabel(snap, line);
  $("nextHint").textContent = "click ▸ show all";
  const text = line.text;
  const words = text.split(/\s+/).length;
  const tts = Voice.enabled();
  const step = tts ? Math.max(1, Math.round(text.length / (Voice.estimateMs(text, character) / 30))) : 3;
  return new Promise((resolve) => {
    let i = 0, done = false, typedAll = false, spoken = !tts;
    const finish = () => {
      if (!done && typedAll && spoken) { done = true; setTimeout(resolve, tts ? 250 : 700 + words * 25); }
    };
    const showAll = () => { i = text.length; $("say").textContent = text; typedAll = true; clearInterval(timer); finish(); };
    const timer = setInterval(() => {
      i += step;
      $("say").innerHTML = esc(text.slice(0, i)) + '<span class="caret"></span>';
      if (i >= text.length) showAll();
    }, 30);
    $("dialog").onclick = showAll; // shows the whole line; the voice keeps going
    if (tts) Voice.speakText(text, character).then(() => { spoken = true; showAll(); });
  });
}

function setDialog(mode) {
  const me = mode === "me";
  $("dialog").classList.toggle("me", me);
  $("myText").hidden = $("myButtons").hidden = !me;
  $("nextHint").hidden = me;
  $("pass").disabled = !me;
  $("pillTurn").hidden = !me;
  if (!me) $("dialog").onclick = null;
}

function onIdle() {
  const snap = S.snap;
  const key = snap.lines.length + ":" + snap.waiting + ":" + snap.state;
  clearTimeout(S.handsTimer);
  if (snap.waiting === "audio") {
    if (S.advancedAt !== key) { S.advancedAt = key; act("advance", { meta: { at: snap.lines.length } }); }
  } else if (snap.waiting === "hands") {
    if (S.advancedAt === key) return;
    S.advancedAt = key;
    Scene.setSpeaker(null);
    $("whoName").textContent = snap.prof_name;
    $("whoRole").textContent = "is waiting for hands";
    $("say").textContent = "Hands open… raise yours with Space or the Hand Up! button.";
    S.handsTimer = setTimeout(() => act("advance", { meta: { at: snap.lines.length } }), 3500);
  } else if (snap.waiting === "me") {
    myTurn(snap);
  } else if (snap.waiting === "end") {
    showEnd(snap);
  }
}

function myTurn(snap) {
  if (S.advancedAt === "me:" + snap.lines.length) return;
  S.advancedAt = "me:" + snap.lines.length;
  setDialog("me");
  Scene.setSpeaker("me");
  $("face").src = Scene.portrait("brunette");
  $("whoName").textContent = "You";
  $("whoRole").textContent = "";
  $("say").textContent = "";
  $("myText").value = "";
  $("rerecord").hidden = true;
  if (!S.typing && Voice.startTurn((t) => ($("myText").value = t))) {
    $("listening").hidden = false;
    $("rerecord").hidden = false;
    $("rerecord").disabled = false;
    $("myText").placeholder = "Speak now… your words appear here (you can edit once before sending)";
  } else {
    $("myText").placeholder = "Type your answer… (Enter to send, Shift+Enter for a new line)";
    $("myText").focus();
  }
}

$("rerecord").onclick = () => {
  if (Voice.rerecord()) $("rerecord").disabled = true; // re-record once
};

function setMode(typing, reason = "") {
  S.typing = typing;
  Voice.setListen(!typing, reason);
  $("modeHint").textContent = typing
    ? `Space = raise hand · ⌨ typing mode${reason ? " — " + reason : ""}`
    : "Space = raise hand · 🎤 voice mode (mic on only during your turn)";
}
Voice.onFallback((reason) => {
  setMode(true, reason);
  $("listening").hidden = true;
  $("rerecord").hidden = true;
  $("myText").placeholder = reason + " Type your answer instead.";
  $("myText").focus();
});

$("ttsBtn").onclick = () => {
  const on = !Voice.enabled();
  Voice.setTTS(on);
  $("ttsBtn").textContent = on ? "🔊 Voice on" : "🔇 Voice off";
};

async function checkMic(ask) {
  const forced = $("forceTyping").checked;
  if (!Voice.hasSTT) {
    $("micCheck").textContent = "Typing mode — this browser has no speech recognition (use Chrome for voice)";
    $("micCheck").className = "mic-check";
    $("micBtn").hidden = true;
    return setHomeMode(true, "no speech recognition in this browser");
  }
  if (forced) {
    $("micCheck").textContent = "Typing mode (your choice)";
    $("micCheck").className = "mic-check";
    return setHomeMode(true, "");
  }
  if (!ask) {
    $("micCheck").textContent = "Voice available — press Check mic";
    return setHomeMode(false, "");
  }
  const r = await Voice.micCheck();
  $("micCheck").textContent = r.ok ? "🎤 Voice ready" : "Typing mode — " + r.reason;
  $("micCheck").className = "mic-check" + (r.ok ? " voice" : "");
  setHomeMode(!r.ok, r.ok ? "" : r.reason);
}
function setHomeMode(typing, reason) { S.homeTyping = typing; S.homeReason = reason; }
$("micBtn").onclick = () => checkMic(true);
$("forceTyping").onchange = () => checkMic(false);

function sendAnswer() {
  const t = $("myText").value.trim();
  if (!t || S.snap?.waiting !== "me") return;
  const meta = S.typing ? { mode: "typing", words: t.split(/\s+/).length } : Voice.turnMeta(t);
  Voice.stopTurn();
  $("listening").hidden = true;
  setDialog("npc");
  act("answer", { text: t, meta });
}
$("send").onclick = sendAnswer;
$("myText").onkeydown = (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendAnswer(); } };
$("pass").onclick = () => { Voice.stopTurn(); $("listening").hidden = true; setDialog("npc"); act("pass"); };
$("hand").onclick = () => act(S.snap?.my_hand ? "lower" : "raise");
$("endClass").onclick = () => { Voice.cancel(); $("listening").hidden = true; act("end"); };
document.addEventListener("keydown", (e) => {
  if (e.code !== "Space" || $("classroom").hidden) return;
  if (["TEXTAREA", "INPUT", "SELECT", "BUTTON"].includes(e.target.tagName)) return;
  e.preventDefault();
  if (S.snap?.waiting !== "me") $("hand").click();
});

function renderHistory(snap) {
  // only lines that have started playing (no spoilers before the dialogue box types them)
  $("log").innerHTML = snap.lines.slice(0, S.played).map((l) => {
    const cls = l.speaker === "prof" ? "prof" : l.speaker === "me" ? "me" : "";
    const to = l.meta?.target ? ` → ${nameOf(snap, l.meta.target).toUpperCase()}` : "";
    return `<div class="entry ${cls}"><b>${esc(l.name.toUpperCase())}${esc(to)}</b>${esc(l.text)}`
      + (l.cited_ids?.length ? ` <span class="cite">[${esc(l.cited_ids.join(", "))}]</span>` : "") + `</div>`;
  }).join("");
  $("log").scrollTop = $("log").scrollHeight;
}
$("histToggle").onclick = () => {
  $("history").classList.toggle("closed");
  document.querySelector(".layout").classList.toggle("hist-closed");
  setTimeout(Scene.fit, 0);
};

function renderTrace(snap) {
  $("traceBody").innerHTML = snap.trace.slice().reverse().map((t) => {
    if (t.event === "llm")
      return `<div>T${t.turn} <b>${esc(t.agent)}</b> ${esc(t.summary)} · in ${t.input} (cached ${t.cached}) · out ${t.output} · $${t.cost.toFixed(5)} · ${t.latency}s</div>`;
    const { t: _, turn, state, event, ...rest } = t;
    return `<div>T${turn} ${esc(state)} · <b>${esc(event)}</b> ${esc(JSON.stringify(rest))}</div>`;
  }).join("");
}
$("traceLink").onclick = (e) => { e.preventDefault(); $("costPanel").hidden = true; $("tracePanel").hidden = false; };
$("costLink").onclick = (e) => { e.preventDefault(); $("tracePanel").hidden = true; $("costPanel").hidden = false; loadCosts(); };
$("costClose").onclick = () => ($("costPanel").hidden = true);

const usd = (x) => "$" + Number(x || 0).toFixed(4);
const n = (x) => Number(x || 0).toLocaleString();
async function loadCosts() {
  const c = await api(`/api/costs?sid=${encodeURIComponent(S.snap?.id || "")}`);
  const row = (label, t) => `<tr><td>${label}</td><td>${n(t.input)}</td><td>${n(t.cached)}</td><td>${n(t.output)}</td><td>${usd(t.cost)}</td></tr>`;
  const head = "<tr><th></th><th>Input</th><th>Cached</th><th>Output</th><th>$</th></tr>";
  const ses = c.this_session;
  const p = c.projections;
  $("costBody").innerHTML = `
    <h4>This turn (T${c.this_turn?.turn ?? "–"}) and this session</h4>
    <table class="ctable">${head}${c.this_turn ? row("This turn", c.this_turn) : ""}${ses ? row("This session", ses.totals) : ""}</table>
    <h4>This session by agent</h4>
    <table class="ctable">${head}${ses ? Object.entries(ses.by_agent).map(([a, t]) => row(a, t)).join("") : ""}</table>
    <p class="sub">Cache share this session: ${ses ? Math.round(ses.totals.cache_share * 100) : 0}% of input (measured, not guaranteed).
      Budget: hard cap $${c.budget.hard_cap.toFixed(2)} = $${c.budget.discussion.toFixed(2)} discussion + $${c.budget.reserve.toFixed(2)} reserved for wrap-up and evaluation.</p>
    <h4>Projections (3 sessions/week × 4.3 weeks)</h4>
    <table class="ctable"><tr><th>Scale</th><th>Sessions</th><th>$ measured avg</th><th>$ 14-turn est.</th></tr>
      ${p.rows.map((r) => `<tr><td>${esc(r.scale)}</td><td>${n(r.sessions)}</td><td>$${r.usd}</td><td>${r.usd_14_turns != null ? "$" + r.usd_14_turns : ""}</td></tr>`).join("")}</table>
    <p class="sub">${esc(p.note)} Prices per 1M tokens: input $${p.prices_per_1m?.input ?? "–"}, cached $${p.prices_per_1m?.cached_input ?? "–"}, output $${p.prices_per_1m?.output ?? "–"}.</p>
    <h4>Cost cuts in this session</h4>
    <div class="sub">${Object.entries(c.cost_cuts || {}).map(([k, v]) => `${v ? "✓" : "✗"} ${esc(CUTS[k] || k)}`).join("<br>")}</div>`;
}
$("traceClose").onclick = () => ($("tracePanel").hidden = true);

function showEnd(snap) {
  Scene.setSpeaker(null);
  setDialog("npc");
  $("endClass").disabled = $("hand").disabled = true;
  const card = $("endCard");
  card.hidden = false;
  if (snap.state === "BUDGET_ERROR_END") {
    const mine = snap.lines.filter((l) => l.speaker === "me" && l.kind === "answer");
    card.innerHTML = `<h3>Class ended early</h3><p class="sub">${esc(snap.end_reason)}</p>
      <p><b>Evaluation unavailable</b> (no more model calls were made).</p>
      <p><b>Takeaways</b></p><ul>${snap.takeaways.map((t) => `<li>[${esc(t.id)}] ${esc(t.text)}</li>`).join("")}</ul>
      <p><b>Your saved lines</b></p><ul>${mine.map((l) => `<li>${esc(l.text)}</li>`).join("") || "<li>(none)</li>"}</ul>`;
  } else {
    const why = { end_class: "you ended the class", "turn cap": "14 turns reached", "questions done": "all questions covered" }[snap.end_reason] || snap.end_reason;
    card.innerHTML = `<h3>Class is over — ${esc(why)}</h3>
      <button class="btn primary" id="toEval">See my evaluation ▸</button>`;
    $("toEval").onclick = () => window.showEvaluation ? window.showEvaluation(snap) : alert("Evaluation comes in step 6.");
  }
}

/* ============================ boot ============================ */
renderRoles();
$("cutList").innerHTML = Object.entries(CUTS).map(([k, label]) =>
  `<label class="check"><input type="checkbox" id="cut_${k}" checked> ${esc(label)}</label>`).join("");
renderConfidence("confBefore", (v) => { S.confBefore = v; updateStart(); });
loadCourses().catch((e) => ($("prepStatus").textContent = e.message));
checkMic(false);
Scene.load();
