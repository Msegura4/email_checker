"""
mail_reader_imap.py
Lecteur de mail via IMAP — compatible Thunderbird, Outlook, Yahoo, etc.
Configure les variables dans .env (voir README).
"""

import imaplib
import email
import re
import os
from email.header import decode_header

from dotenv import load_dotenv

from mail_reader_base import BaseMailReader

load_dotenv()


def _decode_mime_words(s: str) -> str:
    """Décode les en-têtes MIME encodés (ex: =?utf-8?b?...?=)."""
    if not s:
        return ""
    parts = decode_header(s)
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(part)
    return "".join(result)


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    return re.sub(r"\s+", " ", text).strip()


def _get_body(msg: email.message.Message) -> str:
    """Extrait le corps texte d'un message email (préfère text/plain)."""
    plain = ""
    html = ""

    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if "attachment" in cd:
                continue
            charset = part.get_content_charset() or "utf-8"
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            text = payload.decode(charset, errors="replace")
            if ct == "text/plain" and not plain:
                plain = text.strip()
            elif ct == "text/html" and not html:
                html = _strip_html(text).strip()
    else:
        charset = msg.get_content_charset() or "utf-8"
        payload = msg.get_payload(decode=True)
        if payload:
            text = payload.decode(charset, errors="replace")
            if msg.get_content_type() == "text/html":
                html = _strip_html(text).strip()
            else:
                plain = text.strip()

    return plain or html or ""


class IMAPReader(BaseMailReader):
    """
    Lecture des emails via IMAP.

    Variables .env requises :
        IMAP_HOST      : ex. imap.gmail.com / imap.mail.yahoo.com / outlook.office365.com
        IMAP_PORT      : 993 (SSL, recommandé) ou 143 (STARTTLS)
        IMAP_USER      : adresse email complète
        IMAP_PASSWORD  : mot de passe ou mot de passe d'application
        IMAP_FOLDER    : dossier à surveiller (défaut : INBOX)
        IMAP_USE_SSL   : true/false (défaut : true)

    ⚠️  Gmail : activer "Accès IMAP" dans les paramètres Gmail et générer
        un "mot de passe d'application" si la 2FA est activée.
    ⚠️  Thunderbird : utiliser les mêmes identifiants que dans Thunderbird.
    """

    # Serveurs IMAP courants pour référence rapide
    KNOWN_HOSTS = {
        "gmail":    ("imap.gmail.com", 993),
        "outlook":  ("outlook.office365.com", 993),
        "yahoo":    ("imap.mail.yahoo.com", 993),
        "icloud":   ("imap.mail.me.com", 993),
        "ovh":      ("ssl0.ovh.net", 993),
    }

    def __init__(self):
        self.host     = os.getenv("IMAP_HOST", "")
        self.port     = int(os.getenv("IMAP_PORT", 993))
        self.user     = os.getenv("IMAP_USER", "")
        self.password = os.getenv("IMAP_PASSWORD", "")
        self.folder   = os.getenv("IMAP_FOLDER", "INBOX")
        use_ssl       = os.getenv("IMAP_USE_SSL", "true").lower() != "false"

        if not self.host or not self.user or not self.password:
            raise ValueError(
                "Variables IMAP manquantes dans .env : IMAP_HOST, IMAP_USER, IMAP_PASSWORD"
            )

        print(f"[IMAP] Connexion à {self.host}:{self.port} en tant que {self.user}...")

        if use_ssl:
            self.conn = imaplib.IMAP4_SSL(self.host, self.port)
        else:
            self.conn = imaplib.IMAP4(self.host, self.port)
            self.conn.starttls()

        self.conn.login(self.user, self.password)
        print(f"[IMAP] Connecté. Dossier : {self.folder}")

    # ── Lecture des mails ─────────────────────────────────────────────────────

    def fetch_unread_emails(self, max_results: int = 500, mark_as_read: bool = False) -> list[dict]:
        self.conn.select(self.folder, readonly=not mark_as_read)

        # Cherche les messages non lus
        status, data = self.conn.search(None, "UNSEEN")
        if status != "OK" or not data[0]:
            print("[IMAP] Aucun email non lu.")
            return []

        mail_ids = data[0].split()
        # Les plus récents en premier, limités à max_results
        mail_ids = mail_ids[::-1][:max_results]

        print(f"[IMAP] {len(mail_ids)} email(s) non lu(s) trouvé(s).")
        tickets = []

        for i, mail_id in enumerate(mail_ids, 1):
            try:
                status, msg_data = self.conn.fetch(mail_id, "(RFC822)")
                if status != "OK":
                    continue

                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)

                sujet = _decode_mime_words(msg.get("Subject", "(Sans sujet)"))
                corps = _get_body(msg)

                tickets.append({
                    "id": mail_id.decode(),
                    "sujet": sujet,
                    "corps": corps,
                })

                if mark_as_read:
                    self.mark_as_read(mail_id.decode())

                print(f"  [{i}] {sujet[:70]}")

            except Exception as e:
                print(f"  [IMAP] Erreur sur le mail {mail_id} : {e}")
                continue

        print(f"\n[IMAP] {len(tickets)} emails récupérés.")
        return tickets

    def mark_as_read(self, mail_id: str) -> None:
        self.conn.store(mail_id.encode(), "+FLAGS", "\\Seen")

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass
        try:
            self.conn.logout()
        except Exception:
            pass
        print("[IMAP] Connexion fermée.")


# ── Test autonome ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    with IMAPReader() as reader:
        tickets = reader.fetch_unread_emails(max_results=10)
        for t in tickets:
            print(f"\nSujet : {t['sujet']}")
            print(f"Corps : {t['corps'][:200]}")
