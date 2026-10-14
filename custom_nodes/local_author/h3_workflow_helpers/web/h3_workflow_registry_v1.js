import { app } from "../../../scripts/app.js";
import {
  SELECTOR_TYPE,
  REGISTRY_FLAG,
  registrySnapshot,
  functionById,
  registryWidget,
  currentFunctionId,
  applyFunction,
  selectFunction,
  requiredInputsSatisfied,
  queueSelectedFunction,
} from "./h3_workflow_registry_core.js";

/**
 * P1 N选1 注册表控制器（UI 层）。
 * 所有功能行为逻辑均在 h3_workflow_registry_core.js（单一事实源）。
 *
 * 隔离原则：
 *   只在图中存在带 h3_registry_v1=true 的 H3OperationSelector 节点时才启动。
 *   没有该标记 → 本文件立即 no-op，不接管任何 UI / mode / Queue。
 *   正式版无 h3_registry_v1，本控制器不生效，保持原 h3_foolproof_v2 行为。
 */

const EXCLUSIVE_COLOR = "#277a52";
const EXCLUSIVE_BG = "#123b2a";
const BYPASSED_COLOR = "#62408a";
const BYPASSED_BG = "#281a38";

function refreshPanel(node, selected) {
  const controls = node.__h3RegistryControls;
  if (!controls) return;
  for (const def of registrySnapshot()) {
    const control = controls.cards.get(def.function_id);
    if (!control) continue;
    const active = def.function_id === selected.function_id;
    control.card.style.background = active ? "#123b2a" : "#241833";
    control.card.style.borderColor = active ? "#62dfa0" : "#76549a";
    control.radio.checked = active;
    control.button.textContent = active ? `▶ ${def.action}` : def.action;
  }
  controls.state.textContent = selected.function_id === "all_bypass"
    ? "当前状态：全部功能已紫色旁路，不会提交任务。"
    : `当前已点亮：${selected.order}｜${selected.name_zh}。SELECT 不运行；点执行按钮才 Queue。`;
}

function applyAndRefresh(node, functionId) {
  const result = applyFunction(node, functionId);
  const controls = node.__h3RegistryControls;
  if (controls) {
    if (result.ok) refreshPanel(node, result.definition);
    else controls.state.textContent = result.message;
  }
  return result;
}

function installRegistryPanel(node, widget) {
  const panel = document.createElement("div");
  panel.style.cssText = "box-sizing:border-box;width:100%;padding:12px;background:#100d18;border:1px solid #76549a;border-radius:9px;color:#fff;font:600 14px sans-serif";

  const heading = document.createElement("div");
  heading.textContent = "导演台｜选择要执行的功能";
  heading.style.cssText = "font-size:18px;color:#e6d8ff;margin-bottom:6px";
  const hint = document.createElement("div");
  hint.textContent = "一采始终生成新视频。上传视频来源开关仅用于检测、扩时和二采；引用动作请开启“参考视频”。";
  hint.style.cssText = "font-size:12px;font-weight:500;color:#c7b4df;margin-bottom:10px;line-height:1.45";

  const grid = document.createElement("div");
  grid.style.cssText = "display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px";
  const cards = new Map();

  for (const definition of registrySnapshot()) {
    const card = document.createElement("div");
    card.style.cssText = "box-sizing:border-box;min-height:120px;padding:10px;border:2px solid #76549a;border-radius:8px;background:#241833;cursor:pointer;transition:.12s ease";
    card.dataset.registryFunction = definition.function_id;

    const top = document.createElement("label");
    top.style.cssText = "display:flex;gap:8px;align-items:center;cursor:pointer;color:#fff;font-size:14px";
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = `h3-registry-${node.id}`;
    radio.value = definition.function_id;
    radio.style.cssText = "width:17px;height:17px;accent-color:#52d692";
    const title = document.createElement("span");
    title.textContent = `${definition.order}｜${definition.name_zh}`;
    top.append(radio, title);

    const button = document.createElement("button");
    button.type = "button";
    button.textContent = definition.action;
    button.style.cssText = "width:100%;height:32px;border:0;border-radius:6px;background:#593d78;color:#fff;font:700 13px sans-serif;cursor:pointer";

    const cardClick = () => {
      const result = selectFunction(node, definition.function_id);
      if (result.ok) refreshPanel(node, result.definition);
      else if (node.__h3RegistryControls) node.__h3RegistryControls.state.textContent = result.message;
      return result;
    };
    radio.addEventListener("change", cardClick);
    card.addEventListener("click", (event) => {
      if (event.target === button || event.target === radio) return;
      cardClick();
    });
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (node.__h3RegistryControls?.busy) return;
      node.__h3RegistryControls.busy = true;
      for (const control of cards.values()) control.button.disabled = true;
      selectFunction(node, definition.function_id);
      queueSelectedFunction(node, definition.function_id, {
        async queueCallback() {
          await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
          await app.queuePrompt(0, 1);
        },
      }).then((result) => {
        const controls = node.__h3RegistryControls;
        if (controls) controls.state.textContent = result.message;
      }).finally(() => {
        node.__h3RegistryControls.busy = false;
        for (const control of cards.values()) control.button.disabled = false;
      });
    });

    card.append(top, button);
    grid.appendChild(card);
    cards.set(definition.function_id, { card, radio, button, definition });
  }

  const state = document.createElement("div");
  state.style.cssText = "margin-top:10px;padding:9px 10px;border-radius:6px;background:#0c241a;color:#aaf1ca;font-size:12px;line-height:1.4";
  panel.append(heading, hint, grid, state);
  for (const eventName of ["pointerdown", "pointerup", "mousedown", "mouseup", "click", "wheel", "keydown"]) {
    panel.addEventListener(eventName, (event) => event.stopPropagation());
  }

  node.__h3RegistryControls = { panel, cards, state, busy: false };
  const domWidget = node.addDOMWidget("h3_registry_v1", "H3_REGISTRY_V1", panel, {
    serialize: false,
    hideOnZoom: false,
    getHeight: () => 460,
  });
  domWidget.computeSize = (width) => [width, 460];
  node.setSize([820, 540]);
}

