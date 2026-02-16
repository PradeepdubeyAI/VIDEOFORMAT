import os
import json
import base64
from io import BytesIO

import pandas as pd
import streamlit as st


def render_quick_check():
    """Handle the Quick Check (client-side) workflow."""
    st.info("🚀 Quick Check: Files analyzed in your browser without uploading. Full analysis for MP4/MOV files, basic info for others.")

    metadata_list = None
    timeline_entries = []
    payload_size = None

    results_param = st.query_params.get("results")

    if results_param:
        try:
            decoded = base64.b64decode(results_param).decode("utf-8")
            decoded_payload = json.loads(decoded)
            if isinstance(decoded_payload, dict) and "metadata" in decoded_payload:
                metadata_list = decoded_payload.get("metadata", [])
                timeline_entries = decoded_payload.get("timeline", [])
            else:
                metadata_list = decoded_payload
            payload_size = len(results_param)
        except Exception as exc:  # pylint: disable=broad-except
            st.error(f"Error decoding results: {exc}")

    html_code = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8" />
        <script src="https://cdn.jsdelivr.net/npm/mp4box@0.5.2/dist/mp4box.all.min.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js"></script>
        <style>
            body {
                font-family: sans-serif;
                padding: 16px;
                background: #ffffff;
                color: #1f2328;
            }
            #fileInputWrapper {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: 12px;
                margin-bottom: 12px;
            }
            #fileLabel {
                font-weight: 600;
            }
            #fileInput {
                margin: 0;
            }
            #analyzeBtn {
                background: #FF4B4B;
                color: white;
                padding: 8px 20px;
                border: none;
                border-radius: 4px;
                cursor: pointer;
            }
            #analyzeBtn:disabled { background: #ccc; }
            #downloadBtn {
                background: #28a745;
                color: white;
                padding: 8px 20px;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                margin-left: 12px;
                display: none;
            }
            #downloadBtn:hover { background: #218838; }
            #status { margin-top: 10px; color: #0066cc; font-weight: 500; }
            #debugLog {
                display: none;
            }
            #resultContainer {
                margin-top: 18px;
                border: 1px solid #d0d7de;
                border-radius: 6px;
                padding: 12px;
                background: #ffffff;
            }
            #resultsTable {
                width: 100%;
                border-collapse: collapse;
                margin-top: 8px;
                font-size: 13px;
            }
            #resultsTable th, #resultsTable td {
                border: 1px solid #d0d7de;
                padding: 6px 10px;
                text-align: left;
            }
            #resultsTable th {
                background: #f0f3f5;
                font-weight: 600;
            }
        </style>
    </head>
    <body>
        <div id="fileInputWrapper">
            <label id="fileLabel" for="fileInput">Select video files:</label>
            <input type="file" id="fileInput" multiple accept="video/*,.mp4,.mov,.avi,.mkv,.flv,.wmv,.webm,.m4v,.mpeg,.mpg">
            <button id="analyzeBtn">Analyze</button>
            <button id="downloadBtn">📥 Download Excel</button>
        </div>
        <div id="status"></div>
        <div id="debugLog"><strong>Debug Timeline</strong></div>
        <div id="resultContainer"></div>

        <script>
            const timelineEntries = [];
            const fileInput = document.getElementById('fileInput');
            const analyzeBtn = document.getElementById('analyzeBtn');
            const downloadBtn = document.getElementById('downloadBtn');
            const status = document.getElementById('status');
            const debugLog = document.getElementById('debugLog');
            const resultContainer = document.getElementById('resultContainer');
            let lastMetadata = [];
            const TIMEOUT_MS = 45000;
            const CHUNK_SIZE = 4 * 1024 * 1024;
            const toMb = (bytes) => (bytes / (1024 * 1024)).toFixed(1);

            let streamlitId = null;
            let postMessageErrorLogged = false;
            let streamlitBridge = null;
            let bridgePollAttempts = 0;
            const BRIDGE_POLL_MAX = 40;
            let readyAnnounceCount = 0;
            let readyAnnounceInterval = null;
            let readyAnnounceErrorLogged = false;
            let frameResizeErrorLogged = false;

            const logStep = (message) => {
                timelineEntries.push(message);
                const entry = document.createElement('div');
                entry.textContent = message;
                debugLog.appendChild(entry);
                updateFrameHeight();
            };

            const postToStreamlit = (type, data = {}) => {
                if (streamlitId === null) {
                    return false;
                }
                try {
                    window.parent.postMessage({
                        isStreamlitMessage: true,
                        type,
                        id: streamlitId,
                        ...data
                    }, '*');
                    return true;
                } catch (error) {
                    if (!postMessageErrorLogged) {
                        postMessageErrorLogged = true;
                        logStep(`⚠️ postMessage to parent failed: ${error.message}`);
                    }
                    return false;
                }
            };

            const updateFrameHeight = () => {
                if (streamlitBridge && streamlitBridge.setFrameHeight) {
                    streamlitBridge.setFrameHeight(document.body.scrollHeight);
                    return;
                }
                if (streamlitId !== null) {
                    postToStreamlit('streamlit:setFrameHeight', { height: document.body.scrollHeight });
                } else {
                    try {
                        window.parent.postMessage({
                            isStreamlitMessage: true,
                            type: 'streamlit:setFrameHeight',
                            height: document.body.scrollHeight
                        }, '*');
                    } catch (error) {
                        if (!frameResizeErrorLogged) {
                            frameResizeErrorLogged = true;
                            logStep(`⚠️ Unable to request frame resize: ${error.message}`);
                        }
                    }
                }
            };

            const setComponentReady = () => {
                if (streamlitBridge && streamlitBridge.setComponentReady) {
                    streamlitBridge.setComponentReady();
                } else {
                    postToStreamlit('streamlit:setComponentReady');
                }
            };

            const announceComponentReady = (withLog = false) => {
                try {
                    window.parent.postMessage({
                        isStreamlitMessage: true,
                        type: 'streamlit:componentReady',
                        apiVersion: 1
                    }, '*');
                    readyAnnounceCount += 1;
                    if (withLog) {
                        logStep('Notified Streamlit parent that component is ready.');
                    }
                } catch (error) {
                    if (withLog && !readyAnnounceErrorLogged) {
                        readyAnnounceErrorLogged = true;
                        logStep(`⚠️ Failed to notify parent: ${error.message}`);
                    }
                }
            };

            const sendComponentValue = (value) => {
                if (streamlitBridge && streamlitBridge.setComponentValue) {
                    try {
                        streamlitBridge.setComponentValue(value);
                        return true;
                    } catch (error) {
                        logStep(`⚠️ setComponentValue via bridge failed: ${error.message}`);
                    }
                }
                if (streamlitId === null) {
                    logStep('⚠️ Cannot send results to Streamlit yet (no component id).');
                    return false;
                }
                return postToStreamlit('streamlit:setComponentValue', { value });
            };

            window.addEventListener('message', (event) => {
                const data = event.data;
                if (!data || !data.type) {
                    return;
                }
                if (data.isStreamlitMessage === false) {
                    return;
                }
                if (data.type === 'streamlit:render') {
                    streamlitId = data.id;
                    logStep(`✅ Connected to Streamlit (component id: ${streamlitId}).`);
                    if (readyAnnounceInterval) {
                        clearInterval(readyAnnounceInterval);
                        readyAnnounceInterval = null;
                    }
                    if (data.args && Object.keys(data.args).length > 0) {
                        logStep(`Received args: ${JSON.stringify(data.args)}`);
                    }
                    setComponentReady();
                    updateFrameHeight();
                }
            });

            const pollStreamlitBridge = () => {
                if (streamlitBridge) {
                    return;
                }
                bridgePollAttempts += 1;
                try {
                    const candidate = window.parent && window.parent.Streamlit;
                    if (candidate) {
                        streamlitBridge = candidate;
                        logStep('✅ Detected window.parent.Streamlit bridge.');
                        if (streamlitBridge.setFrameHeight) {
                            streamlitBridge.setFrameHeight(document.body.scrollHeight);
                        }
                        if (streamlitBridge.setComponentReady) {
                            streamlitBridge.setComponentReady();
                        }
                        return;
                    }
                } catch (error) {
                    logStep(`⚠️ Accessing parent Streamlit threw: ${error.message}`);
                }
                if (bridgePollAttempts >= BRIDGE_POLL_MAX) {
                    logStep('⚠️ Streamlit bridge not detected after polling. Using postMessage fallback only.');
                    clearInterval(bridgePollInterval);
                }
            };

            const bridgePollInterval = setInterval(() => {
                pollStreamlitBridge();
                if (streamlitBridge) {
                    clearInterval(bridgePollInterval);
                }
            }, 250);

            window.addEventListener('load', () => {
                logStep('Component loaded. Waiting for Streamlit render event...');
                pollStreamlitBridge();
                updateFrameHeight();
                announceComponentReady(true);
                if (!readyAnnounceInterval) {
                    readyAnnounceInterval = setInterval(() => {
                        if (streamlitId !== null) {
                            clearInterval(readyAnnounceInterval);
                            readyAnnounceInterval = null;
                            return;
                        }
                        announceComponentReady(false);
                        if (readyAnnounceCount >= 10) {
                            clearInterval(readyAnnounceInterval);
                            readyAnnounceInterval = null;
                            logStep('⚠️ No Streamlit response after announcing readiness multiple times.');
                        }
                    }, 1500);
                }
            });

            const renderLocalResults = (rows) => {
                if (!resultContainer) {
                    return;
                }
                resultContainer.innerHTML = '';

                if (!rows || rows.length === 0) {
                    resultContainer.innerHTML = '<em>No results to display.</em>';
                    return;
                }

                const heading = document.createElement('div');
                heading.textContent = 'Results:';
                heading.style.fontWeight = '600';
                heading.style.fontSize = '16px';
                heading.style.marginBottom = '8px';
                resultContainer.appendChild(heading);

                const table = document.createElement('table');
                table.id = 'resultsTable';
                const headerRow = document.createElement('tr');
                ['File Name', 'Video Format', 'Video Format Flag', 'Video Codecs', 'Video Codecs Flag', 'File Size', 'File Size Flag'].forEach((label) => {
                    const th = document.createElement('th');
                    th.textContent = label;
                    headerRow.appendChild(th);
                });
                table.appendChild(headerRow);

                rows.forEach((item) => {
                    const tr = document.createElement('tr');
                    const safeSize = (item.size || 0) / (1024 * 1024);
                    const validation = validateFile(item);
                    const cells = [
                        item.fileName || 'unknown',
                        item.format || 'unknown',
                        validation.formatFlag,
                        `Video: ${item.videoCodec || 'unknown'}, Audio: ${item.audioCodec || 'unknown'}`,
                        validation.codecFlag,
                        safeSize.toFixed(2) + ' MB',
                        validation.sizeFlag
                    ];
                    cells.forEach((value, index) => {
                        const td = document.createElement('td');
                        td.textContent = value;
                        if ([2, 4, 6].includes(index) && value === 'error') {
                            td.style.color = '#d73a49';
                            td.style.fontWeight = '600';
                        } else if ([2, 4, 6].includes(index) && value === 'good to go') {
                            td.style.color = '#28a745';
                            td.style.fontWeight = '600';
                        }
                        tr.appendChild(td);
                    });
                    table.appendChild(tr);
                });

                resultContainer.appendChild(table);
            };

            const validateFile = (item) => {
                const sizeMB = (item.size || 0) / (1024 * 1024);
                
                const validFormats = ['mp4', 'mov'];
                const formatFlag = validFormats.includes((item.format || '').toLowerCase()) ? 'good to go' : 'error';
                
                const validCodecs = ['h264', 'avc', 'hevc', 'h265', 'mpeg1video', 'mpeg2video', 'mpeg1', 'mpeg2'];
                const videoCodec = (item.videoCodec || '').toLowerCase();
                const codecFlag = validCodecs.includes(videoCodec) ? 'good to go' : 'error';
                
                const sizeFlag = sizeMB <= 200 ? 'good to go' : 'error';
                
                return { formatFlag, codecFlag, sizeFlag };
            };

            const generateExcel = () => {
                if (!lastMetadata || lastMetadata.length === 0) {
                    alert('No data to download. Please analyze files first.');
                    return;
                }

                logStep('Generating Excel file...');
                
                const worksheetData = [
                    ['File Name', 'Video Format', 'Video Format Flag', 'Video Codecs', 'Video Codecs Flag', 'File Size', 'File Size Flag']
                ];
                
                lastMetadata.forEach((item) => {
                    const sizeMB = ((item.size || 0) / (1024 * 1024)).toFixed(2) + ' MB';
                    const validation = validateFile(item);
                    worksheetData.push([
                        item.fileName || 'unknown',
                        item.format || 'unknown',
                        validation.formatFlag,
                        `Video: ${item.videoCodec || 'unknown'}, Audio: ${item.audioCodec || 'unknown'}`,
                        validation.codecFlag,
                        sizeMB,
                        validation.sizeFlag
                    ]);
                });

                const workbook = XLSX.utils.book_new();
                const worksheet = XLSX.utils.aoa_to_sheet(worksheetData);
                
                const colWidths = [
                    { wch: 50 },
                    { wch: 15 },
                    { wch: 18 },
                    { wch: 35 },
                    { wch: 18 },
                    { wch: 15 },
                    { wch: 15 }
                ];
                worksheet['!cols'] = colWidths;

                const range = XLSX.utils.decode_range(worksheet['!ref']);
                
                for (let row = range.s.r; row <= range.e.r; row++) {
                    for (let col = range.s.c; col <= range.e.c; col++) {
                        const cellAddress = XLSX.utils.encode_cell({ r: row, c: col });
                        if (!worksheet[cellAddress]) continue;
                        
                        if (!worksheet[cellAddress].s) worksheet[cellAddress].s = {};
                        
                        if (row === 0) {
                            worksheet[cellAddress].s = {
                                font: { bold: true, color: { rgb: "FFFFFF" } },
                                fill: { fgColor: { rgb: "4472C4" } },
                                alignment: { horizontal: "center", vertical: "center", wrapText: true },
                                border: {
                                    top: { style: "thin", color: { rgb: "000000" } },
                                    bottom: { style: "thin", color: { rgb: "000000" } },
                                    left: { style: "thin", color: { rgb: "000000" } },
                                    right: { style: "thin", color: { rgb: "000000" } }
                                }
                            };
                        } else {
                            const cellValue = worksheet[cellAddress].v;
                            let fillColor = "FFFFFF";
                            let fontColor = "000000";
                            let fontBold = false;
                            
                            if ([2, 4, 6].includes(col)) {
                                if (cellValue === 'good to go') {
                                    fillColor = "C6EFCE";
                                    fontColor = "006100";
                                    fontBold = true;
                                } else if (cellValue === 'error') {
                                    fillColor = "FFC7CE";
                                    fontColor = "9C0006";
                                    fontBold = true;
                                }
                            }
                            
                            worksheet[cellAddress].s = {
                                font: { bold: fontBold, color: { rgb: fontColor } },
                                fill: { fgColor: { rgb: fillColor } },
                                alignment: { vertical: "center", wrapText: col === 0 || col === 3 },
                                border: {
                                    top: { style: "thin", color: { rgb: "D3D3D3" } },
                                    bottom: { style: "thin", color: { rgb: "D3D3D3" } },
                                    left: { style: "thin", color: { rgb: "D3D3D3" } },
                                    right: { style: "thin", color: { rgb: "D3D3D3" } }
                                }
                            };
                        }
                    }
                }
                
                worksheet['!autofilter'] = { ref: XLSX.utils.encode_range(range) };
                worksheet['!freeze'] = { xSplit: 0, ySplit: 1, topLeftCell: 'A2', activePane: 'bottomLeft' };

                XLSX.utils.book_append_sheet(workbook, worksheet, 'Video Metadata');

                const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
                const filename = `video_metadata_${timestamp}.xlsx`;

                XLSX.writeFile(workbook, filename, { cellStyles: true });
                logStep(`✅ Excel file downloaded: ${filename}`);
                status.textContent = 'Excel file downloaded successfully!';
            };

            downloadBtn.addEventListener('click', generateExcel);

            analyzeBtn.addEventListener('click', async () => {
                const files = fileInput.files;
                if (files.length === 0) {
                    alert('Please select video files first');
                    return;
                }

                analyzeBtn.disabled = true;
                downloadBtn.style.display = 'none';
                lastMetadata = [];
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

                try {
                    logStep('Building payload object...');
                    const payload = {
                        metadata: metadata,
                        timeline: timelineEntries
                    };

                    logStep('Stringifying payload...');
                    const jsonStr = JSON.stringify(payload);
                    logStep(`JSON string length: ${jsonStr.length} characters.`);

                    logStep('Base64 encoding (UTF-8 safe)...');
                    const utf8Bytes = encodeURIComponent(jsonStr).replace(/%([0-9A-F]{2})/g, (_, p1) => {
                        return String.fromCharCode(parseInt(p1, 16));
                    });
                    const encodedPayload = btoa(utf8Bytes);
                    logStep(`Encoded payload size (base64): ${encodedPayload.length} characters.`);

                    logStep('Rendering local results preview in component...');
                    renderLocalResults(metadata);

                    lastMetadata = metadata;
                    downloadBtn.style.display = 'inline-block';
                    logStep('✅ Excel download ready. Click the Download Excel button above.');
                    status.textContent = 'Analysis complete!';
                    analyzeBtn.disabled = false;
                    updateFrameHeight();
                } catch (encodingError) {
                    logStep(`❌ Error encoding results: ${encodingError.message}`);
                    console.error('Encoding error details:', encodingError);
                    status.textContent = 'Error encoding results. Check console.';
                    analyzeBtn.disabled = false;
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

    component_value = st.components.v1.html(
        html_code,
        height=520,
        scrolling=True,
    )

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


def main():
    st.set_page_config(page_title="Video Metadata Extractor", layout="wide")

    st.title("🎥 Video Metadata Extractor")
    st.markdown("Analyze video files to extract format, codec details, and check file size.")

    render_quick_check()


if __name__ == "__main__":
    main()
