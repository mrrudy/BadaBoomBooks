"""
Audio operations processor.

This module handles audio file operations including ID3 tag updates
and audio file analysis.
"""

import logging as log
from pathlib import Path
from typing import List

from ..models import BookMetadata
from ..utils import find_audio_files


class AudioProcessor:
    """Handles audio file operations."""
    
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
    
    def update_id3_tags(self, metadata: BookMetadata) -> bool:
        """
        Update ID3 tags for all audio files in the audiobook folder.
        
        Args:
            metadata: BookMetadata object with tag information
            
        Returns:
            True if successful, False otherwise
        """
        if self.dry_run:
            print(f"[DRY-RUN] Would update ID3 tags in: {metadata.final_output}")
            return True
        
        try:
            print("Updating ID3 tags...")
            log.info(f"Updating ID3 tags for: {metadata.input_folder}")
            
            # Find all audio files
            audio_files = find_audio_files(metadata.final_output)
            
            if not audio_files:
                log.info("No audio files found for ID3 tagging")
                return True
            
            # Update tags for each file
            success_count = 0
            for audio_file in audio_files:
                if self._update_single_file_tags(audio_file, metadata):
                    success_count += 1

            log.info(f"Successfully updated ID3 tags for {success_count}/{len(audio_files)} files")
            print(f"Updated ID3 tags for {success_count}/{len(audio_files)} audio files")

            # Return True only if ALL files were updated successfully
            return success_count == len(audio_files)
            
        except Exception as e:
            log.error(f"Error updating ID3 tags for {metadata.input_folder}: {e}")
            metadata.mark_as_failed(f"ID3 tag update error: {e}")
            return False
    
    def _update_single_file_tags(self, file_path: Path, metadata: BookMetadata) -> bool:
        """Update ID3 tags for a single audio file."""
        try:
            if file_path.suffix.lower() == ".mp3":
                return self._update_mp3_tags(file_path, metadata)
            else:
                # For non-MP3 files, we could implement other tag formats
                log.info(f"Skipping non-MP3 file for ID3 tagging: {file_path}")
                return True
                
        except Exception as e:
            log.error(f"Failed to update ID3 tags for {file_path}: {e}")
            return False
    
    def _update_mp3_tags(self, file_path: Path, metadata: BookMetadata) -> bool:
        """Update ID3 tags for MP3 files."""
        try:
            from mutagen.easyid3 import EasyID3
            from mutagen.id3 import ID3, ID3NoHeaderError, COMM, TDRC
            from mutagen.mp3 import MP3

            # Prepare tag values
            title = metadata.get_safe_title()
            author = metadata.get_safe_author()
            album = metadata.series or title
            genre = metadata.genres
            date_value = metadata.get_publication_date()
            language = metadata.language or 'eng'

            # Build comment with ASIN/ISBN prefix if available
            comment = self._build_comment_field(metadata)

            # Try to load existing ID3 tags, create new ones if they don't exist
            try:
                audio = EasyID3(str(file_path))
            except ID3NoHeaderError:
                # File has no ID3 tags - create new ones
                log.debug(f"No ID3 tags found in {file_path}, creating new tags")
                audio = MP3(str(file_path))
                audio.add_tags()
                audio.save()
                # Now load as EasyID3
                audio = EasyID3(str(file_path))

            # Update easy ID3 tags
            audio['title'] = title
            audio['artist'] = author
            audio['album'] = album

            if genre:
                audio['genre'] = genre
            if date_value:
                audio['date'] = date_value
            if language:
                audio['language'] = language

            audio.save()

            # Add advanced tags using full ID3
            id3 = ID3(str(file_path))

            # Add comment with language code
            comm_lang = language if len(language) == 3 else 'eng'
            id3.add(COMM(encoding=3, lang=comm_lang, desc='desc', text=comment))

            # Add date if available
            if date_value:
                id3.add(TDRC(encoding=3, text=date_value))

            id3.save()

            log.debug(f"Updated ID3 tags for: {file_path}")
            return True

        except ImportError:
            log.error("Mutagen library not available for ID3 tag updates")
            return False
        except Exception as e:
            log.error(f"Error updating MP3 tags for {file_path}: {e}")
            return False
    
    def _build_comment_field(self, metadata: BookMetadata) -> str:
        """Build comment field with identifiers and summary."""
        comment_parts = []
        
        if metadata.asin:
            comment_parts.append(f"ASIN: {metadata.asin}")
        if metadata.isbn:
            comment_parts.append(f"ISBN: {metadata.isbn}")
        
        comment_prefix = " | ".join(comment_parts)
        summary = metadata.summary or ""
        
        if comment_prefix:
            return f"{comment_prefix} | {summary}" if summary else comment_prefix
        else:
            return summary
    
    def analyze_audio_files(self, folder_path: Path) -> dict:
        """
        Analyze audio files in a folder to extract information.
        
        Args:
            folder_path: Path to analyze
            
        Returns:
            Dictionary with analysis results
        """
        try:
            audio_files = find_audio_files(folder_path)
            
            analysis = {
                'total_files': len(audio_files),
                'file_types': {},
                'total_duration': 0,
                'has_id3_info': False,
                'sample_metadata': {}
            }
            
            # Count file types
            for file_path in audio_files:
                ext = file_path.suffix.lower()
                analysis['file_types'][ext] = analysis['file_types'].get(ext, 0) + 1
            
            # Analyze first file for metadata if available
            if audio_files:
                analysis['sample_metadata'] = self._extract_sample_metadata(audio_files[0])
                analysis['has_id3_info'] = bool(analysis['sample_metadata'])
            
            return analysis
            
        except Exception as e:
            log.error(f"Error analyzing audio files in {folder_path}: {e}")
            return {'error': str(e)}
    
    def _extract_sample_metadata(self, file_path: Path) -> dict:
        """Extract metadata from a sample audio file."""
        try:
            from tinytag import TinyTag
            
            tag = TinyTag.get(str(file_path))
            
            return {
                'title': tag.title,
                'artist': tag.artist,
                'album': tag.album,
                'duration': tag.duration,
                'bitrate': tag.bitrate,
                'filesize': tag.filesize
            }
            
        except ImportError:
            log.warning("TinyTag not available for audio analysis")
            return {}
        except Exception as e:
            log.debug(f"Could not extract metadata from {file_path}: {e}")
            return {}


# Legacy function for backward compatibility
def update_id3_tags(metadata: BookMetadata, logger: log.Logger, dry_run: bool = False) -> None:
    """Legacy function for backward compatibility."""
    processor = AudioProcessor(dry_run=dry_run)
    processor.update_id3_tags(metadata)
