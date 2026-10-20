"""确定性中英术语表（官方词汇优先）。

这是任务书 §9.2「翻译保护机制」的核心：
  * 官方镜头运动词汇（base-en.txt §4.3）必须**逐字**使用，不能交给通用 MT 自由发挥
    （实测 Argos 会把"镜头向左平移"译成 "Move camera to left"，不符合官方词汇）。
  * 方位、身体部位、动作、否定、时序等高风险语义，一律走**确定性映射**，
    不进入统计机器翻译，从根上消除 §9.3 列举的方向/否定/归属误译。

约定：术语按**中文长度降序**参与最长匹配，保证"站起"优于"站"。
"""

from __future__ import annotations

# key = 中文（简体），value = 官方英文
# 分组仅用于维护可读性，运行时统一展平为一张表并按长度降序匹配。

CAMERA_TERMS: dict[str, str] = {
    "变焦推近": "Zoom In", "变焦拉远": "Zoom Out",
    "机位推近": "Push In", "机位拉远": "Pull Out",
    "向左摇摄": "Pan Left", "向右摇摄": "Pan Right",
    "向左平移": "Truck Left", "向右平移": "Truck Right",
    "向上仰摄": "Tilt Up", "向下俯摄": "Tilt Down",
    "机位上升": "Pedestal Up", "机位下降": "Pedestal Down",
    "环绕拍摄": "Arc Shot", "跟拍": "Tracking Shot",
    "固定镜头": "Static Shot", "静止镜头": "Static Shot",
    "镜头固定不动": "Static Shot", "固定不动": "Static Shot",
    "镜头不动": "Static Shot", "静止不动": "Static Shot",
    "主观视角": "POV", "主观镜头": "POV",
    "顺时针滚转": "Roll Clockwise", "逆时针滚转": "Roll Counterclockwise",
    "推近": "Push In", "拉远": "Pull Out", "推进": "Push In",
    "左摇": "Pan Left", "右摇": "Pan Right",
    "左移": "Truck Left", "右移": "Truck Right",
    "上摇": "Tilt Up", "下摇": "Tilt Down",
    "环绕": "Arc Shot", "跟镜": "Tracking Shot",
    "晃动": "Shake Slightly",
    "小幅度": "with small amplitude", "大幅度": "with large amplitude",
    "缓慢": "at slow speed", "慢速": "at slow speed",
    "快速": "at fast speed", "迅速": "at fast speed",
}

SIDE_TERMS: dict[str, str] = {
    "画面左侧": "the left side of the frame", "画面右侧": "the right side of the frame",
    "左侧": "the left side", "右侧": "the right side",
    "左边": "the left side", "右边": "the right side",
    "左前方": "front-left", "右前方": "front-right",
    "左后方": "back-left", "右后方": "back-right",
    "前方": "ahead", "后方": "behind",
    "向前": "forward", "向后": "backward",
    "居中": "at the center of the frame",
    "前景": "the foreground", "背景": "the background",
}

BODY_TERMS: dict[str, str] = {
    "左手": "left hand", "右手": "right hand",
    "左臂": "left arm", "右臂": "right arm",
    "左腿": "left leg", "右腿": "right leg",
    "左脚": "left foot", "右脚": "right foot",
    "双手": "both hands", "双臂": "both arms",
    "面部": "face", "脸部": "face", "眼睛": "eyes",
    "嘴唇": "lips", "肩膀": "shoulders", "头部": "head",
}

