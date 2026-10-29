"""PhotoManager: offline Windows batch image converter and photo/video collector."""
import csv
import datetime as dt
import hashlib
import json
import os
import queue
import re
import shutil
import struct
import subprocess
import threading
import tkinter as tk
from collections import Counter, defaultdict
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

register_heif_opener()
Image.MAX_IMAGE_PIXELS = 180_000_000
IMAGE_EXT = {'.heic', '.heif', '.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'}
VIDEO_EXT = {'.mov', '.mp4', '.m4v'}
MAC_EPOCH = dt.datetime(1904, 1, 1, tzinfo=dt.timezone.utc)
INDEX_NAME = 'PhotoManager_Index.json'


def parse_date(raw):
    if not raw:
        return None
    s = str(raw).strip().replace('\x00', '')
    match = re.match(r'^(\d{4})[:\-](\d\d)[:\-](\d\d)[ T](\d\d):(\d\d):(\d\d)', s)
    if match:
        try:
            return dt.datetime(*(int(n) for n in match.groups()))
        except ValueError:
            return None
    try:
        date = dt.datetime.fromisoformat(s.replace('Z', '+00:00'))
        return date.astimezone().replace(tzinfo=None) if date.tzinfo else date
    except ValueError:
        return None


def photo_date(path):
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            for tag in (36867, 36868, 306):
                val = parse_date(exif.get(tag))
                if val:
                    return val, 'EXIF capture date'
            blob = img.info.get('exif')
            if blob:
                obj = Image.Exif()
                obj.load(blob)
                for tag in (36867, 36868, 306):
                    val = parse_date(obj.get(tag))
                    if val:
                        return val, 'EXIF capture date'
    except Exception:
        pass
    return None, ''


def video_date(path):
    ffprobe = shutil.which('ffprobe')
    if ffprobe:
        try:
            result = subprocess.run([ffprobe, '-v', 'quiet', '-show_entries',
                'format_tags:stream_tags', '-of', 'json', str(path)], capture_output=True,
                text=True, timeout=25, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            data = json.loads(result.stdout)
            for field in ('com.apple.quicktime.creationdate', 'creation_time', 'date'):
                for section in [data.get('format', {})] + data.get('streams', []):
                    tags = {k.lower(): v for k, v in section.get('tags', {}).items()}
                    date = parse_date(tags.get(field))
                    if date:
                        return date, 'QuickTime metadata' + (' (UTC may differ)' if field == 'creation_time' else '')
        except Exception:
            pass
    try:
        size = path.stat().st_size
        with path.open('rb') as f:
            pos = 0
            while pos + 8 <= size:
                f.seek(pos)
                atom = f.read(8)
                length, kind = struct.unpack('>I4s', atom)
                head = 8
                if length == 1:
                    length = struct.unpack('>Q', f.read(8))[0]
                    head = 16
                elif length == 0:
                    length = size - pos
                if length < head or pos + length > size:
                    break
                if kind == b'moov':
                    sub = pos + head
                    end = pos + length
                    while sub + 8 <= end:
                        f.seek(sub)
                        length2, kind2 = struct.unpack('>I4s', f.read(8))
                        head2 = 8
                        if length2 == 1:
                            length2 = struct.unpack('>Q', f.read(8))[0]
                            head2 = 16
                        elif length2 == 0:
                            length2 = end - sub
                        if length2 < head2 or sub + length2 > end:
                            break
                        if kind2 == b'mvhd':
                            f.seek(sub + head2)
                            v = f.read(1)
                            f.read(3)
                            seconds = struct.unpack('>Q' if v == b'\x01' else '>I', f.read(8 if v == b'\x01' else 4))[0]
                            if seconds:
                                date = MAC_EPOCH + dt.timedelta(seconds=seconds)
                                if 1990 <= date.year <= dt.datetime.now().year + 2:
                                    return date.astimezone().replace(tzinfo=None), 'QuickTime header (UTC may differ)'
                        sub += length2
                pos += length
    except (OSError, OverflowError, struct.error, ValueError):
        pass
    return None, ''


def contained(path, parent):
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def gather(source, target, include_videos=True):
    result = []
    for root, dirs, names in os.walk(source):
        base = Path(root)
        dirs[:] = [d for d in dirs if not (base / d).is_symlink() and not contained(base / d, target)]
        for name in names:
            path = base / name
            if (path.suffix.lower() in IMAGE_EXT or (include_videos and path.suffix.lower() in VIDEO_EXT)) and path.is_file() and not path.is_symlink():
                result.append(path)
    return sorted(result, key=lambda x: str(x).casefold())


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def safe_stem(path):
    return (re.sub(r'[^\w\-]+', '_', path.stem, flags=re.UNICODE).strip('_')[:85] or 'Media')


def load_index(target):
    try:
        obj = json.loads((target / INDEX_NAME).read_text(encoding='utf-8'))
        return obj if obj.get('version') == 2 else {'version': 2, 'entries': []}
    except (OSError, ValueError, AttributeError):
        return {'version': 2, 'entries': []}


def save_index(target, index):
    temp = target / (INDEX_NAME + '.tmp')
    temp.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, target / INDEX_NAME)


