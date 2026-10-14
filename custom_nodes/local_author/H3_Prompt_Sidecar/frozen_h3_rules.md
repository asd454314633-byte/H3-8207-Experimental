# H3 Ref2VA 冻结输出规则（官方 guide 蒸馏版）

来源：`<COMFYUI_DIR>\ComfyUI_H3_V27_Lab\custom_nodes\H3_V28_Director\skills\official-minimax-h3-prompt\references\ref-en.txt`
原文 SHA256：`1E574F356716AD55612247FFB7BBCCBCD484AD96599D63C7DCA1AF186B1FAB7`（23,553 字节 / 5,433 tokens）
本蒸馏版 SHA256：`9ABBA7A74D789E202413D3B816E9C1D021619BBD002691AEF8B71E6F383549C0`（10,814 字节 / 3,012 tokens）
蒸馏日期：2026-10-02 · 用途：Sidecar 常驻 system 前缀
实测收益：prompt 侧省 2,421 tokens（降幅 45%），使 CTX=12288 足以容纳 AUTO_CONTINUE 全长输出
原文始终只读、未被修改（可随时按上面 SHA256 复核）。

本文件是官方 guide 的**无损规则浓缩**：保留全部规范性条款（must / 不得 / 固定枚举值 / 格式契约），
删除长篇示例散文与推理过程说明。**任何与原文冲突之处以原文为准。**

---

## 1. 总体结构（六段，顺序与节名固定）

```
subject_definitions:
summary:
retention_analysis:
detailed_description:
overall_soundscape:
non_diegetic_music:
```

| 段 | 职责 |
| --- | --- |
| `subject_definitions` | 定义被引用内容及其引用标签 |
| `summary` | 任务类型 + 目标视频 + 主要引用关系 |
| `retention_analysis` | 每个被引用内容如何被保留/迁移/复用 |
| `detailed_description` | 按播放顺序写画面、动作、镜头、声音、台词 |
| `overall_soundscape` | 环境底噪与物理声 |
| `non_diegetic_music` | 只有观众能听到的配乐 |

- 六段全部用**英文**写；只有 `<d>` 内的台词/歌词与画面内可见文字保留原语言。
- `detailed_description` 必须尽可能详细具体：逐镜头写清构图、主体外貌与位置、环境与光线、
  动作与状态变化、运镜、当前声音、被引用内容实际生效/出现的位置。
  **不得降级为剧情摘要或引用关系清单。**
- 生成类任务 `detailed_description` 通常 350–500 英文词；台词密集内容优先保证完整口语时间线，
  不机械凑词数。单镜头不自动等于短描述，按信息量分配细节。

## 2. 引用标签

| 标签 | 含义 |
| --- | --- |
| `<Subject N>` | 从参考素材抽象出的、可在目标视频中复用或修改的**可见内容**（人/动物/物体/场景背景/服装道具界面/风格动作表情姿势） |
| `<Picture N>` | 作为具体首帧、关键帧、尾帧或构图锚点的参考图 |
| `<Video N>` | 提供剪辑源、续写起点或整片时序结构的参考视频 |
| `<Audio N>` | 被复制或被参考的音频信号 |

- 标签一经赋值，在六段中含义保持一致。
- `subject_definitions` 中每项独占一行，说明标签指向、引用职责与主要特征。
- 仅用于定义人物/场景/服装/风格、不会被单独分析的 `<Picture N>`/`<Video N>`，
  **不单独列行**，写进对应 `<Subject N>` 的定义里。
- 一个 `<Subject N>` 可由多个素材定义；一个素材也可定义多个 subject。
- `<Video N>`/`<Audio N>` **各自独立编号**，下标只表示同类别内的出现顺序，不编码配对关系。
  同一素材可同时是 `<Video 1>` 与 `<Audio 2>`。参考视频含声音**不等于**自动产生 `<Audio N>`。

