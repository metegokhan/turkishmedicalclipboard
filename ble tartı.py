import asyncio
import time
import json
import os
import re
from bleak import BleakScanner
from winotify import Notification

TARTI_JSON_FILE = "tarti.json"

# Zaman ve kilo değişkenleri
last_measurement_time = 0
highest_weight = 0.0
measurement_active = True  # Yeni ölçüm alınıyor mu?

# Manufacturer Data'yı kilo verisine çeviren fonksiyon
def parse_weight(manufacturer_data):
    if len(manufacturer_data) < 2:
        return None
    raw_weight = (manufacturer_data[0] << 8) | manufacturer_data[1]
    weight = raw_weight / 100.0
    return weight

def is_valid_mac(mac):
    return bool(re.match(r'^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$', mac))

async def get_mac_address():
    if os.path.exists(TARTI_JSON_FILE):
        try:
            with open(TARTI_JSON_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                mac = data.get("mac_address", "").strip().upper()
                if is_valid_mac(mac):
                    return mac
                else:
                    print("⚠ tarti.json içindeki MAC adresi geçersiz. Yeniden yapılandırılıyor...")
        except Exception as e:
            print(f"⚠ tarti.json okunamadı: {e}")

    while True:
        prompt = (
            "Lütfen BLE tartının MAC adresini girin (Örn: 50:E4:52:79:AD:9A) \n"
            "Eğer MAC adresini bilmiyorsanız, cihazınızın çalışmaya uygun olduğundan ve yakınınızda olduğundan emin olup ENTER tuşuna basarak sonraki ekrana geçiniz: "
        )
        mac_input = await asyncio.to_thread(input, prompt)
        mac_input = mac_input.strip().upper()

        if mac_input == "":
            print("\nŞimdi tartıya çıkınız...")
            print("⏳ Çevredeki cihazlar 30 saniye boyunca taranıyor, lütfen bekleyin...")
            
            found_scales = {}

            def discover_callback(device, advertisement_data):
                manufacturer_data_dict = advertisement_data.manufacturer_data
                if manufacturer_data_dict:
                    for key, raw_bytes in manufacturer_data_dict.items():
                        manufacturer_data = list(raw_bytes)
                        weight = parse_weight(manufacturer_data)
                        if weight and weight > 0:
                            # Tartı tespit edildi, listeye ekle/güncelle
                            found_scales[device.address] = {
                                "name": device.name or "Bilinmeyen Cihaz",
                                "weight": weight
                            }

            scanner = BleakScanner(discover_callback)
            await scanner.start()
            
            # 30 saniye tarama süresi
            await asyncio.sleep(30)
            await scanner.stop()

            if not found_scales:
                print("⚠ Hiçbir uyumlu tartı bulunamadı. Lütfen tekrar deneyin.\n")
                continue
            
            print("\n✅ Bulunan Tartılar:")
            scales_list = list(found_scales.items())
            for i, (addr, data) in enumerate(scales_list, 1):
                print(f"  [{i}] MAC: {addr} | İsim: {data['name']} | Son okunan kilo: {data['weight']:.1f} kg")
            
            while True:
                selection = await asyncio.to_thread(input, f"\nLütfen kullanmak istediğiniz tartının numarasını seçin (1-{len(scales_list)}) veya 0 yazıp iptal edin: ")
                selection = selection.strip()
                if selection == '0':
                    print("❌ Seçim iptal edildi. Başa dönülüyor...\n")
                    break
                try:
                    idx = int(selection) - 1
                    if 0 <= idx < len(scales_list):
                        mac_input = scales_list[idx][0]
                        break
                    else:
                        print("⚠ Geçersiz seçim. Lütfen listedeki numaralardan birini girin.")
                except ValueError:
                    print("⚠ Lütfen geçerli bir sayı girin.")
            
            if mac_input == "":
                continue # İptal edildiyse veya seçim yapılmadıysa başa dön

        if is_valid_mac(mac_input):
            try:
                with open(TARTI_JSON_FILE, "w", encoding="utf-8") as f:
                    json.dump({"mac_address": mac_input}, f, indent=4)
                print(f"✅ MAC adresi ({mac_input}) başarıyla tarti.json dosyasına kaydedildi.")
                return mac_input
            except Exception as e:
                print(f"⚠ MAC adresi kaydedilemedi: {e}")
                return mac_input
        else:
            print("⚠ Hatalı MAC adresi formatı! Geçerli bir MAC adresi 12 hex karakter ve 5 adet ':' işareti içermelidir (Örn: 50:E4:52:79:AD:9A).\n")


# Bildirim gösterme fonksiyonu (winotify ile)
def show_notification(message):
    try:
        toast = Notification(app_id="OKOK Tartı", title="Tartı Sonucu", msg=message, duration="short")
        toast.show()
    except Exception as e:
        print(f"Bildirim hatası: {e}")

# BLE Tarama fonksiyonu
async def scan_ble(tarti_mac_adresi):
    global last_measurement_time, highest_weight, measurement_active

    print("🔍 BLE cihazları taranıyor...")

    def detection_callback(device, advertisement_data):
        global last_measurement_time, highest_weight, measurement_active

        if device.address.upper() == tarti_mac_adresi and measurement_active:
            print(f"✅ Tartı bulundu! MAC: {device.address}")

            manufacturer_data_dict = advertisement_data.manufacturer_data
            print(f"📡 Gelen Manufacturer Data: {manufacturer_data_dict}")

            if manufacturer_data_dict:
                for key, raw_bytes in manufacturer_data_dict.items():
                    manufacturer_data = list(raw_bytes)
                    hex_data = " ".join(f"{byte:02X}" for byte in manufacturer_data)
                    print(f"📊 Manufacturer Data (HEX): {hex_data}")

                    weight = parse_weight(manufacturer_data)
                    if weight:
                        print(f"⚖ Tespit Edilen Kilo: {weight:.1f} kg")
                        highest_weight = max(highest_weight, weight)

                        if last_measurement_time == 0:
                            last_measurement_time = time.time()

    scanner = BleakScanner(detection_callback)
    await scanner.start()

    try:
        while True:
            await asyncio.sleep(1)

            if measurement_active and last_measurement_time != 0 and (time.time() - last_measurement_time >= 5):
                if highest_weight > 0:
                    message = f"Ağırlık: {highest_weight:.1f} kg"
                    print(f"🔔 Son Ölçüm: {message}")
                    show_notification(message)

                measurement_active = False
                highest_weight = 0.0
                last_measurement_time = 0

                print("⏳ 10 saniye boyunca yeni ölçüm alınmayacak...")
                await asyncio.sleep(10)

                measurement_active = True
                print("✅ Yeni ölçüm için hazır!")

    except KeyboardInterrupt:
        print("\n🛑 BLE tarama durduruldu.")
        await scanner.stop()

# Ana döngü
async def main():
    tarti_mac_adresi = await get_mac_address()
    await scan_ble(tarti_mac_adresi)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"\n⚠ Hata Oluştu: {e}")
