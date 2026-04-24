# Asynchronous DIRECTIONAL Sniper (ADS) v1.0 — PRD

**Architectural Review Edition · Senior Quant Trader + HFT Architect**
`Platform: Polymarket / Hyperliquid · Mode: Ultra-Lean Directional`

---

## 01 · Executive Summary

**Asynchronous DIRECTIONAL Sniper (ADS) v1.0** adalah bot latency arbitrage dengan arsitektur *ultra-lean* yang secara eksklusif mengeksekusi **Strategy A: DIRECTIONAL**. Bot ini dirancang untuk membuang semua overhead logika hedging (Smart Hedge & Temporal Hedge) demi memaksimalkan kecepatan eksekusi (HFT) dan meminimalisir latensi pada *golden window*.

**Core Philosophy:**
- **Reactionary & Asynchronous:** Memanfaatkan `asyncio` murni tanpa bloking antar I/O stream.
- **Single-Sided Bet:** Hanya membeli satu sisi market (UP atau DOWN) berdasarkan sinyal Triple Confirmation yang tervalidasi.
- **Ultra-Lean:** Menghapus state management yang tidak relevan, menyederhanakan pipeline, dan mempercepat order submission.

---

## 02 · Strategy Logic: DIRECTIONAL (Triple Confirmation)

Strategi ini berfokus pada asimetri informasi antara Hyperliquid (real-time) dan Polymarket (lagging) dengan mengeksekusi taruhan satu arah ketika momentum (CVD) dan Velocity selaras dengan Gap, dan harga opsi masih *underpriced*.

### 2.1 Sinyal Pemicu (Triple Confirmation)
Eksekusi HANYA valid jika ketiga kondisi berikut terpenuhi pada saat yang sama (AND logic):
1. **Gap Strength:** `|Gap| > GAP_THRESHOLD_DEFAULT` (25.0)
   - Gap positif (Hyperliquid > Strike) → Bias **UP**
   - Gap negatif (Hyperliquid < Strike) → Bias **DOWN**
2. **Momentum (CVD):** `CVD > CVD_THRESHOLD_PCT` (45.0%)
   - CVD dihitung berbasis *rolling 5 menit*. Arah CVD harus selaras dengan arah Gap.
3. **Velocity:** `Velocity > VELOCITY_MIN_DELTA` (25.0)
   - Velocity dihitung dari *price change* dalam `VELOCITY_WINDOW_SECONDS` (2 detik).

### 2.2 Aturan Eksekusi & Sizing
- **Max Odds Limit:** Entri hanya dieksekusi jika harga sisi target `<= DIRECTIONAL_MAX_ODDS` (0.78).
- **Position Sizing (Flat Risk):** Menggunakan `BASE_TRADE_USD=5.00`.
  - Rumus: `order_size = round(config.BASE_TRADE_USD / target_ask, 2)`
- **Optimistic Lock:** Menggunakan lock `self.order_sent` untuk memastikan tidak ada *multiple fills* dalam satu window.

---

## 03 · Technical Implementation & Module Specs

Sistem dipecah ke dalam 5 modul inti yang berjalan secara konkuren.

### 3.1 File `config.py` & `.env`
Konfigurasi dikontrol penuh melalui *environment variables*.
- Menggunakan `python-dotenv` untuk memuat variabel.
- **Key Parameters:**
  - `GAP_THRESHOLD_DEFAULT=25.0`
  - `CVD_THRESHOLD_PCT=45.0`
  - `VELOCITY_MIN_DELTA=25.0`
  - `VELOCITY_WINDOW_SECONDS=2.0`
  - `DIRECTIONAL_MAX_ODDS=0.78`
  - `BASE_TRADE_USD=5.00`

### 3.2 File Feeders
**`poly_feed.py`**
- Fokus eksklusif pada WebSocket untuk *L2 Book* Polymarket.
- **Proteksi Mutasi Payload:** Wajib memvalidasi tipe data (list/dict) sebelum diproses untuk mencegah *crash*.
- **Timestamping:** Menyematkan *local timestamp* pada setiap objek `OrderBookEvent` saat diterima untuk sinkronisasi latensi.

**`hyperliquid_feed.py`**
- WebSocket asinkron yang menarik data *spot BTC price* dari Hyperliquid.
- Menghitung **CVD** (rolling 5m) dan **Velocity** (price change dalam 2 detik) secara asinkron di *background*.
- *Zero-blocking buffer:* Menyediakan metrik secara instan saat diminta oleh Engine.

