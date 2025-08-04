__version__ = 0.60

from pathlib import Path
import argparse
import base64
import configparser
import logging as log
import re
import shutil
import sys
import time
import webbrowser
import xml.etree.ElementTree as ET

root_path = Path(sys.argv[0]).resolve().parent
sys.path.append(str(root_path))
from scrapers import http_request, api_audible, scrape_goodreads_type1, scrape_goodreads_type2
from scrapers import scrape_lubimyczytac
from optional import create_opf, create_info, flatten_folder, rename_tracks, update_id3_tags

from bs4 import BeautifulSoup
from tinytag import TinyTag
import pyperclip

# --- Define globals ---
config_file = root_path / 'queue.ini'
debug_file = root_path / 'debug.log'
opf_template = root_path / 'template.opf'
default_output = '_BadaBoomBooks_'  # In the same directory as the input folder

# --- Logging configuration ---
log.basicConfig(level=log.DEBUG, filename=str(debug_file), filemode='w', style='{', format="Line: {lineno} | Level: {levelname} |  Time: {asctime} | Info: {message}")

# --- Configuring queue.ini ---
config = configparser.ConfigParser()
config.optionxform = lambda option: option
config['urls'] = {}
log.debug(config_file)

# --- Book processing results ---
failed_books = []
skipped_books = []
success_books = []


print(fr"""

=========================================================================================

    ______           _      ______                      ______             _
    | ___ \         | |     | ___ \                     | ___ \           | |
    | |_/ / __ _  __| | __ _| |_/ / ___   ___  _ __ ___ | |_/ / ___   ___ | | _____
    | ___ \/ _` |/ _` |/ _` | ___ \/ _ \ / _ \| '_ ` _ \| ___ \/ _ \ / _ \| |/ / __|
    | |_/ / (_| | (_| | (_| | |_/ / (_) | (_) | | | | | | |_/ / (_) | (_) |   <\__ \
    \____/ \__,_|\__,_|\__,_\____/ \___/ \___/|_| |_| |_\____/ \___/ \___/|_|\_\___/

                            An audioBook organizer (v{__version__})

=========================================================================================
""")

parser = argparse.ArgumentParser(prog='python BadaBoomBooks.py', formatter_class=argparse.RawTextHelpFormatter, description='Organize audiobook folders through webscraping metadata', epilog=r"""
Cheers to the community for providing our content and building our tools!

----------------------------------- INSTRUCTIONS --------------------------------------

1) Call the script and pass it the audiobook folders you would like to process, including any optional arguments...
    python BadaBoomBooks.py "C:\Path\To\Audiobook_folder1\" "C:\Path\To\Audiobook_folder2" ...
    python BadaBoomBooks.py --infotxt --opf --rename --series --id3-tag --move -O 'T:\Sorted' -R 'T:\Incoming\'

2) Your browser will open and perform a web search for the current book, simply select the correct web-page and copy the url to your clipboard.

3) After building the queue, the process will start and folders will be organized accordingly. Cheers!
""")

# ===== Prepare vaild arguments =====
parser.add_argument('-O', dest='output', metavar='OUTPUT', help='Path to place organized folders')
parser.add_argument('-c', '--copy', action='store_true', help='Copy folders instead of moving them')
parser.add_argument('-d', '--debug', action='store_true', help='Enable debugging to log file')
parser.add_argument('-D', '--dry-run', action='store_true', help="Perform a trial run without making any changes to filesystem")
parser.add_argument('-f', '--flatten', action='store_true', help="Flatten book folders, useful if the player has issues with multi-folder books")
parser.add_argument('-i', '--infotxt', action='store_true', help="Generate 'info.txt' file, used by SmartAudioBookPlayer to display book summary")
parser.add_argument('-o', '--opf', action='store_true', help="Generate 'metadata.opf' file, used by Audiobookshelf to import metadata")
parser.add_argument('-r', '--rename', action='store_true', help="Rename audio tracks to '## - {title}' format")
parser.add_argument('-s', '--site', metavar='',  default='all', choices=['audible', 'goodreads', 'lubimyczytac', 'all'], help="Specify the site to perform initial searches [audible, goodreads, lubimyczytac, all]")
parser.add_argument('-v', '--version', action='version', version=f"Version {__version__}")
parser.add_argument('folders', metavar='folder', nargs='*', help='Audiobook folder(s) to be organized')
parser.add_argument('-S', '--series', action='store_true', help="Include series information in output path (series/volume - title)")
parser.add_argument('-R', '--book-root', dest='book_root', metavar='BOOK_ROOT', help='Treat all first-level subdirectories of this directory as books to process')
parser.add_argument('-I', '--id3-tag', action='store_true', help='Update ID3 tags of audio files using scraped metadata')
parser.add_argument('-F', '--from-opf', action='store_true', help='Read metadata from metadata.opf file if present, fallback to web scraping if not')
parser.add_argument('-m', '--move', action='store_true', help="Move folders instead of copying them")

