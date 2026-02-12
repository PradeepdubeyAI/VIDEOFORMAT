# Video Metadata Helper

This repository hosts the source code and automated build system for the **Video Metadata Helper** tool.

## 📥 how to Download the App

**For Windows Users:**
1. Go to the **Actions** tab (top of this page).
2. Click on the latest workflow run (top of the list).
3. Scroll down to the **Artifacts** section.
4. Click **VideoHelper-Windows** to download the zip file.
5. Extract the zip and run `VideoHelper.exe`. No installation required.

**For Mac Users:**
1. Follow the same steps but download **VideoHelper-Mac**.
2. Extract and run `VideoHelper`.

---

## 🛠 For Developers

### How to Release a New Version
1. Make changes to `video_app_tk.py`.
2. Push the changes to the `main` branch.
3. GitHub Actions will **automatically** build new executables for Windows and Mac.

### Local Development
- **Run App:** `python video_app_tk.py`
- **Dependencies:** `pip install -r requirements.txt`
