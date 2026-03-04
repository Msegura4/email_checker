from __future__ import print_function
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow


SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def generate_token():
    creds = None
    if os.path.exists("token.json"):
        print("token.json existe déjà.")
        return

    flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)

    creds = flow.run_local_server(port=0)

    with open("token.json", "w") as token_file:
        token_file.write(creds.to_json())

    print("token.json généré avec succès !")


if __name__ == "__main__":
    generate_token()
