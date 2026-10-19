import assert from 'node:assert/strict';

const snapshot={output:{'136':{class_type:'MiniMaxH3ReferenceToVideo',inputs:{length:192,'ref_images.ref_image_0':['IMG1',0]}},'IMG1':{class_type:'LoadImage',inputs:{image:'user-selected-reference.png'}}}};
async function runCase({roles,promptValid,compileResult,prompt='不合格提示词：随便画一个。'}){
 const {compileForSubmission}=await import('./h3_six_compiler_under_test.mjs?case='+Math.random());
 const calls=[];globalThis.fetch=async(url,opts={})=>{const path=String(url).replace('/h3/compiler','');const body=opts.body?JSON.parse(opts.body):null;calls.push({path,body});let data={};
  if(path==='/api/state')data={project:{compiler_version:'test',active_segment_id:'ACTIVE',roles}};
  else if(path==='/api/segment/add')data={segment:{id:'SEG_TEST'}};
  else if(path==='/api/validate')data={report:{valid:promptValid}};
  else if(path==='/api/compile')data=compileResult;
  return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}});
 };
 const messages=[];const result=await compileForSubmission(prompt,0,{submission_id:'12345678'},m=>messages.push(m),snapshot);return {prompt:result,calls,messages};
}
const bad=await runCase({roles:[],promptValid:false,compileResult:{ok:false,errors:['fixture']}});
assert.equal(bad.prompt,'不合格提示词：随便画一个。');assert(!bad.calls.some(c=>c.path==='/api/compile'));assert(bad.messages.some(m=>m.includes('按原稿提交')));
const ref=await runCase({roles:[{id:'R1',name:'林薇',name_en:'Lin Wei',aliases:[]}],prompt:'不合格提示词：林薇随便画一个。',promptValid:false,compileResult:{ok:true,prompt:'compiled prompt',report:{valid:true,checks:[]}}});
assert.equal(ref.prompt,'compiled prompt');const updates=ref.calls.filter(c=>c.path==='/api/segment/update');assert(updates.length>=1);const firstAssets=updates[0].body.assets;assert.equal(firstAssets.length,1);assert.deepEqual({role_id:firstAssets[0].role_id,purpose:firstAssets[0].purpose,note:firstAssets[0].note},{role_id:'',purpose:'',note:''});const compile=ref.calls.find(c=>c.path==='/api/compile');assert.deepEqual(compile.body.assets.map(a=>({role_id:a.role_id,purpose:a.purpose,note:a.note})),[{role_id:'',purpose:'',note:''}]);assert(ref.messages.some(m=>m.includes('用途由您决定')));
console.log(JSON.stringify({INVALID_PROMPT_STILL_ALLOWED:'PASS',REFERENCE_RESPONSIBILITY_USER_DECIDES:'PASS',calls_invalid:bad.calls.map(c=>c.path),calls_reference:ref.calls.map(c=>c.path)}));
