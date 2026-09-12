import type { Locale } from "./i18n/shared";

export type ErrorExplanation = {
  title: string;
  explanation: string;
  action?: string;
};

type Rule = {
  match: RegExp;
  fr: ErrorExplanation;
  en: ErrorExplanation;
};

/**
 * Translates raw API / engine error messages into a readable title, an
 * explanation of what actually happened, and a suggested corrective action.
 * Rules are matched against the raw message; the first hit wins.
 */
const RULES: Rule[] = [
  {
    match: /INSUFFICIENT_KRONES|Solde insuffisant/i,
    fr: {
      title: "Solde Krônes insuffisant",
      explanation: "La création d'un service débite le portefeuille. Le solde actuel ne couvre pas le coût.",
      action: "Ouvrez la boutique Krônes pour recharger, ou liez Discord pour partager le solde du site public.",
    },
    en: {
      title: "Not enough Krônes",
      explanation: "Creating a service debits the wallet. The current balance does not cover the cost.",
      action: "Open the Krônes shop to top up, or link Discord to share the public-site balance.",
    },
  },
  {
    match: /COMMAND_SOURCES_LOCKED/i,
    fr: {
      title: "Sources des commandes protégées",
      explanation:
        "Le contenu exact des cogs Synkrone n'est pas lisible depuis Fichiers : ce sont nos commandes.",
      action:
        "Le rang Kronalloy (et au-dessus) débloque la lecture et la modification de ces fichiers. Liste des dossiers, config et le reste du volume restent accessibles. SFTP n'est pas filtré de la même façon.",
    },
    en: {
      title: "Command sources are locked",
      explanation:
        "The exact Synkrone cog files cannot be read from Files: those are our commands.",
      action:
        "Kronalloy (and above) unlocks reading and editing those files. Directory listing, config and the rest of the volume stay available. SFTP is not filtered the same way.",
    },
  },
  {
    match: /DATABASE_UNAVAILABLE|The database is unreachable|connect ECONNREFUSED/i,
    fr: {
      title: "Base de données injoignable",
      explanation:
        "Le panneau tourne, mais PostgreSQL n'accepte pas les connexions (souvent le conteneur postgres est arrêté).",
      action: "Démarrez Postgres puis rechargez la page.",
    },
    en: {
      title: "Database unreachable",
      explanation:
        "The panel is running, but PostgreSQL is not accepting connections (often the postgres container is stopped).",
      action: "Start Postgres then reload the page.",
    },
  },
  {
    match: /not reachable|DOCKER_UNAVAILABLE|socket .* not found/i,
    fr: {
      title: "Moteur de conteneurs injoignable",
      explanation:
        "L'API de contrôle n'arrive pas à joindre le démon Docker/Podman. Les fichiers, la configuration et les sauvegardes restent disponibles.",
      action:
        "Vérifiez que la socket est active : systemctl --user enable --now podman.socket (ou que le service Docker tourne).",
    },
    en: {
      title: "Container engine unreachable",
      explanation:
        "The control API cannot reach the Docker/Podman daemon. Files, configuration and backups keep working.",
      action:
        "Check the socket is active: systemctl --user enable --now podman.socket (or that the Docker service is running).",
    },
  },
  {
    match: /disallowed intents/i,
    fr: {
      title: "Intents Discord refusés",
      explanation:
        "Le bot demande des intents privilégiés que le portail développeur n'autorise pas encore.",
      action:
        "Dans le portail Discord → Bot, activez Server Members Intent et Message Content Intent, ou décochez GuildMembers / MessageContent / GuildPresences dans le panneau, puis redémarrez.",
    },
    en: {
      title: "Discord intents refused",
      explanation:
        "The bot requests privileged intents that the developer portal has not enabled yet.",
      action:
        "In the Discord portal → Bot, enable Server Members Intent and Message Content Intent, or uncheck GuildMembers / MessageContent / GuildPresences in the panel, then restart.",
    },
  },
  {
    match: /stored but cannot be decrypted|could not be encrypted with the current server key/i,
    fr: {
      title: "Token Discord illisible",
      explanation:
        "Un token est bien enregistré, mais le panel ne peut plus le déchiffrer (clé serveur changée ou héritée d'un autre process).",
      action:
        "Collez à nouveau le token dans l'onglet Token, enregistrez, puis redémarrez. Inutile de le réinitialiser sur Discord s'il n'a pas fuité.",
    },
    en: {
      title: "Discord token unreadable",
      explanation:
        "A token is stored, but the panel can no longer decrypt it (server key changed or inherited from another process).",
      action:
        "Paste the token again in the Token tab, save, then restart. You do not need to reset it on Discord unless it leaked.",
    },
  },
  {
    match: /BOT_TOKEN is not set/i,
    fr: {
      title: "Token Discord manquant",
      explanation:
        "Le bot ne peut pas se connecter à Discord sans token d'authentification.",
      action:
        "Collez le token de votre bot (portail développeur Discord → Bot → Reset Token) dans l'onglet Token, puis redémarrez.",
    },
    en: {
      title: "Discord token missing",
      explanation: "The bot cannot connect to Discord without an authentication token.",
      action:
        "Paste your bot token (Discord developer portal → Bot → Reset Token) in the Token tab, then start the service again.",
    },
  },
  {
    match: /Authentication required/i,
    fr: {
      title: "Authentification requise",
      explanation: "Votre session a expiré ou n'est plus valide.",
      action: "Reconnectez-vous.",
    },
    en: {
      title: "Authentication required",
      explanation: "Your session has expired or is no longer valid.",
      action: "Sign in again.",
    },
  },
  {
    match: /Current password is incorrect/i,
    fr: {
      title: "Mot de passe actuel incorrect",
      explanation: "Le mot de passe actuel ne correspond pas à celui du compte.",
      action: "Vérifiez la saisie, ou utilisez un mot de passe que vous connaissez.",
    },
    en: {
      title: "Current password is incorrect",
      explanation: "The current password does not match this account.",
      action: "Check what you typed, or use a password you know.",
    },
  },
  {
    match: /Password must be at least 8 characters/i,
    fr: {
      title: "Mot de passe trop court",
      explanation: "Le mot de passe doit contenir au moins 8 caractères.",
      action: "Choisissez un mot de passe plus long.",
    },
    en: {
      title: "Password too short",
      explanation: "The password must be at least 8 characters.",
      action: "Choose a longer password.",
    },
  },
  {
    match: /Invalid email or password/i,
    fr: {
      title: "Identifiants incorrects",
      explanation: "L'e-mail ou le mot de passe saisi ne correspond à aucun compte.",
      action: "Vérifiez la saisie ou créez un compte.",
    },
    en: {
      title: "Invalid credentials",
      explanation: "The email or password you entered does not match any account.",
      action: "Check your input or create an account.",
    },
  },
  {
    match: /already uses this email/i,
    fr: {
      title: "E-mail déjà utilisé",
      explanation: "Un compte existe déjà avec cette adresse e-mail.",
      action: "Connectez-vous plutôt, ou utilisez une autre adresse.",
    },
    en: {
      title: "Email already in use",
      explanation: "An account already exists with this email address.",
      action: "Sign in instead, or use a different address.",
    },
  },
  {
    match: /Too many requests/i,
    fr: {
      title: "Trop de requêtes",
      explanation: "L'action a été tentée trop souvent en peu de temps (limite de débit).",
      action: "Patientez une minute avant de réessayer.",
    },
    en: {
      title: "Too many requests",
      explanation: "The action was attempted too often in a short time (rate limit).",
      action: "Wait a minute before trying again.",
    },
  },
  {
    match: /no container is registered/i,
    fr: {
      title: "Aucun conteneur",
      explanation: "Ce service n'a pas encore de conteneur associé.",
      action: "Lancez d'abord une création ou un déploiement.",
    },
    en: {
      title: "No container",
      explanation: "This service has no container registered yet.",
      action: "Run a create or deploy first.",
    },
  },
  {
    match: /Path traversal|Path escapes|Symlink escapes/i,
    fr: {
      title: "Chemin refusé",
      explanation:
        "Le chemin demandé sortirait du volume du service. Le gestionnaire de fichiers l'a bloqué par sécurité.",
    },
    en: {
      title: "Path refused",
      explanation:
        "The requested path would escape the service volume. The file manager blocked it for safety.",
    },
  },
  {
    match: /File too large/i,
    fr: {
      title: "Fichier trop volumineux",
      explanation: "L'éditeur intégré est limité aux fichiers texte de 2 Mo maximum.",
      action: "Utilisez SFTP pour les gros fichiers.",
    },
    en: {
      title: "File too large",
      explanation: "The built-in editor is limited to text files of 2 MB maximum.",
      action: "Use SFTP for large files.",
    },
  },
  {
    match: /pull|image/i,
    fr: {
      title: "Échec du téléchargement d'image",
      explanation: "Le moteur n'a pas pu récupérer l'image du runtime.",
      action: "Vérifiez la connexion réseau de l'hôte et le nom de l'image, puis réessayez.",
    },
    en: {
      title: "Image pull failed",
      explanation: "The engine could not fetch the runtime image.",
      action: "Check the host network connection and the image name, then retry.",
    },
  },
  {
    match: /GITHUB_NOT_CONFIGURED|GitHub OAuth is not configured/i,
    fr: {
      title: "GitHub OAuth non configuré",
      explanation: "Le serveur n'a pas GITHUB_CLIENT_ID / GITHUB_CLIENT_SECRET.",
      action: "Renseignez ces variables dans .env, enregistrez l'URI de redirection, puis redémarrez le panneau.",
    },
    en: {
      title: "GitHub OAuth is not configured",
      explanation: "The server is missing GITHUB_CLIENT_ID / GITHUB_CLIENT_SECRET.",
      action: "Set those variables in .env, register the redirect URI, then restart the panel.",
    },
  },
  {
    match: /GITHUB_NOT_LINKED|Link a GitHub account/i,
    fr: {
      title: "GitHub n'est pas lié",
      explanation: "L'import d'un dépôt exige un compte GitHub lié à votre profil Synkrone.",
      action: "Ouvrez Compte → Profil et cliquez sur Lier GitHub, puis réessayez.",
    },
    en: {
      title: "GitHub is not linked",
      explanation: "Importing a repository requires a GitHub account linked to your Synkrone profile.",
      action: "Open Account → Profile, click Link GitHub, then try again.",
    },
  },
  {
    match: /OAUTH_TOKEN_EXPIRED|token expired/i,
    fr: {
      title: "Jeton OAuth expiré",
      explanation: "Le jeton du fournisseur n'est plus valable.",
      action: "Déliez puis reliez le compte depuis Compte → Profil.",
    },
    en: {
      title: "OAuth token expired",
      explanation: "The provider token is no longer valid.",
      action: "Unlink and link the account again from Account → Profile.",
    },
  },
  {
    match: /not found|introuvable/i,
    fr: {
      title: "Élément introuvable",
      explanation: "La ressource demandée n'existe pas ou a été supprimée.",
      action: "Actualisez la page.",
    },
    en: {
      title: "Not found",
      explanation: "The requested resource does not exist or was deleted.",
      action: "Refresh the page.",
    },
  },
  {
    match: /fetch failed|NetworkError|Failed to fetch|ECONNREFUSED/i,
    fr: {
      title: "Erreur réseau",
      explanation: "Le navigateur n'a pas pu joindre le serveur du panneau.",
      action: "Vérifiez que le serveur tourne et réessayez.",
    },
    en: {
      title: "Network error",
      explanation: "The browser could not reach the panel server.",
      action: "Check the server is running and retry.",
    },
  },
];

const FALLBACK: Record<Locale, (message: string) => ErrorExplanation> = {
  fr: (message) => ({
    title: "L'action a échoué",
    explanation: "Une erreur inattendue s'est produite.",
    action: message || undefined,
  }),
  en: (message) => ({
    title: "The action failed",
    explanation: "An unexpected error occurred.",
    action: message || undefined,
  }),
};

export function explainError(message: string, locale: Locale): ErrorExplanation {
  for (const rule of RULES) {
    if (rule.match.test(message)) return rule[locale];
  }
  return FALLBACK[locale](message);
}
