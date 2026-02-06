import { Composition } from "remotion";
import { VoiceoverVideo } from "./videos/VoiceoverVideo";

// Import your script here (or load dynamically)
// import script from "../scripts/your-video.json";

// Example script for testing
const exampleScript = {
  audioFile: "example.mp3",
  totalDuration: 15,
  slides: [
    {
      text: "Welcome to Hailey Finance",
      type: "title" as const,
      startTime: 0,
      endTime: 4,
    },
    {
      text: "Today's Topic",
      subtext: "Finance made simple",
      type: "point" as const,
      startTime: 4,
      endTime: 10,
    },
    {
      text: "Subscribe!",
      subtext: "Hit that bell 🔔",
      type: "outro" as const,
      startTime: 10,
      endTime: 15,
    },
  ],
};

export const RemotionRoot: React.FC = () => {
  const fps = 30;
  const durationInFrames = Math.ceil(exampleScript.totalDuration * fps);

  return (
    <>
      <Composition
        id="VoiceoverVideo"
        component={VoiceoverVideo}
        durationInFrames={durationInFrames}
        fps={fps}
        width={1080}
        height={1920}
        defaultProps={{
          script: exampleScript,
        }}
      />
    </>
  );
};
