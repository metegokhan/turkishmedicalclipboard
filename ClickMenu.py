import pyperclip
import time
import re
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox
import pygetwindow as gw
import json
import os
import datetime
import sys
import websocket  # pip install websocket-client
import threading
import requests
# --- Fonksiyon Tanımları ---
def is_tc_number(text):
    if not text:
        return False
    return bool(re.match(r'^\d{11}$', text.strip()))
# Yeni: İlaç barkodu kontrolü
def is_drug_barcode(text):
    if not text:
        return False
    # 13 haneli normal veya 14 haneli barkod (baştaki 0 dahil)
    return bool(re.match(r'^\d{13}$', text.strip()) or re.match(r'^0\d{13}$', text.strip()))
def is_target_window_active():
    """
    Bu fonksiyon artık her zaman True döndürür, böylece herhangi bir pencerede
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         haneli TC numarası kopyalandığında menü açılır.
    """
    return True  # Her zaman True döndürerek tüm programlarda çalışmasını sağlıyoruz
def open_new_prescription(tc_number):
    try:
        url = f"https://recetem.enabiz.gov.tr/RBS/Prescription/Create?tc={tc_number}"
        webbrowser.open_new_tab(url)
        print(f"Yeni Reçete sayfası açıldı: {url}")
    except Exception as e:
        print(f"Yeni reçete sayfası açma hatası: {e}")
def open_erapor(tc_number):
    try:
        url = f"https://recetem.enabiz.gov.tr/RBS/PatientReport?tck={tc_number}&r=erapor"
        webbrowser.open_new_tab(url)
        print(f"E-Rapor sorgusu açıldı: {url}")
    except Exception as e:
        print(f"E-Rapor sayfası açma hatası: {e}")
def open_recetem_report(tc_number):
    try:
        url = f"https://recetem.enabiz.gov.tr/RBS/PatientReport?tck={tc_number}&r=recetem"
        webbrowser.open_new_tab(url)
        print(f"Reçetem sorgusu açıldı: {url}")
    except Exception as e:
        print(f"Reçetem sayfası açma hatası: {e}")
def get_prescriptions_for_tc(tc_number):
    try:
        today = datetime.datetime.now()
        file_date = today.strftime("%d%m%y")
        json_filename = f"receteler_{file_date}.json"
        if not os.path.exists(json_filename):
            # print(f"Uyarı: {json_filename} bulunamadı.") # İstenirse loglama açılabilir
            return []
        with open(json_filename, 'r', encoding='utf-8') as f:
            content = f.read()
            if not content: return []
            try:
                prescriptions = json.loads(content)
                if not isinstance(prescriptions, list): return []
            except json.JSONDecodeError: return []
        matching = [p for p in prescriptions if isinstance(p, dict) and p.get("original_tc") == tc_number]
        try:
            matching.sort(key=lambda x: x.get("tarih", datetime.datetime.min.isoformat()), reverse=True)
        except Exception: pass
        return matching
    except Exception as e:
        print(f"Reçeteleri çekerken hata: {str(e)}")
        return []
# --- Obezite ve HT Fonksiyonları ---
def send_obesity_data(tc_number, height, weight, waist):
    """Obezite verilerini localhost'a gönderir."""
    try:
        url = "http://localhost:8080/obesity"
        data = {
            "tc": tc_number,
            "height": height,
            "weight": weight,
            "waist": waist,
            "timestamp": datetime.datetime.now().isoformat()
        }
        
        response = requests.post(url, json=data, timeout=5)
        
        if response.status_code == 200:
            print(f"✅ Obezite verisi başarıyla gönderildi: TC={tc_number}")
            return True
        else:
            print(f"❌ Obezite verisi gönderilirken hata: {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ Localhost bağlantısı yapılamadı")
        return False
    except Exception as e:
        print(f"❌ Obezite verisi gönderme hatası: {str(e)}")
        return False

def send_ht_data(tc_number, systolic, diastolic, pulse):
    """HT verilerini localhost'a gönderir."""
    try:
        url = "http://localhost:8080/ht"
        data = {
            "tc": tc_number,
            "systolic": systolic,
            "diastolic": diastolic,
            "pulse": pulse,
            "timestamp": datetime.datetime.now().isoformat()
        }
        
        response = requests.post(url, json=data, timeout=5)
        
        if response.status_code == 200:
            print(f"✅ HT verisi başarıyla gönderildi: TC={tc_number}")
            return True
        else:
            print(f"❌ HT verisi gönderilirken hata: {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ Localhost bağlantısı yapılamadı")
        return False
    except Exception as e:
        print(f"❌ HT verisi gönderme hatası: {str(e)}")
        return False

def open_obesity_window(tc_number):
    """Obezite veri girişi penceresi açar."""
    try:
        obesity_win = tk.Toplevel()
        obesity_win.title(f"Obezite - TC: {tc_number}")
        obesity_win.geometry("350x200")
        obesity_win.resizable(False, False)
        obesity_win.attributes('-topmost', True)
        
        # Ana çerçeve
        main_frame = tk.Frame(obesity_win, padx=20, pady=20)
        main_frame.pack(fill='both', expand=True)
        
        # TC başlık
        tc_label = tk.Label(main_frame, text=f"TC: {tc_number}", font=('Arial', 12, 'bold'))
        tc_label.grid(row=0, column=0, columnspan=2, pady=(0, 15))
        
        # Boy girişi
        tk.Label(main_frame, text="Boy (cm):").grid(row=1, column=0, sticky='w', pady=5)
        height_entry = tk.Entry(main_frame, width=15)
        height_entry.grid(row=1, column=1, padx=(10, 0), pady=5)
        height_entry.focus()
        
        # Kilo girişi
        tk.Label(main_frame, text="Kilo (kg):").grid(row=2, column=0, sticky='w', pady=5)
        weight_entry = tk.Entry(main_frame, width=15)
        weight_entry.grid(row=2, column=1, padx=(10, 0), pady=5)
        
        # Bel çevresi girişi
        tk.Label(main_frame, text="Bel (cm):").grid(row=3, column=0, sticky='w', pady=5)
        waist_entry = tk.Entry(main_frame, width=15)
        waist_entry.grid(row=3, column=1, padx=(10, 0), pady=5)
        
        # Buton çerçevesi
        button_frame = tk.Frame(main_frame)
        button_frame.grid(row=4, column=0, columnspan=2, pady=(20, 0))
        
        def save_obesity_data():
            try:
                height = height_entry.get().strip()
                weight = weight_entry.get().strip()
                waist = waist_entry.get().strip()
                
                if not all([height, weight, waist]):
                    messagebox.showwarning("Eksik Veri", "Lütfen tüm alanları doldurun.")
                    return
                
                # Sayısal kontrol
                height_val = float(height)
                weight_val = float(weight)
                waist_val = float(waist)
                
                if send_obesity_data(tc_number, height_val, weight_val, waist_val):
                    messagebox.showinfo("Başarılı", "Obezite verisi başarıyla kaydedildi.")
                    obesity_win.destroy()
                else:
                    messagebox.showerror("Hata", "Veri gönderilirken hata oluştu.")
                    
            except ValueError:
                messagebox.showerror("Hata", "Lütfen geçerli sayısal değerler girin.")
            except Exception as e:
                messagebox.showerror("Hata", f"Bir hata oluştu: {str(e)}")
        
        # Kaydet butonu
        save_btn = tk.Button(button_frame, text="Kaydet", command=save_obesity_data, 
                           bg="#4CAF50", fg="white", padx=20)
        save_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # Kapat butonu
        close_btn = tk.Button(button_frame, text="Kapat", command=obesity_win.destroy,
                            bg="#f44336", fg="white", padx=20)
        close_btn.pack(side=tk.LEFT)
        
    except Exception as e:
        print(f"Obezite penceresi açma hatası: {str(e)}")
        messagebox.showerror("Hata", f"Obezite penceresi açılamadı: {str(e)}")

def open_ht_window(tc_number):
    """HT veri girişi penceresi açar."""
    try:
        ht_win = tk.Toplevel()
        ht_win.title(f"Hipertansiyon - TC: {tc_number}")
        ht_win.geometry("350x200")
        ht_win.resizable(False, False)
        ht_win.attributes('-topmost', True)
        
        # Ana çerçeve
        main_frame = tk.Frame(ht_win, padx=20, pady=20)
        main_frame.pack(fill='both', expand=True)
        
        # TC başlık
        tc_label = tk.Label(main_frame, text=f"TC: {tc_number}", font=('Arial', 12, 'bold'))
        tc_label.grid(row=0, column=0, columnspan=2, pady=(0, 15))
        
        # Sistolik girişi
        tk.Label(main_frame, text="Sistolik:").grid(row=1, column=0, sticky='w', pady=5)
        systolic_entry = tk.Entry(main_frame, width=15)
        systolic_entry.grid(row=1, column=1, padx=(10, 0), pady=5)
        systolic_entry.focus()
        
        # Diyastolik girişi
        tk.Label(main_frame, text="Diyastolik:").grid(row=2, column=0, sticky='w', pady=5)
        diastolic_entry = tk.Entry(main_frame, width=15)
        diastolic_entry.grid(row=2, column=1, padx=(10, 0), pady=5)
        
        # Nabız girişi
        tk.Label(main_frame, text="Nabız:").grid(row=3, column=0, sticky='w', pady=5)
        pulse_entry = tk.Entry(main_frame, width=15)
        pulse_entry.grid(row=3, column=1, padx=(10, 0), pady=5)
        
        # Buton çerçevesi
        button_frame = tk.Frame(main_frame)
        button_frame.grid(row=4, column=0, columnspan=2, pady=(20, 0))
        
        def save_ht_data():
            try:
                systolic = systolic_entry.get().strip()
                diastolic = diastolic_entry.get().strip()
                pulse = pulse_entry.get().strip()
                
                if not all([systolic, diastolic, pulse]):
                    messagebox.showwarning("Eksik Veri", "Lütfen tüm alanları doldurun.")
                    return
                
                # Sayısal kontrol
                systolic_val = int(systolic)
                diastolic_val = int(diastolic)
                pulse_val = int(pulse)
                
                if send_ht_data(tc_number, systolic_val, diastolic_val, pulse_val):
                    messagebox.showinfo("Başarılı", "HT verisi başarıyla kaydedildi.")
                    ht_win.destroy()
                else:
                    messagebox.showerror("Hata", "Veri gönderilirken hata oluştu.")
                    
            except ValueError:
                messagebox.showerror("Hata", "Lütfen geçerli sayısal değerler girin.")
            except Exception as e:
                messagebox.showerror("Hata", f"Bir hata oluştu: {str(e)}")
        
        # Kaydet butonu
        save_btn = tk.Button(button_frame, text="Kaydet", command=save_ht_data, 
                           bg="#4CAF50", fg="white", padx=20)
        save_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # Kapat butonu
        close_btn = tk.Button(button_frame, text="Kapat", command=ht_win.destroy,
                            bg="#f44336", fg="white", padx=20)
        close_btn.pack(side=tk.LEFT)
        
    except Exception as e:
        print(f"HT penceresi açma hatası: {str(e)}")
        messagebox.showerror("Hata", f"HT penceresi açılamadı: {str(e)}")

# Yeni: İlaç bilgilerini getiren fonksiyon
'''def get_drug_info(barcode):
    """
    Barkod numarasına göre ilaç bilgilerini getirir.
    """
    try:
        # Barkodun 13 haneli olmasını sağlayalım
        if len(barcode) == 14 and barcode.startswith('0'):
            barcode = barcode[1:]  # Baştaki 0'ı kaldır
        # İlaç bilgilerini saklamak için dosya adı
        today = datetime.datetime.now()
        file_date = today.strftime("%d%m%y")
        json_filename = f"ilaclar_{file_date}.json"
        # Önce yerel dosyadan bakalım
        if os.path.exists(json_filename):
            try:
                with open(json_filename, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if content:
                        drugs = json.loads(content)
                        if isinstance(drugs, list):
                            # Barkod eşleşmesini kontrol et
                            for drug in drugs:
                                if isinstance(drug, dict) and drug.get("barkod") == barcode:
                                    return drug
            except Exception as e:
                print(f"Yerel ilaç dosyasını okuma hatası: {str(e)}")
        # Yerel dosyada bulunamazsa API'den getir
        try:
            # Not: Bu örnek bir API endpoint'idir, gerçek API URL'nizi kullanın
            api_url = f"http://localhost:8080/ilac/bilgi?barkod={barcode}"
            #api_url = f"https://www.google.com/search?q={barcode}"

            response = requests.get(api_url, timeout=5)
            if response.status_code == 200:
                drug_info = response.json()
                # Dosyaya kaydet (isteğe bağlı)
                try:
                    if os.path.exists(json_filename):
                        with open(json_filename, 'r', encoding='utf-8') as f:
                            content = f.read()
                            if content:
                                drugs = json.loads(content)
                                if not isinstance(drugs, list):
                                    drugs = []
                            else:
                                drugs = []
                    else:
                        drugs = []
                    # Aynı barkodlu ilaç varsa güncelle, yoksa ekle
                    updated = False
                    for i, drug in enumerate(drugs):
                        if isinstance(drug, dict) and drug.get("barkod") == barcode:
                            drugs[i] = drug_info
                            updated = True
                            break
                    if not updated:
                        drugs.append(drug_info)
                    with open(json_filename, 'w', encoding='utf-8') as f:
                        json.dump(drugs, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    print(f"İlaç bilgilerini dosyaya kaydetme hatası: {str(e)}")
                return drug_info
            else:
                print(f"İlaç API hatası: {response.status_code}")
                return None
        except Exception as e:
            print(f"İlaç API isteği hatası: {str(e)}")
            return None
    except Exception as e:
        print(f"İlaç bilgilerini getirme hatası: {str(e)}")
        return None'''
