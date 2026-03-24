"""
Barkod PDF Otomatik Yazdırma & Arayüz Tetikleme Servisi
Hem arayüzdeki "Gönder" butonunu takip eder, hem de PDF dosyalarını otomatik yazdırır.
"""

import os
import sys  # Dizin sabitleme için eklendi
import time
import configparser
import win32api
import win32print
import win32ui
import win32con
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from datetime import datetime

# Arayüz kontrol kütüphanesi eklendi
from pywinauto import Desktop

try:
    import fitz  # PyMuPDF
    from PIL import Image
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False


# ==========================================
# ÇÖZÜM: ÇALIŞMA DİZİNİNİ SABİTLEME
# ==========================================
if getattr(sys, 'frozen', False):
    # Program .exe olarak çalışıyorsa (PyInstaller)
    SCRIPT_DIR = os.path.dirname(sys.executable)
else:
    # Program normal .py scripti olarak çalışıyorsa
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Çalışma dizinini kalıcı olarak exe'nin yanına alıyoruz
os.chdir(SCRIPT_DIR)
# ==========================================

SETTINGS_FILE = os.path.join(SCRIPT_DIR, "settings.ini")


class Config:
    """Ayar dosyasını okur"""
    def __init__(self):
        self.config = configparser.ConfigParser()

        if not os.path.exists(SETTINGS_FILE):
            self.log_error(f"HATA: settings.ini dosyası bulunamadı: {SETTINGS_FILE}")
            self.log_error("Lütfen setup.py scriptini çalıştırın!")
            exit(1)

        self.config.read(SETTINGS_FILE, encoding='utf-8')

        # Ayarları oku
        self.printer_name = self.config.get('PRINTER', 'PrinterName')
        self.watch_folder = self.config.get('WATCH', 'WatchFolder')
        self.watch_file = self.config.get('WATCH', 'WatchFile')
        self.wait_seconds = self.config.getint('OPTIONS', 'WaitSeconds', fallback=2)
        self.prevent_duplicates = self.config.getboolean('OPTIONS', 'PreventDuplicates', fallback=True)
        self.enable_logging = self.config.getboolean('OPTIONS', 'EnableLogging', fallback=True)
        self.log_file = self.config.get('OPTIONS', 'LogFile', fallback=os.path.join(SCRIPT_DIR, 'print_log.txt'))
        self.adobe_path = self.config.get('OPTIONS', 'AdobePath', fallback=None)

        # Klasör kontrolü
        if not os.path.exists(self.watch_folder):
            self.log_error(f"HATA: İzlenecek klasör bulunamadı: {self.watch_folder}")
            exit(1)

    def log_error(self, message):
        print(message)


