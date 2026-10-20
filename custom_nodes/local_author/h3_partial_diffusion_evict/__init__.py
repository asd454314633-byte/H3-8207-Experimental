"""Exact MiniMaxH3 residency release after sampling, before all VAE branches."""

import folder_paths
import json
import logging
import hashlib
import math
import os
from pathlib import Path
import sys
import time
import comfy.model_management as mm
import torch



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

def branch_identity(prompt, unique_id, ancestors):
    """Prove the active guider's model lineage, never infer from UI labels."""
    def linked(node, key, slot=0):
        ref = node['inputs'].get(key)
        if not isinstance(ref, list) or len(ref) != 2 or ref[1] != slot or str(ref[0]) not in prompt:
            raise RuntimeError('Unknown H3 branch: invalid ' + key + ' link')
        return str(ref[0])

    sampler = prompt[linked(prompt[str(unique_id)], 'latent')]
    if sampler['class_type'] != 'SamplerCustomAdvanced':
        raise RuntimeError('Unknown H3 branch: expected final sampler latent')
    guider = prompt[linked(sampler, 'guider')]
    if guider['class_type'] != 'BasicGuider':
        raise RuntimeError('Unknown H3 branch: expected BasicGuider')
    current = linked(guider, 'model')
    seen = set()
    route = []
    while current not in seen:
        seen.add(current)
        node = prompt[current]
        kind = node['class_type']
        route.append((current, node))
        if kind == 'UNETLoader':
            break
        if kind == 'Any Switch (rgthree)':
            active = [key for key in node['inputs'] if key.startswith('any_')]
            if len(active) != 1:
                raise RuntimeError('Unknown H3 branch: ambiguous model switch')
            current = linked(node, active[0])
        elif kind in ('ModelAttentionBackend', 'H3MemoryOptimization', 'ModelPreviewOverrideKJ',
                      'MiniMaxH3SigmaShift', 'LoraLoaderModelOnly', 'MiniMaxH3PDDAccApply'):
            current = linked(node, 'model')
        elif kind == 'H3PrecisionAudit':
            # Opt-in observation clone; no weight/attention edits. Keep all
            # model/PDD/provenance checks below, and reject duplicate observers.
            if any(n['class_type'] == kind for _, n in route[:-1]):
                raise RuntimeError('Unknown H3 branch: duplicate precision observers')
            if set(node['inputs']) != {'model', 'label'} or not isinstance(node['inputs']['label'], str):
                raise RuntimeError('Unknown H3 branch: invalid precision observer')
            current = linked(node, 'model')
        elif kind == 'MiniMaxH3FunControlNetApply':
            # Official MODEL clone: prove this validated Union2 route, but keep
            # release ownership on the actual H3 LoadedModel below. Its sampler
            # owns Fun patch cleanup; this guard never unloads the control model.
            if any(n['class_type'] == kind for _, n in route[:-1]):
                raise RuntimeError('Unknown H3 branch: multiple Fun control patches')
            control = prompt[linked(node, 'model_patch')]
            if (control['class_type'] != 'ModelPatchLoader' or
                    control['inputs'].get('name') !=
                    'minimax_h3_fun_controlnet_union_2.0_pruned_int8_convrot.safetensors'):
                raise RuntimeError('Unknown H3 branch: unvalidated Fun control model patch')
            current = linked(node, 'model')
        else:
            raise RuntimeError('Unknown H3 branch: unsupported model route ' + kind)
    else:
        raise RuntimeError('Unknown H3 branch: model route cycle')
    pdds = [(nid, node) for nid, node in route if node['class_type'] == 'MiniMaxH3PDDAccApply']
    loras = [(nid, node) for nid, node in route if node['class_type'] == 'LoraLoaderModelOnly']
    all_pdds = [nid for nid in ancestors if prompt[nid]['class_type'] == 'MiniMaxH3PDDAccApply']
    all_loras = [nid for nid in ancestors if prompt[nid]['class_type'] == 'LoraLoaderModelOnly']
    if len(pdds) == 1 and all_pdds == [pdds[0][0]] and all_loras == [nid for nid, _ in loras]:
        pdd_id, pdd = pdds[0]
        pdd_inputs = pdd['inputs']
        if (pdd_inputs.get('enabled', True) is not True or
                pdd_inputs.get('pdd_file') != 'MiniMax-H3-Ref2VA-Acc-8Step.safetensors' or
                str(pdd_inputs.get('nfe')) != '8'):
            raise RuntimeError('Unknown H3 branch: unvalidated PDD8 identity')
        route_ids = [nid for nid, _ in route]
        if not loras:
            return {'branch': 'pdd8', 'model_route': route_ids, 'pdd_node': pdd_id,
                    'people_lora': None}
        if len(loras) == 1:
            lora_id, lora = loras[0]
            inputs = lora['inputs']
            name = inputs.get('lora_name', '').replace('\\', '/')
            strength = inputs.get('strength_model')
            # route is traversed from sampler toward the source UNET: PDD must
            # consume the already-LoRA-patched MODEL, not the reverse.
            if (name == 'h3-realism-people-t2v-i2v-r2v.safetensors' and
                    isinstance(strength, (int, float)) and not isinstance(strength, bool) and
                    math.isfinite(strength) and strength == 1.0 and
                    route_ids.index(pdd_id) < route_ids.index(lora_id) and
                    route[-1][1]['class_type'] == 'UNETLoader' and
                    route[-1][1]['inputs'].get('unet_name') ==
                    'minimax_h3_ref2va_pruned_int8_convrot.safetensors'):
                return {'branch': 'pdd8_people_lora', 'model_route': route_ids,
                        'pdd_node': pdd_id, 'people_lora_node': lora_id,
                        'people_lora': name, 'people_lora_strength': float(strength),
                        'people_lora_sha256':
                        'ACC529601D2DA117FB81179E76C56E488A3BEAB1171659D305F04FA3655B787E'}
        raise RuntimeError('Unknown H3 branch: PDD8 permits only the allowlisted People LoRA')
    if not pdds and not all_pdds and len(loras) == 1 and all_loras == [loras[0][0]]:
        inputs = loras[0][1]['inputs']
        name = inputs.get('lora_name', '').replace('\\', '/')
        strength = inputs.get('strength_model')
        if (name == 'MINIMAX/minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors'
                and isinstance(strength, (int, float)) and not isinstance(strength, bool)
                and math.isfinite(strength) and strength != 0):
            return {'branch': 'stable8', 'model_route': [nid for nid, _ in route],
                    'turbo_lora': name, 'PDD_REQUIREMENT': 'NONE'}
    raise RuntimeError('Unknown or conflicting H3 branch; fail closed')


