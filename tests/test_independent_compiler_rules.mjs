import assert from 'node:assert/strict';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';

const sourceUrl=process.env.H3_COMPILER_SOURCE
 ? pathToFileURL(resolve(process.env.H3_COMPILER_SOURCE))
 : new URL('../custom_nodes/local_author/H3_Prompt_Sidecar/web/h3_six_compiler.js',import.meta.url);

const snapshot={output:{'136':{class_type:'MiniMaxH3ReferenceToVideo',inputs:{length:192,'ref_images.ref_image_0':['IMG1',0]}},'IMG1':{class_type:'LoadImage',inputs:{image:'user-selected-reference.png'}}}};
async function runCase({roles,promptValid,compileResult,prompt='不合格提示词：随便画一个。',snapshotOverride=snapshot}){
 const {compileForSubmission}=await import(`${sourceUrl.href}?case=${Math.random()}`);
 const calls=[];globalThis.fetch=async(url,opts={})=>{const path=String(url).replace('/h3/compiler','');const body=opts.body?JSON.parse(opts.body):null;calls.push({path,body});let data={};
  if(path==='/api/state')data={project:{compiler_version:'test',active_segment_id:'ACTIVE',roles}};
  else if(path==='/api/segment/add')data={segment:{id:'SEG_TEST'}};
  else if(path==='/api/validate')data={report:{valid:promptValid}};
  else if(path==='/api/compile')data=compileResult;
  return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}});
 };
 const messages=[];const result=await compileForSubmission(prompt,0,{submission_id:'12345678'},m=>messages.push(m),snapshotOverride);return {prompt:result,calls,messages};
}
await assert.rejects(()=>runCase({roles:[],promptValid:false,compileResult:{ok:false,errors:['fixture']}}),/未匹配到真实角色档案/);
const ref=await runCase({roles:[{id:'R1',name:'林薇',name_en:'Lin Wei',aliases:[]}],prompt:'不合格提示词：林薇随便画一个。',promptValid:false,compileResult:{ok:true,prompt:'compiled prompt',report:{valid:true,checks:[]}}});
assert.equal(ref.prompt,'compiled prompt');const updates=ref.calls.filter(c=>c.path==='/api/segment/update');assert(updates.length>=1);const firstAssets=updates[0].body.assets;assert.equal(firstAssets.length,1);assert.deepEqual({role_id:firstAssets[0].role_id,purpose:firstAssets[0].purpose,note:firstAssets[0].note},{role_id:'',purpose:'',note:''});const compile=ref.calls.find(c=>c.path==='/api/compile');assert.deepEqual(compile.body.assets.map(a=>({role_id:a.role_id,purpose:a.purpose,note:a.note})),[{role_id:'',purpose:'',note:''}]);assert(ref.messages.some(m=>m.includes('用途由您决定')));
console.log(JSON.stringify({INVALID_PROMPT_BLOCKED:'PASS',REFERENCE_RESPONSIBILITY_USER_DECIDES:'PASS',calls_reference:ref.calls.map(c=>c.path)}));
const multi=structuredClone(snapshot);
Object.assign(multi.output['136'].inputs,{'ref_videos.ref_video_0':['V',0],'ref_video_audios.ref_video_audio_0':['PAIRED',0],'ref_video_audios.ref_video_audio_2':['UNCONSUMED',0],'ref_audios.ref_audio_0':['A',0]});
const labeled=await runCase({roles:[],promptValid:true,prompt:'official six-field prompt fixture',snapshotOverride:multi});
const assets=labeled.calls.find(c=>c.path==='/api/segment/update').body.assets;
assert.deepEqual(assets.map(a=>a.kind),['Picture','Video','Audio','Audio']);
assert(assets[2].label.includes('PAIRED'));assert(assets[3].label.includes('node_A'));
assert(!JSON.stringify(assets).includes('UNCONSUMED'));
const framed=structuredClone(snapshot);framed.output['136'].inputs.length=['M',1];framed.output.M={class_type:'ComfyMathExpression',inputs:{expression:'max(5, round(a * 24)) + (5 - (max(5, round(a * 24)) % 17)) % 17','values.a':['SECONDS',0]}};framed.output.SECONDS={class_type:'PrimitiveFloat',inputs:{value:8}};
const resolved=await runCase({roles:[],promptValid:true,prompt:'official prompt fixture',snapshotOverride:framed});
assert.equal(resolved.calls.find(c=>c.path==='/api/segment/add').body.duration,8);
framed.output.M.class_type='UnsupportedMath';
await assert.rejects(()=>runCase({roles:[],promptValid:true,prompt:'fixture',snapshotOverride:framed}),/无法解析/);
console.log('REAL_REFERENCE_KIND_ORDER_AND_FRAME_RESOLUTION_UNIT_CHECKS=PASS');

for(const token of ['<Picture 99>','<Video 1>','<Audio 1>']) {
 await assert.rejects(()=>runCase({roles:[],promptValid:true,prompt:'official '+token}),/没有对应实际接线/);
}
const validOfficial=await runCase({roles:[],promptValid:true,prompt:'official <Picture 1>'});assert.equal(validOfficial.prompt,'official <Picture 1>');
await assert.rejects(()=>runCase({roles:[{id:'R1',name:'林薇'}],prompt:'林薇看向参考图',promptValid:false,compileResult:{ok:true,prompt:'compiled <Picture 99>',report:{valid:true,checks:[]}}}),/没有对应实际接线/);
console.log('OFFICIAL_AND_COMPILED_REFERENCE_CONNECTION_GATES=PASS');
