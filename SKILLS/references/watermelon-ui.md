# Watermelon UI — catalogue de blocs, dashboards, templates & composants animés

Site : https://ui.watermelon.sh · llms.txt : https://ui.watermelon.sh/llms.txt · Licence MIT · Repos : github.com/WatermelonCorp
Catalogue (≈ 849 entrées) : **516 components · 131 animated-components · 189 blocks · 12 dashboards · 1 template**.
Stack : React 19, Tailwind 4, `motion` (souvent importé comme `framer-motion`), `lucide-react`, parfois `react-icons`, `number-flow`.

## Quand le choisir

- **Sections de page** (hero, pricing, features, testimonials, footer, CTA…) → `blocks`.
- **Dashboards / back-office** (layout complet, sidebar, cartes de stats) → `dashboards`.
- **Composition de page complète** → `templates` (1) ou MCP `compose_page`.
- **Largeur de choix** de composants animés (cards, disclosures, sliders, widgets, onboarding, deployment/billing cards) → `animated-components`.
- **Inspiration + code source** avant de designer à la main.

**Ne pas choisir** si Kokonut a un composant IA équivalent (chat, tool calls) ; ni pour de vrais graphiques (→ ECharts : les « charts » des dashboards Watermelon sont souvent statiques/SVG ; remplace-les par ECharts si les données sont réelles).

## Accès machine (par ordre de préférence)

1. **MCP hébergé** (aucune clé) : `claude mcp add --transport http watermelon https://mcp.watermelon.sh/mcp` (Codex : `codex mcp add watermelon --url https://mcp.watermelon.sh/mcp`).
   Outils : `search` (recherche plein texte du catalogue), `get_inspiration`, `get_component` (source), `compose_page` (assemble des blocs en page), `list_categories`.
2. **API REST publique** (lecture seule, sans auth) :
   - `GET https://ui.watermelon.sh/api/v1/catalog/summary`
   - `GET https://ui.watermelon.sh/api/v1/catalog/entries?kind=<kind>&category=<cat>&limit=<n>&query=<texte>`
     `kind` ∈ `components | animated-components | blocks | dashboards | templates`
   - `GET https://ui.watermelon.sh/api/v1/catalog/entries/<kind>/<slug>` → `installCommand`, `dependencies`, `previewUrl`, `registryUrl`
   - ⚠ Par défaut **limit=20, tri alphabétique** : une requête sans `category`/`limit` ne montre qu'un début de liste. Pagine/filtre, ou préfère le MCP `search`.
3. Pages web : `/animated-components`, `/blocks`, `/dashboards`, `/templates`, `/free`.

Exemple (liste des cartes animées avec leurs dépendances) :
```bash
curl -s "https://ui.watermelon.sh/api/v1/catalog/entries?kind=animated-components&category=cards&limit=40" \
 | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>JSON.parse(s).entries.forEach(e=>console.log(e.slug,"|",e.description.slice(0,70),"|",e.dependencies.join(","))))'
```
Catégories d'animated-components observées : `cards`, `disclosure`, `sliders`, `widgets`, `micro-interaction`… → `list_categories` pour la liste à jour.

## Installation (testée)

```bash
# namespace officiel (shadcn le résout sans components.json) :
#   "@watermelon": "https://registry.watermelon.sh/r/{name}.json"
npx shadcn@latest add @watermelon/<slug> -y
# ou URL directe
npx shadcn@latest add https://registry.watermelon.sh/r/<slug>.json -y
# ex.
npx shadcn@latest add @watermelon/deployment-card @watermelon/credit-usage-card -y
# chercher : npx shadcn@latest search @watermelon -q "pricing"
# variante aux tokens du thème : suffixe -base (card-split-accordian-base)
```
Écrit dans `src/components/watermelon/<slug>.tsx` (ou `ui/`, `blocks/`, `dashboards/` selon le kind).

### ⚠ Correctifs systématiques après installation

1. **`src/lib/utils.ts`** : l'install d'un composant a réécrit le fichier en `export { cn } from "cn"` (package inexistant) → build cassé.
   Restaurer : `clsx` + `twMerge` (voir `scripts/setup.sh`). Toujours relancer `scripts/preflight.sh`.
2. **`framer-motion` → `motion/react`** : `sed -i "s#from 'framer-motion'#from 'motion/react'#" src/components/watermelon/*.tsx` puis `npm uninstall framer-motion` si plus utilisé.
3. **Icônes** : les composants mélangent `lucide-react` et `react-icons` ; accepte ou remplace par `lucide-react` pour alléger.
4. **Mode sombre** : beaucoup de composants utilisent `bg-white dark:bg-[#...]`. Active la classe `.dark` sur `<html>` (et `@custom-variant dark (&:is(.dark *));` en Tailwind v4) ou adapte les classes au thème du projet.
5. **Données de démo** : props `data`/`usageHistory` factices → remplacer. Certains composants sont **sans props** (état interne) : les adapter en éditant la source.

## Usage correct (APIs vérifiées)

```tsx
import { DeploymentCard, type DeploymentData } from "@/components/watermelon/deployment-card";
<DeploymentCard data={deployment} />            // données obligatoires (DeploymentData : steps[], status 'Ready'|'Building'|'Error'…)

import { CreditUsageCard } from "@/components/watermelon/credit-usage-card";
<CreditUsageCard usedCreditsPercent={72} totalCreditsLabel="100M CRÉDITS" creditsUsedLabel="72M" creditsLeftLabel="28M"
                 usageHistory={rows} onManagePlan={…} onAutoSwitchChange={…} />
```
Toujours **lire les `interface …Props`** dans le fichier installé : elles diffèrent d'un composant à l'autre.

## Workflow recommandé pour une page

1. `compose_page` (MCP) ou lister `blocks` par catégorie → choisir 1 hero, 1 features, 1 pricing/CTA, 1 footer cohérents (même ton visuel).
2. Installer les blocs ; **uniformiser** : mêmes tokens, mêmes radius/espacements, une seule police.
3. Remplacer textes/images/liens ; supprimer le superflu ; vérifier responsive 375 / 768 / 1280.
4. Insérer ECharts pour les données, React Bits (1 fond / 1 titre animé) pour le wow — pas plus.

## Pièges

- Beaucoup de composants = beaucoup de styles hétérogènes : ne mélange pas 8 « looks » ; choisis une famille.
- Dépendances variées (`number-flow`, `react-icons`, `tailwindcss` listé en dep → ignorable) : n'installe que ce que le CLI demande.
- `components.json` doit exister avant `shadcn add` ; l'alias `@/` doit pointer sur `src`.
- Les URLs d'assets (`assets.watermelon.sh`, avatars) sont des exemples : héberge/remplace tes propres images.
