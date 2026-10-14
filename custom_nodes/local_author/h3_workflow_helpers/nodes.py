# -*- coding: utf-8 -*-
"""
H3 workflow helpers: optional image load + lazy first-frame branch switch.

Used by 10Eros formal workflows so:
- mode=1 only evaluates the direct first-frame branch
- mode=2 only evaluates the multi-ref / HiDream fusion branch
- last_frame can be omitted without mute/unmute or LoadImage errors
"""
from __future__ import annotations

import logging
import os
import re

import folder_paths
import node_helpers
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageOps, ImageSequence

import comfy.utils

logger = logging.getLogger("h3_workflow_helpers")

NONE_NAMES = {"", "none", "(none)", "None", "null", "NULL", "disabled"}


def _is_none_name(name) -> bool:
    if name is None:
        return True
    if not isinstance(name, str):
        return False
    return name.strip() in NONE_NAMES


def _load_rgb_image(image_name: str):
    image_path = folder_paths.get_annotated_filepath(image_name)
    img = node_helpers.pillow(Image.open, image_path)

    output_images = []
    output_masks = []
    w = h = None
    for i in ImageSequence.Iterator(img):
        i = node_helpers.pillow(ImageOps.exif_transpose, i)
        if i.mode == "I":
            i = i.point(lambda x: x * (1 / 255))
        image_rgb = i.convert("RGB")
        if len(output_images) == 0:
            w, h = image_rgb.size
        if image_rgb.size != (w, h):
            continue
        image_np = np.array(image_rgb).astype(np.float32) / 255.0
        image_t = torch.from_numpy(image_np)[None,]
        if "A" in i.getbands():
            mask = np.array(i.getchannel("A")).astype(np.float32) / 255.0
            mask = 1.0 - torch.from_numpy(mask)
        else:
            mask = torch.zeros((64, 64), dtype=torch.float32, device="cpu")
        output_images.append(image_t)
        output_masks.append(mask.unsqueeze(0))

    if not output_images:
        raise RuntimeError(f"Failed to load image: {image_name}")

    if len(output_images) > 1:
        output_image = torch.cat(output_images, dim=0)
        output_mask = torch.cat(output_masks, dim=0)
    else:
        output_image = output_images[0]
        output_mask = output_masks[0]
    return output_image, output_mask


def _pad_resize(image: torch.Tensor, width: int, height: int, upscale_method: str = "lanczos"):
    """Keep aspect ratio, letterbox/pad to exact width x height. image: [B,H,W,C]."""
    if image is None:
        return None
    width = int(width)
    height = int(height)
    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid resize target: {width}x{height}")

    _b, h, w, _c = image.shape
    if w == width and h == height:
        return image

    scale = min(width / float(w), height / float(h))
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))

    samples = image.movedim(-1, 1)
    method = upscale_method if upscale_method in (
        "nearest-exact", "bilinear", "area", "bicubic", "lanczos"
    ) else "lanczos"
    samples = comfy.utils.common_upscale(samples, new_w, new_h, method, "disabled")

    pad_w = width - new_w
    pad_h = height - new_h
    left = pad_w // 2
    right = pad_w - left
    top = pad_h // 2
    bottom = pad_h - top
    # F.pad on NCHW: (left, right, top, bottom)
    samples = F.pad(samples, (left, right, top, bottom), mode="constant", value=0.0)
    return samples.movedim(1, -1)


class LoadImageWithSwitch:
    """Legacy helper kept for compatibility."""

    @classmethod
    def INPUT_TYPES(s):
        input_dir = folder_paths.get_input_directory()
        files = [f for f in os.listdir(input_dir) if os.path.isfile(os.path.join(input_dir, f))]
        return {
            "required": {
                "image": (sorted(files), {"image_upload": True}),
            },
            "optional": {
                "enabled": ("BOOLEAN", {"default": True, "label_on": "enabled", "label_off": "disabled"}),
            },
        }

    CATEGORY = "H3/helpers"
    RETURN_TYPES = ("IMAGE", "MASK", "BOOLEAN")
    RETURN_NAMES = ("image", "mask", "enabled")
    FUNCTION = "load_image_with_switch"

    def load_image_with_switch(self, image, enabled=True):
        if not enabled or _is_none_name(image):
            return (None, None, False)
        out_img, out_mask = _load_rgb_image(image)
        return (out_img, out_mask, True)

    @classmethod
    def IS_CHANGED(s, image, enabled=True):
        if not enabled or _is_none_name(image):
            return "disabled"
        image_path = folder_paths.get_annotated_filepath(image)
        return f"{image_path}:{os.path.getmtime(image_path)}"

    @classmethod
    def VALIDATE_INPUTS(s, image, enabled=True):
        if not enabled or _is_none_name(image):
            return True
        if not folder_paths.exists_annotated_filepath(image):
            return f"Invalid image file: {image}"
        return True


class H3OptionalLoadImage:
    """Load image; empty/none selection returns None without validation error."""

    @classmethod
    def INPUT_TYPES(s):
        input_dir = folder_paths.get_input_directory()
        files = [f for f in os.listdir(input_dir) if os.path.isfile(os.path.join(input_dir, f))]
        choices = ["(none)"] + sorted(files)
        return {
            "required": {
                "image": (choices, {"image_upload": True}),
            },
        }

    CATEGORY = "H3/helpers"
    RETURN_TYPES = ("IMAGE", "MASK", "BOOLEAN")
    RETURN_NAMES = ("image", "mask", "has_image")
    FUNCTION = "load_optional"
    DESCRIPTION = "Optional image loader. Choose (none) or leave empty to skip without errors."

    def load_optional(self, image):
        if _is_none_name(image):
            return (None, None, False)
        if not folder_paths.exists_annotated_filepath(image):
            logger.warning("H3OptionalLoadImage: missing file treated as none: %s", image)
            return (None, None, False)
        out_img, out_mask = _load_rgb_image(image)
        return (out_img, out_mask, True)

    @classmethod
    def IS_CHANGED(s, image):
        if _is_none_name(image):
            return "none"
        try:
            image_path = folder_paths.get_annotated_filepath(image)
            return f"{image_path}:{os.path.getmtime(image_path)}"
        except Exception:
            return f"missing:{image}"

    @classmethod
    def VALIDATE_INPUTS(s, image):
        # Never fail the graph because an optional slot is empty/missing.
        return True


