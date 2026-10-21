#!/usr/bin/env python3
"""Persistent platform-PORT launcher; fail before starting worker respawn loops."""
from pathlib import Path
import os,sys,sqlite3

def main():
 try:
  port=int(os.environ.get('PORT','8000'))
  if not 1<=port<=65535:raise ValueError
 except ValueError:raise SystemExit('Invalid PORT: set an integer between 1 and 65535.')
 root=Path(__file__).resolve().parent.parent;os.chdir(root);sys.path.insert(0,str(root))
 from app.core.config import get_settings
 settings=get_settings()
 if not settings.enable_legacy_meilisearch:
  path=Path(settings.library_db_path)
  if not path.is_file():raise SystemExit('library.db not found; run python scripts/build_index.py before starting the service.')
  try:
   with sqlite3.connect(f'file:{path.resolve()}?mode=ro',uri=True) as conn:
    if conn.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise SystemExit('library.db failed integrity check; rebuild before deploying.')
    required={'discovery_passages','discovery_fts','discovery_meta','term_document_frequency','discovery_topics','evidence_units','evidence_concepts'};actual={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if required-actual:raise SystemExit('library.db is missing the 2.10.16 evidence-unit index; run python scripts/build_index.py.')
    from app.services.evidence_units import INDEX_VERSION
    row=conn.execute("SELECT value FROM discovery_meta WHERE key='index_version'").fetchone()
    if not row or row[0]!=INDEX_VERSION:raise SystemExit('library.db feature version differs from this build; run python scripts/build_index.py.')
  except sqlite3.Error as exc:raise SystemExit('library.db could not be read; rebuild before deploying.') from exc
 try:
  workers=int(os.environ.get('WEB_CONCURRENCY','2'))
  if not 1<=workers<=8:raise ValueError
 except ValueError:raise SystemExit('Invalid WEB_CONCURRENCY: use 1 to 8.')
 os.environ['PYTHONUNBUFFERED']='1';print(f'Starting library HTTP service on 0.0.0.0:{port}; health=/health; MCP=/mcp/',flush=True)
 if settings.monitor_enabled:
  import subprocess
  subprocess.Popen([sys.executable,str(root/'scripts/monitor_service.py')],stdin=subprocess.DEVNULL)
 os.execv(sys.executable,[sys.executable,'-m','uvicorn','app.main:app','--host','0.0.0.0','--port',str(port),'--workers',str(workers)])
if __name__=='__main__':main()
