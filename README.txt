PHOTOMANAGER - WINDOWS 11
=========================
# PhotoManager – Photo & Video Management Made Easy

**PhotoManager** is a lightweight, user-friendly Windows application designed to simplify the organisation and processing of large photo and video collections.

Whether you're transferring thousands of photos from an iPhone, consolidating files from multiple folders or preparing images for long-term storage, PhotoManager automates repetitive tasks while keeping you in control.

### Key Features

**Image Conversion & Resizing**
- Convert HEIC, HEIF, PNG, TIFF and other supported image formats to JPG.
- Automatically resize images by a configurable percentage (60% reduction by default).
- Adjust JPEG compression quality to balance file size and image quality.
- Process thousands of images in a single batch.

**Video Support**
- Include MOV, MP4 and M4V video files.
- Copy videos without re-encoding or reducing quality.
- Extract recording dates from available metadata.
- Use file modification dates as a fallback when recording metadata is unavailable.

**Smart File Organisation**
- Automatically scan folders and subfolders.
- Consolidate all processed files into one destination folder or preserve the original folder structure.
- Rename photos and videos using their capture dates.
- Prevent filename conflicts and optionally skip existing files.
- Identify duplicate source files using SHA-256 checksums.
- Recognise related Live Photo image and video components.

**Preview & Processing**
- Preview planned operations before processing.
- Monitor progress throughout batch operations.
- Keep original files untouched.

**Detailed Reports**
- View a clear processing summary.
- Identify successfully processed, skipped and duplicate files.
- Review missing metadata and processing errors.
- Export detailed CSV and TXT reports for troubleshooting.

### Designed for Simplicity

PhotoManager provides an intuitive graphical interface, making advanced batch processing accessible without command-line experience.

**Platform:** Windows 11  
**Interface language:** English  
**Default image reduction:** 60% (width and height)  
**Default JPEG quality:** 85%  
**Video processing:** Copy without re-encoding

### Ideal For

- Backing up and organising iPhone photo libraries.
- Converting HEIC images into universally compatible JPG files.
- Reducing image dimensions to save storage space.
- Consolidating photos and videos from multiple folders.
- Organising large collections by capture date.
- Identifying duplicates and avoiding unnecessary reprocessing.

INSTALL AND START
1. Extract this ZIP file to a normal local folder.
2. Install Python 3.11 or newer from https://www.python.org/downloads/windows/
   (tick Add Python to PATH during installation).
3. Double-click Start.bat. Required packages are installed automatically
   on the first launch (internet connection needed for first install).
4. Choose your source and destination folders.
5. Choose output layout: all files together, or preserve subfolders.
6. Adjust image reduction (default 60%) and JPEG quality (default 85%).
7. Click "1. Preview files", review the list, then "2. Start processing".
8. Review the table and the CSV/TXT reports in the destination folder.

FEATURES
- Include MOV/MP4/M4V videos is enabled by default (toggle in settings).
- Videos missing QuickTime capture metadata are STILL COPIED: the file
  modification date is used for their output name and flagged in preview.
- Converts HEIC/HEIF/JPG/PNG/etc. to JPEG and reduces image dimensions.
- Copies MOV/MP4/M4V without changing the video.
- Flat output or preserved source subfolder structure.
- Date-based names (capture date from EXIF / QuickTime where available).
- Optional modification-date fallback when capture date is missing.
- Live Photo pairs (matching original stem in the same source folder) use
  the same capture time where reasonably possible.
- Optional SHA-256 content duplicate detection, including files with
  different source names; optional skip if destination exists.
- Re-running with the same settings can skip files recorded in the index.
- No originals are modified. No existing destination is overwritten.
- A preview, progress bar and reports show skipped and failed files.

IMPORTANT NOTES
- A 60% reduction means each image dimension becomes 40% of its original,
  NOT a guarantee to reduce storage size by 60%.
- If date fallback is disabled, PHOTOS lacking capture dates are skipped
  when date-based names are enabled. Videos are always copied using their
  modification date as fallback; review those timestamps before archiving.
- QuickTime timestamps sometimes use UTC; check a few videos in preview.
- Live Photo pairing is best effort, based on filename and proximity of dates.
- SHA-256 duplicates are detected for IDENTICAL SOURCE BYTES. Edited or
  recompressed versions of the same photo are not detected as duplicates.
- With "Skip existing files" enabled, a destination NAME collision is skipped
  even if the contents are different. The report identifies this situation.
- The processing index tracks successful outputs and is saved in the target.
  Do not delete it if you want reliable re-run detection.
- Files are COPIED, not moved. Keep original files until you verify the backup.
- When you change output settings, previously exported photos may be processed
  again, since settings are part of the index key.
- Any previously created PhotoManager index from earlier tools is not imported.

Privacy: All processing is performed locally; no files are uploaded.
