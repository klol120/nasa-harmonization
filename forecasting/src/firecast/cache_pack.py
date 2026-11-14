"""Losslessly pack an inactive raw cache, verifying every byte before removing copies."""
import argparse
from datetime import datetime,timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def pack(raw_dir,packed_dir,target_free=400000000,batch_size=200):
    raw_dir=Path(raw_dir);packed_dir=Path(packed_dir);packed_dir.mkdir(parents=True,exist_ok=True)
    if raw_dir.resolve()==packed_dir.resolve():raise ValueError('Packed directory must differ from raw input')
    files=sorted(raw_dir.glob('VNP14A1*.h5'));done=0
    for offset in range(0,len(files),batch_size):
        if shutil.disk_usage(raw_dir).free>=target_free:break
        source=files[offset:offset+batch_size];paths=[]
        for p in source:
            meta=p.with_suffix('.h5.manifest.json')
            if not meta.exists() or digest(p)!=json.loads(meta.read_text())['sha256']:raise ValueError('Original NASA cache verification failed')
            paths.extend([p,meta])
        name='part-'+str(len(list(packed_dir.glob('part-*.tar.gz')))+1).zfill(4)+'.tar.gz';dest=packed_dir/name;temp=dest.with_suffix(dest.suffix+'.part')
        records=[{'name':p.name,'bytes':p.stat().st_size,'sha256':digest(p)} for p in paths]
        with temp.open('wb') as output:
            with gzip.GzipFile(fileobj=output,mode='wb',compresslevel=3,mtime=0,filename='') as compressed:
                with tarfile.open(fileobj=compressed,mode='w') as tar:
                    for p in paths:
                        info=tar.gettarinfo(str(p),arcname=p.name);info.mtime=0;info.uid=info.gid=0;info.uname=info.gname=''
                        with p.open('rb') as f:tar.addfile(info,f)
                    raw=json.dumps({'files':records,'original_dir_role':'Unfiltered NASA VNP14A1 original files and provenance'},sort_keys=True).encode()
                    info=tarfile.TarInfo('PACK-MANIFEST.json');info.size=len(raw);info.mtime=0;tar.addfile(info,io.BytesIO(raw))
        # Verify ALL members against pre-compression original hashes before any unlink.
        with tarfile.open(temp,'r:gz') as tar:
            for record in records:
                data=tar.extractfile(record['name']).read()
                if len(data)!=record['bytes'] or hashlib.sha256(data).hexdigest()!=record['sha256']:raise ValueError('Lossless archive verification failed')
        temp.replace(dest)
        dest.with_suffix(dest.suffix+'.manifest.json').write_text(json.dumps({'sha256':digest(dest),'verified_at':datetime.now(timezone.utc).isoformat(),'files':records,'original_bytes':sum(r['bytes'] for r in records),'archive_bytes':dest.stat().st_size},indent=2))
        for p in paths:p.unlink()
        done+=len(source);print('Losslessly archived',done,'original NASA files; free bytes',shutil.disk_usage(raw_dir).free,flush=True)
    return done


def restore(packed_dir,raw_dir):
    packed_dir=Path(packed_dir);raw_dir=Path(raw_dir);raw_dir.mkdir(parents=True,exist_ok=True)
    for archive in sorted(packed_dir.glob('part-*.tar.gz')):
        meta=json.loads(archive.with_suffix(archive.suffix+'.manifest.json').read_text())
        if digest(archive)!=meta['sha256']:raise ValueError('Archive checksum mismatch')
        with tarfile.open(archive,'r:gz') as tar:
            for record in meta['files']:
                name=record['name']
                if Path(name).name!=name:raise ValueError('Unsafe archive member name')
                dest=raw_dir/name
                if dest.exists():
                    if digest(dest)!=record['sha256']:raise ValueError('Existing restore target differs')
                    continue
                data=tar.extractfile(name).read()
                if hashlib.sha256(data).hexdigest()!=record['sha256']:raise ValueError('Restore checksum mismatch')
                dest.write_bytes(data)
    print('Restored exact NASA original files; packed copies preserved',flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('operation',choices=['pack','restore']);p.add_argument('--raw',required=True);p.add_argument('--packed',required=True);p.add_argument('--target-free',type=int,default=400000000);a=p.parse_args()
    if a.operation=='pack':pack(a.raw,a.packed,a.target_free)
    else:restore(a.packed,a.raw)

if __name__=='__main__':main()
