"""Focused structural proof that ambiguous interaction is explicitly recoverable."""
from pathlib import Path
import json,sys

ROOT=Path(__file__).resolve().parents[2]
workflow=json.loads((ROOT/'workflows'/'leadflow_core_initial.json').read_text(encoding='utf-8'))
nodes={node['name']:node for node in workflow['nodes']}; connections=workflow['connections']; checks={}
def check(name,value): checks[name]=bool(value); print(('PASS' if value else 'FAIL')+' '+name)
def outputs(name): return [[edge['node'] for edge in branch] for branch in connections[name]['main']]

check('AMB-01-outcome-before-decision',outputs('Persist Interaction Outcome')==[['Interaction Succeeded']])
check('AMB-02-failure-enters-ambiguity-decision',outputs('Interaction Succeeded')[1]==['Interaction Ambiguous'])
check('AMB-03-explicit-recoverable-route',outputs('Interaction Ambiguous')[0]==['Respond Interaction Recoverable'])
check('AMB-04-no-ambiguous-terminalization','Persist CRM Failure' not in outputs('Interaction Ambiguous')[0])
check('AMB-05-definitive-failure-retained',outputs('Interaction Ambiguous')[1]==['Persist CRM Failure'])
response=nodes['Respond Interaction Recoverable']['parameters']
check('AMB-06-http-202',response['options']['responseCode']==202)
body=response['responseBody']
check('AMB-07-sanitized-response',all(token in body for token in ("status:'processing'","recoverable:true","type:'ambiguous_interaction'")) and all(token not in body for token in ('message','interest','email')))
persist=nodes['Persist Interaction Outcome']['parameters']
check('AMB-08-ambiguous-persisted','record_interaction_outcome' in persist['query'] and "item.json.ambiguous" in persist['options']['queryReplacement'])
checkpoint=nodes['Persist CRM Contact Checkpoint']['parameters']['query']
check('AMB-09-checkpoint-precedes-interaction','record_crm_contact_checkpoint' in checkpoint and outputs('Persist CRM Contact Checkpoint')==[['CRM Interaction']])
recovery=(ROOT/'scripts'/'recovery'/'continue_recovery.py').read_text(encoding='utf-8')
check('AMB-10-reconcile-before-write',recovery.index("'/crm/reconcile-interaction'")<recovery.index("'/crm/record-interaction'"))

failed=[name for name,value in checks.items() if not value]
print(f"RESULT: {'FAIL' if failed else 'PASS'}; passed={sum(checks.values())}/{len(checks)}")
sys.exit(1 if failed else 0)
