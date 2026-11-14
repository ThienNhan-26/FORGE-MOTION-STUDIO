\# FORGE G1.3.1 — SCENE VALIDATOR 2.0

\## Technical Implementation Mission



\### 1. Mission Objective



Upgrade the existing Scene Validator into a reliable pre-render validation system for FORGE Motion Studio.



The validator must detect structural, camera-space, spatial, animation and composition issues in a Scene3DSpec before the rendering pipeline starts.



The implementation must preserve the existing Three.js + Remotion rendering pipeline and maintain backward compatibility with existing render consumers.



This is an incremental upgrade, NOT a rewrite of FORGE.



\### 2. Protected Components



Do not modify or replace these components unless a concrete dependency requires it and the change is explicitly justified:



\- Existing Planner, Coder, Reviewer and Coordinator.

\- Task Contract and Scheduler.

\- Permission Engine and Recovery Engine.

\- Skill Registry and Tool Dispatcher.

\- Existing Three.js scene rendering implementation.

\- Remotion composition and render pipeline.

\- Existing render QA implementation.

\- Existing successful regression project:

&#x20; `floating\_island\_scale\_test`



Do not overwrite its scene.json, MP4, validation report or QA report.



All new tests must use temporary test data or dedicated test fixtures.



\### 3. Files to Inspect Before Coding



Read the current implementation of:



\- contracts/scene3d.py

\- production/remotion/scene\_validator.py

\- production/remotion/three\_adapter.py

\- motion\_studio/shared/SceneWorld.tsx

\- motion\_studio/shared/sceneTypes.ts

\- skills/render\_3d\_scene/skill.py

\- tests/test\_scene\_validator.py

\- tests/test\_render\_qa.py



Confirm the actual camera near/far values, camera interpolation, orbit implementation, animation behavior and geometry definitions before changing validation logic.



Do not assume that the validator's geometry estimates are exact.



\### 4. Validation Architecture



Implement the following validation groups:



A. CONTRACT



\- Validate Scene3DSpec using the existing Pydantic contract.

\- Detect missing or invalid fields.

\- Detect invalid object IDs and unsupported object kinds.

\- Preserve the existing schema contract.

\- Do not duplicate Pydantic validation unnecessarily.



B. VISIBLE OBJECTS



\- Count visible and invisible objects.

\- Return a blocking error if there are no visible objects.

\- Preserve object-level visibility information.



C. CAMERA-SPACE VALIDATION



For each camera sample:



1\. Calculate camera position and target.

2\. Calculate the normalized forward vector:

&#x20;  forward = normalize(target - camera\_position)

3\. Calculate object center relative to camera:

&#x20;  relative = object\_center - camera\_position

4\. Calculate signed camera-space depth:

&#x20;  depth = dot(relative, forward)

5\. Estimate the object's bounding radius.

6\. Check near and far plane intersection using:

&#x20;  nearest\_depth = depth - radius

&#x20;  farthest\_depth = depth + radius



Rules:



\- An object entirely behind the camera must be reported.

\- An object intersecting the near plane must be reported.

\- An object entirely beyond the far plane must be reported.

\- An object partially intersecting a clipping plane must be reported distinctly.

\- Objects outside the camera frustum must not automatically become blocking errors.

\- Background and decorative objects may legitimately be outside the visible frustum.



D. CAMERA MOTION SAMPLING



Sample camera motion at:



\- 0%

\- 25%

\- 50%

\- 75%

\- 100%



Use the same interpolation and orbit behavior as SceneWorld.cameraPose().



The validator must not silently implement a different camera path.



For motion=none, duplicate samples may be optimized, but report the actual sampling policy.



E. SPATIAL VALIDATION



\- Estimate object bounding spheres from geometry definitions.

\- Apply object scale.

\- Include float animation displacement.

\- Include pulse animation scale variation.

\- Detect unusually large scale ratios.

\- Detect extreme object dimensions.

\- Detect possible camera/object bounding-sphere intersections.



Every approximate geometry check must be identified as approximate in the report.



Do not claim exact mesh collision detection.



F. ANIMATION VALIDATION



\- Check that animated objects have supported animation types.

\- Sample the expected animation displacement at relevant times where feasible.

\- Detect objects that may move outside expected camera bounds.

\- Do not reject a scene merely because an animated object temporarily leaves the frame.



G. COMPOSITION DIAGNOSTICS



Provide non-blocking diagnostics for:



\- No visible subject near the camera target.

\- Main subject potentially too small relative to camera distance.

\- Extreme scale disparity.

\- Excessive empty-space risk.

\- Objects distributed outside the camera framing region.



Do not claim pixel-perfect composition analysis. These are geometric estimates only.



\### 5. Validation Severity Model



Use three final statuses:



\- PASSED: no errors and no warnings.

\- PASSED\_WITH\_WARNINGS: no blocking errors, but one or more warnings exist.

\- FAILED: one or more blocking errors exist.



Maintain backward compatibility:



\- "passed": true when status is PASSED or PASSED\_WITH\_WARNINGS.

