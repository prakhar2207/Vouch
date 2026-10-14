const path = require('path');
const fs = require('fs');

const rootDir = path.resolve(__dirname, '..');
const frontendDir = path.join(rootDir, 'frontend');
const sharp = require(path.join(frontendDir, 'node_modules', 'sharp'));

// User's custom HD logos
const hdLogoDark = path.join(rootDir, 'ShriLekh-icon-for-dark-bg-HD-2048.png');
const hdLogoFinal = path.join(rootDir, 'ShriLekh-final-logo-HD-2400.png');
const fallbackLogo = path.join(frontendDir, 'public', 'logo-mark.png');

const primaryLogo = fs.existsSync(hdLogoFinal) ? hdLogoFinal : (fs.existsSync(hdLogoDark) ? hdLogoDark : fallbackLogo);
const iconSource = fs.existsSync(hdLogoDark) ? hdLogoDark : primaryLogo;

const androidRes = path.join(frontendDir, 'android', 'app', 'src', 'main', 'res');
const iosAppIcon = path.join(frontendDir, 'ios', 'App', 'App', 'Assets.xcassets', 'AppIcon.appiconset');
const mobileShellDir = path.join(frontendDir, 'mobile-shell');

console.log('Generating native mobile icons and splash screens...');
console.log('Primary logo source:', primaryLogo);
console.log('Icon source:', iconSource);

async function run() {
  // 1. Copy logo to mobile-shell and public icons
  await sharp(primaryLogo)
    .resize(512, 512, { fit: 'contain', background: { r: 255, g: 255, b: 255, alpha: 0 } })
    .toFile(path.join(mobileShellDir, 'logo.png'));
  console.log('✓ Updated mobile-shell/logo.png');

  await sharp(primaryLogo)
    .resize(512, 512, { fit: 'contain', background: { r: 255, g: 255, b: 255, alpha: 0 } })
    .toFile(path.join(frontendDir, 'public', 'icons', 'icon-512x512.png'));
  
  await sharp(primaryLogo)
    .resize(192, 192, { fit: 'contain', background: { r: 255, g: 255, b: 255, alpha: 0 } })
    .toFile(path.join(frontendDir, 'public', 'icons', 'icon-192x192.png'));

  // 2. Android densities
  const androidDensities = [
    { dir: 'mipmap-mdpi', size: 48, fgSize: 108, logoInner: 72 },
    { dir: 'mipmap-hdpi', size: 72, fgSize: 162, logoInner: 108 },
    { dir: 'mipmap-xhdpi', size: 96, fgSize: 216, logoInner: 144 },
    { dir: 'mipmap-xxhdpi', size: 144, fgSize: 324, logoInner: 216 },
    { dir: 'mipmap-xxxhdpi', size: 192, fgSize: 432, logoInner: 288 },
  ];

  for (const { dir, size, fgSize, logoInner } of androidDensities) {
    const targetDir = path.join(androidRes, dir);
    if (!fs.existsSync(targetDir)) fs.mkdirSync(targetDir, { recursive: true });

    // ic_launcher.png (legacy square)
    await sharp(primaryLogo)
      .resize(size, size, { fit: 'contain', background: { r: 255, g: 255, b: 255, alpha: 1 } })
      .toFile(path.join(targetDir, 'ic_launcher.png'));

    // ic_launcher_round.png
    await sharp(primaryLogo)
      .resize(size, size, { fit: 'contain', background: { r: 255, g: 255, b: 255, alpha: 1 } })
      .toFile(path.join(targetDir, 'ic_launcher_round.png'));

    // ic_launcher_foreground.png (for Android adaptive icons - centered with padding)
    const resizedInner = await sharp(iconSource)
      .resize(logoInner, logoInner, { fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } })
      .toBuffer();

    const padding = Math.floor((fgSize - logoInner) / 2);
    await sharp({
      create: {
        width: fgSize,
        height: fgSize,
        channels: 4,
        background: { r: 0, g: 0, b: 0, alpha: 0 }
      }
    })
      .composite([{ input: resizedInner, left: padding, top: padding }])
      .png()
      .toFile(path.join(targetDir, 'ic_launcher_foreground.png'));

    console.log(`✓ Android ${dir} icons generated`);
  }

  // 3. Android Splash Screens
  const splashLogo = await sharp(primaryLogo)
    .resize(480, 480, { fit: 'contain', background: { r: 15, g: 23, b: 42, alpha: 0 } })
    .toBuffer();

  const drawableDir = path.join(androidRes, 'drawable');
  if (fs.existsSync(drawableDir)) {
    await sharp({
      create: {
        width: 1080,
        height: 1920,
        channels: 4,
        background: { r: 15, g: 23, b: 42, alpha: 1 } // #0F172A dark theme
      }
    })
      .composite([{ input: splashLogo, gravity: 'centre' }])
      .png()
      .toFile(path.join(drawableDir, 'splash.png'));
    console.log('✓ Android splash.png generated');
  }

  // 4. iOS AppIcon
  if (fs.existsSync(iosAppIcon)) {
    await sharp(primaryLogo)
      .resize(1024, 1024, { fit: 'contain', background: { r: 255, g: 255, b: 255, alpha: 1 } })
      .toFile(path.join(iosAppIcon, 'AppIcon-512@2x.png'));
    console.log('✓ iOS AppIcon-512@2x.png generated (1024x1024)');
  }

  console.log('All native icons generated successfully!');
}

run().catch(err => {
  console.error('Error generating icons:', err);
  process.exit(1);
});
