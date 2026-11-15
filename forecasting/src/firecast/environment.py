"""Array-level NASA quality transformations, ready for authenticated raster adapters.

No geolocation, reprojection, publication date or swath coverage is fabricated here.
These functions have been checked on fixtures, not on acquired environmental rasters.
"""
import numpy as np
import pandas as pd

def ndvi_values(raw,reliability,composite_end,available_at):
    """MOD13Q1 raw NDVI scale 0.0001; retain only reliability 0 (good)."""
    if pd.Timestamp(available_at)<pd.Timestamp(composite_end):raise ValueError('Composite cannot be available before its interval ends')
    raw=np.asarray(raw,dtype=float);qa=np.asarray(reliability)
    if raw.shape!=qa.shape:raise ValueError('NDVI and QA shapes differ')
    good=(qa==0)&np.isfinite(raw)&(raw>=-2000)&(raw<=10000)
    return np.where(good,raw*.0001,np.nan),good

def vegetation_fraction(igbp,quality_good,include_agriculture=True):
    """NASA MCD12Q1 IGBP vegetation fraction over valid quality-qualified pixels.

    Class 11 wetlands retained as vegetation; 12/14 cropland/mosaic configurable.
    Invalid/fill pixels do not become barren land. Caller supplies decoded quality.
    """
    land=np.asarray(igbp);good=np.asarray(quality_good,dtype=bool)
    if land.shape!=good.shape:raise ValueError('Land-cover and quality shapes differ')
    valid=good&np.isin(land,np.arange(1,18))
    vegetation=list(range(1,12))+([12,14] if include_agriculture else [])
    return float(np.isin(land[valid],vegetation).mean()) if valid.any() else np.nan

def terrain(elevation_m,pixel_width_m,pixel_height_m):
    """Slope/aspect on a projected north-up DEM; never on mean cell elevation."""
    dem=np.asarray(elevation_m,dtype=float)
    if dem.ndim!=2 or min(dem.shape)<2 or pixel_width_m<=0 or pixel_height_m<=0:raise ValueError('Need 2D projected DEM and positive metre spacing')
    south,east=np.gradient(dem,pixel_height_m,pixel_width_m)
    slope=np.degrees(np.arctan(np.hypot(east,south)))
    aspect=np.degrees(np.arctan2(-east,south))%360
    flat=np.hypot(east,south)<1e-12
    aspect=np.where(flat,np.nan,aspect)
    return {'slope_deg':slope,'aspect_deg':aspect,'flat':flat}

def coverage_fraction(fire_mask,eligible_pixels,quality_good=None):
    """Instantaneous 375m mask evidence; NOT daily/continuous detection completeness.

    Caller must supply a full geolocated VNP14IMG mask in the eligible grid, a
    verified class convention, matching QA, and sensor/time metadata separately.
    Never call this with the sparse FIRMS point list or a rendered browse image.
    """
    mask=np.asarray(fire_mask);eligible=np.asarray(eligible_pixels,dtype=bool)
    if mask.shape!=eligible.shape:raise ValueError('Mask and eligible-pixel shapes differ')
    qa=np.ones(mask.shape,dtype=bool) if quality_good is None else np.asarray(quality_good,dtype=bool)
    if qa.shape!=mask.shape:raise ValueError('Mask and QA shapes differ')
    if not np.isin(mask,np.arange(10)).all():raise ValueError('Unrecognized fire-mask code')
    clear=eligible&qa&np.isin(mask,[5,7,8,9])
    return {'eligible_pixels':int(eligible.sum()),'observable_pixels':int(clear.sum()),
            'fraction':float(clear.sum()/eligible.sum()) if eligible.any() else None,
            'evidence_type':'instantaneous_swath_proxy_not_continuous_daily_coverage'}
