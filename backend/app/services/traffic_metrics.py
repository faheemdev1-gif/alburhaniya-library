"""All-tool attempts, separate from scheduled probes; configurable persistence.

Every request ID is recorded once. No queries, quotes or credentials are logged.
A /tmp database is explicitly ephemeral; operators must mount persistent storage
or collect the JSON log for production continuity.
"""
import sqlite3,time,logging,json,math
from app.core.config import get_settings
log=logging.getLogger(__name__)
def record_attempt(request_id,tool,payload,ms):
    from app.mcp_contract import SERVER_VERSION
    outcome=(payload.get('status') or {}).get('execution') if isinstance(payload.get('status'),dict) else 'failed' if payload.get('error') else 'full'
    event={'request_id':request_id,'tool':tool,'build':SERVER_VERSION,'execution':outcome,'ms':round(ms,3),'timestamp':time.time()}
    try:
        with sqlite3.connect(get_settings().traffic_metrics_path,timeout=.05) as c:
            c.execute('CREATE TABLE IF NOT EXISTS attempts(request_id TEXT PRIMARY KEY,tool TEXT,build TEXT,execution TEXT,ms REAL,timestamp REAL)')
            c.execute('INSERT OR IGNORE INTO attempts VALUES(?,?,?,?,?,?)',tuple(event[k] for k in ('request_id','tool','build','execution','ms','timestamp')))
            c.execute('DELETE FROM attempts WHERE timestamp<?',(time.time()-30*86400,))
    except (OSError,sqlite3.Error):log.warning('Traffic metrics write failed')
    log.info('tool_attempt %s',json.dumps(event,separators=(',',':')))

def traffic_summary():
    from app.mcp_contract import SERVER_VERSION
    path=get_settings().traffic_metrics_path
    persistence='ephemeral_container_path' if path.startswith('/tmp/') else 'configured_path_verify_mounted_storage'
    try:
        with sqlite3.connect('file:'+path+'?mode=ro',uri=True,timeout=.05) as c:
            rows=c.execute('SELECT execution,ms,timestamp FROM attempts WHERE timestamp>=? AND build=?',(time.time()-7*86400,SERVER_VERSION)).fetchall()
        times=sorted(x[1] for x in rows);n=len(rows)
        return {'scope':'all_tool_attempts_for_current_build','build':SERVER_VERSION,'persistence_scope':persistence,'attempts_7d':n,
                'failed':sum(x[0]=='failed' for x in rows),'partial':sum(x[0]=='partial' for x in rows),
                'p95_ms':times[math.ceil(.95*n)-1] if n else None,
                'observed_days':round((max(x[2] for x in rows)-min(x[2] for x in rows))/86400,3) if n else 0,
                'production_acceptance':'pending_independent_deployed_observation'}
    except sqlite3.Error:return {'scope':'all_tool_attempts_for_current_build','build':SERVER_VERSION,'status':'awaiting_attempts','persistence_scope':persistence}
