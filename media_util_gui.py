import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import sys
import subprocess
from yt_dlp import YoutubeDL
from PIL import Image, ExifTags
import threading
import fitz  # PyMuPDF
from docx import Document
from openpyxl import Workbook, load_workbook
from pptx import Presentation
import io
# glitch 
def install(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])
def check_dependencies():
    try:
        import yt_dlp
    except ImportError:
        print("Installing yt-dlp...")
        install("yt-dlp")

    try:
        subprocess.run([ffmpeg_path, "-version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("\nFFmpeg not found! Required for media processing.")
        sys.exit(1)

    try:
        import pillow_heif
    except ImportError:
        print("\nInstalling pillow-heif for HEIC support...")
        install("pillow-heif")
        import pillow_heif
        pillow_heif.register_heif_opener()
import sys
import os

def get_ffmpeg_path():
    if hasattr(sys, '_MEIPASS'):
        # When bundled, ffmpeg.exe is extracted to the temporary folder.
        return os.path.join(sys._MEIPASS, "ffmpeg.exe")
    else:
        # When running from source, assume ffmpeg.exe is in the current directory (or adjust as needed).
        return os.path.join(os.getcwd(), "ffmpeg.exe")

# Use this function to get the ffmpeg path
ffmpeg_path = get_ffmpeg_path()
print(f"FFmpeg path: {ffmpeg_path}")
def get_platform(url):
    domains = {
        'youtube': ['youtube.com', 'youtu.be'],
        'facebook': ['facebook.com', 'fb.watch'],
        'instagram': ['instagram.com', 'instagr.am'],
        'tiktok': ['tiktok.com'],
        'twitter': ['twitter.com', 'x.com']
    }
    for platform, urls in domains.items():
        if any(domain in url for domain in urls):
            return platform
    return 'generic'

def parse_time(time_str):
    parts = list(map(int, time_str.split(':')))
    if len(parts) == 1:
        return parts[0]
    elif len(parts) == 2:
        return parts[0] * 60 + parts[1]
    elif len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    else:
        raise ValueError("Invalid time format. Use H:MM:SS, M:SS, or S")

def download_media(url, platform, save_dir=None, media_type='video', quality=None, start_time=None, end_time=None, audio_format="mp3"):
    # Set output template with directory if provided
    output_template = os.path.join(save_dir, '%(title)s.%(ext)s') if save_dir else '%(title)s.%(ext)s'
    
    ydl_opts = {
        'outtmpl': output_template,
        'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
        'postprocessor_args': ['-loglevel', 'error'],
        'force_keyframes_at_cuts': True
    }

    if start_time and end_time:
        start = parse_time(start_time)
        end = parse_time(end_time)
        
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4'
        }]
        ydl_opts['postprocessor_args'] += [
            '-ss', str(start), '-to', str(end),
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
            '-c:a', 'aac'
        ]
        # Also update the trimmed file output template with directory
        ydl_opts['outtmpl'] = os.path.join(save_dir, f'%(title)s_Trimmed_{start}s_{end}s.%(ext)s') if save_dir else f'%(title)s_Trimmed_{start}s_{end}s.%(ext)s'

    if media_type == 'audio':
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': audio_format,
            'preferredquality': '320'
        }]
    else:
        ydl_opts['format'] = quality or 'bestvideo+bestaudio/best'
        ydl_opts['merge_output_format'] = 'mp4'
        ydl_opts['postprocessor_args'] += ['-c:a', 'aac']

    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return True
    except Exception as e:
        print(f"Error downloading: {str(e)}")
        return False

def convert_images(file_paths, target_format):
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except ImportError:
        install("pillow-heif")
        import pillow_heif
        pillow_heif.register_heif_opener()

    format_mapping = {
        "jpg": "JPEG",
        "jpeg": "JPEG",
        "png": "PNG",
        "bmp": "BMP",
        "gif": "GIF",
        "webp": "WEBP",
        "heic": "HEIF",
        "heif": "HEIF"
    }

    target_format = format_mapping.get(target_format.lower(), target_format.upper())
    if target_format not in format_mapping.values():
        print(f"Unsupported target format: {target_format}")
        return False

    success_count = 0
    for file_path in file_paths:
        try:
            image = Image.open(file_path)
            exif_data = image.info.get("exif")
            output_path = file_path.rsplit(".", 1)[0] + f".{target_format.lower()}"

            if target_format == "HEIF":
                heif_options = {
                    "quality": 90,
                    "compression": "hevc",
                    "bit_depth": 8,
                    "chroma_subsampling": "420",
                    "save_all": False,
                }
                image.save(output_path, format="HEIF", exif=exif_data, **heif_options)
            else:
                image.save(output_path, format=target_format, quality=95)

            success_count += 1
        except Exception as e:
            print(f"Conversion failed for {file_path}: {e}")

    return success_count > 0

