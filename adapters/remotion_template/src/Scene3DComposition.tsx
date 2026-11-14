import React from 'react';
import { ThreeCanvas } from '@remotion/three';
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion';
import { SceneWorld } from '../../../motion_studio/shared/SceneWorld';
import type { Scene3DSpec } from '../../../motion_studio/shared/sceneTypes';

export const Scene3DComposition: React.FC<{ scene: Scene3DSpec }> = ({ scene }) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  return (
    <AbsoluteFill style={{ backgroundColor: scene.environment.background }}>
      <ThreeCanvas
        width={width}
        height={height}
        style={{ backgroundColor: scene.environment.background }}
        shadows
      >
        <SceneWorld scene={scene} frame={frame} interactive={false} />
      </ThreeCanvas>
    </AbsoluteFill>
  );
};
