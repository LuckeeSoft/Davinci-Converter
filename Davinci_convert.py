import os
import sys
import json
import subprocess
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QListWidget,
    QFileDialog, QLabel, QComboBox, QProgressBar, QMessageBox,
    QHBoxLayout, QTextEdit
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from collections import Counter



class ConverterThread(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, files, resolution, output_dir, open_after, play_after):
        super().__init__()
        self.files = files
        self.resolution = resolution
        self.output_dir = output_dir
        self.open_after = open_after
        self.play_after = play_after
        self.converted_files = []


    def run(self):
        self.converted_files = []  # store converted file paths
        total = len(self.files)

        for i, f in enumerate(self.files, 1):
            result, out_path = self.convert_file(
                f, self.resolution, self.output_dir
            )
            self.status.emit(result)
            self.progress.emit(int(i / total * 100))

            if out_path:
                self.converted_files.append(out_path)

        self.finished.emit()


    def get_video_resolution(self, file_path):
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "json", file_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            data = json.loads(result.stdout)
            width = data["streams"][0]["width"]
            height = data["streams"][0]["height"]
            return width, height
        except Exception as e:
            print(f"Failed to get resolution for {file_path}: {e}")
            return 1920, 1080  # fallback

    def convert_file(self, input_file, selected_resolution, output_dir):
        ext = os.path.splitext(input_file)[1].lower()
        base_name = os.path.splitext(os.path.basename(input_file))[0]
        output_file = os.path.join(output_dir, base_name + ".mov")

        if ext == ".mkv":
            cmd = [
                "ffmpeg", "-y", "-i", input_file,
                "-map", "0:0", "-map", "0:1", "-map", "0:2?",
                "-c:v", "dnxhd", "-profile:v", "dnxhr_hq",
                "-pix_fmt", "yuv422p",
                "-c:a:0", "pcm_s16le",
                "-c:a:1", "pcm_s16le",
                "-s", selected_resolution,
                "-r", "30000/1001",
                "-b:v", "36M",
                "-f", "mov", output_file
            ]
        elif ext == ".mp4":
            cmd = [
                "ffmpeg", "-y", "-i", input_file,
                "-c:v", "dnxhd", "-profile:v", "dnxhr_hq",
                "-pix_fmt", "yuv422p",
                "-c:a", "pcm_s16le",
                output_file
            ]
        else:
            self.status.emit(f"Skipped unsupported file: {input_file}")
            return None, None

        try:
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
            )

            # ✅ Stream ffmpeg output live
            for line in process.stdout:
                self.status.emit(line.strip())  # Updates mini terminal

            process.wait()

            if process.returncode == 0:
                return f"Converted: {os.path.basename(input_file)} → {os.path.basename(output_file)}", output_file
            else:
                return f"Error converting {input_file}", None

        except Exception as e:
            return f"Error converting {input_file}: {e}", None


    def open_folder(self, path):
        folder = os.path.dirname(path)
        if sys.platform == "win32":
            os.startfile(folder)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", folder])
        else:
            subprocess.Popen(["xdg-open", folder])

    def play_video(self, path):
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])


