import {useEffect,useRef,useState} from 'react';
export function sampleAtTime(samples:{time:number}[],time:number){
 let lo=0,hi=samples.length-1;
 while(lo<hi){const mid=Math.ceil((lo+hi)/2);if(samples[mid].time<=time)lo=mid;else hi=mid-1;}
 return lo;
}
export function usePlayback(samples:{time:number}[],index:number,setIndex:(value:number)=>void){
 const [playing,setPlaying]=useState(false),[speed,setSpeed]=useState(1);
 const cursor=useRef(index);cursor.current=index;
 useEffect(()=>{
  if(!playing||!samples.length)return;
  const startTime=performance.now(),start=samples[cursor.current].time;
  let request:number;
  function tick(now:number){
   const t=start+(now-startTime)/1000*speed;
   const next=sampleAtTime(samples,t);
   if(next!==cursor.current){cursor.current=next;setIndex(next);}
   if(next===samples.length-1){setPlaying(false);return;}
   request=requestAnimationFrame(tick);
  }
  request=requestAnimationFrame(tick);return()=>cancelAnimationFrame(request);
 },[playing,speed,samples,setIndex]);
 function seek(i:number){setPlaying(false);setIndex(Math.max(0,Math.min(samples.length-1,i)));}
 function toggle(){if(index===samples.length-1)setIndex(0);setPlaying(v=>!v);}
 return {playing,speed,setSpeed,seek,toggle,pause:()=>setPlaying(false)};
}
