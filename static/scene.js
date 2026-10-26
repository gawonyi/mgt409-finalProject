/* Classroom scene: room.png viewport crop + sprites placed from static/img/layout.json.
   Students: <name>_back.png flipped horizontally, bottom-right corner on the chair point (+4,+4).
   Professor: bottom-center on the professor point. Draw order = increasing y. */
const Scene = (() => {
  const IMG = "/static/img/";
  let layout = null, world = null, scene = null;
  const actors = {}; // id → element

  async function load() {
    if (!layout) layout = await (await fetch(IMG + "layout.json")).json();
    return layout;
  }

  function el(tag, cls, parent) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (parent) parent.appendChild(e);
    return e;
  }

  function fit() {
    if (!scene || !layout) return;
    world.style.transform = `scale(${scene.clientWidth / layout.viewport.w})`;
  }

  function addActor(id, { sprite, x, y, scale, anchor, flip, label, cls }) {
    const v = layout.viewport;
    const a = el("div", `actor idle ${cls || ""}`, world);
    a.style.zIndex = Math.round(y);
    const img = el("img", "body", a);
    img.alt = label;
    const hand = el("img", "icon hand", a);
    hand.src = IMG + "sprites/" + layout.icons.hand + ".png";
    const alert = el("img", "icon alert", a);
    alert.src = IMG + "sprites/" + layout.icons.cold_call + ".png";
    if (label) el("span", "tag", a).textContent = label;
    img.onload = () => {
      const w = img.naturalWidth * scale, h = img.naturalHeight * scale;
      a.style.width = w + "px";
      a.style.height = h + "px";
      const left = anchor === "bottom-center" ? x - w / 2 : x + 4 - w;
      const top = anchor === "bottom-center" ? y - h : y + 4 - h;
      a.style.left = left - v.x + "px";
      a.style.top = top - v.y + "px";
      // icons above the head, 35% from the sprite's left
      for (const ic of [hand, alert]) {
        ic.style.left = w * 0.35 - 24 + "px";
        ic.style.top = -56 + "px";
      }
    };
    img.src = IMG + "sprites/" + sprite + ".png";
    if (flip) a.classList.add("flip");
    actors[id] = a;
    return a;
  }

  /* cast = {prof: {name}, me: {name, character}, classmates: [{id, name, character}]} */
  async function build(container, cast) {
    await load();
    scene = container;
    container.querySelectorAll(".world").forEach((w) => (w.innerHTML = ""));
    world = container.querySelector(".world");
    for (const k in actors) delete actors[k];

    const room = el("img", "room", world);
    room.alt = "Isometric pixel classroom";
    room.onerror = () => { // fallback if the image asset is missing
      room.remove();
      world.style.background = "linear-gradient(#BFE0F0 0 35%, #F3E3BE 35%)";
    };
    room.src = IMG + layout.image;

    const p = layout.professor;
    addActor("prof", { sprite: p.sprite, x: p.x, y: p.y, scale: p.scale, anchor: "bottom-center",
      label: cast.prof.name, cls: "prof" });

    const seating = layout.default_seating;
    const used = new Set([seating.me]);
    const chairOf = (character) => {
      let c = seating.classmates[character];
      if (!c || used.has(c)) c = Object.keys(layout.chairs).find((k) => !used.has(k));
      used.add(c);
      return c;
    };
    const seat = (id, character, label, cls, chair) => {
      const [x, y] = layout.chairs[chair];
      addActor(id, { sprite: layout.characters[character].scene, x, y, scale: layout.student_scale,
        anchor: "bottom-right", flip: true, label, cls });
    };
    seat("me", cast.me.character || layout.me.character, cast.me.name || layout.me.label, "me", seating.me);
    cast.classmates.forEach((c) => seat(c.id, c.character, c.name, "", chairOf(c.character)));

    fit();
    window.addEventListener("resize", fit);
  }

  function setSpeaker(id) {
    for (const k in actors) actors[k].classList.toggle("speaking", k === id);
  }

  function setHands(hands, myHand) {
    for (const k in actors) {
      if (k === "prof") continue;
      actors[k].classList.toggle("raised", k === "me" ? !!myHand : !!hands[k]);
    }
  }

  function coldCall() {
    const a = actors.me;
    if (!a) return;
    a.classList.add("cold");
    setTimeout(() => a.classList.remove("cold"), 1500);
  }

  const portrait = (character) =>
    IMG + "sprites/" + (layout?.characters[character]?.portrait || character) + ".png";

  return { build, setSpeaker, setHands, coldCall, portrait, load, fit };
})();
