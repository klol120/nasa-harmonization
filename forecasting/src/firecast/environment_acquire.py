"""Reproduce fixed NASA land-cover, terrain and country-geometry acquisition."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlparse
from .acquire import nasa_download
from .earthdata import download_sample

COUNTRIES='https://firms.modaps.eosdis.nasa.gov/content/geodata/world_countries.geojson'

def acquire_environment(plan,out,token):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    entries=json.loads(Path(plan).read_text())
    for item in entries:
        url=item['url'];name=Path(urlparse(url).path).name
        if not name or name in {'.','..'}:raise ValueError('Invalid NASA filename')
        download_sample(url,out/'raw'/name,token)
    source=nasa_download(COUNTRIES,out/'raw/world_countries.geojson')
    collection=json.loads(source.read_text())
    matches=[f for f in collection['features'] if f.get('properties',{}).get('ISO_3DIGIT')=='LBN']
    if len(matches)!=1:raise ValueError('Expected exactly one NASA Lebanon analysis geometry')
    (out/'lebanon.geojson').write_text(json.dumps(matches[0],indent=2))
    (out/'inventory.json').write_text(json.dumps(entries,indent=2))
    return {'files':len(entries),'geometry_source':COUNTRIES,'complete':True}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--plan',required=True);p.add_argument('--out',required=True);p.add_argument('--token-file',required=True);a=p.parse_args()
    print(json.dumps(acquire_environment(a.plan,a.out,Path(a.token_file).read_text().strip())))

if __name__=='__main__':main()
