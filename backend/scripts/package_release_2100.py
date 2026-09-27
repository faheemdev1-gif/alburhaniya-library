#!/usr/bin/env python3
"""Validate source preservation, authorized metadata changes and ZIP contents."""
import argparse,hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
EXCLUDED={'__MACOSX','__pycache__','.pytest_cache','.venv','.git'}
def included(p):
 rel=p.relative_to(ROOT)
 return p.is_file() and not any(x in EXCLUDED or x.startswith('._') for x in rel.parts) and p.name not in {'library.db','.env'} and not p.name.startswith(('library.db-','.library.db.')) and p.suffix not in {'.zip','.pyc'}
def digest(b):return hashlib.sha256(b).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--original',required=True);ap.add_argument('--output',required=True);a=ap.parse_args();modified=[];preserved=[]
 with zipfile.ZipFile(a.original) as z:
  for name in z.namelist():
   if name.endswith('/'):continue
   rel=Path(*Path(name).parts[1:]);p=ROOT/rel
   if not p.is_file():raise RuntimeError('Missing original file: '+str(rel))
   if digest(p.read_bytes())==digest(z.read(name)):preserved.append(str(rel));continue
   if str(rel).startswith(('data/raw_htm/','data/raw_utf8/')) or str(rel)=='data/mapping.json':raise RuntimeError('Source content changed: '+str(rel))
   if str(rel)=='data/sources.json':
    before=json.loads(z.read(name));after=json.loads(p.read_text());decisions=json.loads((ROOT/'data/provenance_decisions_2100.json').read_text())['records']
    expected=json.loads(json.dumps(before))
    for decision in decisions:
     assert before['books'][decision['book_id']]==decision['before']
     expected['books'][decision['book_id']]=decision['after']
    assert expected==after,'Undocumented provenance edit'
   modified.append(str(rel))
 manifest=ROOT/'verification/2.10.0/package_manifest.json';files=sorted(p for p in ROOT.rglob('*') if included(p) and p!=manifest)
 manifest.write_text(json.dumps({'server_version':'2.10.0','original_sha256':digest(Path(a.original).read_bytes()),'raw_sources_unchanged':True,'documented_metadata_decisions':4,'modified_original_files':modified,'preserved_original_files':preserved,'files':[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':digest(p.read_bytes())} for p in files]},indent=2)+'\n')
 files.append(manifest);target=Path(a.output);target.parent.mkdir(parents=True,exist_ok=True);prefix='Al_Burhaniya_Connector_2.10.0'
 with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for p in sorted(files):z.write(p,f'{prefix}/{p.relative_to(ROOT).as_posix()}')
 with zipfile.ZipFile(target) as z:
  assert z.testzip() is None
  for p in files:assert digest(z.read(f'{prefix}/{p.relative_to(ROOT).as_posix()}'))==digest(p.read_bytes())
 print(json.dumps({'file':str(target),'bytes':target.stat().st_size,'sha256':digest(target.read_bytes()),'files':len(files),'raw_sources_unchanged':True}))
if __name__=='__main__':main()
