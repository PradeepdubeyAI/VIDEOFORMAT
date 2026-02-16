import os
import json
import base64
import shutil
import tempfile
import time
from io import BytesIO

import ffmpeg
import pandas as pd
import streamlit as st


def get_video_metadata(file_path: str):
    """Extract container and codec information using ffprobe."""
    try:
        probe = ffmpeg.probe(file_path)
        format_info = probe.get("format", {})
        streams = probe.get("streams", [])

        container_format = format_info.get("format_name", "Unknown")
        if "," in container_format:
            formats = container_format.split(",")
            ext = file_path.split(".")[-1].lower() if "." in file_path else ""
            container_format = ext if ext in formats else formats[0]

        video_codec = "Unknown"
        audio_codec = "None"

        video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
        if video_streams:
            video_codec = video_streams[0].get("codec_name", "Unknown")

        audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
        if audio_streams:
            audio_codec = audio_streams[0].get("codec_name", "Unknown")

        return container_format, video_codec, audio_codec
    except ffmpeg.Error as exc:
        message = exc.stderr.decode("utf8") if exc.stderr else "Unknown"
        return "Error", "Error", f"FFmpeg Error: {message}"
    except Exception as exc:  # pylint: disable=broad-except
        return "Error", "Error", f"Exception: {exc}"


def analyze_videos(file_list, original_names=None):
    """Run ffprobe sequentially for each video and return a DataFrame."""
    results = []
    progress_bar = st.progress(0)

    valid_formats = ["mp4", "mov"]
    valid_codecs = [
        "h264",
        "avc",
        "hevc",
        "h265",
        "mpeg1video",
        "mpeg2video",
        "mpeg1",
        "mpeg2",
    ]

    total_files = len(file_list)

    for index, file_path in enumerate(file_list):
        file_name = original_names[index] if original_names else os.path.basename(file_path)

        fmt, v_codec, a_codec = get_video_metadata(file_path)

        format_flag = "good to go" if fmt.lower() in valid_formats else "error"
        codec_flag = "good to go" if v_codec.lower() in valid_codecs else "error"

        file_size_bytes = os.path.getsize(file_path)
        file_size_mb = file_size_bytes / (1024 * 1024)
        size_flag = "good to go" if file_size_mb <= 200 else "error"

        results.append(
            {
                "File Name": file_name,
                "Video Format": fmt,
                "Video Format Flag": format_flag,
                "Video Codecs": f"Video: {v_codec}, Audio: {a_codec}",
                "Video Codecs Flag": codec_flag,
                "File Size": f"{file_size_mb:.2f} MB",
                "File Size Flag": size_flag,
            }
        )
        progress_bar.progress((index + 1) / total_files)

    return pd.DataFrame(results)


