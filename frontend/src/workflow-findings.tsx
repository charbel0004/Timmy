import { useEffect,useState } from 'react';
import type { FormEvent } from 'react';
import { request,errorMessage } from './api';
import { Badge } from './design';

type Finding={id:string;code:string;scope:string;subject:string;state:string;decision:string|null;evidence_ref:string|null;source_refs:string[];detail:Record<string,unknown>;options:string[];evidence_required:boolean};
type ProjectRound={project_id:number;project_code:string;validation_id:number;run_id:number;open:number;decided:number;findings:Finding[]};
type Round={projects:ProjectRound[];open_total:number;ready_for_payment:boolean;assurance:string};

const labels:Record<string,string>={
  invalidate:'Exclude these records from this payment request',
  escalate:'Escalate — keep the project blocked',
  correct_source:'Correct the source and reprocess',
};

function unit(finding:Finding){
  if(finding.scope==='activity')return `Activity ${finding.subject}`;
  if(finding.scope==='hours_month')return `Staff month ${finding.subject.replace('|',' · ')}`;
  return 'Project-wide evidence';
}

function FindingCard({finding,csrf,canExclude,onChanged}:{finding:Finding;csrf:string;canExclude:boolean;onChanged:()=>void}){
  const [decision,setDecision]=useState(finding.options[0]);
  const [evidence,setEvidence]=useState(''),[note,setNote]=useState('');
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const decided=finding.state!=='open';
  async function submit(event:FormEvent<HTMLFormElement>){
    event.preventDefault();setBusy(true);setError('');
    try{
      await request(`/workflow-findings/${finding.id}/decide`,{method:'POST',
        headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},
        body:JSON.stringify({decision,evidence_ref:evidence,note:note||undefined})});
      onChanged();
    }catch(err){setError(errorMessage(err));}finally{setBusy(false);}
  }
  return <article className="register-candidate"><h4>{finding.code}</h4>
    <Badge tone={decided?'green':'amber'}>{decided?finding.state.replaceAll('_',' '):'Open decision'}</Badge>
    <p className="muted">{unit(finding)}{finding.detail.affected_claims?` · ${String(finding.detail.affected_claims)} affected claims`:''}</p>
    {finding.source_refs.length>0&&<details><summary>Original source references</summary>
      <ul>{finding.source_refs.map(ref=><li key={ref}><code>{ref}</code></li>)}</ul></details>}
    {decided?<p className="muted">Decision: {finding.decision} · evidence {finding.evidence_ref}</p>
      :<form onSubmit={submit}>
        <label>Decision<select value={decision} onChange={event=>setDecision(event.target.value)}>
          {finding.options.map(option=><option key={option} value={option} disabled={option==='invalidate'&&!canExclude}>{labels[option]}</option>)}
        </select></label>
        <label>Evidence reference<input required minLength={5} maxLength={500} value={evidence}
          onChange={event=>setEvidence(event.target.value)}/></label>
        <label>Note<input maxLength={1000} value={note} onChange={event=>setNote(event.target.value)}/></label>
        <button disabled={busy||!evidence.trim()}>Record decision</button>
        {finding.evidence_required&&<p className="muted">Project-wide findings cannot be excluded: supply the evidence or escalate.</p>}
      </form>}
    {error&&<p role="alert">{error}</p>}
  </article>;
}

export function WorkflowFindings({conversation,csrf,permissions,revision,onResumed}:{conversation?:string;csrf:string;permissions:Record<string,string[]>;revision:number;onResumed:()=>void}){
  const [round,setRound]=useState<Round|null>(null),[error,setError]=useState(''),[refresh,setRefresh]=useState(0);
  useEffect(()=>{if(!conversation)return;let active=true;
    request<Round>(`/workflow-findings/conversations/${conversation}`).then(value=>{if(active){setRound(value);setError('');}},
      err=>{if(active)setError(errorMessage(err));});
    return()=>{active=false;};},[conversation,revision,refresh]);
  if(!conversation)return null;
  if(!round)return error?<p role="alert">{error}</p>:null;
  if(!round.projects.length)return null;
  const open=round.projects.filter(project=>project.findings.some(finding=>finding.state==='open'));
  if(!open.length)return <section className="report-register-panel"><h2>Flag decisions</h2>
    <p className="muted">All recorded flags are decided. A payment request still requires every planning, report and staff evidence gate.</p></section>;
  return <section className="report-register-panel"><h2>Flag decisions</h2>
    <p className="muted">One decision pass after processing: {round.open_total} flag(s) remain open. Excluding a record removes it from this payment request; nothing is corrected, added or paid automatically.</p>
    {open.map(project=>{
      const items=project.findings.filter(finding=>finding.state==='open');
      const grants=permissions[String(project.project_id)]||[];
      return <div key={project.project_id}><h3>{project.project_code} · {items.length} open of {project.findings.length}
        {project.decided>0&&<span className="muted"> · {project.decided} decided</span>}</h3>
        {items.map(finding=><FindingCard key={finding.id} finding={finding} csrf={csrf}
          canExclude={grants.includes('payments.allocate')}
          onChanged={()=>{setRefresh(value=>value+1);onResumed();}}/>)}
      </div>;
    })}
    {error&&<p role="alert">{error}</p>}
  </section>;
}