class H3OptionalImageResize:
    """Pad-resize when image present; pass None through when absent."""

    upscale_methods = ["nearest-exact", "bilinear", "area", "bicubic", "lanczos"]

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "width": ("INT", {"default": 864, "min": 16, "max": 8192, "step": 1}),
                "height": ("INT", {"default": 480, "min": 16, "max": 8192, "step": 1}),
                "upscale_method": (s.upscale_methods, {"default": "lanczos"}),
                "keep_proportion": (
                    ["stretch", "resize", "pad", "pad_edge", "pad_edge_pixel", "crop", "pillarbox_blur", "total_pixels"],
                    {"default": "pad"},
                ),
                "pad_color": ("STRING", {"default": "0, 0, 0"}),
                "crop_position": (["center", "top", "bottom", "left", "right"], {"default": "center"}),
                "divisible_by": ("INT", {"default": 32, "min": 0, "max": 512, "step": 1}),
            },
            "optional": {
                "image": ("IMAGE",),
                "mask": ("MASK",),
                "device": (["cpu", "gpu"], {"default": "cpu"}),
            },
        }

    CATEGORY = "H3/helpers"
    RETURN_TYPES = ("IMAGE", "INT", "INT", "MASK")
    RETURN_NAMES = ("IMAGE", "width", "height", "mask")
    FUNCTION = "resize"
    DESCRIPTION = "Optional pad-resize. If image is None, returns None (no work)."

    def resize(
        self,
        width,
        height,
        upscale_method="lanczos",
        keep_proportion="pad",
        pad_color="0, 0, 0",
        crop_position="center",
        divisible_by=32,
        image=None,
        mask=None,
        device="cpu",
    ):
        if image is None:
            return (None, int(width), int(height), None)

        # Force pad/letterbox behavior for identity-safe geometry.
        mode = keep_proportion if keep_proportion else "pad"
        if mode != "pad":
            # Still avoid non-uniform stretch unless explicitly stretch.
            if mode == "stretch":
                samples = image.movedim(-1, 1)
                samples = comfy.utils.common_upscale(
                    samples, int(width), int(height), upscale_method, "disabled"
                )
                out = samples.movedim(1, -1)
            else:
                out = _pad_resize(image, int(width), int(height), upscale_method)
        else:
            out = _pad_resize(image, int(width), int(height), upscale_method)

        out_mask = mask
        return (out, int(width), int(height), out_mask)


class H3LazyImageSwitch:
    """
    True lazy first-frame source switch.
    mode=1 -> only evaluate image1 (direct first frame)
    mode=2 -> only evaluate image2 (multi-ref fusion result)
    """

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "mode": (
                    "INT",
                    {
                        "default": 1,
                        "min": 1,
                        "max": 2,
                        "step": 1,
                        "tooltip": "1=单参考直接首帧；2=多参考融合首帧。只执行被选中的分支。",
                    },
                ),
            },
            "optional": {
                "image1": ("IMAGE", {"lazy": True}),
                "image2": ("IMAGE", {"lazy": True}),
            },
        }

    CATEGORY = "H3/helpers"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION = "switch"
    DESCRIPTION = "Lazy switch: mode 1 runs direct first frame only; mode 2 runs multi-ref fusion only."

    def check_lazy_status(self, mode, image1=None, image2=None):
        mode = int(mode)
        needed = []
        if mode == 1:
            if image1 is None:
                needed.append("image1")
        else:
            if image2 is None:
                needed.append("image2")
        return needed

    def switch(self, mode, image1=None, image2=None):
        mode = int(mode)
        if mode == 1:
            if image1 is None:
                raise RuntimeError("单参考模式(mode=1)：请上传「正式首帧」。")
            return (image1,)
        if image2 is None:
            raise RuntimeError(
                "多参考模式(mode=2)：多参考融合结果为空。请上传身份/参考图后重试。"
            )
        return (image2,)


class H3OperationSelector:
    """Single, explicit UI selector for the production H3 workflow stages.

    Execution routing is performed by the companion lightweight frontend
    extension, which synchronizes the selected value to the pre-tagged workflow
    nodes' bypass modes.  The returned string is intentionally optional: the
    node is a control surface, not part of the generation dependency graph.
    """

    MODES = [
        "只跑一采",
        "检测坏段",
        "放大/扩时",
        "执行二采",
        "自动检测+扩时+二采（实验）",
        "无任何选项状态",
    ]

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"当前操作": (cls.MODES, {"default": cls.MODES[0]})}}

    CATEGORY = "H3/helpers"
    RETURN_TYPES = ()
    RETURN_NAMES = ()
    FUNCTION = "select"
    DESCRIPTION = "H3 工作流唯一运行模式选择器；任意时刻只允许一个阶段启用。"

    def select(self, 当前操作):
        return ()


class H3SpeedModeSelector:
    """Third control axis: 一采生成 的画质/速度偏好（双模式正式整合 2026-09-03）。

    与 H3OperationSelector（操作阶段轴）正交：只作用于功能 1 一采生成。
    默认（原样）= 源工作流原行为；画质优先 = SLA0.85 + FP16；
    高速平衡 = Turbo8(v4) + Sage(H3) + INT8 ConvRot。
    由前端 JS 按节点 properties["h3_speed_branch"] 同步 node.mode 0/4。
    """

    MODES = ["默认（原样）", "画质优先", "高速平衡"]

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"一采模式": (cls.MODES, {"default": cls.MODES[0]})}}

    CATEGORY = "H3/helpers"
    RETURN_TYPES = ()
    RETURN_NAMES = ()
    FUNCTION = "select"
    DESCRIPTION = "一采生成模式：默认（原样）/ 画质优先（SLA0.85+FP16）/ 高速平衡（Turbo8+Sage+INT8）。仅作用于功能 1。"
    MODES_EXTRA_NOTE = "h3_speed_branch: default|quality|fast（数组允许多模式同节点，如 119 VAE=[default,quality]）"

    def select(self, 一采模式):
        return ()


class H3SizeModeSelector:
    """Serialized control surface for the real preset/custom size branches."""

    MODES = ["预设尺寸", "自定义尺寸"]

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"尺寸模式": (cls.MODES, {"default": cls.MODES[0]})}}

    CATEGORY = "H3/helpers"
    RETURN_TYPES = ()
    RETURN_NAMES = ()
    FUNCTION = "select"
    DESCRIPTION = "真正切换预设宽高与自定义宽高分支。"

    def select(self, 尺寸模式):
        return ()