def verify_pdd_people_patch_stack(patcher, prompt, branch):
    """Prove exact PDD and allowlisted People-LoRA patches, including overlays."""
    import comfy.lora
    import comfy.utils
    import folder_paths
    # The PDD node package keeps this helper as a relative module; its folder
    # is not on sys.path as a top-level import in this isolated runtime.
    try:
        import pdd_acc_core
    except ModuleNotFoundError as exc:
        if exc.name != 'pdd_acc_core':
            raise
        import importlib
        # Match MiniMaxH3PDDAccApply's registered Comfy package and its normal
        # relative submodule import instead of changing sys.path or duplicating
        # the PDD core module.
        pdd_acc_core = importlib.import_module(
            'custom_nodes.ComfyUI-MiniMax-H3-PDD-Acc.pdd_acc_core')

    people_name = branch['people_lora']
    people_path = Path(folder_paths.get_full_path_or_raise('loras', people_name))
    digest = hashlib.sha256()
    with people_path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    if digest.hexdigest().upper() != branch['people_lora_sha256']:
        raise RuntimeError('People LoRA file SHA256 mismatch')
    people_sd = comfy.utils.load_torch_file(str(people_path), safe_load=True)
    key_map = comfy.lora.model_lora_keys_unet(patcher.model, {})
    people_loaded = comfy.lora.load_lora(people_sd, key_map)
    if not people_loaded:
        raise RuntimeError('People LoRA matched no H3 model patch keys')

    pdd_name = prompt[branch['pdd_node']]['inputs']['pdd_file']
    pdd_path = folder_paths.get_full_path_or_raise('pdd_acc', pdd_name)
    pdd_sd, metadata = comfy.utils.load_torch_file(
        pdd_path, safe_load=True, return_metadata=True)
    pdd_lora_sd, _heads, _config = pdd_acc_core.split_pdd_state_dict(
        pdd_sd, metadata, pdd_name)
    # Mirror MiniMaxH3PDDAccApply exactly. On pruned H3 checkpoints the PDD
    # node rebases each AdaLN curve LoRA into both a weight diff and a bias
    # diff. comfy.lora.load_lora maps each .diff_b to a separate target .bias
    # patch; omitting this official transformation makes those legitimate
    # PDD patches look like unknown extras at the release gate.
    pdd_nodes = __import__(
        'custom_nodes.ComfyUI-MiniMax-H3-PDD-Acc.nodes',
        fromlist=['_curve_rebase_if_pruned'])
    # PDD Apply receives Comfy's ModelPatcher. Its helper calls
    # get_model_object("diffusion_model"), which belongs to the patcher;
    # patcher.model is only the MiniMaxH3 model-base object. Mirror Apply.
    pdd_lora_sd, curve_note = pdd_nodes._curve_rebase_if_pruned(
        patcher, pdd_lora_sd, pdd_name)
    pdd_loaded = comfy.lora.load_lora(pdd_lora_sd, key_map)
    pdd_expected_modules = sum(
        1 for key in pdd_lora_sd
        if key.endswith(('.lora_A.weight', '.diff')))
    pdd_expected_entries = sum(
        1 for key in pdd_lora_sd
        if key.endswith(('.lora_A.weight', '.diff', '.diff_b')))
    if (not pdd_expected_modules or
            len(pdd_loaded) != pdd_expected_entries):
        raise RuntimeError(
            'PDD patch key identity mismatch: '
            f'expected {pdd_expected_entries} patch entries from '
            f'{pdd_expected_modules} trained modules, got {len(pdd_loaded)}')

    def patch_key(key):
        return key if isinstance(key, str) else key[0]

    expected = {}
    for key in pdd_loaded:
        expected[patch_key(key)] = expected.get(patch_key(key), 0) + 1
    for key in people_loaded:
        expected[patch_key(key)] = expected.get(patch_key(key), 0) + 1
    actual = {patch_key(key): len(value) for key, value in patcher.patches.items()}
    if actual != expected:
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        bad_counts = sorted((key, expected[key], actual.get(key, 0))
                            for key in set(expected) & set(actual)
                            if expected[key] != actual[key])
        raise RuntimeError('PDD/People patch provenance mismatch: '
                           f'missing={len(missing)} extra={len(extra)} overlays={len(bad_counts)}; '
                           f'missing_keys={missing[:64]} extra_keys={extra[:64]} '
                           f'overlay_keys={bad_counts[:64]}')

    # PDD Apply stores the Head Bank as a ModelPatcher object patch and its
    # sampler wrapper in ModelPatcher.wrappers (not model_options).
    pdd_nodes = __import__(
        'custom_nodes.ComfyUI-MiniMax-H3-PDD-Acc.nodes',
        fromlist=['WRAPPER_KEY'])
    pdd_wrappers = patcher.get_wrappers(
        comfy.patcher_extension.WrappersMP.DIFFUSION_MODEL,
        pdd_nodes.WRAPPER_KEY)
    if ('diffusion_model.final_layer.forward' not in patcher.object_patches or
            len(pdd_wrappers) != 1):
        raise RuntimeError('PDD Head Bank forward patch or sampler wrapper missing')
    shared = set(map(patch_key, pdd_loaded)) & set(map(patch_key, people_loaded))
    curve_bias_count = sum(1 for key in pdd_lora_sd if key.endswith('.diff_b'))
    return {'PDD_PATCH_KEYS': len(pdd_loaded),
            'PDD_TRAINED_MODULES': pdd_expected_modules,
            'PDD_CURVE_BIAS_PATCHES': curve_bias_count,
            'PDD_CURVE_REBASE_NOTE': curve_note,
            'PDD_DIFF_B_SOURCE_KEYS': sorted(
                key for key in pdd_lora_sd if key.endswith('.diff_b')),
            'PEOPLE_LORA_MATCHED_KEYS': len(people_loaded),
            'SHARED_PATCH_KEYS': len(shared), 'PATCH_DICT_KEYS': len(actual),
            'TOTAL_PATCH_ENTRIES': sum(actual.values()), 'PDD_HEAD_BANK_FORWARD': True,
            'PDD_SAMPLER_WRAPPER_COUNT': len(pdd_wrappers),
            'PEOPLE_LORA_SHA256': digest.hexdigest().upper()}


