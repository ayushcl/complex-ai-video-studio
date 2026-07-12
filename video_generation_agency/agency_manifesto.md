# Maxiion / Kunisys Video Generation Agency

This agency manages the video generation pipeline.

The pipeline separates creative direction, prompt engineering, video generation, asset management, and quality review.

The goal is to create a structured, testable, and expandable system for generating videos through Google/Omni/Veo-style APIs.

Agents must keep their responsibilities separate.

No agent should invent missing production requirements without clearly marking them as assumptions.

All generation requests should preserve:
- original creative brief
- final prompt
- model used
- generation parameters
- job ID
- output location
- review status
