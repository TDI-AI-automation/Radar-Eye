"""RM-11.SIV visualization subsystem.

Renders operator-visible video directly from the existing DeepStream
pipeline's own PGIE/NvDCF/SGIE inference results -- no second inference
pass, no OpenCV. See docs/DEEPSTREAM_PIPELINE_SPEC.md's Visualization Path
section for the full architecture.

Everything visualization-specific lives in this package. Nothing outside
it (``apps/deepstream/app/pipeline/builder.py``, ``runtime.py``) imports
anything from here except ``VisualizationManager``
(``apps/deepstream/app/visualization/manager.py``).
"""

from __future__ import annotations
