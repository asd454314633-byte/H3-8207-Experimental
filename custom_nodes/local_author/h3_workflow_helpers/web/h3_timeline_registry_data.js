/**
 * GENERATED PUBLIC COPY — original generator output; reference fields sanitized structurally for distribution.
 * Source: original timeline registry; original hash records are kept in the private audit.
 * Phase-1 实验扩展（TLD Timeline Director）；不修改任何正式注册表/ux 逻辑。
 * 许可证：本项目自有 clean-room 实现，未复制任何外部 GPL 代码。
 */
// Original source document hash; sanitized public payload differs.
export const TLD_ROUTE_REGISTRY_SHA = "eb1ae98514c730648953780e34eaac4916c6766c97bb18a0a0391e19e3eb3cf2";
export const TLD_TIMELINE_FIXTURE_SHA = "6aa9f1f5e585ea335e6eeb3478f9842aef7fc8760481ba69719b2fff4f65be8a";
/**
 * 路线生命周期状态 → 中文显示名映射（G33 / AC-08）。
 * status 字段本身保留英文（后端固定枚举，白名单），仅前端显示层翻译。
 */
export const H3_ROUTE_STATUS_ZH = {
  "RESERVED_NOT_PHASE1": "暂未开放",
  "PHASE1_ACTIVE": "实验可用",
  "PHASE1_ACTIVE_PENDING_RUNTIME": "实验可用（运行待验）",
};
export const TLD_ROUTE_REGISTRY = {
  "registry_version": "1.2.0",
  "timeline_schema_version": "0.1.2",
  "selectability_rule": "UI 可选性由 routes[key].phase1_selectable === true 决定（fail-closed：字段缺失/非法类型 → 不可选/registry validation STOP）；生命周期 status 独立承载 Runtime Gate 进度，UI 可选不等于 Runtime PASS。",
  "single_source_of_truth": true,
  "generated_from": {
    "candidate": "【TLD Phase1实验候选】MiniMax_H3_全中文傻瓜导演台_Timeline_v011_20260905.json",
    "candidate_sha256": "422fd3cf1026778649b30e68248dbb5e0a7138892df8d48c8e5e25ef8fee4254",
    "branch_scan": "evidence/TLD_PHASE1_MINIMUM_IMPLEMENTATION_20260905/p3f1_branch_scan.json",
    "static_gate": "evidence/TLD_STATIC_GATE_V011_RETEST_20260905.txt",
    "output_contract_repair": "evidence/H3_PERMANENT_AUDIT_20260906/workflow_repair.json"
  },
  "consumption_rule": "Timeline controller / compiler / UI 只能通过 routes[key] 查询路线；禁止散落 if route==A 分支；禁止建立第二套路由真相。",
  "operation_axis_note": "h3_operation 轴（功能1..6）归 P1 FUNCTION_REGISTRY 所有；Timeline 只使用 pass1（功能1 输出 N764），不接管、不旁路操作轴。",
  "authorities": {
    "duration": {
      "DURATION_SECONDS_AUTHORITY": "N132",
      "LENGTH_FRAMES_DERIVATION": "max(5, round(a*24)) + (5 - (max(5,round(a*24)) % 17)) % 17",
      "LENGTH_NODE_CHAIN": "N132->N131->N136.length / N644.length / N638.frame_load_cap",
      "FPS_AUTHORITY": 24,
      "source": "evidence/TLD_STATIC_GATE_V011_RETEST_20260905/duration_length_authority.json"
    },
    "resolution": {
      "RESOLUTION_AUTHORITY": "N627",
      "WIDTH_HEIGHT_EFFECTIVE_SOURCE": "N627->(N115 preset | N624/N625 custom)->N626/N628->N136/N644",
      "verified_preset": {
        "aspect_ratio": "9:16 (Portrait Widescreen)",
        "megapixels": 0.6,
        "multiple": 32,
        "width": 608,
        "height": 1056
      },
      "source": "evidence/TLD_STATIC_GATE_V011_RETEST_20260905/resolution_authority.json"
    },
    "ref2va_speed": {
      "REF2VA_STEPS_AUTHORITY": "N873",
      "REF2VA_PROFILE_LOOKUP": {
        "default": 8,
        "quality": 20,
        "fast": 8
      },
      "REF2VA_MANUAL_STEPS_ALLOWED": "NO",
      "source": "evidence/TLD_STATIC_GATE_V011_RETEST_20260905/ref2va_n873_steps_authority.json"
    }
  },
  "zone_mode_to_route": {
    "REF2VA": "REF2VA",
    "FL2V-F4": "FL2V_F4",
    "FL2V-F1": "FL2V_F1"
  },
  "routes": {
    "REF2VA": {
      "route_id": "REF2VA",
      "chinese_name": "多参考图生成（Ref2VA）",
      "status": "PHASE1_ACTIVE",
      "phase1_selectable": true,
      "timeline_zone_modes": [
        "REF2VA"
      ],
      "exclusive_nodes": {
        "generation_branch_ref2va": [
          124,
          136,
          620,
          861
        ],
        "reference_images": [
          687,
          688,
          689,
          690
        ],
        "reference_video": [
          669,
          915
        ],
        "reference_audio1": [
          143
        ],
        "reference_audio2": [
          685
        ],
        "speed_default": [
          119,
          123,
          636,
          674,
          750
        ],
        "speed_quality": [
          119,
          860,
          863,
          865
        ],
        "speed_fast": [
          663,
          861,
          862,
          864,
          866
        ]
      },
      "selector_writes": [
        {
          "node_id": 647,
          "type": "H3GenerationModeSelector",
          "widget": "生成模式",
          "value": "多参考图（REF2VA）"
        }
      ],
      "binding_writes": {
        "ref_images": {
          "switch_node": 150,
          "switch_widget": "启用四张参考图",
          "file_nodes": [
            687,
            688,
            689,
            690
          ]
        },
        "ref_video": {
          "switch_node": 150,
          "switch_widget": "启用参考视频",
          "file_node": 638,
          "frozen": {
            "force_rate": 24,
            "skip_first_frames": 0,
            "select_every_nth": 1
          }
        },
        "ref_audio1": {
          "switch_node": 150,
          "switch_widget": "启用参考音频1",
          "file_node": 143
        },
        "ref_audio2": {
          "switch_node": 150,
          "switch_widget": "启用参考音频2",
          "file_node": 685
        },
        "video_usage": {
          "node": 915,
          "widget": "video_usage",
          "allowed": [
            "动作/镜头参考",
            "直接编辑源视频"
          ]
        }
      },
      "required_assets": {
        "ref_images": {
          "cardinality": 4,
          "required": false,
          "nodes": [
            687,
            688,
            689,
            690
          ]
        },
        "ref_video": {
          "required": false,
          "node": 638,
          "chain": "N638->N669->N136.ref_video_0"
        },
        "ref_audio1": {
          "required": false,
          "node": 143
        },
        "ref_audio2": {
          "required": false,
          "node": 685
        }
      },
      "required_models": [
        {
          "node_id": 620,
          "type": "UNETLoader",
          "role": "Ref2VA INT8 convrot 一采主模型"
        }
      ],
      "required_loras": [
        {
          "node_id": 674,
          "role": "Turbo LoRA FL2V v1（默认档加速，速度分支 exclusive）"
        }
      ],
      "required_vae": [
        {
          "node_id": 119,
          "role": "H3 视频 VAE FP16（默认/画质档共用）"
        },
        {
          "node_id": 862,
          "role": "H3 视频 VAE INT8（高速档专用）"
        }
      ],
      "default_runtime_profile": {
        "ref2va_speed_mode": "默认（原样）",
        "ref2va_steps": 8,
        "size_mode": "预设尺寸",
        "duration_seconds": 3,
        "fps": 24
      },
      "size_authority": "N627",
      "duration_authority": "N132->N131",
      "speed_authority": "N873->N871->N124.steps",
      "prompt_role": {
        "schema": "ref2va-6",
        "text_node": 138,
        "chain": "N138->N915(视频用途+ref镜像)->N136.prompt",
        "sections": [
          "subject_definitions",
          "summary",
          "retention_analysis",
          "detailed_description",
          "overall_soundscape",
          "non_diegetic_music"
        ]
      },
      "anchor_supported": false,
      "audio_supported": true,
      "output_node": 764,
      "fail_closed_rules": [
        "缺任一启用素材声明文件 -> STOP",
        "ref_video.enabled=true 时 force_rate!=24 / skip_first_frames!=0 / select_every_nth!=1 -> STOP",
        "ref2va_steps 只能由 N873 派生；任何独立 steps 输入 -> STOP",
        "anchor.supported=false 时 anchor.enabled=true -> STOP",
        "<Video 1> 只允许出现在 subject_definitions / retention_analysis",
        "无 fallback：缺 Ref2VA 依赖时禁止换任何其他路线/模型"
      ]
    },
    "FL2V_F4": {
      "route_id": "FL2V_F4",
      "chinese_name": "首尾帧生视频（FL2V 主用 F4 · LightX2V 4步）",
      "status": "PHASE1_ACTIVE",
      "phase1_selectable": true,
      "timeline_zone_modes": [
        "FL2V-F4"
      ],
      "exclusive_nodes": {
        "generation_branch_fl2va": [
          644,
          646,
          880,
          881,
          914
        ],
        "fl2v_route_f4": [
          877,
          878,
          882
        ],
        "image_mode_first": [
          656,
          874
        ],
        "image_mode_last": [
          666,
          875
        ],
        "addguide_conditional": [
          900,
          901,
          902,
          903
        ]
      },
      "selector_writes": [
        {
          "node_id": 647,
          "type": "H3GenerationModeSelector",
          "widget": "生成模式",
          "value": "文生/单图/首尾帧（FL2VA）"
        },
        {
          "node_id": 886,
          "type": "H3Fl2vRouteSelector",
          "widget": "FL2V 路线",
          "value": "主用 F4（LightX2V 4步）"
        },
        {
          "node_id": 761,
          "type": "H3ImageModeSelector",
          "widget": "图片模式",
          "value": "首尾帧生视频"
        }
      ],
      "binding_writes": {
        "fl2v_frames": {
          "first_node": 874,
          "last_node": 875,
          "required": false
        },
        "anchor_image": {
          "node": 902,
          "guard_node": 903,
          "sentinel": "__H3_GUIDE_NOT_SET__.png"
        }
      },
      "required_assets": {
        "first_frame": {
          "required": false,
          "node": 874
        },
        "last_frame": {
          "required": false,
          "node": 875
        },
        "anchor_image": {
          "required": false,
          "node": 902,
          "only_when": "anchor.enabled=true"
        }
      },
      "required_models": [
        {
          "node_id": 646,
          "type": "UNETLoader",
          "role": "FL2VA 一采主模型"
        }
      ],
      "required_loras": [
        {
          "node_id": 877,
          "role": "LightX2V Turbo 4step v1.1 LoRA（仅 F4）"
        }
      ],
      "required_vae": [
        {
          "node_id": 872,
          "role": "AddGuide VAE（N872->N900.vae）"
        }
      ],
      "default_runtime_profile": {
        "fl2v_route": "F4",
        "fl2v_steps": 4,
        "scheduler": "simple",
        "sampler": "euler",
        "sigma_shift": "video6/audio3",
        "size_mode": "预设尺寸",
        "duration_seconds": 3,
        "fps": 24
      },
      "size_authority": "N627",
      "duration_authority": "N132->N131",
      "speed_authority": "N882(4)->N884->N880.steps（冻结配方，无档位）",
      "prompt_role": {
        "schema": "fl2v-3",
        "text_node": 914,
        "chain": "N914->N644.prompt",
        "sections": [
          "integrated_multimodal_description",
          "overall_soundscape",
          "non_diegetic_music"
        ]
      },
      "anchor_supported": true,
      "audio_supported": false,
      "output_node": 764,
      "fail_closed_rules": [
        "first/last 帧为可选（模型层 optional，G18/R05）：不传对应帧即跳过，不再 STOP",
        "ref_images/ref_video/ref_audio1/ref_audio2 任一启用 -> STOP（V7）",
        "REPLACE_WITH_SYNTHETIC_TEST_IMAGE",
        "frame_idx 超出 [0, length-1] 或为负 -> STOP",
        "fl2v steps 冻结 4，禁止手调",
        "无 fallback：缺 F4 依赖时禁止降级 F1 或 REF2VA"
      ]
    },
    "FL2V_F1": {
      "route_id": "FL2V_F1",
      "chinese_name": "FL2V 备用 F1（v4 step600 EMA）",
      "status": "PHASE1_ACTIVE_PENDING_RUNTIME",
      "phase1_selectable": true,
      "timeline_zone_modes": [
        "FL2V-F1"
      ],
      "exclusive_nodes": {
        "generation_branch_fl2va": [
          644,
          646,
          880,
          881,
          914
        ],
        "fl2v_route_f1": [
          876,
          879,
          883
        ],
        "image_mode_first": [
          656,
          874
        ],
        "image_mode_last": [
          666,
          875
        ]
      },
      "selector_writes": [
        {
          "node_id": 647,
          "type": "H3GenerationModeSelector",
          "widget": "生成模式",
          "value": "文生/单图/首尾帧（FL2VA）"
        },
        {
          "node_id": 886,
          "type": "H3Fl2vRouteSelector",
          "widget": "FL2V 路线",
          "value": "备用 F1（v4 step600 EMA）"
        }
      ],
      "binding_writes": {
        "fl2v_frames": {
          "first_node": 874,
          "last_node": 875,
          "required": false
        }
      },
      "required_assets": {
        "first_frame": {
          "required": false,
          "node": 874
        },
        "last_frame": {
          "required": false,
          "node": 875
        }
      },
      "required_models": [
        {
          "node_id": 646,
          "type": "UNETLoader",
          "role": "FL2VA 一采主模型"
        }
      ],
      "required_loras": [
        {
          "node_id": 879,
          "role": "Larry v4 step600 EMA LoRA（仅 F1）"
        }
      ],
      "required_vae": [
        {
          "node_id": 872,
          "role": "AddGuide VAE（N872->N900.vae，F1 未验证）"
        }
      ],
      "default_runtime_profile": {
        "fl2v_route": "F1",
        "fl2v_steps": 8,
        "scheduler": "simple",
        "sampler": "euler"
      },
      "size_authority": "N627",
      "duration_authority": "N132->N131",
      "speed_authority": "N883(8)->N884->N880.steps（冻结配方，无档位）",
      "prompt_role": {
        "schema": "fl2v-3",
        "text_node": 914,
        "chain": "N914->N644.prompt",
        "sections": [
          "integrated_multimodal_description",
          "overall_soundscape",
          "non_diegetic_music"
        ]
      },
      "anchor_supported": false,
      "audio_supported": false,
      "output_node": 764,
      "fail_closed_rules": [
        "F1 仅在满足完整 F1 条件时允许进入 Phase-1 编译，否则 fail-closed（v0.1.2，取代 v0.1.1 N12 永久禁止）",
        "first/last 帧为可选（模型层 optional，G18/R05）：缺省帧按单图/文生模式处理，不再 STOP",
        "ref_images/ref_video/ref_audio1/ref_audio2 任一启用 -> STOP（V7，无 fallback）",
        "steps 冻结 N883=8，禁止 Timeline 独立覆写（F1_STEPS_MANUAL_OVERRIDE=NO）",
        "声明 F4 profile/LoRA/sigma_shift 字段 -> STOP（F1/F4 路线互斥）",
        "anchor_supported=false：anchor.enabled=true -> STOP",
        "Runtime Gate PASS 前禁止进入任何 queue/编译执行（PHASE1_ACTIVE_PENDING_RUNTIME）",
        "无 fallback：缺 F1 依赖时禁止换 F4 或 REF2VA"
      ]
    },
    "V2V": {
      "route_id": "V2V",
      "chinese_name": "视频到视频（暂未开放）",
      "status": "RESERVED_NOT_PHASE1",
      "phase1_selectable": false,
      "timeline_zone_modes": [],
      "note": "现有能力 ≈ REF2VA + video_usage=直接编辑源视频；本轮不注册执行语义、不接线、不伪装完成 Timeline 接入。",
      "exclusive_nodes": {},
      "selector_writes": [],
      "binding_writes": {},
      "required_assets": {},
      "required_models": [],
      "required_loras": [],
      "required_vae": [],
      "default_runtime_profile": {},
      "size_authority": "N627",
      "duration_authority": "N132->N131",
      "speed_authority": "N873->N871->N124.steps",
      "prompt_role": {},
      "anchor_supported": false,
      "audio_supported": false,
      "output_node": 764,
      "fail_closed_rules": [
        "任何 V2V zone mode 输入 -> STOP"
      ]
    },
    "RV2V": {
      "route_id": "RV2V",
      "chinese_name": "参考标签视频重绘（暂未开放）",
      "status": "RESERVED_NOT_PHASE1",
      "phase1_selectable": false,
      "timeline_zone_modes": [],
      "note": "现有能力保持原样；本轮不注册执行语义、不接线、不伪装完成 Timeline 接入。",
      "exclusive_nodes": {},
      "selector_writes": [],
      "binding_writes": {},
      "required_assets": {},
      "required_models": [],
      "required_loras": [],
      "required_vae": [],
      "default_runtime_profile": {},
      "size_authority": "N627",
      "duration_authority": "N132->N131",
      "speed_authority": "N873->N871->N124.steps",
      "prompt_role": {},
      "anchor_supported": false,
      "audio_supported": false,
      "output_node": 764,
      "fail_closed_rules": [
        "任何 RV2V zone mode 输入 -> STOP"
      ]
    }
  },
  "shared_nodes": {
    "description": "无任何独占分支标签的节点（含尺寸/时长/种子/输出等功能卡共享链）；Timeline 不得旁路、不得写入 mode。",
    "node_ids": [
      117,
      120,
      121,
      122,
      125,
      126,
      128,
      129,
      131,
      132,
      138,
      140,
      142,
      146,
      148,
      149,
      150,
      157,
      158,
      159,
      626,
      627,
      628,
      635,
      637,
      638,
      639,
      642,
      645,
      647,
      648,
      650,
      655,
      657,
      658,
      659,
      660,
      661,
      673,
      675,
      676,
      682,
      686,
      691,
      692,
      694,
      698,
      699,
      700,
      703,
      721,
      725,
      726,
      727,
      728,
      729,
      744,
      745,
      746,
      747,
      761,
      762,
      764,
      765,
      766,
      767,
      768,
      769,
      770,
      771,
      772,
      773,
      774,
      775,
      776,
      777,
      778,
      779,
      780,
      781,
      782,
      783,
      784,
      785,
      786,
      787,
      788,
      789,
      790,
      791,
      792,
      800,
      801,
      803,
      804,
      805,
      808,
      809,
      810,
      811,
      812,
      813,
      867,
      870,
      871,
      872,
      873,
      884,
      885,
      886,
      900,
      901,
      902,
      903,
      911,
      916
    ],
    "count": 116
  },
  "serialization_separation": {
    "runtime_write_targets": "selector_writes + binding_writes + seed/duration/size/speed 权威节点；只含 runtime_prompt / derived_before_prompt 语义字段",
    "ui_metadata_never_written": [
      "timeline_id",
      "zones[]",
      "zone_id",
      "UI 展开状态",
      "轨道颜色/显示信息",
      "retake UI 状态"
    ],
    "rule": "UI metadata 永不写入任何节点 widget/input，永不成为 conditioning 文本。"
  }
};
export const TLD_TIMELINE_FIXTURE = {
  "schema_version": "0.1.2",
  "timeline_id": "TLD_PHASE1_MINIMUM_IMPLEMENTATION_20260905",
  "engine": "H3-director-phase1",
  "zones": [
    {
      "zone_id": "Z01",
      "mode": "FL2V-F4",
      "fl2v_image_mode": "首尾帧生视频",
      "seed": 140231279990275,
      "size_mode": "预设尺寸",
      "width": 608,
      "height": 1056,
      "duration_seconds": 3,
      "length_frames": 73,
      "fps": 24,
      "binding": {
        "ref_images": {
          "enabled": false,
          "pic1": "",
          "pic2": "",
          "pic3": "",
          "pic4": ""
        },
        "ref_video": {
          "enabled": false,
          "file": "",
          "force_rate": 24,
          "frame_load_cap": 73,
          "skip_first_frames": 0,
          "select_every_nth": 1
        },
        "ref_audio1": {
          "enabled": false,
          "file": ""
        },
        "ref_audio2": {
          "enabled": false,
          "file": ""
        },
        "fl2v_frames": {
          "first_file": "REPLACE_WITH_SYNTHETIC_TEST_IMAGE",
          "last_file": "REPLACE_WITH_SYNTHETIC_TEST_IMAGE"
        }
      },
      "prompt_zone": {
        "schema": "fl2v-3",
        "text": "integrated_multimodal_description:\n[Shot 1] Transition deterministically from the declared first frame to the declared last frame.\n\noverall_soundscape:\nQuiet wind.\n\nnon_diegetic_music:\nNo music."
      },
      "anchor": {
        "supported": true,
        "enabled": true,
        "frame_idx": 36,
        "image": "REPLACE_WITH_SYNTHETIC_TEST_IMAGE"
      },
      "retake_policy": {
        "enabled": false
      }
    },
    {
      "zone_id": "Z02",
      "mode": "REF2VA",
      "video_usage": "动作/镜头参考",
      "seed": 140231279990275,
      "size_mode": "预设尺寸",
      "width": 608,
      "height": 1056,
      "duration_seconds": 3,
      "length_frames": 73,
      "fps": 24,
      "ref2va_speed_mode": "默认（原样）",
      "ref2va_steps": 8,
      "binding": {
        "ref_images": {
          "enabled": true,
          "pic1": "REPLACE_WITH_SYNTHETIC_TEST_IMAGE",
          "pic2": "REPLACE_WITH_SYNTHETIC_TEST_IMAGE",
          "pic3": "REPLACE_WITH_SYNTHETIC_TEST_IMAGE",
          "pic4": "REPLACE_WITH_SYNTHETIC_TEST_IMAGE"
        },
        "ref_video": {
          "enabled": true,
          "file": "REPLACE_WITH_SYNTHETIC_TEST_IMAGE",
          "force_rate": 24,
          "frame_load_cap": 73,
          "skip_first_frames": 0,
          "select_every_nth": 1
        },
        "ref_audio1": {
          "enabled": false,
          "file": ""
        },
        "ref_audio2": {
          "enabled": false,
          "file": ""
        },
        "fl2v_frames": {
          "first_file": "",
          "last_file": ""
        }
      },
      "prompt_zone": {
        "schema": "ref2va-6",
        "text": "subject_definitions:\n<Picture 1> is the primary person reference.\n<Picture 2> is the costume reference.\n<Picture 3> is the environment reference.\n<Picture 4> is the lighting reference.\n<Video 1> is a motion-and-camera reference only.\n\nsummary:\n[reference generation] A short cinematic motion-reference test for Timeline Zone 2.\n\nretention_analysis:\n<Picture 1>: fully_preserved - preserve the target identity.\n<Picture 2>: attribute_transfer - transfer costume attributes.\n<Picture 3>: weak_reference - borrow environment language.\n<Picture 4>: weak_reference - borrow lighting language.\n<Video 1>: weak_reference - borrow motion, camera, rhythm, timing and composition only.\n\ndetailed_description:\n[Shot 1] The target subject follows the referenced movement in a new scene.\n\noverall_soundscape:\nQuiet room tone.\n\nnon_diegetic_music:\nNo music."
      },
      "anchor": {
        "supported": false,
        "enabled": false,
        "frame_idx": null,
        "image": ""
      },
      "retake_policy": {
        "enabled": false
      }
    }
  ]
};