class PDFPrintHandler(FileSystemEventHandler):
    """PDF dosyası değişikliklerini izleyen handler"""

    def __init__(self, config):
        self.config = config
        self.last_modified_times = {}
        self.printed_files = set()
        self.scan_existing_files()

    def scan_existing_files(self):
        try:
            for filename in os.listdir(self.config.watch_folder):
                if self.should_watch_file(filename):
                    filepath = os.path.join(self.config.watch_folder, filename)
                    if os.path.isfile(filepath):
                        self.last_modified_times[filepath] = os.path.getmtime(filepath)
                        self.log(f"Mevcut dosya kaydedildi: {filename}")
        except Exception as e:
            self.log(f"Dosya tarama hatası: {e}")

    def should_watch_file(self, filename):
        watch_file = self.config.watch_file.strip()
        if watch_file == "*.pdf":
            return filename.lower().endswith('.pdf')
        return filename == watch_file

    def on_created(self, event):
        return

    def on_modified(self, event):
        if event.is_directory:
            return

        filename = os.path.basename(event.src_path)
        if not self.should_watch_file(filename):
            return

        try:
            current_modified_time = os.path.getmtime(event.src_path)
            last_time = self.last_modified_times.get(event.src_path)

            if last_time is None or current_modified_time > last_time:
                self.last_modified_times[event.src_path] = current_modified_time
                self.log(f"Dosya değişikliği tespit edildi: {filename}")
                time.sleep(self.config.wait_seconds)
                self.print_pdf(event.src_path)
        except Exception as e:
            self.log(f"Dosya kontrol hatası: {e}")

    def print_pdf(self, filepath):
        try:
            if not os.path.exists(filepath):
                self.log(f"HATA: Dosya bulunamadı: {filepath}")
                return

            if self.config.prevent_duplicates:
                file_key = f"{filepath}_{os.path.getmtime(filepath)}"
                if file_key in self.printed_files:
                    self.log(f"Bu dosya zaten yazdırıldı, atlaniyor: {os.path.basename(filepath)}")
                    return
                self.printed_files.add(file_key)

                if len(self.printed_files) > 100:
                    self.printed_files.clear()

            self.log(f"Yazdırma başlatılıyor: {os.path.basename(filepath)} → {self.config.printer_name}")

            success = False

            # YÖNTEM 1
            if not success and self.config.adobe_path and os.path.exists(self.config.adobe_path):
                try:
                    self.log("  Yöntem 1: Adobe Acrobat ile yazdırılıyor...")
                    success = self.print_with_adobe(filepath)
                    if success:
                        self.log(f"  ✓ Adobe ile yazdırma başarılı!")
                except Exception as e:
                    self.log(f"  Yöntem 1 başarısız: {e}")

            # YÖNTEM 2
            if not success and PYMUPDF_AVAILABLE:
                try:
                    self.log("  Yöntem 2: PDF render ediliyor (Windows driver)...")
                    success = self.print_with_gdi(filepath)
                    if success:
                        self.log(f"  ✓ Windows GDI ile yazdırma başarılı!")
                except Exception as e:
                    self.log(f"  Yöntem 2 başarısız: {e}")

            # YÖNTEM 3
            if not success:
                try:
                    self.log("  Yöntem 3: PrintTo komutu deneniyor...")
                    result = win32api.ShellExecute(0, "printto", filepath, f'"{self.config.printer_name}"', ".", 0)
                    if result > 32:
                        self.log(f"  ✓ PrintTo ile yazdırma başarılı!")
                        success = True
                    else:
                        self.log(f"  Yöntem 3 başarısız, sonuç kodu: {result}")
                except Exception as e:
                    self.log(f"  Yöntem 3 başarısız: {e}")

            if not success:
                self.log(f"✗ TÜM YÖNTEMLER BAŞARISIZ!")
            else:
                self.log(f"✓ Yazdırma işlemi başarıyla gönderildi!")

        except Exception as e:
            self.log(f"HATA: {e}")

    def print_with_adobe(self, filepath):
        import subprocess
        import psutil
        try:
            page_count = 0
            if PYMUPDF_AVAILABLE:
                try:
                    doc = fitz.open(filepath)
                    page_count = len(doc)
                    doc.close()
                except:
                    pass

            adobe_exe_name = os.path.basename(self.config.adobe_path)
            
            try:
                for proc in psutil.process_iter(['pid', 'name']):
                    if proc.info['name'] and proc.info['name'].lower() == adobe_exe_name.lower():
                        try:
                            proc.kill()
                        except:
                            pass
                time.sleep(1.0)
            except:
                pass

            cmd = [self.config.adobe_path, "/t", filepath, self.config.printer_name]
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )

            try:
                process.communicate(timeout=7)
                return True
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                    process.wait(timeout=6)
                except:
                    pass
                return True

        except Exception:
            return False

    def print_with_gdi(self, filepath):
        import tempfile
        try:
            doc = fitz.open(filepath)
            hDC = win32ui.CreateDC()
            hDC.CreatePrinterDC(self.config.printer_name)
            hDC.StartDoc(os.path.basename(filepath))

            for page_num in range(len(doc)):
                page = doc[page_num]
                zoom = 203 / 72
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                
                temp_bmp = os.path.join(tempfile.gettempdir(), f"temp_print_{page_num}.bmp")
                img.save(temp_bmp, "BMP")
                bmp = Image.open(temp_bmp)
                
                hDC.StartPage()
                printer_width = hDC.GetDeviceCaps(win32con.HORZRES)
                printer_height = hDC.GetDeviceCaps(win32con.VERTRES)
                img_width, img_height = bmp.size
                
                scale = min(printer_width / img_width, printer_height / img_height)
                scaled_width = int(img_width * scale)
                scaled_height = int(img_height * scale)
                x_offset = (printer_width - scaled_width) // 2
                y_offset = (printer_height - scaled_height) // 2
                
                dib = win32ui.CreateBitmap()
                with open(temp_bmp, 'rb') as bmp_file:
                    dib.LoadBitmapFile(bmp_file)
                    
                dcMem = hDC.CreateCompatibleDC()
                dcMem.SelectObject(dib)
                hDC.StretchBlt((x_offset, y_offset), (scaled_width, scaled_height), dcMem, (0, 0), (img_width, img_height), win32con.SRCCOPY)
                
                dcMem.DeleteDC()
                bmp.close()
                try: os.remove(temp_bmp)
                except: pass
                
                hDC.EndPage()

            hDC.EndDoc()
            hDC.DeleteDC()
            doc.close()
            return True

        except Exception:
            try:
                hDC.AbortDoc()
                hDC.DeleteDC()
            except:
                pass
            return False

    def log(self, message):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_message = f"[{timestamp}] {message}"
        print(log_message)
        if self.config.enable_logging:
            try:
                with open(self.config.log_file, 'a', encoding='utf-8') as f:
                    f.write(log_message + '\n')
            except:
                pass


