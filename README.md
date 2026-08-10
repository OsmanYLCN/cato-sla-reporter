# Cato SLA Reporter

Cato Networks cihaz loglarından (CSV / GraphQL API) **lokasyon bazlı Aylık ve 3 Aylık SLA / Availability** raporu üreten, enterprise standartlarında modüler bir Python projesidir.

---

## 🗂️ Proje Yapısı

```
cato-sla-reporter/
├── main.py                    # CLI giriş noktası
├── config/settings.py         # Merkezi yapılandırma
├── data_ingestion/
│   ├── base_reader.py         # Abstract okuyucu arayüzü
│   ├── csv_reader.py          # CSV okuyucu (aktif)
│   └── graphql_reader.py      # GraphQL istemcisi (stub)
├── preprocessing/
│   └── transformer.py         # UTC→Istanbul + veri temizleme
├── engine/
│   ├── leg_detector.py        # Dinamik bacak tespiti
│   ├── state_machine.py       # Kesinti korelasyon motoru (core)
│   └── sla_calculator.py      # Availability % ve SLA kararı
├── reporting/
│   ├── excel_exporter.py      # 2 sekme .xlsx çıktısı
│   └── email_sender.py        # SMTP gönderici (stub)
├── utils/logger.py            # Merkezi logging
├── tests/                     # Birim testler (pytest)
├── sample_data/               # Örnek CSV
└── output/                    # Üretilen raporlar
```

---

## ⚙️ Kurulum

**Gereksinimler:** Python 3.9+

```bash
# Bağımlılıkları yükle
pip install -r requirements.txt
```

---

## 🚀 Kullanım

### Manuel Mod (PC'den çalıştırma)

```bash
# Son 30 günü analiz et
python main.py --input sample_data/Cato_events_sample.csv --period 1

# Son 90 günü analiz et, raporları özel klasöre yaz
python main.py --input sample_data/Cato_events_sample.csv --period 3 --output ./raporlar
```

### Otomatik Mod (Sunucu / CronJob)

```bash
# Bir önceki tam takvim ayını analiz et
python main.py --input /data/cato_events.csv --period 1 --mode auto

# Bir önceki tam çeyreği analiz et
python main.py --input /data/cato_events.csv --period 3 --mode auto
```

### Tüm Parametreler

| Parametre | Açıklama | Zorunlu | Varsayılan |
|-----------|----------|---------|------------|
| `--input` | CSV dosyasının yolu | ✅ | — |
| `--period` | Rapor dönemi: `1` (30 gün) veya `3` (90 gün) | ✅ | — |
| `--mode` | `manual` (geriye dönük) veya `auto` (önceki ay/çeyrek) | ❌ | `manual` |
| `--output` | Çıktı klasörü | ❌ | `./output` |

---

## 📊 Çıktı

Üretilen Excel dosyası (`output/SLA_Report_<N>M_<YYYY-MM-DD>.xlsx`) iki sekme içerir:

### Sekme 1 — SLA Özet
| Site Name | Rapor Dönemi | Gerçek Kesinti Sayısı | Toplam Kesinti Süresi (Dakika) | Availability (%) | SLA Durumu |
|-----------|-------------|----------------------|-------------------------------|-----------------|------------|
| Istanbul-HQ | Son 1 Ay | 2 | 90.00 | 99.7917 | Failed |
| Ankara-DC | Son 1 Ay | 1 | 30.00 | 99.9306 | Passed |

- **Passed** → Yeşil arka plan
- **Failed** → Kırmızı arka plan

### Sekme 2 — Kesinti Detayları
| Site Name | Başlangıç | Bitiş | Süre (Dakika) |
|-----------|-----------|-------|--------------|
| Istanbul-HQ | 10.07.2026 10:00:00 | 10.07.2026 11:30:00 | 90.00 |

---

## 🔬 İş Kuralları

| Kural | Değer |
|-------|-------|
| Saat Dilimi | UTC → `Europe/Istanbul` (UTC+3) |
| SLA Eşiği | `%99.90` |
| Korelasyon Toleransı | `30 saniye` |
| 1 Ay Toplam Dakika | `43.200 dk` (sabit) |
| 3 Ay Toplam Dakika | `129.600 dk` (sabit) |
| Gerçek DOWN Kriteri | Tüm bacaklar eş zamanlı Disconnected |
| Tek Bacaklı Site | 1 bacak kopması = Site DOWN |
| Açık Kesinti Bitiş | Rapor döneminin son anı |

---

## 🧪 Testleri Çalıştırma

```bash
# Tüm testleri çalıştır
pytest tests/ -v

# Belirli bir test modülü
pytest tests/test_state_machine.py -v

# Kapsam raporu ile
pytest tests/ --cov=. --cov-report=term-missing
```

---

## 📁 CSV Format

```
src_site_name,time,event_sub_type,socket_interface,socket_role
Istanbul-HQ,2026-07-10 07:00:00,Disconnected,WAN1,primary
Istanbul-HQ,2026-07-10 08:30:00,Connected,WAN1,primary
```

| Sütun | Açıklama |
|-------|----------|
| `src_site_name` | Site adı |
| `time` | Olay zamanı (UTC, format: `YYYY-MM-DD HH:MM:SS`) |
| `event_sub_type` | `Connected` veya `Disconnected` |
| `socket_interface` | `WAN1`, `WAN2`, `PRIMARY1` vb. |
| `socket_role` | `primary` veya `secondary` |

---

## 🗺️ Yol Haritası

- [ ] Cato GraphQL API entegrasyonu (`graphql_reader.py`)
- [ ] SMTP e-posta gönderimi (`email_sender.py`)
- [ ] CronJob entegrasyonu (Otomatik Mod zamanlayıcı)
- [ ] Çoklu CSV birleştirme desteği (`--input` multi-file)
- [ ] PDF rapor çıktısı
