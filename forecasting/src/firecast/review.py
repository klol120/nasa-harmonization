"""Review a frozen real model without changing its fit, selection or threshold."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import precision_recall_curve
from .models import split
from .release import build_manifest


def reliability(y,p,bins=10):
    """Quantile score intervals; tied predictions always remain in the same bin."""
    y=np.asarray(y);p=np.asarray(p,dtype=float)
    if not len(p) or len(p)!=len(y) or not np.isfinite(p).all():raise ValueError('Nonempty finite aligned probabilities required')
    boundaries=np.unique(np.quantile(p,np.linspace(0,1,bins+1)))
    groups=np.searchsorted(boundaries[1:-1],p,side='right')
    return [{'n':int((groups==i).sum()),'positive_windows':int(y[groups==i].sum()),
      'min_probability':float(p[groups==i].min()),'max_probability':float(p[groups==i].max()),
      'mean_probability':float(p[groups==i].mean()),'observed_fraction':float(y[groups==i].mean())}
      for i in np.unique(groups)]


def review(data,models,out):
    data=Path(data);models=Path(models);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    metrics=json.loads((models/'metrics.json').read_text());dataset=json.loads((data/'dataset-report.json').read_text())
    artifact=joblib.load(models/'model.joblib') # trusted local producer only
    selected=next(e for e in metrics['experiments'] if e['id']==metrics['selected'])
    baseline=next(e for e in metrics['experiments'] if e['policy']==selected['policy'] and e['algorithm']=='seasonal')
    frame=pd.read_csv(data/f"dataset-{selected['policy']}.csv.gz")
    for key in ['prediction_time','window_end']:frame[key]=pd.to_datetime(frame[key],utc=True)
    train,validation,test,_=split(frame,artifact['config'])
    manifest=pd.concat([f[['cell_id','prediction_time','window_end','y']].assign(split=name) for name,f in [('train',train),('validation',validation),('test',test)]],ignore_index=True)
    if manifest.duplicated(['cell_id','prediction_time']).any():raise ValueError('Overlapping split identity')
    manifest.to_csv(out/'split-manifest.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    p=artifact['model'].predict_proba(test[artifact['features']])[:,1]
    calibration=reliability(test.y,p)
    evaluation={'synthetic':False,'mode':metrics['mode'],'test':dict(selected['test'],start=str(test.prediction_time.min()),end=str(test.window_end.max())),
      'baseline_test':baseline['test'],'validated_cells':artifact['validated_cells'],'validated_products':artifact['validated_products'],
      'validated_weather_sources':artifact['validated_weather_sources'],'evidence':{
        'compatible_observation_coverage':{'passed':True,'source':'dataset-report.json; same-product daily mask/QA; conditional 0.8 processed-area criterion only'},
        'national_vegetation_grid':{'passed':True,'source':'static-report.json; NASA FIRMS geometry, MCD12Q1.061 and SRTMGL1.003'},
        'historical_feature_availability':{'passed':False,'source':'Observed target-day POWER and later reprocessed land-cover version'},
        'issued_forecast_backtest':{'passed':False,'source':'Historical inputs are not forecasts; one current complete GEOS forecast window is not a backtest'},
        'independent_incident_split_review':{'passed':False,'source':'No independent incident catalogue; seven-day temporal gaps do not establish incident independence'},
        'calibration_review':{'passed':False,'source':'review.json quantile reliability; low precision and unvalidated GEOS transfer do not support release'},
        'current_sensor_transition_review':{'passed':True,'source':'Separate NOAA-20 VJ114A1.002 target rather than transferring the S-NPP benchmark'}}}
    (out/'evaluation.json').write_text(json.dumps(evaluation,indent=2))
    release=build_manifest(out/'evaluation.json',models/'model.joblib',out/'release.json')
    report={'reviewed_at':datetime.now(timezone.utc).isoformat(),'selected':selected['id'],'model_version':metrics['model_version'],
      'dataset':dataset,'split_counts':{name:{'observations':len(f),'positive_windows':int(f.y.sum()),'start':str(f.prediction_time.min()),'window_end':str(f.window_end.max())} for name,f in [('train',train),('validation',validation),('test',test)]},
      'test_prevalence':float(test.y.mean()),'test_mean_probability':float(p.mean()),'quantile_reliability':calibration,
      'selected_test':selected['test'],'baseline_test':baseline['test'],'release':release,
      'split_manifest_sha256':hashlib.sha256((out/'split-manifest.csv.gz').read_bytes()).hexdigest(),
      'note':'Post-fit review only. No fitting, threshold changes or model selection occurs in this command.'}
    (out/'review.json').write_text(json.dumps(report,indent=2))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(11,4))
    precision,recall,_=precision_recall_curve(test.y,p)
    axes[0].plot(recall,precision,label='Frozen environmental logistic model')
    axes[0].axhline(test.y.mean(),color='grey',linestyle='--',label='Test prevalence')
    axes[0].set(xlabel='Recall',ylabel='Precision',title='Reserved 2023–2025 Lebanese test');axes[0].legend(fontsize=8)
    x=[b['mean_probability'] for b in calibration];y=[b['observed_fraction'] for b in calibration]
    axes[1].plot(x,y,'o-',label='Score-quantile intervals');limit=max([*x,*y])*1.1
    axes[1].plot([0,limit],[0,limit],'--',color='grey',label='Perfect calibration')
    axes[1].set(xlabel='Mean predicted probability',ylabel='Observed detected-fire fraction',title='Coverage-conditioned retrospective reliability');axes[1].legend(fontsize=8)
    fig.suptitle('NASA NOAA-20 real data: research evaluation, not operational validation',fontsize=11)
    fig.tight_layout();fig.savefig(out/'evaluation.png',dpi=170);plt.close(fig)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data',required=True);p.add_argument('--models',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    r=review(a.data,a.models,a.out);print(json.dumps({'selected':r['selected'],'production_approved':r['release']['approved'],'failures':r['release']['failures']}))

if __name__=='__main__':main()
