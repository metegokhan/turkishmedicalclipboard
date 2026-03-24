"""
Barkod Yazdırma Servisi Kurulum ve Yapılandırma
settings.ini dosyasını kolayca düzenlemenizi sağlar
"""

import os
import configparser
import win32print

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(SCRIPT_DIR, "settings.ini")


def list_printers():
    """Sistemdeki tüm yazıcıları listele"""
    try:
        printers = win32print.EnumPrinters(
            win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        )
        return [p[2] for p in printers]
    except Exception as e:
        print(f"Yazıcılar listelenemedi: {e}")
        return []


def select_printer():
    """Kullanıcıya yazıcı seçtir"""
    print("\n" + "=" * 80)
    print("YAZICI SEÇİMİ")
    print("=" * 80)

    printers = list_printers()

    if not printers:
        print("Sistemde yazıcı bulunamadı!")
        return None

    print("\nMevcut yazıcılar:")
    for i, printer in enumerate(printers, 1):
        print(f"{i}. {printer}")

    print("\nYazıcı seçin (numara girin) veya yazıcı adını tam olarak yazın:")
    choice = input("Seçiminiz: ").strip()

    # Numara ile seçim
    if choice.isdigit():
        index = int(choice) - 1
        if 0 <= index < len(printers):
            return printers[index]
        else:
            print("Geçersiz numara!")
            return None

    # İsim ile seçim
    if choice in printers:
        return choice

    print("Yazıcı bulunamadı!")
    return None


def select_folder():
    """İzlenecek klasörü seç"""
    print("\n" + "=" * 80)
    print("İZLENECEK KLASÖR")
    print("=" * 80)

    default_folder = r"C:\Neuroogle_AHBYS\BarkodPdf"
    print(f"\nVarsayılan klasör: {default_folder}")
    print("Farklı bir klasör girmek için tam yolunu yazın")
    print("Varsayılanı kullanmak için Enter'a basın:")

    folder = input("Klasör yolu: ").strip()

    if not folder:
        folder = default_folder

    if os.path.exists(folder):
        return folder
    else:
        print(f"⚠ UYARI: Klasör şu an mevcut değil: {folder}")
        print("Yine de kullanmak istiyor musunuz? (E/H):", end=' ')
        choice = input().strip().upper()
        if choice == 'E':
            return folder
        return None


def select_watch_file():
    """İzlenecek dosyayı seç"""
    print("\n" + "=" * 80)
    print("İZLENECEK DOSYA")
    print("=" * 80)
    print("\nSeçenekler:")
    print("1. Belirli bir dosya (örn: Barkod.pdf)")
    print("2. Tüm PDF dosyaları (*.pdf)")

    choice = input("\nSeçiminiz (1 veya 2): ").strip()

    if choice == "1":
        filename = input("Dosya adı (örn: Barkod.pdf): ").strip()
        return filename if filename else "Barkod.pdf"
    elif choice == "2":
        return "*.pdf"
    else:
        print("Geçersiz seçim! Varsayılan: Barkod.pdf")
        return "Barkod.pdf"


def create_settings(printer_name, watch_folder, watch_file):
    """settings.ini dosyasını oluştur"""
    config = configparser.ConfigParser()

    config['PRINTER'] = {
        'PrinterName': printer_name
    }

    config['WATCH'] = {
        'WatchFolder': watch_folder,
        'WatchFile': watch_file
    }

    config['OPTIONS'] = {
        'WaitSeconds': '2',
        'PreventDuplicates': 'True',
        'EnableLogging': 'True',
        'LogFile': os.path.join(SCRIPT_DIR, 'print_log.txt')
    }

    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        f.write("# Barkod Yazdırma Servisi Ayarları\n")
        f.write("# Bu dosyayı metin editörü ile düzenleyebilirsiniz\n\n")
        config.write(f)

    print(f"\n✓ Ayarlar kaydedildi: {SETTINGS_FILE}")


def show_current_settings():
    """Mevcut ayarları göster"""
    if not os.path.exists(SETTINGS_FILE):
        print("\n⚠ settings.ini dosyası henüz oluşturulmamış.")
        return False

    print("\n" + "=" * 80)
    print("MEVCUT AYARLAR")
    print("=" * 80)

    try:
        config = configparser.ConfigParser()
        config.read(SETTINGS_FILE, encoding='utf-8')

        print("\n[PRINTER]")
        print(f"  Yazıcı: {config.get('PRINTER', 'PrinterName')}")

        print("\n[WATCH]")
        print(f"  İzlenen klasör: {config.get('WATCH', 'WatchFolder')}")
        print(f"  İzlenen dosya: {config.get('WATCH', 'WatchFile')}")

        print("\n[OPTIONS]")
        print(f"  Bekleme süresi: {config.get('OPTIONS', 'WaitSeconds')} saniye")
        print(f"  Çift yazdırma önleme: {config.get('OPTIONS', 'PreventDuplicates')}")
        print(f"  Log kayıt: {config.get('OPTIONS', 'EnableLogging')}")
        print(f"  Log dosyası: {config.get('OPTIONS', 'LogFile')}")

        return True
    except Exception as e:
        print(f"Ayarlar okunamadı: {e}")
        return False


def main():
    """Ana fonksiyon"""
    print("=" * 80)
    print("BARKOD YAZDIRMA SERVİSİ KURULUM")
    print("=" * 80)

    # Mevcut ayarları göster
    has_settings = show_current_settings()

    if has_settings:
        print("\n" + "=" * 80)
        print("Yeni ayarlar oluşturmak istiyor musunuz? (E/H):", end=' ')
        choice = input().strip().upper()
        if choice != 'E':
            print("Kurulum iptal edildi.")
            return

    # Yazıcı seç
    printer_name = select_printer()
    if not printer_name:
        print("\nKurulum iptal edildi.")
        return

    # Klasör seç
    watch_folder = select_folder()
    if not watch_folder:
        print("\nKurulum iptal edildi.")
        return

    # Dosya seç
    watch_file = select_watch_file()

    # Özet göster
    print("\n" + "=" * 80)
    print("AYAR ÖZETİ")
    print("=" * 80)
    print(f"Yazıcı: {printer_name}")
    print(f"İzlenen klasör: {watch_folder}")
    print(f"İzlenen dosya: {watch_file}")

    print("\nBu ayarlarla devam edilsin mi? (E/H):", end=' ')
    choice = input().strip().upper()

    if choice == 'E':
        create_settings(printer_name, watch_folder, watch_file)

        print("\n" + "=" * 80)
        print("KURULUM TAMAMLANDI!")
        print("=" * 80)
        print("\nServisi başlatmak için:")
        print("  python barkod_yazdir.py")
        print("\nAyarları değiştirmek için:")
        print(f"  {SETTINGS_FILE} dosyasını düzenleyin")
        print("  veya bu setup.py scriptini tekrar çalıştırın")
        print("=" * 80)
    else:
        print("\nKurulum iptal edildi.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nKurulum iptal edildi.")
    except Exception as e:
        print(f"\nHATA: {e}")
        import traceback
        traceback.print_exc()
