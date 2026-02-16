import streamlit as st
import os
import pandas as pd
import ffmpeg
import json
import tempfile
import shutil
import time
from io import BytesIO
import streamlit.components.v1 as components

def get_video_metadata(file_path):
    """
    Extracts video format and codec information using ffprobe.
    """
    try:
        # Run ffprobe to get metadata in JSON format
        probe = ffmpeg.probe(file_path)
        
        format_info = probe.get('format', {})
        streams = probe.get('streams', [])
        
        container_format = format_info.get('format_name', 'Unknown')
        
        # Clean up container format (e.g., "mov,mp4,m4a..." -> "mp4")
        if ',' in container_format:
            formats = container_format.split(',')
            # Try to find the format that matches the file extension
            ext = file_path.split('.')[-1].lower() if '.' in file_path else ''
            if ext in formats:
                container_format = ext
            else:
                container_format = formats[0] # Fallback to the first one
        
        # Extract codecs
        video_codec = 'Unknown'
        audio_codec = 'None'
        
        video_streams = [s for s in streams if s['codec_type'] == 'video']
        if video_streams:
            video_codec = video_streams[0].get('codec_name', 'Unknown')
            
        audio_streams = [s for s in streams if s['codec_type'] == 'audio']
        if audio_streams:
            audio_codec = audio_streams[0].get('codec_name', 'Unknown')
            
        return container_format, video_codec, audio_codec
    except ffmpeg.Error as e:
        return "Error", "Error", f"FFmpeg Error: {e.stderr.decode('utf8') if e.stderr else 'Unknown'}"
    except Exception as e:
        return "Error", "Error", f"Exception: {str(e)}"

def analyze_videos(file_list, original_names=None):
    """
    Analyzes a list of video files and returns a DataFrame.
    file_list: List of absolute file paths to process.
    original_names: List of display names corresponding to file_list (optional).
    """
    results = []
    progress_bar = st.progress(0)
    
    # Valid Formats and Codecs
    valid_formats = ['mp4', 'mov']
    valid_codecs = ['h264', 'avc', 'hevc', 'h265', 'mpeg1video', 'mpeg2video', 'mpeg1', 'mpeg2']
    
    total_files = len(file_list)

    for i, file_path in enumerate(file_list):
        # Use provided display name if available, else basename
        if original_names:
            file_name = original_names[i]
        else:
            file_name = os.path.basename(file_path)
            
        fmt, v_codec, a_codec = get_video_metadata(file_path)
        
        # Logic for Video Format Flag
        format_flag = "good to go" if fmt.lower() in valid_formats else "error"
        
        # Logic for Video Codecs Flag
        codec_flag = "good to go" if v_codec.lower() in valid_codecs else "error"

        # Logic for File Size
        file_size_bytes = os.path.getsize(file_path)
        file_size_mb = file_size_bytes / (1024 * 1024)
        size_flag = "good to go" if file_size_mb <= 200 else "error"

        results.append({
            "File Name": file_name,
            "Video Format": fmt,
            "Video Format Flag": format_flag,
            "Video Codecs": f"Video: {v_codec}, Audio: {a_codec}", 
            "Video Codecs Flag": codec_flag,
            "File Size": f"{file_size_mb:.2f} MB",
            "File Size Flag": size_flag
        })
        progress_bar.progress((i + 1) / total_files)
    
    return pd.DataFrame(results)

