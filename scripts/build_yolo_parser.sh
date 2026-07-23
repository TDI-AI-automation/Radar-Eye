#!/usr/bin/env bash
# Builds apps/deepstream/native/nvdsinfer_custom_impl_Yolo/libnvdsinfer_custom_impl_Yolo.so
# -- the custom bbox parser plugin required to run a custom-trained YOLO
# model through nvinfer (see apps/deepstream/native/README.md for why this
# exists). Never run as part of `pytest`/CI -- this needs the real
# DeepStream SDK headers and nvcc, absent on any machine without the SDK
# installed, same constraint as every other GStreamer/pyds-dependent piece
# of apps/deepstream.
#
# Usage:
#   ./scripts/build_yolo_parser.sh [CUDA_VER]
#
# CUDA_VER defaults to the version reported by `nvcc --version` if not
# passed explicitly -- set it yourself if that detection is wrong for your
# machine (e.g. multiple CUDA toolkits installed side by side).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PARSER_DIR="$REPO_ROOT/apps/deepstream/native/nvdsinfer_custom_impl_Yolo"

if [ ! -d "$PARSER_DIR" ]; then
    echo "error: $PARSER_DIR not found" >&2
    exit 1
fi

CUDA_VER="${1:-}"
if [ -z "$CUDA_VER" ]; then
    CUDA_VER="$(nvcc --version 2>/dev/null | sed -n 's/.*release \([0-9]\+\.[0-9]\+\).*/\1/p')"
fi
if [ -z "$CUDA_VER" ]; then
    echo "error: could not detect CUDA_VER automatically -- pass it explicitly, e.g.:" >&2
    echo "  ./scripts/build_yolo_parser.sh 12.2" >&2
    exit 1
fi

echo "Building libnvdsinfer_custom_impl_Yolo.so with CUDA_VER=$CUDA_VER"
export CUDA_VER
make -C "$PARSER_DIR" clean
make -C "$PARSER_DIR"

echo "Built: $PARSER_DIR/libnvdsinfer_custom_impl_Yolo.so"
