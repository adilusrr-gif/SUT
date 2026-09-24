import os
import secrets
from pathlib import Path
root=Path(__file__).resolve().parent.parent
body=(root/'.env.example').read_text().replace('CHANGE_THIS_STRONG_PASSWORD',secrets.token_hex(24)).replace('CHANGE_ACCESS_TOKEN',secrets.token_urlsafe(36))
try: fd=os.open(root/'.env',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
except FileExistsError: raise SystemExit('.env exists; unchanged. Add new settings manually; keep the existing database password.')
with os.fdopen(fd,'w') as f: f.write(body)
print('Created .env (600). Configure OpenAI locally; do not send keys in chat.')
