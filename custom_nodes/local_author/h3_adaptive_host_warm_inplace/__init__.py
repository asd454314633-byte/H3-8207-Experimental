"""Same official class, same schema/cache; execute-entry H3 release only."""
import functools,inspect,json,logging,math,os,sys,time
from pathlib import Path
import nodes
import comfy.model_management as mm
Official=nodes.NODE_CLASS_MAPPINGS['MiniMaxH3ReferenceToVideo']
if Path(inspect.getfile(Official)).resolve()!=Path(__file__).resolve().parents[2].joinpath('comfy_extras/nodes_minimax_h3.py').resolve() or Official.__name__!='MiniMaxH3ReferenceToVideo':
    raise RuntimeError('Registered Node136 is not the official source class')
from comfy_execution.utils import get_executing_context
FOLDER=Path(__file__).resolve().parents[2]/'user'/'h3_adaptive_host_warm_inplace'
ACTIVE={}
NODE_CLASS_MAPPINGS={}

# Identity is independent of current GPU/pinned/HostBuffer residency.
H3_VARIANT_CONTRACTS = {'INT8_CONVROT': {'checkpoint': 'minimax_h3_ref2va_pruned_int8_convrot.safetensors', 'sha256': '9255F52B6677845AD238F20DFAAFA94727053694127AB7F255C048F0F9365779', 'file_size': 20970379616, 'quant_format': 'int8_tensorwise', 'weights': {'blocks.0.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.0.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.0.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.0.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.1.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.1.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.1.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.1.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.10.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.10.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.10.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.10.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.11.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.11.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.11.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.11.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.12.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.12.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.12.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.12.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.13.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.13.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.13.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.13.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.14.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.14.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.14.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.14.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.15.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.15.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.15.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.15.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.16.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.16.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.16.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.16.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.17.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.17.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.17.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.17.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.18.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.18.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.18.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.18.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.19.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.19.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.19.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.19.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.2.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.2.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.2.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.2.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.20.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.20.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.20.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.20.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.21.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.21.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.21.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.21.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.22.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.22.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.22.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.22.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.23.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.23.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.23.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.23.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.24.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.24.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.24.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.24.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.25.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.25.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.25.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.25.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.26.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.26.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.26.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.26.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.27.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.27.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.27.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.27.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.28.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.28.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.28.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.28.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.29.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.29.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.29.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.29.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.3.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.3.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.3.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.3.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.30.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.30.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.30.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.30.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.31.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.31.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.31.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.31.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.32.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.32.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.32.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.32.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.33.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.33.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.33.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.33.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.34.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.34.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.34.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.34.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.35.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.35.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.35.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.35.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.36.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.36.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.36.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.36.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.37.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.37.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.37.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.37.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.38.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.38.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.38.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.38.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.39.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.39.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.39.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.39.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.4.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.4.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.4.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.4.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.40.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.40.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.40.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.40.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.41.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.41.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.41.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.41.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.42.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.42.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.42.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.42.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.43.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.43.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.43.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.43.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.44.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.44.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.44.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.44.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.45.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.45.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.45.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.45.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.46.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.46.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.46.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.46.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.47.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.47.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.47.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.47.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.48.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.48.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.48.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.48.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.49.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.49.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.49.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.49.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.5.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.5.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.5.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.5.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.6.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.6.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.6.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.6.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.7.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.7.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.7.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.7.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.8.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.8.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.8.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.8.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}, 'blocks.9.attn.out_proj': {'shape': [5376, 7168], 'bytes': 38535168}, 'blocks.9.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 115605504}, 'blocks.9.mlp.fc1': {'shape': [28672, 5376], 'bytes': 154140672}, 'blocks.9.mlp.fc2': {'shape': [5376, 14336], 'bytes': 77070336}}, 'signatures': {'video_patch_proj': [5376, 96], 'audio_patch_proj': [5376, 32], 'condition_proj': [5376, 5120]}, 'memory_min_bytes': 20955293488, 'memory_max_bytes': 22643002976, 'header_sha256': 'c1a65ff59085cbed8a6ea7c935ae7e58b1d2f870239df54c58a68fb7989e1cd8', 'range_basis': 'Packed quant weight bytes + nonquant tensors at permitted BF16/FP32 widths; quant metadata/scales excluded from lower bound. No residency threshold.'}, 'NVFP4': {'checkpoint': 'minimax_h3_ref2va_pruned_nvfp4.safetensors', 'sha256': '8EEA02F43902E69904990C4405968D01A13C6656AA392D37AB80331E79B5DF2F', 'file_size': 12528636800, 'quant_format': 'nvfp4', 'weights': {'blocks.0.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.0.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.0.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.0.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.1.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.1.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.1.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.1.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.10.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.10.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.10.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.10.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.11.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.11.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.11.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.11.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.12.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.12.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.12.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.12.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.13.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.13.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.13.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.13.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.14.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.14.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.14.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.14.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.15.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.15.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.15.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.15.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.16.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.16.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.16.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.16.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.17.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.17.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.17.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.17.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.18.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.18.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.18.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.18.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.19.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.19.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.19.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.19.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.2.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.2.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.2.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.2.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.20.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.20.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.20.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.20.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.21.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.21.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.21.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.21.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.22.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.22.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.22.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.22.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.23.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.23.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.23.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.23.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.24.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.24.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.24.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.24.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.25.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.25.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.25.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.25.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.26.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.26.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.26.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.26.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.27.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.27.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.27.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.27.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.28.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.28.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.28.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.28.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.29.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.29.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.29.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.29.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.3.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.3.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.3.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.3.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.30.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.30.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.30.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.30.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.31.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.31.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.31.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.31.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.32.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.32.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.32.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.32.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.33.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.33.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.33.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.33.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.34.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.34.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.34.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.34.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.35.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.35.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.35.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.35.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.36.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.36.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.36.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.36.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.37.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.37.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.37.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.37.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.38.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.38.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.38.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.38.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.39.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.39.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.39.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.39.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.4.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.4.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.4.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.4.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.40.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.40.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.40.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.40.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.41.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.41.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.41.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.41.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.42.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.42.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.42.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.42.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.43.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.43.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.43.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.43.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.44.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.44.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.44.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.44.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.45.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.45.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.45.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.45.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.46.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.46.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.46.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.46.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.47.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.47.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.47.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.47.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.48.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.48.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.48.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.48.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.49.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.49.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.49.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.49.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.5.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.5.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.5.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.5.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.6.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.6.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.6.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.6.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.7.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.7.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.7.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.7.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.8.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.8.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.8.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.8.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}, 'blocks.9.attn.out_proj': {'shape': [5376, 7168], 'bytes': 19267584}, 'blocks.9.attn.qkv_proj': {'shape': [21504, 5376], 'bytes': 57802752}, 'blocks.9.mlp.fc1': {'shape': [28672, 5376], 'bytes': 77070336}, 'blocks.9.mlp.fc2': {'shape': [5376, 14336], 'bytes': 38535168}}, 'signatures': {'video_patch_proj': [5376, 96], 'audio_patch_proj': [5376, 32], 'condition_proj': [5376, 5120]}, 'memory_min_bytes': 11321501488, 'memory_max_bytes': 13009210976, 'header_sha256': 'af8c4e1fd4745336b6c13d9c82e4716bc834f5ecaa7b7f5d377ae649b6bcd820', 'range_basis': 'Packed quant weight bytes + nonquant tensors at permitted BF16/FP32 widths; quant metadata/scales excluded from lower bound. No residency threshold.'}}

def h3_variant_identity(entry, checkpoint=None):
    model = entry.model.model
    if (type(model).__module__, type(model).__qualname__) != ('comfy.model_base', 'MiniMaxH3'):
        raise RuntimeError('Variant contract: non-H3 model')
    diffusion = getattr(model, 'diffusion_model', None)
    if (type(diffusion).__module__, type(diffusion).__qualname__) != ('comfy.ldm.minimax.model', 'MiniMaxH3Model'):
        raise RuntimeError('Variant contract: wrong diffusion architecture')
    if (getattr(diffusion, 'hidden_size', None), getattr(diffusion, 'latents_dim', None),
        getattr(diffusion, 'audio_latents_dim', None), tuple(getattr(diffusion, 'patch_size', ())),
        len(diffusion.blocks)) != (5376, 24, 32, (1, 2, 2), 50):
        raise RuntimeError('Variant contract: wrong H3 Ref2VA structure')
    modules = dict(diffusion.named_modules())
    quant = {name: module for name, module in modules.items() if getattr(module, 'quant_format', None) is not None}
    formats = {module.quant_format for module in quant.values()}
    variants = [name for name, spec in H3_VARIANT_CONTRACTS.items() if formats == {spec['quant_format']}]
    if len(variants) != 1:
        raise RuntimeError('Variant contract: unknown or mixed quant format')
    name = variants[0]; spec = H3_VARIANT_CONTRACTS[name]
    if checkpoint is not None and checkpoint != spec['checkpoint']:
        raise RuntimeError('Variant contract: graph checkpoint / loaded quant mismatch')
    if set(quant) != set(spec['weights']):
        raise RuntimeError('Variant contract: quant module signature mismatch')
    for key, signature in spec['signatures'].items():
        if tuple(modules[key].weight.shape) != tuple(signature):
            raise RuntimeError('Variant contract: projection shape mismatch')
    for key, expected in spec['weights'].items():
        weight = quant[key].weight
        params = getattr(weight, '_params', None)
        if tuple(weight.shape) != tuple(expected['shape']) or weight.nbytes != expected['bytes'] or params is None:
            raise RuntimeError('Variant contract: packed weight shape/size mismatch: ' + key)
        if name == 'INT8_CONVROT' and (getattr(params, 'convrot', None) is not True or getattr(params, 'convrot_groupsize', None) != 256):
            raise RuntimeError('Variant contract: INT8 ConvRot metadata mismatch')
        if name == 'NVFP4' and (getattr(params, 'block_scale', None) is None or getattr(params, 'scale', None) is None):
            raise RuntimeError('Variant contract: NVFP4 scales missing')
    memory = entry.model_memory()
    if isinstance(memory, bool) or not isinstance(memory, (int, float)) or not math.isfinite(memory) or not spec['memory_min_bytes'] <= memory <= spec['memory_max_bytes']:
        raise RuntimeError('Variant contract: variant-specific model storage mismatch')
    return {'variant': name, 'checkpoint': spec['checkpoint'], 'quant_format': spec['quant_format'],
            'quant_modules': len(quant), 'model_memory_bytes': memory,
            'memory_min_bytes': spec['memory_min_bytes'], 'memory_max_bytes': spec['memory_max_bytes'],
            'frozen_checkpoint_sha256': spec['sha256'], 'sha_scope': 'Preflight file hash; runtime checks architecture/quant/shape/storage, not full byte hash',
            'residency_used_as_identity': False}

def audit_module():
    path = Path(__file__).parent.parent / 'h3_sampler_to_vae_residency_probe' / '__init__.py'
    for m in tuple(sys.modules.values()):
        if getattr(m, '__file__', None) and Path(m.__file__) == path and hasattr(m, 'model_snapshot'):
            return m
    raise RuntimeError('Read-only observer unavailable')

def write(record, phase):
    record['phase'] = phase
    record['epoch'] = time.time()
    record['pid'] = os.getpid()
    FOLDER.mkdir(parents=True, exist_ok=True)
    (FOLDER / f"{os.getpid()}_{record.get('prompt_id', 'offline')}_{phase}_{time.time_ns()}.json").write_text(json.dumps(record, indent=2), encoding='utf-8')
    logging.info('H3AdaptiveHostWarm phase=%s prompt=%s epoch=%.6f', phase, record.get('prompt_id'), record['epoch'])
    return record

def retention_budget(audit, pre):
    """Forecast the known cold TE plus reference encode; no global eviction."""
    mem = audit.shared._windows_memory()
    gib = audit.shared.GIB
    reserve = (14.75 + 3.0) * gib
    floor = 6.0 * gib
    available = mem['SYSTEM_RAM_AVAILABLE_BYTES']
    commit_used = mem['SYSTEM_COMMIT_USED_BYTES']
    commit_limit = mem['SYSTEM_COMMIT_LIMIT_BYTES']
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or
           not math.isfinite(v) or v < 0 for v in (available, commit_used, commit_limit)) or commit_limit <= 0:
        raise RuntimeError('Invalid RAM/Commit forecast; TE blocked')
    host = pre['pins']['TE_HOSTBUFFER_GIB'] * gib
    # Match the official 256 MiB pin-pressure hysteresis. Account for OS
    # counters moving while native truncation/snapshot collection completes.
    hysteresis = 256 * 1024 ** 2
    release = max(0, reserve + floor + hysteresis - available,
                  reserve + commit_used + hysteresis - .90 * commit_limit)
    return {'reserve_bytes': reserve, 'available_floor_bytes': floor,
            'commit_ceiling': .90, 'hysteresis_bytes': hysteresis, 'release_required_bytes': release,
            'host_retention_budget_bytes': max(0, host - release), 'memory_before': mem}

def release_retained(e, p, m, pre, record, audit):
    """Only official DynamicVRAM partial methods; same managed H3 identity."""
    budget = retention_budget(audit, pre)
    record['retention_budget'] = budget
    gib = audit.shared.GIB
    if budget['host_retention_budget_bytes'] < gib:
        record['retention_decision'] = 'FULL_RELEASE_RAM_PRESSURE'
        return False
    peers = tuple(id(x) for x in mm.current_loaded_models if x is not e)
    patches = p.patches
    p.partially_unload(p.offload_device, 1e32)
    required = budget['release_required_bytes']
    if required > 0:
        p.partially_unload_ram(math.ceil(required))
    post = audit.model_snapshot(e)
    validate_measurement(post)
    if e.model is not p or p.model is not m or e.real_model is None or e.real_model() is not m or p.patches is not patches:
        raise RuntimeError('Retained H3 identity changed; TE blocked')
    if tuple(id(x) for x in mm.current_loaded_models if x is not e) != peers or sum(x is e for x in mm.current_loaded_models) != 1:
        raise RuntimeError('Retained H3/peer entry invariant failed; TE blocked')
    if post['loaded_size_gib'] > 1.05:
        raise RuntimeError('H3 GPU residency exceeds cold baseline; TE blocked')
    freed = (pre['pins']['TE_HOSTBUFFER_GIB'] - post['pins']['TE_HOSTBUFFER_GIB']) * gib
    if freed + .05 * gib < required:
        raise RuntimeError('Partial RAM release incomplete; TE blocked')
    mem = audit.shared._windows_memory()
    record['memory_after_partial'] = mem
    record['partial_after'] = post
    if mem['SYSTEM_RAM_AVAILABLE_BYTES'] < budget['reserve_bytes'] + budget['available_floor_bytes'] or \
       mem['SYSTEM_COMMIT_USED_BYTES'] + budget['reserve_bytes'] > budget['commit_ceiling'] * mem['SYSTEM_COMMIT_LIMIT_BYTES'] or \
       post['pins']['TE_HOSTBUFFER_GIB'] < 1.0:
        record['retention_decision'] = 'FULL_RELEASE_AFTER_PRESSURE_RECHECK'
        return False
    record.update(status='PASS', retention_decision='PARTIAL_HOST_RETENTION', after=post,
                  H3_HOST_AFTER_GIB=post['pins']['TE_HOSTBUFFER_GIB'], H3_HOST_FREED_GIB=freed/gib,
                  H3_ENTRY_RETAINED=True)
    write(record, 'H3_RELEASE_COMPLETE')
    return True


def release_exact(record):
    audit = audit_module()
    targets = []
    for e in tuple(mm.current_loaded_models):
        p = e.model
        if p is None:
            continue
        c = type(p.model)
        if c.__name__ == 'MiniMaxH3':
            if c.__module__ != 'comfy.model_base' or c.__qualname__ != 'MiniMaxH3':
                raise RuntimeError('Wrong H3 class identity')
            targets.append((e, p, p.model))
    record['H3_MATCH_COUNT'] = len(targets)
    if len(targets) > 1:
        raise RuntimeError('Multiple H3 targets; fail closed')
    if not targets:
        record.update(status='SAFE_NOOP', H3_HOST_BEFORE_GIB=0, H3_HOST_AFTER_GIB=0)
        return write(record, 'H3_RELEASE_COMPLETE')
    e, p, m = targets[0]
    # LoadedModel._switch_parent legitimately switches a collected PDD clone
    # back to its unpatched parent. Both patchers own the same H3 residency.
    # This pre-TE release is independent of PDD; sampling/Node1058 validates it.
    variant = h3_variant_identity(e)
    record['H3_VARIANT_IDENTITY'] = variant
    guards = {'entry_patcher_identity': e.model is p,
              'real_model_identity': e.real_model is not None and e.real_model() is m,
              'dynamic_patcher': p.is_dynamic(),
              'h3_variant_identity': bool(variant)}
    record['identity_guards'] = guards
    record['PDD_PATCH_COUNT_BEFORE'] = len(p.patches)
    record['PDD_PATCH_COUNT_IS_RELEASE_GATE'] = False
    if not all(guards.values()):
        raise RuntimeError('Exact H3 release identity guard failed: ' + ', '.join(k for k,v in guards.items() if not v))
    pre = audit.model_snapshot(e)
    validate_measurement(pre)
    record['before'] = pre
    record['H3_HOST_BEFORE_GIB'] = pre['pins']['TE_HOSTBUFFER_GIB']
    if release_retained(e, p, m, pre, record, audit):
        return record
    peers = tuple((id(x) for x in mm.current_loaded_models if x is not e))
    if e.model_unload(memory_to_free=None, unpatch_weights=True) is not True:
        raise RuntimeError('Full lifecycle unload not reported')
    if e.model is not p or p.model is not m:
        raise RuntimeError('Model identity changed')
    post = audit.model_snapshot(e)
    record['after'] = post
    validate_measurement(post)
    if post['pins']['TE_PIN_REGISTERED_GIB'] > 0.05 or post['pins']['TE_HOSTBUFFER_GIB'] > 0.05 or (post['loaded_size_gib'] > 0.05):
        raise RuntimeError('H3 residency not zero; TE blocked')
    for i, x in enumerate(mm.current_loaded_models):
        if x is e:
            del mm.current_loaded_models[i]
            break
    if any((x is e for x in mm.current_loaded_models)) or tuple((id(x) for x in mm.current_loaded_models)) != peers:
        raise RuntimeError('Loaded entries invariant failed')
    record.update(status='PASS', H3_HOST_AFTER_GIB=post['pins']['TE_HOSTBUFFER_GIB'])
    return write(record, 'H3_RELEASE_COMPLETE')

def validate_measurement(snapshot):
    if snapshot['errors']:
        raise RuntimeError('H3 measurement errors')
    pins = snapshot['pins']
    values = [snapshot['loaded_size_gib']] + [pins[k] for k in
              ('TE_PIN_ALLOCATED_GIB', 'TE_PIN_REGISTERED_GIB', 'TE_HOSTBUFFER_GIB')]
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or
           not math.isfinite(v) or v < 0 for v in values):
        raise RuntimeError('H3 residency measurement missing or invalid')
    if values[2] > values[1] + .01 or values[1] > values[3] + .01:
        raise RuntimeError('H3 pin/HostBuffer measurements inconsistent')