args = parser.parse_args()

if args.output:
    test_output = Path(args.output).resolve()
    if not test_output.is_dir():
        log.debug(f"Output is not a directory/exists: {test_output}")
        print(f"\nThe output path is not a directory or does not exist: {test_output}")
        input("\nPress enter to exit...")
        sys.exit()


if not args.debug:
    # --- Logging disabled ---
    log.disable(log.CRITICAL)


def clipboard_queue(folder, config, dry_run=False):
    # ----- Search for audibooks then monitor clipboard for URL -----

    book_path = folder.resolve()
    # - Try for search terms from id3 tags

    title = False
    author = False

    for file in book_path.glob('**/*'):
        if file.suffix in ['.mp3', '.m4a', '.m4b', '.wma', '.flac']:
            log.debug(f"TinyTag audio file: {file}")
            track = TinyTag.get(str(file))
            try:
                title = re.sub(r"\&", 'and', track.album).strip()
                if title == '':
                    title = False
                author = re.sub(r"\&", 'and', track.artist).strip()
                if author == '':
                    author = False
                break
            except Exception as e:
                log.debug(f"Couldn't get search term metadata from ID3 tags, using foldername ({file}) | {e}")

    if title and author:
        search_term = f"{title} by {author}"
    elif title:
        search_term = title
    else:
        search_term = str(book_path.name)

    # - Prompt user to copy AudioBook url
    log.info(f"Search term: {search_term}")
    if args.site == 'audible':
        webbrowser.open(f"https://duckduckgo.com/?t=ffab&q=site:audible.com {search_term}", new=2)
    elif args.site == 'goodreads':
        webbrowser.open(f"https://duckduckgo.com/?t=ffab&q=site:goodreads.com {search_term}", new=2)
    elif args.site == 'lubimyczytac':
        webbrowser.open(f"https://duckduckgo.com/?t=ffab&q=site:lubimyczytac.pl {search_term}", new=2)
    elif args.site == 'all':
        # Open all three searches
        webbrowser.open(f"https://duckduckgo.com/?t=ffab&q=lubimyczytac.pl audible.com goodreads.com {search_term}", new=2)


    clipboard_old = pyperclip.paste()