def render_quick_check():
    """Handle the Quick Check (client-side) workflow."""
    st.info("🚀 Quick Check: Files analyzed in your browser without uploading. Works with MP4/MOV files.")

    st.write("🔍 **Debug Info:**")
    query_params = dict(st.query_params)
    st.write(f"All query params: {query_params}")

    results_param = st.query_params.get("results")
    st.write(f"Results param exists: {results_param is not None}")

    metadata_list = None
    timeline_entries = []
    payload_size = None

    if results_param:
        try:
            st.write(f"Results param length: {len(results_param)} characters")
            st.write(f"First 100 chars: {results_param[:100]}...")
            decoded = base64.b64decode(results_param).decode("utf-8")
            st.write(f"Decoded payload length: {len(decoded)} characters")
            decoded_payload = json.loads(decoded)
            if isinstance(decoded_payload, dict) and "metadata" in decoded_payload:
                metadata_list = decoded_payload.get("metadata", [])
                timeline_entries = decoded_payload.get("timeline", [])
            else:
                metadata_list = decoded_payload
            st.write(f"Parsed {len(metadata_list)} items from URL payload")
            payload_size = len(results_param)
        except Exception as exc:  # pylint: disable=broad-except
            st.error(f"Error decoding results: {exc}")

    st.write("---")
    st.write("🧭 **Client-side Steps:**")
    st.write("1️⃣ Choose MP4/MOV files using the picker below")
    st.write("2️⃣ Click Analyze to run browser-side metadata extraction")
    st.write("3️⃣ Watch the timeline for progress updates")
    st.write("4️⃣ Results appear here without uploading")

    html_code = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8" />
        <script src="https://cdn.jsdelivr.net/npm/mp4box@0.5.2/dist/mp4box.all.min.js"></script>
        <style>
            body { font-family: sans-serif; padding: 10px; }
            #fileInput { margin: 10px 0; }
            #analyzeBtn {
                background: #FF4B4B;
                color: white;
                padding: 8px 20px;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                margin-left: 10px;
            }
            #analyzeBtn:disabled { background: #ccc; }
            #status { margin-top: 10px; color: #0066cc; font-weight: 500; }
            #debugLog {
                margin-top: 12px;
                padding: 12px;
                border: 1px solid #d0d7de;
                border-radius: 6px;
                background: #f6f8fa;
                font-size: 13px;
                max-height: 220px;
                overflow-y: auto;
            }
            #debugLog div { margin-bottom: 6px; }
        </style>
    </head>
    <body>
        <input type="file" id="fileInput" multiple accept="video/*,.mp4,.mov,.m4v">
        <button id="analyzeBtn">Analyze</button>
        <div id="status"></div>
        <div id="debugLog"><strong>Debug Timeline</strong></div>

        <script>
            const getStreamlit = () => (window.parent && window.parent.Streamlit) ? window.parent.Streamlit : null;
            const timelineEntries = [];
            const fileInput = document.getElementById('fileInput');
            const analyzeBtn = document.getElementById('analyzeBtn');
            const status = document.getElementById('status');
            const debugLog = document.getElementById('debugLog');
            const TIMEOUT_MS = 45000;
            const CHUNK_SIZE = 4 * 1024 * 1024;
            const toMb = (bytes) => (bytes / (1024 * 1024)).toFixed(1);

            const updateFrameHeight = () => {
                const Streamlit = getStreamlit();
                if (Streamlit && Streamlit.setFrameHeight) {
                    Streamlit.setFrameHeight(document.body.scrollHeight);
                }
            };

            const logStep = (message) => {
                timelineEntries.push(message);
                const entry = document.createElement('div');
                entry.textContent = message;
                debugLog.appendChild(entry);
                updateFrameHeight();
            };

            window.addEventListener('load', () => {
                const Streamlit = getStreamlit();
                if (Streamlit && Streamlit.setComponentReady) {
                    Streamlit.setComponentReady();
                }
                updateFrameHeight();
            });

            analyzeBtn.addEventListener('click', async () => {
                const files = fileInput.files;
                if (files.length === 0) {
                    alert('Please select video files first');
                    return;
                }

                analyzeBtn.disabled = true;
                status.textContent = `Analyzing ${files.length} file(s)...`;
                logStep(`Selected ${files.length} file(s). Starting analysis...`);

                const metadata = [];

                for (let i = 0; i < files.length; i++) {
                    const file = files[i];
                    status.textContent = `Processing ${i + 1}/${files.length}: ${file.name}`;
                    logStep(`Processing file ${i + 1}: ${file.name}`);

                    try {
                        const data = await analyzeFile(file);
                        metadata.push(data);
                    } catch (error) {
                        console.error(`Error processing ${file.name}:`, error);
                        logStep(`⚠️ Error on ${file.name}: ${error.message}`);
                        metadata.push({
                            fileName: file.name,
                            format: 'error',
                            videoCodec: 'error',
                            audioCodec: error.message || 'timeout',
                            size: file.size
                        });
                    }
                }

                status.textContent = 'Complete! Returning results...';
                logStep(`Analysis complete. Preparing ${metadata.length} result(s) for return.`);

                const payload = {
                    metadata: metadata,
                    timeline: timelineEntries
                };

                const jsonStr = JSON.stringify(payload);
                const encodedPayload = btoa(jsonStr);
                logStep(`Encoded payload size (base64): ${encodedPayload.length} characters.`);

                const Streamlit = getStreamlit();
                if (Streamlit && Streamlit.setComponentValue) {
                    logStep('Sending results to Streamlit parent via component bridge...');
                    Streamlit.setComponentValue({
                        metadata: metadata,
                        timeline: timelineEntries,
                        payloadSize: encodedPayload.length
                    });
                    status.textContent = 'Results sent to Streamlit.';
                    analyzeBtn.disabled = false;
                    updateFrameHeight();
                    return;
                }

                logStep('Component bridge unavailable. Attempting parent redirect with payload...');
                const parentWindow = window.parent;
                if (parentWindow && parentWindow.location) {
                    try {
                        const baseUrl = parentWindow.location.href.split('?')[0];
                        parentWindow.location.href = baseUrl + '?results=' + encodeURIComponent(encodedPayload);
                        logStep('Parent redirect triggered.');
                        status.textContent = 'Redirecting with results...';
                    } catch (redirectError) {
                        logStep(`❌ Redirect blocked: ${redirectError.message}`);
                        analyzeBtn.disabled = false;
                        status.textContent = 'Redirect blocked. See timeline.';
                    }
                } else {
                    logStep('❌ Unable to access parent window. Please open Quick Check in a new tab.');
                    analyzeBtn.disabled = false;
                    status.textContent = 'Unable to reach parent window.';
                }
            });

            async function analyzeFile(file) {
                return new Promise((resolve, reject) => {
                    const ext = file.name.split('.').pop().toLowerCase();

                    if (!['mp4', 'mov', 'm4v'].includes(ext)) {
                        logStep(`Skipping ${file.name} (extension ${ext}) - treated as non-MP4.`);
                        resolve({
                            fileName: file.name,
                            format: ext,
                            videoCodec: 'N/A',
                            audioCodec: 'N/A',
                            size: file.size
                        });
                        return;
                    }

                    let finished = false;
                    let offset = 0;
                    let chunkCount = 0;
                    const chunkSizeMb = toMb(CHUNK_SIZE);
                    const totalMb = toMb(file.size);
                    logStep(`Chunked parser reading ${totalMb} MB in ${chunkSizeMb} MB chunks.`);

                    const mp4boxfile = MP4Box.createFile();

                    const cleanup = () => {
                        finished = true;
                        clearTimeout(timerId);
                    };

                    mp4boxfile.onError = () => {
                        if (finished) {
                            return;
                        }
                        cleanup();
                        logStep(`❌ MP4Box parse error on ${file.name}`);
                        reject(new Error('MP4Box parse error'));
                    };

                    mp4boxfile.onReady = (info) => {
                        if (finished) {
                            return;
                        }
                        cleanup();

                        let format = info.brand || 'mp4';
                        if (format && format.includes('qt')) {
                            format = 'mov';
                        } else if (format && (format.includes('mp4') || format.includes('isom'))) {
                            format = 'mp4';
                        }

                        let videoCodec = 'unknown';
                        const videoTrack = info.videoTracks[0];
                        if (videoTrack) {
                            const codec = videoTrack.codec || '';
                            if (codec.includes('avc') || codec.includes('h264')) {
                                videoCodec = 'h264';
                            } else if (codec.includes('hvc') || codec.includes('hev') || codec.includes('h265')) {
                                videoCodec = 'hevc';
                            } else {
                                videoCodec = codec || 'unknown';
                            }
                        }

                        let audioCodec = 'none';
                        const audioTrack = info.audioTracks[0];
                        if (audioTrack) {
                            const codec = audioTrack.codec || '';
                            if (codec.includes('mp4a')) {
                                audioCodec = 'aac';
                            } else {
                                audioCodec = codec || 'unknown';
                            }
                        }

                        logStep(`✅ Parsed ${file.name} → format: ${format || 'mp4'}, video: ${videoCodec}, audio: ${audioCodec}`);
                        resolve({
                            fileName: file.name,
                            format: format || 'mp4',
                            videoCodec: videoCodec,
                            audioCodec: audioCodec,
                            size: file.size
                        });
                    };

                    const timerId = setTimeout(() => {
                        if (finished) {
                            return;
                        }
                        cleanup();
                        reject(new Error('Processing timeout'));
                    }, TIMEOUT_MS);

                    const readNextChunk = () => {
                        if (finished) {
                            return;
                        }
                        if (offset >= file.size) {
                            mp4boxfile.flush();
                            return;
                        }

                        const slice = file.slice(offset, offset + CHUNK_SIZE);
                        const reader = new FileReader();

                        reader.onload = (event) => {
                            if (finished) {
                                return;
                            }
                            const arrayBuffer = event.target.result;
                            arrayBuffer.fileStart = offset;
                            offset += arrayBuffer.byteLength;
                            chunkCount += 1;
                            if (chunkCount === 1 || offset >= file.size || chunkCount % 5 === 0) {
                                logStep(`Read chunk ${chunkCount} (${toMb(Math.min(offset, file.size))} of ${totalMb} MB).`);
                            }
                            mp4boxfile.appendBuffer(arrayBuffer);
                            if (offset < file.size) {
                                readNextChunk();
                            } else {
                                mp4boxfile.flush();
                            }
                        };

                        reader.onerror = () => {
                            if (finished) {
                                return;
                            }
                            cleanup();
                            reject(new Error('File read error'));
                        };

                        reader.readAsArrayBuffer(slice);
                    };

                    readNextChunk();
                });
            }
        </script>
    </body>
    </html>
    """

    component_value = st.components.v1.html(html_code, height=420, scrolling=True)

    if isinstance(component_value, dict):
        metadata_from_component = component_value.get("metadata")
        if isinstance(metadata_from_component, list) and metadata_from_component:
            metadata_list = metadata_from_component

        timeline_from_component = component_value.get("timeline")
        if isinstance(timeline_from_component, list) and timeline_from_component:
            timeline_entries = timeline_from_component

        payload_size_value = component_value.get("payloadSize")
        if isinstance(payload_size_value, int):
            payload_size = payload_size_value

    if metadata_list:
        st.write("---")
        st.write("📊 **Processing Steps (Python):**")
        st.write("1️⃣ Received metadata payload from browser component")
        st.write(f"2️⃣ Payload size: {payload_size if payload_size is not None else 'unknown'} characters")
        st.write(f"3️⃣ Preparing DataFrame with {len(metadata_list)} rows")
        st.success(f"✅ Quick Check completed for {len(metadata_list)} files!")

        valid_formats = ["mp4", "mov"]
        valid_codecs = [
            "h264",
            "avc",
            "hevc",
            "h265",
            "mpeg1video",
            "mpeg2video",
            "mpeg1",
            "mpeg2",
        ]

        results = []
        for item in metadata_list:
            file_name = item.get("fileName", "unknown")
            fmt_raw = item.get("format", "unknown")
            fmt_lower = fmt_raw.lower() if isinstance(fmt_raw, str) else "unknown"
            video_codec_raw = item.get("videoCodec", "unknown")
            video_codec_lower = video_codec_raw.lower() if isinstance(video_codec_raw, str) else "unknown"
            audio_codec = item.get("audioCodec", "unknown")
            file_size_bytes = item.get("size", 0) or 0
            file_size_mb = file_size_bytes / (1024 * 1024)

            format_flag = "good to go" if fmt_lower in valid_formats else "error"
            codec_flag = "good to go" if video_codec_lower in valid_codecs else "error"
            size_flag = "good to go" if file_size_mb <= 200 else "error"

            results.append(
                {
                    "File Name": file_name,
                    "Video Format": fmt_raw,
                    "Video Format Flag": format_flag,
                    "Video Codecs": f"Video: {video_codec_raw}, Audio: {audio_codec}",
                    "Video Codecs Flag": codec_flag,
                    "File Size": f"{file_size_mb:.2f} MB",
                    "File Size Flag": size_flag,
                }
            )

        df = pd.DataFrame(results)
        st.dataframe(df, width="stretch")

        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Video Metadata")
        processed_data = output.getvalue()

        st.download_button(
            label="📥 Download Excel Report",
            data=processed_data,
            file_name="video_metadata_quick_check.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        if timeline_entries:
            st.write("---")
            st.write("🕒 **Client Debug Timeline:**")
            for entry in timeline_entries:
                st.write(f"- {entry}")

        if st.button("🔄 Analyze New Files"):
            st.query_params.clear()
            st.rerun()
    else:
        if timeline_entries:
            st.write("---")
            st.write("🕒 **Client Debug Timeline (latest run):**")
            for entry in timeline_entries:
                st.write(f"- {entry}")
        st.info(
            "Waiting for Quick Check results. After clicking Analyze the browser timeline above should end with either a bridge success message or a redirect attempt."
        )


def render_standard_upload():
    """Handle the standard upload (server-side) workflow."""
    st.warning("⚠️ Large files (10+) may cause timeout. For 10+ files, use Quick Check mode.")

    uploaded_files = st.file_uploader(
        "Choose video files",
        accept_multiple_files=True,
        type=["mp4", "mov", "avi", "mkv", "flv", "wmv", "webm", "m4v"],
    )

    if uploaded_files:
        st.success(f"✅ {len(uploaded_files)} file(s) uploaded successfully!")

        if st.button("Analyze Videos", type="primary"):
            start_time = time.time()
            st.info(f"Processing {len(uploaded_files)} files with ffprobe...")

            results = []
            progress_placeholder = st.empty()
            status_placeholder = st.empty()

            valid_formats = ["mp4", "mov"]
            valid_codecs = [
                "h264",
                "avc",
                "hevc",
                "h265",
                "mpeg1video",
                "mpeg2video",
                "mpeg1",
                "mpeg2",
            ]

            for index, uploaded_file in enumerate(uploaded_files):
                progress_placeholder.progress(index / len(uploaded_files))
                status_placeholder.info(
                    f"🔄 Processing file {index + 1} of {len(uploaded_files)}: {uploaded_file.name}"
                )

                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=os.path.splitext(uploaded_file.name)[1]
                ) as tmp_file:
                    shutil.copyfileobj(uploaded_file, tmp_file)
                    temp_path = tmp_file.name

                try:
                    fmt, v_codec, a_codec = get_video_metadata(temp_path)

                    format_flag = "good to go" if fmt.lower() in valid_formats else "error"
                    codec_flag = "good to go" if v_codec.lower() in valid_codecs else "error"

                    file_size_bytes = os.path.getsize(temp_path)
                    file_size_mb = file_size_bytes / (1024 * 1024)
                    size_flag = "good to go" if file_size_mb <= 200 else "error"

                    results.append(
                        {
                            "File Name": uploaded_file.name,
                            "Video Format": fmt,
                            "Video Format Flag": format_flag,
                            "Video Codecs": f"Video: {v_codec}, Audio: {a_codec}",
                            "Video Codecs Flag": codec_flag,
                            "File Size": f"{file_size_mb:.2f} MB",
                            "File Size Flag": size_flag,
                        }
                    )
                finally:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)

            progress_placeholder.progress(1.0)
            status_placeholder.empty()

            elapsed_time = time.time() - start_time
            df = pd.DataFrame(results)
            st.success(f"✅ Standard Analysis Complete! Time taken: {elapsed_time:.2f} seconds")
            st.dataframe(df, width="stretch")

            output = BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="Video Metadata")
            processed_data = output.getvalue()

            st.download_button(
                label="📥 Download Excel Report",
                data=processed_data,
                file_name="video_metadata_upload_report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )


def main():
    st.set_page_config(page_title="Video Metadata Extractor", layout="wide")

    st.title("🎥 Video Metadata Extractor")
    st.markdown("Analyze video files to extract format, codec details, and check file size.")

    input_method = st.sidebar.radio("Select Input Method:", ("Folder Path (Local)", "Upload Files"))

    if input_method == "Folder Path (Local)":
        st.subheader("📂 Local Folder Analysis")
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
                    video_extensions = (
                        ".mp4",
                        ".mov",
                        ".avi",
                        ".mkv",
                        ".flv",
                        ".wmv",
                        ".webm",
                        ".m4v",
                    )
                    files = [name for name in os.listdir(folder_path) if name.lower().endswith(video_extensions)]

                    if not files:
                        st.warning("No video files found in this directory.")
                    else:
                        st.info(f"Found {len(files)} video files. Processing...")
                        file_paths = [os.path.join(folder_path, name) for name in files]

                        df = analyze_videos(file_paths)
                        st.success("Analysis Complete!")
                        st.dataframe(df, width="stretch")

                        output = BytesIO()
                        with pd.ExcelWriter(output, engine="openpyxl") as writer:
                            df.to_excel(writer, index=False, sheet_name="Video Metadata")
                        processed_data = output.getvalue()

                        st.download_button(
                            label="📥 Download Excel Report",
                            data=processed_data,
                            file_name="video_metadata_report.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        )
            else:
                import platform

                system_os = platform.system()
                if system_os != "Windows" and (":\\" in folder_path or ":/" in folder_path):
                    st.error(
                        f"Invalid path. You seem to be using a Windows path (`{folder_path}`) but this application is running on {system_os}. Please use a valid path for this computer."
                    )
                elif system_os == "Windows" and folder_path.startswith("/"):
                    st.error(
                        f"Invalid path. You seem to be using a Unix/Mac path (`{folder_path}`) but this application is running on Windows. Please use a valid Windows path."
                    )
                else:
                    st.error(
                        f"Invalid folder path: `{folder_path}`. Please verify the folder exists and is accessible."
                    )

    elif input_method == "Upload Files":
        st.subheader("📤 File Upload Analysis")
        st.markdown("Upload video files directly from your computer.")

        processing_method = st.radio(
            "⚙️ Select Analysis Method:",
            ("Standard Upload (Server-side)", "Quick Check (Client-side - Browser only)"),
            help=(
                "**Standard**: Uploads files to server, full ffprobe analysis (accurate but slow for 10+ files).\n\n"
                "**Quick Check**: Files stay in your browser, instant metadata extraction (MP4/MOV only, avoids 502 timeout)."
            ),
        )

        st.markdown("---")

        if processing_method == "Quick Check (Client-side - Browser only)":
            render_quick_check()
        else:
            render_standard_upload()


if __name__ == "__main__":
    main()
