// Tab-local input drafts only. These never contain authoritative engineering data.
export function readDraft<T>(key:string):T|undefined{try{const raw=sessionStorage.getItem('embody-draft:'+key);if(raw&&raw.length<=4000)return JSON.parse(raw) as T;}catch{/* Storage can be unavailable. */}return undefined;}
export function writeDraft(key:string,value:unknown){try{const raw=JSON.stringify(value);if(raw.length<=4000)sessionStorage.setItem('embody-draft:'+key,raw);}catch{/* The active draft still works in memory. */}}
export function clearDraft(key:string){try{sessionStorage.removeItem('embody-draft:'+key);}catch{/* No authority or backend evidence is stored here. */}}
