#!/usr/bin/env node
/**
 * YouTube Upload
 * Uploads video with SEO-optimized metadata
 * 
 * Usage: node youtube-upload.js --file video.mp4 --title "Title" --description "Desc" --tags "tag1,tag2"
 */

const fs = require('fs');
const https = require('https');

let config;
try {
  config = require('./config');
} catch (e) {
  console.error('❌ Missing config.js');
  process.exit(1);
}

async function getAccessToken() {
  return new Promise((resolve, reject) => {
    const postData = new URLSearchParams({
      client_id: config.youtube.clientId,
      client_secret: config.youtube.clientSecret,
      refresh_token: config.youtube.refreshToken,
      grant_type: 'refresh_token',
    }).toString();

    const options = {
      hostname: 'oauth2.googleapis.com',
      port: 443,
      path: '/token',
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Content-Length': Buffer.byteLength(postData),
      },
    };

    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          if (parsed.access_token) {
            resolve(parsed.access_token);
          } else {
            reject(new Error(`Token error: ${data}`));
          }
        } catch (e) {
          reject(e);
        }
      });
    });

    req.on('error', reject);
    req.write(postData);
    req.end();
  });
}

async function uploadVideo(videoPath, metadata, accessToken) {
  return new Promise((resolve, reject) => {
    const videoData = fs.readFileSync(videoPath);
    const videoMeta = {
      snippet: {
        title: metadata.title,
        description: metadata.description,
        tags: metadata.tags || config.youtubeDefaults?.tags || [],
        categoryId: metadata.categoryId || config.youtubeDefaults?.categoryId || '22',
        defaultLanguage: metadata.defaultLanguage || 'en',
        defaultAudioLanguage: metadata.defaultAudioLanguage || 'en',
      },
      status: {
        privacyStatus: metadata.privacyStatus || config.youtubeDefaults?.privacyStatus || 'public',
        selfDeclaredMadeForKids: false,
      },
    };

    const boundary = '----WebKitFormBoundary' + Math.random().toString(36).slice(2);
    const metadataJson = JSON.stringify(videoMeta);
    
    const header = [
      `--${boundary}`,
      'Content-Type: application/json; charset=UTF-8',
      '',
      metadataJson,
      `--${boundary}`,
      'Content-Type: video/mp4',
      '',
      ''
    ].join('\r\n');
    
    const footer = `\r\n--${boundary}--`;
    
    const fullBody = Buffer.concat([
      Buffer.from(header),
      videoData,
      Buffer.from(footer)
    ]);

    const options = {
      hostname: 'www.googleapis.com',
      port: 443,
      path: '/upload/youtube/v3/videos?uploadType=multipart&part=snippet,status',
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': `multipart/related; boundary=${boundary}`,
        'Content-Length': fullBody.length,
      },
    };

    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          if (parsed.id) {
            resolve({
              videoId: parsed.id,
              url: `https://youtube.com/shorts/${parsed.id}`,
              ...parsed,
            });
          } else {
            reject(new Error(`Upload error: ${data}`));
          }
        } catch (e) {
          reject(new Error(`Parse error: ${data}`));
        }
      });
    });

    req.on('error', reject);
    req.write(fullBody);
    req.end();
  });
}

async function main() {
  const args = process.argv.slice(2);
  
  const getArg = (flag) => {
    const idx = args.indexOf(flag);
    return idx !== -1 ? args[idx + 1] : null;
  };

  const filePath = getArg('--file');
  const title = getArg('--title');
  const description = getArg('--description') || '';
  const tagsStr = getArg('--tags') || '';
  const privacy = getArg('--privacy') || 'public';

  if (!filePath || !title) {
    console.log('Usage:');
    console.log('  node youtube-upload.js --file video.mp4 --title "Title" [options]');
    console.log('');
    console.log('Options:');
    console.log('  --description "Desc"  Video description');
    console.log('  --tags "a,b,c"        Comma-separated tags');
    console.log('  --privacy public      public/private/unlisted');
    process.exit(1);
  }

  if (!fs.existsSync(filePath)) {
    console.error(`❌ File not found: ${filePath}`);
    process.exit(1);
  }

  console.log('📤 Starting YouTube upload...');
  console.log(`  File: ${filePath}`);
  console.log(`  Title: ${title}`);

  // Check credentials
  if (!config.youtube.clientId || !config.youtube.refreshToken) {
    console.error('❌ YouTube credentials not configured');
    console.error('   Run `node youtube-auth.js` to set up OAuth');
    process.exit(1);
  }

  console.log('  Getting access token...');
  const accessToken = await getAccessToken();

  console.log('  Uploading video...');
  const result = await uploadVideo(filePath, {
    title,
    description,
    tags: tagsStr.split(',').map(t => t.trim()).filter(Boolean),
    privacyStatus: privacy,
  }, accessToken);

  console.log(`\n✅ Uploaded!`);
  console.log(`  Video ID: ${result.videoId}`);
  console.log(`  URL: ${result.url}`);
}

main().catch(err => {
  console.error('❌ Error:', err.message);
  process.exit(1);
});

module.exports = { getAccessToken, uploadVideo };
