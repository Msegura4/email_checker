"""
main.py
Point d'entrée principal de l'agent de traitement de tickets.
Orchestre : lecture mail (Gmail ou IMAP) → classification LLM → écriture Google Sheet.

Sélection du provider via la variable d'environnement MAIL_PROVIDER :
    MAIL_PROVIDER=gmail   → Gmail OAuth2      (défaut)
    MAIL_PROVIDER=imap    → IMAP (Thunderbird, Outlook, Yahoo, OVH...)

Sélection du profil via la variable d'environnement ACTIVE_PROFILE :
    ACTIVE_PROFILE=support_informatique   (défaut)
"""

import time
import os
from dotenv import load_dotenv

from agent_mail import classify_mail
from drive_client import DriveClient
from mail_reader_base import BaseMailReader
from profile_manager import load_profile, build_context_txt, build_prompt_txt, get_category_to_sheet
from pathlib import Path

load_dotenv()

# ── Configuration ──────────────────────────────────────────────────────────────
SPREADSHEET_ID      = os.getenv("GOOGLE_SHEET_ID")
MAIL_PROVIDER       = os.getenv("MAIL_PROVIDER", "gmail").lower()
ACTIVE_PROFILE_ID   = os.getenv("ACTIVE_PROFILE", "support_informatique")
DELAY_BETWEEN_CALLS = float(os.getenv("DELAY_BETWEEN_CALLS", 0.5))
MAX_EMAILS          = int(os.getenv("MAX_EMAILS", 500))
MARK_AS_READ        = os.getenv("MARK_AS_READ", "false").lower() == "true"


# ── Chargement du profil ───────────────────────────────────────────────────────

def load_active_profile() -> dict:
    profile = load_profile(ACTIVE_PROFILE_ID)
    if not profile:
        raise ValueError(
            f"Profil '{ACTIVE_PROFILE_ID}' introuvable. "
            f"Vérifiez la variable ACTIVE_PROFILE dans .env."
        )
    return profile


# ── Sélection du reader ────────────────────────────────────────────────────────

def build_reader() -> BaseMailReader:
    """Instancie le bon lecteur de mail selon MAIL_PROVIDER."""
    if MAIL_PROVIDER == "gmail":
        from mail_reader_gmail import GmailReader
        print("📧 Provider : Gmail (OAuth2)")
        return GmailReader()
    elif MAIL_PROVIDER == "imap":
        from mail_reader_imap import IMAPReader
        host = os.getenv("IMAP_HOST", "?")
        user = os.getenv("IMAP_USER", "?")
        print(f"📧 Provider : IMAP  ({user} @ {host})")
        return IMAPReader()
    else:
        raise ValueError(
            f"MAIL_PROVIDER inconnu : '{MAIL_PROVIDER}'. Valeurs acceptées : gmail, imap"
        )


# ── Traitement d'un ticket ─────────────────────────────────────────────────────

def process_ticket(
    reader: BaseMailReader,
    drive: DriveClient,
    ticket: dict,
    index: int,
    total: int,
    category_to_sheet: dict,
) -> None:
    sujet   = ticket.get("sujet", "(Sans sujet)")
    corps   = ticket.get("corps", "")
    mail_id = ticket.get("id")

    print(f"\n[{index}/{total}] 📧 {sujet[:65]}...")

    # 1. Classification LLM
    mail_content   = f"Sujet : {sujet}\n\n{corps}"
    classification = classify_mail(mail_content)

    categorie = classification.get("categorie", list(category_to_sheet.keys())[0])
    urgence   = classification.get("urgence",   "Modérée")
    resume    = classification.get("résumé",    sujet)

    print(f"         → Catégorie : {categorie}")
    print(f"         → Urgence   : {urgence}")
    print(f"         → Synthèse  : {resume[:80]}...")

    # 2. Écriture dans Google Sheet
    sheet_name = category_to_sheet.get(categorie, list(category_to_sheet.values())[0])
    drive.write_to_sheet(sheet_name, sujet, urgence, resume)

    # 3. Marquer comme lu
    if MARK_AS_READ:
        reader.mark_as_read(mail_id)


# ── Point d'entrée ─────────────────────────────────────────────────────────────

def main():
    # Chargement du profil
    profile = load_active_profile()

    print("=" * 60)
    print("   AGENT DE TRAITEMENT DE TICKETS")
    print(f"   Profil   : {profile.get('emoji','')} {profile['nom']}")
    print(f"   Provider : {MAIL_PROVIDER.upper()}")
    print("=" * 60)

    # Écriture des fichiers context/prompt pour l'agent LLM
    Path("context.txt").write_text(build_context_txt(profile), encoding="utf-8")
    Path("prompt.txt").write_text(build_prompt_txt(profile),   encoding="utf-8")

    category_to_sheet = get_category_to_sheet(profile)

    # Connexion Google Sheets — profil transmis
    print("\n📊 Connexion à Google Sheets...")
    drive = DriveClient(SPREADSHEET_ID, profile)

    # Connexion au reader mail (context manager → fermeture propre)
    with build_reader() as reader:
        tickets = reader.fetch_unread_emails(
            max_results=MAX_EMAILS,
            mark_as_read=False,
        )

        if not tickets:
            print("\n✅ Aucun mail non lu à traiter.")
            return

        total   = len(tickets)
        success = 0
        errors  = 0

        print(f"\n🚀 Début du traitement de {total} ticket(s)...\n")

        for i, ticket in enumerate(tickets, 1):
            try:
                process_ticket(reader, drive, ticket, i, total, category_to_sheet)
                success += 1
            except Exception as e:
                errors += 1
                print(f"         ❌ Erreur sur '{ticket.get('sujet', '?')}' : {e}")

            if i < total:
                time.sleep(DELAY_BETWEEN_CALLS)

    # Tri et formatage final
    drive.finalize_all_sheets()

    print("\n" + "=" * 60)
    print("   ✅ Traitement terminé")
    print(f"   → Succès  : {success}/{total}")
    if errors:
        print(f"   → Erreurs : {errors}/{total}")
    print("=" * 60)


if __name__ == "__main__":
    main()
