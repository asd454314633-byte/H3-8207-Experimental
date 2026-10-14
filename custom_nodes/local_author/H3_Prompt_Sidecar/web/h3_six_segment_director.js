import {app} from '../../../scripts/app.js';
import {api} from '../../../scripts/api.js';
import {executeVisiblePrompt} from './h3_six_execute.js?v=20261014queue';
import {installNativeMerge,beforeSixExecution} from './h3_native_merge.js?v=20261006switchbackend';

import {SIX_MIN_WIDTH,installSixWidthContract} from './h3_six_width_contract.js?v=20261006d';
import {storyId,restoreProductionIdentity,restoreProductionExecution,syncProductionTexts} from '/extensions/h3_conditioning_prebake/production.js?v=20261014queue';

function saveVideoNodeId(){
  const nodes=app.graph._nodes.filter(n=>(n.comfyClass||n.type)==='SaveVideo'&&n.properties?.h3_operation==='pass1');
  if(nodes.length!==1)throw Error('正式pass1 SaveVideo节点缺少或不唯一');
  return String(nodes[0].id);
}

async function resolveSegmentVideo(index,result){
  if(!result?.prompt_id)throw Error('缺少本段prompt_id');
  const response=await api.fetchApi(`/history/${encodeURIComponent(result.prompt_id)}`);
  if(!response.ok)throw Error('读取本段历史失败：'+response.status);
  const history=(await response.json())[result.prompt_id];
  if(history?.status?.status_str!=='success'||history.status.completed!==true)throw Error('本段历史尚未确认SUCCESS');
  const id=result.save_video_node_id||saveVideoNodeId();
  const nodeOutput=history.outputs?.[id];
  const videos=[...(nodeOutput?.images||[]),...(nodeOutput?.videos||[])].filter(v=>typeof v.filename==='string'&&/\.(mp4|webm|mov|mkv)$/i.test(v.filename));
  if(videos.length!==1)throw Error('正式SaveVideo输出不是唯一视频');
  const video=videos[0];
  if(typeof video.subfolder!=='string'||typeof video.type!=='string')throw Error('视频输出缺少subfolder/type');
  return {filename:video.filename,subfolder:video.subfolder,type:video.type,prompt_id:result.prompt_id};
}

function videoURL(ref){return api.apiURL('/view?'+new URLSearchParams({filename:ref.filename,subfolder:ref.subfolder,type:ref.type}).toString())}

function isolateConsolePromptControls() {
  const node=app.graph.getNodeById(159);
  if(!node?.properties?.h3_six_prompt_authority)return;
  const panel=node.__h3DashboardV3Panel;
  if(!panel)return;
  for(const section of panel.querySelectorAll('section')){
    if(section.querySelector('.h3v14-section-title')?.textContent==='④ 导演整理'){
      section.hidden=true;
    }
  }
}

function candidateActive(){return app.graph?.extra?.h3_six_segment_director?.enabled===true&&app.graph._nodes.some(n=>n.type==='H3SixDirectorState'&&n.properties?.h3_six_director===true)}
function updateCandidateEntrance(){for(const button of document.querySelectorAll('.h3-six-open'))button.hidden=!candidateActive()}
function hideBackendContinuityControl(){
  if(!candidateActive())return;
  const node=app.graph._nodes.find(n=>n.properties?.h3_six_backend_only===true);
  if(!node)return;
  node.flags.collapsed=true;
  for(const widget of node.widgets||[]){widget.type='hidden';widget.computeSize=()=>[0,-4]}
}

