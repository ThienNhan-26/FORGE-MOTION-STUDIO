# G1 release validation report

## Passed in this environment
- Python source compilation: `compileall` passed for `production/` and `tests/`.
- Existing FORGE core suite: 11/11 tests passed.
- New render QA suite: 2/2 tests passed.
- QA regression: a synthetic solid-color MP4 was rejected; a synthetic patterned MP4 passed.
- Previously supplied failing MP4 (`motion-37a5faf33063_3d.mp4`): FFprobe metadata passed (1920x1080, 30 FPS, 18.0 s, 540 frames), but sampled image content failed. Two decoded samples had luma min=max=204.47, standard deviation 0, and zero detected edges.
- Update script: applied to an isolated copy of the supplied source tree, converged exactly to the release files, and a second run reported no changes.
- Both ZIP archives passed integrity checks.

## Not verified here
- The full Remotion/TypeScript bundle was not built in this environment because `npm ci` did not complete before the command timeout.
- A new Floating Island MP4 was not rendered on the user's Windows installation. The camera ownership change is based on the inspected source structure and Remotion's declarative `ThreeCanvas` model; final render confirmation still requires the Windows environment.

## Scope
This is a G1 rendering reliability update, not a claim that the full autonomous multi-style film studio is complete. Floating Island remains a demonstration scene; the project structure and `SceneSpec` pipeline remain reusable for different scenes. Pixel QA is a blank-frame guard, not semantic verification of all scene content.
