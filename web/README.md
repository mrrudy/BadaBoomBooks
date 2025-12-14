# BadaBoomBooks Web Interface

A modern, intuitive web-based interface for the BadaBoomBooks audiobook organization tool. Provides a user-friendly alternative to the command-line interface with real-time progress monitoring, interactive candidate selection, and comprehensive file management.

## 🌟 Features

### 📁 **Interactive File Browser**
- Navigate your filesystem with ease
- Visual identification of audiobook folders
- Multi-selection with checkbox interface
- Real-time folder information and audio file counts

### ⚙️ **Comprehensive Processing Options**
- All CLI options available through intuitive forms
- Quick presets for common workflows
- Real-time processing summary
- Advanced options for power users

### 🔄 **Real-Time Progress Monitoring**
- Live progress bars and status updates
- Detailed processing logs
- WebSocket-based real-time communication
- Job management and cancellation

### 🎯 **Interactive Candidate Selection**
- Visual metadata candidate comparison
- Rich book context display
- One-click selection or skip options
- Side-by-side candidate information

### 📊 **Modern UI/UX**
- Responsive Bootstrap 5 design
- Dark mode support
- Mobile-friendly interface
- Smooth animations and transitions

## 🚀 Quick Start

### 1. Install Dependencies
```bash
# From the main BadaBoomBooks directory
cd web
pip install -r requirements.txt
```

### 2. Start the Web Interface
```bash
# Simple start
python start_web.py

# Or run directly
python app.py
```

### 3. Access the Interface
Open your browser and navigate to:
- **Local access**: http://localhost:5000
- **Network access**: http://your-ip:5000

## 📋 Prerequisites

### Required Python Packages
- **Flask** 2.3.3+ - Web framework
- **Flask-SocketIO** 5.3.6+ - Real-time communication
- **All existing BadaBoomBooks dependencies**

### Browser Compatibility
- **Chrome/Chromium** 90+ (recommended)
- **Firefox** 88+
- **Safari** 14+
- **Edge** 90+

## 🎯 Usage Guide

### 1. **Browse and Select Folders**
1. Navigate to the **Browse Files** section
2. Use the file browser to find your audiobook folders
3. Click checkboxes to select audiobook folders (🎧 icon)
4. Selected folders appear in the sidebar

### 2. **Configure Processing Options**
1. Go to **Processing Options**
2. Configure search, organization, and metadata options
3. Use quick presets for common workflows:
   - **Basic Organization**: Essential processing
   - **Complete Processing**: All features enabled
   - **Metadata Only**: Just metadata updates
   - **Preview Mode**: Dry run for testing

### 3. **Start Processing**
1. Click **Start Processing** to begin
2. Monitor progress in real-time
3. Make candidate selections when prompted
4. View detailed logs and results

### 4. **Interactive Candidate Selection**
When auto-search finds multiple candidates:
1. Review book context information
2. Compare candidate details
3. Click **Select** on the best match
4. Or click **Skip This Book** to skip

## 🎨 Interface Sections

### 📊 **Dashboard**
- Welcome screen with feature overview
- Quick stats and navigation
- Feature highlights and benefits

### 📁 **Browse Files**
- Interactive filesystem navigation
- Audiobook folder identification
- Multi-selection interface
- Selected folders management

### ⚙️ **Processing Options**
- Comprehensive option configuration
- Real-time processing summary
- Quick preset applications
- Advanced settings access

### 📈 **Active Jobs**
- Real-time job monitoring
- Progress tracking
- Log viewing
- Job management

## 🔧 Advanced Configuration

### Custom Port and Host
Edit `app.py` to change default settings:
```python
# Change port from 5000
socketio.run(app, host='0.0.0.0', port=8080, debug=True)

# Local access only
socketio.run(app, host='127.0.0.1', port=5000, debug=True)
```

### Debug Mode
Enable Flask debug mode for development:
```python
socketio.run(app, host='0.0.0.0', port=5000, debug=True)
```

### Production Deployment
For production use, consider:
- Using a proper WSGI server (Gunicorn, uWSGI)
- Setting up reverse proxy (Nginx, Apache)
- Enabling HTTPS
- Configuring firewall rules

## 🔐 Security Considerations

### File System Access
- The web interface has access to your entire filesystem
- Only run on trusted networks
- Consider restricting host binding for security

### Network Access
- Default configuration allows network access (0.0.0.0)
- Change to 127.0.0.1 for local-only access
- Use firewall rules to restrict access

### Authentication
- No built-in authentication (single-user tool)
- Consider adding authentication for multi-user environments
- Use VPN or SSH tunneling for remote access

## 🐛 Troubleshooting

### Common Issues

#### **Port Already in Use**
```bash
# Error: Address already in use
# Solution: Change port in app.py or kill existing process
lsof -ti:5000 | xargs kill -9
```

#### **Module Import Errors**
```bash
# Error: No module named 'flask'
# Solution: Install requirements
pip install -r requirements.txt
```

#### **File Browser Not Working**
- Check filesystem permissions
- Ensure Python has read access to directories
- Try starting with administrator/sudo privileges

#### **WebSocket Connection Issues**
- Check browser console for errors
- Ensure no firewall blocking WebSocket connections
- Try disabling browser extensions

### Debug Mode
Enable debug logging by editing `app.py`:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 🔄 Integration with CLI

The web interface is fully compatible with the CLI version:
- Uses the same configuration files
- Shares queue.ini for job state
- Maintains same output structure
- Can be used alongside CLI tools

## 🎯 Workflow Examples

### Basic Audiobook Organization
1. **Browse** → Select audiobook folders
2. **Processing** → Enable "Basic Organization" preset
3. **Start** → Monitor progress and select candidates
4. **Complete** → Review organized collection

### Complete Processing Workflow
1. **Browse** → Select entire audiobook collection
2. **Processing** → Enable "Complete Processing" preset
3. **Configure** → Set output directory and options
4. **Process** → Full automation with metadata enhancement
5. **Verify** → Check results and logs

### Preview Changes
1. **Browse** → Select test folders
2. **Processing** → Enable "Preview Mode" preset
3. **Review** → See what would happen without changes
4. **Adjust** → Modify options based on preview
5. **Execute** → Run actual processing

## 📈 Performance Tips

### Large Collections
- Process in smaller batches for better responsiveness
- Use series organization for efficient structure
- Monitor memory usage during large jobs

### Network Performance
- Use local access when possible
- Consider bandwidth for remote access
- Enable browser caching for better performance

### Browser Optimization
- Use Chrome/Chromium for best performance
- Close unnecessary tabs during processing
- Enable hardware acceleration if available

## 🆘 Support

### Getting Help
1. Check this README for common solutions
2. Review browser console for error messages
3. Check Flask/Python logs for server errors
4. Create issues with detailed error information

### Reporting Bugs
Include in bug reports:
- Operating system and version
- Python version
- Browser and version
- Full error messages
- Steps to reproduce

---

**The web interface provides a modern, user-friendly way to harness the full power of BadaBoomBooks with intuitive controls, real-time feedback, and comprehensive audiobook management capabilities!** 🎉
