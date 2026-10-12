"""Honest scheduled-sample summaries; never imply all-traffic monitoring."""
import json,time,math
from collections import Counter
from pathlib import Path
from app.core.config import get_settings

def monitoring_summary():
 path=get_settings().monitor_summary_path
 if not path:return {'status':'not_configured','success_rate_24h':None,'scope':'scheduled_samples_not_all_traffic'}
 try:
  values=json.loads(Path(path).read_text());values=values if isinstance(values,list) else [values]
  recent=[v for v in values if v.get('event')!='restart' and v.get('timestamp',0)>=time.time()-86400]
  count=sum(v.get('calls',0) for v in recent);passed=sum(v.get('successful',0) for v in recent)
  samples=[r for v in recent for r in v.get('results',[])];times=sorted(r['ms'] for r in samples)
  codes=Counter()
  for row in samples:
   if not row.get('ok'):
    err=row.get('error');codes[(err.get('error',{}).get('code','unknown') if isinstance(err,dict) else str(err))]+=1
  oldest=min((v['timestamp'] for v in values if v.get('event')!='restart'),default=time.time())
  restarts=[{'timestamp':v['timestamp'],'server_version':v.get('server_version')} for v in values if v.get('event')=='restart']
  return {'status':'ok' if recent and max(v['timestamp'] for v in recent)>time.time()-900 else 'stale',
   'samples_24h':count,'success_rate_24h':passed/count if count else None,
   'p50_ms':times[len(times)//2] if times else None,'p95_ms':times[min(len(times)-1,math.ceil(len(times)*.95)-1)] if times else None,
   'error_codes':dict(codes),'observed_days':round((time.time()-oldest)/86400,3),
   'restarts':restarts[-20:],
   'persistence_scope':'ephemeral_container_path' if str(path).startswith('/tmp/') else 'configured_path_verify_mounted_storage',
   'seven_day_acceptance':'pending_external_continuity_review','scope':'scheduled_samples_not_all_traffic'}
 except (OSError,ValueError,TypeError):return {'status':'awaiting_samples','success_rate_24h':None,'scope':'scheduled_samples_not_all_traffic'}