def check_printer(printer_name):
    """Yazıcının erişilebilir olup olmadığını kontrol et"""
    try:
        printers = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)
        printer_names = [p[2] for p in printers]

        if printer_name in printer_names:
            print(f"✓ Yazıcı bulundu: {printer_name}")
            return True
        else:
            print(f"⚠ UYARI: Yazıcı listede bulunamadı: {printer_name}")
            return False
    except Exception:
        return False


import ctypes

def _hwnd_gecerli_mi(hwnd):
    """Windows API ile HWND'nin hâlâ var olan bir pencereye ait olup olmadığını kontrol eder."""
    try:
        return bool(ctypes.windll.user32.IsWindow(hwnd))
    except Exception:
        return False


def _melis_penceresi_bul(desktop):
    """
    Gerçekten var olan (handle'ı olan) MELİS penceresini döndürür.
    Bulunamazsa None döner, exception fırlatmaz.
    """
    try:
        tum_pencereler = desktop.windows()
        for pen in tum_pencereler:
            try:
                baslik = pen.window_text()
                if ("MELİS" in baslik and "İstem" in baslik) or "Merkezi Laboratuvar" in baslik:
                    return pen
            except Exception:
                continue
    except Exception:
        pass
    return None


def _buton_etkin_mi(buton):
    """
    Butonun aktif (enabled) olup olmadığını birden fazla yöntemle kontrol eder.
    is_enabled() bazen UIA cache nedeniyle yanlış sonuç döner.
    """
    try:
        # Yöntem 1: UIA'nın IsEnabled property'si (en güvenilir)
        props = buton.get_properties()
        return props.get('is_enabled', False)
    except Exception:
        pass
    try:
        # Yöntem 2: Doğrudan is_enabled() çağrısı
        return buton.is_enabled()
    except Exception:
        pass
    return None  # Okunamadı


def _tum_butonlari_listele(pencere):
    """DEBUG: Penceredeki tüm butonları ve durumlarını yazdırır."""
    try:
        butonlar = pencere.children(control_type="Button")
        print(f"  [DEBUG] Pencerede {len(butonlar)} buton bulundu:")
        for b in butonlar:
            try:
                ad = b.window_text()
                etkin = b.get_properties().get('is_enabled', '?')
                print(f"    - '{ad}' | enabled={etkin}")
            except Exception as e:
                print(f"    - [okunamadı: {e}]")
    except Exception as e:
        print(f"  [DEBUG] Buton listesi alınamadı: {e}")


