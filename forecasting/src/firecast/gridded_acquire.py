"""Acquire a bounded, audited NASA daily fire-mask archive with restartable cache."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import ssl
import threading
import httpx
import time
from urllib.parse import urlencode
import urllib.error
from .earthdata import get_json,data_link,download_sample_with_client


def discover_archive(config,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);items=[];page=1
    while True:
        params={'collection_concept_id':config['collection_id'],'bounding_box':','.join(map(str,config['bbox'])),
          'temporal':config['start']+','+config['end'],'page_size':config['page_size'],'page_num':page,'sort_key[]':'start_date'}
        url='https://cmr.earthdata.nasa.gov/search/granules.json?'+urlencode(params)
        raw=get_json(url,out/f'catalog-page-{page:03d}.json')['feed']['entry']
        for g in raw:
            name=g.get('producer_granule_id',g['title'])
            if not any('.'+tile+'.' in name for tile in config['tiles']):continue
            u=data_link(g)
            if not u:raise ValueError('No NASA data URL for '+name)
            items.append({'name':name,'url':u,'time_start':g.get('time_start'),'time_end':g.get('time_end'),'size_mb':float(g.get('granule_size',0))})
        print('Catalog page',page,'entries',len(raw),'selected cumulative',len(items),flush=True)
        if len(raw)<config['page_size']:break
        page+=1
    # Keep every version named in the inventory; conflicting same date/tile is rejected downstream.
    if len({x['name'] for x in items})!=len(items):raise ValueError('Catalog pagination duplicated granules')
    (out/'inventory.json').write_text(json.dumps({'config':config,'items':items,'estimated_raw_mb':sum(x['size_mb'] for x in items)},indent=2))
    return items


def acquire_archive(config_path,out,token_file,catalog_only=False):
    config=json.loads(Path(config_path).read_text());out=Path(out)
    items=discover_archive(config,out/'catalog')
    if catalog_only:return
    token=Path(token_file).read_text().strip()
    if not token:raise ValueError('Credential file is empty')
    raw=out/'raw';raw.mkdir(exist_ok=True)
    needed=sum(x['size_mb']*1024*1024 for x in items if not (raw/(x['url'].rsplit('/',1)[-1])).exists())
    free=shutil.disk_usage(out).free
    if needed+config['min_free_bytes']>free:raise ValueError(f'Insufficient disk budget: need approximately {needed:.0f} bytes plus reserve, have {free}')
    local=threading.local();clients=[];client_lock=threading.Lock()
    def get(item):
        if not hasattr(local,'client'):
            def enforce_https(request):
                if request.url.scheme!='https':raise ValueError('Refuse non-HTTPS redirect')
            local.client=httpx.Client(verify=ssl.create_default_context(),trust_env=True,follow_redirects=True,timeout=45,event_hooks={'request':[enforce_https]})
            with client_lock:clients.append(local.client)
        error=None
        for attempt in range(4):
            try:
                p=download_sample_with_client(item['url'],raw/item['url'].rsplit('/',1)[-1],token,local.client)
                return {'name':item['name'],'file':p.name,'bytes':p.stat().st_size},None
            except Exception as exc:
                error={'name':item['name'],'error':type(exc).__name__,'status':getattr(exc,'code',None)}
                if isinstance(exc,urllib.error.HTTPError) and exc.code in [401,403]:break
                if attempt<3:time.sleep(min(30,2**attempt))
        return None,error
    failures=[];count=0;total_bytes=0
    with ThreadPoolExecutor(max_workers=config['download_workers']) as pool:
        for result,error in pool.map(get,items):
            if error:failures.append(error)
            else:count+=1;total_bytes+=result['bytes']
            if (count+len(failures))%100==0:print('Progress',count,'downloaded/cached,',len(failures),'failed of',len(items),flush=True)
    for client in clients:client.close()
    report={'generated_at':datetime.now(timezone.utc).isoformat(),'config':config,'catalog_items':len(items),
      'downloaded_or_cached':count,'bytes':total_bytes,'failures':failures,'complete':count==len(items),
      'label_definition':config['label_definition'],'inventory_sha256':hashlib.sha256((out/'catalog/inventory.json').read_bytes()).hexdigest()}
    (out/'archive-report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({'complete':report['complete'],'files':count,'failures':len(failures)}),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',required=True);p.add_argument('--out',required=True);p.add_argument('--token-file');p.add_argument('--catalog-only',action='store_true');a=p.parse_args()
    if not a.catalog_only and not a.token_file:p.error('--token-file required for downloads; never pass credential values as arguments')
    acquire_archive(a.config,a.out,a.token_file,a.catalog_only)

if __name__=='__main__':main()
