import {expect,it} from 'vitest';
import evidenceRaw from '../test/recorded-study.public.json?raw';
import {sampleAtTime} from './playback';
const samples=JSON.parse(evidenceRaw).experiments.A.variants.original.samples;
it('seeks the preceding actual measured timestamp without synthesizing states',()=>{
 expect(samples).toHaveLength(601);
 for(let i=0;i<samples.length-1;i++){
  expect(sampleAtTime(samples,samples[i].time)).toBe(i);
  expect(sampleAtTime(samples,(samples[i].time+samples[i+1].time)/2)).toBe(i);
 }
 expect(sampleAtTime(samples,-1)).toBe(0);expect(sampleAtTime(samples,100)).toBe(600);
});
