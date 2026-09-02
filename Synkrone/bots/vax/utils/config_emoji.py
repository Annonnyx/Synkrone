"""Configuration centralisee des emojis.

Regles:
- Version custom prioritaire.
- Si pas de custom, custom == fallback.
- Les tuiles 2048 sont gerees dans 2048.py.
- Listing exhaustif des emojis utilises dans cogs/ et utils/ (noms de fichiers).
"""

from __future__ import annotations

import re
from pathlib import Path


def _resolve_emoji(custom_value: str | None, fallback_value: str) -> str:
    return custom_value if custom_value else fallback_value


def _build_usage_index() -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Retourne:
    - usage par symbole emoji
    - usage par constante E.NOM

    Les valeurs contiennent des noms de fichiers uniquement.
    """
    root = Path(__file__).resolve().parent.parent
    targets = [root / "cogs", root / "utils"]

    custom_re = re.compile(r"<a?:[A-Za-z0-9_]+:[0-9]+>")
    e_ref_re = re.compile(r"\bE\.([A-Z0-9_]+)\b")
    unicode_re = re.compile(r"(?:[\U0001F300-\U0001FAFF]|[\u2600-\u27BF]|[0-9#*]\uFE0F?\u20E3)")

    by_symbol: dict[str, set[str]] = {}
    by_constant: dict[str, set[str]] = {}

    for base in targets:
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue

            filename = path.name
            try:
                content = path.read_text(encoding="utf-8")
            except Exception:
                continue

            for m in custom_re.finditer(content):
                by_symbol.setdefault(m.group(0), set()).add(filename)
            for m in unicode_re.finditer(content):
                by_symbol.setdefault(m.group(0), set()).add(filename)
            for m in e_ref_re.finditer(content):
                by_constant.setdefault(m.group(1), set()).add(filename)

    out_symbol = {k: sorted(v) for k, v in sorted(by_symbol.items())}
    out_constant = {k: sorted(v) for k, v in sorted(by_constant.items())}
    return out_symbol, out_constant


class Emoji:
    # =========================================================
    # Emojis racines (custom + fallback)
    # =========================================================
    VALIDER_CUSTOM = "<:1VValider:1534254861498056852>"
    VALIDER_FALLBACK = "✅"
    VALIDER = _resolve_emoji(VALIDER_CUSTOM, VALIDER_FALLBACK)

    RETOUR_CUSTOM = "<:1VRetour:1534254856804634746>"
    RETOUR_FALLBACK = "↩️"
    RETOUR = _resolve_emoji(RETOUR_CUSTOM, RETOUR_FALLBACK)

    REFUSER_CUSTOM = "<:1VRefuser:1534254904695328860>"
    REFUSER_FALLBACK = "❌"
    REFUSER = _resolve_emoji(REFUSER_CUSTOM, REFUSER_FALLBACK)

    PROFIL_CUSTOM = "<:1VProfil:1534255770647134238>"
    PROFIL_FALLBACK = "👤"
    PROFIL = _resolve_emoji(PROFIL_CUSTOM, PROFIL_FALLBACK)

    OWNER_CUSTOM = "<:1VOwner:1534254898420519043>"
    OWNER_FALLBACK = "👑"
    OWNER = _resolve_emoji(OWNER_CUSTOM, OWNER_FALLBACK)

    ACCUEIL_CUSTOM = "<:1VAccueil:1534254872885596383>"
    ACCUEIL_FALLBACK = "🏠"
    ACCUEIL = _resolve_emoji(ACCUEIL_CUSTOM, ACCUEIL_FALLBACK)

    CLASSEMENT_CUSTOM = "<:1VClassement:1534254882822029493>"
    CLASSEMENT_FALLBACK = "🏆"
    CLASSEMENT = _resolve_emoji(CLASSEMENT_CUSTOM, CLASSEMENT_FALLBACK)

    FLECHE_HAUT_CUSTOM = "<:1VFlecheDeHaut:1534254891407638568>"
    FLECHE_HAUT_FALLBACK = "⬆️"
    FLECHE_HAUT = _resolve_emoji(FLECHE_HAUT_CUSTOM, FLECHE_HAUT_FALLBACK)

    FLECHE_BAS_CUSTOM = "<:1VFlecheDeBas:1534254885149872310>"
    FLECHE_BAS_FALLBACK = "⬇️"
    FLECHE_BAS = _resolve_emoji(FLECHE_BAS_CUSTOM, FLECHE_BAS_FALLBACK)

    FLECHE_DROITE_CUSTOM = "<:1VFlecheDeDroite:1534254887418728609>"
    FLECHE_DROITE_FALLBACK = "➡️"
    FLECHE_DROITE = _resolve_emoji(FLECHE_DROITE_CUSTOM, FLECHE_DROITE_FALLBACK)

    RAFRAICHIR_FALLBACK = "🔄"
    RAFRAICHIR_CUSTOM = "<:1VRafrachir:1534254900672856217>"
    RAFRAICHIR = _resolve_emoji(RAFRAICHIR_CUSTOM, RAFRAICHIR_FALLBACK)

    IDENTIFIANT_FALLBACK = "🆔"
    IDENTIFIANT_CUSTOM = "<:1VIDENTIT:1534261517430558821>"
    IDENTIFIANT = _resolve_emoji(IDENTIFIANT_CUSTOM, IDENTIFIANT_FALLBACK)

    IMAGE_FALLBACK = "🖼️"
    IMAGE_CUSTOM = "<:1VImage:1538179900429697084>"
    IMAGE = _resolve_emoji(IMAGE_CUSTOM, IMAGE_FALLBACK)

    LIEN_FALLBACK = "🔗"
    LIEN_CUSTOM = "<:1VLien:1534254894138003707>"
    LIEN = _resolve_emoji(LIEN_CUSTOM, LIEN_FALLBACK)

    MONDE_FALLBACK = "🌐"
    MONDE_CUSTOM = "<:1VMonde:1538179909116231731>"
    MONDE = _resolve_emoji(MONDE_CUSTOM, MONDE_FALLBACK)

    STATUS_ONLINE_FALLBACK = "🟢"
    STATUS_ONLINE_CUSTOM = STATUS_ONLINE_FALLBACK
    STATUS_ONLINE = _resolve_emoji(STATUS_ONLINE_CUSTOM, STATUS_ONLINE_FALLBACK)

    STATUS_IDLE_FALLBACK = "🌙"
    STATUS_IDLE_CUSTOM = STATUS_IDLE_FALLBACK
    STATUS_IDLE = _resolve_emoji(STATUS_IDLE_CUSTOM, STATUS_IDLE_FALLBACK)

    STATUS_DND_FALLBACK = "🔴"
    STATUS_DND_CUSTOM = STATUS_DND_FALLBACK
    STATUS_DND = _resolve_emoji(STATUS_DND_CUSTOM, STATUS_DND_FALLBACK)

    STATUS_INVISIBLE_FALLBACK = "⚫"
    STATUS_INVISIBLE_CUSTOM = STATUS_INVISIBLE_FALLBACK
    STATUS_INVISIBLE = _resolve_emoji(STATUS_INVISIBLE_CUSTOM, STATUS_INVISIBLE_FALLBACK)

    ATTENTION_FALLBACK = "⚠️"
    ATTENTION_CUSTOM = "<:1VAttention:1534254878417747998>"
    ATTENTION = _resolve_emoji(ATTENTION_CUSTOM, ATTENTION_FALLBACK)

    AJOUTER_FALLBACK = "➕"
    AJOUTER_CUSTOM = "<:1VAjouter:1534254875083407480>"
    AJOUTER = _resolve_emoji(AJOUTER_CUSTOM, AJOUTER_FALLBACK)

    MODIFIER_FALLBACK = "✏️"
    MODIFIER_CUSTOM = "<:1VModifier:1534254896348397629>"
    MODIFIER = _resolve_emoji(MODIFIER_CUSTOM, MODIFIER_FALLBACK)

    SUPPRIMER_FALLBACK = "🗑️"
    SUPPRIMER_CUSTOM = "<:1VSupprimer:1534254858972954704>"
    SUPPRIMER = _resolve_emoji(SUPPRIMER_CUSTOM, SUPPRIMER_FALLBACK)

    FLECHE_GAUCHE_FALLBACK = "⬅️"
    FLECHE_GAUCHE_CUSTOM = "<:1VFlecheDeGauche:1534254889411280997>"
    FLECHE_GAUCHE = _resolve_emoji(FLECHE_GAUCHE_CUSTOM, FLECHE_GAUCHE_FALLBACK)

    ROLE_FALLBACK = "🎭"
    ROLE_CUSTOM = "<:1VRoles:1534265633351405860>"
    ROLE = _resolve_emoji(ROLE_CUSTOM, ROLE_FALLBACK)

    VAX_CUSTOM = "<:vax:1506410094529740840>"
    VAX_FALLBACK = "🤖"
    VAX = _resolve_emoji(VAX_CUSTOM, VAX_FALLBACK)

    BOUCLIER_FALLBACK = "🛡️"
    BOUCLIER_CUSTOM = "<:V1Bouclier:1538179919824035950>"
    BOUCLIER = _resolve_emoji(BOUCLIER_CUSTOM, BOUCLIER_FALLBACK)

    CIBLE_FALLBACK = "🎯"
    CIBLE_CUSTOM = "<:V1Cible:1538179918167543838>"
    CIBLE = _resolve_emoji(CIBLE_CUSTOM, CIBLE_FALLBACK)

    DES_FALLBACK = "🎲"
    DES_CUSTOM = "<:1VDes:1538179923330596945>"
    DES = _resolve_emoji(DES_CUSTOM, DES_FALLBACK)

    EPEES_FALLBACK = "⚔️"
    EPEES_CUSTOM = "<:1VEpee:1538179916573577256>"
    EPEES = _resolve_emoji(EPEES_CUSTOM, EPEES_FALLBACK)

    JEU_FALLBACK = "🎮"
    JEU_CUSTOM = "<:1VJeux:1538179902191435847>"
    JEU = _resolve_emoji(JEU_CUSTOM, JEU_FALLBACK)

    RECHERCHE_FALLBACK = "🔎"
    RECHERCHE_CUSTOM = "<:1VRechercher:1534254902644179114>"
    RECHERCHE = _resolve_emoji(RECHERCHE_CUSTOM, RECHERCHE_FALLBACK)

    LAMPE_FALLBACK = "💡"
    LAMPE_CUSTOM = "<:1VLampe:1538179911116914818>"
    LAMPE = _resolve_emoji(LAMPE_CUSTOM, LAMPE_FALLBACK)

    HORLOGE_FALLBACK = "⏱️"
    HORLOGE_CUSTOM = "<:1VHorloge:1538179915101507695>"
    HORLOGE = _resolve_emoji(HORLOGE_CUSTOM, HORLOGE_FALLBACK)

    MEMO_FALLBACK = "📝"
    MEMO_CUSTOM = "<:1VMemo:1538179913104883734>"
    MEMO = _resolve_emoji(MEMO_CUSTOM, MEMO_FALLBACK)

    COEUR_FALLBACK = "❤️"
    COEUR_CUSTOM = "<:1VCoeur:1538179906913964102>"
    COEUR = _resolve_emoji(COEUR_CUSTOM, COEUR_FALLBACK)

    COEUR_BRISE_FALLBACK = "💔"
    COEUR_BRISE_CUSTOM = "<:1VCoeurBrise:1538179904204447785>"
    COEUR_BRISE = _resolve_emoji(COEUR_BRISE_CUSTOM, COEUR_BRISE_FALLBACK)

    BAGUE_FALLBACK = "💍"
    BAGUE_CUSTOM = "<:V1Bague:1538179921497694299>"
    BAGUE = _resolve_emoji(BAGUE_CUSTOM, BAGUE_FALLBACK)

    QUESTION_FALLBACK = "❓"
    QUESTION_CUSTOM = "<:1VQuestions:1540008213104164945>"
    QUESTION = _resolve_emoji(QUESTION_CUSTOM, QUESTION_FALLBACK)

    INFO_FALLBACK = "ℹ️"
    INFO_CUSTOM = "<:1VInformation:1540008199825006713>"
    INFO = _resolve_emoji(INFO_CUSTOM, INFO_FALLBACK)

    LISTE_FALLBACK = "📋"
    LISTE_CUSTOM = "<:1VListe:1540008201683206204>"
    LISTE = _resolve_emoji(LISTE_CUSTOM, LISTE_FALLBACK)

    DOCUMENT_FALLBACK = "📄"
    DOCUMENT_CUSTOM = "<:1VDocument:1540008194984779897>"
    DOCUMENT = _resolve_emoji(DOCUMENT_CUSTOM, DOCUMENT_FALLBACK)

    HISTOIRE_FALLBACK = "📜"
    HISTOIRE_CUSTOM = "<:1VHistoire:1540008198021451859>"
    HISTOIRE = _resolve_emoji(HISTOIRE_CUSTOM, HISTOIRE_FALLBACK)

    GRAPHIQUE_FALLBACK = "📊"
    GRAPHIQUE_CUSTOM = "<:1VStats:1540008214744277063>"
    GRAPHIQUE = _resolve_emoji(GRAPHIQUE_CUSTOM, GRAPHIQUE_FALLBACK)

    HAUSSE_FALLBACK = "📈"
    HAUSSE_CUSTOM = "<:1VHausse:1540008196440330261>"
    HAUSSE = _resolve_emoji(HAUSSE_CUSTOM, HAUSSE_FALLBACK)

    BAISSE_FALLBACK = "📉"
    BAISSE_CUSTOM = "<:1VBaisse:1540008190278897734>"
    BAISSE = _resolve_emoji(BAISSE_CUSTOM, BAISSE_FALLBACK)

    ANNONCE_FALLBACK = "📢"
    ANNONCE_CUSTOM = "<:1VAnnonce:1540008188802506855>"
    ANNONCE = _resolve_emoji(ANNONCE_CUSTOM, ANNONCE_FALLBACK)

    CLOCHE_FALLBACK = "🔔"
    CLOCHE_CUSTOM = "<:1VNotification:1540008205172871268>"
    CLOCHE = _resolve_emoji(CLOCHE_CUSTOM, CLOCHE_FALLBACK)

    ETOILE_FALLBACK = "⭐"
    ETOILE_CUSTOM = ETOILE_FALLBACK
    ETOILE = _resolve_emoji(ETOILE_CUSTOM, ETOILE_FALLBACK)

    EXCELLENT_FALLBACK = "🌟"
    EXCELLENT_CUSTOM = EXCELLENT_FALLBACK
    EXCELLENT = _resolve_emoji(EXCELLENT_CUSTOM, EXCELLENT_FALLBACK)

    FEU_FALLBACK = "🔥"
    FEU_CUSTOM = FEU_FALLBACK
    FEU = _resolve_emoji(FEU_CUSTOM, FEU_FALLBACK)

    ECLAIR_FALLBACK = "⚡"
    ECLAIR_CUSTOM = ECLAIR_FALLBACK
    ECLAIR = _resolve_emoji(ECLAIR_CUSTOM, ECLAIR_FALLBACK)

    DIAMANT_FALLBACK = "💎"
    DIAMANT_CUSTOM = DIAMANT_FALLBACK
    DIAMANT = _resolve_emoji(DIAMANT_CUSTOM, DIAMANT_FALLBACK)

    BOULE_8_FALLBACK = "🎱"
    BOULE_8_CUSTOM = BOULE_8_FALLBACK
    BOULE_8 = _resolve_emoji(BOULE_8_CUSTOM, BOULE_8_FALLBACK)

    EXTRATERRESTRE_FALLBACK = "🎮"
    EXTRATERRESTRE_CUSTOM = "<:1VJeux:1538179902191435847>"
    EXTRATERRESTRE = _resolve_emoji(EXTRATERRESTRE_CUSTOM, EXTRATERRESTRE_FALLBACK)

    CADEAU_FALLBACK = "🎁"
    CADEAU_CUSTOM = "<:1VCadeau:1540008193034424431>"
    CADEAU = _resolve_emoji(CADEAU_CUSTOM, CADEAU_FALLBACK)

    AUTORITE_FALLBACK = "👮"
    AUTORITE_CUSTOM = "<:1VStaff:1540008207190069411>"
    AUTORITE = _resolve_emoji(AUTORITE_CUSTOM, AUTORITE_FALLBACK)

    LOAD_FALLBACK = "<a:load:1531764005402710207>"
    LOAD_CUSTOM = LOAD_FALLBACK
    LOAD = _resolve_emoji(LOAD_CUSTOM, LOAD_FALLBACK)

    BOOST_FALLBACK = "<a:boost:1508178804093354004>"
    BOOST_CUSTOM = BOOST_FALLBACK
    BOOST = _resolve_emoji(BOOST_CUSTOM, BOOST_FALLBACK)

    CONFIRMER_FALLBACK = "<:oui:1504857885031796778>"
    CONFIRMER_CUSTOM = CONFIRMER_FALLBACK
    CONFIRMER = _resolve_emoji(CONFIRMER_CUSTOM, CONFIRMER_FALLBACK)

    REFUSER_ACTION_FALLBACK = "<:non:1504857882452033586>"
    REFUSER_ACTION_CUSTOM = REFUSER_ACTION_FALLBACK
    REFUSER_ACTION = _resolve_emoji(REFUSER_ACTION_CUSTOM, REFUSER_ACTION_FALLBACK)

    OUI_FALLBACK = CONFIRMER_FALLBACK
    OUI_CUSTOM = CONFIRMER_CUSTOM
    OUI = _resolve_emoji(OUI_CUSTOM, OUI_FALLBACK)

    NON_FALLBACK = REFUSER_ACTION_FALLBACK
    NON_CUSTOM = REFUSER_ACTION_CUSTOM
    NON = _resolve_emoji(NON_CUSTOM, NON_FALLBACK)

    SYNKRONE_FALLBACK = "<:Synkrone:1502091722392469724>"
    SYNKRONE_CUSTOM = SYNKRONE_FALLBACK
    SYNKRONE = _resolve_emoji(SYNKRONE_CUSTOM, SYNKRONE_FALLBACK)

    KAYABA_FALLBACK = "<:kayaba:1505171139528233052>"
    KAYABA_CUSTOM = KAYABA_FALLBACK
    KAYABA = _resolve_emoji(KAYABA_CUSTOM, KAYABA_FALLBACK)

    ASUNA_FALLBACK = "<:Asuna:1505137735877525564>"
    ASUNA_CUSTOM = ASUNA_FALLBACK
    ASUNA = _resolve_emoji(ASUNA_CUSTOM, ASUNA_FALLBACK)

    YUI_FALLBACK = "<:yui:1505166357623214110>"
    YUI_CUSTOM = YUI_FALLBACK
    YUI = _resolve_emoji(YUI_CUSTOM, YUI_FALLBACK)

    CREATE_FALLBACK = AJOUTER_FALLBACK
    CREATE_CUSTOM = AJOUTER_CUSTOM
    CREATE = _resolve_emoji(CREATE_CUSTOM, CREATE_FALLBACK)

    EDIT_FALLBACK = MODIFIER_FALLBACK
    EDIT_CUSTOM = MODIFIER_CUSTOM
    EDIT = _resolve_emoji(EDIT_CUSTOM, EDIT_FALLBACK)

    DELETE_FALLBACK = SUPPRIMER_FALLBACK
    DELETE_CUSTOM = SUPPRIMER_CUSTOM
    DELETE = _resolve_emoji(DELETE_CUSTOM, DELETE_FALLBACK)

    SEND_FALLBACK = VALIDER_FALLBACK
    SEND_CUSTOM = VALIDER_CUSTOM
    SEND = _resolve_emoji(SEND_CUSTOM, SEND_FALLBACK)

    SUCCESS_FALLBACK = VALIDER_FALLBACK
    SUCCESS_CUSTOM = VALIDER_CUSTOM
    SUCCESS = _resolve_emoji(SUCCESS_CUSTOM, SUCCESS_FALLBACK)

    ERROR_FALLBACK = REFUSER_FALLBACK
    ERROR_CUSTOM = REFUSER_CUSTOM
    ERROR = _resolve_emoji(ERROR_CUSTOM, ERROR_FALLBACK)

    ERREUR_FALLBACK = ERROR_FALLBACK
    ERREUR_CUSTOM = ERROR_CUSTOM
    ERREUR = _resolve_emoji(ERREUR_CUSTOM, ERREUR_FALLBACK)

    BACK_FALLBACK = RETOUR_FALLBACK
    BACK_CUSTOM = RETOUR_CUSTOM
    BACK = _resolve_emoji(BACK_CUSTOM, BACK_FALLBACK)

    NEXT_FALLBACK = FLECHE_DROITE_FALLBACK
    NEXT_CUSTOM = FLECHE_DROITE_CUSTOM
    NEXT = _resolve_emoji(NEXT_CUSTOM, NEXT_FALLBACK)

    LINK_FALLBACK = LIEN_FALLBACK
    LINK_CUSTOM = LIEN_CUSTOM
    LINK = _resolve_emoji(LINK_CUSTOM, LINK_FALLBACK)

    TEXT_FALLBACK = MEMO_FALLBACK
    TEXT_CUSTOM = MEMO_CUSTOM
    TEXT = _resolve_emoji(TEXT_CUSTOM, TEXT_FALLBACK)

    THUMBNAIL_FALLBACK = IMAGE_FALLBACK
    THUMBNAIL_CUSTOM = IMAGE_CUSTOM
    THUMBNAIL = _resolve_emoji(THUMBNAIL_CUSTOM, THUMBNAIL_FALLBACK)

    BANNER_FALLBACK = IMAGE_FALLBACK
    BANNER_CUSTOM = IMAGE_CUSTOM
    BANNER = _resolve_emoji(BANNER_CUSTOM, BANNER_FALLBACK)

    COPY_FALLBACK = LISTE_FALLBACK
    COPY_CUSTOM = LISTE_CUSTOM
    COPY = _resolve_emoji(COPY_CUSTOM, COPY_FALLBACK)

    IMAGE_FALLBACK = IMAGE_FALLBACK
    IMAGE_CUSTOM = IMAGE_CUSTOM
    IMAGE = _resolve_emoji(IMAGE_CUSTOM, IMAGE_FALLBACK)

    WARNING_FALLBACK = ATTENTION_FALLBACK
    WARNING_CUSTOM = ATTENTION_CUSTOM
    WARNING = _resolve_emoji(WARNING_CUSTOM, WARNING_FALLBACK)

    HOME_FALLBACK = ACCUEIL_FALLBACK
    HOME_CUSTOM = ACCUEIL_CUSTOM
    HOME = _resolve_emoji(HOME_CUSTOM, HOME_FALLBACK)

    LOCK_FALLBACK = "🔒"
    LOCK_CUSTOM = "<:1VLock:1540008211560792125>"
    LOCK = _resolve_emoji(LOCK_CUSTOM, LOCK_FALLBACK)

    UNLOCK_FALLBACK = "🔓"
    UNLOCK_CUSTOM = "<:1VUnLock:1540008216300355614>"
    UNLOCK = _resolve_emoji(UNLOCK_CUSTOM, UNLOCK_FALLBACK)

    TEMPS_FALLBACK = "⏳"
    TEMPS_CUSTOM = "<:1VTemps:1540008209820024964>"
    TEMPS = _resolve_emoji(TEMPS_CUSTOM, TEMPS_FALLBACK)

    RAZ_FALLBACK = "♻️"
    RAZ_CUSTOM = "<:1VRaz:1540008217919103037>"
    RAZ = _resolve_emoji(RAZ_CUSTOM, RAZ_FALLBACK)

    VALIDE_FALLBACK = VALIDER_FALLBACK
    VALIDE_CUSTOM = VALIDER_CUSTOM
    VALIDE = _resolve_emoji(VALIDE_CUSTOM, VALIDE_FALLBACK)

    # =========================================================
    # Serie N1..N25: generee automatiquement en bas du module
    # =========================================================

    NUM_0_CUSTOM = "<:1NO:1534254870629191830>"
    NUM_0_FALLBACK = "0️⃣"
    NUM_0 = _resolve_emoji(NUM_0_CUSTOM, NUM_0_FALLBACK)

_NUMBER_SERIES_CUSTOM = {
    1: "<:1N1:1534254956276879491>",
    2: "<:1N2:1534254909136961646>",
    3: "<:1N3:1534254913633259681>",
    4: "<:1N4:1534254917735420014>",
    5: "<:1N5:1534254920117653514>",
    6: "<:1N6:1534254922462269672>",
    7: "<:1N7:1534254863590883378>",
    8: "<:1N8:1534254865763532921>",
    9: "<:1N9:1534254868015874209>",
    10: "<:1N1O:1534254906939015308>",
    11: "<:1N11:1534254924802691072>",
    12: "<:1N12:1534254926929334272>",
    13: "<:1N13:1534254928950984884>",
    14: "<:1N14:1534254931006062743>",
    15: "<:1N15:1534254934831403158>",
    16: "<:1N16:1534261506068320447>",
    17: "<:1N17:1534254937033150767>",
    18: "<:1N18:1534254940141387776>",
    19: "<:1N19:1534254944335560897>",
    20: "<:1N2O:1534254911284318308>",
    21: "<:1N21:1534254946562609433>",
    22: "<:1N22:1534254949809131680>",
    23: "<:1N23:1534254951843237888>",
    24: "<:1N24:1534254954204758109>",
    25: "<:1N25:1534261510526861473>",
}

def _number_fallback(i: int) -> str:
    if 1 <= i <= 9:
        return f"{i}️⃣"
    if i == 10:
        return "🔟"
    return "🔢"

for i in range(1, 26):
    custom = _NUMBER_SERIES_CUSTOM[i]
    fallback = _number_fallback(i)
    setattr(Emoji, f"N{i}_CUSTOM", custom)
    setattr(Emoji, f"N{i}_FALLBACK", fallback)
    setattr(Emoji, f"N{i}", _resolve_emoji(custom, fallback))

NUMBER_CUSTOM = {i: getattr(Emoji, f"N{i}") for i in range(1, 26)}

for i in range(1, 10):
    setattr(Emoji, f"NUM_{i}", NUMBER_CUSTOM[i])


def number_custom(index: int) -> str:
    return NUMBER_CUSTOM.get(index, str(index))


# Index exhaustif des emojis utilises (noms de fichiers uniquement)
EMOJI_USAGE_BY_SYMBOL, EMOJI_USAGE_BY_CONSTANT = _build_usage_index()
ALL_EMOJIS_USED = EMOJI_USAGE_BY_SYMBOL