#    log.debug(f"clipboard_old: {clipboard_old}")

    if (
        re.search(r"http.+goodreads.+book/show/\d+", clipboard_old)
        or re.search(r"http.+audible.+/pd/[\w-]+Audiobook/\w+\??", clipboard_old)
        or re.search(r"https?://lubimyczytac\.pl/(ksiazka|audiobook)/\d+/.+", clipboard_old)
        or re.search(r"skip", clipboard_old)
    ):  # Remove old script contents from clipboard
        clipboard_old = '__clipboard_cleared__'
        pyperclip.copy(clipboard_old)

    # - Wait for  url to be coppied
    print(f"\nCopy the Audible or Goodreads URL for \"{book_path.name}\"\nCopy 'skip' to skip the current book...           ", end='')
    while True:
        time.sleep(1)
        clipboard_current = pyperclip.paste()

        if clipboard_current == clipboard_old:  # Clipboard contents have not yet changed
            continue
        elif clipboard_current == 'skip':  # user coppied 'skip' to clipboard
            log.info(f"Skipping: {book_path.name}")
            print(f"\n\nSkipping: {book_path.name}")
            skipped_books.append(book_path.name)
            break
        elif re.search(r"^http.+audible.+/pd/[\w-]+Audiobook/\w{10}", clipboard_current):
            # --- A valid Audible URL ---
            log.debug(f"Clipboard Audible match: {clipboard_current}")

            audible_url = re.search(r"^http.+audible.+/pd/[\w-]+Audiobook/\w{10}", clipboard_current)[0]
            b64_folder = base64.standard_b64encode(bytes(str(book_path.resolve()), 'utf-8')).decode()
            b64_url = base64.standard_b64encode(bytes(audible_url, 'utf-8')).decode()

            log.debug(f"b64_folder: {b64_folder}")
            log.debug(f"b64_url: {b64_url}")

            config['urls'][b64_folder] = b64_url
            print(f"\n\nAudible URL: {audible_url}")
            break
        elif re.search(r"^http.+goodreads.+book/show/\d+", clipboard_current):
            # --- A valid Goodreads URL
            log.debug(f"Clipboard GoodReads match: {clipboard_current}")

            goodreads_url = re.search(r"^http.+goodreads.+book/show/\d+", clipboard_current)[0]
            b64_folder = base64.standard_b64encode(bytes(str(book_path.resolve()), 'utf-8')).decode()
            b64_url = base64.standard_b64encode(bytes(goodreads_url, 'utf-8')).decode()

            log.debug(f"b64_folder: {b64_folder}")
            log.debug(f"b64_url: {b64_url}")

            config['urls'][b64_folder] = b64_url
            print(f"\n\nGoodreads URL: {goodreads_url}")
            break
        elif re.search(r"^https?://lubimyczytac\.pl/(ksiazka|audiobook)/\d+/.+", clipboard_current):
            # --- A valid lubimyczytac.pl URL ---
            log.debug(f"Clipboard lubimyczytac.pl match: {clipboard_current}")

            # Use the full clipboard_current as the URL
            lmc_url = clipboard_current.strip()
            b64_folder = base64.standard_b64encode(bytes(str(book_path.resolve()), 'utf-8')).decode()
            b64_url = base64.standard_b64encode(bytes(lmc_url, 'utf-8')).decode()

            log.debug(f"b64_folder: {b64_folder}")
            log.debug(f"b64_url: {b64_url}")

            config['urls'][b64_folder] = b64_url
            print(f"\n\nlubimyczytac.pl URL: {lmc_url}")
            break
        else:
            continue

    pyperclip.copy(clipboard_old)
    return config


def read_opf_metadata(opf_path):
    metadata = {
        'author': '',
        'authors_multi': '',
        'title': '',
        'summary': '',
        'subtitle': '',
        'narrator': '',
        'publisher': '',
        'publishyear': '',
        'genres': '',
        'isbn': '',
        'asin': '',
        'series': '',
        'sereis_multi': '',
        'volumenumber': '',
        'language': '',
        'input_folder': str(opf_path.parent.name),
        'failed': False,  # Always set this key
        'failed_exception': '',
        'skip': False,    # Always set this key
        'url': ''         # Always set this key
    }
    try:
        tree = ET.parse(opf_path)
        root = tree.getroot()
        ns = {
            'dc': 'http://purl.org/dc/elements/1.1/',
            'opf': 'http://www.idpf.org/2007/opf',
            'calibre': 'http://calibre.kovidgoyal.net/2008/metadata'
        }
        # Standard fields
        metadata['title'] = root.find('.//dc:title', ns).text if root.find('.//dc:title', ns) is not None else ''
        metadata['subtitle'] = root.find('.//dc:subtitle', ns).text if root.find('.//dc:subtitle', ns) is not None else ''
        metadata['summary'] = root.find('.//dc:description', ns).text if root.find('.//dc:description', ns) is not None else ''
        metadata['author'] = root.find('.//dc:creator[@opf:role="aut"]', ns).text if root.find('.//dc:creator[@opf:role="aut"]', ns) is not None else ''
        metadata['narrator'] = root.find('.//dc:creator[@opf:role="nrt"]', ns).text if root.find('.//dc:creator[@opf:role="nrt"]', ns) is not None else ''
        metadata['publisher'] = root.find('.//dc:publisher', ns).text if root.find('.//dc:publisher', ns) is not None else ''
        metadata['publishyear'] = root.find('.//dc:date', ns).text if root.find('.//dc:date', ns) is not None else ''
        metadata['language'] = root.find('.//dc:language', ns).text if root.find('.//dc:language', ns) is not None else ''
        # Identifiers
        metadata['isbn'] = root.find('.//dc:identifier[@opf:scheme="ISBN"]', ns).text if root.find('.//dc:identifier[@opf:scheme="ISBN"]', ns) is not None else ''
        metadata['asin'] = root.find('.//dc:identifier[@opf:scheme="ASIN"]', ns).text if root.find('.//dc:identifier[@opf:scheme="ASIN"]', ns) is not None else ''
        # Genres
        genre_elements = root.findall('.//dc:subject', ns)
        metadata['genres'] = ','.join([g.text for g in genre_elements if g.text]) if genre_elements else ''
        # Series and volume number (calibre style)
        series_meta = root.find('.//ns0:meta[@name="calibre:series"]', {'ns0': ns['opf']})
        metadata['series'] = series_meta.attrib['content'] if series_meta is not None and 'content' in series_meta.attrib else ''
        volume_meta = root.find('.//ns0:meta[@name="calibre:series_index"]', {'ns0': ns['opf']})
        metadata['volumenumber'] = volume_meta.attrib['content'] if volume_meta is not None and 'content' in volume_meta.attrib else ''
        # --- Read URL from <dc:source> if present ---
        url_elem = root.find('.//dc:source', ns)
        if url_elem is not None and url_elem.text:
            metadata['url'] = url_elem.text.strip()
    except Exception as e:
        metadata['failed'] = True
        metadata['failed_exception'] = f"OPF parsing error: {e}"
    return metadata

