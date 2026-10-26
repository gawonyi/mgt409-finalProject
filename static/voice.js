/* Voice layer (browser only, no paid audio API).
   TTS: speechSynthesis, one natural voice + rate per character. It is OFF by default (the student's
   own voice is the point; AI lines show as a typed script) and can be switched on in Home or class.
   speakText() resolves on the utterance end, error OR cancel, or a safety timeout (estimated
   duration + 3 s), so voices never overlap and the class never freezes.
   STT: Web Speech API SpeechRecognition, on only during my turn. Any recognition error or a
   missing API switches to typing mode with a short reason (full parity).
   Hand Up! never records or uploads audio; the browser's speech service may process it. */
const Voice = (() => {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const synth = window.speechSynthesis;
  // preferred natural voices per character (macOS, Chrome/Google, Windows/Edge names); pitch stays 1
  const PROFILE = {
    prof: { rate: 0.97, prefer: ["Daniel", "Google UK English Male", "Microsoft Guy", "Rishi", "Arthur", "Aaron"] },
    brown: { rate: 1.03, prefer: ["Samantha", "Google US English", "Microsoft Aria", "Ava", "Allison"] },
    dark: { rate: 1.0, prefer: ["Karen", "Google UK English Female", "Microsoft Jenny", "Serena", "Kate"] },
    blonde: { rate: 1.05, prefer: ["Moira", "Tessa", "Microsoft Sonia", "Fiona", "Zoe"] },
    brunette: { rate: 1.0, prefer: ["Samantha", "Google US English", "Microsoft Aria", "Ava"] },
  };
  // novelty / robotic macOS voices are never picked
  const NOVELTY = /^(Albert|Bad News|Bahh|Bells|Boing|Bubbles|Cellos|Good News|Jester|Organ|Superstar|Trinoids|Whisper|Wobble|Zarvox|Fred|Junior|Ralph|Kathy|Grandma|Grandpa|Eddy|Flo|Reed|Rocko|Sandy|Shelley)\b/i;
  const TTS_KEY = "handup.tts";
  let savedTTS = false;
  try { savedTTS = localStorage.getItem(TTS_KEY) === "on"; } catch { /* storage blocked: default off */ }
  const st = {
    tts: !!synth && savedTTS, listen: !!SR, reason: SR ? "" : "This browser has no speech recognition (use Chrome for voice).",
    rec: null, active: false, finalText: "", t0: null, t1: null, rerecords: 0, onFallback: null,
  };
  const chosen = {}; // character → voice, so each character keeps one voice

  function naturalVoices() {
    const all = synth ? synth.getVoices() : [];
    const en = all.filter((x) => /^en(-|_|$)/i.test(x.lang) && !NOVELTY.test(x.name));
    return en.length ? en : all.filter((x) => !NOVELTY.test(x.name));
  }
  if (synth) synth.onvoiceschanged = () => { for (const k in chosen) delete chosen[k]; };

  function voiceFor(character) {
    if (chosen[character] !== undefined) return chosen[character];
    const vs = naturalVoices();
    // class speakers get distinct voices; "brunette" (me, only for ▶ Play) may share one
    const taken = character === "brunette" ? new Set()
      : new Set(Object.entries(chosen).filter(([k, v]) => v && k !== "brunette").map(([, v]) => v.name));
    const byName = (n) => vs.find((v) => v.name === n || v.name.startsWith(n + " ") || v.name.startsWith(n + " ("));
    const p = PROFILE[character] || PROFILE.prof;
    let v = p.prefer.map(byName).find((x) => x && !taken.has(x.name))
      || vs.find((x) => /Enhanced|Premium|Natural|Google|Siri/i.test(x.name) && !taken.has(x.name))
      || vs.find((x) => !taken.has(x.name)) || null;
    chosen[character] = v;
    return v;
  }

  /* ---------- TTS ---------- */
  // force = true plays even when voice output is off (the ▶ Play button on polished lines)
  function speakText(text, character = "prof", { force = false } = {}) {
    return new Promise((resolve) => {
      if (!synth || !text || (!st.tts && !force)) return resolve("skipped");
      const p = PROFILE[character] || PROFILE.prof;
      const words = text.split(/\s+/).length;
      const estMs = (words / (2.6 * p.rate)) * 1000; // ~156 wpm at rate 1
      let done = false;
      const finish = (why) => { if (!done) { done = true; clearTimeout(timer); resolve(why); } };
      const timer = setTimeout(() => { synth.cancel(); finish("timeout"); }, estMs + 3000);
      try {
        const u = new SpeechSynthesisUtterance(text.replace(/\[[A-Z][\w-]*\]/g, "")); // don't read IDs
        const v = voiceFor(character);
        if (v) { u.voice = v; u.lang = v.lang; }
        u.pitch = 1;
        u.rate = p.rate;
        u.onend = () => finish("end");
        u.onerror = () => finish("error"); // also fires on cancel in Chrome
        if (synth.speaking || synth.pending) {
          synth.cancel(); // Chrome can drop an utterance queued right after cancel(); wait a beat
          setTimeout(() => synth.speak(u), 60);
        } else {
          synth.speak(u);
        }
      } catch (e) {
        finish("error");
      }
    });
  }

  const estimateMs = (text, character) => {
    const p = PROFILE[character] || PROFILE.prof;
    return (text.split(/\s+/).length / (2.6 * p.rate)) * 1000;
  };

  /* ---------- STT ---------- */
  function fallback(reason) {
    st.listen = false;
    st.reason = reason;
    stopTurn();
    st.onFallback?.(reason);
  }

  function startRec() {
    const rec = new SR();
    rec.lang = "en-US";
    rec.continuous = true;
    rec.interimResults = true;
    let base = st.finalText;
    rec.onspeechstart = () => { if (!st.t0) st.t0 = performance.now(); };
    rec.onresult = (e) => {
      if (!st.t0) st.t0 = performance.now();
      st.t1 = performance.now();
      let fin = "", interim = "";
      for (let i = 0; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) fin += r[0].transcript; else interim += r[0].transcript;
      }
      st.finalText = (base + " " + fin).trim();
      st.onText?.((st.finalText + " " + interim).trim());
    };
    rec.onspeechend = () => { st.t1 = performance.now(); };
    rec.onerror = (e) => {
      if (e.error === "no-speech" || e.error === "aborted") return; // keep the turn open
      const why = {
        "not-allowed": "Microphone permission was denied.",
        "service-not-allowed": "Speech service is not allowed in this browser.",
        "audio-capture": "No microphone was found.",
        network: "The browser's speech service is unreachable.",
      }[e.error] || `Speech recognition error: ${e.error}.`;
      fallback(why + " Switched to typing mode.");
    };
    rec.onend = () => { // Chrome stops after silence; restart while it is still my turn
      if (st.active && st.rec === rec) { base = st.finalText; try { rec.start(); } catch { /* ignore */ } }
    };
    st.rec = rec;
    try { rec.start(); } catch (e) { fallback("Could not start speech recognition. Switched to typing mode."); }
  }

  function startTurn(onText) {
    if (!st.listen) return false;
    st.onText = onText;
    st.finalText = "";
    st.t0 = st.t1 = null;
    st.rerecords = 0;
    st.active = true;
    startRec();
    return true;
  }

  function rerecord() {
    if (!st.active || st.rerecords >= 1) return false;
    st.rerecords += 1;
    const old = st.rec;
    st.rec = null;
    try { old?.abort(); } catch { /* ignore */ }
    st.finalText = "";
    st.t0 = st.t1 = null;
    st.onText?.("");
    startRec();
    return true;
  }

  function stopTurn() {
    st.active = false;
    const r = st.rec;
    st.rec = null;
    try { r?.abort(); } catch { /* ignore */ }
  }

  /* WPM = words in my final transcript ÷ (speech end − speech start); approximate */
  function turnMeta(finalText) {
    const words = finalText.trim().split(/\s+/).filter(Boolean).length;
    const ms = st.t0 && st.t1 ? st.t1 - st.t0 : null;
    const spoke = !!st.t0;
    return {
      mode: spoke ? "voice" : "typing",
      words,
      speech_ms: spoke ? Math.round(ms) : null,
      wpm: spoke && ms > 1500 ? Math.round(words / (ms / 60000)) : null,
      rerecorded: st.rerecords,
      edited: spoke && finalText.trim() !== st.finalText.trim(),
    };
  }

  async function micCheck() {
    if (!SR) return { ok: false, reason: st.reason };
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((t) => t.stop()); // permission check only; nothing is recorded
      st.listen = true;
      st.reason = "";
      return { ok: true };
    } catch (e) {
      st.listen = false;
      st.reason = "Microphone permission was denied or no mic was found.";
      return { ok: false, reason: st.reason };
    }
  }

  return {
    hasSTT: !!SR,
    enabled: () => st.tts,
    hasTTS: !!synth,
    setTTS: (on) => {
      st.tts = on && !!synth;
      if (!on) synth?.cancel();
      try { localStorage.setItem(TTS_KEY, st.tts ? "on" : "off"); } catch { /* per-viewer convenience only */ }
    },
    voiceName: (character) => voiceFor(character)?.name || "browser default",
    listenEnabled: () => st.listen,
    setListen: (on, reason = "") => { st.listen = on && !!SR; st.reason = reason; },
    reason: () => st.reason,
    onFallback: (fn) => (st.onFallback = fn),
    speakText, estimateMs, startTurn, rerecord, stopTurn, turnMeta, micCheck,
    canRerecord: () => st.active && st.rerecords < 1,
    cancel: () => { synth?.cancel(); stopTurn(); },
  };
})();
window.Voice = Voice;
