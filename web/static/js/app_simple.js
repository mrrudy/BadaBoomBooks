/**
 * Updated web interface JavaScript with real BadaBoomBooks integration
 * This version handles actual processing states and provides detailed feedback
 */

class BadaBoomBooksWebApp {
    constructor() {
        this.selectedFolders = new Set();
        this.currentPath = '';
        this.currentJobId = null;
        this.pollingInterval = null;
        this.jobCompleted = false;
        this.lastLoggedStep = null;
        
        this.initializeEventListeners();
        this.loadInitialData();
        this.testIntegration();
    }
    
    async testIntegration() {
        try {
            const response = await fetch('/test_processing');
            const data = await response.json();
            
            if (data.status === 'success') {
                console.log('✅ BadaBoomBooks integration working:', data.message);
                this.showToast('Integration Ready', 'BadaBoomBooks core is properly loaded', 'success');
            } else if (data.status === 'warning') {
                console.log('⚠️ BadaBoomBooks simulation mode:', data.message);
                this.showToast('Simulation Mode', 'Running in simulation mode - core modules not available', 'warning');
            } else {
                console.error('❌ Integration test failed:', data.message);
                this.showToast('Integration Warning', 'Core modules may not be available', 'warning');
            }
        } catch (error) {
            console.error('❌ Integration test error:', error);
            this.showToast('Integration Error', 'Failed to test integration', 'danger');
        }
    }
    
