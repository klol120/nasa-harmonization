"""Fit/evaluate real retrospective baselines only after complete NASA preparation."""
import argparse
import json
from pathlib import Path
import pandas as pd
import joblib
from .data import WEATHER
from .models import train_experiments,split


def train(data,out,seed=42,allow_tree=True):
    data=Path(data);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    report=json.loads((data/'dataset-report.json').read_text())
    source_config=json.loads((data/'static-report.json').read_text())['config']
    if report.get('synthetic') is not False or report.get('mode')!='retrospective':raise ValueError('Expected real retrospective dataset report')
    config={'synthetic':False,'mode':'retrospective','seed':seed,'grid_deg':source_config['grid_deg'],'horizon_hours':source_config['horizon_hours'],
      'train_end':source_config['train_end_exclusive'],'validation_end':source_config['validation_end_exclusive'],'embargo_days':7,
      'primary_policy':'strict','regional_cells':[],'heldout_cells':[],'allow_tree':allow_tree,
      'environment_features':['vegetation_fraction','elevation_m','slope_deg','aspect_sin','aspect_cos'],
      'prediction_scope':'Research probability conditional on daily processed eligible-area fraction >=0.8',
      'label_product':report['label_product'],'history_lag_days':source_config.get('history_lag_days',3),
      'real_data_readiness':{'training_allowed':True,'scope':'retrospective_research_only',
        'operational_release_allowed':False,'reason':'Real compatible product labels and pre-target static observations; observed target-day weather and reprocessing prevent an operational claim'}}
    datasets={};counts={}
    for policy in ['conservative','strict']:
        f=pd.read_csv(data/f'dataset-{policy}.csv.gz')
        for c in ['prediction_time','window_end']:f[c]=pd.to_datetime(f[c],utc=True,errors='raise')
        needed=WEATHER+config['environment_features']
        missing=f[needed].isna().any(axis=1)&f.y.notna()
        f.loc[missing,'label_status']='excluded_missing_feature';f.loc[missing,'y']=float('nan')
        tr,va,te,_=split(f,config)
        if any(x.y.nunique()!=2 for x in [tr,va,te]):raise ValueError('Both classes required in every split')
        datasets[policy]=f;counts[policy]={name:{'rows':len(x),'positive_windows':int(x.y.sum())} for name,x in [('train',tr),('validation',va),('test',te)]}
    (out/'preflight.json').write_text(json.dumps({'counts':counts,'configuration':config},indent=2))
    result=train_experiments(datasets,config,out,report['provenance'])
    artifact=joblib.load(out/'model.joblib')
    artifact['validated_cells']=pd.read_csv(data/'cells.csv').cell_id.tolist()
    artifact['analysis_geometry']=report['country_geometry']
    artifact['validated_products']=[report['label_product'].split()[0]]
    artifact['validated_weather_sources']=['NASA_POWER_HISTORICAL']
    artifact['research_limitations']=report['limitations']
    joblib.dump(artifact,out/'model.joblib')
    # All test calculations occur after the validation-based choice is frozen in train_experiments.
    (out/'RESEARCH_ONLY.txt').write_text('Real-data retrospective evaluation. Not a production-approved forecasting model. See dataset-report.json and decisions.md.\n')
    print(json.dumps({'selected':result['selected'],'synthetic':False,'mode':'retrospective','production_approved':False}))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data',required=True);p.add_argument('--out',required=True);p.add_argument('--no-tree',action='store_true');a=p.parse_args();train(a.data,a.out,allow_tree=not a.no_tree)

if __name__=='__main__':main()
