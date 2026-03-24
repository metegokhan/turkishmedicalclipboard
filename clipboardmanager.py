#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gelişmiş Clipboard Manager - Python Versiyonu
Tüm özellikleri içeren modern clipboard yöneticisi
Komut çalıştırma özelliği eklendi.
"""

import sys
import os

# PyInstaller exe'si içinden diğer Python scriptlerini çalıştırmak için özel handler
# EXE çalıştırıldığında argüman olarak --run-script verilmişse, verilen dosyayı çalıştır
if getattr(sys, 'frozen', False) and len(sys.argv) >= 3 and sys.argv[1] == '--run-script':
    script_path = sys.argv[2]
    # PyInstaller'ın kütüphaneleri exe'ye dahil etmesi için dummy importları burada kullanabiliriz
    try:
        import tkinter
        from tkinter import messagebox
        import win32gui
        import webbrowser
        import tempfile
    except:
        pass
    
    try:
        with open(script_path, 'r', encoding='utf-8') as f:
            code = f.read()
        exec(code, {'__name__': '__main__', '__file__': script_path})
    except Exception as e:
        import traceback
        traceback.print_exc()
    sys.exit(0)
import json
import re
import time
import threading
import subprocess
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple
import uuid
from pathlib import Path

# PyQt5 imports
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QScrollArea, QFrame, QTextEdit, QLineEdit,
    QSystemTrayIcon, QMenu, QAction, QDialog, QComboBox, QTabWidget,
    QListWidget, QListWidgetItem, QMessageBox, QShortcut, QGraphicsDropShadowEffect,
    QCheckBox, QSpinBox, QFontComboBox
)
from PyQt5.QtCore import (
    Qt, QTimer, pyqtSignal, QThread, QRect, QPoint, QSize,
    QPropertyAnimation, QEasingCurve, QEvent, pyqtSlot
)
from PyQt5.QtGui import (
    QIcon, QPixmap, QPainter, QColor, QFont, QKeySequence,
    QPalette, QBrush, QLinearGradient, QCursor, QMouseEvent,
    QPen
)

# Diğer kütüphaneler
import pyperclip

try:
    import keyboard

    KEYBOARD_AVAILABLE = True
except ImportError:
    KEYBOARD_AVAILABLE = False
    print("keyboard modülü yüklenemedi, global kısayollar devre dışı")

import pyautogui
from pathlib import Path

# Çalışma dizinini sabitleme (PyInstaller --onefile desteği için)
if getattr(sys, 'frozen', False):
    os.chdir(os.path.dirname(sys.executable))
else:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))


# Veri yapıları
@dataclass
class ClipboardRule:
    id: str
    name: str
    regex: str
    display_template: str
    shortcut: Optional[str] = None
    action: str = "paste"  # Eylemler: paste, openUrl, customScript
    group: str = "Genel"


@dataclass
class ClipboardItem:
    id: str
    text: str
    original_text: str
    display_text: str
    timestamp: float
    rule: ClipboardRule
    shortcut: Optional[str] = None
    drug_info: Optional[Dict] = None


@dataclass
class ItemGroup:
    id: str
    group_name: str
    display_name: str
    items: List[ClipboardItem] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)
    shortcut: Optional[str] = None
    collapsed: bool = False
    group_action: str = "pasteAll"


@dataclass
class Snippet:
    id: str
    name: str
    content: str = ""  # Artık opsiyonel, varsayılan boş string
    shortcut: Optional[str] = None
    category: str = "Genel"
    action_type: str = "paste"  # 'paste', 'execute_command', 'execute_python'
    command: Optional[str] = None  # Çalıştırılacak komut
    python_code: Optional[str] = None  # Python kodu


@dataclass
class PinnedItem:
    id: str
    original_text: str
    display_text: str
    shortcut: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    rule: Optional[ClipboardRule] = None
    drug_info: Optional[Dict] = None


# Mini ikon widget
class MiniIcon(QWidget):
    """Mini pencere için özel ikon widget"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.hover = False

    def enterEvent(self, event):
        self.hover = True
        self.update()

    def leaveEvent(self, event):
        self.hover = False
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self.hover:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, 80))
            painter.drawEllipse(2, 2, 58, 58)

        gradient = QLinearGradient(0, 0, 60, 60)
        gradient.setColorAt(0, QColor(33, 150, 243, 230))
        gradient.setColorAt(1, QColor(25, 118, 210, 230))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(5, 5, 50, 50)

        painter.setBrush(QColor(255, 255, 255, 40))
        painter.drawEllipse(8, 8, 44, 44)

        painter.setPen(QPen(Qt.white, 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(18, 22, 24, 28, 3, 3)
        painter.drawRect(23, 17, 14, 8)
        painter.setBrush(Qt.white)
        painter.drawRect(25, 16, 10, 6)

        painter.setPen(QPen(Qt.white, 1.5))
        painter.drawLine(22, 30, 38, 30)
        painter.drawLine(22, 35, 35, 35)
        painter.drawLine(22, 40, 36, 40)


# Clipboard İzleyici Thread
class ClipboardMonitor(QThread):
    new_clip = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.last_text = ""
        self.running = True

    def run(self):
        while self.running:
            try:
                current_text = pyperclip.paste()
                if current_text and current_text != self.last_text and len(current_text.strip()) > 1:
                    self.last_text = current_text
                    self.new_clip.emit(current_text)
            except Exception as e:
                print(f"Clipboard okuma hatası: {e}")
            time.sleep(0.5)

    def stop(self):
        self.running = False


# Özel Widget'lar
class ClipboardItemWidget(QFrame):
    clicked = pyqtSignal()
    copy_clicked = pyqtSignal()
    pin_clicked = pyqtSignal()
    delete_clicked = pyqtSignal()
    paste_clicked = pyqtSignal()

    def __init__(self, item: ClipboardItem, parent=None):
        super().__init__(parent)
        self.item = item
        self.folded = len(item.original_text) > 200 or item.original_text.count('\n') > 5
        self.settings = parent.settings if parent and hasattr(parent, 'settings') else {}
        self.setup_ui()

    def setup_ui(self):
        self.setFrameStyle(QFrame.StyledPanel)
        widget_text_color = self.settings.get('appearance', {}).get('textColor', '#FFFFFF')

        # Yeni renk şeması
        self.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(30, 30, 46, 0.85); /* Catppuccin Base */
                border-radius: 8px;
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-left: 4px solid #8B5CF6;  /* Violet Vurgu */
                padding: 4px;
                margin: 2px;
            }}
            QFrame:hover {{
                background-color: rgba(49, 50, 68, 0.95); /* Surface0 */
                border-left: 4px solid #A78BFA;
                border: 1px solid rgba(139, 92, 246, 0.3);
            }}
            QLabel {{ 
                background-color: transparent;
            }}
            QPushButton {{
                background-color: rgba(255, 255, 255, 0.05);
                color: #CDD6F4; 
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 4px;
                padding: 2px;
                font-weight: bold;
                min-width: 25px;
                max-width: 30px;
            }}
            QPushButton:hover {{
                background-color: rgba(139, 92, 246, 0.2);
                border: 1px solid #8B5CF6;
                color: white;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(2)

        top_layout = QHBoxLayout()
        top_layout.setSpacing(4)

        # BAŞLIK CONTAINER - BEYAZ BORDER
        title_container = QFrame()
        title_container.setStyleSheet("""
            QFrame {
                background-color: transparent;
                border-radius: 4px;
                border: none;
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
                padding: 2px;
                margin: 0px;
            }
        """)
        title_container_layout = QHBoxLayout(title_container)
        title_container_layout.setContentsMargins(2, 2, 2, 2)

        title_text = self.item.original_text[:10] + ("..." if len(self.item.original_text) > 10 else "")
        title = QLabel(title_text)
        base_font_size = self.settings.get('appearance', {}).get('fontSize', 12)
        title.setStyleSheet(f"""
            color: #FFFFFF; 
            font-weight: bold; 
            font-size: {base_font_size + 1}px;
            background-color: transparent;
            border: none;
        """)
        title.setWordWrap(True)
        title.setMaximumWidth(100)
        title_container_layout.addWidget(title, 1)

        # Butonlar container - SAĞ TARAfA SABİTLENMİŞ
        buttons_container = QWidget()
        buttons_container.setFixedWidth(90)  # Sabit genişlik: 3 buton + boşluklar
        buttons_layout = QHBoxLayout(buttons_container)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(6)  # Sabit 3px boşluk

        paste_btn = QPushButton("📋")
        paste_btn.setToolTip("Akıllı Yapıştır")
        paste_btn.clicked.connect(self.paste_clicked.emit)
        paste_btn.setFixedSize(28, 24)  # Sabit boyut

        pin_btn = QPushButton("📌")
        pin_btn.setToolTip("Sabitle")
        pin_btn.clicked.connect(self.pin_clicked.emit)
        pin_btn.setFixedSize(28, 24)  # Sabit boyut

        delete_btn = QPushButton("×")
        delete_btn.setToolTip("Sil")
        delete_btn.clicked.connect(self.delete_clicked.emit)
        delete_btn.setFixedSize(28, 24)  # Sabit boyut
        delete_btn.setStyleSheet("""
            QPushButton { color: #F38BA8; border: 1px solid rgba(243, 139, 168, 0.2); background-color: rgba(243, 139, 168, 0.1); }
            QPushButton:hover { background-color: rgba(243, 139, 168, 0.3); border: 1px solid #F38BA8; color: white; }
        """)

        buttons_layout.addWidget(paste_btn)
        buttons_layout.addWidget(pin_btn)
        buttons_layout.addWidget(delete_btn)
        title_container_layout.addWidget(buttons_container)
        layout.addWidget(title_container)

        # İÇERİK CONTAINER - SARI BORDER
        content_container = QFrame()
        item_bg_color = self.settings.get('appearance', {}).get('itemBgColor', 'rgba(24, 24, 37, 0.6)')
        content_container.setStyleSheet(f"""
            QFrame {{
                background-color: {item_bg_color}; /* Mantle */
                border-radius: 6px;
                border: 1px solid rgba(255, 255, 255, 0.03);
                border-left: 3px solid #89B4FA;  /* Mavi accent */
                padding: 6px 8px;
                margin: 2px 0px;
            }}
        """)
        content_container_layout = QVBoxLayout(content_container)
        content_container_layout.setContentsMargins(2, 2, 2, 2)

        preview_text_content = self.item.original_text
        if self.folded and len(preview_text_content) > 100:
            preview_text_content = preview_text_content[:100] + "..."

        self.preview = QLabel(preview_text_content.replace('\n', '<br>'))
        self.preview.setWordWrap(True)
        base_font_size = self.settings.get('appearance', {}).get('fontSize', 12)
        font_family = self.settings.get('appearance', {}).get('fontFamily', '')
        font_family_css = f"font-family: '{font_family}';" if font_family else ""
        self.preview.setStyleSheet(f"""
            color: #F1C40F; 
            font-size: {base_font_size - 1}px;
            {font_family_css}
            background-color: transparent;
            border: none;
        """)
        content_container_layout.addWidget(self.preview)
        layout.addWidget(content_container)

        # META CONTAINER - KIRMIZI BORDER
        meta_container = QFrame()
        meta_container.setStyleSheet("""
            QFrame {
                background-color: transparent;
                border: none;
                padding: 2px 6px;
                margin: 0px;
            }
        """)
        meta_container_layout = QVBoxLayout(meta_container)
        meta_container_layout.setContentsMargins(2, 2, 2, 2)

        meta_text_content_str = f"{self._format_time(self.item.timestamp)}"
        if self.item.shortcut:
            meta_text_content_str += f" • {self.item.shortcut}"

        meta_label = QLabel(meta_text_content_str)
        base_font_size = self.settings.get('appearance', {}).get('fontSize', 12)
        meta_label.setStyleSheet(f"""
            color: #E74C3C; 
            font-size: {base_font_size - 2}px; 
            font-style: italic;
            background-color: transparent;
            border: none;
        """)
        meta_label.setWordWrap(True)
        meta_label.setMaximumWidth(180)
        meta_container_layout.addWidget(meta_label)
        layout.addWidget(meta_container)

        # İlaç bilgisi varsa ekle (MOR border ile)
        if self.item.drug_info:
            drug_info = self.item.drug_info

            drug_frame = QFrame()
            drug_frame.setStyleSheet("""
                QFrame {
                    background-color: rgba(203, 166, 247, 0.1);
                    border-radius: 6px;
                    border: 1px solid rgba(203, 166, 247, 0.2);
                    border-left: 3px solid #CBA6F7;  /* Mauve */
                    padding: 6px;
                    margin: 2px 0px;
                }
            """)
            drug_layout = QVBoxLayout(drug_frame)
            drug_layout.setContentsMargins(4, 2, 4, 2)
            drug_layout.setSpacing(2)

            # İlaç adı - MOR ve KALIN
            drug_name_label = QLabel(f"<b>💊 {drug_info['name']}</b>")
            drug_name_label.setWordWrap(True)
            base_font_size = self.settings.get('appearance', {}).get('fontSize', 12)
            drug_name_label.setStyleSheet(f"""
                color: #9b59b6; 
                font-size: {base_font_size}px; 
                font-weight: bold;
                background-color: transparent;
            """)
            drug_layout.addWidget(drug_name_label)

            # ATC bilgisi - KOYU MOR
            if drug_info.get('atc_code'):
                atc_label = QLabel(f"ATC: {drug_info['atc_code']} - {drug_info.get('atc_name', '')}")
                atc_label.setWordWrap(True)
                base_font_size = self.settings.get('appearance', {}).get('fontSize', 12)
                atc_label.setStyleSheet(f"""
                    color: #8e44ad; 
                    font-size: {base_font_size - 1}px; 
                    font-style: italic;
                    background-color: transparent;
                """)
                drug_layout.addWidget(atc_label)

            # ICD kodları - KOYU MOR
            if drug_info.get('icd_codes'):
                icd_list = drug_info['icd_codes']
                if len(icd_list) > 8:
                    icd_text = "ICD: " + ", ".join(icd_list[:8]) + f" (+{len(icd_list) - 8} daha)"
                else:
                    icd_text = "ICD: " + ", ".join(icd_list)

                icd_label = QLabel(icd_text)
                icd_label.setWordWrap(True)
                base_font_size = self.settings.get('appearance', {}).get('fontSize', 12)
                icd_label.setStyleSheet(f"""
                    color: #8e44ad; 
                    font-size: {base_font_size - 1}px;
                    background-color: transparent;
                """)
                drug_layout.addWidget(icd_label)

            layout.addWidget(drug_frame)

        self.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                self.toggle_fold()
                return True
            elif event.button() == Qt.RightButton:
                self.copy_clicked.emit()
                return True
        return super().eventFilter(obj, event)

    def toggle_fold(self):
        self.folded = not self.folded
        preview_text_val = self.item.original_text
        if self.folded and len(preview_text_val) > 100:
            preview_text_val = preview_text_val[:100] + "..."
        self.preview.setText(preview_text_val.replace('\n', '<br>'))

    def _format_time(self, timestamp_val):
        now = datetime.now()
        item_time = datetime.fromtimestamp(timestamp_val)
        diff = now - item_time

        if diff.total_seconds() < 60:
            return "şimdi"
        elif diff.total_seconds() < 3600:
            return f"{int(diff.total_seconds() // 60)}d önce"
        elif diff.days == 0:
            return f"{int(diff.total_seconds() // 3600)}s önce"
        else:
            return item_time.strftime("%d.%m.%Y")


# Ana Pencere
class ClipboardManagerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.groups: List[ItemGroup] = []
        self.pinned_items: List[PinnedItem] = []
        self.snippets: List[Snippet] = []
        self.rules: List[ClipboardRule] = []
        self.settings = {}
        self.used_shortcuts = set()
        self.is_minimized = False
        self.normal_geometry = None
        self.old_pos = None
        self.resize_start_pos = None

        # Mini mod sürükleme durumu için değişkenler
        self.mini_dragging = False
        self.mini_drag_offset = None
        self.mini_press_global_pos = None
        self.mini_position = None  # Mini mod konumu
        self.normal_window_position = None  # Normal mod pencere konumu

        # Kısayol işleme için
        self.last_processed_shortcut = None
        self.last_shortcut_time = 0
        self.shortcut_debounce_ms = 100  # 100ms debounce (daha az katı)

        print("ClipboardManagerWindow başlatılıyor...")

        try:
            self.load_data()
            self.load_drug_data()  # İlaç verilerini yükle
            print("Veriler yüklendi")
            self.setup_ui()
            print("UI kuruldu")
            self.setup_clipboard_monitor()
            print("Clipboard monitor başlatıldı")
            self.setup_global_shortcuts()
            print("Kısayollar ayarlandı")
            self.setup_system_tray()
            print("Sistem tepsisi kuruldu")
        except Exception as e:
            print(f"Başlatma hatası: {e}")
            import traceback
            traceback.print_exc()

    def load_data(self):
        self.default_rules = [
            ClipboardRule(id="tc_kimlik", name="TC Kimlik No", regex=r"^\d{11}$",
                          display_template="Kimlik No: \"{text}\"", shortcut="alt+1", action="paste",
                          group="Kimlik Bilgileri"),
            ClipboardRule(id="ilac_barkod", name="İlaç Barkodu", regex=r"^\d{13,14}$",
                          display_template="İlaç: \"{text}\"", shortcut="alt+2", action="paste", group="İlaçlar"),
            ClipboardRule(id="url", name="Web Adresi", regex=r"^https?://.+", display_template="🔗 {text}",
                          shortcut="alt+3", action="openUrl", group="Web Linkleri"),
            ClipboardRule(id="email", name="E-posta", regex=r"\S+@\S+\.\S+", display_template="📧 {text}",
                          shortcut="alt+4", action="paste", group="İletişim")
        ]
        sma_code = r'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SMA Teslim Tutanağı - Minyatür Versiyon
Çalıştır → Tanı-İlaç-Bulgu varsa → Barkod iste → HTML oluştur → Yazdır → Kapat
"""

import win32gui
import time
import webbrowser
import tempfile
import tkinter as tk
from tkinter import messagebox

def find_medical_window():
    """Tanı - İlaç - Bulgu penceresini bul"""
    try:
        # Önce aktif pencereyi kontrol et
        hwnd = win32gui.GetForegroundWindow()
        window_text = win32gui.GetWindowText(hwnd)
        if window_text and "Tanı - İlaç - Bulgu" in window_text:
            return window_text
        
        # Aktif pencere uygun değilse tüm pencereleri tara
        result = None
        
        def enum_windows_proc(hwnd, lparam):
            nonlocal result
            try:
                if win32gui.IsWindowVisible(hwnd):
                    window_text = win32gui.GetWindowText(hwnd)
                    if window_text and "Tanı - İlaç - Bulgu" in window_text:
                        result = window_text
                        return False
            except:
                pass
            return True
        
        win32gui.EnumWindows(enum_windows_proc, 0)
        return result
        
    except Exception as e:
        # Hata durumunda kullanıcıdan manuel giriş iste
        return get_manual_patient_info()

def get_manual_patient_info():
    """Manuel hasta bilgisi girişi"""
    ad = None
    tc = None
    
    def on_submit():
        nonlocal ad, tc
        ad = entry_ad.get().strip()
        tc = entry_tc.get().strip()
        if ad and tc:
            root.destroy()
        else:
            messagebox.showwarning("Uyarı", "Lütfen tüm alanları doldurunuz!")
    
    def on_cancel():
        root.destroy()
    
    def on_enter(event):
        on_submit()
    
    # Ana pencere
    root = tk.Tk()
    root.title("Hasta Bilgileri Girişi")
    root.geometry("350x200")
    root.resizable(False, False)
    
    # Pencereyi ortala
    root.update_idletasks()
    x = (root.winfo_screenwidth() // 2) - (350 // 2)
    y = (root.winfo_screenheight() // 2) - (200 // 2)
    root.geometry(f"350x200+{x}+{y}")
    
    # Ad Label ve Entry
    label_ad = tk.Label(root, text="Hasta Adı Soyadı:", font=("Arial", 10))
    label_ad.pack(pady=(20, 5))
    
    entry_ad = tk.Entry(root, font=("Arial", 12), width=25, justify='center')
    entry_ad.pack(pady=5)
    entry_ad.focus()
    
    # TC Label ve Entry
    label_tc = tk.Label(root, text="TC Kimlik No:", font=("Arial", 10))
    label_tc.pack(pady=(10, 5))
    
    entry_tc = tk.Entry(root, font=("Arial", 12), width=25, justify='center')
    entry_tc.pack(pady=5)
    entry_tc.bind('<Return>', on_enter)
    
    # Butonlar
    button_frame = tk.Frame(root)
    button_frame.pack(pady=15)
    
    submit_btn = tk.Button(button_frame, text="Devam", command=on_submit, 
                          font=("Arial", 10), bg="#4CAF50", fg="white", width=8)
    submit_btn.pack(side=tk.LEFT, padx=5)
    
    cancel_btn = tk.Button(button_frame, text="İptal", command=on_cancel, 
                          font=("Arial", 10), bg="#f44336", fg="white", width=8)
    cancel_btn.pack(side=tk.LEFT, padx=5)
    
    # Pencereyi çalıştır
    root.mainloop()
    
    if ad and tc:
        return f"Manuel Giriş | {ad} - {tc}"
    return None

def parse_patient_info(title):
    """Pencere başlığından ad ve TC çıkar"""
    try:
        if "|" in title:
            parts = title.split("|")
            if len(parts) >= 2:
                patient_part = parts[1].strip()
                if "(" in patient_part:
                    patient_part = patient_part.split("(")[0].strip()
                if " - " in patient_part:
                    patient_data = patient_part.split(" - ")
                    if len(patient_data) >= 2:
                        return patient_data[0].strip(), patient_data[1].strip()
    except:
        pass
    return None, None

def get_barcode_input():
    """Barkod girişi için basit pencere"""
    barkod = None
    
    def on_submit():
        nonlocal barkod
        barkod = entry.get().strip()
        if barkod:
            root.destroy()
        else:
            messagebox.showwarning("Uyarı", "Lütfen barkod giriniz!")
    
    def on_cancel():
        root.destroy()
    
    def on_enter(event):
        on_submit()
    
    # Ana pencere
    root = tk.Tk()
    root.title("SMA Barkod Girişi")
    root.geometry("300x150")
    root.resizable(False, False)
    
    # Pencereyi ortala
    root.update_idletasks()
    x = (root.winfo_screenwidth() // 2) - (300 // 2)
    y = (root.winfo_screenheight() // 2) - (150 // 2)
    root.geometry(f"300x150+{x}+{y}")
    
    # Label
    label = tk.Label(root, text="Barkod Numarasını Giriniz:", font=("Arial", 12))
    label.pack(pady=20)
    
    # Entry
    entry = tk.Entry(root, font=("Arial", 14), width=20, justify='center')
    entry.pack(pady=10)
    entry.focus()
    entry.bind('<Return>', on_enter)
    
    # Butonlar
    button_frame = tk.Frame(root)
    button_frame.pack(pady=10)
    
    submit_btn = tk.Button(button_frame, text="Tamam", command=on_submit, 
                          font=("Arial", 10), bg="#4CAF50", fg="white", width=8)
    submit_btn.pack(side=tk.LEFT, padx=5)
    
    cancel_btn = tk.Button(button_frame, text="İptal", command=on_cancel, 
                          font=("Arial", 10), bg="#f44336", fg="white", width=8)
    cancel_btn.pack(side=tk.LEFT, padx=5)
    
    # Pencereyi çalıştır
    root.mainloop()
    
    return barkod

def create_sma_html(ad, tc, barkod):
    """SMA HTML formu oluştur"""
    tarih = time.strftime("%d.%m.%Y")
    
    sma_table = f"""
    <table style="width:100%; border-collapse:collapse; margin:20px 0;">
        <tr>
            <td colspan="6" style="border:2px solid black; height:50px; text-align:center; font-weight:bold; font-size:16px; background-color:#f0f0f0; padding:10px;">
                %il% %ilce% %birim% AİLE HEKİMLİĞİ BİRİMİ
            </td>
        </tr>
        <tr>
            <td colspan="6" style="border:2px solid black; height:50px; text-align:center; font-weight:bold; font-size:18px; background-color:#e0e0e0; padding:10px;">
                SMA TESLİM TUTANAĞI
            </td>
        </tr>
        <tr>
            <td style="border:2px solid black; height:40px; width:16.66%;"></td>
            <td style="border:2px solid black; height:40px; width:16.66%;"></td>
            <td style="border:2px solid black; height:40px; width:16.66%;"></td>
            <td style="border:2px solid black; height:40px; width:16.66%;"></td>
            <td style="border:2px solid black; height:40px; width:16.66%;"></td>
            <td style="border:2px solid black; height:40px; width:16.66%;"></td>
        </tr>
        <tr>
            <td style="border:2px solid black; height:40px; text-align:center; font-weight:bold; font-size:12px; background-color:#f8f8f8; padding:5px;">
                Ad Soyad
            </td>
            <td style="border:2px solid black; height:40px; text-align:center; font-weight:bold; font-size:12px; background-color:#f8f8f8; padding:5px;">
                Hasta Kimlik No
            </td>
            <td style="border:2px solid black; height:40px; text-align:center; font-weight:bold; font-size:12px; background-color:#f8f8f8; padding:5px;">
                Numune Alınma Tarihi
            </td>
            <td style="border:2px solid black; height:40px; text-align:center; font-weight:bold; font-size:12px; background-color:#f8f8f8; padding:5px;">
                Barkod
            </td>
            <td style="border:2px solid black; height:40px; text-align:center; font-weight:bold; font-size:12px; background-color:#f8f8f8; padding:5px;">
                İşlem Tarihi
            </td>
            <td style="border:2px solid black; height:40px; text-align:center; font-weight:bold; font-size:12px; background-color:#f8f8f8; padding:5px;">
                Doktor
            </td>
        </tr>
        <tr>
            <td style="border:2px solid black; height:50px; text-align:center; font-size:12px; font-weight:bold; padding:5px; vertical-align:middle;">
                {ad}
            </td>
            <td style="border:2px solid black; height:50px; text-align:center; font-size:12px; font-weight:bold; padding:5px; vertical-align:middle;">
                {tc}
            </td>
            <td style="border:2px solid black; height:50px; text-align:center; font-size:12px; font-weight:bold; padding:5px; vertical-align:middle;">
                {tarih}
            </td>
            <td style="border:2px solid black; height:50px; text-align:center; font-size:12px; font-weight:bold; padding:5px; vertical-align:middle;">
                {barkod}
            </td>
            <td style="border:2px solid black; height:50px; text-align:center; font-size:12px; font-weight:bold; padding:5px; vertical-align:middle;">
                {tarih}
            </td>
            <td style="border:2px solid black; height:50px; text-align:center; font-size:10px; font-weight:bold; padding:5px; vertical-align:middle;">
                %doctor%
            </td>
        </tr>
    </table>"""
    
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>SMA Teslim Tutanağı - {ad}</title>
    <style>
        @page {{
            size: A4;
            margin: 10mm;
        }}
        body {{
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 0;
            background: white;
        }}
        .container {{
            width: 100%;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }}
        @media print {{
            body {{
                margin: 0;
                padding: 0;
            }}
            .container {{
                padding: 0;
            }}
        }}
    </style>
    <script>
        window.onload = function() {{
            setTimeout(function() {{
                window.print();
            }}, 500);
        }}
    </script>
</head>
<body>
    <div class="container">
        {sma_table}
    </div>
</body>
</html>"""
    
    try:
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8')
        temp_file.write(html_content)
        temp_file.close()
        return temp_file.name
    except:
        return None

def main():
    # Tanı-İlaç-Bulgu penceresini ara
    window_title = find_medical_window()
    if not window_title:
        return
    
    # Hasta bilgilerini parse et
    ad, tc = parse_patient_info(window_title)
    if not ad or not tc:
        return
    
    # Barkod girişi iste
    barkod = get_barcode_input()
    if not barkod:
        return
    
    # HTML oluştur
    html_file = create_sma_html(ad, tc, barkod)
    if not html_file:
        return
    
    # Tarayıcıda aç ve yazdır
    webbrowser.open(f"file:///{html_file.replace('\\\\', '/')}")

if __name__ == "__main__":
    main()
'''

        minitalasemi_code = r'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Talasemi İstem Formu - Minyatür Versiyon
Çalıştır → Tanı-İlaç-Bulgu varsa HTML oluştur → Yazdır → Kapat
"""

import win32gui
import time
import webbrowser
import tempfile

def find_medical_window():
    """Tanı - İlaç - Bulgu penceresini bul"""
    result = None
    
    def enum_windows_proc(hwnd, lparam):
        nonlocal result
        try:
            if win32gui.IsWindowVisible(hwnd):
                window_text = win32gui.GetWindowText(hwnd)
                if window_text and "Tanı - İlaç - Bulgu" in window_text:
                    result = window_text
                    return False
        except:
            pass
        return True
    
    win32gui.EnumWindows(enum_windows_proc, 0)
    return result

def parse_patient_info(title):
    """Pencere başlığından ad ve TC çıkar"""
    try:
        if "|" in title:
            parts = title.split("|")
            if len(parts) >= 2:
                patient_part = parts[1].strip()
                if "(" in patient_part:
                    patient_part = patient_part.split("(")[0].strip()
                if " - " in patient_part:
                    patient_data = patient_part.split(" - ")
                    if len(patient_data) >= 2:
                        return patient_data[0].strip(), patient_data[1].strip()
    except:
        pass
    return None, None

def create_html_file(ad, tc):
    """HTML formu oluştur"""
    tarih = time.strftime("%d.%m.%Y")
    
    form_table = f"""
    <table style="width:100%; border-collapse:collapse; margin-bottom:30px;">
        <tr><td colspan="4" style="border:2px solid black; height:32px; text-align:center; font-weight:bold; font-size:16px; background-color:#f0f0f0;">TALASEMİ VARYANT TESTİ İSTEM FORMU</td></tr>
        <tr><td colspan="2" style="border:2px solid black; height:32px; text-align:center; font-weight:bold; font-size:14px; background-color:#f8f8f8;">AİLE SAĞLIĞI MERKEZİ</td><td colspan="2" style="border:2px solid black; height:32px; text-align:center; font-weight:bold; font-size:14px; background-color:#f8f8f8;">LABORATUVAR</td></tr>
        <tr><td rowspan="2" style="border:2px solid black; height:32px; text-align:left; padding-left:10px; font-weight:bold; font-size:12px; background-color:#fafafa; width:30%;">HASTA ADI SOYADI</td><td rowspan="2" style="border:2px solid black; height:32px; text-align:center; font-size:12px; font-weight:bold; width:30%;">{ad}</td><td colspan="2" rowspan="7" style="border:2px solid black; text-align:center; font-weight:bold; font-size:14px; vertical-align:top; padding-top:10px; background-color:#f8f8f8;">TESLİM ALAN</td><br><p></tr>
        <tr></tr>
        <tr><td rowspan="2" style="border:2px solid black; height:32px; text-align:left; padding-left:10px; font-weight:bold; font-size:12px; background-color:#fafafa; width:30%;">T.C. KİMLİK NUMARASI</td><td rowspan="2" style="border:2px solid black; height:32px; text-align:center; font-size:12px; font-weight:bold; width:30%;">{tc}</td></tr>
        <tr></tr>
        <tr><td rowspan="2" style="border:2px solid black; height:32px; text-align:left; padding-left:10px; font-weight:bold; font-size:12px; background-color:#fafafa; width:30%;">KAN ALMA TARİHİ</td><td rowspan="2" style="border:2px solid black; height:32px; text-align:center; font-size:12px; font-weight:bold; width:30%;">{tarih}</td></tr>
        <tr></tr>
        <tr><td style="border:2px solid black; height:32px; text-align:left; padding-left:10px; font-weight:bold; font-size:12px; background-color:#fafafa; width:30%;">İSTEM YAPAN HEKİM</td><td style="border:2px solid black; height:32px; text-align:center; font-size:10px; font-weight:bold; width:30%;">%doctor%</td></tr>
        <tr><td colspan="2" rowspan="4" style="border:2px solid black; text-align:center; font-weight:bold; font-size:14px; vertical-align:top; padding-top:10px; background-color:#f8f8f8;">TESLİM ALAN</td><td colspan="2" rowspan="4" style="border:2px solid black; text-align:center; font-weight:bold; font-size:14px; vertical-align:top; padding-top:10px; background-color:#f8f8f8;">TESLİM EDEN<p><br></td></tr>
        <tr></tr><tr></tr><tr></tr>
    </table>"""
    
    html_content = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Talasemi İstem Formu - {ad}</title>
<style>@page{{size:A4;margin:10mm;}}body{{font-family:Arial,sans-serif;margin:0;padding:0;background:white;}}</style>
<script>window.onload=function(){{setTimeout(function(){{window.print();}},500);}}</script>
</head><body>{form_table}{form_table}{form_table}</body></html>"""
    
    try:
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8')
        temp_file.write(html_content)
        temp_file.close()
        return temp_file.name
    except:
        return None

def main():
    # Tanı-İlaç-Bulgu penceresini ara
    window_title = find_medical_window()
    if not window_title:
        return
    
    # Hasta bilgilerini parse et
    ad, tc = parse_patient_info(window_title)
    if not ad or not tc:
        return
    
    # HTML oluştur
    html_file = create_html_file(ad, tc)
    if not html_file:
        return
    
    # Tarayıcıda aç ve yazdır
    webbrowser.open(f"file:///{html_file.replace('\\\\', '/')}")

if __name__ == "__main__":
    main()
'''

        self.default_snippets = [
            Snippet(id="snippet_1", name="E-posta İmzası",
                    content="İyi çalışmalar,\n[Adınız]\n[Pozisyonunuz]\n[Şirket Adı]\n[Telefon] | [E-posta]",
                    shortcut="alt+q", category="İletişim", action_type="paste"),
            Snippet(id="snippet_2", name="Tarih - Bugün", content=datetime.now().strftime("%d.%m.%Y"), shortcut="alt+w",
                    category="Tarih/Saat", action_type="paste"),
            Snippet(id="snippet_3", name="Python Test", content="",
                    python_code="import datetime\nprint('Merhaba! Şu anki saat:', datetime.datetime.now())",
                    shortcut="alt+e", category="Python", action_type="execute_python"),
            Snippet(id="snippet_4", name="SMA Teslim Tutanağı", content="",
                    python_code=sma_code, shortcut="alt+r", category="Tıbbi Formlar", action_type="execute_python"),
            Snippet(id="snippet_5", name="Talasemi İstem Formu", content="",
                    python_code=minitalasemi_code, shortcut="alt+t", category="Tıbbi Formlar", action_type="execute_python")
        ]

        try:
            with open("rules.json", "r", encoding="utf-8") as f:
                self.rules = [ClipboardRule(**rule) for rule in json.load(f)]
        except:
            self.rules = self.default_rules
            self.save_rules()

        try:
            with open("snippets.json", "r", encoding="utf-8") as f:
                # Geriye dönük uyumluluk için yeni alanları kontrol et
                loaded_snippets = json.load(f)
                self.snippets = []
                for s in loaded_snippets:
                    if 'action_type' not in s:
                        s['action_type'] = 'paste'
                    if 'command' not in s:
                        s['command'] = None
                    if 'python_code' not in s:
                        s['python_code'] = None
                    if 'content' not in s:
                        s['content'] = ""
                    self.snippets.append(Snippet(**s))
        except:
            self.snippets = self.default_snippets
            self.save_snippets()

        try:
            with open("pinned.json", "r", encoding="utf-8") as f:
                pinned_data = json.load(f)
                self.pinned_items = []
                for item_data in pinned_data:
                    if 'rule' in item_data and item_data['rule']:
                        item_data['rule'] = ClipboardRule(**item_data['rule'])
                    self.pinned_items.append(PinnedItem(**item_data))
        except:
            self.pinned_items = []

        try:
            with open("settings.json", "r", encoding="utf-8") as f:
                self.settings = json.load(f)
        except:
            self.settings = {
                "appearance": {"backgroundColor": "rgba(30, 30, 30, 0.95)", "textColor": "#FFFFFF", "fontSize": 12},
                "behavior": {"maxItems": 50, "groupTimeWindow": 60000, "alwaysOnTop": True},
                "window": {"miniPosition": None}  # Mini mod konumu
            }
            
        # Varsayılan değişkenleri ayarla
        default_vars = {
            "%doctor%": "Doktor (ayarlardan değiştirin)",
            "%il%": "İl (ayarlardan değiştirin)",
            "%ilce%": "İlçe (ayarlardan değiştirin)",
            "%asm%": "ASM (ayarlardan değiştirin)",
            "%birim%":"birim (ayarlardan değiştirin)",
            "%mudurluk%": "Müdürlük (ayarlardan değiştirin)"
        }
        
        if "variables" not in self.settings:
            self.settings["variables"] = default_vars
            self.save_settings()
        else:
            # Eksik varsayılan değişkenleri ekle
            needs_save = False
            for k, v in default_vars.items():
                if k not in self.settings["variables"]:
                    self.settings["variables"][k] = v
                    needs_save = True
            if needs_save:
                self.save_settings()

        # Mini position'ı yükle
        mini_pos = self.settings.get("window", {}).get("miniPosition")
        if mini_pos:
            self.mini_position = QPoint(mini_pos["x"], mini_pos["y"])
            print(f"📌 Mini mod konumu yüklendi: {self.mini_position}")
        else:
            print("📌 Mini mod konumu bulunamadı, varsayılan kullanılacak")

        # Normal pencere pozisyonunu yükle
        window_pos = self.settings.get("window", {}).get("position")
        if window_pos:
            self.normal_window_position = QPoint(window_pos["x"], window_pos["y"])
            print(f"📌 Normal pencere konumu yüklendi: {self.normal_window_position}")
        else:
            self.normal_window_position = None
            print("📌 Normal pencere konumu bulunamadı, varsayılan kullanılacak")

        # Geçmiş gruplarını yükle
        try:
            with open("history.json", "r", encoding="utf-8") as f:
                groups_data = json.load(f)
                self.groups = []
                for group_data in groups_data:
                    # Grup içindeki itemları deserialize et
                    items = []
                    for item_data in group_data.get('items', []):
                        if 'rule' in item_data and item_data['rule']:
                            item_data['rule'] = ClipboardRule(**item_data['rule'])
                        items.append(ClipboardItem(**item_data))

                    # ItemGroup oluştur
                    group_data['items'] = items
                    self.groups.append(ItemGroup(**group_data))
                print(f"📋 {len(self.groups)} grup yüklendi")
        except FileNotFoundError:
            print("📋 Geçmiş dosyası bulunamadı, yeni başlatılıyor")
            self.groups = []
        except Exception as e:
            print(f"❌ Geçmiş yükleme hatası: {e}")
            self.groups = []

    def load_drug_data(self):
        """İlaç ve ATC-ICD mapping verilerini yükle"""
        self.drugs_data = {}
        self.atc_icd_mapping = {}

        try:
            # İlaçlar JSON dosyasını yükle
            drugs_file = Path("data/ilaclar.json")
            if drugs_file.exists():
                with open(drugs_file, "r", encoding="utf-8") as f:
                    drugs_list = json.load(f)
                    # Barcode'a göre dictionary'ye çevir
                    for drug in drugs_list:
                        self.drugs_data[str(drug["barcode"])] = drug
                print(f"📋 {len(self.drugs_data)} ilaç verisi yüklendi")
            else:
                print("⚠️ İlaçlar JSON dosyası bulunamadı")
        except Exception as e:
            print(f"❌ İlaçlar yükleme hatası: {e}")

        try:
            # ATC-ICD mapping dosyasını yükle
            mapping_file = Path("data/atc_icd_mapping.json")
            if mapping_file.exists():
                with open(mapping_file, "r", encoding="utf-8") as f:
                    self.atc_icd_mapping = json.load(f)

                # atc_to_icd anahtarının varlığını kontrol et
                atc_count = len(self.atc_icd_mapping.get("atc_to_icd", {}))
                print(f"📋 ATC-ICD mapping yüklendi: {atc_count} ATC kodu")
            else:
                print("⚠️ ATC-ICD mapping dosyası bulunamadı")
        except Exception as e:
            print(f"❌ ATC-ICD mapping yükleme hatası: {e}")

    def get_drug_info(self, barcode: str) -> Optional[Dict]:
        """Barkod ile ilaç bilgilerini getir"""
        try:
            if barcode in self.drugs_data:
                drug = self.drugs_data[barcode]
                atc_code = drug.get("atc_code", "").strip()

                # ICD kodlarını al
                icd_codes = []
                if atc_code and self.atc_icd_mapping:
                    # atc_to_icd anahtarından al
                    atc_to_icd = self.atc_icd_mapping.get("atc_to_icd", {})

                    # Tam eşleşme dene
                    if atc_code in atc_to_icd:
                        icd_codes = atc_to_icd[atc_code]
                        print(f"✅ Tam ATC eşleşmesi bulundu: {atc_code} -> {len(icd_codes)} ICD")
                    else:
                        # Wildcard eşleşmeleri dene (A01AA* gibi)
                        for atc_pattern, icd_list in atc_to_icd.items():
                            if '*' in atc_pattern:
                                # A01AA* -> A01AA ile başlayan kodları eşleştir
                                pattern_base = atc_pattern.replace('*', '')
                                if atc_code.startswith(pattern_base):
                                    icd_codes = icd_list
                                    print(
                                        f"✅ Wildcard ATC eşleşmesi: {atc_code} -> {atc_pattern} -> {len(icd_codes)} ICD")
                                    break

                        if not icd_codes:
                            print(f"❌ ATC kodu için ICD bulunamadı: {atc_code}")

                return {
                    "name": drug.get("name", ""),
                    "atc_code": atc_code,
                    "atc_name": drug.get("atc_name", ""),
                    "icd_codes": icd_codes
                }
        except Exception as e:
            print(f"❌ İlaç bilgisi alma hatası: {e}")

        return None

    def save_rules(self):
        with open("rules.json", "w", encoding="utf-8") as f:
            json.dump([asdict(rule) for rule in self.rules], f, ensure_ascii=False, indent=2)

    def save_snippets(self):
        with open("snippets.json", "w", encoding="utf-8") as f:
            json.dump([asdict(snippet) for snippet in self.snippets], f, ensure_ascii=False, indent=2)

    def save_pinned(self):
        with open("pinned.json", "w", encoding="utf-8") as f:
            pinned_data_to_save = []
            for item_to_save in self.pinned_items:
                item_dict = asdict(item_to_save)
                if item_dict['rule']:
                    item_dict['rule'] = asdict(item_to_save.rule)
                pinned_data_to_save.append(item_dict)
            json.dump(pinned_data_to_save, f, ensure_ascii=False, indent=2)

    def save_groups(self):
        """Geçmiş gruplarını kalıcı olarak kaydet"""
        try:
            with open("history.json", "w", encoding="utf-8") as f:
                groups_data = []
                for group in self.groups:
                    group_dict = asdict(group)
                    # Her grup içindeki itemları da serialize et
                    group_dict['items'] = []
                    for item in group.items:
                        item_dict = asdict(item)
                        if item_dict['rule']:
                            item_dict['rule'] = asdict(item.rule)
                        group_dict['items'].append(item_dict)
                    groups_data.append(group_dict)
                json.dump(groups_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"❌ Geçmiş kaydetme hatası: {e}")

    def save_settings(self):
        with open("settings.json", "w", encoding="utf-8") as f:
            json.dump(self.settings, f, ensure_ascii=False, indent=2)

    def setup_global_shortcuts(self):
        try:
            # Ana açma/kapama kısayolu
            qt_shortcut = QShortcut(QKeySequence("Ctrl+Alt+V"), self)
            qt_shortcut.activated.connect(self.toggle_overlay)
            print("Ctrl+Alt+V kısayolu ayarlandı")

            # Qt Shortcuts (Daha güvenli ama sınırlı)
            print("🔧 Qt Global Shortcuts kuruluyor...")
            self.qt_shortcuts = []

            # Dinamik olarak kısayolları Qt ile kaydet
            self.setup_qt_shortcuts()

            # Keyboard modülü (Mevcut sistem)
            if KEYBOARD_AVAILABLE:
                try:
                    # Ana toggle kısayolu
                    keyboard.add_hotkey('ctrl+alt+v', self.toggle_overlay)
                    print("Global kısayollar keyboard ile ayarlandı")

                    # Tüm olası tuşlar için dinleyici - daha kapsamlı
                    # Sayılar
                    for i in range(0, 10):
                        keyboard.on_press_key(str(i),
                                              lambda _, key=str(i): self.handle_keyboard_shortcut_with_modifiers(key))

                    # Harfler
                    for char in 'abcdefghijklmnopqrstuvwxyz':
                        keyboard.on_press_key(char,
                                              lambda _, key=char: self.handle_keyboard_shortcut_with_modifiers(key))

                    # F tuşları
                    for i in range(1, 13):
                        keyboard.on_press_key(f'f{i}',
                                              lambda _, key=f'f{i}': self.handle_keyboard_shortcut_with_modifiers(key))

                    print("🎹 Keyboard modülü tuş dinleyicileri kuruldu")

                except Exception as e_kb:
                    print(f"❌ Keyboard modülü hatası: {e_kb}")
                    print("🔄 Qt Shortcuts'a geçiliyor...")
            else:
                print("⚠️ keyboard modülü yok, Qt kısayolları kullanılıyor")

        except Exception as e_sc:
            print(f"❌ Kısayol ayarlama hatası: {e_sc}")

    def setup_qt_shortcuts(self):
        """Qt ile güvenli global shortcuts"""
        try:
            # Mevcut Qt shortcuts'ları temizle
            for shortcut in getattr(self, 'qt_shortcuts', []):
                shortcut.setEnabled(False)
                shortcut.deleteLater()

            self.qt_shortcuts = []

            # Tüm snippet'ler için
            for snippet in self.snippets:
                if snippet.shortcut:
                    try:
                        # Qt format: "Ctrl+Alt+Q"
                        qt_format = self.convert_to_qt_shortcut(snippet.shortcut)
                        if qt_format:
                            qt_shortcut = QShortcut(QKeySequence(qt_format), self)
                            qt_shortcut.activated.connect(lambda s=snippet: self.execute_snippet_safe(s))
                            self.qt_shortcuts.append(qt_shortcut)
                            print(f"✅ Qt Shortcut: {qt_format} -> {snippet.name}")
                    except Exception as e:
                        print(f"❌ Qt shortcut hatası ({snippet.shortcut}): {e}")

            # Sabitlenmiş öğeler için
            for pinned in self.pinned_items:
                if pinned.shortcut:
                    try:
                        qt_format = self.convert_to_qt_shortcut(pinned.shortcut)
                        if qt_format:
                            qt_shortcut = QShortcut(QKeySequence(qt_format), self)
                            qt_shortcut.activated.connect(lambda p=pinned: self.execute_pinned_item_safe(p))
                            self.qt_shortcuts.append(qt_shortcut)
                            print(f"✅ Qt Shortcut: {qt_format} -> Pinned")
                    except Exception as e:
                        print(f"❌ Qt shortcut hatası ({pinned.shortcut}): {e}")

        except Exception as e:
            print(f"❌ Qt shortcuts kurulum hatası: {e}")

    def convert_to_qt_shortcut(self, shortcut: str) -> str:
        """Shortcut'u Qt formatına çevir"""
        try:
            # "alt+4" -> "Alt+4"
            # "ctrl+alt+a" -> "Ctrl+Alt+A"
            # "f1" -> "F1"

            parts = shortcut.lower().split('+')
            qt_parts = []

            for part in parts:
                if part == 'ctrl':
                    qt_parts.append('Ctrl')
                elif part == 'alt':
                    qt_parts.append('Alt')
                elif part == 'shift':
                    qt_parts.append('Shift')
                elif part.startswith('f') and part[1:].isdigit():
                    qt_parts.append(part.upper())  # f1 -> F1
                elif part.isdigit():
                    qt_parts.append(part)  # 4 -> 4
                elif len(part) == 1 and part.isalpha():
                    qt_parts.append(part.upper())  # a -> A
                else:
                    return None  # Desteklenmeyen format

            return '+'.join(qt_parts)

        except Exception as e:
            print(f"❌ Shortcut çevirme hatası ({shortcut}): {e}")
            return None

    def handle_keyboard_shortcut_with_modifiers(self, key):
        """Modifier tuşlarını kontrol ederek kısayolu oluştur"""
        try:
            current_time = time.time() * 1000  # milisaniye cinsinden

            modifiers = []
            if keyboard.is_pressed('ctrl'):
                modifiers.append('ctrl')
            if keyboard.is_pressed('alt'):
                modifiers.append('alt')
            if keyboard.is_pressed('shift'):
                modifiers.append('shift')

            if not modifiers:
                return  # Sadece tuşa basıldıysa işlem yapma

            shortcut = '+'.join(modifiers + [key.lower()])

            # Debounce kontrolü - daha esnek
            if (self.last_processed_shortcut == shortcut and
                    current_time - self.last_shortcut_time < self.shortcut_debounce_ms):
                # print(f"Debounce nedeniyle atlandı: {shortcut}")
                return

            self.last_processed_shortcut = shortcut
            self.last_shortcut_time = current_time

            print(f"🎹 Algılanan kısayol: {shortcut}")

            # Ana thread'de güvenli şekilde işle
            QApplication.instance().processEvents()
            self.handle_global_shortcut(shortcut)

        except Exception as e:
            print(f"❌ Kısayol işleme hatası: {e}")
            import traceback
            traceback.print_exc()

    def setup_ui(self):
        self.setWindowTitle("Clipboard Manager")
        desktop = QApplication.desktop()
        screen = desktop.availableGeometry()

        # Kaydedilmiş pozisyon varsa kullan, yoksa varsayılan pozisyon
        if self.normal_window_position:
            win_x = self.normal_window_position.x()
            win_y = self.normal_window_position.y()
            print(f"📌 Kaydedilmiş pencere pozisyonu kullanılıyor: {win_x}, {win_y}")
        else:
            win_x = screen.width() - 370
            win_y = 20
            if win_x < 0: win_x = 10
            print(f"📌 Varsayılan pencere pozisyonu kullanılıyor: {win_x}, {win_y}")

        default_w = self.settings.get("appearance", {}).get("windowWidth", 350)
        default_h = self.settings.get("appearance", {}).get("windowHeight", 500)
        self.setGeometry(win_x, win_y, default_w, default_h)
        self.setMinimumSize(220, 400)  # Minimum genişlik 220 piksel
        self.setMaximumSize(800, 1000)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        print(f"Pencere pozisyonu: {win_x}, {win_y}")
        print(f"Ekran boyutu: {screen.width()}x{screen.height()}")

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        main_layout = QVBoxLayout(self.central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.bg_frame = QFrame()
        self._apply_main_styles()
        bg_main_layout = QVBoxLayout(self.bg_frame)

        header_main_layout = QHBoxLayout()
        settings_btn = QPushButton("⚙")
        settings_btn.setToolTip("Ayarlar")
        settings_btn.clicked.connect(self.show_settings)
        settings_btn.setMaximumSize(30, 30)
        settings_btn.setStyleSheet(
            "QPushButton {background-color: rgba(255,255,255,0.05); color:#CDD6F4; border-radius:15px; font-size:16px; border:1px solid rgba(255,255,255,0.1);} QPushButton:hover {background-color: rgba(139,92,246,0.3); border: 1px solid #8B5CF6; color:white;}")

        minimize_btn = QPushButton("━")
        minimize_btn.setToolTip("Küçült")
        minimize_btn.clicked.connect(self.toggle_minimize)
        minimize_btn.setMaximumSize(30, 30)
        minimize_btn.setStyleSheet(
            "QPushButton {background-color: rgba(249,226,175,0.1); color:#F9E2AF; border-radius:15px; font-size:16px; font-weight:bold; border:1px solid rgba(249,226,175,0.2);} QPushButton:hover {background-color: rgba(249,226,175,0.3); border:1px solid #F9E2AF;}")

        close_main_btn = QPushButton("✕")
        close_main_btn.setToolTip("Kapat")
        close_main_btn.clicked.connect(self.hide)
        close_main_btn.setMaximumSize(30, 30)
        close_main_btn.setStyleSheet(
            "QPushButton {background-color: rgba(243,139,168,0.1); color:#F38BA8; border-radius:15px; font-size:16px; font-weight:bold; border:1px solid rgba(243,139,168,0.2);} QPushButton:hover {background-color: rgba(243,139,168,0.3); border:1px solid #F38BA8; color:white;}")

        header_main_layout.addWidget(settings_btn)
        header_main_layout.addWidget(minimize_btn)
        header_main_layout.addStretch()

        self.title_label_widget = QLabel("📋 Clipboard Manager")
        self.title_label_widget.setStyleSheet(
            f"QLabel {{color: {self.settings.get('appearance', {}).get('textColor', '#FFFFFF')}; font-size:16px; font-weight:bold; background-color:transparent;}}")
        header_main_layout.addWidget(self.title_label_widget)
        header_main_layout.addStretch()
        header_main_layout.addWidget(close_main_btn)
        bg_main_layout.addLayout(header_main_layout)
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border:none; border-top: 1px solid rgba(255,255,255,0.1); background-color:transparent; margin-top: -1px; }
            QTabBar::tab { background-color:transparent; color:#A6ADC8; padding:8px 16px; margin:0px 4px; min-width: 80px; border-bottom: 2px solid transparent; border-radius: 0px; font-weight: bold; }
            QTabBar::tab:selected { color:#8B5CF6; border-bottom: 2px solid #8B5CF6; }
            QTabBar::tab:hover { color:#CDD6F4; background-color:rgba(255,255,255,0.03); border-radius: 6px 6px 0 0; }
        """)

        # =================== HISTORY TAB ===================
        self.history_tab = QWidget()
        self.history_layout = QVBoxLayout(self.history_tab)
        self.history_layout.setContentsMargins(0, 0, 0, 0)
        self.history_layout.setSpacing(0)

        # HISTORY SCROLL AREA - DÜZELTİLMİŞ
        self.history_scroll = QScrollArea()
        self.history_scroll.setWidgetResizable(True)

        self.history_scroll.setMinimumHeight(100)  # Minimum yükseklik ayarla
        self.history_scroll.setSizePolicy(
            self.history_scroll.sizePolicy().Expanding,
            self.history_scroll.sizePolicy().Expanding
        )
        self.history_scroll.setStyleSheet(
            """
            QScrollArea {
                background-color:transparent; 
                border:none;
            } 
            QScrollBar:vertical {
                width: 8px; 
                background-color: transparent; 
                margin: 0px;
            } 
            QScrollBar::handle:vertical {
                background-color: rgba(255,255,255,0.15); 
                border-radius: 4px;
                min-height: 30px;
                margin: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: rgba(139,92,246,0.5); 
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background-color: transparent;
            }
            """)

        self.history_content = QWidget()
        self.history_content.setStyleSheet("background-color: transparent;")
        self.history_content_layout = QVBoxLayout(self.history_content)
        self.history_content_layout.setAlignment(Qt.AlignTop)
        self.history_content_layout.setContentsMargins(3, 3, 3, 3)
        self.history_content_layout.setSpacing(2)  # Widget'lar arası boşluğu azalt

        # İçerik widget'inin boyut politikasını ayarla
        self.history_content.setSizePolicy(
            self.history_content.sizePolicy().Preferred,
            self.history_content.sizePolicy().Minimum
        )

        self.history_scroll.setWidget(self.history_content)
        self.history_layout.addWidget(self.history_scroll)

        # =================== PINNED TAB ===================
        self.pinned_tab = QWidget()
        self.pinned_layout = QVBoxLayout(self.pinned_tab)
        self.pinned_layout.setContentsMargins(0, 0, 0, 0)
        self.pinned_layout.setSpacing(0)

        # PINNED SCROLL AREA - DÜZELTİLMİŞ
        self.pinned_scroll = QScrollArea()
        self.pinned_scroll.setWidgetResizable(True)
        self.pinned_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.pinned_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.pinned_scroll.setMinimumHeight(100)
        self.pinned_scroll.setSizePolicy(
            self.pinned_scroll.sizePolicy().Expanding,
            self.pinned_scroll.sizePolicy().Expanding
        )
        self.pinned_scroll.setStyleSheet(
            """
            QScrollArea {
                background-color:transparent; 
                border:none;
                padding: 0px;
                margin: 0px;
            } 
            QScrollBar:vertical {
                width:6px; 
                background-color:rgba(255,255,255,0.05); 
                border-radius:3px;
                margin: 0px;
            } 
            QScrollBar::handle:vertical {
                background-color:rgba(255,255,255,0.3); 
                border-radius:3px;
                margin: 0px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            """)

        self.pinned_content = QWidget()
        self.pinned_content.setStyleSheet("background-color: transparent;")
        self.pinned_content_layout = QVBoxLayout(self.pinned_content)
        self.pinned_content_layout.setAlignment(Qt.AlignTop)
        self.pinned_content_layout.setContentsMargins(3, 3, 3, 3)
        self.pinned_content_layout.setSpacing(2)

        self.pinned_content.setSizePolicy(
            self.pinned_content.sizePolicy().Preferred,
            self.pinned_content.sizePolicy().Minimum
        )

        self.pinned_scroll.setWidget(self.pinned_content)
        self.pinned_layout.addWidget(self.pinned_scroll)

        # =================== SNIPPETS TAB ===================
        self.snippets_tab = QWidget()
        self.snippets_layout = QVBoxLayout(self.snippets_tab)
        self.snippets_layout.setContentsMargins(0, 0, 0, 0)
        self.snippets_layout.setSpacing(2)

        # Snippet ekle butonu
        add_snippet_btn = QPushButton("+ Yeni Snippet Ekle")
        add_snippet_btn.clicked.connect(self.show_add_snippet_dialog)
        add_snippet_btn.setStyleSheet(
            "QPushButton {background-color:rgba(139,92,246,0.2); border:1px solid #8B5CF6; color:#CDD6F4; border-radius:6px; padding:10px; font-size:14px; font-weight:bold;} QPushButton:hover {background-color:rgba(139,92,246,0.4); color:white;} QPushButton:pressed {background-color:rgba(139,92,246,0.6);}")
        self.snippets_layout.addWidget(add_snippet_btn)

        # SNIPPETS SCROLL AREA - DÜZELTİLMİŞ
        self.snippets_scroll = QScrollArea()
        self.snippets_scroll.setWidgetResizable(True)
        self.snippets_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.snippets_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.snippets_scroll.setMinimumHeight(100)
        self.snippets_scroll.setSizePolicy(
            self.snippets_scroll.sizePolicy().Expanding,
            self.snippets_scroll.sizePolicy().Expanding
        )
        self.snippets_scroll.setStyleSheet(
            """
            QScrollArea {
                background-color:transparent; 
                border:none;
                padding: 0px;
                margin: 0px;
            } 
            QScrollBar:vertical {
                width:6px; 
                background-color:rgba(255,255,255,0.05); 
                border-radius:3px;
                margin: 0px;
            } 
            QScrollBar::handle:vertical {
                background-color:rgba(255,255,255,0.3); 
                border-radius:3px;
                margin: 0px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            """)

        self.snippets_content = QWidget()
        self.snippets_content.setStyleSheet("background-color: transparent;")
        self.snippets_content_layout = QVBoxLayout(self.snippets_content)
        self.snippets_content_layout.setAlignment(Qt.AlignTop)
        self.snippets_content_layout.setContentsMargins(3, 3, 3, 3)
        self.snippets_content_layout.setSpacing(2)

        self.snippets_content.setSizePolicy(
            self.snippets_content.sizePolicy().Preferred,
            self.snippets_content.sizePolicy().Minimum
        )

        self.snippets_scroll.setWidget(self.snippets_content)
        self.snippets_layout.addWidget(self.snippets_scroll)

        # TAB'LARI EKLE
        self.tabs.addTab(self.history_tab, "📋 Geçmiş")
        self.tabs.addTab(self.pinned_tab, "📌 Sabit")
        self.tabs.addTab(self.snippets_tab, "📝 Snippet")
        bg_main_layout.addWidget(self.tabs)

        main_layout.addWidget(self.bg_frame)

        # Resize handle'ları oluştur
        self.setup_resize_handles()

        # Mouse event'leri
        self.mousePressEvent = self.mouse_press_event
        self.mouseMoveEvent = self.mouse_move_event
        self.resizing = False
        self.resize_direction = None

        self.render_history()
        self.render_pinned()
        self.render_snippets()
        self.update_tab_badges()

    def setup_resize_handles(self):
        """Windows tarzı resize handle'ları oluştur"""
        handle_size = 8

        # Resize handle'ları
        self.resize_handles = {}

        # Köşeler
        self.resize_handles['top_left'] = self.create_resize_handle('top_left', Qt.SizeFDiagCursor)
        self.resize_handles['top_right'] = self.create_resize_handle('top_right', Qt.SizeBDiagCursor)
        self.resize_handles['bottom_left'] = self.create_resize_handle('bottom_left', Qt.SizeBDiagCursor)
        self.resize_handles['bottom_right'] = self.create_resize_handle('bottom_right', Qt.SizeFDiagCursor)

        # Kenarlar
        self.resize_handles['top'] = self.create_resize_handle('top', Qt.SizeVerCursor)
        self.resize_handles['bottom'] = self.create_resize_handle('bottom', Qt.SizeVerCursor)
        self.resize_handles['left'] = self.create_resize_handle('left', Qt.SizeHorCursor)
        self.resize_handles['right'] = self.create_resize_handle('right', Qt.SizeHorCursor)

        self.update_resize_handles()

    def create_resize_handle(self, direction, cursor):
        """Tek bir resize handle oluştur"""
        handle = QWidget(self)
        handle.setCursor(cursor)
        handle.setStyleSheet("""
            QWidget {
                background-color: transparent;
            }
            QWidget:hover {
                background-color: rgba(33, 150, 243, 0.3);
            }
        """)

        handle.mousePressEvent = lambda event, d=direction: self.resize_handle_press(event, d)
        handle.mouseMoveEvent = lambda event, d=direction: self.resize_handle_move(event, d)
        handle.mouseReleaseEvent = self.resize_handle_release

        return handle

    def update_resize_handles(self):
        """Resize handle'ları pencere boyutuna göre güncelle"""
        if not hasattr(self, 'resize_handles'):
            return

        w, h = self.width(), self.height()
        handle_size = 8

        # Köşeler
        self.resize_handles['top_left'].setGeometry(0, 0, handle_size, handle_size)
        self.resize_handles['top_right'].setGeometry(w - handle_size, 0, handle_size, handle_size)
        self.resize_handles['bottom_left'].setGeometry(0, h - handle_size, handle_size, handle_size)
        self.resize_handles['bottom_right'].setGeometry(w - handle_size, h - handle_size, handle_size, handle_size)

        # Kenarlar
        self.resize_handles['top'].setGeometry(handle_size, 0, w - 2 * handle_size, handle_size)
        self.resize_handles['bottom'].setGeometry(handle_size, h - handle_size, w - 2 * handle_size, handle_size)
        self.resize_handles['left'].setGeometry(0, handle_size, handle_size, h - 2 * handle_size)
        self.resize_handles['right'].setGeometry(w - handle_size, handle_size, handle_size, h - 2 * handle_size)

    def resize_handle_press(self, event, direction):
        """Resize handle'a basıldığında"""
        if event.button() == Qt.LeftButton:
            self.resizing = True
            self.resize_direction = direction
            self.resize_start_pos = event.globalPos()
            self.resize_start_geometry = self.geometry()

    def resize_handle_move(self, event, direction):
        """Resize handle hareket ettirildiğinde"""
        if not self.resizing or event.buttons() != Qt.LeftButton:
            return

        delta = event.globalPos() - self.resize_start_pos
        new_geo = QRect(self.resize_start_geometry)

        # Minimum boyutlar
        min_w, min_h = 220, 400

        if 'left' in direction:
            new_width = max(min_w, self.resize_start_geometry.width() - delta.x())
            new_geo.setLeft(self.resize_start_geometry.right() - new_width)

        if 'right' in direction:
            new_width = max(min_w, self.resize_start_geometry.width() + delta.x())
            new_geo.setWidth(new_width)

        if 'top' in direction:
            new_height = max(min_h, self.resize_start_geometry.height() - delta.y())
            new_geo.setTop(self.resize_start_geometry.bottom() - new_height)

        if 'bottom' in direction:
            new_height = max(min_h, self.resize_start_geometry.height() + delta.y())
            new_geo.setHeight(new_height)

        self.setGeometry(new_geo)

    def resize_handle_release(self, event):
        """Resize handle bırakıldığında"""
        self.resizing = False
        self.resize_direction = None

    def _apply_main_styles(self):
        bg_color = self.settings.get('appearance', {}).get('backgroundColor', 'rgba(30, 30, 46, 0.95)')
        text_color = self.settings.get('appearance', {}).get('textColor', '#CDD6F4')
        self.bg_frame.setStyleSheet(f"""
            QFrame {{ background-color:{bg_color}; border-radius:12px; color:{text_color}; border: 1px solid rgba(255,255,255,0.05); }}
            QLabel {{ color:{text_color}; background-color:transparent; border: none; }}
            QPushButton {{ background-color:rgba(255,255,255,0.05); color:{text_color}; border:1px solid rgba(255,255,255,0.1); border-radius:6px; padding:6px; font-weight:bold; }}
            QPushButton:hover {{ background-color:rgba(139,92,246,0.3); border:1px solid #8B5CF6; color:white; }}
        """)
        if hasattr(self, 'title_label_widget'):
            self.title_label_widget.setStyleSheet(
                f"QLabel {{color:{text_color}; font-size:16px; font-weight:bold; background-color:transparent; letter-spacing: 1px; border: none;}}")

    def mouse_press_event(self, event):
        """Ana pencere mouse press - sadece sürükleme için"""
        if event.button() == Qt.LeftButton:
            # Resize handle'ların dışında mıyız?
            if not self.resizing:
                self.old_pos = event.globalPos()

    def mouse_move_event(self, event):
        """Ana pencere mouse move - sadece sürükleme için"""
        if (event.buttons() == Qt.LeftButton and
                hasattr(self, 'old_pos') and
                self.old_pos is not None and
                not self.resizing):
            delta = event.globalPos() - self.old_pos
            self.move(self.pos() + delta)
            self.old_pos = event.globalPos()

    def mouseReleaseEvent(self, event):
        """Mouse release event"""
        self.resizing = False
        self.resize_direction = None
        self.old_pos = None
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event):
        """Pencere boyutu değiştiğinde resize handle'ları güncelle"""
        super().resizeEvent(event)
        self.update_resize_handles()

    def moveEvent(self, event):
        """Pencere taşındığında pozisyonu kaydet"""
        super().moveEvent(event)
        # Sadece normal modda değilse (küçültülmemiş) pozisyonu kaydet
        if not self.is_minimized:
            self.normal_window_position = self.pos()
            # Pozisyonu settings'e kaydet
            if "window" not in self.settings:
                self.settings["window"] = {}
            self.settings["window"]["position"] = {"x": self.pos().x(), "y": self.pos().y()}
            self.save_settings()

    def setup_clipboard_monitor(self):
        self.clipboard_monitor = ClipboardMonitor()
        self.clipboard_monitor.new_clip.connect(self.process_clipboard_item)
        self.clipboard_monitor.start()

    def setup_system_tray(self):
        self.tray = QSystemTrayIcon(self)
        icon_pix = QPixmap(64, 64)
        icon_pix.fill(Qt.transparent)
        painter = QPainter(icon_pix)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(QColor(33, 150, 243)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(4, 4, 56, 56)
        painter.setBrush(QBrush(QColor(255, 255, 255, 30)))
        painter.drawEllipse(8, 8, 48, 48)
        painter.setPen(QPen(Qt.white, 3))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(16, 20, 32, 36, 4, 4)
        painter.drawRect(24, 14, 16, 10)
        painter.setBrush(QColor(255, 255, 255))
        painter.drawRect(26, 12, 12, 8)
        painter.setPen(QPen(Qt.white, 2))
        painter.drawLine(22, 30, 42, 30)
        painter.drawLine(22, 36, 38, 36)
        painter.drawLine(22, 42, 40, 42)
        painter.end()

        self.tray.setIcon(QIcon(icon_pix))
        self.tray.setToolTip("Clipboard Manager")

        tray_menu_widget = QMenu()
        show_act = QAction("Göster/Gizle", self)
        show_act.triggered.connect(self.toggle_overlay)
        tray_menu_widget.addAction(show_act)

        settings_act = QAction("Ayarlar", self)
        settings_act.triggered.connect(self.show_settings)
        tray_menu_widget.addAction(settings_act)
        tray_menu_widget.addSeparator()

        clear_act = QAction("Geçmişi Temizle", self)
        clear_act.triggered.connect(self.clear_history)
        tray_menu_widget.addAction(clear_act)
        tray_menu_widget.addSeparator()

        quit_act = QAction("Çıkış", self)
        quit_act.triggered.connect(QApplication.quit)
        tray_menu_widget.addAction(quit_act)

        self.tray.setContextMenu(tray_menu_widget)
        self.tray.show()
        self.tray.activated.connect(self.tray_activated)

    def tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.toggle_overlay()

    def toggle_overlay(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()

    def toggle_minimize(self):
        if not self.is_minimized:
            self.normal_geometry = self.geometry()
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setFixedSize(60, 60)
            self.is_minimized = True
            self.bg_frame.hide()
            if hasattr(self, 'resize_handle'):
                self.resize_handle.hide()

            self.mini_widget = QWidget(self)
            self.mini_widget.setGeometry(0, 0, 60, 60)
            self.mini_widget.setAttribute(Qt.WA_TranslucentBackground)
            self.mini_icon = MiniIcon(self.mini_widget)
            self.mini_icon.setGeometry(0, 0, 60, 60)

            # Mini mod için sürükleme durumu değişkenlerini başlat
            self.mini_dragging = False
            self.mini_drag_offset = None
            self.mini_press_global_pos = None

            self.mini_icon.mousePressEvent = self.mini_mouse_press
            self.mini_icon.mouseMoveEvent = self.mini_mouse_move
            self.mini_icon.mouseReleaseEvent = self.mini_mouse_release

            self.mini_widget.show()
            self.mini_icon.show()
            self.show()
        else:
            self.restore_from_mini()

    def mini_mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            self.mini_dragging = True
            self.mini_drag_offset = event.globalPos() - self.pos()
            self.mini_press_global_pos = event.globalPos()

    def mini_mouse_move(self, event):
        if self.mini_dragging and event.buttons() == Qt.LeftButton and self.mini_drag_offset is not None:
            self.move(event.globalPos() - self.mini_drag_offset)

    def mini_mouse_release(self, event):
        if event.button() == Qt.LeftButton:
            is_a_click = True  # Varsayılan olarak tıklama kabul et
            self.mini_position = self.pos()

            if self.mini_dragging and self.mini_press_global_pos is not None:
                moved_distance = (event.globalPos() - self.mini_press_global_pos).manhattanLength()
                if moved_distance >= 5:  # Sürüklemeyi tıklamadan ayırmak için eşik değer
                    is_a_click = False

            if is_a_click:
                self.restore_from_mini()

            # Sürükleme durumu değişkenlerini sıfırla
            self.mini_dragging = False
            self.mini_drag_offset = None
            self.mini_press_global_pos = None

    def restore_from_mini(self):
        if hasattr(self, 'mini_widget') and self.mini_widget is not None:
            self.mini_widget.hide()
            self.mini_widget.deleteLater()
            self.mini_widget = None
        if hasattr(self, 'mini_icon') and self.mini_icon is not None:
            self.mini_icon.deleteLater()
            self.mini_icon = None

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(220, 400)  # Minimum genişlik 220 piksel
        self.setMaximumSize(800, 1000)
        if self.normal_geometry:
            self.setGeometry(self.normal_geometry)
        if self.mini_position:
            self.settings.setdefault("window", {})["miniPosition"] = {
                "x": self.mini_position.x(),
                "y": self.mini_position.y()
            }
            self.save_settings()
            print(f"📌 Mini mod konumu kaydedildi: {self.mini_position}")
        self.is_minimized = False
        self.bg_frame.show()
        if hasattr(self, 'resize_handle'):
            self.resize_handle.show()

        self.show()
        self.raise_()
        self.activateWindow()

        # Mini moddan çıkarken sürükleme değişkenlerini de sıfırla
        self.mini_dragging = False
        self.mini_drag_offset = None
        self.mini_press_global_pos = None

    def find_matching_rule(self, text: str) -> Optional[ClipboardRule]:
        for rule_item in self.rules:
            try:
                if re.match(rule_item.regex, text):
                    return rule_item
            except:
                pass
        return None

    def format_display_text(self, template: str, text: str) -> str:
        return template.replace("{text}", text)

    def get_next_available_shortcut(self, prefix: str = "") -> Optional[str]:
        used_sc = set()

        # Tüm kullanılan kısayolları topla
        for snip in self.snippets:
            if snip.shortcut:
                used_sc.add(snip.shortcut.lower())

        for pinned_item in self.pinned_items:
            if pinned_item.shortcut:
                used_sc.add(pinned_item.shortcut.lower())

        for group in self.groups:
            if group.shortcut:
                used_sc.add(group.shortcut.lower())
            for item in group.items:
                if item.shortcut:
                    used_sc.add(item.shortcut.lower())

        # Default rules'ların kısayollarını da ekle
        for rule in self.rules:
            if rule.shortcut:
                used_sc.add(rule.shortcut.lower())

        print(f"🔍 Kullanılan kısayollar: {sorted(used_sc)}")

        # Kısayol öncelik sırası - daha sistematik
        shortcuts_to_try = []

        # Alt+1-9 (en yüksek öncelik) - ama rules'lar için ayrılmış olanları atla
        reserved_shortcuts = {'alt+1', 'alt+2', 'alt+3', 'alt+4'}  # Default rules için ayrılmış

        for i in range(5, 10):  # Alt+5'ten başla
            shortcuts_to_try.append(f"alt+{i}")

        # Alt+0
        shortcuts_to_try.append("alt+0")

        # Alt+harfler (a-z) - ama snippet'ler için ayrılmış olanları atla
        reserved_letters = {'alt+q', 'alt+w'}  # Default snippet'ler için ayrılmış

        for c in range(ord('a'), ord('z') + 1):
            shortcut = f"alt+{chr(c)}"
            if shortcut not in reserved_letters:
                shortcuts_to_try.append(shortcut)

        # F1-F12
        for i in range(1, 13):
            shortcuts_to_try.append(f"f{i}")

        # Ctrl+Alt+harfler
        for c in range(ord('a'), ord('z') + 1):
            shortcuts_to_try.append(f"ctrl+alt+{chr(c)}")

        # Shift+Alt+harfler
        for c in range(ord('a'), ord('z') + 1):
            shortcuts_to_try.append(f"shift+alt+{chr(c)}")

        print(f"🎯 Deneyeceğim kısayollar: {shortcuts_to_try[:10]}...")

        for shortcut in shortcuts_to_try:
            if shortcut not in used_sc and shortcut not in reserved_shortcuts:
                print(f"✅ Seçilen kısayol: {shortcut}")
                return shortcut

        print("❌ Uygun kısayol bulunamadı!")
        return None

    @pyqtSlot(str)
    def process_clipboard_item(self, text: str):
        # Blacklist kontrolü
        blacklist_regexes = self.settings.get("filters", {}).get("blacklist", [])
        for block_pattern in blacklist_regexes:
            if block_pattern.strip():
                try:
                    if re.search(block_pattern.strip(), text):
                        print(f"🚫 Öğe kara listeye takıldı ({block_pattern})")
                        return
                except re.error as e:
                    print(f"❌ Hatalı regex kuralı ({block_pattern}): {e}")

        matched_rule = self.find_matching_rule(text)
        if not matched_rule:
            matched_rule = ClipboardRule(id="general", name="Genel", regex=".*", display_template="{text}",
                                         action="paste", group="Genel")

        # İlaç bilgisini kontrol et
        drug_info = None
        if matched_rule.id == "ilac_barkod":  # İlaç barkodu kuralı
            drug_info = self.get_drug_info(text.strip())

        new_clip_item = ClipboardItem(
            id=f"item_{int(time.time())}_{uuid.uuid4().hex[:8]}",
            text=text,
            original_text=text,
            display_text=self.format_display_text(matched_rule.display_template, text),
            timestamp=time.time(),
            rule=matched_rule,
            shortcut=self.get_next_available_shortcut(),
            drug_info=drug_info
        )
        self.add_to_grouped_history(new_clip_item)

    def add_to_grouped_history(self, item_to_add: ClipboardItem):
        now = time.time()
        group_time_win = self.settings.get("behavior", {}).get("groupTimeWindow", 60000) / 1000
        target_grp = None

        for grp_item in self.groups:
            if (grp_item.group_name == item_to_add.rule.group and
                    (now - grp_item.last_updated) <= group_time_win):
                target_grp = grp_item
                break

        if not target_grp:
            # Yeni grup oluşturuluyor
            print(f"📁 Yeni grup oluşturuluyor: {item_to_add.rule.group}")
            target_grp = ItemGroup(
                id=f"group_{int(time.time())}_{uuid.uuid4().hex[:8]}",
                group_name=item_to_add.rule.group,
                display_name=item_to_add.rule.group,
                shortcut=None  # Başlangıçta kısayol yok
            )
            self.groups.insert(0, target_grp)

        # Tüm geçmişi kontrol et ve varsa eskisini sil (Deduplication)
        item_found_and_deleted = False
        empty_groups = []
        for grp in self.groups:
            # Listeyi tersten dön ki silerken indeks kaymasın
            for i in range(len(grp.items) - 1, -1, -1):
                existing_item = grp.items[i]
                if existing_item.original_text == item_to_add.original_text:
                    grp.items.pop(i)
                    item_found_and_deleted = True
                    print(f"📋 Aynı öğe bulundu, eski kaydı silindi: {item_to_add.original_text[:30]}...")

            if not grp.items:
                empty_groups.append(grp)

        # İçinde hiç eleman kalmayan grupları sil
        for empty_grp in empty_groups:
            if empty_grp in self.groups:
                self.groups.remove(empty_grp)
                
        # target_grp boşalmış veya silinmişse, listeye ekli olduğundan emin ol (Eğer önceden oluşturulup boşaldıysa vs.)
        if target_grp not in self.groups:
            self.groups.insert(0, target_grp)

        # Öğeyi gruba ekle
        target_grp.items.insert(0, item_to_add)
        target_grp.last_updated = now

        # Grup kısayol mantığı
        if len(target_grp.items) == 1:
            # İlk öğe eklendiğinde: öğenin kısayolunu gruba VER, öğeden AL
            if item_to_add.shortcut:
                target_grp.shortcut = item_to_add.shortcut
                item_to_add.shortcut = None  # Öğeden kısayolu kaldır
                print(f"🔄 İlk öğenin kısayolu gruba aktarıldı: {target_grp.shortcut}")
            else:
                # İlk öğenin kısayolu yoksa gruba yeni bir tane ata
                target_grp.shortcut = self.get_next_available_shortcut(f"{item_to_add.rule.group}_group")
                print(f"🆕 Gruba yeni kısayol atandı: {target_grp.shortcut}")
        elif len(target_grp.items) == 2:
            # İkinci öğe eklendiğinde: grup kısayolunu koru, yeni öğeye kısayol verme
            item_to_add.shortcut = None
            print(f"🔒 Grup kısayolu korundu: {target_grp.shortcut}, yeni öğeye kısayol verilmedi")
        else:
            # Üçüncü ve sonraki öğeler: kısayol verme
            item_to_add.shortcut = None
            print(f"➕ Gruba öğe eklendi, kısayol verilmedi")

        # Display name güncelle
        target_grp.display_name = f"{target_grp.group_name} ({len(target_grp.items)})" if len(
            target_grp.items) > 1 else target_grp.group_name

        max_items_setting = self.settings.get("behavior", {}).get("maxItems", 50)
        if len(self.groups) > max_items_setting:
            self.groups = self.groups[:max_items_setting]

        print(f"📊 Grup durumu: {target_grp.display_name}, Kısayol: {target_grp.shortcut}")

        # Geçmişi kaydet
        self.save_groups()

        self.render_history()
        self.update_tab_badges()

    def render_history(self):
        while self.history_content_layout.count():
            child_widget = self.history_content_layout.takeAt(0)
            if child_widget.widget():
                child_widget.widget().deleteLater()

        if not self.groups:
            empty_lbl_color = QColor(self.settings.get('appearance', {}).get('textColor', '#FFFFFF'))
            empty_lbl_color.setAlpha(150)
            empty_history_label = QLabel("Henüz clipboard öğesi yok.\nKopyalanan içerikler burada görünecek.")
            empty_history_label.setAlignment(Qt.AlignCenter)
            empty_history_label.setWordWrap(True)  # Python'da wordWrap ayarı
            empty_history_label.setStyleSheet(
                f"QLabel {{color:{empty_lbl_color.name(QColor.HexArgb)}; font-style:italic; background-color:rgba(255,255,255,0.05); border:1px dashed rgba(255,255,255,0.2); border-radius:8px; padding:20px; margin:10px;}}")
            self.history_content_layout.addWidget(empty_history_label)
            return

        for group_data in self.groups:
            group_item_frame = QFrame()
            group_item_frame.setStyleSheet(
                """
                QFrame {
                    background-color:rgba(255,255,255,0.05); 
                    border:1px solid rgba(255,255,255,0.2); 
                    border-radius:8px; 
                    margin:2px; 
                    padding:2px;
                }
                """)
            group_item_layout = QVBoxLayout(group_item_frame)

            header_grp_widget = QWidget()
            header_grp_widget.setStyleSheet(
                "QWidget {background-color:rgba(255,255,255,0.1); border-radius:4px; padding:5px;}")
            header_grp_layout = QHBoxLayout(header_grp_widget)
            header_grp_layout.setContentsMargins(10, 5, 10, 5)

            header_label_txt = f"<b>{group_data.display_name}</b>"
            if group_data.shortcut:
                header_label_txt += f" ({group_data.shortcut})"
            header_display_label = QLabel(header_label_txt)
            header_display_label.setStyleSheet(
                f"color:{self.settings.get('appearance', {}).get('textColor', '#FFFFFF')}; font-size:14px;")
            header_display_label.setWordWrap(True)
            header_display_label.setMaximumWidth(150)  # Responsive genişlik
            header_grp_layout.addWidget(header_display_label)
            header_grp_layout.addStretch()

            toggle_grp_btn = QPushButton("▼" if not group_data.collapsed else "▶")
            toggle_grp_btn.clicked.connect(lambda checked, g_data=group_data: self.toggle_group(g_data))
            toggle_grp_btn.setMaximumSize(20, 20)
            toggle_grp_btn.setMinimumSize(18, 18)
            toggle_grp_btn.setStyleSheet(
                "QPushButton {background-color:rgba(255,193,7,0.7); color:white; border-radius:3px; font-weight:bold;} QPushButton:hover {background-color:rgba(255,193,7,0.9);}")

            delete_grp_btn = QPushButton("×")
            delete_grp_btn.clicked.connect(lambda checked, g_del_data=group_data: self.delete_group(g_del_data))
            delete_grp_btn.setMaximumSize(20, 20)
            delete_grp_btn.setMinimumSize(18, 18)
            delete_grp_btn.setStyleSheet(
                "QPushButton {background-color:rgba(255,0,0,0.7); color:white; border-radius:3px; font-weight:bold;} QPushButton:hover {background-color:rgba(255,0,0,0.9);}")

            header_grp_layout.addWidget(toggle_grp_btn)
            header_grp_layout.addWidget(delete_grp_btn)
            group_item_layout.addWidget(header_grp_widget)

            if not group_data.collapsed:
                for item_detail in group_data.items:
                    clip_item_widget = ClipboardItemWidget(item_detail, self)
                    clip_item_widget.paste_clicked.connect(
                        lambda i_paste=item_detail: self.execute_item_action(i_paste))
                    clip_item_widget.copy_clicked.connect(lambda i_copy=item_detail: self.copy_item(i_copy))
                    clip_item_widget.pin_clicked.connect(lambda i_pin=item_detail: self.pin_item(i_pin))
                    clip_item_widget.delete_clicked.connect(
                        lambda i_del=item_detail, grp_context=group_data: self.delete_item(grp_context, i_del))
                    group_item_layout.addWidget(clip_item_widget)

            self.history_content_layout.addWidget(group_item_frame)

    def render_pinned(self):
        while self.pinned_content_layout.count():
            child_pin_widget = self.pinned_content_layout.takeAt(0)
            if child_pin_widget.widget():
                child_pin_widget.widget().deleteLater()

        if not self.pinned_items:
            empty_pin_lbl_color = QColor(self.settings.get('appearance', {}).get('textColor', '#FFFFFF'))
            empty_pin_lbl_color.setAlpha(150)
            empty_pinned_label = QLabel(
                "📌 Henüz sabitlenmiş öğe yok\n\nGeçmiş sekmesindeki 📌 butonunu kullanarak\nsık kullandığınız öğeleri sabitleyebilirsiniz.")
            empty_pinned_label.setAlignment(Qt.AlignCenter)
            empty_pinned_label.setWordWrap(True)  # Python'da wordWrap ayarı
            empty_pinned_label.setStyleSheet(
                f"QLabel {{color:{empty_pin_lbl_color.name(QColor.HexArgb)}; font-style:italic; background-color:rgba(255,255,255,0.05); border:1px dashed rgba(255,255,255,0.2); border-radius:8px; padding:20px; margin:10px;}}")
            self.pinned_content_layout.addWidget(empty_pinned_label)
            return

        for pinned_data_item in self.pinned_items:
            temp_clip_item = ClipboardItem(
                id=pinned_data_item.id,
                text=pinned_data_item.original_text,
                original_text=pinned_data_item.original_text,
                display_text=pinned_data_item.display_text,
                timestamp=pinned_data_item.timestamp,
                rule=pinned_data_item.rule or ClipboardRule(id="general", name="Genel", regex=".*",
                                                            display_template="{text}", action="paste", group="Genel"),
                shortcut=pinned_data_item.shortcut,
                drug_info=pinned_data_item.drug_info
            )

            pinned_item_widget = ClipboardItemWidget(temp_clip_item, self)
            pinned_item_widget.paste_clicked.connect(lambda p_paste=pinned_data_item: self.execute_pinned_item(p_paste))
            pinned_item_widget.copy_clicked.connect(
                lambda p_copy=pinned_data_item: self.copy_text(p_copy.original_text))
            pinned_item_widget.delete_clicked.connect(lambda p_del=pinned_data_item: self.unpin_item(p_del))

            for btn_item in pinned_item_widget.findChildren(QPushButton):
                if btn_item.text() == "📌":
                    btn_item.hide()

            self.pinned_content_layout.addWidget(pinned_item_widget)

    def render_snippets(self):
        for i_snip_render in reversed(range(self.snippets_content_layout.count())):
            item_snip_widget = self.snippets_content_layout.itemAt(i_snip_render).widget()
            if item_snip_widget and not isinstance(item_snip_widget, QPushButton) or (
                    isinstance(item_snip_widget, QPushButton) and item_snip_widget.text() != "+ Yeni Snippet Ekle"):
                item_snip_widget.deleteLater()
            elif item_snip_widget is None and self.snippets_content_layout.itemAt(i_snip_render).layout() is not None:
                inner_snip_layout = self.snippets_content_layout.itemAt(i_snip_render).layout()
                while inner_snip_layout.count():
                    inner_snip_item_widget = inner_snip_layout.takeAt(0)
                    if inner_snip_item_widget.widget():
                        inner_snip_item_widget.widget().deleteLater()

        if not self.snippets:
            if self.snippets_content_layout.count() <= 1:
                for i_empty_snip in reversed(range(self.snippets_content_layout.count())):
                    widget_empty_snip = self.snippets_content_layout.itemAt(i_empty_snip).widget()
                    if isinstance(widget_empty_snip, QLabel) and "Henüz snippet yok" in widget_empty_snip.text():
                        widget_empty_snip.deleteLater()

                empty_snip_lbl_color = QColor(self.settings.get('appearance', {}).get('textColor', '#FFFFFF'))
                empty_snip_lbl_color.setAlpha(150)
                empty_snippet_label = QLabel(
                    "📝 Henüz snippet yok\n\nYukarıdaki '+' butonunu kullanarak\nsık kullandığınız metinleri ekleyebilirsiniz.")
                empty_snippet_label.setAlignment(Qt.AlignCenter)
                empty_snippet_label.setWordWrap(True)
                empty_snippet_label.setStyleSheet(
                    f"QLabel {{color:{empty_snip_lbl_color.name(QColor.HexArgb)}; font-style:italic; background-color:rgba(255,255,255,0.05); border:1px dashed rgba(255,255,255,0.2); border-radius:8px; padding:20px; margin:10px;}}")
                self.snippets_content_layout.addWidget(empty_snippet_label)
            return
        else:
            for i_remove_empty_snip in reversed(range(self.snippets_content_layout.count())):
                widget_remove_empty_snip = self.snippets_content_layout.itemAt(i_remove_empty_snip).widget()
                if isinstance(widget_remove_empty_snip,
                              QLabel) and "Henüz snippet yok" in widget_remove_empty_snip.text():
                    widget_remove_empty_snip.deleteLater()

        snippet_categories = {}
        for snip_data_item in self.snippets:
            cat_name = snip_data_item.category
            if cat_name not in snippet_categories:
                snippet_categories[cat_name] = []
            snippet_categories[cat_name].append(snip_data_item)

        font_sz = self.settings.get('appearance', {}).get('fontSize', 12)
        cat_lbl_clr = QColor(self.settings.get('appearance', {}).get('textColor', '#FFFFFF'))
        cat_lbl_clr.setAlpha(170)

        for cat_key, snippets_list_in_cat in snippet_categories.items():
            category_title_label = QLabel(f"<b>{cat_key}</b>")
            category_title_label.setStyleSheet(
                f"QLabel {{color:{cat_lbl_clr.name(QColor.HexArgb)}; margin-top:10px; padding:5px; border-bottom:1px solid rgba(255,255,255,0.2); font-size:{font_sz - 1}px;}}")
            category_title_label.setWordWrap(True)
            self.snippets_content_layout.addWidget(category_title_label)

            for snip_detail_item in snippets_list_in_cat:
                snip_item_frame = QFrame()
                snip_item_frame.setStyleSheet(
                    """
                    QFrame {
                        background-color:rgba(33,150,243,0.3); 
                        border-radius:6px; 
                        border-left:4px solid #2196f3; 
                        padding:6px; 
                        margin:2px;
                    } 
                    QFrame:hover {
                        background-color:rgba(33,150,243,0.4);
                    } 
                    QLabel {
                        color:white; 
                        background-color:transparent;
                    } 
                    QPushButton {
                        background-color:rgba(255,255,255,0.2); 
                        color:white; 
                        border:none; 
                        border-radius:3px; 
                        padding:2px; 
                        font-weight:bold;
                        min-width: 25px;
                        max-width: 30px;
                    } 
                    QPushButton:hover {
                        background-color:rgba(255,255,255,0.3);
                    }
                    """
                )
                snip_item_layout = QVBoxLayout(snip_item_frame)
                snip_item_layout.setContentsMargins(4, 4, 4, 4)
                snip_item_layout.setSpacing(2)

                # Frame'in tam genişlikte olmasını sağla
                snip_item_frame.setSizePolicy(snip_item_frame.sizePolicy().Expanding,
                                              snip_item_frame.sizePolicy().Preferred)

                top_snip_layout = QHBoxLayout()
                top_snip_layout.setSpacing(8)  # Biraz daha boşluk

                # Snippet adı
                snip_name_label = QLabel(f"<b>{snip_detail_item.name}</b>")
                top_snip_layout.addWidget(snip_name_label)

                # Compact action type indicator - TEK KARAKTER SIMGE
                action_icon = ""
                action_tooltip = ""
                if snip_detail_item.action_type == 'execute_command':
                    action_icon = "⚡"  # Şimşek - Komut çalıştırma
                    action_tooltip = "Komut Çalıştır"
                elif snip_detail_item.action_type == 'execute_python':
                    action_icon = "🐍"  # Yılan - Python
                    action_tooltip = "Python Scripti"
                else:
                    action_icon = "📋"  # Clipboard - Yapıştır
                    action_tooltip = "Metin Yapıştır"

                action_icon_label = QLabel(action_icon)
                action_icon_label.setToolTip(action_tooltip)
                action_icon_label.setStyleSheet(f"""
                    color: #ddd; 
                    font-size: {font_sz}px;
                    background-color: rgba(255,255,255,0.1);
                    border-radius: 10px;
                    padding: 2px 4px;
                    min-width: 16px;
                    max-width: 20px;
                """)
                action_icon_label.setAlignment(Qt.AlignCenter)
                top_snip_layout.addWidget(action_icon_label)

                top_snip_layout.addStretch()

                paste_snip_btn = QPushButton("🚀")
                paste_snip_btn.setToolTip("Çalıştır / Yapıştır")
                paste_snip_btn.clicked.connect(lambda checked, s_paste=snip_detail_item: self.execute_snippet(s_paste))
                paste_snip_btn.setMaximumSize(30, 25)

                edit_snip_btn = QPushButton("✏️")
                edit_snip_btn.setToolTip("Düzenle")
                edit_snip_btn.clicked.connect(
                    lambda checked, s_edit=snip_detail_item: self.show_add_snippet_dialog(s_edit))
                edit_snip_btn.setMaximumSize(30, 25)

                delete_snip_btn = QPushButton("×")
                delete_snip_btn.setToolTip("Sil")
                delete_snip_btn.clicked.connect(lambda checked, s_del=snip_detail_item: self.delete_snippet(s_del))
                delete_snip_btn.setMaximumSize(30, 25)

                top_snip_layout.addWidget(paste_snip_btn)
                top_snip_layout.addWidget(edit_snip_btn)
                top_snip_layout.addWidget(delete_snip_btn)
                snip_item_layout.addLayout(top_snip_layout)

                # Content display - Responsive içerik gösterimi
                content_text = ""
                if snip_detail_item.action_type == 'execute_command':
                    content_text = snip_detail_item.command or ""
                    snip_content_label = QLabel(content_text)
                    snip_content_label.setStyleSheet(
                        "color:#ccc; font-family: 'Courier New', monospace; font-size:10px;")
                elif snip_detail_item.action_type == 'execute_python':
                    content_text = snip_detail_item.python_code[:80] + "..." if len(
                        snip_detail_item.python_code or "") > 80 else (snip_detail_item.python_code or "")
                    snip_content_label = QLabel(content_text)
                    snip_content_label.setStyleSheet(
                        "color:#ccc; font-family: 'Courier New', monospace; font-size:10px;")
                else:
                    content_text = snip_detail_item.content[:80] + "..." if len(
                        snip_detail_item.content) > 80 else snip_detail_item.content
                    snip_content_label = QLabel(content_text)
                    snip_content_label.setStyleSheet("color:#ccc; font-size:11px;")

                snip_content_label.setWordWrap(True)
                snip_item_layout.addWidget(snip_content_label)

                if snip_detail_item.shortcut:
                    snip_shortcut_label = QLabel(f"Kısayol: {snip_detail_item.shortcut}")
                    snip_shortcut_label.setStyleSheet("color:#aaa; font-size:9px;")
                    snip_shortcut_label.setWordWrap(True)
                    snip_item_layout.addWidget(snip_shortcut_label)

                self.snippets_content_layout.addWidget(snip_item_frame)

        # Layout'u yenile
        self.snippets_content_layout.update()

        # Qt shortcuts'ları güncelle
        self.setup_qt_shortcuts()

    def update_tab_badges(self):
        self.tabs.setTabText(0, f"📋 Geçmiş ({len(self.groups)})")
        self.tabs.setTabText(1, f"📌 Sabit ({len(self.pinned_items)})")
        self.tabs.setTabText(2, f"📝 Snippet ({len(self.snippets)})")

    def handle_global_shortcut(self, shortcut_key: str):
        print(f"🔍 İşlenen kısayol: {shortcut_key}")

        found = False

        # Snippet'leri kontrol et
        for snippet in self.snippets:
            if snippet.shortcut and snippet.shortcut.lower() == shortcut_key:
                print(f"📝 Snippet bulundu: {snippet.name}")
                self.execute_snippet_safe(snippet)
                found = True
                break

        if found:
            return

        # Sabitlenmiş öğeler
        for pinned_item in self.pinned_items:
            if pinned_item.shortcut and pinned_item.shortcut.lower() == shortcut_key:
                print(f"📌 Sabitlenmiş öğe bulundu: {pinned_item.display_text[:20]}...")
                self.execute_pinned_item_safe(pinned_item)
                found = True
                break

        if found:
            return

        # Gruplar
        for group in self.groups:
            if group.shortcut and group.shortcut.lower() == shortcut_key:
                print(f"📁 Grup bulundu: {group.display_name}")
                self.execute_group_action_safe(group)
                found = True
                break

        if found:
            return

        # Tekil öğeler
        for group in self.groups:
            for item in group.items:
                if item.shortcut and item.shortcut.lower() == shortcut_key:
                    print(f"📋 Öğe bulundu: {item.display_text[:20]}...")
                    self.execute_item_action_safe(item)
                    found = True
                    break
            if found:
                break

        if not found:
            print(f"❌ Kısayol bulunamadı: {shortcut_key}")
            print("🔍 Mevcut kısayollar:")

            # Debug için mevcut kısayolları listele
            all_shortcuts = []

            for snippet in self.snippets:
                if snippet.shortcut:
                    all_shortcuts.append(f"📝 {snippet.shortcut} -> {snippet.name}")

            for pinned_item in self.pinned_items:
                if pinned_item.shortcut:
                    all_shortcuts.append(f"📌 {pinned_item.shortcut} -> {pinned_item.display_text[:20]}...")

            for group in self.groups:
                if group.shortcut:
                    all_shortcuts.append(f"📁 {group.shortcut} -> {group.display_name}")
                for item in group.items:
                    if item.shortcut:
                        all_shortcuts.append(f"📋 {item.shortcut} -> {item.display_text[:20]}...")

            for sc in all_shortcuts[:5]:  # Sadece ilk 5'ini göster
                print(f"   {sc}")

            if len(all_shortcuts) > 5:
                print(f"   ... ve {len(all_shortcuts) - 5} tane daha")

    def _prepare_for_action(self):
        """Hides window if visible and returns its previous state."""
        was_visible = self.isVisible()
        if was_visible:
            self.hide()
            QApplication.processEvents()
            time.sleep(0.1)
        return was_visible

    def _handle_snippet_execution(self, snippet: Snippet):
        """Helper to decide snippet action."""
        if snippet.action_type == 'execute_command' and snippet.command:
            self.run_snippet_command(snippet)
        elif snippet.action_type == 'execute_python' and snippet.python_code:
            self.run_python_code(snippet)
        else:  # Default is paste
            current_datetime = datetime.now()
            content = snippet.content.replace("{DATE}", current_datetime.strftime("%d.%m.%Y")) \
                .replace("{TIME}", current_datetime.strftime("%H:%M:%S")) \
                .replace("{DATETIME}", current_datetime.strftime("%d.%m.%Y %H:%M:%S"))
            
            # Değişkenleri değiştir
            for k, v in self.settings.get("variables", {}).items():
                content = content.replace(k, str(v))
                
            self.perform_smart_paste(content)

    def run_python_code(self, snippet: Snippet):
        """Executes Python code in a non-blocking way."""

        def python_thread():
            try:
                print(f"🐍 Python kodu yürütülüyor: {snippet.name}")

                # Değişkenleri kod içinde değiştir
                python_code_executed = snippet.python_code
                if python_code_executed:
                    for k, v in self.settings.get("variables", {}).items():
                        python_code_executed = python_code_executed.replace(k, str(v))

                # Python kodunu geçici dosyaya yaz
                import tempfile

                # Python script'ine encoding header'ı ekle
                python_code_with_encoding = f"""# -*- coding: utf-8 -*-
import sys
import os

# Türkçe karakter desteği için
if sys.platform.startswith('win'):
    import locale
    # Windows için console encoding ayarla
    try:
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.detach())
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.detach())
    except:
        pass

# Kullanıcının kodu
{python_code_executed}
"""

                with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False,
                                                 encoding='utf-8', newline='\n') as temp_file:
                    temp_file.write(python_code_with_encoding)
                    temp_file_path = temp_file.name

                # Environment değişkenleri ayarla
                env = os.environ.copy()
                env['PYTHONIOENCODING'] = 'utf-8'
                env['PYTHONUTF8'] = '1'

                # Windows için özel ayarlar
                if sys.platform.startswith('win'):
                    env['PYTHONLEGACYWINDOWSSTDIO'] = '0'

                # Python executable'ı belirle
                if getattr(sys, 'frozen', False):
                    # PyInstaller ile derlendiğinde: exe'nin kendi Python ortamını kullan
                    # sys.executable = clipboardmanager.exe
                    # --run-script argümanı dosyanın başındaki handler tarafından yakalanır
                    python_exe = sys.executable
                    cmd_args = [python_exe, '--run-script', temp_file_path]
                else:
                    python_exe = sys.executable
                    cmd_args = [python_exe, temp_file_path]

                # Python'u subprocess ile çalıştır
                process = subprocess.Popen(
                    cmd_args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    env=env
                )
                stdout, stderr = process.communicate(timeout=30)  # 30 saniye zaman aşımı

                # Geçici dosyayı sil
                try:
                    os.unlink(temp_file_path)
                except:
                    pass

                if process.returncode == 0:
                    if stdout.strip():
                        # Çıktıyı temizle ve düzelt
                        clean_output = stdout.strip()
                        self.show_notification("🐍 Python Kodu Tamamlandı",
                                               f"{snippet.name}\nÇıktı: {clean_output[:150]}")
                    else:
                        self.show_notification("🐍 Python Kodu Tamamlandı",
                                               f"{snippet.name}\nKod başarıyla çalıştırıldı.")
                else:
                    # Hata mesajını temizle
                    clean_error = stderr.strip()
                    self.show_notification("❌ Python Kodu Hatası", f"{snippet.name}\nHata: {clean_error[:150]}")

            except subprocess.TimeoutExpired:
                try:
                    os.unlink(temp_file_path)
                except:
                    pass
                self.show_notification("⏳ Python Kodu Zaman Aşımı", f"{snippet.name}\nKod 30 saniyeden uzun sürdü.")
            except Exception as e:
                try:
                    os.unlink(temp_file_path)
                except:
                    pass
                self.show_notification("❌ Python Kodu Çalıştırılamadı", f"{snippet.name}\n{str(e)}")

        threading.Thread(target=python_thread, daemon=True).start()

    def run_snippet_command(self, snippet: Snippet):
        """Executes a command in a non-blocking way."""

        def command_thread():
            try:
                print(f"🚀 Komut yürütülüyor: {snippet.command}")
                
                # Değişkenleri komut içinde değiştir
                command_executed = snippet.command
                if command_executed:
                    for k, v in self.settings.get("variables", {}).items():
                        command_executed = command_executed.replace(k, str(v))
                        
                # shell=True güvenlik riski oluşturabilir. Kullanıcıyı uyarmak önemlidir.
                process = subprocess.Popen(command_executed, shell=True, stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
                stdout, stderr = process.communicate(timeout=30)  # 30 saniye zaman aşımı

                if process.returncode == 0:
                    self.show_notification("✅ Komut Tamamlandı", f"{snippet.name}\nÇıktı: {stdout[:150]}")
                else:
                    self.show_notification("❌ Komut Hatası", f"{snippet.name}\nHata: {stderr[:150]}")
            except subprocess.TimeoutExpired:
                self.show_notification("⏳ Komut Zaman Aşımı", f"{snippet.name}\nKomut 30 saniyeden uzun sürdü.")
            except Exception as e:
                self.show_notification("❌ Komut Çalıştırılamadı", f"{snippet.name}\n{str(e)}")

        threading.Thread(target=command_thread, daemon=True).start()

    def execute_item_action(self, item_action: ClipboardItem):
        was_visible = self._prepare_for_action()
        if item_action.rule.action == "paste":
            self.perform_smart_paste(item_action.original_text)
        elif item_action.rule.action == "openUrl":
            import webbrowser
            webbrowser.open(item_action.original_text)
        else:
            self.perform_smart_paste(item_action.original_text)
        if was_visible:
            self.show()

    def execute_item_action_safe(self, item_action: ClipboardItem):
        """Global kısayol için güvenli versiyon"""
        try:
            if item_action.rule.action == "paste":
                self.perform_smart_paste(item_action.original_text)
                self.show_notification("✅ Yapıştırıldı", f"{item_action.display_text[:30]}...")
            elif item_action.rule.action == "openUrl":
                import webbrowser
                webbrowser.open(item_action.original_text)
                self.show_notification("🔗 URL açıldı", f"{item_action.original_text[:30]}...")
            else:
                self.perform_smart_paste(item_action.original_text)
                self.show_notification("✅ Yapıştırıldı", f"{item_action.display_text[:30]}...")
        except Exception as e:
            print(f"Öğe işleme hatası: {e}")
            self.show_notification("❌ Hata", str(e))

    def execute_group_action(self, group_action_item: ItemGroup):
        was_visible = self._prepare_for_action()
        if group_action_item.group_action == "pasteAll":
            self.perform_smart_paste('\n'.join([item.original_text for item in group_action_item.items]))
        elif group_action_item.group_action == "pasteFirst" and group_action_item.items:
            self.perform_smart_paste(group_action_item.items[0].original_text)
        if was_visible:
            self.show()

    def execute_group_action_safe(self, group_action_item: ItemGroup):
        """Global kısayol için güvenli versiyon"""
        try:
            if group_action_item.group_action == "pasteAll":
                text_to_paste = '\n'.join([item.original_text for item in group_action_item.items])
                self.perform_smart_paste(text_to_paste)
                self.show_notification("✅ Grup yapıştırıldı", f"{group_action_item.display_name}")
            elif group_action_item.group_action == "pasteFirst" and group_action_item.items:
                self.perform_smart_paste(group_action_item.items[0].original_text)
                self.show_notification("✅ İlk öğe yapıştırıldı", f"{group_action_item.display_name}")
        except Exception as e:
            print(f"Grup işleme hatası: {e}")
            self.show_notification("❌ Hata", str(e))

    def execute_pinned_item(self, pinned_action_item: PinnedItem):
        was_visible = self._prepare_for_action()
        self.perform_smart_paste(pinned_action_item.original_text)
        if was_visible:
            self.show()

    def execute_pinned_item_safe(self, pinned_action_item: PinnedItem):
        """Global kısayol için güvenli versiyon"""
        try:
            self.perform_smart_paste(pinned_action_item.original_text)
            self.show_notification("✅ Sabit öğe yapıştırıldı", f"{pinned_action_item.display_text[:30]}...")
        except Exception as e:
            print(f"Sabit öğe işleme hatası: {e}")
            self.show_notification("❌ Hata", str(e))

    def execute_snippet(self, snippet_action_item: Snippet):
        was_visible = self._prepare_for_action()
        self._handle_snippet_execution(snippet_action_item)
        if was_visible and snippet_action_item.action_type == 'paste':
            self.show()

    def execute_snippet_safe(self, snippet_action_item: Snippet):
        """Global kısayol için güvenli versiyon"""
        try:
            self._handle_snippet_execution(snippet_action_item)
            if snippet_action_item.action_type == 'paste':
                self.show_notification("✅ Snippet yapıştırıldı", f"{snippet_action_item.name}")
            elif snippet_action_item.action_type == 'execute_python':
                self.show_notification("🐍 Python kodu başlatıldı", f"{snippet_action_item.name}")
            else:
                self.show_notification("🚀 Komut başlatıldı", f"{snippet_action_item.name}")
        except Exception as e:
            print(f"Snippet işleme hatası: {e}")
            self.show_notification("❌ Snippet hatası", str(e))

    def perform_smart_paste(self, text_to_paste: str):
        try:
            print(f"🔄 Yapıştırma işlemi başlatılıyor...")
            print(f"📋 Metin: {text_to_paste[:100]}...")

            # 1. Eski clipboard'u kaydet
            old_clipboard = ""
            try:
                old_clipboard = pyperclip.paste()
            except:
                pass

            # 2. Yeni metni clipboard'a kopyala
            pyperclip.copy(text_to_paste)
            print("✅ Clipboard'a kopyalandı")

            # 3. Doğrulama
            time.sleep(0.1)
            verification = pyperclip.paste()
            if verification != text_to_paste:
                print(f"❌ Clipboard doğrulama başarısız!")
                return

            print("✅ Clipboard doğrulandı")

            # 4. Yapıştırma - Çakışmayı önlemek için gecikme
            print("⏳ Yapıştırma için bekleniyor...")
            time.sleep(0.3)  # Tuş dinleyicisinin serbest kalması için

            # 5. Pyautogui ile yapıştırma
            pyautogui.FAILSAFE = False
            pyautogui.PAUSE = 0.01  # Hızlandır

            print("🖱️ Pyautogui ile yapıştırılıyor...")
            # Ctrl tuşunu ayrı ayrı basıp bırak
            pyautogui.keyDown('ctrl')
            time.sleep(0.05)  # Kısa bekleme
            pyautogui.keyDown('v')
            time.sleep(0.05)
            pyautogui.keyUp('v')
            time.sleep(0.05)
            pyautogui.keyUp('ctrl')

            print("✅ Yapıştırma komutu gönderildi")

            # 6. Eski clipboard'u geri yükle (opsiyonel)
            time.sleep(0.5)  # Yapıştırma işleminin tamamlanması için

        except Exception as e:
            print(f"❌ Yapıştırma hatası: {e}")
            self.show_notification("❌ Yapıştırma hatası", str(e))
            import traceback
            traceback.print_exc()

    def show_notification(self, title: str, msg_text: str):
        """Ana thread'den güvenli bildirim gösterme"""
        try:
            if hasattr(self, 'tray') and self.tray:
                self.tray.showMessage(title, msg_text, QSystemTrayIcon.Information, 2000)
            print(f"Bildirim: {title} - {msg_text}")
        except Exception as e:
            print(f"Bildirim hatası: {e}")

    def copy_text(self, text_to_copy: str):
        pyperclip.copy(text_to_copy)
        self.show_notification("📋 Kopyalandı", text_to_copy[:50] + "...")

    def copy_item(self, item_to_copy: ClipboardItem):
        self.copy_text(item_to_copy.original_text)

    def pin_item(self, item_to_pin: ClipboardItem):
        new_pinned_item = PinnedItem(
            id=f"pinned_{int(time.time())}_{uuid.uuid4().hex[:8]}",
            original_text=item_to_pin.original_text,
            display_text=item_to_pin.display_text,
            shortcut=self.get_next_available_shortcut("pinned"),
            rule=item_to_pin.rule,
            drug_info=item_to_pin.drug_info
        )
        self.pinned_items.append(new_pinned_item)
        self.save_pinned()
        self.render_pinned()
        self.update_tab_badges()
        self.show_notification("📌 Öğe sabitlendi", "")

    def unpin_item(self, pinned_to_unpin: PinnedItem):
        self.pinned_items = [p_item for p_item in self.pinned_items if p_item.id != pinned_to_unpin.id]
        self.save_pinned()
        self.render_pinned()
        self.update_tab_badges()
        self.show_notification("📌 Sabitleme kaldırıldı", "")

    def delete_item(self, group_context: ItemGroup, item_to_delete: ClipboardItem):
        if QMessageBox.question(self, "Onay", "Bu öğeyi silmek istediğinizden emin misiniz?",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            group_context.items = [i_item for i_item in group_context.items if i_item.id != item_to_delete.id]
            if not group_context.items:
                self.groups = [g_item for g_item in self.groups if g_item.id != group_context.id]
            else:
                group_context.display_name = f"{group_context.group_name} ({len(group_context.items)})" if len(
                    group_context.items) > 1 else group_context.group_name
            self.save_groups()
            self.render_history()
            self.update_tab_badges()
            self.show_notification("🗑️ Öğe silindi", "")

    def delete_group(self, group_to_delete: ItemGroup):
        if QMessageBox.question(self, "Onay", "Bu grubu ve tüm öğelerini silmek istediğinizden emin misiniz?",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.groups = [g_del_item for g_del_item in self.groups if g_del_item.id != group_to_delete.id]
            self.save_groups()
            self.render_history()
            self.update_tab_badges()
            self.show_notification("🗑️ Grup silindi", "")

    def delete_snippet(self, snippet_to_delete: Snippet):
        if QMessageBox.question(self, "Onay", "Bu snippet'i silmek istediğinizden emin misiniz?",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.snippets = [s_del_item for s_del_item in self.snippets if s_del_item.id != snippet_to_delete.id]
            self.save_snippets()
            self.render_snippets()
            self.update_tab_badges()
            self.show_notification("🗑️ Snippet silindi", "")

    def toggle_group(self, group_to_toggle: ItemGroup):
        group_to_toggle.collapsed = not group_to_toggle.collapsed
        self.render_history()

    def clear_history(self):
        if QMessageBox.question(self, "Onay", "Tüm geçmişi temizlemek istediğinizden emin misiniz?",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.groups = []
            self.save_groups()
            self.render_history()
            self.update_tab_badges()
            self.show_notification("🗑️ Geçmiş temizlendi", "")

    def show_add_snippet_dialog(self, existing_snippet: Optional[Snippet] = None):
        snip_dialog = QDialog(self)
        snip_dialog.setWindowTitle("Snippet Düzenle" if existing_snippet else "Yeni Snippet Ekle")
        snip_dialog.setModal(True)
        snip_dialog.setMinimumWidth(450)
        snip_layout = QVBoxLayout(snip_dialog)

        snip_layout.addWidget(QLabel("Snippet Adı:"))
        name_snip_input = QLineEdit(existing_snippet.name if existing_snippet else "")
        snip_layout.addWidget(name_snip_input)

        snip_layout.addWidget(QLabel("Kategori:"))
        category_snip_input = QComboBox()
        category_snip_input.setEditable(True)
        categories = sorted(list(set(s_cat.category for s_cat in self.snippets if s_cat.category)))
        if not categories:
            categories = ["Genel"]
        category_snip_input.addItems(categories)
        if existing_snippet:
            category_snip_input.setCurrentText(existing_snippet.category)
        snip_layout.addWidget(category_snip_input)

        snip_layout.addWidget(QLabel("Kısayol (opsiyonel):"))
        shortcut_snip_input = QLineEdit(
            existing_snippet.shortcut if existing_snippet and existing_snippet.shortcut else "")
        shortcut_snip_input.setPlaceholderText("Örn: alt+e")
        snip_layout.addWidget(shortcut_snip_input)

        snip_layout.addWidget(QLabel("Eylem Türü:"))
        action_combo = QComboBox()
        action_combo.addItems(["Metin Yapıştır", "Komut Çalıştır", "Python Scripti"])
        snip_layout.addWidget(action_combo)

        content_label = QLabel("İçerik (Metin Yapıştır için):")
        snip_layout.addWidget(content_label)
        content_snip_input = QTextEdit()
        content_snip_input.setMaximumHeight(100)

        # İçerik varsa doğru şekilde yükle
        if existing_snippet and existing_snippet.content:
            content_snip_input.setPlainText(existing_snippet.content)

        snip_layout.addWidget(content_snip_input)

        command_label = QLabel("Komut (Komut Çalıştır için):")
        snip_layout.addWidget(command_label)
        command_snip_input = QLineEdit(
            existing_snippet.command if existing_snippet and existing_snippet.command else "")
        command_snip_input.setPlaceholderText("Örn: python C:/scripts/my_script.py")
        snip_layout.addWidget(command_snip_input)

        python_label = QLabel("Python Kodu (Python Scripti için):")
        snip_layout.addWidget(python_label)
        python_snip_input = QTextEdit()
        python_snip_input.setMaximumHeight(150)
        python_snip_input.setPlaceholderText("Örn:\nimport os\nprint('Merhaba Dünya!')\nos.system('dir')")

        # Monospace font ayarla
        font = QFont("Courier New", 10)
        font.setFamily("Consolas, Courier New, monospace")
        python_snip_input.setFont(font)

        # Python kodu varsa doğru şekilde yükle
        if existing_snippet and existing_snippet.python_code:
            python_snip_input.setPlainText(existing_snippet.python_code)

        snip_layout.addWidget(python_snip_input)

        warning_label = QLabel(
            "⚠️ <b>Uyarı:</b> 'Komut Çalıştır' ve 'Python Scripti' seçenekleri sisteminizde kod çalıştırabilir. Sadece güvendiğiniz kodları ekleyin.")
        warning_label.setStyleSheet(
            "background-color: rgba(255, 152, 0, 0.2); border: 1px solid #FF9800; padding: 5px; border-radius: 4px;")
        warning_label.setWordWrap(True)
        snip_layout.addWidget(warning_label)

        def toggle_action_fields(index):
            is_paste = index == 0
            is_command = index == 1
            is_python = index == 2

            content_label.setVisible(is_paste)
            content_snip_input.setVisible(is_paste)
            command_label.setVisible(is_command)
            command_snip_input.setVisible(is_command)
            python_label.setVisible(is_python)
            python_snip_input.setVisible(is_python)
            warning_label.setVisible(is_command or is_python)

        action_combo.currentIndexChanged.connect(toggle_action_fields)
        if existing_snippet:
            if existing_snippet.action_type == 'execute_command':
                action_combo.setCurrentIndex(1)
            elif existing_snippet.action_type == 'execute_python':
                action_combo.setCurrentIndex(2)
            else:
                action_combo.setCurrentIndex(0)
        else:
            action_combo.setCurrentIndex(0)
        toggle_action_fields(action_combo.currentIndex())

        buttons_snip_layout = QHBoxLayout()
        buttons_snip_layout.addStretch()
        cancel_snip_btn = QPushButton("İptal")
        cancel_snip_btn.clicked.connect(snip_dialog.reject)
        buttons_snip_layout.addWidget(cancel_snip_btn)

        save_snip_btn = QPushButton("Kaydet")
        save_snip_btn.clicked.connect(
            lambda: self.save_new_snippet(snip_dialog, name_snip_input.text(), content_snip_input.toPlainText(),
                                          category_snip_input.currentText(), shortcut_snip_input.text(),
                                          action_combo.currentText(), command_snip_input.text(),
                                          python_snip_input.toPlainText(), existing_snippet))
        buttons_snip_layout.addWidget(save_snip_btn)
        snip_layout.addLayout(buttons_snip_layout)

        snip_dialog.exec_()

    def save_new_snippet(self, dialog_ref, name_val, content_val, category_val, shortcut_val_str, action_type_str,
                         command_val, python_code_val, existing_snippet):
        if not name_val:
            QMessageBox.warning(self, "Hata", "Snippet adı boş olamaz!")
            return

        if action_type_str == "Komut Çalıştır":
            action_type = 'execute_command'
        elif action_type_str == "Python Scripti":
            action_type = 'execute_python'
        else:
            action_type = 'paste'

        if action_type == 'paste' and not content_val:
            QMessageBox.warning(self, "Hata", "Yapıştırılacak içerik boş olamaz!")
            return

        if action_type == 'execute_command' and not command_val:
            QMessageBox.warning(self, "Hata", "Çalıştırılacak komut boş olamaz!")
            return

        if action_type == 'execute_python' and not python_code_val:
            QMessageBox.warning(self, "Hata", "Python kodu boş olamaz!")
            return

        new_snip_shortcut = shortcut_val_str if shortcut_val_str else None

        if existing_snippet:
            # Var olan snippet'i düzenle
            existing_snippet.name = name_val
            existing_snippet.content = content_val if action_type == 'paste' else ""
            existing_snippet.category = category_val or "Genel"
            existing_snippet.shortcut = new_snip_shortcut
            existing_snippet.action_type = action_type
            existing_snippet.command = command_val if action_type == 'execute_command' else None
            existing_snippet.python_code = python_code_val if action_type == 'execute_python' else None
        else:
            # Yeni snippet oluştur
            if new_snip_shortcut:
                self.used_shortcuts.add(new_snip_shortcut)

            new_snippet_obj = Snippet(
                id=f"snippet_{int(time.time())}_{uuid.uuid4().hex[:8]}",
                name=name_val,
                content=content_val if action_type == 'paste' else "",
                category=category_val or "Genel",
                shortcut=new_snip_shortcut,
                action_type=action_type,
                command=command_val if action_type == 'execute_command' else None,
                python_code=python_code_val if action_type == 'execute_python' else None
            )
            self.snippets.append(new_snippet_obj)

        self.save_snippets()
        self.render_snippets()
        self.update_tab_badges()
        self.setup_qt_shortcuts()  # Kısayolları güncelle
        self.show_notification("✅ Snippet kaydedildi", name_val)
        dialog_ref.accept()

    def show_settings(self):
        settings_dialog = QDialog(self)
        settings_dialog.setWindowTitle("Ayarlar")
        settings_dialog.setModal(True)
        settings_dialog.setMinimumSize(600, 500)
        settings_dialog.setStyleSheet(
            "QDialog{background-color:#1E1E2E;color:#CDD6F4;}QLabel{color:#CDD6F4;}QCheckBox{color:#CDD6F4;}QLineEdit,QSpinBox,QComboBox{background-color:#181825;color:#CDD6F4;border:1px solid rgba(255,255,255,0.1);padding:6px;border-radius:6px;}QLineEdit:focus,QSpinBox:focus,QComboBox:focus{border:1px solid #8B5CF6;background-color:#313244;}QPushButton{background-color:rgba(255,255,255,0.05);color:#CDD6F4;border:1px solid rgba(255,255,255,0.1);padding:6px 16px;border-radius:6px;font-weight:bold;}QPushButton:hover{background-color:rgba(139,92,246,0.2);border:1px solid #8B5CF6;color:white;}QTabWidget::pane{border:none;border-top:1px solid rgba(255,255,255,0.1);background-color:transparent;margin-top:-1px;}QTabBar::tab{background-color:transparent;color:#A6ADC8;padding:8px 20px;min-width:80px;margin:0px 4px;border-bottom:2px solid transparent;font-weight:bold;}QTabBar::tab:selected{color:#8B5CF6;border-bottom:2px solid #8B5CF6;}QTabBar::tab:hover{color:#CDD6F4;background-color:rgba(255,255,255,0.03);border-radius:6px 6px 0 0;}")

        settings_layout = QVBoxLayout(settings_dialog)
        settings_tabs = QTabWidget()
        settings_tabs.setUsesScrollButtons(True)

        general_settings_tab = QWidget()
        general_settings_layout = QVBoxLayout(general_settings_tab)

        max_items_set_layout = QHBoxLayout()
        max_items_set_layout.addWidget(QLabel("Maksimum öğe sayısı:"))
        self.max_items_spin = QSpinBox()
        self.max_items_spin.setRange(10, 200)
        self.max_items_spin.setValue(self.settings.get("behavior", {}).get("maxItems", 50))
        max_items_set_layout.addWidget(self.max_items_spin)
        max_items_set_layout.addStretch()
        general_settings_layout.addLayout(max_items_set_layout)

        group_time_set_layout = QHBoxLayout()
        group_time_set_layout.addWidget(QLabel("Gruplama süresi (saniye):"))
        self.group_time_spin = QSpinBox()
        self.group_time_spin.setRange(10, 300)
        self.group_time_spin.setValue(self.settings.get("behavior", {}).get("groupTimeWindow", 60000) // 1000)
        group_time_set_layout.addWidget(self.group_time_spin)
        group_time_set_layout.addStretch()
        general_settings_layout.addLayout(group_time_set_layout)

        self.always_on_top_check = QCheckBox("Her zaman üstte")
        self.always_on_top_check.setChecked(self.settings.get("behavior", {}).get("alwaysOnTop", True))
        general_settings_layout.addWidget(self.always_on_top_check)
        general_settings_layout.addStretch()

        appearance_settings_tab = QWidget()
        appearance_settings_layout = QVBoxLayout(appearance_settings_tab)

        bg_color_set_layout = QHBoxLayout()
        bg_color_set_layout.addWidget(QLabel("Arka plan rengi:"))
        self.bg_color_edit = QLineEdit(
            self.settings.get("appearance", {}).get("backgroundColor", "rgba(30,30,30,0.95)"))
        bg_color_set_layout.addWidget(self.bg_color_edit)
        appearance_settings_layout.addLayout(bg_color_set_layout)

        text_color_set_layout = QHBoxLayout()
        text_color_set_layout.addWidget(QLabel("Yazı rengi:"))
        self.text_color_edit = QLineEdit(self.settings.get("appearance", {}).get("textColor", "#ffffff"))
        text_color_set_layout.addWidget(self.text_color_edit)
        appearance_settings_layout.addLayout(text_color_set_layout)

        font_size_set_layout = QHBoxLayout()
        font_size_set_layout.addWidget(QLabel("Font boyutu:"))
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 24)
        self.font_size_spin.setValue(self.settings.get("appearance", {}).get("fontSize", 12))
        font_size_set_layout.addWidget(self.font_size_spin)
        font_size_set_layout.addStretch()
        appearance_settings_layout.addLayout(font_size_set_layout)

        font_family_set_layout = QHBoxLayout()
        font_family_set_layout.addWidget(QLabel("Font tipi:"))
        self.font_family_combo = QFontComboBox()
        font_family_val = self.settings.get("appearance", {}).get("fontFamily", "")
        if font_family_val:
            self.font_family_combo.setCurrentFont(QFont(font_family_val))
        font_family_set_layout.addWidget(self.font_family_combo)
        appearance_settings_layout.addLayout(font_family_set_layout)

        item_bg_color_layout = QHBoxLayout()
        item_bg_color_layout.addWidget(QLabel("Pano öğe arkaplanı:"))
        self.item_bg_color_edit = QLineEdit(self.settings.get("appearance", {}).get("itemBgColor", "rgba(24, 24, 37, 0.6)"))
        item_bg_color_layout.addWidget(self.item_bg_color_edit)
        appearance_settings_layout.addLayout(item_bg_color_layout)

        window_size_layout = QHBoxLayout()
        window_size_layout.addWidget(QLabel("Varsayılan genişlik / yükseklik:"))
        self.window_w_spin = QSpinBox()
        self.window_w_spin.setRange(220, 1000)
        self.window_w_spin.setValue(self.settings.get("appearance", {}).get("windowWidth", 350))
        self.window_h_spin = QSpinBox()
        self.window_h_spin.setRange(400, 1000)
        self.window_h_spin.setValue(self.settings.get("appearance", {}).get("windowHeight", 500))
        window_size_layout.addWidget(self.window_w_spin)
        window_size_layout.addWidget(self.window_h_spin)
        window_size_layout.addStretch()
        appearance_settings_layout.addLayout(window_size_layout)

        appearance_settings_layout.addStretch()

        rules_settings_tab = QWidget()
        rules_settings_layout = QVBoxLayout(rules_settings_tab)
        rules_settings_layout.addWidget(QLabel("Kurallar:"))

        self.rules_list_widget = QListWidget()
        self.rules_list_widget.setStyleSheet("QListWidget{background-color:#181825;border:1px solid rgba(255,255,255,0.1);border-radius:6px;color:#CDD6F4;padding:4px;}")
        for rule_item_settings in self.rules:
            self.rules_list_widget.addItem(f"{rule_item_settings.name} - {rule_item_settings.regex}")
        rules_settings_layout.addWidget(self.rules_list_widget)

        rule_set_buttons = QHBoxLayout()
        add_rule_set_btn = QPushButton("Ekle")
        add_rule_set_btn.clicked.connect(self.add_rule_dialog)
        rule_set_buttons.addWidget(add_rule_set_btn)

        edit_rule_set_btn = QPushButton("Düzenle")
        edit_rule_set_btn.clicked.connect(self.edit_rule_dialog)
        rule_set_buttons.addWidget(edit_rule_set_btn)

        delete_rule_set_btn = QPushButton("Sil")
        delete_rule_set_btn.clicked.connect(self.delete_rule)
        rule_set_buttons.addWidget(delete_rule_set_btn)
        rules_settings_layout.addLayout(rule_set_buttons)

        variables_settings_tab = QWidget()
        variables_settings_layout = QVBoxLayout(variables_settings_tab)
        variables_settings_layout.addWidget(QLabel("Snippet Değişkenleri (Her satıra bir tane: %user%=Mete):"))
        self.variables_text_edit = QTextEdit()
        vars_dict = self.settings.get("variables", {})
        vars_text = "\n".join([f"{k}={v}" for k, v in vars_dict.items()])
        self.variables_text_edit.setPlainText(vars_text)
        self.variables_text_edit.setStyleSheet("QTextEdit{background-color:#181825;color:#CDD6F4;border:1px solid rgba(255,255,255,0.1);border-radius:6px;font-family:Consolas,monospace;padding:6px;} QTextEdit:focus{border:1px solid #8B5CF6;background-color:#313244;}")
        variables_settings_layout.addWidget(self.variables_text_edit)

        filters_settings_tab = QWidget()
        filters_settings_layout = QVBoxLayout(filters_settings_tab)
        filters_settings_layout.addWidget(QLabel("Kara Liste Regex Kuralları (Filtrelenmesi istenenler, her satıra bir tane):"))
        self.blacklist_text_edit = QTextEdit()
        blacklist_rules = self.settings.get("filters", {}).get("blacklist", [])
        self.blacklist_text_edit.setPlainText("\n".join(blacklist_rules))
        self.blacklist_text_edit.setStyleSheet("QTextEdit{background-color:#181825;color:#CDD6F4;border:1px solid rgba(255,255,255,0.1);border-radius:6px;font-family:Consolas,monospace;padding:6px;} QTextEdit:focus{border:1px solid #8B5CF6;background-color:#313244;}")
        filters_settings_layout.addWidget(self.blacklist_text_edit)

        settings_tabs.addTab(general_settings_tab, "Genel")
        settings_tabs.addTab(appearance_settings_tab, "Görünüm")
        settings_tabs.addTab(rules_settings_tab, "Kurallar")
        settings_tabs.addTab(variables_settings_tab, "Değişkenler")
        settings_tabs.addTab(filters_settings_tab, "Filtreler")
        settings_layout.addWidget(settings_tabs)

        buttons_set_layout = QHBoxLayout()
        buttons_set_layout.addStretch()

        cancel_set_btn = QPushButton("İptal")
        cancel_set_btn.clicked.connect(settings_dialog.reject)
        buttons_set_layout.addWidget(cancel_set_btn)

        save_set_btn = QPushButton("Kaydet")
        save_set_btn.clicked.connect(lambda: self.save_settings_from_dialog(settings_dialog))
        save_set_btn.setStyleSheet("QPushButton{background-color:rgba(166,227,161,0.2);color:#A6E3A1;border:1px solid rgba(166,227,161,0.3);}QPushButton:hover{background-color:rgba(166,227,161,0.4);border:1px solid #A6E3A1;color:white;}")
        buttons_set_layout.addWidget(save_set_btn)
        settings_layout.addLayout(buttons_set_layout)

        settings_dialog.exec_()

    def save_settings_from_dialog(self, dialog_ref_settings):
        self.settings["behavior"]["maxItems"] = self.max_items_spin.value()
        self.settings["behavior"]["groupTimeWindow"] = self.group_time_spin.value() * 1000
        self.settings["behavior"]["alwaysOnTop"] = self.always_on_top_check.isChecked()
        self.settings["appearance"]["backgroundColor"] = self.bg_color_edit.text()
        self.settings["appearance"]["textColor"] = self.text_color_edit.text()
        self.settings["appearance"]["fontSize"] = self.font_size_spin.value()
        self.settings["appearance"]["fontFamily"] = self.font_family_combo.currentFont().family()
        self.settings["appearance"]["itemBgColor"] = self.item_bg_color_edit.text()
        self.settings["appearance"]["windowWidth"] = self.window_w_spin.value()
        self.settings["appearance"]["windowHeight"] = self.window_h_spin.value()

        # Save variables
        vars_text = self.variables_text_edit.toPlainText().strip()
        vars_dict = {}
        for line in vars_text.split('\n'):
            line = line.strip()
            if '=' in line:
                k, v = line.split('=', 1)
                vars_dict[k.strip()] = v.strip()
        self.settings["variables"] = vars_dict

        # Save blacklist filters
        blacklist_text = self.blacklist_text_edit.toPlainText().strip()
        blacklist_rules = []
        for line in blacklist_text.split('\n'):
            line = line.strip()
            if line:
                blacklist_rules.append(line)
        if "filters" not in self.settings:
            self.settings["filters"] = {}
        self.settings["filters"]["blacklist"] = blacklist_rules

        self.save_settings()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, self.settings["behavior"]["alwaysOnTop"])
        self._apply_main_styles()
        self.show()
        self.render_history()
        self.render_pinned()
        self.render_snippets()
        self.show_notification("✅ Ayarlar kaydedildi", "")
        dialog_ref_settings.accept()

    def add_rule_dialog(self):
        rule_add_dialog = QDialog(self)
        rule_add_dialog.setWindowTitle("Yeni Kural Ekle")
        rule_add_dialog.setModal(True)
        rule_add_dialog.setMinimumWidth(400)
        rule_add_layout = QVBoxLayout(rule_add_dialog)

        rule_add_layout.addWidget(QLabel("Kural Adı:"))
        name_rule_input = QLineEdit()
        rule_add_layout.addWidget(name_rule_input)

        rule_add_layout.addWidget(QLabel("Regex:"))
        regex_rule_input = QLineEdit()
        rule_add_layout.addWidget(regex_rule_input)

        rule_add_layout.addWidget(QLabel("Görüntü Şablonu:"))
        template_rule_input = QLineEdit()
        template_rule_input.setPlaceholderText("Örn: Kimlik No: \"{text}\"")
        rule_add_layout.addWidget(template_rule_input)

        rule_add_layout.addWidget(QLabel("Grup:"))
        group_rule_input = QLineEdit()
        rule_add_layout.addWidget(group_rule_input)

        rule_add_layout.addWidget(QLabel("Eylem:"))
        action_rule_combo = QComboBox()
        action_rule_combo.addItems(["paste", "openUrl", "custom"])
        rule_add_layout.addWidget(action_rule_combo)

        buttons_rule_layout = QHBoxLayout()
        cancel_rule_btn = QPushButton("İptal")
        cancel_rule_btn.clicked.connect(rule_add_dialog.reject)
        buttons_rule_layout.addWidget(cancel_rule_btn)

        save_rule_btn = QPushButton("Kaydet")
        save_rule_btn.clicked.connect(
            lambda: self.save_new_rule(rule_add_dialog, name_rule_input.text(), regex_rule_input.text(),
                                       template_rule_input.text(), group_rule_input.text(),
                                       action_rule_combo.currentText()))
        buttons_rule_layout.addWidget(save_rule_btn)
        rule_add_layout.addLayout(buttons_rule_layout)

        rule_add_dialog.exec_()

    def save_new_rule(self, dialog_rule_ref, name_rule_val, regex_rule_val, template_rule_val, group_rule_val,
                      action_rule_val):
        if not all([name_rule_val, regex_rule_val, template_rule_val, group_rule_val]):
            QMessageBox.warning(self, "Hata", "Tüm alanları doldurun!")
            return

        new_rule_obj = ClipboardRule(id=f"rule_{int(time.time())}", name=name_rule_val, regex=regex_rule_val,
                                     display_template=template_rule_val, group=group_rule_val, action=action_rule_val)
        self.rules.append(new_rule_obj)
        self.save_rules()
        self.rules_list_widget.addItem(f"{name_rule_val} - {regex_rule_val}")
        self.show_notification("✅ Kural eklendi", "")
        dialog_rule_ref.accept()

    def edit_rule_dialog(self):
        current_rule_idx = self.rules_list_widget.currentRow()
        if current_rule_idx < 0:
            return
            
        rule_to_edit = self.rules[current_rule_idx]

        rule_edit_dialog = QDialog(self)
        rule_edit_dialog.setWindowTitle("Kuralı Düzenle")
        rule_edit_dialog.setModal(True)
        rule_edit_dialog.setMinimumWidth(400)
        rule_edit_layout = QVBoxLayout(rule_edit_dialog)

        rule_edit_layout.addWidget(QLabel("Kural Adı:"))
        name_rule_input = QLineEdit(rule_to_edit.name)
        rule_edit_layout.addWidget(name_rule_input)

        rule_edit_layout.addWidget(QLabel("Regex:"))
        regex_rule_input = QLineEdit(rule_to_edit.regex)
        rule_edit_layout.addWidget(regex_rule_input)

        rule_edit_layout.addWidget(QLabel("Görüntü Şablonu:"))
        template_rule_input = QLineEdit(rule_to_edit.display_template)
        template_rule_input.setPlaceholderText("Örn: Kimlik No: \"{text}\"")
        rule_edit_layout.addWidget(template_rule_input)

        rule_edit_layout.addWidget(QLabel("Grup:"))
        group_rule_input = QLineEdit(rule_to_edit.group)
        rule_edit_layout.addWidget(group_rule_input)

        rule_edit_layout.addWidget(QLabel("Eylem:"))
        action_rule_combo = QComboBox()
        action_rule_combo.addItems(["paste", "openUrl", "custom"])
        action_rule_combo.setCurrentText(rule_to_edit.action)
        rule_edit_layout.addWidget(action_rule_combo)

        buttons_rule_layout = QHBoxLayout()
        cancel_rule_btn = QPushButton("İptal")
        cancel_rule_btn.clicked.connect(rule_edit_dialog.reject)
        buttons_rule_layout.addWidget(cancel_rule_btn)

        save_rule_btn = QPushButton("Kaydet")
        save_rule_btn.clicked.connect(
            lambda: self.save_edited_rule(rule_edit_dialog, current_rule_idx, name_rule_input.text(), regex_rule_input.text(),
                                       template_rule_input.text(), group_rule_input.text(),
                                       action_rule_combo.currentText()))
        buttons_rule_layout.addWidget(save_rule_btn)
        rule_edit_layout.addLayout(buttons_rule_layout)

        rule_edit_dialog.exec_()
        
    def save_edited_rule(self, dialog_rule_ref, rule_idx, name_rule_val, regex_rule_val, template_rule_val, group_rule_val, action_rule_val):
        if not all([name_rule_val, regex_rule_val, template_rule_val, group_rule_val]):
            QMessageBox.warning(self, "Hata", "Tüm alanları doldurun!")
            return

        rule_to_edit = self.rules[rule_idx]
        rule_to_edit.name = name_rule_val
        rule_to_edit.regex = regex_rule_val
        rule_to_edit.display_template = template_rule_val
        rule_to_edit.group = group_rule_val
        rule_to_edit.action = action_rule_val
        
        self.save_rules()
        self.rules_list_widget.item(rule_idx).setText(f"{name_rule_val} - {regex_rule_val}")
        self.show_notification("✅ Kural güncellendi", "")
        dialog_rule_ref.accept()

    def delete_rule(self):
        current_del_rule_idx = self.rules_list_widget.currentRow()
        if current_del_rule_idx < 0:
            return
        if QMessageBox.question(self, "Onay", "Bu kuralı silmek istediğinizden emin misiniz?",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.rules.pop(current_del_rule_idx)
            self.rules_list_widget.takeItem(current_del_rule_idx)
            self.save_rules()
            self.show_notification("🗑️ Kural silindi", "")

    def closeEvent(self, event):
        # Pencere pozisyonunu kaydet (normal moddaysa)
        if not self.is_minimized:
            self.normal_window_position = self.pos()
            if "window" not in self.settings:
                self.settings["window"] = {}
            self.settings["window"]["position"] = {"x": self.pos().x(), "y": self.pos().y()}
            self.save_settings()

        event.ignore()
        self.hide()
        self.show_notification("Clipboard Manager", "Arka planda çalışmaya devam ediyor")


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")

    print("Clipboard Manager başlatılıyor...")
    main_window = ClipboardManagerWindow()
    main_window.show()
    main_window.raise_()
    main_window.activateWindow()

    print("Ana pencere gösteriliyor...")
    print(f"Pencere görünür mü: {main_window.isVisible()}")
    print(f"Pencere pozisyonu: {main_window.pos()}")
    print(f"Pencere boyutu: {main_window.size()}")

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()