"""Explicit, serializable global/local model adaptations and CPU neural networks."""
import copy
import warnings
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit,logit
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier,ExtraTreesClassifier,HistGradientBoostingClassifier
from sklearn.neural_network import MLPClassifier
from .global_data import FEATURES


def matrix(frame):return frame[FEATURES].to_numpy(dtype=np.float32)

def target(frame):return frame.y.to_numpy(dtype=np.int32)

def probabilities(p):
    p=np.clip(np.asarray(p,dtype=float),0,1)
    if not np.isfinite(p).all():raise ValueError('Nonfinite model probabilities')
    return np.column_stack([1-p,p])


class SeasonalModel:
    def fit(self,frame):
        f=frame.copy();f['month']=f.prediction_time.dt.month;f['hemisphere']=f.lat.ge(0)
        self.rate=float((f.y.sum()+1)/(len(f)+2));self.rates={}
        for key,g in f.groupby(['hemisphere','month']):self.rates[key]=float((g.y.sum()+1)/(len(g)+2))
        return self
    def predict_proba(self,frame):return probabilities([self.rates.get((a,m),self.rate) for a,m in zip(frame.lat.ge(0),frame.prediction_time.dt.month)])


class FrameModel:
    def __init__(self,algorithm,params,seed=42):self.algorithm=algorithm;self.params=params;self.seed=seed
    def fit(self,frame):
        x=matrix(frame);y=target(frame);self.scaler=None
        if self.algorithm in {'logistic','neural'}:self.scaler=StandardScaler().fit(x);x=self.scaler.transform(x)
        p=dict(self.params)
        if self.algorithm=='logistic':self.estimator=LogisticRegression(max_iter=500,random_state=self.seed,**p)
        elif self.algorithm=='forest':self.estimator=RandomForestClassifier(random_state=self.seed,n_jobs=2,**p)
        elif self.algorithm=='extra_trees':self.estimator=ExtraTreesClassifier(random_state=self.seed,n_jobs=2,**p)
        elif self.algorithm=='boosting':self.estimator=HistGradientBoostingClassifier(random_state=self.seed,early_stopping=False,**p)
        elif self.algorithm=='neural':self.estimator=MLPClassifier(random_state=self.seed,early_stopping=False,n_iter_no_change=1000,batch_size=512,**p)
        else:raise ValueError('Unknown algorithm')
        with warnings.catch_warnings(record=True) as records:
            warnings.simplefilter('always');self.estimator.fit(x,y)
        self.fit_warnings=sorted({type(r.message).__name__+': '+str(r.message) for r in records})
        self.fit_rows=len(frame);self.fit_positive_windows=int(frame.y.sum())
        return self
    def transform(self,frame):
        x=matrix(frame);return self.scaler.transform(x) if self.scaler is not None else x
    def predict_proba(self,frame):return probabilities(self.estimator.predict_proba(self.transform(frame))[:,1])


class PlattModel:
    def __init__(self,base):self.base=base
    def fit(self,calibration):
        x=logit(np.clip(self.base.predict_proba(calibration)[:,1],1e-7,1-1e-7)).reshape(-1,1)
        self.calibrator=LogisticRegression(C=1,max_iter=500).fit(x,target(calibration))
        self.calibration_rows=len(calibration);self.calibration_positive_windows=int(calibration.y.sum())
        return self
    def predict_proba(self,frame):
        x=logit(np.clip(self.base.predict_proba(frame)[:,1],1e-7,1-1e-7)).reshape(-1,1)
        return probabilities(self.calibrator.predict_proba(x)[:,1])


class ProbabilityEnsemble:
    def __init__(self,global_model,local_model,local_weight):self.global_model=global_model;self.local_model=local_model;self.local_weight=local_weight
    def predict_proba(self,frame):return probabilities((1-self.local_weight)*self.global_model.predict_proba(frame)[:,1]+self.local_weight*self.local_model.predict_proba(frame)[:,1])


class AnchoredLogistic:
    """Minimize local BCE plus a penalty toward the global coefficients; free intercept."""
    def __init__(self,base,strength):
        if not isinstance(base,FrameModel) or base.algorithm!='logistic':raise ValueError('Requires global logistic source')
        self.base=base;self.strength=strength
    def fit(self,frame):
        x=self.base.transform(frame).astype(float);y=target(frame);source=self.base.estimator
        anchor=np.r_[source.intercept_[0],source.coef_[0]].copy()
        def objective(w):
            z=w[0]+x@w[1:];residual=expit(z)-y;delta=w[1:]-anchor[1:]
            loss=np.mean(np.logaddexp(0,z)-y*z)+.5*self.strength*np.dot(delta,delta)
            grad=np.r_[residual.mean(),x.T@residual/len(y)+self.strength*delta]
            return loss,grad
        result=minimize(objective,anchor,jac=True,method='L-BFGS-B',options={'maxiter':200,'ftol':1e-10})
        if not np.isfinite(result.x).all():raise ValueError('Local adaptation diverged')
        self.weights=result.x;self.optimization={'converged':bool(result.success),'iterations':int(result.nit),'objective':float(result.fun)}
        return self
    def predict_proba(self,frame):return probabilities(expit(self.weights[0]+self.base.transform(frame)@self.weights[1:]))


