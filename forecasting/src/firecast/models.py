"""Chronological experiments. All model/threshold selection uses validation only."""
import json
import platform
import hashlib
from pathlib import Path
import importlib.metadata
import joblib
import numpy as np
import pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import precision_recall_curve,average_precision_score,precision_score,recall_score,f1_score,confusion_matrix,brier_score_loss
from .data import WEATHER,ENV,summarize

class Seasonal:
    def fit(self,x,y):
        self.rate=(sum(y)+1)/(len(y)+2)
        self.month={m:(sum(np.asarray(y)[x.month.to_numpy()==m])+1)/(sum(x.month.to_numpy()==m)+2) for m in range(1,13)}
        return self
    def predict_proba(self,x):
        p=np.array([self.month.get(m,self.rate) for m in x.month]);return np.column_stack([1-p,p])

def features(frame):
    f=frame.copy();f['month']=f.prediction_time.dt.month
    f['season_sin']=np.sin(2*np.pi*f.prediction_time.dt.day_of_year/365.25)
    f['season_cos']=np.cos(2*np.pi*f.prediction_time.dt.day_of_year/365.25)
    return f

def split(frame,config):
    f=features(frame[frame.y.notna()].copy())
    a,b=pd.Timestamp(config['train_end']),pd.Timestamp(config['validation_end'])
    gap=pd.Timedelta(days=config['embargo_days'])
    if gap<pd.Timedelta(hours=config['horizon_hours']): raise ValueError('Embargo must cover horizon')
    if a>=b: raise ValueError('Split order')
    held=set(config.get('heldout_cells',[]))
    train=f[(f.window_end<a-gap)&~f.cell_id.isin(held)]
    val=f[(f.prediction_time>=a+gap)&(f.window_end<b-gap)&f.region.eq('lebanon')&~f.cell_id.isin(held)]
    test=f[(f.prediction_time>=b+gap)&f.region.eq('lebanon')&~f.cell_id.isin(held)]
    for part in [train,val,test]:
        if part.y.nunique()!=2: raise ValueError('Each temporal split needs both classes; no defensible experiment otherwise')
    return train,val,test,f[(f.prediction_time>=b+gap)&f.region.eq('lebanon')&f.cell_id.isin(held)]

def metrics(y,p,threshold):
    y=np.asarray(y,dtype=int);p=np.asarray(p);pred=p>=threshold
    bins=[]
    for lo in np.arange(0,1,.1):
        mask=(p>=lo)&(p<lo+.1 if lo<.9 else p<=1)
        if mask.any(): bins.append({'lower':float(lo),'n':int(mask.sum()),'mean_probability':float(p[mask].mean()),'observed_fraction':float(y[mask].mean())})
    return {'observations':len(y),'positive_windows':int(y.sum()),'pr_auc_average_precision':float(average_precision_score(y,p)) if len(set(y))>1 else None,
       'precision':float(precision_score(y,pred,zero_division=0)),'recall':float(recall_score(y,pred,zero_division=0)),
       'f1':float(f1_score(y,pred,zero_division=0)),'brier':float(brier_score_loss(y,p)),
       'threshold':float(threshold),'confusion_matrix_tn_fp_fn_tp':confusion_matrix(y,pred,labels=[0,1]).ravel().tolist(),'calibration':bins}