# ==========================================================================================================
# ==========================================================================================================

# ===== Build list of folders to process =====
folders = []

# Handle --book-root if provided
if args.book_root:
    book_root = Path(args.book_root.rstrip(r'\/"\'')).resolve()
    if not book_root.is_dir():
        print(f"\nThe book root path is not a directory or does not exist: {book_root}")
        input("\nPress enter to exit...")
        sys.exit()
    # Find all subfolders (any depth) that contain at least one audio file
    audio_exts = {'.mp3', '.m4a', '.m4b', '.wma', '.flac', '.ogg'}
    candidate_folders = set()
    for file in book_root.rglob('*'):
        if file.is_file() and file.suffix.lower() in audio_exts:
            candidate_folders.add(file.parent.resolve())
    folders.extend(sorted(candidate_folders))

# Add any folders given as positional arguments
folders += [Path(argument.rstrip(r'\/"\'')).resolve() for argument in getattr(args, 'folders', [])]

# Remove duplicates, just in case
folders = list(dict.fromkeys(folders))

for folder in folders:
    # Only check existence for positional folders if --book-root is not set
    if not args.book_root:
        exists = folder.is_dir()
        if not exists:
            print(f"The input folder '{folder.name}' does not exist or is not a directory...")
            input('Press enter to exit...')
            sys.exit()

log.debug(folders)


# ===== Build the queue using the .ini =====
for folder in folders:
    folder = folder.resolve()
    opf_file = folder / 'metadata.opf'
    if args.from_opf and opf_file.exists():
        # Write OPF marker instead of URL
        b64_folder = base64.standard_b64encode(bytes(str(folder), 'utf-8')).decode()
        b64_url = base64.standard_b64encode(b'OPF').decode()
        config['urls'][b64_folder] = b64_url
        print(f"Queued OPF metadata for {folder}")
    else:
        config = clipboard_queue(folder, config, dry_run=args.dry_run)
        print('\n-------------------------------------------')

print('\n===================================== PROCESSING ====================================')

with config_file.open('w', encoding='utf-8') as file:
    config.write(file)

