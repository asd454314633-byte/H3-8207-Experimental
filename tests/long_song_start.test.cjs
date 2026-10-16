const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../custom_nodes/local_author/H3_LongSong/web/start_contract.js'),'utf8');
const modulePromise=import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
test('explicit Chinese/English origin overrides UI fallback',async()=>{
 const {resolveSongStart}=await modulePromise;
 const cases=[['音频起点=12.5秒',12.5],['从52秒开始生成',52],['音频起点=01:02.5',62.5],['从音频开头开始生成',0],['audio start=8.125 seconds',8.125],['beginning at the actual start of the original supplied song',0]];
 for(const [text,expected] of cases)assert.equal(resolveSongStart({enabled:true,start_seconds:52},text).start_seconds,expected);
});
test('ambiguous lyric/conflicting/invalid origin fails before submission',async()=>{
 const {resolveSongStart,seconds}=await modulePromise;
 for(const text of ['音频起点=0秒 audio start=52 seconds','从第一句歌词开始生成','音频起点=-1秒'])assert.throws(()=>resolveSongStart({enabled:true},text));
 assert.throws(()=>seconds('01:60'));
 assert.equal(resolveSongStart({enabled:true,lyric_start_seconds:12.5},'从第一句歌词开始生成').start_seconds,12.5);
 assert.equal(resolveSongStart({enabled:true}).start_seconds,0);
 assert.deepEqual(resolveSongStart({enabled:false,start_seconds:52},'音频起点=0秒'),{enabled:false,start_seconds:52});
});