def classify_model_roles(prompt, ancestors, branch):
    """Classify MODEL loaders by their consumers, before releasing only H3."""
    consumers = {}
    for nid in ancestors:
        for field, ref in prompt[nid]['inputs'].items():
            if isinstance(ref, list) and len(ref) == 2 and ref[1] == 0:
                consumers.setdefault(str(ref[0]), []).append((nid, field))
    forward = {'ModelAttentionBackend', 'H3MemoryOptimization', 'ModelPreviewOverrideKJ',
               'MiniMaxH3SigmaShift', 'LoraLoaderModelOnly', 'MiniMaxH3PDDAccApply',
               'MiniMaxH3FunControlNetApply', 'H3PrecisionAudit'}
    auxiliary = {'RTDETR_detect', 'SDPoseKeypointExtractor'}
    loaders = {'UNETLoader', 'CheckpointLoaderSimple'}
    for nid in ancestors:
        node = prompt[nid]
        if node['class_type'] in forward | auxiliary | {'BasicGuider', 'BasicScheduler'}:
            ref = node['inputs'].get('model')
            if isinstance(ref, list) and len(ref) == 2 and str(ref[0]) in prompt:
                if prompt[str(ref[0])]['class_type'] not in loaders | forward | {'Any Switch (rgthree)'}:
                    raise RuntimeError('Unknown model role: unclassified MODEL producer')

    def trace(nid, path):
        if nid in path:
            raise RuntimeError('Unknown model role: MODEL route cycle')
        uses = consumers.get(nid, [])
        if not uses:
            raise RuntimeError('Unknown model role: no proven consumer')
        roles, terminals = set(), []
        for child, field in uses:
            node = prompt[child]; kind = node['class_type']
            if kind == 'BasicGuider' and field == 'model':
                if not any(prompt[k]['class_type'] == 'SamplerCustomAdvanced' and
                           prompt[k]['inputs'].get('guider') == [child, 0] for k in ancestors):
                    raise RuntimeError('Unknown model role: guider without proven sampler')
                roles.add('H3_MAIN_MODEL'); terminals.append(child)
            elif kind in auxiliary and field == 'model':
                roles.add('AUXILIARY_MODEL'); terminals.append(child)
            elif kind == 'BasicScheduler' and field == 'model':
                terminals.append(child)  # Reads model sampling parameters; outputs only SIGMAS.
            elif ((kind in forward and field == 'model') or
                  (kind == 'Any Switch (rgthree)' and field.startswith('any_'))):
                if kind == 'Any Switch (rgthree)' and sum(k.startswith('any_') for k in node['inputs']) != 1:
                    raise RuntimeError('Unknown model role: ambiguous model switch')
                r, t = trace(child, path | {nid}); roles.update(r); terminals.extend(t)
            else:
                raise RuntimeError('Unknown model role: unsupported consumer ' + kind + '.' + field)
        return roles, terminals

    records = []
    for nid in sorted(ancestors):
        node = prompt[nid]
        if node['class_type'] not in loaders:
            continue
        roles, terminals = trace(nid, set())
        if len(roles) != 1:
            raise RuntimeError('Unknown model role: mixed main/auxiliary uses')
        records.append({'loader': nid, 'role': next(iter(roles)), 'consumers': sorted(set(terminals))})
    main = [r['loader'] for r in records if r['role'] == 'H3_MAIN_MODEL']
    if len(main) != 1 or main[0] != branch['model_route'][-1]:
        raise RuntimeError('Expected exactly one sampler-lineage H3 main MODEL loader')
    return records


