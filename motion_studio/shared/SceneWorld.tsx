import React, { Fragment, useMemo } from 'react';
import { OrbitControls, PerspectiveCamera as DreiPerspectiveCamera } from '@react-three/drei';
import { Euler, PerspectiveCamera as ThreePerspectiveCamera, Vector3 } from 'three';
import type { Scene3DSpec, SceneObjectSpec, Vec3 } from './sceneTypes';

type Props = {
  scene: Scene3DSpec;
  frame?: number;
  interactive?: boolean;
  selectedObjectId?: string | null;
  onObjectSelect?: (id: string) => void;
  resetToken?: number;
};

const lerp3 = (a: Vec3, b: Vec3, t: number): Vec3 => [
  a[0] + (b[0] - a[0]) * t,
  a[1] + (b[1] - a[1]) * t,
  a[2] + (b[2] - a[2]) * t,
];

function cameraPose(scene: Scene3DSpec, frame: number): { position: Vec3; target: Vec3; rotation: Vec3 } {
  const totalFrames = Math.max(1, scene.duration_seconds * scene.fps - 1);
  const raw = Math.min(1, Math.max(0, frame / totalFrames));
  const t = raw * raw * (3 - 2 * raw);
  let position = scene.camera.motion === 'none'
    ? scene.camera.position
    : lerp3(scene.camera.position, scene.camera.end_position, t);
  const target = scene.camera.motion === 'none'
    ? scene.camera.target
    : lerp3(scene.camera.target, scene.camera.end_target, t);
  if (scene.camera.motion === 'orbit') {
    const relative = new Vector3(position[0] - target[0], position[1] - target[1], position[2] - target[2]);
    relative.applyAxisAngle(new Vector3(0, 1, 0), raw * 1.35);
    position = [target[0] + relative.x, target[1] + relative.y, target[2] + relative.z];
  }
  const looker = new ThreePerspectiveCamera();
  looker.position.set(...position);
  looker.lookAt(...target);
  const rotation = new Euler(looker.rotation.x, looker.rotation.y, looker.rotation.z, 'XYZ');
  return { position, target, rotation: [rotation.x, rotation.y, rotation.z] };
}

function animatedTransform(object: SceneObjectSpec, frame: number, fps: number) {
  const seconds = frame / fps;
  const position: Vec3 = [...object.position];
  const rotation: Vec3 = [...object.rotation];
  const scale: Vec3 = [...object.scale];
  if (object.animation === 'float') position[1] += Math.sin(seconds * 1.45 + object.id.length * 0.7) * 0.14;
  if (object.animation === 'rotate') rotation[1] += seconds * 0.35;
  if (object.animation === 'pulse') {
    const pulse = 1 + Math.sin(seconds * 2.2) * 0.055;
    scale[0] *= pulse; scale[1] *= pulse; scale[2] *= pulse;
  }
  return { position, rotation, scale };
}

const StandardMaterial = ({ color, roughness = 0.92 }: { color: string; roughness?: number }) => (
  <meshStandardMaterial color={color} roughness={roughness} flatShading />
);

