import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig, random } from 'remotion';

const ParticleLayer = ({ color }: { color: string }) => {
  const frame = useCurrentFrame();
  const particles = new Array(30).fill(0).map((_, i) => {
    const x = random(`x-${i}`) * 1920;
    const y = (random(`y-${i}`) * 1080 + frame * 2) % 1080;
    return <div key={i} style={{ position: 'absolute', left: x, top: y, width: 4, height: 4, backgroundColor: color, borderRadius: '50%', boxShadow: `0 0 10px ${color}` }} />;
  });
  return <>{particles}</>;
};

const TextLayer = ({ content, color }: { content: string, color: string }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const opacity = interpolate(frame, [0, 20, durationInFrames - 20, durationInFrames], [0, 1, 1, 0]);
  return <h1 style={{ fontSize: 120, color, opacity, margin: 0, fontFamily: 'sans-serif', textShadow: '0 0 30px rgba(0,0,0,0.8)' }}>{content}</h1>;
};

export const SceneRenderer = ({ scene }: any) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();

  let scale = 1, translateX = 0;
  if (scene.camera_motion === 'zoom_in') scale = interpolate(frame, [0, durationInFrames], [1, 1.2]);
  if (scene.camera_motion === 'zoom_out') scale = interpolate(frame, [0, durationInFrames], [1.2, 1]);
  if (scene.camera_motion === 'pan_left') translateX = interpolate(frame, [0, durationInFrames], [0, -200]);
  if (scene.camera_motion === 'pan_right') translateX = interpolate(frame, [0, durationInFrames], [0, 200]);

  return (
    <AbsoluteFill style={{ background: `linear-gradient(45deg, ${scene.bg_color1}, ${scene.bg_color2})`, overflow: 'hidden' }}>
      <AbsoluteFill style={{ transform: `scale(${scale}) translateX(${translateX}px)`, justifyContent: 'center', alignItems: 'center' }}>
        {scene.layers.map((layer: any, index: number) => {
          if (layer.type === 'particles') return <ParticleLayer key={index} color={layer.color} />;
          if (layer.type === 'text') return <TextLayer key={index} content={layer.content} color={layer.color} />;
          return null;
        })}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};