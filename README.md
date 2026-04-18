# Lens

> A simple OCR tool for GNOME. Point it at anything on your screen and pull the text out.

## Features

- Extract text from screenshots, images, PDFs, QR codes and more
- Drag and drop image files directly onto the window
- Paste images from clipboard
- Auto-copy extracted text to clipboard
- Automatically open URLs found in QR codes
- Text-to-speech support
- Share extracted text directly to email, Telegram, Mastodon and more
- Multi-language OCR support via Tesseract

## Installation

### Build from source (Flatpak)

Requirements:
- `flatpak`
- `flatpak-builder`
- GNOME Platform runtime 49

```bash
flatpak install flathub org.gnome.Platform//49 org.gnome.Sdk//49
flatpak-builder --user --install --force-clean build-dir flatpak/io.github.seed43.lens.json
```

Then run:
```bash
flatpak run io.github.seed43.lens
```

## Building for development

The easiest way to develop Lens is with [GNOME Builder](https://wiki.gnome.org/Apps/Builder).
Open the project folder in Builder and press **Execute** (F5).

Or manually with Meson:
```bash
meson setup build
cd build
ninja
ninja install
```

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

Original work copyright © 2021-2025 Andrey Maksimov  
Modifications copyright © 2026-present Seed-43

## Contributing

Contributions are welcome! Feel free to open issues or pull requests on [GitHub](https://github.com/Seed-43/Lens).