def output_options(settings):
    return f"scale={settings['scale']};quality={settings['quality']};rename={settings['rename']};layout={settings['layout']}"


def generate_plan(source, target, options, emit=None, stop=None):
    files = gather(source, target, options.get("include_videos", True))
    original_index = load_index(target)
    existing = defaultdict(list)
    for entry in original_index['entries']:
        dest = target / entry['destination']
        if dest.is_file():
            existing[(entry['hash'], entry['options'])].append(entry['destination'])
    plan = []
    used = set()
    by_image = {}
    meta = []
    total = len(files)
    for i, path in enumerate(files, 1):
        if stop and stop.is_set():
            break
        kind = 'Video' if path.suffix.lower() in VIDEO_EXT else 'Photo'
        taken, date_source = video_date(path) if kind == 'Video' else photo_date(path)
        if not taken and (options['fallback'] or kind == 'Video'):
            taken = dt.datetime.fromtimestamp(path.stat().st_mtime)
            date_source = ('Video file modification date (automatic fallback; verify)'
                           if kind == 'Video' and not options['fallback'] else 'File modification date (fallback)')
        rel = path.relative_to(source)
        key = (str(rel.parent).casefold(), path.stem.casefold())
        if kind == 'Photo' and taken:
            by_image[key] = taken
        meta.append({'source': path, 'relative': rel, 'kind': kind, 'date': taken,
                     'date_source': date_source, 'pair_key': key})
        if emit:
            emit(('scan', i, total, path.name))
    # Pair a Live Photo's short MOV with its corresponding image when names match.
    # Only near timestamps are paired; no arbitrary pairing from matching timestamps alone.
    for item in meta:
        if item['kind'] == 'Video' and item['source'].suffix.lower() == '.mov':
            sibling_date = by_image.get(item['pair_key'])
            if sibling_date and (item['date'] is None or abs((sibling_date - item['date']).total_seconds()) <= 15):
                item['date'] = sibling_date
                item['date_source'] = 'Paired Live Photo (photo EXIF)'
    all_keys = set()
    for item in meta:
        if stop and stop.is_set():
            break
        src = item['source']
        ext = src.suffix.lower() if item['kind'] == 'Video' else '.jpg'
        taken = item['date']
        prefix = taken.strftime('%Y-%m-%d_%H-%M-%S_') if options['rename'] and taken else ''
        original = prefix + safe_stem(src) + ext
        folder = Path('.') if options['layout'] == 'flat' else item['relative'].parent
        rel = folder / original
        entry = dict(source=str(src), relative=str(item['relative']), destination=str(rel),
                     kind=item['kind'], date_source=item['date_source'], status='Ready', reason='',
                     digest='', duplicate_of='')
        if options['rename'] and not taken:
            entry.update(status='Missing date', reason='No capture date; enable modification-date fallback if appropriate')
        else:
            if options['duplicates'] or options['skip']:
                try:
                    digest = sha256(src)
                    entry['digest'] = digest
                    signature = output_options(options) if item['kind'] == 'Photo' else 'original-video'
                    matched = existing.get((digest, signature), [])
                    if options['skip'] and matched:
                        entry.update(status='Already processed', reason='Matching content found in processing index',
                                     duplicate_of=matched[0], destination=matched[0])
                    elif options['duplicates'] and (digest, signature) in all_keys:
                        entry.update(status='Duplicate content', reason='Identical source content in this batch')
                    all_keys.add((digest, signature))
                except OSError as exc:
                    entry.update(status='Error', reason='Cannot read file: ' + str(exc))
            key = str(rel).casefold()
            if entry['status'] == 'Ready':
                if options['skip'] and (target / rel).exists():
                    entry.update(status='Already exists', reason='Target filename already exists (content not checked)')
                elif key in used or (target / rel).exists():
                    n = 2
                    while True:
                        alternate = folder / (prefix + safe_stem(src) + f'_{n:03d}' + ext)
                        if str(alternate).casefold() not in used and not (target / alternate).exists():
                            rel = alternate
                            break
                        n += 1
                    entry['destination'] = str(rel)
                if entry['status'] == 'Ready':
                    used.add(str(rel).casefold())
        plan.append(entry)
    return plan, original_index, len(files)


