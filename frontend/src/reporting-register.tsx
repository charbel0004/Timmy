import { useEffect, useState } from 'react';
import { api, request, errorMessage } from './api';
import { Badge } from './design';

type Source = { id:string; name:string; project_ids:number[] };
type Sheet = {sheet_index:number;sheet_name:string;headers:string[];columns:Record<string,number>};
type Candidate = {file_id:string;filename:string;sha256:string;uploaded_at:string;sheets:Sheet[];confirmed_import_id:string|null;assurance:string;
 evaluation?:{rows:{project_id:number;activity_code:string;report_id:string;version:string;register_status:string;issue_codes:string[];cutoff:string|null}[]}};
const fields=['project_code','activity_code','report_id','report_version','submitted_at','validation_status','validated_at','evidence_ref'];

function DeclarationCard({conversation,candidate,sources,csrf,canConfirm,onConfirmed}:{conversation:string;candidate:Candidate;sources:Source[];csrf:string;canConfirm:boolean;onConfirmed:()=>void}) {
 const [source,setSource]=useState(sources[0]?.id||'');
 const [declared,setDeclared]=useState(false);
 const [mappings,setMappings]=useState(candidate.sheets.map(s=>({sheet_index:s.sheet_index,columns:Object.fromEntries(fields.map(f=>[f,s.columns[f]??-1]))})));
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 return <article className="register-candidate"><h3>{candidate.filename}</h3><p className="muted">Uploaded {candidate.uploaded_at} · original SHA-256: <code>{candidate.sha256}</code></p>
 {candidate.confirmed_import_id ? <><Badge tone="amber">Coordinator-declared provenance</Badge><p className="muted">This declaration is not independent reporting-team authentication. Report statuses below come from the register; importing them does not change them.</p>
 <div className="chat-table"><table><thead><tr><th>Project</th><th>Activity / report version</th><th>Register status</th><th>Frozen cutoff</th><th>Required review</th></tr></thead><tbody>{candidate.evaluation?.rows.map((r,i)=><tr key={i}><td>{r.project_id}</td><td>{r.activity_code} / {r.report_id} v{r.version}</td><td>{r.register_status}</td><td>{r.cutoff||'Not frozen'}</td><td>{r.issue_codes.join(', ')||'No evidence conflict found'}</td></tr>)}</tbody></table></div></> : <form onSubmit={async e=>{e.preventDefault();setBusy(true);setError('');try {
 await request(`/reporting-register/conversations/${conversation}/confirm`,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({source_id:source,file_id:candidate.file_id,sha256:candidate.sha256,official_export_declared:declared,sheets:mappings})});
 onConfirmed();
 } catch(err){setError(errorMessage(err));}finally{setBusy(false);}}}>
 <label>Approved register source<select required value={source} onChange={e=>setSource(e.target.value)}><option value="">Choose the designated register</option>{sources.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
 {candidate.sheets.map((sheet,index)=><details key={sheet.sheet_index}><summary>Review report column mapping · {sheet.sheet_name}</summary><div className="register-mappings">{fields.map(field=><label key={field}>{field.replaceAll('_',' ')}<select value={mappings[index].columns[field]} onChange={e=>setMappings(current=>current.map((m,i)=>i===index?{...m,columns:{...m.columns,[field]:Number(e.target.value)}}:m))}><option value={-1}>Select original column</option>{sheet.headers.map((h,i)=><option key={i} value={i}>{i+1}. {h}</option>)}</select></label>)}</div></details>)}
 <label className="register-declaration"><input type="checkbox" checked={declared} onChange={e=>setDeclared(e.target.checked)} required />I declare that this original workbook is an official export from the selected designated reporting register. This is my provenance declaration, not independent authentication by the reporting team.</label>
 {error&&<p role="alert">{error}</p>}<button disabled={busy||!declared||!source||!canConfirm||mappings.some(m=>Object.values(m.columns).some(i=>i<0))}>{busy?'Checking register evidence…':'Confirm mapping and official-export declaration'}</button>
 </form>}
 </article>;
}

export function ReportingRegisterPanel({conversation,csrf,canDesignate,canConfirm,revision,onResumed}:{onResumed:()=>void;conversation?:string;csrf:string;canDesignate:boolean;canConfirm:boolean;revision:number}) {
 const [files,setFiles]=useState<Candidate[]>([]),[sources,setSources]=useState<Source[]>([]);
 const [refresh,setRefresh]=useState(0),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{if(!conversation)return;let active=true;Promise.all([request<Candidate[]>(`/reporting-register/conversations/${conversation}`),request<Source[]>('/reporting-register/sources')]).then(([f,s])=>{if(active){setFiles(f);setSources(s);setError('');}},e=>{if(active)setError(errorMessage(e));});return()=>{active=false;};},[conversation,revision,refresh]);
 if(!conversation||(!files.length&&!error))return null;
 return <section className="report-register-panel"><h2>Official reporting register</h2><p className="muted">Report status remains exactly as supplied by the reporting process. A financial cutoff requires a designated source, declared provenance, registered activity and consistent validation evidence.</p>
 {error&&<p role="alert">{error}</p>}
 {!sources.length&&<><p role="status">An administrator must designate the official register before its statuses can be used.</p>{canDesignate&&<form onSubmit={async e=>{e.preventDefault();const name=String(new FormData(e.currentTarget).get('name'));setBusy(true);try{const projects=await api.projects();await request('/reporting-register/sources',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({name,project_ids:projects.map(p=>p.id),approved_source:true})});setRefresh(n=>n+1);}catch(err){setError(errorMessage(err));}finally{setBusy(false);}}}><label>Approved reporting register name<input name="name" required minLength={3} maxLength={160}/></label><p className="muted">This designates the named register for your currently assigned active projects. It does not validate any report or approve payments.</p><button disabled={busy}>Approve register-source designation</button></form>}</>}
 {files.map(file=><DeclarationCard key={file.file_id+(sources[0]?.id||'')} conversation={conversation} candidate={file} sources={sources} csrf={csrf} canConfirm={canConfirm} onConfirmed={()=>{setRefresh(n=>n+1);onResumed();}}/>)}
 </section>;
}