# ===== Process all keys (folders) in .ini file =====
config.read(config_file, encoding='utf-8')
for key, value in config.items('urls'):
    log.debug(f"Key: '{key}' ({type(key)}) - Value: '{value}' ({type(value)}")
    try:
        folder = base64.standard_b64decode(bytes(key, 'utf-8')).decode()
        url = base64.standard_b64decode(bytes(value, 'utf-8')).decode()
        log.debug(f"Folder: {folder} - URL: {url}")
    except Exception as exc:
        log.debug(f"Exception: {exc}")
        continue

    # ----- Scrape metadata -----
    folder = Path(folder).resolve()
    metadata = {
        'author': '',
        'authors_multi': '',
        'title': '',
        'summary': '',
        'subtitle': '',
        'narrator': '',
        'publisher': '',
        'publishyear': '',
        'datepublished': '',
        'genres': '',
        'isbn': '',
        'asin': '',
        'series': '',
        'sereis_multi': '',
        'volumenumber': '',
        'language': '',
        'url': url,
        'skip': False,
        'failed': False,
        'failed_exception': '',
        'input_folder': str(folder.resolve().name)
    }

    print(f"\n----- {metadata['input_folder']} -----")

    if url == "OPF":
        opf_file = folder / 'metadata.opf'
        metadata = read_opf_metadata(opf_file)
        if metadata.get('failed'):
            print(f"Failed to read OPF metadata: {metadata.get('failed_exception')}")
            continue
        print(f"Read metadata from OPF for {metadata['input_folder']}")
    else:
        # --- Request Metadata ---
        while True:

            if 'audible.com' in metadata['url']:
                # --- ASIN ---
                metadata['asin'] = re.search(r"^http.+audible.+/pd/[\w-]+Audiobook/(\w{10})", metadata['url'])[1]
                query = {'response_groups': 'contributors,product_desc,series,product_extended_attrs,media'}
                metadata, response = http_request(metadata, log, f"https://api.audible.com/1.0/catalog/products/{metadata['asin']}", query)
                if metadata['skip'] is True:
                    break
                page = response.json()['product']
                metadata = api_audible(metadata, page, log)
                break

            elif 'goodreads.com' in metadata['url']:
                metadata, response = http_request(metadata, log)

                if args.debug:
                    with Path(root_path / 'goodreads_page.html').open('w', encoding='utf-8') as html_page:
                        html_page.write(response.text)

                if metadata['skip'] is True:
                    break
                parsed = BeautifulSoup(response.text, 'html.parser')
                if parsed.select_one('#bookTitle') is not None:
                    metadata = scrape_goodreads_type1(parsed, metadata, log)
                    break
                elif parsed.select_one("script[type='application/ld+json']") is not None:
                    metadata = scrape_goodreads_type2(parsed, metadata, log)
                    break
            elif 'lubimyczytac.pl' in metadata['url']:
                metadata, response = http_request(metadata, log)
                if args.debug:
                    with Path(root_path / 'lubimyczytac_page.html').open('w', encoding='utf-8') as html_page:
                        html_page.write(response.text)
                if metadata['skip'] is True:
                    break
                parsed = BeautifulSoup(response.text, 'html.parser')
                metadata = scrape_lubimyczytac(parsed, metadata, log)
                break

    if metadata['failed'] is True:
        failed_books.append(f"{metadata['input_folder']} ({metadata['failed_exception']})")
    if metadata['skip'] is True:
        continue

    print(f"""
Title: {metadata['title']}
Author: {metadata['author']}
URL: {metadata['url']}
Series: {metadata['series']} | Volume: {metadata['volumenumber']}

""")

    # ----- [--output] Prepare output folder -----
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = folder.parent / f"{default_output}/"

    # - Clean paths -
    author_clean = re.sub(r"[^\w\-\.\(\) ]+", '', metadata['author'])
    title_clean = re.sub(r"[^\w\-\.\(\) ]+", '', metadata['title'])
    log.info(f"Cleaned path names: Author ({author_clean} | Title ({title_clean}")

    # Clean series and volume data if they exist
    series_clean = re.sub(r"[^\w\-\.\(\) ]+", '', metadata['series']) if metadata['series'] else ""
    volumenumber_clean = re.sub(r"[^\w\-\.\(\), ]+", '', metadata['volumenumber']) if metadata['volumenumber'] else ""

    log.info(f"Cleaned series: {series_clean} | {volumenumber_clean}")

    # Prepare output path

    author_folder = output_path / f"{author_clean}/"
    author_folder.resolve()
    author_folder.mkdir(parents=True, exist_ok=True)
    # Apply series-based structure if requested and series data exists
    if args.series and series_clean and volumenumber_clean:
        series_dir = author_folder / series_clean
        series_dir.mkdir(parents=True, exist_ok=True)
        final_output = series_dir / f"{volumenumber_clean} - {title_clean}/"
    else:    
        final_output = author_folder / f"{title_clean}/"

    metadata['final_output'] = final_output.resolve()

    print(f"\nOutput: {metadata['final_output']}")

    # ----- [--copy] Copy/move book folder ---
    if args.copy and not args.move:
        if args.dry_run:
            print(f"\n[DRY-RUN] Would copy '{folder}' to '{metadata['final_output']}'")
        else:
            print("\nCopying...")
            shutil.copytree(folder, metadata['final_output'], dirs_exist_ok=True, copy_function=shutil.copy2)
    elif args.move and not args.copy:
        if args.dry_run:
            print(f"\n[DRY-RUN] Would move '{folder}' to '{metadata['final_output']}'")
        else:
            print("\nMoving...")
            try:
                folder.rename(metadata['final_output'])
            except Exception as e:
                log.info(f"Couldn't move folder directly, performing copy-move (metadata['title']) | {e}")
                shutil.copytree(folder, metadata['final_output'], dirs_exist_ok=True, copy_function=shutil.copy2)
                shutil.rmtree(folder)
    elif args.copy and args.move:
        print("\n[WARNING] Both --copy and --move are set - ucertian what user wants - doing nothing.")
        exit(1)
    elif not args.copy and not args.move:
        print("\n[INFO] Neither --copy nor --move are set - all operations will be performed in the current location.")
        # final_outut needs to be set to the current folder
        metadata['final_output'] = folder
    # ----- [--flatten] Flatten Book Folders -----
    if args.flatten:
        if args.dry_run:
            print(f"\n[DRY-RUN] Would flatten '{metadata['final_output']}'")
        else:
            print('\nFlattening...')
            flatten_folder(metadata, log, dry_run=args.dry_run)

    # ----- [--rename] Rename audio tracks -----
    if args.rename:
        if args.dry_run:
            print(f"\n[DRY-RUN] Would rename audio tracks in '{metadata['final_output']}'")
        else:
            print('\nRenaming...')
            rename_tracks(metadata, log, dry_run=args.dry_run)

    # ----- [--opf] Create .opf file -----
    if args.opf:
        if args.dry_run:
            print(f"\n[DRY-RUN] Would create 'metadata.opf' in '{metadata['final_output']}'")
        else:
            print("\nCreating 'metadata.opf'")
            create_opf(metadata, opf_template, dry_run=args.dry_run)

    # ----- [--i] Create info.txt file -----
    if args.infotxt:
        if args.dry_run:
            print(f"\n[DRY-RUN] Would create 'info.txt' in '{metadata['final_output']}'")
        else:
            print("\nCreating 'info.txt'")
            create_info(metadata, dry_run=args.dry_run)

    # ----- [--id3-tag] Update ID3 tags -----
    if args.id3_tag:
        update_id3_tags(metadata, log, dry_run=args.dry_run)

    # ---- Folder complete ----
    print("\nDone!")
    success_books.append(f"{folder.stem}/ --> {output_path.stem}/{metadata['author']}/{metadata['title']}/")


# ===== Summary =====
if failed_books:
    log.critical(f"Failed metadata scrapes: {','.join(failed_books)}")
    print('\n\n====================================== FAILURES ======================================')
    for failure in failed_books:
        print(f"\nFailed: {failure}", end='')
    print()
    if skipped_books:
        print('\n\n====================================== SKIPPED ======================================')
        for skipped in skipped_books:
            print(f"\nSkipped: {skipped}", end='')
        print()
    if success_books:
        print('\n\n====================================== SUCCESS ======================================')
        for book in success_books:
            print(f"\nSuccess: {book}", end='')
    print('\n\n====================================== WARNING ======================================')
    print('\nSome books did not get processed successfully...\n')
    input('press enter to exit...')
    sys.exit()
else:
    log.info('Completed without errors')
    if skipped_books:
        print('\n\n====================================== SKIPPED ======================================')
        for skipped in skipped_books:
            print(f"\nSkipped: {skipped}", end='')
        print()
    print('\n\n====================================== SUCCESS ======================================')
    for book in success_books:
        print(f"\nSuccess: {book}", end='')
    print('\n\n====================================== COMPLETE ======================================')
    print('\nCheers to the community providing our content and building our tools!\n')
    input('Press enter to exit...')
    sys.exit()