def convert(source, destination, options):
    temp = destination.with_name(destination.name + '.partial')
    try:
        with Image.open(source) as im:
            exif = im.getexif()
            icc = im.info.get('icc_profile')
            im = ImageOps.exif_transpose(im)
            scale = options['scale']
            dims = (max(1, round(im.width * scale)), max(1, round(im.height * scale)))
            if im.size != dims:
                im = im.resize(dims, Image.Resampling.LANCZOS)
            if im.mode in ('RGBA', 'LA') or (im.mode == 'P' and 'transparency' in im.info):
                rgba = im.convert('RGBA')
                bg = Image.new('RGB', rgba.size, (255, 255, 255))
                bg.paste(rgba, mask=rgba.getchannel('A'))
                im = bg
            elif im.mode != 'RGB':
                im = im.convert('RGB')
            args = {'format': 'JPEG', 'quality': options['quality'], 'optimize': True}
            if exif:
                try:
                    exif[274] = 1
                    args['exif'] = exif.tobytes()
                except Exception:
                    pass
            if icc:
                args['icc_profile'] = icc
            with temp.open('wb') as stream:
                im.save(stream, **args)
        shutil.copystat(source, temp)
        os.replace(temp, destination)
    finally:
        if temp.exists():
            temp.unlink()


def write_reports(target, plan, scanned, cancelled, problems_extra=''):
    stamp = dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    csvfile = target / f'PhotoManager_Report_{stamp}.csv'
    txtfile = target / f'PhotoManager_Report_{stamp}.txt'
    keys = ['source', 'destination', 'kind', 'status', 'reason', 'date_source', 'duplicate_of']
    with csvfile.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=keys, delimiter=';', extrasaction='ignore')
        writer.writeheader()
        writer.writerows(plan)
    counts = Counter(x['status'] for x in plan)
    lines = ['PHOTOMANAGER - PROCESSING REPORT', dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), '',
             f'Files found: {scanned}', f'Converted/copied: {counts["Completed"]}',
             f'Skipped (already processed / exists): {counts["Already processed"] + counts["Already exists"]}',
             f'Duplicate content: {counts["Duplicate content"]}',
             f'Missing capture date: {counts["Missing date"]}', f'Errors: {counts["Error"]}',
             f'Not processed: {counts["Ready"] + counts["Cancelled"]}',
             f'Cancelled: {"Yes" if cancelled else "No"}', '',
             'ISSUES AND SKIPPED FILES', '------------------------']
    if problems_extra:
        lines += [problems_extra, '']
    issues = [x for x in plan if x['status'] != 'Completed']
    if not issues:
        lines.append('No issues.')
    for entry in issues:
        lines += ['', f'[{entry["status"]}] {entry["source"]}',
                  f'  Reason: {entry["reason"]}', f'  Destination: {entry["destination"]}']
    txtfile.write_text('\n'.join(lines), encoding='utf-8-sig')
    return txtfile, csvfile, counts


def execute_plan(target, options, plan, index, scanned, emit, stop):
    signature = output_options(options)
    for n, item in enumerate(plan, 1):
        if stop.is_set():
            for remaining in plan[n - 1:]:
                if remaining['status'] == 'Ready':
                    remaining.update(status='Cancelled', reason='Stopped by user')
            break
        if item['status'] == 'Ready':
            try:
                src = Path(item['source'])
                dest = target / item['destination']
                dest.parent.mkdir(parents=True, exist_ok=True)
                # Double-check the destination to handle changes between preview and start.
                if dest.exists():
                    item.update(status='Already exists', reason='Destination appeared after preview')
                else:
                    if item['kind'] == 'Photo':
                        convert(src, dest, options)
                    else:
                        temp = dest.with_name(dest.name + '.partial')
                        try:
                            shutil.copy2(src, temp)
                            os.replace(temp, dest)
                        finally:
                            if temp.exists():
                                temp.unlink()
                    item.update(status='Completed', reason='JPG created' if item['kind'] == 'Photo' else 'Video copied')
                    if not item['digest']:
                        item['digest'] = sha256(src)
                    index['entries'].append({'hash': item['digest'], 'options': signature if item['kind'] == 'Photo' else 'original-video',
                                             'destination': item['destination']})
            except Exception as exc:
                item.update(status='Error', reason=f'{type(exc).__name__}: {exc}')
        emit(('progress', n, len(plan), item))
    error = ''
    try:
        save_index(target, index)
        txt, csvpath, counts = write_reports(target, plan, scanned, stop.is_set())
    except Exception as exc:
        txt, csvpath, counts = None, None, Counter(x['status'] for x in plan)
        error = str(exc)
    emit(('done', str(txt) if txt else '', str(csvpath) if csvpath else '', counts, error))


