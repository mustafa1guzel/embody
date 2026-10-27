export function UnifiedDiff({source}:{source:string}){
 return <pre className="unified-diff" aria-label="Exact unified source diff">{source.split('\n').map((line,index,lines)=><span key={index} className={line.startsWith('@@')?'hunk':line.startsWith('+')&&!line.startsWith('+++')?'added':line.startsWith('-')&&!line.startsWith('---')?'removed':''}>{line+(index<lines.length-1?'\n':'')}</span>)}</pre>;
}