def melis_arayuz_izleyicisi():
    """MELİS programını sürekli izleyerek otomatik tıklama yapan ana döngü"""
    print("\n" + "-" * 80)
    print("Arayüz (GUI) İzleme Sistemi Devrede...")
    print("MELİS programında 'Gönder' butonu takip ediliyor.")
    print("-" * 80)
    
    desktop = Desktop(backend="uia")
    
    onceki_durum = None
    program_bulundu = False
    mevcut_hwnd = None          # Önbelleklenmiş pencere handle'ı
    pencere_ref = None          # Önbelleklenmiş pencere nesnesi
    hata_sayaci = 0             # Arka arkaya hata sayısı — geçici mi kalıcı mı?
    HATA_ESIGI = 6              # 6 × 0.5s = 3 saniye hata toleransı
    debug_mod = True            # İlk buluşta buton listesini göster

    while True:
        # --- 1. ADIM: Pencere geçerliliğini kontrol et ---
        pencere_gecerli = False
        if mevcut_hwnd is not None and _hwnd_gecerli_mi(mevcut_hwnd):
            pencere_gecerli = True
        else:
            # HWND geçersiz veya yok — yeniden ara
            pencere_ref = _melis_penceresi_bul(desktop)
            if pencere_ref is not None:
                try:
                    mevcut_hwnd = pencere_ref.handle
                    pencere_gecerli = True
                except Exception:
                    pencere_ref = None

        if not pencere_gecerli:
            hata_sayaci += 1
            if hata_sayaci >= HATA_ESIGI and program_bulundu:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] >> MELİS programı bulunamadı. Programın açılması bekleniyor...")
                program_bulundu = False
                onceki_durum = None
                mevcut_hwnd = None
                pencere_ref = None
                debug_mod = True
            time.sleep(0.5)
            continue

        # Pencere geçerli — hata sayacını sıfırla
        hata_sayaci = 0

        if not program_bulundu:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] >> MELİS programı bulundu, otomatik tıklama aktif.")
            program_bulundu = True

        # --- 2. ADIM: Butonlara eriş ---
        try:
            # UIA cache'ini atlatmak için pencere referansını tazele
            pencere_ref = desktop.window(handle=mevcut_hwnd)

            gonder_butonu = pencere_ref.child_window(title="Gönder", control_type="Button")
            yazdir_butonu = pencere_ref.child_window(title="Tüm Numunelerin Barkodunu Yazdır", control_type="Button")

            # İlk bağlantıda veya yeniden bağlantıda buton listesini göster
            if debug_mod:
                _tum_butonlari_listele(pencere_ref)
                debug_mod = False

            su_anki_durum = _buton_etkin_mi(gonder_butonu)

            if su_anki_durum is None:
                # Buton okunamadı — geçici, bekle
                time.sleep(0.5)
                continue

        except Exception as e:
            # Pencere var ama butonlara henüz erişilemiyor
            hata_sayaci += 1
            if hata_sayaci >= HATA_ESIGI:
                # Pencere referansını yenile
                mevcut_hwnd = None
                pencere_ref = None
            time.sleep(0.5)
            continue

        # --- 3. ADIM: Durum değişikliğini yakala ---
        if onceki_durum is True and su_anki_durum is False:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] >> Tahlil gönderildi! Barkod için kısa bir süre bekleniyor...")
            
            # Programın barkodu oluşturması için bekle
            time.sleep(1.0)

            # Yazdir butonunu tazele ve tıkla
            tiklama_basarili = False
            for deneme in range(3):
                try:
                    yazdir_butonu = pencere_ref.child_window(
                        title="Tüm Numunelerin Barkodunu Yazdır", control_type="Button"
                    )
                    yazdir_butonu.click_input()
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] >> 'Yazdır' tuşuna BAŞARIYLA tıklandı!\n")
                    tiklama_basarili = True
                    break
                except Exception as e1:
                    try:
                        yazdir_butonu.invoke()
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] >> 'Yazdır' tuşuna (invoke) BAŞARIYLA tıklandı!\n")
                        tiklama_basarili = True
                        break
                    except Exception as e2:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] >> Deneme {deneme+1} başarısız: {e2}")
                        time.sleep(0.5)

            if not tiklama_basarili:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] >> HATA: Yazdır butonuna 3 denemede de basılamadı!\n")
            else:
                # Yazdırma başarılı — MELİS penceresini kapat
                time.sleep(0.5)
                try:
                    pencere_ref.close()
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] >> MELİS penceresi kapatıldı.")
                    # Durum sıfırla — pencere kapandığı için HWND artık geçersiz
                    mevcut_hwnd = None
                    pencere_ref = None
                    program_bulundu = False
                    onceki_durum = None
                    debug_mod = True
                except Exception as e:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] >> MELİS penceresi kapatılamadı: {e}")

        onceki_durum = su_anki_durum
            
        # CPU'yu yormamak için her kontrol arasında yarım saniye bekle
        time.sleep(0.5)


def main():
    print("=" * 80)
    print("BARKOD OTOMASYON VE YAZDIRMA SERVİSİ")
    print("=" * 80)
    print(f"Başlangıç zamanı: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    config = Config()

    if not check_printer(config.printer_name):
        print("\n⚠ UYARI: Yazıcı şu an erişilebilir değil!")
        print("Yine de arayüz otomasyonu başlatılsın mı? (E/H): ", end='')
        try:
            choice = input().strip().upper()
            if choice != 'E':
                return
        except KeyboardInterrupt:
            return

    # 1. Aşama: Arka planda klasör izleyiciyi (Watchdog) başlat
    event_handler = PDFPrintHandler(config)
    observer = Observer()
    observer.schedule(event_handler, config.watch_folder, recursive=False)
    observer.start()
    
    print(f"\n✓ PDF İzleme başlatıldı: {config.watch_folder}")

    # 2. Aşama: Ana iş parçacığında Arayüz İzleyiciyi çalıştır
    try:
        # Bu fonksiyon sonsuz döngüye girecek ve programı hayatta tutacak
        melis_arayuz_izleyicisi()
        
    except KeyboardInterrupt:
        print("\n\nSistem kullanıcı tarafından durduruluyor...")
    finally:
        # Sistem durdurulduğunda arka plandaki klasör izleyiciyi de temiz bir şekilde kapat
        observer.stop()
        observer.join()
        print("Servis tamamen kapatıldı.")

if __name__ == "__main__":
    main()