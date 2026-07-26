# apps/deepstream/native/

Vendored native (C++/CUDA) source required to run a **custom-trained YOLO
model** through DeepStream's `nvinfer` element. Stock DeepStream (and this
repo's RM-11 Phase 1/2 placeholder configs, `apps/deepstream/configs/
pgie_placeholder.txt`/`sgie_placeholder.txt`) uses `resnet18_trafficcamnet`,
whose output `nvinfer` can decode natively. A custom architecture's raw
output tensor has no built-in decoder — `nvinfer` needs a compiled shared
library (`custom-lib-path`) exposing a bbox-parsing function
(`parse-bbox-func-name`) to turn it into detections at all. Without this,
PGIE loads and runs "successfully" but silently produces zero usable
detections.

## `nvdsinfer_custom_impl_Yolo/`

Source only — **never commit `.o`/`.so` build output** (see `.gitignore`).
Vendored from [`marcoslucianops/DeepStream-Yolo`](https://github.com/marcoslucianops/DeepStream-Yolo)
(MIT License — see `LICENSE-DeepStream-Yolo.md`), the community project used
to export/wire this project's real weapon-detection model
(`yolo26m_weapon.onnx`) into DeepStream, per `docs/MODEL_REGISTRY.md`'s
Model-001. Build with `scripts/build_yolo_parser.sh`.

Model weights, ONNX exports, and TensorRT engines are **not** vendored here
or anywhere in this repo (`.gitignore` already excludes `models/*.onnx`/
`*.engine`/`*.pt`/`*.pth` repo-wide) — `configs/models.yaml` references
their location on whatever machine is running the pipeline, per RM-11.SIV
Decision C. Per `MODEL_REGISTRY.md`'s standing rule ("No model is production
approved until benchmarked"), the checked-in `configs/models.yaml` keeps
`pgie.enabled`/`sgie.enabled` at `false` (placeholder fallback) regardless
of this vendored parser's presence — enabling the real model is a separate,
local/environment-specific decision, not something this commit changes.
