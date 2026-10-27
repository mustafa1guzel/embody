let token='';
export function setToken(value:string){token=value;}
export async function api<T>(path:string,body?:unknown):Promise<T>{
 const response=await fetch('/api/'+path,body===undefined?undefined:{method:'POST',headers:{'Content-Type':'application/json','X-EMBODY-Token':token},body:JSON.stringify(body)});
 const value=await response.json();
 if(!response.ok)throw Object.assign(new Error(value.error||'Backend request failed'),{diagnostics:value.diagnostics||[]});
 return value;
}
export async function job<T>(path:string,body:unknown,onProgress?:(message:string)=>void):Promise<T>{
 const {job_id}=await api<{job_id:string}>(path,body);
 onProgress?.('Running local operation · '+job_id.slice(0,8));
 for(;;){
  const result=await api<{status:string;result:T;error?:string}>('job?id='+job_id);
  if(result.status==='BLOCKED')throw new Error(result.error||'Operation blocked');
  if(result.status==='COMPLETED')return result.result;
  await new Promise(resolve=>setTimeout(resolve,800));
 }
}
