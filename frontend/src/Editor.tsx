import {useEffect,useRef,useState} from 'react';
import type {editor} from 'monaco-editor';
import type {FileData} from './types';
// editor.api omits optional editor contributions. Preserve real keyboard, find
// and clipboard commands explicitly without loading every language or LSP.
import 'monaco-editor/editor/browser/coreCommands.js';
import 'monaco-editor/editor/contrib/find/browser/findController.js';
import 'monaco-editor/editor/contrib/clipboard/browser/clipboard.js';
import EditorWorker from 'monaco-editor/editor/editor.worker.js?worker';
import JsonWorker from 'monaco-editor/language/json/json.worker.js?worker';

const models=new Map<string,editor.ITextModel>();
let modulePromise:Promise<typeof import('monaco-editor/editor/editor.api.js')>|undefined;
function monaco(){
 if(!modulePromise){
  (self as any).MonacoEnvironment={getWorker:(_:string,label:string)=>label==='json'?new JsonWorker():new EditorWorker()};
  modulePromise=import('monaco-editor/editor/editor.api.js').then(async m=>{
   // Load the languages this project uses; no LSP client or all-language bundle.
   await Promise.all([import('monaco-editor/languages/definitions/python/register.js'),import('monaco-editor/languages/definitions/xml/register.js'),import('monaco-editor/language/json/monaco.contribution.js')]);
   return m;
  });
 }
 return modulePromise;
}
export default function Editor({file,draft,onChange,diff}:{file:FileData;draft:string;onChange:(value:string)=>void;diff?:{original:string;modified:string}}){
 const host=useRef<HTMLDivElement>(null),editorRef=useRef<editor.IStandaloneCodeEditor|null>(null);
 const [error,setError]=useState('');
 const change=useRef(onChange);change.current=onChange;
 useEffect(()=>{
  let alive=true,dispose:undefined|(()=>void);
  monaco().then(m=>{
   if(!alive||!host.current)return;
   m.editor.defineTheme('embody',{base:'vs-dark',inherit:true,rules:[],colors:{'editor.background':'#191E23','editor.foreground':'#DBDEE1','editorLineNumber.foreground':'#7F8993','editorLineNumber.activeForeground':'#DBDEE1','editorCursor.foreground':'#E2A15D','editor.selectionBackground':'#384752','editorGutter.background':'#191E23','diffEditor.insertedTextBackground':'#87B89B26','diffEditor.removedTextBackground':'#E17D7426'}});
   const options={theme:'embody',automaticLayout:true,fontFamily:'IBM Plex Mono',fontSize:12,lineHeight:20,minimap:{enabled:false},scrollBeyondLastLine:false,padding:{top:12},readOnly:file.historical,wordWrap:'off' as const};
   if(diff){
    const original=m.editor.createModel(diff.original,'python'),modified=m.editor.createModel(diff.modified,'python');
    const instance=m.editor.createDiffEditor(host.current,{...options,readOnly:true,renderSideBySide:true,originalEditable:false});
    instance.setModel({original,modified});dispose=()=>{instance.dispose();original.dispose();modified.dispose();};
   }else{
    let model=models.get(file.path);
    if(!model){model=m.editor.createModel(draft,file.path.endsWith('.py')?'python':file.path.endsWith('.json')?'json':file.path.endsWith('.xml')?'xml':'plaintext');models.set(file.path,model);}
    const instance=m.editor.create(host.current,{...options,model});editorRef.current=instance;
    const subscription=instance.onDidChangeModelContent(()=>change.current(instance.getValue()));
    dispose=()=>{subscription.dispose();instance.dispose();editorRef.current=null;};
   }
  }).catch(()=>{if(alive)setError('Monaco failed to load; editor unavailable. Source remains below.');});
  return()=>{alive=false;dispose?.();};
 },[file.path,file.historical,diff]);
 return <div className="editor-wrapper">{error?<><p role="alert">{error}</p><pre>{draft}</pre></>:<div className="monaco-host" ref={host} aria-label={diff?'Original versus proposal diff':'Code editor'}/>}</div>;
}
