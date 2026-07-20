"""Artifact Continuity Runtime — 11-stage pipeline for disciplined AI execution.

Stages:
  1. Evidence ingestion
  2. Multimodal canonicalization
  3. Semantic glyph compilation
  4. Anti-overcompute gate
  5. Minimum-evidence retrieval
  6. Shadow Self (local resolution)
  7. Model router
  8. Frontier execution
  9. Verification
 10. Shadow learning
 11. Cost receipt

Every terminal path produces a receipt. Intelligence already purchased
becomes reusable state. The executor is temporary; preserved state is
authoritative.
"""

from .runtime import ArtifactContinuityRuntime, RuntimeResult
from .evidence import Evidence, EvidenceStore
from .canonicalization import Canonicalizer, CanonicalForm
from .glyph_compiler import GlyphCompiler, TaskSignature
from .overcompute_gate import OvercomputeGate, CacheEntry
from .retrieval import EvidenceRetriever
from .shadow_self import ShadowSelf
from .model_router import ModelRouter, Route
from .frontier import FrontierExecutor
from .verification import Verifier
from .shadow_learning import ShadowLearner, LearningClass
from .cost_receipt import CostReceipt
from .artifact_registry import ArtifactRegistry

__version__ = "0.1.0"
