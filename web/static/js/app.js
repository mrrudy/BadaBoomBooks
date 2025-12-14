/**
 * BadaBoomBooks Web Interface JavaScript
 * 
 * Handles all client-side functionality for the web interface including
 * file browsing, job management, real-time updates, and user interactions.
 */

class BadaBoomBooksWebApp {
    constructor() {
        this.socket = io();
        this.selectedFolders = new Set();
        this.currentPath = '';
        this.currentJobId = null;
        
        this.initializeEventListeners();
        this.initializeSocketHandlers();
        this.loadInitialData();
    }
    
    initializeEventListeners() {
        // File browser events
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('file-item') || e.target.closest('.file-item')) {
                this.handleFileItemClick(e);
            }
        });
    }
    
    initializeSocketHandlers() {
        // Job progress updates
        this.socket.on('job_progress', (data) => {
            console.log('Received job progress:', data);
            this.updateJobProgress(data);
        });
        
        // Candidate selection required
        this.socket.on('candidate_selection_required', (data) => {
            console.log('Candidate selection required:', data);
            this.showCandidateSelection(data);
        });
        
        // Job completion
        this.socket.on('job_completed', (data) => {
            console.log('Job completed:', data);
            this.handleJobCompletion(data);
        });
        
        // Job failure
        this.socket.on('job_failed', (data) => {
            console.log('Job failed:', data);
            this.handleJobFailure(data);
        });
        
        // Connection events
        this.socket.on('connect', () => {
            console.log('WebSocket connected');
        });
        
        this.socket.on('disconnect', () => {
            console.log('WebSocket disconnected');
        });
    }
    
    loadInitialData() {
        // Load file browser with drives on Windows, root on Unix
        this.browseDirectory('drives');
        this.updateSelectedFoldersDisplay();
    }
    
    // Navigation
    showSection(sectionId) {
        // Hide all sections
        document.querySelectorAll('.content-section').forEach(section => {
            section.style.display = 'none';
        });
        
        // Show selected section
        const targetSection = document.getElementById(sectionId);
        if (targetSection) {
            targetSection.style.display = 'block';
        }
        
        // Update navigation
        document.querySelectorAll('.nav-link').forEach(link => {
            link.classList.remove('active');
        });
        
        document.querySelectorAll(`[href="#${sectionId}"]`).forEach(link => {
            link.classList.add('active');
        });
        
        // Load section-specific data (but avoid recursion)
        if (sectionId === 'browser') {
            this.refreshBrowser();
        }
        // Remove the jobs refresh that was causing recursion
    }
    
    // File Browser
    async browseDirectory(path) {
        try {
            const response = await fetch(`/browse?path=${encodeURIComponent(path)}`);
            const data = await response.json();
            
            if (data.error) {
                this.showToast('Error', data.error, 'danger');
                return;
            }
            
            this.currentPath = data.current_path;
            this.renderFileList(data);
            
        } catch (error) {
            this.showToast('Error', 'Failed to browse directory', 'danger');
            console.error('Browse error:', error);
        }
    }
    
    renderFileList(data) {
        const fileList = document.getElementById('file-list');
        const currentPathElement = document.getElementById('current-path');
        const manualPathInput = document.getElementById('manual-path');
        
        currentPathElement.textContent = data.current_path;
        
        // Update manual path input placeholder
        if (manualPathInput) {
            manualPathInput.value = '';
            manualPathInput.placeholder = data.is_drives ? 'Enter drive letter or path...' : data.current_path;
        }
        
        fileList.innerHTML = '';
        
        // Add parent directory link if available
        if (data.parent) {
            const parentItem = this.createFileItem({
                name: '..',
                path: data.parent,
                type: 'parent',
                audio_count: 0
            });
            fileList.appendChild(parentItem);
        }
        
        // Add folders and audiobook folders
        data.items.forEach(item => {
            const fileItem = this.createFileItem(item);
            fileList.appendChild(fileItem);
        });
    }
    
    createFileItem(item) {
        const div = document.createElement('div');
        div.className = `list-group-item file-item ${item.type}`;
        div.dataset.path = item.path;
        div.dataset.type = item.type;
        
        let icon = '📁';
        let badge = '';
        
        if (item.type === 'parent') {
            icon = '⬆️';
        } else if (item.type === 'audiobook') {
            icon = '🎧';
            badge = `<span class="badge bg-success ms-2">${item.audio_count} files</span>`;
        } else if (item.type === 'drive') {
            icon = '💾';
        } else if (item.type === 'drive_inaccessible') {
            icon = '🚫';
            div.classList.add('text-muted');
        }
        
        const isSelected = this.selectedFolders.has(item.path);
        const checkboxHtml = item.type === 'audiobook' ? 
            `<input type="checkbox" class="form-check-input me-2" ${isSelected ? 'checked' : ''}>` : '';
        
        div.innerHTML = `
            <div class="d-flex justify-content-between align-items-center">
                <div class="d-flex align-items-center">
                    ${checkboxHtml}
                    <span class="me-2">${icon}</span>
                    <span class="file-name">${item.name}</span>
                    ${badge}
                </div>
            </div>
        `;
        
        return div;
    }
    
    handleFileItemClick(e) {
        const fileItem = e.target.closest('.file-item');
        const path = fileItem.dataset.path;
        const type = fileItem.dataset.type;
        
        if (type === 'parent' || type === 'folder' || type === 'drive') {
            // Navigate to directory
            this.browseDirectory(path);
        } else if (type === 'audiobook') {
            // Toggle selection
            const checkbox = fileItem.querySelector('input[type="checkbox"]');
            if (checkbox) {
                checkbox.checked = !checkbox.checked;
                this.toggleFolderSelection(path, checkbox.checked);
            }
        } else if (type === 'drive_inaccessible') {
            this.showToast('Access Denied', 'This drive is not accessible', 'warning');
        }
    }
    
    browseManualPath(path) {
        if (!path.trim()) {
            this.showToast('Invalid Path', 'Please enter a valid path', 'warning');
            return;
        }
        this.browseDirectory(path.trim());
    }
    
    showDrives() {
        this.browseDirectory('drives');
    }
    
    toggleFolderSelection(path, selected) {
        if (selected) {
            this.selectedFolders.add(path);
        } else {
            this.selectedFolders.delete(path);
        }
        
        this.updateSelectedFoldersDisplay();
    }
    
    updateSelectedFoldersDisplay() {
        const selectedCount = document.getElementById('selected-count');
        const selectedFoldersDiv = document.getElementById('selected-folders');
        const processBtn = document.getElementById('process-btn');
        
        selectedCount.textContent = this.selectedFolders.size;
        
        if (this.selectedFolders.size === 0) {
            selectedFoldersDiv.innerHTML = '<p class="text-muted">No folders selected</p>';
            processBtn.disabled = true;
        } else {
            processBtn.disabled = false;
            
            const foldersHtml = Array.from(this.selectedFolders).map(path => {
                const name = path.split(/[\\\/]/).pop();
                return `
                    <div class="selected-folder-item">
                        <span class="text-truncate">${name}</span>
                        <span class="remove-btn" onclick="app.toggleFolderSelection('${path}', false)">
                            <i class="bi bi-x"></i>
                        </span>
                    </div>
                `;
            }).join('');
            
            selectedFoldersDiv.innerHTML = foldersHtml;
        }
        
        this.updateProcessingSummary();
    }
    
    updateProcessingSummary() {
        const summaryDiv = document.getElementById('processing-summary');
        
        if (this.selectedFolders.size === 0) {
            summaryDiv.innerHTML = '<p class="text-muted">Select folders to see processing summary</p>';
            return;
        }
        
        const options = this.getProcessingOptions();
        const operations = [];
        
        if (options.auto_search) operations.push('Automatic metadata search');
        if (options.series) operations.push('Series organization');
        if (options.opf) operations.push('Generate OPF files');
        if (options.id3_tags) operations.push('Update ID3 tags');
        if (options.info_txt) operations.push('Generate info.txt files');
        if (options.cover) operations.push('Download cover images');
        
        summaryDiv.innerHTML = `
            <div class="mb-3">
                <strong>Selected Folders:</strong> ${this.selectedFolders.size}
            </div>
            <div class="mb-3">
                <strong>Operations:</strong>
                <ul class="list-unstyled ms-3">
                    ${operations.map(op => `<li><i class="bi bi-check text-success me-2"></i>${op}</li>`).join('')}
                </ul>
            </div>
        `;
    }
    
    getProcessingOptions() {
        return {
            auto_search: document.getElementById('auto-search').checked,
            site: document.getElementById('search-site').value,
            series: document.getElementById('series-org').checked,
            flatten: document.getElementById('flatten').checked,
            rename: document.getElementById('rename').checked,
            opf: document.getElementById('opf').checked,
            id3_tags: document.getElementById('id3-tags').checked,
            info_txt: document.getElementById('info-txt').checked,
            cover: document.getElementById('cover').checked
        };
    }
    
    // Processing
    async startProcessing() {
        if (this.selectedFolders.size === 0) {
            this.showToast('Warning', 'Please select folders to process', 'warning');
            return;
        }
        
        const options = this.getProcessingOptions();
        const folders = Array.from(this.selectedFolders);
        
        try {
            const response = await fetch('/start_processing', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    folders: folders,
                    options: options
                })
            });
            
            const data = await response.json();
            
            if (data.error) {
                this.showToast('Error', data.error, 'danger');
                return;
            }
            
            this.currentJobId = data.job_id;
            console.log('[DEBUG] Set currentJobId to:', this.currentJobId);
            this.showProgressModal();
            // Don't automatically switch to jobs section
            
        } catch (error) {
            this.showToast('Error', 'Failed to start processing', 'danger');
            console.error('Processing error:', error);
        }
    }
    
    // Progress Modal
    showProgressModal() {
        const modal = new bootstrap.Modal(document.getElementById('progressModal'));
        modal.show();
        
        // Reset progress
        this.updateProgressModal({
            progress: 0,
            current_step: 'Initializing...',
            current_book: ''
        });
    }
    
    updateProgressModal(data) {
        console.log('Updating progress modal with:', data);
        
        const progressBar = document.getElementById('progress-bar');
        const progressPercentage = document.getElementById('progress-percentage');
        const progressText = document.getElementById('progress-text');
        const currentBookName = document.getElementById('current-book-name');
        
        if (progressBar) {
            progressBar.style.width = `${data.progress || 0}%`;
        }
        
        if (progressPercentage) {
            progressPercentage.textContent = `${Math.round(data.progress || 0)}%`;
        }
        
        if (progressText) {
            progressText.textContent = data.current_step || 'Processing...';
        }
        
        if (currentBookName) {
            currentBookName.textContent = data.current_book || '-';
        }
        
        // Add log entry if we have a step update
        if (data.current_step) {
            this.addLogEntry('info', data.current_step);
        }
    }
    
    addLogEntry(level, message) {
        const logDiv = document.getElementById('processing-log');
        const timestamp = new Date().toLocaleTimeString();
        
        const logEntry = document.createElement('div');
        logEntry.className = 'log-entry';
        logEntry.innerHTML = `
            <span class="log-timestamp">[${timestamp}]</span>
            <span class="log-level-${level} ms-2">${message}</span>
        `;
        
        logDiv.appendChild(logEntry);
        logDiv.scrollTop = logDiv.scrollHeight;
    }
    
    // Candidate Selection
    showCandidateSelection(data) {
        const modal = new bootstrap.Modal(document.getElementById('candidateModal'));
        
        // Update book context
        const bookContext = document.getElementById('book-context');
        bookContext.innerHTML = this.renderBookContext(data.book_info);
        
        // Update candidates list
        const candidatesList = document.getElementById('candidates-list');
        candidatesList.innerHTML = this.renderCandidates(data.candidates);
        
        modal.show();
    }
    
    renderBookContext(bookInfo) {
        if (!bookInfo || Object.keys(bookInfo).length === 0) {
            return `
                <h6><i class="bi bi-book me-2"></i>Select Metadata For:</h6>
                <p class="mb-0">Unknown audiobook</p>
            `;
        }
        
        const fields = [
            { key: 'title', icon: 'book', label: 'Title' },
            { key: 'author', icon: 'person', label: 'Author' },
            { key: 'series', icon: 'collection', label: 'Series' },
            { key: 'year', icon: 'calendar', label: 'Year' },
            { key: 'source', icon: 'info-circle', label: 'Source' }
        ];
        
        const infoHtml = fields
            .filter(field => bookInfo[field.key])
            .map(field => `
                <div class="mb-2">
                    <i class="bi bi-${field.icon} me-2"></i>
                    <strong>${field.label}:</strong> ${bookInfo[field.key]}
                </div>
            `).join('');
        
        return `
            <h6><i class="bi bi-book me-2"></i>Select Metadata For:</h6>
            ${infoHtml}
        `;
    }
    
    renderCandidates(candidates) {
        return candidates.map((candidate, index) => `
            <div class="card candidate-card mb-3" onclick="selectCandidate(${index})">
                <div class="card-body">
                    <div class="d-flex justify-content-between align-items-start">
                        <div style="flex: 1;">
                            <h6 class="card-title">
                                <i class="bi bi-globe me-2"></i>
                                ${candidate.site_key}
                            </h6>
                            <h5 class="card-subtitle mb-2">${candidate.title}</h5>
                            <p class="card-text">${candidate.snippet}</p>
                            <small class="text-muted">${candidate.url}</small>
                        </div>
                        <button class="btn btn-outline-primary ms-3" onclick="selectCandidate(${index})">
                            Select
                        </button>
                    </div>
                </div>
            </div>
        `).join('');
    }
    
    // Utility Functions
    refreshBrowser() {
        // If we're at Computer, redirect to drives
        if (this.currentPath === 'Computer' || this.currentPath === '') {
            this.browseDirectory('drives');
        } else {
            this.browseDirectory(this.currentPath);
        }
    }
    
    goUp() {
        // Navigate to parent directory
        const pathParts = this.currentPath.split(/[\\\/]/);
        pathParts.pop();
        const parentPath = pathParts.join('/') || '/';
        this.browseDirectory(parentPath);
    }
    
    async refreshJobs() {
        // Just refresh the jobs data without changing sections
        console.log('Refreshing jobs data');
        // In a real implementation, this would fetch job status from server
    }
    
    showToast(title, message, type = 'info') {
        // Create and show a simple alert instead of toast for demo
        const alertClass = type === 'danger' ? 'alert-danger' : 
                          type === 'warning' ? 'alert-warning' : 
                          type === 'success' ? 'alert-success' : 'alert-info';
        
        const alertHtml = `
            <div class="alert ${alertClass} alert-dismissible fade show position-fixed" 
                 style="top: 20px; right: 20px; z-index: 9999; min-width: 300px;">
                <strong>${title}:</strong> ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', alertHtml);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            const alert = document.querySelector('.alert:last-of-type');
            if (alert) {
                alert.remove();
            }
        }, 5000);
    }
    
    updateJobProgress(data) {
        console.log('[DEBUG] updateJobProgress called with:', data);
        if (data.job_id === this.currentJobId) {
            console.log('[DEBUG] Job ID matches current job, updating progress modal');
            this.updateProgressModal(data);
        } else {
            console.log('[DEBUG] Job ID mismatch - received:', data.job_id, 'current:', this.currentJobId);
        }
    }
    
    handleJobCompletion(data) {
        if (data.job_id === this.currentJobId) {
            this.addLogEntry('success', 'Processing completed successfully!');
            document.getElementById('cancel-job-btn').style.display = 'none';
            document.getElementById('close-progress-btn').style.display = 'block';
            
            this.showToast('Success', 'Audiobook processing completed!', 'success');
        }
    }
    
    handleJobFailure(data) {
        if (data.job_id === this.currentJobId) {
            this.addLogEntry('error', `Processing failed: ${data.error}`);
            document.getElementById('cancel-job-btn').style.display = 'none';
            document.getElementById('close-progress-btn').style.display = 'block';
            
            this.showToast('Error', 'Processing failed. Check the log for details.', 'danger');
        }
    }
    
    closeProgressModal() {
        const modal = bootstrap.Modal.getInstance(document.getElementById('progressModal'));
        modal.hide();
        this.currentJobId = null;
    }
    
    async cancelJob() {
        if (this.currentJobId) {
            this.addLogEntry('warning', 'Job cancellation requested...');
            this.closeProgressModal();
        }
    }
}

// Global functions for template access
let app;

function showSection(sectionId) {
    app.showSection(sectionId);
}

function refreshBrowser() {
    app.refreshBrowser();
}

function goUp() {
    app.goUp();
}

function startProcessing() {
    app.startProcessing();
}

function previewChanges() {
    app.startProcessing();
}

function refreshJobs() {
    app.refreshJobs();
}

function showDrives() {
    app.showDrives();
}

function handlePathInput(event) {
    if (event.key === 'Enter') {
        const path = event.target.value;
        app.browseManualPath(path);
    }
}

function goToPath() {
    const manualPathInput = document.getElementById('manual-path');
    if (manualPathInput) {
        const path = manualPathInput.value;
        app.browseManualPath(path);
    }
}

function closeProgressModal() {
    app.closeProgressModal();
}

function cancelJob() {
    app.cancelJob();
}

function selectCandidate(index) {
    // Send candidate selection to server
    if (app.currentJobId) {
        fetch('/select_candidate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                job_id: app.currentJobId,
                candidate_index: index
            })
        }).then(response => response.json())
        .then(data => {
            if (data.success) {
                // Close candidate modal
                const modal = bootstrap.Modal.getInstance(document.getElementById('candidateModal'));
                modal.hide();
                
                app.addLogEntry('success', `Selected candidate ${index + 1}`);
            } else {
                app.showToast('Error', data.error || 'Failed to select candidate', 'danger');
            }
        })
        .catch(error => {
            app.showToast('Error', 'Failed to select candidate', 'danger');
            console.error('Selection error:', error);
        });
    }
}

function skipCurrentBook() {
    // Skip current book
    if (app.currentJobId) {
        fetch('/skip_book', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                job_id: app.currentJobId
            })
        }).then(response => response.json())
        .then(data => {
            if (data.success) {
                // Close candidate modal
                const modal = bootstrap.Modal.getInstance(document.getElementById('candidateModal'));
                modal.hide();
                
                app.addLogEntry('warning', 'Skipped current book');
            } else {
                app.showToast('Error', data.error || 'Failed to skip book', 'danger');
            }
        })
        .catch(error => {
            app.showToast('Error', 'Failed to skip book', 'danger');
            console.error('Skip error:', error);
        });
    }
}

// Initialize application when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    app = new BadaBoomBooksWebApp();
    
    // Set up form change listeners
    document.querySelectorAll('#processing-form input, #processing-form select').forEach(element => {
        element.addEventListener('change', () => {
            app.updateProcessingSummary();
        });
    });
    
    console.log('BadaBoomBooks Web Interface initialized');
});
