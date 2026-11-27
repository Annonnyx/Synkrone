#!/usr/bin/env bash
# preflight.sh — état du projet avant d'installer des composants UI.
# Usage : bash SKILLS/scripts/preflight.sh
set -u
ok()   { printf "  \033[32m✔\033[0m %s\n" "$1"; }
warn() { printf "  \033[33m!\033[0m %s\n" "$1"; }
info() { printf "  - %s\n" "$1"; }

echo "== ai-ui-stack preflight =="
[ -f package.json ] || { echo "package.json introuvable (lance depuis la racine du projet)"; exit 1; }

has_dep() { node -e "const p=require('./package.json');const d={...p.dependencies,...p.devDependencies};process.exit(d['$1']?0:1)"; }
ver()     { node -e "const p=require('./package.json');const d={...p.dependencies,...p.devDependencies};console.log(d['$1']||'')"; }

echo "Framework"
has_dep react && ok "react $(ver react)" || warn "react absent (ces outils ciblent React)"
has_dep next && info "next $(ver next) → ajouter \"use client\" aux composants animés"
has_dep vite && info "vite $(ver vite)"

echo "Tailwind"
if has_dep tailwindcss; then
  TW=$(ver tailwindcss); ok "tailwindcss $TW"
  case "$TW" in *4.*) info "v4 : tokens via @theme inline dans le CSS, pas de tailwind.config.js";; *) warn "v3 : choisir les variantes React Bits -TW compatibles v3 et vérifier tailwind.config";; esac
else warn "tailwindcss absent → les variantes -TW ne fonctionneront pas"; fi

echo "shadcn"
if [ -f components.json ]; then
  ok "components.json présent"
  node -e "const c=require('./components.json');console.log('  - registries:',JSON.stringify(c.registries||{}));console.log('  - aliases:',JSON.stringify(c.aliases))"
else warn "components.json absent → lance SKILLS/scripts/setup.sh"; fi
[ -f src/lib/utils.ts ] && { grep -q "twMerge" src/lib/utils.ts && ok "src/lib/utils.ts : cn() OK" || warn "src/lib/utils.ts n'implémente pas cn() (écrasé par un registry ?) :  $(head -1 src/lib/utils.ts)"; } || warn "src/lib/utils.ts absent"
grep -q '"@/\*"' tsconfig.json 2>/dev/null && ok "alias @/* dans tsconfig" || warn "alias @/* manquant dans tsconfig"
grep -q 'alias' vite.config.* 2>/dev/null && ok "alias dans vite.config" || info "pas d'alias vite détecté"

echo "Dépendances de la stack"
for d in animejs echarts motion framer-motion gsap lenis three ogl lucide-react class-variance-authority react-icons; do
  has_dep "$d" && ok "$d $(ver $d)" || info "$d : non installé"
done
has_dep framer-motion && has_dep motion && warn "framer-motion ET motion : unifier sur motion/react"
has_dep animejs && node -e "process.exit(/^[\^~]?[0-3]\./.test(require('./package.json').dependencies.animejs||'')?0:1)" && warn "animejs < 4 : API différente (v3) — voir references/anime-js.md"

echo "Composants installés"
for d in src/components/ui src/components/kokonutui src/components/watermelon; do [ -d "$d" ] && info "$d : $(ls $d | wc -l) fichier(s)"; done
echo "Fait."
