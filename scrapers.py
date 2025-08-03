# --- Functions that scrape the parsed webpage for metadata ---
import json
import time
import re
import requests
from bs4 import BeautifulSoup
from language_map import LANGUAGE_MAP


def http_request(metadata, log, url=False, query=False):
    # --- Parse a webpage for scraping ---

    log.info(f"Metadata URL for get() request: {metadata['url']}")

    # --- Request webpage ---
    timer = 2
    while True:
        try:
            if url and query:
                html_response = requests.get(url, params=query, headers={'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:108.0) Gecko/20100101 Firefox/108.0'})
            else:
                html_response = requests.get(metadata['url'], headers={'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:108.0) Gecko/20100101 Firefox/108.0'})
        except Exception as exc:
            log.error(f"Requests HTML get error: {exc}")
            if timer == 2:
                print('\n\nBad response from webpage, retrying for up-to 25 seconds...')
            elif timer >= 10:
                log.error(f"Requests HTML get error: {exc}")
                print(f"Failed to get webpage page, skipping {metadata['input_folder']}...")
                metadata['skip'] = True
                metadata['failed'] = True
                metadata['failed_exception'] = f"{metadata['input_folder']}: Requests HTML get error: {exc}"
                break
            time.sleep(timer)
            timer = timer * 1.5
        else:
            break

    if metadata['failed']:
        return metadata, html_response

    log.info(f"Requests Status code: {str(html_response.status_code)}")
    if html_response.status_code != requests.codes.ok:
        log.error(f"Requests error: {str(html_response.status_code)}")
        print(f"Bad requests status code, skipping {metadata['input_folder']}: {html_response.status_code}")
        metadata['skip'] = True
        metadata['failed'] = True
        metadata['failed_exception'] = f"{metadata['input_folder']}: Requests status code = {html_response.status_code}"
        return metadata, html_response

    try:
        html_response.raise_for_status()
    except Exception as exc:
        log.error(f"Requests status error: {exc}")
        print(f"Requests raised an error, skipping {metadata['input_folder']}: {exc}")
        metadata['skip'] = True
        metadata['failed'] = True
        metadata['failed_exception'] = f"{metadata['input_folder']}: Requests raised status = {exc}"
        return metadata, html_response
    else:
        # --- Parse webpage for scraping ---
        return metadata, html_response


def api_audible(metadata, page, log):
    # ----- Get metadata from Audible.com API -----

    # --- Author ---
    try:
        authors = page['authors']
        if len(authors) == 1:
            metadata['author'] = page['authors'][0]['name']
        if len(authors) > 1:
            authors_list = []
            for author in authors:
                authors_list.append(author)
            metadata['author'] = page['authors'][0]['name']
            metadata['authors_multi'] = authors_list

    except Exception as e:
        log.info(f"No author in json, using '_unknown_' ({metadata['input_folder']}) | {e}")
        print(f" - Warning: No author found, placing in author folder '_unknown_': {metadata['input_folder']}")
        metadata['author'] = '_unknown_'  # If no author is found, use the name '_unknown_'

    # --- Title ---
    try:
        metadata['title'] = page['title']
    except Exception as e:
        log.info(f"No title in json, using folder name ({metadata['input_folder']}) | {e}")
        print(f" - Warning: No title found, using folder name: {metadata['input_folder']}")
        metadata['title'] = metadata['input_folder']  # If no title is found, use original foldername

    # --- Summary ---
    try:
        summary_dirty = BeautifulSoup(page['publisher_summary'], 'html.parser')
        metadata['summary'] = summary_dirty.getText()
        log.info(f"summary element: {str(summary_dirty)}")
    except Exception as e:
        log.info(f"No summary in json, leaving blank ({metadata['input_folder']} | {e}")

    # --- Subtitle ---
    try:
        metadata['subtitle'] = page['subtitle']
    except Exception as e:
        log.info(f"No subtitle scraped, leaving blank ({metadata['input_folder']}) | {e}")

    # --- Narrator ---
    try:
        narrators = page['narrotors']
        if len(narrators) == 1:
            metadata['narrator'] = page['narrators'][0]['name']
        elif len(narrators) > 1:
            narrators_list = []
            for narrator in narrators:
                narrators_list.append(narrator)
            metadata['narrator'] = page['narrators'][0]['name']
            metadata['narrators_multi'] = narrators_list

    except Exception as e:
        log.info(f"No narrator in json, leaving blank ({metadata['input_folder']}) | {e}")

    # --- Publisher ---
    try:
        metadata['publisher'] = page['publisher_name']
        log.info(f"Publisher: {metadata['publisher']}")
    except Exception as e:
        log.info(f"No publisher in json, leaving blank({metadata['input_folder']}) | {e}")

    # --- Publish Year ---
    try:
        metadata['publishyear'] = re.search(r"(\d{4})", page['release_date'])[1]
        log.info(f"Publish year: {metadata['publishyear']}")
    except Exception as e:
        log.info(f"No publish year in json, leaving blank ({metadata['input_folder']}) | {e}")

    # --- Genres ---
    # try:
    #     # element = meta_json['datePublished']
    #     # metadata['genres'] = element
    #     # !!! element = parsed.select_one('li.narratorLabel > a:nth-child(1)')
    #     # !!! metadata['publisheryear'] = element.getText()
    #     log.info(f"Genres element: {str(element)}")
    # except:
    #     log.info(f"No genres in json, leaving blank ({metadata['input_folder']}) | {e}")

    # --- Series ---
    try:
        series = page['series']
        if len(series) == 1:
            metadata['series'] = page['series'][0]['title']
        if len(series) > 1:
            series_list = []
            for serie in series:
                series_list.append(serie)
            metadata['series'] = page['series'][0]['title']
            metadata['series_multi'] = series_list
    except Exception as e:
        log.info(f"No series in json, leaving blank ({metadata['input_folder']}) | {e}")

    # --- Volume Number ---
    try:
        metadata['volumenumber'] = page['series'][0]['sequence']
        log.info(f"Volume number element: {page['series'][0]['sequence']}")
    except Exception as e:
        log.info(f"No volume number in json, leaving blank ({metadata['input_folder']}) | {e}")

    return metadata


