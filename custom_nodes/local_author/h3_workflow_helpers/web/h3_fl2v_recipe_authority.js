/* =============================================================
 * H3 FL2V FROZEN RECIPE AUTHORITY + SUBMIT FAIL-CLOSED
 * Task: H3_FL_FROZEN_RECIPE_AUTHORITY_REPAIR_20260906
 * Repair: H3_V28_2_REF2VA_STABLE8_REVALIDATION_04 / JS_GUARD
 *         FAIL_CLOSED_REPAIR_20260930 (author-directed)
 * -------------------------------------------------------------
 * WHY: the existing H3 console sync (syncGenerationMode /
 *      syncSpeedMode / syncFl2vRoute) only owns node MODE.
 *      Nothing in the codebase owns the WIDGET VALUE of
 *      N646 (unet_name) / N880 (scheduler) / N882 (F4 steps) /
 *      N883 (F1 steps). Those values therefore drift and stay
 *      drifted. This module adds the missing VALUE authority and
 *      a fail-closed check on the REAL graphToPrompt output.
 *
 * REPAIR 20260930 (v028_2, author order: UNKNOWN must NOT pass):
 *  1) FAIL_CLOSED_BEFORE was INEFFECTIVE for two reasons:
 *     a. setup() wrapped app.graphToPrompt too early (or the
 *        wrap was later overwritten by other extensions) so the
 *        gate never ran. Fixed: retry wrap + additional
 *        beforeQueued hook as a second, overwrite-proof gate.
 *     b. detectBranch UNKNOWN returned ok:true skipped:true
 *        (silent pass). Fixed: unknown branch on an H3 graph is
 *        now a hard rejection. Only graphs with NO H3-flavored
 *        class_type at all are skipped as NOT_H3_GRAPH.
 *  2) Node ids are no longer trusted alone. Selectors are
 *     discovered by class_type first (H3GenerationModeSelector /
 *     H3Fl2vRouteSelector) with legacy ids kept as fallback.
 *  3) v028_2 closeout (2026-09-29) removed legacy F1/F4 route
 *     nodes (876/877/879/882/883/884/969). Rules that REQUIRED
 *     their presence are removed; rules that CHECK values when
 *     present are kept ("present => verify" semantics) so the
 *     gate still catches drift without rejecting v028_2 FL2VA
 *     submissions. Branch/value checks for REF2VA backend axis
 *     (stable8/pdd8) are deliberately NOT duplicated here: that
 *     axis is owned by syncRef2vaBackend + live six-layer gate.
 *
 * RULES (frozen, do not change):
 *   N646 = 10Eros_Max_H3_FL2VA-NVFP4.safetensors   ALWAYS
 *   N620 = REF2VA checkpoint                        ALWAYS
 *          (never "simulate" REF2VA by editing N646)
 *   N880.scheduler = simple                         ALWAYS
 *   Steps are user-owned (v016): F4=4 / F1=8 are recommendations.
 *   LoRA files / strengths / Sigma 6-3 / Sage impl / VAE /
 *   sampler / 10E model file are NOT touched here.
 *
 * SOURCE IS ASCII-ONLY ON PURPOSE (bridge delivery safety).
 * Chinese user-facing strings use \uXXXX escapes.
 * ============================================================= */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module && module.exports) module.exports = api;
  if (typeof window !== "undefined") window.H3Fl2vRecipeAuthority = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var FL2VA_MODEL = "minimax_h3_fastvideo_vsa_datafree_1300step_4step_int8_convrot.safetensors";
  var REF2VA_REPAIR_MODEL = "minimax_h3_ref2va_pruned_int8_convrot.safetensors";
  var FROZEN_SCHEDULER = "simple";
  var F4_STEPS = 4;
  var F1_STEPS = 8;

  var ERR_DRIFT = "FL2V \u51bb\u7ed3\u914d\u65b9\u53d1\u751f\u6f02\u79fb\uff0c\u5df2\u62d2\u7edd\u63d0\u4ea4\u3002";
  var ERR_CHECK = "FL2V \u51bb\u7ed3\u914d\u65b9\u6821\u9a8c\u5931\u8d25\uff0c\u5df2\u62d2\u7edd\u63d0\u4ea4\uff1a";
  var ERR_BRANCH_UNKNOWN = "H3 \u5de5\u4f5c\u6d41\u5206\u652f\u65e0\u6cd5\u5224\u5b9a\uff08fail-closed\uff09\uff0c\u5df2\u62d2\u7edd\u63d0\u4ea4\u3002";

  var ID = {
    FL2VA_UNET: "646",
    REF2VA_UNET: "620",
    SCHEDULER: "880",
    F4_LORA: "877",
    F4_SIGMA: "878",
    F4_STEPS: "882",
    F1_SAGE: "876",
    F1_LORA: "879",
    F1_STEPS: "883",
    GEN_SELECTOR: "647",
    ROUTE_SELECTOR: "886"
  };

  /* Semantic class-type anchors (v028_2): discovery by class_type
   * first, legacy node ids only as fallback. */
  var CLS = {
    GEN_SELECTOR: "H3GenerationModeSelector",
    ROUTE_SELECTOR: "H3Fl2vRouteSelector"
  };

  /* ---------------- prompt-side helpers ---------------- */

  function nodeOf(prompt, id) {
    return (prompt && prompt[String(id)]) || null;
  }

  function has(prompt, id) {
    return Boolean(nodeOf(prompt, id));
  }

  function lit(prompt, id, name) {
    var n = nodeOf(prompt, id);
    if (!n || !n.inputs) return undefined;
    var v = n.inputs[name];
    if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") return v;
    return undefined;
  }

  function firstStringInput(prompt, id) {
    var n = nodeOf(prompt, id);
    if (!n || !n.inputs) return undefined;
    var keys = Object.keys(n.inputs);
    for (var i = 0; i < keys.length; i++) {
      var v = n.inputs[keys[i]];
      if (typeof v === "string") return v;
    }
    return undefined;
  }

  function findPromptNodeByClass(prompt, classType) {
    if (!prompt) return null;
    var keys = Object.keys(prompt);
    for (var i = 0; i < keys.length; i++) {
      var n = prompt[keys[i]];
      if (n && n.class_type === classType) return n;
    }
    return null;
  }

  function hasAnyH3Node(prompt) {
    if (!prompt) return false;
    var keys = Object.keys(prompt);
    for (var i = 0; i < keys.length; i++) {
      var ct = (prompt[keys[i]] && prompt[keys[i]].class_type) || "";
      if (typeof ct === "string" && (ct.indexOf("H3") === 0 || ct.indexOf("MiniMaxH3") >= 0 || ct.indexOf("H3") === 0)) return true;
    }
    return false;
  }

  /* Read the current string value of a selector node: prefer the
   * node found by class_type, fall back to the legacy id. */
  function readSelectorValue(prompt, classType, legacyId) {
    var byClass = findPromptNodeByClass(prompt, classType);
    if (byClass && byClass.inputs) {
      var keys = Object.keys(byClass.inputs);
      for (var i = 0; i < keys.length; i++) {
        var v = byClass.inputs[keys[i]];
        if (typeof v === "string") return v;
      }
    }
    return firstStringInput(prompt, legacyId);
  }

  function linkTarget(prompt, id, name) {
    var n = nodeOf(prompt, id);
    if (!n || !n.inputs) return null;
    if (name) {
      var v = n.inputs[name];
      if (Array.isArray(v) && v.length >= 2 && typeof v[0] === "string") return v[0];
      return null;
    }
    var keys = Object.keys(n.inputs);
    var found = [];
    for (var i = 0; i < keys.length; i++) {
      var val = n.inputs[keys[i]];
      if (Array.isArray(val) && val.length >= 2 && typeof val[0] === "string") found.push(val[0]);
    }
    return found.length === 1 ? found[0] : null;
  }

  // N880.steps is fed by a link chain (880 -> 884 switch -> 882/883 constant).
  // The literal widget on N880 is ignored by ComfyUI once linked.
  function resolveSteps(prompt, schedulerId) {
    var cur = linkTarget(prompt, schedulerId, "steps");
    var path = [];
    var guard = 0;
    while (cur && guard++ < 8) {
      path.push(cur);
      var direct = lit(prompt, cur, "value");
      if (direct !== undefined) return { value: direct, path: path };
      var nxt = linkTarget(prompt, cur, null);
      if (!nxt) return { value: undefined, path: path };
      cur = nxt;
    }
    return { value: lit(prompt, schedulerId, "steps"), path: path };
  }

  function detectBranch(prompt) {
    var v = readSelectorValue(prompt, CLS.GEN_SELECTOR, ID.GEN_SELECTOR);
    if (v === undefined) return "UNKNOWN";
    var s = String(v);
    if (s.indexOf("REF2VA") >= 0) return "REF2VA";
    if (s.indexOf("FL2VA") >= 0) return "FL2VA";
    return "UNKNOWN";
  }

  function detectRoute(prompt) {
    var v = readSelectorValue(prompt, CLS.ROUTE_SELECTOR, ID.ROUTE_SELECTOR);
    if (v === undefined) return "UNKNOWN";
    var s = String(v);
    if (s.indexOf("F4") >= 0) return "F4";
    if (s.indexOf("F1") >= 0) return "F1";
    return "UNKNOWN";
  }

  /* ---------------- the gate ---------------- */

  function validateFl2vFrozenRecipe(prompt) {
    var branch = detectBranch(prompt);
    var route = detectRoute(prompt);
    var base = { branch: branch, route: route };

    if (!hasAnyH3Node(prompt)) {
      return {
        ok: true, skipped: true, reason: "NOT_H3_GRAPH -> no H3-flavored class_type in submission",
        problems: [], branch: branch, route: route
      };
    }

    if (branch === "UNKNOWN") {
      return {
        ok: false, skipped: false,
        reason: "FAIL_CLOSED: H3 graph detected but generation-mode branch is undeterminable",
        problems: [ERR_BRANCH_UNKNOWN], branch: branch, route: route
      };
    }

    var problems = [];

    if (branch === "REF2VA") {
      if (!has(prompt, ID.REF2VA_UNET)) problems.push("REF2VA: N620 (Ref2VA checkpoint authority) missing");
      var u620 = lit(prompt, ID.REF2VA_UNET, "unet_name");
      if (typeof u620 === "string" && (u620.indexOf("FL2VA") >= 0 || u620.indexOf("10Eros") >= 0)) {
        problems.push("REF2VA: N620 holds an FL2VA model (" + u620 + ")");
      }
      if (has(prompt, ID.FL2VA_UNET)) problems.push("REF2VA: N646 must be absent");
      var f = [ID.F4_LORA, ID.F4_SIGMA, ID.F1_SAGE, ID.F1_LORA];
      for (var i = 0; i < f.length; i++) {
        if (has(prompt, f[i])) problems.push("REF2VA: FL2V route node N" + f[i] + " must be absent");
      }
      return {
        ok: problems.length === 0, skipped: false, problems: problems,
        branch: branch, route: route, unet_620: u620
      };
    }

    /* FL2VA */
    var unet = lit(prompt, ID.FL2VA_UNET, "unet_name");
    if (!has(prompt, ID.FL2VA_UNET)) {
      problems.push("FL2VA: N646 (FL2VA checkpoint authority) missing");
    } else if (unet !== FL2VA_MODEL) {
      problems.push("FL2VA: N646.unet_name=" + unet + " != " + FL2VA_MODEL);
    }
    if (has(prompt, ID.REF2VA_UNET)) problems.push("FL2VA: N620 must be absent");

    /* v028_2 closeout: N880 may be absent; verify only when present. */
    if (has(prompt, ID.SCHEDULER)) {
      var sched = lit(prompt, ID.SCHEDULER, "scheduler");
      if (sched !== FROZEN_SCHEDULER) {
        problems.push("FL2VA: N880.scheduler=" + sched + " != " + FROZEN_SCHEDULER);
      }
      var rs = resolveSteps(prompt, ID.SCHEDULER);
      if (rs.value !== undefined && (!Number.isInteger(rs.value) || rs.value < 1 || rs.value > 10000)) {
        problems.push("FL2VA: steps must be an integer from 1 to 10000");
      }
    }

    if (route === "F4") {
      /* v028_2: legacy VSA node N877 was removed by closeout; verify
       * only when the node is present in the submission. */
      if (has(prompt, ID.F4_LORA)) {
        if (nodeOf(prompt, ID.F4_LORA).class_type !== "SolAttnMiniMax") problems.push("FastH3: VSA node missing");
        if (lit(prompt, ID.F4_LORA, "selection") !== "VSA (FastVideo)") problems.push("FastH3: VSA selection required");
        if (lit(prompt, ID.F4_LORA, "selection.vsa_keep_percent") !== 10) problems.push("FastH3: VSA keep must be 10 percent");
        if (lit(prompt, ID.F4_LORA, "start_percent") !== 0 || lit(prompt, ID.F4_LORA, "end_percent") !== 1 || lit(prompt, ID.F4_LORA, "min_tokens") !== 0) problems.push("FastH3: VSA must cover all steps and clip sizes");
      }
      if (has(prompt, ID.F4_SIGMA)) {
        if (lit(prompt, ID.F4_SIGMA, "shift_video") !== 12 || lit(prompt, ID.F4_SIGMA, "shift_audio") !== 3) problems.push("FastH3: SigmaShift must be 12/3");
      }
      if (has(prompt, ID.F1_SAGE)) problems.push("F4: N876 (F1 Sage) must be absent");
      if (has(prompt, ID.F1_LORA)) problems.push("F4: N879 (F1 Larry LoRA) must be absent");
    } else if (route === "F1") {
      /* v028_2: F1 chain was closed out on 2026-09-29 and replaced by
       * the V2 route (FL2VA axis). Presence-required assertion on
       * N876 removed; mutual-exclusion checks kept. */
      if (has(prompt, ID.F4_LORA)) problems.push("F1: N877 (F4 LightX2V LoRA) must be absent");
      if (has(prompt, ID.F4_SIGMA)) problems.push("F1: N878 (F4 SigmaShift) must be absent");
    }

    return {
      ok: problems.length === 0, skipped: false, problems: problems,
      branch: branch, route: route, unet_646: unet
    };
  }

  /* ---------------- graph-side value authority ---------------- */

  function graphNode(graph, id) {
    if (!graph) return null;
    if (typeof graph.getNodeById === "function") {
      try { return graph.getNodeById(Number(id)); } catch (e) { }
    }
    var nodes = graph._nodes || graph.nodes || [];
    for (var i = 0; i < nodes.length; i++) {
      if (String(nodes[i].id) === String(id)) return nodes[i];
    }
    return null;
  }

  function readWidget(graph, id, name) {
    var n = graphNode(graph, id);
    if (!n || !n.widgets) return undefined;
    if (name) {
      for (var i = 0; i < n.widgets.length; i++) {
        if (n.widgets[i].name === name) return n.widgets[i].value;
      }
    }
    return n.widgets[0] ? n.widgets[0].value : undefined;
  }

  function setWidget(graph, id, value, name) {
    var n = graphNode(graph, id);
    if (!n || !n.widgets) return false;
    var w = null;
    if (name) {
      for (var i = 0; i < n.widgets.length; i++) {
        if (n.widgets[i].name === name) { w = n.widgets[i]; break; }
      }
    }
    if (!w && name) return false;
    if (!w) w = n.widgets[0];
    if (!w) return false;
    if (w.value === value) return false;
    w.value = value;
    return true;
  }

  function setMode(graph, id, on) {
    var n = graphNode(graph, id);
    if (!n) return false;
    var target = on ? 0 : 4;
    if (n.mode === target) return false;
    n.mode = target;
    return true;
  }

  function graphBranch(graph) {
    var v = readWidget(graph, ID.GEN_SELECTOR, null);
    if (v === undefined || v === null) return "UNKNOWN";
    var s = String(v);
    if (s.indexOf("REF2VA") >= 0) return "REF2VA";
    if (s.indexOf("FL2VA") >= 0) return "FL2VA";
    return "UNKNOWN";
  }

  function graphRoute(graph) {
    var v = readWidget(graph, ID.ROUTE_SELECTOR, null);
    if (v === undefined || v === null) return "UNKNOWN";
    var s = String(v);
    if (s.indexOf("F4") >= 0) return "F4";
    if (s.indexOf("F1") >= 0) return "F1";
    return "UNKNOWN";
  }

  function applyFl2vRecipeAuthority(graph) {
    var changed = [];
    if (!graph) return { changed: changed, branch: "UNKNOWN", route: "UNKNOWN" };
    var branch = graphBranch(graph);
    var route = graphRoute(graph);

    // 1) checkpoint authority: N646 is FL2VA-only, N620 is REF2VA-only.
    //    They must never overwrite each other.
    if (branch === "FL2VA" || branch === "UNKNOWN") {
      if (setWidget(graph, ID.FL2VA_UNET, FL2VA_MODEL, "unet_name")) changed.push("646.unet_name");
    }
    var u620 = readWidget(graph, ID.REF2VA_UNET, "unet_name");
    if (typeof u620 === "string" && (u620.indexOf("FL2VA") >= 0 || u620.indexOf("10Eros") >= 0)) {
      if (setWidget(graph, ID.REF2VA_UNET, REF2VA_REPAIR_MODEL, "unet_name")) changed.push("620.unet_name");
    }

    // 2) Scheduler preset only when the node exists (v028_2 may close
    //    it out on the REF2VA backend axis); step counts belong to the
    //    user's native widgets.
    if (branch === "FL2VA") {
      if (setWidget(graph, ID.SCHEDULER, FROZEN_SCHEDULER, "scheduler")) changed.push("880.scheduler");
    }
    // Do not overwrite N880.steps or the legacy N882/N883 values.

    // 3) route node modes (same semantics as syncFl2vRoute, idempotent).
    //    Nodes absent from the current workflow are skipped by graphNode.
    var fl2v = branch === "FL2VA";
    if (setMode(graph, ID.F4_LORA, fl2v && route === "F4")) changed.push("877.mode");
    if (setMode(graph, ID.F4_SIGMA, fl2v && route === "F4")) changed.push("878.mode");
    if (setMode(graph, ID.F1_SAGE, fl2v && route === "F1")) changed.push("876.mode");
    if (setMode(graph, ID.F1_LORA, fl2v && route === "F1")) changed.push("879.mode");

    return { changed: changed, branch: branch, route: route };
  }

  /* ---------------- ComfyUI frontend wiring ---------------- */

  var GATE_FLAG = "__h3Fl2vRecipeAuthority";

  function gateResult(result) {
    var out = result && result.output ? result.output : result;
    var check;
    try {
      check = validateFl2vFrozenRecipe(out);
    } catch (e) {
      throw new Error(ERR_CHECK + (e && e.message ? e.message : e));
    }
    if (!check.ok) {
      if (typeof console !== "undefined" && console.error) console.error("[H3] FL2V frozen recipe drift", check);
      var detail = check.problems && check.problems.length ? check.problems.join("\n") : (check.reason || "");
      throw new Error(ERR_DRIFT + "\n" + detail);
    }
    return check;
  }

  function wrapGraphToPrompt() {
    var original = app.graphToPrompt;
    if (typeof original !== "function" || original[GATE_FLAG]) return original && original[GATE_FLAG] ? true : false;
    var wrapped = async function () {
      var graph = this && this.graph ? this.graph : app.graph;
      // 1) sync recipe BEFORE graphToPrompt (value authority)
      try {
        applyFl2vRecipeAuthority(graph);
      } catch (e) {
        if (typeof console !== "undefined" && console.error) console.error("[H3] FL2V recipe authority sync failed", e);
      }
      // 2) graphToPrompt
      var result = await original.apply(this, arguments);
      // 3) validate the REAL api prompt, fail-closed
      gateResult(result);
      return result;
    };
    wrapped[GATE_FLAG] = true;
    app.graphToPrompt = wrapped;
    return true;
  }

  function wrapQueuePrompt() {
    if (typeof app === "undefined" || !app) return false;
    if (typeof app.queuePrompt !== "function") return false;
    if (app.queuePrompt[GATE_FLAG]) return true;
    var originalQueue = app.queuePrompt;
    // Second, overwrite-proof gate: pre-flight validate (read-only
    // graphToPrompt) BEFORE calling the original queuePrompt once.
    // If validation throws, the submission never happens.
    var wrappedQueue = async function () {
      try {
        applyFl2vRecipeAuthority(app.graph);
        var pending = await app.graphToPrompt();
        gateResult(pending);
      } catch (e) {
        throw e;
      }
      return originalQueue.apply(this, arguments);
    };
    wrappedQueue[GATE_FLAG] = true;
    app.queuePrompt = wrappedQueue;
    return true;
  }

  function install() {
    if (typeof app === "undefined" || !app || !app.registerExtension) return false;
    app.registerExtension({
      name: "H3.FL2V.RecipeAuthority",
      setup: function () {
        // graphToPrompt may not be defined yet during setup: retry.
        var tries = 0;
        var timer = setInterval(function () {
          tries += 1;
          var done = false;
          try { done = wrapGraphToPrompt(); } catch (e) { done = false; }
          if (done || tries > 50) clearInterval(timer);
        }, 200);
        try { wrapQueuePrompt(); } catch (e) { }
      }
    });
    return true;
  }

  /* REPAIR 20260930: install() had ZERO callers anywhere in the codebase
   * (verified by grep), so the gate never armed - this was the primary
   * root cause of FAIL_CLOSED_BEFORE=INEFFECTIVE. Auto-arm now: poll for
   * a live app instance and attach both wraps directly (registerExtension
   * setup is not replayed for late-registered extensions, so we do not
   * depend on it). */
  if (typeof window !== "undefined") {
    var autoTries = 0;
    var autoTimer = setInterval(function () {
      autoTries += 1;
      var armed = false;
      try {
        if (typeof app !== "undefined" && app && app.graphToPrompt) {
          wrapGraphToPrompt();
          wrapQueuePrompt();
          armed = Boolean(app.graphToPrompt[GATE_FLAG] && app.queuePrompt && app.queuePrompt[GATE_FLAG]);
        }
      } catch (e) { armed = false; }
      if (armed || autoTries > 150) clearInterval(autoTimer);
    }, 200);
  }

  return {
    FL2VA_MODEL: FL2VA_MODEL,
    REF2VA_REPAIR_MODEL: REF2VA_REPAIR_MODEL,
    FROZEN_SCHEDULER: FROZEN_SCHEDULER,
    F4_STEPS: F4_STEPS,
    F1_STEPS: F1_STEPS,
    ID: ID,
    CLS: CLS,
    ERR_DRIFT: ERR_DRIFT,
    validateFl2vFrozenRecipe: validateFl2vFrozenRecipe,
    applyFl2vRecipeAuthority: applyFl2vRecipeAuthority,
    detectBranch: detectBranch,
    detectRoute: detectRoute,
    resolveSteps: resolveSteps,
    gateResult: gateResult,
    wrapGraphToPrompt: wrapGraphToPrompt,
    wrapQueuePrompt: wrapQueuePrompt,
    install: install
  };
});
