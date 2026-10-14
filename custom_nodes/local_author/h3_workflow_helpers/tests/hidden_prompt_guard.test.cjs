const {readFileSync}=require('node:fs');
const {join}=require('node:path');
const vm=require('node:vm');
const test=require('node:test');
const assert=require('node:assert/strict');
const source=readFileSync(join(__dirname,'../web/h3_workflow_registry_core.js'),'utf8');
const c={};vm.createContext(c);
vm.runInContext(source.slice(source.indexOf('function instantiatedGraphNodes('),source.indexOf('/**',source.indexOf('function validatePrimaryOutput('))),c);
function fixture(hidden,linked=true){
 const graph={_nodes:[{id:1,type:'CreateVideo',properties:{h3_operation:'pass1'},mode:0}],getNodeById:()=>({widgets:[{name:'prompt',value:hidden}]})};
 const prompt={'1':{inputs:{images:['2',0],audio:['3',0]}},'2':{class_type:'VAEDecode',inputs:{samples:['4',0]}},'3':{class_type:'VAEDecodeAudio',inputs:{samples:['4',1]}},'4':{class_type:'SamplerCustomAdvanced'},'136':{class_type:'MiniMaxH3ReferenceToVideo',inputs:{prompt:linked?['138',0]:'old internal text','ref_images.ref_image_0':['687',0]}},'138':{class_type:'PrimitiveStringMultiline',inputs:{value:'<Picture 1> identity only.'}}};
 return {graph,prompt};
}
test('stale hidden prompt blocks the real submission validator',()=>{const {graph,prompt}=fixture('STALE');assert.throws(()=>c.validatePrimaryOutput(graph,prompt),/内部旧 Prompt 必须为空/);});
test('disconnected external prompt cannot fall back to an internal string',()=>{const {graph,prompt}=fixture('',false);assert.throws(()=>c.validatePrimaryOutput(graph,prompt),/连接外部最终 Prompt/);});
test('empty hidden prompt and linked canonical external text pass',()=>{const {graph,prompt}=fixture('');assert.doesNotThrow(()=>c.validatePrimaryOutput(graph,prompt));});

test('submission keeps user Picture labels without requiring extra images',()=>{const {graph,prompt}=fixture('');graph.extra={h3_six_segment_director:{enabled:true}};graph._nodes.push({properties:{h3_six_director:true}});prompt['138'].inputs.value='<Picture 4> and <Picture 9> are user-authored text.';assert.doesNotThrow(()=>c.validatePrimaryOutput(graph,prompt));assert.equal(Object.keys(prompt['136'].inputs).length,2);});

test('unmarked frozen validator retains original Picture checks',()=>{const {graph,prompt}=fixture('');prompt['138'].inputs.value='<Picture 4>';assert.throws(()=>c.validatePrimaryOutput(graph,prompt),/实际只连接了 1 张/);});

function nativeFixture(){const f=fixture('');f.graph._nodes.push({type:'H3ContinuationProvider',properties:{h3_continuation_provider:'CORE_NATIVE_MASKED_AV'}});f.prompt['1'].inputs.images=['trim',0];f.prompt['1'].inputs.audio=['trim',1];f.prompt.trim={class_type:'H3ContinuationTrimOnce',inputs:{images:['2',0],audio:['3',0]}};return f;}
test('native trim still requires real sampled video and audio decodes',()=>{const {graph,prompt}=nativeFixture();assert.doesNotThrow(()=>c.validatePrimaryOutput(graph,prompt));prompt['2'].class_type='LoadImage';assert.throws(()=>c.validatePrimaryOutput(graph,prompt),/真实采样解码/);});
test('native trim does not bypass provenance without its native provider',()=>{const {graph,prompt}=nativeFixture();graph._nodes.pop();assert.throws(()=>c.validatePrimaryOutput(graph,prompt),/真实采样解码/);});