def scrape_goodreads_type1(parsed, metadata, log):
    # ----- Scrape a Goodreads.com book page for metadata -----
    log.debug(f"Scraping Goodreads Type 1 for metadata: {metadata['input_folder']}")
    # --- Author ---
    try:
        element = parsed.select_one('#bookAuthors')
        log.info(f"Author element: {str(element)}")
        element = element.find('a')
        # Clean extracted text by collapsing multiple spaces
        raw_text = element.getText(strip=False)  # Keep original whitespace
        cleaned_author = ' '.join(raw_text.split())  # Collapse whitespace
        metadata['author'] = cleaned_author
    except Exception as e:
        log.info(f"No author in bs4, using '_unknown_' ({metadata['input_folder']}) | {e}")
        print(f" - Warning: No author scraped, placing in author folder '_unknown_': {metadata['input_folder']}")
        metadata['author'] = '_unknown_'  # If no author is found, use the name '_unknown_'

    # --- Title ---
    try:
        element = parsed.select_one('#bookTitle')
        log.info(f"Title element: {str(element)}")
        metadata['title'] = element.getText(strip=True)
    except Exception as e:
        log.info(f"No title scraped, using '_unknown_' ({metadata['input_folder']}) | {e}")
        print(f" - Warning: No title scraped, using folder name: {metadata['input_folder']}")
        metadata['title'] = metadata['input_folder']  # If no title is found, use original foldername

    # --- Summary ---
    try:
        element = parsed.select_one('#description')
        log.info(f"Summary element: {str(element)}")
        summary = element.find_all('span')[1]
        if summary is None:
            summary = element.find('span')
        metadata['summary'] = summary.getText()
    except Exception as e:
        log.info(f"No summary scraped, leaving blank ({metadata['input_folder']}) | {e}")

    # --- Series ---
    try:
        element = parsed.select_one('#bookSeries')
        log.info(f"Series element: {str(element)}")
        if element is not None:
            series = re.search(r'(\w.+),? #\d+', element.getText(strip=True))
            metadata['series'] = series[1]
    except Exception as e:
        log.info(f"No series scraped, leaving blank ({metadata['input_folder']}) | {e}")

    # --- Series Number ---
    if metadata['series'] != '':
        try:
            element = parsed.select_one('#bookSeries')
            log.info(f"Volume number element: {str(element)}")
            if element is not None:
                number = re.search(r'\w.+,? #([\d\.]+)', element.getText(strip=True))
                metadata['volumenumber'] = number[1]
        except Exception as e:
            log.info(f"No volume number scraped, leaving blank ({metadata['input_folder']}) | {e}")

    # --- Genres ---
    try:
        genres_list = []
        genres_container = parsed.select('div[data-testid="genresList"]')
        if genres_container:
            genre_buttons = genres_container.select('a.Button--tag span.Button__labelItem')
            for button in genre_buttons:
                genre_text = button.getText(strip=True)
                if genre_text and genre_text != "Genres":  # Skip the "Genres" label
                    genres_list.append(genre_text)
            metadata['genres'] = ','.join(genres_list)
    except Exception as e:
        log.info(f"No genres scraped, leaving blank ({metadata['input_folder']}) | {e}")

    # --- Language ---


    return metadata


