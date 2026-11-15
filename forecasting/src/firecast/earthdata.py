"""NASA CMR discovery and authenticated sample acquisition, with explicit access status.

Catalog metadata are not rasters. Sample granules are not full historical coverage.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlencode,urlparse
import urllib.request
import urllib.error
from .sources import cached_download

PRODUCTS={
 'VNP03IMG':{'version':'2','provider':'LAADS','purpose':'Full 375m swath geolocation matching VNP14IMG acquisition time'},
 'VNP14IMG':{'version':'002','purpose':'375m primary-sensor fire mask and QA; requires swath geolocation and per-overpass treatment'},
 'VNP14A1':{'version':'002','purpose':'750m-band-derived daily 1km fire/coverage sensitivity proxy, NOT equivalent to 375m detection completeness'},
 'MCD12Q1':{'version':'061','purpose':'annual land cover and quality; use publication time, not just nominal year'},
 'MOD13Q1':{'version':'061','purpose':'NDVI/EVI plus QA; composite interval and production/publication times matter'},
 'SRTMGL1':{'version':'003','purpose':'elevation; projected slope/aspect derivation required'},
}

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        parsed=urlparse(newurl)
        if parsed.scheme!='https': raise ValueError('Refuse non-HTTPS data redirect')
        new=super().redirect_request(req,fp,code,msg,headers,newurl)
        if parsed.hostname!=urlparse(req.full_url).hostname and new:
            new.remove_header('Authorization')
        return new

def get_json(url,path):
    path=cached_download(url,path)
    return json.loads(path.read_text())

def data_link(granule):
    for link in granule.get('links',[]):
        url=link.get('href','');host=urlparse(url).hostname or ''
        if host.endswith('.nasa.gov') and link.get('rel','').endswith('/data#') and not link.get('inherited',False) and ('/lp-prod-protected/' in url or '/archive/allData/' in url or '/prod-lads/' in url):
            return url
    return None

def discover(out,bbox=(35,33,36.7,34.75),start='2019-08-01T00:00:00Z',end='2019-08-17T00:00:00Z'):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);entries=[]
    for name,spec in PRODUCTS.items():
        query=urlencode({'short_name':name,'version':spec['version'],'page_size':10})
        collections=get_json('https://cmr.earthdata.nasa.gov/search/collections.json?'+query,out/f'{name}-collections.json')['feed']['entry']
        collections=[x for x in collections if x.get('data_center')==spec.get('provider','LPCLOUD')]
        if len(collections)!=1: raise ValueError(f'{name}: expected unique NASA product/provider collection')
        collection=collections[0]
        params={'collection_concept_id':collection['id'],'bounding_box':','.join(map(str,bbox)),'page_size':8,'sort_key[]':'start_date'}
        if name!='SRTMGL1':params['temporal']=start+','+end
        url='https://cmr.earthdata.nasa.gov/search/granules.json?'+urlencode(params)
        granules=get_json(url,out/f'{name}-sample-granules.json')['feed']['entry']
        samples=[]
        for g in granules:
            samples.append({'concept_id':g['id'],'name':g.get('producer_granule_id',g.get('title')),
              'observation_start':g.get('time_start'),'observation_end':g.get('time_end'),
              'catalog_updated_at':g.get('updated'),'data_url':data_link(g),
              'publication_available_at':None,'availability_note':'Catalog update time is not proof of historical dissemination time'})
        entries.append({'product':name,'version':spec['version'],'collection_id':collection['id'],'purpose':spec['purpose'],
                        'query_url':url,'samples':samples,'status':'metadata discovered; raster download requires authenticated access'})
    report={'generated_at':datetime.now(timezone.utc).isoformat(),'bbox':list(bbox),'sample_temporal_window':[start,end],
      'sample_limit_per_product':8,'full_history_downloaded':False,'products':entries,
      'authentication':'Set EARTHDATA_TOKEN securely in environment; never put it in notebooks, configs or chat',
      'coverage_warning':'A daily composite or clear pixel is not continuous 24-hour fire observability; swath QA and incident detectability remain limitations'}
    (out/'download-plan.json').write_text(json.dumps(report,indent=2))
    return report

def download_sample(url,path,token):
    host=urlparse(url).hostname or ''
    if not host.endswith('.nasa.gov') or urlparse(url).scheme!='https':raise ValueError('NASA HTTPS data URLs only')
    if not token:raise ValueError('EARTHDATA_TOKEN is absent; no secret should be sent in chat')
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    manifest=path.with_suffix(path.suffix+'.manifest.json')
    if path.exists():
        if not manifest.exists():raise ValueError('Cached granule lacks provenance')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=json.loads(manifest.read_text())['sha256']:raise ValueError('Cached granule checksum mismatch')
        return path
    req=urllib.request.Request(url,headers={'Authorization':'Bearer '+token})
    temp=path.with_suffix(path.suffix+'.part')
    try:
        with urllib.request.build_opener(SafeRedirect()).open(req,timeout=45) as response:
            signature=response.read(8)
            if not any(signature.startswith(s) for s in [b'\x89HDF\r\n\x1a\n',b'\x0e\x03\x13\x01',b'CDF',b'PK\x03\x04',b'II*\x00',b'MM\x00*']):
                raise ValueError('Response is not a recognized science raster/container; possible login page')
            with temp.open('wb') as f:
                f.write(signature)
                while chunk:=response.read(1024*1024):f.write(chunk)
        temp.replace(path)
    except Exception:
        temp.unlink(missing_ok=True);raise
    manifest.write_text(json.dumps({'url':url,'downloaded_at':datetime.now(timezone.utc).isoformat(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size},indent=2))
    return path

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True);p.add_argument('--download-samples',action='store_true');a=p.parse_args()
    plan=discover(a.out)
    if a.download_samples:
        token=os.getenv('EARTHDATA_TOKEN','')
        if not token:p.error('EARTHDATA_TOKEN missing. Metadata plan saved; configure authentication securely, not through chat.')
        for product in plan['products']:
            sample=next((x for x in product['samples'] if x['data_url']),None)
            if sample: download_sample(sample['data_url'],Path(a.out)/'raw'/sample['data_url'].rsplit('/',1)[-1],token)
    print(json.dumps({'products':{x['product']:len(x['samples']) for x in plan['products']},'full_history_downloaded':False},indent=2))

if __name__=='__main__':main()


def download_sample_with_client(url,path,token,client):
    """Same file contract, with a caller-owned reusable HTTPS client for bulk transfers."""
    host=urlparse(url).hostname or ''
    if not host.endswith('.nasa.gov') or urlparse(url).scheme!='https':raise ValueError('NASA HTTPS data URLs only')
    if not token:raise ValueError('Earthdata credential is absent')
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if path.with_suffix(path.suffix+'.manifest.json').exists():return download_sample(url,path,token)
        path.replace(path.with_suffix(path.suffix+'.unverified'))
    temp=path.with_suffix(path.suffix+'.part')
    try:
        with client.stream('GET',url,headers={'Authorization':'Bearer '+token}) as response:
            if response.status_code!=200:
                raise urllib.error.HTTPError(url,response.status_code,'NASA science-file request failed',None,None)
            chunks=iter(response.iter_bytes(chunk_size=1024*1024));first=next(chunks,b'')
            if not any(first.startswith(s) for s in [b'\x89HDF\r\n\x1a\n',b'\x0e\x03\x13\x01',b'CDF',b'PK\x03\x04',b'II*\x00',b'MM\x00*']):
                raise ValueError('Response is not a recognized science container')
            with temp.open('wb') as handle:
                handle.write(first)
                for chunk in chunks:handle.write(chunk)
        temp.replace(path)
    except Exception:
        temp.unlink(missing_ok=True);raise
    path.with_suffix(path.suffix+'.manifest.json').write_text(json.dumps({'url':url,'downloaded_at':datetime.now(timezone.utc).isoformat(),
        'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size,'transport':'reused HTTPS connection'},indent=2))
    return path
