#!/bin/bash
set -e

echo "→ Generating icon..."
python -c "
from PIL import Image, ImageDraw
img = Image.new('RGBA', (512, 512), (0,0,0,0))
d = ImageDraw.Draw(img)
d.ellipse([20,20,492,492], fill='#534AB7')
d.rectangle([156,180,356,332], outline='white', width=8)
d.ellipse([216,210,296,290], outline='white', width=8)
d.polygon([196,160,316,160,336,180,176,180], fill='white')
img.save('app/assets/icon.png')
print('icon saved')
"

echo "→ Converting icon to .icns..."
mkdir -p app/assets/icon.iconset
for size in 16 32 64 128 256 512; do
  python -c "
from PIL import Image
img = Image.open('app/assets/icon.png').resize(($size,$size), Image.LANCZOS)
img.save('app/assets/icon.iconset/icon_${size}x${size}.png')
"
done
iconutil -c icns app/assets/icon.iconset -o app/assets/icon.icns
rm -rf app/assets/icon.iconset

echo "→ Building .app with PyInstaller..."
pyinstaller memorybox.spec --noconfirm --clean

echo "✓ Done: dist/MemoryBox.app"
