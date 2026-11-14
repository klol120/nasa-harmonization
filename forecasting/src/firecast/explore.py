"""Discovery of existing monthly exports and subregion similarity diagnostics."""
from pathlib import Path
import json
import numpy as np
import pandas as pd

PROFILE=['annual_rain_mm','summer_temperature_c','seasonality_index','vegetation_fraction','elevation_m','fire_peak_month_sin','fire_peak_month_cos','fire_rate_observable_day']

def compare_profiles(profiles):
    """Distances for climate/vegetation/terrain/fire strata, not entire countries.

    Fit scaling on Lebanese reference strata only. Distances are diagnostics, not
    an automatic assertion of ecological or sensor/coverage equivalence.
    """
    if not set(['area','region',*PROFILE])<=set(profiles): raise ValueError('Missing similarity profile columns')
    reference=profiles[profiles.region.eq('lebanon')]
    if len(reference)<2: raise ValueError('Need at least two Lebanese reference strata')
    scale=reference[PROFILE].std().replace(0,1)
    results=[]
    for _,r in profiles.iterrows():
        dist=np.sqrt((((reference[PROFILE]-r[PROFILE])/scale)**2).astype(float).mean(axis=1))
        results.append({'area':r.area,'nearest_lebanese_stratum':reference.loc[dist.idxmin(),'area'],'distance':float(dist.min()),'approved_for_training':False})
    return pd.DataFrame(results)

def inspect_monthly(root):
    records=[]
    for p in sorted(Path(root).glob('*/meta.json')):
        meta=json.loads(p.read_text());frame=pd.read_csv(p.parent/'region_monthly.csv')
        records.append({'region':meta['region'],'cells':meta['n_cells'],'persistent_cells':meta['n_persistent_cells'],
          'units':meta['units'],'time':meta['time'],'monthly_rows':len(frame),'columns':list(frame),
          'eligible_for_daily_labels':False,'reason':'No detection acquisition times or daily observation coverage'})
    return records
