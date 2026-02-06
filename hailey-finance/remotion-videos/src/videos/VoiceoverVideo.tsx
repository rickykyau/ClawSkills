import { AbsoluteFill, Audio, staticFile, useCurrentFrame, useVideoConfig, Sequence, interpolate, Img } from "remotion";
import { brandStyles, colors } from "../styles/brand";

interface Slide {
  text: string;
  subtext?: string;
  highlight?: string;
  startTime: number;
  endTime: number;
  type?: "title" | "point" | "number" | "quote" | "outro";
}

interface VoiceoverScript {
  audioFile: string;
  slides: Slide[];
  totalDuration: number;
}

interface Props {
  script: VoiceoverScript;
}

const SlideContent: React.FC<{ slide: Slide; frame: number; fps: number; durationInFrames: number }> = ({ 
  slide, 
  frame, 
  fps,
  durationInFrames 
}) => {
  const fadeIn = interpolate(frame, [0, fps * 0.3], [0, 1], { extrapolateRight: "clamp" });
  const slideUp = interpolate(frame, [0, fps * 0.3], [30, 0], { extrapolateRight: "clamp" });
  const fadeOut = interpolate(
    frame, 
    [durationInFrames - fps * 0.3, durationInFrames], 
    [1, 0], 
    { extrapolateLeft: "clamp" }
  );
  const opacity = Math.min(fadeIn, fadeOut);

  const baseStyle = {
    display: "flex",
    flexDirection: "column" as const,
    alignItems: "center",
    justifyContent: "center",
    textAlign: "center" as const,
    padding: 48,
    opacity,
    transform: `translateY(${slideUp}px)`,
  };

  if (slide.type === "title") {
    return (
      <div style={baseStyle}>
        <h1 style={{
          fontSize: 64,
          fontWeight: 800,
          color: colors.haileyGold,
          textShadow: "0 4px 20px rgba(0,0,0,0.5)",
          lineHeight: 1.2,
          margin: 0,
        }}>
          {slide.text}
        </h1>
        {slide.subtext && (
          <p style={{
            fontSize: 32,
            color: colors.textWhite,
            marginTop: 24,
            opacity: 0.9,
          }}>
            {slide.subtext}
          </p>
        )}
      </div>
    );
  }

  if (slide.type === "number") {
    return (
      <div style={baseStyle}>
        {slide.highlight && (
          <span style={{
            fontSize: 120,
            fontWeight: 900,
            color: colors.haileyGold,
            textShadow: "0 4px 30px rgba(212,175,55,0.4)",
            marginBottom: 16,
          }}>
            {slide.highlight}
          </span>
        )}
        <p style={{
          fontSize: 40,
          fontWeight: 600,
          color: colors.textWhite,
          lineHeight: 1.4,
          margin: 0,
        }}>
          {slide.text}
        </p>
      </div>
    );
  }

  if (slide.type === "quote") {
    return (
      <div style={baseStyle}>
        <span style={{ fontSize: 80, color: colors.haileyGold, opacity: 0.5 }}>"</span>
        <p style={{
          fontSize: 36,
          fontWeight: 500,
          color: colors.textWhite,
          fontStyle: "italic",
          lineHeight: 1.5,
          maxWidth: 800,
          margin: 0,
        }}>
          {slide.text}
        </p>
        {slide.subtext && (
          <p style={{ fontSize: 24, color: colors.haileyGold, marginTop: 24 }}>
            — {slide.subtext}
          </p>
        )}
      </div>
    );
  }

  if (slide.type === "outro") {
    return (
      <div style={baseStyle}>
        <p style={{
          fontSize: 48,
          fontWeight: 700,
          color: colors.haileyGold,
          marginBottom: 24,
        }}>
          {slide.text}
        </p>
        {slide.subtext && (
          <p style={{
            fontSize: 32,
            color: colors.textWhite,
            opacity: 0.9,
          }}>
            {slide.subtext}
          </p>
        )}
      </div>
    );
  }

  // Default: point style
  return (
    <div style={baseStyle}>
      {slide.highlight && (
        <span style={{
          fontSize: 72,
          fontWeight: 800,
          color: colors.haileyGold,
          marginBottom: 16,
        }}>
          {slide.highlight}
        </span>
      )}
      <p style={{
        fontSize: 44,
        fontWeight: 600,
        color: colors.textWhite,
        lineHeight: 1.4,
        maxWidth: 900,
        margin: 0,
      }}>
        {slide.text}
      </p>
      {slide.subtext && (
        <p style={{
          fontSize: 28,
          color: colors.haileyCream,
          marginTop: 20,
          opacity: 0.85,
        }}>
          {slide.subtext}
        </p>
      )}
    </div>
  );
};

export const VoiceoverVideo: React.FC<Props> = ({ script }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  return (
    <AbsoluteFill style={brandStyles.container}>
      {/* Background */}
      <AbsoluteFill style={{
        background: `linear-gradient(180deg, ${colors.bgDark} 0%, ${colors.bgDarker} 100%)`,
      }} />

      {/* Header */}
      <div style={{ ...brandStyles.headerBar, zIndex: 10 }}>
        <span style={brandStyles.brandName}>Hailey Finance</span>
        <Img src={staticFile("avatar.png")} style={brandStyles.avatar} />
      </div>

      {/* Slides */}
      {script.slides.map((slide, index) => {
        const startFrame = slide.startTime * fps;
        const endFrame = slide.endTime * fps;
        const durationInFrames = endFrame - startFrame;
        
        return (
          <Sequence key={index} from={startFrame} durationInFrames={durationInFrames}>
            <AbsoluteFill style={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
              <SlideContent 
                slide={slide} 
                frame={frame - startFrame} 
                fps={fps}
                durationInFrames={durationInFrames}
              />
            </AbsoluteFill>
          </Sequence>
        );
      })}

      {/* Audio */}
      <Audio src={staticFile(script.audioFile)} />

      {/* Footer */}
      <div style={{ ...brandStyles.footer, zIndex: 10 }}>
        <span style={brandStyles.footerHandle}>@YourHandle</span>
      </div>
    </AbsoluteFill>
  );
};
