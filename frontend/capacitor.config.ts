import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.srilekh.app',
  appName: 'SriLekh',
  webDir: 'mobile-shell',
  server: {
    url: 'https://srilekh.com/dashboard',
    cleartext: false,
    errorPath: 'index.html',
    androidScheme: 'https',
    iosScheme: 'srilekh',
    allowNavigation: [
      'srilekh.com',
      '*.srilekh.com',
      'api.srilekh.com'
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