class H3GenerationModeSelector:
    """Serialized selector for REF2VA versus FL2VA generation."""

    MODES = ["多参考图（REF2VA）", "文生/单图/首尾帧（FL2VA）"]
    # 本机真实存在的 FL2VA 基模（2026-09-03 资产核验）
    FL2VA_MODEL = "10Eros_Max_H3_FL2VA-NVFP4.safetensors"

    @classmethod
    def INPUT_TYPES(cls):
        available_models = set(folder_paths.get_filename_list("diffusion_models"))
        modes = cls.MODES if cls.FL2VA_MODEL in available_models else cls.MODES[:1]
        return {"required": {"生成模式": (modes, {"default": cls.MODES[0]})}}

    CATEGORY = "H3/helpers"
    RETURN_TYPES = ()
    RETURN_NAMES = ()
    FUNCTION = "select"
    DESCRIPTION = "真正切换 REF2VA/FL2VA 模型、条件和初始潜空间分支。"

    def select(self, 生成模式):
        return ()


class H3ImageModeSelector:
    """Controls which FL2VA image-conditioning inputs are evaluated."""

    MODES = ["文生视频（不用图）", "单图生视频", "首尾帧生视频"]

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"图片模式": (cls.MODES, {"default": cls.MODES[0]})}}

    CATEGORY = "H3/helpers"
    RETURN_TYPES = ()
    RETURN_NAMES = ()
    FUNCTION = "select"
    DESCRIPTION = "真正切换 FL2VA 无图、单图和首尾帧条件分支。"

    def select(self, 图片模式):
        return ()


