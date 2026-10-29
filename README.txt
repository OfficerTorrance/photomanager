PHOTOMANAGER - WINDOWS 11
=========================

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
