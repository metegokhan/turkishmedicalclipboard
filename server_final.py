import os
import json
import asyncio
import urllib.parse
import win32ui
import win32print
import win32con
import qrcode
import tempfile
from PIL import Image
import win32gui
import pyautogui
import time
import socket
import websockets
from win32com.client import Dispatch
import ctypes
import aiohttp
from aiohttp import web  # Yeni eklenen kütüphane
from datetime import datetime, timedelta
from zeroconf import ServiceInfo, Zeroconf

# --- AYARLAR BAŞLANGIÇ ---
def load_settings():
    settings_file = "ayarlar.json"
    default_settings = {
        "printer_name": "TP806",
        "kurum_adi_recete": "60.05.015 Mevlana ASM",
        "kurum_adi_vital": "MEVLANA ASM",
        "kurum_adi_mamografi": "ERBAA DEVLET HASTANESİ",
        "hekim_mesaji": "Sağlıklı Günler Dileriz",
        "port": 8080,
        "mdns_name": "server15"
    }
    
    if os.path.exists(settings_file):
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                settings = json.load(f)
                # Yeni eklenen ayarlar eski dosyada olmayabilir, varsayılanlari korumak için:
                for k, v in default_settings.items():
                    if k not in settings:
                        settings[k] = v
                return settings
        except Exception as e:
            print(f"Ayarlar okunurken hata oluştu: {e}")
            return default_settings
    else:
        print("\n" + "="*50)
        print("İLK KURULUM - Lütfen kişisel/kurum ayarlarınızı giriniz.")
        print("(Boş bırakıp Enter'a basarsanız varsayılan değer kullanılır)")
        print("="*50)
        
        settings = {}
        
        val = input(f"Yazıcı Adı [{default_settings['printer_name']}]: ").strip()
        settings["printer_name"] = val if val else default_settings["printer_name"]
        
        val = input(f"Kurum/ASM Adı (Reçete için) [{default_settings['kurum_adi_recete']}]: ").strip()
        settings["kurum_adi_recete"] = val if val else default_settings["kurum_adi_recete"]
        
        val = input(f"Kurum/ASM Adı (Vital Bulgular için) [{default_settings['kurum_adi_vital']}]: ").strip()
        settings["kurum_adi_vital"] = val if val else default_settings["kurum_adi_vital"]
        
        val = input(f"Kurum/Hastane Adı (Mamografi için) [{default_settings['kurum_adi_mamografi']}]: ").strip()
        settings["kurum_adi_mamografi"] = val if val else default_settings["kurum_adi_mamografi"]
        
        val = input(f"Hekim/Alt Mesajı [{default_settings['hekim_mesaji']}]: ").strip()
        settings["hekim_mesaji"] = val if val else default_settings["hekim_mesaji"]
        
        val = input(f"Sunucu Portu [{default_settings['port']}]: ").strip()
        settings["port"] = int(val) if val.isdigit() else default_settings["port"]
        
        val = input(f"mDNS Ağ Adı [{default_settings['mdns_name']}]: ").strip()
        settings["mdns_name"] = val if val else default_settings["mdns_name"]
        
        try:
            with open(settings_file, "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=4)
            print("\n✅ Ayarlar 'ayarlar.json' dosyasına başarıyla kaydedildi!")
            print("="*50 + "\n")
        except Exception as e:
            print(f"Ayarlar kaydedilirken hata oluştu: {e}")
            
        return settings

APP_SETTINGS = load_settings()
# --- AYARLAR BİTİŞ ---

global_enabiz_tokens = {}  # TC -> token mapping

# Global değişken tanımı (dosyanın üst kısmına ekleyin)
global_lab_request = {
    "status": False,
    "tc": "",
    "timestamp": None
}

# TC bazlı hasta verilerini saklamak için dosya adı
HASTA_DATA_FILE = "hasta_verileri.json"

# --- TC Bazlı Hasta Veri Yönetimi ---
def load_hasta_verileri():
    """Hasta verilerini JSON dosyasından yükler"""
    try:
        if os.path.exists(HASTA_DATA_FILE):
            with open(HASTA_DATA_FILE, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    return json.loads(content)
        return {}
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"Hasta verileri yükleme hatası: {str(e)}")
        return {}

def save_hasta_verileri(data):
    """Hasta verilerini JSON dosyasına kaydeder"""
    try:
        with open(HASTA_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Hasta verileri kaydetme hatası: {str(e)}")
        return False

def get_or_create_hasta(tc_number):
    """TC numarasına göre hasta kaydını getirir veya yeni bir kayıt oluşturur"""
    hasta_verileri = load_hasta_verileri()
    
    if tc_number not in hasta_verileri:
        # Yeni hasta kaydı oluştur
        hasta_verileri[tc_number] = {
            "tc": tc_number,
            "kisisel_bilgiler": {
                "dogum_tarihi": "",
                "cinsiyet": ""
            },
            "olcumler": {
                "obezite": [],
                "hipertansiyon": []
            },
            "hyp_verileri": {
                "bel_olcumu": "",
                "sigara": "",
                "egzersiz": "",
                "genel_durum": "",
                "son_guncelleme": ""
            },
            "ilk_kayit": datetime.now().isoformat(),
            "son_guncelleme": datetime.now().isoformat()
        }
        save_hasta_verileri(hasta_verileri)
    elif "hyp_verileri" not in hasta_verileri[tc_number]:
        # Mevcut hasta kaydına HYP verilerini ekle (geriye uyumluluk için)
        hasta_verileri[tc_number]["hyp_verileri"] = {
            "bel_olcumu": "",
            "sigara": "",
            "egzersiz": "",
            "genel_durum": "",
            "son_guncelleme": ""
        }
        save_hasta_verileri(hasta_verileri)
    
    return hasta_verileri[tc_number]

def add_obezite_olcum(tc_number, height, weight, waist):
    """TC numarasına obezite ölçümü ekler"""
    try:
        hasta_verileri = load_hasta_verileri()
        hasta = get_or_create_hasta(tc_number)
        
        # BMI hesapla
        height_m = height / 100  # cm'den m'ye çevir
        bmi = round(weight / (height_m ** 2), 2) if height_m > 0 else 0
        
        # Yeni ölçüm verisi
        yeni_olcum = {
            "tarih": datetime.now().isoformat(),
            "boy": height,
            "kilo": weight,
            "bel_cevresi": waist,
            "bmi": bmi,
            "timestamp": datetime.now().timestamp()
        }
        
        # Ölçümü hasta kaydına ekle
        hasta_verileri[tc_number]["olcumler"]["obezite"].append(yeni_olcum)
        hasta_verileri[tc_number]["son_guncelleme"] = datetime.now().isoformat()
        
        # Maksimum 100 ölçüm tut (bellek optimizasyonu)
        if len(hasta_verileri[tc_number]["olcumler"]["obezite"]) > 100:
            hasta_verileri[tc_number]["olcumler"]["obezite"] = hasta_verileri[tc_number]["olcumler"]["obezite"][-100:]
        
        # Kaydet
        if save_hasta_verileri(hasta_verileri):
            return {
                "status": "success",
                "message": "Obezite ölçümü başarıyla kaydedildi",
                "data": yeni_olcum
            }
        else:
            return {"status": "error", "message": "Veri kaydetme hatası"}
            
    except Exception as e:
        print(f"Obezite ölçümü ekleme hatası: {str(e)}")
        return {"status": "error", "message": f"Ölçüm ekleme hatası: {str(e)}"}

def add_hipertansiyon_olcum(tc_number, systolic, diastolic, pulse):
    """TC numarasına hipertansiyon ölçümü ekler"""
    try:
        hasta_verileri = load_hasta_verileri()
        hasta = get_or_create_hasta(tc_number)
        
        # Yeni ölçüm verisi
        yeni_olcum = {
            "tarih": datetime.now().isoformat(),
            "sistolik": systolic,
            "diyastolik": diastolic,
            "nabiz": pulse,
            "timestamp": datetime.now().timestamp()
        }
        
        # Ölçümü hasta kaydına ekle
        hasta_verileri[tc_number]["olcumler"]["hipertansiyon"].append(yeni_olcum)
        hasta_verileri[tc_number]["son_guncelleme"] = datetime.now().isoformat()
        
        # Maksimum 100 ölçüm tut (bellek optimizasyonu)
        if len(hasta_verileri[tc_number]["olcumler"]["hipertansiyon"]) > 100:
            hasta_verileri[tc_number]["olcumler"]["hipertansiyon"] = hasta_verileri[tc_number]["olcumler"]["hipertansiyon"][-100:]
        
        # Kaydet
        if save_hasta_verileri(hasta_verileri):
            return {
                "status": "success",
                "message": "Hipertansiyon ölçümü başarıyla kaydedildi",
                "data": yeni_olcum
            }
        else:
            return {"status": "error", "message": "Veri kaydetme hatası"}
            
    except Exception as e:
        print(f"Hipertansiyon ölçümü ekleme hatası: {str(e)}")
        return {"status": "error", "message": f"Ölçüm ekleme hatası: {str(e)}"}

def search_hasta_by_tc(tc_number):
    """TC numarasına göre hasta verilerini arar"""
    try:
        hasta_verileri = load_hasta_verileri()
        
        if tc_number in hasta_verileri:
            hasta = hasta_verileri[tc_number]
            
            # Ölçümleri tarihe göre sırala
            if hasta["olcumler"]["obezite"]:
                hasta["olcumler"]["obezite"].sort(key=lambda x: x["timestamp"], reverse=True)
            
            if hasta["olcumler"]["hipertansiyon"]:
                hasta["olcumler"]["hipertansiyon"].sort(key=lambda x: x["timestamp"], reverse=True)
            
            return {
                "status": "success",
                "data": hasta,
                "message": f"TC {tc_number} için veri bulundu"
            }
        else:
            return {
                "status": "error",
                "message": f"TC {tc_number} için veri bulunamadı"
            }
            
    except Exception as e:
        print(f"TC arama hatası: {str(e)}")
        return {"status": "error", "message": f"Arama hatası: {str(e)}"}

def get_hasta_statistics():
    """Genel hasta istatistiklerini döndürür"""
    try:
        hasta_verileri = load_hasta_verileri()
        
        toplam_hasta = len(hasta_verileri)
        toplam_obezite_olcum = sum(len(hasta["olcumler"]["obezite"]) for hasta in hasta_verileri.values())
        toplam_ht_olcum = sum(len(hasta["olcumler"]["hipertansiyon"]) for hasta in hasta_verileri.values())
        
        return {
            "status": "success",
            "data": {
                "toplam_hasta": toplam_hasta,
                "toplam_obezite_olcum": toplam_obezite_olcum,
                "toplam_hipertansiyon_olcum": toplam_ht_olcum,
                "son_guncelleme": datetime.now().isoformat()
            }
        }
        
    except Exception as e:
        print(f"İstatistik alma hatası: {str(e)}")
        return {"status": "error", "message": f"İstatistik hatası: {str(e)}"}

def add_hyp_verileri(tc_number, bel_olcumu, sigara, egzersiz, genel_durum):
    """TC numarasına HYP verilerini ekler/günceller"""
    try:
        hasta_verileri = load_hasta_verileri()
        hasta = get_or_create_hasta(tc_number)
        
        # HYP verilerini güncelle
        hasta_verileri[tc_number]["hyp_verileri"] = {
            "bel_olcumu": bel_olcumu,
            "sigara": sigara,
            "egzersiz": egzersiz,
            "genel_durum": genel_durum,
            "son_guncelleme": datetime.now().isoformat()
        }
        
        hasta_verileri[tc_number]["son_guncelleme"] = datetime.now().isoformat()
        
        # Kaydet
        if save_hasta_verileri(hasta_verileri):
            return {
                "status": "success",
                "message": "HYP verileri başarıyla kaydedildi",
                "data": hasta_verileri[tc_number]["hyp_verileri"]
            }
        else:
            return {"status": "error", "message": "Veri kaydetme hatası"}
            
    except Exception as e:
        print(f"HYP verileri ekleme hatası: {str(e)}")
        return {"status": "error", "message": f"HYP veri ekleme hatası: {str(e)}"}
# Windows bildirim sistemi için alternatif yöntem
class Notifier:
    def __init__(self):
        self.wscript = Dispatch("WScript.Shell")

    def show_notification(self, title, message, duration=5):
        """
        Windows bildirim balonu gösterir

        Args:
            title: Bildirim başlığı
            message: Bildirim mesajı
            duration: Gösterim süresi (saniye)
        """
        try:
            # Bildirim balonunu göster (WScript.Shell ile)
            self.wscript.Popup(message, duration, title, 64)

            # Log mesajı
            print(f"Bildirim gösterildi: {title} - {message}")
            return True
        except Exception as e:
            print(f"Bildirim gösterilirken hata oluştu: {e}")
            return False

    def show_message_box(self, title, message):
        """
        MessageBox kullanarak bildirim gösterir

        Args:
            title: Bildirim başlığı
            message: Bildirim mesajı
        """
        try:
            ctypes.windll.user32.MessageBoxW(0, message, title, 0)
            return True
        except Exception as e:
            print(f"MessageBox gösterilirken hata oluştu: {e}")
            return False


# Notifier sınıfını oluştur
notifier = Notifier()


# IP adresini almak için fonksiyon
def get_ip_address():
    """
    Cihazın IP adresini döndürür.
    """
    try:
        # Socket bağlantısı oluşturarak IP adresini alma
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception as e:
        print(f"IP adresi alınırken hata oluştu: {e}")
        return "127.0.0.1"  # Hata durumunda localhost döndür


def register_mdns_service(service_name, port, ip_address):
    """
    mDNS servisi kaydeder
    """
    try:
        # Zeroconf instance oluştur
        zeroconf = Zeroconf()

        # IP adresini byte array'e çevir
        ip_parts = ip_address.split('.')
        addresses = [socket.inet_aton(ip_address)]

        # Servis bilgilerini oluştur
        service_type = "_http._tcp.local."
        service_full_name = f"{service_name}.{service_type}"

        info = ServiceInfo(
            service_type,
            service_full_name,
            port=port,
            addresses=addresses,
            properties={
                'path': '/',
                'description': 'Medical Server'
            },
            server=f"{service_name}.local."
        )

        # Servisi kaydet
        zeroconf.register_service(info)
        print(f"mDNS servisi kaydedildi: {service_name}.local ({ip_address}:{port})")

        return zeroconf, info
    except Exception as e:
        print(f"mDNS servisi kaydedilirken hata oluştu: {e}")
        return None, None


def get_tani_ilac_bulgu_info():
    """
    Açık pencereler arasında başlığı "Tanı - İlaç - Bulgu |" ile başlayanı arar.
    Bulunursa, pencerenin ikinci kısmından ad soyad ve TC bilgilerini (ilk token olarak TC) ayrıştırır.
    """
    titles = []

    def enumHandler(hwnd, lParam):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title.startswith("Tanı - İlaç - Bulgu |"):
                lParam.append(title)
        return True  # Her zaman True döndür

    win32gui.EnumWindows(enumHandler, titles)
    if titles:
        # İlk bulunan pencereyi kullanıyoruz
        title = titles[0]
        parts = title.split("|")
        if len(parts) >= 2:
            info_str = parts[1].strip()
            subparts = info_str.split("-")
            if len(subparts) >= 2:
                name = subparts[0].strip()
                tc = subparts[1].strip().split()[0]  # İlk token TC numarası olarak alınıyor
                return tc, name
    return None


def simulate_alt_tab():
    pyautogui.keyDown('alt')
    pyautogui.press('tab')
    pyautogui.keyUp('alt')
    print("Alt+Tab simüle edildi.")


async def process_ilac_ekle(params):
    try:
        # Parametreleri al
        numara = params.get('numara', '')
        tc = params.get('tc', '')
        p = params.get('p', '')
        ptime = params.get('ptime', '')
        times = params.get('times', '')
        dose = params.get('dose', '')
        usage = params.get('usage', '')

        if not tc or not numara:
            return {"status": "error", "message": "TC ve numara parametreleri gereklidir"}

        # İlaç bilgilerini data/ilaclar.json'dan al
        ilac_adi = ""
        atc_code = ""
        atc_name = ""

        try:
            if os.path.exists("data/ilaclar.json"):
                with open("data/ilaclar.json", 'r', encoding='utf-8') as f:
                    ilaclar = json.load(f)

                # Numara (barcode) ile ilaç ara
                for ilac in ilaclar:
                    if str(ilac.get("barcode", "")) == str(numara):
                        ilac_adi = ilac.get("name", "")
                        atc_code = ilac.get("atc_code", "").strip()
                        atc_name = ilac.get("atc_name", "")
                        break
        except Exception as e:
            print(f"İlaç bilgisi okuma hatası: {str(e)}")

        # ICD-10 kodlarını ATC kodundan al
        icd_codes = []
        icd_descriptions = []

        if atc_code:
            print(f"DEBUG: ATC kodu bulundu: {atc_code}")
            try:
                # ATC-ICD mapping'den ICD kodlarını al
                if os.path.exists("data/atc_icd_mapping.json"):
                    print("DEBUG: atc_icd_mapping.json dosyası bulundu")
                    with open("data/atc_icd_mapping.json", 'r', encoding='utf-8') as f:
                        atc_icd_mapping = json.load(f)

                    print(f"DEBUG: Mapping dosyası yüklendi, toplam anahtar sayısı: {len(atc_icd_mapping)}")

                    # atc_to_icd içinden ATC kodu ile eşleşen ICD kodlarını bul
                    atc_to_icd = atc_icd_mapping.get("atc_to_icd", {})
                    print(f"DEBUG: atc_to_icd içinde {len(atc_to_icd)} anahtar var")

                    mapped_icds = []

                    # Tam eşleşme ara
                    print(f"DEBUG: Tam eşleşme arıyor: {atc_code}")
                    if atc_code in atc_to_icd:
                        mapped_icds = atc_to_icd[atc_code]
                        print(f"DEBUG: Tam eşleşme bulundu: {mapped_icds}")
                    else:
                        print("DEBUG: Tam eşleşme bulunamadı, wildcard arıyor")
                        # Wildcard eşleşme ara - farklı uzunluklarda dene
                        for i in range(1, len(atc_code) + 1):
                            atc_prefix = atc_code[:i]
                            wildcard_key = atc_prefix + "*"
                            print(f"DEBUG: Wildcard deneniyor: {wildcard_key}")
                            if wildcard_key in atc_to_icd:
                                mapped_icds = atc_to_icd[wildcard_key]
                                print(f"DEBUG: Wildcard eşleşme bulundu: {wildcard_key} -> {mapped_icds}")
                                break

                        # Eğer hala bulunamadıysa, mevcut anahtarları listele
                        if not mapped_icds:
                            print("DEBUG: Hiçbir eşleşme bulunamadı. Mevcut anahtarlar:")
                            for key in list(atc_to_icd.keys())[:10]:  # İlk 10 anahtarı göster
                                print(f"  {key}")
                            if len(atc_to_icd) > 10:
                                print(f"  ... ve {len(atc_to_icd) - 10} tane daha")

                    if mapped_icds:
                        print(f"DEBUG: ICD kodları bulundu: {mapped_icds}")
                        # ICD açıklamalarını icd10turk.json'dan al
                        if os.path.exists("data/icd10turk.json"):
                            print("DEBUG: icd10turk.json dosyası bulundu")
                            with open("data/icd10turk.json", 'r', encoding='utf-8') as f:
                                icd10_data = json.load(f)

                            print(f"DEBUG: ICD10 dosyası yüklendi, {len(icd10_data)} kayıt var")

                            for icd_code in mapped_icds:
                                icd_codes.append(icd_code)
                                # ICD açıklamasını bul
                                icd_description = ""
                                print(f"DEBUG: {icd_code} için açıklama arıyor")
                                for icd_item in icd10_data:
                                    if icd_item.get("ICD KODU", "") == icd_code:
                                        icd_description = icd_item.get("TANI", "")
                                        print(f"DEBUG: {icd_code} için açıklama bulundu: {icd_description}")
                                        break

                                if not icd_description:
                                    # İlk birkaç kayıtı kontrol et
                                    print(f"DEBUG: {icd_code} için açıklama bulunamadı. İlk birkaç kayıt:")
                                    for i, item in enumerate(icd10_data[:5]):
                                        print(f"  {i}: {item}")

                                icd_descriptions.append(icd_description if icd_description else "Açıklama bulunamadı")
                        else:
                            print("DEBUG: icd10turk.json dosyası bulunamadı")
                            # icd10turk.json yoksa sadece kodları ekle
                            icd_codes = mapped_icds
                            icd_descriptions = ["Açıklama dosyası bulunamadı"] * len(mapped_icds)
                    else:
                        print("DEBUG: Hiçbir ICD kodu bulunamadı")
                else:
                    print("DEBUG: atc_icd_mapping.json dosyası bulunamadı")
            except Exception as e:
                print(f"ICD mapping okuma hatası: {str(e)}")
                import traceback
                traceback.print_exc()
        else:
            print("DEBUG: ATC kodu boş")

        # Reçeteler dosyası
        receteler_dosya = "ilac_receteler.json"

        # Mevcut reçeteleri oku
        receteler = {}
        if os.path.exists(receteler_dosya):
            try:
                with open(receteler_dosya, 'r', encoding='utf-8') as f:
                    receteler = json.load(f)
            except json.JSONDecodeError:
                receteler = {}

        # TC için reçete geçmişini kontrol et
        if tc not in receteler:
            receteler[tc] = []

        # Son reçete kontrolü (5 dakika kuralı)
        current_time = datetime.now()
        son_recete_indeks = None

        if receteler[tc]:
            # En son reçeteyi kontrol et
            son_recete = receteler[tc][-1]
            son_recete_zamani = datetime.fromisoformat(son_recete['timestamp'])

            # 5 dakika geçmemişse aynı reçeteye ekle
            if current_time - son_recete_zamani <= timedelta(minutes=5):
                son_recete_indeks = len(receteler[tc]) - 1

        # Yeni ilaç bilgisi (genişletilmiş)
        yeni_ilac = {
            "numara": numara,
            "ilac_adi": ilac_adi,
            "atc_code": atc_code,
            "atc_name": atc_name,
            "icd_codes": icd_codes,
            "icd_descriptions": icd_descriptions,
            "p": p,
            "ptime": ptime,
            "times": times,
            "dose": dose,
            "usage": usage,
            "ekleme_zamani": current_time.isoformat()
        }

        if son_recete_indeks is not None:
            # Mevcut reçeteye ilaç ekle
            receteler[tc][son_recete_indeks]['ilaclar'].append(yeni_ilac)
            receteler[tc][son_recete_indeks]['guncelleme_zamani'] = current_time.isoformat()
            mesaj = f"İlaç mevcut reçeteye eklendi (Reçete {son_recete_indeks + 1})"
        else:
            # Yeni reçete oluştur
            # Maksimum 3 reçete kuralını kontrol et
            if len(receteler[tc]) >= 3:
                # En eski reçeteyi sil
                receteler[tc].pop(0)

            yeni_recete = {
                "recete_no": len(receteler[tc]) + 1,
                "timestamp": current_time.isoformat(),
                "guncelleme_zamani": current_time.isoformat(),
                "ilaclar": [yeni_ilac]
            }
            receteler[tc].append(yeni_recete)
            mesaj = f"Yeni reçete oluşturuldu (Reçete {len(receteler[tc])})"

        # Dosyaya kaydet
        with open(receteler_dosya, 'w', encoding='utf-8') as f:
            json.dump(receteler, f, ensure_ascii=False, indent=2)

        # Detaylı log mesajı
        print(f"İlaç eklendi: TC={tc}, Numara={numara}")
        print(f"İlaç Adı: {ilac_adi}")
        print(f"ATC Kodu: {atc_code} - {atc_name}")
        if icd_codes:
            print("ICD-10 Kodları:")
            for i, (icd_code, icd_desc) in enumerate(zip(icd_codes, icd_descriptions)):
                print(f"  {icd_code} - {icd_desc}")
        print(f"Mesaj: {mesaj}")

        return {
            "status": "success",
            "message": mesaj,
            "tc": tc,
            "ilac_adi": ilac_adi,
            "atc_code": atc_code,
            "icd_codes": icd_codes,
            "toplam_recete": len(receteler[tc]),
            "son_recete_ilac_sayisi": len(receteler[tc][-1]['ilaclar'])
        }

    except Exception as e:
        print(f"İlaç ekleme hatası: {str(e)}")
        return {"status": "error", "message": f"İlaç ekleme hatası: {str(e)}"}


# Reçeteleri görüntülemek için güncellenmiş fonksiyon
async def get_ilac_receteler_formatted(tc=None):
    """TC'ye göre reçeteleri formatlanmış şekilde getir"""
    try:
        receteler_dosya = "ilac_receteler.json"

        if not os.path.exists(receteler_dosya):
            return {"status": "success", "data": "", "message": "Reçete dosyası bulunamadı"}

        with open(receteler_dosya, 'r', encoding='utf-8') as f:
            receteler = json.load(f)

        if tc and tc in receteler:
            # Belirli TC için formatlanmış reçeteleri oluştur
            formatted_output = f"=== TC: {tc} REÇETELERİ ===\n\n"

            for i, recete in enumerate(receteler[tc], 1):
                formatted_output += f"REÇETE {i}\n"
                formatted_output += f"Tarih: {recete['timestamp'][:19]}\n"
                formatted_output += "-" * 50 + "\n"

                for j, ilac in enumerate(recete['ilaclar'], 1):
                    formatted_output += f"{j}. {ilac['numara']} - {ilac.get('ilac_adi', 'İlaç adı bulunamadı')}\n"
                    formatted_output += f"   Kullanım: {ilac.get('dose', '')} {ilac.get('times', '')} {ilac.get('usage', '')}\n"

                    if ilac.get('atc_code'):
                        formatted_output += f"   ATC: {ilac['atc_code']} - {ilac.get('atc_name', '')}\n"

                    if ilac.get('icd_codes'):
                        for icd_code, icd_desc in zip(ilac['icd_codes'], ilac.get('icd_descriptions', [])):
                            formatted_output += f"   ICD-10: {icd_code} - {icd_desc}\n"

                    formatted_output += "\n"

                formatted_output += "=" * 50 + "\n\n"

            return {
                "status": "success",
                "data": formatted_output,
                "message": f"TC {tc} için {len(receteler[tc])} reçete formatlandı"
            }
        else:
            return {
                "status": "error",
                "message": f"TC {tc} için reçete bulunamadı"
            }

    except Exception as e:
        print(f"Reçete formatlama hatası: {str(e)}")
        return {"status": "error", "message": f"Reçete formatlama hatası: {str(e)}"}

async def get_ilac_receteler(tc=None):
    """TC'ye göre reçeteleri getir veya tüm reçeteleri listele"""
    try:
        receteler_dosya = "ilac_receteler.json"

        if not os.path.exists(receteler_dosya):
            return {"status": "success", "data": {}, "message": "Reçete dosyası bulunamadı"}

        with open(receteler_dosya, 'r', encoding='utf-8') as f:
            receteler = json.load(f)

        if tc:
            # Belirli TC için reçeteleri getir
            tc_receteler = receteler.get(tc, [])
            return {
                "status": "success",
                "data": {tc: tc_receteler},
                "message": f"TC {tc} için {len(tc_receteler)} reçete bulundu"
            }
        else:
            # Tüm reçeteleri getir
            return {
                "status": "success",
                "data": receteler,
                "message": f"Toplam {len(receteler)} TC için reçete bulundu"
            }

    except Exception as e:
        print(f"Reçete okuma hatası: {str(e)}")
        return {"status": "error", "message": f"Reçete okuma hatası: {str(e)}"}


# HTTP handler fonksiyonu
async def handle_ilac_ekle(request):
    """HTTP GET isteği ile ilaç ekleme"""
    try:
        # Query parametrelerini al
        params = {
            'numara': request.query.get('numara', ''),
            'tc': request.query.get('tc', ''),
            'p': request.query.get('p', ''),
            'ptime': request.query.get('ptime', ''),
            'times': request.query.get('times', ''),
            'dose': request.query.get('dose', ''),
            'usage': request.query.get('usage', '')
        }

        # İlacı ekle
        result = await process_ilac_ekle(params)

        # JSON yanıt döndür
        return web.json_response(result)

    except Exception as e:
        return web.json_response({
            "status": "error",
            "message": f"HTTP isteği işlenirken hata: {str(e)}"
        }, status=500)


async def handle_get_receteler(request):
    """Reçeteleri getir"""
    try:
        tc = request.query.get('tc', None)
        result = await get_ilac_receteler(tc)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({
            "status": "error",
            "message": f"Reçete getirme hatası: {str(e)}"
        }, status=500)

def minimize_current_window():
    """
    Mevcut aktif pencereyi minimize eder.
    """
    try:
        # Aktif pencerenin handle'ını al
        hwnd = win32gui.GetForegroundWindow()

        # Pencereyi minimize et
        win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)

        print("Mevcut pencere minimize edildi.")
        return True
    except Exception as e:
        print(f"Pencere minimize edilirken hata oluştu: {e}")
        return False


def silence_event_loop_closed(loop):
    """Windows'ta ProactorEventLoop kapanırken oluşan hataları yakalar"""
    # Mevcut exception handler'ı al
    old_handler = loop.get_exception_handler()

    def ignore_socket_exception(loop, context):
        # Soket kapatma hatalarını görmezden gel
        exception = context.get('exception')
        if isinstance(exception, ConnectionResetError) and "call_connection_lost" in str(context.get('message', '')):
            return  # Bu hatayı sessizce geç
        if isinstance(exception, ConnectionAbortedError):
            return  # Bu hatayı da sessizce geç

        # Diğer hataları eskisi gibi işle
        if old_handler is not None:
            old_handler(loop, context)
        else:
            loop.default_exception_handler(context)

    # Yeni exception handler'ı ayarla
    loop.set_exception_handler(ignore_socket_exception)
def print_text_and_qr(text_lines, qr_data1, qr_data2=None):
    printer_name = win32print.GetDefaultPrinter()
    # Ayarlardan gelen yazıcı adını kullan
    printer_name = APP_SETTINGS.get("printer_name", "TP806")
    device_handle = win32print.OpenPrinter(printer_name)
    attributes = win32print.GetPrinter(device_handle, 2)
    win32print.ClosePrinter(device_handle)

    dc = win32ui.CreateDC()
    dc.CreatePrinterDC(printer_name)

    dpi_x = dc.GetDeviceCaps(win32con.LOGPIXELSX)
    dpi_y = dc.GetDeviceCaps(win32con.LOGPIXELSY)
    width = dc.GetDeviceCaps(win32con.PHYSICALWIDTH)
    height = dc.GetDeviceCaps(win32con.PHYSICALHEIGHT)

    left_margin = int(dpi_x * 0)
    top_margin = int(dpi_y * 0)
    line_height = int(dpi_y * 0.15)

    temp_path = None
    try:
        dc.StartDoc('QR Kod Yazdırma')
        dc.StartPage()

        # Yazı için font ayarları
        normal_font = win32ui.CreateFont({
            'name': 'Arial',
            'height': int(dpi_y / 8 * 1.5),
            'weight': 400
        })
        bold_small_font = win32ui.CreateFont({
            'name': 'Arial',
            'height': int(dpi_y / 10 * 1.5),
            'weight': 700,
            'italic': True,
            'underline': True
        })

        # Metin satırlarını yazdırma
        dc.SelectObject(normal_font)
        y = top_margin
        for line in text_lines[:-2]:
            dc.TextOut(left_margin, y, line)
            y += line_height

        dc.SelectObject(bold_small_font)
        for line in text_lines[-2:]:
            dc.TextOut(left_margin, y, line)
            y += line_height

        # İlk QR kodu (örneğin, TC bilgisi) oluşturma ve yazdırma
        qr1 = qrcode.QRCode(version=1, box_size=4, border=4)
        qr1.add_data(qr_data1)
        qr1.make(fit=True)
        qr1_image = qr1.make_image(fill_color="black", back_color="white")

        temp_path = os.path.join(tempfile.gettempdir(), 'temp_qr.bmp')
        qr1_image.save(temp_path, 'BMP')

        bitmap = win32gui.LoadImage(
            0, temp_path, win32con.IMAGE_BITMAP,
            0, 0, win32con.LR_LOADFROMFILE
        )
        if bitmap is None:
            raise Exception("QR kod bitmap'i yüklenemedi (ilk QR).")

        mem_dc = dc.CreateCompatibleDC()
        mem_dc.SelectObject(win32ui.CreateBitmapFromHandle(bitmap))

        qr_size = int(dpi_x * 1)
        qr_x = int(width * 0.5)
        qr_y = top_margin + line_height

        dc.BitBlt((qr_x, qr_y), (qr_size, qr_size), mem_dc, (0, 0), win32con.SRCCOPY)

        mem_dc.DeleteDC()
        win32gui.DeleteObject(bitmap)

        # İkinci QR kodu (boy ve kilo) varsa, ilk QR kodun altına yazdırma
        if qr_data2:
            qr2 = qrcode.QRCode(version=1, box_size=4, border=4)
            qr2.add_data(qr_data2)
            qr2.make(fit=True)
            qr2_image = qr2.make_image(fill_color="black", back_color="white")

            temp_path2 = os.path.join(tempfile.gettempdir(), 'temp_qr2.bmp')
            qr2_image.save(temp_path2, 'BMP')

            bitmap2 = win32gui.LoadImage(
                0, temp_path2, win32con.IMAGE_BITMAP,
                0, 0, win32con.LR_LOADFROMFILE
            )
            if bitmap2 is None:
                raise Exception("QR kod bitmap'i yüklenemedi (ikinci QR).")

            mem_dc2 = dc.CreateCompatibleDC()
            mem_dc2.SelectObject(win32ui.CreateBitmapFromHandle(bitmap2))

            # İkinci QR kod, ilk QR kodun altına (bir satır boşluk bırakacak şekilde) yerleştiriliyor.
            qr2_x = qr_x
            qr2_y = qr_y + qr_size + line_height
            dc.BitBlt((qr2_x, qr2_y), (qr_size, qr_size), mem_dc2, (0, 0), win32con.SRCCOPY)

            mem_dc2.DeleteDC()
            win32gui.DeleteObject(bitmap2)
            if os.path.exists(temp_path2):
                os.remove(temp_path2)

        dc.EndPage()
        dc.EndDoc()
        print("Yazdırma başarılı!")

    except Exception as e:
        print(f"Yazdırma hatası: {e}")
        if dc:
            dc.AbortDoc()
    finally:
        if dc:
            dc.DeleteDC()
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

# WebSocket üzerinden gelen mesajları işleme
# Mevcut process_recete fonksiyonunu şu şekilde güncelleyelim:
async def process_recete(params):
    try:
        # Reçete bilgilerini hazırla
        tc = params.get('tc', '**********')  # Maskelenmiş TC
        original_tc = params.get('originalTc', '')  # Orjinal TC'yi al
        if original_tc.isdigit() and len(original_tc) == 11:
            tc = '*' * 7 + original_tc[-4:]
        else:
            tc = tc
        ad_soyad = f"{params.get('ad', '')} {params.get('soyad', '')}"
        recete_kodu = params.get('recetekodu', '')
        result_id = params.get('resultId', '')

        # Bugünün tarihini GGAAYY formatında al
        from datetime import datetime
        tarih_kodu = datetime.now().strftime('%d%m%y')

        # Reçete bilgilerini dosyaya kaydet (TC ile arama yapabilmek için)
        recete_data = {
            "tc": tc,
            "original_tc": original_tc,  # Orjinal TC'yi JSON'a ekle
            "ad_soyad": ad_soyad,
            "recete_kodu": recete_kodu,
            "result_id": result_id,
            "tarih": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        # Dosya adı için tarih kodunu kullan
        dosya_adi = f"receteler_{tarih_kodu}.json"

        # Mevcut dosyayı oku veya yeni bir dosya oluştur
        import os
        import json

        receteler = []
        if os.path.exists(dosya_adi):
            try:
                with open(dosya_adi, 'r', encoding='utf-8') as f:
                    receteler = json.load(f)
            except json.JSONDecodeError:
                # Dosya boşsa veya geçersiz JSON içeriyorsa, yeni bir liste başlat
                receteler = []

        # Yeni reçete verisini ekle
        receteler.append(recete_data)

        # Dosyaya kaydet
        with open(dosya_adi, 'w', encoding='utf-8') as f:
            json.dump(receteler, f, ensure_ascii=False, indent=2)

        print(f"Reçete bilgisi kaydedildi: {dosya_adi} - TC: {tc}, Original TC: {original_tc}, ResultID: {result_id}")

        baslik = APP_SETTINGS.get("kurum_adi_recete", "60.05.015 Mevlana ASM")
        text_lines = [
            f"   {baslik}",
            "   ---------------------",
            "   e-REÇETE",
            "                        ",
            f"  TC: {tc}",
            f"  Reçete Kodu: {recete_kodu}",
            #f"  Ad Soyad: {ad_soyad}",
            "   ---------------------"
        ]

        # QR kod için reçete kodunu kullan
        qr_data = recete_kodu

        # Yazdırma işlemini başlat
        # simulate_alt_tab()
        minimize_current_window()
        print_text_and_qr(text_lines, qr_data)

        # Terminale çıktı ver
        print(f"Reçete yazdırıldı: {ad_soyad} - {recete_kodu}")

        # Kullanıcıya bildirim göster
        '''
        notifier.show_notification(
            "Reçete İşlemi",
            f"Reçete yazdırıldı ve kaydedildi: {tc}",
            duration=1
        )
        '''
        return {"status": "success", "message": "Reçete yazdırıldı ve kaydedildi"}
    except Exception as e:
        print(f"Reçete işleme hatası: {str(e)}")
        return {"status": "error", "message": f"Yazdırma hatası: {str(e)}"}

# TC numarasına göre result ID'yi arayan yeni bir fonksiyon ekleyelim
async def search_result_id_by_tc(tc):
    try:
        import os
        import json
        from datetime import datetime

        # Son 7 günün dosyalarını kontrol et
        bulunan_sonuclar = []
        for i in range(7):  # Son 7 gün için
            from datetime import timedelta
            tarih = datetime.now() - timedelta(days=i)
            tarih_kodu = tarih.strftime('%d%m%y')
            dosya_adi = f"receteler_{tarih_kodu}.json"

            if os.path.exists(dosya_adi):
                try:
                    with open(dosya_adi, 'r', encoding='utf-8') as f:
                        receteler = json.load(f)

                    # TC numarasına göre filtrele
                    for recete in receteler:
                        if recete.get("tc") == tc:
                            bulunan_sonuclar.append({
                                "tarih": recete.get("tarih"),
                                "result_id": recete.get("result_id"),
                                "recete_kodu": recete.get("recete_kodu")
                            })
                except Exception as e:
                    print(f"Dosya okuma hatası ({dosya_adi}): {str(e)}")

        return {"status": "success", "results": bulunan_sonuclar}
    except Exception as e:
        return {"status": "error", "message": f"Arama hatası: {str(e)}"}

async def process_vitaller(params):
    try:
        post_tc = params.get("tc", "").strip()
        sistolik = params.get("sistolik", "")
        diyastolik = params.get("diyastolik", "")
        nabiz = params.get("nabiz", "")
        boy = params.get("boy", "")
        kilo = params.get("kilo", "")
        bel = params.get("bel", "")

        vitaller = (
            f"TC: {post_tc}\nSistolik: {sistolik}\nDiyastolik: {diyastolik}\nNabız: {nabiz}\n"
            f"Boy: {boy}\nKilo: {kilo}\nBel Çevresi: {bel}\n"
            "------------------------\n"
        )
        with open("vitaller.txt", "a", encoding="utf-8") as f:
            f.write(vitaller)

        text_lines = [
            f"TC: {post_tc}",
            "",
            f"Sistolik: {sistolik}                      mmHg",
            "",
            f"Diyastolik: {diyastolik}                  mmHg",
            "",
            f"Nabız: {nabiz}                            bpm",
            "",
            f"Boy: {boy} cm",
            f"Kilo: {kilo} kg",
            f"Bel Çevresi: {bel}                        cm",
            "",
            "VİTAL BULGULAR RAPORU",
            APP_SETTINGS.get("kurum_adi_vital", "MEVLANA ASM"),
            APP_SETTINGS.get("hekim_mesaji", "Sağlıklı Günler Dileriz")
        ]
        qr_data1 = post_tc  # İlk QR kod: tc bilgisi
        # İkinci QR kod: Boy ve Kilo bilgilerini içerecek şekilde oluşturuluyor
        qr_data2 = f"{boy},{kilo}"

        tanila_info = get_tani_ilac_bulgu_info()
        if tanila_info:
            extracted_tc, extracted_name = tanila_info
            print("Tanı - İlaç - Bulgu bilgileri bulundu:", extracted_tc, extracted_name)
            if post_tc == "":
                post_tc = extracted_tc
            text_lines[0] = f"TC: {post_tc}"
            text_lines.insert(1, f"Ad Soyad: {extracted_name}")
            qr_data1 = post_tc
            # Yazdırma işlemi: İki QR kod bilgisi gönderiliyor.
            print_text_and_qr(text_lines, qr_data1, qr_data2)

            # Yeni bildirim sistemini kullan

            notifier.show_notification(
                "Vital Bulgular",
                f"TC: {post_tc}, Boy:{boy}, Kilo:{kilo}, vital bulgular yazdırıldı.",
                duration=10
            )
        else:
            print("Tanı - İlaç - Bulgu penceresi bulunamadı. Yazdırma işlemi iptal edildi.")
            # Yeni bildirim sistemini kullan
            notifier.show_notification(
                "Vital Bulgular",
                f"Boy:{boy}, Kilo:{kilo}",
                duration=15
            )

        return {"status": "success", "message": "Vitaller işlendi"}
    except Exception as e:
        print("Vitaller endpoint error:", str(e))
        return {"status": "error", "message": f"Yazdırma hatası: {str(e)}"}


async def process_mamografi(params):
    try:
        # Mamografi kaydını dosyaya yaz
        mamografi = f"Ad-Soyad: {params.get('adsoyad', '')}\n"
        mamografi += f"TC: {params.get('tc', '')}\n"
        mamografi += f"Tarih: {params.get('tarih', '')}\n"
        mamografi += f"Saat: {params.get('saat', '')}\n"
        mamografi += "------------------------\n"

        with open("mamografi.txt", "a", encoding="utf-8") as f:
            f.write(mamografi)

        # Yazdırılacak metni hazırla
        text_lines = [
            f"{params.get('adsoyad', '')}",
            f"TC: {params.get('tc', '')}",
            f"Tarih: {params.get('tarih', '')}",
            f"Saat: {params.get('saat', '')}",
            "",
            "ULUSAL MAMOGRAFİ TARAMASI",
            "MAMOGRAFİ RANDEVUSU",
            APP_SETTINGS.get("kurum_adi_mamografi", "ERBAA DEVLET HASTANESİ")
        ]

        # QR kod için TC'yi kullan
        qr_data = params.get('tc', '')

        # Yazdırma işlemini başlat
        print_text_and_qr(text_lines, qr_data)
        return {"status": "success", "message": "Mamografi randevusu yazdırıldı"}
    except Exception as e:
        return {"status": "error", "message": f"Yazdırma hatası: {str(e)}"}


async def process_run(params):
    ahk_script = params.get("ahk", "")
    if ahk_script:
        print(f"AHK komutu çalıştırılacak: {ahk_script}")
    return {"status": "success", "message": "AHK çalıştırıldı"}


async def process_print(params):
    satir1 = params.get("satir1", "")
    satir2 = params.get("satir2", "")
    with open("print.txt", "a", encoding="utf-8") as f:
        f.write(satir1 + "\n" + satir2 + "\n")
    return {"status": "success", "message": "Yazdırıldı"}


async def process_mesaj(params):
    print("Mesaj:", params.get("mesaj", ""))
    return {"status": "success", "message": "OK"}


async def get_mamografi():
    if os.path.exists("mamografi.txt"):
        with open("mamografi.txt", "r", encoding="utf-8") as f:
            content = f.read()
        return {"status": "success", "data": content}
    else:
        return {"status": "success", "data": "Kayıt bulunamadı"}

async def process_meliscs(params):
    try:
        # Melis verilerini JSON olarak kaydet
        from datetime import datetime

        melis_data = {
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "data": params
        }



        melis_veriler = []
        if os.path.exists("melis.json"):
            try:
                with open("melis.json", 'r', encoding='utf-8') as f:
                    melis_veriler = json.load(f)
            except json.JSONDecodeError:
                # Dosya boşsa veya geçersiz JSON içeriyorsa, yeni bir liste başlat
                melis_veriler = []

        # Yeni melis verisini ekle
        melis_veriler.append(melis_data)

        # Dosyaya kaydet
        with open("melis.json", 'w', encoding='utf-8') as f:
            json.dump(melis_veriler, f, ensure_ascii=False, indent=2)

        print(f"Melis CS verisi kaydedildi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Kullanıcıya bildirim göster
        """ 
        notifier.show_notification(
            "Melis CS Verisi",
            "Melis verisi başarıyla kaydedildi",
            duration=1
        )
        """
        return {"status": "success", "message": "Melis CS verisi kaydedildi"}
    except Exception as e:
        print(f"Melis veri kayıt hatası: {str(e)}")
        return {"status": "error", "message": f"Kayıt hatası: {str(e)}"}

async def get_csmelis():
    try:
        if os.path.exists("melis.json"):
            with open("melis.json", "r", encoding="utf-8") as f:
                melis_veriler = json.load(f)
                return {"status": "success", "data": melis_veriler}
        else:
            return {"status": "success", "data": [], "message": "Melis verisi bulunamadı"}
    except Exception as e:
        print(f"Melis veri okuma hatası: {str(e)}")
        return {"status": "error", "message": f"Veri okuma hatası: {str(e)}"}


# Asenkron HTTP POST isteği gönderen fonksiyon
async def post_tc_to_melis(tc_no, cs_value):
    try:
        # İstek URL'i
        url = f"https://melis.saglik.gov.tr/TetkikSonuc/AraTCKimlikNoGecmis?cs={cs_value}"

        # Form verilerini hazırla
        form_data = {
            "TCKimlikNo": tc_no,
            "GecmisVizitSorgula": "Sorgula"
        }

        # Headers
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": url,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
        }

        # Asenkron HTTP isteği gönder
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=form_data, headers=headers, allow_redirects=True) as response:
                if response.status == 200:
                    # Yanıtı metin olarak al
                    response_text = await response.text()
                    print(f"POST isteği başarılı: {response.status}")

                    return {
                        "status": "success",
                        "message": f"TC numarası {tc_no} için sorgu yapıldı",
                        "html_content": response_text
                    }
                else:
                    print(f"POST isteği başarısız, durum kodu: {response.status}")
                    return {"status": "error", "message": f"POST isteği başarısız: {response.status}"}
    except Exception as e:
        print(f"POST isteği gönderilirken hata oluştu: {str(e)}")
        return {"status": "error", "message": f"Hata: {str(e)}"}


async def get_latest_cs_value():
    try:
        if os.path.exists("melis.json"):
            with open("melis.json", "r", encoding="utf-8") as f:
                melis_veriler = json.load(f)

            # En son eklenen CS değerini al
            if melis_veriler and len(melis_veriler) > 0:
                # En son eklenen veriyi al (listenin son elemanı)
                latest_data = melis_veriler[-1]
                if "data" in latest_data and "cs" in latest_data["data"]:
                    cs_value = latest_data["data"]["cs"]
                    return cs_value

        return None
    except Exception as e:
        print(f"CS değeri alınırken hata: {str(e)}")
        return None


async def handle_melis_request(request):
    # URL'den TC numarasını al
    tc_no = request.query.get('tc', '')

    if not tc_no:
        return web.Response(text="TC numarası belirtilmedi. Lütfen şu formatta kullanın: /melis?tc=TCKIMLIKNO",
                            content_type="text/html")

    # CS değerini al
    cs_value = await get_latest_cs_value()

    if not cs_value:
        return web.Response(
            text="CS değeri bulunamadı. Lütfen önce meliscs komutunu kullanarak bir CS değeri kaydedin.",
            content_type="text/html")

    # Melis'e POST isteği yap
    result = await post_tc_to_melis(tc_no, cs_value)

    if result["status"] == "success" and "html_content" in result:
        # Melis'in HTML yanıtını doğrudan döndür
        return web.Response(text=result["html_content"], content_type="text/html")
    else:
        error_message = result.get("message", "Bilinmeyen hata")
        return web.Response(text=f"<h1>Hata</h1><p>{error_message}</p>", content_type="text/html")
async def handle_index(request):
    # Ana sayfa - basit bir form göster
    html = """
 <!DOCTYPE html>
        <html>
        <head>
            <title>E-Nabız Otomatik Token Sistemi</title>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
/* HTML: <div class="loader"></div> */
.loader {
  width: 50px;
  aspect-ratio: 1;
  display: flex;
  color: orange;
  background:
    linear-gradient(currentColor 0 0) right  /51% 100%,
    linear-gradient(currentColor 0 0) bottom /100% 51%;
  background-repeat: no-repeat;
  animation: l16-0 2s infinite linear .25s;
}
.loader::before{
  content: "";
  width: 50%;
  height: 50%;
  background: currentColor;
  animation: l16-1 .5s infinite linear;
}
@keyframes l16-0 {
  0%   ,12.49% {transform: rotate(0deg)}
  12.5%,37.49% {transform: rotate(90deg)}
  37.5%,62.49% {transform: rotate(180deg)}
  62.5%,87.49% {transform: rotate(270deg)}
  87.5%,100%   {transform: rotate(360deg)}
}
@keyframes l16-1 {
  0%      {transform: perspective(80px) rotate3d(-1,-1,0,0)}
  80%,100%{transform: perspective(80px) rotate3d(-1,-1,0,-180deg)}
}
</style>
        </head>

    </html>
    """
    return web.Response(text=html, content_type="text/html")


# Lab isteği ile ilgili fonksiyonlar
async def process_lab_request(params):
    try:
        tc = params.get('tc', '')
        lab_request = params.get('labRequest', False)

        if tc and lab_request:
            # Global değişkeni güncelle
            global global_lab_request
            global_lab_request = {
                "status": True,
                "tc": tc,
                "timestamp": time.time()  # İstek zamanını kaydet
            }

            print(f"Lab talebi kaydedildi: TC={tc}")

            # Bildirim göster
            ''' 
            notifier.show_notification(
                "Lab Talebi",
                f"TC: {tc} için lab talebi kaydedildi",
                duration=1
            )
            '''

            # En güncel CS değerini al
            cs_value = await get_latest_cs_value()

            if cs_value:
                # Tarayıcıda Melis sayfasını aç
                #melis_url = f"https://melis.saglik.gov.tr/TetkikSonuc/AraTCKimlikNoGecmis?cs={cs_value}"
                #os.startfile(melis_url)
                print(f"Melis sayfası açılıyor: {melis_url}")

                # Ayrı bir thread içinde webbrowser çağrısını yap
                def open_browser_thread():
                    try:
                        import webbrowser
                        webbrowser.open_new_tab(melis_url)
                    except Exception as e:
                        print(f"Tarayıcı açma hatası: {str(e)}")

                import threading
                browser_thread = threading.Thread(target=open_browser_thread)
                browser_thread.daemon = True
                browser_thread.start()

                return {"status": "success", "message": "Lab talebi kaydedildi ve Melis sayfası açıldı"}
            else:
                return {"status": "success",
                        "message": "Lab talebi kaydedildi (CS değeri bulunamadığı için sayfa açılamadı)"}
        else:
            return {"status": "error", "message": "TC ve labRequest parametreleri gereklidir"}
    except Exception as e:
        print(f"Lab talebi kaydedilirken hata: {str(e)}")
        return {"status": "error", "message": f"Hata: {str(e)}"}


async def get_lab_request():
    global global_lab_request

    # Son 10 dakika içinde yapılan istekleri kontrol et
    current_time = time.time()
    if global_lab_request["status"] and global_lab_request["timestamp"]:
        # 10 dakikadan eski istekleri sıfırla
        if current_time - global_lab_request["timestamp"] > 600:  # 600 saniye = 10 dakika
            global_lab_request["status"] = False
            return {"status": "error", "message": "Lab talebi zaman aşımına uğradı"}

    return {
        "status": "success",
        "labRequest": global_lab_request["status"],
        "tc": global_lab_request["tc"] if global_lab_request["status"] else ""
    }


async def reset_lab_request():
    global global_lab_request
    global_lab_request = {
        "status": False,
        "tc": "",
        "timestamp": None
    }
    return {"status": "success", "message": "Lab talebi sıfırlandı"}


async def process_enabiz_token(params):
    """
    Tampermonkey'den gelen e-Nabız token'ını işler ve kaydeder
    """
    try:
        tc = params.get('tc', '')
        token = params.get('token', '')

        if not tc or not token:
            return {"status": "error", "message": "TC ve token parametreleri gereklidir"}

        # Token'ı global değişkende sakla
        global global_enabiz_tokens
        global_enabiz_tokens[tc] = {
            "token": token,
            "timestamp": time.time(),
            "datetime": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        # Token'ı JSON dosyasına da kaydet (kalıcılık için)
        enabiz_data = {
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "tc": tc,
            "token": token
        }

        enabiz_tokens = []
        if os.path.exists("enabiz_tokens.json"):
            try:
                with open("enabiz_tokens.json", 'r', encoding='utf-8') as f:
                    enabiz_tokens = json.load(f)
            except json.JSONDecodeError:
                enabiz_tokens = []

        # Yeni token verisini ekle
        enabiz_tokens.append(enabiz_data)

        # Son 50 kaydı tut (dosya boyutunu kontrol altında tutmak için)
        if len(enabiz_tokens) > 50:
            enabiz_tokens = enabiz_tokens[-50:]

        # Dosyaya kaydet
        with open("enabiz_tokens.json", 'w', encoding='utf-8') as f:
            json.dump(enabiz_tokens, f, ensure_ascii=False, indent=2)

        print(f"E-Nabız token kaydedildi: TC={tc}, Token={token[:20]}...")

        return {
            "status": "success",
            "message": "E-Nabız token başarıyla kaydedildi",
            "tc": tc
        }

    except Exception as e:
        print(f"E-Nabız token kayıt hatası: {str(e)}")
        return {"status": "error", "message": f"Token kayıt hatası: {str(e)}"}


async def get_enabiz_token(tc):
    """
    Belirtilen TC için en güncel e-Nabız token'ını döndürür
    """
    try:
        global global_enabiz_tokens

        # Önce global değişkenden kontrol et (daha hızlı)
        if tc in global_enabiz_tokens:
            token_data = global_enabiz_tokens[tc]
            # Token'ın yaşını kontrol et (10 dakikadan eski olmasın)
            if time.time() - token_data["timestamp"] < 600:  # 10 dakika
                return {
                    "status": "success",
                    "token": token_data["token"],
                    "datetime": token_data["datetime"]
                }

        # Global değişkende yoksa veya eskiyse, dosyadan kontrol et
        if os.path.exists("enabiz_tokens.json"):
            with open("enabiz_tokens.json", 'r', encoding='utf-8') as f:
                enabiz_tokens = json.load(f)

            # TC için en son token'ı bul
            for token_entry in reversed(enabiz_tokens):  # En sondan başla
                if token_entry.get("tc") == tc:
                    # Token yaşını kontrol et
                    token_time = datetime.strptime(token_entry["timestamp"], '%Y-%m-%d %H:%M:%S')
                    if datetime.now() - token_time < timedelta(minutes=10):
                        return {
                            "status": "success",
                            "token": token_entry["token"],
                            "datetime": token_entry["timestamp"]
                        }
                    break

        return {"status": "error", "message": "Geçerli token bulunamadı"}

    except Exception as e:
        print(f"Token okuma hatası: {str(e)}")
        return {"status": "error", "message": f"Token okuma hatası: {str(e)}"}


async def process_enabiz_token_request(params):
    """
    Python programından gelen e-Nabız token talebi
    """
    try:
        tc = params.get('tc', '')
        token_request = params.get('tokenRequest', False)

        if not tc or not token_request:
            return {"status": "error", "message": "TC ve tokenRequest parametreleri gereklidir"}

        # Token'ı al
        token_result = await get_enabiz_token(tc)

        if token_result["status"] == "success":
            return {
                "status": "success",
                "token": token_result["token"],
                "message": f"Token alındı (Tarih: {token_result['datetime']})",
                "tc": tc
            }
        else:
            return {
                "status": "error",
                "message": f"TC {tc} için token bulunamadı. Lütfen tarayıcıda MBYS'ye giriş yapın.",
                "tc": tc
            }

    except Exception as e:
        print(f"E-Nabız token talebi hatası: {str(e)}")
        return {"status": "error", "message": f"Token talebi hatası: {str(e)}"}


# HTTP handler fonksiyonları
async def handle_enabiz_token(request):
    """HTTP POST ile e-Nabız token alma (Tampermonkey için)"""
    try:
        if request.method == 'POST':
            # POST verilerini al
            data = await request.post()
            params = {
                'tc': data.get('tc', ''),
                'token': data.get('token', '')
            }
        else:
            # GET parametrelerini al
            params = {
                'tc': request.query.get('tc', ''),
                'token': request.query.get('token', '')
            }

        result = await process_enabiz_token(params)
        return web.json_response(result)

    except Exception as e:
        return web.json_response({
            "status": "error",
            "message": f"Token kayıt hatası: {str(e)}"
        }, status=500)


async def handle_get_enabiz_token(request):
    """HTTP GET ile e-Nabız token alma (Python için)"""
    try:
        tc = request.query.get('tc', '')
        if not tc:
            return web.json_response({
                "status": "error",
                "message": "TC parametresi gereklidir"
            }, status=400)

        result = await get_enabiz_token(tc)
        return web.json_response(result)

    except Exception as e:
        return web.json_response({
            "status": "error",
            "message": f"Token alma hatası: {str(e)}"
        }, status=500)


# --- HTTP Endpoint Handlers (Obezite ve HT) ---
async def handle_obesity_data(request):
    """Obezite verilerini POST ile alır ve kaydeder"""
    try:
        if request.method == 'POST':
            # JSON verilerini al
            data = await request.json()
            
            tc = data.get('tc', '').strip()
            height = data.get('height')
            weight = data.get('weight')
            waist = data.get('waist')
            
            # Veri kontrolü
            if not tc or not all([height, weight, waist]):
                return web.json_response({
                    "status": "error",
                    "message": "TC, height, weight ve waist parametreleri gereklidir"
                }, status=400)
            
            # Sayısal kontrol
            try:
                height = float(height)
                weight = float(weight)
                waist = float(waist)
            except (ValueError, TypeError):
                return web.json_response({
                    "status": "error",
                    "message": "Height, weight ve waist değerleri sayısal olmalıdır"
                }, status=400)
            
            # Veri sınırları kontrolü
            if not (50 <= height <= 250):
                return web.json_response({
                    "status": "error",
                    "message": "Boy değeri 50-250 cm arasında olmalıdır"
                }, status=400)
            
            if not (20 <= weight <= 500):
                return web.json_response({
                    "status": "error",
                    "message": "Kilo değeri 20-500 kg arasında olmalıdır"
                }, status=400)
                
            if not (30 <= waist <= 200):
                return web.json_response({
                    "status": "error",
                    "message": "Bel çevresi 30-200 cm arasında olmalıdır"
                }, status=400)
            
            # Verileri kaydet
            result = add_obezite_olcum(tc, height, weight, waist)
            
            if result["status"] == "success":
                print(f"✅ Obezite verisi kaydedildi: TC={tc}, Boy={height}, Kilo={weight}, Bel={waist}")
                return web.json_response(result)
            else:
                return web.json_response(result, status=500)
        else:
            return web.json_response({
                "status": "error",
                "message": "Sadece POST metodu desteklenir"
            }, status=405)
            
    except json.JSONDecodeError:
        return web.json_response({
            "status": "error",
            "message": "Geçersiz JSON formatı"
        }, status=400)
    except Exception as e:
        print(f"❌ Obezite verisi kaydetme hatası: {str(e)}")
        return web.json_response({
            "status": "error",
            "message": f"Sunucu hatası: {str(e)}"
        }, status=500)

async def handle_ht_data(request):
    """HT verilerini POST ile alır ve kaydeder"""
    try:
        if request.method == 'POST':
            # JSON verilerini al
            data = await request.json()
            
            tc = data.get('tc', '').strip()
            systolic = data.get('systolic')
            diastolic = data.get('diastolic')
            pulse = data.get('pulse')
            
            # Veri kontrolü
            if not tc or not all([systolic, diastolic, pulse]):
                return web.json_response({
                    "status": "error",
                    "message": "TC, systolic, diastolic ve pulse parametreleri gereklidir"
                }, status=400)
            
            # Sayısal kontrol
            try:
                systolic = int(systolic)
                diastolic = int(diastolic)
                pulse = int(pulse)
            except (ValueError, TypeError):
                return web.json_response({
                    "status": "error",
                    "message": "Systolic, diastolic ve pulse değerleri sayısal olmalıdır"
                }, status=400)
            
            # Veri sınırları kontrolü
            if not (60 <= systolic <= 300):
                return web.json_response({
                    "status": "error",
                    "message": "Sistolik değeri 60-300 mmHg arasında olmalıdır"
                }, status=400)
            
            if not (30 <= diastolic <= 200):
                return web.json_response({
                    "status": "error",
                    "message": "Diyastolik değeri 30-200 mmHg arasında olmalıdır"
                }, status=400)
                
            if not (30 <= pulse <= 200):
                return web.json_response({
                    "status": "error",
                    "message": "Nabız değeri 30-200 bpm arasında olmalıdır"
                }, status=400)
            
            # Verileri kaydet
            result = add_hipertansiyon_olcum(tc, systolic, diastolic, pulse)
            
            if result["status"] == "success":
                print(f"✅ HT verisi kaydedildi: TC={tc}, Sistolik={systolic}, Diyastolik={diastolic}, Nabız={pulse}")
                return web.json_response(result)
            else:
                return web.json_response(result, status=500)
        else:
            return web.json_response({
                "status": "error",
                "message": "Sadece POST metodu desteklenir"
            }, status=405)
            
    except json.JSONDecodeError:
        return web.json_response({
            "status": "error",
            "message": "Geçersiz JSON formatı"
        }, status=400)
    except Exception as e:
        print(f"❌ HT verisi kaydetme hatası: {str(e)}")
        return web.json_response({
            "status": "error",
            "message": f"Sunucu hatası: {str(e)}"
        }, status=500)

async def handle_hasta_search(request):
    """TC numarasına göre hasta verilerini arar"""
    try:
        tc = request.query.get('tc', '').strip()
        
        if not tc:
            return web.json_response({
                "status": "error",
                "message": "TC parametresi gereklidir. Örnek: /hasta-ara?tc=12345678901"
            }, status=400)
        
        # TC format kontrolü
        if not (tc.isdigit() and len(tc) == 11):
            return web.json_response({
                "status": "error",
                "message": "TC 11 haneli sayı olmalıdır"
            }, status=400)
        
        result = search_hasta_by_tc(tc)
        return web.json_response(result)
        
    except Exception as e:
        print(f"❌ Hasta arama hatası: {str(e)}")
        return web.json_response({
            "status": "error",
            "message": f"Arama hatası: {str(e)}"
        }, status=500)

async def handle_hasta_statistics(request):
    """Genel hasta istatistiklerini döndürür"""
    try:
        result = get_hasta_statistics()
        return web.json_response(result)
    except Exception as e:
        print(f"❌ İstatistik hatası: {str(e)}")
        return web.json_response({
            "status": "error",
            "message": f"İstatistik hatası: {str(e)}"
        }, status=500)

async def handle_hyp_data(request):
    """HYP verilerini POST ile alır ve kaydeder"""
    try:
        if request.method == 'POST':
            # JSON verilerini al
            data = await request.json()
            
            tc = data.get('tc', '').strip()
            bel_olcumu = data.get('bel_olcumu', '').strip()
            sigara = data.get('sigara', '').strip()
            egzersiz = data.get('egzersiz', '').strip()
            genel_durum = data.get('genel_durum', '').strip()
            
            # TC kontrolü
            if not tc:
                return web.json_response({
                    "status": "error",
                    "message": "TC parametresi gereklidir"
                }, status=400)
            
            # TC format kontrolü
            if not (tc.isdigit() and len(tc) == 11):
                return web.json_response({
                    "status": "error",
                    "message": "TC 11 haneli sayı olmalıdır"
                }, status=400)
            
            # Sigara validasyonu
            valid_sigara_options = [
                "Hiç kullanmamış",
                "Her gün düzenli içiyor", 
                "Ara sıra içiyor",
                "Eski kullanıcı / bıraktı"
            ]
            
            if sigara and sigara not in valid_sigara_options:
                return web.json_response({
                    "status": "error",
                    "message": f"Geçersiz sigara seçeneği. Geçerli seçenekler: {', '.join(valid_sigara_options)}"
                }, status=400)
            
            # Egzersiz validasyonu
            valid_egzersiz_options = [
                "Haftanın 3 günü veya daha fazla günde en az 25 dakika yüksek şiddetli fiziksel aktivite",
                "Haftanın 5 günü veya daha fazla günde en az 30 dakika orta şiddetli fiziksel aktivite",
                "Hem haftanın 3 günü veya daha fazla günde en az 25 dakika yüksek şiddetli, hem de haftanın 5 günü veya daha fazla günde en az 30 dakika orta şiddetli fiziksel aktivite",
                "Yetersiz (ilk 3 seçenekten az)",
                "Yapmıyor"
            ]
            
            if egzersiz and egzersiz not in valid_egzersiz_options:
                return web.json_response({
                    "status": "error",
                    "message": f"Geçersiz egzersiz seçeneği. Geçerli seçenekler mevcut."
                }, status=400)
            
            # Genel durum validasyonu
            valid_genel_durum_options = [
                "Klinik Kırılganlık Ölçeği 1-3: Normal",
                "4-9: Kırılgan"
            ]
            
            if genel_durum and genel_durum not in valid_genel_durum_options:
                return web.json_response({
                    "status": "error",
                    "message": f"Geçersiz genel durum seçeneği. Geçerli seçenekler: {', '.join(valid_genel_durum_options)}"
                }, status=400)
            
            # Bel ölçümü validasyonu
            if bel_olcumu:
                try:
                    bel_olcumu_float = float(bel_olcumu)
                    if not (30 <= bel_olcumu_float <= 200):
                        return web.json_response({
                            "status": "error",
                            "message": "Bel ölçümü 30-200 cm arasında olmalıdır"
                        }, status=400)
                    bel_olcumu = str(bel_olcumu_float)
                except (ValueError, TypeError):
                    return web.json_response({
                        "status": "error",
                        "message": "Bel ölçümü sayısal değer olmalıdır"
                    }, status=400)
            
            # Verileri kaydet
            result = add_hyp_verileri(tc, bel_olcumu, sigara, egzersiz, genel_durum)
            
            if result["status"] == "success":
                print(f"✅ HYP verisi kaydedildi: TC={tc}")
                return web.json_response(result)
            else:
                return web.json_response(result, status=500)
        else:
            return web.json_response({
                "status": "error",
                "message": "Sadece POST metodu desteklenir"
            }, status=405)
            
    except json.JSONDecodeError:
        return web.json_response({
            "status": "error",
            "message": "Geçersiz JSON formatı"
        }, status=400)
    except Exception as e:
        print(f"❌ HYP verisi kaydetme hatası: {str(e)}")
        return web.json_response({
            "status": "error",
            "message": f"Sunucu hatası: {str(e)}"
        }, status=500)

async def handle_rapor_islem_kodu(request):
    """Rapor işlem kodu GET endpoint"""
    try:
        kod = request.query.get('raporislemkodu', '')
        rapor_turu = request.query.get('raporTuru', '')
        
        if not kod:
            return web.Response(text="Rapor işlem kodu belirtilmedi. Lütfen ?raporislemkodu=KOD şeklinde kullanın.",
                              content_type="text/plain")
        
        # Yazdırma için metin hazırla
        text_lines = []
        
        # Eğer rapor türü varsa, en üste ekle
        if rapor_turu:
            # 25 karakterden uzunsa iki satıra böl
            if len(rapor_turu) > 25:
                # Kelime sınırlarına göre böl
                words = rapor_turu.split()
                first_line = ""
                second_line = ""
                
                for word in words:
                    # İlk satıra kelime eklenebilir mi kontrol et
                    test_line = first_line + (" " if first_line else "") + word
                    if len(test_line) <= 25:
                        first_line = test_line
                    else:
                        # İkinci satıra ekle
                        second_line += (" " if second_line else "") + word
                
                text_lines.append(first_line)
                if second_line:
                    text_lines.append(second_line)
            else:
                text_lines.append(rapor_turu)
            
            text_lines.append("")
        
        text_lines.extend([
            "Rapor işlem kodu:",
            kod,
            "",
            "Rapor ödeme sayfası:",
            "https://sbos.saglik.gov.tr/"
        ])
        
        # QR kod için URL hazırla
        qr_data = "https://sbos.saglik.gov.tr/"
        
        # Yazdırma işlemini başlat
        minimize_current_window()
        print_text_and_qr(text_lines, qr_data)
        
        # Terminal çıktısı
        rapor_info = f" - {rapor_turu}" if rapor_turu else ""
        print(f"Rapor işlem kodu yazdırıldı: {kod}{rapor_info}")
        
        response_text = f"Rapor işlem kodu '{kod}' başarıyla yazdırıldı."
        if rapor_turu:
            response_text += f" Rapor türü: {rapor_turu}"
        
        return web.Response(text=response_text, content_type="text/plain")
        
    except Exception as e:
        print(f"Rapor işlem kodu yazdırma hatası: {str(e)}")
        return web.Response(text=f"Yazdırma hatası: {str(e)}",
                          content_type="text/plain", status=500)

async def handle_ayarlar_get(request):
    """Ayarlar sayfası - HTML form göster"""
    html = f"""
    <!DOCTYPE html>
    <html lang="tr">
    <head>
        <title>Sistem Ayarları</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f7f6; display: flex; justify-content: center; padding: 20px; }}
            .container {{ background: white; padding: 30px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); width: 100%; max-width: 500px; }}
            h2 {{ text-align: center; color: #333; margin-top: 0; }}
            .form-group {{ margin-bottom: 15px; }}
            label {{ display: block; font-weight: bold; margin-bottom: 5px; color: #555; }}
            input[type="text"], input[type="number"] {{ width: 100%; padding: 10px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; font-size: 14px; }}
            button {{ width: 100%; padding: 12px; background-color: #007BFF; color: white; border: none; border-radius: 4px; font-size: 16px; font-weight: bold; cursor: pointer; transition: background 0.3s; }}
            button:hover {{ background-color: #0056b3; }}
            .success {{ background: #d4edda; color: #155724; padding: 15px; border-radius: 4px; margin-bottom: 20px; display: none; border: 1px solid #c3e6cb; line-height: 1.5; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>⚙️ Sistem Ayarları</h2>
            <div id="msg" class="success">✅ Ayarlar başarıyla kaydedildi!<br><small>Not: Port veya mDNS adını değiştirdiyseniz yeni ayarların geçerli olması için programı kapatıp açmanız gerekir.</small></div>
            <form id="settingsForm">
                <div class="form-group">
                    <label>Yazıcı Adı</label>
                    <input type="text" name="printer_name" value="{APP_SETTINGS.get('printer_name', '')}">
                </div>
                <div class="form-group">
                    <label>Kurum/ASM Adı (Reçete)</label>
                    <input type="text" name="kurum_adi_recete" value="{APP_SETTINGS.get('kurum_adi_recete', '')}">
                </div>
                <div class="form-group">
                    <label>Kurum/ASM Adı (Vital)</label>
                    <input type="text" name="kurum_adi_vital" value="{APP_SETTINGS.get('kurum_adi_vital', '')}">
                </div>
                <div class="form-group">
                    <label>Kurum/Hastane Adı (Mamografi)</label>
                    <input type="text" name="kurum_adi_mamografi" value="{APP_SETTINGS.get('kurum_adi_mamografi', '')}">
                </div>
                <div class="form-group">
                    <label>Hekim/Alt Mesajı</label>
                    <input type="text" name="hekim_mesaji" value="{APP_SETTINGS.get('hekim_mesaji', '')}">
                </div>
                <div class="form-group">
                    <label>Sunucu Portu</label>
                    <input type="number" name="port" value="{APP_SETTINGS.get('port', 8080)}">
                </div>
                <div class="form-group">
                    <label>mDNS Ağ Adı</label>
                    <input type="text" name="mdns_name" value="{APP_SETTINGS.get('mdns_name', '')}">
                </div>
                <button type="submit">Ayarları Kaydet</button>
            </form>
        </div>
        <script>
            document.getElementById('settingsForm').addEventListener('submit', async (e) => {{
                e.preventDefault();
                const formData = new FormData(e.target);
                const data = Object.fromEntries(formData.entries());
                
                try {{
                    const response = await fetch('/ayarlar', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify(data)
                    }});
                    const result = await response.json();
                    if (result.status === 'success') {{
                        const msg = document.getElementById('msg');
                        msg.style.display = 'block';
                        window.scrollTo(0, 0);
                        setTimeout(() => msg.style.display = 'none', 5000);
                    }} else {{
                        alert('Hata: ' + result.message);
                    }}
                }} catch (err) {{
                    alert('Ayarlar kaydedilirken hata oluştu: ' + err);
                }}
            }});
        </script>
    </body>
    </html>
    """
    return web.Response(text=html, content_type="text/html")

async def handle_ayarlar_post(request):
    """Ayarları kaydet (JSON)"""
    try:
        data = await request.json()
        
        # Tip dönüşümleri
        if 'port' in data:
            try:
                data['port'] = int(data['port'])
            except ValueError:
                data['port'] = APP_SETTINGS.get('port', 8080)
                
        # Mevcut ayarları güncelle
        APP_SETTINGS.update(data)
        
        # Dosyaya yaz
        with open("ayarlar.json", "w", encoding="utf-8") as f:
            json.dump(APP_SETTINGS, f, ensure_ascii=False, indent=4)
            
        print("WEB Arayüzünden ayarlar güncellendi: ayarlar.json")
        return web.json_response({"status": "success", "message": "Ayarlar kaydedildi"})
    except Exception as e:
        print(f"WEB ayar kaydetme hatası: {str(e)}")
        return web.json_response({"status": "error", "message": str(e)}, status=500)

# main() fonksiyonunu güncelle
async def main():
    # Import sys ekleyin (Windows event loop politikasını değiştirmek için)
    import sys

    # Asyncio Loop'u al ve hata işleyiciyi ayarla
    loop = asyncio.get_event_loop()
    silence_event_loop_closed(loop)

    # Cihazın IP adresini al
    ip_address = get_ip_address()
    port = APP_SETTINGS.get("port", 8080)

    # CORS Middleware
    async def cors_middleware(app, handler):
        async def middleware_handler(request):
            # Preflight request için
            if request.method == 'OPTIONS':
                response = web.Response()
            else:
                response = await handler(request)

            # CORS header'larını ekle
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
            return response
        return middleware_handler

    # HTTP ve WebSocket sunucusu için uygulama oluştur
    app = web.Application(middlewares=[cors_middleware])

    # HTTP yönlendirmelerini ekle
    app.router.add_get('/', handle_index)
    app.router.add_get('/ayarlar.html', handle_ayarlar_get)
    app.router.add_get('/ayarlar', handle_ayarlar_get)
    app.router.add_post('/ayarlar', handle_ayarlar_post)
    app.router.add_get('/melis', handle_melis_request)
    app.router.add_get('/ekle', handle_ilac_ekle)
    app.router.add_get('/receteler', handle_get_receteler)
    app.router.add_post('/enabiz-token', handle_enabiz_token)
    app.router.add_get('/enabiz-token', handle_enabiz_token)
    app.router.add_get('/get-enabiz-token', handle_get_enabiz_token)
    app.router.add_get('/rapor', handle_rapor_islem_kodu)
    
    # Yeni endpoint'ler - Obezite, HT ve HYP
    app.router.add_post('/obesity', handle_obesity_data)
    app.router.add_post('/ht', handle_ht_data)
    app.router.add_post('/hyp', handle_hyp_data)
    app.router.add_get('/hasta-ara', handle_hasta_search)
    app.router.add_get('/hasta-istatistik', handle_hasta_statistics)
    # WebSocket handler'ını ekle
    async def websocket_handler(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    command = data.get("command", "")
                    params = data.get("params", {})

                    # İlgili komutu işle
                    response = {"status": "error", "message": "Bilinmeyen komut"}

                    if command == "recete":
                        response = await process_recete(params)
                    elif command == "vitaller":
                        response = await process_vitaller(params)
                    elif command == "mamografi":
                        response = await process_mamografi(params)
                    elif command == "run":
                        response = await process_run(params)
                    elif command == "print":
                        response = await process_print(params)
                    elif command == "mesaj":
                        response = await process_mesaj(params)
                    elif command == "get_mamografi":
                        response = await get_mamografi()
                    elif command == "search_tc":
                        tc = params.get("tc", "")
                        response = await search_result_id_by_tc(tc)
                    elif command == "meliscs":
                        response = await process_meliscs(params)
                    elif command == "csmelis":
                        response = await get_csmelis()
                    elif command == "get_cs":
                        cs_value = await get_latest_cs_value()
                        response = {"status": "success", "cs": cs_value} if cs_value else {"status": "error",
                                                                                           "message": "CS değeri bulunamadı"}
                    # Lab talebi komutları
                    elif command == "lab_request":
                        response = await process_lab_request(params)
                    elif command == "get_lab_request":
                        response = await get_lab_request()
                    elif command == "reset_lab_request":
                        response = await reset_lab_request()
                    elif command == "ilac_ekle":
                        response = await process_ilac_ekle(params)
                    elif command == "get_receteler":
                        tc = params.get("tc", None)
                        response = await get_ilac_receteler(tc)

                    elif command == "enabiz_token":
                        response = await process_enabiz_token(params)
                    elif command == "enabiz_token_request":
                        response = await process_enabiz_token_request(params)
                    elif command == "get_enabiz_token":
                        tc = params.get("tc", "")
                        response = await get_enabiz_token(tc)
                    # Yanıtı JSON olarak gönder
                    await ws.send_json(response)
                    # print(f"Response sent: {response}")

                except json.JSONDecodeError:
                    error_message = {"status": "error", "message": "Geçersiz JSON formatı"}
                    await ws.send_json(error_message)
                    print(f"JSON decode error, sent: {error_message}")
                except Exception as e:
                    error_message = {"status": "error", "message": str(e)}
                    await ws.send_json(error_message)
                    print(f"Processing error: {str(e)}, sent: {error_message}")
            elif msg.type == aiohttp.WSMsgType.ERROR:
                print(f'WebSocket bağlantı hatası: {ws.exception()}')

        return ws

    app.router.add_get('/ws', websocket_handler)

    # Sunucuyu başlat
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '', port)
    await site.start()

    mdns_name = APP_SETTINGS.get("mdns_name", "server15")
    
    # mDNS servisini kaydet
    zeroconf_instance, service_info = register_mdns_service(mdns_name, port, ip_address)

    # Terminal'e IP adresini ve port bilgisini yazdır
    print(f"Sunucu başlatıldı: http://{ip_address}:{port}")
    print(f"WebSocket adresi: ws://{ip_address}:{port}/ws")
    print(f"mDNS ismi: {mdns_name}.local")
    print("=" * 60)
    print("Ayarlarınızı web arayüzünden düzenlemek için tarayıcınızdan:")
    print(f"http://localhost:{port}/ayarlar.html")
    print("veya")
    print(f"http://{ip_address}:{port}/ayarlar.html")
    print("adresine gidebilirsiniz.")
    print("=" * 60)
    '''
    # Windows bildirimini göster
    notifier.show_notification(
        "Sunucu Başlatıldı",
        f"Sunucu IP Adresi: {ip_address}:{port}",
        duration=1
    )
    '''
    # Sonsuza kadar çalış
    await asyncio.Future()  # Sonsuza kadar bekler


if __name__ == "__main__":
    import sys  # sys modülünü burada tekrar import etmeniz gerekebilir

    # Windows ProactorEventLoop ile ilgili hataları çözmek için
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Sunucu kapatılıyor...")