import html
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def _get_credentials() -> Credentials:
    creds_path = os.environ["GOOGLE_CREDENTIALS_PATH"]
    token_path = os.path.join(os.path.dirname(creds_path), "token.json")

    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as fh:
            fh.write(creds.to_json())

    return creds


def fetch_unread(max_results: int = 10) -> list[dict]:
    """Return up to max_results unread Gmail messages as metadata dicts.

    Each dict has keys: sender, subject, snippet, date.
    Email body content is never fetched or stored.
    """
    service = build("gmail", "v1", credentials=_get_credentials())

    result = service.users().messages().list(
        userId="me", q="is:unread", maxResults=max_results
    ).execute()

    emails = []
    for stub in result.get("messages", []):
        msg = service.users().messages().get(
            userId="me",
            id=stub["id"],
            format="metadata",
            metadataHeaders=["From", "Subject", "Date"],
        ).execute()

        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        emails.append({
            "sender": headers.get("From", ""),
            "subject": headers.get("Subject", "(no subject)"),
            "snippet": html.unescape(msg.get("snippet", "")),
            "date": headers.get("Date", ""),
        })

    return emails
