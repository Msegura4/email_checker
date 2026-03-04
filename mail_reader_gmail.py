"""
mail_reader_gmail.py
Lecteur Gmail via OAuth2 (Google API).
Remplace l'ancien mail_reader.py en implémentant BaseMailReader.
"""

import os
import base64
import re

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from mail_reader_base import BaseMailReader

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"


class GmailReader(BaseMailReader):
    """
    Lecture des emails via l'API Gmail (OAuth2).

    Nécessite :
        - credentials.json  : Client ID OAuth2 (type Desktop app)
        - token.json        : généré par generate_token.py
    """

    def __init__(self):
        self.service = self._get_service()

    # ── Authentification ──────────────────────────────────────────────────────

    def _get_service(self):
        creds = None

        if os.path.exists(TOKEN_FILE):
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                print("[Gmail] Token expiré, rafraîchissement...")
                creds.refresh(Request())
            else:
                print("[Gmail] Authentification OAuth2 requise")
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                creds = flow.run_local_server(port=0)

            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
            print(f"[Gmail] Token sauvegardé dans '{TOKEN_FILE}'.")

        return build("gmail", "v1", credentials=creds)

    # ── Lecture des mails ─────────────────────────────────────────────────────

    def fetch_unread_emails(self, max_results: int = 500, mark_as_read: bool = False) -> list[dict]:
        tickets = []
        page_token = None
        fetched = 0

        print(f"[Gmail] Récupération des emails non lus (max {max_results})")

        try:
            while fetched < max_results:
                batch_size = min(100, max_results - fetched)
                params = {
                    "userId": "me",
                    "q": "is:unread",
                    "maxResults": batch_size,
                    "labelIds": ["INBOX"],
                }
                if page_token:
                    params["pageToken"] = page_token

                response = self.service.users().messages().list(**params).execute()
                messages = response.get("messages", [])
                if not messages:
                    break

                for msg_ref in messages:
                    msg_id = msg_ref["id"]
                    try:
                        msg = (
                            self.service.users()
                            .messages()
                            .get(userId="me", id=msg_id, format="full")
                            .execute()
                        )
                        headers = msg.get("payload", {}).get("headers", [])
                        sujet = next(
                            (h["value"] for h in headers if h["name"].lower() == "subject"),
                            "(Sans sujet)",
                        )
                        corps = self._extract_body(msg.get("payload", {}))
                        tickets.append({"id": msg_id, "sujet": sujet, "corps": corps})

                        if mark_as_read:
                            self.mark_as_read(msg_id)

                        fetched += 1
                        print(f"  [{fetched}] {sujet[:70]}")

                    except HttpError as e:
                        print(f"  [Gmail] Erreur sur le mail {msg_id} : {e}")
                        continue

                page_token = response.get("nextPageToken")
                if not page_token:
                    break

        except HttpError as e:
            print(f"[Gmail] Erreur API : {e}")
            raise

        print(f"\n[Gmail] {len(tickets)} emails récupérés.")
        return tickets

    def mark_as_read(self, mail_id: str) -> None:
        self.service.users().messages().modify(
            userId="me",
            id=mail_id,
            body={"removeLabelIds": ["UNREAD"]},
        ).execute()

    def close(self) -> None:
        # L'API Gmail n'a pas de connexion persistante à fermer
        pass

    # ── Helpers décodage ──────────────────────────────────────────────────────

    @staticmethod
    def _decode_part(data: str) -> str:
        padding = 4 - len(data) % 4
        data += "=" * (padding % 4)
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    @staticmethod
    def _strip_html(html: str) -> str:
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)
        return re.sub(r"\s+", " ", text).strip()

    def _extract_body(self, payload: dict) -> str:
        mime_type = payload.get("mimeType", "")
        parts = payload.get("parts", [])
        body_data = payload.get("body", {}).get("data", "")

        if not parts:
            if not body_data:
                return ""
            text = self._decode_part(body_data)
            if mime_type == "text/html":
                text = self._strip_html(text)
            return text.strip()

        plain_text = ""
        html_text = ""
        for part in parts:
            part_mime = part.get("mimeType", "")
            part_data = part.get("body", {}).get("data", "")
            if part_mime == "text/plain" and part_data:
                plain_text = self._decode_part(part_data).strip()
            elif part_mime == "text/html" and part_data:
                html_text = self._strip_html(self._decode_part(part_data)).strip()
            elif part_mime.startswith("multipart/"):
                nested = self._extract_body(part)
                if nested:
                    plain_text = plain_text or nested

        return plain_text or html_text or ""


# ── Test autonome ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    with GmailReader() as reader:
        tickets = reader.fetch_unread_emails(max_results=10)
        for t in tickets:
            print(f"\nSujet : {t['sujet']}")
            print(f"Corps : {t['corps'][:200]}")
