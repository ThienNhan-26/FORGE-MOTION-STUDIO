import React from 'react';
import { Composition, CalculateMetadataFunction, Series } from 'remotion';
import { SceneRenderer } from './SceneRenderer';
import { Scene3DComposition } from './Scene3DComposition';
import { ThreeCanvasProbe } from './ThreeCanvasProbe';
import type { Scene3DSpec } from '../../../motion_studio/shared/sceneTypes';

const MainComposition = ({ video }: any) => (
  <Series>
    {video.scenes.map((scene: any, index: number) => (
      <Series.Sequence key={index} durationInFrames={scene.duration_seconds * 30}>
        <SceneRenderer scene={scene} />
      </Series.Sequence>
    ))}
  </Series>
);

const calculateMetadata: CalculateMetadataFunction<any> = ({ props }) => {
  const fps = 30;
  const totalFrames = props.video?.scenes?.reduce((acc: number, scene: any) => acc + scene.duration_seconds * fps, 0) ?? 0;
  return { durationInFrames: totalFrames > 0 ? totalFrames : 150 };
};

const fallbackScene = {
  schema_version: 1,
  project_id: 'preview',
  title: 'Preview Scene',
  style: 'low_poly',
  width: 1920,
  height: 1080,
  fps: 30,
  duration_seconds: 18,
  environment: { background: '#a9d9e8', fog_color: '#a9d9e8', fog_near: 22, fog_far: 72, ambient_intensity: 1.2, sun_intensity: 2.3 },
  camera: { position: [10, 8, 13], end_position: [6.5, 5, 9], target: [0, 1.1, 0], end_target: [0, 1.3, 0], fov: 42, motion: 'push_in' },
  objects: [{ id: 'preview-island', name: 'Island', kind: 'island', position: [0, 1.35, 0], rotation: [0, 0, 0], scale: [2.6, 1.7, 2.6], color: '#6e8550', visible: true, animation: 'float' }],
} as unknown as Scene3DSpec;

const calculate3DMetadata: CalculateMetadataFunction<{ scene: Scene3DSpec }> = ({ props }) => ({
  durationInFrames: props.scene.duration_seconds * props.scene.fps,
  fps: props.scene.fps,
  width: props.scene.width,
  height: props.scene.height,
});

export const RemotionRoot = () => (
  <>
    <Composition
      id="DynamicVideo"
      component={MainComposition}
      fps={30}
      width={1920}
      height={1080}
      defaultProps={{ video: { scenes: [] } }}
      calculateMetadata={calculateMetadata}
    />
    <Composition
      id="ThreeCanvasProbe"
      component={ThreeCanvasProbe}
      fps={30}
      width={1920}
      height={1080}
      durationInFrames={30}
    />
    <Composition
      id="ThreeDScene"
      component={Scene3DComposition}
      fps={30}
      width={1920}
      height={1080}
      durationInFrames={540}
      defaultProps={{ scene: fallbackScene }}
      calculateMetadata={calculate3DMetadata}
    />
  </>
);