def convert_media(file_path):
    if not os.path.exists(file_path):
        return False

    supported_formats = {
        'audio': {'mp3', 'wav', 'aac', 'flac', 'ogg', 'm4a'},
        'video': {'mp4', 'mkv', 'avi', 'mov', 'webm', 'flv'},
        'image': {'jpg', 'jpeg', 'png', 'bmp', 'gif', 'webp', 'heic', 'heif'}
    }

    ext = os.path.splitext(file_path)[1][1:].lower()
    media_type = None
    for category, exts in supported_formats.items():
        if ext in exts:
            media_type = category
            break

    if not media_type:
        return False

    if media_type == "image":
        return convert_images([file_path], ext)

    base = os.path.splitext(file_path)[0]
    output_path = f"{base}_converted.{ext}"

    try:
        cmd = [ffmpeg_path, '-y', '-i', file_path, output_path]
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False

def convert_document(input_path, output_format):
    """Convert documents between different formats"""
    input_ext = os.path.splitext(input_path)[1].lower()
    base_name = os.path.splitext(input_path)[0]
    output_path = f"{base_name}_converted.{output_format}"
    
    # PDF to other formats
    if input_ext == '.pdf':
        doc = fitz.open(input_path)
        
        if output_format == 'docx':
            word_doc = Document()
            for page in doc:
                text = page.get_text()
                word_doc.add_paragraph(text)
            word_doc.save(output_path)
            
        elif output_format == 'pptx':
            prs = Presentation()
            for page in doc:
                slide = prs.slides.add_slide(prs.slide_layouts[5])
                text = page.get_text()
                txBox = slide.shapes.add_textbox(0, 0, prs.slide_width, prs.slide_height)
                tf = txBox.text_frame
                tf.text = text
            prs.save(output_path)
            
        elif output_format == 'xlsx':
            wb = Workbook()
            ws = wb.active
            for i, page in enumerate(doc):
                text = page.get_text()
                ws.cell(row=i+1, column=1, value=text)
            wb.save(output_path)
    
    # Word to other formats
    elif input_ext == '.docx':
        doc = Document(input_path)
        
        if output_format == 'pdf':
            # Since direct conversion isn't available, we'll save text content
            pdf_doc = fitz.open()
            page = pdf_doc.new_page()
            text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
            page.insert_text((50, 50), text)
            pdf_doc.save(output_path)
            
        elif output_format == 'xlsx':
            wb = Workbook()
            ws = wb.active
            for i, paragraph in enumerate(doc.paragraphs):
                ws.cell(row=i+1, column=1, value=paragraph.text)
            wb.save(output_path)
            
        elif output_format == 'pptx':
            prs = Presentation()
            for paragraph in doc.paragraphs:
                if paragraph.text.strip():
                    slide = prs.slides.add_slide(prs.slide_layouts[5])
                    txBox = slide.shapes.add_textbox(0, 0, prs.slide_width, prs.slide_height)
                    tf = txBox.text_frame
                    tf.text = paragraph.text
            prs.save(output_path)
    
    # Excel to other formats
    elif input_ext == '.xlsx':
        wb = load_workbook(input_path)
        ws = wb.active
        
        if output_format == 'pdf':
            pdf_doc = fitz.open()
            page = pdf_doc.new_page()
            text = "\n".join([f"{cell.value}" for row in ws.rows for cell in row if cell.value])
            page.insert_text((50, 50), text)
            pdf_doc.save(output_path)
            
        elif output_format == 'docx':
            doc = Document()
            for row in ws.rows:
                text = " ".join([str(cell.value) for cell in row if cell.value])
                if text.strip():
                    doc.add_paragraph(text)
            doc.save(output_path)
            
        elif output_format == 'pptx':
            prs = Presentation()
            slide = prs.slides.add_slide(prs.slide_layouts[5])
            txBox = slide.shapes.add_textbox(0, 0, prs.slide_width, prs.slide_height)
            tf = txBox.text_frame
            text = "\n".join([f"{cell.value}" for row in ws.rows for cell in row if cell.value])
            tf.text = text
            prs.save(output_path)
    
    # PowerPoint to other formats
    elif input_ext == '.pptx':
        prs = Presentation(input_path)
        
        if output_format == 'pdf':
            pdf_doc = fitz.open()
            for slide in prs.slides:
                page = pdf_doc.new_page()
                text = "\n".join([shape.text for shape in slide.shapes if hasattr(shape, "text")])
                page.insert_text((50, 50), text)
            pdf_doc.save(output_path)
            
        elif output_format == 'docx':
            doc = Document()
            for slide in prs.slides:
                for shape in slide.shapes:
                    if hasattr(shape, "text"):
                        doc.add_paragraph(shape.text)
            doc.save(output_path)
            
        elif output_format == 'xlsx':
            wb = Workbook()
            ws = wb.active
            row_num = 1
            for slide in prs.slides:
                for shape in slide.shapes:
                    if hasattr(shape, "text"):
                        ws.cell(row=row_num, column=1, value=shape.text)
                        row_num += 1
            wb.save(output_path)
    
    # Image to PDF
    elif input_ext.lower() in ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp']:
        if output_format == 'pdf':
            image = Image.open(input_path)
            pdf_doc = fitz.open()
            img_bytes = io.BytesIO()
            image.save(img_bytes, format='PNG')
            img_bytes.seek(0)
            page = pdf_doc.new_page()
            page.insert_image(page.rect, stream=img_bytes.getvalue())
            pdf_doc.save(output_path)
            
    return True


