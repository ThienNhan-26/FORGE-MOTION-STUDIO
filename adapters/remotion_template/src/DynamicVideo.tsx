import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from 'remotion';

export const DynamicVideo = ({ title, subtitle, color1, color2 }: any) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const scale = interpolate(frame, [0, durationInFrames], [1, 1.1]);
  const opacity = interpolate(frame, [0, 30, 60, 90], [0, 1, 1, 0]);

  return (
    <AbsoluteFill style={{ background: `linear-gradient(45deg, ${color1}, ${color2})`, justifyContent: 'center', alignItems: 'center', color: 'white', fontFamily: 'sans-serif' }}>
      <div style={{ transform: `scale(${scale})`, textAlign: 'center' }}>
        <h1 style={{ fontSize: 120, opacity, margin: 0, textShadow: '0 0 30px rgba(0,0,0,0.8)' }}>{title}</h1>
        <h2 style={{ fontSize: 50, color: '#ccc', opacity, marginTop: 20 }}>{subtitle}</h2>
      </div>
    </AbsoluteFill>
  );
};