# İlaç bilgilerini getiren fonksiyon
def get_drug_info(barcode):
    """
    Barkod numarasına göre ilaç bilgilerini getirir.
    """
    try:
        # Barkodun 13 haneli olmasını sağlayalım
        if len(barcode) == 14 and barcode.startswith('0'):
            barcode = barcode[1:]  # Baştaki 0'ı kaldır
        # İlaç bilgilerini saklamak için dosya adı
        today = datetime.datetime.now()
        file_date = today.strftime("%d%m%y")
        json_filename = f"ilaclar_{file_date}.json"
        # Önce yerel dosyadan bakalım
        if os.path.exists(json_filename):
            try:
                with open(json_filename, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if content:
                        drugs = json.loads(content)
                        if isinstance(drugs, list):
                            # Barkod eşleşmesini kontrol et
                            for drug in drugs:
                                if isinstance(drug, dict) and drug.get("barkod") == barcode:
                                    return drug
            except Exception as e:
                print(f"Yerel ilaç dosyasını okuma hatası: {str(e)}")
        # Yerel dosyada bulunamazsa örnek veri dön
        try:
            # API'ye bağlanma denemesi - Hata verebilir, bu yüzden try içinde
            api_url = f"http://localhost:8080/ilac/bilgi?barkod={barcode}"
            try:
                response = requests.get(api_url, timeout=2)  # Kısa timeout süresi
                if response.status_code == 200:
                    drug_info = response.json()
                    # Dosyaya kaydet (isteğe bağlı)
                    try:
                        if os.path.exists(json_filename):
                            with open(json_filename, 'r', encoding='utf-8') as f:
                                content = f.read()
                                if content:
                                    drugs = json.loads(content)
                                    if not isinstance(drugs, list):
                                        drugs = []
                                else:
                                    drugs = []
                        else:
                            drugs = []
                        # Aynı barkodlu ilaç varsa güncelle, yoksa ekle
                        updated = False
                        for i, drug in enumerate(drugs):
                            if isinstance(drug, dict) and drug.get("barkod") == barcode:
                                drugs[i] = drug_info
                                updated = True
                                break
                        if not updated:
                            drugs.append(drug_info)
                        with open(json_filename, 'w', encoding='utf-8') as f:
                            json.dump(drugs, f, ensure_ascii=False, indent=2)
                    except Exception as e:
                        print(f"İlaç bilgilerini dosyaya kaydetme hatası: {str(e)}")
                    return drug_info
            except requests.exceptions.RequestException as e:
                print(f"API bağlantı hatası: {e}")
                # Bağlantı hatalarını yönet, örnek veri döndür
        except Exception as e:
            print(f"API isteği hazırlama hatası: {e}")
        # API'ye erişilemezse JSON dosyasından veri çekmeye çalış
        json_drug = get_drug_from_json(barcode)
        if json_drug:
            print(f"JSON dosyasından ilaç verisi alınıyor: {barcode}")
            # Etken madde boşsa örnek veri kullan
            etken_madde = json_drug.get("ingredients", "").strip()
            if not etken_madde:
                etken_madde = "Örnek Etken Madde"
            return {
                "barkod": barcode,
                "ilac_adi": json_drug.get("name", "Bilinmiyor"),
                "kutu_miktari": "20",
                "fiyat": "45.99",
                "etken_madde": etken_madde,
                "recete_turu": "Normal"
            }
        else:
            print(f"İlaç bilgisi bulunamadı: {barcode}")
            return None
    except Exception as e:
        print(f"İlaç bilgilerini getirme hatası: {str(e)}")
        return None
def print_prescription(result_id):
    try:
        print_url = f"https://recetem.enabiz.gov.tr/RBS/Prescription/Detail?prescriptionId={result_id}"
        webbrowser.open_new_tab(print_url)
        print(f"Reçete yazdırma sayfası açıldı: {print_url}")
    except Exception as e:
        print(f"Reçete yazdırma hatası: {str(e)}")
def delete_prescription_page(result_id):
    try:
        delete_url = f"https://recetem.enabiz.gov.tr/RBS/Prescription/Delete?prescriptionId={result_id}"
        webbrowser.open_new_tab(delete_url)
        print(f"Reçete silme sayfası açıldı: {delete_url}")
    except Exception as e:
        print(f"Reçete silme sayfası açma hatası: {str(e)}")
# Yeni: İlaç arama sayfasını açan fonksiyon
def open_drug_search(barcode):
    """
    Barkod numarasına göre ilaç arama sayfasını açar
    """
    try:
        # Barkodun 13 haneli olmasını sağlayalım
        if len(barcode) == 14 and barcode.startswith('0'):
            barcode = barcode[1:]  # Baştaki 0'ı kaldır
        search_url = f"https://www.google.com/search?q={barcode}"
        webbrowser.open_new_tab(search_url)
        print(f"İlaç arama sayfası açıldı: {search_url}")
    except Exception as e:
        print(f"İlaç arama sayfası açma hatası: {str(e)}")
# Yeni: İlaç ekleme sayfasını açan fonksiyon
def open_drug_add(barcode):
    """
    Barkod numarasına göre ilaç ekleme sayfasını açar
    """
    try:
        # Barkodun 13 haneli olmasını sağlayalım
        if len(barcode) == 14 and barcode.startswith('0'):
            barcode = barcode[1:]  # Baştaki 0'ı kaldır
        add_url = f"http://localhost:8080/ekle?numara={barcode}"
        webbrowser.open_new_tab(add_url)
        print(f"İlaç ekleme sayfası açıldı: {add_url}")
    except Exception as e:
        print(f"İlaç ekleme sayfası açma hatası: {str(e)}")
# Yeni: İlaç doz ayarlama sayfasını açan fonksiyon
def open_drug_dose(barcode):
    """
    Barkod numarasına göre ilaç doz ayarlama sayfasını açar
    """
    try:
        # Barkodun 13 haneli olmasını sağlayalım
        if len(barcode) == 14 and barcode.startswith('0'):
            barcode = barcode[1:]  # Baştaki 0'ı kaldır
        dose_url = f"http://localhost:8080/doz?numara={barcode}"
        webbrowser.open_new_tab(dose_url)
        print(f"İlaç doz ayarlama sayfası açıldı: {dose_url}")
    except Exception as e:
        print(f"İlaç doz ayarlama sayfası açma hatası: {str(e)}")
# WebSocket bağlantısı için fonksiyon - BU FONKSİYONU YUKARI TAŞIYIN
def get_latest_cs_value():
    """
    melis.json dosyasından en son CS değerini okur.
    Dosya okunamazsa veya CS değeri yoksa varsayılan değeri döndürür.
    """
    try:
        import json
        import os
        # Dosya mevcutsa oku
        if os.path.exists("melis.json"):
            with open("melis.json", 'r', encoding='utf-8') as f:
                content = f.read()
                if not content:
                    print("melis.json dosyası boş.")
                    return "4D5DAE2D"  # Varsayılan değer
                try:
                    data = json.loads(content)
                    if not isinstance(data, list) or len(data) == 0:
                        print("melis.json geçerli veri içermiyor.")
                        return "4D5DAE2D"
                    # Son kaydı al
                    last_entry = data[-1]
                    if "data" in last_entry and "cs" in last_entry["data"]:
                        cs_value = last_entry["data"]["cs"]
                        print(f"En son CS değeri bulundu: {cs_value}")
                        return cs_value
                    elif "data" in last_entry and "url" in last_entry["data"]:
                        # URL'den CS değerini çıkar
                        url = last_entry["data"]["url"]
                        import re
                        cs_match = re.search(r"cs=([A-Z0-9]+)", url)
                        if cs_match:
                            cs_value = cs_match.group(1)
                            print(f"URL'den CS değeri çıkarıldı: {cs_value}")
                            return cs_value
                    print("CS değeri bulunamadı, varsayılan değer kullanılıyor.")
                    return "4D5DAE2D"
                except json.JSONDecodeError:
                    print("melis.json JSON formatında değil.")
                    return "4D5DAE2D"
        else:
            print("melis.json dosyası bulunamadı.")
            return "4D5DAE2D"
    except Exception as e:
        print(f"CS değeri okunurken hata: {str(e)}")
        return "4D5DAE2D"  # Hata durumunda varsayılan değeri döndür
def open_lab_results(tc_number):
    """
    TC numarası için lab sonuçlarını görüntüler.
    melis.json'dan en son CS değerini alır ve ilgili URL'yi açar.
    """
    try:
        # En son CS değerini al
        cs_value = get_latest_cs_value()
        # Lab sonuçları URL'sini oluştur
        lab_results_url = f"https://melis.saglik.gov.tr/TetkikSonuc/AraTCKimlikNoGecmis?cs={cs_value}"
        # URL'yi yeni sekmede aç
        webbrowser.open_new_tab(lab_results_url)
        print(f"Lab Sonuç sayfası açıldı: {lab_results_url}")
    except Exception as e:
        print(f"Lab sonuç sayfası açma hatası: {str(e)}")
def send_lab_request(tc_number):
    """
    TC numarası için lab talebini WebSocket üzerinden sunucuya gönderir
    ve ardından lab sonuçları sayfasını açar.
    """
    try:
        # WebSocket sunucu adresi (IP adresinize uygun şekilde değiştirin)
        server_url = "ws://localhost:8080/ws"
        # Göndereceğimiz veri
        data = {
            "command": "lab_request",
            "params": {
                "tc": tc_number,
                "labRequest": True
            }
        }
        print(f"Lab talebi gönderiliyor: TC={tc_number}")
        # WebSocket bağlantısı kurma ve veri gönderme işlemini bir thread'de yap
        def send_request_thread():
            try:
                # WebSocket bağlantısını aç
                ws = websocket.create_connection(server_url)
                # Veriyi JSON formatında gönder
                ws.send(json.dumps(data))
                # Yanıtı al
                result = ws.recv()
                ws.close()
                # Yanıtı işle
                try:
                    response = json.loads(result)
                    if response.get("status") == "success":
                        print(f"Lab talebi başarıyla gönderildi: {response.get('message', '')}")
                        # WebSocket başarılı olursa, lab sonuçları sayfasını aç
                        open_lab_results(tc_number)
                    else:
                        print(f"Lab talebi gönderilirken hata: {response.get('message', 'Bilinmeyen hata')}")
                        # WebSocket hatası olsa bile lab sonuçları sayfasını açmayı dene
                        open_lab_results(tc_number)
                except json.JSONDecodeError:
                    print(f"Sunucu yanıtı JSON formatında değil: {result}")
                    # JSON hatası olsa bile lab sonuçları sayfasını açmayı dene
                    open_lab_results(tc_number)
            except Exception as e:
                print(f"WebSocket bağlantısı sırasında hata: {str(e)}")
                # WebSocket bağlantı hatası olsa bile lab sonuçları sayfasını açmayı dene
                open_lab_results(tc_number)
        # Thread oluştur ve başlat
        thread = threading.Thread(target=send_request_thread)
        thread.daemon = True  # Ana uygulama kapandığında thread de kapanır
        thread.start()
        return True
    except Exception as e:
        print(f"Lab talebi gönderme fonksiyonunda hata: {str(e)}")
        # Herhangi bir hata olursa lab sonuçları sayfasını açmayı dene
        try:
            open_lab_results(tc_number)
        except Exception as ex:
            print(f"Hata sonrası lab sonuçları açılırken ikincil hata: {str(ex)}")
        return False
# --- Global Değişkenler ---
menu_window_active = False
drug_menu_window_active = False  # Yeni: İlaç menüsü için durum değişkeni
active_menu_window = None
active_drug_menu_window = None  # Yeni: İlaç menüsü için pencere referansı
last_clipboard = ""
last_tc_number = ""
last_drug_barcode = ""  # Yeni: Son işlenen ilaç barkodu
is_processing = False
can_process_clipboard = True
clipboard_check_id = None
menu_close_timer_id = None # Fare ayrıldığında kapanma zamanlayıcısı için ID
drug_menu_close_timer_id = None  # Yeni: İlaç menüsü kapatma zamanlayıcısı için ID
atc_icd_mapping_window_open = False  # ATC-ICD eşleştirme penceresi açık mı?
# --- Menü Penceresi Yönetimi ---
def cancel_menu_close_timer(root):
    """Aktif menü kapatma zamanlayıcısını iptal eder."""
    global menu_close_timer_id
    if menu_close_timer_id:
        try:
            if root and root.winfo_exists():
                root.after_cancel(menu_close_timer_id)
                # print("Kapatma zamanlayıcısı iptal edildi.") # Debug
        except tk.TclError:
            pass # Zamanlayıcı zaten çalışmıyor olabilir
        except Exception as e:
            print(f"Zamanlayıcı iptal hatası: {e}")
        finally:
            menu_close_timer_id = None
# Yeni: İlaç menüsü için zamanlayıcı iptal fonksiyonu
def cancel_drug_menu_close_timer(root):
    """Aktif ilaç menüsü kapatma zamanlayıcısını iptal eder."""
    global drug_menu_close_timer_id
    if drug_menu_close_timer_id:
        try:
            if root and root.winfo_exists():
                root.after_cancel(drug_menu_close_timer_id)
                # print("İlaç menüsü kapatma zamanlayıcısı iptal edildi.") # Debug
        except tk.TclError:
            pass # Zamanlayıcı zaten çalışmıyor olabilir
        except Exception as e:
            print(f"İlaç menüsü zamanlayıcı iptal hatası: {e}")
        finally:
            drug_menu_close_timer_id = None
def enable_clipboard_processing_after_delay(root):
    global can_process_clipboard, is_processing
    if root and root.winfo_exists():
        can_process_clipboard = True
        is_processing = False
        print("Pano işleme yeniden etkinleştirildi.")
    else:
        print("Root window closed before clipboard processing could be re-enabled.")
def close_menu_window(root, reason="Bilinmiyor"):
    """Menü penceresini kapatır ve ilgili durumları sıfırlar."""
    global menu_window_active, active_menu_window, is_processing, can_process_clipboard, last_tc_number
    if is_processing or not menu_window_active:
        return
    print(f"Menü kapatma işlemi başlatıldı (Sebep: {reason})")
    is_processing = True
    can_process_clipboard = False
    # --- ÖNEMLİ: Aktif kapatma zamanlayıcısını iptal et ---
    cancel_menu_close_timer(root)
    # Global tıklama dinleyicisi artık yok, bu satır kaldırıldı: root.unbind_all("<Button-1>")
    if active_menu_window and active_menu_window.winfo_exists():
        try:
            active_menu_window.destroy()
            print("Menü penceresi yok edildi")
        except tk.TclError:
            print("Menü penceresi zaten yok edilmiş.")
        except Exception as e:
            print(f"Error destroying menu window: {e}")
    active_menu_window = None
    menu_window_active = False
    def safe_clear_clipboard():
        global last_clipboard
        try:
            # Mevcut panodaki içeriğin sonuna "-" ekle
            current = pyperclip.paste()
            if current:
                new_value = current + "-"
                pyperclip.copy(new_value)
                last_clipboard = new_value
                print(f"Pano güncellendi: {new_value}")
            else:
                pyperclip.copy("_")
                last_clipboard = "_"
                print("Pano temizlendi.")
        except Exception as e:
            print(f"Pano temizleme hatası (görmezden geliniyor): {e}")
    if root and root.winfo_exists():
        root.after(50, safe_clear_clipboard)
        root.after(400, lambda: enable_clipboard_processing_after_delay(root))
    else:
        can_process_clipboard = True
        is_processing = False
    print("Menü kapatma işlemi tamamlandı (re-enable scheduled)")
# Yeni: İlaç menüsünü kapatma fonksiyonu
def close_drug_menu_window(root, reason="Bilinmiyor"):
    """İlaç menüsü penceresini kapatır ve ilgili durumları sıfırlar."""
    global drug_menu_window_active, active_drug_menu_window, is_processing, can_process_clipboard, last_drug_barcode
    if is_processing or not drug_menu_window_active:
        return
    print(f"İlaç menüsü kapatma işlemi başlatıldı (Sebep: {reason})")
    is_processing = True
    can_process_clipboard = False
    # --- ÖNEMLİ: Aktif kapatma zamanlayıcısını iptal et ---
    cancel_drug_menu_close_timer(root)
    if active_drug_menu_window and active_drug_menu_window.winfo_exists():
        try:
            active_drug_menu_window.destroy()
            print("İlaç menüsü penceresi yok edildi")
        except tk.TclError:
            print("İlaç menüsü penceresi zaten yok edilmiş.")
        except Exception as e:
            print(f"İlaç menüsü kapatma hatası: {e}")
    active_drug_menu_window = None
    drug_menu_window_active = False
    def safe_clear_clipboard():
        global last_clipboard
        try:
            # Mevcut panodaki içeriğin sonuna "-" ekle
            current = pyperclip.paste()
            if current:
                new_value = current + "-"
                pyperclip.copy(new_value)
                last_clipboard = new_value
                print(f"Pano güncellendi: {new_value}")
            else:
                pyperclip.copy("_")
                last_clipboard = "_"
                print("Pano temizlendi.")
        except Exception as e:
            print(f"Pano temizleme hatası (görmezden geliniyor): {e}")
    if root and root.winfo_exists():
        root.after(50, safe_clear_clipboard)
        root.after(400, lambda: enable_clipboard_processing_after_delay(root))
    else:
        can_process_clipboard = True
        is_processing = False
    print("İlaç menüsü kapatma işlemi tamamlandı")
def create_menu_window(root, tc_number, x, y):
    """TC numarası için menü penceresi oluşturur."""
    global menu_window_active, active_menu_window, is_processing, can_process_clipboard, menu_close_timer_id
    if is_processing:
        print("İşlem devam ediyor (is_processing=True), yeni menü açılmayacak")
        return
    if menu_window_active or (active_menu_window and active_menu_window.winfo_exists()):
        print("Menü zaten aktif veya mevcut, yeni menü açılmayacak")
        return
    print(f"Yeni menü oluşturuluyor: TC={tc_number}, Konum=({x},{y})")
    is_processing = True
    can_process_clipboard = False
    menu_window_active = True
    try:
        menu_win = tk.Toplevel(root)
        active_menu_window = menu_win
        menu_win.withdraw()
        menu_win.overrideredirect(True)
        menu_win.attributes('-topmost', True)
        try: menu_win.attributes("-toolwindow", True)
        except tk.TclError: pass
        menu_bg = "#f0f0f0"
        button_bg = menu_bg
        button_active_bg = "#e0e0e0"
        separator_color = "#cccccc"
        text_color = "#000000"
        menu_win.config(bg=menu_bg, highlightbackground=separator_color, highlightthickness=1)
        frame = tk.Frame(menu_win, bg=menu_bg)
        frame.pack(padx=1, pady=1)
        # --- Zamanlayıcı Fonksiyonları ---
        def auto_close_menu():
            """Zamanlayıcı dolduğunda menüyü kapatır."""
            global menu_close_timer_id, active_menu_window, menu_window_active
            print("Otomatik kapatma zamanlayıcısı tetiklendi.")
            menu_close_timer_id = None # Zamanlayıcı ID'sini sıfırla
            # Menü hala aktif ve mevcutsa kapat
            if menu_window_active and active_menu_window and active_menu_window.winfo_exists():
                close_menu_window(root, reason="Fare ayrıldı (zaman aşımı)")
            else:
                print("Zamanlayıcı tetiklendi ama menü zaten kapalı/yok.")
        def start_close_timer(event=None):
            """Fare ayrıldığında kapatma zamanlayıcısını başlatır."""
            global menu_close_timer_id
            # print("Fare ayrıldı (<Leave>), zamanlayıcı başlatılıyor...") # Debug
            cancel_menu_close_timer(root) # Önceki zamanlayıcıyı iptal et
            if root and root.winfo_exists():
                # 1000 ms = 1 saniye
                menu_close_timer_id = root.after(1000, auto_close_menu)
        def cancel_close_timer_on_enter(event=None):
            """Fare girdiğinde (<Enter>) kapatma zamanlayıcısını iptal eder."""
            # print("Fare girdi (<Enter>), zamanlayıcı iptal ediliyor...") # Debug
            cancel_menu_close_timer(root)
        # --- Widget'lar ---
        tc_label = tk.Label(frame, text=f"TC: {tc_number}", anchor='w', justify='left',
            bg=menu_bg, fg="#666666", padx=5, pady=3)
        tc_label.pack(fill='x')
        tc_label.bind("<Button-1>", lambda e: "break")
        tk.Frame(frame, height=1, bg=separator_color).pack(fill='x', pady=3)
        def execute_command(command, *args):
            # Komut çalışmadan önce menüyü kapatır (zamanlayıcıyı da iptal eder)
            close_menu_window(root, reason="Menü seçeneği seçildi")
            if root and root.winfo_exists():
                root.after(200, lambda: command(*args))
        new_btn = tk.Button(frame, text="Yeni Reçete", relief='flat', anchor='w', justify='left',
            bg=button_bg, activebackground=button_active_bg, fg=text_color,
            activeforeground=text_color, borderwidth=0, highlightthickness=0,
            padx=5, pady=3,
            command=lambda tc=tc_number: execute_command(open_new_prescription, tc))
        new_btn.pack(fill='x')
        # Lab Sorgu butonu ekle
        lab_btn = tk.Button(frame, text="Lab Sorgu", relief='flat', anchor='w', justify='left',
            bg=button_bg, activebackground=button_active_bg, fg=text_color,
            activeforeground=text_color, borderwidth=0, highlightthickness=0,
            padx=5, pady=3,
            command=lambda tc=tc_number: execute_command(send_lab_request, tc))
        lab_btn.pack(fill='x')
        
        # Obezite butonu
        obesity_btn = tk.Button(frame, text="Obezite", relief='flat', anchor='w', justify='left',
            bg=button_bg, activebackground=button_active_bg, fg=text_color,
            activeforeground=text_color, borderwidth=0, highlightthickness=0,
            padx=5, pady=3,
            command=lambda tc=tc_number: execute_command(open_obesity_window, tc))
        obesity_btn.pack(fill='x')
        
        # HT butonu
        ht_btn = tk.Button(frame, text="Hipertansiyon", relief='flat', anchor='w', justify='left',
            bg=button_bg, activebackground=button_active_bg, fg=text_color,
            activeforeground=text_color, borderwidth=0, highlightthickness=0,
            padx=5, pady=3,
            command=lambda tc=tc_number: execute_command(open_ht_window, tc))
        ht_btn.pack(fill='x')
        
        interactive_widgets = [new_btn, lab_btn, obesity_btn, ht_btn]  # Tüm butonları listeye ekledik
        prescriptions = get_prescriptions_for_tc(tc_number)
        if prescriptions:
            tk.Frame(frame, height=1, bg=separator_color).pack(fill='x', pady=3)
            for p_info in prescriptions[:3]:
                recete_kodu = p_info.get("recete_kodu", "ID Yok")
                result_id = p_info.get("result_id")
                if result_id:
                    pres_frame = tk.Frame(frame, bg=menu_bg)
                    pres_frame.pack(fill='x')
                    tk.Label(pres_frame, text=f"{recete_kodu}:", anchor='w', justify='left',
                        bg=menu_bg, fg="#333333", padx=5, pady=1).pack(side=tk.LEFT)
                    delete_btn = tk.Button(pres_frame, text="Sil", relief='flat',
                        bg=button_bg, activebackground=button_active_bg, fg='red',
                        activeforeground='red', borderwidth=0, highlightthickness=0,
                        padx=3, pady=1, font=("TkDefaultFont", 8),
                        command=lambda rid=result_id: execute_command(delete_prescription_page, rid))
                    delete_btn.pack(side=tk.RIGHT, padx=(0, 5))
                    print_btn = tk.Button(pres_frame, text="Yazdır", relief='flat',
                        bg=button_bg, activebackground=button_active_bg, fg=text_color,
                        activeforeground=text_color, borderwidth=0, highlightthickness=0,
                        padx=3, pady=1, font=("TkDefaultFont", 8),
                        command=lambda rid=result_id: execute_command(print_prescription, rid))
                    print_btn.pack(side=tk.RIGHT, padx=(0, 5))
                    interactive_widgets.extend([pres_frame, delete_btn, print_btn]) # Bu widget'lara girince de timer iptal olsun
                else:
                    tk.Label(frame, text=f"{recete_kodu} (ID Eksik)", anchor='w', justify='left',
                        bg=menu_bg, fg="#666666", padx=5, pady=3).pack(fill='x')
        tk.Frame(frame, height=1, bg=separator_color).pack(fill='x', pady=3)
        # Rapor butonları için çerçeve
        reports_frame = tk.Frame(frame, bg=menu_bg)
        reports_frame.pack(fill='x', pady=2)
        # E-Rapor butonu
        erapor_btn = tk.Button(reports_frame, text="E-Rapor", relief='flat',
            bg=button_bg, activebackground=button_active_bg, fg=text_color,
            activeforeground=text_color, borderwidth=0, highlightthickness=0,
            padx=5, pady=3,
            command=lambda tc=tc_number: execute_command(open_erapor, tc))
        erapor_btn.pack(side=tk.LEFT, fill='x', expand=True)
        # Reçetem Rapor butonu
        recetem_btn = tk.Button(reports_frame, text="Reçetem Rapor", relief='flat',
            bg=button_bg, activebackground=button_active_bg, fg=text_color,
            activeforeground=text_color, borderwidth=0, highlightthickness=0,
            padx=5, pady=3,
            command=lambda tc=tc_number: execute_command(open_recetem_report, tc))
        recetem_btn.pack(side=tk.LEFT, fill='x', expand=True)
        # İptal butonu için ayrı çerçeve
        tk.Frame(frame, height=1, bg=separator_color).pack(fill='x', pady=3)
        cancel_btn = tk.Button(frame, text="İptal", relief='flat', anchor='w', justify='left',
            bg=button_bg, activebackground=button_active_bg, fg=text_color,
            activeforeground=text_color, borderwidth=0, highlightthickness=0,
            padx=5, pady=3,
            # İptal butonu doğrudan kapatır, zamanlayıcıya gerek yok
            command=lambda: close_menu_window(root, reason="İptal butonu"))
        cancel_btn.pack(fill='x')
        # Etkileşimli widget'lar listesine yeni butonları ekle
        interactive_widgets.extend([reports_frame, erapor_btn, recetem_btn, cancel_btn])
        # --- Fare Giriş/Çıkış Olaylarını Bağlama ---
        print("Fare giriş/çıkış olayları bağlanıyor...")
        # Ana pencere ve çerçeve için olaylar
        menu_win.bind("<Enter>", cancel_close_timer_on_enter)
        menu_win.bind("<Leave>", start_close_timer)
        frame.bind("<Enter>", cancel_close_timer_on_enter) # Çerçeveye girince de iptal
        frame.bind("<Leave>", start_close_timer)      # Çerçeveden çıkınca başlat (pencereden çıkmayla aynı olabilir)
        # Etkileşimli iç widget'lar için <Enter> olayı (zamanlayıcıyı iptal etmek için)
        for widget in interactive_widgets:
            # Widget hala varsa bağla
            if widget and widget.winfo_exists():
                widget.bind("<Enter>", cancel_close_timer_on_enter)
                # Bu widget'lardan ayrılınca ana pencerenin <Leave>'i tetiklenmeli,
                # o yüzden bunlara <Leave> bağlamıyoruz.
        print("Fare olayları bağlandı.")
        # --- Show Window ---
        menu_win.update_idletasks()
        # Get window dimensions after all widgets are packed
        menu_win.update_idletasks()  # Make sure geometry info is updated
        win_width = menu_win.winfo_reqwidth()
        # Position the window so TC label is just below the mouse cursor
        # Center the window horizontally with the mouse cursor
        new_x = x - (win_width // 2)  # Center window horizontally with cursor
        new_y = y - 25  # Position window just below cursor
        # Ensure window stays on screen (assuming 0,0 is top-left)
        if new_x < 0:
            new_x = 0
        menu_win.geometry(f'+{new_x}+{new_y}')
        menu_win.deiconify()
        menu_win.focus_force()
        print(f"Menü penceresi başarıyla oluşturuldu ve gösterildi (konum: {new_x},{new_y}, genişlik: {win_width})")
    except Exception as e:
        print(f"Menü penceresi oluşturma/gösterme hatası: {e}")
        # Hata durumunda temizlik
        if active_menu_window and active_menu_window.winfo_exists():
            try: active_menu_window.destroy()
            except: pass
        active_menu_window = None
        menu_window_active = False
        cancel_menu_close_timer(root) # Hata durumunda timer'ı iptal et
        is_processing = False
        can_process_clipboard = True
        return
    is_processing = False # Oluşturma bitti, işlemeyi serbest bırak
    # Clipboard işlemini hemen etkinleştirmeyelim, enable_clipboard_processing_after_delay yapacak
    # can_process_clipboard = True # Bu satır kaldırıldı
    # --- Ana Program ---
def main():
    """Ana program başlangıç noktası."""
    print("TC Kimlik numarası ve İlaç Barkodu izleyici başlatıldı (Fare Takibi Sürüm)...")
    print("Panoya 11 haneli TC kimlik numarası kopyalandığında TC menüsü gösterilecek.")
    print("Panoya 13/14 haneli ilaç barkodu kopyalandığında ilaç menüsü gösterilecek.")
    print("Fare menüden ayrıldıktan 1sn sonra menü otomatik kapanacaktır.")
    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-alpha", 0.0)
        root.attributes("-toolwindow", True)
        root.attributes("-topmost", True)
    except tk.TclError:
        print("Uyarı: Özel pencere öznitelikleri ayarlanamadı.")
        pass
    global last_clipboard, can_process_clipboard, is_processing, menu_window_active, active_menu_window, menu_close_timer_id
    global drug_menu_window_active, active_drug_menu_window, drug_menu_close_timer_id, last_drug_barcode
    try:
        last_clipboard_raw = pyperclip.paste()
        last_clipboard = last_clipboard_raw if last_clipboard_raw is not None else ""
    except Exception as e:
        print(f"Başlangıçta pano okunamadı (görmezden geliniyor): {e}")
        last_clipboard = ""
    can_process_clipboard = True
    is_processing = False
    menu_window_active = False
    active_menu_window = None
    menu_close_timer_id = None
    # İlaç menüsü değişkenleri
    drug_menu_window_active = False
    active_drug_menu_window = None
    drug_menu_close_timer_id = None
    last_drug_barcode = ""
    print("Pano denetimi başlatılıyor...")
    root.after(750, lambda: check_clipboard(root))
    def on_close():
        print("\nKapatma isteği alındı (on_close)...")
        global clipboard_check_id, active_menu_window, active_drug_menu_window, root, is_processing
        is_processing = True
        can_process_clipboard = False
        # Zamanlayıcıları iptal et
        cancel_menu_close_timer(root) # TC Menü kapatma zamanlayıcısı
        cancel_drug_menu_close_timer(root) # İlaç Menü kapatma zamanlayıcısı
        if clipboard_check_id:
            try:
                if root and root.winfo_exists(): root.after_cancel(clipboard_check_id)
                clipboard_check_id = None
                print("Pano denetimi durduruldu.")
            except: pass
        # TC Menüsünü kapat
        if menu_window_active and active_menu_window and active_menu_window.winfo_exists():
            print("Aktif TC menü penceresi kapatılıyor...")
            try:
                active_menu_window.destroy()
                active_menu_window = None
                menu_window_active = False
                print("TC menü penceresi kapatıldı.")
            except Exception as e:
                print(f"TC menü kapatma hatası: {e}")
        # İlaç Menüsünü kapat
        if drug_menu_window_active and active_drug_menu_window and active_drug_menu_window.winfo_exists():
            print("Aktif ilaç menü penceresi kapatılıyor...")
            try:
                active_drug_menu_window.destroy()
                active_drug_menu_window = None
                drug_menu_window_active = False
                print("İlaç menü penceresi kapatıldı.")
            except Exception as e:
                print(f"İlaç menü kapatma hatası: {e}")
        print("Ana pencere kapatılıyor...")
        if root and root.winfo_exists():
            try: root.destroy()
            except tk.TclError as e: print(f"Ana pencere kapatılırken hata: {e}")
        else: print("Ana pencere zaten kapatılmış.")
    # Kapatma düğmesi protokolü
    root.protocol("WM_DELETE_WINDOW", on_close)
    try:
        print("Ana döngü başlatıldı. Çıkmak için Ctrl+C basın.")
        root.mainloop()
        print("Mainloop normal şekilde sona erdi.")
    except KeyboardInterrupt:
        print("\nProgram Ctrl+C ile kesildi.")
        on_close()
    except Exception as e:
        print(f"\nAna döngüde beklenmedik hata: {e}")
        import traceback
        traceback.print_exc()  # Hata ayrıntılarını yazdır
        on_close()
    finally:
        print("Program sonlandırılıyor (finally bloğu)...")
        # Ekstra güvenlik: Kalan pencere veya zamanlayıcıları temizlemeye çalış
        cancel_menu_close_timer(root)
        cancel_drug_menu_close_timer(root)
        # TC menüsünü kapat
        if active_menu_window and hasattr(active_menu_window,'winfo_exists') and active_menu_window.winfo_exists():
            try: active_menu_window.destroy()
            except: pass
        # İlaç menüsünü kapat
        if active_drug_menu_window and hasattr(active_drug_menu_window,'winfo_exists') and active_drug_menu_window.winfo_exists():
            try: active_drug_menu_window.destroy()
            except: pass
        # Ana pencereyi kapat
        if root and hasattr(root,'winfo_exists') and root.winfo_exists():
            try: root.destroy()
            except: pass
        print("Program sonlandırıldı.")
# ilaç menüsü penceresi oluşturma fonksiyonu eksik
# Yeni: JSON dosyasından ilaç ATC bilgisini alma fonksiyonu
def get_drug_from_json(barcode):
    """
    data/ilaclar.json dosyasından barkoda göre ilaç bilgilerini getirir.
    """
    try:
        # Barkodu string olarak normalize et
        barcode_str = str(barcode).strip()
        if len(barcode_str) == 14 and barcode_str.startswith('0'):
            barcode_str = barcode_str[1:]  # Baştaki 0'ı kaldır
        # Test verileri - gerçek dosya olmadan çalışması için
        test_drugs = [
            {
                "barcode": "8681308961235",
                "name": "ABRYSVO 0.5 ML IM ENJEKSIYONLUK COZELTI HAZIRLAMAK ICIN TOZ VE COZUCU (1 ADET)",
                "ingredients": "",
                "atc_code": "J07BX05",
                "atc_name": "respiratory syncytial virus vaccines",
                "update_date": "2025-04-28"
            },
            {
                "barcode": "8699591150397",
                "name": "CEFORIST 300 MG SERT KAPSUL (10 KASUL)",
                "ingredients": "",
                "atc_code": "J01DD15",
                "atc_name": "cefdinir",
                "update_date": "2025-04-28"
            },
            {
                "barcode": "8683555350022",
                "name": "EXOVAG 750MG/200MG/100MG VAJINAL TABLET (7 TABLET)",
                "ingredients": "",
                "atc_code": "G01AF20",
                "atc_name": "combinations of imidazole derivatives",
                "update_date": "2025-04-28"
            }
        ]
        # JSON dosyasını önce kontrol et
        json_path = "data/ilaclar.json"
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    drugs = json.load(f)
                    if isinstance(drugs, list) and len(drugs) > 0:
                        # Gerçek dosyadan veri oku
                        for drug in drugs:
                            if isinstance(drug, dict):
                                # Barcode alanı "barcode" olarak geçiyor
                                drug_barcode = str(drug.get("barcode", "")).strip()
                                if drug_barcode == barcode_str:
                                    return drug
            except Exception as e:
                print(f"JSON dosyası okuma hatası: {e}, test verileri kullanılacak")
        # Gerçek dosya yoksa veya okuma hatası olduysa test verilerini kullan
        for drug in test_drugs:
            if str(drug.get("barcode", "")).strip() == barcode_str:
                return drug
        print(f"İlaç bilgisi bulunamadı: {barcode}")
        return None
    except Exception as e:
        print(f"İlaç bilgisi okuma hatası: {str(e)}")
        return None
# İlaç menüsü penceresi oluşturma fonksiyonunda değişiklik
# ICD-10 kodlarının sıralamasını belirleme fonksiyonu
def get_icd_order_from_json():
    """
    icd10top.json dosyasından ICD kodlarının sıralama bilgisini getirir.
    Dosya yoksa veya okunamazsa boş bir sözlük döndürür.
    """
    try:
        json_path = "data/icd10top.json"
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data
        else:
            print(f"ICD sıralama dosyası bulunamadı: {json_path}")
            return {}
    except Exception as e:
        print(f"ICD sıralama dosyası okuma hatası: {str(e)}")
        return {}
# ICD-10 kodlarının sıralamasını belirleme fonksiyonu
def get_icd_order_from_json():
    """
    icd10top.json dosyasından ICD kodlarının sıralama bilgisini getirir.
    Dosya yoksa veya okunamazsa boş bir sözlük döndürür.
    """
    try:
        json_path = "data/icd10top.json"
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Sıralama bilgisini döndür
                # Beklenen format: {"J12.1": 1, "J20.5": 2, ...} şeklinde
                return data
        else:
            print(f"ICD sıralama dosyası bulunamadı: {json_path}")
            return {}
    except Exception as e:
        print(f"ICD sıralama dosyası okuma hatası: {str(e)}")
        return {}
# ICD kodlarını sıralama fonksiyonu
def sort_icd_codes(icd_codes):
    """
    ICD kodlarını icd10top.json'daki sıralamaya göre düzenler.
    Dosyada olmayan kodlar alfabetik olarak sıralanır.
    """
    try:
        # Sıralama bilgilerini al
        order_dict = get_icd_order_from_json()
        if not order_dict:
            # Sıralama bilgisi yoksa alfabetik sırala
            return sorted(icd_codes)
        # Sıralama bilgisi olan ve olmayan kodları ayır
        ordered_codes = []
        unordered_codes = []
        for code in icd_codes:
            if code in order_dict:
                ordered_codes.append((code, order_dict[code]))
            else:
                unordered_codes.append(code)
        # Sıralama bilgisi olanları sırala
        ordered_codes.sort(key=lambda x: x[1])
        # Sıralı kodlar + alfabetik sıralı diğer kodlar
        result = [code for code, _ in ordered_codes] + sorted(unordered_codes)
        return result
    except Exception as e:
        print(f"ICD kodları sıralama hatası: {str(e)}")
        # Hata durumunda orijinal listeyi alfabetik sırala
        return sorted(icd_codes)
# ATC-ICD eşleştirmelerini güncelleme fonksiyonu
def update_atc_icd_mapping(atc_code, icd_codes, mode="add"):
    """
    ATC-ICD eşleştirmelerini günceller.
    Parametreler:
    - atc_code: Güncellenecek ATC kodu
    - icd_codes: ICD kodları listesi
    - mode: "add" (ekleme), "remove" (silme) veya "replace" (tümünü değiştirme)
    Dönüş değeri:
    - Başarı durumu (True/False)
    """
    try:
        json_path = "data/atc_icd_mapping.json"
        mapping_data = {"atc_to_icd": {}}
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if content:
                        mapping_data = json.loads(content)
            except Exception as e:
                print(f"ATC-ICD mapping dosyası okuma hatası: {e}")
                return False
        if "atc_to_icd" not in mapping_data:
            mapping_data["atc_to_icd"] = {}
        formatted_atc_code = atc_code
        if not atc_code.endswith('*'):
            atc_level = len(atc_code.strip())
            if atc_level < 7:
                formatted_atc_code = f"{atc_code}*"
        if mode == "add":
            current_codes = mapping_data["atc_to_icd"].get(formatted_atc_code, [])
            updated_codes = list(set(current_codes + icd_codes))
            mapping_data["atc_to_icd"][formatted_atc_code] = updated_codes
        elif mode == "remove":
            if formatted_atc_code in mapping_data["atc_to_icd"]:
                current_codes = mapping_data["atc_to_icd"][formatted_atc_code]
                updated_codes = [code for code in current_codes if code not in icd_codes]
                mapping_data["atc_to_icd"][formatted_atc_code] = updated_codes
        elif mode == "replace":
            mapping_data["atc_to_icd"][formatted_atc_code] = icd_codes
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(mapping_data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"ATC-ICD eşleştirme güncelleme hatası: {str(e)}")
        return False
# Seçilen ICD kodunu silme fonksiyonu
def move_icd_code(atc_code, icd_code, direction):
    """
    ICD kodunun sırasını yukarı veya aşağı taşır.
    Parametreler:
    - atc_code: ATC kodu
    - icd_code: Taşınacak ICD kodu
    - direction: "up" veya "down"
    Dönüş değeri:
    - Başarı durumu (True/False)
    """
    try:
        print(f"ICD kodu taşınacak: {icd_code} - Yön: {direction}")
        return True
    except Exception as e:
        print(f"ICD kodu taşıma hatası: {str(e)}")
        return False
# ICD kodları için yukarı/aşağı taşıma fonksiyonu
def move_icd_code(atc_code, icd_code, direction):
    """
    ICD kodunun sırasını yukarı veya aşağı taşır.
    Parametreler:
    - atc_code: ATC kodu
    - icd_code: Taşınacak ICD kodu
    - direction: "up" veya "down"
    Dönüş değeri:
    - Başarı durumu (True/False)
    """
    try:
        # Bu fonksiyon şu anda sadece yer tutucu
        # Gerçek implementasyon için daha sonra doldurulacak
        print(f"ICD kodu taşınacak: {icd_code} - Yön: {direction}")
        return True
    except Exception as e:
        print(f"ICD kodu taşıma hatası: {str(e)}")
        return False
# Yeni ATC-ICD eşleştirme penceresi oluşturma fonksiyonu
# Yeni ATC-ICD eşleştirme penceresi oluşturma fonksiyonu
def create_atc_icd_mapping_window(parent, atc_code, atc_name=""):
    """
    Yeni ATC-ICD eşleştirme penceresi oluşturur.
    Parametreler:
    - parent: Üst pencere
    - atc_code: ATC kodu
    - atc_name: ATC kodu adı (opsiyonel)
    """
    global atc_icd_mapping_window_open
    try:
        atc_icd_mapping_window_open = True
        mapping_win = tk.Toplevel(parent)
        mapping_win.title("ATC-ICD Eşleştirme")
        mapping_win.geometry("600x500")
        mapping_win.transient(parent)
        mapping_win.grab_set()
        
        # Pencere kapandığında flag'i sıfırla
        def on_window_close():
            global atc_icd_mapping_window_open
            atc_icd_mapping_window_open = False
            try:
                mapping_win.destroy()
            except:
                pass
        
        mapping_win.protocol("WM_DELETE_WINDOW", on_window_close)
        main_frame = tk.Frame(mapping_win, padx=10, pady=10)
        main_frame.pack(fill='both', expand=True)
        atc_frame = tk.Frame(main_frame)
        atc_frame.pack(fill='x', pady=(0, 10))
        tk.Label(atc_frame, text="ATC Kodu:").grid(row=0, column=0, sticky='w')
        tk.Label(atc_frame, text=atc_code, font=("TkDefaultFont", 9, "bold")).grid(row=0, column=1, sticky='w')
        if atc_name:
            tk.Label(atc_frame, text="ATC Adı:").grid(row=1, column=0, sticky='w')
            tk.Label(atc_frame, text=atc_name).grid(row=1, column=1, sticky='w')
        search_frame = tk.Frame(main_frame)
        search_frame.pack(fill='both', expand=True)
        search_box_frame = tk.Frame(search_frame)
        search_box_frame.pack(fill='x', pady=(0, 5))
        tk.Label(search_box_frame, text="ICD-10 Ara:").pack(side=tk.LEFT)
        search_var = tk.StringVar()
        search_entry = tk.Entry(search_box_frame, textvariable=search_var, width=40)
        search_entry.pack(side=tk.LEFT, padx=(5, 0))
        results_frame = tk.Frame(search_frame)
        results_frame.pack(fill='both', expand=True)
        tk.Label(results_frame, text="Arama Sonuçları:").pack(anchor='w')
        listbox_frame = tk.Frame(results_frame)
        listbox_frame.pack(fill='both', expand=True, pady=(5, 10))
        scrollbar = tk.Scrollbar(listbox_frame)
        scrollbar.pack(side=tk.RIGHT, fill='y')
        results_listbox = tk.Listbox(listbox_frame, yscrollcommand=scrollbar.set, height=15)
        results_listbox.pack(side=tk.LEFT, fill='both', expand=True)
        scrollbar.config(command=results_listbox.yview)
        search_results = []
        def search_icd():
            results_listbox.delete(0, tk.END)
            search_results.clear()
            search_text = search_var.get().strip().lower()
            if not search_text:
                return
            json_path = "data/icd10turk.json"
            if os.path.exists(json_path):
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        icd_data = json.load(f)
                        for item in icd_data:
                            if "ICD KODU" in item and "TANI" in item:
                                icd_code = item["ICD KODU"].strip()
                                desc = item["TANI"].strip()
                                if (search_text in icd_code.lower() or search_text in desc.lower()):
                                    display_text = f"{icd_code} - {desc}"
                                    results_listbox.insert(tk.END, display_text)
                                    search_results.append((icd_code, desc))
                except Exception as e:
                    print(f"ICD arama hatası: {e}")
            else:
                print(f"ICD tanımları dosyası bulunamadı: {json_path}")
                test_data = [
                    {"ICD KODU": "J12.1", "TANI": "Respiratuar sinsisyal virüs (RSV)'a bağlı pnömoni"},
                    {"ICD KODU": "J20.5", "TANI": "Solunum sinsisyal virüsü'ne bağlı akut bronşit"},
                    {"ICD KODU": "N39.0", "TANI": "Üriner sistem enfeksiyonu, yeri tanımlanmamış"}
                ]
                for item in test_data:
                    icd_code = item["ICD KODU"].strip()
                    desc = item["TANI"].strip()
                    if (search_text in icd_code.lower() or search_text in desc.lower()):
                        display_text = f"{icd_code} - {desc}"
                        results_listbox.insert(tk.END, display_text)
                        search_results.append((icd_code, desc))
        search_button = tk.Button(search_box_frame, text="Ara", command=search_icd)
        search_button.pack(side=tk.LEFT, padx=(5, 0))
        search_entry.bind("<Return>", lambda event: search_icd())
        button_frame = tk.Frame(main_frame)
        button_frame.pack(fill='x', pady=(10, 0))
        def add_selected_icd():
            selection = results_listbox.curselection()
            if not selection:
                messagebox.showwarning("Uyarı", "Lütfen bir ICD kodu seçin.")
                return
            idx = selection[0]
            if idx < len(search_results):
                icd_code = search_results[idx][0]
                if update_atc_icd_mapping(atc_code, [icd_code], mode="add"):
                    messagebox.showinfo("Başarılı", f"ICD kodu {icd_code} başarıyla eklendi.")
                    on_window_close()
                else:
                    messagebox.showerror("Hata", "ICD kodu eklenirken bir hata oluştu.")
        add_button = tk.Button(button_frame, text="Seçili ICD Kodunu Ekle", command=add_selected_icd)
        add_button.pack(side=tk.LEFT, padx=(0, 5))
        cancel_button = tk.Button(button_frame, text="İptal", command=on_window_close)
        cancel_button.pack(side=tk.RIGHT)
        mapping_win.focus_set()
        search_entry.focus()
    except Exception as e:
        print(f"ATC-ICD eşleştirme penceresi oluşturma hatası: {str(e)}")
# İlaç menüsü penceresi oluşturma fonksiyonunu güncelle
# İlaç menüsü penceresi oluşturma fonksiyonu
def create_drug_menu_window(root, barcode, x, y):
    """Barkod numarası için ilaç menüsü penceresi oluşturur."""
    global drug_menu_window_active, active_drug_menu_window, is_processing, can_process_clipboard, drug_menu_close_timer_id
    if is_processing:
        print("İşlem devam ediyor (is_processing=True), yeni ilaç menüsü açılmayacak")
        return
    if drug_menu_window_active or (active_drug_menu_window and active_drug_menu_window.winfo_exists()):
        print("İlaç menüsü zaten aktif veya mevcut, yeni menü açılmayacak")
        return
    # Barkodun 13 haneli olmasını sağlayalım
    normalized_barcode = barcode
    if len(barcode) == 14 and barcode.startswith('0'):
        normalized_barcode = barcode[1:]  # Baştaki 0'ı kaldır
    print(f"Yeni ilaç menüsü oluşturuluyor: Barkod={barcode}, Normalize={normalized_barcode}, Konum=({x},{y})")
    is_processing = True
    can_process_clipboard = False
    drug_menu_window_active = True
    try:
        drug_menu_win = tk.Toplevel(root)
        active_drug_menu_window = drug_menu_win
        drug_menu_win.withdraw()
        drug_menu_win.overrideredirect(True)
        drug_menu_win.attributes('-topmost', True)
        try:
            drug_menu_win.attributes("-toolwindow", True)
        except tk.TclError:
            pass
        menu_bg = "#f0f0f0"
        button_bg = menu_bg
        button_active_bg = "#e0e0e0"
        separator_color = "#cccccc"
        text_color = "#000000"
        drug_menu_win.config(bg=menu_bg, highlightbackground=separator_color, highlightthickness=1)
        frame = tk.Frame(drug_menu_win, bg=menu_bg)
        frame.pack(padx=1, pady=1)
        # --- Zamanlayıcı Fonksiyonları ---
        def auto_close_drug_menu():
            """Zamanlayıcı dolduğunda ilaç menüsünü kapatır."""
            global drug_menu_close_timer_id, active_drug_menu_window, drug_menu_window_active, atc_icd_mapping_window_open
            print("İlaç menüsü otomatik kapatma zamanlayıcısı tetiklendi.")
            drug_menu_close_timer_id = None  # Zamanlayıcı ID'sini sıfırla
            # ATC-ICD eşleştirme penceresi açıksa menüyü kapatma
            if atc_icd_mapping_window_open:
                print("İlaç menüsü kapatma iptal edildi (Sebep: ATC-ICD eşleştirme penceresi açık)")
                return
            # Menü hala aktif ve mevcutsa kapat
            if drug_menu_window_active and active_drug_menu_window and active_drug_menu_window.winfo_exists():
                close_drug_menu_window(root, reason="Fare ayrıldı (zaman aşımı)")
            else:
                print("İlaç menüsü zamanlayıcısı tetiklendi ama menü zaten kapalı/yok.")
        def start_drug_close_timer(event=None):
            """Fare ayrıldığında ilaç menüsü kapatma zamanlayıcısını başlatır."""
            global drug_menu_close_timer_id
            # print("Fare ayrıldı (<Leave>), zamanlayıcı başlatılıyor...") # Debug
            cancel_drug_menu_close_timer(root)  # Önceki zamanlayıcıyı iptal et
            if root and root.winfo_exists():
                # 1000 ms = 1 saniye
                drug_menu_close_timer_id = root.after(1000, auto_close_drug_menu)
        def cancel_drug_close_timer_on_enter(event=None):
            """Fare girdiğinde (<Enter>) ilaç menüsü kapatma zamanlayıcısını iptal eder."""
            # print("Fare girdi (<Enter>), zamanlayıcı iptal ediliyor...") # Debug
            cancel_drug_menu_close_timer(root)
        # --- Widget'lar ---
        # İlaç bilgilerini almaya çalış
        drug_info = get_drug_info(barcode)
        # JSON dosyasından ATC bilgilerini al
        json_drug_info = get_drug_from_json(barcode)
        # İlaç adı ve barkod bilgisi göster
        barcode_label = tk.Label(frame, text=f"Barkod: {normalized_barcode}", anchor='w', justify='left',
            bg=menu_bg, fg="#666666", padx=5, pady=3)
        barcode_label.pack(fill='x')
        barcode_label.bind("<Button-1>", lambda e: "break")
        if drug_info:
            drug_name = drug_info.get("ilac_adi", "Bilinmiyor")
            drug_name_label = tk.Label(frame, text=f"İlaç: {drug_name}", anchor='w', justify='left',
                bg=menu_bg, fg="#000000", font=("TkDefaultFont", 9, "bold"), padx=5, pady=3)
            drug_name_label.pack(fill='x')
            drug_name_label.bind("<Button-1>", lambda e: "break")
        elif json_drug_info:
            drug_name = json_drug_info.get("name", "Bilinmiyor")
            drug_name_label = tk.Label(frame, text=f"İlaç: {drug_name}", anchor='w', justify='left',
                bg=menu_bg, fg="#000000", font=("TkDefaultFont", 9, "bold"), padx=5, pady=3)
            drug_name_label.pack(fill='x')
            drug_name_label.bind("<Button-1>", lambda e: "break")
        # ATC bilgilerini ve eşleşen ICD kodlarını sakla
        atc_code = ""
        atc_name = ""
        # JSON'dan ATC bilgilerini göster
        if json_drug_info:
            # ATC Kodu ve Adı bilgilerini ekle
            atc_code = json_drug_info.get("atc_code", "").strip()
            atc_name = json_drug_info.get("atc_name", "").strip()
            if atc_code or atc_name:
                tk.Frame(frame, height=1, bg=separator_color).pack(fill='x', pady=1)
                if atc_code:
                    atc_code_label = tk.Label(frame, text=f"ATC Kodu: {atc_code}", anchor='w', justify='left',
                        bg=menu_bg, fg="#333333", padx=5, pady=2)
                    atc_code_label.pack(fill='x')
                if atc_name:
                    atc_name_label = tk.Label(frame, text=f"ATC Adı: {atc_name}", anchor='w', justify='left',
                        bg=menu_bg, fg="#333333", padx=5, pady=2)
                    atc_name_label.pack(fill='x')
        tk.Frame(frame, height=1, bg=separator_color).pack(fill='x', pady=3)
        # ATC koduna göre ICD-10 kodlarını getir
        if atc_code:
            # İlk olarak, düşük ya da orta seviyeli ATC kodu tamamlama kontrolü
            if len(atc_code) < 7 and not atc_code.endswith('*'):
                atc_search_code = f"{atc_code}*"
            else:
                atc_search_code = atc_code
            icd_codes = get_icd_codes_for_atc(atc_search_code)
            # ICD kodlarını sırala
            sorted_icd_codes = sort_icd_codes(icd_codes)
            # YENİ: ATC-ICD Eşleştirme Düğmesi
            atc_icd_button_frame = tk.Frame(frame, bg=menu_bg)
            atc_icd_button_frame.pack(fill='x', padx=5, pady=(0, 5))
            add_atc_icd_btn = tk.Button(
                atc_icd_button_frame,
                text="Yeni ATC-ICD Eşleştirme",
                command=lambda: create_atc_icd_mapping_window(drug_menu_win, atc_code, atc_name),
                bg="#e0e8f0", activebackground="#d0d8e0",
                relief="raised", borderwidth=1,
                padx=5, pady=2
            )
            add_atc_icd_btn.pack(side=tk.LEFT, fill='x', expand=True)
            if sorted_icd_codes:
                # ICD kodları için başlık
                icd_title_label = tk.Label(frame, text="ICD-10 Kodları:", anchor='w', justify='left',
                    bg=menu_bg, fg="#333333", font=("TkDefaultFont", 9, "bold"), padx=5, pady=2)
                icd_title_label.pack(fill='x')
                # ICD kodları için kaydırılabilir çerçeve
                icd_container_frame = tk.Frame(frame, bg=menu_bg, highlightbackground="#cccccc", highlightthickness=1)
                icd_container_frame.pack(fill='x', padx=5, pady=2, expand=True)
                # Kaydırma çubuğu
                icd_canvas = tk.Canvas(icd_container_frame, bg=menu_bg, height=150, highlightthickness=0)
                scrollbar = ttk.Scrollbar(icd_container_frame, orient="vertical", command=icd_canvas.yview)
                # Canvas ve scrollbar düzeni
                icd_canvas.pack(side=tk.LEFT, fill='both', expand=True)
                scrollbar.pack(side=tk.RIGHT, fill='y')
                icd_canvas.configure(yscrollcommand=scrollbar.set)
                # İçerik frame'i
                icd_content_frame = tk.Frame(icd_canvas, bg=menu_bg)
                icd_canvas.create_window((0, 0), window=icd_content_frame, anchor='nw')
                # ICD kodları ve tanımlarını ekle
                for i, icd_code in enumerate(sorted_icd_codes):
                    # Her kod için bir çerçeve
                    code_frame = tk.Frame(icd_content_frame, bg=menu_bg, bd=0)
                    code_frame.pack(fill='x', pady=1, anchor='w')
                    # ICD kodu tanımını al
                    icd_description = get_icd_description(icd_code)
                    # Kod etiketi
                    code_label = tk.Label(code_frame, text=icd_code,
                        bg="#e8e8e8", fg="#0066cc",
                        width=7, padx=5, pady=2, anchor='w',
                        relief="ridge", cursor="hand2")
                    code_label.pack(side=tk.LEFT, padx=(0, 2))
                    # Tanım etiketi - uzun tanımları kısalt
                    desc_text = icd_description if icd_description else "Tanım bulunamadı"
                    if len(desc_text) > 40:
                        desc_text = desc_text[:37] + "..."
                    desc_label = tk.Label(code_frame, text=desc_text,
                        bg=menu_bg, fg="#333333",
                        padx=2, pady=2, anchor='w', justify='left')
                    desc_label.pack(side=tk.LEFT, fill='x', expand=True)
                    # YENİ: Düğmeler için çerçeve
                    buttons_frame = tk.Frame(code_frame, bg=menu_bg)
                    buttons_frame.pack(side=tk.RIGHT, padx=(2, 0))
                    # YENİ: Yukarı/Aşağı Düğmeleri
                    up_button = tk.Button(
                        buttons_frame, text="↑", width=1, height=1,
                        command=lambda c=icd_code: move_icd_code(atc_code, c, "up"),
                        bg="#f0f0f0", activebackground="#e0e0e0",
                        relief="flat", borderwidth=0, padx=2, pady=0,
                        font=("TkDefaultFont", 8)
                    )
                    up_button.pack(side=tk.LEFT)
                    down_button = tk.Button(
                        buttons_frame, text="↓", width=1, height=1,
                        command=lambda c=icd_code: move_icd_code(atc_code, c, "down"),
                        bg="#f0f0f0", activebackground="#e0e0e0",
                        relief="flat", borderwidth=0, padx=2, pady=0,
                        font=("TkDefaultFont", 8)
                    )
                    down_button.pack(side=tk.LEFT)
                    # YENİ: Düzenle Düğmesi
                    edit_button = tk.Button(
                        buttons_frame, text="✎", width=1, height=1,
                        command=lambda c=icd_code: create_atc_icd_mapping_window(drug_menu_win, atc_code, atc_name),
                        bg="#f0f0f0", activebackground="#e0e0e0",
                        relief="flat", borderwidth=0, padx=2, pady=0,
                        font=("TkDefaultFont", 8)
                    )
                    edit_button.pack(side=tk.LEFT)
                    # YENİ: Sil Düğmesi
                    delete_button = tk.Button(
                        buttons_frame, text="✕", width=1, height=1,
                        command=lambda c=icd_code: confirm_and_remove_icd(atc_code, c, drug_menu_win),
                        bg="#f0f0f0", activebackground="#e0e0e0", fg="red",
                        relief="flat", borderwidth=0, padx=2, pady=0,
                        font=("TkDefaultFont", 8)
                    )
                    delete_button.pack(side=tk.LEFT)
                    # Kod etiketine tıklama olayları
                    code_label.bind("<Button-1>", lambda e, code=icd_code, lbl=code_label: copy_to_clipboard(code, lbl))
                    # Mouse over efekti
                    code_label.bind("<Enter>", lambda e, lbl=code_label: lbl.config(bg="#d0d0ff"))
                    code_label.bind("<Leave>", lambda e, lbl=code_label: lbl.config(bg="#e8e8e8"))
                # Scroll frame'i yapılandır
                def on_frame_configure(event):
                    icd_canvas.configure(scrollregion=icd_canvas.bbox("all"))
                icd_content_frame.bind("<Configure>", on_frame_configure)
                # Farenin canvas üzerindeki tekerleği
                def on_mousewheel(event):
                    icd_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                # Windows
                icd_canvas.bind_all("<MouseWheel>", on_mousewheel)
                # Linux
                icd_canvas.bind_all("<Button-4>", lambda e: icd_canvas.yview_scroll(-1, "units"))
                icd_canvas.bind_all("<Button-5>", lambda e: icd_canvas.yview_scroll(1, "units"))
                # Ayırıcı çizgi
                tk.Frame(frame, height=1, bg=separator_color).pack(fill='x', pady=3)
            def execute_drug_command(command, *args):
                # Komut çalışmadan önce menüyü kapatır (zamanlayıcıyı da iptal eder)
                close_drug_menu_window(root, reason="İlaç menüsü seçeneği seçildi")
                if root and root.winfo_exists():
                    root.after(200, lambda: command(*args))
            # İlaç arama butonu
            search_btn = tk.Button(frame, text="İlaç Ara", relief='flat', anchor='w', justify='left',
                bg=button_bg, activebackground=button_active_bg, fg=text_color,
                activeforeground=text_color, borderwidth=0, highlightthickness=0,
                padx=5, pady=3,
                command=lambda bc=normalized_barcode: execute_drug_command(open_drug_search, bc))
            search_btn.pack(fill='x')
            # İlaç ekleme butonu
            add_btn = tk.Button(frame, text="İlaç Ekle", relief='flat', anchor='w', justify='left',
                bg=button_bg, activebackground=button_active_bg, fg=text_color,
                activeforeground=text_color, borderwidth=0, highlightthickness=0,
                padx=5, pady=3,
                command=lambda bc=normalized_barcode: execute_drug_command(open_drug_add, bc))
            add_btn.pack(fill='x')
            # Doz ayarlama butonu
            dose_btn = tk.Button(frame, text="Doz Ayarla", relief='flat', anchor='w', justify='left',
                bg=button_bg, activebackground=button_active_bg, fg=text_color,
                activeforeground=text_color, borderwidth=0, highlightthickness=0,
                padx=5, pady=3,
                command=lambda bc=normalized_barcode: execute_drug_command(open_drug_dose, bc))
            dose_btn.pack(fill='x')
            interactive_widgets = [search_btn, add_btn, dose_btn]
            # ICD butonlarını da interactive_widgets listesine ekle
            if atc_code:
                if 'add_atc_icd_btn' in locals():
                    interactive_widgets.append(add_atc_icd_btn)
                # Her bir ICD kodu için butonları interactive_widgets listesine ekle
                if 'sorted_icd_codes' in locals() and sorted_icd_codes:
                    for widget in icd_content_frame.winfo_children():
                        for child_widget in widget.winfo_children():
                            if isinstance(child_widget, tk.Button):
                                interactive_widgets.append(child_widget)
        # İlaç bilgileri mevcut ise ek detaylar göster
        if drug_info:
            tk.Frame(frame, height=1, bg=separator_color).pack(fill='x', pady=3)
            # İlaç detayları
            details_frame = tk.Frame(frame, bg=menu_bg)
            details_frame.pack(fill='x', padx=5, pady=3)
            # Kutu/Tablet ve Fiyat Bilgisi
            box_unit = drug_info.get("kutu_miktari", "?")
            price = drug_info.get("fiyat", "?")
            details_label = tk.Label(details_frame,
                text=f"Kutu: {box_unit} adet | Fiyat: ₺{price}",
                anchor='w', justify='left',
                bg=menu_bg, fg="#333333", padx=0, pady=2)
            details_label.pack(fill='x')
            # Reçete Türü ve Etken Madde
            etken_madde = drug_info.get("etken_madde", "?")
            if etken_madde == "?" and json_drug_info:
                etken_madde = json_drug_info.get("ingredients", "?")
            recete_turu = drug_info.get("recete_turu", "Normal")
            etken_label = tk.Label(details_frame,
                text=f"Etken Madde: {etken_madde}",
                anchor='w', justify='left',
                bg=menu_bg, fg="#333333", padx=0, pady=2)
            etken_label.pack(fill='x')
            recete_label = tk.Label(details_frame,
                text=f"Reçete Türü: {recete_turu}",
                anchor='w', justify='left',
                bg=menu_bg, fg="#333333", padx=0, pady=2)
            recete_label.pack(fill='x')
            interactive_widgets.extend([details_frame, details_label, etken_label, recete_label])
        # İptal butonu
        tk.Frame(frame, height=1, bg=separator_color).pack(fill='x', pady=3)
        cancel_btn = tk.Button(frame, text="İptal", relief='flat', anchor='w', justify='left',
            bg=button_bg, activebackground=button_active_bg, fg=text_color,
            activeforeground=text_color, borderwidth=0, highlightthickness=0,
            padx=5, pady=3,
            command=lambda: close_drug_menu_window(root, reason="İptal butonu"))
        cancel_btn.pack(fill='x')
        interactive_widgets.append(cancel_btn)
        # --- Fare Giriş/Çıkış Olaylarını Bağlama ---
        print("İlaç menüsü fare olayları bağlanıyor...")
        # Ana pencere ve çerçeve için olaylar
        drug_menu_win.bind("<Enter>", cancel_drug_close_timer_on_enter)
        drug_menu_win.bind("<Leave>", start_drug_close_timer)
        frame.bind("<Enter>", cancel_drug_close_timer_on_enter)
        frame.bind("<Leave>", start_drug_close_timer)
        # Etkileşimli iç widget'lar için <Enter> olayı
        for widget in interactive_widgets:
            if widget and widget.winfo_exists():
                widget.bind("<Enter>", cancel_drug_close_timer_on_enter)
        print("İlaç menüsü fare olayları bağlandı.")
        # --- Pencereyi Göster ---
        drug_menu_win.update_idletasks()
        win_width = drug_menu_win.winfo_reqwidth()
        # Fare imlecinin altında ortalanmış olarak konumlandır
        new_x = x - (win_width // 2)
        new_y = y - 25
        # Ekranda kalmasını sağla
        if new_x < 0:
            new_x = 0
        drug_menu_win.geometry(f'+{new_x}+{new_y}')
        drug_menu_win.deiconify()
        drug_menu_win.focus_force()
        print(f"İlaç menüsü penceresi başarıyla oluşturuldu (konum: {new_x},{new_y}, genişlik: {win_width})")
    except Exception as e:
        print(f"İlaç menüsü penceresi oluşturma hatası: {e}")
        # Hata durumunda temizlik
        if active_drug_menu_window and active_drug_menu_window.winfo_exists():
            try:
                active_drug_menu_window.destroy()
            except:
                pass
        active_drug_menu_window = None
        drug_menu_window_active = False
        cancel_drug_menu_close_timer(root)
        is_processing = False
        can_process_clipboard = True
        return
    is_processing = False  # Oluşturma bitti, işlemeyi serbest bırak
# ATC koduna göre ICD kodlarını bulma fonksiyonu
def get_icd_codes_for_atc(atc_code):
    """
    ATC koduna göre eşleşen ICD-10 kodlarını data/atc_icd_mapping.json dosyasından bulur.
    Tam eşleşme olmadığında prefix eşleşmesi aranır (örn. A01A* gibi).
    """
    if not atc_code:
        return []
    try:
        # Test verileri - gerçek dosya yoksa kullanılacak
        test_mapping = {
            "atc_to_icd": {
                "A01AA*": [
                    "K02.9",
                    "K03.2",
                    "K03.3"
                ],
                "A01AD*": [
                    "K13.7",
                    "R52.9"
                ],
                "A02AA*": [
                    "K21.9",
                    "K25.9",
                    "K27.9",
                    "K30"
                ],
                "J07BX*": [
                    "J12.1",
                    "J20.5",
                    "J21.0"
                ],
                "J01DD*": [
                    "J01.9",
                    "J15.9",
                    "N39.0"
                ],
                "G01AF*": [
                    "B37.3",
                    "N76.0",
                    "N77.1"
                ]
            }
        }
        atc_code = atc_code.strip()
        matching_codes = []
        # JSON dosyasını kontrol et
        json_path = "data/atc_icd_mapping.json"
        mapping_data = None
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    mapping_data = json.load(f)
            except Exception as e:
                print(f"ATC-ICD mapping dosyası okuma hatası: {e}, test verileri kullanılacak")
                mapping_data = test_mapping
        else:
            print(f"ATC-ICD mapping dosyası bulunamadı: {json_path}, test verileri kullanılacak")
            mapping_data = test_mapping
        # Mapping verilerini kullan
        if mapping_data and "atc_to_icd" in mapping_data:
            atc_map = mapping_data["atc_to_icd"]
            # Birebir eşleşme kontrolü
            if atc_code in atc_map:
                return atc_map[atc_code]
            # Wildcard (* ile biten) eşleşmeleri kontrol et
            for pattern, icd_codes in atc_map.items():
                if pattern.endswith('*'):
                    prefix = pattern[:-1]  # Son karakter (*) hariç prefix al
                    if atc_code.startswith(prefix):
                        matching_codes.extend(icd_codes)
        return matching_codes
    except Exception as e:
        print(f"ICD kodu arama hatası: {str(e)}")
        return []
# ICD kodunu silmek için onay penceresi
def confirm_and_remove_icd(atc_code, icd_code, parent):
    """
    ICD kodunu silmek için onay sorar ve onaylanırsa siler.
    Parametreler:
    - atc_code: ATC kodu
    - icd_code: Silinecek ICD kodu
    - parent: Üst pencere
    Dönüş değeri:
    - Başarı durumu (True/False)
    """
    try:
        icd_description = get_icd_description(icd_code)
        if icd_description:
            message = f"'{icd_code} - {icd_description}' kodunu silmek istediğinize emin misiniz?"
        else:
            message = f"'{icd_code}' kodunu silmek istediğinize emin misiniz?"
        confirm = messagebox.askyesno("Onay", message, parent=parent)
        if confirm:
            if remove_icd_from_atc(atc_code, icd_code):
                messagebox.showinfo("Başarılı", f"ICD kodu '{icd_code}' başarıyla silindi.", parent=parent)
                # Menüyü yenile
                if parent and hasattr(parent, 'after'):
                    parent.after(100, lambda: refresh_drug_menu_if_exists())
                return True
            else:
                messagebox.showerror("Hata", f"ICD kodu '{icd_code}' silinirken bir hata oluştu.", parent=parent)
                return False
        else:
            return False
    except Exception as e:
        print(f"ICD kodu silme onayı hatası: {str(e)}")
        return False
def remove_icd_from_atc(atc_code, icd_code):
    """
    Removes a specific ICD code from an ATC code mapping.
    """
    return update_atc_icd_mapping(atc_code, [icd_code], mode="remove")

def refresh_drug_menu_if_exists():
    """
    Aktif ilaç menüsü varsa yeniler.
    """
    global active_drug_menu_window
    try:
        if active_drug_menu_window and active_drug_menu_window.winfo_exists():
            print("İlaç menüsü yenileniyor...")
            # Menü yenileme mantığı burada olacak - şimdilik log
        else:
            print("Yenilenecek aktif ilaç menüsü yok.")
    except:
        print("İlaç menüsü yenileme hatası.")
# Panoya kopyalama işlevi
def copy_to_clipboard(text, label=None):
    """Metni panoya kopyalar ve opsiyonel olarak label'ın rengini değiştirir"""
    try:
        pyperclip.copy(text)
        print(f"Kopyalandı: {text}")
        # Label varsa renk değiştir ve 1 saniye sonra geri al
        if label and hasattr(label, 'config'):
            original_bg = label.cget('bg')
            original_fg = label.cget('fg')
            label.config(bg="#e0ffe0", fg="#006600")  # Yeşil ton
            # 1 saniye sonra orijinal renge dön
            label.after(1000, lambda: label.config(bg=original_bg, fg=original_fg))
    except Exception as e:
        print(f"Kopyalama hatası: {e}")
# İlaç menüsü penceresi oluşturma fonksiyonunu güncelle
# ICD-10 kodlarının tanımlarını bulan fonksiyon
def get_icd_description(icd_code):
    """
    ICD-10 kodunun tanımını data/icd10turk.json dosyasından bulur.
    """
    if not icd_code:
        return ""
    try:
        # Test verileri - gerçek dosya yoksa kullanılacak
        test_icd_data = [
            {
                "ICD KODU": "A00",
                "TANI": "Kolera"
            },
            {
                "ICD KODU": "A00.0",
                "TANI": "Kolera, Vibrio cholorea 01, biovar kolera'ya bağlı"
            },
            {
                "ICD KODU": "A00.1",
                "TANI": "Kolera, Vibrio cholerae 01, biovar eltor'a bağlı"
            },
            {
                "ICD KODU": "J12.1",
                "TANI": "Respiratuar sinsisyal virüs (RSV)'a bağlı pnömoni"
            },
            {
                "ICD KODU": "J20.5",
                "TANI": "Solunum sinsisyal virüsü'ne bağlı akut bronşit"
            },
            {
                "ICD KODU": "J21.0",
                "TANI": "Solunum sinsisyal virüsü'ne bağlı akut bronşiolit"
            },
            {
                "ICD KODU": "K02.9",
                "TANI": "Diş çürüğü, tanımlanmamış"
            },
            {
                "ICD KODU": "K03.2",
                "TANI": "Diş erozyonu"
            },
            {
                "ICD KODU": "K03.3",
                "TANI": "Patolojik diş aşınması"
            },
            {
                "ICD KODU": "K13.7",
                "TANI": "Oral mukozanın diğer ve tanımlanmamış lezyonları"
            },
            {
                "ICD KODU": "K21.9",
                "TANI": "Gastro-özofageal reflü hastalığı, özofajitsiz"
            },
            {
                "ICD KODU": "K25.9",
                "TANI": "Gastrik ülser, akut veya kronik olarak tanımlanmamış, kanamasız veya perforasyonsuz"
            },
            {
                "ICD KODU": "K27.9",
                "TANI": "Peptik ülser, yeri tanımlanmamış, akut veya kronik olarak tanımlanmamış, kanamasız veya perforasyonsuz"
            },
            {
                "ICD KODU": "K30",
                "TANI": "Dispepsi"
            },
            {
                "ICD KODU": "N39.0",
                "TANI": "Üriner sistem enfeksiyonu, yeri tanımlanmamış"
            },
            {
                "ICD KODU": "N76.0",
                "TANI": "Akut vajinit"
            },
            {
                "ICD KODU": "N77.1",
                "TANI": "Vajina ve vulvanın mantarsal hastalıklarda vajiniti ve vulviti"
            },
            {
                "ICD KODU": "R52.9",
                "TANI": "Ağrı, tanımlanmamış"
            },
            {
                "ICD KODU": "B37.3",
                "TANI": "Vulva ve vajinanın kandidiyazı"
            },
            {
                "ICD KODU": "J01.9",
                "TANI": "Akut sinüzit, tanımlanmamış"
            },
            {
                "ICD KODU": "J15.9",
                "TANI": "Bakteriyel pnömoni, tanımlanmamış"
            }
        ]
        icd_code = icd_code.strip()
        # JSON dosyasını kontrol et
        json_path = "data/icd10turk.json"
        icd_data = None
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    icd_data = json.load(f)
            except Exception as e:
                print(f"ICD-10 tanımları dosyası okuma hatası: {e}, test verileri kullanılacak")
                icd_data = test_icd_data
        else:
            print(f"ICD-10 tanımları dosyası bulunamadı: {json_path}, test verileri kullanılacak")
            icd_data = test_icd_data
        # ICD kodunu ve tanısını bul
        if icd_data:
            for item in icd_data:
                if "ICD KODU" in item and item["ICD KODU"].strip() == icd_code:
                    return item.get("TANI", "")
        return ""
    except Exception as e:
        print(f"ICD tanımı arama hatası: {str(e)}")
        return ""
# ATC koduna göre ICD kodlarını bulma fonksiyonu
def get_icd_codes_for_atc(atc_code):
    """
    ATC koduna göre eşleşen ICD-10 kodlarını data/atc_icd_mapping.json dosyasından bulur.
    Tam eşleşme olmadığında prefix eşleşmesi aranır (örn. A01A* gibi).
    """
    if not atc_code:
        return []
    try:
        # Test verileri - gerçek dosya yoksa kullanılacak
        test_mapping = {
            "atc_to_icd": {
                "A01AA*": [
                    "K02.9",
                    "K03.2",
                    "K03.3"
                ],
                "A01AD*": [
                    "K13.7",
                    "R52.9"
                ],
                "A02AA*": [
                    "K21.9",
                    "K25.9",
                    "K27.9",
                    "K30"
                ],
                "J07BX*": [
                    "J12.1",
                    "J20.5",
                    "J21.0"
                ],
                "J01DD*": [
                    "J01.9",
                    "J15.9",
                    "N39.0"
                ],
                "G01AF*": [
                    "B37.3",
                    "N76.0",
                    "N77.1"
                ]
            }
        }
        atc_code = atc_code.strip()
        matching_codes = []
        # JSON dosyasını kontrol et
        json_path = "data/atc_icd_mapping.json"
        mapping_data = None
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    mapping_data = json.load(f)
            except Exception as e:
                print(f"ATC-ICD mapping dosyası okuma hatası: {e}, test verileri kullanılacak")
                mapping_data = test_mapping
        else:
            print(f"ATC-ICD mapping dosyası bulunamadı: {json_path}, test verileri kullanılacak")
            mapping_data = test_mapping
        # Mapping verilerini kullan
        if mapping_data and "atc_to_icd" in mapping_data:
            atc_map = mapping_data["atc_to_icd"]
            # Birebir eşleşme kontrolü
            if atc_code in atc_map:
                return atc_map[atc_code]
            # Wildcard (* ile biten) eşleşmeleri kontrol et
            for pattern, icd_codes in atc_map.items():
                if pattern.endswith('*'):
                    prefix = pattern[:-1]  # Son karakter (*) hariç prefix al
                    if atc_code.startswith(prefix):
                        matching_codes.extend(icd_codes)
        return matching_codes
    except Exception as e:
        print(f"ICD kodu arama hatası: {str(e)}")
        return []
# Panoya kopyalama işlevi
def copy_to_clipboard(text, label=None):
    """Metni panoya kopyalar ve opsiyonel olarak label'ın rengini değiştirir"""
    try:
        pyperclip.copy(text)
        print(f"Kopyalandı: {text}")
        # Label varsa renk değiştir ve 1 saniye sonra geri al
        if label and hasattr(label, 'config'):
            original_bg = label.cget('bg')
            original_fg = label.cget('fg')
            label.config(bg="#e0ffe0", fg="#006600")  # Yeşil ton
            # 1 saniye sonra orijinal renge dön
            label.after(1000, lambda: label.config(bg=original_bg, fg=original_fg))
    except Exception as e:
        print(f"Kopyalama hatası: {e}")
# İlaç menüsü penceresi oluşturma fonksiyonunu güncelle
def create_drug_menu_window(root, barcode, x, y):
    """Barkod numarası için ilaç menüsü penceresi oluşturur."""
    global drug_menu_window_active, active_drug_menu_window, is_processing, can_process_clipboard, drug_menu_close_timer_id
    if is_processing:
        print("İşlem devam ediyor (is_processing=True), yeni ilaç menüsü açılmayacak")
        return
    if drug_menu_window_active or (active_drug_menu_window and active_drug_menu_window.winfo_exists()):
        print("İlaç menüsü zaten aktif veya mevcut, yeni menü açılmayacak")
        return
    # Barkodun 13 haneli olmasını sağlayalım
    normalized_barcode = barcode
    if len(barcode) == 14 and barcode.startswith('0'):
        normalized_barcode = barcode[1:]  # Baştaki 0'ı kaldır
    print(f"Yeni ilaç menüsü oluşturuluyor: Barkod={barcode}, Normalize={normalized_barcode}, Konum=({x},{y})")
    is_processing = True
    can_process_clipboard = False
    drug_menu_window_active = True
    try:
        drug_menu_win = tk.Toplevel(root)
        active_drug_menu_window = drug_menu_win
        drug_menu_win.withdraw()
        drug_menu_win.overrideredirect(True)
        drug_menu_win.attributes('-topmost', True)
        try:
            drug_menu_win.attributes("-toolwindow", True)
        except tk.TclError:
            pass
        menu_bg = "#f0f0f0"
        button_bg = menu_bg
        button_active_bg = "#e0e0e0"
        separator_color = "#cccccc"
        text_color = "#000000"
        drug_menu_win.config(bg=menu_bg, highlightbackground=separator_color, highlightthickness=1)
        frame = tk.Frame(drug_menu_win, bg=menu_bg)
        frame.pack(padx=1, pady=1)
        # --- Zamanlayıcı Fonksiyonları ---
        def auto_close_drug_menu():
            """Zamanlayıcı dolduğunda ilaç menüsünü kapatır."""
            global drug_menu_close_timer_id, active_drug_menu_window, drug_menu_window_active, atc_icd_mapping_window_open
            print("İlaç menüsü otomatik kapatma zamanlayıcısı tetiklendi.")
            drug_menu_close_timer_id = None  # Zamanlayıcı ID'sini sıfırla
            # ATC-ICD eşleştirme penceresi açıksa menüyü kapatma
            if atc_icd_mapping_window_open:
                print("İlaç menüsü kapatma iptal edildi (Sebep: ATC-ICD eşleştirme penceresi açık)")
                return
            # Menü hala aktif ve mevcutsa kapat
            if drug_menu_window_active and active_drug_menu_window and active_drug_menu_window.winfo_exists():
                close_drug_menu_window(root, reason="Fare ayrıldı (zaman aşımı)")
            else:
                print("İlaç menüsü zamanlayıcısı tetiklendi ama menü zaten kapalı/yok.")
        def start_drug_close_timer(event=None):
            """Fare ayrıldığında ilaç menüsü kapatma zamanlayıcısını başlatır."""
            global drug_menu_close_timer_id
            # print("Fare ayrıldı (<Leave>), zamanlayıcı başlatılıyor...") # Debug
            cancel_drug_menu_close_timer(root)  # Önceki zamanlayıcıyı iptal et
            if root and root.winfo_exists():
                # 1000 ms = 1 saniye
                drug_menu_close_timer_id = root.after(1000, auto_close_drug_menu)
        def cancel_drug_close_timer_on_enter(event=None):
            """Fare girdiğinde (<Enter>) ilaç menüsü kapatma zamanlayıcısını iptal eder."""
            # print("Fare girdi (<Enter>), zamanlayıcı iptal ediliyor...") # Debug
            cancel_drug_menu_close_timer(root)
        # --- Widget'lar ---
        # İlaç bilgilerini almaya çalış
        drug_info = get_drug_info(barcode)
        # JSON dosyasından ATC bilgilerini al
        json_drug_info = get_drug_from_json(barcode)
        # İlaç adı ve barkod bilgisi göster
        barcode_label = tk.Label(frame, text=f"Barkod: {normalized_barcode}", anchor='w', justify='left',
            bg=menu_bg, fg="#666666", padx=5, pady=3)
        barcode_label.pack(fill='x')
        barcode_label.bind("<Button-1>", lambda e: "break")
        if drug_info:
            drug_name = drug_info.get("ilac_adi", "Bilinmiyor")
            drug_name_label = tk.Label(frame, text=f"İlaç: {drug_name}", anchor='w', justify='left',
                bg=menu_bg, fg="#000000", font=("TkDefaultFont", 9, "bold"), padx=5, pady=3)
            drug_name_label.pack(fill='x')
            drug_name_label.bind("<Button-1>", lambda e: "break")
        elif json_drug_info:
            drug_name = json_drug_info.get("name", "Bilinmiyor")
            drug_name_label = tk.Label(frame, text=f"İlaç: {drug_name}", anchor='w', justify='left',
                bg=menu_bg, fg="#000000", font=("TkDefaultFont", 9, "bold"), padx=5, pady=3)
            drug_name_label.pack(fill='x')
            drug_name_label.bind("<Button-1>", lambda e: "break")
        # ATC bilgilerini ve eşleşen ICD kodlarını sakla
        atc_code = ""
        # JSON'dan ATC bilgilerini göster
        if json_drug_info:
            # ATC Kodu ve Adı bilgilerini ekle
            atc_code = json_drug_info.get("atc_code", "").strip()
            atc_name = json_drug_info.get("atc_name", "").strip()
            if atc_code or atc_name:
                tk.Frame(frame, height=1, bg=separator_color).pack(fill='x', pady=1)
                if atc_code:
                    atc_code_label = tk.Label(frame, text=f"ATC Kodu: {atc_code}", anchor='w', justify='left',
                        bg=menu_bg, fg="#333333", padx=5, pady=2)
                    atc_code_label.pack(fill='x')
                if atc_name:
                    atc_name_label = tk.Label(frame, text=f"ATC Adı: {atc_name}", anchor='w', justify='left',
                        bg=menu_bg, fg="#333333", padx=5, pady=2)
                    atc_name_label.pack(fill='x')
        tk.Frame(frame, height=1, bg=separator_color).pack(fill='x', pady=3)
        # ATC koduna göre ICD-10 kodlarını getir
        if atc_code:
            icd_codes = get_icd_codes_for_atc(atc_code)
            if icd_codes:
                # ICD kodları için başlık
                icd_title_label = tk.Label(frame, text="ICD-10 Kodları:", anchor='w', justify='left',
                    bg=menu_bg, fg="#333333", font=("TkDefaultFont", 9, "bold"), padx=5, pady=2)
                icd_title_label.pack(fill='x')
                # ICD kodları için kaydırılabilir çerçeve
                icd_container_frame = tk.Frame(frame, bg=menu_bg, highlightbackground="#cccccc", highlightthickness=1)
                icd_container_frame.pack(fill='x', padx=5, pady=2, expand=True)
                # Kaydırma çubuğu
                icd_canvas = tk.Canvas(icd_container_frame, bg=menu_bg, height=150, highlightthickness=0)
                scrollbar = ttk.Scrollbar(icd_container_frame, orient="vertical", command=icd_canvas.yview)
                # Canvas ve scrollbar düzeni
                icd_canvas.pack(side=tk.LEFT, fill='both', expand=True)
                scrollbar.pack(side=tk.RIGHT, fill='y')
                icd_canvas.configure(yscrollcommand=scrollbar.set)
                # İçerik frame'i
                icd_content_frame = tk.Frame(icd_canvas, bg=menu_bg)
                icd_canvas.create_window((0, 0), window=icd_content_frame, anchor='nw')
                # ICD kodları ve tanımlarını ekle
                for i, icd_code in enumerate(icd_codes):
                    # Her kod için bir çerçeve
                    code_frame = tk.Frame(icd_content_frame, bg=menu_bg, bd=0)  # Her ICD kodu için bir çerçeve
                    code_frame.pack(fill='x', pady=1, anchor='w')
                    icd_description = get_icd_description(icd_code)  # ICD kodunun tanımını al
                    # ICD kodu etiketi
                    code_label = tk.Label(code_frame, text=icd_code,
                        bg="#e8e8e8", fg="#0066cc",
                        width=7, padx=5, pady=2, anchor='w',
                        relief="ridge", cursor="hand2")
                    code_label.pack(side=tk.LEFT, padx=(0, 2))
                    # ICD kodu tanımı etiketi - uzun tanımları kısalt
                    desc_text = icd_description if icd_description else "Tanım bulunamadı"
                    if len(desc_text) > 40:
                        desc_text = desc_text[:37] + "..."
                    desc_label = tk.Label(code_frame, text=desc_text,
                        bg=menu_bg, fg="#333333",
                        padx=2, pady=2, anchor='w', justify='left')
                    desc_label.pack(side=tk.LEFT, fill='x', expand=True)
                    # Butonlar için bir çerçeve oluştur (YENİ)
                    buttons_frame = tk.Frame(code_frame, bg=menu_bg)
                    buttons_frame.pack(side=tk.RIGHT, padx=(2, 0))
                    # Yukarı taşıma düğmesi (YENİ)
                    up_button = tk.Button(
                        buttons_frame, text="↑", width=1, height=1,
                        command=lambda c=icd_code: move_icd_code(atc_code, c, "up"),
                        bg="#f0f0f0", activebackground="#e0e0e0",
                        relief="flat", borderwidth=0, padx=2, pady=0,
                        font=("TkDefaultFont", 8)
                    )
                    up_button.pack(side=tk.LEFT)
                    # Aşağı taşıma düğmesi (YENİ)
                    down_button = tk.Button(
                        buttons_frame, text="↓", width=1, height=1,
                        command=lambda c=icd_code: move_icd_code(atc_code, c, "down"),
                        bg="#f0f0f0", activebackground="#e0e0e0",
                        relief="flat", borderwidth=0, padx=2, pady=0,
                        font=("TkDefaultFont", 8)
                    )
                    down_button.pack(side=tk.LEFT)
                    # Düzenleme düğmesi (YENİ)
                    edit_button = tk.Button(
                        buttons_frame, text="✎", width=1, height=1,
                        command=lambda c=icd_code: create_atc_icd_mapping_window(drug_menu_win, atc_code, atc_name),
                        bg="#f0f0f0", activebackground="#e0e0e0",
                        relief="flat", borderwidth=0, padx=2, pady=0,
                        font=("TkDefaultFont", 8)
                    )
                    edit_button.pack(side=tk.LEFT)
                    # Silme düğmesi (YENİ)
                    delete_button = tk.Button(
                        buttons_frame, text="✕", width=1, height=1,
                        command=lambda c=icd_code: confirm_and_remove_icd(atc_code, c, drug_menu_win),
                        bg="#f0f0f0", activebackground="#e0e0e0", fg="red",
                        relief="flat", borderwidth=0, padx=2, pady=0,
                        font=("TkDefaultFont", 8)
                    )
                    delete_button.pack(side=tk.LEFT)
                    # Kod etiketine tıklama olayı
                    code_label.bind("<Button-1>", lambda e, code=icd_code, lbl=code_label: copy_to_clipboard(code, lbl))
                    # Mouse over efekti
                    code_label.bind("<Enter>", lambda e, lbl=code_label: lbl.config(bg="#d0d0ff"))
                    code_label.bind("<Leave>", lambda e, lbl=code_label: lbl.config(bg="#e8e8e8"))
                    code_frame = tk.Frame(icd_content_frame, bg=menu_bg, bd=0)
                    code_frame.pack(fill='x', pady=1, anchor='w')
                    # ICD kodu tanımını al
                    icd_description = get_icd_description(icd_code)
                # Scroll frame'i yapılandır
                def on_frame_configure(event):
                    icd_canvas.configure(scrollregion=icd_canvas.bbox("all"))
                icd_content_frame.bind("<Configure>", on_frame_configure)
                # Farenin canvas üzerindeki tekerleği
                def on_mousewheel(event):
                    icd_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                # Windows
                icd_canvas.bind_all("<MouseWheel>", on_mousewheel)
                # Linux
                icd_canvas.bind_all("<Button-4>", lambda e: icd_canvas.yview_scroll(-1, "units"))
                icd_canvas.bind_all("<Button-5>", lambda e: icd_canvas.yview_scroll(1, "units"))
                # Ayırıcı çizgi
                tk.Frame(frame, height=1, bg=separator_color).pack(fill='x', pady=3)
        def execute_drug_command(command, *args):
            # Komut çalışmadan önce menüyü kapatır (zamanlayıcıyı da iptal eder)
            close_drug_menu_window(root, reason="İlaç menüsü seçeneği seçildi")
            if root and root.winfo_exists():
                root.after(200, lambda: command(*args))
        # İlaç arama butonu
        search_btn = tk.Button(frame, text="İlaç Ara", relief='flat', anchor='w', justify='left',
            bg=button_bg, activebackground=button_active_bg, fg=text_color,
            activeforeground=text_color, borderwidth=0, highlightthickness=0,
            padx=5, pady=3,
            command=lambda bc=normalized_barcode: execute_drug_command(open_drug_search, bc))
        search_btn.pack(fill='x')
        # İlaç ekleme butonu
        add_btn = tk.Button(frame, text="İlaç Ekle", relief='flat', anchor='w', justify='left',
            bg=button_bg, activebackground=button_active_bg, fg=text_color,
            activeforeground=text_color, borderwidth=0, highlightthickness=0,
            padx=5, pady=3,
            command=lambda bc=normalized_barcode: execute_drug_command(open_drug_add, bc))
        add_btn.pack(fill='x')
        # Doz ayarlama butonu
        dose_btn = tk.Button(frame, text="Doz Ayarla", relief='flat', anchor='w', justify='left',
            bg=button_bg, activebackground=button_active_bg, fg=text_color,
            activeforeground=text_color, borderwidth=0, highlightthickness=0,
            padx=5, pady=3,
            command=lambda bc=normalized_barcode: execute_drug_command(open_drug_dose, bc))
        dose_btn.pack(fill='x')
        interactive_widgets = [search_btn, add_btn, dose_btn]
        # İlaç bilgileri mevcut ise ek detaylar göster
        if drug_info:
            tk.Frame(frame, height=1, bg=separator_color).pack(fill='x', pady=3)
            # İlaç detayları
            details_frame = tk.Frame(frame, bg=menu_bg)
            details_frame.pack(fill='x', padx=5, pady=3)
            # Kutu/Tablet ve Fiyat Bilgisi
            box_unit = drug_info.get("kutu_miktari", "?")
            price = drug_info.get("fiyat", "?")
            details_label = tk.Label(details_frame,
                text=f"Kutu: {box_unit} adet | Fiyat: ₺{price}",
                anchor='w', justify='left',
                bg=menu_bg, fg="#333333", padx=0, pady=2)
            details_label.pack(fill='x')
            # Reçete Türü ve Etken Madde
            etken_madde = drug_info.get("etken_madde", "?")
            if etken_madde == "?" and json_drug_info:
                etken_madde = json_drug_info.get("ingredients", "?")
            recete_turu = drug_info.get("recete_turu", "Normal")
            etken_label = tk.Label(details_frame,
                text=f"Etken Madde: {etken_madde}",
                anchor='w', justify='left',
                bg=menu_bg, fg="#333333", padx=0, pady=2)
            etken_label.pack(fill='x')
            recete_label = tk.Label(details_frame,
                text=f"Reçete Türü: {recete_turu}",
                anchor='w', justify='left',
                bg=menu_bg, fg="#333333", padx=0, pady=2)
            recete_label.pack(fill='x')
            interactive_widgets.extend([details_frame, details_label, etken_label, recete_label])
        # İptal butonu
        tk.Frame(frame, height=1, bg=separator_color).pack(fill='x', pady=3)
        cancel_btn = tk.Button(frame, text="İptal", relief='flat', anchor='w', justify='left',
            bg=button_bg, activebackground=button_active_bg, fg=text_color,
            activeforeground=text_color, borderwidth=0, highlightthickness=0,
            padx=5, pady=3,
            command=lambda: close_drug_menu_window(root, reason="İptal butonu"))
        cancel_btn.pack(fill='x')
        interactive_widgets.append(cancel_btn)
        # --- Fare Giriş/Çıkış Olaylarını Bağlama ---
        print("İlaç menüsü fare olayları bağlanıyor...")
        # Ana pencere ve çerçeve için olaylar
        drug_menu_win.bind("<Enter>", cancel_drug_close_timer_on_enter)
        drug_menu_win.bind("<Leave>", start_drug_close_timer)
        frame.bind("<Enter>", cancel_drug_close_timer_on_enter)
        frame.bind("<Leave>", start_drug_close_timer)
        # Etkileşimli iç widget'lar için <Enter> olayı
        for widget in interactive_widgets:
            if widget and widget.winfo_exists():
                widget.bind("<Enter>", cancel_drug_close_timer_on_enter)
        print("İlaç menüsü fare olayları bağlandı.")
        # --- Pencereyi Göster ---
        drug_menu_win.update_idletasks()
        win_width = drug_menu_win.winfo_reqwidth()
        # Fare imlecinin altında ortalanmış olarak konumlandır
        new_x = x - (win_width // 2)
        new_y = y - 25
        # Ekranda kalmasını sağla
        if new_x < 0:
            new_x = 0
        drug_menu_win.geometry(f'+{new_x}+{new_y}')
        drug_menu_win.deiconify()
        drug_menu_win.focus_force()
        print(f"İlaç menüsü penceresi başarıyla oluşturuldu (konum: {new_x},{new_y}, genişlik: {win_width})")
    except Exception as e:
        print(f"İlaç menüsü penceresi oluşturma hatası: {e}")
        # Hata durumunda temizlik
        if active_drug_menu_window and active_drug_menu_window.winfo_exists():
            try:
                active_drug_menu_window.destroy()
            except:
                pass
        active_drug_menu_window = None
        drug_menu_window_active = False
        cancel_drug_menu_close_timer(root)
        is_processing = False
        can_process_clipboard = True
        return
    is_processing = False  # Oluşturma bitti, işlemeyi serbest bırak
# Eksik olan clipboard check fonksiyonu
def check_clipboard(root):
    """Panoyu periyodik olarak kontrol eder."""
    global last_clipboard, last_tc_number, last_drug_barcode, can_process_clipboard, clipboard_check_id, is_processing
    global menu_window_active, drug_menu_window_active
    if not root or not root.winfo_exists():
        print("Root window closed, stopping clipboard check.")
        return
    if not can_process_clipboard or is_processing:
        try:
            if root and root.winfo_exists():
                clipboard_check_id = root.after(500, lambda: check_clipboard(root))
        except tk.TclError: pass
        return
    if menu_window_active or drug_menu_window_active:
        try:
            if root and root.winfo_exists():
                clipboard_check_id = root.after(500, lambda: check_clipboard(root))
        except tk.TclError: pass
        return
    current_clipboard = ""
    try:
        current_clipboard_raw = pyperclip.paste()
        current_clipboard = current_clipboard_raw if current_clipboard_raw is not None else ""
    except Exception as e:
        # print(f"Pano okuma hatası (görmezden geliniyor): {e}") # İstenirse açılabilir
        current_clipboard = last_clipboard
    if current_clipboard != last_clipboard:
        last_clipboard = current_clipboard
        # TC Kimlik numarası kontrolü
        if is_tc_number(current_clipboard):
            print(f"Geçerli TC Kimlik numarası algılandı: {current_clipboard}")
            last_tc_number = current_clipboard
            try:
                x, y = root.winfo_pointerxy()
                create_menu_window(root, current_clipboard, x, y)
            except tk.TclError as e:
                print(f"Fare konumu alınırken/Menü oluşturulurken TclError: {e}")
            except Exception as e:
                print(f"Menü oluşturma sırasında beklenmedik hata: {e}")
        # İlaç barkodu kontrolü
        elif is_drug_barcode(current_clipboard):
            print(f"Geçerli İlaç Barkodu algılandı: {current_clipboard}")
            last_drug_barcode = current_clipboard
            try:
                x, y = root.winfo_pointerxy()
                create_drug_menu_window(root, current_clipboard, x, y)
            except tk.TclError as e:
                print(f"Fare konumu alınırken/İlaç menüsü oluşturulurken TclError: {e}")
            except Exception as e:
                print(f"İlaç menüsü oluşturma sırasında beklenmedik hata: {e}")
    try:
        if root and root.winfo_exists():
            clipboard_check_id = root.after(500, lambda: check_clipboard(root))
    except tk.TclError:
        print("Root window already destroyed while rescheduling clipboard check.")
if __name__ == "__main__":
    try:
        print("Program başlatılıyor...")
        main()
    except Exception as e:
        print(f"Programın ana bölümünde beklenmeyen hata: {e}")
        import traceback
        traceback.print_exc()
        input("Programı kapatmak için Enter tuşuna basın...")  # Kullanıcıya hatayı görebilmesi için beklet