def main():
    st.set_page_config(page_title="Video Metadata Extractor", layout="wide")
    
    st.title("🎥 Video Metadata Extractor")
    st.markdown("Analyze video files to extract format, codec details, and check file size.")

    # Sidebar for Input Method
    input_method = st.sidebar.radio("Select Input Method:", ("Folder Path (Local)", "Upload Files"))

    if input_method == "Folder Path (Local)":
        st.subheader("📂 Local Folder Analysis")
        # Instructions for users
        st.info(
            r"""
            **How to use:**
            1. Navigate to the folder containing your videos.
            2. Copy the folder path address.
               - **Windows:** Right-click the address bar in File Explorer and select "Copy address".
               - **Mac:** Right-click the folder, hold `Option` key, and select "Copy ... as Pathname".
               - Remove the video name from the directory in case there is any.
               ex. Mac: /Users/nik/Documents/DocProject/videoformat/videos
               ex. Windows: C:\Users\nik\Documents\DocProject\videoformat\videos
            3. Paste the path below.
            """
        )

        folder_path_input = st.text_input("Enter Video Folder Path:", "")
        folder_path = folder_path_input.strip('"').strip("'").strip()

        if folder_path:
            if os.path.exists(folder_path) and os.path.isdir(folder_path):
                if st.button("Analyze Videos"):
                    video_extensions = ('.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv', '.webm', '.m4v')
                    files = [f for f in os.listdir(folder_path) if f.lower().endswith(video_extensions)]
                    
                    if not files:
                        st.warning("No video files found in this directory.")
                    else:
                        st.info(f"Found {len(files)} video files. Processing...")
                        file_paths = [os.path.join(folder_path, f) for f in files]
                        
                        df = analyze_videos(file_paths)
                        
                        st.success("Analysis Complete!")
                        st.dataframe(df, width="stretch")
                        
                        # Excel Export logic moved to reuse
                        output = BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            df.to_excel(writer, index=False, sheet_name='Video Metadata')
                        processed_data = output.getvalue()
                        
                        st.download_button(
                            label="📥 Download Excel Report",
                            data=processed_data,
                            file_name="video_metadata_report.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )

            else:
                import platform
                system_os = platform.system()
                if system_os != "Windows" and (":\\" in folder_path or ":/" in folder_path):
                    st.error(f"Invalid path. You seem to be using a Windows path (`{folder_path}`) but this application is running on {system_os}. Please use a valid path for this computer.")
                elif system_os == "Windows" and folder_path.startswith("/"):
                    st.error(f"Invalid path. You seem to be using a Unix/Mac path (`{folder_path}`) but this application is running on Windows. Please use a valid Windows path.")
                else:
                    st.error(f"Invalid folder path: `{folder_path}`. Please verify the folder exists and is accessible.")

    elif input_method == "Upload Files":
        st.subheader("📤 File Upload Analysis")
        st.markdown("**🚀 New: Browser-based analysis** - No upload needed! Analyze 50+ videos instantly.")
        
        # Tab selection for analysis method
        analysis_tab = st.radio(
            "Select Analysis Method:",
            ("🚀 Browser Analysis (Recommended - Fast, No Upload)", "📤 Upload Analysis (Legacy - Slow)"),
            help="Browser Analysis: Extracts metadata locally, works with 50+ files. Upload Analysis: Traditional method, may timeout with many files."
        )
        
        if analysis_tab == "🚀 Browser Analysis (Recommended - Fast, No Upload)":
            st.info("💡 **How it works:** Your browser reads video metadata locally (no upload!). Only metadata is sent to server.")
            
            # HTML component with mp4box.js for client-side analysis
            html_component = """
            <!DOCTYPE html>
            <html>
            <head>
                <script src="https://cdn.jsdelivr.net/npm/mp4box@0.5.2/dist/mp4box.all.min.js"></script>
                <style>
                    body { font-family: sans-serif; padding: 20px; }
                    .upload-box { border: 2px dashed #ccc; padding: 40px; text-align: center; margin: 20px 0; border-radius: 10px; }
                    .upload-box:hover { border-color: #4CAF50; background: #f9f9f9; }
                    #fileInput { margin: 20px 0; }
                    .progress { margin: 10px 0; }
                    .result { background: #e8f5e9; padding: 10px; margin: 5px 0; border-radius: 5px; }
                    button { background: #4CAF50; color: white; border: none; padding: 12px 24px; font-size: 16px; border-radius: 5px; cursor: pointer; }
                    button:hover { background: #45a049; }
                    button:disabled { background: #ccc; cursor: not-allowed; }
                </style>
            </head>
            <body>
                <div class="upload-box">
                    <h3>📂 Select Video Files</h3>
                    <input type="file" id="fileInput" multiple accept="video/*" style="display:none">
                    <button onclick="document.getElementById('fileInput').click()">Choose Videos</button>
                    <p id="fileCount" style="margin-top: 10px; color: #666;"></p>
                </div>
                <button id="analyzeBtn" onclick="analyzeVideos()" disabled>Analyze Videos</button>
                <div id="progress"></div>
                <div id="results"></div>

                <script>
                    let selectedFiles = [];
                    
                    document.getElementById('fileInput').addEventListener('change', function(e) {
                        selectedFiles = Array.from(e.target.files);
                        document.getElementById('fileCount').textContent = 
                            selectedFiles.length > 0 ? `${selectedFiles.length} file(s) selected` : '';
                        document.getElementById('analyzeBtn').disabled = selectedFiles.length === 0;
                    });

                    async function getVideoInfo(file) {
                        return new Promise((resolve) => {
                            // Basic file info (always available)
                            const basicInfo = {
                                fileName: file.name,
                                fileSize: file.size,
                                fileSizeMB: (file.size / (1024 * 1024)).toFixed(2)
                            };

                            // Try to extract format from extension
                            const ext = file.name.split('.').pop().toLowerCase();
                            basicInfo.format = ext;

                            // For MP4/MOV, try to extract codec info using mp4box.js
                            if (ext === 'mp4' || ext === 'mov' || ext === 'm4v') {
                                try {
                                    const reader = new FileReader();
                                    // Read only first 2MB for metadata
                                    const blob = file.slice(0, 2 * 1024 * 1024);
                                    
                                    reader.onload = function(e) {
                                        try {
                                            const arrayBuffer = e.target.result;
                                            arrayBuffer.fileStart = 0;
                                            
                                            const mp4boxfile = MP4Box.createFile();
                                            mp4boxfile.onReady = function(info) {
                                                let videoCodec = 'Unknown';
                                                let audioCodec = 'None';
                                                
                                                if (info.videoTracks && info.videoTracks.length > 0) {
                                                    const vTrack = info.videoTracks[0];
                                                    videoCodec = vTrack.codec || 'Unknown';
                                                }
                                                
                                                if (info.audioTracks && info.audioTracks.length > 0) {
                                                    const aTrack = info.audioTracks[0];
                                                    audioCodec = aTrack.codec || 'Unknown';
                                                }
                                                
                                                resolve({
                                                    ...basicInfo,
                                                    videoCodec: videoCodec.toLowerCase(),
                                                    audioCodec: audioCodec.toLowerCase()
                                                });
                                            };
                                            
                                            mp4boxfile.onError = function(e) {
                                                // Fallback to basic info if mp4box fails
                                                resolve({
                                                    ...basicInfo,
                                                    videoCodec: 'unknown',
                                                    audioCodec: 'unknown'
                                                });
                                            };
                                            
                                            mp4boxfile.appendBuffer(arrayBuffer);
                                            mp4boxfile.flush();
                                        } catch (err) {
                                            resolve({
                                                ...basicInfo,
                                                videoCodec: 'unknown',
                                                audioCodec: 'unknown'
                                            });
                                        }
                                    };
                                    
                                    reader.onerror = function() {
                                        resolve({
                                            ...basicInfo,
                                            videoCodec: 'unknown',
                                            audioCodec: 'unknown'
                                        });
                                    };
                                    
                                    reader.readAsArrayBuffer(blob);
                                } catch (err) {
                                    resolve({
                                        ...basicInfo,
                                        videoCodec: 'unknown',
                                        audioCodec: 'unknown'
                                    });
                                }
                            } else {
                                // For non-MP4/MOV files, return basic info
                                resolve({
                                    ...basicInfo,
                                    videoCodec: 'unknown',
                                    audioCodec: 'unknown'
                                });
                            }
                        });
                    }

                    async function analyzeVideos() {
                        const progressDiv = document.getElementById('progress');
                        const resultsDiv = document.getElementById('results');
                        const analyzeBtn = document.getElementById('analyzeBtn');
                        
                        analyzeBtn.disabled = true;
                        resultsDiv.innerHTML = '';
                        progressDiv.innerHTML = '<p>🔄 Analyzing videos...</p>';
                        
                        const results = [];
                        
                        for (let i = 0; i < selectedFiles.length; i++) {
                            const file = selectedFiles[i];
                            progressDiv.innerHTML = `<p>🔄 Processing ${i + 1} of ${selectedFiles.length}: ${file.name}</p>`;
                            
                            const info = await getVideoInfo(file);
                            results.push(info);
                        }
                        
                        progressDiv.innerHTML = '<p>✅ Analysis complete! Sending results...</p>';
                        
                        // Send results to Streamlit
                        window.parent.postMessage({
                            type: 'streamlit:setComponentValue',
                            value: JSON.stringify(results)
                        }, '*');
                        
                        resultsDiv.innerHTML = `<div class="result">✅ Successfully analyzed ${results.length} files. Results sent to server for validation.</div>`;
                        analyzeBtn.disabled = false;
                    }
                </script>
            </body>
            </html>
            """
            
            # Render the component
            metadata_json = components.html(html_component, height=400, scrolling=True)
            
            # Process results when received from JavaScript
            if metadata_json:
                try:
                    metadata_list = json.loads(metadata_json)
                    st.success(f"✅ Received metadata for {len(metadata_list)} files!")
                    
                    # Valid Formats and Codecs
                    valid_formats = ['mp4', 'mov', 'm4v']
                    valid_codecs = ['h264', 'avc', 'avc1', 'hevc', 'hvc1', 'h265', 'mpeg1video', 'mpeg2video', 'mpeg1', 'mpeg2', 'mp4v']
                    
                    results = []
                    for meta in metadata_list:
                        fmt = meta.get('format', 'unknown')
                        v_codec = meta.get('videoCodec', 'unknown')
                        a_codec = meta.get('audioCodec', 'none')
                        file_size_mb = float(meta.get('fileSizeMB', 0))
                        
                        # Validation logic
                        format_flag = "good to go" if fmt.lower() in valid_formats else "error"
                        codec_flag = "good to go" if any(vc in v_codec.lower() for vc in valid_codecs) else "error"
                        size_flag = "good to go" if file_size_mb <= 200 else "error"
                        
                        results.append({
                            "File Name": meta.get('fileName', 'unknown'),
                            "Video Format": fmt,
                            "Video Format Flag": format_flag,
                            "Video Codecs": f"Video: {v_codec}, Audio: {a_codec}",
                            "Video Codecs Flag": codec_flag,
                            "File Size": f"{file_size_mb} MB",
                            "File Size Flag": size_flag
                        })
                    
                    df = pd.DataFrame(results)
                    st.dataframe(df, width="stretch")
                    
                    # Excel Export
                    output = BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        df.to_excel(writer, index=False, sheet_name='Video Metadata')
                    processed_data = output.getvalue()
                    
                    st.download_button(
                        label="📥 Download Excel Report",
                        data=processed_data,
                        file_name="video_metadata_browser_analysis.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                except Exception as e:
                    st.error(f"Error processing metadata: {str(e)}")
        
        else:  # Legacy upload method
            st.warning("⚠️ This method may timeout with 10+ large files. Consider using Browser Analysis instead.")
            
            uploaded_files = st.file_uploader("Choose video files", accept_multiple_files=True, type=['mp4', 'mov', 'avi', 'mkv', 'flv', 'wmv', 'webm', 'm4v'])

            if uploaded_files:
                st.success(f"✅ {len(uploaded_files)} file(s) uploaded successfully!")
                
                if st.button("Analyze Uploaded Videos"):
                    start_time = time.time()
                    st.info(f"Processing {len(uploaded_files)} files...")
                    
                    # SEQUENTIAL PROCESSING (Safe for large files)
                    results = []
                    progress_placeholder = st.empty()
                    status_placeholder = st.empty()
                    
                    # Valid Formats and Codecs
                    valid_formats = ['mp4', 'mov']
                    valid_codecs = ['h264', 'avc', 'hevc', 'h265', 'mpeg1video', 'mpeg2video', 'mpeg1', 'mpeg2']
                    
                    for idx, uploaded_file in enumerate(uploaded_files):
                        # Update progress
                        progress_placeholder.progress((idx) / len(uploaded_files))
                        status_placeholder.info(f"🔄 Processing file {idx + 1} of {len(uploaded_files)}: {uploaded_file.name}")
                        
                        # Process ONE file at a time
                        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[1]) as tmp:
                            # Save to disk
                            shutil.copyfileobj(uploaded_file, tmp)
                            tmp_path = tmp.name
                        
                        try:
                            # Analyze this file
                            fmt, v_codec, a_codec = get_video_metadata(tmp_path)
                            
                            # Validation
                            format_flag = "good to go" if fmt.lower() in valid_formats else "error"
                            codec_flag = "good to go" if v_codec.lower() in valid_codecs else "error"
                            
                            file_size_bytes = os.path.getsize(tmp_path)
                            file_size_mb = file_size_bytes / (1024 * 1024)
                            size_flag = "good to go" if file_size_mb <= 200 else "error"
                            
                            results.append({
                                "File Name": uploaded_file.name,
                                "Video Format": fmt,
                                "Video Format Flag": format_flag,
                                "Video Codecs": f"Video: {v_codec}, Audio: {a_codec}",
                                "Video Codecs Flag": codec_flag,
                                "File Size": f"{file_size_mb:.2f} MB",
                                "File Size Flag": size_flag
                            })
                        finally:
                            # Delete immediately after processing
                            if os.path.exists(tmp_path):
                                os.remove(tmp_path)
                    
                    # Complete progress
                    progress_placeholder.progress(1.0)
                    status_placeholder.empty()
                    
                    end_time = time.time()
                    elapsed_time = end_time - start_time
                    
                    df = pd.DataFrame(results)
                    st.success(f"✅ Analysis Complete! Time taken: {elapsed_time:.2f} seconds")
                    st.dataframe(df, width="stretch")
                    
                    # Excel Export
                    output = BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        df.to_excel(writer, index=False, sheet_name='Video Metadata')
                    processed_data = output.getvalue()
                    
                    st.download_button(
                        label="📥 Download Excel Report",
                        data=processed_data,
                        file_name="video_metadata_upload_report.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

if __name__ == "__main__":
    main()