class PhotoManager(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('PhotoManager | Photos & Videos')
        self.geometry('1120x790')
        self.minsize(880, 650)
        self.source = tk.StringVar()
        self.target = tk.StringVar()
        self.reduction = tk.StringVar(value='60')
        self.quality = tk.StringVar(value='85')
        self.layout = tk.StringVar(value='flat')
        self.skip = tk.BooleanVar(value=True)
        self.duplicates = tk.BooleanVar(value=True)
        self.rename = tk.BooleanVar(value=True)
        self.include_videos = tk.BooleanVar(value=True)
        self.fallback = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value='Choose source and destination folders to begin.')
        self.stats = tk.StringVar(value='No operation yet.')
        self.events = queue.Queue()
        self.stop = threading.Event()
        self.running = False
        self.plan = None
        self.plan_signature = None
        self.last_report = None
        self.build_ui()
        self.after(100, self.poll)

    def build_ui(self):
        shell = ttk.Frame(self, padding=16)
        shell.pack(fill='both', expand=True)
        ttk.Label(shell, text='PhotoManager', font=('Segoe UI', 21, 'bold')).pack(anchor='w')
        ttk.Label(shell, text='Convert images to JPEG  |  Resize  |  Collect videos  |  Detect duplicates  |  Review issues').pack(anchor='w', pady=(0, 12))
        for label, variable in [('Source folder (including subfolders)', self.source),
                                ('Destination folder', self.target)]:
            ttk.Label(shell, text=label).pack(anchor='w')
            line = ttk.Frame(shell)
            line.pack(fill='x', pady=(3, 8))
            ttk.Entry(line, textvariable=variable).pack(side='left', fill='x', expand=True)
            ttk.Button(line, text='Browse...', command=lambda v=variable: self.browse(v)).pack(side='left', padx=(8, 0))
        options = ttk.LabelFrame(shell, text='Processing options', padding=10)
        options.pack(fill='x', pady=(1, 8))
        line = ttk.Frame(options)
        line.pack(fill='x')
        ttk.Label(line, text='Reduce width and height by').pack(side='left')
        ttk.Combobox(line, textvariable=self.reduction, width=5, state='readonly',
                     values=['0', '20', '30', '40', '50', '60', '70', '80']).pack(side='left', padx=(6, 3))
        ttk.Label(line, text='%    JPEG quality').pack(side='left')
        ttk.Combobox(line, textvariable=self.quality, width=5, state='readonly',
                     values=['70', '75', '80', '85', '90', '95']).pack(side='left', padx=6)
        ttk.Label(line, text='%').pack(side='left')
        layouts = ttk.Frame(options)
        layouts.pack(fill='x', pady=(10, 6))
        ttk.Label(layouts, text='Destination layout:').pack(side='left', padx=(0, 10))
        ttk.Radiobutton(layouts, text='Put all files in one folder', variable=self.layout, value='flat').pack(side='left')
        ttk.Radiobutton(layouts, text='Preserve source folder structure', variable=self.layout, value='tree').pack(side='left', padx=(18, 0))
        for label, var in [('Include MOV / MP4 / M4V videos (copy unchanged)', self.include_videos),
                           ('Skip existing files (recommended)', self.skip),
                           ('Detect identical source content using SHA-256', self.duplicates),
                           ('Add capture date to filenames (YYYY-MM-DD_HH-MM-SS)', self.rename),
                           ('Use file modification date when capture date is missing (less reliable)', self.fallback)]:
            ttk.Checkbutton(options, text=label, variable=var).pack(anchor='w')
        ttk.Label(options, text='Originals are never modified. Videos are copied unchanged. Live Photo image/MOV pairs retain matching names where possible.',
                  foreground='#555555').pack(anchor='w', pady=(6, 0))
        controls = ttk.Frame(shell)
        controls.pack(fill='x', pady=(3, 6))
        self.preview_btn = ttk.Button(controls, text='1. Preview files', command=self.preview)
        self.preview_btn.pack(side='left')
        self.start_btn = ttk.Button(controls, text='2. Start processing', command=self.start, state='disabled')
        self.start_btn.pack(side='left', padx=(7, 0))
        self.stop_btn = ttk.Button(controls, text='Cancel', command=self.stop.set, state='disabled')
        self.stop_btn.pack(side='left', padx=(7, 0))
        self.report_btn = ttk.Button(controls, text='Open last report', command=self.open_report, state='disabled')
        self.report_btn.pack(side='right')
        self.progress = ttk.Progressbar(shell, mode='determinate')
        self.progress.pack(fill='x', pady=(5, 4))
        ttk.Label(shell, textvariable=self.status).pack(anchor='w')
        ttk.Label(shell, textvariable=self.stats, font=('Segoe UI', 10, 'bold'), wraplength=1050).pack(anchor='w', pady=(7, 6))
        notebook = ttk.Notebook(shell)
        notebook.pack(fill='both', expand=True)
        tab = ttk.Frame(notebook)
        notebook.add(tab, text='File preview and results')
        cols = ('status', 'kind', 'source', 'destination', 'reason')
        self.table = ttk.Treeview(tab, columns=cols, show='headings')
        for name, header, width in [('status', 'Status', 135), ('kind', 'Type', 65),
                                    ('source', 'Source file', 300), ('destination', 'Destination', 280),
                                    ('reason', 'Details', 260)]:
            self.table.heading(name, text=header)
            self.table.column(name, width=width, stretch=name not in ('status', 'kind'))
        yscroll = ttk.Scrollbar(tab, orient='vertical', command=self.table.yview)
        xscroll = ttk.Scrollbar(tab, orient='horizontal', command=self.table.xview)
        self.table.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.table.grid(row=0, column=0, sticky='nsew')
        yscroll.grid(row=0, column=1, sticky='ns')
        xscroll.grid(row=1, column=0, sticky='ew')
        tab.rowconfigure(0, weight=1)
        tab.columnconfigure(0, weight=1)
        logtab = ttk.Frame(notebook)
        notebook.add(logtab, text='Activity log')
        self.log = tk.Text(logtab, font=('Consolas', 9), wrap='none', state='disabled')
        self.log.pack(fill='both', expand=True)

    def browse(self, var):
        path = filedialog.askdirectory()
        if path:
            var.set(path)

    def settings(self):
        return {'scale': (100 - int(self.reduction.get())) / 100,
                'quality': int(self.quality.get()), 'layout': self.layout.get(),
                'skip': self.skip.get(), 'duplicates': self.duplicates.get(),
                'rename': self.rename.get(), 'fallback': self.fallback.get(),
                'include_videos': self.include_videos.get()}

    def get_paths(self):
        source, target = self.source.get().strip(), self.target.get().strip()
        if not source or not target or not Path(source).is_dir():
            messagebox.showerror('Invalid folders', 'Choose a valid source folder and destination folder.')
            return None
        src, dst = Path(source).resolve(), Path(target).resolve()
        if src == dst or contained(src, dst):
            messagebox.showerror('Invalid folders', 'The source cannot be the destination or be inside it.')
            return None
        try:
            dst.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror('Destination unavailable', str(exc))
            return None
        return src, dst

    def log_line(self, txt):
        self.log.config(state='normal')
        self.log.insert('end', txt + '\n')
        self.log.see('end')
        self.log.config(state='disabled')

    def preview(self):
        if self.running:
            return
        paths = self.get_paths()
        if not paths:
            return
        self.running = True
        self.plan = None
        self.stop.clear()
        self.preview_btn.config(state='disabled')
        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.status.set('Scanning files and checking capture dates / duplicates...')
        self.progress['value'] = 0
        self.stats.set('Building preview. Large libraries may take a while to hash.')
        self.table.delete(*self.table.get_children())
        src, dst = paths
        opts = self.settings()
        self.plan_signature = (str(src), str(dst), tuple(sorted(opts.items())))
        threading.Thread(target=self.preview_worker, args=(src, dst, opts), daemon=True).start()

    def preview_worker(self, src, dst, opts):
        try:
            plan, index, scanned = generate_plan(src, dst, opts, self.events.put, self.stop)
            self.events.put(('preview_done', plan, index, scanned, opts, src, dst))
        except Exception as exc:
            self.events.put(('error', f'{type(exc).__name__}: {exc}'))

    def start(self):
        if self.running or not self.plan:
            return
        paths = self.get_paths()
        if not paths:
            return
        src, dst = paths
        opts = self.settings()
        new_signature = (str(src), str(dst), tuple(sorted(opts.items())))
        if new_signature != self.plan_signature:
            messagebox.showinfo('Preview required', 'Settings or folders changed. Click Preview files again.')
            self.start_btn.config(state='disabled')
            return
        if not opts['skip'] and not messagebox.askyesno('Skipping disabled',
                'Existing files will not be overwritten. New numbered copies may be created. Continue?'):
            return
        self.running = True
        self.stop.clear()
        self.start_btn.config(state='disabled')
        self.preview_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.progress['maximum'] = max(len(self.plan), 1)
        self.progress['value'] = 0
        self.status.set('Processing files...')
        self.log_line('--- New processing run ---')
        threading.Thread(target=execute_plan,
                         args=(dst, opts, self.plan, self.index, self.scanned, self.events.put, self.stop),
                         daemon=True).start()

    def refresh_table(self):
        self.table.delete(*self.table.get_children())
        if self.plan:
            for item in self.plan:
                self.table.insert('', 'end', values=(item['status'], item['kind'], item['source'],
                            item['destination'], item['reason']))

    def poll(self):
        try:
            for _ in range(150):
                event = self.events.get_nowait()
                kind = event[0]
                if kind == 'scan':
                    _, i, total, name = event
                    self.progress['maximum'] = max(total, 1)
                    self.progress['value'] = i
                    self.status.set(f'Scanning {i} / {total}: {name}')
                elif kind == 'preview_done':
                    _, self.plan, self.index, self.scanned, self.opts, self.src, self.dst = event
                    self.running = False
                    self.stop_btn.config(state='disabled')
                    self.preview_btn.config(state='normal')
                    self.start_btn.config(state='normal' if self.plan and not self.stop.is_set() else 'disabled')
                    self.refresh_table()
                    counts = Counter(x['status'] for x in self.plan)
                    self.stats.set(f'Found: {self.scanned}   |   Ready: {counts["Ready"]}   |   Already processed/existing: '
                                   f'{counts["Already processed"] + counts["Already exists"]}   |   '
                                   f'Duplicates: {counts["Duplicate content"]}   |   Missing dates: {counts["Missing date"]}   |   Errors: {counts["Error"]}')
                    self.status.set('Preview ready. Review the table, then click Start processing.' if not self.stop.is_set() else 'Preview cancelled.')
                elif kind == 'progress':
                    _, i, total, item = event
                    self.progress['value'] = i
                    self.status.set(f'Processing {i} / {total}: {Path(item["source"]).name}')
                    # Update corresponding table line, preserving displayed order
                    rows = self.table.get_children()
                    if i - 1 < len(rows):
                        self.table.item(rows[i - 1], values=(item['status'], item['kind'], item['source'], item['destination'], item['reason']))
                    if item['status'] != 'Completed':
                        self.log_line(f'{item["status"]}: {item["source"]} - {item["reason"]}')
                elif kind == 'done':
                    _, txt, csvfile, counts, err = event
                    self.running = False
                    self.preview_btn.config(state='normal')
                    self.stop_btn.config(state='disabled')
                    self.start_btn.config(state='disabled')
                    self.refresh_table()
                    self.stats.set(f'Completed: {counts["Completed"]}   |   Already exists/processed: '
                                   f'{counts["Already exists"] + counts["Already processed"]}   |   '
                                   f'Duplicate content: {counts["Duplicate content"]}   |   '
                                   f'Missing dates: {counts["Missing date"]}   |   Errors: {counts["Error"]}   |   Cancelled: {counts["Cancelled"]}')
                    self.status.set('Finished. See the file table and report for details.' if not err else 'Finished, but report/index saving failed: ' + err)
                    self.last_report = txt
                    self.report_btn.config(state='normal' if txt else 'disabled')
                    self.log_line(self.stats.get())
                    if txt:
                        self.log_line('Report: ' + txt)
                elif kind == 'error':
                    self.running = False
                    self.preview_btn.config(state='normal')
                    self.start_btn.config(state='disabled')
                    self.stop_btn.config(state='disabled')
                    self.status.set('Operation failed: ' + event[1])
                    messagebox.showerror('Error', event[1])
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def open_report(self):
        if self.last_report and Path(self.last_report).is_file():
            os.startfile(self.last_report)


if __name__ == '__main__':
    PhotoManager().mainloop()
