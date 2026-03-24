"""
Çoklu Ekran Pencere Yöneticisi
Ekranlar arasında pencereleri kolayca taşıyın
"""

import tkinter as tk
from tkinter import ttk
import win32gui
import win32con
import win32ui
import win32process
import ctypes
import psutil
import threading
from collections import defaultdict
from screeninfo import get_monitors
from PIL import Image, ImageTk, ImageGrab


class WindowManager:
    def __init__(self, root):
        self.root = root
        self.root.title("Pencere Yöneticisi")
        self.root.geometry("1200x760")

        # Seçili pencereyi takip et
        self.selected_window = None
        self.selected_monitor = None
        self.selected_hwnd = None

        # Monitörleri al
        self.monitors = self.get_monitors()

        # Otomatik yenileme ayarları (pencere listesi)
        self.auto_refresh_enabled = tk.BooleanVar(value=True)
        self.auto_refresh_interval = 3000  # ms
        self._auto_refresh_job = None
        self._is_refreshing = False

        # Seçili pencere önizlemesi
        self._preview_job = None
        self.preview_photo = None

        # Her zaman üstte butonu referansı (toggle rengi için)
        self._topmost_btn = None

        # Ham önizleme görüntüsü — resize'da yeniden kullanılır
        self._preview_img_raw = None

        # Monitör ekran önizlemeleri (liste)
        self.monitor_preview_labels = []   # tk.Label listesi
        self.monitor_preview_photos = []   # ImageTk referansları
        self.monitor_raw_images = []       # Ham PIL görüntüleri (resize için)
        self._monitor_preview_job = None
        self.monitor_preview_interval = 4000  # ms

        # UI oluştur
        self.create_ui()

        # İlk yükleme
        self.refresh_windows()

        # Otomatik yenilemeyi başlat
        self.schedule_auto_refresh()

        # Monitör önizlemelerini başlat (kısa gecikme ile, pencere render olduktan sonra)
        self.root.after(800, self.update_monitor_previews)

    # ─────────────────────────── Monitör yardımcıları ───────────────────────────

    def get_monitors(self):
        """Tüm monitörleri listele"""
        monitors = []
        for m in get_monitors():
            monitors.append({
                'left': m.x,
                'top': m.y,
                'right': m.x + m.width,
                'bottom': m.y + m.height,
                'width': m.width,
                'height': m.height
            })
        monitors.sort(key=lambda m: m['left'])
        return monitors

    def get_window_monitor_index(self, hwnd):
        """Pencerenin hangi monitörde olduğunu bul"""
        try:
            rect = win32gui.GetWindowRect(hwnd)
            cx = (rect[0] + rect[2]) // 2
            cy = (rect[1] + rect[3]) // 2
            for idx, m in enumerate(self.monitors):
                if m['left'] <= cx <= m['right'] and m['top'] <= cy <= m['bottom']:
                    return idx
            return 0
        except Exception:
            return 0

    # ─────────────────────────── Pencere listeleme ───────────────────────────────

    def enum_windows_callback(self, hwnd, windows_by_monitor):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title and len(title.strip()) > 0:
                class_name = win32gui.GetClassName(hwnd)
                if class_name not in ['Progman', 'WorkerW', 'Shell_TrayWnd']:
                    monitor_idx = self.get_window_monitor_index(hwnd)
                    windows_by_monitor[monitor_idx].append({'hwnd': hwnd, 'title': title})
        return True

    def get_windows_by_monitor(self):
        windows_by_monitor = defaultdict(list)
        win32gui.EnumWindows(
            lambda hwnd, param: self.enum_windows_callback(hwnd, param),
            windows_by_monitor
        )
        return dict(windows_by_monitor)

    # ─────────────────────────── Pencere Detay Bilgileri ─────────────────────────

    def get_window_details(self, hwnd):
        """Pencere hakkında detaylı bilgi topla"""
        details = {}
        try:
            rect = win32gui.GetWindowRect(hwnd)
            details['x'] = rect[0]
            details['y'] = rect[1]
            details['width'] = rect[2] - rect[0]
            details['height'] = rect[3] - rect[1]
            details['title'] = win32gui.GetWindowText(hwnd)
            details['class'] = win32gui.GetClassName(hwnd)
            details['hwnd'] = hwnd

            # PID
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            details['pid'] = pid

            # Proses adı
            try:
                proc = psutil.Process(pid)
                details['process'] = proc.name()
                details['exe'] = proc.exe()
                try:
                    details['cpu'] = f"{proc.cpu_percent(interval=None):.1f}%"
                    mem_mb = proc.memory_info().rss / (1024 * 1024)
                    details['memory'] = f"{mem_mb:.1f} MB"
                except Exception:
                    details['cpu'] = "—"
                    details['memory'] = "—"
            except Exception:
                details['process'] = "—"
                details['exe'] = "—"
                details['cpu'] = "—"
                details['memory'] = "—"

            # Pencere durumu
            if win32gui.IsIconic(hwnd):
                details['state'] = "Simge Durumuna Küçültülmüş"
            elif win32gui.IsZoomed(hwnd):
                details['state'] = "Ekranı Kaplamış"
            else:
                details['state'] = "Normal"

            # Hangi monitör
            mon_idx = self.get_window_monitor_index(hwnd)
            details['monitor'] = f"Ekran {mon_idx + 1}"

        except Exception as e:
            details['error'] = str(e)
        return details

    # ─────────────────────────── UI kurulumu ─────────────────────────────────────

    def create_ui(self):
        # ── Üst çubuk ──
        top_frame = tk.Frame(self.root, bg="#1a1a2e", pady=6)
        top_frame.pack(fill=tk.X)

        tk.Label(
            top_frame,
            text=f"  🖥  {len(self.monitors)} Ekran Bağlı",
            font=("Segoe UI", 10, "bold"),
            bg="#1a1a2e", fg="#e0e0e0"
        ).pack(side=tk.LEFT, padx=8)

        auto_cb = tk.Checkbutton(
            top_frame,
            text="Otomatik Yenile (3sn)",
            variable=self.auto_refresh_enabled,
            command=self.on_auto_refresh_toggle,
            font=("Segoe UI", 9),
            bg="#1a1a2e", fg="#aaaaaa",
            selectcolor="#1a1a2e",
            activebackground="#1a1a2e",
            activeforeground="#ffffff"
        )
        auto_cb.pack(side=tk.RIGHT, padx=(0, 12))

        tk.Button(
            top_frame,
            text="⟳  Yenile",
            command=self.refresh_windows,
            font=("Segoe UI", 9),
            bg="#2a2a4a", fg="#cccccc",
            relief=tk.FLAT, padx=10, pady=2,
            cursor="hand2"
        ).pack(side=tk.RIGHT, padx=(0, 6))

        self.auto_indicator = tk.Label(
            top_frame, text="● OTO",
            font=("Segoe UI", 8, "bold"), fg="#44cc77",
            bg="#1a1a2e"
        )
        self.auto_indicator.pack(side=tk.RIGHT, padx=(0, 4))

        # ── İçerik: listeler + pencere önizlemesi ──
        content_frame = tk.Frame(self.root, bg="#111122")
        content_frame.pack(fill=tk.BOTH, expand=True)

        # Sol: monitör sütunları
        list_frame = tk.Frame(content_frame, bg="#111122")
        list_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Sağ: seçili pencere önizleme paneli — sabit genişlik, dikey bölünmüş
        preview_outer = tk.Frame(content_frame, bg="#16162a", width=290)
        preview_outer.pack(side=tk.RIGHT, fill=tk.Y)
        preview_outer.pack_propagate(False)

        # Başlık bandı
        tk.Label(
            preview_outer,
            text="PENCERE ÖN İZLEME",
            font=("Segoe UI", 7, "bold"),
            bg="#0f0f1e", fg="#556688",
            pady=4
        ).pack(fill=tk.X)

        # Üst yarı: görüntü önizlemesi
        self.preview_image_frame = tk.Frame(
            preview_outer, bg="#0d0d1a"
        )
        self.preview_image_frame.pack(fill=tk.BOTH, expand=True)

        # place kullanıyoruz — tkinter görüntüyü ASLA uzatmaz
        self.preview_label = tk.Label(
            self.preview_image_frame,
            text="Bir pencere\nseçin",
            bg="#0d0d1a", fg="#334455",
            font=("Segoe UI", 9),
            justify=tk.CENTER
        )
        self.preview_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        # Tıklayınca canlı önizleme popup aç
        self.preview_label.bind("<Button-1>", lambda e: self.show_window_preview_popup())
        self.preview_image_frame.bind("<Button-1>", lambda e: self.show_window_preview_popup())

        # Frame boyutu değişince görüntüyü yeniden ölçekle
        self.preview_image_frame.bind("<Configure>", self._on_preview_frame_resize)

        # Ayraç
        tk.Frame(preview_outer, height=1, bg="#2a2a4a").pack(fill=tk.X)

        # Alt yarı: pencere bilgileri + eylem butonları
        # Butonlar ÖNCE BOTTOM'a pack edilir, info_text kalan alanı alır
        info_frame = tk.Frame(preview_outer, bg="#12121f")
        info_frame.pack(fill=tk.BOTH, side=tk.BOTTOM, expand=False)

        # ── Eylem Butonları — BOTTOM'dan yukarı doğru pack ──
        tk.Frame(info_frame, height=1, bg="#2a2a4a").pack(fill=tk.X, side=tk.BOTTOM)

        btn_grid = tk.Frame(info_frame, bg="#12121f")
        btn_grid.pack(fill=tk.X, side=tk.BOTTOM, padx=6, pady=(0, 6))

        btn_defs = [
            ("📌  Her Zaman Üstte",  "#ffdd88", "#2a2210", self.action_toggle_topmost),
            ("⬜  Ekranı Kapla",     "#aaddff", "#1a2a3a", self.action_maximize),
            ("⬛  Küçült",           "#aaccaa", "#1a2a1a", self.action_minimize),
            ("↩  Normal Boyut",     "#ccbbaa", "#2a2218", self.action_restore),
            ("✕  Pencereyi Kapat",  "#ffaaaa", "#2a1a1a", self.action_close_window),
            ("☠  Prosesi Sonlandır","#ff6666", "#331111", self.action_kill_process),
        ]

        for i, (text, fg, bg, cmd) in enumerate(reversed(btn_defs)):
            btn = tk.Button(
                btn_grid,
                text=text,
                font=("Segoe UI", 8, "bold"),
                fg=fg, bg=bg,
                activeforeground="#ffffff",
                activebackground="#333355",
                relief=tk.FLAT,
                cursor="hand2",
                anchor=tk.W,
                padx=8, pady=5,
                command=cmd
            )
            btn.pack(fill=tk.X, pady=1)
            # "Her Zaman Üstte" butonu en son reversed'de ilk sırada — referansı sakla
            real_idx = len(btn_defs) - 1 - i
            if real_idx == 0:
                self._topmost_btn = btn

        tk.Label(
            info_frame,
            text="PENCERE EYLEMLERİ",
            font=("Segoe UI", 7, "bold"),
            bg="#0f0f1e", fg="#556688",
            pady=4
        ).pack(fill=tk.X, side=tk.BOTTOM)

        tk.Frame(info_frame, height=1, bg="#2a2a4a").pack(fill=tk.X, side=tk.BOTTOM)

        # ── Bilgi metni — kalan alanı doldurur (TOP) ──
        tk.Label(
            info_frame,
            text="PENCERE BİLGİLERİ",
            font=("Segoe UI", 7, "bold"),
            bg="#0f0f1e", fg="#556688",
            pady=4
        ).pack(fill=tk.X, side=tk.TOP)

        self.info_text = tk.Text(
            info_frame,
            font=("Consolas", 8),
            bg="#12121f", fg="#99aabb",
            relief=tk.FLAT,
            state=tk.DISABLED,
            wrap=tk.WORD,
            padx=8, pady=6,
            height=10,
            insertbackground="#99aabb",
            selectbackground="#2a2a4a"
        )
        self.info_text.pack(fill=tk.BOTH, expand=True, side=tk.TOP)

        # ── Monitör sütunları ──
        self.monitor_frames = []
        self.listboxes = []
        self.windows_data = {}

        # Önizleme listelerini monitör sayısına göre başlat
        self.monitor_preview_labels = [None] * len(self.monitors)
        self.monitor_preview_photos = [None] * len(self.monitors)
        self.monitor_raw_images = [None] * len(self.monitors)

        for idx, monitor in enumerate(self.monitors):
            # Dış çerçeve
            frame = tk.Frame(list_frame, bg="#111122", bd=0)
            frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)

            # Başlık
            hdr = tk.Frame(frame, bg="#1a1a35")
            hdr.pack(fill=tk.X)
            tk.Label(
                hdr,
                text=f"  EKRAN {idx + 1}   {monitor['width']}×{monitor['height']}",
                font=("Segoe UI", 8, "bold"),
                bg="#1a1a35", fg="#8888cc",
                pady=5
            ).pack(side=tk.LEFT)

            # Listbox alanı
            list_area = tk.Frame(frame, bg="#111122")
            list_area.pack(fill=tk.BOTH, expand=True)

            scrollbar = tk.Scrollbar(list_area, bg="#1a1a35", troughcolor="#0d0d1a",
                                     activebackground="#3a3a6a", relief=tk.FLAT)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

            listbox = tk.Listbox(
                list_area,
                yscrollcommand=scrollbar.set,
                font=("Segoe UI", 9),
                activestyle='none',
                bg="#0f0f1e", fg="#aabbcc",
                selectbackground="#2a3a5a",
                selectforeground="#ddeeff",
                relief=tk.FLAT, bd=0,
                highlightthickness=0
            )
            listbox.pack(fill=tk.BOTH, expand=True)
            scrollbar.config(command=listbox.yview)

            listbox.bind('<<ListboxSelect>>',
                         lambda e, m=idx: self.on_select(m))

            self.listboxes.append(listbox)
            self.monitor_frames.append(frame)

            # ── Monitör Ekran Önizlemesi — tamamen çerçevesiz ──
            # Önce BOTTOM'a, sınır çizgisi sonra
            sep = tk.Frame(frame, height=1, bg="#2a2a4a")
            sep.pack(side=tk.BOTTOM, fill=tk.X)

            # Tıklanabilir başlık etiketi (önizleme üstünde küçük bant)
            mon_hdr = tk.Label(
                frame,
                text=f"📷  EKRAN {idx + 1} — tıkla: büyüt",
                font=("Segoe UI", 7),
                bg="#0a0a18", fg="#445566",
                pady=2, cursor="hand2"
            )
            mon_hdr.pack(side=tk.BOTTOM, fill=tk.X)

            # Önizleme etiketi — çerçeve yok, sabit yükseklik, kenardan kenara
            preview_container = tk.Frame(frame, bg="#0a0a18", height=150)
            preview_container.pack(side=tk.BOTTOM, fill=tk.X)
            preview_container.pack_propagate(False)

            mon_preview = tk.Label(
                preview_container,
                text="Yükleniyor...",
                bg="#0a0a18",
                fg="#334455",
                font=("Segoe UI", 8),
                cursor="hand2",
                bd=0
            )
            # place ile merkeze sabitle — tkinter görüntüyü uzatmaz
            mon_preview.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
            mon_preview.bind("<Button-1>", lambda e, i=idx: self.show_monitor_popup(i))
            mon_hdr.bind("<Button-1>", lambda e, i=idx: self.show_monitor_popup(i))

            # Container boyutu değişince önizlemeyi yeniden ölçekle
            preview_container.bind(
                "<Configure>",
                lambda e, i=idx: self._on_monitor_preview_resize(i)
            )

            self.monitor_preview_labels[idx] = mon_preview

            # Oklar (monitörler arası)
            if idx < len(self.monitors) - 1:
                arrow_frame = tk.Frame(list_frame, width=44, bg="#111122")
                arrow_frame.pack(side=tk.LEFT, fill=tk.Y)
                arrow_frame.pack_propagate(False)

                tk.Button(
                    arrow_frame, text="›", font=("Segoe UI", 18, "bold"),
                    command=lambda m=idx: self.move_window_right(m),
                    bg="#1a1a35", fg="#6677cc",
                    relief=tk.FLAT, cursor="hand2",
                    activebackground="#2a2a55", activeforeground="#aabbff"
                ).pack(pady=8, fill=tk.X, padx=4)

                tk.Button(
                    arrow_frame, text="‹", font=("Segoe UI", 18, "bold"),
                    command=lambda m=idx + 1: self.move_window_left(m),
                    bg="#1a1a35", fg="#6677cc",
                    relief=tk.FLAT, cursor="hand2",
                    activebackground="#2a2a55", activeforeground="#aabbff"
                ).pack(pady=4, fill=tk.X, padx=4)

        # ── Alt durum çubuğu ──
        self.status_label = tk.Label(
            self.root, text="  Hazır",
            relief=tk.FLAT, anchor=tk.W,
            font=("Segoe UI", 8), fg="#667788",
            bg="#0d0d1a", pady=4
        )
        self.status_label.pack(fill=tk.X, side=tk.BOTTOM)

    # ──────────────────── Monitör Ekran Görüntüsü Yakalama ───────────────────────

    def capture_monitor(self, monitor, thumb_w=None, thumb_h=None):
        """
        Verilen monitörün ekranını yakalar.
        thumb_w/thumb_h verilirse o boyuta resize eder (popup için).
        Verilmezse işlem yapmadan ham görüntüyü döndürür
        (boyutlandırma _render_monitor_preview'a bırakılır).
        """
        m = monitor
        img = ImageGrab.grab(
            bbox=(m['left'], m['top'], m['right'], m['bottom']),
            all_screens=True
        )
        if thumb_w is not None and thumb_h is not None:
            img = img.resize((thumb_w, thumb_h), Image.LANCZOS)
        return img

    def update_monitor_previews(self):
        """Tüm monitörlerin küçük ekran görüntüsünü yakala, ham olarak sakla, ölçekle."""
        for idx, monitor in enumerate(self.monitors):
            lbl = self.monitor_preview_labels[idx]
            if lbl is None:
                continue
            try:
                # Ham (orijinal) ekran görüntüsünü al — boyutlandırma yok
                img = self.capture_monitor(monitor)
                self.monitor_raw_images[idx] = img          # ham görüntüyü sakla
                self._render_monitor_preview(idx)           # orana göre ölçekle
            except Exception as exc:
                lbl.config(image='', text=f"Görüntü alınamadı\n({type(exc).__name__})",
                           bg="#0a0a18", fg="#445566")
                self.monitor_raw_images[idx] = None
                self.monitor_preview_photos[idx] = None

        # Bir sonraki güncellemeyi zamanla
        self._monitor_preview_job = self.root.after(
            self.monitor_preview_interval, self.update_monitor_previews
        )

    def _render_monitor_preview(self, idx):
        """Ham monitör görüntüsünü container boyutuna göre oranı koruyarak render et."""
        img = self.monitor_raw_images[idx]
        lbl = self.monitor_preview_labels[idx]
        if img is None or lbl is None:
            return
        container = lbl.master
        container.update_idletasks()
        cw = container.winfo_width()
        ch = container.winfo_height()
        if cw < 2 or ch < 2:
            return

        img_w, img_h = img.size
        # Orijinal en-boy oranını koru — container'a sığacak maksimum boyut
        scale = min(cw / img_w, ch / img_h)
        new_w = max(1, int(img_w * scale))
        new_h = max(1, int(img_h * scale))
        img_scaled = img.resize((new_w, new_h), Image.LANCZOS)

        photo = ImageTk.PhotoImage(img_scaled)
        self.monitor_preview_photos[idx] = photo
        lbl.config(image=photo, text="", bg="#0a0a18")
        lbl.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

    def _on_monitor_preview_resize(self, idx):
        """Container boyutu değişince ham görüntüyü yeniden ölçekle."""
        if self.monitor_raw_images[idx] is not None:
            self._render_monitor_preview(idx)

    # ── PiP yardımcısı: sürükle ──────────────────────────────────────────────────

    def _make_draggable(self, window, drag_widget):
        """drag_widget'a tıklayıp sürükleyince pencereyi taşı."""
        state = {}

        def _press(e):
            state['x'] = e.x_root - window.winfo_x()
            state['y'] = e.y_root - window.winfo_y()

        def _drag(e):
            window.geometry(f"+{e.x_root - state['x']}+{e.y_root - state['y']}")

        drag_widget.bind("<ButtonPress-1>", _press)
        drag_widget.bind("<B1-Motion>", _drag)

    # ── Ortak canlı önizleme motoru ───────────────────────────────────────────────

    def _make_live_popup(self, title, capture_fn, display_w, display_h, pip=False):
        """
        Verilen capture_fn()'ı ~30fps ile çağıran canlı önizleme popup'ı.
        pip=True  → çerçevesiz, her zaman üstte, 480px max, sürüklenebilir
        pip=False → normal başlıklı pencere, yeniden boyutlandırılabilir
        """
        import time

        PIP_MAX = 480   # PiP modunda max genişlik/yükseklik

        popup = tk.Toplevel(self.root)
        popup.configure(bg="#0a0a18")
        popup.resizable(not pip, not pip)

        if pip:
            popup.overrideredirect(True)
            popup.wm_attributes("-topmost", True)
            sw = popup.winfo_screenwidth()
            sh = popup.winfo_screenheight()
            ratio = display_h / display_w if display_w > 0 else 0.5625
            pip_w = min(PIP_MAX, display_w)
            pip_h = int(pip_w * ratio)
            popup.geometry(f"{pip_w}x{pip_h + 22}+{sw - pip_w - 16}+{sh - pip_h - 22 - 48}")
        else:
            popup.title(title)
            # Ekranı aşmayacak şekilde başlangıç boyutu — ortala
            sw = popup.winfo_screenwidth()
            sh = popup.winfo_screenheight()
            win_w = min(display_w, sw - 80)
            win_h = min(display_h + 30, sh - 80)
            x = (sw - win_w) // 2
            y = (sh - win_h) // 2
            popup.geometry(f"{win_w}x{win_h}+{x}+{y}")

        # ── PiP durum değişkenleri ──
        # rolled_up: sadece başlık görünür, canvas gizli
        # size_idx: 0=tam(480), 1=yarı(240), 2=üçte-bir(160)
        pip_state = {
            'rolled_up': False,
            'size_idx': 0,
            'base_w': min(PIP_MAX, display_w) if pip else display_w,
            'ratio': display_h / display_w if display_w > 0 else 0.5625,
        }
        PIP_SIZES = [1.0, 0.5, 1/3]          # tam, yarı, üçte-bir
        SIZE_ICONS = ["⬛", "▪", "·"]          # büyüklük simgeleri
        SIZE_LABELS = ["Tam", "½", "⅓"]

        # ── Başlık bandı ──
        hdr_h = 22 if pip else 30
        hdr = tk.Frame(popup, bg="#0f0f1e", height=hdr_h)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)

        short_title = (title[:28] + "…") if len(title) > 28 else title
        title_lbl = tk.Label(hdr,
                             text=("📌 " if pip else "") + short_title,
                             font=("Segoe UI", 7, "bold") if pip else ("Segoe UI", 8, "bold"),
                             bg="#0f0f1e", fg="#44aacc" if pip else "#556688",
                             padx=6, cursor="hand2" if pip else "")
        title_lbl.pack(side=tk.LEFT, fill=tk.Y)

        fps_lbl = tk.Label(hdr, text="— fps", font=("Consolas", 7 if pip else 8),
                           bg="#0f0f1e", fg="#44cc77", padx=4)
        fps_lbl.pack(side=tk.RIGHT, fill=tk.Y)

        tk.Button(hdr, text="✕",
                  font=("Segoe UI", 8, "bold"),
                  bg="#0f0f1e", fg="#cc4444",
                  relief=tk.FLAT, cursor="hand2",
                  padx=6, pady=0,
                  command=lambda: _on_close()).pack(side=tk.RIGHT, fill=tk.Y)

        if pip:
            # ── Boyut döngüsü butonu ──
            size_btn = tk.Button(hdr,
                                 text=SIZE_ICONS[0],
                                 font=("Segoe UI", 8, "bold"),
                                 bg="#0f0f1e", fg="#aaaaff",
                                 relief=tk.FLAT, cursor="hand2",
                                 padx=5, pady=0,
                                 command=lambda: _cycle_size())
            size_btn.pack(side=tk.RIGHT, fill=tk.Y)

            # ── Başlık çift tık: rulo modu ──
            self._make_draggable(popup, hdr)
            self._make_draggable(popup, title_lbl)
            hdr.bind("<Double-Button-1>", lambda e: _toggle_roll())
            title_lbl.bind("<Double-Button-1>", lambda e: _toggle_roll())

        else:
            # Normal modda PiP düğmesi
            tk.Button(hdr, text="📌 PiP",
                      font=("Segoe UI", 7, "bold"),
                      bg="#1a2a1a", fg="#88cc88",
                      relief=tk.FLAT, cursor="hand2",
                      padx=6, pady=0,
                      command=lambda: _spawn_pip()).pack(side=tk.RIGHT, fill=tk.Y)

        # ── Görüntü alanı ──
        canvas_frame = tk.Frame(popup, bg="#0a0a18")
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        img_lbl = tk.Label(canvas_frame, bg="#0a0a18",
                           text="Yükleniyor...", fg="#334455",
                           font=("Segoe UI", 9))
        img_lbl.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        # ── PiP pencere boyutunu güncelle ──────────────────────────────────────
        def _apply_pip_size():
            """Mevcut size_idx ve rolled_up'a göre pencere geometrisini ayarla."""
            if not pip:
                return
            scale = PIP_SIZES[pip_state['size_idx']]
            base_w = pip_state['base_w']
            ratio  = pip_state['ratio']
            w = max(120, int(base_w * scale))
            h = max(1,   int(w * ratio))
            total_h = hdr_h if pip_state['rolled_up'] else h + hdr_h

            # Mevcut konumu koru
            x = popup.winfo_x()
            y = popup.winfo_y()
            popup.geometry(f"{w}x{total_h}+{x}+{y}")

            if pip_state['rolled_up']:
                canvas_frame.pack_forget()
            else:
                canvas_frame.pack(fill=tk.BOTH, expand=True)

        def _toggle_roll():
            """Çift tık: canvas'ı gizle/göster (rulo modu)."""
            pip_state['rolled_up'] = not pip_state['rolled_up']
            _apply_pip_size()

        def _cycle_size():
            """Boyut butonuna basınca 3 adım arasında döngü: tam → yarı → üçte-bir → tam."""
            pip_state['size_idx'] = (pip_state['size_idx'] + 1) % 3
            idx = pip_state['size_idx']
            size_btn.config(text=SIZE_ICONS[idx],
                            fg=["#aaaaff", "#8888cc", "#665599"][idx])
            _apply_pip_size()

        # ── Durum ──
        alive = [True]
        photo_ref = [None]
        target_fps = 30
        capture_max = PIP_MAX if pip else None

        def _capture_loop():
            frame_times = []
            while alive[0]:
                t0 = time.perf_counter()
                try:
                    # Rulo modunda capture yapma — CPU tasarrufu
                    if pip_state.get('rolled_up', False):
                        time.sleep(1 / 10)
                        continue

                    img = capture_fn()

                    if capture_max is not None:
                        iw, ih = img.size
                        if iw > capture_max or ih > capture_max:
                            pre_scale = min(capture_max / iw, capture_max / ih)
                            img = img.resize(
                                (max(1, int(iw * pre_scale)),
                                 max(1, int(ih * pre_scale))),
                                Image.NEAREST
                            )

                    cw = canvas_frame.winfo_width()
                    ch = canvas_frame.winfo_height()
                    if cw < 2: cw = display_w
                    if ch < 2: ch = display_h
                    iw, ih = img.size
                    scale = min(cw / iw, ch / ih)
                    nw = max(1, int(iw * scale))
                    nh = max(1, int(ih * scale))
                    img_scaled = img.resize((nw, nh), Image.BILINEAR)

                    def _update(im=img_scaled):
                        if not alive[0]:
                            return
                        ph = ImageTk.PhotoImage(im)
                        photo_ref[0] = ph
                        img_lbl.config(image=ph, text="", bg="#0a0a18")
                        img_lbl.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
                    popup.after(0, _update)

                except Exception:
                    pass

                elapsed = time.perf_counter() - t0
                time.sleep(max(0.0, (1 / target_fps) - elapsed))

                frame_times.append(time.perf_counter())
                if len(frame_times) > 15:
                    frame_times.pop(0)
                if len(frame_times) >= 2:
                    avg = (frame_times[-1] - frame_times[0]) / (len(frame_times) - 1)
                    fps_val = 1 / avg if avg > 0 else 0
                    def _fps(f=fps_val):
                        if alive[0]:
                            fps_lbl.config(text=f"{f:.0f} fps")
                    popup.after(0, _fps)

        def _on_close():
            alive[0] = False
            popup.destroy()

        def _spawn_pip():
            self._make_live_popup(title, capture_fn, display_w, display_h, pip=True)

        popup.protocol("WM_DELETE_WINDOW", _on_close)
        t = threading.Thread(target=_capture_loop, daemon=True)
        t.start()
        return popup

    def show_monitor_popup(self, monitor_idx):
        """Monitör önizlemesine tıklandığında 30fps canlı popup göster."""
        monitor = self.monitors[monitor_idx]
        title = f"📷  Ekran {monitor_idx + 1}  —  {monitor['width']}×{monitor['height']}"

        def _capture():
            return self.capture_monitor(monitor)

        self._make_live_popup(title, _capture, 960, 540)

    def show_window_preview_popup(self):
        """Seçili pencere önizlemesine tıklandığında 30fps canlı popup göster."""
        hwnd = self.selected_hwnd
        if not hwnd:
            return
        try:
            title_text = win32gui.GetWindowText(hwnd)
        except Exception:
            title_text = "Pencere"
        title = f"🪟  {title_text[:50]}"

        def _capture():
            rect = win32gui.GetWindowRect(hwnd)
            ww = rect[2] - rect[0]
            wh = rect[3] - rect[1]
            if ww <= 0 or wh <= 0:
                raise ValueError("Geçersiz boyut")
            hwnd_dc = win32gui.GetWindowDC(hwnd)
            mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
            save_dc = mfc_dc.CreateCompatibleDC()
            save_bitmap = win32ui.CreateBitmap()
            save_bitmap.CreateCompatibleBitmap(mfc_dc, ww, wh)
            save_dc.SelectObject(save_bitmap)
            ctypes.windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 2)
            bmp_info = save_bitmap.GetInfo()
            bmp_str = save_bitmap.GetBitmapBits(True)
            img = Image.frombuffer(
                'RGB', (bmp_info['bmWidth'], bmp_info['bmHeight']),
                bmp_str, 'raw', 'BGRX', 0, 1
            )
            win32gui.DeleteObject(save_bitmap.GetHandle())
            save_dc.DeleteDC()
            mfc_dc.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwnd_dc)
            return img

        self._make_live_popup(title, _capture, 960, 600)

    # ────────────────────── Seçili Pencere Önizlemesi ────────────────────────────

    def on_select(self, monitor_idx):
        listbox = self.listboxes[monitor_idx]
        selection = listbox.curselection()
        if selection:
            self.selected_window = selection[0]
            self.selected_monitor = monitor_idx
            win_list = self.windows_data.get(monitor_idx, [])
            self.selected_hwnd = (
                win_list[self.selected_window]['hwnd']
                if self.selected_window < len(win_list) else None
            )
            window_title = listbox.get(selection[0])
            self.status_label.config(
                text=f"  ✔  Seçili: {window_title}  |  Ekran {monitor_idx + 1}",
                fg="#44cc77"
            )
            self.schedule_preview()

    def _render_preview_image(self):
        """Ham görüntüyü mevcut frame boyutuna göre ölçekle ve place ile ortala."""
        if self._preview_img_raw is None:
            return
        self.preview_image_frame.update_idletasks()
        pw = self.preview_image_frame.winfo_width()
        ph = self.preview_image_frame.winfo_height()
        if pw < 2 or ph < 2:
            return

        img_w, img_h = self._preview_img_raw.size
        # Orijinal en-boy oranını koru — en fazla frame'e sığacak kadar büyüt
        scale = min(pw / img_w, ph / img_h)
        new_w = max(1, int(img_w * scale))
        new_h = max(1, int(img_h * scale))
        img_scaled = self._preview_img_raw.resize((new_w, new_h), Image.LANCZOS)

        photo = ImageTk.PhotoImage(img_scaled)
        self.preview_photo = photo
        # place ile merkeze sabitle — tkinter görüntüyü uzatmaz
        self.preview_label.config(image=photo, text="", bg="#0d0d1a")
        self.preview_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

    def _on_preview_frame_resize(self, event):
        """Ana pencere boyutu değişince önizlemeyi yeniden ölçekle."""
        if self._preview_img_raw is not None:
            self._render_preview_image()

    def schedule_preview(self):
        if self._preview_job:
            self.root.after_cancel(self._preview_job)
        self._preview_job = self.root.after(150, self.update_preview)

    def _set_info_text(self, text):
        """Bilgi panelindeki metni güncelle"""
        self.info_text.config(state=tk.NORMAL)
        self.info_text.delete(1.0, tk.END)
        self.info_text.insert(tk.END, text)
        self.info_text.config(state=tk.DISABLED)

    def update_preview(self):
        hwnd = self.selected_hwnd
        if not hwnd:
            self.preview_label.config(image='', text="Pencere bulunamadı", fg="#334455")
            self.preview_photo = None
            self._set_info_text("—")
            return
        try:
            rect = win32gui.GetWindowRect(hwnd)
            win_w = rect[2] - rect[0]
            win_h = rect[3] - rect[1]
            if win_w <= 0 or win_h <= 0:
                raise ValueError("Geçersiz pencere boyutu")

            hwnd_dc = win32gui.GetWindowDC(hwnd)
            mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
            save_dc = mfc_dc.CreateCompatibleDC()
            save_bitmap = win32ui.CreateBitmap()
            save_bitmap.CreateCompatibleBitmap(mfc_dc, win_w, win_h)
            save_dc.SelectObject(save_bitmap)
            ctypes.windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 2)
            bmp_info = save_bitmap.GetInfo()
            bmp_str = save_bitmap.GetBitmapBits(True)
            img = Image.frombuffer(
                'RGB', (bmp_info['bmWidth'], bmp_info['bmHeight']),
                bmp_str, 'raw', 'BGRX', 0, 1
            )
            win32gui.DeleteObject(save_bitmap.GetHandle())
            save_dc.DeleteDC()
            mfc_dc.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwnd_dc)

            # Ham görüntüyü sakla, render fonksiyonu ölçeklemeyi yapar
            self._preview_img_raw = img.copy()
            self._render_preview_image()

        except Exception as e:
            self.preview_label.config(
                image='', bg="#0d0d1a", fg="#334455",
                text=f"Ön izleme\nalınamadı\n({type(e).__name__})"
            )
            self.preview_photo = None

        # Pencere detaylarını güncelle (her durumda)
        try:
            d = self.get_window_details(hwnd)
            topmost = self._is_topmost(hwnd)
            lines = []
            lines.append(f"Başlık\n  {d.get('title', '—')[:60]}\n")
            lines.append(f"Sınıf    {d.get('class', '—')}")
            lines.append(f"HWND     {d.get('hwnd', '—')}")
            lines.append(f"Konum    X:{d.get('x','—')}  Y:{d.get('y','—')}")
            lines.append(f"Boyut    {d.get('width','—')} × {d.get('height','—')} px")
            lines.append(f"Durum    {d.get('state','—')}")
            lines.append(f"Üstte    {'✔ Evet' if topmost else '✘ Hayır'}")
            lines.append(f"Ekran    {d.get('monitor','—')}")
            lines.append(f"\nPID      {d.get('pid','—')}")
            lines.append(f"Proses   {d.get('process','—')}")
            lines.append(f"CPU      {d.get('cpu','—')}")
            lines.append(f"RAM      {d.get('memory','—')}")
            self._set_info_text("\n".join(lines))

            # Topmost buton görünümünü duruma göre güncelle
            if self._topmost_btn:
                if topmost:
                    self._topmost_btn.config(
                        text="📌  Her Zaman Üstte  ✔",
                        fg="#111100", bg="#ddbb00"
                    )
                else:
                    self._topmost_btn.config(
                        text="📌  Her Zaman Üstte",
                        fg="#ffdd88", bg="#2a2210"
                    )
        except Exception:
            self._set_info_text("Bilgi alınamadı")

    # ─────────────────────────── Otomatik Yenileme ───────────────────────────────

    def on_auto_refresh_toggle(self):
        if self.auto_refresh_enabled.get():
            self.auto_indicator.config(fg="#44cc77")
            self.schedule_auto_refresh()
        else:
            self.auto_indicator.config(fg="#444466")
            if self._auto_refresh_job:
                self.root.after_cancel(self._auto_refresh_job)
                self._auto_refresh_job = None

    def schedule_auto_refresh(self):
        if self._auto_refresh_job:
            self.root.after_cancel(self._auto_refresh_job)
        if self.auto_refresh_enabled.get():
            self._auto_refresh_job = self.root.after(
                self.auto_refresh_interval, self.auto_refresh_tick
            )

    def auto_refresh_tick(self):
        if self.auto_refresh_enabled.get():
            self.silent_refresh()
            self.schedule_auto_refresh()

    def silent_refresh(self):
        if self._is_refreshing:
            return
        self._is_refreshing = True

        saved_hwnd = self.selected_hwnd
        windows = self.get_windows_by_monitor()
        self.windows_data = windows

        for monitor_idx in range(len(self.monitors)):
            listbox = self.listboxes[monitor_idx]
            listbox.delete(0, tk.END)
            for w in windows.get(monitor_idx, []):
                listbox.insert(tk.END, w['title'])

        restored = False
        if saved_hwnd:
            for monitor_idx in range(len(self.monitors)):
                for i, w in enumerate(self.windows_data.get(monitor_idx, [])):
                    if w['hwnd'] == saved_hwnd:
                        self.listboxes[monitor_idx].selection_set(i)
                        self.listboxes[monitor_idx].see(i)
                        self.selected_window = i
                        self.selected_monitor = monitor_idx
                        self.selected_hwnd = saved_hwnd
                        restored = True
                        break
                if restored:
                    break

        if not restored and saved_hwnd:
            self.selected_window = None
            self.selected_monitor = None
            self.selected_hwnd = None
            self.preview_label.config(image='', text="Pencere kapandı", fg="#334455")
            self.preview_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
            self.preview_photo = None
            self._preview_img_raw = None
            self._set_info_text("—")

        self._is_refreshing = False

    # ─────────────────────────── Manuel Yenile ───────────────────────────────────

    def refresh_windows(self):
        windows = self.get_windows_by_monitor()
        self.windows_data = windows

        for listbox in self.listboxes:
            listbox.delete(0, tk.END)

        for monitor_idx in range(len(self.monitors)):
            for w in windows.get(monitor_idx, []):
                self.listboxes[monitor_idx].insert(tk.END, w['title'])

        self.selected_window = None
        self.selected_monitor = None
        self.selected_hwnd = None
        self.preview_label.config(image='', text="Bir pencere\nseçin",
                                  fg="#334455", bg="#0d0d1a")
        self.preview_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        self.preview_photo = None
        self._preview_img_raw = None
        self._set_info_text("—")
        self.status_label.config(text="  Liste yenilendi", fg="#667788")
        self.schedule_auto_refresh()

    def _is_topmost(self, hwnd):
        """Pencerenin şu an 'her zaman üstte' modunda olup olmadığını döndür"""
        try:
            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            return bool(ex_style & win32con.WS_EX_TOPMOST)
        except Exception:
            return False

    def action_toggle_topmost(self):
        hwnd = self._require_selection()
        if not hwnd:
            return
        try:
            currently_topmost = self._is_topmost(hwnd)
            if currently_topmost:
                # Kapat
                win32gui.SetWindowPos(
                    hwnd,
                    win32con.HWND_NOTOPMOST,
                    0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
                )
                self.status_label.config(text="  📌  'Her zaman üstte' kapatıldı", fg="#888866")
                if self._topmost_btn:
                    self._topmost_btn.config(
                        text="📌  Her Zaman Üstte",
                        fg="#ffdd88", bg="#2a2210"
                    )
            else:
                # Aç
                win32gui.SetWindowPos(
                    hwnd,
                    win32con.HWND_TOPMOST,
                    0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
                )
                self.status_label.config(text="  📌  'Her zaman üstte' açıldı", fg="#ffdd44")
                if self._topmost_btn:
                    self._topmost_btn.config(
                        text="📌  Her Zaman Üstte  ✔",
                        fg="#111100", bg="#ddbb00"
                    )
            # Bilgi panelini yenile
            self.root.after(200, self.schedule_preview)
        except Exception as e:
            self.status_label.config(text=f"  ⚠  Hata: {e}", fg="#cc4444")

    # ─────────────────────────── Pencere Eylemleri ───────────────────────────────

    def _require_selection(self):
        """Seçili pencere yoksa uyarı ver, varsa hwnd döndür"""
        if not self.selected_hwnd:
            self.status_label.config(text="  ⚠  Önce bir pencere seçin", fg="#cc8844")
            return None
        return self.selected_hwnd

    def action_maximize(self):
        hwnd = self._require_selection()
        if not hwnd:
            return
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
            self.status_label.config(text="  ⬜  Pencere ekranı kapladı", fg="#44ccff")
            self.root.after(400, self.schedule_preview)
        except Exception as e:
            self.status_label.config(text=f"  ⚠  Hata: {e}", fg="#cc4444")

    def action_minimize(self):
        hwnd = self._require_selection()
        if not hwnd:
            return
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
            self.status_label.config(text="  ⬛  Pencere küçültüldü", fg="#88cc88")
            self.root.after(400, self.schedule_preview)
        except Exception as e:
            self.status_label.config(text=f"  ⚠  Hata: {e}", fg="#cc4444")

    def action_restore(self):
        hwnd = self._require_selection()
        if not hwnd:
            return
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            self.status_label.config(text="  ↩  Pencere normal boyuta getirildi", fg="#ccbbaa")
            self.root.after(400, self.schedule_preview)
        except Exception as e:
            self.status_label.config(text=f"  ⚠  Hata: {e}", fg="#cc4444")

    def action_close_window(self):
        hwnd = self._require_selection()
        if not hwnd:
            return
        try:
            title = win32gui.GetWindowText(hwnd)
            # Onay popup
            confirm = tk.Toplevel(self.root)
            confirm.title("Onayla")
            confirm.configure(bg="#1a1a2e")
            confirm.resizable(False, False)
            confirm.grab_set()
            # Ortalama
            confirm.geometry("320x130")
            confirm.update_idletasks()
            rx = self.root.winfo_x() + (self.root.winfo_width() - 320) // 2
            ry = self.root.winfo_y() + (self.root.winfo_height() - 130) // 2
            confirm.geometry(f"320x130+{rx}+{ry}")

            tk.Label(
                confirm,
                text=f"Pencere kapatılsın mı?",
                font=("Segoe UI", 10, "bold"),
                bg="#1a1a2e", fg="#dddddd"
            ).pack(pady=(16, 4))
            tk.Label(
                confirm,
                text=title[:50],
                font=("Segoe UI", 8),
                bg="#1a1a2e", fg="#778899",
                wraplength=290
            ).pack()

            btn_row = tk.Frame(confirm, bg="#1a1a2e")
            btn_row.pack(pady=14)

            def _do_close():
                confirm.destroy()
                try:
                    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                    self.status_label.config(text=f"  ✕  '{title}' kapatma isteği gönderildi", fg="#ffaaaa")
                    self.root.after(600, self.refresh_windows)
                except Exception as ex:
                    self.status_label.config(text=f"  ⚠  Hata: {ex}", fg="#cc4444")

            tk.Button(btn_row, text="Kapat", command=_do_close,
                      font=("Segoe UI", 9, "bold"),
                      bg="#3a1a1a", fg="#ff8888", relief=tk.FLAT,
                      padx=18, pady=4, cursor="hand2").pack(side=tk.LEFT, padx=6)
            tk.Button(btn_row, text="İptal", command=confirm.destroy,
                      font=("Segoe UI", 9),
                      bg="#1e1e35", fg="#888888", relief=tk.FLAT,
                      padx=18, pady=4, cursor="hand2").pack(side=tk.LEFT, padx=6)

        except Exception as e:
            self.status_label.config(text=f"  ⚠  Hata: {e}", fg="#cc4444")

    def action_kill_process(self):
        hwnd = self._require_selection()
        if not hwnd:
            return
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc = psutil.Process(pid)
            proc_name = proc.name()
            title = win32gui.GetWindowText(hwnd)

            # Onay popup — daha belirgin uyarı
            confirm = tk.Toplevel(self.root)
            confirm.title("⚠ Prosesi Sonlandır")
            confirm.configure(bg="#1a0a0a")
            confirm.resizable(False, False)
            confirm.grab_set()
            confirm.geometry("340x160")
            confirm.update_idletasks()
            rx = self.root.winfo_x() + (self.root.winfo_width() - 340) // 2
            ry = self.root.winfo_y() + (self.root.winfo_height() - 160) // 2
            confirm.geometry(f"340x160+{rx}+{ry}")

            tk.Label(
                confirm,
                text="☠  Proses zorla sonlandırılacak!",
                font=("Segoe UI", 10, "bold"),
                bg="#1a0a0a", fg="#ff5555"
            ).pack(pady=(14, 2))
            tk.Label(
                confirm,
                text=f"{proc_name}  (PID: {pid})",
                font=("Consolas", 9),
                bg="#1a0a0a", fg="#cc6666"
            ).pack()
            tk.Label(
                confirm,
                text="Kaydedilmemiş veriler kaybolabilir.",
                font=("Segoe UI", 8),
                bg="#1a0a0a", fg="#885555"
            ).pack(pady=(4, 0))

            btn_row = tk.Frame(confirm, bg="#1a0a0a")
            btn_row.pack(pady=14)

            def _do_kill():
                confirm.destroy()
                try:
                    proc.kill()
                    self.status_label.config(
                        text=f"  ☠  '{proc_name}' (PID:{pid}) sonlandırıldı",
                        fg="#ff6666"
                    )
                    self.selected_hwnd = None
                    self.selected_window = None
                    self.selected_monitor = None
                    self.preview_label.config(image='', text="Proses sonlandırıldı", fg="#334455")
                    self.preview_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
                    self.preview_photo = None
                    self._preview_img_raw = None
                    self._set_info_text("—")
                    self.root.after(600, self.refresh_windows)
                except Exception as ex:
                    self.status_label.config(text=f"  ⚠  Hata: {ex}", fg="#cc4444")

            tk.Button(btn_row, text="☠  Sonlandır", command=_do_kill,
                      font=("Segoe UI", 9, "bold"),
                      bg="#440000", fg="#ff4444", relief=tk.FLAT,
                      padx=14, pady=4, cursor="hand2").pack(side=tk.LEFT, padx=6)
            tk.Button(btn_row, text="İptal", command=confirm.destroy,
                      font=("Segoe UI", 9),
                      bg="#1e1e1e", fg="#888888", relief=tk.FLAT,
                      padx=14, pady=4, cursor="hand2").pack(side=tk.LEFT, padx=6)

        except Exception as e:
            self.status_label.config(text=f"  ⚠  Hata: {e}", fg="#cc4444")

    # ─────────────────────────── Pencere Taşıma ──────────────────────────────────

    def move_window_right(self, from_monitor):
        if from_monitor >= len(self.monitors) - 1:
            return
        if self.selected_monitor == from_monitor and self.selected_window is not None:
            self.move_window(from_monitor, from_monitor + 1)

    def move_window_left(self, from_monitor):
        if from_monitor <= 0:
            return
        if self.selected_monitor == from_monitor and self.selected_window is not None:
            self.move_window(from_monitor, from_monitor - 1)

    def move_window(self, from_monitor, to_monitor):
        if self.selected_window is None:
            return

        windows = self.get_windows_by_monitor()
        if from_monitor not in windows or self.selected_window >= len(windows[from_monitor]):
            self.status_label.config(text="  ⚠  Pencere bulunamadı!", fg="#cc4444")
            return

        window_info = windows[from_monitor][self.selected_window]
        hwnd = window_info['hwnd']
        target = self.monitors[to_monitor]

        try:
            rect = win32gui.GetWindowRect(hwnd)
            w = rect[2] - rect[0]
            h = rect[3] - rect[1]
            new_x = target['left'] + (target['width'] - w) // 2
            new_y = target['top'] + (target['height'] - h) // 2

            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

            win32gui.SetWindowPos(
                hwnd, None, new_x, new_y, w, h,
                win32con.SWP_NOZORDER | win32con.SWP_NOSIZE
            )
            self.status_label.config(
                text=f"  ✔  '{window_info['title']}' → Ekran {to_monitor + 1}",
                fg="#44cc77"
            )
        except Exception as e:
            msg = str(e)
            if "Erişim engellendi" in msg or "Access is denied" in msg:
                self.status_label.config(
                    text=f"  ⚠  Erişim engellendi! '{window_info['title']}' taşınamadı.",
                    fg="#cc4444"
                )
            else:
                self.status_label.config(text=f"  ⚠  Hata: {msg}", fg="#cc4444")
            return

        self.root.after(300, self.refresh_windows)


def main():
    root = tk.Tk()
    app = WindowManager(root)
    root.mainloop()


if __name__ == "__main__":
    main()
