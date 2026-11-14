import json
import numpy as np
import pytest
from firecast.review import reliability
from firecast.inference import overlay
from firecast.gridded import build_dataset


def test_quantile_reliability_preserves_tied_scores():
    result=reliability([0,1,0,0],[.01,.01,.9,.9],bins=10)
    assert sum(b['n'] for b in result)==4
    assert len(result)==2
    assert result[0]['observed_fraction']==.5
    assert result[1]['observed_fraction']==0
    constant=reliability([0,1,0],[.01]*3)
    assert len(constant)==1 and constant[0]['n']==3
    with pytest.raises(ValueError):reliability([1],[np.nan])


def test_clipped_multipolygon_exposure_overlay(tmp_path):
    # Clipping a border cell may create disconnected pieces. Screening must handle both.
    polygon=lambda x:[[[x,33],[x+.1,33],[x+.1,33.1],[x,33.1],[x,33]]]
    risk={'type':'FeatureCollection','features':[{'type':'Feature','properties':{'cell_id':'test','above_validation_threshold':True},'geometry':{'type':'MultiPolygon','coordinates':[polygon(35),polygon(35.5)]}}]}
    assets={'type':'FeatureCollection','features':[{'type':'Feature','properties':{'id':'near'},'geometry':{'type':'Point','coordinates':[35.55,33.05]}},{'type':'Feature','properties':{'id':'far'},'geometry':{'type':'Point','coordinates':[37,34]}}]}
    for name,obj in [('risk',risk),('assets',assets)]: (tmp_path/f'{name}.json').write_text(json.dumps(obj))
    overlay(tmp_path/'risk.json',tmp_path/'assets.json',tmp_path/'out.json',buffer_km=0)
    result=json.loads((tmp_path/'out.json').read_text())
    assert [f['properties']['id'] for f in result['features']]==['near']


def test_daily_composite_adapter_refuses_unimplemented_horizon(tmp_path):
    cfg=tmp_path/'config.json';cfg.write_text(json.dumps({'horizon_hours':48}))
    with pytest.raises(ValueError,match='24-hour horizon'):
        build_dataset(tmp_path/'data',tmp_path/'environment',tmp_path/'archive',cfg,tmp_path/'out')
