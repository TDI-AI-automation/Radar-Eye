# Radar Eye Model Registry

## Model-001

Name:

yolo26m_weapon.pt

Type:

Object Detection

Status:

BASELINE CANDIDATE

File Size:

44 MB

Checkpoint Type:

Full Training Checkpoint

Known Facts:

- Ultralytics checkpoint
- Contains training metadata
- Contains optimizer state
- Contains model state
- TensorRT compatibility CONFIRMED (2026-07-23) -- exported to ONNX
  (`yolo26m_weapon.onnx`) and a working FP16 TensorRT engine built
  successfully outside this repo, via `marcoslucianops/DeepStream-Yolo`
  (a third-party ONNX-export + custom-parser toolchain, MIT licensed).
  Engine/ONNX files are not committed here (per this repo's `.gitignore`
  and RM-11.SIV Decision C -- model binaries are never vendored).
- DeepStream compatibility CONFIRMED (2026-07-23) -- this architecture's
  raw output requires a custom `nvinfer` bbox-parser plugin (stock
  DeepStream cannot decode it natively); that plugin's *source* is now
  vendored at `apps/deepstream/native/nvdsinfer_custom_impl_Yolo/`
  (`scripts/build_yolo_parser.sh` builds it), and `ModelStageSettings`/
  `ModelConfigResolver` (`apps/deepstream/app/config.py`/`models_config.py`)
  gained the config surface (`custom_lib_path`, `parse_bbox_func_name`,
  `cluster_mode`, `network_type`, `maintain_aspect_ratio`,
  `symmetric_padding`, `infer_dims`, `topk`) needed to wire it in. This
  confirms the *integration path* works end-to-end (`ModelConfigResolver`
  output verified to reproduce a real, independently hand-authored working
  `nvinfer` config); it does not confirm detection accuracy -- see Rule
  below.
- Classes now KNOWN: 5-class detector output -- **corrected 2026-08-09**,
  confirmed against the real, provided `models/labels.txt`:
  `fire, melee_lethal, non_lethal, person, ranged_lethal`. This already
  matches THREAT_ENGINE_SPEC.md's own `WeaponType` taxonomy directly (no
  material-based intermediate mapping) -- the earlier entry here
  (`fire, metal, non_metal, person, ranged_metal`) was an unconfirmed
  guess, not read from an actual label file, and was wrong.
  `services/incident_service/classification.py`'s `WEAPON_LABEL_TO_TYPE`
  maps these 1:1 to `WeaponType.FIRE`/`MELEE_LETHAL`/`NON_LETHAL`/
  `RANGED_LETHAL`.

Unknowns:

- Input size (nvinfer auto-detects this from the ONNX graph at runtime --
  RM-11.SIV's config surface deliberately never hardcodes a guessed value)
- Dataset
- Accuracy
- Latency

---

## Model-002

Name:

vit_48k_binary.pth

Type:

Image Classification

Status:

BASELINE CANDIDATE

File Size:

343 MB

Checkpoint Type:

State Dictionary

Known Facts:

- Vision Transformer architecture
- 12 encoder layers
- Binary classification
- TensorRT compatibility CONFIRMED (2026-07-23) -- exported to ONNX
  (`vit_binary.onnx`), working FP16 TensorRT engine built successfully
  outside this repo (see Model-001's identical note; not committed here).
- DeepStream compatibility CONFIRMED (2026-07-23) -- runs as a stock
  `nvinfer` secondary classifier (no custom parser needed, unlike
  Model-001); `ModelConfigResolver` output verified to reproduce a real,
  independently hand-authored working `nvinfer` classifier config
  (`operate_on_class_ids`, `input_object_min_width`/`height`,
  `model_color_format` all now configurable, matching that config exactly).
- Classes now KNOWN: `Civilian;Military` -- maps directly onto
  `shared/constants/uniform_classes.py`'s `UniformClass.CIVILIAN`/
  `MILITARY` (`UNKNOWN` remains reserved for low classifier confidence,
  per THREAT_ENGINE_SPEC.md, not a third model output class).

Unknowns:

- Dataset
- Accuracy
- Input size (nvinfer auto-detects from the ONNX graph -- see Model-001)
- Latency

---

## Rule

No model is production approved until benchmarked.