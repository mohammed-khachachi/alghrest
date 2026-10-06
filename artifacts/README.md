# Local artifacts

`models/` contains the pre-existing CNN and PPO files moved from `ml/weights/` without changing their contents. Training writes new model files here. `checkpoints/` is the default checkpoint directory.

Generated files are ignored by Git and excluded from runtime wheels and Docker build contexts. Keep model provenance, evaluation results, and deployment selection explicit; the experimental inference service does not automatically load these weights. Store important model versions in an artifact registry or a backed-up location before cleaning this directory.
