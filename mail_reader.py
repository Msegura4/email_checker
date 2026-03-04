import os
import base64
import re
from email import message_from_bytes

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"


def get_gmail_service():
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # Refresh si expiré, ou nouveau flow si absent / invalide
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Token expiré")
            creds.refresh(Request())
        else:
            print("Authentification OAuth2 requise")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        # Sauvegarde du token mis à jour
        with open(TOKEN_FILE, "w") as token_file:
            token_file.write(creds.to_json())
        print(f"Token sauvegardé dans '{TOKEN_FILE}'.")

    return build("gmail", "v1", credentials=creds)


def _decode_part(data: str) -> str:
    # Décode un payload base64url en texte UTF-8
    padding = 4 - len(data) % 4
    data += "=" * (padding % 4)
    return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")


def _strip_html(html: str) -> str:
    # Supprime les balises HTML et nettoie les espaces
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_body(payload: dict) -> str:
    mime_type = payload.get("mimeType", "")
    parts = payload.get("parts", [])
    body_data = payload.get("body", {}).get("data", "")

    # Cas simple : message non multipart
    if not parts:
        if not body_data:
            return ""
        text = _decode_part(body_data)
        if mime_type == "text/html":
            text = _strip_html(text)
        return text.strip()

    # Cas multipart : on cherche text/plain en priorité
    plain_text = ""
    html_text = ""

    for part in parts:
        part_mime = part.get("mimeType", "")
        part_data = part.get("body", {}).get("data", "")

        if part_mime == "text/plain" and part_data:
            plain_text = _decode_part(part_data).strip()
        elif part_mime == "text/html" and part_data:
            html_text = _strip_html(_decode_part(part_data)).strip()
        elif part_mime.startswith("multipart/"):
            # Récursion pour les parties imbriquées
            nested = extract_body(part)
            if nested:
                plain_text = plain_text or nested

    return plain_text or html_text or ""


def fetch_unread_emails(
    service,
    max_results: int = 500,
    mark_as_read: bool = False,
) -> list[dict]:
    tickets = []
    page_token = None
    fetched = 0

    print(f"Récupération des emails non lus (max {max_results})")

    try:
        while fetched < max_results:
            # Récupération des IDs par page (max 100 par appel)
            batch_size = min(100, max_results - fetched)

            params = {
                "userId": "me",
                "q": "is:unread",
                "maxResults": batch_size,
                "labelIds": ["INBOX"],
            }
            if page_token:
                params["pageToken"] = page_token

            response = service.users().messages().list(**params).execute()
            messages = response.get("messages", [])

            if not messages:
                break

            # Récupération du contenu de chaque mail
            for msg_ref in messages:
                msg_id = msg_ref["id"]
                try:
                    msg = (
                        service.users()
                        .messages()
                        .get(
                            userId="me",
                            id=msg_id,
                            format="full",
                        )
                        .execute()
                    )

                    # Extraction du sujet depuis les headers
                    headers = msg.get("payload", {}).get("headers", [])
                    sujet = next(
                        (h["value"] for h in headers if h["name"].lower() == "subject"),
                        "(Sans sujet)",
                    )

                    # Extraction du corps
                    corps = extract_body(msg.get("payload", {}))

                    tickets.append(
                        {
                            "id": msg_id,
                            "sujet": sujet,
                            "corps": corps,
                        }
                    )

                    # Marquer comme lu si demandé
                    if mark_as_read:
                        service.users().messages().modify(
                            userId="me",
                            id=msg_id,
                            body={"removeLabelIds": ["UNREAD"]},
                        ).execute()

                    fetched += 1
                    print(f"[{fetched}] {sujet[:70]}")

                except HttpError as error:
                    print(f"Erreur sur le mail {msg_id} : {error}")
                    continue

            # Pagination
            page_token = response.get("nextPageToken")
            if not page_token:
                break

    except HttpError as error:
        print(f" Erreur API Gmail : {error}")
        raise

    print(f"\n{len(tickets)} emails récupérés.")
    return tickets


# Point d'entrée de test
if __name__ == "__main__":
    service = get_gmail_service()
    tickets = fetch_unread_emails(service, max_results=10)

    print("\nAperçu des tickets")
    for t in tickets:
        print(f"\n Sujet  : {t['sujet']}")
        print(f"   Corps  : {t['corps'][:200]}")
        print(f"   ID     : {t['id']}")
