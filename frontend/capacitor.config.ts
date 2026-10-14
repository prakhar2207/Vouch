import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.srilekh.app',
  appName: 'SriLekh',
  webDir: 'mobile-shell',
  server: {
    androidScheme: 'https',
    iosScheme: 'srilekh',
    allowNavigation: [
      'api.srilekh.com',
      'vouch-pi-one.vercel.app',
      'localhost',
      '127.0.0.1'
    ],
  },
  plugins: {
    SplashScreen: {
      launchShowDuration: 1800,
      launchAutoHide: true,
      backgroundColor: '#0F172A',
      androidSplashResourceName: 'splash',
      showSpinner: false,
      splashFullScreen: true,
      splashImmersive: true,
    },
    StatusBar: {
      style: 'DARK',
      backgroundColor: '#0F172A',
    },
    Network: {},
  },
};

export default config;
