import numpy as np
import pandas as pd
import pytest
from firecast.gridded import inverse_sinusoidal,grid_coordinates,label_counts


def test_sinusoidal_coordinates_and_pixel_centres():
    lon,lat=inverse_sinusoidal(np.array([0.]),np.array([0.]))
    assert lon[0]==lat[0]==0
    lon,lat=grid_coordinates('h21v05',1200)
    assert lon.shape==(1200,1200) and lat.shape==(1200,1)
    assert lat[0,0]<40 and lat[-1,0]>30
    with pytest.raises(ValueError):grid_coordinates('../bad',1200)


def test_coverage_conditions_apply_to_positive_and_negative():
    f=pd.DataFrame({'fire':[1,0,1,0,0],'processed_fraction':[1,1,.3,.3,1],'unknown_fire':[0,0,0,0,1],
        'low_fire':[0]*5,'noneligible_fire':[0]*5})
    status,y=label_counts(f,np.zeros(5,dtype=bool),'conservative',.8)
    assert status.tolist()==['positive','negative','positive_low_coverage','uncertain','uncertain']
    assert y[:2].tolist()==[1,0] and np.isnan(y[2:]).all()


def test_discarded_or_mixed_hotspot_never_manufactures_negative():
    f=pd.DataFrame({'fire':[1,0,1],'processed_fraction':[1,1,1],'unknown_fire':[0,0,0],
        'low_fire':[0,0,1],'noneligible_fire':[0,1,0]})
    status,y=label_counts(f,[True,False,False],'strict',.8)
    assert status.tolist()==['excluded','excluded','excluded'] and np.isnan(y).all()
    status,y=label_counts(f,[False,False,False],'conservative',.8)
    assert status.tolist()==['positive','excluded','positive']

def test_collection6_landcover_qc_is_categorical_not_bitwise():
    from firecast.gridded import landcover_quality
    veg,valid=landcover_quality([1,1,1,17,1],[0,8,4,2,10])
    assert veg.tolist()==[True,False,False,False,False]
    assert valid.tolist()==[True,False,False,True,False]
