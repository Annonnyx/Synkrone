# ai-ui-stack (skill d'agent)

Skill pour agents IA (Claude Code, Codex, Cursor…) : choisir et utiliser correctement **GSAP 3, Lenis, anime.js, ECharts, Kokonut UI, Watermelon UI et React Bits**.

```
SKILLS/                         ← dossier canonique (nom du skill : ai-ui-stack)
├─ SKILL.md                  ← point d'entrée : routeur de décision, procédure, règles dures, checklist
├─ references/
│  ├─ gsap.md                ← ScrollTrigger, SplitText, Flip, useGSAP (plugins gratuits)
│  ├─ lenis.md               ← smooth scroll MIT, une boucle avec le ticker GSAP
│  ├─ anime-js.md            ← API v4, pièges v3→v4, pattern React, recettes
│  ├─ echarts.md             ← tree-shaking, hook React, thème, choix du chart
│  ├─ kokonut-ui.md          ← catalogue IA/UI, install, usage
│  ├─ watermelon-ui.md       ← MCP/API, install, correctifs post-install
│  ├─ react-bits.md          ← variantes, deps, backgrounds/texte
│  └─ recipes.md             ← thème, compositions de pages, table de routage
└─ scripts/
   ├─ setup.sh               ← components.json + registries + cn()  (idempotent)
   └─ preflight.sh           ← diagnostic projet / détection d'écrasements
```

## Installation du skill

- **Cursor** : lien `.cursor/skills/ai-ui-stack` → `SKILLS/`. Cursor charge ce skill sur les tâches UI, animation et data-viz.
- **Claude Code** : copier ou lier le dossier dans `.claude/skills/ai-ui-stack/` (projet) ou `~/.claude/skills/ai-ui-stack/` (global).
- **Codex / autres agents** : dans `AGENTS.md` :
  > Pour toute tâche UI/animation/dataviz, lis `SKILLS/SKILL.md` et suis-le.

## Test rapide

> « Crée un dashboard avec un graphique de ventes, des KPI qui comptent, un fond animé et un bouton de sauvegarde. »

Attendu : ECharts (chart) · React Bits CountUp (KPI) + Aurora (fond) · Kokonut ParticleButton (bouton) · anime.js (entrée en cascade) — avec preflight, installation CLI, build.
