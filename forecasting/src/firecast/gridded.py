"""NASA product-specific daily labels and retrospective research feature construction.

VNP14A1 labels are not FIRMS 375m labels. Observed POWER weather is not a forecast.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import zipfile
import h5py
import numpy as np
import pandas as pd
from pyhdf.SD import SD,SDC
from shapely.geometry import shape
from shapely import contains_xy
from .data import km_distance
from .real import candidate_grid,audit_detections

RADIUS=6371007.181
TILE_WIDTH=np.pi*RADIUS/18


def inverse_sinusoidal(x,y):
    lat=y/RADIUS
    return np.degrees(x/(RADIUS*np.cos(lat))),np.degrees(lat)


def grid_coordinates(tile,size):
    match=re.fullmatch(r'h(\d{2})v(\d{2})',tile)
    if not match:raise ValueError('Invalid sinusoidal tile')
    h,v=map(int,match.groups());step=TILE_WIDTH/size
    x=-np.pi*RADIUS+h*TILE_WIDTH+(np.arange(size)+.5)*step
    y=np.pi*RADIUS/2-v*TILE_WIDTH-(np.arange(size)+.5)*step
    return inverse_sinusoidal(x[None,:],y[:,None])


def landcover_quality(land,qc):
    """Collection 6.1 QC is categorical, NOT the old collection-5 bit field."""
    land=np.asarray(land);qc=np.asarray(qc)
    if land.shape!=qc.shape:raise ValueError('Land-cover and categorical QC shapes differ')
    valid=np.isin(qc,[0,2])&np.isin(land,np.arange(1,18))
    vegetation=valid&np.isin(land,list(range(1,13))+[14])
    return vegetation,valid

def read_landcover(path):
    f=SD(str(path),SDC.READ)
    try:land=f.select('LC_Type1')[:];qc=f.select('QC')[:]
    finally:f.end()
    if land.shape!=(2400,2400) or qc.shape!=land.shape:raise ValueError('Expected MCD12Q1 500m tile')
    # NASA collection-6 guide: 0 classified land, 2 classified water; other categories are not this strict quality tier.
    vegetation,valid=landcover_quality(land,qc)
    down=lambda a:a.reshape(1200,2,1200,2).mean(axis=(1,3))
    return down(vegetation),down(valid)


class SRTM:
    def __init__(self,paths):
        self.tiles={}
        for p in paths:
            m=re.search(r'N(\d{2})E(\d{3})',p.name)
            if not m:continue
            with zipfile.ZipFile(p) as z:
                files=[n for n in z.namelist() if n.lower().endswith('.hgt')]
                if len(files)!=1:raise ValueError('Expected one elevation HGT in archive')
                array=np.frombuffer(z.read(files[0]),dtype='>i2')
            size=int(np.sqrt(array.size))
            if size!=3601:raise ValueError('Expected one-arcsecond SRTM')
            self.tiles[tuple(map(int,m.groups()))]=array.reshape(size,size)

    def sample(self,lat,lon):
        lat=np.asarray(lat);lon=np.asarray(lon);n=lat.size
        elevation=np.full(n,np.nan);slope=np.full(n,np.nan);sin_aspect=np.full(n,np.nan);cos_aspect=np.full(n,np.nan)
        for (south,west),dem in self.tiles.items():
            use=(lat>=south)&(lat<south+1)&(lon>=west)&(lon<west+1)
            if not use.any():continue
            rr=np.rint((south+1-lat[use])*3600).astype(int).clip(0,3600);cc=np.rint((lon[use]-west)*3600).astype(int).clip(0,3600)
            r0=(rr-1).clip(0,3600);r1=(rr+1).clip(0,3600);c0=(cc-1).clip(0,3600);c1=(cc+1).clip(0,3600)
            centre=dem[rr,cc].astype(float);north=dem[r0,cc].astype(float);south_z=dem[r1,cc].astype(float);east=dem[rr,c1].astype(float);west_z=dem[rr,c0].astype(float)
            good=np.all(np.column_stack([centre,north,south_z,east,west_z])!=-32768,axis=1)
            dy=RADIUS*np.pi/180/3600;dx=dy*np.cos(np.radians(lat[use]))
            dz_south=(south_z-north)/((r1-r0)*dy);dz_east=(east-west_z)/((c1-c0)*dx)
            magnitude=np.hypot(dz_south,dz_east);angle=np.arctan2(-dz_east,dz_south)
            indices=np.flatnonzero(use)[good]
            elevation[indices]=centre[good];slope[indices]=np.degrees(np.arctan(magnitude[good]))
            sin_aspect[indices]=np.where(magnitude[good]<1e-12,0,np.sin(angle[good]));cos_aspect[indices]=np.where(magnitude[good]<1e-12,0,np.cos(angle[good]))
        return elevation,slope,sin_aspect,cos_aspect


def prepare_static(environment,config,out):
    environment=Path(environment);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    boundary=json.loads((environment/'lebanon.geojson').read_text());polygon=shape(boundary['geometry'])
    terrain=SRTM(list((environment/'raw').glob('*.hgt.zip')))
    all_points=[];country_samples=[];maps={}
    grid=candidate_grid(dict(config,scope='NASA_FIRMS_country_geometry_and_MCD12Q1_vegetation'))
    lookup={cid:i for i,cid in enumerate(grid.cell_id)}
    for tile in config['tiles']:
        landfiles=list((environment/'raw').glob(f'MCD12Q1.A2010001.{tile}.*.hdf'))
        if len(landfiles)!=1:raise ValueError('Need one 2010 land-cover file per analysis tile')
        veg,valid=read_landcover(landfiles[0]);lon,lat=grid_coordinates(tile,1200)
        # Broadcast latitude to full tile before selection.
        lat=np.broadcast_to(lat,lon.shape)
        inside=contains_xy(polygon,lon,lat)
        known=inside&(valid>=.75)
        selected=known&(veg>=config['min_vegetation_fraction_per_pixel'])
        cr,cc=np.where(inside)
        country_ids=np.array([f'{int(np.floor((a+90)/config["grid_deg"]+1e-8))}_{int(np.floor((b+180)/config["grid_deg"]+1e-8))}' for a,b in zip(lat[inside],lon[inside])])
        country_keep=np.array([x in lookup for x in country_ids])
        cr,cc,country_ids=cr[country_keep],cc[country_keep],country_ids[country_keep]
        country_samples.append(pd.DataFrame({'cell_id':country_ids,'vegetation_fraction':np.where(valid[cr,cc]>=.75,veg[cr,cc],np.nan)}))
        rows,cols=np.where(selected);lats=lat[selected];lons=lon[selected]
        ids=[f'{int(np.floor((a+90)/config["grid_deg"]+1e-8))}_{int(np.floor((b+180)/config["grid_deg"]+1e-8))}' for a,b in zip(lats,lons)]
        keep=np.array([x in lookup for x in ids])
        rows,cols,lats,lons=rows[keep],cols[keep],lats[keep],lons[keep];ids=np.array(ids)[keep]
        # Nine native-DEM samples per selected kilometre pixel, then aggregate.
        samples=[]
        for dy in [-.0025,0,.0025]:
            for dx in [-.0025,0,.0025]:samples.append(terrain.sample(lats+dy,lons+dx))
        features=np.nanmean(np.stack(samples),axis=0)
        points=pd.DataFrame({'cell_id':ids,'lat':lats,'lon':lons,'vegetation_fraction':veg[rows,cols],
          'elevation_m':features[0],'slope_deg':features[1],'aspect_sin':features[2],'aspect_cos':features[3]})
        if not np.isfinite(points[['elevation_m','slope_deg','aspect_sin','aspect_cos']]).all().all():raise ValueError('Missing terrain samples')
        all_points.append(points)
        maps[tile]={'rows':cr,'cols':cc,'cell_ids':country_ids,'eligible':selected[cr,cc]}
        np.savez_compressed(out/f'pixel-map-{tile}.npz',**maps[tile])
    pixels=pd.concat(all_points,ignore_index=True)
    counts=pixels.groupby('cell_id').size();eligible=counts[counts>=config['min_eligible_pixels_per_cell']].index
    cells=pixels[pixels.cell_id.isin(eligible)].groupby('cell_id').agg(eligible_pixels=('cell_id','size'),
      vegetation_fraction=('vegetation_fraction','mean'),elevation_m=('elevation_m','mean'),slope_deg=('slope_deg','mean'),aspect_sin=('aspect_sin','mean'),aspect_cos=('aspect_cos','mean')).reset_index()
    fraction=pd.concat(country_samples).groupby('cell_id').vegetation_fraction.mean()
    cells['vegetation_fraction']=cells.cell_id.map(fraction)
    representative=[]
    for cid,g in pixels[pixels.cell_id.isin(eligible)].groupby('cell_id'):
        distance=km_distance(g.lat,g.lon,g.lat.mean(),g.lon.mean());point=g.loc[distance.idxmin()]
        representative.append({'cell_id':cid,'lat':point.lat,'lon':point.lon})
    centres=grid[['cell_id','lat','lon']].rename(columns={'lat':'cell_center_lat','lon':'cell_center_lon'})
    cells=cells.merge(pd.DataFrame(representative),on='cell_id',validate='one_to_one').merge(centres,on='cell_id',validate='one_to_one');cells['region']='lebanon'
    cells.to_csv(out/'cells.csv',index=False)
    meta={'country_geometry_source':'https://firms.modaps.eosdis.nasa.gov/content/geodata/world_countries.geojson',
      'country_geometry_role':'NASA map analysis geometry, not an official legal border assertion',
      'landcover_observation_year':2010,'landcover_processing_mode':'retrospective reprocessed collection 6.1',
      'terrain':'NASA SRTM 1 arcsecond; nine native-point samples per selected 1km pixel; latitude-aware finite differences',
      'cell_location':'Representative eligible in-country kilometre pixel nearest the cell vegetation centroid; original grid centre retained separately',
      'cells':len(cells),'eligible_km_grid_pixels':int(cells.eligible_pixels.sum()),'config':config}
    meta['raw_input_hashes']={m.name:json.loads(m.read_text())['sha256'] for m in (environment/'raw').glob('*.manifest.json')}
    (out/'static-report.json').write_text(json.dumps(meta,indent=2))
    return cells,maps


def summarize_day(path,mapping,cells,expected_product="VNP14A1"):
    with h5py.File(path) as f:
        if f.attrs.get('ShortName',b'').decode()!=expected_product:raise ValueError('Unexpected fire-mask product')
        base=f['HDFEOS/GRIDS/VIIRS_Grid_Daily_Fire/Data Fields']
        mask=base['FireMask'][:][mapping['rows'],mapping['cols']];qa=base['QA'][:][mapping['rows'],mapping['cols']]
        if not np.isin(mask,np.arange(10)).all():raise ValueError('Unknown daily fire class')
        day=pd.Timestamp(f.attrs['RangeBeginningDate'].decode(),tz='UTC')
    land=np.isin(qa&3,[1,2]);eligible=mapping['eligible']
    points=pd.DataFrame({'cell_id':mapping['cell_ids'],'processed':eligible&land&np.isin(mask,[5,7,8,9]),
      'fire':eligible&land&np.isin(mask,[7,8,9]),'nominal_fire':eligible&land&np.isin(mask,[8,9]),'low_fire':eligible&land&(mask==7),
      'noneligible_fire':(~eligible)&np.isin(mask,[7,8,9]),
      'unknown_fire':eligible&(mask==6),'cloud':eligible&(mask==4),'missing':eligible&np.isin(mask,[0,1,2])})
    points=points[points.cell_id.isin(cells.cell_id)]
    result=points.groupby('cell_id').sum().reset_index();result['prediction_time']=day
    return result


def label_counts(frame,external_excluded,policy,min_fraction):
    if policy not in {'conservative','strict'}:raise ValueError('Unknown policy')
    positive=frame.fire.gt(0).to_numpy()
    qualified=(frame.processed_fraction.ge(min_fraction)&frame.unknown_fire.eq(0)).to_numpy()
    low=frame.low_fire.gt(0).to_numpy() if policy=='strict' else np.zeros(len(frame),dtype=bool)
    blocked=np.asarray(external_excluded,dtype=bool)|low|frame.noneligible_fire.gt(0).to_numpy()
    status=np.select([blocked,positive&qualified,positive,qualified],['excluded','positive','positive_low_coverage','negative'],default='uncertain')
    y=np.select([status=='positive',status=='negative'],[1.0,0.0],default=np.nan)
    return status,y

def build_dataset(data,environment,fire_archive,config_path,out):
    data=Path(data);fire_archive=Path(fire_archive);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    config=json.loads(Path(config_path).read_text())
    if config.get('horizon_hours') != 24:
        raise ValueError('Daily NASA composite adapter requires a 24-hour horizon; reaggregate labels and weather before using another horizon')
    archive_report=json.loads((fire_archive/'archive-report.json').read_text())
    if archive_report.get('complete') is not True:raise ValueError('Historical NASA archive is incomplete; do not train on a partial download')
    cells,maps=prepare_static(environment,config,out)
    summaries=[];used=[]
    for i,path in enumerate(sorted((fire_archive/'raw').glob(config.get('label_product','VNP14A1')+'*.h5'))):
        tile=re.search(r'\.h\d{2}v\d{2}\.',path.name).group(0).strip('.')
        if tile not in maps:continue
        summaries.append(summarize_day(path,maps[tile],cells,config.get('label_product','VNP14A1')));used.append(path)
        if i%1000==0:print('Decoded',i+1,'daily files',flush=True)
    if not summaries:raise ValueError('No daily masks')
    daily=pd.concat(summaries).groupby(['cell_id','prediction_time']).sum().reset_index()
    dates=pd.date_range(config['start'],pd.Timestamp(config['end_exclusive'])-pd.Timedelta(days=1),freq='D')
    windows=pd.MultiIndex.from_product([cells.cell_id,dates],names=['cell_id','prediction_time']).to_frame(index=False)
    windows=windows.merge(daily,on=['cell_id','prediction_time'],how='left',validate='one_to_one').merge(cells,on='cell_id',validate='many_to_one')
    # No tile/pixel evidence remains missing, never implicitly zero.
    windows['processed_fraction']=windows.processed/windows.eligible_pixels
    weather=pd.read_csv(data/'weather_historical.csv');weather['prediction_time']=pd.to_datetime(weather.date,utc=True)
    points=weather[['weather_point_id','lat','lon']].drop_duplicates();links=[]
    for r in cells.itertuples():
        dist=km_distance(points.lat,points.lon,r.lat,r.lon);j=dist.idxmin()
        links.append({'cell_id':r.cell_id,'weather_point_id':points.loc[j,'weather_point_id'],'weather_distance_km':float(dist.loc[j])})
    windows=windows.merge(pd.DataFrame(links),on='cell_id',validate='many_to_one')
    weather=weather.rename(columns={'T2M':'temperature_c','RH2M':'humidity_pct','PRECTOTCORR':'precip_mm','rain_preceding_7days_mm':'rain7_mm'})
    weather=weather.sort_values(['weather_point_id','prediction_time'])
    weather['rain7_mm']=weather.groupby('weather_point_id').rain7_mm.shift(config.get('history_lag_days',3))
    weather_columns=['weather_point_id','prediction_time','temperature_c','humidity_pct','precip_mm','wind_u_ms','wind_v_ms','rain7_mm']
    windows=windows.merge(weather[weather_columns],on=['weather_point_id','prediction_time'],how='left',validate='many_to_one')
    raw=pd.read_csv(data/'detections.csv',keep_default_na=False,dtype={'confidence':str,'processing_version':str})
    audit,_=audit_detections(raw,config);audit.to_csv(out/'firms-review-audit.csv.gz',index=False)
    files=[];reports={}
    for policy in ['conservative','strict']:
        frame=windows.copy();quarantine=audit[audit[policy+'_action'].eq('quarantine_entire_cell_window')].groupby(['cell_id','window_start']).size()
        idx=pd.MultiIndex.from_frame(frame[['cell_id','prediction_time']]);blocked=quarantine.reindex(idx,fill_value=0).to_numpy()>0
        frame['label_status'],frame['y']=label_counts(frame,blocked,policy,config['min_processed_fraction'])
        frame['window_end']=frame.prediction_time+pd.Timedelta(days=1)
        frame['sensor']=config.get('label_product','VNP14A1')+'_750m_to_1km';frame['event_type']=np.where(blocked|frame.low_fire.gt(0).to_numpy(),'flagged','unflagged')
        frame['detection_count']=frame.fire.fillna(0);frame['feature_mode']='retrospective_observed_weather_not_forecast'
        frame['policy']=policy;frame['region']='lebanon'
        frame['history_end']=frame.prediction_time-pd.Timedelta(days=config.get('history_lag_days',3))
        path=out/f'dataset-{policy}.csv.gz';frame.to_csv(path,index=False,compression={'method':'gzip','mtime':0});files.append(path)
        reports[policy]={'windows':len(frame),'statuses':frame.label_status.value_counts().to_dict(),'qualified_rows_with_missing_features':int((frame.y.notna()&frame[config['weather_features']].isna().any(axis=1)).sum())}
    provenance={'fire_inventory':{'sha256':hashlib.sha256((fire_archive/'catalog/inventory.json').read_bytes()).hexdigest()},
      'weather':{'sha256':hashlib.sha256((data/'weather_historical.csv').read_bytes()).hexdigest()},
      'static':{'sha256':hashlib.sha256((out/'static-report.json').read_bytes()).hexdigest()},
      'raw_fire_manifests':{'sha256':hashlib.sha256(''.join(json.loads(p.with_suffix(p.suffix+'.manifest.json').read_text())['sha256'] for p in used).encode()).hexdigest()},
      'configuration':{'sha256':hashlib.sha256(Path(config_path).read_bytes()).hexdigest()}}
    report={'generated_at':datetime.now(timezone.utc).isoformat(),'mode':'retrospective','synthetic':False,'decoded_daily_files':len(used),'cells':len(cells),
      'policies':reports,'provenance':provenance,'label_product':config.get('label_product','VNP14A1')+'.002 daily 1km; not FIRMS 375m',
      'country_geometry':json.loads((Path(environment)/'lebanon.geojson').read_text())['geometry'],
      'limitations':['Both fitted classes require processed fraction threshold; probabilities are conditional on this observable population',
        'Positive detections below coverage threshold are retained as positive_low_coverage, never zero',
        'Processed clear-land fraction is daily-composite evidence, not continuous fire observability',
        'Labels describe satellite detections, not complete ground incidents','Observed target-window POWER weather is a retrospective stand-in, not issued forecast performance',
        'Static inputs are reprocessed pre-target observations, not verified historically available versions','No complete NDVI history was invented']}
    (out/'dataset-report.json').write_text(json.dumps(report,indent=2))
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data',required=True);p.add_argument('--environment',required=True);p.add_argument('--fire-archive',required=True);p.add_argument('--config',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    print(json.dumps(build_dataset(a.data,a.environment,a.fire_archive,a.config,a.out),indent=2))

if __name__=='__main__':main()
