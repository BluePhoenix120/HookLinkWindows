# Integration policy for V1.3.4 onward

Decision recorded 2026-11-27: official NXnative takes precedence over
HookLink X3 until the next major HookLink release, when the policy will be
reviewed. V1.3.3 remains the known working baseline, including BodiesOfTruth.

- Start from the complete official NXnative target; include all upstream
  changes and deletions, not just selected files.
- Prefer the official implementation whenever the two projects implement
  the same or substantially similar functionality, including cleanly merged
  changes that overlap semantically rather than textually.
- Retain independently useful HookLink-only features and adapt them to the
  official engine. Preserve necessary Windows compatibility, the GUI,
  build-time mods, packaging and transfer behavior.
- Restore the official frame-step ABI as a consistent whole. Do not retain
  HookLink's competing duration field at +0x38 or relocate the official tick
  unit merely to preserve the superseded implementation.
- Review graphics, MetalFX, frame pacing, texture lifetime, audio, launcher,
  generated shader tables, PSO manifests and cache behavior for duplication.
  Preserve unique functionality without preserving outdated implementations.
- Record all retained differences and their rationale; regenerate source
  provenance and shader-chain metadata. Run Windows tests, native/iOS
  compile checks and release audit before publishing an ordinary release
  from main. Retest the new IPA and BodiesOfTruth on device.

The official-first audit is a read-only provisional merge, not approval
of the resulting tree. No engine pin or published release changes until
integration has been reviewed and validated.
