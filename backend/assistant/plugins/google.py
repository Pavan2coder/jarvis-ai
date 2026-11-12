"""Google command plugin.

Owns:
  Intents — email_updates (reads unread Gmail via IMAP), google_open (opens a
            Google web app, or searches Drive/Gmail for a named file/mail)

Email readout needs GMAIL_ADDRESS and GMAIL_APP_PASSWORD in .env
(app password: https://myaccount.google.com/apppasswords, needs 2-step verification).
"""

import os
import email
import imaplib
import webbrowser
from email.header import decode_header, make_header
from email.utils import parseaddr
from urllib.parse import quote

from backend.assistant.intent_classifier import GOOGLE_SERVICES
from backend.assistant.session_memory import session_memory
from backend.voice.audio_engine import speak
from backend.utils.logger import logger


def _decode(value):
    return str(make_header(decode_header(value or "")))


def fetch_unread(limit=5):
    """Return (unread_count, [(sender, subject), ...newest first]) or None if not configured."""
    user, pw = os.environ.get("GMAIL_ADDRESS"), os.environ.get("GMAIL_APP_PASSWORD")
    if not (user and pw):
        return None
    with imaplib.IMAP4_SSL("imap.gmail.com", timeout=15) as m:
        m.login(user, pw.replace(" ", ""))
        m.select("INBOX", readonly=True)
        ids = m.search(None, "UNSEEN")[1][0].split()
        mails = []
        for i in reversed(ids[-limit:]):
            raw = m.fetch(i, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])")[1][0][1]
            msg = email.message_from_bytes(raw)
            name, addr = parseaddr(_decode(msg["From"]))
            mails.append((name or addr, _decode(msg["Subject"]) or "no subject"))
        return len(ids), mails


def summarize(count, mails):
    if not count:
        return "No new emails. Inbox is clear."
    head = f"You have {count} unread email{'s' if count != 1 else ''}."
    return head + " " + " ".join(f"From {s}: {subj}." for s, subj in mails)


INTENTS = {
}

FALLBACKS = []
