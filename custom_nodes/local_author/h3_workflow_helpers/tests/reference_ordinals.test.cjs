const {readFileSync}=require('node:fs');
const {join}=require('node:path');
const vm=require('node:vm');
const test=require('node:test');
const assert=require('node:assert/strict');
const source=readFileSync(join(__dirname,'../web/h3_workflow_registry_core.js'),'utf8');
const context={};vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('const H3_MEDIA_REF_RE'),source.indexOf('function applyFunction(')),context);
function fixture(role,slots,text){
 const inputs={prompt:[role?'915':'138',0]};
 for(const slot of slots)inputs['ref_images.ref_image_'+slot]=['image-'+slot,0];
 return {'136':{class_type:'MiniMaxH3ReferenceToVideo',inputs},'138':{class_type:'PrimitiveStringMultiline',inputs:{value:text}},'915':{class_type:'H3VideoPromptRole',inputs:{base_prompt:['138',0],picture_refs_enabled:true}}};
}
test('canonical third picture is not silently changed to the second across sparse slots',()=>{
 for(const role of [false,true]){
  const p=fixture(role,[0,2,3],'<Picture 1> face; <Picture 3> chair only; <Video 1> motion.');
  const before=p['138'].inputs.value;context.compactRefImageSlots(p);
  assert.equal(p['138'].inputs.value,before);
  assert.deepEqual(p['136'].inputs['ref_images.ref_image_2'],['image-3',0]);
  const once=JSON.stringify(p);context.compactRefImageSlots(p);assert.equal(JSON.stringify(p),once);
 }
});
test('Director canonical two-image mapping works with and without role node',()=>{
 for(const role of [false,true]){
  const p=fixture(role,[0,2],'<Picture 1> identity; <Picture 2> sofa only.');
  context.compactRefImageSlots(p);assert.equal(p['138'].inputs.value,'<Picture 1> identity; <Picture 2> sofa only.');
  assert.deepEqual(p['136'].inputs['ref_images.ref_image_1'],['image-2',0]);
 }
});
test('user image count never requires matching every Picture tag',()=>{
 for(const role of [false,true])for(const slots of [[],[0],[0,2],[0,1,2,3]]){
  const text='<Picture 4> user text; <Picture 9> optional description.';
  const p=fixture(role,slots,text);assert.doesNotThrow(()=>context.compactRefImageSlots(p,true));
  assert.equal(p['138'].inputs.value,text);
  const packed=Object.keys(p['136'].inputs).filter(k=>k.startsWith('ref_images.'));
  assert.equal(packed.length,slots.length);
  slots.forEach((slot,i)=>assert.deepEqual(p['136'].inputs['ref_images.ref_image_'+i],['image-'+slot,0]));
 }
});
test('nine inputs preserve ordinal order and role instructions verbatim',()=>{
 const text='<Subject 1> face from <Picture 1>; <Subject 2> object from <Picture 9>. No pose anchor.';
 const p=fixture(true,[0,1,2,3,4,5,6,7,8],text);context.compactRefImageSlots(p);
 assert.equal(p['138'].inputs.value,text);assert.equal(Object.keys(p['136'].inputs).length,10);
});

test('unmarked frozen workflows retain their original reference checks',()=>{const p=fixture(false,[0,1],'<Picture 4>');assert.throws(()=>context.compactRefImageSlots(p),/实际只有 2 张/);});