def scrape_goodreads_type2(parsed, metadata, log):
    # ----- Scrape a Goodreads.com book page for metadata -----
    log.debug(f"Scraping Goodreads Type 2 for metadata: {metadata['input_folder']}")
    try:
        # Find the JSON-LD script block in the <head>
        jsonld_script = parsed.find("script", {"type": "application/ld+json"})
        if jsonld_script:
            jsonld = json.loads(jsonld_script.get_text(strip=True))
        else:
            jsonld = None
    except Exception as exc:
        log.error(f"JSON-LD Parsing Error: {exc}")
        jsonld = None

    try:
        data = json.loads(parsed.select_one("script[type='application/ld+json']").getText(strip=True))
    except Exception as exc:
        log.error(f"JSON Parsing Error: {exc}")
        print(f"Could not prepare JSON object, skipping {metadata['input_folder']}...")
        metadata['skip'] = True
        metadata['failed'] = True
        metadata['failed_exception'] = f"{metadata['input_folder']}: BS4 to JSON loads: {exc}"
        return metadata

    # --- Author ---
    try:
        value = data['author'][0]['name']
        log.info(f"Author element: {str(value)}")
        cleaned_author = ' '.join(value.split())
        metadata['author'] = cleaned_author
    except Exception as e:
        log.info(f"No author in bs4, using '_unknown_' ({metadata['input_folder']}) | {e}")
        print(f" - Warning: No author scraped, placing in author folder '_unknown_': {metadata['input_folder']}")
        metadata['author'] = '_unknown_'

    # --- Title ---
    try:
        title = re.search(r'^(.+?)(\s\(.+,\s.+\))?$', data['name'])
        log.info(f"Title element: {str(title)}")
        metadata['title'] = title[1]
    except Exception as e:
        log.info(f"No title scraped, using '_unknown_' ({metadata['input_folder']}) | {e}")
        print(f" - Warning: No title scraped, using folder name: {metadata['input_folder']}")
        metadata['title'] = metadata['input_folder']

    # --- Summary ---
    try:
        element = parsed.select_one("div[data-testid='description']")
        log.info(f"Summary element: {str(element)}")
        if element is not None:
            summary = element.select_one("span[class='Formatted']")
            metadata['summary'] = summary.getText()
    except Exception as e:
        log.info(f"No summary scraped, leaving blank ({metadata['input_folder']}) | {e}")

    # --- Series ---
    try:
        element = parsed.select_one("div[class='BookPageTitleSection__title']").select_one('h3')
        log.info(f"Series element: {str(element)}")
        # Match series name and number(s) like "#3", "#3-4", "#3,4", "#3.5"
        series_match = re.search(r'^(.+?)\s*#([\d\-,\.]+)$', element.getText(strip=True))
        if series_match:
            metadata['series'] = series_match.group(1)
            # Normalize series number: replace '-' with ',' and remove spaces
            raw_number = series_match.group(2).replace('-', ',').replace(' ', '')
            metadata['volumenumber'] = raw_number
        else:
            # Fallback: just series name if no number found
            metadata['series'] = element.getText(strip=True)
    except Exception as e:
        log.info(f"No series scraped, leaving blank ({metadata['input_folder']}) | {e}")

    # --- Series Number ---
    # Already handled above, no need for separate block

    # --- Genres ---
    try:
        genres_list = []
        genres_container = parsed.select('div[data-testid="genresList"]')
        if genres_container:
            genre_buttons = genres_container.select('a.Button--tag span.Button__labelItem')
            for button in genre_buttons:
                genre_text = button.getText(strip=True)
                if genre_text and genre_text != "Genres":  # Skip the "Genres" label
                    genres_list.append(genre_text)
            metadata['genres'] = ','.join(genres_list)
    except Exception as e:
        log.info(f"No genres scraped, leaving blank ({metadata['input_folder']}) | {e}")

    # --- Language ---
    try:
        # Prefer JSON-LD "inLanguage" field if available
        language = None
        if jsonld and "inLanguage" in jsonld:
            language = jsonld["inLanguage"]
        # Fallback to previous regex if not found
        if not language:
            html = str(parsed)
            lang_match = re.search(r'"language":\s*{[^}]*"name":"([^"]+)"', html)
            if lang_match:
                language = lang_match.group(1)
        if language:
            # Convert to ISO code using LANGUAGE_MAP
            lang_key = language.strip().lower()
            iso_code = LANGUAGE_MAP.get(lang_key, language)
            metadata['language'] = iso_code
            log.info(f"Language scraped: {language} -> {iso_code}")
        else:
            log.info(f"No language found in JSON-LD or HTML for {metadata['input_folder']}")
    except Exception as e:
        log.info(f"Exception while scraping language ({metadata['input_folder']}) | {e}")

    # --- ISBN ---
    try:
        isbn = None
        # Try JSON-LD first
        if jsonld and "isbn" in jsonld:
            isbn = jsonld["isbn"]
        # Fallback to regex in HTML if not found
        if not isbn:
            html = str(parsed)
            isbn_match = re.search(r'"isbn"\s*:\s*"(\d+)"', html)
            if isbn_match:
                isbn = isbn_match.group(1)
        if isbn:
            metadata['isbn'] = isbn
            log.info(f"ISBN scraped: {isbn}")
        else:
            log.info(f"No ISBN found in JSON-LD or HTML for {metadata['input_folder']}")
    except Exception as e:
        log.info(f"Exception while scraping ISBN ({metadata['input_folder']}) | {e}")

    return metadata


