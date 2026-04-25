# Bulk Unsubscribe

A mobile-first web tool that connects to your mail provider and helps you unsubscribe from newsletters in bulk.

## Features

- 📧 **IMAP support** – connect to any IMAP server (Gmail, Outlook, self-hosted, etc.)
- ⚡ **Fastmail JMAP API** – native Fastmail integration via API token
- 📱 **Mobile-first UI** – clean, responsive interface that works great on phones
- 🗄️ **SQLite database** – lightweight local storage, no external server needed
- 🔍 **Smart scanning** – detects newsletters via the `List-Unsubscribe` email header
- 🚫 **One-tap unsubscribe** – follow HTTP unsubscribe links automatically

## Quick Start

### Prerequisites

- Python 3.11+

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/schellevis/bulk-unsubscribe.git
cd bulk-unsubscribe

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start the server
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open your browser at [http://localhost:8000](http://localhost:8000).

## Usage

1. **Add an account** (⚙️ Accounts tab)
   - For IMAP: enter your server details and password / app-password
   - For Fastmail: generate an API token at *Settings → Security → API tokens*
2. **Scan your inbox** by clicking the 🔍 icon next to an account
3. **Review senders** in the 📋 Senders tab – newsletters are grouped by sender
4. **Unsubscribe** with one tap – the app follows the `List-Unsubscribe` link automatically

## Architecture

```
bulk-unsubscribe/
├── app/
│   ├── main.py                 # FastAPI application
│   ├── database.py             # SQLite / SQLAlchemy setup
│   ├── models.py               # ORM models (Account, Sender, UnsubscribeAttempt)
│   ├── crypto.py               # Credential encryption (Fernet)
│   ├── routers/
│   │   ├── accounts.py         # POST /api/accounts/imap|fastmail
│   │   ├── senders.py          # GET/POST /api/senders
│   │   └── scan.py             # POST /api/scan/{account_id}
│   └── services/
│       ├── imap_service.py     # imaplib-based IMAP scanner
│       └── fastmail_service.py # JMAP-based Fastmail scanner
├── static/
│   ├── index.html              # Single-page app shell
│   ├── css/style.css           # Mobile-first styles
│   └── js/app.js               # Vanilla JS frontend
└── requirements.txt
```

## Security Notes

- Credentials are encrypted at rest using **Fernet** (AES-128-CBC).
- Set the `CREDENTIAL_SECRET` environment variable (min. 32 characters) before deploying; the default value is for development only.
- The API has no authentication layer yet – run it on localhost or behind a reverse proxy with auth.

## API Reference

The interactive API docs are available at [http://localhost:8000/docs](http://localhost:8000/docs).

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/accounts` | List accounts |
| `POST` | `/api/accounts/imap` | Add IMAP account |
| `POST` | `/api/accounts/fastmail` | Add Fastmail account |
| `DELETE` | `/api/accounts/{id}` | Remove account |
| `GET` | `/api/senders` | List newsletter senders |
| `POST` | `/api/senders/{id}/unsubscribe` | Unsubscribe from a sender |
| `POST` | `/api/scan/{account_id}` | Scan inbox for newsletters |