def install():
    if getattr(Official,'_H3_ADAPTIVE_HOST_WARM_PATCHED',False):return False
    if nodes.NODE_CLASS_MAPPINGS.get('MiniMaxH3ReferenceToVideo') is not Official:
        raise RuntimeError('Official registered class identity mismatch')
    schema_method=Official.__dict__['define_schema']; original=Official.__dict__['execute'].__func__
    input_before=Official.INPUT_TYPES(); signature=inspect.signature(original)
    @functools.wraps(original)
    def hooked(cls,*args,**kwargs):
        context=get_executing_context()
        if context is None:raise RuntimeError('Real backend execution context required')
        record={'prompt_id':context.prompt_id,'node_id':context.node_id,'status':'FAIL_CLOSED'}
        key=(context.prompt_id,context.node_id);ACTIVE[key]=record
        try:
            write(dict(record),'NODE136_EXECUTE_ENTER')
            release_exact(record)
            # All official reference encode/tokenize/TE loads occur after this release.
            result=original(cls,*args,**kwargs)
            audit=audit_module()
            write({'prompt_id':context.prompt_id,'te':audit.shared.snapshot(),'models':[audit.model_snapshot(e)for e in tuple(mm.current_loaded_models)if e.model is not None]},'ENCODE_COMPLETE')
            return result
        except Exception as ex:
            write({**record,'error':f'{type(ex).__name__}: {ex}'},'FAIL_CLOSED');raise
        finally:ACTIVE.pop(key,None)
    Official.execute=classmethod(hooked)
    if Official.__dict__['define_schema'] is not schema_method or Official.INPUT_TYPES()!=input_before or inspect.signature(hooked)!=signature:
        Official.execute=classmethod(original);raise RuntimeError('Schema/signature changed')
    Official._H3_ADAPTIVE_HOST_WARM_PATCHED=True
    Official._H3_ADAPTIVE_HOST_WARM_PATCH_INSTALL_COUNT=1
    Official._H3_ADAPTIVE_HOST_WARM_ORIGINAL_EXECUTE=original
    write({'class_object_same':nodes.NODE_CLASS_MAPPINGS['MiniMaxH3ReferenceToVideo']is Official,'schema_unchanged':True,'cache_signature_inputs_unchanged':True,'patch_install_count':1,'original_class_id':id(Official)},'PATCH_INSTALLED')
    return True
