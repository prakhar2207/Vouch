import os
import numpy as np
from PIL import Image

def generate_icons():
    src_path = r"C:\Users\prakh\.gemini\antigravity\brain\2afbc44c-2f59-44f4-bf1d-8fa2715cb80c\vouch_logo_cleaned_1790356958702.jpg"
    img = Image.open(src_path).convert("RGBA")
    arr = np.array(img)

    # 1. Exact emblem bounding box
    mask = (arr[:620, :, 0] < 240) | (arr[:620, :, 1] < 240) | (arr[:620, :, 2] < 240)
    ymin, ymax = np.where(mask.any(axis=1))[0][[0, -1]]
    xmin, xmax = np.where(mask.any(axis=0))[0][[0, -1]]
    
    # Crop the emblem
    emblem_raw = img.crop((xmin, ymin, xmax + 1, ymax + 1))
    
    # Create transparent version of emblem by turning pure white background into transparent
    emblem_arr = np.array(emblem_raw)
    # Check near-white background
    white_mask = (emblem_arr[:, :, 0] > 250) & (emblem_arr[:, :, 1] > 250) & (emblem_arr[:, :, 2] > 250)
    transparent_emblem_arr = emblem_arr.copy()
    transparent_emblem_arr[white_mask, 3] = 0
    emblem_transparent = Image.fromarray(transparent_emblem_arr)

    # Create solid PWA canvas (512x512) with safe margins
    # Modern white background
    pwa_512 = Image.new("RGBA", (512, 512), (255, 255, 255, 255))
    
    # Scale emblem to fit comfortably within the 80% safe zone (e.g. target width 340px)
    target_w = 340
    aspect = emblem_raw.height / emblem_raw.width
    target_h = int(target_w * aspect)
    
    scaled_emblem = emblem_raw.resize((target_w, target_h), Image.Resampling.LANCZOS)
    
    paste_x = (512 - target_w) // 2
    paste_y = (512 - target_h) // 2
    
    pwa_512.paste(scaled_emblem, (paste_x, paste_y))

    # Also make a 192x192 version
    pwa_192 = pwa_512.resize((192, 192), Image.Resampling.LANCZOS)
    
    # 180x180 for Apple touch icon
    apple_180 = pwa_512.resize((180, 180), Image.Resampling.LANCZOS)

    # Save destinations
    icons_dir = r"c:\Users\prakh\OneDrive\Desktop\projects\B2B\frontend\public\icons"
    public_dir = r"c:\Users\prakh\OneDrive\Desktop\projects\B2B\frontend\public"
    app_dir = r"c:\Users\prakh\OneDrive\Desktop\projects\B2B\frontend\src\app"
    os.makedirs(icons_dir, exist_ok=True)

    # Save PWA icons
    pwa_512.save(os.path.join(icons_dir, "icon-512x512.png"), "PNG")
    pwa_192.save(os.path.join(icons_dir, "icon-192x192.png"), "PNG")
    apple_180.save(os.path.join(icons_dir, "apple-touch-icon.png"), "PNG")
    apple_180.save(os.path.join(public_dir, "apple-touch-icon.png"), "PNG")

    # Save transparent logo mark
    emblem_transparent.save(os.path.join(public_dir, "logo-mark.png"), "PNG")
    
    # Save full cleaned logo
    img.save(os.path.join(public_dir, "logo.png"), "PNG")

    # Generate multi-size favicon.ico
    favicons = [
        pwa_512.resize((16, 16), Image.Resampling.LANCZOS),
        pwa_512.resize((32, 32), Image.Resampling.LANCZOS),
        pwa_512.resize((48, 48), Image.Resampling.LANCZOS),
    ]
    favicons[0].save(
        os.path.join(public_dir, "favicon.ico"),
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48)],
        append_images=favicons[1:]
    )
    favicons[0].save(
        os.path.join(app_dir, "favicon.ico"),
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48)],
        append_images=favicons[1:]
    )

    print("Successfully generated all PWA icons, apple touch icon, and favicons!")

if __name__ == "__main__":
    generate_icons()
