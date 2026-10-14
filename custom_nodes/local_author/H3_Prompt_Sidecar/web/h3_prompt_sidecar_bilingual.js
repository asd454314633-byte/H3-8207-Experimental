import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

// H3 提示词导演：把 Sidecar 一次生成的中英文稿真实回填到节点自己的两个文本框。
// 只做「服务端已返回什么就写回什么」，不生成、不翻译、不联动、不覆盖用户手改。
const NODE_TYPE = "H3PromptSidecar";
const FIELDS = ["prompt_zh", "prompt_en", "delta_sha256", "scene_context_sha256", "reference_roles"];

function widgetMap(node) {
  const map = new Map();
  for (const w of node.widgets || []) {
    if (w && w.name) map.set(w.name, w);
  }
  return map;
}

api.addEventListener("executed", (event) => {
  const data = event && event.detail;
  if (!data || !data.output || data.node === undefined || data.node === null) return;
  const node = app.graph && app.graph.getNodeById(String(data.node));
  if (!node || node.type !== NODE_TYPE) return;
  const widgets = widgetMap(node);
  let touched = false;
  for (const key of FIELDS) {
    const payload = data.output[key];
    if (!Array.isArray(payload) || typeof payload[0] !== "string") continue;
    const widget = widgets.get(key);
    if (!widget) continue;
    if (widget.value !== payload[0]) {
      widget.value = payload[0];
      touched = true;
    }
  }
  if (touched && node.setDirtyCanvas) node.setDirtyCanvas(true, true);
});

// A compile-only submission uses the existing graph serializer unchanged.
// Preserve workflow metadata for material identity, but submit only this node's dependencies.
app.registerExtension({
  name: "H3.Sidecar.CompilePreview",
  nodeCreated(node) {
    if (node.type !== NODE_TYPE && node.comfyClass !== NODE_TYPE) return;
    node.addWidget("button", "只编译提示词（不生成视频）", null, async () => {
      try {
        const serialized = await app.graphToPrompt();
        const graph = serialized.output;
        const keep = {};
        function retain(id) {
          if (keep[id]) return;
          const entry = graph[id];
          if (!entry) throw new Error(`Missing compile dependency ${id}`);
          if (/Sampler|SaveVideo|CreateVideo/i.test(entry.class_type))
            throw new Error("编译依赖中出现视频节点，已停止提交");
          keep[id] = { ...entry, inputs: { ...entry.inputs } };
          for (const value of Object.values(entry.inputs || {}))
            if (Array.isArray(value) && value.length === 2 && typeof value[1] === "number") retain(String(value[0]));
        }
        retain(String(node.id));
        // Explicit compile action requests a new draft. Keep visible/user-edited
        // text until generation succeeds; never reuse a cached draft here.
        const request = keep[String(node.id)].inputs;
        request.prompt_en = "";
        request.prompt_zh = "";
        request.delta_sha256 = "";
        request.scene_context_sha256 = "";
        const workflow = { ...serialized.workflow, extra: { ...serialized.workflow.extra, sidecar_preview_only: true } };
        await api.queuePrompt(0, { output: keep, workflow });
      } catch (error) {
        console.error("Sidecar compile preview failed", error);
        alert(String(error));
      }
    }, { serialize: false });
  }
});
