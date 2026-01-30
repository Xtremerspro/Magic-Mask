import tkinter as tk
from tkinter import filedialog, messagebox, ttk, colorchooser
import threading
import os
from pathlib import Path
from PIL import Image, ImageOps, ImageTk
import torch
import time  # Ensure this is added at the top of your script

# Import the core library
from transparent_background import Remover


# --- New Class for Interactive Cropping ---
class CropSelector:
    def __init__(self, parent, image_path, callback):
        self.callback = callback
        self.original_image_path = image_path

        # 1. Load and prepare image for display
        img = Image.open(image_path)

        # Resize for comfortable viewing (max 600x600)
        max_size = 600
        ratio = min(max_size / img.width, max_size / img.height)
        self.display_img = img.resize((int(img.width * ratio), int(img.height * ratio)))
        self.img_tk = ImageTk.PhotoImage(self.display_img)

        self.scale_factor = (
            img.width / self.display_img.width
        )  # To scale selection back to original pixels

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

        # Status Label
        tk.Label(
            self.root, text="Click and drag to select an area. Press ESC to cancel."
        ).pack(pady=5)

        # Bind Mouse Events
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.root.bind("<Escape>", lambda e: self.root.destroy())

        # Selection variables
        self.start_x = None
        self.start_y = None
        self.rect = None
        self.selected_coords = None

    def on_mouse_down(self, event):
        self.start_x = event.x
        self.start_y = event.y
        # Delete previous rectangle if exists
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
        # Update the rectangle as the user drags
        self.canvas.coords(self.rect, self.start_x, self.start_y, cur_x, cur_y)

    def on_mouse_up(self, event):
        end_x, end_y = event.x, event.y

        # Final coordinates on the display image
        display_x1 = min(self.start_x, end_x)
        display_y1 = min(self.start_y, end_y)
        display_x2 = max(self.start_x, end_x)
        display_y2 = max(self.start_y, end_y)

        # Scale back to original image size for accurate cropping
        x1 = int(display_x1 * self.scale_factor)
        y1 = int(display_y1 * self.scale_factor)
        x2 = int(display_x2 * self.scale_factor)
        y2 = int(display_y2 * self.scale_factor)

        self.selected_coords = (x1, y1, x2, y2)

        # Send the final coordinates back to the main app
        self.callback(self.selected_coords)

        # Optionally, show the final crop box clearly
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
        self.root.geometry("700x650")  # Slightly taller for the new button
        self.root.resizable(False, False)

        # State variables
        self.input_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready")
        self.model_type = tk.StringVar(value="base")
        self.invert_mask = tk.BooleanVar(value=False)
        self.crop_box_var = tk.StringVar()  # This will be filled by the CropSelector
        self.bg_color = None

        self.is_processing = False

        self._setup_ui()

    def _setup_ui(self):
        # ... (GUI setup remains largely the same, but add the new button)

        # --- Header and I/O Frame setup (same as v3) ---
        header = tk.Label(
            self.root,
            text="Magic Mask: Image Background Remover",
            font=("Poppins", 16, "bold"),
        )
        header.pack(pady=15)

        io_frame = tk.LabelFrame(self.root, text="Input & Output", padx=10, pady=10)
        io_frame.pack(fill="x", padx=20, pady=5)

        # Input (row 0, 1)
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

        # Output (row 2, 3)
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

        # --- Configuration Frame setup (same as v3) ---
        config_frame = tk.LabelFrame(self.root, text="Configuration", padx=10, pady=10)
        config_frame.pack(fill="x", padx=20, pady=5)

        # Model Selection (row 0)
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

        # Invert Option (row 1)
        tk.Label(config_frame, text="Mode:").grid(
            row=1, column=0, padx=5, sticky="w", pady=5
        )
        ttk.Checkbutton(
            config_frame,
            text="Invert Mask (Remove Object, Keep Background)",
            variable=self.invert_mask,
        ).grid(row=1, column=1, columnspan=2, sticky="w")

        # Background Color Option (row 2)
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

        # --- Interactive Crop Frame ---
        crop_frame = tk.LabelFrame(
            self.root, text="Interactive Crop Selection", padx=10, pady=5
        )
        crop_frame.pack(fill="x", padx=20, pady=5)

        # New Button to launch the selector
        tk.Button(
            crop_frame,
            text="Select Crop Area Visually",
            command=self.launch_crop_selector,
            bg="#4CAF50",
            fg="white",
            font=("Arial", 10, "bold"),
        ).pack(side="left", padx=10)

        # Entry box to show the resulting coordinates
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

        # --- Action Area (same as v3) ---
        self.progress = ttk.Progressbar(
            self.root, orient="horizontal", length=400, mode="determinate"
        )
        self.progress.pack(pady=20)

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

    # --- New Function to Launch Selector ---
    def launch_crop_selector(self):
        input_path = self.input_path.get()
        if not input_path or not Path(input_path).is_file():
            messagebox.showwarning(
                "Input Needed",
                "Please select a single image file first to use the visual selector.",
            )
            return

        # Start the interactive selector window
        CropSelector(self.root, input_path, self.update_crop_box)

    def update_crop_box(self, coords):
        """Callback function to receive the selected coordinates."""
        self.crop_box_var.set(f"{coords[0]}, {coords[1]}, {coords[2]}, {coords[3]}")

    # ... (Other helper functions and run_processing logic remain the same as v3)
    # NOTE: The run_processing function in v3 is already correct and compatible with this new input method.

    # --- Helper functions (browse, color, status, reset) are omitted here for brevity but are in the full code. ---
    def pick_color(self):
        color = colorchooser.askcolor(title="Choose Background Color")
        if color[1]:
            self.bg_color = color[0]
            self.btn_color.config(text=f"Color: {color[1]}", bg=color[1], fg="black")

    def reset_color(self):
        self.bg_color = None
        self.btn_color.config(
            text="Transparent (Default)", bg="SystemButtonFace", fg="black"
        )

    def browse_file(self):
        filename = filedialog.askopenfilename(
            filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.webp;*.bmp")]
        )
        if filename:
            self.input_path.set(filename)
            # If input is a file, clear folder path
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

    # --- Processing Core (This is the run_processing function from v3, re-included for completeness) ---
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

            # Device Selection
            device = "cuda" if torch.cuda.is_available() else "cpu"
            if device == "cpu" and torch.backends.mps.is_available():
                device = "mps"

            remover = Remover(mode=self.model_type.get(), device=device)

            # Parse Crop Coordinates
            crop_coords = None
            crop_input = self.crop_box_var.get().strip()
            if crop_input:
                try:
                    coords = [int(c.strip()) for c in crop_input.split(",")]
                    crop_coords = tuple(coords) if len(coords) == 4 else None
                except:
                    pass

            # Gather files
            input_path_obj = Path(in_path)
            if input_path_obj.is_file():
                files = [input_path_obj]
            else:
                exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
                files = [
                    f for f in input_path_obj.iterdir() if f.suffix.lower() in exts
                ]

            if not files:
                raise ValueError("No valid images found.")

            os.makedirs(out_path, exist_ok=True)

            total = len(files)
            start_time = time.time()

            for i, file_path in enumerate(files):
                # Calculate ETA
                elapsed = time.time() - start_time
                if i > 0:
                    avg_time_per_img = elapsed / i
                    remaining_imgs = total - i
                    eta_seconds = int(avg_time_per_img * remaining_imgs)

                    # Format seconds to MM:SS
                    mins, secs = divmod(eta_seconds, 60)
                    eta_str = f" | ETA: {mins:02d}:{secs:02d}"
                else:
                    eta_str = " | ETA: Calculating..."

                self.update_status(f"Processing {i+1}/{total}{eta_str}")

                # --- Core Processing Logic ---
                original_img = Image.open(file_path).convert("RGB")
                original_size = original_img.size
                img_to_process = original_img.copy()

                if crop_coords:
                    try:
                        img_to_process = original_img.crop(crop_coords)
                    except:
                        img_to_process = original_img.copy()

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
                        final_img.paste(original_img.convert("RGB"), (0, 0), mask_img)
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
                0, lambda: messagebox.showinfo("Success", f"Processed {total} images.")
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
