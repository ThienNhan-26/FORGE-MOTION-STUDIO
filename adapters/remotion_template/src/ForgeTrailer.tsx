import React from "react";
import {
  AbsoluteFill,
  Composition,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

type ForgeProps = {
  title: string;
  subtitle: string;
  color1: string;
  color2: string;
};

const particles = Array.from({ length: 35 }, (_, i) => ({
  x: (i * 37) % 100,
  y: (i * 61) % 100,
  size: 2 + (i % 4),
  speed: 0.25 + (i % 5) * 0.12,
}));

export const ForgeTrailer: React.FC<ForgeProps> = ({
  title,
  subtitle,
  color1,
  color2,
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();

  const progress = frame / durationInFrames;
  const zoom = interpolate(frame, [0, durationInFrames], [1.08, 1]);
  const titleOpacity = interpolate(frame, [0, 18, 45], [0, 0.5, 1], {
    extrapolateRight: "clamp",
  });
  const titleY = interpolate(frame, [0, 45], [45, 0], {
    extrapolateRight: "clamp",
  });
  const subtitleOpacity = interpolate(frame, [35, 65], [0, 1], {
    extrapolateRight: "clamp",
  });
  const glowX = 20 + progress * 60;

  return (
    <AbsoluteFill
      style={{
        background: `linear-gradient(125deg, ${color1}, ${color2})`,
        color: "white",
        fontFamily: "Arial, sans-serif",
        overflow: "hidden",
      }}
    >
      <AbsoluteFill
        style={{
          transform: `scale(${zoom})`,
          background: `radial-gradient(ellipse at ${glowX}% 45%, rgba(150,120,255,0.32), transparent 48%)`,
        }}
      />

      {particles.map((p, i) => {
        const y = (p.y - frame * p.speed + 200) % 100;
        const opacity = 0.25 + 0.5 * Math.abs(Math.sin(frame / 25 + i));
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: `${p.x}%`,
              top: `${y}%`,
              width: p.size,
              height: p.size,
              borderRadius: "50%",
              background: "#ffffff",
              opacity,
              boxShadow: "0 0 12px rgba(180,190,255,0.9)",
            }}
          />
        );
      })}

      <AbsoluteFill
        style={{
          justifyContent: "center",
          alignItems: "center",
          transform: `scale(${zoom})`,
        }}
      >
        <div
          style={{
            textAlign: "center",
            opacity: titleOpacity,
            transform: `translateY(${titleY}px)`,
          }}
        >
          <div
            style={{
              fontSize: 76,
              fontWeight: 800,
              letterSpacing: 9,
              textShadow: "0 0 30px rgba(150,140,255,0.8)",
            }}
          >
            {title}
          </div>
          <div
            style={{
              marginTop: 24,
              fontSize: 23,
              letterSpacing: 7,
              color: "#d9d5ff",
              opacity: subtitleOpacity,
            }}
          >
            {subtitle}
          </div>
        </div>
      </AbsoluteFill>

      <div
        style={{
          position: "absolute",
          bottom: 70,
          left: "12%",
          width: "76%",
          height: 1,
          background: "rgba(255,255,255,0.45)",
          transform: `scaleX(${interpolate(frame, [0, 60], [0, 1], {
            extrapolateRight: "clamp",
          })})`,
          transformOrigin: "left",
        }}
      />
    </AbsoluteFill>
  );
};

export const ForgeComposition: React.FC = () => {
  return (
    <Composition
      id="ForgeTrailer"
      component={ForgeTrailer}
      durationInFrames={150}
      fps={30}
      width={1920}
      height={1080}
      defaultProps={{
        title: "THE LAST LIGHT",
        subtitle: "A FORGE AI PRODUCTION",
        color1: "#071426",
        color2: "#32145c",
      }}
    />
  );
};

