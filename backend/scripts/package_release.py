#!/usr/bin/env python3
"""Package source and evidence, preserve originals, and verify the resulting ZIP."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parent.parent
EXCLUDED={'__MACOSX','__pycache__','.pytest_cache','.venv','.git'}


def included(path):
    rel=path.relative_to(ROOT)
    return path.is_file() and not any(p in EXCLUDED or p.startswith('._') for p in rel.parts) and path.name not in {'library.db','.env'} and path.suffix not in {'.zip','.pyc'}


def digest(data):return hashlib.sha256(data).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--original',required=True)
    parser.add_argument('--output',required=True);args=parser.parse_args()
    target=Path(args.output).resolve();target.parent.mkdir(parents=True,exist_ok=True)
    files=sorted(p for p in ROOT.rglob('*') if included(p))
    modified=[];missing=[];preserved=[]
    with zipfile.ZipFile(args.original) as original:
        for entry in original.infolist():
            if entry.is_dir() or '__MACOSX' in Path(entry.filename).parts:continue
            local=ROOT/entry.filename
            if not local.is_file():missing.append(entry.filename);continue
            if digest(local.read_bytes())!=digest(original.read(entry)):
                modified.append(entry.filename)
            else:preserved.append(entry.filename)
    if missing:raise RuntimeError(f'Original project files unexpectedly missing: {missing}')
    protected=[p for p in modified if p.startswith(('data/raw_htm/','data/raw_utf8/')) or p in ('data/sources.json','data/mapping.json')]
    if protected:raise RuntimeError(f'Authoritative source data unexpectedly changed: {protected}')
    manifest=ROOT/'verification/project_inventory.json'
    manifest.write_text(json.dumps({'modified_original_files':modified,
        'unchanged_original_files':preserved,'missing_original_files':missing,
        'authoritative_source_data_unchanged':True,
        'files':[{'path':str(p.relative_to(ROOT)),'sha256':digest(p.read_bytes()),'bytes':p.stat().st_size}
                 for p in files if p!=manifest]},ensure_ascii=False,indent=2)+'\n')
    files=sorted(p for p in ROOT.rglob('*') if included(p))
    prefix='Al_Burhaniya_Connector_2.7.0'
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in files:z.write(path,f'{prefix}/{path.relative_to(ROOT).as_posix()}')
    with zipfile.ZipFile(target) as z:
        if z.testzip():raise RuntimeError('ZIP checksum validation failed')
        for path in files:
            if digest(z.read(f'{prefix}/{path.relative_to(ROOT).as_posix()}'))!=digest(path.read_bytes()):
                raise RuntimeError(f'ZIP content mismatch: {path}')
    print(json.dumps({'output':str(target),'bytes':target.stat().st_size,'sha256':digest(target.read_bytes()),
                      'files':len(files),'modified_original_files':len(modified),'source_data_unchanged':True},indent=2))


if __name__=='__main__':main()