def install_observer():
    original=mm.load_models_gpu
    if getattr(original,'_h3_adaptive_inplace_observer',False):return
    @functools.wraps(original)
    def observed(models,*args,**kwargs):
        ctx=get_executing_context();rec=ACTIVE.get((ctx.prompt_id,ctx.node_id))if ctx else None
        is_te=any(type(p.model).__module__=='comfy.text_encoders.minimax' and type(p.model).__qualname__=='te.<locals>.MiniMaxH3TEModel_'for p in models)
        is_h3=any(type(p.model).__module__=='comfy.model_base' and type(p.model).__qualname__=='MiniMaxH3'for p in models)
        if rec and is_te:
            audit=audit_module();write({'prompt_id':ctx.prompt_id,'release_epoch':rec['epoch'],'H3_models':[audit.model_snapshot(e)for e in tuple(mm.current_loaded_models)if e.model is not None and type(e.model.model).__name__=='MiniMaxH3']},'TE_LOAD_START')
        elif ctx and is_h3 and ctx.node_id=='125':
            audit=audit_module();write({'prompt_id':ctx.prompt_id,'models':[audit.model_snapshot(e)for e in tuple(mm.current_loaded_models)if e.model is not None and type(e.model.model).__name__=='MiniMaxH3']},'H3_SAMPLER_LOAD_START')
        return original(models,*args,**kwargs)
    observed._h3_adaptive_inplace_observer=True;mm.load_models_gpu=observed
install()
install_observer()
