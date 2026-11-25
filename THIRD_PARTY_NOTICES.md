# Third-party notices

Videl is built on the open-source software and AI models below. Each keeps its own licence; the full licence texts are at the linked project pages. AI components and model weights are downloaded on first use, not shipped in the installer.

## Bundled with the app

- FFmpeg: GPL-3.0 (Windows build by gyan.dev, Linux build by BtbN). Run as a separate program. Source: https://ffmpeg.org, build sources: https://github.com/GyanD/codexffmpeg and https://github.com/BtbN/FFmpeg-Builds
- Qt for Python (PySide6): LGPL-3.0. https://www.qt.io/qt-for-python
- yt-dlp: Unlicense. https://github.com/yt-dlp/yt-dlp
- PyMuPDF (fitz): AGPL-3.0 or commercial. https://github.com/pymupdf/PyMuPDF
- Pillow: MIT-CMU. https://python-pillow.org
- cryptography: Apache-2.0 or BSD-3-Clause. https://github.com/pyca/cryptography

## AI components (downloaded on demand)

- PyTorch and torchvision: BSD-3-Clause. https://pytorch.org
- Real-ESRGAN (AI Upscaler, AI Video Upscaler): BSD-3-Clause. https://github.com/xinntao/Real-ESRGAN
- BasicSR: Apache-2.0. https://github.com/XPixelGroup/BasicSR
- RestoreFormer++ (Photo Restore faces), architecture vendored in core/vendor: Apache-2.0. https://github.com/wzhouxiff/RestoreFormerPlusPlus
- GFPGAN (installed with the AI Upscaler): Apache-2.0. https://github.com/TencentARC/GFPGAN
- facexlib (face detection and parsing): Apache-2.0. https://github.com/xinntao/facexlib
- DDColor (Photo Restore colorize): Apache-2.0. https://github.com/piddnad/DDColor
- Colorful Image Colorization, Zhang et al. 2016 (colorize fallback): BSD-2-Clause. https://github.com/richzhang/colorization
- Bringing Old Photos Back to Life, Microsoft (Photo Restore heal), via zeroscratches: MIT and Apache-2.0. https://github.com/microsoft/Bringing-Old-Photos-Back-to-Life
- ONNX Runtime: MIT. https://github.com/microsoft/onnxruntime
- OpenCV: Apache-2.0. https://opencv.org
- Demucs (Vocal Isolator): MIT. https://github.com/facebookresearch/demucs
- rembg and U2-Net (Background Eraser): MIT and Apache-2.0. https://github.com/danielgatis/rembg
- BiRefNet (Background Eraser): MIT. https://github.com/ZhengPeng7/BiRefNet
- LaMa (Background Eraser cleanup): Apache-2.0. https://github.com/advimman/lama
- whisper.cpp and OpenAI Whisper models (AI Transcript): MIT. https://github.com/ggml-org/whisper.cpp
- EasyOCR: Apache-2.0. https://github.com/JaidedAI/EasyOCR
- RapidOCR: Apache-2.0. https://github.com/RapidAI/RapidOCR