ACTION_TERMS: dict[str, str] = {
    "站起": "stands up", "起身": "stands up", "站起来": "stands up",
    "坐下": "sits down", "坐回": "sits back down", "坐到": "sits down on",
    "坐在": "sits", "坐着": "sits",
    "转身": "turns around", "回头": "looks back over the shoulder",
    "面对": "faces", "背对": "turns their back to",
    "接触": "touches", "分离": "separates", "松开": "releases",
    "靠近": "moves closer to", "远离": "moves away from",
    "走向": "walks toward", "跑向": "runs toward",
    "走进": "walks into", "走出": "walks out of", "进门": "enters the room",
    "走进来": "walks in", "走进屋": "walks into the room",
    "走出来": "walks out", "离开": "leaves", "回来": "returns",
    "抬起": "raises", "放下": "lowers", "举起": "lifts up",
    "拿起": "picks up", "抓起": "grabs", "放下手": "puts down",
    "打开": "opens", "关上": "closes", "推开": "pushes open",
    "抱住": "embraces", "拥抱": "hugs", "扶起": "helps up",
    "牵手": "holds hands", "握手": "shakes hands",
    "点头": "nods", "摇头": "shakes their head",
    "微笑": "smiles", "大笑": "laughs out loud", "哭泣": "cries",
    "皱眉": "frowns", "叹气": "sighs", "眨眼": "blinks",
    "说": "says", "问": "asks", "回答": "answers", "喊": "shouts",
    "低声说": "says quietly", "大声说": "says loudly",
    "看": "looks at", "望向": "looks toward", "注视": "gazes at",
    "挥手": "waves", "鼓掌": "claps", "跳": "jumps",
    "递给": "hands over to", "接过": "takes",
    "躺下": "lies down", "跪下": "kneels down",
    "跟住": "follows", "跟": "follows",
    "停住": "stops", "停下": "stops",
    # 基础姿态/移动动词（覆盖率越高，分片后的中文碎片越少、英文越通顺）
    # 注意：不要把这些动词译成含介词的短语（如 "sits on"），否则会与紧随其后的
    # 中文方位片段（"沙发上"→"on the couch"）产生 "sits on On the couch" 的重复。
    "站在": "stands", "站着": "stands", "坐着": "sits", "躺在": "lies",
    "走在": "walks", "跑在": "runs", "趴在": "leans over",
    "看向": "looks at", "望着": "gazes at", "盯着": "stares at",
    "走去": "walks", "退回": "steps back", "后退": "steps backward",
    "向后退": "steps backward", "向前走": "walks forward",
    "接触到": "makes contact with", "碰触": "touches",
    "分开": "separates", "拉开距离": "puts distance between them",
    "第三人": "the third person", "第四人": "the fourth person",
    "第一人": "the first person", "第二人": "the second person",
    "后有": "and then", "后又": "and then", "之后再": "and then",
    "侧身": "turns sideways", "低头": "lowers their head",
    "抬头": "lifts their head", "直起身": "straightens up",
    "停下来": "stops", "转过身": "turns around",
    "捧着": "holds", "握着": "grips", "抱着": "carries in their arms",
    # 代词（长词优先匹配）。中文"他/她"不分主宾格，此处统一按**主语格**映射；
    # 编译器的指代歧义检测会提示用户改用角色姓名，角色名走受保护通道不受影响。
    "他们": "they", "她们": "they", "它们": "they",
    "他": "he", "她": "she", "它": "it",
    "两人": "the two of them", "二人": "the two of them", "双方": "both sides",
}

NEGATION_TERMS: dict[str, str] = {
    "没有动": "does not move", "不动": "does not move",
    "没有说": "does not speak", "不说话": "does not speak",
    "不回头": "does not look back", "没有回头": "does not look back",
    "不能": "cannot", "不要": "must not", "禁止": "must not",
    "不允许": "must not", "没有": "does not", "不是": "is not",
    "不": "does not",
}

SEQUENCE_TERMS: dict[str, str] = {
    "然后": "then", "接着": "next", "随后": "afterwards",
    "同时": "at the same time", "之后": "after that",
    "首先": "first", "最后": "finally", "起初": "initially",
    "一直": "continuously", "始终": "throughout",
    "先": "first", "再": "then", "又": "again",
}

SHOT_TERMS: dict[str, str] = {
    "中景": "medium shot", "近景": "close shot", "特写": "close-up",
    "全景": "wide shot", "远景": "extreme wide shot",
    "过肩镜头": "over-the-shoulder shot", "俯拍": "high-angle shot",
    "仰拍": "low-angle shot", "镜头": "the camera",
}

STYLE_TERMS: dict[str, str] = {
    "电影感": "Cinematic", "写实": "live-action", "实拍": "live-action",
    "二维动画": "2D-animated", "三维": "3D CG", "定格动画": "claymation",
    "黏土动画": "claymation", "水彩": "watercolor", "复古胶片": "vintage film",
    "动画": "animated", "黑白": "black-and-white",
}

