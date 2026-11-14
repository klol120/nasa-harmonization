import argparse
import json
from pathlib import Path
import pandas as pd
from .data import load_inputs,build_dataset,summarize
from .fixture import create_fixture
from .models import train_experiments
from .inference import predict,overlay

def prepare(data,config,out):
    tables,provenance=load_inputs(data,config);out=Path(out);out.mkdir(parents=True,exist_ok=True);datasets={}
    for policy in ['conservative','strict']:
        frame,audit=build_dataset(tables,config,policy);datasets[policy]=frame
        frame.to_csv(out/f'dataset-{policy}.csv',index=False)
        audit.to_csv(out/f'detection-audit-{policy}.csv',index=False)
    (out/'provenance.json').write_text(json.dumps(provenance,indent=2))
    (out/'exploration.json').write_text(json.dumps({p:summarize(f) for p,f in datasets.items()},indent=2,default=str))
    return datasets,provenance

def main():
    parser=argparse.ArgumentParser(description='Satellite-detected fire occurrence RESEARCH pipeline')
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('fixture');p.add_argument('--out',required=True);p.add_argument('--config',default='configs/lebanon.json')
    for cmd in ['prepare','run']:
        p=sub.add_parser(cmd);p.add_argument('--data',required=True);p.add_argument('--config',required=True);p.add_argument('--out',required=True)
    p=sub.add_parser('predict');p.add_argument('--model',required=True);p.add_argument('--input',required=True);p.add_argument('--out',required=True);p.add_argument('--lat',type=float);p.add_argument('--lon',type=float)
    p=sub.add_parser('overlay');p.add_argument('--risk',required=True);p.add_argument('--assets',required=True);p.add_argument('--out',required=True);p.add_argument('--buffer-km',type=float,default=1)
    p=sub.add_parser('sources');p.add_argument('--out',required=True)
    args=parser.parse_args()
    if args.command=='sources':
        from .sources import check_sources
        check_sources(args.out);return
    if args.command=='predict':
        if (args.lat is None)!=(args.lon is None): parser.error('Supply both lat and lon')
        predict(args.model,args.input,args.out,(args.lat,args.lon) if args.lat is not None else None);return
    if args.command=='overlay': overlay(args.risk,args.assets,args.out,args.buffer_km);return
    config=json.loads(Path(args.config).read_text())
    if args.command=='fixture': create_fixture(args.out,config);return
    datasets,provenance=prepare(args.data,config,args.out)
    if args.command=='run':
        report=train_experiments(datasets,config,args.out,provenance)
        # Export a fixture inference request only; real operations supply new forecasts.
        frame=datasets['conservative'];latest=frame[frame.prediction_time==frame.prediction_time.max()].copy()
        latest.drop(columns=['y','label_status','detection_count','sensor','event_type','observable']).to_csv(Path(args.out)/'inference-example.csv',index=False)
        print(json.dumps({'selected':report['selected'],'synthetic':config['synthetic']}))

if __name__=='__main__': main()
