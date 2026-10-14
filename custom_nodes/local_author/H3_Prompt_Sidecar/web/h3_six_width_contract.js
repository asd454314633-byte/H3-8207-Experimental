// Preserve the validated 1058px layout; never let generic computeSize collapse it.
export const SIX_MIN_WIDTH=1000;
export function installSixWidthContract(node){
  if(node.__sixWidthContract===3)return;
  node.__sixWidthContract=3;
  const compute=node.computeSize;
  node.computeSize=function(...args){const size=compute.apply(this,args);return [Math.max(SIX_MIN_WIDTH,size[0]),size[1]]};
  const sync=()=>{
    if(!Number.isFinite(node.size[0])||node.size[0]<SIX_MIN_WIDTH)node.size[0]=SIX_MIN_WIDTH;
    const root=node.__sixRoot, parent=root?.parentElement;
    // Vue DOM-widget layout can retain a stale width while the canvas node is wide.
    if(parent){
      const width=Math.max(SIX_MIN_WIDTH-20,node.size[0]-20)+'px';
      // A CSS floor also protects idle/background tabs where observers are throttled.
      if(parent.style.minWidth!==width)parent.style.minWidth=width;
      if(parent.style.width!==width)parent.style.width=width;
      // Layout updates can happen without another canvas draw (e.g. an idle tab).
      if(node.__sixWidthObservedRoot!==root){
        node.__sixWidthObserver?.disconnect();
        node.__sixWidthObserver=new ResizeObserver(sync);
        node.__sixWidthObserver.observe(root);
        node.__sixWidthObservedRoot=root;
      }
    }
  };
  for(const hook of ['onConfigure','onResize','onDrawForeground']){
    const previous=node[hook];node[hook]=function(...args){const result=previous?.apply(this,args);sync();return result};
  }
  node.__sixSyncWidth=sync;
  sync();
}
