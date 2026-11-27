# Kokonut UI — composants produit & IA (registry shadcn)

Site : https://kokonutui.com · Catalogue machine-lisible : https://kokonutui.com/llms.txt · Setup agent : https://kokonutui.com/setup.md
Licence MIT (Kokonut UI **Pro** = payant → ne pas utiliser sans licence). Stack : React 19, Tailwind, `motion`, `lucide-react`, shadcn/ui.

## Quand le choisir

**Premier choix** pour : tout ce qui est **UI d'agent/chat IA**, boutons à états, cartes de produit interactives, navigation originale,
inputs spécialisés, feedback (toasts, empty states), micro-UI soignée. **Les composants sont des *produits finis* à fort polish** :
si le besoin est dans le catalogue, ne le refais pas.

**Ne pas choisir** pour : effets décoratifs créatifs/WebGL (→ React Bits), grandes sections de page/templates gratuits (→ Watermelon), graphiques (→ ECharts).

## Catalogue par catégorie (extrait utile pour router)

| Catégorie | Slugs (CLI `@kokonutui/<slug>`) | Usage |
|---|---|---|
| **AI** (`/docs/ai`) | `ai-prompt` (input + modèle + effort + fichiers + `/`), `ai-input-search`, `ai-loading`, `ai-text-loading`, `ai-voice`, `ai-tool-approval`, `ai-tool-calls`, `ai-checkout`, `ai-connect`, `ai-send`, `ai-schedule`, `ai-attachment`, `ai-code-run`, `ai-order-status`, `ai-handoff`, `ai-context-meter`, `ai-citations`, `ai-diff-review`, `ai-model-selector`, `ai-token-alternatives`, `ai-branches`, `ai-agent-lanes`, `ai-inline-edit`, `ai-message-queue`, `ai-redact`, `ai-memory`, `ai-autocomplete` | chat, agents, copilotes, workflows agentiques |
| **Buttons** | `particle-button` (async status : idle→pending→success/error + particules), `gradient-button`, `attract-button`, `hold-button`, `command-button`, `switch-button`, `slide-text-button`, `pull-cord`, `tear-button`, `bell-button`, `morph-popover`, `undo-button`, `slide-to-confirm`, `save-button`, `cart-button`, `v0-button` | CTA, actions destructrices (`hold-button`, `slide-to-confirm`), actions async |
| **Cards** | `card-flip`, `card-stack`, `liquid-glass-card`, `apple-activity-card`, `bento-grid`, `currency-transfer`, `carousel-cards`, `notification-stack`, `liquid-gauge`, `activity-terrain`, `page-flip`, `receipt-printer`, `metric-card`, `uptime-card`, `spending-ring`, `boarding-pass`, `lightbox-grid`, `onboarding-checklist` | KPI, statuts, widgets |
| **Navigation** | `morphic-navbar`, `toolbar`, `smooth-tab`, `profile-dropdown`, `action-search-bar` (⌘K), `smooth-drawer`, `marking-menu`, `scroll-index`, `status-island`, `stack-panel` | navbars, menus, palette de commandes |
| **Inputs** | `file-upload`, `avatar-picker`, `team-selector`, `loader`, `detent-dial`, `wheel-picker`, `liquid-slider`, `signature-pad`, `timezone-planner`, `amount-pad`, `seat-map`, `card-field`, `stay-picker`, `slot-picker`, `tip-selector`, `location-picker` | formulaires riches |
| **Backgrounds** | `dot-field`, `background-paths`, `shape-hero`, `flow-field`, `topo-background`, `drape-background`, `halftone-background`, `ink-background`, `caustics-background`, `rain-glass-background` | fonds (alternative à React Bits ; **choisis-en un seul** par page) |
| **Texts** | `type-writer`, `dynamic-text`, `glitch-text`, `swoosh-text`, `plucked-text`, `cradle-text`, `spoiler-text`, `marker-text`, `shadow-text`, `split-flap-text` | titres animés |
| **Feedback** | `promise-toast`, `inline-alert`, `save-status`, `empty-state`, `helpful-rating` | états UX |
| **Media** | `clip-trimmer`, `synced-transcript`, `focal-point-picker`, `photo-straighten`, `contact-sheet` | éditeurs média |

