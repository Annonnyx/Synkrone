/**
 * Entrée du bundle vitrine `public/assets/motion.js`.
 * Chargé seulement si <html data-motion="story"> et si l'utilisateur n'a pas
 * demandé reduced-motion (voir public/assets/synkrone-motion.js).
 *
 * Un seul propriétaire du scroll : Lenis est piloté par gsap.ticker, pas de
 * second requestAnimationFrame, pas de ScrollSmoother, pas de scrollerProxy.
 */
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { SplitText } from 'gsap/SplitText';
import Lenis from 'lenis';
import { animate, createTimeline, createScope, createDrawable, stagger, utils, onScroll } from 'animejs';

gsap.registerPlugin(ScrollTrigger, SplitText);

window.SynkroneMotionLib = {
    gsap,
    ScrollTrigger,
    SplitText,
    Lenis,
    anime: { animate, createTimeline, createScope, createDrawable, stagger, utils, onScroll }
};
