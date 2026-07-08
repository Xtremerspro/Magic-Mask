import tkinter as tk
from tkinter import filedialog, messagebox, ttk, colorchooser
import threading
import os
from pathlib import Path
from PIL import Image, ImageOps, ImageTk
import torch
import time
import cv2
import numpy as np
import subprocess  # Used for robust ProRes and HDR tone-mapped FFmpeg pipes

from transparent_background import Remover


# --- Class for Interactive Cropping ---
class CropSelector:
    def __init__(self, parent, file_path, callback, tone_map_hdr=False):
        self.callback = callback
        self.original_image_path = file_path

        # Handle MP4 vs Image for the preview
        if str(file_path).lower().endswith(".mp4"):
            # If HDR tone mapping is enabled, extract the frame via FFmpeg to prevent washed out preview
            if tone_map_hdr:
                cmd = [
                    "ffmpeg",
                    "-ss",
                    "00:00:00",
                    "-i",
                    str(file_path),
                    "-vf",
                    "zscale=t=linear:p=bt709,tonemap=tonemap=hable,zscale=t=bt709:m=bt709",
                    "-vframes",
                    "1",
                    "-f",
                    "image2pipe",
                    "-vcodec",
                    "png",
                    "-",
                ]
                try:
                    proc = subprocess.Popen(
                        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                    )
                    out, _ = proc.communicate()
                    img = Image.open(io.BytesIO(out))
                except:
                    cap = cv2.VideoCapture(str(file_path))
                    ret, frame = cap.read()
                    cap.release()
                    img = (
                        Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                        if ret
                        else None
                    )
            else:
                cap = cv2.VideoCapture(str(file_path))
                ret, frame = cap.read()
                cap.release()
                if ret:
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    img = Image.fromarray(frame_rgb)
                else:
                    messagebox.showerror(
                        "Error", "Could not read the first frame of the video."
                    )
                    return
        else:
            img = Image.open(file_path)

        if img is None:
            messagebox.showerror("Error", "Could not load image file preview.")
            return

        # Resize for comfortable viewing (max 600x600)
        max_size = 600
        ratio = min(max_size / img.width, max_size / img.height)
        self.display_img = img.resize((int(img.width * ratio), int(img.height * ratio)))
        self.img_tk = ImageTk.PhotoImage(self.display_img)

        self.scale_factor = img.width / self.display_img.width

        self.root = tk.Toplevel(parent)
        self.root.title("Select Crop Area")
        self.root.resizable(False, False)

        self.canvas = tk.Canvas(
            self.root,
            width=self.img_tk.width(),
            height=self.img_tk.height(),
            cursor="cross",
        )
        self.canvas.pack(padx=10, pady=10)
        self.canvas.create_image(0, 0, image=self.img_tk, anchor="nw")

        tk.Label(
            self.root, text="Click and drag to select an area. Press ESC to cancel."
        ).pack(pady=5)

        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.root.bind("<Escape>", lambda e: self.root.destroy())

        self.start_x = None
        self.start_y = None
        self.rect = None
        self.selected_coords = None

    def on_mouse_down(self, event):
        self.start_x = event.x
        self.start_y = event.y
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(
            self.start_x,
            self.start_y,
            self.start_x,
            self.start_y,
            outline="red",
            width=2,
            dash=(5, 2),
        )

    def on_mouse_drag(self, event):
        cur_x, cur_y = event.x, event.y
        self.canvas.coords(self.rect, self.start_x, self.start_y, cur_x, cur_y)

    def on_mouse_up(self, event):
        end_x, end_y = event.x, event.y

        display_x1 = min(self.start_x, end_x)
        display_y1 = min(self.start_y, end_y)
        display_x2 = max(self.start_x, end_x)
        display_y2 = max(self.start_y, end_y)

        x1 = int(display_x1 * self.scale_factor)
        y1 = int(display_y1 * self.scale_factor)
        x2 = int(display_x2 * self.scale_factor)
        y2 = int(display_y2 * self.scale_factor)

        self.selected_coords = (x1, y1, x2, y2)
        self.callback(self.selected_coords)

        self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(
            display_x1, display_y1, display_x2, display_y2, outline="green", width=3
        )

        messagebox.showinfo(
            "Selection Complete",
            f"Coordinates set: {x1}, {y1}, {x2}, {y2}. Click OK to close.",
        )
        self.root.destroy()