class H3ReferenceSourceSelector:
    """Independent, serialized toggles for REF2VA reference material sources.

    REF_MASTER_CONTROL_20260906：第 5 项「后处理使用上传视频」是后处理上传
    视频链（766/767/768/769/770）的唯一总控开关，与四个 REF2VA 参考开关
    相互独立。关 = 整链 MUTE（彻底断链）；开 = 整链恢复。它只影响
    检测/扩时/二采/修复的素材来源，不影响一采。
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "启用四张参考图": ("BOOLEAN", {"default": True}),
                "启用参考视频": ("BOOLEAN", {"default": False}),
                "启用参考音频1": ("BOOLEAN", {"default": False}),
                "启用参考音频2": ("BOOLEAN", {"default": False}),
                # 第五项 = 后处理总控（置于底部，避免误开；默认 True 保持
                # 与历史行为一致：上传链当前处于启用状态）。
                "后处理使用上传视频": ("BOOLEAN", {"default": True}),
            }
        }

    CATEGORY = "H3/helpers"
    RETURN_TYPES = ()
    RETURN_NAMES = ()
    FUNCTION = "select"
    DESCRIPTION = (
        "【参考素材总控】仅作用于 REF2VA 多参考分支（MiniMaxH3ReferenceToVideo）：启用/关闭图1-4、参考视频与音频。"
        "注意：若当前生成引擎为「常规视频生成（FL2VA）/ MiniMaxH3ImageToVideo」，只使用首帧(first_frame)，"
        "图2/图3/图4 不进入生成；此时「启用四张参考图 = true」不代表四图参与，请以控制台【参考模式：单首帧】为准。"
        "第五项独立控制后处理上传视频链（仅检测/扩时/二采/修复）。"
    )

    def select(self, 启用四张参考图, 启用参考视频, 启用参考音频1, 启用参考音频2, 后处理使用上传视频):
        return ()


class H3Fl2vRouteSelector:
    """FL2V 二级路线轴：主用 F4（社区 V1 4-step 重打包）/ 快速平衡（官方 FastH3 V2 8-Step）。

    与 H3GenerationModeSelector（一级：REF2VA/FL2VA）正交，只作用于 FL2VA 分支。
    由前端 JS 按节点 properties["h3_fl2v_route_branch"] 同步 node.mode 0/4：
      - 主用 F4: f4 链（646 主模型源 / 878 SigmaShift12-3 / 880 调度 simple4 / 881 采样 euler）点亮
      - 快速平衡: v2 链（977 官方 V2 权重 / 978 SigmaShift10-3 / 979 注意力后端 /
        980 Core 原生 VSA 稀疏载体 / 981 调度 simple8 / 982 res_multistep）点亮
    两档互斥：被选档点亮，另一档整链旁路（m4）。REF2VA 模式或 FL2VA 未启用时全部旁路，
    链路透明零副作用。自动路由开关取『第一个非空输入』，故未选中档必须连源节点一起旁路。
    """

    MODES = ["主用 F4（FastH3 VSA 4步）", "快速平衡（FastH3 V2 8步）"]

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"FL2V 路线": (cls.MODES, {"default": cls.MODES[0]})}}

    CATEGORY = "H3/helpers"
    RETURN_TYPES = ()
    RETURN_NAMES = ()
    FUNCTION = "select"
    DESCRIPTION = "FL2V 路线：主用 F4＝社区 V1 4-step 重打包（SigmaShift12/3·4步·euler）/ 快速平衡＝官方 FastH3 V2 8-Step 蒸馏权重（SigmaShift10/3·8步·res_multistep·Core 原生 VSA，仅文生音视频，官方未蒸馏 FL2VA/Ref2VA）。仅 FL2VA 生效。"

    def select(self, **kwargs):
        return ()


class H3Ref2vaBackendSelector:
    """Ref2VA 二级后端轴：稳定8步 / PDD 8步（两档生产收口，2026-09-29）。

    与 H3GenerationModeSelector（一级：REF2VA/FL2VA）正交，只作用于 REF2VA 分支。
    由前端 JS 按节点 properties["h3_ref2va_backend_branch"] 同步 node.mode 0/2/4：
      - stable8 : 稳定8步链（N940 turbo→N1007→N1008→N941 6/3；N942 simple/8）点亮；
                  00029 健康路线形态（turbo_8step，208 patches），不得误接 PDD
      - pdd8    : PDD 链（N1006 Apply→N998→N950；N1006.sigmas；N943 euler）点亮；
                  MiniMaxH3PDDAccApply，8 NFE / Shift 12/3 / Euler，308 patches
      - vsa / original : 旧档（枚举已移除=生产 UI 隐藏）；分支节点保留作 rollback
    FL2VA 模式或 Ref2VA 未启用时全部旁路，链路透明零副作用。
    旧图兼容：旧值"官方…"按 PDD 档点亮（pdd8/official8 标签同组）。
    """

    MODES = ["稳定多参考8步", "PDD多参考8步", "Native Ref2VA 20步诊断"]

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"Ref2VA 后端": (cls.MODES, {"default": cls.MODES[0]})}}

    CATEGORY = "H3/helpers"
    RETURN_TYPES = ()
    RETURN_NAMES = ()
    FUNCTION = "select"
    DESCRIPTION = "Ref2VA 后端：稳定8步 / PDD8步 / Native 20步诊断。诊断档不使用加速 LoRA，仅高级手动选择。"

    def select(self, **kwargs):
        return ()


class H3Ref2vaAttentionSelector:
    """Ref2VA 官方8步二级轴：注意力方案 标准 / 内置 INT8。

    与 H3Ref2vaBackendSelector 正交，只作用于官方 Ref2VA 8步分支内部。
    前端按 h3_ref2va_attention_branch 同步节点执行模式。
    """

    MODES = ["标准", "内置 INT8"]

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"注意力方案": (cls.MODES, {"default": cls.MODES[0]})}}

    CATEGORY = "H3/helpers"
    RETURN_TYPES = ()
    RETURN_NAMES = ()
    FUNCTION = "select"
    DESCRIPTION = "官方 Ref2VA 8步注意力方案：标准（不经过 INT8 注意力）/ 内置 INT8（经过 ModelAttentionBackend）。仅官方8步后端生效。"

    def select(self, **kwargs):
        return ()


class H3MemoryOptimizationSelector:
    """PDD Ref2VA 高级开关：关闭（默认）/ 开启 H3MemoryOptimization。"""

    MODES = ["关闭", "开启"]

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"H3内存优化": (cls.MODES, {"default": cls.MODES[0]})}}

    CATEGORY = "H3/helpers"
    RETURN_TYPES = ()
    RETURN_NAMES = ()
    FUNCTION = "select"
    DESCRIPTION = "PDD Ref2VA 8步高级开关。默认关闭；开启时仅增加官方 H3MemoryOptimization MODEL patch，保留 Comfy Kitchen INT8 dense attention。"

    def select(self, **kwargs):
        return ()


class H3GuideModeSelector:
    """时间轴关键帧轴：让画面在指定时间点到达目标状态（Core 原生 MiniMaxH3AddGuide）。

    与其它轴正交，REF2VA / FL2VA 两种生成模式都可用；它控制的是
    properties["h3_guide_branch"] = 1/2/3 的关键帧链，槽位号 ≤ 所选数量的点亮，
    其余整链旁路（m4）。旁路时前端把 conditioning 直通回 N648，默认路线零副作用。

    概念边界（作者 2026-09-19 方案 §8，禁止再混淆）：
      Reference（参考图/参考视频）＝语义参考，不规定出现在第几帧；
      Guide（本轴）＝时间轴锚点，规定"第 frame_idx 帧必须是这张画面"。
    """

    MODES = ["不使用关键帧", "1 个关键帧画面", "2 个关键帧画面", "3 个关键帧画面"]

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"关键帧控制": (cls.MODES, {"default": cls.MODES[0]})}}

    CATEGORY = "H3/helpers"
    RETURN_TYPES = ()
    RETURN_NAMES = ()
    FUNCTION = "select"
    DESCRIPTION = "时间轴关键帧：让画面在指定第几帧到达你给的那张图。与参考图不同，关键帧规定出现时刻。默认不使用；开启后必须为每个关键帧选择图片，否则执行时报中文错误。"

    def select(self, **kwargs):
        return ()


class H3ContinuationSelector:
    """【接续生产】轴：V27 唯一新增能力，官方 Motion Context 的中文薄壳。

    解决的问题：长故事分段生成时"第一段结束 → 第二段重新起步 → 动作明显顿一下
    → 运动速度/姿态/声音不连续"。开启后本段不再从零起步，而是接着上一段结尾
    的运动与声音继续演（由官方 MiniMaxH3MotionContext 完成，本节点不参与算法）。

    与其它轴（尺寸 / 生成模式 / 图片模式 / 参考素材 / 一采速度 / FL2V 路线 /
    Ref2VA 后端 / 注意力方案 / 关键帧）全部正交，REF2VA 与 FL2VA 都可用。

    前端 JS 按 properties["h3_continuation_branch"] 同步官方链的执行模式：
      - 关闭（默认）：整条接续链旁路（m4 直通），画面/音频/条件都原样透传，
        执行输入与 V26 冻结基线逐项相同 ⇒ 零污染。
      - 开启：官方五节点点亮（读取上一段存档 → 接续 → 去保护区 → 存档 → 分段推进）。
    本类 RETURN_TYPES=()：不连任何线，纯 UI 事实源（thin adapter）。但
    RETURN_TYPES=() 本身并不会让它退出 /prompt——前端把任何已注册后端类都写进
    执行图（MarkdownNote 干净只因为它是纯前端节点、不是后端类）。实测确认后，
    由前端 h3_workflow_ux.js 的 stripUiOnlyNodes() 在提交前摘掉「零连线的纯 UI
    开关」，STEP 8 因此做成提交级逐字节相等，而不是"多一个无害节点"。

    概念边界（禁止再混淆）：
      Reference＝语义参考（长什么样/什么音色）；
      Guide＝时间轴锚点（第几帧必须是这张图）；
      接续生产＝上一段结尾的运动与声音状态（第几帧都不管，只管"怎么接上"）。
    """

    MODES = ["关闭（本段独立起步）", "开启（接上一段继续演）"]
    STRENGTHS = ["自动", "更强连续"]

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "接续生产": (cls.MODES, {"default": cls.MODES[0]}),
            "接续强度": (cls.STRENGTHS, {"default": cls.STRENGTHS[0]}),
        }}

    CATEGORY = "H3/helpers"
    RETURN_TYPES = ()
    RETURN_NAMES = ()
    FUNCTION = "select"
    DESCRIPTION = (
        "接续生产：用于\"同一镜头继续往下演\"。换镜头时请关闭接续，开始新的镜头段。"
        "关闭＝默认，与本功能加入前的行为完全一致。"
        "接续强度：自动（默认）/ 更强连续（连续大幅动作仍接不上时再开，更慢）。"
    )

    # 技术别名（STEP 7：这些英文概念一律不出现在用户可见标题里，只登记在此）
    TECHNICAL_ALIAS = {
        "接续生产": "h3_continuation_branch / MiniMaxH3MotionContext{Load,Save,Trim,Chain}",
        "自动": "context_length=22 (official VIDEO_RUN_GRID point)",
        "更强连续": "context_length=39 (same grid, unvalidated this round)",
        "保护区": "pinned head = span frames removed by MiniMaxH3MotionContextTrim",
        "上一段存档": "context_latent slot clip_index（Load 0=无上一段直通 / N=接第 N 段）",
        "声音接续": "audio_context_length=22 → 40Hz 网格取整为 37 步（≈22.2 帧）",
    }

    def select(self, **kwargs):
        return ()


SENTINEL_GUIDE_NAME = "__H3_GUIDE_NOT_SET__.png"


class H3GuideImageGuard:
    """任意关键帧锚定（实验）·运行保护（后端 fail-closed）。

    只做一件事：AddGuide 执行链中若关键帧图片仍是专用哨兵（未替换），
    立即 raise 中文错误；否则 IMAGE 原样透传，不修改像素。

    语义要点（依赖 ComfyUI 执行模型，勿"优化"掉）：
    - 不实现 VALIDATE_INPUTS：prompt 校验阶段仅做 combo 成员校验，
      因此 OFF 态（900 bypass → Guard 为孤儿节点）虽被序列化进 API prompt，
      但不会被实际执行，不报错 —— "关闭时完全不参与生成"成立。
    - ON 态（900 激活 → Guard 成为输出节点祖先）才会真正执行 → 哨兵即报错。
    - 不自动关闭 AddGuide、不 fallback、不自动选其它图片。
    """

    @classmethod
    def INPUT_TYPES(cls):
        input_dir = folder_paths.get_input_directory()
        try:
            files = [
                f for f in os.listdir(input_dir)
                if os.path.isfile(os.path.join(input_dir, f)) and not f.startswith(".")
            ]
        except Exception:
            files = []
        if SENTINEL_GUIDE_NAME not in files:
            files.append(SENTINEL_GUIDE_NAME)
        files.sort()
        return {
            "required": {
                "images": ("IMAGE",),
                "image_name": (files, {"default": SENTINEL_GUIDE_NAME}),
            }
        }

    CATEGORY = "H3/helpers"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("IMAGE",)
    FUNCTION = "guard"
    DESCRIPTION = (
        "任意关键帧锚定（实验）·运行保护：关键帧图片未替换（仍为专用哨兵 "
        "__H3_GUIDE_NOT_SET__.png）时立即中文报错；已设置则原样透传，"
        "不修改像素、不自动回退、不自动选择其它图片。"
    )

    def guard(self, images, image_name):
        if image_name == SENTINEL_GUIDE_NAME:
            raise RuntimeError("AddGuide 已开启，请先选择关键帧图片。")
        return (images,)


# =====================================================================
# P3F/P3F1: H3VideoPromptRole —— 视频用途 + Reference Label 一致性节点（确定性）
#
# 职责一（P3F，保持）：读取 Ref2VA 六段 base_prompt，只改写与 <Video 1>
#   有关的三处：
#   1. summary 段任务类型标签 [reference generation] <-> [video editing]
#   2. subject_definitions 段 <Video 1> subject 定义（插入或整行替换）
#   3. retention_analysis 段 <Video 1> retention 行（插入或整行替换）
#
# 职责二（P3F1 新增）：Reference Label 一致性 —— 最终 Prompt 中出现的
#   reference label 必须与 N150 实际开启的 reference 一致：
#   - picture_refs_enabled=False：删除 subject_definitions 中 <Picture N>
#     定义行、retention_analysis 中 <Picture N> retention 行；全文若仍
#     残留 <Picture N> -> 中文 fail-closed。
#   - audio1_enabled=False / audio2_enabled=False：同理删除对应 <Audio N>
#     定义与 retention 行；无法安全删除 -> 中文 fail-closed，不猜着改。
#   - 图片/音频 ON 时对应标签内容字节级保留。
#   - 三个状态输入由共享 JS mirrorReferenceState() 从 N150 自动镜像，
#     不是第二套用户开关（用户只操作 N150）。
#
# 模式：
#   动作/镜头参考  -> task type=[reference generation]，retention=weak_reference
#   直接编辑源视频 -> task type=[video editing]，retention=partially_preserved
#
# 纪律：
#   - 纯文本规则转换；不调用 LLM / 网络 / 模型 / API。
#   - 六段结构缺失 / summary 或 retention_analysis 缺失 / 出现无法确定的
#     重复 <Video 1> 定义 / <Video 1> 出现在不可修改段 -> 中文 fail-closed。
#   - 禁止重写剧情 / Shot / 台词 / detailed_description / soundscape / music。
#   - 由 properties.h3_reference_branch="video" 接受共享 JS 旁路控制。
# =====================================================================

_REF2VA_SECTION_ORDER = (
    "subject_definitions",
    "summary",
    "retention_analysis",
    "detailed_description",
    "overall_soundscape",
    "non_diegetic_music",
)

_VIDEO_USAGE_MOTION_REF = "动作/镜头参考"
_VIDEO_USAGE_SOURCE_EDIT = "直接编辑源视频"
H3_VIDEO_USAGE_OPTIONS = (_VIDEO_USAGE_MOTION_REF, _VIDEO_USAGE_SOURCE_EDIT)

_H3_VIDEO_SUMMARY_TAG = {
    _VIDEO_USAGE_MOTION_REF: "[reference generation]",
    _VIDEO_USAGE_SOURCE_EDIT: "[video editing]",
}

_H3_VIDEO_SUBJECT_DEF = {
    _VIDEO_USAGE_MOTION_REF: (
        "<Video 1>: motion-and-camera reference only. Borrow camera movement, "
        "lens motion, cuts, rhythm, timing, temporal structure, and composition "
        "relationships from <Video 1>; do not default to copying the identity, "
        "appearance, costume, or background of anything in <Video 1>. Final "
        "subject, look, and scene follow the user text and any other enabled "
        "references (pictures / audio)."
    ),
    _VIDEO_USAGE_SOURCE_EDIT: (
        "<Video 1>: source video to edit. This is the source video being edited; "
        "the output is an edited version of <Video 1>, preserving its motion, "
        "temporal structure, shots, and every part not requested to change, and "
        "modifying only the parts the user explicitly asks to change."
    ),
}

_H3_VIDEO_RETENTION_LINE = {
    _VIDEO_USAGE_MOTION_REF: (
        "<Video 1>: weak_reference - borrow motion, camera movement, cuts, rhythm, "
        "timing, temporal structure, and composition only; identity, appearance, "
        "costume, and background are not retained by default and follow the user "
        "text and other enabled references."
    ),
    _VIDEO_USAGE_SOURCE_EDIT: (
        "<Video 1>: partially_preserved - retain the source video's motion, "
        "temporal structure, shots, and all content not requested to change; "
        "modify only the parts the user explicitly asks to change."
    ),
}


class H3VideoPromptRole:
    """【视频用途】把 <Video 1> 定义为 动作/镜头参考 或 直接编辑源视频。

    确定性节点：读取 Ref2VA 六段 base_prompt，仅改写 summary 任务类型标签、
    subject_definitions 中 <Video 1> 定义、retention_analysis 中 <Video 1>
    保留行；其余段落字节级原样保留。结构无法确定时中文 fail-closed。
    不调用 LLM / 网络 / 模型 / API。
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base_prompt": ("STRING", {"multiline": True, "default": ""}),
                "video_usage": (list(H3_VIDEO_USAGE_OPTIONS), {"default": _VIDEO_USAGE_MOTION_REF}),
            },
            "optional": {
                "picture_refs_enabled": ("BOOLEAN", {"default": True}),
                "audio1_enabled": ("BOOLEAN", {"default": False}),
                "audio2_enabled": ("BOOLEAN", {"default": False}),
                # VIDEO_SWITCH_INDEPENDENT_MINIMAL_FIX_20260905：
                # 唯一事实源 = N150(H3ReferenceSourceSelector)「启用参考视频」。
                # video_refs_enabled 只允许作为该开关的内部镜像值（由共享 JS
                # mirrorReferenceState() 在加载/同步时覆写），禁止作为
                # 独立默认 True 的第二控制源（N150 视频默认 False → 此处
                # 默认同步为 False = fail-closed）。
                "video_refs_enabled": ("BOOLEAN", {"default": False}),
            },
        }

    CATEGORY = "H3/helpers"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("prompt",)
    FUNCTION = "apply"
    DESCRIPTION = (
        "视频用途二选一（动作/镜头参考 = [reference generation] + weak_reference；"
        "直接编辑源视频 = [video editing] + partially_preserved）。只改写 Ref2VA "
        "六段中与 <Video 1> 相关的内容；并保证最终 Prompt 中出现的 reference "
        "label 与 N150 实际开启的 reference 一致（图片/音频 OFF 时删除对应 "
        "<Picture N>/<Audio N> 定义与 retention 行；残留即中文 fail-closed）。"
        "不调 LLM/网络/模型/API；结构无法确定时中文报错（fail-closed）。"
        "由 h3_reference_branch=video 随参考视频开关自动启停；picture/audio/video 状态"
        "由共享 JS mirrorReferenceState() 从 N150 自动镜像，非第二套用户开关。"
        "官方 Ref2VA Guide 兼容：<Video N> 可在 summary / detailed_description "
        "引用已定义的视频参考；未启用视频却引用 <Video 1>、或 <Video N> 超出启用"
        "数量（当前仅 1 路视频）时 fail-closed。"
    )

    @staticmethod
    def _line_nl(text):
        return "\r\n" if "\r\n" in text else "\n"

    def _parse_sections(self, text):
        """返回 {段名: (header_start, body_start)}；六段必须齐全且首现顺序规范。"""
        hdr_re = re.compile(
            r"(?m)^[ \t]*(%s):[ \t]*(?:\r?\n|$)"
            % "|".join(re.escape(s) for s in _REF2VA_SECTION_ORDER)
        )
        matches = list(hdr_re.finditer(text))
        if not matches:
            raise RuntimeError(
                "H3VideoPromptRole：base_prompt 不是 Ref2VA 六段结构（找不到任何段标题），拒绝改写。"
            )
        first_of = {}
        for m in matches:
            name = m.group(1)
            if name in first_of:
                raise RuntimeError("H3VideoPromptRole：段标题「%s」重复，拒绝歧义提示词。" % name)
            if name not in first_of:
                first_of[name] = m
        missing = [s for s in _REF2VA_SECTION_ORDER if s not in first_of]
        if missing:
            raise RuntimeError(
                "H3VideoPromptRole：base_prompt 缺少段「%s」，不是完整 Ref2VA 六段结构，拒绝改写。"
                % "、".join(missing)
            )
        # 六段标题首现位置必须严格递增（否则段落内部出现疑似标题 -> 无法确定边界）
        pos = [first_of[s].start() for s in _REF2VA_SECTION_ORDER]
        if any(pos[i] >= pos[i + 1] for i in range(len(pos) - 1)):
            raise RuntimeError(
                "H3VideoPromptRole：六段标题顺序异常（段内有疑似重复标题），无法确定段落边界，拒绝改写。"
            )
        spans = {}
        for s in _REF2VA_SECTION_ORDER:
            m = first_of[s]
            spans[s] = (m.start(), m.end())  # header line 起止
        return spans

    def _first_video1_def_line(self, body):
        """body 内以行首 <Video 1> 开头的定义行（绝对区间列表）。"""
        out = []
        re_line = re.compile(r"(?m)^[ \t]*<Video 1>[^\r\n]*")
        for m in re_line.finditer(body):
            out.append((m.start(), m.end()))
        return out

    def _apply_summary_tag(self, text, usage):
        spans = self._parse_sections(text)
        s = spans["summary"][1]  # summary header 行结束（body 起点）
        e = spans["detailed_description"][0] if "detailed_description" in spans else len(text)
        body = text[s:e]
        target = _H3_VIDEO_SUMMARY_TAG[usage]
        m = re.match(r"[ \t\r\n]*(\[(?:reference generation|video editing)\])", body)
        if not m:
            raise RuntimeError(
                "H3VideoPromptRole：summary 段缺少 [reference generation] 或 [video editing]"
                " 任务类型标签，无法确定视频用途，拒绝改写。"
            )
        old_tag = m.group(1)
        if old_tag == target:
            return text
        a = s + m.start(1)
        b = s + m.end(1)
        return text[:a] + target + text[b:]

    def _apply_subject_video1(self, text, usage):
        spans = self._parse_sections(text)
        nl = self._line_nl(text)
        s = spans["subject_definitions"][1]
        e = spans["summary"][0] if "summary" in spans else len(text)
        body = text[s:e]
        def_line = _H3_VIDEO_SUBJECT_DEF[usage]
        defs = self._first_video1_def_line(body)
        if len(defs) > 1:
            raise RuntimeError(
                "H3VideoPromptRole：subject_definitions 段出现多处 <Video 1> 定义，"
                "无法确定唯一语义，拒绝改写。"
            )
        if len(defs) == 1:
            a, b = s + defs[0][0], s + defs[0][1]
            return text[:a] + def_line + text[b:]
        if "<Video 1>" in body:
            raise RuntimeError(
                "H3VideoPromptRole：subject_definitions 段出现行内 <Video 1> 提及但无"
                "独立定义行，无法确定 <Video 1> 语义，拒绝改写。"
            )
        # 无定义 -> 在段首（标题行后）插入
        insert_at = s
        return text[:insert_at] + def_line + nl + text[insert_at:]

    def _apply_retention_video1(self, text, usage):
        spans = self._parse_sections(text)
        nl = self._line_nl(text)
        s = spans["retention_analysis"][1]
        e = spans["detailed_description"][0] if "detailed_description" in spans else len(text)
        body = text[s:e]
        ret_line = _H3_VIDEO_RETENTION_LINE[usage]
        defs = self._first_video1_def_line(body)
        if len(defs) > 1:
            raise RuntimeError(
                "H3VideoPromptRole：retention_analysis 段出现多处 <Video 1> 保留行，"
                "无法确定唯一语义，拒绝改写。"
            )
        if len(defs) == 1:
            a, b = s + defs[0][0], s + defs[0][1]
            return text[:a] + ret_line + text[b:]
        if "<Video 1>" in body:
            raise RuntimeError(
                "H3VideoPromptRole：retention_analysis 段出现行内 <Video 1> 提及但无"
                "独立保留行，无法确定 <Video 1> 语义，拒绝改写。"
            )
        insert_at = s
        return text[:insert_at] + ret_line + nl + text[insert_at:]

    def _strip_disabled_reference_lines(self, text, picture_on, audio1_on, audio2_on):
        """Reference Label 一致性：删除 subject_definitions / retention_analysis
        段中与「已关闭 reference」绑定的行。

        - picture OFF：删除含 <Picture N> 的整行（定义行 / retention 行），并删除
          retention_analysis 内紧随图片 retention 的无标签图片收尾句
          （"The four pictures are independent; ..." 句式，视为图片 retention
          组成部分）。图片 ON 时 Picture 1-4 字节级保留。
        - audio1/audio2 OFF：删除含 <Audio 1> / <Audio 2> 的整行。
        - 一行同时含禁用标签与启用标签（<Video N> / 开启中的其它参考）时，
          无法安全整行删除 -> 中文 fail-closed，不猜着改用户内容。
        - 删除后全文任何段若仍残留已关闭标签 -> 中文 fail-closed。
        只操作 subject_definitions / retention_analysis；detailed_description /
        summary / soundscape / music 等其它段绝不重写。
        """
        if picture_on and audio1_on and audio2_on:
            return text

        tag_re = re.compile(r"<\s*(?:Picture|Audio|Video)\s*\d+\s*>", re.IGNORECASE)

        def tag_family(tag):
            m = re.match(r"<\s*(Picture|Audio|Video)\s*(\d+)\s*>", tag, re.IGNORECASE)
            if not m:
                return None
            return m.group(1).lower(), int(m.group(2))

        def tag_disabled(fam):
            kind, num = fam
            if kind == "picture":
                return not picture_on
            if kind == "audio":
                return (num == 1 and not audio1_on) or (num == 2 and not audio2_on)
            return False  # Video 恒启用（N915 仅视频 ON 时激活）

        def tag_enabled(fam):
            kind, num = fam
            if kind == "picture":
                return picture_on
            if kind == "audio":
                return (num == 1 and audio1_on) or (num == 2 and audio2_on)
            return True  # Video

        # 逐行重建文本；只处理 subject_definitions / retention_analysis 两段的 body。
        lines = text.splitlines(keepends=True)
        out_lines = []
        current = None
        for raw in lines:
            stripped = raw.strip()
            is_header = False
            if stripped:
                for name in _REF2VA_SECTION_ORDER:
                    if re.match(r"^%s:[ \t]*$" % re.escape(name), stripped):
                        current = name
                        is_header = True
                        break
            in_editable = current in ("subject_definitions", "retention_analysis")
            if is_header or not in_editable:
                out_lines.append(raw)
                continue
            content = raw[:-1] if raw.endswith("\n") else raw
            if content.endswith("\r"):
                content = content[:-1]
            tags = tag_re.findall(content)
            if not tags:
                out_lines.append(raw)
                continue
            fams = [tag_family(t) for t in tags]
            has_disabled = any(tag_disabled(f) for f in fams)
            if not has_disabled:
                out_lines.append(raw)
                continue
            if any(tag_enabled(f) for f in fams):
                raise RuntimeError(
                    "H3VideoPromptRole：同一行同时引用已启用与已关闭的 reference"
                    "（%s），无法安全整行删除，拒绝改写。请手动整理该行。"
                    % " ".join(sorted(set(tags)))
                )
            # 整行删除
            continue
        text = "".join(out_lines)

        # retention_analysis 图片收尾句（图片 OFF，template 句式视为图片块组成部分）
        if not picture_on:
            spans = self._parse_sections(text)
            h = spans["retention_analysis"]
            idx = _REF2VA_SECTION_ORDER.index("retention_analysis")
            nxt = spans[_REF2VA_SECTION_ORDER[idx + 1]][0] if idx + 1 < len(_REF2VA_SECTION_ORDER) else len(text)
            seg = text[h[1]:nxt]
            kept = []
            for raw in seg.splitlines(keepends=True):
                if raw.strip() and raw.strip().lower().startswith("the four pictures are independent"):
                    continue
                kept.append(raw)
            text = text[:h[1]] + "".join(kept) + text[nxt:]

        # 折叠删行引起的连续空行（不触碰任何非空内容）
        text = re.sub(r"\n{3,}", "\n\n", text)

        # 全文残留检查：已关闭标签不得出现在任何段
        for m in tag_re.finditer(text):
            fam = tag_family(m.group(0))
            if fam and tag_disabled(fam):
                kind = fam[0]
                if kind == "picture":
                    raise RuntimeError(
                        "H3VideoPromptRole：当前提示词仍引用未启用的图片参考，请检查提示词。"
                        "（残留 %s）" % m.group(0)
                    )
                raise RuntimeError(
                    "H3VideoPromptRole：当前提示词仍引用未启用的音频参考（%s），请检查提示词。"
                    % m.group(0)
                )
        return text

    def apply(self, base_prompt, video_usage=_VIDEO_USAGE_MOTION_REF,
              picture_refs_enabled=True, audio1_enabled=False, audio2_enabled=False,
              video_refs_enabled=False):
        if not isinstance(base_prompt, str) or not base_prompt.strip():
            raise RuntimeError(
                "H3VideoPromptRole：base_prompt 为空，无法改写。请先填写 Ref2VA 六段提示词。"
            )
        if video_usage not in H3_VIDEO_USAGE_OPTIONS:
            raise RuntimeError("H3VideoPromptRole：未知视频用途，拒绝自动切换为其他用途。")
        usage = video_usage
        text = base_prompt
        spans = self._parse_sections(text)

        # ① <Video N> 索引范围校验：N 不得超过实际启用的视频参考数量
        #   （启用=1，未启用=0）。未启用视频却出现 <Video 1> → STOP；
        #   <Video 2> 及更高超出启用数量 → STOP。此规则与官方 Ref2VA Guide 一致：
        #   reference labels 在六段中保持统一含义，summary / detailed_description
        #   可引用已定义的 <Video N>，故此处只校验索引范围，不再按段封禁 <Video N>。
        _video_tag_re = re.compile(r"<\s*Video\s*(\d+)\s*>", re.IGNORECASE)
        max_video_idx = 1 if video_refs_enabled else 0
        for m in _video_tag_re.finditer(text):
            idx = int(m.group(1))
            if idx < 1 or idx > max_video_idx:
                if not video_refs_enabled:
                    raise RuntimeError(
                        "H3VideoPromptRole：未启用视频参考，但提示词仍引用 %s，拒绝改写。"
                        % m.group(0)
                    )
                raise RuntimeError(
                    "H3VideoPromptRole：提示词引用 %s，超出实际启用的视频参考数量（1），"
                    "拒绝改写。" % m.group(0)
                )

        # ② 音频段（overall_soundscape / non_diegetic_music）仍不接受 <Video N>
        #   引用（视频参考标签只授权出现在 subject_definitions / retention_analysis /
        #   summary / detailed_description 四段）。
        frozen = [
            "overall_soundscape", "non_diegetic_music",
        ]
        for name in frozen:
            h = spans[name]
            nxt = len(text)
            # 用六段顺序找下一段 header 起点
            idx = _REF2VA_SECTION_ORDER.index(name)
            if idx + 1 < len(_REF2VA_SECTION_ORDER):
                nxt = spans[_REF2VA_SECTION_ORDER[idx + 1]][0]
            seg = text[h[1]:nxt]
            if _video_tag_re.search(seg):
                raise RuntimeError(
                    "H3VideoPromptRole：<Video> 出现在不允许引用的「%s」段内，无法确定语义，拒绝改写。"
                    % name
                )
        if not video_refs_enabled:
            return (self._strip_disabled_reference_lines(
                text, bool(picture_refs_enabled), bool(audio1_enabled), bool(audio2_enabled)
            ),)
        out = self._apply_summary_tag(text, usage)
        out = self._apply_subject_video1(out, usage)
        out = self._apply_retention_video1(out, usage)
        out = self._strip_disabled_reference_lines(
            out,
            picture_on=bool(picture_refs_enabled),
            audio1_on=bool(audio1_enabled),
            audio2_on=bool(audio2_enabled),
        )
        return (out,)


