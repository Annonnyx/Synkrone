#!/usr/bin/env bash
# setup.sh — prépare un projet React (Vite/Next) + Tailwind pour la stack ai-ui-stack. Idempotent.
# Usage : bash SKILLS/scripts/setup.sh [--with-core]
#   --with-core  installe aussi animejs, echarts, motion, gsap, @gsap/react, lenis, lucide-react, class-variance-authority
set -euo pipefail

[ -f package.json ] || { echo "Lance ce script depuis la racine du projet."; exit 1; }
PM=npm; [ -f pnpm-lock.yaml ] && PM=pnpm; [ -f yarn.lock ] && PM=yarn; [ -f bun.lockb ] && PM=bun
echo "Gestionnaire : $PM"

# 1. utilitaire cn() (clsx + tailwind-merge) — requis par TOUS les composants shadcn-like
mkdir -p src/lib
if [ ! -f src/lib/utils.ts ] || ! grep -q twMerge src/lib/utils.ts; then
  cat > src/lib/utils.ts <<'EOF'
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
EOF
  echo "✔ src/lib/utils.ts écrit"
fi
node -e "const p=require('./package.json');const d={...p.dependencies,...p.devDependencies};process.exit(d.clsx&&d['tailwind-merge']?0:1)" \
  || $PM install clsx tailwind-merge

# 2. components.json (sans écraser l'existant) + registries
CSS=$( [ -f src/index.css ] && echo src/index.css || ([ -f src/app/globals.css ] && echo src/app/globals.css || echo src/index.css) )
if [ ! -f components.json ]; then
  cat > components.json <<EOF
{
  "\$schema": "https://ui.shadcn.com/schema.json",
  "style": "new-york",
  "rsc": false,
  "tsx": true,
  "tailwind": { "config": "", "css": "$CSS", "baseColor": "neutral", "cssVariables": true, "prefix": "" },
  "iconLibrary": "lucide",
  "aliases": { "components": "@/components", "utils": "@/lib/utils", "ui": "@/components/ui", "lib": "@/lib", "hooks": "@/hooks" },
  "registries": {}
}
EOF
  echo "✔ components.json créé"
fi
node -e "
const fs=require('fs');const c=JSON.parse(fs.readFileSync('components.json','utf8'));
c.registries={...(c.registries||{}),'@kokonutui':'https://kokonutui.com/r/{name}.json','@react-bits':'https://reactbits.dev/r/{name}.json'};
fs.writeFileSync('components.json',JSON.stringify(c,null,2)+'\n');console.log('✔ registries @kokonutui + @react-bits déclarés');"

# 3. dépendances de base (optionnel)
if [ "${1:-}" = "--with-core" ]; then
  $PM install animejs echarts motion gsap @gsap/react lenis lucide-react class-variance-authority
fi

# 4. rappel des tokens de thème
grep -q -- "--background" "$CSS" 2>/dev/null || echo "! Aucun token shadcn (--background…) dans $CSS : définis :root + @theme inline (voir references/recipes.md §Thème)."

cat <<'EOF'

Prochaines commandes :
  npx shadcn@latest add @kokonutui/<nom> -y
  npx shadcn@latest add @react-bits/<Nom>-TS-TW -y
  npx shadcn@latest add https://registry.watermelon.sh/r/<slug>.json -y
  (MCP, optionnel)  npx shadcn@latest mcp init --client <claude|cursor|vscode|codex>
Puis : bash SKILLS/scripts/preflight.sh   # vérifier qu'aucun fichier partagé n'a été écrasé
EOF