例：
```
<Subject 1> is the young woman in <Picture 1>, with long dark hair, a blue cardigan, and a thin silver necklace.
<Subject 1> is the woman whose appearance comes from <Picture 1> and whose walking motion comes from <Video 1>.
<Picture 2> is the first frame of [Shot 1], showing a woman seated beside a café window.
<Picture 3> is a storyboard reference for [Shot 1] and [Shot 2], defining their viewpoint, subject placement, and shot order.
<Audio 1> is the voice-timbre reference for <Subject 1> (S1).
```

## 3. `summary`

- 一个简短英文段落，**以方括号任务类型前缀开头**，随后描述目标视频与引用关系。
- 可选任务类型（固定枚举）：

| 任务类型 | 何时使用 |
| --- | --- |
| `keyframe completion` | 图片作为首帧/关键帧/尾帧/编辑关键帧等具体帧锚点 |
| `reference generation` | 素材提供人物/场景/风格/动作/运镜/分镜等生成指引，但不是具体帧、也不是被剪辑或续写的源视频 |
| `video editing` | 直接修改已有源视频（编辑图片或在静帧间生成**不属于**此类） |
| `video continuation` | 新内容从已有源视频继续、延展、恢复或过渡 |
| `audio reuse` | 同一音频信号被全部或部分复用 |
| `audio reference` | 不直接复制音频，只参考其音乐风格、音色、台词或歌词内容、音效质感、节拍或连续性 |

- 多个关系用 ` + ` 连接，同一类型不重复：`[video continuation + keyframe completion]`。
- 单纯存在视频或音频**不自动**产生对应任务类型。源视频只提供运镜/剪辑/节奏时通常属
  `reference generation`；只有该视频被直接剪辑或续写时才用 `video editing` / `video continuation`。
- 剪辑源视频且原音保留 → 同时用 `audio reuse`；续写但未直接复制音频、只延续原音特征 → 用 `audio reference`。
- 本段只使用已定义的标签，**不得引入新标签**。
- 剪辑任务在本段任务前缀之后以 `The target video is an edited version of <Video 1>.` 开头。

## 4. `retention_analysis`

每个标签独占一行，含义与 `subject_definitions` 保持一致。

**可见内容**（`<Subject N>` / `<Picture N>` / `<Video N>`）固定枚举：

| 标记 | 含义 |
| --- | --- |
| `fully_preserved` | 已定义职责被完整保留 |
| `partially_preserved` | 仍被使用，但部分特征被改变或只部分保留 |
| `attribute_transfer` | 被引用特征被迁移到另一个可识别的主体 |
| `weak_reference` | 只保留风格/类别/构图/氛围上的宽泛相似 |

**音频**（`<Audio N>`）固定枚举：

| 标记 | 含义 |
| --- | --- |
| `fully_copy` | 完整源音频作为目标视频的完整最终音轨 |
| `partially_copy` | 只复制部分时间线或部分音频层，或复制后有增删替换 |
| `reference` | 不直接复制，只参考音色、节奏、音乐风格、台词内容或声音质感 |
| `weak_reference` | 只保留类别或氛围上的宽泛相似 |

```
<Subject 1> (appears in [Shot 1], [Shot 3]): fully_preserved - ...
<Picture 2> ([Shot 1] first frame): fully_preserved - ...
<Video 1> (cut and pacing structure): weak_reference - ...
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
<Audio 2>: reference - the target speaker follows <Audio 2>'s voice timbre and measured delivery without copying the original signal.
```

- 只能在 `subject_definitions` 已定义的职责范围内选择标记。
- **不得**把目标视频里新加的动作、背景或剧情事件当成引用保真度的损失。
- **本段不得写 `(Sx)`。**

## 5. `detailed_description`

### 5.1 基本格式

- 正文英文；台词、歌词、画面可见文字保留原语言。
- `[Shot 1]` 表示开场镜头，**无时间戳**；后续镜头用 `[Shot N] At MM:SS.mmm, ...` 标记切点。
- 运镜写成当前镜头内的自然英文，必要时包含运动类型、幅度与速度。
- 发声主体使用稳定 ID：`(S1)`、`(S2)`…… 台词写作 `<d>[Language] ...</d>`。
- 跨镜头对白、结尾被截断的说话、跨镜头连续音频分别使用 `<scenetrans>`、`<cutoff>` 与相应连续性描述。