# --- Main Application Class ---
class MagicMaskApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Magic Mask Tool")
        self.root.geometry("700x750")  # Expanded height for extra options
        self.root.resizable(False, False)

        self.input_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready")
        self.model_type = tk.StringVar(value="base")
        self.invert_mask = tk.BooleanVar(value=False)
        self.crop_box_var = tk.StringVar()

        # New Video/HDR Feature Variables
        self.video_output_mode = tk.StringVar(
            value="mask_only"
        )  # mask_only, transparent_prores, solid_bg
        self.tone_map_hdr = tk.BooleanVar(value=False)

        self.bg_color = None
        self.is_processing = False

        self._setup_ui()

    def _setup_ui(self):
        header = tk.Label(
            self.root,
            text="Magic Mask: Image & Video Background Remover",
            font=("Poppins", 16, "bold"),
        )
        header.pack(pady=15)

        io_frame = tk.LabelFrame(self.root, text="Input & Output", padx=10, pady=10)
        io_frame.pack(fill="x", padx=20, pady=5)

        tk.Label(io_frame, text="Input (File or Folder):", anchor="w").grid(
            row=0, column=0, sticky="w", pady=2
        )
        input_frame = tk.Frame(io_frame)
        input_frame.grid(row=1, column=0, sticky="ew", columnspan=2, pady=(0, 10))
        tk.Entry(input_frame, textvariable=self.input_path, width=40).pack(
            side="left", fill="x", expand=True
        )
        tk.Button(input_frame, text="Browse File", command=self.browse_file).pack(
            side="left", padx=5
        )
        tk.Button(input_frame, text="Browse Folder", command=self.browse_folder).pack(
            side="left"
        )

        tk.Label(io_frame, text="Output Folder:", anchor="w").grid(
            row=2, column=0, sticky="w", pady=2
        )
        output_frame = tk.Frame(io_frame)
        output_frame.grid(row=3, column=0, sticky="ew", columnspan=2)
        tk.Entry(output_frame, textvariable=self.output_path, width=40).pack(
            side="left", fill="x", expand=True
        )
        tk.Button(output_frame, text="Browse", command=self.browse_output).pack(
            side="left", padx=5
        )

        config_frame = tk.LabelFrame(self.root, text="Configuration", padx=10, pady=10)
        config_frame.pack(fill="x", padx=20, pady=5)

        tk.Label(config_frame, text="Model:").grid(row=0, column=0, padx=5, sticky="w")
        ttk.Radiobutton(
            config_frame,
            text="Base (Best Quality)",
            variable=self.model_type,
            value="base",
        ).grid(row=0, column=1, sticky="w")
        ttk.Radiobutton(
            config_frame,
            text="Fast (Lower Latency)",
            variable=self.model_type,
            value="fast",
        ).grid(row=0, column=2, sticky="w", padx=10)

        tk.Label(config_frame, text="Mode:").grid(
            row=1, column=0, padx=5, sticky="w", pady=5
        )
        ttk.Checkbutton(
            config_frame,
            text="Invert Mask (Keep Background)",
            variable=self.invert_mask,
        ).grid(row=1, column=1, columnspan=2, sticky="w")

        tk.Label(config_frame, text="Background:").grid(
            row=2, column=0, padx=5, sticky="w", pady=5
        )
        self.btn_color = tk.Button(
            config_frame,
            text="Transparent (Default)",
            command=self.pick_color,
            width=20,
        )
        self.btn_color.grid(row=2, column=1, sticky="w")
        tk.Button(
            config_frame,
            text="Reset to Transparent",
            command=self.reset_color,
            font=("Arial", 8),
        ).grid(row=2, column=2, sticky="w", padx=5)

        # --- Enhanced Video Options Frame ---
        video_frame = tk.LabelFrame(
            self.root, text="Advanced Video Settings (MP4 Input Only)", padx=10, pady=10
        )
        video_frame.pack(fill="x", padx=20, pady=5)

        tk.Label(video_frame, text="Output Format:").grid(
            row=0, column=0, padx=5, sticky="w"
        )
        ttk.Radiobutton(
            video_frame,
            text="Mask Only (Greyscale MP4)",
            variable=self.video_output_mode,
            value="mask_only",
        ).grid(row=0, column=1, sticky="w")
        ttk.Radiobutton(
            video_frame,
            text="Transparent Video (ProRes 4444 MOV)",
            variable=self.video_output_mode,
            value="transparent_prores",
        ).grid(row=0, column=2, sticky="w", padx=10)

        ttk.Checkbutton(
            video_frame,
            text="Enable HDR10+ to SDR Tonemapping (BT.2020 -> BT.709)",
            variable=self.tone_map_hdr,
        ).grid(row=1, column=1, columnspan=2, sticky="w", pady=(5, 0))

        crop_frame = tk.LabelFrame(
            self.root, text="Interactive Crop Selection", padx=10, pady=5
        )
        crop_frame.pack(fill="x", padx=20, pady=5)

        tk.Button(
            crop_frame,
            text="Select Crop Area Visually",
            command=self.launch_crop_selector,
            bg="#4CAF50",
            fg="white",
            font=("Arial", 10, "bold"),
        ).pack(side="left", padx=10)

        tk.Label(crop_frame, text="Coords (X1, Y1, X2, Y2):").pack(side="left")
        tk.Entry(crop_frame, textvariable=self.crop_box_var, width=30).pack(
            side="left", padx=5
        )
        tk.Button(
            crop_frame,
            text="Clear",
            command=lambda: self.crop_box_var.set(""),
            font=("Arial", 8),
        ).pack(side="left")

        self.progress = ttk.Progressbar(
            self.root, orient="horizontal", length=400, mode="determinate"
        )
        self.progress.pack(pady=15)

        self.status_label = tk.Label(self.root, textvariable=self.status_var, fg="gray")
        self.status_label.pack()

        self.btn_process = tk.Button(
            self.root,
            text="START PROCESSING",
            command=self.start_thread,
            bg="#007acc",
            fg="white",
            font=("Arial", 12, "bold"),
            height=2,
        )
        self.btn_process.pack(pady=10, fill="x", padx=150)

    def launch_crop_selector(self):
        input_path = self.input_path.get()
        if not input_path or not Path(input_path).is_file():
            messagebox.showwarning(
                "Input Needed",
                "Please select a single file first to use the visual selector.",
            )
            return
        CropSelector(
            self.root,
            input_path,
            self.update_crop_box,
            tone_map_hdr=self.tone_map_hdr.get(),
        )

    def update_crop_box(self, coords):
        self.crop_box_var.set(f"{coords[0]}, {coords[1]}, {coords[2]}, {coords[3]}")

    def pick_color(self):
        color = colorchooser.askcolor(title="Choose Background Color")
        if color[1]:
            self.bg_color = color[0]
            self.btn_color.config(text=f"Color: {color[1]}", bg=color[1], fg="black")
            if self.video_output_mode.get() == "transparent_prores":
                self.video_output_mode.set("mask_only")
                messagebox.showinfo(
                    "Mode Adjusted",
                    "ProRes 4444 mode sets true transparent values. Switched format destination mode.",
                )

    def reset_color(self):
        self.bg_color = None
        self.btn_color.config(
            text="Transparent (Default)", bg="SystemButtonFace", fg="black"
        )

    def browse_file(self):
        filename = filedialog.askopenfilename(
            filetypes=[
                ("Images & Videos", "*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.mp4;*.mov")
            ]
        )
        if filename:
            self.input_path.set(filename)
            if Path(filename).is_file():
                current_out = self.output_path.get()
                if (
                    not current_out
                    or Path(current_out)
                    == Path(self.input_path.get()).parent / "processed"
                ):
                    self.output_path.set(str(Path(filename).parent))

    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.input_path.set(folder)
            if not self.output_path.get():
                self.output_path.set(str(Path(folder) / "processed"))

    def browse_output(self):
        folder = filedialog.askdirectory()
        if folder:
            self.output_path.set(folder)

    def start_thread(self):
        if self.is_processing:
            return
        in_p, out_p = self.input_path.get(), self.output_path.get()
        if not in_p or not out_p:
            messagebox.showwarning(
                "Missing Info", "Please select input and output paths."
            )
            return

        self.is_processing = True
        self.btn_process.config(state="disabled", text="Processing...")
        threading.Thread(
            target=self.run_processing, args=(in_p, out_p), daemon=True
        ).start()

    def run_processing(self, in_path, out_path):
        try:
            self.update_status("Loading AI Model...")

            device = "cuda" if torch.cuda.is_available() else "cpu"
            if device == "cpu" and torch.backends.mps.is_available():
                device = "mps"

            remover = Remover(mode=self.model_type.get(), device=device)

            crop_coords = None
            crop_input = self.crop_box_var.get().strip()
            if crop_input:
                try:
                    coords = [int(c.strip()) for c in crop_input.split(",")]
                    crop_coords = tuple(coords) if len(coords) == 4 else None
                except:
                    pass

            input_path_obj = Path(in_path)
            if input_path_obj.is_file():
                files = [input_path_obj]
            else:
                exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".mp4", ".mov"}
                files = [
                    f for f in input_path_obj.iterdir() if f.suffix.lower() in exts
                ]

            if not files:
                raise ValueError("No valid source files found.")

            os.makedirs(out_path, exist_ok=True)
            total = len(files)
            start_time = time.time()

            for i, file_path in enumerate(files):
                is_video = file_path.suffix.lower() in {".mp4", ".mov"}

                elapsed = time.time() - start_time
                if i > 0:
                    avg_time_per_img = elapsed / i
                    remaining_imgs = total - i
                    eta_seconds = int(avg_time_per_img * remaining_imgs)
                    mins, secs = divmod(eta_seconds, 60)
                    eta_str = f" | ETA: {mins:02d}:{secs:02d}"
                else:
                    eta_str = " | ETA: Calculating..."

                if is_video:
                    self.update_status(
                        f"Processing Video {i+1}/{total} (Analyzing frames...)"
                    )

                    # Read properties using default capture pipeline
                    cap = cv2.VideoCapture(str(file_path))
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                    orig_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    orig_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    cap.release()

                    if fps <= 0 or np.isnan(fps):
                        fps = 30.0

                    mode = self.video_output_mode.get()

                    # Determine target output format configuration
                    if mode == "transparent_prores":
                        save_path = os.path.join(
                            out_path, f"{file_path.stem}_alpha.mov"
                        )
                        # Added -loglevel error to suppress verbose stream outputs
                        ffmpeg_cmd = [
                            "ffmpeg",
                            "-y",
                            "-loglevel",
                            "error",
                            "-f",
                            "rawvideo",
                            "-pix_fmt",
                            "rgba",
                            "-s",
                            f"{orig_width}x{orig_height}",
                            "-r",
                            f"{fps}",
                            "-i",
                            "-",
                            "-c:v",
                            "prores_ks",
                            "-profile:v",
                            "4",
                            "-vendor",
                            "appl",
                            "-pix_fmt",
                            "yuva444p10le",
                            save_path,
                        ]
                    else:
                        save_path = os.path.join(out_path, f"{file_path.stem}_mask.mp4")
                        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                        video_writer = cv2.VideoWriter(
                            save_path,
                            fourcc,
                            fps,
                            (orig_width, orig_height),
                            isColor=True,
                        )

                    # Initialize Video Source Capture Pipeline (with/without Tone mapping)
                    if self.tone_map_hdr.get():
                        # Added -loglevel error here as well
                        src_cmd = [
                            "ffmpeg",
                            "-loglevel",
                            "error",
                            "-i",
                            str(file_path),
                            "-vf",
                            "zscale=t=linear:p=bt709,tonemap=tonemap=hable,zscale=t=bt709:m=bt709",
                            "-f",
                            "rawvideo",
                            "-pix_fmt",
                            "rgb24",
                            "-",
                        ]
                        video_stream = subprocess.Popen(
                            src_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
                        )
                    else:
                        cap = cv2.VideoCapture(str(file_path))

                    frame_count = 0
                    ffmpeg_proc = None
                    try:
                        if mode == "transparent_prores":
                            # Changed stderr to DEVNULL to prevent OS pipe buffer allocation deadlocks
                            ffmpeg_proc = subprocess.Popen(
                                ffmpeg_cmd,
                                stdin=subprocess.PIPE,
                                stderr=subprocess.DEVNULL,
                            )

                        while True:
                            if self.tone_map_hdr.get():
                                raw_frame = video_stream.stdout.read(
                                    orig_width * orig_height * 3
                                )
                                if not raw_frame or len(raw_frame) != (
                                    orig_width * orig_height * 3
                                ):
                                    break
                                frame_np = np.frombuffer(
                                    raw_frame, dtype=np.uint8
                                ).reshape((orig_height, orig_width, 3))
                                original_img = Image.fromarray(frame_np)
                            else:
                                ret, frame = cap.read()
                                if not ret:
                                    break
                                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                                original_img = Image.fromarray(frame_rgb)

                            img_to_process = original_img.copy()

                            if crop_coords:
                                try:
                                    img_to_process = original_img.crop(crop_coords)
                                except:
                                    pass

                            mask_img = remover.process(
                                img_to_process, type="map"
                            ).convert("L")

                            if self.invert_mask.get():
                                mask_img = ImageOps.invert(mask_img)

                            if crop_coords:
                                final_mask = Image.new(
                                    "L", (orig_width, orig_height), 0
                                )
                                final_mask.paste(mask_img, crop_coords)
                            else:
                                final_mask = mask_img

                            if mode == "transparent_prores":
                                rgba_img = original_img.convert("RGBA")
                                rgba_img.putalpha(final_mask)
                                ffmpeg_proc.stdin.write(rgba_img.tobytes())
                            else:
                                final_mask_np = np.array(final_mask)
                                final_frame_bgr = cv2.cvtColor(
                                    final_mask_np, cv2.COLOR_GRAY2BGR
                                )
                                video_writer.write(final_frame_bgr)

                            frame_count += 1

                            if frame_count % 5 == 0:
                                self.update_status(
                                    f"Processing Video {i+1}/{total} (Frame {frame_count}/{total_frames or '?'}){eta_str}"
                                )
                                if total_frames > 0:
                                    progress_val = (
                                        (i + (frame_count / total_frames)) / total
                                    ) * 100
                                    self.root.after(
                                        0,
                                        lambda v=progress_val: self.progress.configure(
                                            value=v
                                        ),
                                    )
                    finally:
                        if self.tone_map_hdr.get():
                            video_stream.terminate()
                            video_stream.wait()
                        else:
                            cap.release()

                        if mode == "transparent_prores" and ffmpeg_proc:
                            if ffmpeg_proc.stdin:
                                ffmpeg_proc.stdin.close()
                            ffmpeg_proc.wait()
                        elif mode != "transparent_prores":
                            video_writer.release()

                else:
                    # Keep existing standard standalone image execution stack logic intact
                    self.update_status(f"Processing Image {i+1}/{total}{eta_str}")

                    original_img = Image.open(file_path).convert("RGB")
                    original_size = original_img.size
                    img_to_process = original_img.copy()

                    if crop_coords:
                        try:
                            img_to_process = original_img.crop(crop_coords)
                        except:
                            pass

                    mask_img = remover.process(img_to_process, type="map").convert("L")

                    if self.invert_mask.get():
                        mask_img = ImageOps.invert(mask_img)

                    img_to_process = img_to_process.convert("RGBA")

                    if crop_coords:
                        final_img = Image.new("RGBA", original_size, (0, 0, 0, 0))
                        img_to_process.putalpha(mask_img)
                        final_img.paste(img_to_process, crop_coords, img_to_process)
                        if self.bg_color:
                            solid_bg = Image.new("RGB", original_size, self.bg_color)
                            solid_bg.paste(final_img, (0, 0), final_img)
                            final_img = solid_bg
                    else:
                        if self.bg_color:
                            final_img = Image.new("RGB", original_size, self.bg_color)
                            final_img.paste(
                                original_img.convert("RGB"), (0, 0), mask_img
                            )
                        else:
                            final_img = original_img.convert("RGBA")
                            final_img.putalpha(mask_img)

                    save_path = os.path.join(out_path, f"{file_path.stem}_masked.png")
                    final_img.save(save_path, "PNG")

                    progress_val = ((i + 1) / total) * 100
                    self.root.after(
                        0, lambda v=progress_val: self.progress.configure(value=v)
                    )

            self.update_status("Complete!")
            self.root.after(
                0, lambda: messagebox.showinfo("Success", f"Processed {total} file(s).")
            )

        except Exception as e:
            error_message = str(e)
            self.update_status(f"Error: {error_message}")
            self.root.after(
                0, lambda msg=error_message: messagebox.showerror("Fatal Error", msg)
            )
        finally:
            self.is_processing = False
            self.root.after(0, self.reset_ui)

    def update_status(self, text):
        self.root.after(0, lambda: self.status_var.set(text))

    def reset_ui(self):
        self.btn_process.config(state="normal", text="START PROCESSING")
        self.progress.configure(value=0)


if __name__ == "__main__":
    root = tk.Tk()
    app = MagicMaskApp(root)
    root.mainloop()
