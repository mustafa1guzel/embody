import {describe,expect,it} from 'vitest';
import * as monaco from 'monaco-editor/editor/editor.api.js';
import './Editor';
import {EditorExtensionsRegistry} from 'monaco-editor/editor/browser/editorExtensions.js';
import {CommandsRegistry} from 'monaco-editor/platform/commands/common/commands.js';
import 'monaco-editor/languages/definitions/python/register.js';
import 'monaco-editor/languages/definitions/xml/register.js';
import evidenceRaw from '../test/recorded-study.public.json?raw';
const evidence=JSON.parse(evidenceRaw);
describe('actual Monaco text models; DOM rendering separately unverified',()=>{
 it('registers the actual find action for the focused editor',()=>{
  expect(EditorExtensionsRegistry.getEditorActions().some(action=>action.id==='actions.find')).toBe(true);
  expect(CommandsRegistry.getCommand('undo')).toBeDefined();
  expect(CommandsRegistry.getCommand('redo')).toBeDefined();
 });
 it('loads exact project Python, supports real edit/undo/redo and retains source',()=>{
  const original=evidence.files['robot/controller.py'].content;
  const model=monaco.editor.createModel(original,'python');
  expect(model.getValue()).toBe(original);expect(model.getLanguageId()).toBe('python');
  model.pushStackElement();model.pushEditOperations([],[{range:new monaco.Range(1,1,1,1),text:'# local draft\n'}],()=>null);model.pushStackElement();
  expect(model.getValue()).toContain('# local draft');model.undo();expect(model.getValue()).toBe(original);model.redo();expect(model.getValue()).toContain('# local draft');model.dispose();
 });
 it('preserves actual original and model-generated modified source in distinct models',()=>{
  const original=monaco.editor.createModel(evidence.files['robot/controller.py'].content,'python');
  const modified=monaco.editor.createModel(evidence.proposals.attempt_2.source,'python');
  expect(original.getValue()).not.toBe(modified.getValue());expect(modified.getValue()).toBe(evidence.proposals.attempt_2.source);
  expect(monaco.languages.getLanguages().some(l=>l.id==='python')).toBe(true);original.dispose();modified.dispose();
 });
});
