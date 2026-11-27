/**
 * Synkrone — contrôleur de mouvement de la vitrine (HTML servi par Express, pas React).
 *
 * Règles appliquées (docs/plans/refonte-visuelle.md §2, SKILLS/SKILL.md §4) :
 *  - un nœud, un moteur : le bus SVG et les armoires appartiennent à anime.js v4,
 *    le h1 à GSAP SplitText, le scroll à Lenis piloté par gsap.ticker ;
 *  - Lenis une seule instance, `autoRaf: false`, `lenis.raf(time * 1000)` depuis
 *    gsap.ticker, CSS lenis/dist/lenis.css (assets/motion.css) ;
 *  - jamais de second requestAnimationFrame, jamais ScrollTrigger.scrollerProxy,
 *    jamais ScrollSmoother ;
 *  - `prefers-reduced-motion` : rien ne se monte, le bus est déjà tracé, tout est lisible ;
 *  - `.stop()` est appelé avant chaque échange de feuille : SplitText.revert() et
 *    revert du contexte GSAP précèdent snapshotLeaf/innerHTML.
 *
 * Ce fichier reste petit et synchronisé : le bundle lourd (assets/motion.js) n'est
 * importé que si <html data-motion="story">, assets/status-chart.js que sur /stats.
 */
(function () {
    'use strict';

    var html = document.documentElement;
    var STORY_PATHS = ['/', '/accueil', '/discord', '/discord/bots', '/minecraft', '/minecraft/serveur'];
    var STATUS_PATH = '/stats';
    var ARM_TIMEOUT = 3000;

    var runtime = {
        path: '',
        lib: null,
        lenis: null,
        tick: null,
        ctx: null,
        split: null,
        scope: null,
        chart: null,
        chartRo: null,
        armed: false,
        armTimer: null
    };

    function norm(path) {
        var value = String(path || '/');
        if (value.length > 1 && value.charAt(value.length - 1) === '/') value = value.slice(0, -1);
        return value || '/';
    }

    function reduceMotion() {
        return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    }

    function currentMotion() {
        return html.getAttribute('data-motion') || 'off';
    }

    function isStoryPath(path) {
        return STORY_PATHS.indexOf(norm(path)) !== -1;
    }

    function isLeaf(path) {
        return !/\/(discord\/(bump|me|publicbot|dashbot|commandes)|admin|equipe|minecraft\/modpack)\b/.test(norm(path));
    }

    function arm() {
        if (runtime.armed) return;
        runtime.armed = true;
        html.classList.add('sk-armed');
        clearTimeout(runtime.armTimer);
        runtime.armTimer = window.setTimeout(disarm, ARM_TIMEOUT);
    }

    function disarm() {
        clearTimeout(runtime.armTimer);
        runtime.armTimer = null;
        if (!runtime.armed) return;
        runtime.armed = false;
        html.classList.remove('sk-armed');
    }

    function ensureLenisCss() {
        if (document.querySelector('link[data-motion-css]')) return;
        var link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = '/assets/motion.css';
        link.setAttribute('data-motion-css', '1');
        document.head.appendChild(link);
    }

    /* ——— Allumage : bus ambre tracé par anime.js, armoires qui montent ——— */

    function ignition(lib, hero) {
        var anime = lib.anime;
        var bus = hero.querySelector('.sk-bus');
        if (!bus) return null;
        return anime.createScope({ root: hero }).add(function () {
            anime.createTimeline({ defaults: { ease: 'outExpo', duration: 900 } })
                .add(anime.createDrawable(bus.querySelectorAll('.sk-bus-line')), {
                    draw: ['0 0', '0 1'],
                    duration: 1100,
                    delay: anime.stagger(140)
                })
                .add(bus.querySelectorAll('.sk-bus-node'), {
                    opacity: [0, 1],
                    scale: [0.4, 1],
                    duration: 520,
                    delay: anime.stagger(70)
                }, '-=700')
                .add(hero.querySelectorAll('.cabinet'), {
                    opacity: [0, 1],
                    y: [16, 0],
                    duration: 720,
                    delay: anime.stagger(90)
                }, '-=520')
                .add(hero.querySelector('.grid-plane'), {
                    opacity: [0.4, 1],
                    duration: 900
                }, '-=600')
                .onComplete(function () {
                    // Le DOM revient à l'état CSS : le cache de feuille voit un HTML propre.
                    if (runtime.scope) runtime.scope.revert();
                    runtime.scope = null;
                    disarm();
                    if (lib.ScrollTrigger) lib.ScrollTrigger.refresh();
                });
        });
    }

    /* ——— Titre : GSAP SplitText, masque de lignes, texte conservé ——— */

    function revealTitle(lib, hero) {
        var gsap = lib.gsap;
        var SplitText = lib.SplitText;
        var h1 = hero.querySelector('.hero-copy h1');
        if (!h1 || !SplitText) return;
        var split = new SplitText(h1, { type: 'lines,words', mask: 'lines', autoSplit: true });
        runtime.split = split;
        gsap.set(h1, { opacity: 1 });
        gsap.from(split.words, {
            yPercent: 115,
            autoAlpha: 0,
            duration: 0.9,
            ease: 'power3.out',
            stagger: 0.05,
            delay: 0.15
        });
    }

    /* ——— Lecture : batch sur .bot-card/.plate puis .project. Pas de pin, pas de scrub ——— */

    function batches(lib) {
        var gsap = lib.gsap;
        var ScrollTrigger = lib.ScrollTrigger;
        var cards = document.querySelectorAll('.bot-card, .plate');
        var projects = document.querySelectorAll('.project');
        gsap.set(cards, { y: 24, autoAlpha: 0 });
        ScrollTrigger.batch(cards, {
            interval: 0.1,
            batchMax: 6,
            start: 'top bottom-=80',
            once: true,
            onEnter: function (els) {
                gsap.to(els, { y: 0, autoAlpha: 1, duration: 0.7, ease: 'power3.out', stagger: 0.06, overwrite: true });
            }
        });
        gsap.set(projects, { y: 24, autoAlpha: 0 });
        ScrollTrigger.batch(projects, {
            interval: 0.1,
            batchMax: 4,
            start: 'top bottom-=70',
            once: true,
            onEnter: function (els) {
                gsap.to(els, { y: 0, autoAlpha: 1, duration: 0.7, ease: 'power3.out', stagger: 0.08, overwrite: true });
            }
        });
    }

    function refreshAfterPaint(lib, lenis) {
        var ScrollTrigger = lib.ScrollTrigger;
        window.setTimeout(function () {
            ScrollTrigger.refresh();
            if (lenis) lenis.resize();
        }, 260);
        if (document.fonts && document.fonts.ready) {
            document.fonts.ready.then(function () {
                ScrollTrigger.refresh();
                if (lenis) lenis.resize();
            });
        }
    }

    /* ——— /stats : ECharts sur uptime.bars (pct, date) ——— */

    function mountStatusChart(echarts) {
        var host = document.getElementById('st-chart');
        var bars = document.getElementById('st-bars');
        var payload = window.__skStatusData;
        if (!host || !echarts || !payload) return;
        var rows = Array.isArray(payload.uptime && payload.uptime.bars) ? payload.uptime.bars : [];
        if (!rows.length) return;
        var styles = window.getComputedStyle(host);
        var accent = (styles.getPropertyValue('--sk-accent') || '#3f6b52').trim() || '#3f6b52';
        var muted = (styles.getPropertyValue('--sk-text-muted') || '#5c6a66').trim() || '#5c6a66';
        var reduce = reduceMotion();

        if (bars) bars.hidden = true;
        var chart = echarts.init(host, undefined, { renderer: 'canvas' });
        runtime.chart = chart;
        chart.setOption({
            backgroundColor: 'transparent',
            animation: !reduce,
            animationDuration: 600,
            aria: { enabled: true, label: { description: 'Uptime mesuré sur 7 jours, pourcentage par jour, de 0 à 100.' } },
            grid: { left: 8, right: 8, top: 28, bottom: 8, containLabel: true },
            tooltip: {
                trigger: 'axis',
                backgroundColor: 'rgba(27,33,30,.94)',
                borderColor: 'rgba(255,255,255,.12)',
                textStyle: { color: '#eef0ea', fontFamily: 'IBM Plex Sans, sans-serif' },
                valueFormatter: function (value) { return `${Number(value).toFixed(2).replace('.', ',')} %`; }
            },
            xAxis: {
                type: 'category',
                data: rows.map(function (row) { return String(row.date || '').slice(5); }),
                axisLabel: { color: muted, fontSize: 11, fontFamily: 'IBM Plex Mono, monospace' },
                axisLine: { lineStyle: { color: 'rgba(92,106,102,.32)' } },
                axisTick: { show: false }
            },
            yAxis: {
                type: 'value',
                min: 0,
                max: 100,
                axisLabel: { color: muted, fontSize: 11, formatter: '{value}%' },
                splitLine: { lineStyle: { color: 'rgba(92,106,102,.14)' } }
            },
            series: [{
                name: 'Uptime',
                type: 'bar',
                data: rows.map(function (row) { return Number(row.pct) || 0; }),
                barMaxWidth: 26,
                itemStyle: { color: accent, borderRadius: [3, 3, 0, 0] }
            }]
        });
        runtime.chartRo = new ResizeObserver(function () { chart.resize(); });
        runtime.chartRo.observe(host);
    }

    function unmountStatusChart() {
        if (runtime.chartRo) { runtime.chartRo.disconnect(); runtime.chartRo = null; }
        if (runtime.chart) { runtime.chart.dispose(); runtime.chart = null; }
        var bars = document.getElementById('st-bars');
        if (bars) bars.hidden = false;
    }

    /* ——— cycle de vie ——— */

    function stop() {
        disarm();
        if (runtime.split) {
            try { runtime.split.revert(); } catch (err) { /* déjà revert */ }
            runtime.split = null;
        }
        if (runtime.scope) {
            try { runtime.scope.revert(); } catch (err) { /* déjà revert */ }
            runtime.scope = null;
        }
        if (runtime.ctx) {
            try { runtime.ctx.revert(); } catch (err) { /* déjà revert */ }
            runtime.ctx = null;
        }
        if (runtime.tick && runtime.lib) {
            try { runtime.lib.gsap.ticker.remove(runtime.tick); } catch (err) { /* ticker déjà vidé */ }
            runtime.tick = null;
        }
        if (runtime.lenis) {
            try { runtime.lenis.destroy(); } catch (err) { /* déjà détruit */ }
            runtime.lenis = null;
        }
        unmountStatusChart();
        runtime.lib = null;
        runtime.path = '';
    }

    function sync(pathOverride) {
        var motion = currentMotion();
        var path = norm(pathOverride || window.location.pathname);
        if (motion !== 'story' || reduceMotion() || !isStoryPath(path) || !isLeaf(path)) {
            stop();
            return;
        }
        if (runtime.path === path && runtime.lib) return;
        stop();
        start(path);
    }

    async function start(path) {
        runtime.path = path;
        arm();
        var lib;
        try {
            lib = await import('/assets/motion.js');
        } catch (err) {
            disarm();
            runtime.path = '';
            return;
        }
        if (runtime.path !== path) return; // une autre feuille est déjà arrivée
        runtime.lib = lib;
        ensureLenisCss();

        var gsap = lib.gsap;
        var ScrollTrigger = lib.ScrollTrigger;
        gsap.registerPlugin(ScrollTrigger, lib.SplitText);

        // Lenis : une instance racine, pilotée par gsap.ticker (secondes → millisecondes).
        var lenis = null;
        try {
            lenis = new lib.Lenis({ autoRaf: false, lerp: 0.12, syncTouch: false });
            lenis.on('scroll', ScrollTrigger.update);
            var tick = function (time) { lenis.raf(time * 1000); };
            gsap.ticker.add(tick);
            gsap.ticker.lagSmoothing(0);
            runtime.lenis = lenis;
            runtime.tick = tick;
        } catch (err) {
            lenis = null;
        }

        var hero = document.querySelector('.hero');
        runtime.ctx = gsap.context(function () {
            if (hero) {
                revealTitle(lib, hero);
                runtime.scope = ignition(lib, hero);
            }
            batches(lib);
        }, document.getElementById('content-root') || document.body);

        refreshAfterPaint(lib, lenis);

        if (path === STATUS_PATH) {
            try {
                var echarts = await import('/assets/status-chart.js');
                if (runtime.path === path) mountStatusChart(window.SynkroneChart || echarts);
            } catch (err) { /* les barres CSS restent en place */ }
        }
    }

    document.addEventListener('synkrone:status', function () {
        if (runtime.chart || !window.SynkroneChart) return;
        if (norm(runtime.path) !== STATUS_PATH) return;
        if (reduceMotion() || currentMotion() !== 'off') return;
        try {
            import('/assets/status-chart.js').then(function () {
                mountStatusChart(window.SynkroneChart);
            });
        } catch (err) { /* barres CSS conservées */ }
    });

    window.addEventListener('pageshow', function () {
        if (runtime.lib && runtime.lib.ScrollTrigger) runtime.lib.ScrollTrigger.refresh();
    });

    window.synkroneMotion = { stop: stop, sync: sync };
    if (currentMotion() === 'story' && !reduceMotion() && isStoryPath(window.location.pathname)) sync();
}());
