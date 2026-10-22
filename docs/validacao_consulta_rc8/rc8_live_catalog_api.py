from pathlib import Path
from threading import Event, Timer
from datetime import datetime, timezone
from urllib.parse import urlsplit
from urllib.error import HTTPError
import urllib.request
import time, json, platform
from liarte_core.comex import ComexProvider
from liarte_core.domain import Period
from liarte_engine import comexstat_importacoes as engine

root=Path('/workspace/scratch/d4c2b58ee5ea/rc8_live_catalog_data')
root.mkdir(exist_ok=True)
output=Path('/workspace/scratch/d4c2b58ee5ea/rc8_live_catalog_api.json')
requests=[]
original=urllib.request.urlopen
started=time.monotonic()

def opener(request, **kwargs):
    if urlsplit(request.full_url).hostname!='api-comexstat.mdic.gov.br':
        raise AssertionError('Unexpected non-API host')
    event={'method':request.get_method(),'path':urlsplit(request.full_url).path,'started_after_seconds':round(time.monotonic()-started,3)}
    try:
        response=original(request, **kwargs)
        event['http_status']=response.status
        return response
    except HTTPError as exc:
        event.update(http_status=exc.code,retry_after=exc.headers.get('Retry-After'))
        raise
    except Exception as exc:
        event.update(error_type=type(exc).__name__,error=str(exc)[:300])
        raise
    finally:
        requests.append(event)
        print(json.dumps(event),flush=True)

urllib.request.urlopen=opener
cancel=Event()
watchdog=Timer(300,cancel.set);watchdog.daemon=True;watchdog.start()
provider=ComexProvider(root)
report={'version':'5.2.0-rc.8','started_at':datetime.now(timezone.utc).isoformat(),'python':platform.python_version(),'platform':platform.system(),'company_network':False,'synthetic':False,'period':{'from':'2026-01','to':'2026-09'},'catalog_scope':'complete embedded LIARTE catalog; associated municipal SH4 positions','policy':{'min_interval_seconds':0,'max_attempts':1,'deadline_seconds':300,'central':False,'csv':False,'persistent_query_cache':False}}
last_message=['']
def progress(value,message):
    # Avoid printing the coordinator's countdown every second.
    if 'Aguardando' not in message and message!=last_message[0]:
        print(str(value)+' '+message,flush=True);last_message[0]=message
try:
    snap=provider.load(Period('2026-01','2026-09'),cancel,progress)
    report.update(status='passed',general_rows=len(snap.general),municipal_rows=len(snap.municipal),totals_verified=snap.totals_verified,response_validated=snap.response_validated,source_channels=snap.source_channels,data_api_requests=snap.api_requests,ncm_count=len(provider.codes),sh4_count=len({n[:4] for n in provider.codes}),general_cif_cents=sum(r.cif_cents for r in snap.general_records),general_kg=sum(r.kg for r in snap.general_records),municipal_fob_cents=sum(r.fob_cents for r in snap.municipal_records),municipal_kg=sum(r.kg for r in snap.municipal_records),persistent_cache_hits=snap.cache_hits,shared_cache_hits=snap.shared_cache_hits)
except Exception as exc:
    causes=[];current=exc
    for _ in range(6):
        if current is None:break
        causes.append({'type':type(current).__name__,'message':str(current)[:600],'observed_http_status':getattr(current,'observed_http_status',None)})
        current=current.__cause__
    report.update(status='not_completed',causes=causes,complete_snapshot_published=provider.snapshot is not None)
finally:
    watchdog.cancel();provider.close()
    report.update(seconds=round(time.monotonic()-started,3),requests=requests)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
