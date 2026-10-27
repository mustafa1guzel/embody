import {useState} from 'react';
/** Keep exact evidence inspectable without eagerly serializing closed records. */
export default function EngineeringDetails({title,value}:{title:string;value:unknown}){
 const [open,setOpen]=useState(false);
 return <details onToggle={e=>setOpen(e.currentTarget.open)}><summary>{title}</summary>{open&&<pre>{JSON.stringify(value,null,2)}</pre>}</details>;
}
