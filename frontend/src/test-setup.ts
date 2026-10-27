import '@testing-library/jest-dom/vitest';
import {afterEach,vi} from 'vitest';
import {cleanup} from '@testing-library/react';
afterEach(()=>{cleanup();sessionStorage.clear();vi.unstubAllGlobals();});
Object.defineProperty(window,'matchMedia',{writable:true,value:(query:string)=>({matches:false,media:query,addEventListener(){},removeEventListener(){},addListener(){},removeListener(){}})});
globalThis.ResizeObserver=class {observe(){}unobserve(){}disconnect(){}};
