"""
File operations processor.

This module handles all file system operations including copying,
moving, organizing, and path management for audiobook folders.
"""

import shutil
import logging as log
from pathlib import Path
from typing import Optional

from ..models import BookMetadata, ProcessingArgs
from ..utils import clean_filename, get_folder_size, format_file_size


class FileProcessor:
    """Handles file system operations for audiobook processing."""

    def __init__(self, args: ProcessingArgs):
        self.args = args
        self.dry_run = args.dry_run
        self.lock_manager = None  # Injected by queue system for parallel processing
    
    def process_folder_organization(self, metadata: BookMetadata) -> bool:
        """
        Organize folder according to processing arguments.
        
        Args:
            metadata: BookMetadata with file paths and information
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Determine output path
            output_path = self._determine_output_path(metadata)
            if not output_path:
                return False
            
            # Create output directory structure
            final_output = self._create_output_structure(metadata, output_path)
            metadata.final_output = final_output
            
            # Handle copy/move operations
            if self.args.copy and not self.args.move:
                return self._copy_folder(metadata)
            elif self.args.move and not self.args.copy:
                return self._move_folder(metadata)
            elif not self.args.copy and not self.args.move:
                # In-place processing
                metadata.final_output = Path(metadata.input_folder)
                return True
            else:
                log.error("Both copy and move flags set - this should have been caught in validation")
                return False
                
        except Exception as e:
            log.error(f"Error organizing folder {metadata.input_folder}: {e}")
            metadata.mark_as_failed(f"File organization error: {e}")
            return False
    
    def _determine_output_path(self, metadata: BookMetadata) -> Optional[Path]:
        """Determine the base output path for organized files."""
        if self.args.output:
            return Path(self.args.output)
        else:
            # Use parent of input folder with default suffix
            from ..config import default_output
            input_path = Path(metadata.input_folder)
            return input_path.parent / default_output
    
    def _create_output_structure(self, metadata: BookMetadata, base_output: Path) -> Path:
        """
        Create the complete output directory structure.
        
        Args:
            metadata: BookMetadata with book information
            base_output: Base output directory
            
        Returns:
            Final output path for the book
        """
        # Clean author and title for filesystem
        author_clean = clean_filename(metadata.get_safe_author())
        title_clean = clean_filename(metadata.get_safe_title())
        
        log.info(f"Cleaned path names: Author ({author_clean}) | Title ({title_clean})")
        
        # Create author folder
        author_folder = base_output / author_clean

        if not self.dry_run:
            # Use file lock if available (parallel processing)
            if self.lock_manager and metadata.task_id:
                with self.lock_manager.lock_directory(author_folder, metadata.task_id):
                    author_folder.mkdir(parents=True, exist_ok=True)
            else:
                author_folder.mkdir(parents=True, exist_ok=True)
        
        # Handle series-based structure if requested
        if self.args.series and metadata.has_series_info():
            series_clean = clean_filename(metadata.series)
            volume_clean = clean_filename(metadata.volumenumber)
            
            log.info(f"Cleaned series: {series_clean} | {volume_clean}")
            
            series_dir = author_folder / series_clean
            if not self.dry_run:
                # Use file lock if available (parallel processing)
                if self.lock_manager and metadata.task_id:
                    with self.lock_manager.lock_directory(series_dir, metadata.task_id):
                        series_dir.mkdir(parents=True, exist_ok=True)
                else:
                    series_dir.mkdir(parents=True, exist_ok=True)
            
            final_output = series_dir / f"{volume_clean} - {title_clean}"
        else:
            final_output = author_folder / title_clean
        
        return final_output.resolve()
    
    def _copy_folder(self, metadata: BookMetadata) -> bool:
        """Copy audiobook folder to new location."""
        source = Path(metadata.input_folder)
        target = metadata.final_output
        
        if self.dry_run:
            size = get_folder_size(source)
            print(f"[DRY-RUN] Would copy '{source}' to '{target}' ({format_file_size(size)})")
            return True
        
        try:
            print(f"Copying {source.name}...")
            log.info(f"Copying folder: {source} -> {target}")
            
            shutil.copytree(source, target, dirs_exist_ok=True, copy_function=shutil.copy2)
            
            # Verify copy was successful
            if target.exists():
                log.info(f"Successfully copied folder to: {target}")
                return True
            else:
                log.error(f"Copy operation completed but target doesn't exist: {target}")
                return False
                
        except Exception as e:
            log.error(f"Error copying folder {source} to {target}: {e}")
            metadata.mark_as_failed(f"Copy error: {e}")
            return False
    
    def _move_folder(self, metadata: BookMetadata) -> bool:
        """Move audiobook folder to new location."""
        source = Path(metadata.input_folder)
        target = metadata.final_output
        
        if self.dry_run:
            size = get_folder_size(source)
            print(f"[DRY-RUN] Would move '{source}' to '{target}' ({format_file_size(size)})")
            return True
        
        try:
            print(f"Moving {source.name}...")
            log.info(f"Moving folder: {source} -> {target}")
            
            # Try direct rename first (faster if on same filesystem)
            try:
                source.rename(target)
                log.info(f"Successfully moved folder using rename: {target}")
                return True
            except OSError:
                # Cross-filesystem move - use copy then delete
                log.info(f"Direct rename failed, performing copy-then-delete move")
                shutil.copytree(source, target, dirs_exist_ok=True, copy_function=shutil.copy2)
                shutil.rmtree(source)
                log.info(f"Successfully moved folder using copy-delete: {target}")
                return True
                
        except Exception as e:
            log.error(f"Error moving folder {source} to {target}: {e}")
            metadata.mark_as_failed(f"Move error: {e}")
            return False
    
    def flatten_folder(self, metadata: BookMetadata) -> bool:
        """
        Flatten audiobook folder structure, moving all audio files to root.
        
        Args:
            metadata: BookMetadata with target folder path
            
        Returns:
            True if successful, False otherwise
        """
        if self.dry_run:
            print(f"[DRY-RUN] Would flatten folder: {metadata.final_output}")
            return True
        
        try:
            from ..utils import find_audio_files, calculate_padding_for_tracks
            
            print("Flattening...")
            log.info(f"Flattening folder: {metadata.final_output}")
            
            # Get all audio files in subdirectories
            all_audio_files = find_audio_files(metadata.final_output)
            files_to_move = [f for f in all_audio_files if f.parent != metadata.final_output]
            
            if not files_to_move:
                log.info("No audio files in subdirectories to flatten")
                return True
            
            # Sort files and determine padding
            files_to_move.sort()
            padding = calculate_padding_for_tracks(len(files_to_move))
            
            log.debug(f"Audio files to flatten: {[str(f) for f in files_to_move]}")
            
            # Move and rename files
            title_clean = clean_filename(metadata.get_safe_title())
            
            for index, file_path in enumerate(files_to_move, 1):
                new_name = f"{str(index).zfill(padding)} - {title_clean}{file_path.suffix}"
                new_path = metadata.final_output / new_name
                
                log.debug(f"Moving {file_path} -> {new_path}")
                file_path.rename(new_path)
            
            # Remove empty subdirectories
            self._remove_empty_subdirs(metadata.final_output)
            
            log.info(f"Successfully flattened {len(files_to_move)} audio files")
            return True
            
        except Exception as e:
            log.error(f"Error flattening folder {metadata.final_output}: {e}")
            metadata.mark_as_failed(f"Flatten error: {e}")
            return False
    
    def rename_audio_tracks(self, metadata: BookMetadata) -> bool:
        """
        Rename audio tracks to standardized format.
        
        Args:
            metadata: BookMetadata with target folder path
            
        Returns:
            True if successful, False otherwise
        """
        if self.dry_run:
            print(f"[DRY-RUN] Would rename audio tracks in: {metadata.final_output}")
            return True
        
        try:
            from ..utils import find_audio_files, calculate_padding_for_tracks
            
            print("Renaming...")
            log.info(f"Renaming audio tracks in: {metadata.final_output}")
            
            # Get all audio files in the target directory
            audio_files = find_audio_files(metadata.final_output)
            
            if not audio_files:
                log.info("No audio files found to rename")
                return True
            
            # Sort and determine padding
            audio_files.sort()
            padding = calculate_padding_for_tracks(len(audio_files))
            
            log.debug(f"Audio files to rename: {[str(f) for f in audio_files]}")
            
            # Rename files
            title_clean = clean_filename(metadata.get_safe_title())
            
            for index, file_path in enumerate(audio_files, 1):
                new_name = f"{str(index).zfill(padding)} - {title_clean}{file_path.suffix}"
                new_path = file_path.parent / new_name
                
                # Skip if already has correct name
                if file_path.name == new_name:
                    continue
                
                log.debug(f"Renaming {file_path.name} -> {new_name}")
                file_path.rename(new_path)
            
            log.info(f"Successfully renamed {len(audio_files)} audio files")
            return True
            
        except Exception as e:
            log.error(f"Error renaming tracks in {metadata.final_output}: {e}")
            metadata.mark_as_failed(f"Rename error: {e}")
            return False
    
    def _remove_empty_subdirs(self, root_path: Path):
        """Remove empty subdirectories after flattening."""
        try:
            for item in root_path.iterdir():
                if item.is_dir():
                    # Recursively check subdirectories
                    self._remove_empty_subdirs(item)
                    
                    # Remove if empty
                    try:
                        if not any(item.iterdir()):
                            log.debug(f"Removing empty directory: {item}")
                            item.rmdir()
                    except OSError:
                        # Directory not empty or permission denied
                        pass
        except Exception as e:
            log.warning(f"Error removing empty subdirectories: {e}")


# Legacy functions for backward compatibility
def flatten_folder(metadata: BookMetadata, logger: log.Logger, dry_run: bool = False) -> None:
    """Legacy function for backward compatibility."""
    from ..models import ProcessingArgs
    args = ProcessingArgs(dry_run=dry_run, flatten=True)
    processor = FileProcessor(args)
    processor.flatten_folder(metadata)


def rename_tracks(metadata: BookMetadata, logger: log.Logger, dry_run: bool = False) -> None:
    """Legacy function for backward compatibility."""
    from ..models import ProcessingArgs
    args = ProcessingArgs(dry_run=dry_run, rename=True)
    processor = FileProcessor(args)
    processor.rename_audio_tracks(metadata)
