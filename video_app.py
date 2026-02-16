import streamlit as st
import os
import pandas as pd
import ffmpeg
import json
import tempfile
import shutil
import time
from io import BytesIO

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
        st.markdown("Upload video files directly from your computer.")
        
        # Processing method selection
        st.markdown("---")
        processing_method = st.radio(
            "⚙️ Select Analysis Method:",
            ("Standard Upload (Server-side)", "Quick Check (Client-side - EXPERIMENTAL)"),
            help="Standard: Full upload + ffprobe analysis. Quick Check: Browser reads metadata only (no upload, much faster)."
        )
        
        if processing_method == "Quick Check (Client-side - EXPERIMENTAL)":
            st.info("🚀 Quick Check analyzes videos in your browser without uploading them. Perfect for 10+ files!")
            
            # Custom HTML component for mp4box.js
            html_code = """
            <!DOCTYPE html>
            <html>
            <head>
                <script src="https://cdn.jsdelivr.net/npm/mp4box@0.5.2/dist/mp4box.all.min.js"></script>
                <style>
                    body { font-family: sans-serif; padding: 20px; }
                    #fileInput { margin: 10px 0; }
                    #analyzeBtn { 
                        background: #FF4B4B; 
                        color: white; 
                        padding: 10px 20px; 
                        border: none; 
                        border-radius: 5px; 
                        cursor: pointer; 
                        font-size: 16px;
                    }
                    #analyzeBtn:hover { background: #FF6B6B; }
                    #status { margin: 10px 0; color: #0066cc; }
                    #results { margin: 20px 0; }
                </style>
            </head>
            <body>
                <input type="file" id="fileInput" multiple accept="video/*">
                <button id="analyzeBtn">Analyze Videos</button>
                <div id="status"></div>
                <div id="results"></div>
                
                <script>
                    const fileInput = document.getElementById('fileInput');
                    const analyzeBtn = document.getElementById('analyzeBtn');
                    const status = document.getElementById('status');
                    const results = document.getElementById('results');
                    
                    analyzeBtn.addEventListener('click', async () => {
                        const files = fileInput.files;
                        if (files.length === 0) {
                            alert('Please select video files first');
                            return;
                        }
                        
                        status.textContent = `Analyzing ${files.length} files...`;
                        const metadata = [];
                        
                        for (let i = 0; i < files.length; i++) {
                            const file = files[i];
                            status.textContent = `Processing ${i + 1}/${files.length}: ${file.name}`;
                            
                            try {
                                const data = await analyzeFile(file);
                                metadata.push(data);
                            } catch (error) {
                                metadata.push({
                                    fileName: file.name,
                                    format: 'error',
                                    videoCodec: 'error',
                                    audioCodec: error.message,
                                    size: file.size
                                });
                            }
                        }
                        
                        // Send results back to Streamlit
                        status.textContent = 'Analysis complete! Sending results...';
                        window.parent.postMessage({
                            type: 'streamlit:setComponentValue',
                            value: metadata
                        }, '*');
                    });
                    
                    async function analyzeFile(file) {
                        return new Promise((resolve, reject) => {
                            const reader = new FileReader();
                            const chunkSize = 1024 * 1024; // Read first 1MB
                            
                            reader.onload = (e) => {
                                try {
                                    const mp4boxfile = MP4Box.createFile();
                                    let format = 'unknown';
                                    let videoCodec = 'unknown';
                                    let audioCodec = 'none';
                                    
                                    mp4boxfile.onError = (e) => {
                                        // Check file extension for non-MP4/MOV files
                                        const ext = file.name.split('.').pop().toLowerCase();
                                        if (['mp4', 'mov', 'm4v'].includes(ext)) {
                                            reject(new Error('Parse error'));
                                        } else {
                                            resolve({
                                                fileName: file.name,
                                                format: ext,
                                                videoCodec: 'N/A',
                                                audioCodec: 'N/A',
                                                size: file.size
                                            });
                                        }
                                    };
                                    
                                    mp4boxfile.onReady = (info) => {
                                        // Detect format
                                        format = info.brand || 'mp4';
                                        if (format.includes('qt')) format = 'mov';
                                        else if (format.includes('mp4') || format.includes('isom')) format = 'mp4';
                                        
                                        // Extract video codec
                                        const videoTrack = info.videoTracks[0];
                                        if (videoTrack) {
                                            const codec = videoTrack.codec;
                                            if (codec.includes('avc') || codec.includes('h264')) videoCodec = 'h264';
                                            else if (codec.includes('hvc') || codec.includes('hev') || codec.includes('h265')) videoCodec = 'hevc';
                                            else videoCodec = codec;
                                        }
                                        
                                        // Extract audio codec
                                        const audioTrack = info.audioTracks[0];
                                        if (audioTrack) {
                                            const codec = audioTrack.codec;
                                            if (codec.includes('mp4a')) audioCodec = 'aac';
                                            else audioCodec = codec;
                                        }
                                        
                                        resolve({
                                            fileName: file.name,
                                            format: format,
                                            videoCodec: videoCodec,
                                            audioCodec: audioCodec,
                                            size: file.size
                                        });
                                    };
                                    
                                    const buffer = e.target.result;
                                    buffer.fileStart = 0;
                                    mp4boxfile.appendBuffer(buffer);
                                    mp4boxfile.flush();
                                    
                                } catch (error) {
                                    reject(error);
                                }
                            };
                            
                            reader.onerror = () => reject(new Error('File read error'));
                            reader.readAsArrayBuffer(file.slice(0, chunkSize));
                        });
                    }
                </script>
            </body>
            </html>
            """
            
            # Display the component
            component_value = st.components.v1.html(html_code, height=200, scrolling=False)
            
            # Process results from JavaScript
            if component_value and isinstance(component_value, list):
                st.success("✅ Metadata received from browser!")
                
                # Valid Formats and Codecs
                valid_formats = ['mp4', 'mov']
                valid_codecs = ['h264', 'avc', 'hevc', 'h265', 'mpeg1video', 'mpeg2video', 'mpeg1', 'mpeg2']
                
                results = []
                for item in component_value:
                    file_name = item['fileName']
                    fmt = item['format']
                    v_codec = item['videoCodec']
                    a_codec = item['audioCodec']
                    file_size_bytes = item['size']
                    file_size_mb = file_size_bytes / (1024 * 1024)
                    
                    # Validation
                    format_flag = "good to go" if fmt.lower() in valid_formats else "error"
                    codec_flag = "good to go" if v_codec.lower() in valid_codecs else "error"
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
                    file_name="video_metadata_quick_report.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        
        else:
            # Standard upload method
            st.info("📤 Standard method: Full upload + server-side ffprobe analysis (most accurate)")
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
