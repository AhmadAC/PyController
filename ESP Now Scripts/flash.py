# ESP32 Deployer GUI
import sys
import os
import json
import subprocess
import threading
import time
import serial
import serial.tools.list_ports
import shutil
import re
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QFileDialog, QComboBox, QPlainTextEdit, QMessageBox, QFrame,
                             QRadioButton, QTabWidget, QLineEdit, QCheckBox, QTreeWidget, QTreeWidgetItem,
                             QAbstractItemView)
from PySide6.QtCore import QObject, Signal, Slot, Qt, QEventLoop, QTimer
from PySide6.QtGui import QPalette, QColor, QTextCursor

CONFIG_FILE = "esp32_deployer_config.json"

class WorkerSignals(QObject):
    log_signal = Signal(str)
    update_log_signal = Signal(str)
    repl_signal = Signal(str)
    repl_state_signal = Signal(bool)
    explorer_update_signal = Signal(list)
    explorer_error_signal = Signal(str)
    auto_connect_repl_signal = Signal()

class ESP32Uploader(QWidget):
    def __init__(self):
        super().__init__()
        self.root_folder_path = ""
        self.boot_path = ""
        self.main_path = ""
        self.lib_path = ""
        self.firmware_path = ""
        self.env = "micropython"
        self.preserve_names = False
        
        # Default Flash Settings
        self.flash_address = "0x1000"
        self.flash_mode = "dio"
        self.flash_size = "detect"
        self.flash_freq = "keep"
        self.flash_baud = "921600"
        
        # REPL variables
        self.repl_serial = None
        self.repl_thread = None
        self.repl_stop_event = threading.Event()
        self.known_ports =[]
        
        self.load_config()
        
        self.signals = WorkerSignals()
        self.signals.log_signal.connect(self.update_terminal)
        self.signals.update_log_signal.connect(self.update_last_line_in_terminal)
        self.signals.repl_signal.connect(self.update_repl_console)
        self.signals.repl_state_signal.connect(self.update_repl_btn_state)
        self.signals.explorer_update_signal.connect(self.populate_explorer_tree)
        self.signals.explorer_error_signal.connect(self.show_explorer_error)
        self.signals.auto_connect_repl_signal.connect(self.auto_connect_repl)
        
        self.initUI()

        # Timer for automatic COM port refreshing
        self.port_monitor_timer = QTimer(self)
        self.port_monitor_timer.timeout.connect(self.check_for_port_changes)
        self.port_monitor_timer.start(1000) # Check for new ports every 1 second

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    config = json.load(f)
                    self.root_folder_path = config.get("root_folder", "")
                    self.boot_path = config.get("boot", "")
                    self.main_path = config.get("main", "")
                    self.lib_path = config.get("lib", "")
                    self.firmware_path = config.get("firmware", "")
                    self.env = config.get("env", "micropython")
                    self.preserve_names = config.get("preserve_names", False)
                    
                    # Load flash parameters
                    self.flash_address = config.get("flash_address", "0x1000")
                    self.flash_mode = config.get("flash_mode", "dio")
                    self.flash_size = config.get("flash_size", "detect")
                    self.flash_freq = config.get("flash_freq", "keep")
                    self.flash_baud = config.get("flash_baud", "921600")
            except Exception as e:
                print(f"Failed to load config: {e}")

    def save_config(self):
        config = {
            "root_folder": self.root_folder_path,
            "boot": self.boot_path,
            "main": self.main_path,
            "lib": self.lib_path,
            "firmware": self.firmware_path,
            "env": self.env,
            "preserve_names": self.cb_preserve_names.isChecked() if hasattr(self, 'cb_preserve_names') else self.preserve_names,
            "flash_address": self.combo_flash_address.currentText() if hasattr(self, 'combo_flash_address') else self.flash_address,
            "flash_mode": self.combo_flash_mode.currentText() if hasattr(self, 'combo_flash_mode') else self.flash_mode,
            "flash_size": self.combo_flash_size.currentText() if hasattr(self, 'combo_flash_size') else self.flash_size,
            "flash_freq": self.combo_flash_freq.currentText() if hasattr(self, 'combo_flash_freq') else self.flash_freq,
            "flash_baud": self.combo_flash_baud.currentText() if hasattr(self, 'combo_flash_baud') else self.flash_baud
        }
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            print(f"Failed to save config: {e}")

    def create_path_row(self, layout, target, is_folder=False):
        row_layout = QHBoxLayout()
        
        btn_select = QPushButton("") 
        btn_select.setStyleSheet("padding: 8px; background-color: #2d3748; color: white; border-radius: 4px;")
        
        btn_clear = QPushButton("❌ Clear")
        btn_clear.setFixedWidth(80)
        btn_clear.setStyleSheet("padding: 8px; background-color: #7f1d1d; color: white; font-weight: bold; border-radius: 4px;")
        
        row_layout.addWidget(btn_select, stretch=1)
        row_layout.addWidget(btn_clear)
        layout.addLayout(row_layout)
        
        setattr(self, f"btn_{target}", btn_select)
        setattr(self, f"btn_clear_{target}", btn_clear)
        
        if is_folder:
            btn_select.clicked.connect(lambda _, t=target: self.select_folder(t))
        elif target == 'firmware':
            btn_select.clicked.connect(self.select_firmware_file)
        else:
            btn_select.clicked.connect(lambda _, t=target: self.select_file(t))
            
        btn_clear.clicked.connect(lambda _, t=target: self.clear_path(t))

    def initUI(self):
        main_layout = QVBoxLayout()

        # --- PORT SELECTION (Global) ---
        port_group = QWidget()
        port_layout = QHBoxLayout(port_group)
        port_layout.setContentsMargins(0, 0, 0, 10)
        port_layout.addWidget(QLabel("1. Select COM Port:"))
        self.port_combo = QComboBox()
        self.port_combo.setStyleSheet("padding: 5px;")
        
        self.btn_refresh = QPushButton("🔄 Refresh")
        self.btn_refresh.setStyleSheet("padding: 5px;")
        self.btn_refresh.clicked.connect(self.refresh_ports)
        
        port_layout.addWidget(self.port_combo, stretch=3)
        port_layout.addWidget(self.btn_refresh, stretch=1)
        main_layout.addWidget(port_group)
        self.refresh_ports()

        # --- TABS ---
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # Tab 1: Deploy & Flash
        self.tab_deploy = QWidget()
        self.setup_deploy_tab()
        self.tabs.addTab(self.tab_deploy, "Deploy & Flash")

        # Tab 2: REPL
        self.tab_repl = QWidget()
        self.setup_repl_tab()
        self.tabs.addTab(self.tab_repl, "Serial REPL")
        
        # Tab 3: File Explorer
        self.tab_explorer = QWidget()
        self.setup_explorer_tab()
        self.tabs.addTab(self.tab_explorer, "File Explorer")
        
        # Tab 4: Flash Settings
        self.tab_flash_settings = QWidget()
        self.setup_flash_settings_tab()
        self.tabs.addTab(self.tab_flash_settings, "Flash Settings")

        self.setLayout(main_layout)
        self.setWindowTitle('ESP32 Deployer & Flasher')
        self.resize(750, 800) 

        for target in['root_folder', 'boot', 'main', 'lib', 'firmware']:
            self.update_button_ui(target)

    def setup_deploy_tab(self):
        deploy_layout = QVBoxLayout(self.tab_deploy)

        # --- ENVIRONMENT & SCRIPT UPLOADING ---
        script_group_label = QLabel("2. Select Environment & Upload Scripts")
        script_group_label.setStyleSheet("font-weight: bold; margin-top: 5px;")
        deploy_layout.addWidget(script_group_label)

        env_layout = QHBoxLayout()
        self.rb_micro = QRadioButton("MicroPython (main.py)")
        self.rb_circuit = QRadioButton("CircuitPython (code.py)")
        
        if self.env == "circuitpython":
            self.rb_circuit.setChecked(True)
        else:
            self.rb_micro.setChecked(True)
            
        self.rb_micro.toggled.connect(self.on_env_changed)
        self.rb_circuit.toggled.connect(self.on_env_changed)
        
        env_layout.addWidget(self.rb_micro)
        env_layout.addWidget(self.rb_circuit)
        deploy_layout.addLayout(env_layout)

        # Checkbox to prevent renaming scripts
        self.cb_preserve_names = QCheckBox("Do not rename py scripts (preserve exact filenames)")
        self.cb_preserve_names.setChecked(self.preserve_names)
        self.cb_preserve_names.toggled.connect(self.on_preserve_names_changed)
        deploy_layout.addWidget(self.cb_preserve_names)

        # File selections
        self.create_path_row(deploy_layout, 'root_folder', is_folder=True)
        self.create_path_row(deploy_layout, 'boot')
        self.create_path_row(deploy_layout, 'main')
        self.create_path_row(deploy_layout, 'lib', is_folder=True)

        self.btn_upload = QPushButton("UPLOAD SCRIPTS")
        self.btn_upload.setStyleSheet("""
            QPushButton { background-color: #166534; color: white; padding: 12px; font-weight: bold; border-radius: 5px;}
            QPushButton:disabled { background-color: #555; color: #999; }
        """)
        self.btn_upload.clicked.connect(self.start_upload_thread)
        deploy_layout.addWidget(self.btn_upload)

        # --- FIRMWARE FLASHING SECTION ---
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        deploy_layout.addWidget(line)

        flash_group_label = QLabel("3. Flash New Firmware (Bootloader Mode)")
        flash_group_label.setStyleSheet("font-weight: bold; margin-top: 5px;")
        deploy_layout.addWidget(flash_group_label)
        
        self.create_path_row(deploy_layout, 'firmware')

        self.btn_flash = QPushButton("ERASE and FLASH FIRMWARE")
        self.btn_flash.setStyleSheet("""
            QPushButton { background-color: #c2410c; color: white; padding: 12px; font-weight: bold; font-size: 14px; border-radius: 5px;}
            QPushButton:disabled { background-color: #555; color: #999; }
        """)
        self.btn_flash.clicked.connect(self.start_flash_thread)
        deploy_layout.addWidget(self.btn_flash)

        # --- TERMINAL WINDOW ---
        deploy_layout.addWidget(QLabel("Deployment Terminal Output:"))
        self.terminal = QPlainTextEdit()
        self.terminal.setReadOnly(True)
        self.terminal.setStyleSheet("background-color: #1e1e1e; color: #4ade80; font-family: Consolas, monospace; font-size: 13px;")
        deploy_layout.addWidget(self.terminal)

    def setup_repl_tab(self):
        repl_layout = QVBoxLayout(self.tab_repl)
        
        # Toolbar
        toolbar = QHBoxLayout()
        self.btn_repl_connect = QPushButton("Connect")
        self.btn_repl_connect.setStyleSheet("background-color: #166534; color: white; font-weight: bold;")
        self.btn_repl_connect.clicked.connect(self.toggle_repl_connection)
        toolbar.addWidget(self.btn_repl_connect)
        
        btn_repl_clear = QPushButton("Clear Console")
        btn_repl_clear.clicked.connect(lambda: self.repl_console.clear())
        toolbar.addWidget(btn_repl_clear)
        
        btn_ctrl_c = QPushButton("Ctrl+C (Interrupt)")
        btn_ctrl_c.clicked.connect(lambda: self.send_repl_bytes(b'\x03'))
        toolbar.addWidget(btn_ctrl_c)
        
        btn_ctrl_d = QPushButton("Ctrl+D (Soft Reset)")
        btn_ctrl_d.clicked.connect(lambda: self.send_repl_bytes(b'\x04'))
        toolbar.addWidget(btn_ctrl_d)
        
        repl_layout.addLayout(toolbar)
        
        # Terminal Output
        self.repl_console = QPlainTextEdit()
        self.repl_console.setReadOnly(True)
        self.repl_console.setStyleSheet("background-color: #1e1e1e; color: #e5e5e5; font-family: Consolas, monospace; font-size: 13px;")
        repl_layout.addWidget(self.repl_console)
        
        # Input row
        input_layout = QHBoxLayout()
        self.repl_input = QLineEdit()
        self.repl_input.setPlaceholderText("Enter command to send to REPL...")
        self.repl_input.returnPressed.connect(self.send_repl_command)
        input_layout.addWidget(self.repl_input)
        
        btn_send = QPushButton("Send")
        btn_send.clicked.connect(self.send_repl_command)
        input_layout.addWidget(btn_send)
        
        repl_layout.addLayout(input_layout)

    def setup_explorer_tab(self):
        explorer_layout = QVBoxLayout(self.tab_explorer)
        
        toolbar = QHBoxLayout()
        self.btn_explorer_refresh = QPushButton("🔄 Fetch File System")
        self.btn_explorer_refresh.setStyleSheet("background-color: #2563eb; color: white; padding: 10px; font-weight: bold; border-radius: 4px;")
        self.btn_explorer_refresh.clicked.connect(self.start_explorer_fetch)
        toolbar.addWidget(self.btn_explorer_refresh)
        
        self.btn_explorer_delete = QPushButton("🗑️ Delete Selected")
        self.btn_explorer_delete.setStyleSheet("background-color: #dc2626; color: white; padding: 10px; font-weight: bold; border-radius: 4px;")
        self.btn_explorer_delete.clicked.connect(self.start_delete_thread)
        toolbar.addWidget(self.btn_explorer_delete)

        explorer_layout.addLayout(toolbar)
        
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(["Name", "Size (Bytes)", "Type"])
        self.tree_widget.setColumnWidth(0, 350)
        self.tree_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree_widget.setStyleSheet("""
            QTreeWidget { background-color: #1e1e1e; color: #e5e5e5; font-size: 14px; }
            QTreeWidget::item:selected { background-color: #3b82f6; }
            QHeaderView::section { background-color: #333333; color: white; padding: 4px; font-weight: bold; }
        """)
        explorer_layout.addWidget(self.tree_widget)

    def setup_flash_settings_tab(self):
        layout = QVBoxLayout(self.tab_flash_settings)
        
        info_label = QLabel("Configure esptool.py flash parameters.\nNote: Standard ESP32/WROOM modules require address 0x1000 and mode DIO.\nNewer S2/S3/C3 modules typically start at address 0x0.")
        info_label.setStyleSheet("color: #fbbf24; font-weight: bold; margin-bottom: 15px;")
        layout.addWidget(info_label)

        def add_setting(label_text, options, default_val, editable=False):
            row = QHBoxLayout()
            label = QLabel(label_text)
            label.setFixedWidth(150)
            
            combo = QComboBox()
            combo.addItems(options)
            if editable:
                combo.setEditable(True)
                
            idx = combo.findText(default_val)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            elif editable:
                combo.setCurrentText(default_val)
            
            combo.currentTextChanged.connect(lambda _: self.save_config())
            
            row.addWidget(label)
            row.addWidget(combo)
            layout.addLayout(row)
            return combo

        self.combo_flash_address = add_setting("Flash Address:",["0x0", "0x1000", "0x8000", "0x10000"], self.flash_address, editable=True)
        self.combo_flash_mode = add_setting("Flash Mode (-fm):",["keep", "dio", "qio", "dout", "qout"], self.flash_mode)
        self.combo_flash_size = add_setting("Flash Size (-fs):",["detect", "keep", "1MB", "2MB", "4MB", "8MB", "16MB", "32MB"], self.flash_size)
        self.combo_flash_freq = add_setting("Flash Freq (-ff):",["keep", "40m", "80m"], self.flash_freq)
        self.combo_flash_baud = add_setting("Baud Rate:",["115200", "230400", "460800", "921600", "2000000"], self.flash_baud)

        layout.addStretch()

    # --- FILE EXPLORER LOGIC ---
    def start_explorer_fetch(self):
        port = self.port_combo.currentData()
        if not port and self.env != "circuitpython":
            QMessageBox.warning(self, "Error", "No valid COM port selected!")
            return
            
        self.btn_explorer_refresh.setEnabled(False)
        self.btn_explorer_delete.setEnabled(False)
        self.btn_explorer_refresh.setText("Fetching File System...")
        
        thread = threading.Thread(target=self.fetch_file_system_thread, args=(port,), daemon=True)
        thread.start()

    def fetch_file_system_thread(self, port):
        # Disconnect REPL if currently connected
        if self.repl_serial and self.repl_serial.is_open:
            self.disconnect_repl()
            time.sleep(0.5)

        # Handle CircuitPython (Via USB Mass Storage)
        if self.env == "circuitpython":
            cp_drive = self.find_circuitpython_drive()
            if cp_drive:
                items =[]
                try:
                    for root, dirs, files in os.walk(cp_drive):
                        rel = os.path.relpath(root, cp_drive).replace('\\', '/')
                        if rel == '.': rel = ''
                        else: rel = '/' + rel
                        
                        for d in dirs:
                            p = f"{rel}/{d}" if rel else f"/{d}"
                            items.append({"p": p, "d": 1})
                        for f in files:
                            p = f"{rel}/{f}" if rel else f"/{f}"
                            try:
                                s = os.path.getsize(os.path.join(root, f))
                            except: s = 0
                            items.append({"p": p, "d": 0, "s": s})
                    
                    self.signals.explorer_update_signal.emit(items)
                    return
                except Exception as e:
                    self.signals.explorer_error_signal.emit(f"Failed parsing CircuitPython Drive:\n{e}")
                    return
            else:
                self.signals.explorer_error_signal.emit("Could not locate CircuitPython USB Drive.\nPlease ensure it is mounted to your PC.")
                return

        # Handle MicroPython (Via Raw REPL Serial)
        ser = None
        try:
            ser = self.connect_raw_repl(port)
            # This compact Python script uses BFS to read the entire ESP file system
            script = """import os,json
d=['/']
try:os.listdir('/')
except:d=['']
o=[]
while d:
 x=d.pop(0)
 try:
  for n in os.listdir(x):
   p=n if x=='' else ('/'+n if x=='/' else x+'/'+n)
   try:
    s=os.stat(p)
    if s[0]&0x4000:d.append(p);o.append({"p":p,"d":1})
    else:o.append({"p":p,"d":0,"s":s[6]})
   except:pass
 except:pass
print("===JSON_START==="+json.dumps(o)+"===JSON_END===")
"""
            out = self.exec_raw(ser, script).decode('utf-8', errors='ignore')
            self.exit_raw_repl(ser)
            
            match = re.search(r'===JSON_START===(.*?)===JSON_END===', out, re.DOTALL)
            if match:
                data = json.loads(match.group(1))
                self.signals.explorer_update_signal.emit(data)
            else:
                # Provide the raw output if JSON format failed to parse
                self.signals.explorer_error_signal.emit(f"Failed to extract JSON from board.\nBoard Output:\n{out}")
                
        except Exception as e:
            self.signals.explorer_error_signal.emit(str(e))
        finally:
            if ser and ser.is_open:
                try: ser.close()
                except: pass

    @Slot(list)
    def populate_explorer_tree(self, items):
        self.tree_widget.clear()
        nodes = {}
        
        # Sort so that parent directories appear before their files
        sorted_items = sorted(items, key=lambda x: x['p'])
        
        for item in sorted_items:
            path = item['p'].lstrip('/')
            is_dir = item['d'] == 1
            size = item.get('s', 0)
            
            parts = path.split('/')
            name = parts[-1]
            parent_path = '/'.join(parts[:-1])
            
            if parent_path == '':
                parent_item = self.tree_widget.invisibleRootItem()
            else:
                # Automatically construct missing parent directories if needed
                if parent_path not in nodes:
                    p_node = QTreeWidgetItem(self.tree_widget.invisibleRootItem(),[parent_path, "", "Folder"])
                    p_node.setData(0, Qt.ItemDataRole.UserRole, '/' + parent_path)
                    nodes[parent_path] = p_node
                parent_item = nodes[parent_path]
            
            display_name = f"📁 {name}" if is_dir else f"📄 {name}"
            node = QTreeWidgetItem(parent_item,[display_name, str(size) if not is_dir else "", "Folder" if is_dir else "File"])
            
            # Save absolute path to UserRole for interaction (deleting)
            node.setData(0, Qt.ItemDataRole.UserRole, '/' + path)
            nodes[path] = node
            
        self.tree_widget.expandAll()
        self.btn_explorer_refresh.setEnabled(True)
        self.btn_explorer_delete.setEnabled(True)
        self.btn_explorer_refresh.setText("🔄 Fetch File System")
        
    @Slot(str)
    def show_explorer_error(self, msg):
        QMessageBox.warning(self, "Explorer Error", f"Could not fetch file system:\n{msg}")
        self.btn_explorer_refresh.setEnabled(True)
        self.btn_explorer_delete.setEnabled(True)
        self.btn_explorer_refresh.setText("🔄 Fetch File System")

    # --- FILE DELETION LOGIC ---
    def start_delete_thread(self):
        selected_items = self.tree_widget.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "No Selection", "Please select one or more files/folders to delete.")
            return

        paths_to_delete =[]
        for item in selected_items:
            p = item.data(0, Qt.ItemDataRole.UserRole)
            if p:
                paths_to_delete.append(p)

        # Filter paths: If a parent folder is selected, skip deleting its children separately
        paths_to_delete.sort(key=len)
        filtered_paths =[]
        for p in paths_to_delete:
            # If `p` is not inside any already filtered (shorter) paths, keep it
            if not any(p.startswith(fp + '/') for fp in filtered_paths):
                filtered_paths.append(p)

        reply = QMessageBox.question(self, 'Confirm Delete', 
                                     f"Are you sure you want to completely delete {len(filtered_paths)} item(s) from the board?\nThis cannot be undone.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                                     QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.No:
            return

        port = self.port_combo.currentData()
        if not port and self.env != "circuitpython":
            QMessageBox.warning(self, "Error", "No valid COM port selected!")
            return

        self.btn_explorer_delete.setEnabled(False)
        self.btn_explorer_refresh.setEnabled(False)

        thread = threading.Thread(target=self.delete_items_thread, args=(port, filtered_paths), daemon=True)
        thread.start()

    def delete_items_thread(self, port, paths):
        if self.repl_serial and self.repl_serial.is_open:
            self.disconnect_repl()
            time.sleep(0.5)

        try:
            if self.env == "circuitpython":
                cp_drive = self.find_circuitpython_drive()
                if cp_drive:
                    for p in paths:
                        local_p = os.path.join(cp_drive, p.lstrip('/'))
                        if os.path.isdir(local_p):
                            shutil.rmtree(local_p)
                        elif os.path.exists(local_p):
                            os.remove(local_p)
                else:
                    self.signals.explorer_error_signal.emit("Could not locate CircuitPython drive for deletion.")
                    return
            else:
                ser = self.connect_raw_repl(port)
                
                # We inject the path strings directly into the MicroPython script 
                paths_json = json.dumps(paths)
                
                # Recursive deletion script that handles both files and directories
                script = f"""import os
def rm(p):
 try:
  if os.stat(p)[0]&0x4000:
   for f in os.listdir(p):rm(p+'/'+f)
   os.rmdir(p)
  else:os.remove(p)
 except:pass
for p in {paths_json}:rm(p)
"""
                self.exec_raw(ser, script)
                self.exit_raw_repl(ser)

        except Exception as e:
            self.signals.explorer_error_signal.emit(f"Error during deletion:\n{e}")
        finally:
            if 'ser' in locals() and ser and ser.is_open:
                try: ser.close()
                except: pass
            
            # Immediately trigger a refresh of the tree widget
            self.start_explorer_fetch()

    # --- REPL LOGIC ---
    @Slot(bool)
    def update_repl_btn_state(self, connected):
        if connected:
            self.btn_repl_connect.setText("Disconnect")
            self.btn_repl_connect.setStyleSheet("background-color: #7f1d1d; color: white; font-weight: bold;")
            self.port_combo.setEnabled(False)
            self.btn_refresh.setEnabled(False)
        else:
            self.btn_repl_connect.setText("Connect")
            self.btn_repl_connect.setStyleSheet("background-color: #166534; color: white; font-weight: bold;")
            self.port_combo.setEnabled(True)
            self.btn_refresh.setEnabled(True)

    @Slot(str)
    def update_repl_console(self, text):
        cursor = self.repl_console.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self.repl_console.setTextCursor(cursor)
        self.repl_console.ensureCursorVisible()

    @Slot()
    def auto_connect_repl(self):
        # Programmatically transition to the REPL tab and open the connection
        self.tabs.setCurrentWidget(self.tab_repl)
        if not (self.repl_serial and self.repl_serial.is_open) and not (self.repl_thread and self.repl_thread.is_alive()):
            port = self.port_combo.currentData()
            if port:
                self.repl_stop_event.clear()
                self.repl_thread = threading.Thread(target=self.repl_reader_thread, args=(port,), daemon=True)
                self.repl_thread.start()

    def toggle_repl_connection(self):
        if self.repl_serial and self.repl_serial.is_open:
            self.disconnect_repl()
        else:
            port = self.port_combo.currentData()
            if not port:
                QMessageBox.warning(self, "Error", "No valid COM port selected!")
                return
            self.repl_stop_event.clear()
            self.repl_thread = threading.Thread(target=self.repl_reader_thread, args=(port,), daemon=True)
            self.repl_thread.start()

    def disconnect_repl(self):
        self.repl_stop_event.set()

    def repl_reader_thread(self, port):
        self.signals.repl_state_signal.emit(True)
        self.signals.repl_signal.emit(f"\n--- Connected to {port} at 115200 baud ---\n")
        
        # Adding an Auto-Reconnect Loop for Native USB devices (ESP32-S3)
        while not self.repl_stop_event.is_set():
            try:
                # Open or Re-open the port
                if self.repl_serial is None or not self.repl_serial.is_open:
                    self.repl_serial = serial.Serial()
                    self.repl_serial.port = port
                    self.repl_serial.baudrate = 115200
                    self.repl_serial.timeout = 0.1
                    
                    # Setting DTR/RTS to False prior to open prevents the default PySerial behavior 
                    # from automatically asserting them and halting the ESP32.
                    self.repl_serial.dtr = False
                    self.repl_serial.rts = False
                    
                    self.repl_serial.open()

                    # Trigger a clean Hard Reset on REPL connect to ensure we get a fresh boot sequence
                    self.repl_serial.dtr = False
                    self.repl_serial.rts = True
                    time.sleep(0.1)
                    self.repl_serial.dtr = False
                    self.repl_serial.rts = False
                
                # Active Reading Loop
                while not self.repl_stop_event.is_set():
                    if self.repl_serial.in_waiting > 0:
                        data = self.repl_serial.read(self.repl_serial.in_waiting)
                        text = data.decode('utf-8', errors='replace')
                        self.signals.repl_signal.emit(text)
                    else:
                        time.sleep(0.01)
                        
            except (serial.SerialException, OSError):
                # An exception here means the port disconnected (e.g. Native USB Soft Reboot)
                if self.repl_serial:
                    try:
                        self.repl_serial.close()
                    except:
                        pass
                    self.repl_serial = None
                
                # Wait 0.5 seconds and loop back up to reconnect silently
                time.sleep(0.5)

        # Cleanup when explicitly disconnected by user
        if self.repl_serial and self.repl_serial.is_open:
            try:
                self.repl_serial.close()
            except:
                pass
        self.repl_serial = None
        self.signals.repl_state_signal.emit(False)
        self.signals.repl_signal.emit(f"\n--- Disconnected from {port} ---\n")

    def send_repl_command(self):
        cmd = self.repl_input.text()
        self.repl_input.clear()
        if self.repl_serial and self.repl_serial.is_open:
            try:
                self.repl_serial.write((cmd + '\r\n').encode('utf-8'))
            except Exception:
                # Silently catch exceptions in case Native USB drops mid-command
                pass

    def send_repl_bytes(self, b_val):
        if self.repl_serial and self.repl_serial.is_open:
            try:
                self.repl_serial.write(b_val)
            except Exception:
                pass

    # --- NATIVE RAW REPL PROTOCOL ---
    def connect_raw_repl(self, port):
        # Open port manually, preventing PySerial from asserting DTR/RTS out of the gate
        ser = serial.Serial()
        ser.port = port
        ser.baudrate = 115200
        ser.timeout = 3
        ser.dtr = False
        ser.rts = False
        ser.open()
        
        # Hard reset board to guarantee it's not permanently stuck before uploading
        self.signals.log_signal.emit("[SYSTEM] Hard resetting board to ensure clean state...")
        ser.dtr = False
        ser.rts = True
        time.sleep(0.1)
        ser.dtr = False
        ser.rts = False
        
        self.signals.log_signal.emit("[SYSTEM] Waiting 1.5s for board to finish booting...")
        time.sleep(1.5)  
        
        self.signals.log_signal.emit("[SYSTEM] Injecting Halt sequence...")
        
        # 1. Exit Raw REPL if it was previously stuck there
        ser.write(b'\r\x02') 
        time.sleep(0.1)
        
        # 2. Send multiple Ctrl-C interrupts with delays (fast bursts are sometimes ignored)
        for _ in range(5):
            ser.write(b'\r\x03')
            time.sleep(0.1)
            
        ser.reset_input_buffer()
        
        self.signals.log_signal.emit("[SYSTEM] Entering Raw REPL Mode...")
        ser.write(b'\r\x01') 
        
        # 3. Look for the "raw REPL" text instead of the strict exact prompt
        resp = ser.read_until(b'raw REPL')
        if b'raw REPL' not in resp:
            ser.close()
            # 4. Include the board's actual response in the exception for debugging
            resp_str = resp.decode('utf-8', errors='ignore').strip()
            raise Exception(f"Failed to enter Raw REPL.\nBoard Response: '{resp_str}'\nThe board might be completely frozen. Try manually resetting it.")
            
        # Consume the rest of the prompt up to the '>' char
        ser.read_until(b'>')
            
        return ser

    def exit_raw_repl(self, ser):
        if ser and ser.is_open:
            ser.write(b'\x02') 
            time.sleep(0.1)

    def exec_raw(self, ser, cmd_str):
        ser.reset_input_buffer()
        
        ser.write(cmd_str.encode('utf-8'))
        ser.write(b'\x04')
        
        resp = ser.read_until(b'OK')
        if not resp.endswith(b'OK'):
            time.sleep(0.1)
            err_dump = ser.read(ser.in_waiting).decode('utf-8', errors='ignore').strip()
            raise Exception(f"Raw REPL failed to compile the command. Response: {err_dump}")
            
        out = ser.read_until(b'\x04')[:-1]
        err = ser.read_until(b'\x04')[:-1]
        ser.read_until(b'>')
        
        if err:
            raise Exception(f"Device error: {err.decode('utf-8', errors='ignore')}")
            
        return out

    def upload_file_mp(self, ser, local_path, remote_path):
        self.signals.log_signal.emit(f"[RUNNING] Writing: {remote_path}")
        with open(local_path, "rb") as f:
            data = f.read()
            
        import binascii
        hex_data = binascii.hexlify(data).decode('ascii')
        
        self.exec_raw(ser, f"f = open('{remote_path}', 'wb')")
        self.exec_raw(ser, "import binascii")
        
        chunk_size = 64
        for i in range(0, len(hex_data), chunk_size):
            chunk = hex_data[i:i+chunk_size]
            self.exec_raw(ser, f"f.write(binascii.unhexlify('{chunk}'))")
            
        self.exec_raw(ser, "f.close()")
        self.signals.log_signal.emit(f"    -> [SUCCESS] Uploaded {len(data)} bytes.")

    def upload_dir_mp(self, ser, local_dir, remote_dir):
        self.signals.log_signal.emit(f"[SYSTEM] Creating remote directory: {remote_dir}")
        self.exec_raw(ser, f"import os\ntry:\n    os.mkdir('{remote_dir}')\nexcept:\n    pass")
        
        for item in os.listdir(local_dir):
            l_path = os.path.join(local_dir, item)
            r_path = f"{remote_dir}/{item}"
            if os.path.isdir(l_path):
                self.upload_dir_mp(ser, l_path, r_path)
            else:
                self.upload_file_mp(ser, l_path, r_path)

    # --- GENERAL UPLOADER LOGIC ---
    def on_env_changed(self):
        if self.rb_circuit.isChecked():
            self.env = "circuitpython"
        else:
            self.env = "micropython"
            
        self.update_button_ui('main')
        self.save_config()

    def on_preserve_names_changed(self):
        self.save_config()
        self.update_button_ui('boot')
        self.update_button_ui('main')
        self.update_button_ui('lib')

    def update_button_ui(self, target):
        path = getattr(self, f"{target}_path", "")
        btn = getattr(self, f"btn_{target}")
        
        main_script_name = "code.py" if self.env == "circuitpython" else "main.py"
        
        default_texts = {
            'root_folder': "📁 Select Root Folder (Uploads all contents to root)",
            'boot': "📄 Select Source for boot.py",
            'main': f"📄 Select Source for {main_script_name}",
            'lib': "📁 Select Entire 'lib' Folder",
            'firmware': "📁 Select Firmware (.bin file)"
        }
        
        if path:
            filename = os.path.basename(path)
            if target == 'lib' or target == 'root_folder':
                parent_dir = os.path.basename(os.path.dirname(path))
                display_name = f"{parent_dir}/{filename}" if parent_dir else filename
                btn.setText(f"✅ {target}: {display_name}")
            elif target == 'main':
                if hasattr(self, 'cb_preserve_names') and self.cb_preserve_names.isChecked():
                    btn.setText(f"✅ main source: {filename}")
                else:
                    btn.setText(f"✅ {main_script_name}: {filename}")
            else:
                btn.setText(f"✅ {target}: {filename}")
            btn.setStyleSheet("padding: 8px; background-color: #15803d; color: white; border-radius: 4px;")
        else:
            btn.setText(default_texts.get(target, f"Select {target}"))
            btn.setStyleSheet("padding: 8px; background-color: #2d3748; color: white; border-radius: 4px;")

    @Slot()
    def check_for_port_changes(self):
        """Periodically checks for changes in connected COM ports and refreshes the list if needed."""
        if self.repl_serial and self.repl_serial.is_open:
            return # Don't refresh while REPL is actively connected
        try:
            current_port_devices = [port.device for port in serial.tools.list_ports.comports()]
            if set(current_port_devices) != set(self.known_ports):
                self.signals.log_signal.emit("[SYSTEM] COM port change detected. Refreshing list...")
                self.refresh_ports()
        except Exception:
            # This can fail transiently when a device is being enumerated.
            pass

    def refresh_ports(self):
        """Updates the COM port dropdown list, preserving the selection if possible."""
        current_selection = self.port_combo.currentData()
        
        self.port_combo.clear()
        ports = serial.tools.list_ports.comports()
        
        self.known_ports = [port.device for port in ports]
        
        if not ports:
            self.port_combo.addItem("No COM ports found", None)
            return

        new_selection_index = -1
        for i, port in enumerate(ports):
            self.port_combo.addItem(f"{port.device} - {port.description}", port.device)
            if port.device == current_selection:
                new_selection_index = i
        
        if new_selection_index != -1:
            self.port_combo.setCurrentIndex(new_selection_index)

    @Slot(str)
    def update_terminal(self, text):
        self.terminal.appendPlainText(text)
        self.terminal.verticalScrollBar().setValue(self.terminal.verticalScrollBar().maximum())
        
    @Slot(str)
    def update_last_line_in_terminal(self, text):
        cursor = self.terminal.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
        cursor.removeSelectedText()
        cursor.insertText(text)
        self.terminal.ensureCursorVisible()

    def select_file(self, target):
        script_name = "code.py" if (target == 'main' and self.env == "circuitpython") else f"{target}.py"
        path, _ = QFileDialog.getOpenFileName(self, f"Select {script_name}", "", "Python Files (*.py)")
        
        if path:
            setattr(self, f"{target}_path", path)
            self.signals.log_signal.emit(f"[SYSTEM] Selected {path} as source for {script_name}")
            self.update_button_ui(target)
            self.save_config()

    def select_folder(self, target):
        path = QFileDialog.getExistingDirectory(self, f"Select {target} folder")
        if path:
            setattr(self, f"{target}_path", path)
            self.signals.log_signal.emit(f"[SYSTEM] Selected folder {path} for {target}")
            self.update_button_ui(target)
            self.save_config()

    def select_firmware_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Firmware File", "", "Binary Files (*.bin)")
        if path:
            self.firmware_path = path
            self.signals.log_signal.emit(f"[SYSTEM] Selected firmware: {path}")
            self.update_button_ui('firmware')
            self.save_config()

    def clear_path(self, target):
        setattr(self, f"{target}_path", "")
        self.signals.log_signal.emit(f"[SYSTEM] Cleared {target} selection.")
        self.update_button_ui(target)
        self.save_config()

    def set_ui_enabled(self, enabled):
        self.btn_upload.setEnabled(enabled)
        self.btn_flash.setEnabled(enabled)
        self.btn_refresh.setEnabled(enabled)
        self.port_combo.setEnabled(enabled)
        self.rb_micro.setEnabled(enabled)
        self.rb_circuit.setEnabled(enabled)
        self.cb_preserve_names.setEnabled(enabled)
        self.btn_explorer_refresh.setEnabled(enabled)
        if hasattr(self, 'btn_explorer_delete'):
            self.btn_explorer_delete.setEnabled(enabled)
        
        for target in['root_folder', 'boot', 'main', 'lib', 'firmware']:
            getattr(self, f"btn_{target}").setEnabled(enabled)
            getattr(self, f"btn_clear_{target}").setEnabled(enabled)
            
        # Enable/Disable Flash Setting widgets
        for widget in[self.combo_flash_address, self.combo_flash_mode, self.combo_flash_size, self.combo_flash_freq, self.combo_flash_baud]:
            widget.setEnabled(enabled)

    def start_upload_thread(self):
        port = self.port_combo.currentData()
        if not port:
            QMessageBox.warning(self, "Error", "No valid COM port selected!")
            return
        
        if not any([self.root_folder_path, self.boot_path, self.main_path, self.lib_path]):
            QMessageBox.warning(self, "Error", "No scripts or folders selected to upload!")
            return
            
        self.terminal.clear()
        self.set_ui_enabled(False)
        thread = threading.Thread(target=self.run_script_upload, args=(port,), daemon=True)
        thread.start()

    def start_flash_thread(self):
        port = self.port_combo.currentData()
        if not port:
            QMessageBox.warning(self, "Error", "No valid COM port selected!")
            return
        if not self.firmware_path:
            QMessageBox.warning(self, "Error", "No firmware .bin file selected!")
            return
        reply = QMessageBox.question(self, 'Confirm Action', 
                                     "This will ERASE EVERYTHING on the ESP32 and install new firmware. Are you sure you want to continue?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.No:
            return
            
        self.terminal.clear()
        self.set_ui_enabled(False)
        
        # Grab GUI values securely before dispatching to thread
        flash_params = {
            "baud": self.combo_flash_baud.currentText(),
            "addr": self.combo_flash_address.currentText(),
            "mode": self.combo_flash_mode.currentText(),
            "size": self.combo_flash_size.currentText(),
            "freq": self.combo_flash_freq.currentText()
        }
        
        thread = threading.Thread(target=self.run_firmware_flash, args=(port, flash_params), daemon=True)
        thread.start()

    def find_circuitpython_drive(self):
        if sys.platform == 'win32':
            import ctypes
            import string
            volume_name_buf = ctypes.create_unicode_buffer(1024)
            for letter in string.ascii_uppercase:
                drive = f"{letter}:\\"
                if os.path.exists(drive):
                    try:
                        ctypes.windll.kernel32.GetVolumeInformationW(
                            ctypes.c_wchar_p(drive),
                            volume_name_buf,
                            ctypes.sizeof(volume_name_buf),
                            None, None, None, None, 0
                        )
                        if volume_name_buf.value == 'CIRCUITPY':
                            return drive
                    except:
                        pass
            for letter in string.ascii_uppercase:
                if os.path.exists(os.path.join(f"{letter}:\\", "boot_out.txt")):
                    return f"{letter}:\\"
        elif sys.platform == 'darwin':
            if os.path.exists('/Volumes/CIRCUITPY'):
                return '/Volumes/CIRCUITPY'
        else:
            import getpass
            user = getpass.getuser()
            paths =[
                f'/media/{user}/CIRCUITPY',
                f'/run/media/{user}/CIRCUITPY',
                '/mnt/CIRCUITPY'
            ]
            for p in paths:
                if os.path.exists(p):
                    return p
        return None

    def run_command(self, cmd):
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                                   text=True, bufsize=1, universal_newlines=True,
                                   creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
        for line in iter(process.stdout.readline, ''):
            self.signals.log_signal.emit(line.strip())
        process.wait()
        return process.returncode

    def run_script_upload(self, port):
        if self.repl_serial and self.repl_serial.is_open:
            self.signals.log_signal.emit("[SYSTEM] Auto-disconnecting REPL to free COM port...")
            self.disconnect_repl()
            time.sleep(0.5)

        tasks =[]
        preserve = self.cb_preserve_names.isChecked()

        if self.root_folder_path:
            for item in os.listdir(self.root_folder_path):
                local_path = os.path.join(self.root_folder_path, item)
                remote_name = item
                if not preserve:
                    if self.env == "circuitpython" and item == "main.py": remote_name = "code.py"
                    elif self.env == "micropython" and item == "code.py": remote_name = "main.py"
                tasks.append((local_path, remote_name, os.path.isdir(local_path)))

        if self.boot_path: 
            tasks.append((self.boot_path, os.path.basename(self.boot_path) if preserve else "boot.py", False))
        if self.main_path:
            tasks.append((self.main_path, os.path.basename(self.main_path) if preserve else ("code.py" if self.env == "circuitpython" else "main.py"), False))
        if self.lib_path: 
            tasks.append((self.lib_path, os.path.basename(self.lib_path) if preserve else "lib", True))
        
        if self.env == "circuitpython":
            cp_drive = self.find_circuitpython_drive()
            if not cp_drive:
                self.signals.log_signal.emit("[FATAL] Could not find CIRCUITPY mounted USB drive.\n")
                self.set_ui_enabled(True)
                return
                
            try:
                self.signals.log_signal.emit("[SYSTEM] Automatically clearing any existing main.py or code.py...")
                for target_file in["main.py", "code.py"]:
                    target_path = os.path.join(cp_drive, target_file)
                    if os.path.exists(target_path):
                        os.remove(target_path)
                        self.signals.log_signal.emit(f"    -> [SUCCESS] Deleted {target_file}")
                        
                for local, remote, is_dir in tasks:
                    self.signals.log_signal.emit(f"[RUNNING] Uploading {local} -> {remote} ...")
                    dest_path = os.path.join(cp_drive, remote)
                    if is_dir:
                        if os.path.exists(dest_path): shutil.rmtree(dest_path)
                        shutil.copytree(local, dest_path)
                    else:
                        shutil.copy2(local, dest_path)
                    self.signals.log_signal.emit(f"[SUCCESS] Finished {remote}\n")
                self.signals.log_signal.emit("[DONE] All script operations completed.")
            except Exception as e:
                self.signals.log_signal.emit(f"[EXCEPTION] {str(e)}")

        else:
            ser = None
            try:
                self.signals.log_signal.emit(f"[SYSTEM] Connecting natively to {port}...")
                ser = self.connect_raw_repl(port)
                self.signals.log_signal.emit("[SYSTEM] Connection established successfully.\n")
                
                self.signals.log_signal.emit("[SYSTEM] Automatically clearing any existing main.py or code.py...")
                del_script = "import os\ntry: os.remove('main.py')\nexcept: pass\ntry: os.remove('code.py')\nexcept: pass"
                self.exec_raw(ser, del_script)
                self.signals.log_signal.emit("    ->[SUCCESS] Deletion sequence executed.")

                for local, remote, is_dir in tasks:
                    if is_dir:
                        self.upload_dir_mp(ser, local, remote)
                    else:
                        self.upload_file_mp(ser, local, remote)
                
                self.signals.log_signal.emit("\n[SYSTEM] Triggering Hard Reboot...")
                self.exit_raw_repl(ser)
                
                # Perform Hard reset post-upload to execute scripts from a fully flushed boot state
                time.sleep(0.1)
                ser.dtr = False
                ser.rts = True
                time.sleep(0.1)
                ser.dtr = False
                ser.rts = False
                time.sleep(0.5)
                
                self.signals.log_signal.emit("[DONE] Scripts uploaded and board rebooted.")
                
            except Exception as e:
                self.signals.log_signal.emit(f"[EXCEPTION] Upload Failed: {str(e)}")
            finally:
                if ser and ser.is_open:
                    try:
                        ser.close()
                    except:
                        pass
            
        self.set_ui_enabled(True)
        # Automatically connect to REPL after update finishes
        self.signals.auto_connect_repl_signal.emit()

    def run_firmware_flash(self, port, flash_params):
        if self.repl_serial and self.repl_serial.is_open:
            self.signals.log_signal.emit("[SYSTEM] Auto-disconnecting REPL to free COM port...")
            self.disconnect_repl()
            time.sleep(0.5)

        filename = os.path.basename(self.firmware_path).lower()
        chip_type = "auto"
        if "esp32s3" in filename or "esp32_s3" in filename or "esp32-s3" in filename: chip_type = "esp32s3"
        elif "esp32s2" in filename or "esp32_s2" in filename or "esp32-s2" in filename: chip_type = "esp32s2"
        elif "esp32c3" in filename or "esp32_c3" in filename or "esp32-c3" in filename: chip_type = "esp32c3"
        elif "esp32c6" in filename or "esp32_c6" in filename or "esp32-c6" in filename: chip_type = "esp32c6"
        elif "esp32h2" in filename or "esp32_h2" in filename or "esp32-h2" in filename: chip_type = "esp32h2"
        elif "esp8266" in filename: chip_type = "esp8266"
        elif "esp32" in filename: chip_type = "esp32"

        self.signals.log_signal.emit("--- Starting Firmware Flash ---")
        try:
            self.signals.log_signal.emit(f"[RUNNING] Erasing flash on {port}...")
            erase_cmd =[sys.executable, "-m", "esptool"]
            if chip_type != "auto": erase_cmd.extend(["--chip", chip_type])
            erase_cmd.extend(["--port", port, "erase-flash"])
            if self.run_command(erase_cmd) != 0: raise Exception("esptool erase-flash failed.")
            
            time.sleep(1)

            self.signals.log_signal.emit(f"[RUNNING] Writing firmware: {self.firmware_path} at {flash_params['addr']}...")
            
            # Construct the dynamic flash command based on the UI settings
            write_cmd =[sys.executable, "-m", "esptool"]
            if chip_type != "auto": write_cmd.extend(["--chip", chip_type])
            write_cmd.extend([
                "--port", port, 
                "--baud", flash_params['baud'], 
                "write-flash", "-z",
                "--flash-mode", flash_params['mode'],
                "--flash-size", flash_params['size'],
                "--flash-freq", flash_params['freq'],
                flash_params['addr'], self.firmware_path
            ])
            
            if self.run_command(write_cmd) != 0: raise Exception("esptool write_flash failed.")
            
            self.signals.log_signal.emit("\n[SUCCESS] New firmware flashed successfully.")
        except Exception as e:
            self.signals.log_signal.emit(f"[EXCEPTION] An error occurred: {str(e)}")
            
        self.set_ui_enabled(True)
        # Automatically connect to REPL after flash completes
        self.signals.auto_connect_repl_signal.emit()

def main():
    app = QApplication.instance()
    is_standalone = False
    
    if not app:
        app = QApplication(sys.argv)
        is_standalone = True

    app.setStyle("Fusion")
    dark_palette = QPalette()
    dark_palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
    dark_palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
    dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 255))
    dark_palette.setColor(QPalette.ColorRole.ToolTipText, QColor(255, 255, 255))
    dark_palette.setColor(QPalette.ColorRole.Text, QColor(255, 255, 255))
    dark_palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
    dark_palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
    dark_palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))
    app.setPalette(dark_palette)

    ex = ESP32Uploader()
    if is_standalone:
        ex.showMaximized()
        sys.exit(app.exec())
    else:
        ex.setAttribute(Qt.WA_DeleteOnClose)
        loop = QEventLoop()
        ex.destroyed.connect(loop.quit)
        ex.showMaximized()
        loop.exec()

if __name__ == '__main__':
    main()