export type Vec3 = [number, number, number];
export type ObjectKind = 'island' | 'tree' | 'pine' | 'house' | 'cloud' | 'rock' | 'crystal' | 'cube' | 'sphere';
export type ObjectAnimation = 'none' | 'float' | 'rotate' | 'pulse';

export interface SceneObjectSpec {
  id: string;
  name: string;
  kind: ObjectKind;
  position: Vec3;
  rotation: Vec3;
  scale: Vec3;
  color: string;
  visible: boolean;
  animation: ObjectAnimation;
}

export interface Scene3DSpec {
  schema_version: 1;
  project_id: string;
  title: string;
  style: 'low_poly';
  width: number;
  height: number;
  fps: number;
  duration_seconds: number;
  environment: {
    background: string;
    fog_color: string;
    fog_near: number;
    fog_far: number;
    ambient_intensity: number;
    sun_intensity: number;
  };
  camera: {
    position: Vec3;
    end_position: Vec3;
    target: Vec3;
    end_target: Vec3;
    fov: number;
    motion: 'none' | 'push_in' | 'orbit';
  };
  objects: SceneObjectSpec[];
}

export const OBJECT_PRESETS: Record<ObjectKind, Omit<SceneObjectSpec, 'id'>> = {
  island: { name: 'Floating island', kind: 'island', position: [0, 1.35, 0], rotation: [0, 0, 0], scale: [2.6, 1.7, 2.6], color: '#6e8550', visible: true, animation: 'float' },
  tree: { name: 'Tree', kind: 'tree', position: [0, 2.1, 0], rotation: [0, 0, 0], scale: [0.65, 0.8, 0.65], color: '#3d865c', visible: true, animation: 'none' },
  pine: { name: 'Pine tree', kind: 'pine', position: [0, 2.2, 0], rotation: [0, 0, 0], scale: [0.65, 0.85, 0.65], color: '#347a61', visible: true, animation: 'none' },
  house: { name: 'Cottage', kind: 'house', position: [0, 2.1, 0], rotation: [0, 0, 0], scale: [0.7, 0.7, 0.7], color: '#ecd5aa', visible: true, animation: 'none' },
  cloud: { name: 'Cloud', kind: 'cloud', position: [3.5, 2.5, -2.5], rotation: [0, 0, 0], scale: [1.2, 0.7, 0.8], color: '#ffffff', visible: true, animation: 'float' },
  rock: { name: 'Rock', kind: 'rock', position: [0, 0, 0], rotation: [0, 0, 0], scale: [0.7, 0.5, 0.7], color: '#71808d', visible: true, animation: 'none' },
  crystal: { name: 'Crystal', kind: 'crystal', position: [0, 3, 0], rotation: [0, 0, 0], scale: [0.35, 0.8, 0.35], color: '#82e8e0', visible: true, animation: 'pulse' },
  cube: { name: 'Cube', kind: 'cube', position: [0, 2, 0], rotation: [0, 0, 0], scale: [1, 1, 1], color: '#74a4c4', visible: true, animation: 'none' },
  sphere: { name: 'Sphere', kind: 'sphere', position: [0, 2, 0], rotation: [0, 0, 0], scale: [0.8, 0.8, 0.8], color: '#82b8c7', visible: true, animation: 'none' },
};