function installRegistrySelector(node) {
  if (node?.type !== SELECTOR_TYPE || node.__h3RegistryReady) return;
  // 隔离门：只有带 h3_registry_v1=true 才启动注册表控制器。
  if (node.properties?.h3_registry_v1 !== true) return;
  node.__h3RegistryReady = true;
  const widget = registryWidget(node);
  if (!widget) return;
  widget.draw = () => {};
  widget.computeSize = () => [0, -4];
  installRegistryPanel(node, widget);
  const originalCallback = widget.callback;
  widget.callback = function (value) {
    const result = originalCallback?.apply(this, arguments);
    setTimeout(() => applyAndRefresh(node, currentFunctionId(node)), 0);
    return result;
  };
  const fn = currentFunctionId(node);
  setTimeout(() => applyAndRefresh(node, fn), 0);
  installDiagnostics(node);
}

app.registerExtension({
  name: "H3.Workflow.RegistryV1Controller",
  beforeRegisterNodeDef(nodeType, nodeData) {
    const onCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const result = onCreated?.apply(this, arguments);
      setTimeout(() => installRegistrySelector(this), 0);
      return result;
    };
    const onConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
      const result = onConfigure?.apply(this, arguments);
      setTimeout(() => installRegistrySelector(this), 0);
      return result;
    };
  },
});

/**
 * 只读/安全诊断把手：仅在注册表控制器已启动（候选工作流）时暴露。
 * 正式版（无 h3_registry_v1）不暴露，确保隔离。
 */
function installDiagnostics(sel) {
  if (!sel || sel.properties?.h3_registry_v1 !== true) return;
  window.__H3_REGISTRY__ = {
    registry: () => registrySnapshot().map((f) => ({ function_id: f.function_id, name_zh: f.name_zh, order: f.order, h3_operation: f.h3_operation, allow_queue: f.allow_queue, required_inputs: f.required_inputs })),
    functionCount: () => registrySnapshot().length,
    applyFunction: (id) => applyAndRefresh(sel, id),
    currentFunctionId: () => currentFunctionId(sel),
    selectFunction: (id) => selectFunction(sel, id),
    queueSelectedFunction: (id, rt) => queueSelectedFunction(sel, id, rt),
    requiredSatisfied: (id) => requiredInputsSatisfied(sel, functionById(id)),
    selectors: () => {
      const graph = app.graph?._nodes || [];
      const out = {};
      for (const id of [159, 647, 886, 645, 884, 885]) {
        const n = graph.find((m) => m.id === id);
        out[id] = n ? { mode: n.mode, title: n.title } : null;
      }
      return out;
    },
    operationModes: () => {
      const graph = app.graph?._nodes || [];
      const result = [];
      for (const n of graph) {
        const tagged = n.properties?.h3_operation;
        if (!tagged) continue;
        result.push({ id: n.id, tagged, mode: n.mode });
      }
      return result;
    },
    sharedBypassed: () => {
      const graph = app.graph?._nodes || [];
      return graph.filter((n) => !n.properties?.h3_operation && n.mode === 4).map((n) => n.id);
    },
  };
}
