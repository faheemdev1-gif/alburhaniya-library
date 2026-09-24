import json,time
from pathlib import Path
from app.core.config import get_settings
def monitoring_summary():
 path=get_settings().monitor_summary_path
 if not path:return {'status':'not_configured','success_rate_24h':None,'scope':'scheduled_samples_not_all_traffic'}
 try:
  values=json.loads(Path(path).read_text());values=values if isinstance(values,list) else [values];recent=[v for v in values if v.get('timestamp',0)>=time.time()-86400];count=sum(v.get('calls',0) for v in recent);passed=sum(v.get('successful',0) for v in recent)
  return {'status':'ok' if recent and max(v['timestamp'] for v in recent)>time.time()-1800 else 'stale','samples_24h':count,'success_rate_24h':passed/count if count else None,'scope':'scheduled_samples_not_all_traffic'}
 except (OSError,ValueError,TypeError):return {'status':'unavailable','success_rate_24h':None}
