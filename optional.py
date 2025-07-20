# --- Optional functions specified by flags ---
import re
import shutil
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TCON, TDRC, COMM


def create_opf(metadata, opf_template, dry_run=False):
    if dry_run:
        print(f"[DRY-RUN] Would create OPF file in: {metadata['final_output']}")
        return

    # --- Generate .opf Metadata file ---

    with opf_template.open('r') as file:
        template = file.read()

    # - Author -
    if metadata['author'] == '__unknown__':
        template = re.sub(r"__AUTHOR__", '', template)
    else:
        template = re.sub(r"__AUTHOR__", metadata['author'], template)

    # - Title -
    if metadata['title'] == metadata['input_folder']:
        template = re.sub(r"__TITLE__", '', template)
    else:
        template = re.sub(r"__TITLE__", metadata['title'], template)

    # - Summary -
    template = re.sub(r"__SUMMARY__", metadata['summary'], template)

    # - Subtitle -
    template = re.sub(r"__SUBTITLE__", metadata['subtitle'], template)

    # - Narrator -
    template = re.sub(r"__NARRATOR__", metadata['narrator'], template)

    # - Publisher -
    template = re.sub(r"__PUBLISHER__", metadata['publisher'], template)

    # - Publish Year -
    template = re.sub(r"__PUBLISHYEAR__", metadata['publishyear'], template)

    # - Genres -
    # Handle both string (old format) and list (new format)
    if isinstance(metadata['genres'], list):
        genre_list = metadata['genres']
    else:
        # Convert comma-separated string to list
        genre_list = [g.strip() for g in metadata['genres'].split(',')] if metadata['genres'] else []
    
    # Create XML structure for genres
    genre_xml = ""
    for genre in genre_list:
        genre_xml += f"<dc:subject>{genre}</dc:subject>\n    "
    # Remove trailing newline and spaces
    genre_xml = genre_xml.rstrip()
    
    template = re.sub(r"__GENRES__", genre_xml, template)

    # - ISBN -
    template = re.sub(r"__ISBN__", metadata['isbn'], template)

    # - ASIN -
    template = re.sub(r"__ASIN__", metadata['asin'], template)

    # - LANGUAGE -
    template = re.sub(r"__LANGUAGE__", metadata['language'], template)

    # - Series -
    template = re.sub(r"__SERIES__", metadata['series'], template)

    # - Volume Number -
    template = re.sub(r"__VOLUMENUMBER__", metadata['volumenumber'], template)

    opf_output = metadata['final_output'] / 'metadata.opf'
    with opf_output.open('w', encoding='utf-8') as file:
        file.write(template)

    return


def create_info(metadata, dry_run=False):
    if dry_run:
        print(f"[DRY-RUN] Would create info.txt in: {metadata['final_output']}")
        return

    # --- Generate info.txt summary file ---
    txt_file = metadata['final_output'] / 'info.txt'
    with txt_file.open('w', encoding='utf-8') as file:
        file.write(metadata['summary'])


def flatten_folder(metadata, log, dry_run=False):
    if dry_run:
        print(f"[DRY-RUN] Would flatten folder: {metadata['final_output']}")
        return
    # --- Flatten folder and rename audio files to avoid conflicts ---

    # - Get all audio files -
    audio_ext = ['mp3', 'm4b', 'm4a', 'ogg']
    audio_files = []
    for extension in audio_ext:
        results = sorted(metadata['final_output'].rglob(f"./*.{extension}"))
        for result in results:
            if result.parent != metadata['final_output']:
                audio_files.append(result)

    # - Sort files for renaming
    audio_files.sort()
    log.debug(f"Globbed audio files for flattening = {str(audio_files)}")

    # - Move all audio files to root of book folder -
    track = 1
    padding = 2
    if len(audio_files) >= 100:
        padding = 3

    for file in audio_files:
        clean_title = re.sub(r"[^\w\-\.\(\) ]+", '', metadata['title'])
        file.rename(metadata['final_output'] / f"{str(track).zfill(padding)} - {clean_title}{file.suffix}")
        log.debug(metadata['final_output'] / f"{str(track).zfill(padding)} - {clean_title}{file.suffix}")
        track += 1

    # - Delete old folders -
    for file in audio_files:
        if file.parent != metadata['final_output']:
            shutil.rmtree(file.parent, ignore_errors=True)

    return