### 3.3 File `directional_engine.py` (Core Logic)
- **Pipeline Gate:** Mengevaluasi "Triple Confirmation" (Gap > 25.0 AND CVD > 45.0 AND Velocity > 25.0).
- **Sizing Execution:** Menghitung order size secara dinamis berdasarkan formula *Flat Risk* (`BASE_TRADE_USD / target_ask`).
- **Lightweight Persistent File Logging:** 
  - Mencatat setiap aktivitas krusial ke `ads_execution.log`.
  - Wajib dibungkus dalam blok `try-except` (misal *background task* atau *non-blocking file write*) agar I/O *disk* tidak menyebabkan *zero-blocking* (tidak mengganggu latensi).
- **State Guard:** Lock `self.order_sent` di-set ke `True` langsung sebelum melempar order.

### 3.4 File `ui.py` (CLI Dashboard)
Dibangun menggunakan library `rich` untuk antarmuka terminal yang *informative* dan bergaya HFT. Terdiri dari 4 panel utama:
1. **Header:** Menampilkan *Target Window* (Slug Polymarket) dan *T-Minus* (waktu tersisa menuju penutupan).
2. **Market Panel:** Menampilkan *HL Price*, *Poly Strike*, *Gap ($)*, *CVD (%)*, dan *Velocity ($/s)*. Menggunakan warna hijau (Pass) / merah (Fail) secara dinamis untuk indikator konfirmasi.
3. **Inventory Panel:** Status posisi yang sedang dipegang (UP / DOWN / NONE) dan modal yang telah terpakai.
4. **Log Panel:** Menampilkan *tailing* 10 baris terakhir dari `ads_execution.log`.
╭─────────────────────────────────────────────────────────────────────────────────────────╮
│               🎯 TARGET WINDOW: btc-updown-5m-1777017900 | ⏱️ T-MINUS: 45s               │
╰─────────────────────────────────────────────────────────────────────────────────────────╯
╭──────── LIVE MARKET & TRIPLE CONFIRMATION ───────╮╭────────── INVENTORY & RISK ────────╮
│                                                   ││                                      │
│  HL Spot Price : $65,150.50                       ││  POSITION : [NONE]                   │
│  Poly Strike   : $65,120.00                       ││  RISK USD : $0.00                    │
|                                                   ││                                      │
│  [TRIPLE CONFIRMATION GATE]                       ││  [TARGET ODDS LIMIT]                 │
│  • GAP ($)     : 30.50     [PASSED]               ││  • UP Ask   : 0.65                   │
│  • CVD (%)     : 52.4%     [PASSED]               ││  • DOWN Ask : 0.40                   │
│  • VELOCITY    : 28.5 $/s  [PASSED]               ││                                      │
│                                                   ││                                      │
╰─────────────────────────────────────────────────╯╰─────────────────────────────────────╯
╭─────────────────────────────────── EXECUTION LOGS ──────────────────────────────────────╮
│ [2026-04-24 16:30:01] 🔄 New Window: btc-updown-5m-1777017900                            │
│ [2026-04-24 16:30:02] 📡 Feed Connected: Hyperliquid & Polymarket                        │
│ [2026-04-24 16:34:15] 🎯 TRIPLE CONFIRMATION MATCH! Gap:30.5, CVD:52%, Vel:28.5          │
│ [2026-04-24 16:34:15] ⚡ ORDER SENT: BUY UP @ 0.65 (Limit)                               │
│ [2026-04-24 16:34:16] ✅ FILLED: 7.69 Shares @ 0.65 | Tx: 0x8f7a...                      │
╰─────────────────────────────────────────────────────────────────────────────────────────╯

### 3.5 File `main.py`
Titik masuk (*entry point*) utama dari keseluruhan sistem.
- Menjalankan seluruh proses secara konkuren tanpa saling memblokir.
- Wajib menggunakan `asyncio.gather()` untuk merangkai:
  1. `poly_feed` loop
  2. `hyperliquid_feed` loop
  3. `directional_engine` loop
  4. `ui` rendering loop

---

## 04 · Verification Plan (Pre-Flight Audit)

1. **Triple Confirmation Alignment:** Memastikan Gap, CVD, dan Velocity dihitung dan disinkronisasikan dalam hitungan milidetik.
2. **Sizing Precision:** Mengaudit pembulatan 2 desimal pada formula *Flat Risk* untuk menghindari masalah kuantisasi API Polymarket.
3. **Non-Blocking Observability:** Memverifikasi bahwa penulisan ke `ads_execution.log` tidak menunda *order submission* di bawah beban tinggi (HFT mode).