def fine_tune_neural(base,frame,epochs,learning_rate,positive_weight=1):
    if not isinstance(base,FrameModel) or base.algorithm!='neural':raise ValueError('Requires pretrained neural network')
    model=copy.deepcopy(base);before=[a.copy() for a in model.estimator.coefs_]
    model.estimator.set_params(warm_start=True,max_iter=epochs,learning_rate_init=learning_rate)
    # Call estimator.fit directly: preserve the GLOBAL training scaler and pretrained weights.
    with warnings.catch_warnings(record=True) as records:
        warnings.simplefilter('always')
        weights=np.where(target(frame)==1,positive_weight,1.)
        model.estimator.fit(model.transform(frame),target(frame),sample_weight=weights)
    model.fit_warnings=sorted({type(r.message).__name__+': '+str(r.message) for r in records})
    model.adaptation={'method':'continued_neural_weights_with_frozen_global_scaler','epochs':epochs,'learning_rate':learning_rate,'positive_weight':positive_weight,
      'coefficient_change_l2':float(np.sqrt(sum(np.square(a-b).sum() for a,b in zip(model.estimator.coefs_,before))))}
    return model


class ScoreTransfer:
    """Fit a local tree to local features plus an out-of-domain pretrained global score."""
    def __init__(self,base,algorithm,params,seed=42):self.base=base;self.algorithm=algorithm;self.params=params;self.seed=seed
    def x(self,frame):return np.column_stack([matrix(frame),logit(np.clip(self.base.predict_proba(frame)[:,1],1e-7,1-1e-7))])
    def fit(self,frame):
        if self.algorithm=='boosting':self.estimator=HistGradientBoostingClassifier(random_state=self.seed,early_stopping=False,**self.params)
        elif self.algorithm=='forest':self.estimator=RandomForestClassifier(random_state=self.seed,n_jobs=2,**self.params)
        elif self.algorithm=='extra_trees':self.estimator=ExtraTreesClassifier(random_state=self.seed,n_jobs=2,**self.params)
        else:raise ValueError('Tree score transfer requires a supported tree family')
        self.estimator.fit(self.x(frame),target(frame));return self
    def predict_proba(self,frame):return probabilities(self.estimator.predict_proba(self.x(frame))[:,1])


def specifications():
    return [
      ('seasonal','seasonal',[{}]),
      ('logistic','logistic',[{'C':.1},{'C':1.0},{'C':1.0,'class_weight':'balanced'}]),
      ('random_forest','forest',[{'n_estimators':80,'max_leaf_nodes':256,'max_depth':14,'min_samples_leaf':30,'max_samples':80000},{'n_estimators':120,'max_leaf_nodes':512,'max_depth':16,'min_samples_leaf':30,'max_samples':100000,'class_weight':'balanced_subsample'}]),
      ('extra_trees','extra_trees',[{'n_estimators':100,'max_leaf_nodes':256,'max_depth':16,'min_samples_leaf':40},{'n_estimators':100,'max_leaf_nodes':512,'max_depth':18,'min_samples_leaf':30,'class_weight':'balanced'}]),
      ('gradient_boosting','boosting',[{'max_iter':100,'max_leaf_nodes':15,'l2_regularization':2},{'max_iter':160,'max_leaf_nodes':31,'l2_regularization':10,'learning_rate':.05}]),
      ('neural_32','neural',[{'hidden_layer_sizes':(32,),'max_iter':12,'learning_rate_init':.001,'alpha':.001},{'hidden_layer_sizes':(32,),'max_iter':24,'learning_rate_init':.001,'alpha':.01}]),
      ('neural_64_32','neural',[{'hidden_layer_sizes':(64,32),'max_iter':12,'learning_rate_init':.001,'alpha':.001},{'hidden_layer_sizes':(64,32),'max_iter':24,'learning_rate_init':.001,'alpha':.01}]),
      ('neural_128_64_32','neural',[{'hidden_layer_sizes':(128,64,32),'max_iter':12,'learning_rate_init':.001,'alpha':.001},{'hidden_layer_sizes':(128,64,32),'max_iter':24,'learning_rate_init':.001,'alpha':.01}])]