def rename_tracks(metadata, log, dry_run=False):
    if dry_run:
        print(f"[DRY-RUN] Would rename tracks in: {metadata['final_output']}")
        return
    # --- Rename audio tracks to '## - {title}' format ---

    # - Get all audio files -
    audio_ext = ['mp3', 'm4b', 'm4a', 'ogg']
    audio_files = []
    for extension in audio_ext:
        results = sorted(metadata['final_output'].rglob(f"./*.{extension}"))
        for result in results:
            audio_files.append(result)

    # - Sort files for renaming
    audio_files.sort()
    log.debug(f"Globbed audio files for renaming = {str(audio_files)}")

    # - Rename to '## - {title}.{extension}' in current folder
    track = 1
    padding = 2
    if len(audio_files) < 1:
        return
    elif len(audio_files) >= 100:
        padding = 3

    for file in audio_files:
        clean_title = re.sub(r"[^\w\-\.\(\) ]+", '', metadata['title'])
        file.rename(file.parent / f"{str(track).zfill(padding)} - {clean_title}{file.suffix}")
        log.debug(metadata['final_output'] / f"{str(track).zfill(padding)} - {clean_title}{file.suffix}")
        track += 1

    return


def update_id3_tags(metadata, log, dry_run=False):
    """
    Update ID3 tags for all audio files in the processed folder using metadata.
    Adds language field and prepends ASIN/ISBN to comment if present.
    """
    if dry_run:
        print(f"[DRY-RUN] Would update ID3 tags in: {metadata['final_output']}")
    audio_ext = ['mp3', 'm4b', 'm4a', 'ogg']
    audio_files = []
    for extension in audio_ext:
        results = sorted(metadata['final_output'].rglob(f"./*.{extension}"))
        for result in results:
            audio_files.append(result)

    for file in audio_files:
        # Prepare tag values
        title = metadata.get('title', '')
        author = metadata.get('author', '')
        album = metadata.get('series', '') or title
        genre = metadata.get('genres', '')
        year = metadata.get('publishyear', '')
        language = metadata.get('language', '')
        asin = metadata.get('asin', '')
        isbn = metadata.get('isbn', '')
        summary = metadata.get('summary', '')

        # Build comment with ASIN/ISBN prefix if available
        comment_parts = []
        if asin:
            comment_parts.append(f"ASIN: {asin}")
        if isbn:
            comment_parts.append(f"ISBN: {isbn}")
        comment_prefix = " | ".join(comment_parts)
        comment = f"{comment_prefix} | {summary}" if comment_prefix else summary

        # Use language for ID3 COMM frame, fallback to 'eng'
        comm_lang = language if language else 'eng'

        if dry_run:
            print(f"[DRY-RUN] Would set tags for: {file}")
            print(f"  Title: {title}")
            print(f"  Artist/Author: {author}")
            print(f"  Album/Series: {album}")
            print(f"  Genre: {genre}")
            print(f"  Year: {year}")
            print(f"  Language: {language}")
            print(f"  Comment: {comment}")
            print(f"  COMM lang: {comm_lang}")
            continue

        try:
            if file.suffix.lower() == ".mp3":
                audio = EasyID3(str(file))
                audio['title'] = title
                audio['artist'] = author
                audio['album'] = album
                if genre:
                    audio['genre'] = genre
                if year:
                    audio['date'] = year
                if language:
                    audio['language'] = language
                audio.save()
                # Add comment using mutagen.id3 for full support
                id3 = ID3(str(file))
                id3.add(COMM(encoding=3, lang=comm_lang, desc='desc', text=comment))
                id3.save()
            else:
                # For non-mp3, skip or implement with mutagen.File if needed
                log.info(f"Skipping non-mp3 file for ID3 tagging: {file}")
        except Exception as e:
            log.info(f"Failed to update ID3 tags for {file}: {e}")

    return
