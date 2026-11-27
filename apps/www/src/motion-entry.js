import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { SplitText } from "gsap/SplitText";
import Lenis from "lenis";
import { createTimeline, createDrawable } from "animejs";

gsap.registerPlugin(ScrollTrigger, SplitText);

const reduced = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

let lenis = null;
let onTick = null;
let split = null;
let animeTl = null;
let startedRoot = null;

function ensureVisible(root) {
  if (!root) return;
  root.querySelectorAll(".reveal").forEach((n) => n.classList.add("in"));
  root.querySelectorAll(".cabinet").forEach((n) => {
    n.style.opacity = "1";
    n.style.transform = "";
  });
  const bus = root.querySelector(".bus-path");
  if (bus) {
    bus.style.strokeDasharray = "none";
    bus.style.strokeDashoffset = "0";
  }
}

function start(root, opts = {}) {
  stop();
  startedRoot = root || document.getElementById("content-root");
  const scope = startedRoot || document.body;
  const isHome = Boolean(opts.isHome || scope.querySelector("#scene-hero, .hero"));

  if (reduced()) {
    ensureVisible(scope);
    return;
  }

  // Lenis — une seule instance, pilotée par gsap.ticker
  lenis = new Lenis({ autoRaf: false });
  lenis.on("scroll", ScrollTrigger.update);
  onTick = (time) => lenis.raf(time * 1000);
  gsap.ticker.add(onTick);
  gsap.ticker.lagSmoothing(0);

  // Batch — GSAP possède .bot-card, .plate, .project
  const batchTargets = scope.querySelectorAll(".bot-card, .plate, .project");
  if (batchTargets.length) {
    gsap.set(batchTargets, { autoAlpha: 0, y: 24 });
    ScrollTrigger.batch(batchTargets, {
      start: "top 88%",
      once: true,
      onEnter: (els) =>
        gsap.to(els, { autoAlpha: 1, y: 0, duration: 0.6, ease: "power3.out", stagger: 0.06 }),
    });
  }

  // Allumage — uniquement sur l'accueil
  if (isHome) {
    const h1 = scope.querySelector(".hero h1");
    const busPath = scope.querySelector(".bus-path");
    const cabinets = scope.querySelectorAll(".cabinet");

    // SplitText — masque de lignes, texte conservé dans le DOM
    if (h1) {
      const doSplit = () => {
        if (split) {
          try { split.revert(); } catch {}
          split = null;
        }
        split = new SplitText(h1, { type: "lines,words", mask: "lines", autoSplit: true });
        gsap.from(split.lines, { yPercent: 110, duration: 0.9, ease: "power3.out", stagger: 0.08 });
      };
      if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(doSplit);
      } else {
        doSplit();
      }
    }

    // Bus SVG ambre tracé avec anime.js v4 createDrawable dans createTimeline
    if (busPath) {
      const drawable = createDrawable(busPath);
      void drawable;
      animeTl = createTimeline({ defaults: { ease: "inOutQuad" } });
      animeTl.add(busPath, { draw: ["0 0", "0 1"], duration: 1400 });
      if (cabinets.length) {
        animeTl.add(cabinets, { opacity: [0, 1], y: [24, 0], duration: 700, ease: "outExpo" }, "-=500");
      }
    } else if (cabinets.length) {
      animeTl = createTimeline({ defaults: { ease: "outExpo" } });
      animeTl.add(cabinets, { opacity: [0, 1], y: [24, 0], duration: 700 });
    }
  }

  const refresh = () => ScrollTrigger.refresh();
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(refresh);
  window.addEventListener("load", refresh);
  ScrollTrigger.refresh();
}

function stop() {
  if (split) {
    try { split.revert(); } catch {}
    split = null;
  }
  if (animeTl) {
    try { animeTl.revert(); } catch {}
    animeTl = null;
  }
  try {
    ScrollTrigger.getAll().forEach((t) => t.kill());
  } catch {}
  if (onTick) {
    try { gsap.ticker.remove(onTick); } catch {}
    onTick = null;
  }
  if (lenis) {
    try { lenis.destroy(); } catch {}
    lenis = null;
  }
  startedRoot = null;
}

window.synkroneMotion = { start, stop };

// Démarrage initial si la page est déjà en mode story (SSR)
if (document.documentElement.dataset.motion === "story") {
  const root = document.getElementById("content-root");
  if (root) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", () => start(root, { isHome: true }));
    } else {
      start(root, { isHome: true });
    }
  }
}