### 5.2 与 T2VA 的差异

| 维度 | T2VA | Ref2VA 全参考模式 |
| --- | --- | --- |
| 主字段 | `integrated_multimodal_description` | `detailed_description` |
| 风格开场 | 写在 `[Shot 1]` 之后 | 在 `[Shot 1]` 之前用一两句英文确立 |
| 引用信息 | 不使用全参考标签 | 在首次出现处及职责生效处插入 `<Subject N>`/`<Picture N>`/`<Video N>`/`<Audio N>` |
| 音频关系 | 描述目标视频自身声音 | 在对应镜头或音频阶段引用 `<Audio N>` 并说明是复制还是参考 |

风格开场示例：
```
The target video is in a cinematic, literary music-video style with soft lighting and a slightly desaturated color palette.
[Shot 1] The scene opens in a crowded urban street...
```

### 5.3 镜头中使用引用标签

- 重要 `<Subject N>` 首次清晰出现时，在镜头实际可见范围内描述其被引用特征、画面位置与当前动作。
  后续镜头继续使用同一标签，**不重新定义标签含义**。
- 具体帧锚点用自然句式：the shot begins from `<Picture 1>` / the shot's keyframe corresponds to
  `<Picture 2>` / the shot ends on `<Picture 3>`。
- 剪辑或续写源视频时，在源状态、结构或续写关系生效处自然引用 `<Video N>`；
  在音频关系生效的镜头或语义阶段引用 `<Audio N>`。

### 5.4 发声主体、音频源与台词

- 被引用主体实际说话时，**同时保留视觉引用标签与说话人 ID**：`<Subject N> (Sx) ...`。
- 同一主体画外音保持同样写法并标记 `off-screen`。发声者不对应已定义主体时，
  用稳定的声音描述加 `(Sx)`。
- 台词格式 `<d>[Language] ...</d>`；纯语言标记保留，方括号内写语言名。
- 只有直接复用的 BGM 或完整音轨内部的口头提示、且**没有**任何具体人物/角色/旁白等独立声源
  实际发声时，用 `<Audio N>` 作可听来源，**不得**另造 `(Sx)`。
- 直接复用参考音频的对白/旁白/歌词，或输入明确要求复现时，必须在 `<d>` 内**逐字保留**
  源文本与原语言。听不清的部分写 `[unclear]`，**不得猜测或改写**。
  标点规范化为表达句子所需的基本记号（`,` `.` `?` `!`），去除重复波浪号、emoji、项目符号与装饰性标点；
  完整陈述句以 `.` 结束，疑问句以 `?`，感叹句以 `!`，然后接 `</d>`。
- **只参考音色、节奏、情绪或表达方式时，不得把参考音频的原始台词带进目标视频。**
- `(Sx)` 按目标视频中实际发声事件顺序**一次性分配**，在该发声主体每次实际发声处复用。
  `subject_definitions` 中绑定到说话人的 `<Audio N>` 复用同一 `(Sx)`，但绝不独立另行分配。

示例：
```
<Subject 2> (S1) turns toward the woman and says, <d>[English] Last summer, I went to my grandfather's house. He talked about you.</d>
```

## 6. `overall_soundscape` 与 `non_diegetic_music`

- `overall_soundscape` 汇总全片环境底噪与物理声。
  **与特定镜头同步的对白、歌唱与声音事件留在 `detailed_description`。**
- `non_diegetic_music` 描述角色听不到、只有观众能听到的配乐。有音乐时说明配器、速度与动态变化。
- 两者都无内容时写 `N/A`。
- 使用参考音频时，复制/参考关系只写在与该可听层对应的段里：
  环境音与音效属于 `overall_soundscape`，观众专属配乐属于 `non_diegetic_music`；
  同一音频同时提供两类内容时，两段各自写对应关系。
- **完整对白与歌词只写在 `detailed_description` 的 `<d>` 内，不得在这两段重复。**
