#!/usr/bin/env python3
"""Validate/extract LF015 archives and validate external DSR evidence receipts."""
from __future__ import annotations
from datetime import datetime,timezone
import json,re,shutil,sys,tarfile
from pathlib import Path,PurePosixPath
BACKUP_ID=re.compile(r"^leadflow-\d{8}T\d{6}Z-[0-9a-f]{12}\.tar\.gcm$"); SHA256=re.compile(r"^[0-9a-f]{64}$")
def _manifest(data: bytes) -> dict:
 if len(data)>4096: raise ValueError("manifest too large")
 value=json.loads(data)
 if set(value)!={"format","backup_id","created_utc","consistency"}: raise ValueError("manifest fields")
 if value["format"]!="LF015-1" or not BACKUP_ID.fullmatch(value["backup_id"]): raise ValueError("manifest identity")
 datetime.strptime(value["created_utc"],"%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
 if value["consistency"]!="n8n_paused_before_pg_dump_until_volume_copy": raise ValueError("manifest consistency")
 return value
def extract(path: Path,destination: Path,max_entries: int,max_total: int,max_member: int) -> dict:
 with tarfile.open(path,"r:") as archive:
  members=archive.getmembers(); names=set(); total=0; n8n_file=False
  if not members or len(members)>max_entries: raise ValueError("entry limit")
  for member in members:
   name=PurePosixPath(member.name); normalized=member.name.rstrip("/")
   if name.is_absolute() or ".." in name.parts or not (member.isfile() or member.isdir()): raise ValueError("unsafe entry")
   if not (normalized in {"manifest.json","postgres.dump","n8n"} or normalized.startswith("n8n/")): raise ValueError("unexpected entry")
   if normalized in names: raise ValueError("duplicate entry")
   names.add(normalized)
   if member.isfile() and normalized.startswith("n8n/"): n8n_file=True
   if member.size<0 or member.size>max_member: raise ValueError("member size")
   total+=member.size
   if total>max_total: raise ValueError("total size")
  if not {"manifest.json","postgres.dump"}.issubset(names) or not n8n_file: raise ValueError("incomplete archive")
  item=archive.extractfile(archive.getmember("manifest.json")); manifest=_manifest(item.read() if item else b"")
  destination.mkdir(mode=0o700)
  for member in members:
   target=destination.joinpath(*PurePosixPath(member.name).parts)
   if member.isdir(): target.mkdir(parents=True,exist_ok=True,mode=0o700)
   else:
    target.parent.mkdir(parents=True,exist_ok=True,mode=0o700); source=archive.extractfile(member)
    if source is None: raise ValueError("member missing")
    with source,target.open("xb") as output: shutil.copyfileobj(source,output,1024*1024)
    target.chmod(0o600)
  return manifest
def main() -> int:
 try:
  if len(sys.argv)==7 and sys.argv[1]=="extract": extract(Path(sys.argv[2]),Path(sys.argv[3]),*(int(v) for v in sys.argv[4:7]))
  else: return 2
  return 0
 except (OSError,ValueError,json.JSONDecodeError,tarfile.TarError,OverflowError): return 1
if __name__=="__main__": raise SystemExit(main())
