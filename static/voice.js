/* Voice layer (browser only, no paid audio API).
   TTS: speechSynthesis, one voice/pitch/rate per character. speak() resolves on the utterance
   end, error OR cancel, or a safety timeout (estimated duration + 3 s), so voices never overlap
   and the class never freezes.
   STT: Web Speech API SpeechRecognition, on only during my turn. Any recognition error or a
   missing API switches to typing mode with a short reason (full parity).
   Hand Up! never records or uploads audio; the browser's speech service may process it. */
const Voice = (() => {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const synth = window.speechSynthesis;
  const PROFILE = { // pitch, rate, preferred voice index among English voices
    prof: { pitch: 0.85, rate: 0.98, pick: 0 },
    brown: { pitch: 1.05, rate: 1.05, pick: 1 },
    dark: { pitch: 0.75, rate: 1.0, pick: 2 },
    blonde: { pitch: 1.25, rate: 1.08, pick: 3 },
    brunette: { pitch: 1.1, rate: 1.0, pick: 4 },
  };
  const st = {
    tts: !!synth, listen: !!SR, reason: SR ? "" : "This browser has no speech recognition (use Chrome for voice).",
    rec: null, active: false, finalText: "", t0: null, t1: null, rerecords: 0, onFallback: null,
  };

  function englishVoices() {
    const v = synth ? synth.getVoices().filter((x) => /^en(-|_|$)/i.test(x.lang)) : [];
    return v.length ? v : synth ? synth.getVoices() : [];
  }
  if (synth) synth.onvoiceschanged = () => englishVoices();

  /* ---------- TTS ---------- */
  function speakText(text, character = "prof") {
    return new Promise((resolve) => {
      if (!st.tts || !text) return resolve("skipped");
      const p = PROFILE[character] || PROFILE.prof;
      const words = text.split(/\s+/).length;
      const estMs = (words / (2.6 * p.rate)) * 1000; // ~156 wpm at rate 1
      let done = false;
      const finish = (why) => { if (!done) { done = true; clearTimeout(timer); resolve(why); } };
      const timer = setTimeout(() => { synth.cancel(); finish("timeout"); }, estMs + 3000);
      try {
        const u = new SpeechSynthesisUtterance(text.replace(/\[[A-Z][\w-]*\]/g, "")); // don't read IDs
        const vs = englishVoices();
        if (vs.length) u.voice = vs[p.pick % vs.length];
        u.pitch = p.pitch;
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
    setTTS: (on) => { st.tts = on && !!synth; if (!on) synth?.cancel(); },
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
