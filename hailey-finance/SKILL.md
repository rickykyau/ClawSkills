# Hailey Finance Video Pipeline

Create short-form finance videos with AI voiceover and animated slides.

## Overview

This skill automates the creation of finance/investment YouTube videos using:
- **ElevenLabs** for AI voice generation (or voice cloning)
- **Remotion** for animated slide videos
- **YouTube API** for automated uploads

No avatar needed - just voice + professional animated graphics.

## Pipeline Steps

1. **Write Script** → Topic + voiceover text + slide content
2. **Generate Voiceover** → ElevenLabs TTS with chosen voice
3. **Render Video** → Remotion animated slides synced to audio
4. **Upload to YouTube** → With SEO-optimized metadata

## Setup

### Prerequisites

```bash
# Node.js 18+
node --version

# ffmpeg (for audio processing)
ffmpeg -version
```

### Install Dependencies

```bash
cd hailey-finance/remotion-videos
npm install
```

### Configuration

Create `pipeline/config.js`:

```javascript
module.exports = {
  elevenlabs: {
    apiKey: process.env.ELEVENLABS_API_KEY || 'your-api-key',
    voiceId: 'hpp4J3VqNfWAUOO0d1Us', // Bella (or your cloned voice)
  },
  youtube: {
    clientId: process.env.YOUTUBE_CLIENT_ID,
    clientSecret: process.env.YOUTUBE_CLIENT_SECRET,
    refreshToken: process.env.YOUTUBE_REFRESH_TOKEN,
  },
};
```

### YouTube OAuth Setup

```bash
node pipeline/youtube-auth.js
# Follow browser prompts to authorize
```

## Usage

### Quick Start

```bash
# Generate voiceover from text
node pipeline/generate-voiceover.js \
  --text "Your script here..." \
  --output remotion-videos/public/audio.mp3

# Create script with slide timings
# Edit remotion-videos/scripts/video.json

# Render video
cd remotion-videos
npx remotion render VoiceoverVideo out/video.mp4

# Upload to YouTube
node pipeline/youtube-upload.js \
  --file out/video.mp4 \
  --title "Your Title" \
  --description "Your description"
```

### Script Format

```json
{
  "audioFile": "audio.mp3",
  "totalDuration": 60,
  "slides": [
    {
      "text": "Welcome!",
      "type": "title",
      "startTime": 0,
      "endTime": 3
    },
    {
      "text": "$5 BILLION",
      "highlight": "$5B",
      "type": "number",
      "startTime": 3,
      "endTime": 8
    },
    {
      "text": "Key insight here",
      "subtext": "Supporting detail",
      "type": "point",
      "startTime": 8,
      "endTime": 15
    }
  ]
}
```

### Slide Types

- **title** - Large centered headline
- **point** - Main text with optional subtext
- **number** - Big highlighted number with context
- **quote** - Styled quote with attribution
- **outro** - Call to action / subscribe

## ElevenLabs Voice Options

### Pre-made Voices
- `hpp4J3VqNfWAUOO0d1Us` - Bella (Professional, Bright, Warm)
- Many others available in ElevenLabs library

### Voice Cloning
1. Record 1-3 minutes of clean audio
2. Upload to ElevenLabs → Voices → Add Voice → Instant Clone
3. Copy the new Voice ID to config

### Credits Math
- Starter ($5/mo): 30,000 chars ≈ 40 min audio
- Creator ($22/mo): 100,000 chars ≈ 130 min audio
- 60-sec video ≈ 750 characters

## Customization

### Branding

Edit `remotion-videos/src/styles/brand.ts`:
- Colors (gold, cream, backgrounds)
- Fonts
- Logo/avatar
- Footer handle

### Video Dimensions

Default: 1080x1920 (YouTube Shorts / TikTok / Reels)

For landscape, update composition in `Root.tsx`:
```typescript
width={1920}
height={1080}
```

## Troubleshooting

### Audio not playing in preview
- Ensure audio file is in `public/` folder
- Check file path in script JSON matches

### Slides out of sync
- Verify `startTime` and `endTime` match audio timing
- Use ffprobe to check audio duration: `ffprobe -v error -show_entries format=duration audio.mp3`

### YouTube upload fails
- Re-run `youtube-auth.js` to refresh token
- Check API quota in Google Cloud Console
