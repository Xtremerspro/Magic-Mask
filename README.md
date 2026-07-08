# Magic Mask: AI Background Remover

**Magic Mask** is a desktop GUI application built with Python and Tkinter that utilizes AI to remove backgrounds from images. It features batch processing, interactive crop selection, and hardware acceleration (CUDA/MPS).

## Features

* **AI-Powered Removal:** Uses the `transparent-background` library (based on InSPyReNet) for high-quality edge detection and matting.
* **Batch Processing:** Process single images or entire folders containing hundreds of images.
* **Interactive Crop Selector:** Visually draw a box around the target object to focus the AI's attention or limit the processing area.
* **Background Options:**
  * **Transparent:** Standard PNG alpha channel.
  * **Solid Color:** Choose any specific background color using a color picker.
  * **Invert Mode:** Remove the object and keep the background (magic eraser style).
* **Special Options:**
  * Supports **HDR10+** Tonemapping
  * **ProRes4444** codec for transparent videos
* **Performance Optimization:**
  * Supports **CUDA** (NVIDIA GPUs) and **MPS** (Apple Silicon) for fast processing.
  * **Base** (High Quality) vs **Fast** (Lower Latency) model selection.
* **Real-time Feedback:** Progress bar with an estimated time of arrival (ETA) calculator.

## Installation

### Prerequisites

* Python 3.8 or higher.
* A working internet connection (to download the AI models on the first run).

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/magic-mask.git
cd magic-mask

```

### 2. Install Dependencies

You can install the required libraries using pip.

```bash
pip install transparent-background torch torchvision pillow

```

*Note: If you are using a specific GPU (like NVIDIA), ensure you install the CUDA-enabled version of PyTorch.*

## Usage

1. **Run the Application:**
```bash
python magic_mask.py

```
or run the `run.bat` file


2. **Select Input:**
* Click **Browse File** for a single image/video
* Click **Browse Folder** to process a directory of images.


3. **Visual Cropping (Optional):**
* If you have a specific object to isolate, click **Select Crop Area Visually**.
* A window will appear displaying your image. Click and drag to draw a box.
* Upon closing, the coordinates will automatically populate in the settings.


4. **Configuration:**
* **Model:** Select "Base" for best details (hair/fur) or "Fast" for speed.
* **Mode:** Check "Invert Mask" if you want to keep the background instead of the object.
* **Background:** Defaults to transparent. Click "Transparent (Default)" to pick a solid color.
* **Special:** Choose HDR10+ Tonemapping or ProRes4444 codec for videos


5. **Process:**
* Click **START PROCESSING**. The tool will download the model (if it's the first time) and begin processing.

### Hardware Acceleration

The script automatically detects your hardware:

* **Windows/Linux + NVIDIA:** Uses `cuda`.
* **Mac (M1/M2/M3):** Uses `mps` (Metal Performance Shaders).
* **Others:** Fallback to `cpu`.

## Requirements

If you prefer a `requirements.txt` file, create one with the following content:

```text
tk
Pillow
torch
transparent-background

```

## 📝 License

[MIT](https://choosealicense.com/licenses/mit/)

## Acknowledgements

* Built using [transparent-background](https://github.com/plemeri/transparent-background) by plemeri.
