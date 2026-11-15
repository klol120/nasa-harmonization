"""Small cached downloads and FIRMS normalization. Never log credential-bearing URLs."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib
import json
import os
import urllib.request
import pandas as pd
from .data import REQUIRED

SOURCES={
 'firms': 'https://firms.modaps.eosdis.nasa.gov/api/',
 'power': 'https://power.larc.nasa.gov/docs/services/api/',
 'geos': 'https://gmao.gsfc.nasa.gov/weather_prediction/',
 'landcover': 'https://www.earthdata.nasa.gov/data/catalog/lpcloud-mcd12q1-061',
 'firms_country': 'https://firms.modaps.eosdis.nasa.gov/country/',
}

def cached_download(url,path,public_url=None):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists():
        with urllib.request.urlopen(url,timeout=30) as response: content=response.read()
        temp=path.with_suffix(path.suffix+'.tmp');temp.write_bytes(content);temp.replace(path)
        manifest={'url':public_url or url,'downloaded_at':datetime.now(timezone.utc).isoformat(),
                  'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content)}
        path.with_suffix(path.suffix+'.manifest.json').write_text(json.dumps(manifest,indent=2))
    manifest_path=path.with_suffix(path.suffix+'.manifest.json')
    if not manifest_path.exists(): raise ValueError('Cache without provenance; re-ingest original file')
    if json.loads(manifest_path.read_text())['sha256']!=hashlib.sha256(path.read_bytes()).hexdigest(): raise ValueError('Cache checksum mismatch')
    return path

def normalize_firms(path,out,sensor,version):
    """Preserve original CSV; canonicalize a single declared sensor/product file."""
    if sensor not in {'MODIS','VIIRS'}: raise ValueError('Declare MODIS or VIIRS')
    f=pd.read_csv(path);rows=[]
    for _,r in f.iterrows():
        hhmm=str(int(r.acq_time)).zfill(4)
        t=pd.Timestamp(f'{r.acq_date}T{hhmm[:2]}:{hhmm[2:]}:00Z')
        identity=f'{r.latitude}|{r.longitude}|{t}|{sensor}|{version}'
        rows.append(dict(detection_id=hashlib.sha256(identity.encode()).hexdigest()[:24],lat=r.latitude,lon=r.longitude,
          detected_at=t,sensor=sensor,processing_version=version,confidence=r.confidence,type=r.get('type','unknown'),
          flag_level='unflagged',flag_reason='',flag_source=str(Path(path).name)))
    result=pd.DataFrame(rows,columns=REQUIRED['detections'])
    result=result.drop_duplicates(['detection_id']);result.to_csv(out,index=False)
    return result

def check_sources(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);checks=[]
    for name,url in SOURCES.items():
        try:
            with urllib.request.urlopen(url,timeout=20) as response:
                status=response.status; response.read(1024)
            checks.append({'source':name,'url':url,'status':status})
        except Exception as exc: checks.append({'source':name,'url':url,'status':getattr(exc,'code',type(exc).__name__)})
    # A small historical weather access check; never used as an operational forecast.
    url='https://power.larc.nasa.gov/api/temporal/daily/point?parameters=T2M,RH2M,PRECTOTCORR,WS10M&community=AG&longitude=35.5&latitude=33.9&start=20200801&end=20200807&format=JSON'
    try:
        p=cached_download(url,out/'power_beirut_20200801_07.json');checks.append({'source':'power_sample','status':'cached historical weather','path':str(p)})
    except Exception as exc: checks.append({'source':'power_sample','status':getattr(exc,'code',type(exc).__name__)})
    checks.append({'source':'FIRMS historical country files','status':'Public per-detection CSVs; use python -m firecast.acquire', 'url':'https://firms.modaps.eosdis.nasa.gov/country/'})
    checks.append({'source':'credentials','present':{k:bool(os.getenv(k)) for k in ['FIRMS_MAP_KEY','EARTHDATA_USERNAME','EARTHDATA_PASSWORD']}})
    (out/'access-checks.json').write_text(json.dumps({'checked_at':datetime.now(timezone.utc).isoformat(),'checks':checks},indent=2))