> Les slugs évoluent : **vérifie toujours** dans `llms.txt` avant d'installer (`curl -s https://kokonutui.com/llms.txt | grep -i <mot>`).

## Installation (testée)

```bash
# une fois par projet
npx shadcn@latest init                                  # si pas de components.json (ou scripts/setup.sh)
# components.json → "registries": { "@kokonutui": "https://kokonutui.com/r/{name}.json" }
npx shadcn@latest add https://kokonutui.com/r/utils.json   # cn() — ⚠ vérifier qu'il n'écrase pas un utils.ts existant

# par composant
npx shadcn@latest add @kokonutui/particle-button @kokonutui/ai-tool-calls -y
# écrit src/components/kokonutui/*.tsx + dépendances (motion, lucide-react, cva) + src/components/ui/button.tsx si requis
```
Puis **lire la source** : `sed -n 1,120p src/components/kokonutui/<slug>.tsx` ou `curl -s https://kokonutui.com/docs/<cat>/<slug>.md`.

Import : `import ParticleButton from "@/components/kokonutui/particle-button"` (export **default**, props typées).

## Usage correct (exemples vérifiés sur les sources installées)

```tsx
// Bouton à états : renvoyer une Promise suffit
<ParticleButton onClick={() => saveProject()} successLabel="Enregistré" pendingLabel="Envoi…" errorLabel="Échec" />
// ⚠ onClick doit retourner une promesse (rejet = état erreur). `status` pour le mode contrôlé.

// Tool calls pilotés par le stream de l'AI SDK (state = part.state)
<AIToolCalls
  calls={parts.map(p => ({ id: p.toolCallId, tool: p.type.replace("tool-", ""), state: p.state,
                            detail: p.input?.query, result: p.output?.summary }))}
  answer={<p>Voici ce que j'ai trouvé…</p>} />
// Sans `state` : mode démo (les appels se jouent seuls sur `duration`) → ne PAS laisser le mode démo en prod.
```

## Règles

1. **Le composant installé est ton code** : édite-le sur place (couleurs, libellés, i18n) ; ne l'enveloppe pas pour contourner.
2. Remplace les **données/démos par défaut** (textes anglais, faux appels, avatars) par les vraies données avant de livrer.
3. Props de pilotage (`status`, `state`, `value`/`onChange`) = mode **contrôlé** : branche-les sur ton state/stream réel.
4. Les composants utilisent `motion/react` : garde **la même lib** pour le reste (pas `framer-motion` en double).
5. Tokens shadcn requis (`bg-background`, `text-muted-foreground`, `bg-primary`…) → définis-les dans `index.css` ; sinon rendu cassé/transparent.
6. `"use client"` déjà présent en tête des fichiers (Next) ; en Vite il est ignoré sans effet.
7. Respecte l'ordre d'importance : 1 composant « héros » par écran (ex. `ai-prompt`), les autres discrets.
8. Pour une UI IA complète : `ai-prompt` (entrée) + `ai-loading`/`ai-tool-calls` (progression) + `ai-tool-approval` (actions sensibles) + `ai-citations` (sources) + `ai-context-meter` (contexte).
9. MCP : `npx shadcn@latest mcp init --client claude` puis demander « ajoute `@kokonutui/ai-prompt` » ; règles à ajouter à `AGENTS.md`/`CLAUDE.md` : *« Avant de construire un composant animé/interactif, consulter https://kokonutui.com/llms.txt ; installer avec le CLI, jamais en collant du code »*.

## Pièges

- `shadcn add` peut créer `src/components/ui/button.tsx` (dépendance `button`) et modifier `package.json` : relire `git diff`.
- Composants basés sur `vaul`, `radix-ui`, `cmdk` : dépendances auto-installées, vérifier la taille du bundle.
- Alias `@/` obligatoire (le CLI écrit `@/lib/utils`, `@/components/ui/*`).
- Icônes `lucide-react` : n'importe que des icônes nommées (`import { Check } from "lucide-react"`), pas `* as`.
