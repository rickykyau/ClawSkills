/**
 * Brand styles for Hailey Finance videos
 * Customize colors, fonts, and layout here
 */

export const colors = {
  // Primary brand colors
  haileyGold: '#D4AF37',
  haileyCream: '#F5F5DC',
  
  // Backgrounds
  bgDark: '#1a1a2e',
  bgDarker: '#0f0f1a',
  
  // Text
  textWhite: '#FFFFFF',
  textMuted: '#B0B0B0',
  
  // Accents
  accentGreen: '#2ECC71',
  accentRed: '#E74C3C',
  accentBlue: '#3498DB',
};

export const fonts = {
  primary: 'Inter, -apple-system, BlinkMacSystemFont, sans-serif',
  mono: 'JetBrains Mono, Menlo, Monaco, monospace',
};

export const brandStyles = {
  container: {
    fontFamily: fonts.primary,
    backgroundColor: colors.bgDark,
    color: colors.textWhite,
  },
  
  headerBar: {
    position: 'absolute' as const,
    top: 0,
    left: 0,
    right: 0,
    padding: '24px 32px',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    background: 'linear-gradient(180deg, rgba(0,0,0,0.6) 0%, transparent 100%)',
  },
  
  brandName: {
    fontSize: 28,
    fontWeight: 700,
    color: colors.haileyGold,
  },
  
  avatar: {
    width: 56,
    height: 56,
    borderRadius: '50%',
    border: `3px solid ${colors.haileyGold}`,
  },
  
  footer: {
    position: 'absolute' as const,
    bottom: 0,
    left: 0,
    right: 0,
    padding: '24px 32px',
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    background: 'linear-gradient(0deg, rgba(0,0,0,0.6) 0%, transparent 100%)',
  },
  
  footerHandle: {
    fontSize: 24,
    fontWeight: 600,
    color: colors.haileyCream,
    opacity: 0.8,
  },
  
  headline: {
    fontSize: 64,
    fontWeight: 800,
    color: colors.haileyGold,
    textAlign: 'center' as const,
    textShadow: '0 4px 20px rgba(0,0,0,0.5)',
  },
  
  dataCard: {
    backgroundColor: 'rgba(255,255,255,0.05)',
    borderRadius: 16,
    padding: '24px 32px',
    borderLeft: `4px solid ${colors.haileyGold}`,
    backdropFilter: 'blur(10px)',
  },
};

export const animations = {
  fadeIn: (frame: number, fps: number, duration = 0.3) => {
    const progress = Math.min(frame / (fps * duration), 1);
    return progress;
  },
  
  slideUp: (frame: number, fps: number, duration = 0.3, distance = 30) => {
    const progress = Math.min(frame / (fps * duration), 1);
    return distance * (1 - progress);
  },
};