    initializeEventListeners() {
        // File browser events
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('file-item') || e.target.closest('.file-item')) {
                this.handleFileItemClick(e);
            }
        });
        
        // Form change listeners for real-time options preview
        document.querySelectorAll('#processing-form input, #processing-form select').forEach(element => {
            element.addEventListener('change', () => {
                this.updateProcessingSummary();
            });
        });
    }
    
    loadInitialData() {
        this.browseDirectory('drives');
        this.updateSelectedFoldersDisplay();
        this.updateProcessingSummary();
    }
    
    updateProcessingSummary() {
        const options = this.getProcessingOptions();
        const summaryDiv = document.getElementById('processing-summary');
        
        if (!summaryDiv) return;
        
        const operations = [];
        
        // Auto-search is always enabled in web interface
        operations.push(`🔍 Auto-search on ${options.site === 'all' ? 'all sites' : options.site}`);
        
        if (options.series) operations.push('📚 Series organization');
        if (options.flatten) operations.push('📁 Flatten folder structure');
        if (options.rename) operations.push('🏷️ Rename audio tracks');
        if (options.opf) operations.push('📄 Create OPF metadata');
        if (options.id3_tags) operations.push('🏷️ Update ID3 tags');
        if (options.info_txt) operations.push('📝 Create info.txt');
        if (options.cover) operations.push('🖼️ Download cover images');
        
        if (options.dry_run) {
            operations.push('⚠️ <strong>DRY RUN MODE</strong> - No files will be modified');
        }
        
        const html = operations.length > 0 ? 
            operations.map(op => `<div class="small">${op}</div>`).join('') :
            '<div class="text-muted small">No processing options selected</div>';
        
        summaryDiv.innerHTML = html;
    }
    
    // File Browser
    async browseDirectory(path) {
        try {
            const response = await fetch(`/browse?path=${encodeURIComponent(path)}`);
            const data = await response.json();
            
            if (data.error) {
                this.showToast('Browse Error', data.error, 'danger');
                return;
            }
            
            this.currentPath = data.current_path;
            this.renderFileList(data);
            
            // Update path input if exists
            const pathInput = document.getElementById('path-input');
            if (pathInput) {
                pathInput.value = data.current_path;
            }
            
        } catch (error) {
            this.showToast('Network Error', 'Failed to browse directory', 'danger');
            console.error('Browse error:', error);
        }
    }
    
    renderFileList(data) {
        const fileList = document.getElementById('file-list');
        const currentPathElement = document.getElementById('current-path');
        
        if (currentPathElement) currentPathElement.textContent = data.current_path;
        if (!fileList) return;
        
        fileList.innerHTML = '<div class="text-center p-3"><div class="spinner-border spinner-border-sm" role="status"></div> Loading...</div>';
        
        setTimeout(() => {
            fileList.innerHTML = '';
            
            if (data.parent) {
                const parentItem = this.createFileItem({
                    name: '..',
                    path: data.parent,
                    type: 'parent',
                    audio_count: 0
                });
                fileList.appendChild(parentItem);
            }
            
            // Sort items: audiobooks first, then folders
            const sortedItems = data.items.sort((a, b) => {
                if (a.type === 'audiobook' && b.type !== 'audiobook') return -1;
                if (b.type === 'audiobook' && a.type !== 'audiobook') return 1;
                return a.name.localeCompare(b.name);
            });
            
            sortedItems.forEach(item => {
                const fileItem = this.createFileItem(item);
                fileList.appendChild(fileItem);
            });
            
            // Show count summary
            const audiobookCount = data.items.filter(item => item.type === 'audiobook').length;
            const folderCount = data.items.filter(item => item.type === 'folder').length;
            
            if (audiobookCount > 0 || folderCount > 0) {
                const summary = document.createElement('div');
                summary.className = 'text-muted small p-2 border-top';
                summary.innerHTML = `Found ${audiobookCount} audiobook folder(s) and ${folderCount} regular folder(s)`;
                fileList.appendChild(summary);
            }
        }, 100);
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
            badge = `<span class="badge bg-success ms-2">${item.audio_count} audio file(s)</span>`;
        } else if (item.type === 'drive') {
            icon = '💾';
        } else if (item.type === 'drive_inaccessible') {
            icon = '🚫';
            div.classList.add('text-muted');
        }
        
        const isSelected = this.selectedFolders.has(item.path);
        const checkboxHtml = item.type === 'audiobook' ? 
            `<input type="checkbox" class="form-check-input me-2" ${isSelected ? 'checked' : ''}
                   title="Select this audiobook folder for processing">` : '';
        
        div.innerHTML = `
            <div class="d-flex justify-content-between align-items-center">
                <div class="d-flex align-items-center">
                    ${checkboxHtml}
                    <span class="me-2">${icon}</span>
                    <span class="file-name">${item.name}</span>
                    ${badge}
                </div>
                ${item.type === 'audiobook' ? '<small class="text-muted">Click to select/deselect</small>' : ''}
            </div>
        `;
        
        return div;
    }
    
    handleFileItemClick(e) {
        const fileItem = e.target.closest('.file-item');
        const path = fileItem.dataset.path;
        const type = fileItem.dataset.type;
        
        if (type === 'parent' || type === 'folder' || type === 'drive') {
            this.browseDirectory(path);
        } else if (type === 'audiobook') {
            const checkbox = fileItem.querySelector('input[type="checkbox"]');
            if (checkbox) {
                checkbox.checked = !checkbox.checked;
                this.toggleFolderSelection(path, checkbox.checked);
            }
        } else if (type === 'drive_inaccessible') {
            this.showToast('Access Denied', 'This drive is not accessible', 'warning');
        }
    }
    
    toggleFolderSelection(path, selected) {
        if (selected) {
            this.selectedFolders.add(path);
        } else {
            this.selectedFolders.delete(path);
        }
        this.updateSelectedFoldersDisplay();
        this.updateProcessingSummary();
    }
    
    updateSelectedFoldersDisplay() {
        const selectedCount = document.getElementById('selected-count');
        const selectedCountDisplay = document.getElementById('selected-count-display');
        const selectedFoldersDiv = document.getElementById('selected-folders');
        const selectedFoldersDisplay = document.getElementById('selected-folders-display');
        const processBtn = document.getElementById('process-btn');
        const previewBtn = document.getElementById('preview-btn');
        
        if (selectedCount) selectedCount.textContent = this.selectedFolders.size;
        if (selectedCountDisplay) selectedCountDisplay.textContent = this.selectedFolders.size;
        
        const hasSelection = this.selectedFolders.size > 0;
        
        if (processBtn) processBtn.disabled = !hasSelection;
        if (previewBtn) previewBtn.disabled = !hasSelection;
        
        if (!hasSelection) {
            if (selectedFoldersDiv) selectedFoldersDiv.innerHTML = '<p class="text-muted">No folders selected</p>';
            if (selectedFoldersDisplay) selectedFoldersDisplay.innerHTML = '<p class="text-muted small">No folders selected</p>';
        } else {
            const foldersHtml = Array.from(this.selectedFolders).map(path => {
                const name = path.split(/[\\\/]/).pop();
                return `
                    <div class="selected-folder-item d-flex justify-content-between align-items-center mb-2 p-2 border rounded">
                        <div class="d-flex align-items-center">
                            <span class="me-2">🎧</span>
                            <div>
                                <div class="fw-bold small">${name}</div>
                                <div class="text-muted" style="font-size: 0.7rem;">${path}</div>
                            </div>
                        </div>
                        <button class="btn btn-sm btn-outline-danger" onclick="app.toggleFolderSelection('${path}', false)" title="Remove from selection">
                            <i class="bi bi-x"></i>
                        </button>
                    </div>
                `;
            }).join('');
            
            if (selectedFoldersDiv) selectedFoldersDiv.innerHTML = foldersHtml;
            if (selectedFoldersDisplay) selectedFoldersDisplay.innerHTML = foldersHtml;
        }
    }
    
    getProcessingOptions() {
        return {
            auto_search: true,  // Always true for web interface
            site: document.getElementById('search-site')?.value || 'all',
            series: document.getElementById('series-org')?.checked || false,
            flatten: document.getElementById('flatten')?.checked || false,
            rename: document.getElementById('rename')?.checked || false,
            opf: document.getElementById('opf')?.checked || true,  // Default to true
            id3_tags: document.getElementById('id3-tags')?.checked || false,
            info_txt: document.getElementById('info-txt')?.checked || false,
            cover: document.getElementById('cover')?.checked || false,
            dry_run: document.getElementById('dry-run')?.checked || false,
            
            // Advanced options
            search_limit: parseInt(document.getElementById('search-limit')?.value) || 5,
            download_limit: parseInt(document.getElementById('download-limit')?.value) || 3,
            search_delay: parseFloat(document.getElementById('search-delay')?.value) || 2.0,
            debug: document.getElementById('debug-mode')?.checked || false
        };
    }
    
    // Enhanced processing with real BadaBoomBooks integration
    async startProcessing() {
        if (this.selectedFolders.size === 0) {
            this.showToast('Warning', 'Please select folders to process', 'warning');
            return;
        }
        
        const options = this.getProcessingOptions();
        const folders = Array.from(this.selectedFolders);
        
        // Show confirmation dialog for non-dry-run operations
        if (!options.dry_run) {
            const confirmed = confirm(
                `⚠️ You are about to process ${folders.length} audiobook folder(s) with REAL file operations.\n\n` +
                `This will modify files and folders. Are you sure you want to continue?\n\n` +
                `Tip: Enable "Dry Run Mode" in the options to test without making changes.`
            );
            
            if (!confirmed) {
                return;
            }
        }
        
        try {
            console.log('🚀 Starting BadaBoomBooks processing');
            
            this.showToast('Starting', 'Initializing processing...', 'info');
            
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
            this.jobCompleted = false;
            
            console.log('✅ Got job ID:', this.currentJobId);
            
            this.showProgressModal();
            this.startPolling();
            
        } catch (error) {
            this.showToast('Error', 'Failed to start processing', 'danger');
            console.error('Processing error:', error);
        }
    }
    
    startPolling() {
        console.log('🔄 Starting status polling for job:', this.currentJobId);
        if (this.pollingInterval) {
            clearInterval(this.pollingInterval);
        }
        
        this.pollingInterval = setInterval(async () => {
            await this.pollJobStatus();
        }, 1000); // Poll every second
        
        this.pollJobStatus(); // Poll immediately
    }
    
    stopPolling() {
        if (this.pollingInterval) {
            console.log('⏹️ Stopping status polling');
            clearInterval(this.pollingInterval);
            this.pollingInterval = null;
        }
    }
    
    async pollJobStatus() {
        if (!this.currentJobId || this.jobCompleted) {
            this.stopPolling();
            return;
        }
        
        try {
            const response = await fetch(`/job_status/${this.currentJobId}`);
            const jobData = await response.json();
            
            console.log('📊 Job status update:', jobData.status, (jobData.progress || 0) + '%');
            
            if (jobData.status === 'completed') {
                this.handleJobCompletion(jobData);
            } else if (jobData.status === 'failed') {
                this.handleJobFailure(jobData);
            } else {
                this.updateProgressModal(jobData);
            }
            
        } catch (error) {
            console.error('❌ Polling error:', error);
        }
    }
    
    showProgressModal() {
        const modal = new bootstrap.Modal(document.getElementById('progressModal'));
        modal.show();
        
        this.setupProgressModalButtons();
        this.updateProgressModal({
            progress: 0,
            current_step: 'Initializing...',
            current_book: '',
            status: 'starting'
        });
        
        const logDiv = document.getElementById('processing-log');
        if (logDiv) {
            logDiv.innerHTML = '<div class="log-entry"><span class="text-muted">[Starting]</span> BadaBoomBooks processing initialized</div>';
        }
    }
    
    setupProgressModalButtons() {
        const cancelBtn = document.getElementById('cancel-job-btn');
        const closeBtn = document.getElementById('close-progress-btn');
        const downloadLogBtn = document.getElementById('download-log-btn');
        
        if (cancelBtn) {
            cancelBtn.style.display = 'inline-block';
            cancelBtn.disabled = false;
        }
        
        if (closeBtn) {
            closeBtn.style.display = 'none';
            closeBtn.disabled = true;
        }
        
        if (downloadLogBtn) {
            downloadLogBtn.style.display = 'none';
            downloadLogBtn.disabled = true;
        }
    }
    
    updateProgressModal(data) {
        if (this.jobCompleted) return;
        
        const progressBar = document.getElementById('progress-bar');
        const progressPercentage = document.getElementById('progress-percentage');
        const progressText = document.getElementById('progress-text');
        const currentBookName = document.getElementById('current-book-name');
        const statusBadge = document.getElementById('status-badge');
        
        if (progressBar) {
            const progress = Math.max(0, Math.min(100, data.progress || 0));
            progressBar.style.width = `${progress}%`;
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
        
        if (statusBadge) {
            const status = data.status || 'unknown';
            statusBadge.textContent = status.replace('_', ' ').toUpperCase();
            statusBadge.className = `badge ${this.getStatusBadgeClass(status)}`;
        }
        
        // Add step to log
        if (data.current_step && data.current_step !== this.lastLoggedStep) {
            this.addLogEntry('info', data.current_step);
            this.lastLoggedStep = data.current_step;
        }
    }
    
    getStatusBadgeClass(status) {
        switch (status) {
            case 'completed': return 'bg-success';
            case 'failed': return 'bg-danger';
            case 'processing': return 'bg-primary';
            case 'building_queue': return 'bg-info';
            case 'initializing': return 'bg-secondary';
            default: return 'bg-secondary';
        }
    }
    
    addLogEntry(level, message, timestamp = null) {
        const logDiv = document.getElementById('processing-log');
        if (!logDiv) return;
        
        const time = timestamp || new Date().toLocaleTimeString();
        
        const logEntry = document.createElement('div');
        logEntry.className = 'log-entry';
        
        const levelIcon = {
            'info': '📘',
            'success': '✅',
            'warning': '⚠️',
            'error': '❌'
        }[level] || '📘';
        
        logEntry.innerHTML = `
            <span class="log-timestamp text-muted">[${time}]</span>
            <span class="log-icon">${levelIcon}</span>
            <span class="log-message">${message}</span>
        `;
        
        logDiv.appendChild(logEntry);
        logDiv.scrollTop = logDiv.scrollHeight;
        
        // Keep log size manageable
        while (logDiv.children.length > 100) {
            logDiv.removeChild(logDiv.firstChild);
        }
    }
    
    handleJobCompletion(data) {
        console.log('🎉 Job completed successfully:', data);
        
        this.jobCompleted = true;
        this.stopPolling();
        
        this.updateFinalProgressState(data, true);
        this.addLogEntry('success', 'Processing completed successfully!');
        
        if (data.results) {
            const { success = [], failed = [], skipped = [] } = data.results;
            
            if (success.length > 0) {
                this.addLogEntry('success', `✅ Successfully processed ${success.length} book(s)`);
            }
            
            if (skipped.length > 0) {
                this.addLogEntry('warning', `⊘ Skipped ${skipped.length} book(s)`);
            }
            
            if (failed.length > 0) {
                this.addLogEntry('warning', `⚠️ ${failed.length} book(s) had issues`);
            }
        }
        
        const totalTime = data.elapsed_time ? ` in ${Math.round(data.elapsed_time)}s` : '';
        this.showToast('Completed', `Processing completed${totalTime}!`, 'success');
    }
    
    handleJobFailure(data) {
        console.log('❌ Job failed:', data);
        
        this.jobCompleted = true;
        this.stopPolling();
        
        this.updateFinalProgressState(data, false);
        
        const errorMsg = data.error || 'Unknown error occurred';
        this.addLogEntry('error', `Processing failed: ${errorMsg}`);
        
        this.showToast('Failed', `Processing failed: ${errorMsg}`, 'danger');
    }
    
    updateFinalProgressState(data, success) {
        if (success) {
            const progressBar = document.getElementById('progress-bar');
            const progressPercentage = document.getElementById('progress-percentage');
            
            if (progressBar) progressBar.style.width = '100%';
            if (progressPercentage) progressPercentage.textContent = '100%';
        }
        
        const progressText = document.getElementById('progress-text');
        const statusBadge = document.getElementById('status-badge');
        
        if (progressText) {
            progressText.textContent = success ? 'Processing completed successfully!' : 'Processing failed';
        }
        
        if (statusBadge) {
            statusBadge.textContent = success ? 'COMPLETED' : 'FAILED';
            statusBadge.className = `badge ${success ? 'bg-success' : 'bg-danger'}`;
        }
        
        // Update buttons
        const cancelBtn = document.getElementById('cancel-job-btn');
        const closeBtn = document.getElementById('close-progress-btn');
        const downloadLogBtn = document.getElementById('download-log-btn');
        
        if (cancelBtn) {
            cancelBtn.style.display = 'none';
            cancelBtn.disabled = true;
        }
        
        if (closeBtn) {
            closeBtn.style.display = 'inline-block';
            closeBtn.disabled = false;
            closeBtn.focus();
        }
        
        if (downloadLogBtn) {
            downloadLogBtn.style.display = 'inline-block';
            downloadLogBtn.disabled = false;
        }
    }
    
    closeProgressModal() {
        this.jobCompleted = true;
        this.stopPolling();
        this.currentJobId = null;
        
        const modal = bootstrap.Modal.getInstance(document.getElementById('progressModal'));
        if (modal) {
            modal.hide();
        }
    }
    
    downloadProcessingLog() {
        const logDiv = document.getElementById('processing-log');
        if (!logDiv) return;
        
        const logEntries = Array.from(logDiv.children).map(entry => {
            return entry.textContent.trim();
        });
        
        const logContent = [
            '# BadaBoomBooks Processing Log',
            `# Generated: ${new Date().toISOString()}`,
            `# Job ID: ${this.currentJobId || 'unknown'}`,
            '',
            ...logEntries
        ].join('\n');
        
        const blob = new Blob([logContent], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        
        const a = document.createElement('a');
        a.href = url;
        a.download = `badaboombooks-log-${new Date().toISOString().slice(0, 19)}.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        
        URL.revokeObjectURL(url);
    }
    
    refreshBrowser() {
        const currentPath = this.currentPath || 'drives';
        this.browseDirectory(currentPath);
    }
    
    showToast(title, message, type = 'info', duration = 5000) {
        const alertClass = {
            'danger': 'alert-danger',
            'warning': 'alert-warning',
            'success': 'alert-success',
            'info': 'alert-info'
        }[type] || 'alert-info';
        
        const alertId = 'alert-' + Date.now();
        
        const alertHtml = `
            <div id="${alertId}" class="alert ${alertClass} alert-dismissible fade show position-fixed" 
                 style="top: 20px; right: 20px; z-index: 9999; min-width: 300px; max-width: 500px;">
                <strong>${title}:</strong> ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', alertHtml);
        
        setTimeout(() => {
            const alert = document.getElementById(alertId);
            if (alert && alert.parentNode) {
                alert.remove();
            }
        }, duration);
    }
}

// Global functions for template access
let app;

function showSection(sectionId) {
    console.log('📄 Switching to section:', sectionId);
    
    document.querySelectorAll('.content-section').forEach(section => {
        section.style.display = 'none';
    });
    
    const targetSection = document.getElementById(sectionId);
    if (targetSection) {
        targetSection.style.display = 'block';
    }
    
    document.querySelectorAll('.nav-link').forEach(link => {
        link.classList.remove('active');
    });
    
    document.querySelectorAll(`[onclick*="${sectionId}"]`).forEach(link => {
        link.classList.add('active');
    });
    
    window.location.hash = sectionId;
    
    if (sectionId === 'browser' && app) {
        app.refreshBrowser();
    }
}

// Global event handlers
function refreshBrowser() { if (app) app.refreshBrowser(); }
function goUp() { if (app) app.browseDirectory('drives'); }
function startProcessing() { if (app) app.startProcessing(); }
function previewChanges() { 
    if (app) {
        const dryRunCheckbox = document.getElementById('dry-run');
        if (dryRunCheckbox) dryRunCheckbox.checked = true;
        app.startProcessing(); 
    }
}
function showDrives() { if (app) app.browseDirectory('drives'); }
function closeProgressModal() { if (app) app.closeProgressModal(); }
function cancelJob() { if (app) app.closeProgressModal(); }
function downloadLog() { if (app) app.downloadProcessingLog(); }

function handlePathInput(event) {
    if (event.key === 'Enter' && app) {
        const path = event.target.value.trim();
        if (path) app.browseDirectory(path);
    }
}

// Initialize application
document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 Initializing BadaBoomBooks Web Interface');
    
    app = new BadaBoomBooksWebApp();
    
    function handleHashChange() {
        const hash = window.location.hash.substring(1);
        const validSections = ['dashboard', 'browser', 'options'];
        const section = validSections.includes(hash) ? hash : 'dashboard';
        showSection(section);
    }
    
    window.addEventListener('hashchange', handleHashChange);
    handleHashChange();
    
    console.log('✅ BadaBoomBooks Web Interface ready');
});