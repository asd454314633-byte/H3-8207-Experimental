import {app} from '../../../scripts/app.js';
export function prepareLongSong(snapshot,index,options){
 const config=options.long_song;
 if(!config?.enabled)return;
 const g=snapshot.output, prep=Object.values(g).find(n=>n.class_type==='H3ContinuationPrepare')?.inputs;
 if(!prep||g['136']?.class_type!=='MiniMaxH3ReferenceToVideo')throw Error('长歌需要现有Ref2VA和Native链');
 const scalar=v=>{if(!Array.isArray(v))return Number(v);const n=g[v[0]];if(n?.class_type?.startsWith('Primitive'))return Number(n.inputs.value);if(n?.class_type==='Any Switch (rgthree)')return scalar(Object.entries(n.inputs).sort().find(([,x])=>x!=null)?.[1]);throw Error('无法确认长歌实际输出帧率')};
 if(scalar(g['764'].inputs.fps)!==24)throw Error('长歌当前只支持原生24fps，未改变现有帧率设置');
 const inherit=options.continuous===true&&(index>0||options.cross_group?.enabled===true)&&options.independent!==true;
 g.LONG_SONG={class_type:'H3LongSongSegment',inputs:{source:config.source,start_seconds:Number(config.start_seconds),
   frames:structuredClone(g['136'].inputs.length),project_id:options.production_selection?.binding?.project_id||options.project_id||'H3_SIX_V288',
   segment_index:index,inherit,clean_rebase:inherit&&prep.clean_rebase_enabled===true&&Number(prep.clean_rebase_segment)===index,fps:24}};
 if(options.cross_group?.enabled)g.LONG_SONG.inputs.cross_group_json=JSON.stringify(options.cross_group.contract);
 const checks=Object.values(g).filter(n=>n.class_type==='H3Audio8ReferencePreflight');
 if(checks.length!==1)throw Error('长歌需要保留唯一15秒音频预检');
 Object.assign(checks[0].inputs,{audio1:['LONG_SONG',2],audio1_enabled:true,audio2_enabled:false,audio3_enabled:false,soundtrack_enabled:false});
 for(const k of Object.keys(g['136'].inputs))if(k.startsWith('ref_audios.')||k.startsWith('ref_video_audios.'))delete g['136'].inputs[k];
 const checkId=Object.keys(g).find(k=>g[k]===checks[0]);
 g['136'].inputs['ref_audios.ref_audio_0']=[checkId,0];
 g['136'].inputs.prompt=[checkId,4];
}
export function finishLongSong(graph,options,project){
 if(!options.long_song?.enabled)return graph;
 const song=graph.LONG_SONG;if(!song)throw Error('长歌取段节点被意外移除');
 song.inputs.project_id=project;
 for(const node of Object.values(graph)){
  if(node.class_type==='H3ContinuationAudioBranch')node.inputs.driving_audio=['LONG_SONG',0];
  if(node.class_type==='H3ContinuationTrimOnce')node.inputs.audio=['LONG_SONG',0];
 }
 // The existing Rebase composition audit requires a truly fresh latent with
 // no noise_mask. Preserve that contract and use Ref2VA audio on this segment.
 if(options.long_song.mode!=='reference'&&!song.inputs.clean_rebase){
  graph.LONG_SONG_LOCK={class_type:'H3LongSongLock',inputs:{latent:structuredClone(graph['125'].inputs.latent_image),audio:['LONG_SONG',0],audio_vae:['120',0]}};
  graph['125'].inputs.latent_image=['LONG_SONG_LOCK',0];
 }
 if(options.cross_group?.enabled){
  const proof=song.inputs.cross_group_json;
  for(const node of Object.values(graph))if(node.class_type==='H3ContinuationAssemble')node.inputs.cross_group_json=proof;
  if(song.inputs.segment_index===0){
   const prepare=Object.keys(graph).find(k=>graph[k].class_type==='H3ContinuationPrepare');
   graph.CROSS_GROUP_PREVIOUS={class_type:'H3CrossGroupPrevious',inputs:{cross_group_json:proof,target_project:project}};
   graph[prepare].inputs.prev_latent=['CROSS_GROUP_PREVIOUS',0];
   graph.CROSS_GROUP_AUDIT={class_type:'H3CrossGroupPrefixAudit',inputs:{latent:[prepare,0],plan_json:[prepare,1],cross_group_json:proof}};
   if(graph.LONG_SONG_LOCK)graph.LONG_SONG_LOCK.inputs.latent=['CROSS_GROUP_AUDIT',0];
   else graph['125'].inputs.latent_image=['CROSS_GROUP_AUDIT',0];
  }
 }
 return graph;
}