function ObjectGeometry({ object }: { object: SceneObjectSpec }) {
  switch (object.kind) {
    case 'island':
      return (
        <>
          <mesh castShadow receiveShadow position={[0, -0.05, 0]} scale={[1.0, 0.62, 1.0]}>
            <dodecahedronGeometry args={[1.48, 0]} /><StandardMaterial color={object.color} />
          </mesh>
          <mesh castShadow receiveShadow position={[0, 0.56, 0]}>
            <cylinderGeometry args={[1.36, 1.5, 0.26, 9, 1]} /><StandardMaterial color="#82a95c" />
          </mesh>
          <mesh castShadow position={[0, -0.82, 0]} rotation={[0, 0.1, Math.PI]}>
            <coneGeometry args={[1.18, 1.48, 8, 1]} /><StandardMaterial color="#687b75" />
          </mesh>
          <mesh castShadow position={[-0.55, -1.38, 0.16]} rotation={[0.1, 0.3, 0.15]} scale={[0.34, 0.52, 0.3]}>
            <dodecahedronGeometry args={[1, 0]} /><StandardMaterial color="#586c70" />
          </mesh>
          <mesh castShadow position={[0.56, -1.2, -0.14]} rotation={[0.2, 0.4, 0.1]} scale={[0.4, 0.58, 0.35]}>
            <dodecahedronGeometry args={[1, 0]} /><StandardMaterial color="#71817b" />
          </mesh>
          <mesh position={[0.82, -0.18, 0.56]} rotation={[0.1, 0.2, -0.32]}>
            <boxGeometry args={[0.18, 0.9, 0.12]} /><meshStandardMaterial color="#54b7d2" roughness={0.2} metalness={0.1} />
          </mesh>
        </>
      );
    case 'tree':
    case 'pine':
      return (
        <>
          <mesh castShadow position={[0, 0.45, 0]}><cylinderGeometry args={[0.12, 0.17, 0.95, 6]} /><StandardMaterial color="#876044" /></mesh>
          <mesh castShadow position={[0, 1.0, 0]}><coneGeometry args={[0.58, 0.9, 7]} /><StandardMaterial color={object.color} /></mesh>
          <mesh castShadow position={[0, 1.52, 0]}><coneGeometry args={[0.43, 0.76, 7]} /><StandardMaterial color={object.color} /></mesh>
          {object.kind === 'pine' && <mesh castShadow position={[0, 1.98, 0]}><coneGeometry args={[0.27, 0.64, 7]} /><StandardMaterial color={object.color} /></mesh>}
        </>
      );
    case 'house':
      return (
        <>
          <mesh castShadow position={[0, 0.43, 0]}><boxGeometry args={[1.2, 0.82, 0.92]} /><StandardMaterial color={object.color} /></mesh>
          <mesh castShadow position={[0, 1.04, 0]} rotation={[0, Math.PI / 4, 0]}><coneGeometry args={[0.88, 0.72, 4]} /><StandardMaterial color="#a85f4b" /></mesh>
          <mesh position={[0.27, 0.36, 0.466]}><boxGeometry args={[0.22, 0.42, 0.035]} /><meshStandardMaterial color="#654d3d" /></mesh>
          <mesh position={[-0.29, 0.55, 0.47]}><boxGeometry args={[0.22, 0.22, 0.035]} /><meshStandardMaterial color="#7fc8d7" emissive="#17404b" /></mesh>
        </>
      );
    case 'cloud':
      return (
        <>
          <mesh position={[-0.48, 0, 0]} scale={[0.72, 0.5, 0.55]}><sphereGeometry args={[1, 9, 7]} /><StandardMaterial color={object.color} /></mesh>
          <mesh position={[0.05, 0.2, 0]} scale={[0.75, 0.68, 0.62]}><sphereGeometry args={[1, 9, 7]} /><StandardMaterial color={object.color} /></mesh>
          <mesh position={[0.58, 0, 0.04]} scale={[0.68, 0.47, 0.54]}><sphereGeometry args={[1, 9, 7]} /><StandardMaterial color={object.color} /></mesh>
        </>
      );
    case 'rock':
      return <mesh castShadow receiveShadow><dodecahedronGeometry args={[1, 0]} /><StandardMaterial color={object.color} /></mesh>;
    case 'crystal':
      return (
        <>
          <mesh castShadow><octahedronGeometry args={[1, 0]} /><meshStandardMaterial color={object.color} roughness={0.18} metalness={0.28} emissive={object.color} emissiveIntensity={0.14} /></mesh>
          <mesh position={[0, -0.55, 0]} scale={[0.8, 0.3, 0.8]}><cylinderGeometry args={[0.36, 0.48, 0.3, 6]} /><meshStandardMaterial color="#91bdc1" metalness={0.12} /></mesh>
        </>
      );
    case 'sphere':
      return <mesh castShadow><icosahedronGeometry args={[0.8, 1]} /><StandardMaterial color={object.color} /></mesh>;
    case 'cube':
    default:
      return <mesh castShadow><boxGeometry args={[1, 1, 1]} /><StandardMaterial color={object.color} /> </mesh>;
  }
}

function SceneObject({ object, frame, fps, selected, interactive, onSelect }: {
  object: SceneObjectSpec; frame: number; fps: number; selected: boolean; interactive: boolean; onSelect?: (id: string) => void;
}) {
  const transform = useMemo(() => animatedTransform(object, frame, fps), [object, frame, fps]);
  const handleClick = (event: any) => {
    if (!interactive || !onSelect) return;
    event.stopPropagation();
    onSelect(object.id);
  };
  return (
    <group position={transform.position} rotation={transform.rotation} scale={transform.scale}
      visible={object.visible} onClick={handleClick}>
      <ObjectGeometry object={object} />
      {selected && interactive && (
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.04, 0]}>
          <ringGeometry args={[1.18, 1.24, 36]} />
          <meshBasicMaterial color="#6ee7f9" transparent opacity={0.95} />
        </mesh>
      )}
    </group>
  );
}

/* FORGE_SINGLE_CAMERA_OWNER_V1 */
export function SceneWorld({ scene, frame = 0, interactive = false, selectedObjectId = null, onObjectSelect, resetToken = 0 }: Props) {
  const pose = useMemo(() => cameraPose(scene, frame), [scene, frame]);
  return (
    <>
      <color attach="background" args={[scene.environment.background]} />
      <fog attach="fog" args={[scene.environment.fog_color, scene.environment.fog_near, scene.environment.fog_far]} />
      <ambientLight intensity={scene.environment.ambient_intensity} />
      <hemisphereLight args={['#e7f8ff', '#55715a', 0.72]} />
      <directionalLight castShadow position={[7, 12, 7]} intensity={scene.environment.sun_intensity} shadow-mapSize-width={2048} shadow-mapSize-height={2048} />
      <directionalLight position={[-8, 3, -6]} intensity={0.55} color="#9bdcf0" />
      <DreiPerspectiveCamera key={`camera-${resetToken}`} makeDefault fov={scene.camera.fov} position={pose.position} rotation={pose.rotation} near={0.1} far={300} />
      {interactive && <OrbitControls key={`controls-${resetToken}`} makeDefault target={pose.target} enableDamping dampingFactor={0.08} minDistance={3} maxDistance={35} />}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -3.9, 0]} receiveShadow>
        <circleGeometry args={[100, 64]} /><meshStandardMaterial color="#a9cbd4" roughness={1} />
      </mesh>
      {scene.objects.map((object) => (
        <Fragment key={object.id}>
          <SceneObject object={object} frame={frame} fps={scene.fps} selected={selectedObjectId === object.id}
            interactive={interactive} onSelect={onObjectSelect} />
        </Fragment>
      ))}
    </>
  );
}
