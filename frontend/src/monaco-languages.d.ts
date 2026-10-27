// Side-effect registration module shipped without a public declaration.
declare module 'monaco-editor/language/json/monaco.contribution.js';
// Test-only inspection of the command registry shipped by the pinned editor.
declare module 'monaco-editor/editor/browser/editorExtensions.js' {
 export const EditorExtensionsRegistry:{getEditorActions():{id:string}[]};
}
declare module 'monaco-editor/platform/commands/common/commands.js' {
 export const CommandsRegistry:{getCommand(id:string):unknown};
}
