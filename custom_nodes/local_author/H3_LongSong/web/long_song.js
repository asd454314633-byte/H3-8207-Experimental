import {app} from '../../../scripts/app.js';
import {api} from '../../../scripts/api.js';
import {resolveSongStart} from './start_contract.js?v=20261016origin1';
function mount(){
 for(const node of app.graph?._nodes||[]){
  const root=node.__sixRoot;if(node.type!=='H3SixDirectorState'||!root)continue;
  const existing=root.querySelector('.h3-long-song');if(existing?.dataset.version==='origin1')continue;existing?.remove();
  const cfg=node.properties.h3_long_song||{enabled:false,source:'',start_seconds:0,mode:'lock'};
  const box=document.createElement('section');box.className='h3-long-song';box.dataset.version='origin1';box.style.cssText='padding:12px;border:1px solid #527281;margin:8px 0;display:flex;flex-wrap:wrap;gap:8px';
  box.innerHTML='<label><input class="song-enabled" type="checkbox"> 完整歌曲自动分段</label><input class="song-source" placeholder="完整WAV或带声音MP4路径" style="width:55%"><label>起始秒 <input class="song-start" type="number" min="0" step="0.001" style="width:80px"></label><select class="song-mode"><option value="lock">指定音轨锁定（待口型验收）</option><option value="reference">Ref2VA参考（保留采样链）</option></select><button class="song-upload">上传一次完整音频/视频</button><small class="song-status">内部取段保留15秒预检；最终使用原曲。修改歌曲请开启新六段项目。</small>';
  const enabled=box.querySelector('.song-enabled'),source=box.querySelector('.song-source'),start=box.querySelector('.song-start'),mode=box.querySelector('.song-mode');
  const lyricLabel=document.createElement('label');lyricLabel.textContent='首句歌词秒数（可选） ';
  const lyric=document.createElement('input');lyric.className='song-lyric-start';lyric.type='number';lyric.min='0';lyric.step='0.001';lyric.style.width='80px';lyric.value=cfg.lyric_start_seconds??'';lyricLabel.append(lyric);box.append(lyricLabel);
  const effective=document.createElement('strong');effective.className='song-effective-start';effective.style.width='100%';box.append(effective);
  box.querySelector('.song-status').textContent='首段可写“音频起点=52.3秒”或“从52.3秒开始生成”；提示词起点优先。未指定时用起始秒。六段自动接续；修改起点须从第1段重生成。';
  mode.options[0].textContent='指定音轨锁定（Clean Rebase使用参考）';
  enabled.checked=cfg.enabled;source.value=cfg.source;start.value=cfg.start_seconds;mode.value=cfg.mode;
  const show=()=>{try{const resolved=resolveSongStart(node.properties.h3_long_song||cfg,root.querySelector('.six-prompt')?.value||'');const cross=node.properties.h3_cross_group;effective.textContent=cross?.enabled?(cross.contract?`跨组新增内容起点：${cross.contract.global_boundary}秒；39帧保护前缀内部回取`:'跨组已开启：请先核验并绑定上一组第6段'):resolved.enabled?`实际原曲起点：${resolved.start_seconds}秒（${resolved.start_origin}）；六段共用该起点`:'完整歌曲分段未启用';effective.style.color='#9de2ae'}catch(e){effective.textContent=e.message;effective.style.color='#ff9b9b'}};
  const save=()=>{node.properties.h3_long_song={enabled:enabled.checked,source:source.value.trim(),start_seconds:start.value,mode:mode.value,lyric_start_seconds:lyric.value===''?null:lyric.value};show();app.graph.setDirtyCanvas(true,true)};
  for(const el of [enabled,source,start,mode,lyric])el.addEventListener('change',save);
  root.addEventListener('input',e=>{if(e.target.matches('.six-prompt'))show()});root.addEventListener('sixchange',show);show();
  box.querySelector('.song-upload').onclick=()=>{
   const input=document.createElement('input');input.type='file';input.accept='audio/*,video/mp4,video/quicktime,video/webm';
   input.onchange=async()=>{const file=input.files?.[0];if(!file)return;const status=box.querySelector('.song-status');status.textContent='上传完整文件…';
    try{const form=new FormData();form.append('image',file);form.append('subfolder','long_song');form.append('overwrite','false');
     const response=await api.fetchApi('/upload/image',{method:'POST',body:form});const result=await response.json();if(!response.ok)throw Error(result.error||response.status);
     source.value=(result.subfolder?result.subfolder+'/':'')+result.name;enabled.checked=true;save();status.textContent='完整文件已上传一次；六段将内部自动取音轨。';
    }catch(e){status.textContent='上传失败：'+e.message}};input.click();
  };
  root.querySelector('.six-common')?.after(box);
 }
}
function attach(){let n=0;const timer=setInterval(()=>{mount();if(++n>=20)clearInterval(timer)},500)}
app.registerExtension({name:'H3.LongSong8207',afterConfigureGraph:attach,nodeCreated:attach});