NODE_CLASS_MAPPINGS = {
    "LoadImageWithSwitch": LoadImageWithSwitch,
    "H3OptionalLoadImage": H3OptionalLoadImage,
    "H3OptionalImageResize": H3OptionalImageResize,
    "H3LazyImageSwitch": H3LazyImageSwitch,
    "H3OperationSelector": H3OperationSelector,
    "H3SpeedModeSelector": H3SpeedModeSelector,
    "H3SizeModeSelector": H3SizeModeSelector,
    "H3GenerationModeSelector": H3GenerationModeSelector,
    "H3ImageModeSelector": H3ImageModeSelector,
    "H3ReferenceSourceSelector": H3ReferenceSourceSelector,
    "H3Fl2vRouteSelector": H3Fl2vRouteSelector,
    "H3Ref2vaBackendSelector": H3Ref2vaBackendSelector,
    "H3Ref2vaAttentionSelector": H3Ref2vaAttentionSelector,
    "H3MemoryOptimizationSelector": H3MemoryOptimizationSelector,
    "H3GuideModeSelector": H3GuideModeSelector,
    "H3GuideImageGuard": H3GuideImageGuard,
    "H3ContinuationSelector": H3ContinuationSelector,
    "H3VideoPromptRole": H3VideoPromptRole,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LoadImageWithSwitch": "H3 带开关图像载入",
    "H3OptionalLoadImage": "H3 可选图像载入",
    "H3OptionalImageResize": "H3 可选图像缩放（补边）",
    "H3LazyImageSwitch": "H3 懒切换图像源（1单参考/2多参考）",
    "H3OperationSelector": "H3 当前操作（真正单选）",
    "H3SpeedModeSelector": "H3 一采模式（画质优先/高速平衡，真切换）",
    "H3SizeModeSelector": "H3 尺寸模式（真切换）",
    "H3GenerationModeSelector": "H3 生成模式（真切换）",
    "H3ImageModeSelector": "H3 图片模式（真切换）",
    "H3ReferenceSourceSelector": "H3 参考素材（真开关）",
    "H3Fl2vRouteSelector": "H3 FL2V 路线（主用 F4 / 快速平衡 FastH3 V2，真切换）",
    "H3Ref2vaBackendSelector": "H3 Ref2VA 后端（原版 / VSA，真切换）",
    "H3Ref2vaAttentionSelector": "H3 Ref2VA 注意力方案（标准 / 内置 INT8）",
    "H3MemoryOptimizationSelector": "H3 内存优化（关闭 / 开启，高级开关）",
    "H3GuideModeSelector": "H3 时间轴关键帧（不使用 / 1~3 个关键帧，真切换）",
    "H3GuideImageGuard": "H3 关键帧图片运行保护（未设置即报错）",
    "H3ContinuationSelector": "H3 接续生产（关闭 / 开启，真切换）",
    "H3VideoPromptRole": "H3 视频用途（动作/镜头参考 或 直接编辑源视频）",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