SPEECH_TERMS: dict[str, str] = {
    "画外音": "off-screen voiceover", "旁白": "voiceover",
    "轻声": "in a quiet voice", "大声": "loudly",
    "颤抖": "with a trembling voice", "哽咽": "with a choked voice",
    "平静": "calmly", "温柔": "gently", "愤怒": "angrily",
    "开心": "happily", "悲伤": "sadly", "惊讶": "in surprise",
    "急促": "quickly", "缓慢地": "slowly", "迟疑": "hesitantly",
    "冷淡": "coldly", "兴奋": "excitedly",
}

# ---------------------------------------------------------------------------
# 场景与外观术语（任务书 §9.3：实体丢失属于必须消除的误译）
#
# 实测证据（_evidence/g3_translation/quality_probe_20261010.txt）：
#   Argos 对"深夜的便利店"整句只输出 "Late at night."，**丢掉了"便利店"这个实体**；
#   而单独翻译"便利店"→"A convenience store."、"深夜"→"Late at night" 均正确。
#   因此把高频场景/外观词纳入确定性表，避免整句 MT 吞掉实体。
#
# 注意：**只收录 ≥2 字的词**。单字中文片段会诱发 MT 幻觉（见 CHAR_TERMS 说明）。
# ---------------------------------------------------------------------------
SCENE_TERMS: dict[str, str] = {
    # 场所
    "便利店": "a convenience store", "超市": "a supermarket", "咖啡馆": "a café",
    "咖啡厅": "a café", "餐厅": "a restaurant", "酒吧": "a bar",
    "办公室": "an office", "卧室": "a bedroom", "客厅": "a living room",
    "厨房": "a kitchen", "浴室": "a bathroom", "教室": "a classroom",
    "学校": "a school", "医院": "a hospital", "医院病房": "a hospital ward",
    "病房": "a hospital ward", "走廊": "a hallway",
    "电梯": "an elevator", "楼梯": "a staircase", "天台": "a rooftop",
    "阳台": "a balcony", "公园": "a park", "街道": "a street",
    "街头": "the street", "地铁": "the subway", "公交车": "a bus",
    "车内": "inside the car", "出租车": "a taxi", "火车": "a train",
    "机场": "an airport", "车站": "a station", "海边": "the seaside",
    "沙滩": "a beach", "雪地": "a snowy field", "森林": "a forest",
    "房间": "a room", "屋子": "the room", "室内": "indoors", "室外": "outdoors",
    # 时段 / 天气 / 氛围
    "深夜": "late at night", "清晨": "early morning", "傍晚": "dusk",
    "黎明": "dawn", "正午": "noon", "雨中": "in the rain",
    "雨夜": "a rainy night", "雪夜": "a snowy night", "黄昏": "dusk",
    # 位置短语（带介词，避免与动词产生 "sits a couch" 之类错拼）
    "沙发上": "on the couch", "床上": "on the bed", "桌上": "on the table",
    "椅子上": "on the chair", "地上": "on the ground", "门口": "the doorway",
    "窗边": "by the window", "床边": "by the bed", "门外": "outside the door",
    "屋里": "inside the room", "前方": "ahead", "身后": "behind them",
    "货架": "a shelf", "柜子": "a cabinet", "镜前": "in front of a mirror",
    # 实测：以下片段若交给 MT 会稳定幻觉（"栏杆边交谈，"→"I'm not sure what I'm
    # talking about."），因此纳入确定性表，从源头消除该风险。
    "栏杆": "a railing", "栏杆边": "by the railing", "交谈": "talks with each other",
    "长椅": "a bench", "长椅上": "on the bench", "海浪": "waves", "礁石": "rocks",
    "楼梯口": "the stairway", "楼梯": "a staircase", "空旷": "open and empty",
    "并肩": "side by side", "窗边": "by the window", "床边": "by the bed",
}