\- "passed": false only when status is FAILED.



Warnings must not cause render failure by default.



Blocking errors must prevent rendering.



Each diagnostic must include:



\- code

\- severity

\- message

\- object\_id when relevant

\- camera\_sample when relevant

\- measured\_value when relevant

\- expected\_value when relevant



Keep existing "errors", "warnings", "checks" fields where possible.



Add "status", "summary", "check\_details" and "metadata".



The meaning of every check must be documented. A warning-only condition must not make a check appear to be a blocking failure.



\### 6. Camera Configuration Consistency



The validator and Three.js runtime must use the same camera near/far values.



Inspect SceneWorld.tsx and determine the authoritative source.



Do not independently hardcode conflicting values in multiple modules.



If a shared configuration is needed, introduce the smallest compatible change.



Do not change the existing camera rendering behavior in this mission.



\### 7. Adapter Integration



Inspect the current ThreeRemotionAdapter integration.



Ensure:



1\. Scene validation runs before Remotion rendering.

2\. The validation report is written to the expected project render directory.

3\. FAILED stops rendering.

4\. PASSED and PASSED\_WITH\_WARNINGS permit rendering.

5\. Existing Render QA remains unchanged.

6\. Validation and QA reports are both preserved.

7\. Validation exceptions return a structured failure result.

8\. A report-writing failure is handled safely and does not falsely claim validation evidence was saved.



Do not weaken Render QA.



Do not silently convert a failed validation into a successful render.



\### 8. Required Validation Report Structure



Use this structure as the target contract. Extend it only when necessary:



{

&#x20; "schema\_version": 2,

&#x20; "status": "PASSED\_WITH\_WARNINGS",

&#x20; "passed": true,

&#x20; "errors": \[],

&#x20; "warnings": \[],

&#x20; "checks": {

&#x20;   "contract": true,

&#x20;   "visible\_objects": true,

&#x20;   "camera": true,

&#x20;   "spatial": true,

&#x20;   "animation": true,

&#x20;   "composition": true

&#x20; },

&#x20; "check\_details": {},

&#x20; "summary": {

&#x20;   "error\_count": 0,

&#x20;   "warning\_count": 1,

&#x20;   "blocking": false

&#x20; },

&#x20; "metadata": {

&#x20;   "project\_id": "example",

&#x20;   "object\_count": 0,

&#x20;   "visible\_object\_count": 0,

&#x20;   "camera\_motion": "none",

&#x20;   "camera\_samples": \[0.0, 0.25, 0.5, 0.75, 1.0],

&#x20;   "geometry\_bounds": "approximate"

&#x20; }

}



The example values are illustrative, not actual scene results.



\### 9. Required Tests



Create or update tests in tests/test\_scene\_validator.py.



At minimum test:



1\. Valid scene returns PASSED.

2\. Valid scene with warnings returns PASSED\_WITH\_WARNINGS.

3\. No visible objects returns FAILED.

4\. Invalid SceneSpec returns a validation failure.

5\. Object entirely behind camera is detected.

6\. Object beyond far plane is detected using camera-space depth.

7\. Object intersecting near plane is detected.

8\. Object outside frustum is not automatically blocking.

9\. Camera orbit samples include intermediate positions.

10\. Camera target too close is detected.

11\. Float animation displacement is included in estimated bounds.

12\. Pulse animation scale is included.

13\. Extreme object scale ratio produces a warning.

14\. Existing floating\_island\_scale\_test SceneSpec remains valid.

15\. Existing render QA tests remain unchanged and pass.



Tests must use controlled fixtures. Do not depend on an Ollama model or an actual MP4 render.



\### 10. Regression Verification



Run:



\- Python compilation for modified modules.

\- pytest tests/test\_scene\_validator.py

\- pytest tests/test\_render\_qa.py

\- Relevant existing core and render tests.

\- Existing project SceneSpec validation without modifying the project.

\- A controlled render regression only after unit tests pass.



The successful baseline project must remain untouched.



\### 11. Execution Constraints



\- Read before writing.

\- Plan before editing.

\- Modify only necessary files.

\- Do not regenerate scene.json.

\- Do not delete any project, model, database or workspace content.

\- Do not execute arbitrary PowerShell commands through agents.

\- Use the existing permission and workspace restrictions.

\- QA must execute tests and report actual exit codes.

\- Never report a test as passed unless it was actually executed.



\### 12. Final Deliverables



Return:



1\. Files inspected.

2\. Files modified.

3\. Technical explanation of each change.

4\. New validation report schema.

5\. Test execution evidence and exit codes.

6\. Regression test results.

7\. Known limitations.

8\. Confirmation that the original render baseline was preserved.



\### Definition of Done



G1.3.1 is complete only when:



\- Validator produces consistent statuses.

\- Camera-space checks work with intermediate motion samples.

\- Warning-only conditions do not block rendering.

\- Blocking conditions stop rendering.

\- Existing render QA remains intact.

\- All required automated tests pass.

\- Existing successful render baseline remains untouched.