async function mount(node) {
  if(node.type==='H3SixDirectorState')installSixWidthContract(node);
  if(!candidateActive()||!node.properties?.h3_six_director||node.__sixRoot)return;
  const root=document.createElement('div');root.style.cssText='width:100%;height:100%;overflow:auto;overscroll-behavior:contain;box-sizing:border-box;padding:0 12px 16px 0';
  node.__sixRoot=root;
  const dom=node.addDOMWidget('h3_six_prompts','H3_SIX_PROMPTS',root,{serialize:false,hideOnZoom:false,getMinHeight:()=>760,getMaxHeight:()=>Infinity});
  const computeLayout=dom.computeLayoutSize;
  dom.computeLayoutSize=function(...args){return {...computeLayout.apply(this,args),minWidth:SIX_MIN_WIDTH-20}};
  const draw=dom.options.onDraw;
  dom.options.onDraw=function(...args){draw?.apply(this,args);node.__sixSyncWidth()};
  node.__sixSyncWidth();
  node.resizable=true;node.flags.resizable=true;
  let ready=false;
  node.__h3EditSync=Promise.resolve();
  const snapshot=()=>{
    if(!ready)return;
    node.properties.six_prompt_state={...node.properties.six_prompt_state,settings:root.querySelector('.six-settings').value,goal:root.querySelector('.six-goal').value,model:root.querySelector('.six-model').value,texts:[...root.querySelectorAll('.six-prompt')].map(t=>t.value),execution:node.__sixUI?.executionSnapshot()||node.properties.six_prompt_state?.execution,video_refs:node.__sixUI?.videoSnapshot()||node.properties.six_prompt_state?.video_refs||Array(6).fill(null)};
    app.graph.setDirtyCanvas(true,true);
  };
  root.addEventListener('input',event=>{snapshot();if(event.target.matches('.six-prompt'))node.__h3EditSync=node.__h3EditSync.catch(()=>{}).then(()=>syncProductionTexts(node));node.__h3EditSync.catch(error=>{node.__h3EditError=String(error);root.title='提示词同步失败：'+error.message;})});
  root.addEventListener('change',snapshot);root.addEventListener('sixchange',snapshot);
  // DOM text controls sit above the canvas; forward wheel to its native handler.
  root.addEventListener('wheel',event=>{if(!event.defaultPrevented)app.canvas.processMouseWheel(event)},{capture:true,passive:false});
  root.title='原生滚轮 / Ctrl+滚轮缩放；拖动节点右下角调整尺寸';
  // Text controls own scrolling and focus, rather than dragging the canvas.
  for(const name of ['pointerdown','mousedown','wheel','keydown'])root.addEventListener(name,event=>event.stopPropagation());
  try{
    await restoreProductionIdentity(node);
    const {mountSixDirector}=await import('/h3-director/six_ui.js?architecture=v1&continuous_button=20261014queue');
    const execute=async(...args)=>{await node.__h3EditSync?.catch(()=>{});await beforeSixExecution(root);const id=saveVideoNodeId();const result=await executeVisiblePrompt(...args);return {...result,save_video_node_id:id,superseded:result.execution_version&&result.execution_version!==node.properties.h3_prebake_binding?.execution_version}};
    const ui=await mountSixDirector(root,{base:'',execute,storyId:storyId(node),executionState:node.properties.six_prompt_state?.execution||{},videoRefs:node.properties.six_prompt_state?.video_refs||[],resolveVideo:resolveSegmentVideo,mediaURL:videoURL});
    const saved=node.properties.six_prompt_state;
    if(saved){root.querySelector('.six-settings').value=saved.settings||'';root.querySelector('.six-goal').value=saved.goal||'';if(saved.model)root.querySelector('.six-model').value=saved.model;ui.cards.forEach((c,i)=>{if(saved.texts?.[i]!==undefined)c.area.value=saved.texts[i]});root.querySelector('.six-model').dispatchEvent(new Event('h3-model-display'))}
    const binding=node.properties.h3_prebake_binding;
    if(binding){root.querySelector('.six-project').value=binding.project_id;root.querySelector('.six-start').value=String(binding.start_index);root.querySelector('.six-inheritance').value=binding.start_mode}
    node.__sixUI=ui;ready=true;snapshot();await restoreProductionExecution(node);
    try{await installNativeMerge(root,()=>{const b=node.properties.h3_prebake_binding,g=ui.group?.id;return {group_id:g||b?.group_id||node.properties.h3_prebake_last_plan?.group_id||storyId(node),project_id:g&&b&&g!==b.group_id?g:(b?.project_id||ui.executionSnapshot().project_id),save_video_node_id:saveVideoNodeId()}})}
    catch(error){root.querySelector('.six-status').textContent+='\n自动拼接未就绪：'+error.message}
  }catch(error){root.textContent='六段面板加载失败：'+error.message+'；请检查8197 Director接口'}
}
app.registerExtension({name:'H3.SixSegmentDirector',
  registerCustomNodes(){
    class H3SixDirectorState extends LGraphNode {
      constructor(){
        super('六段提示词导演台（独立状态）');
        this.isVirtualNode=true;
        this.properties={h3_six_director:true,six_prompt_state:{settings:'',goal:'',model:'dark_roast',texts:Array(6).fill('')},h3_six_prompts:''};
        this.size=[1800,1100];this.resizable=true;
        installSixWidthContract(this);
      }
      onConfigure(){this.isVirtualNode=true;this.resizable=true;this.flags.resizable=true}
      onSerialize(data){data.isVirtualNode=true}
    }
    LiteGraph.registerNodeType('H3SixDirectorState',H3SixDirectorState);
    H3SixDirectorState.category='H3';
  },
  nodeCreated(node){if(node.type==='H3SixDirectorState')setTimeout(()=>mount(node),0)},
  async afterConfigureGraph(){updateCandidateEntrance();hideBackendContinuityControl();for(const node of app.graph._nodes)if(node.type==='H3SixDirectorState')await mount(node);isolateConsolePromptControls();setTimeout(isolateConsolePromptControls,300);setTimeout(isolateConsolePromptControls,1200)},
  setup(){
    if(location.port!=='8197')return;
    const button=document.createElement('button');button.hidden=true;button.textContent='定位六段提示词';button.className='h3-six-open';
    button.style.cssText='position:fixed;right:22px;bottom:22px;z-index:1500;background:#294d43;color:#fff;border:1px solid #a7d7c5;border-radius:8px;padding:10px 18px;cursor:pointer';
    button.onclick=()=>{const node=app.graph._nodes.find(n=>n.type==='H3SixDirectorState'&&n.properties?.h3_six_director);if(node)app.canvas.centerOnNode(node)};
    const consoleButton=button.cloneNode();consoleButton.textContent='定位控制台';consoleButton.style.right='170px';consoleButton.onclick=()=>{const node=app.graph.getNodeById(159);if(node)app.canvas.centerOnNode(node)};
    document.body.append(button,consoleButton);updateCandidateEntrance();
  }
});


