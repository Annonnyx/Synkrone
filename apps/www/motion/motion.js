import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { SplitText } from "gsap/SplitText";
import Lenis from "lenis";
import { createDrawable, createTimeline, stagger } from "animejs";

gsap.registerPlugin(ScrollTrigger, SplitText);

let token = 0;
let lenis = null;
let onTick = null;
let ctx = null;
let rack = null;
let split = null;

function reduced() {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function stop() {
    token += 1;
    if (onTick) {
        gsap.ticker.remove(onTick);
        onTick = null;
    }
    if (lenis) {
        lenis.destroy();
        lenis = null;
    }
    if (rack) {
        rack.revert();
        rack = null;
    }
    if (split) {
        split.revert();
        split = null;
    }
    if (ctx) {
        ctx.revert();
        ctx = null;
    }
    ScrollTrigger.getAll().forEach((trigger) => trigger.kill());
}

function lightRack(root) {
    const paths = root.querySelectorAll(".rack-bus path");
    const cabinets = root.querySelectorAll(".cabinet");
    if (!paths.length && !cabinets.length) return;
    rack = createTimeline({ defaults: { ease: "out(3)" } });
    if (paths.length) {
        rack.add(paths, { opacity: [0, 1], duration: 120 });
        rack.add(createDrawable(paths), {
            draw: ["0 0", "0 1"],
            duration: 780,
            delay: stagger(70)
        }, 0);
    }
    if (cabinets.length) {
        rack.add(cabinets, {
            opacity: [0.45, 1],
            y: [14, 0],
            duration: 420,
            delay: stagger(80)
        }, "-=260");
    }
}

function openMasks(instance) {
    instance.masks.forEach((mask) => {
        mask.style.overflow = "clip";
        mask.style.width = "max-content";
        mask.style.maxWidth = "none";
        mask.style.padding = "0.04em 0.16em 0.18em 0";
    });
}

function revealIfShown(cards) {
    const line = window.innerHeight * 0.92;
    cards.forEach((card) => {
        const box = card.getBoundingClientRect();
        if (box.top < line && box.bottom > 0) {
            gsap.to(card, {
                y: 0,
                autoAlpha: 1,
                duration: 0.55,
                ease: "power3.out",
                overwrite: true
            });
        }
    });
}

function start() {
    stop();
    const mine = token;
    if (document.documentElement.dataset.motion !== "story" || reduced()) return;
    const root = document.getElementById("content-root");
    if (!root) return;

    lenis = new Lenis({ autoRaf: false });
    lenis.on("scroll", ScrollTrigger.update);
    onTick = (time) => lenis.raf(time * 1000);
    gsap.ticker.add(onTick);
    gsap.ticker.lagSmoothing(0);

    const run = () => {
        if (mine !== token) return;
        if (document.documentElement.dataset.motion !== "story" || reduced()) return;
        ctx = gsap.context(() => {
            const title = root.querySelector(".hero h1");
            if (title) {
                split = SplitText.create(title, {
                    type: "lines",
                    mask: "lines",
                    autoSplit: true,
                    aria: "auto",
                    onSplit(self) {
                        openMasks(self);
                        return gsap.from(self.lines, {
                            yPercent: 110,
                            duration: 0.55,
                            ease: "power3.out",
                            stagger: 0.06
                        });
                    }
                });
            }
            const cards = gsap.utils.toArray(".bot-card, .plate, .project", root);
            if (cards.length) {
                gsap.set(cards, { autoAlpha: 0, y: 16 });
                ScrollTrigger.batch(cards, {
                    start: "top 88%",
                    once: true,
                    onEnter(batch) {
                        gsap.to(batch, {
                            y: 0,
                            autoAlpha: 1,
                            duration: 0.55,
                            stagger: 0.05,
                            ease: "power3.out",
                            overwrite: true
                        });
                    }
                });
                revealIfShown(cards);
            }
        }, root);
        lightRack(root);
        ScrollTrigger.refresh();
    };

    if (document.fonts && document.fonts.ready) document.fonts.ready.then(run);
    else run();
}

function scrollTo(target) {
    if (!target) return;
    if (lenis) {
        lenis.scrollTo(target, { offset: -88 });
        return;
    }
    target.scrollIntoView({ block: "start" });
}

window.synkroneMotion = { start, stop, sync: start, scrollTo };
