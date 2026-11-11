#!/usr/bin/env python3
"""Append-only synthetic QA DSR authority journal; never a production authority."""
from __future__ import annotations
from pathlib import Path
import argparse,hashlib,json,sys,tempfile
from dsr_restore_evidence import HEX64,TECH,canonical,run_crypto,timestamp,validate_event

VERSION="LF015-DSR-QA-JOURNAL-1"; SCOPE="synthetic_qa_closed_set"
KEYS={"version","scope","source_system_id","coverage_started_at_utc","covered_through_utc","snapshot_sequence","latest_event_sequence","previous_snapshot_sha256","events"}
def load(path):
 value=json.loads(Path(path).read_text(encoding="utf-8"))
 if set(value)!=KEYS or value["version"]!=VERSION or value["scope"]!=SCOPE or not TECH.fullmatch(str(value["source_system_id"])) or not isinstance(value["snapshot_sequence"],int) or value["snapshot_sequence"]<0 or not isinstance(value["latest_event_sequence"],int) or value["latest_event_sequence"]<0 or not isinstance(value["events"],list): raise ValueError("invalid QA journal")
 start=timestamp(value["coverage_started_at_utc"]); covered=timestamp(value["covered_through_utc"])
 if covered<start or value["latest_event_sequence"]!=len(value["events"]): raise ValueError("invalid QA journal")
 for sequence,event in enumerate(value["events"],1):
  if set(event)!={"sequence","evidence_id","disposition","effective_at_utc","publication_state"} or event["sequence"]!=sequence or not HEX64.fullmatch(str(event["evidence_id"])) or event["disposition"] not in {"deleted","restricted"} or event["publication_state"]!="confirmed" or timestamp(event["effective_at_utc"])<start: raise ValueError("invalid QA journal")
 if len({event["evidence_id"] for event in value["events"]})!=len(value["events"]): raise ValueError("invalid QA journal")
 previous=value["previous_snapshot_sha256"]
 if (value["snapshot_sequence"]==0 and previous is not None) or (value["snapshot_sequence"]>0 and not HEX64.fullmatch(str(previous))): raise ValueError("invalid QA journal")
 return value
def write_new(path,value):
 with Path(path).open("xb") as stream: stream.write(canonical(value))
 Path(path).chmod(0o600); return value
def next_snapshot(previous):
 value=dict(previous); value["snapshot_sequence"]+=1; value["previous_snapshot_sha256"]=hashlib.sha256(canonical(previous)).hexdigest(); value["events"]=list(previous["events"]); return value
def initialize(output,source_system_id,started):
 if not TECH.fullmatch(str(source_system_id)): raise ValueError("invalid source system")
 timestamp(started); return write_new(output,{"version":VERSION,"scope":SCOPE,"source_system_id":source_system_id,"coverage_started_at_utc":started,"covered_through_utc":started,"snapshot_sequence":0,"latest_event_sequence":0,"previous_snapshot_sha256":None,"events":[]})
def record(journal,artifact,key,output):
 previous=load(journal)
 with tempfile.TemporaryDirectory(prefix="lf015-dsr-qa-") as temporary:
  plain=Path(temporary)/"event.json"; run_crypto("decrypt",key,artifact,plain); event=validate_event(json.loads(plain.read_text(encoding="utf-8")))
 if timestamp(event["effective_at_utc"])<timestamp(previous["coverage_started_at_utc"]): raise ValueError("event predates QA authority")
 if event["evidence_id"] in {item["evidence_id"] for item in previous["events"]}: raise ValueError("duplicate QA evidence")
 value=next_snapshot(previous); sequence=previous["latest_event_sequence"]+1; value["latest_event_sequence"]=sequence
 value["events"].append({"sequence":sequence,"evidence_id":event["evidence_id"],"disposition":event["disposition"],"effective_at_utc":event["effective_at_utc"],"publication_state":"confirmed"})
 return write_new(output,value)
def checkpoint(journal,covered_through,pending_count,output):
 previous=load(journal); covered=timestamp(covered_through)
 if pending_count!=0 or covered<timestamp(previous["covered_through_utc"]) or any(timestamp(event["effective_at_utc"])>covered for event in previous["events"]): raise ValueError("incomplete QA checkpoint")
 value=next_snapshot(previous); value["covered_through_utc"]=covered_through; return write_new(output,value)
def export(journal,output,export_id):
 value=load(journal)
 if not TECH.fullmatch(str(export_id)) or any(timestamp(event["effective_at_utc"])>timestamp(value["covered_through_utc"]) for event in value["events"]): raise ValueError("QA authority is not checkpointed")
 events=[{"sequence":event["sequence"],"evidence_id":event["evidence_id"],"disposition":event["disposition"],"effective_at_utc":event["effective_at_utc"],"publication_state":"confirmed"} for event in value["events"]]
 return write_new(output,{"version":"LF015-DSR-ADMIN-EXPORT-1","scope":SCOPE,"source_system_id":value["source_system_id"],"authority_export_id":export_id,"coverage_started_at_utc":value["coverage_started_at_utc"],"covered_through_utc":value["covered_through_utc"],"complete_through_sequence":value["latest_event_sequence"],"events":events})
def main():
 parser=argparse.ArgumentParser(); sub=parser.add_subparsers(dest="command",required=True)
 p=sub.add_parser("init"); p.add_argument("--output",required=True,type=Path); p.add_argument("--source-system-id",required=True); p.add_argument("--coverage-started-at",required=True)
 p=sub.add_parser("record"); p.add_argument("--journal",required=True,type=Path); p.add_argument("--artifact",required=True,type=Path); p.add_argument("--key-file",required=True,type=Path); p.add_argument("--output",required=True,type=Path)
 p=sub.add_parser("checkpoint"); p.add_argument("--journal",required=True,type=Path); p.add_argument("--covered-through",required=True); p.add_argument("--pending-count",required=True,type=int); p.add_argument("--output",required=True,type=Path)
 p=sub.add_parser("export"); p.add_argument("--journal",required=True,type=Path); p.add_argument("--authority-export-id",required=True); p.add_argument("--output",required=True,type=Path)
 args=parser.parse_args()
 try:
  if args.command=="init": initialize(args.output,args.source_system_id,args.coverage_started_at)
  elif args.command=="record": record(args.journal,args.artifact,args.key_file,args.output)
  elif args.command=="checkpoint": checkpoint(args.journal,args.covered_through,args.pending_count,args.output)
  else: export(args.journal,args.output,args.authority_export_id)
  print(json.dumps({"status":"created"},separators=(",",":"))); return 0
 except Exception: print(json.dumps({"status":"failed","result_code":"dsr_qa_authority_error"},separators=(",",":"))); return 1
if __name__=="__main__": raise SystemExit(main())
