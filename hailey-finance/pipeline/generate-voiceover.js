#!/usr/bin/env node
/**
 * Generate voiceover using ElevenLabs
 * 
 * Usage: 
 *   node generate-voiceover.js --text "Hello world" --output audio.mp3
 *   node generate-voiceover.js --script script.json --output audio.mp3
 */

const fs = require('fs');
const path = require('path');
const https = require('https');
const { execSync } = require('child_process');

// Load config
let config;
try {
  config = require('./config');
} catch (e) {
  console.error('❌ Missing config.js - copy config.example.js to config.js and add credentials');
  process.exit(1);
}

const ELEVENLABS_API_KEY = config.elevenlabs.apiKey;
const DEFAULT_VOICE_ID = config.elevenlabs.voiceId;
const MODEL_ID = config.elevenlabs.modelId || 'eleven_multilingual_v2';

async function generateVoiceover(text, outputPath, voiceId = DEFAULT_VOICE_ID) {
  return new Promise((resolve, reject) => {
    const postData = JSON.stringify({
      text: text,
      model_id: MODEL_ID,
      voice_settings: {
        stability: 0.5,
        similarity_boost: 0.75,
        style: 0.3,
        use_speaker_boost: true
      }
    });

    const options = {
      hostname: 'api.elevenlabs.io',
      port: 443,
      path: `/v1/text-to-speech/${voiceId}`,
      method: 'POST',
      headers: {
        'Accept': 'audio/mpeg',
        'xi-api-key': ELEVENLABS_API_KEY,
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(postData),
      },
    };

    console.log('  Sending to ElevenLabs...');
    
    const req = https.request(options, (res) => {
      if (res.statusCode !== 200) {
        let error = '';
        res.on('data', chunk => error += chunk);
        res.on('end', () => reject(new Error(`ElevenLabs error ${res.statusCode}: ${error}`)));
        return;
      }

      const chunks = [];
      res.on('data', chunk => chunks.push(chunk));
      res.on('end', () => {
        const audioBuffer = Buffer.concat(chunks);
        fs.writeFileSync(outputPath, audioBuffer);
        console.log(`  ✅ Audio saved: ${outputPath} (${(audioBuffer.length / 1024).toFixed(1)} KB)`);
        resolve(outputPath);
      });
    });

    req.on('error', reject);
    req.write(postData);
    req.end();
  });
}

function getAudioDuration(filePath) {
  try {
    const result = execSync(
      `ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "${filePath}"`,
      { encoding: 'utf-8' }
    );
    return parseFloat(result.trim());
  } catch (e) {
    console.warn('  ⚠️ Could not get duration (ffprobe not available)');
    return null;
  }
}

async function main() {
  const args = process.argv.slice(2);
  
  const getArg = (flag) => {
    const idx = args.indexOf(flag);
    return idx !== -1 ? args[idx + 1] : null;
  };

  const text = getArg('--text');
  const scriptPath = getArg('--script');
  const outputPath = getArg('--output');
  const voiceId = getArg('--voice') || DEFAULT_VOICE_ID;

  if (!outputPath) {
    console.log('Usage:');
    console.log('  node generate-voiceover.js --text "Your text" --output audio.mp3');
    console.log('  node generate-voiceover.js --script script.json --output audio.mp3');
    console.log('');
    console.log('Options:');
    console.log('  --voice <id>  Use specific ElevenLabs voice ID');
    process.exit(1);
  }

  console.log('🎙️ Generating voiceover...');

  let fullText;
  
  if (text) {
    fullText = text;
  } else if (scriptPath) {
    const script = JSON.parse(fs.readFileSync(scriptPath, 'utf-8'));
    if (script.voiceoverText) {
      fullText = script.voiceoverText;
    } else if (script.slides) {
      fullText = script.slides.map(s => s.voiceover || s.text).join(' ');
    } else {
      throw new Error('Script must have voiceoverText or slides with text');
    }
  } else {
    throw new Error('Must provide --text or --script');
  }

  console.log(`  Text: "${fullText.substring(0, 50)}${fullText.length > 50 ? '...' : ''}"`);
  console.log(`  Characters: ${fullText.length}`);
  console.log(`  Voice ID: ${voiceId}`);

  // Ensure output directory exists
  const outDir = path.dirname(outputPath);
  if (!fs.existsSync(outDir)) {
    fs.mkdirSync(outDir, { recursive: true });
  }

  await generateVoiceover(fullText, outputPath, voiceId);

  const duration = getAudioDuration(outputPath);
  if (duration) {
    console.log(`  Duration: ${duration.toFixed(2)}s`);
  }

  console.log('\n✅ Voiceover generated!');
}

main().catch(err => {
  console.error('❌ Error:', err.message);
  process.exit(1);
});

module.exports = { generateVoiceover, getAudioDuration };