def validate_residency(snapshot):
    """Validate this execution's measurements, independent of cache capacity."""
    target = snapshot['target']
    if snapshot['MEASUREMENT_ERRORS'] or target['errors']:
        raise RuntimeError('Residency measurement reported errors')
    values = [target['loaded_size_gib']] + [target['pins'][key] for key in
              ('TE_PIN_ALLOCATED_GIB', 'TE_PIN_REGISTERED_GIB', 'TE_HOSTBUFFER_GIB')]
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or
           not math.isfinite(x) or x < 0 for x in values):
        raise RuntimeError('Residency measurement missing or invalid')
    allocated, registered, host = values[1:]
    if registered > allocated + .01 or allocated > host + .01:
        raise RuntimeError('Residency pin/HostBuffer measurements inconsistent')
    return target


def cuda_snapshot():
    return {'allocated_gib': torch.cuda.memory_allocated()/1024**3,
            'reserved_gib': torch.cuda.memory_reserved()/1024**3}


def audit_module():
    path=Path(__file__).parent.parent/'h3_sampler_to_vae_residency_probe'/'__init__.py'
    for module in tuple(sys.modules.values()):
        filename=getattr(module,'__file__',None)
        if filename and Path(filename)==path and hasattr(module,'model_snapshot'):
            return module
    raise RuntimeError('Loaded read-only transition observer unavailable')


