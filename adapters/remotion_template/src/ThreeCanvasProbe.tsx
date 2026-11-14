import React from 'react';
import { ThreeCanvas } from '@remotion/three';
import { AbsoluteFill, useVideoConfig } from 'remotion';

/** Isolated diagnostic: no FORGE SceneWorld, no imported camera, no scene JSON. */
export const ThreeCanvasProbe: React.FC = () => {
  const { width, height } = useVideoConfig();
  return (
    <AbsoluteFill style={{ backgroundColor: '#172033' }}>
      <ThreeCanvas
        width={width}
        height={height}
        camera={{ position: [0, 0, 6], fov: 50 }}
        style={{ backgroundColor: '#172033' }}
      >
        <ambientLight intensity={0.8} />
        <directionalLight position={[4, 6, 5]} intensity={2} />
        <mesh rotation={[0.45, 0.65, 0]}>
          <boxGeometry args={[2, 2, 2]} />
          <meshStandardMaterial color="#ff7a36" roughness={0.55} />
        </mesh>
      </ThreeCanvas>
    </AbsoluteFill>
  );
};
