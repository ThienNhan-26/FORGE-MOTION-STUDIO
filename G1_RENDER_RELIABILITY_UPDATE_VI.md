# FORGE Motion Studio G1 — Render Reliability Update

## What changed

1. **Single camera owner**: `ThreeCanvas` no longer receives its own camera object while `SceneWorld` mounts a second default camera. The scene's `PerspectiveCamera` is declarative and derives position/rotation from Remotion's `useCurrentFrame()`-driven `cameraPose`.
2. **Frame-consistent scene animation**: scene transforms and camera pose continue to derive from `useCurrentFrame()`/`frame`; the implementation does not introduce a time-based `useFrame()` animation loop. Remotion documents `ThreeCanvas` as synchronizing React Three Fiber with `useCurrentFrame()` and recommends declarative frame-based animation.
3. **Render QA gate**: after rendering, FFprobe validates codec, dimensions, FPS, duration and frame count. FFmpeg decodes three frames; a near-uniform background-only result is rejected.
4. **QA report**: a JSON report is written beside each MP4 as `<task>_3d.qa.json`. A render can only return `SUCCESS` if the checks pass.
5. **Known-good probe retained**: `ThreeCanvasProbe` remains registered in `Root.tsx` as a control composition.

## Install / update

This is a source package, not a bundled Windows runtime. Extract it to a new folder first, or back up the existing project before replacing files. Keep your `.env` file outside the ZIP and copy it into the project root after extraction.

From PowerShell in the extracted project root:

```powershell
python -m pip install -r requirements.txt
.\scripts\setup.ps1
```

Then start the app using the project's normal run script. For a 3D mission, the adapter will render through Remotion and require `ffmpeg` and `ffprobe` to be on `PATH`.

## Important limitations

- This release improves the generic scene pipeline; Floating Island remains a showcase/test scene, not a hard-coded production path.
- Pixel QA detects blank or near-blank output. It does not certify that every requested object, action, or story detail is semantically correct. That belongs to the later autonomous Film QA stage.
- I verified the source transformation, Python syntax, ZIP integrity, and the QA gate with synthetic video fixtures in this environment. I did not run the full Remotion render inside the user's Windows installation, so the actual 3D scene result must still be confirmed on that machine.