def evaluate(frame,p,threshold,seed):
    result=metrics(frame.y,p,threshold);result['at_threshold_0_5']=metrics(frame.y,p,.5)
    result['by_group']={}
    for col in ['region','sensor','event_type']:
        result['by_group'][col]={str(k):metrics(g.y,p[frame.index.get_indexer(g.index)],threshold) for k,g in frame.groupby(col)}
    season=((frame.prediction_time.dt.month%12)//3).map({0:'winter',1:'spring',2:'summer',3:'autumn'})
    result['by_group']['season']={str(k):metrics(frame.loc[g.index].y,p[frame.index.get_indexer(g.index)],threshold) for k,g in frame.groupby(season)}
    # Resample weeks as blocks, preserving spatial correlation within dates. Not independent incidents.
    weeks=frame.prediction_time.dt.strftime('%Y-%W').to_numpy(); unique=np.unique(weeks);rng=np.random.default_rng(seed); scores=[]
    for _ in range(100):
        idx=np.concatenate([np.flatnonzero(weeks==w) for w in rng.choice(unique,len(unique),replace=True)])
        if frame.y.iloc[idx].nunique()==2: scores.append(average_precision_score(frame.y.iloc[idx],p[idx]))
    result['weekly_bootstrap_pr_auc_95pct']=np.quantile(scores,[.025,.975]).tolist() if scores else None
    return result

def train_experiments(datasets,config,out,provenance):
    if not config.get('synthetic',False):
        from .real import require_ready
        require_ready(config.get('real_data_readiness',{'training_allowed':False,'blockers':['non-synthetic training requires a verified real-data readiness report']}))
    out=Path(out);out.mkdir(parents=True,exist_ok=True);runs=[]; artifacts=[]
    season=['season_sin','season_cos']
    environmental=config.get('environment_features',ENV)
    if not set(environmental)<=set(ENV):raise ValueError('Unknown environmental feature')
    for policy,frame in datasets.items():
        train,val,test,geo=split(frame,config)
        scopes=['lebanon']+(['regional'] if config.get('regional_cells') else [])
        for scope in scopes:
            tr=train[train.region.eq('lebanon') | (train.cell_id.isin(config['regional_cells']) if scope=='regional' else False)]
            if tr.y.nunique()!=2: raise ValueError('Training subset lacks events')
            specs=[('seasonal',['month'],Seasonal()),('weather',WEATHER+season,make_pipeline(StandardScaler(),LogisticRegression(max_iter=1000,random_state=config['seed']))),('environment',WEATHER+environmental+season,make_pipeline(StandardScaler(),LogisticRegression(max_iter=1000,random_state=config['seed'])))]
            if config.get('allow_tree') and len(tr)>=10000 and tr.y.sum()>=200:
                specs.append(('boosting',WEATHER+environmental+season,HistGradientBoostingClassifier(max_iter=100,max_leaf_nodes=15,l2_regularization=2,random_state=config['seed'],early_stopping=False)))
            for name,cols,model in specs:
                model.fit(tr[cols],tr.y.astype(int));pv=model.predict_proba(val[cols])[:,1]
                precision,recall,thresholds=precision_recall_curve(val.y,pv)
                fs=2*precision[:-1]*recall[:-1]/np.maximum(precision[:-1]+recall[:-1],1e-15)
                threshold=float(thresholds[int(np.argmax(fs))])
                run={'id':f'{policy}-{scope}-{name}','policy':policy,'scope':scope,'algorithm':name,'features':cols,
                     'train':{'observations':len(tr),'positive_windows':int(tr.y.sum()),'start':str(tr.prediction_time.min()),'end':str(tr.window_end.max())},
                     'validation':metrics(val.y,pv,threshold),'threshold':threshold}
                artifact={'model':model,'features':cols,'config':config,'threshold':threshold,'id':run['id'],
                          'bounds':{c:[float(tr[c].min()),float(tr[c].max())] for c in cols},'provenance':provenance}
                runs.append(run);artifacts.append((artifact,test,geo))
    # Freeze selection before calculating any test results. Brier prioritizes probability quality.
    primary=config.get('primary_policy','conservative')
    by_policy={policy:min((i for i,r in enumerate(runs) if r['policy']==policy),key=lambda i:runs[i]['validation']['brier']) for policy in datasets}
    if primary not in by_policy: raise ValueError('Primary policy must be present')
    best=by_policy[primary]
    for run,(artifact,test,geo) in zip(runs,artifacts):
        p=artifact['model'].predict_proba(test[artifact['features']])[:,1]
        run['test']=evaluate(test,p,run['threshold'],config['seed'])
        if len(geo): run['geographic_test']=evaluate(geo,artifact['model'].predict_proba(geo[artifact['features']])[:,1],run['threshold'],config['seed'])
        run['parameters']=str(artifact['model'].get_params()) if hasattr(artifact['model'],'get_params') else 'Beta(1,1) month smoothing'
    winner=artifacts[best][0]
    signature={'config':config,'inputs':{k:v['sha256'] for k,v in provenance.items()},'experiment':winner['id'],
               'code':hashlib.sha256(b''.join(p.read_bytes() for p in sorted(Path(__file__).parent.glob('*.py')))).hexdigest()}
    winner['version']=winner['id']+'-'+hashlib.sha256(json.dumps(signature,sort_keys=True).encode()).hexdigest()[:16]
    joblib.dump(winner,out/'model.joblib')
    report={'synthetic':config['synthetic'],'mode':config['mode'],'selected':runs[best]['id'],'model_version':winner['version'],'selection':'lowest validation Brier within predeclared primary policy; test never used for selection',
      'selected_by_policy':{k:runs[i]['id'] for k,i in by_policy.items()},
      'code_sha256':hashlib.sha256(b''.join(p.read_bytes() for p in sorted(Path(__file__).parent.glob('*.py')))).hexdigest(),
      'config':config,'provenance':provenance,'python':platform.python_version(),
      'versions':{p:importlib.metadata.version(p) for p in ['numpy','pandas','scikit-learn','joblib']},
      'datasets':{k:summarize(v) for k,v in datasets.items()},'experiments':runs,
      'limitations':['Synthetic metrics measure mechanics only' if config['synthetic'] else 'Satellite detections are incomplete incident labels',
        'No independent incident grouping available; seven-day embargo does not guarantee separation of long-running incidents',
        'Sensor subgroup metrics describe positive-detection attribution, not sensor-specific population performance',
        'Bootstrap intervals condition on fitted model and labels; they omit source and label uncertainty']}
    (out/'metrics.json').write_text(json.dumps(report,indent=2,default=str,allow_nan=False))
    return report
