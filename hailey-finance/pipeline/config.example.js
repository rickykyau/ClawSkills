/**
 * Hailey Finance Pipeline Configuration
 * Copy this to config.js and fill in your credentials
 */

module.exports = {
  // ElevenLabs TTS
  elevenlabs: {
    apiKey: process.env.ELEVENLABS_API_KEY || 'your-elevenlabs-api-key',
    voiceId: 'hpp4J3VqNfWAUOO0d1Us', // Bella - Professional, Bright, Warm
    modelId: 'eleven_multilingual_v2',
  },

  // YouTube API (OAuth)
  youtube: {
    clientId: process.env.YOUTUBE_CLIENT_ID || 'your-client-id.apps.googleusercontent.com',
    clientSecret: process.env.YOUTUBE_CLIENT_SECRET || 'your-client-secret',
    refreshToken: process.env.YOUTUBE_REFRESH_TOKEN || 'your-refresh-token',
  },

  // Paths (relative to pipeline folder)
  paths: {
    remotion: '../remotion-videos',
    output: '../remotion-videos/out',
    public: '../remotion-videos/public',
    scripts: '../remotion-videos/scripts',
  },

  // Default video settings
  video: {
    width: 1080,
    height: 1920,
    fps: 30,
    codec: 'h264',
  },

  // YouTube defaults
  youtubeDefaults: {
    categoryId: '22', // People & Blogs (use '27' for Education)
    privacyStatus: 'public',
    defaultLanguage: 'en',
    tags: ['finance', 'investing', 'money'],
  },
};
