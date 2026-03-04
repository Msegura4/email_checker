"""
profile_manager.py
Gestion des profils de catégorisation.

Deux types de profils :
  - Défaut  : stockés dans profiles/defaults/, lecture seule, non supprimables.
  - Utilisateur : stockés dans profiles/, modifiables et supprimables.

Les profils chargés exposent un champ _is_default (bool) non persisté sur disque.
"""

import json
import os
import re
from pathlib import Path
from typing import Optional, List

# Répertoires
PROFILES_DIR  = Path(__file__).parent / "profiles"
DEFAULTS_DIR  = PROFILES_DIR / "defaults"


# ── Initialisation ────────────────────────────────────────────────────────────

def _ensure_dirs() -> None:
    PROFILES_DIR.mkdir(exist_ok=True)
    DEFAULTS_DIR.mkdir(exist_ok=True)


# ── Lecture ───────────────────────────────────────────────────────────────────

def list_default_profiles() -> List[dict]:
    """Retourne les profils par défaut (lecture seule)."""
    _ensure_dirs()
    profiles = []
    for f in sorted(DEFAULTS_DIR.glob("*.json")):
        try:
            with open(f, encoding="utf-8") as fp:
                data = json.load(fp)
                data["_is_default"] = True
                profiles.append(data)
        except Exception:
            continue
    return profiles


def list_user_profiles() -> List[dict]:
    """Retourne les profils créés par l'utilisateur."""
    _ensure_dirs()
    profiles = []
    for f in sorted(PROFILES_DIR.glob("*.json")):  # uniquement la racine, pas defaults/
        try:
            with open(f, encoding="utf-8") as fp:
                data = json.load(fp)
                data["_is_default"] = False
                profiles.append(data)
        except Exception:
            continue
    return profiles


def list_profiles() -> List[dict]:
    """Retourne tous les profils : défauts en premier, puis utilisateur."""
    return list_default_profiles() + list_user_profiles()


def load_profile(profile_id: str) -> Optional[dict]:
    """
    Charge un profil par son id.
    Cherche d'abord dans les profils utilisateur, puis dans les défauts.
    """
    user_path    = PROFILES_DIR / f"{profile_id}.json"
    default_path = DEFAULTS_DIR / f"{profile_id}.json"

    if user_path.exists():
        with open(user_path, encoding="utf-8") as f:
            data = json.load(f)
            data["_is_default"] = False
            return data

    if default_path.exists():
        with open(default_path, encoding="utf-8") as f:
            data = json.load(f)
            data["_is_default"] = True
            return data

    return None


def is_default_profile(profile_id: str) -> bool:
    """Indique si un profil est un profil par défaut (lecture seule)."""
    return (DEFAULTS_DIR / f"{profile_id}.json").exists()


# ── Écriture ──────────────────────────────────────────────────────────────────

def save_profile(profile: dict) -> bool:
    """
    Sauvegarde un profil utilisateur (crée ou écrase).
    Refuse de sauvegarder un profil par défaut (is_default_profile).
    """
    _ensure_dirs()
    profile_id = profile.get("id", "")
    if not profile_id:
        return False
    if is_default_profile(profile_id):
        raise PermissionError(
            f"Le profil '{profile_id}' est un profil par défaut et ne peut pas être modifié."
        )
    # Ne pas persister le flag interne
    to_save = {k: v for k, v in profile.items() if k != "_is_default"}
    path = PROFILES_DIR / f"{profile_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(to_save, f, ensure_ascii=False, indent=2)
    return True


def delete_profile(profile_id: str) -> bool:
    """
    Supprime un profil utilisateur.
    Refuse de supprimer un profil par défaut.
    """
    if is_default_profile(profile_id):
        raise PermissionError(
            f"Le profil '{profile_id}' est un profil par défaut et ne peut pas être supprimé."
        )
    path = PROFILES_DIR / f"{profile_id}.json"
    if path.exists():
        path.unlink()
        return True
    return False


def duplicate_profile(source_id: str, new_name: str) -> Optional[dict]:
    """
    Duplique n'importe quel profil (défaut ou utilisateur) sous un nouveau nom.
    Le duplicata est toujours sauvegardé comme profil utilisateur.
    Retourne le nouveau profil, ou None si la source est introuvable.
    """
    original = load_profile(source_id)
    if original is None:
        return None

    new_id = slugify(new_name)

    # Vérifier que l'id cible n'est pas déjà un profil par défaut
    if is_default_profile(new_id):
        raise ValueError(
            f"L'id '{new_id}' est réservé à un profil par défaut. Choisissez un autre nom."
        )

    new_profile = {
        k: v for k, v in original.items()
        if k != "_is_default"
    }
    new_profile["id"]  = new_id
    new_profile["nom"] = new_name

    save_profile(new_profile)
    new_profile["_is_default"] = False
    return new_profile


# ── Génération des fichiers LLM ───────────────────────────────────────────────

def build_context_txt(profile: dict) -> str:
    """Génère le contenu de context.txt à partir d'un profil."""
    cats     = profile.get("categories", [])
    urgences = profile.get("urgences",   [])
    context  = profile.get("context",    "")

    cat_lines = "\n".join(
        f"- {c['label']} : {c.get('description', '')}" for c in cats
    )
    urg_lines = "\n".join(
        f"- {u['label']} : {u.get('description', '')}" for u in urgences
    )
    cat_labels = "\n".join(f"  - {c['label']}" for c in cats)
    urg_labels = "\n".join(f"  - {u['label']}" for u in urgences)

    return f"""{context}

CATEGORIES
{cat_lines}

NIVEAUX D'URGENCE
{urg_lines}

RÈGLES
- Toujours retourner un JSON valide contenant "categorie", "urgence" et "résumé".
- Toujours choisir la meilleure catégorie possible même si le mail n'est pas explicite.
- Ne jamais inclure d'explications dans la réponse finale.
- Les valeurs exactes attendues pour "categorie" :
{cat_labels}
- Les valeurs exactes attendues pour "urgence" :
{urg_labels}
"""


def build_prompt_txt(profile: dict) -> str:
    """Génère le contenu de prompt.txt à partir d'un profil."""
    cats        = profile.get("categories", [])
    urgences    = profile.get("urgences",   [])
    prompt_base = profile.get("prompt",     "")

    cat_labels = "\n   - ".join(c["label"] for c in cats)
    urg_labels = "\n   - ".join(u["label"] for u in urgences)

    return f"""{prompt_base}

À partir du contenu de l'email fourni, détermine :

1. La catégorie parmi :
   - {cat_labels}

2. Le niveau d'urgence parmi :
   - {urg_labels}

Réponds uniquement en JSON :
{{
  "categorie": "...",
  "urgence": "...",
  "résumé": "..."
}}
"""


def get_category_to_sheet(profile: dict) -> dict:
    """Retourne le mapping label → sheet_id pour main.py et streamlit_app.py."""
    return {c["label"]: c["id"] for c in profile.get("categories", [])}


# ── Utilitaire ────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    """Convertit un nom en id slug (ex: 'Support IT' → 'support_it')."""
    text = text.lower().strip()
    text = re.sub(r"[àáâãäå]", "a", text)
    text = re.sub(r"[èéêë]",   "e", text)
    text = re.sub(r"[ìíîï]",   "i", text)
    text = re.sub(r"[òóôõö]",  "o", text)
    text = re.sub(r"[ùúûü]",   "u", text)
    text = re.sub(r"[ç]",      "c", text)
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")