APPEARANCE_TERMS: dict[str, str] = {
    # 人物类型
    "年轻女子": "a young woman", "年轻女性": "a young woman",
    "年轻男子": "a young man", "年轻男人": "a young man",
    "中年男子": "a middle-aged man", "中年女性": "a middle-aged woman",
    "老人": "an elderly person", "老年人": "an elderly person",
    "儿童": "a child", "小孩": "a child", "男孩": "a boy", "女孩": "a girl",
    "男人": "a man", "女人": "a woman", "男性": "a man", "女性": "a woman",
    # 发型 / 面部
    "长发": "long hair", "短发": "short hair", "马尾": "a ponytail",
    "卷发": "curly hair", "眼镜": "glasses", "胡子": "a beard",
    # 服装
    "西装": "a suit", "连衣裙": "a dress", "大衣": "a coat",
    "外套": "a jacket", "校服": "a school uniform", "制服": "a uniform",
    "牛仔裤": "jeans", "衬衫": "a shirt", "毛衣": "a sweater",
    "风衣": "a trench coat", "高跟鞋": "high heels", "运动鞋": "sneakers",
    "穿着": "wearing", "戴着": "wearing",
    # 年龄段（实测"二十多岁的"整段 MT 会给出 "twenty years old." 并带上句号，
    # 与后续术语片段拼在一起读起来像两句；拆成确定性词条后拼接更自然）
    "二十多岁": "in their twenties", "十几岁": "in their teens",
    "三十多岁": "in their thirties", "四十多岁": "in their forties",
    "五十多岁": "in their fifties", "二十岁左右": "around twenty",
    "三十岁左右": "around thirty", "四十岁左右": "around forty",
}

# 角色关系用的「相对位置 → 英文关系短语」（任务书 §6.2）。
# 与 SIDE_TERMS 分开：SIDE_TERMS 用于描述画面里的位置，
# 这里用于"甲相对乙"的关系句，必须自带介词（to the left **of** …）。
RELATION_POSITIONS: dict[str, str] = {
    "左侧": "to the left of", "左边": "to the left of", "左方": "to the left of",
    "右侧": "to the right of", "右边": "to the right of", "右方": "to the right of",
    "前方": "in front of", "前面": "in front of", "面前": "in front of",
    "后方": "behind", "后面": "behind", "背后": "behind", "身后": "behind",
    "旁边": "next to", "身旁": "beside", "身边": "beside",
    "对面": "opposite", "中间": "between", "正对面": "directly opposite",
}

# 关系句里可去掉的动词性前缀（"站在左侧" → "左侧"）
RELATION_PREFIXES = ("站在", "站到", "位于", "处于", "正视", "面向", "在")

# 颜色词（用于"深色大衣"这类"颜色 + 衣物"组合；
# 语序由 engine._clean 的确定性重排规则修正为英文习惯的 "a dark coat"）
COLOR_TERMS: dict[str, str] = {
    "深色": "dark", "浅色": "pale", "黑色": "black", "白色": "white",
    "红色": "red", "蓝色": "blue", "绿色": "green", "黄色": "yellow",
    "灰色": "grey", "棕色": "brown", "粉色": "pink", "紫色": "purple",
    "橙色": "orange", "银色": "silver", "金色": "golden", "米色": "beige",
}

_GROUPS = [
    CAMERA_TERMS, SIDE_TERMS, BODY_TERMS, ACTION_TERMS,
    NEGATION_TERMS, SEQUENCE_TERMS, SHOT_TERMS, STYLE_TERMS, SPEECH_TERMS,
    SCENE_TERMS, APPEARANCE_TERMS, COLOR_TERMS,
]

# 官方镜头标签 → 句中自然英文动词短语（base-en.txt §4.3 示例用法：
# "The camera pushes in with small amplitude at slow speed ..."）。
# 提示词中写自然动词，同时保证不偏离官方词汇表。
CAMERA_LABEL_TO_NATURAL: dict[str, str] = {
    "Zoom In": "zooms in",
    "Zoom Out": "zooms out",
    "Push In": "pushes in",
    "Pull Out": "pulls out",
    "Pan Left": "pans left",
    "Pan Right": "pans right",
    "Truck Left": "trucks left",
    "Truck Right": "trucks right",
    "Tilt Up": "tilts up",
    "Tilt Down": "tilts down",
    "Pedestal Up": "pedestals up",
    "Pedestal Down": "pedestals down",
    "Arc Shot": "moves in an arc around the subject",
    "Tracking Shot": "tracks the moving subject",
    "Static Shot": "holds a static shot",
    "Shake Slightly": "shakes slightly",
    "Shake Strongly": "shakes strongly",
    "POV": "shows the subject's point of view",
    "Roll Clockwise": "rolls clockwise",
    "Roll Counterclockwise": "rolls counterclockwise",
}

# 「中文 → 官方镜头标签」的独立查表（供 QA 与界面下拉使用，不受自然短语影响）
CAMERA_ZH_TO_OFFICIAL: dict[str, str] = dict(CAMERA_TERMS)

