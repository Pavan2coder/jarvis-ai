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


INTENTS = {
}

FALLBACKS = []