def trim_media(file_path, start_time, end_time):
    supported_formats = {
        'audio': {'mp3', 'wav', 'aac', 'flac', 'ogg', 'm4a'},
        'video': {'mp4', 'mkv', 'avi', 'mov', 'webm', 'flv'}
    }

    ext = os.path.splitext(file_path)[1][1:].lower()
    media_type = None
    for category, exts in supported_formats.items():
        if ext in exts:
            media_type = category
            break

    if media_type not in ['audio', 'video']:
        return False

    try:
        start = parse_time(start_time)
        end = parse_time(end_time)
    except ValueError:
        return False

    base, ext = os.path.splitext(file_path)
    output_path = f"{base}_trimmed{ext}"

    cmd = [
        ffmpeg_path, '-y',
        '-i', file_path,
        '-ss', str(start),
        '-to', str(end),
    ]

    if media_type == 'video':
        cmd += [
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
            '-c:a', 'aac', '-b:a', '192k'
        ]
    elif media_type == 'audio':
        codec_map = {
            'mp3': 'libmp3lame',
            'wav': 'pcm_s16le',
            'aac': 'aac',
            'flac': 'flac',
            'ogg': 'libvorbis',
            'm4a': 'aac'
        }
        cmd += ['-c:a', codec_map.get(ext[1:], 'copy')]

    cmd.append(output_path)

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False
def get_available_formats(url):
    with YoutubeDL({'quiet': True}) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            formats = []
            for fmt in info.get('formats', []):
                if fmt.get('vcodec') != 'none':
                    res = fmt.get('resolution', 'unknown')
                    fps = fmt.get('fps', '?')
                    ext = fmt.get('ext', '?')
                    format_id = fmt.get('format_id', '')
                    size = fmt.get('filesize') or fmt.get('filesize_approx')
                    size_mb = f"{size/(1024*1024):.1f}MB" if size else "unknown size"
                    formats.append({
                        'format_id': format_id,
                        'resolution': res,
                        'fps': fps,
                        'ext': ext,
                        'size': size_mb,
                        'display': f"{res} {fps}fps | {ext.upper()} | {size_mb}"
                    })
            return formats
        except Exception as e:
            print(f"Error getting formats: {str(e)}")
            return []
        
class MediaUtilityGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Media Utility")
        self.root.geometry("800x600")
        self.video_quality = None
        self.current_thread = None
        self.cancel_requested = False
        
        # Initialize notebook
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=5)
        
        # Create all tabs
        self.download_tab = ttk.Frame(self.notebook)
        self.convert_tab = ttk.Frame(self.notebook)
        self.batch_convert_tab = ttk.Frame(self.notebook)
        self.trim_tab = ttk.Frame(self.notebook)
        self.document_tab = ttk.Frame(self.notebook)  # Add document tab
        
        # Add all tabs to notebook
        self.notebook.add(self.download_tab, text='Download Media')
        self.notebook.add(self.convert_tab, text='Convert Media')
        self.notebook.add(self.batch_convert_tab, text='Batch Convert')
        self.notebook.add(self.trim_tab, text='Trim Media')
        self.notebook.add(self.document_tab, text='Document Convert')
        
        # Setup all tabs
        self.setup_download_tab()
        self.setup_convert_tab()
        self.setup_batch_convert_tab()
        self.setup_trim_tab()
        self.setup_document_tab()  # Setup document tab
        
        # Setup status frame
        self.status_frame = ttk.Frame(root)
        self.status_frame.pack(fill='x', padx=10, pady=5)
        self.progress_frame = ttk.Frame(self.status_frame)
        self.progress_frame.pack(fill='x', pady=5)
        self.progress = ttk.Progressbar(self.progress_frame, mode='indeterminate')
        self.progress.pack(side='left', fill='x', expand=True, padx=(0, 5))
        self.cancel_button = ttk.Button(self.progress_frame, text="Cancel", 
                                      command=self.cancel_operation, state='disabled')
        self.cancel_button.pack(side='right')
        self.status_label = ttk.Label(self.status_frame, text="Ready")
        self.status_label.pack(pady=5)
        
    def setup_download_tab(self):
        url_frame = ttk.Frame(self.download_tab)
        url_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(url_frame, text="Enter URL:").pack(side='left', padx=5)
        self.url_entry = ttk.Entry(url_frame, width=60)
        self.url_entry.pack(side='left', padx=5, expand=True, fill='x')
        
        ttk.Button(url_frame, text="Check Available Formats", 
                command=self.check_formats).pack(side='left', padx=5)
        
        # Add save location frame
        save_frame = ttk.Frame(self.download_tab)
        save_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(save_frame, text="Save to:").pack(side='left', padx=5)
        self.save_location = ttk.Entry(save_frame, width=60)
        self.save_location.pack(side='left', padx=5, expand=True, fill='x')
        # Set default location to current directory
        self.save_location.insert(0, os.getcwd())
        
        ttk.Button(save_frame, text="Browse", 
                command=self.browse_save_location).pack(side='left', padx=5)
        
        quality_frame = ttk.LabelFrame(self.download_tab, text="Video Quality")
        quality_frame.pack(pady=10, padx=10, fill='both', expand=True)
        
        self.quality_container = ttk.Frame(quality_frame)
        self.quality_container.pack(fill='both', expand=True)
        
        scrollbar = ttk.Scrollbar(self.quality_container)
        scrollbar.pack(side='right', fill='y')
        
        self.quality_listbox = tk.Listbox(self.quality_container, 
                                        yscrollcommand=scrollbar.set,
                                        height=6)
        self.quality_listbox.pack(side='left', fill='both', expand=True)
        scrollbar.config(command=self.quality_listbox.yview)
        
        media_frame = ttk.LabelFrame(self.download_tab, text="Media Type")
        media_frame.pack(pady=10, padx=10, fill='x')
        
        self.media_type = tk.StringVar(value="video")
        ttk.Radiobutton(media_frame, text="Video", variable=self.media_type, 
                    value="video", command=self.update_format_visibility).pack(side='left', padx=20)
        ttk.Radiobutton(media_frame, text="Audio", variable=self.media_type,
                    value="audio", command=self.update_format_visibility).pack(side='left', padx=20)
        
        self.audio_frame = ttk.LabelFrame(self.download_tab, text="Audio Format")
        self.audio_frame.pack(pady=10, padx=10, fill='x')
        
        self.download_audio_format = tk.StringVar(value="mp3")
        formats = ['mp3', 'aac', 'flac', 'wav', 'opus', 'm4a']
        for fmt in formats:
            ttk.Radiobutton(self.audio_frame, text=fmt.upper(), variable=self.download_audio_format, value=fmt).pack(side='left', padx=10)
        
        time_frame = ttk.LabelFrame(self.download_tab, text="Time Range (Optional)")
        time_frame.pack(pady=10, padx=10, fill='x')
        
        ttk.Label(time_frame, text="Start Time:").pack(side='left', padx=5)
        self.start_time = ttk.Entry(time_frame, width=10)
        self.start_time.pack(side='left', padx=5)
        
        ttk.Label(time_frame, text="End Time:").pack(side='left', padx=5)
        self.end_time = ttk.Entry(time_frame, width=10)
        self.end_time.pack(side='left', padx=5)
        
        ttk.Button(self.download_tab, text="Download", 
                command=self.start_download).pack(pady=20)
    
    # Add the browse_save_location method to the MediaUtilityGUI class:
    def browse_save_location(self):
        directory = filedialog.askdirectory()
        if directory:
            self.save_location.delete(0, tk.END)
            self.save_location.insert(0, directory)
    
    def cancel_operation(self):
        if self.current_thread and self.current_thread.is_alive():
            self.cancel_requested = True
            self.update_status("Cancelling operation...")
            self.cancel_button.config(state='disabled')

    def start_progress(self):
        self.progress.start(10)
        self.cancel_button.config(state='normal')
        self.cancel_requested = False
        self.root.update()

    def stop_progress(self):
        self.progress.stop()
        self.cancel_button.config(state='disabled')
        self.current_thread = None
        self.root.update()

    def update_status(self, message, is_error=False):
        self.status_label.config(text=message, 
                               foreground='red' if is_error else 'black')
        self.root.update()

    def check_formats(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("Error", "Please enter a URL")
            return
        
        self.quality_listbox.delete(0, tk.END)
        self.quality_listbox.insert(tk.END, "Checking available formats...")
        self.root.update()

        def check_formats_thread():
            self.start_progress()
            try:
                if not self.cancel_requested:
                    formats = get_available_formats(url)
                    if not self.cancel_requested:
                        self.root.after(0, self.update_quality_list, formats)
                    else:
                        self.root.after(0, self.update_status, "Format check cancelled.")
            except Exception as e:
                if not self.cancel_requested:
                    self.root.after(0, self.update_status, f"Error checking formats: {str(e)}", True)
            finally:
                self.stop_progress()
        
        self.current_thread = threading.Thread(target=check_formats_thread, daemon=True)
        self.current_thread.start()

    
    def update_quality_list(self, formats):
        self.quality_listbox.delete(0, tk.END)
        self.quality_listbox.insert(tk.END, "Best Quality (Automatic)")
        self.formats = formats
        for fmt in formats:
            self.quality_listbox.insert(tk.END, fmt['display'])
    def update_format_visibility(self):
        if self.media_type.get() == 'audio':
            self.quality_container.pack_forget()
            self.audio_frame.pack(pady=10, padx=10, fill='x')
        else:
            self.quality_container.pack(fill='both', expand=True)
            self.audio_frame.pack(pady=10, padx=10, fill='x')
            
    def setup_convert_tab(self):
        # File Selection
        file_frame = ttk.Frame(self.convert_tab)
        file_frame.pack(pady=10, fill='x')
        
        self.convert_path = ttk.Entry(file_frame, width=60)
        self.convert_path.pack(side='left', padx=5)
        
        ttk.Button(file_frame, text="Browse", 
                command=lambda: self.browse_file(self.convert_path)).pack(side='left')
        
        # Media Type Display
        self.media_type_label = ttk.Label(self.convert_tab, text="Media Type: None")
        self.media_type_label.pack(pady=5)
        
        # Format Selection Frame
        self.format_notebook = ttk.Notebook(self.convert_tab)
        self.format_notebook.pack(pady=10, padx=10, fill='both', expand=True)
        
        # Create tabs for each media type
        self.audio_frame = ttk.Frame(self.format_notebook)
        self.video_frame = ttk.Frame(self.format_notebook)
        self.image_frame = ttk.Frame(self.format_notebook)
        
        self.format_notebook.add(self.audio_frame, text='Audio Formats')
        self.format_notebook.add(self.video_frame, text='Video Formats')
        self.format_notebook.add(self.image_frame, text='Image Formats')
        
        # Audio Formats
        self.audio_format = tk.StringVar()
        audio_formats = ['mp3', 'wav', 'aac', 'flac', 'ogg', 'm4a']
        self.setup_format_grid(self.audio_frame, audio_formats, self.audio_format)
        
        # Video Formats
        self.video_format = tk.StringVar()
        video_formats = ['mp4', 'mkv', 'avi', 'mov', 'webm', 'flv']
        self.setup_format_grid(self.video_frame, video_formats, self.video_format)
        
        # Image Formats
        self.image_format = tk.StringVar()
        image_formats = ['jpg', 'jpeg', 'png', 'bmp', 'gif', 'webp', 'heic', 'heif']
        self.setup_format_grid(self.image_frame, image_formats, self.image_format)
        
        # Convert Button
        self.convert_button = ttk.Button(self.convert_tab, text="Convert", 
                                    command=self.start_conversion)
        self.convert_button.pack(pady=20)
        
        # Bind file selection to update media type
        self.convert_path.bind('<KeyRelease>', self.update_media_type)
    def setup_format_grid(self, parent, formats, var):
        row = 0
        col = 0
        for fmt in formats:
            ttk.Radiobutton(parent, text=fmt.upper(), 
                        variable=var, value=fmt).grid(
                            row=row, column=col, padx=10, pady=5)
            col += 1
            if col > 3: 
                col = 0
                row += 1
    def update_media_type(self, event=None):
        file_path = self.convert_path.get()
        if not file_path or not os.path.exists(file_path):
            self.media_type_label.config(text="Media Type: None")
            return
        
        ext = os.path.splitext(file_path)[1][1:].lower()
        supported_formats = {
            'audio': {'mp3', 'wav', 'aac', 'flac', 'ogg', 'm4a'},
            'video': {'mp4', 'mkv', 'avi', 'mov', 'webm', 'flv'},
            'image': {'jpg', 'jpeg', 'png', 'bmp', 'gif', 'webp', 'heic', 'heif'}
        }
        
        media_type = None
        for category, exts in supported_formats.items():
            if ext in exts:
                media_type = category
                break
        
        if media_type:
            self.media_type_label.config(text=f"Media Type: {media_type.capitalize()}")
            tab_index = {'audio': 0, 'video': 1, 'image': 2}.get(media_type, 0)
            self.format_notebook.select(tab_index)
        else:
            self.media_type_label.config(text="Media Type: Unsupported format")
    def get_current_format_var(self):
        current_tab = self.format_notebook.select()
        tab_index = self.format_notebook.index(current_tab)
        return {
            0: self.audio_format,
            1: self.video_format,
            2: self.image_format
        }.get(tab_index)
    
    def setup_batch_convert_tab(self):
        file_frame = ttk.Frame(self.batch_convert_tab)
        file_frame.pack(pady=10, fill='x')
        
        self.batch_files = ttk.Entry(file_frame, width=60)
        self.batch_files.pack(side='left', padx=5)
        
        ttk.Button(file_frame, text="Browse", 
                command=self.browse_multiple_files).pack(side='left')
        
        self.files_frame = ttk.LabelFrame(self.batch_convert_tab, text="Selected Files")
        self.files_frame.pack(pady=10, padx=10, fill='both', expand=True)
        
        self.files_text = tk.Text(self.files_frame, height=5, width=50)
        scrollbar = ttk.Scrollbar(self.files_frame, command=self.files_text.yview)
        self.files_text.configure(yscrollcommand=scrollbar.set)
        self.files_text.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        self.files_text.config(state='disabled')
        
        self.batch_type_label = ttk.Label(self.batch_convert_tab, text="Media Type: None")
        self.batch_type_label.pack(pady=5)
        
        self.batch_format_notebook = ttk.Notebook(self.batch_convert_tab)
        self.batch_format_notebook.pack(pady=10, padx=10, fill='both', expand=True)
        
        self.batch_audio_frame = ttk.Frame(self.batch_format_notebook)
        self.batch_video_frame = ttk.Frame(self.batch_format_notebook)
        self.batch_image_frame = ttk.Frame(self.batch_format_notebook)
        
        self.batch_format_notebook.add(self.batch_audio_frame, text='Audio Formats')
        self.batch_format_notebook.add(self.batch_video_frame, text='Video Formats')
        self.batch_format_notebook.add(self.batch_image_frame, text='Image Formats')
        
        # Audio Formats
        self.batch_audio_format = tk.StringVar()
        audio_formats = ['mp3', 'wav', 'aac', 'flac', 'ogg', 'm4a']
        self.setup_format_grid(self.batch_audio_frame, audio_formats, self.batch_audio_format)
        
        # Video Formats
        self.batch_video_format = tk.StringVar()
        video_formats = ['mp4', 'mkv', 'avi', 'mov', 'webm', 'flv']
        self.setup_format_grid(self.batch_video_frame, video_formats, self.batch_video_format)
        
        # Image Formats
        self.batch_image_format = tk.StringVar()
        image_formats = ['jpg', 'jpeg', 'png', 'bmp', 'gif', 'webp', 'heic', 'heif']
        self.setup_format_grid(self.batch_image_frame, image_formats, self.batch_image_format)
        
        self.batch_convert_button = ttk.Button(self.batch_convert_tab, text="Convert All", 
                                            command=self.start_batch_conversion)
        self.batch_convert_button.pack(pady=20)
    def browse_multiple_files(self):
        filenames = filedialog.askopenfilenames()
        if filenames:
            self.batch_files.delete(0, tk.END)
            self.batch_files.insert(0, ';'.join(filenames))
            
            self.files_text.config(state='normal')
            self.files_text.delete(1.0, tk.END)
            for file in filenames:
                self.files_text.insert(tk.END, f"{os.path.basename(file)}\n")
            self.files_text.config(state='disabled')
            
            self.update_batch_media_type(filenames)
    def update_batch_media_type(self, filenames):
        if not filenames:
            self.batch_type_label.config(text="Media Type: None")
            return
        
        supported_formats = {
            'audio': {'mp3', 'wav', 'aac', 'flac', 'ogg', 'm4a'},
            'video': {'mp4', 'mkv', 'avi', 'mov', 'webm', 'flv'},
            'image': {'jpg', 'jpeg', 'png', 'bmp', 'gif', 'webp', 'heic', 'heif'}
        }
        
        extensions = {os.path.splitext(f)[1][1:].lower() for f in filenames}
        
        media_types = set()
        for ext in extensions:
            for media_type, formats in supported_formats.items():
                if ext in formats:
                    media_types.add(media_type)
                    break
        
        if len(media_types) > 1:
            self.batch_type_label.config(text="Media Type: Mixed (not supported)")
            messagebox.showwarning("Warning", 
                                "Mixed media types detected. Please select files of the same type.")
        elif len(media_types) == 1:
            media_type = media_types.pop()
            self.batch_type_label.config(text=f"Media Type: {media_type.capitalize()}")
            tab_index = {'audio': 0, 'video': 1, 'image': 2}.get(media_type, 0)
            self.batch_format_notebook.select(tab_index)
        else:
            self.batch_type_label.config(text="Media Type: Unsupported format")

    def get_current_batch_format_var(self):
        current_tab = self.batch_format_notebook.select()
        tab_index = self.batch_format_notebook.index(current_tab)
        return {
            0: self.convert_audio_format,
            1: self.video_format,
            2: self.image_format
        }.get(tab_index)
    def setup_trim_tab(self):
        file_frame = ttk.Frame(self.trim_tab)
        file_frame.pack(pady=10, fill='x')
        
        self.trim_path = ttk.Entry(file_frame, width=60)
        self.trim_path.pack(side='left', padx=5)
        
        ttk.Button(file_frame, text="Browse", 
                  command=lambda: self.browse_file(self.trim_path)).pack(side='left')
        
        time_frame = ttk.LabelFrame(self.trim_tab, text="Time Range")
        time_frame.pack(pady=10, padx=10, fill='x')
        
        ttk.Label(time_frame, text="Start Time:").pack(side='left', padx=5)
        self.trim_start = ttk.Entry(time_frame, width=10)
        self.trim_start.pack(side='left', padx=5)
        
        ttk.Label(time_frame, text="End Time:").pack(side='left', padx=5)
        self.trim_end = ttk.Entry(time_frame, width=10)
        self.trim_end.pack(side='left', padx=5)
        
        ttk.Button(self.trim_tab, text="Trim Media", 
                  command=self.start_trim).pack(pady=20)

    def setup_document_tab(self):
        # File Selection
        file_frame = ttk.Frame(self.document_tab)
        file_frame.pack(pady=10, fill='x')
        
        self.doc_path = ttk.Entry(file_frame, width=60)
        self.doc_path.pack(side='left', padx=5)
        
        ttk.Button(file_frame, text="Browse", 
                command=lambda: self.browse_file(self.doc_path)).pack(side='left')
        
        # Format Selection
        format_frame = ttk.LabelFrame(self.document_tab, text="Target Format")
        format_frame.pack(pady=10, padx=10, fill='x')
        
        self.doc_format = tk.StringVar()
        formats = ['pdf', 'docx', 'xlsx', 'pptx']
        for fmt in formats:
            ttk.Radiobutton(format_frame, text=fmt.upper(), 
                        variable=self.doc_format, value=fmt).pack(side='left', padx=10)
        
        # Convert Button
        ttk.Button(self.document_tab, text="Convert", 
                command=self.start_doc_conversion).pack(pady=20)
    
    def start_doc_conversion(self):
        file_path = self.doc_path.get()
        if not file_path or not os.path.exists(file_path):
            messagebox.showerror("Error", "Please select a valid file")
            return
        
        if not self.doc_format.get():
            messagebox.showerror("Error", "Please select a target format")
            return
            
        def convert_thread():
            self.start_progress()
            self.update_status("Converting document...")
            try:
                if not self.cancel_requested:
                    success = convert_document(file_path, self.doc_format.get())
                    if success and not self.cancel_requested:
                        self.update_status("Conversion completed successfully!")
                    elif self.cancel_requested:
                        self.update_status("Conversion cancelled.")
                    else:
                        self.update_status("Conversion failed!", True)
            except Exception as e:
                if not self.cancel_requested:
                    self.update_status(f"Error: {str(e)}", True)
            finally:
                self.stop_progress()
        
        self.current_thread = threading.Thread(target=convert_thread, daemon=True)
        self.current_thread.start()
    
    def browse_file(self, entry_widget):
        filename = filedialog.askopenfilename()
        if filename:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, filename)

    def browse_multiple_files(self):
        filenames = filedialog.askopenfilenames()
        if filenames:
            self.batch_files.delete(0, tk.END)
            self.batch_files.insert(0, ';'.join(filenames))

    def start_download(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("Error", "Please enter a URL")
            return
        
        # Get the save location
        save_dir = self.save_location.get().strip()
        if not save_dir:
            save_dir = os.getcwd()  # Default to current directory if empty
        
        # Validate the directory exists
        if not os.path.isdir(save_dir):
            messagebox.showerror("Error", "Invalid save location. Please select a valid directory.")
            return
        
        quality = None
        if self.media_type.get() == 'video':
            selected_idx = self.quality_listbox.curselection()
            if selected_idx:
                if selected_idx[0] == 0:  # Best Quality
                    quality = 'bestvideo+bestaudio/best'
                elif hasattr(self, 'formats') and self.formats:
                    fmt = self.formats[selected_idx[0] - 1]
                    quality = f"{fmt['format_id']}+bestaudio/best"
        
        def download_thread():
            self.start_progress()
            self.update_status("Downloading...")
            try:
                if not self.cancel_requested:
                    success = download_media(
                        url=url,
                        platform=get_platform(url),
                        save_dir=save_dir,  # Pass the save directory
                        media_type=self.media_type.get(),
                        quality=quality,
                        start_time=self.start_time.get() if self.start_time.get() else None,
                        end_time=self.end_time.get() if self.end_time.get() else None,
                        audio_format=self.download_audio_format.get()
                    )
                    if success and not self.cancel_requested:
                        self.update_status(f"Download completed successfully to {save_dir}!")
                    elif self.cancel_requested:
                        self.update_status("Download cancelled.")
                    else:
                        self.update_status("Download failed!", True)
            except Exception as e:
                if not self.cancel_requested:
                    self.update_status(f"Error: {str(e)}", True)
            finally:
                self.stop_progress()
        
        self.current_thread = threading.Thread(target=download_thread, daemon=True)
        self.current_thread.start()

    def start_batch_conversion(self):
        files = self.batch_files.get().split(';')
        if not files or not files[0]:
            messagebox.showerror("Error", "Please select files to convert")
            return

        format_var = self.get_current_batch_format_var()
        if not format_var or not format_var.get():
            messagebox.showerror("Error", "Please select a target format")
            return

        target_format = format_var.get()

        def batch_convert_thread():
            self.start_progress()
            self.update_status("Converting files...")
            try:
                for i, file_path in enumerate(files):
                    if self.cancel_requested:
                        self.update_status("Batch conversion cancelled.")
                        return
                    
                    self.update_status(f"Converting file {i+1} of {len(files)}...")
                    success = convert_images([file_path], target_format)
                    
                    if not success and not self.cancel_requested:
                        self.update_status(f"Failed to convert {os.path.basename(file_path)}", True)
                        return

                if not self.cancel_requested:
                    self.update_status(f"Successfully converted {len(files)} files!")
                
            except Exception as e:
                if not self.cancel_requested:
                    self.update_status(f"Error: {str(e)}", True)
            finally:
                self.stop_progress()

        self.current_thread = threading.Thread(target=batch_convert_thread, daemon=True)
        self.current_thread.start()



    def start_conversion(self):
        file_path = self.convert_path.get()
        if not file_path or not os.path.exists(file_path):
            messagebox.showerror("Error", "Please select a valid file")
            return
        
        format_var = self.get_current_format_var()
        if not format_var or not format_var.get():
            messagebox.showerror("Error", "Please select a target format")
            return

        target_format = format_var.get()
        
        def convert_thread():
            self.start_progress()
            self.update_status("Converting...")
            try:
                if self.cancel_requested:
                    self.update_status("Conversion cancelled.")
                    return

                ext = os.path.splitext(file_path)[1][1:].lower()
                if ext == target_format:
                    self.update_status("Source and target formats are the same!", True)
                    return

                supported_formats = {
                    'audio': {'mp3', 'wav', 'aac', 'flac', 'ogg', 'm4a'},
                    'video': {'mp4', 'mkv', 'avi', 'mov', 'webm', 'flv'},
                    'image': {'jpg', 'jpeg', 'png', 'bmp', 'gif', 'webp', 'heic', 'heif'}
                }
                
                media_type = None
                for category, formats in supported_formats.items():
                    if ext in formats:
                        media_type = category
                        break

                if self.cancel_requested:
                    self.update_status("Conversion cancelled.")
                    return

                if media_type == "image":
                    success = convert_images([file_path], target_format)
                else:
                    base = os.path.splitext(file_path)[0]
                    output_path = f"{base}_converted.{target_format}"
                    
                    if media_type == 'video' and target_format in supported_formats['audio']:
                        cmd = [
                            ffmpeg_path, '-y',
                            '-i', file_path,
                            '-vn',  # Disable video
                            '-acodec', 'libmp3lame' if target_format == 'mp3' else target_format,
                            output_path
                        ]
                    else:
                        cmd = [ffmpeg_path, '-y', '-i', file_path, output_path]
                    
                    if not self.cancel_requested:
                        result = subprocess.run(cmd, capture_output=True)
                        success = result.returncode == 0
                    else:
                        self.update_status("Conversion cancelled.")
                        return

                if success and not self.cancel_requested:
                    self.update_status("Conversion completed successfully!")
                elif self.cancel_requested:
                    self.update_status("Conversion cancelled.")
                else:
                    self.update_status("Conversion failed!", True)
                    
            except Exception as e:
                if not self.cancel_requested:
                    self.update_status(f"Error: {str(e)}", True)
            finally:
                self.stop_progress()
        
        self.current_thread = threading.Thread(target=convert_thread, daemon=True)
        self.current_thread.start()


    def start_trim(self):
        file_path = self.trim_path.get()
        if not file_path or not os.path.exists(file_path):
            messagebox.showerror("Error", "Please select a valid file")
            return
        
        def trim_thread():
            self.start_progress()
            self.update_status("Trimming media...")
            try:
                if not self.cancel_requested:
                    success = trim_media(
                        file_path,
                        self.trim_start.get(),
                        self.trim_end.get()
                    )
                    if success and not self.cancel_requested:
                        self.update_status("Trimming completed successfully!")
                    elif self.cancel_requested:
                        self.update_status("Trimming cancelled.")
                    else:
                        self.update_status("Trimming failed!", True)
            except Exception as e:
                if not self.cancel_requested:
                    self.update_status(f"Error: {str(e)}", True)
            finally:
                self.stop_progress()
        
        self.current_thread = threading.Thread(target=trim_thread, daemon=True)
        self.current_thread.start()

def main():
    check_dependencies()
    root = tk.Tk()
    app = MediaUtilityGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()