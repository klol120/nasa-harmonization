"""Extract geolocated NASA swath cloud/fire evidence without creating daily negatives."""
from pathlib import Path
import re
import h5py
import numpy as np
import pandas as pd

def find_dataset(file,names):
    found=[]
    def visit(name,obj):
        if isinstance(obj,h5py.Dataset) and name.rsplit('/',1)[-1] in names:found.append(name)
    file.visititems(visit)
    if len(found)!=1:raise ValueError(f'Expected one dataset matching {names}; found {len(found)}')
    return file[found[0]]

def swath_evidence(mask_path,geolocation_path,config):
    """Fixture-tested HDF5 adapter. Real-file validation remains pending authentication.

    Counts are fractions of sampled swath pixels, not continuous daily observation
    coverage or a verified vegetation-area denominator. Mask code 4 is cloud and
    5 is clear land; 7/8/9 are detected-fire classes in the VNP14IMG legend.
    """
    mask_path=Path(mask_path);geo_path=Path(geolocation_path)
    key=lambda p:re.search(r'\.A(\d{7})\.(\d{4})\.',p.name)
    a,b=key(mask_path),key(geo_path)
    if not a or not b or a.groups()!=b.groups():raise ValueError('Mask and full-swath geolocation acquisition times must match')
    if not mask_path.name.startswith('VNP14IMG.') or not geo_path.name.startswith('VNP03IMG.'):raise ValueError('Only matching S-NPP 375m mask/geolocation are supported')
    west,south,east,north=config['bbox'];step=config['grid_deg'];pieces=[]
    with h5py.File(mask_path) as mask_file,h5py.File(geo_path) as geo_file:
        mask=find_dataset(mask_file,{'fire mask','fire_mask','FireMask'})
        lat=find_dataset(geo_file,{'latitude','Latitude'});lon=find_dataset(geo_file,{'longitude','Longitude'})
        if mask.ndim!=2 or mask.shape!=lat.shape or mask.shape!=lon.shape:raise ValueError('Full-swath mask/geolocation shapes differ')
        for row in range(0,mask.shape[0],128):
            x=lon[row:row+128];y=lat[row:row+128];v=mask[row:row+128]
            inside=np.isfinite(x)&np.isfinite(y)&(x>=west)&(x<east)&(y>=south)&(y<north)
            if not inside.any():continue
            if not np.isin(v[inside],np.arange(10)).all():raise ValueError('Unknown VNP14IMG mask class')
            ids=(np.floor((y[inside]+90)/step+1e-8).astype(int).astype(str))
            cols=np.floor((x[inside]+180)/step+1e-8).astype(int).astype(str)
            pieces.append(pd.DataFrame({'cell_id':np.char.add(np.char.add(ids,'_'),cols),'mask_code':v[inside]}))
    if not pieces:raise ValueError('No geolocated mask pixels in configured bbox')
    pixels=pd.concat(pieces,ignore_index=True)
    counts=pixels.groupby(['cell_id','mask_code']).size().unstack(fill_value=0).reindex(columns=range(10),fill_value=0)
    output=pd.DataFrame({'cell_id':counts.index,'sampled_pixels':counts.sum(axis=1).to_numpy(),'cloud_pixels':counts[4].to_numpy(),
      'clear_land_pixels':counts[5].to_numpy(),'fire_pixels':counts[[7,8,9]].sum(axis=1).to_numpy()})
    output['cloud_fraction_of_sampled_pixels']=output.cloud_pixels/output.sampled_pixels
    output['clear_land_fraction_of_sampled_pixels']=output.clear_land_pixels/output.sampled_pixels
    output['coverage_evidence_qualified']=False
    output['qualification_reason']='Requires verified eligible-area denominator, QA, overpass completeness and daily assembly'
    output['acquisition_time']=pd.to_datetime(a[1]+a[2],format='%Y%j%H%M',utc=True)
    output['mask_source_file']=mask_path.name;output['geolocation_source_file']=geo_path.name
    return output
