// Preserve the clicked canvas, while binding its final prompt and immutable task.
// Later draft edits must not rewrite the workflow attached to a submitted task.
export function bindTaskWorkflow(workflow,{nodeId,widgetIndex,widgetName,text,context}) {
 const result=structuredClone(workflow);
 const node=result.nodes?.find(n=>String(n.id)===String(nodeId));
 if(!node||!Array.isArray(node.widgets_values)||widgetIndex<0||widgetIndex>=node.widgets_values.length)throw Error('无法把最终Prompt绑定到提交画布；未提交GPU');
 node.widgets_values[widgetIndex]=text;
 if(node.widgets_values_named&&Object.hasOwn(node.widgets_values_named,widgetName))node.widgets_values_named[widgetName]=text;
 if(context){
  const host=result.nodes.find(n=>n.type==='H3SixDirectorState');
  if(!host)throw Error('提交画布缺少六段身份宿主；未提交GPU');
  host.properties.h3_prebake_story_id=context.story_id;
  host.properties.h3_prebake_binding=structuredClone(context);
  host.properties.h3_prebake_revisions=[...context.revisions];
 }
 return result;
}