# 展平并处理重复（先出现的组优先，同词冲突时保留先定义者）
TERMS: dict[str, str] = {}
for _g in _GROUPS:
    for _k, _v in _g.items():
        if _g is CAMERA_TERMS:
            _v = CAMERA_LABEL_TO_NATURAL.get(_v, _v)
        TERMS.setdefault(_k, _v)

# 按中文长度降序 —— 最长匹配
SORTED_TERMS: list[tuple[str, str]] = sorted(
    TERMS.items(), key=lambda kv: (-len(kv[0]), kv[0])
)

# 官方镜头词汇集合（用于语义 QA 判定是否使用了官方措辞）
OFFICIAL_CAMERA_WORDS = (    "Zoom In", "Zoom Out", "Push In", "Pull Out", "Pan Left", "Pan Right",
    "Truck Left", "Truck Right", "Tilt Up", "Tilt Down", "Pedestal Up",
    "Pedestal Down", "Arc Shot", "Tracking Shot", "Static Shot",
    "Shake Slightly", "Shake Strongly", "POV",
    "Roll Clockwise", "Roll Counterclockwise",
)


# ---------------------------------------------------------------------------
# 声音/情绪术语（任务书 §7.2：每条台词可单独覆盖情绪、语气、语速、音量、停顿、呼吸）
# 这些字段在界面上是下拉选择，走**确定性**映射，不交给机器翻译。
# ---------------------------------------------------------------------------
VOICE_QUALIFIERS: dict[str, str] = {
    # 情绪
    "平静": "calmly", "温柔": "gently", "疲惫": "wearily", "愤怒": "angrily",
    "生气": "angrily", "悲伤": "sadly", "难过": "sadly", "开心": "happily",
    "高兴": "happily", "兴奋": "excitedly", "冷淡": "coldly", "惊讶": "in surprise",
    "恐惧": "fearfully", "紧张": "nervously", "无奈": "helplessly",
    "戏谑": "playfully", "认真": "seriously", "疑惑": "in confusion",
    "尴尬": "awkwardly", "深情": "affectionately", "chilling": "coldly",
    # 情绪（第二批：实测 Argos 会把"关切"译成 "Concerns"、"担忧"译成 "Fear."，
    # 属于明显误译，必须走确定性映射）
    "关切": "with concern", "担忧": "with worry", "欣喜": "joyfully",
    "失望": "with disappointment", "委屈": "with a wounded tone",
    "冷漠": "indifferently", "害羞": "shyly", "好奇": "curiously",
    "坚定": "firmly", "哀伤": "mournfully", "嘲讽": "sarcastically",
    "恳求": "pleadingly", "命令": "in a commanding tone", "释然": "with relief",
    "心疼": "with tender concern", "困惑": "in confusion", "震惊": "in shock",
    "麻木": "numbly", "苦笑": "with a bitter smile", "生气地": "angrily",
    "娇嗔": "coquettishly", "挑逗": "teasingly", "自豪": "proudly",
    "焦急": "anxiously", "迫不得已": "reluctantly",
    # 语气 / 发声方式
    "轻声": "in a quiet voice", "大声": "loudly", "低语": "in a whisper",
    "颤抖": "with a trembling voice", "哽咽": "with a choked voice",
    "沙哑": "in a raspy voice", "清亮": "in a clear voice",
    "急促": "hurriedly", "缓慢": "slowly", "迟疑": "hesitantly",
    "坚决": "firmly", "带笑": "with a smile in the voice",
    "哭腔": "in a tearful voice", "喘息": "while breathing heavily",
    "低沉": "in a low-pitched voice", "高亢": "in a high-pitched voice",
    "柔和": "in a soft voice", "浑厚": "in a deep resonant voice",
    "清亮": "in a clear voice", "沙哑": "in a raspy voice",
    "低沉的": "in a deep voice", "尖细的": "in a high-pitched voice",
    # 语速
    "很慢": "at a very slow pace", "慢": "at a slow pace",
    "中等": "at a moderate pace", "正常": "at a normal pace",
    "快": "at a fast pace", "很快": "at a very fast pace",
    # 音量
    "很轻": "at very low volume", "轻": "at low volume",
    "中": "at moderate volume", "响": "at high volume", "很响": "at very high volume",
    # 呼吸
    "平稳呼吸": "with steady breathing", "屏住呼吸": "holding their breath",
    "深吸一口气": "after a deep breath", "叹息": "with a sigh",
    # 画内 / 画外
    "画内": "onscreen", "画外": "offscreen",
}