def scrape_lubimyczytac(parsed, metadata, log):
    # ----- Scrape a lubimyczytac.pl book page for metadata -----
    log.debug(f"Scraping lubimyczytac.pl for metadata: {metadata['input_folder']}")

    # --- Title ---
    try:
        # Try meta og:title first (usually "Title | Author")
        meta_title = parsed.find("meta", property="og:title")
        if meta_title and meta_title.get("content"):
            # Remove author if present
            title = meta_title["content"].split("|")[0].strip()
            metadata['title'] = title
        else:
            element = parsed.select_one('h1.book__title')
            if element:
                metadata['title'] = element.get_text(strip=True)
    except Exception as e:
        log.info(f"No title scraped ({metadata['input_folder']}) | {e}")

    # --- Author ---
    try:
        # Try meta books:author
        meta_author = parsed.find("meta", property="books:author")
        if meta_author and meta_author.get("content"):
            metadata['author'] = meta_author["content"].strip()
        else:
            element = parsed.select_one('a.author__link')
            if element:
                metadata['author'] = element.get_text(strip=True)
    except Exception as e:
        log.info(f"No author scraped ({metadata['input_folder']}) | {e}")

    # --- Series and volume (if present) ---
    try:
        # Try to find the series in the "Cykl" section
        series = ""
        volumenumber = ""
        # Look for "Cykl:" in the details
        for dt in parsed.select('dt'):
            if dt.get_text(strip=True).lower().startswith("cykl"):
                dd = dt.find_next_sibling('dd')
                if dd:
                    # Example: "Pamiętniki Mordbota (tom 1-2)"
                    series_text = dd.get_text(strip=True)
                    match = re.match(r'(.+?)\s*\(tom\s*([^\)]+)\)', series_text)
                    if match:
                        series = match.group(1)
                        raw_number = match.group(2).replace(' ', '')
                        # Handle 1-2 as 1,2; 1 as 1; 4.5 as 4.5
                        if '-' in raw_number:
                            parts = raw_number.split('-')
                            if len(parts) == 2 and parts[0].replace('.', '', 1).isdigit() and parts[1].replace('.', '', 1).isdigit():
                                # Range, e.g. 1-2 or 4-5
                                try:
                                    start = float(parts[0])
                                    end = float(parts[1])
                                    # Only integer ranges are expanded, otherwise keep as is
                                    if start.is_integer() and end.is_integer():
                                        volumenumber = ','.join(str(int(i)) for i in range(int(start), int(end)+1))
                                    else:
                                        volumenumber = raw_number
                                except Exception:
                                    volumenumber = raw_number
                            else:
                                volumenumber = raw_number
                        else:
                            volumenumber = raw_number
                    else:
                        series = series_text
        # Fallback: try the old selector
        if not series:
            series_element = parsed.select_one('a.book__series-link')
            if series_element:
                series_text = series_element.get_text(strip=True)
                match = re.match(r'(.+?)\s*\(tom\s*([^\)]+)\)', series_text)
                if match:
                    series = match.group(1)
                    raw_number = match.group(2).replace(' ', '')
                    if '-' in raw_number:
                        parts = raw_number.split('-')
                        if len(parts) == 2 and parts[0].replace('.', '', 1).isdigit() and parts[1].replace('.', '', 1).isdigit():
                            try:
                                start = float(parts[0])
                                end = float(parts[1])
                                if start.is_integer() and end.is_integer():
                                    volumenumber = ','.join(str(int(i)) for i in range(int(start), int(end)+1))
                                else:
                                    volumenumber = raw_number
                            except Exception:
                                volumenumber = raw_number
                        else:
                            volumenumber = raw_number
                    else:
                        volumenumber = raw_number
                else:
                    series = series_text
        # If still no volumenumber, set to "0"
        if not volumenumber:
            volumenumber = "0"
        metadata['series'] = series
        metadata['volumenumber'] = volumenumber
    except Exception as e:
        log.info(f"No series scraped ({metadata['input_folder']}) | {e}")

    # --- Summary / Description ---
    try:
        # Prefer the full description from the collapse-content
        desc_element = parsed.select_one('div#book-description div.collapse-content')
        if desc_element:
            # Get all text, preserving line breaks between <p> tags
            paragraphs = desc_element.find_all(['p', 'br'])
            description = '\n'.join(p.get_text(separator=' ', strip=True) for p in paragraphs if p.name == 'p')
            if not description:
                # fallback to all text
                description = desc_element.get_text(separator='\n', strip=True)
            metadata['summary'] = description
        else:
            # Fallback to meta og:description
            meta_desc = parsed.find("meta", property="og:description")
            if meta_desc and meta_desc.get("content"):
                metadata['summary'] = meta_desc["content"].strip()
            else:
                # Fallback to visible description
                element = parsed.select_one('div.book__description')
                if element:
                    metadata['summary'] = element.get_text(strip=True)
    except Exception as e:
        log.info(f"No summary scraped ({metadata['input_folder']}) | {e}")

    # --- Genres (tags) ---
    try:
        genres_list = []
        # Try meta genre
        meta_genre = parsed.find("meta", property="genre")
        if meta_genre and meta_genre.get("content"):
            genres_list.append(meta_genre["content"].strip())
        # Fallback to visible tags
        genres_container = parsed.select('a.book__category')
        for genre in genres_container:
            genre_text = genre.get_text(strip=True)
            if genre_text:
                genres_list.append(genre_text)
        metadata['genres'] = ','.join(genres_list)
    except Exception as e:
        log.info(f"No genres scraped ({metadata['input_folder']}) | {e}")

    # --- Language ---
    try:
        # Try meta inLanguage or og:inLanguage
        meta_lang = parsed.find("meta", attrs={"property": "inLanguage"})
        if meta_lang and meta_lang.get("content"):
            language = meta_lang["content"].strip()
        else:
            # Fallback: look for "Język:" in details
            language = ""
            for dt in parsed.select('dt'):
                if dt.get_text(strip=True).lower().startswith("język"):
                    dd = dt.find_next_sibling('dd')
                    if dd:
                        language = dd.get_text(strip=True)
        # Fallback: default to 'pol'
        if not language:
            language = 'pol'
        # Convert to ISO code using LANGUAGE_MAP (like in goodreads scrapper)
        lang_key = language.strip().lower()
        iso_code = LANGUAGE_MAP.get(lang_key, language)
        metadata['language'] = iso_code
    except Exception as e:
        log.info(f"No language scraped ({metadata['input_folder']}) | {e}")

    # --- ISBN ---
    try:
        # Try meta books:isbn
        meta_isbn = parsed.find("meta", property="books:isbn")
        if meta_isbn and meta_isbn.get("content"):
            metadata['isbn'] = meta_isbn["content"].strip()
        else:
            # Fallback: look for "ISBN:" in details
            for dt in parsed.select('dt'):
                if dt.get_text(strip=True).lower().startswith("isbn"):
                    dd = dt.find_next_sibling('dd')
                    if dd:
                        metadata['isbn'] = dd.get_text(strip=True)
    except Exception as e:
        log.info(f"No ISBN scraped ({metadata['input_folder']}) | {e}")

    return metadata