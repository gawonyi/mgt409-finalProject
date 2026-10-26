/* Screen 3 — Evaluation: baseline (first session) or change vs the PREVIOUS session only. */
(() => {
  const STAT_LABELS = [
    ["hands_raised", "Hands raised"], ["times_spoken", "Times spoken"],
    ["speaking_time_s", "Speaking time (s)"], ["wpm_approx", "WPM (approx.)"],
  ];
  const arrow = (d) => d == null || d === 0 ? "" :
    `<span class="delta ${d > 0 ? "up" : "down"}">${d > 0 ? "↑" : "↓"} ${Math.abs(d)}</span>`;

  async function showEvaluation(snap) {
    $("classroom").hidden = true;
    $("chipTurn").hidden = true;
    const root = $("evaluation");
    root.hidden = false;
    window.scrollTo(0, 0);
    root.innerHTML = `<div class="card pad"><h2>Your evaluation</h2><p class="sub">The Coach is reviewing your lines… (≈15 s)</p></div>`;
    let v;
    try {
      v = await api(`/api/session/${snap.id}/evaluate`, {});
    } catch (e) {
      root.innerHTML = `<div class="card pad"><h2>Evaluation unavailable</h2><p>${esc(e.message)}</p>${homeBtn()}</div>`;
      return bindHome();
    }
    root.innerHTML = render(v, snap);
    bindHome();
    root.querySelectorAll("[data-play]").forEach((b) =>
      (b.onclick = () => Voice.speakText(b.dataset.play, "brunette", { force: true })));
    renderConfidence("confAfter", async (n) => {
      const r = await api(`/api/session/${snap.id}/confidence`, { after: n });
      $("confTrend").innerHTML = trend(r.history);
    });
    if (v.confidence_after) $("confAfter").querySelector(`[data-v="${v.confidence_after}"]`)?.classList.add("sel");
  }

  function homeBtn() { return `<button class="btn primary" id="toHome">Back to Home</button>`; }
  function bindHome() { $("toHome").onclick = () => location.reload(); }

  function trend(history) {
    if (!history?.length) return "";
    return "Confidence across sessions: " + history.map((h) => `${h.before ?? "–"}→${h.after ?? "–"}`).join(" · ");
  }

  function render(v, snap) {
    const first = v.first_session;
    const head = `<div class="card pad eval-head">
      <div><h2>${first ? "Baseline — your first session in this course" : "Compared with your previous session"}</h2>
      <p class="sub">${first ? "Next time you will see how these numbers change." :
        "AI-evaluated trend: questions differ between sessions, so a higher score is not proof of skill gain."}</p></div>
      <div class="sub">Session cost $${v.spent_usd.toFixed(3)}</div></div>`;

    const d = v.deltas?.stats || {};
    const stats = `<div class="stat-row">${STAT_LABELS.map(([k, label]) => `<div class="card stat">
      <b>${v.stats[k] ?? "–"}</b>${first ? "" : arrow(d[k])}<span>${label}${v.stats[k] == null ? " · voice only" : ""}</span></div>`).join("")}</div>`;

    if (!v.available) {
      const mine = snap.lines.filter((l) => l.speaker === "me" && l.kind === "answer");
      return head + stats + `<div class="card pad"><h2>Evaluation unavailable</h2><p class="sub">${esc(v.reason)}</p>
        <h3>Takeaways</h3><ul>${(snap.takeaways || []).map((t) => `<li>[${esc(t.id)}] ${esc(t.text)}</li>`).join("")}</ul>
        <h3>Your saved lines</h3><ul>${mine.map((l) => `<li>${esc(l.text)}</li>`).join("") || "<li>(none)</li>"}</ul>
        </div>${confidenceCard(v)}${homeBtn()}`;
    }

    const ev = v.evaluation;
    const ds = v.deltas?.scores || {};
    const rubric = ev.scores.length ? `<div class="card pad"><h2>Rubric <span class="sub">1–5 · from the course syllabus</span></h2>
      ${ev.scores.map((s) => `<div class="rubric-row"><div class="rubric-name">${esc(s.criterion)}</div>
        <div class="rubric-bar"><i style="width:${s.score * 20}%"></i></div>
        <b>${s.score}</b>${first ? "" : arrow(ds[s.criterion])}
        <div class="rubric-reason">${esc(s.reason)}</div></div>`).join("")}</div>` : "";

    const prevBlock = !first && ev.vs_previous?.length ? `<div class="card pad"><h2>Last session's “needs work” — did it improve?</h2>
      <ul>${ev.vs_previous.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
      <p class="sub">Last time: ${(v.previous?.needs_work || []).map(esc).join(" · ")}</p></div>` : "";

    const strengths = ev.improved?.length ? `<div class="card pad"><h2>What worked</h2>
      <ul>${ev.improved.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>` : "";

    const needs = `<div class="card pad"><h2>What needs work</h2>${ev.needs_work.map((n) =>
      `<div class="needs"><b>${esc(n.point)}</b><div>Fix: ${esc(n.fix)}</div></div>`).join("")}</div>`;

    const lines = `<div class="card pad"><h2>Every line you said → polished</h2>
      ${ev.refused ? `<p class="sub">One request asked for graded work; Hand Up! gives feedback on speaking only.</p>` : ""}
      ${ev.polished_lines.map((p) => `<div class="polish">
        <img src="/static/img/sprites/brunette_front.png" alt="">
        <div><div class="said">${esc(p.said)}</div>
        <div class="polished">${esc(p.polished)} ${p.cited_ids?.length ? `<span class="cite">[${esc(p.cited_ids.join(", "))}]</span>` : ""}</div></div>
        <button class="btn small" data-play="${esc(p.polished)}" title="Play with browser voice">▶ Play</button></div>`).join("")
        || "<p>You did not speak this session.</p>"}</div>`;

    const expr = `<div class="card pad"><h2>Recommended expressions &amp; words</h2>
      <div class="expr">${ev.expressions.map((x) => `<span class="pill">${esc(x)}</span>`).join("")}</div></div>`;

    return head + stats + rubric + prevBlock + strengths + needs + lines + expr + confidenceCard(v) + homeBtn();
  }

  function confidenceCard(v) {
    return `<div class="card pad"><h2>How confident do you feel now? <span class="sub">before: ${v.confidence_before ?? "–"}</span></h2>
      <div class="scale" id="confAfter"></div><p class="sub" id="confTrend">${trend(v.confidence_history)}</p></div>`;
  }

  window.showEvaluation = showEvaluation;
})();