# 环境音 / 配乐常见词（提升这两段的可读性；非强制）
AMBIENCE_TERMS: dict[str, str] = {
    "雨声": "rain", "持续雨声": "steady rain", "环境噪音": "room tone",
    "低频环境噪音": "low-frequency room tone", "街道噪音": "street noise",
    "脚步声": "footsteps", "衣服摩擦声": "fabric movement",
    "呼吸声": "breathing", "风声": "wind", "车流声": "traffic",
    "钢琴": "piano", "钢琴单音": "sparse piano notes", "弦乐": "strings",
    "大提琴": "cello", "小提琴": "violin", "吉他": "acoustic guitar",
    "低音": "low bass", "鼓点": "drums", "电子音": "electronic tones",
    "缓慢的": "slow", "渐弱": "gradually fading", "渐强": "gradually swelling",
    # 混响 / 空间感（实测"低混响"整段 MT 会给出 "low"，丢掉混响语义）
    "混响": "reverb", "低混响": "low reverb", "高混响": "high reverb",
    "环境声": "room tone", "现场感": "a live feel", "空旷感": "an open feel",
    "偏冷": "on the cold side", "偏暖": "on the warm side",
    "安静": "quiet", "嘈杂": "noisy", "回声": "echo",
}

for _k, _v in AMBIENCE_TERMS.items():
    TERMS.setdefault(_k, _v)
SORTED_TERMS = sorted(TERMS.items(), key=lambda kv: (-len(kv[0]), kv[0]))


# ---------------------------------------------------------------------------
# 单字专用表（CHAR_TERMS）
#
# **只在不参与"最长匹配"的分片回退路径中、且该片段已是**孤立单字**时才查此表。**
# 绝不把单字放进 TERMS，否则会误伤含该字的常用词（如"现在"里的"在"）。
#
# 为什么必须单独处理单字（实测证据 _evidence/g3_translation/quality_probe_20261010.txt）：
#   Argos 对孤立单字的输出是**幻觉**，而非翻译：
#     的→"Yes."  了→"Yeah."  在→"Yes."  把→"Put"  跟→"Call."
#     对→"Yeah." 到→"Present." 给→"Here." 之→"Shit."  着→"Here."  过→"Pass."
#   而 ≥2 字的词/短语翻译可靠（门口→"The door."、便利店→"A convenience store."）。
#   因此：孤立单字一律走本表确定性映射；本表未收录的单字**丢弃并计数**，
#   而不是送 MT 产生幻觉（丢弃量在 provider_status().stats.dropped_chars 中可见）。
# ---------------------------------------------------------------------------
CHAR_TERMS: dict[str, str] = {
    # 结构助词 / 时态助词：英文无对应词，丢弃是最安全的确定性处理
    "的": "", "地": "", "得": "", "了": "", "着": "", "过": "",
    "之": "", "而": "and", "以": "with", "所": "",
    # 介词
    "在": "at", "从": "from", "到": "to", "向": "toward", "朝": "toward",
    "往": "toward", "对": "toward", "给": "to", "被": "by", "为": "for",
    "用": "with", "把": "takes", "将": "takes", "自": "from",
    # 连词 / 副词
    "和": "and", "与": "and", "跟": "with", "同": "with", "及": "and",
    "也": "also", "都": "both", "还": "still", "就": "", "才": "only then",
    "很": "very", "太": "too", "更": "more", "最": "most", "没": "does not",
    # 单字名词（高频）
    "伞": "umbrella", "门": "the door", "窗": "the window", "灯": "the lamp",
    "杯": "the cup", "茶": "tea", "酒": "wine", "烟": "a cigarette",
    "包": "the bag", "书": "the book", "信": "the letter", "花": "the flower",
    "水": "water", "手": "hand", "脸": "face", "头": "head", "眼": "eye",
    "泪": "tears", "血": "blood", "雨": "rain", "雪": "snow", "风": "wind",
    "车": "the car", "路": "the road", "墙": "the wall", "桌": "the table",
    "床": "the bed", "椅": "the chair", "田": "the field", "天": "the sky",
}