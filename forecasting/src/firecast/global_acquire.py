"""Bounded global NASA scientific subsetting; exact raw selected pixels are retained.

No whole-Earth coverage is claimed. Original bytes are hashed; transient whole source
containers are discarded only after selected raw arrays and provenance are preserved.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import tempfile
import threading
import time
from urllib.parse import urlencode,urlparse
import zipfile
import h5py
import httpx
import numpy as np
import pandas as pd
from pyhdf.SD import SD,SDC
from .earthdata import data_link
from .gridded import RADIUS,TILE_WIDTH,grid_coordinates,landcover_quality,SRTM
from .data import grid_id,km_distance

CMR='https://cmr.earthdata.nasa.gov/search/granules.json?'
COLLECTIONS={'MCD12Q1':'C2484079608-LPCLOUD','SRTMGL1':'C2763266360-LPCLOUD'}
_local=threading.local()


def client():
    if not hasattr(_local,'client'):
        def https_only(request):
            if request.url.scheme!='https':raise ValueError('Non-HTTPS redirect refused')
        _local.client=httpx.Client(verify=ssl.create_default_context(),trust_env=True,follow_redirects=True,timeout=70,event_hooks={'request':[https_only]})
    return _local.client


def now():return datetime.now(timezone.utc).isoformat()


def fetch(url,token=None):
    host=urlparse(url).hostname or ''
    if urlparse(url).scheme!='https' or not host.endswith('.nasa.gov'):raise ValueError('Initial source must be NASA HTTPS')
    headers={'Authorization':'Bearer '+token} if token else {}
    for attempt in range(4):
        try:
            response=client().get(url,headers=headers)
            if response.status_code!=200:raise RuntimeError('NASA request HTTP '+str(response.status_code))
            return response.content
        except Exception:
            if attempt==3:raise
            time.sleep(2**attempt)


def cached_json(url,path):
    path=Path(path);meta=path.with_suffix(path.suffix+'.manifest.json')
    if path.exists():
        raw=path.read_bytes()
        if not meta.exists():raise ValueError('Missing catalogue cache provenance')
        saved=json.loads(meta.read_text())
        if hashlib.sha256(raw).hexdigest()!=saved['sha256']:raise ValueError('Invalid catalogue cache')
        if saved['url']!=url:raise ValueError('Cache URL differs from requested source; use a versioned output directory')
        return json.loads(gzip.decompress(raw))
    raw=fetch(url);value=json.loads(raw);path.parent.mkdir(parents=True,exist_ok=True)
    compressed=gzip.compress(raw,mtime=0);path.write_bytes(compressed)
    meta.write_text(json.dumps({'url':url,'downloaded_at':now(),'sha256':hashlib.sha256(compressed).hexdigest(),'uncompressed_sha256':hashlib.sha256(raw).hexdigest(),'storage':'Lossless gzip of exact NASA JSON response'},indent=2))
    return value


def granules(params,path):return cached_json(CMR+urlencode(params),path)['feed']['entry']


def tile_at(lat,lon):
    x=RADIUS*np.radians(lon)*np.cos(np.radians(lat));y=RADIUS*np.radians(lat)
    h=int(np.floor((x+np.pi*RADIUS)/TILE_WIDTH));v=int(np.floor((np.pi*RADIUS/2-y)/TILE_WIDTH))
    return f'h{h:02d}v{v:02d}'


def site_tiles(site):
    return sorted({tile_at(a,b) for a in np.linspace(site['south']+.00001,site['north']-.00001,7) for b in [site['west']+.00001,site['east']-.00001]})


def sample_days(config):
    # Identical global dates permit fair cross-site comparisons. Outcomes never select dates.
    rng=np.random.default_rng(config['seed']);dates=[]
    for month in pd.date_range(config['start'],pd.Timestamp(config['end_exclusive'])-pd.Timedelta(days=1),freq='MS'):
        days=sorted(rng.choice(np.arange(1,month.days_in_month+1),size=config['days_per_month'],replace=False))
        dates.extend(month+pd.Timedelta(days=int(d)-1) for d in days)
    return pd.DatetimeIndex(dates)


def science_meta(url,raw):
    return {'url':url,'downloaded_at':now(),'original_bytes':len(raw),'original_sha256':hashlib.sha256(raw).hexdigest(),
      'source_container_retained':False,'retained_data':'Exact selected raw scientific pixels and QA; full source container was transient'}


def save_subset(path,arrays,provenance):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.part')
    with temp.open('wb') as f:np.savez_compressed(f,**arrays)
    temp.replace(path)
    provenance=dict(provenance,subset_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),subset_bytes=path.stat().st_size)
    path.with_suffix(path.suffix+'.manifest.json').write_text(json.dumps(provenance,indent=2))
    return path


def valid_subset(path):
    path=Path(path);meta=path.with_suffix(path.suffix+'.manifest.json')
    if not path.exists():return False
    if not meta.exists() or hashlib.sha256(path.read_bytes()).hexdigest()!=json.loads(meta.read_text())['subset_sha256']:raise ValueError('Scientific subset checksum mismatch')
    return True


def static_land(tile,site,out,token,existing):
    path=out/'static'/f'{site["id"]}-{tile}-land.npz'
    if valid_subset(path):return dict(np.load(path))
    matches=list((existing/'raw').glob(f'MCD12Q1.A2010001.{tile}.*.hdf'))
    if matches:
        source=matches[0];raw=source.read_bytes();url=json.loads(source.with_suffix('.hdf.manifest.json').read_text())['url']
    else:
        params={'collection_concept_id':COLLECTIONS['MCD12Q1'],'producer_granule_id':f'MCD12Q1.A2010001.{tile}.061.*','options[producer_granule_id][pattern]':'true','page_size':10}
        records=granules(params,out/'catalog'/f'land-{tile}.json.gz')
        if len(records)!=1:raise ValueError('Expected one exact MCD12Q1 2010 tile: '+tile)
        url=data_link(records[0]);raw=fetch(url,token)
    lon,lat=grid_coordinates(tile,1200);lat=np.broadcast_to(lat,lon.shape)
    use=(lat>=site['south'])&(lat<site['north'])&(lon>=site['west'])&(lon<site['east'])
    rows,cols=np.where(use)
    if not len(rows):raise ValueError('No native pixels for global site/tile')
    with tempfile.TemporaryDirectory(dir=out,prefix='transient-land-') as folder:
        temp=Path(folder)/'source.hdf';temp.write_bytes(raw);f=SD(str(temp),SDC.READ)
        try:land=f.select('LC_Type1')[:];qc=f.select('QC')[:]
        finally:f.end()
    offsets=np.array([[0,0],[0,1],[1,0],[1,1]])
    r=2*rows[:,None]+offsets[:,0];c=2*cols[:,None]+offsets[:,1]
    arrays={'rows':rows,'cols':cols,'lat':lat[rows,cols],'lon':lon[rows,cols],
      'LC_Type1':land[r,c],'QC':qc[r,c]}
    save_subset(path,arrays,dict(science_meta(url,raw),product='MCD12Q1.061',observation_year=2010,tile=tile))
    return arrays


def terrain_site(site,lat,lon,out,token):
    path=out/'static'/f'{site["id"]}-terrain.npz'
    if valid_subset(path):return dict(np.load(path))
    sources=[];files=[]
    with tempfile.TemporaryDirectory(dir=out,prefix='transient-dem-') as folder:
        for south in range(site['south'],site['north']):
            for west in range(site['west'],site['east']):
                name=f'{"N" if south>=0 else "S"}{abs(south):02d}{"E" if west>=0 else "W"}{abs(west):03d}'
                records=granules({'collection_concept_id':COLLECTIONS['SRTMGL1'],'point':f'{west+.5},{south+.5}','page_size':10},out/'catalog'/f'dem-{name}.json.gz')
                records=[g for g in records if g.get('producer_granule_id','').startswith(name+'.')]
                if len(records)!=1:raise ValueError('Expected exact SRTM tile '+name)
                url=data_link(records[0]);raw=fetch(url,token)
                p=Path(folder)/(name+'.hgt.zip');p.write_bytes(raw);files.append(p);sources.append(science_meta(url,raw))
        terrain=SRTM(files);samples=[];raw_samples=np.full((len(lat),9,5),-32768,dtype=np.int16)
        for k,(dy,dx) in enumerate((a,b) for a in [-.0025,0,.0025] for b in [-.0025,0,.0025]):
            latitude=lat+dy;longitude=lon+dx;samples.append(terrain.sample(latitude,longitude))
            for (south,west),dem in terrain.tiles.items():
                use=(latitude>=south)&(latitude<south+1)&(longitude>=west)&(longitude<west+1)
                rr=np.rint((south+1-latitude[use])*3600).astype(int).clip(0,3600);cc=np.rint((longitude[use]-west)*3600).astype(int).clip(0,3600)
                raw_samples[use,k,:]=np.column_stack([dem[rr,cc],dem[(rr-1).clip(0,3600),cc],dem[(rr+1).clip(0,3600),cc],dem[rr,(cc+1).clip(0,3600)],dem[rr,(cc-1).clip(0,3600)]])
        with np.errstate(invalid='ignore'):
            features=np.nanmean(np.stack(samples),axis=0)
    arrays={'lat':lat,'lon':lon,'raw_elevation_neighbours':raw_samples,'elevation_m':features[0],'slope_deg':features[1],'aspect_sin':features[2],'aspect_cos':features[3]}
    save_subset(path,arrays,{'product':'SRTMGL1.003','downloaded_at':now(),'sources':sources,'sampling':'Nine locations per nominal 1km pixel; original centre/north/south/east/west HGT values retained; outside-panel offsets remain missing'})
    return arrays


def prepare_site(site,config,out,token,existing):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);maps={};frames=[]
    for tile in site_tiles(site):
        a=static_land(tile,site,out,token,Path(existing));maps[tile]=a
        veg,valid=landcover_quality(a['LC_Type1'],a['QC'])
        f=pd.DataFrame({'tile':tile,'tile_index':np.arange(len(a['lat'])),'lat':a['lat'],'lon':a['lon'],
          'vegetation_fraction':veg.mean(axis=1),'known_cover_fraction':valid.mean(axis=1)})
        frames.append(f)
    pixels=pd.concat(frames,ignore_index=True)
    terrain=terrain_site(site,pixels.lat.to_numpy(),pixels.lon.to_numpy(),out,token)
    for key in ['elevation_m','slope_deg','aspect_sin','aspect_cos']:pixels[key]=terrain[key]
    pixels['cell_id']=[grid_id(a,b,config['grid_deg']) for a,b in zip(pixels.lat,pixels.lon)]
    pixels['eligible']=(pixels.known_cover_fraction>=.75)&(pixels.vegetation_fraction>=config['min_vegetation_fraction_per_pixel'])&np.isfinite(pixels[['elevation_m','slope_deg','aspect_sin','aspect_cos']]).all(axis=1)
    counts=pixels[pixels.eligible].groupby('cell_id').size();ids=counts[counts>=config['min_eligible_pixels_per_cell']].index
    selected=pixels[pixels.eligible&pixels.cell_id.isin(ids)]
    cells=selected.groupby('cell_id').agg(lat=('lat','mean'),lon=('lon','mean'),eligible_pixels=('cell_id','size'),elevation_m=('elevation_m','mean'),slope_deg=('slope_deg','mean'),aspect_sin=('aspect_sin','mean'),aspect_cos=('aspect_cos','mean')).reset_index()
    # Vegetation fraction covers all known pixels in the cell, not only its vegetated subset.
    fraction=pixels.assign(vegetation_fraction=pixels.vegetation_fraction.where(pixels.known_cover_fraction>=.75)).groupby('cell_id').vegetation_fraction.mean()
    cells['vegetation_fraction']=cells.cell_id.map(fraction);cells['region']=site['id'];cells['continent']=site['continent'];cells['geographic_holdout']=site['geographic_holdout']
    cells.to_csv(out/'static'/f'{site["id"]}-cells.csv',index=False)
    for tile,a in maps.items():
        part=pixels[pixels.tile.eq(tile)]
        arrays={'rows':a['rows'],'cols':a['cols'],'cell_ids':part.cell_id.to_numpy(dtype=str),'eligible':part.eligible.to_numpy(),'lat':a['lat'],'lon':a['lon']}
        save_subset(out/'maps'/f'{site["id"]}-{tile}.npz',arrays,{'site':site,'tile':tile,'static_source':'Exact raw land-cover and terrain subsets in static/','created_at':now()})
    return {'site':site['id'],'cells':len(cells),'tiles':list(maps)}


def select_daily_versions(items):
    """Keep all catalogue evidence, selecting the latest processing timestamp per day."""
    by_date={}
    for item in items:
        by_date.setdefault(item['date'],{})[item['name']]=item
    selected=[];reviews=[]
    for day,versions in sorted(by_date.items()):
        ordered=sorted(versions.values(),key=lambda x:x['name'].rsplit('.',1)[-1])
        chosen=ordered[-1];selected.append(chosen)
        if len(ordered)>1:reviews.append({'date':day,'selected':chosen,'other_catalogued_versions':ordered[:-1],
          'rule':'Latest NASA processing timestamp within the same collection/version; retrospective reconstruction only'})
    return selected,reviews


def discover_tile(tile,config,out):
    path=out/'catalog'/f'fire-{tile}-inventory.json'
    if path.exists():return json.loads(path.read_text())
    items=[];page=1
    while True:
        params={'collection_concept_id':config['collection_id'],'producer_granule_id':f'{config["product"]}.A*.{tile}.002.*','options[producer_granule_id][pattern]':'true',
          'temporal':config['start']+','+str(pd.Timestamp(config['end_exclusive'])-pd.Timedelta(seconds=1)).replace(' ','T'),'page_size':1000,'page_num':page,'sort_key[]':'start_date'}
        raw=granules(params,out/'catalog'/f'fire-{tile}-{page:02d}.json.gz')
        for g in raw:
            name=g.get('producer_granule_id',g['title'])
            if '.'+tile+'.' not in name:raise ValueError('CMR tile filter returned wrong tile')
            items.append({'name':name,'url':data_link(g),'date':g['time_start'][:10],'size_mb':g.get('granule_size')})
        if len(raw)<1000:break
        page+=1
    items,reviews=select_daily_versions(items)
    (out/'catalog'/f'fire-{tile}-version-choices.json').write_text(json.dumps(reviews,indent=2))
    path.write_text(json.dumps(items,indent=2));return items


def acquire_fire(tile,config,out,token,existing_archive):
    maps={p.stem.rsplit('-'+tile,1)[0]:dict(np.load(p)) for p in (out/'maps').glob('*-'+tile+'.npz')}
    row=np.concatenate([m['rows'] for m in maps.values()]);col=np.concatenate([m['cols'] for m in maps.values()])
    # Global subsets store ordered points for all sites sharing this source tile.
    sites=np.concatenate([np.repeat(name,len(m['rows'])) for name,m in maps.items()]);site_keys=list(maps)
    days={str(t.date()) for t in sample_days(config)};inventory=discover_tile(tile,config,out);tasks=[i for i in inventory if i['date'] in days]
    missing=sorted(days-{i['date'] for i in tasks})
    def one(item):
        path=out/'fire'/f'{item["name"]}.npz'
        if valid_subset(path):return True
        if shutil.disk_usage(out).free<config['min_free_bytes']:raise RuntimeError('Global acquisition disk reserve reached')
        cached=list((Path(existing_archive)/'raw').glob(item['name']+'.h5'))
        raw=cached[0].read_bytes() if cached else fetch(item['url'],token)
        with h5py.File(io.BytesIO(raw)) as f:
            if f.attrs.get('ShortName',b'').decode()!=config['product']:raise ValueError('Wrong fire product')
            base=f['HDFEOS/GRIDS/VIIRS_Grid_Daily_Fire/Data Fields'];mask=base['FireMask'][:][row,col];qa=base['QA'][:][row,col]
            if not np.isin(mask,np.arange(10)).all():raise ValueError('Invalid daily fire mask')
            date=f.attrs['RangeBeginningDate'].decode()
            if date!=item['date']:raise ValueError('Source date does not match catalogue')
        save_subset(path,{'FireMask':mask,'QA':qa,'site_id':sites},dict(science_meta(item['url'],raw),date=date,tile=tile,product='VJ114A1.002',site_order=site_keys,map_files={name:f'{name}-{tile}.npz' for name in site_keys}))
        return True
    successes=0;failures=[]
    def safe(item):
        try:one(item);return None
        except Exception as e:return {'name':item['name'],'type':type(e).__name__,'message':str(e) if str(e).startswith(('NASA request HTTP','Global acquisition disk')) else 'Source validation/download failed'}
    with ThreadPoolExecutor(max_workers=config['max_download_workers']) as pool:
        for n,error in enumerate(pool.map(safe,tasks),1):
            if error:failures.append(error)
            else:successes+=1
            if n%50==0:print(tile,'subsets',n,'of',len(tasks),'failed',len(failures),flush=True)
    report={'tile':tile,'expected_sampled_dates':len(days),'available_sampled_granules':len(tasks),'retained_subsets':successes,'missing_catalogue_dates':missing,'failures':failures,'complete':not failures}
    (out/'catalog'/f'fire-{tile}-report.json').write_text(json.dumps(report,indent=2));return report


def reuse_static(source,out):
    """Share immutable array bytes, copying mutable manifests and derived CSV metadata."""
    source=Path(source);out=Path(out)
    if source.resolve()==out.resolve():raise ValueError('Static source and target must differ')
    if not json.loads((source/'static-report.json').read_text()).get('complete'):raise ValueError('Static source incomplete')
    for folder in ['static','maps']:
        (out/folder).mkdir(parents=True,exist_ok=True)
        for p in (source/folder).iterdir():
            if not p.is_file():continue
            dest=out/folder/p.name
            if p.suffix=='.npz':
                if not valid_subset(p):raise ValueError('Unverified static source')
                if not dest.exists():os.link(p,dest)
            else:
                temp=dest.with_suffix(dest.suffix+'.copy');shutil.copy2(p,temp);temp.replace(dest)
    dest=out/'static-report.json';temp=dest.with_suffix('.copy');shutil.copy2(source/'static-report.json',temp);temp.replace(dest)


def acquire(config_path,out,token_file,environment,existing_archive,stage='all',reuse_from=None):
    config=json.loads(Path(config_path).read_text());out=Path(out);out.mkdir(parents=True,exist_ok=True);token=Path(token_file).read_text().strip()
    if reuse_from:reuse_static(reuse_from,out)
    if stage in {'static','all'}:
        summaries=[]
        for site in config['sites']:
            try:summaries.append(prepare_site(site,config,out,token,environment));print('Static',summaries[-1],flush=True)
            except Exception as e:
                (out/'static-failure.json').write_text(json.dumps({'site':site['id'],'error_type':type(e).__name__,'message':str(e) if isinstance(e,ValueError) else 'NASA/static processing failed'},indent=2));raise
        (out/'static-report.json').write_text(json.dumps({'sites':summaries,'complete':True,'config_sha256':hashlib.sha256(Path(config_path).read_bytes()).hexdigest(),'raw_subset_policy':'Unfiltered selected source arrays retained, transient complete containers discarded after hashing'},indent=2))
    if stage in {'fire','all'}:
        if not (out/'static-report.json').exists():raise ValueError('Complete static stage first')
        tiles=sorted({t for s in config['sites'] for t in site_tiles(s)})
        reports=[]
        for tile in tiles:
            report=acquire_fire(tile,config,out,token,existing_archive);reports.append(report);print('Fire tile complete',tile,report['retained_subsets'],'failed',len(report['failures']),flush=True)
        result={'complete':all(r['complete'] for r in reports),'tiles':reports,'sites':len(config['sites']),'sampled_dates':len(sample_days(config)),'generated_at':now(),'config_sha256':hashlib.sha256(Path(config_path).read_bytes()).hexdigest()}
        (out/'archive-report.json').write_text(json.dumps(result,indent=2));print(json.dumps({'complete':result['complete'],'sites':result['sites']}),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',required=True);p.add_argument('--out',required=True);p.add_argument('--token-file',required=True);p.add_argument('--environment',required=True);p.add_argument('--existing-archive',required=True);p.add_argument('--stage',choices=['static','fire','all'],default='all');p.add_argument('--reuse-static-from');a=p.parse_args();acquire(a.config,a.out,a.token_file,a.environment,a.existing_archive,a.stage,a.reuse_static_from)

if __name__=='__main__':main()