class H3PartialDiffusionEvictBeforeVAE:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'latent':('LATENT',)},'hidden':{'prompt':'PROMPT','unique_id':'UNIQUE_ID'}}
    RETURN_TYPES=('LATENT',)
    RETURN_NAMES=('latent',)
    FUNCTION='release'
    CATEGORY='H3/diagnostics'
    @classmethod
    def IS_CHANGED(cls,**kwargs):return float('nan')

    def release(self,latent,prompt,unique_id):
        started=time.perf_counter()
        record={'schema':'H3_V29_PARTIAL_EVICT_CURRENT_RESIDENCY_V2','pid':os.getpid(),'epoch':time.time(),'node_id':str(unique_id),'status':'FAIL_CLOSED','MEASUREMENT_PHASE_COUNT':0}
        folder=Path(folder_paths.get_user_directory())/'h3_partial_diffusion_evict'
        folder.mkdir(parents=True,exist_ok=True)
        output=folder/f'release_{os.getpid()}_{time.time_ns()}.json'
        try:
            audit=audit_module()
            ancestors=set()
            def visit(nid):
                nid=str(nid)
                if nid in ancestors:return
                ancestors.add(nid)
                for value in prompt[nid]['inputs'].values():
                    if isinstance(value,list) and len(value)==2 and str(value[0]) in prompt:visit(value[0])
            visit(unique_id)
            pdds=[n for nid,n in prompt.items() if str(nid) in ancestors and n['class_type']=='MiniMaxH3PDDAccApply']
            branch = branch_identity(prompt, unique_id, ancestors)
            record['branch_identity'] = branch
            record['model_roles'] = classify_model_roles(prompt, ancestors, branch)
            loaders=[prompt[r['loader']] for r in record['model_roles'] if r['role']=='H3_MAIN_MODEL']
            if len(loaders)!=1 or loaders[0]['inputs'].get('unet_name') not in {v['checkpoint'] for v in H3_VARIANT_CONTRACTS.values()}:
                raise RuntimeError('Unique graph supported H3 variant identity not proven')
            if branch['branch'] in ('pdd8', 'pdd8_people_lora') and (len(pdds)!=1 or pdds[0]['inputs'].get('pdd_file')!='MiniMax-H3-Ref2VA-Acc-8Step.safetensors'):
                raise RuntimeError('Unique graph INT8 H3/PDD identity not proven')
            targets=[]
            for entry in tuple(mm.current_loaded_models):
                patcher=entry.model
                if patcher is not None and type(patcher.model).__module__=='comfy.model_base' and type(patcher.model).__qualname__=='MiniMaxH3':
                    targets.append((entry,patcher,patcher.model))
            record['H3_MATCH_COUNT']=len(targets)
            if len(targets)!=1:raise RuntimeError('Expected exactly one exact MiniMaxH3 LoadedModel')
            entry,patcher,model=targets[0]
            if entry.real_model is None or entry.real_model() is not model or entry.model is not patcher or not patcher.is_dynamic():
                raise RuntimeError('LoadedModel/patcher/model identity mismatch')
            record['H3_VARIANT_IDENTITY'] = h3_variant_identity(entry, loaders[0]['inputs']['unet_name'])
            if branch['branch'] == 'pdd8_people_lora':
                stack = verify_pdd_people_patch_stack(patcher, prompt, branch)
                record['PATCH_STACK_IDENTITY'] = stack
                record['PDD_PATCH_COUNT'] = stack['PDD_PATCH_KEYS']
                record['TOTAL_PATCH_COUNT'] = stack['TOTAL_PATCH_ENTRIES']
            elif branch['branch'] == 'pdd8':
                if len(patcher.patches) != 308:
                    raise RuntimeError('H3 PDD 308 patch guard failed')
                record['PDD_PATCH_COUNT'] = 308
                record['TOTAL_PATCH_COUNT'] = sum(
                    len(v) for v in patcher.patches.values())
            else:
                record['PDD_PATCH_COUNT'] = None
                record['TOTAL_PATCH_COUNT'] = sum(
                    len(v) for v in patcher.patches.values())
            before=audit.shared.snapshot()
            before['target']=audit.model_snapshot(entry)
            record['before']=before
            record['MEASUREMENT_PHASE_COUNT']=1
            record['CUDA_BEFORE']=cuda_snapshot()
            target=validate_residency(before)
            peers=tuple(id(x) for x in mm.current_loaded_models if x is not entry)
            record['identities']={'entry':id(entry),'patcher':id(patcher),'model':id(model)}
            record['MODEL_UNLOAD_CALLED']=False
            record['FULL_DETACH_CALLED']=False
            loaded=patcher.loaded_size()
            if not math.isfinite(loaded) or loaded<0 or abs(loaded/audit.shared.GIB-target['loaded_size_gib'])>.01:
                raise RuntimeError('Current GPU residency measurement inconsistent')
            request=max(0,int(loaded-audit.shared.GIB))
            record['RESIDENCY_STATE_BEFORE']='GPU_RESIDENT' if request else 'ALREADY_GPU_COLD'
            record['GPU_RELEASE_REQUEST_GIB']=request/audit.shared.GIB
            # Direct official partial API: never fall back to full detach on shortfall.
            record['PARTIALLY_UNLOAD_CALLED']=request>0
            freed=patcher.partially_unload(patcher.offload_device,request) if request else 0
            record['GPU_RELEASE_REPORTED_GIB']=freed/audit.shared.GIB
            if entry.model is not patcher or patcher.model is not model or entry.real_model() is not model:
                raise RuntimeError('Target identity changed')
            if tuple(id(x) for x in mm.current_loaded_models if x is not entry)!=peers:
                raise RuntimeError('Peer entry changed')
            after=audit.shared.snapshot()
            after['target']=audit.model_snapshot(entry)
            after['H3_ENTRY_PRESENT_AFTER']=any(x is entry for x in mm.current_loaded_models)
            record['after']=after
            record['MEASUREMENT_PHASE_COUNT']=2
            record['CUDA_AFTER']=cuda_snapshot()
            record['H3_UNLOAD_FREED_PINNED_GIB']=target['pins']['TE_PIN_REGISTERED_GIB']-after['target']['pins']['TE_PIN_REGISTERED_GIB']
            post=validate_residency(after)
            retained=post['pins']['TE_HOSTBUFFER_GIB']
            registered=post['pins']['TE_PIN_REGISTERED_GIB']
            record['HOST_CACHE_RETAINED_GIB']=retained
            if after['MEASUREMENT_ERRORS'] or post['errors'] or not after['H3_ENTRY_PRESENT_AFTER'] or post['loaded_size_gib']>1.5:
                raise RuntimeError('Partial GPU eviction insufficient; VAE branches blocked')
            if retained<.9*target['pins']['TE_HOSTBUFFER_GIB'] or registered<.9*target['pins']['TE_PIN_REGISTERED_GIB']:
                raise RuntimeError('Host cache not retained; VAE branches blocked')
            record['status']='PASS'
            record['RESIDENCY_STATE_AFTER']='GPU_COLD_HOST_RETAINED'
            # Arm existing read-only VAE load/decode observer AFTER successful release.
            audit.H3SamplerToVAEResidencyProbe().observe(latent)
            return {'ui':{'text':[json.dumps(record)]},'result':(latent,)}
        except Exception as e:
            record['error']=f'{type(e).__name__}: {e}'
            raise
        finally:
            record['elapsed_seconds']=time.perf_counter()-started
            output.write_text(json.dumps(record,indent=2),encoding='utf-8')
            logging.info('H3SelectiveDiffusionUnload status=%s path=%s',record['status'],output)


NODE_CLASS_MAPPINGS={'H3PartialDiffusionEvictBeforeVAE':H3PartialDiffusionEvictBeforeVAE}