class ConverterApp(QWidget):
    # ... your existing methods ...

    def check_resolution_consistency(self):
        resolutions = {}
        for f in self.file_list:
            w, h = self.get_video_resolution(f)
            res = f"{w}x{h}"
            resolutions[f] = res

        counts = Counter(resolutions.values())
        if not counts:
            return True  # no files selected

        majority_res, majority_count = counts.most_common(1)[0]
        diff_files = [f for f, res in resolutions.items() if res !=
                                                        majority_res]

        if diff_files:
            diff_count = len(diff_files)
            total = len(self.file_list)
            files_word = "file" if diff_count == 1 else "files"
            message = (
                f"Warning: {diff_count} {
                    files_word} have a different resolution than the majority.\n\n"
                f"Majority resolution: {
                    majority_res} ({majority_count} out of {total})\n\n"
                "Files with different resolution:\n"
            )
            for f in diff_files:
                message += f"- {os.path.basename(f)} ({resolutions[f]})\n"

            reply = QMessageBox.warning(
                self, "Resolution Mismatch", message,
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
            )
            return reply == QMessageBox.StandardButton.Ok

        return True

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Davinci Converter: MKV/MP4 to MOV")
        self.setFixedSize(400, 520)

        self.file_list = []
        self.output_dir = ""

        layout = QVBoxLayout()

        self.file_list_widget = QListWidget()
        layout.addWidget(QLabel("Selected Files:"))
        layout.addWidget(self.file_list_widget)

        self.select_button = QPushButton("Select Files")
        self.select_button.clicked.connect(self.select_files)
        layout.addWidget(self.select_button)

        self.remove_button = QPushButton("Remove Selected")
        self.remove_button.clicked.connect(self.remove_selected_files)
        self.remove_button.hide()
        layout.addWidget(self.remove_button)

        self.file_list_widget.itemSelectionChanged.connect(self.toggle_remove_button)
        self.file_list_widget.installEventFilter(self)


        # Output folder selector
        folder_layout = QHBoxLayout()
        self.output_folder_label = QLabel(
            "Output Folder: (Default: Same as input)")
        folder_layout.addWidget(self.output_folder_label)
        self.select_folder_button = QPushButton("Select Output Folder")
        self.select_folder_button.clicked.connect(self.select_output_folder)
        folder_layout.addWidget(self.select_folder_button)
        layout.addLayout(folder_layout)

        layout.addWidget(QLabel("Select Output Resolution (for MKV):"))
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(
            ["1920x1080", "1280x720", "854x480", "640x480"])
        layout.addWidget(self.resolution_combo)

        self.progress_bar = QProgressBar()
        self.progress_bar.hide()

        self.convert_button = QPushButton("Convert to MOV")
        self.convert_button.clicked.connect(self.convert_files)
        layout.addWidget(self.convert_button)

        layout.addWidget(self.progress_bar)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setFixedHeight(120)  # "mini" size
        self.log_output.setStyleSheet("""
            background-color: #1e1e1e;
            color: #00ff00;
            font-family: monospace;
            font-size: 11px;
""")
        layout.addWidget(self.log_output)

        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label)

        self.setLayout(layout)

        self.thread = None

    def select_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select MKV or MP4 files", "", "Video Files (*.mkv *.mp4)"
        )
        if files:
            self.file_list.extend(files)
            self.update_file_list()
            self.update_resolution_options()

    def remove_selected_files(self):
        selected_items = self.file_list_widget.selectedItems()
        if not selected_items:
           QMessageBox.information(self, "No Selection", "Please select a file to remove.")
           return
        for item in selected_items:
            file_name = item.text()
            # Find full path in self.file_list matching file_name
            full_path = next((f for f in self.file_list if os.path.basename(f) == file_name), None)
            if full_path:
                self.file_list.remove(full_path)
            self.file_list_widget.takeItem(self.file_list_widget.row(item))
        self.update_resolution_options()


    def toggle_remove_button(self):
        if self.file_list_widget.selectedItems():
            self.remove_button.show()
        else:
            self.remove_button.hide()

    def eventFilter(self, source, event):
        if source == self.file_list_widget and event.type() == event.Type.KeyPress:
            if event.key() == Qt.Key.Key_Delete:  # Delete key pressed
                self.remove_selected_files()
                return True  # Event handled
        return super().eventFilter(source, event)


    def update_file_list(self):
        self.file_list_widget.clear()
        for f in self.file_list:
            self.file_list_widget.addItem(os.path.basename(f))

    def select_output_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Output Folder", self.output_dir or os.path.expanduser(
                "~")
        )
        if folder:
            self.output_dir = folder
            self.output_folder_label.setText(
                f"Output Folder: {self.output_dir}")

    def get_video_resolution(self, file_path):
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "json", file_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            data = json.loads(result.stdout)
            width = data["streams"][0]["width"]
            height = data["streams"][0]["height"]
            return width, height
        except Exception as e:
            print(f"Failed to get resolution for {file_path}: {e}")
            return 1920, 1080

    def update_resolution_options(self):
        mkv_files = [f for f in self.file_list if f.lower().endswith(".mkv")]
        if not mkv_files:
            self.resolution_combo.clear()
            self.resolution_combo.addItems(
                ["1920x1080", "1280x720", "854x480", "640x480"])
            self.resolution_combo.setCurrentText("1920x1080")
            return
        w, h = self.get_video_resolution(mkv_files[0])
        if h > w:
            options = ["1080x1920", "720x1280", "480x854", "480x640"]
        else:
            options = ["1920x1080", "1280x720", "854x480", "640x480"]
        self.resolution_combo.clear()
        self.resolution_combo.addItems(options)
        self.resolution_combo.setCurrentIndex(0)

    def convert_files(self):
        if not self.file_list:
            QMessageBox.warning(self, "No Files", "Please select MKV or MP4 files first.")
            return

        if not self.check_resolution_consistency():
            self.status_label.setText("Conversion canceled due to resolution mismatch.")
            return


        self.convert_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.log_output.clear()
        self.status_label.setText("Converting...")

        resolution = self.resolution_combo.currentText()
        output_dir = self.output_dir or ""

        self.thread = ConverterThread(self.file_list, resolution, output_dir, False, False)
        self.thread.progress.connect(self.progress_bar.setValue)
        self.thread.status.connect(self.append_log)
        self.thread.finished.connect(self.conversion_finished)
        self.thread.start()

    def append_log(self, message):
        self.log_output.append(message)
        self.log_output.verticalScrollBar().setValue(
            self.log_output.verticalScrollBar().maximum()
        )  # auto-scroll


    def conversion_finished(self):
        self.convert_button.setEnabled(True)
        self.status_label.setText("Ready")
        self.progress_bar.hide()

        if not self.thread or not self.thread.converted_files:
            QMessageBox.information(self, "Done", "Conversion finished, but no files were converted.")
            return

        last_output = self.thread.converted_files[-1]

        reply = QMessageBox(self)
        reply.setWindowTitle("Conversion Completed!")
        reply.setText("All conversions completed successfully.\n\nWhat would you like to do?")
        open_folder_btn = reply.addButton("Open Folder", QMessageBox.ButtonRole.AcceptRole)
        play_video_btn = reply.addButton("Play Last Video", QMessageBox.ButtonRole.AcceptRole)
        reply.addButton("Close", QMessageBox.ButtonRole.RejectRole)
        reply.exec()

        if reply.clickedButton() == open_folder_btn:
            self.thread.open_folder(last_output)
        elif reply.clickedButton() == play_video_btn:
            self.thread.play_video(last_output)

if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Basic dark theme
    dark_stylesheet = """
    QWidget {
        background-color: #121212;
        color: #eeeeee;
        font-size: 14px;
    }
    QPushButton {
        background-color: #1f1f1f;
        border: 1px solid #3a3a3a;
        padding: 8px;
        border-radius: 5px;
    }
    QPushButton:hover {
        background-color: #333333;
    }
    QListWidget {
        background-color: #1e1e1e;
        border: 1px solid #3a3a3a;
    }
    QComboBox {
        background-color: #1e1e1e;
        border: 1px solid #3a3a3a;
        padding: 4px;
    }
    QProgressBar {
        background-color: #1e1e1e;
        border: 1px solid #3a3a3a;
        text-align: center;
    }
    QProgressBar::chunk {
        background-color: #3a9ef5;
    }
    QLabel {
        font-weight: bold;
    }
    QCheckBox {
        padding: 4px;
    }
    """
    app.setStyleSheet(dark_stylesheet)

    window = ConverterApp()
    window.show()
    sys.exit(app.exec())
