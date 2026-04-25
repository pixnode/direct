# 🔐 ADS v1.0 — FULL SYSTEM AUDIT REPORT & AI AGENT MASTER PROMPT
**Polymarket BTC 5-Minute Binary Market Trading System**
*Perspektif: Senior Python Developer · Senior Quant Trader · Senior Quant Developer · HFT Architect*

---

> **Tanggal Audit:** 2025-04  
> **Versi Sistem:** ADS v1.0  
> **Target Market:** Polymarket BTC Up/Down 5-Minute Binary  
> **Stack:** Python 3.11 · asyncio · WebSocket · py_clob_client · aiohttp · rich

---

## 📋 DAFTAR ISI

1. [Executive Summary](#1-executive-summary)
2. [Critical Security Issue](#2-critical-security-issue)
3. [Audit Per Modul](#3-audit-per-modul)
   - 3.1 [config.py](#31-configpy)
   - 3.2 [hyperliquid_feed.py](#32-hyperliquid_feedpy)
   - 3.3 [poly_feed.py](#33-poly_feedpy)
   - 3.4 [discovery.py](#34-discoverypy)
   - 3.5 [directional_engine.py](#35-directional_enginepy)
   - 3.6 [executor.py](#36-executorpy)
   - 3.7 [main.py & headless.py](#37-mainpy--headlesspy)
   - 3.8 [ui.py](#38-uipy)
4. [Analisa Strategy & Edge](#4-analisa-strategy--edge)
5. [Arsitektur & Pipeline Issues](#5-arsitektur--pipeline-issues)
6. [Priority Fix Roadmap](#6-priority-fix-roadmap)
7. [Score Card](#7-score-card)
8. [🤖 MASTER PROMPT — AI Agent Refactor](#8--master-prompt--ai-agent-refactor)

---

## 1. Executive Summary

ADS v1.0 adalah sistem **directional binary trading bot** yang:
- Membaca price dari Hyperliquid WebSocket (BTC perp) sebagai **primary signal**
- Membaca orderbook Polymarket CLOB sebagai **execution target**
- Menggunakan gap (HL spot vs strike), OFI (mislabeled CVD), dan velocity sebagai **triple-confirmation signal**
- Mengeksekusi order di Polymarket via `py_clob_client` dalam window T-90s hingga T-15s sebelum settlement

**Sistem ini memiliki fondasi konsep yang valid**, namun mengandung **8 bug kritikal** (termasuk 1 yang menyebabkan event loop freeze saat eksekusi), **4 race condition**, **3 logic error di state machine**, dan **strategy edge yang belum tervalidasi secara empiris**.

---

## 2. Critical Security Issue

### 🚨 CREDENTIALS EXPOSED — TINDAKAN WAJIB SEGERA

File `_env` yang di-commit/upload mengandung **live credentials**:

```
POLYMARKET_PRIVATE_KEY=0xf1959c65187cd3d3e9a177ea03c9c4a0e4f5aadd72486f8c04dbc6c99465fdbf
POLYMARKET_API_KEY=d54a5661-37b2-4bd6-8df9-733ca22f1040
POLYMARKET_API_SECRET=MX2tH4kMSl31zLwFx6fXwzZt1TlOED9GdkRcvCH9Mh4=
POLYMARKET_API_PASSPHRASE=f7424b3bb99da25f357737eec59ae6cf0fa8ea79a583f139faf9af309282830e
```

**Risiko:** Siapapun yang mendapat file ini bisa:
1. Menguras dana dari wallet (private key exposed)
2. Menempatkan order sembarangan atas nama akun kamu
3. Membatalkan semua open orders

**Tindakan wajib:**
- [ ] **Segera pindahkan dana** dari wallet yang private key-nya ter-expose ke wallet baru yang bersih
- [ ] **Rotate API credentials** di Polymarket dashboard
- [ ] **Tambahkan `.env` ke `.gitignore`** dan hapus dari seluruh commit history (`git filter-branch` atau BFG Repo Cleaner)
- [ ] **Jangan pernah** commit file `.env` — gunakan `.env.example` sebagai template kosong

```bash
# .gitignore wajib ada:
.env
_env
*.env
```

---

## 3. Audit Per Modul

---

### 3.1 `config.py`

**Rating: ⚠️ 6/10**

#### Bug #1 — Default Value Mismatch antara `config.py` dan `.env`

| Parameter | Default di `config.py` | Nilai di `.env` | Impact |
|---|---|---|---|
| `CVD_THRESHOLD_PCT` | `25.0` | `15.0` | Gate 67% lebih ketat jika `.env` gagal load |
| `VELOCITY_MIN_DELTA` | `15.0` | `3.0` | Gate 5x lebih ketat |
| `CONFIRMATION_WINDOW_START` | `120` | `45` | Window 2.7x lebih panjang |
| `OVERRIDE_WINDOW_START` | `25` | `90` | **Inverted logic** — override jadi lebih sempit dari confirmation |

**Dampak:** Jika `.env` tidak ter-load (deploy di container, path salah, file tidak ada), sistem berjalan dengan parameter yang sangat berbeda — bisa sama sekali tidak pernah trigger atau trigger terlalu agresif. Ini adalah **silent misconfiguration** yang sangat sulit di-debug di production.

#### Bug #2 — Tidak Ada Startup Validation

Sistem bisa berjalan tanpa API credentials dan hanya error saat eksekusi — sudah kehilangan opportunity window.

#### Solusi Lengkap `config.py`:

```python
import os
import sys
from dotenv import load_dotenv

# Strict load — error jika tidak ada
if not load_dotenv(override=True):
    print("FATAL: .env file not found. Cannot start.", file=sys.stderr)
    sys.exit(1)

def _require(key: str, cast=str):
    val = os.getenv(key)
    if not val:
        print(f"FATAL: Required env var '{key}' is missing or empty.", file=sys.stderr)
        sys.exit(1)
    try:
        return cast(val)
    except (ValueError, TypeError) as e:
        print(f"FATAL: Cannot parse '{key}': {e}", file=sys.stderr)
        sys.exit(1)

def _optional(key: str, default, cast=str):
    val = os.getenv(key)
    if val is None:
        return default
    try:
        return cast(val)
    except (ValueError, TypeError):
        return default

# Execution Credentials — REQUIRED
POLYMARKET_PRIVATE_KEY    = _require("POLYMARKET_PRIVATE_KEY")
POLYMARKET_API_KEY        = _require("POLYMARKET_API_KEY")
POLYMARKET_API_SECRET     = _require("POLYMARKET_API_SECRET")
POLYMARKET_API_PASSPHRASE = _require("POLYMARKET_API_PASSPHRASE")
POLYMARKET_HOST           = _optional("POLYMARKET_HOST", "https://clob.polymarket.com")
CHAIN_ID                  = _optional("CHAIN_ID", 137, int)

# Strategy Thresholds — dengan default yang SAMA dengan .env
GAP_THRESHOLD_DEFAULT     = _optional("GAP_THRESHOLD_DEFAULT", 45.0, float)
CVD_THRESHOLD_PCT         = _optional("CVD_THRESHOLD_PCT", 15.0, float)   # FIX: was 25.0
VELOCITY_MIN_DELTA        = _optional("VELOCITY_MIN_DELTA", 3.0, float)   # FIX: was 15.0
VELOCITY_WINDOW_SECONDS   = _optional("VELOCITY_WINDOW_SECONDS", 2.0, float)

# Sniper Parameters
CONFIRMATION_WINDOW_START = _optional("CONFIRMATION_WINDOW_START", 45, int)  # FIX: was 120
OVERRIDE_WINDOW_START     = _optional("OVERRIDE_WINDOW_START", 90, int)      # FIX: was 25
SNIPER_ZONE_END           = _optional("SNIPER_ZONE_END", 15, int)
OVERRIDE_GAP_THRESHOLD    = _optional("OVERRIDE_GAP_THRESHOLD", 90.0, float)

# Execution Parameters
DIRECTIONAL_MAX_ODDS      = _optional("DIRECTIONAL_MAX_ODDS", 0.78, float)
BASE_SHARES               = _optional("BASE_SHARES", 1.0, float)
HEARTBEAT_INTERVAL        = _optional("HEARTBEAT_INTERVAL", 1.0, float)

# Sanity check ranges
assert 0 < GAP_THRESHOLD_DEFAULT < 10000, "GAP_THRESHOLD out of range"
assert 0 < CVD_THRESHOLD_PCT < 100, "CVD_THRESHOLD must be 0-100%"
assert 0 < DIRECTIONAL_MAX_ODDS <= 1.0, "MAX_ODDS must be 0-1"
assert SNIPER_ZONE_END < CONFIRMATION_WINDOW_START, "Window config invalid"
```

---

### 3.2 `hyperliquid_feed.py`

**Rating: ⚠️ 6.5/10**

#### Bug #3 — CVD Formula Salah Secara Quant

**Kode saat ini:**
```python
total_vol = cvd_buy + cvd_sell
self.cvd_value = ((cvd_buy - cvd_sell) / total_vol) * 100.0
```

**Masalah:** Ini adalah **Volume Imbalance Percentage (VIP)** atau **Order Flow Imbalance (OFI)**, BUKAN Cumulative Volume Delta (CVD). Perbedaannya:

| Metrik | Formula | Range | Sifat |
|---|---|---|---|
| **CVD (benar)** | `Σ(buy_vol - sell_vol)` | Unbounded | Cumulative, running sum |
| **OFI/VIP (kode saat ini)** | `(buy - sell) / total * 100` | -100% s/d +100% | Normalized per window |

OFI/VIP yang diimplementasi sebenarnya **valid dan berguna** untuk binary signal dalam window pendek — hanya saja salah nama. Pastikan threshold `CVD_THRESHOLD_PCT=15` dikalibrasi untuk OFI (normalized), bukan CVD (unbounded).

#### Bug #4 — Velocity Terlalu Naive dan Noise-Prone

```python
# Hanya delta price antara trade pertama dan terakhir dalam 2 detik
self.velocity_value = newest_velocity_price - oldest_velocity_price
```

Masalah:
- Satu outlier trade (fat finger, liquidation spike) bisa buat velocity spike besar yang palsu
- Tidak ada minimum trade count
- BTC di kondisi volatile bisa bergerak $50 dalam 2 detik secara normal — tidak ada normalisasi

**Solusi:**
```python
def _calculate_velocity(self):
    trades = list(self.vel_trades)
    
    # Minimum trade count untuk validitas signal
    if len(trades) < 3:
        self.velocity_value = 0.0
        return
    
    # VWAP antara paruh pertama dan kedua window (lebih robust dari edge-to-edge)
    mid = len(trades) // 2
    early_trades = trades[:mid]
    late_trades = trades[mid:]
    
    def vwap(t_list):
        total_val = sum(p * s for _, p, s, _ in t_list)
        total_sz = sum(s for _, _, s, _ in t_list)
        return total_val / total_sz if total_sz > 0 else 0.0
    
    early_vwap = vwap(early_trades)
    late_vwap = vwap(late_trades)
    
    if early_vwap > 0:
        self.velocity_value = late_vwap - early_vwap
    else:
        self.velocity_value = 0.0
```

#### Bug #5 — Tidak Ada Exponential Backoff pada Reconnect

```python
except Exception as e:
    self.is_connected = False
    await asyncio.sleep(1)  # Fixed — langsung hammer server
```

**Solusi:**
```python
async def connect(self):
    attempt = 0
    while True:
        try:
            backoff = min(0.5 * (2 ** attempt), 30.0)  # Max 30 detik
            if attempt > 0:
                logger.warning(f"HL reconnect attempt {attempt}, waiting {backoff:.1f}s")
                await asyncio.sleep(backoff)
            
            async with websockets.connect(
                self.ws_url,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5
            ) as ws:
                self.is_connected = True
                attempt = 0  # Reset on success
                ...
        except Exception as e:
            self.is_connected = False
            attempt += 1
```

#### Bug #6 — Missing `ping_interval` pada WebSocket

Tanpa `ping_interval`, koneksi yang idle (pasar sepi, malam hari) akan timeout secara silent tanpa exception — feed tampak "connected" tapi tidak ada data.

```python
async with websockets.connect(
    self.ws_url,
    ping_interval=20,    # Kirim ping setiap 20 detik
    ping_timeout=10,     # Timeout kalau tidak ada pong dalam 10 detik
) as ws:
```

---

### 3.3 `poly_feed.py`

**Rating: ⚠️ 6/10**

#### Bug #7 — Stale Price Risk Pasca Reconnect

Saat WebSocket disconnect dan reconnect, nilai `up_ask` dan `down_ask` dari sebelum disconnect masih tersimpan dan digunakan untuk keputusan eksekusi. Ini bisa trigger order dengan harga yang sudah tidak valid.

**Solusi — Tambahkan timestamp per ask:**
```python
def __init__(self):
    ...
    self.up_ask = 0.0
    self.down_ask = 0.0
    self.up_ask_updated_at = 0.0    # TAMBAH
    self.down_ask_updated_at = 0.0  # TAMBAH
    self.ASK_STALENESS_THRESHOLD = 10.0  # Detik

def _update_ask(self, asset_id, price):
    now = asyncio.get_event_loop().time()
    if asset_id == self.token_id_up and price > 0:
        self.up_ask = price
        self.up_ask_updated_at = now
    elif asset_id == self.token_id_down and price > 0:
        self.down_ask = price
        self.down_ask_updated_at = now

def get_state(self):
    now = asyncio.get_event_loop().time()
    # Return 0.0 jika data stale (lebih aman — engine akan skip eksekusi)
    fresh_up = self.up_ask if (now - self.up_ask_updated_at) < self.ASK_STALENESS_THRESHOLD else 0.0
    fresh_down = self.down_ask if (now - self.down_ask_updated_at) < self.ASK_STALENESS_THRESHOLD else 0.0
    return {
        "up_ask": fresh_up,
        "down_ask": fresh_down,
        ...
    }
```

#### Bug #8 — `float()` Cast Bisa Crash pada Data Tidak Valid

```python
price = float(change.get("best_ask", 0))  # float(None) = TypeError!
```

**Solusi:**
```python
def _safe_float(val, default=0.0) -> float:
    try:
        f = float(val)
        return f if f > 0 else default
    except (TypeError, ValueError):
        return default
```

#### Bug #9 — Race Condition pada `update_subscription`

```python
async def update_subscription(self, token_up, token_down, strike):
    self.token_id_up = token_up       # Set token baru
    self.token_id_down = token_down
    self.strike_price = strike
    # ← Context switch bisa terjadi di sini (karena await berikutnya)
    if self.ws and self.is_connected:
        await self.ws.send(...)       # WS masih subscribe token lama
```

Jika ada message yang masuk antara assignment token dan send subscription, `_process_message` akan assign harga ke token baru tapi data masih dari token lama.

**Solusi — Atomic update dengan tuple:**
```python
async def update_subscription(self, token_up, token_down, strike):
    # Simpan state lama untuk validasi
    old_up = self.token_id_up
    
    # Atomic-ish assignment (single expression di Python)
    self.token_id_up, self.token_id_down, self.strike_price = token_up, token_down, strike
    
    # Reset harga lama agar tidak stale
    self.up_ask = 0.0
    self.down_ask = 0.0
    self.up_ask_updated_at = 0.0
    self.down_ask_updated_at = 0.0
    
    if self.ws and self.is_connected:
        try:
            sub_msg = {
                "assets_ids": [token_up, token_down],
                "type": "market",
                "custom_feature_enabled": True
            }
            await self.ws.send(json.dumps(sub_msg))
            logger.info(f"PolyFeed: Subscribed to {token_up[:8]}.../{token_down[:8]}...")
        except Exception as e:
            logger.error(f"Poly Sub Error: {e}")
```

---

### 3.4 `discovery.py`

**Rating: ⚠️ 6/10**

#### Bug #10 — `aiohttp.ClientSession` Leak

Session HTTP tidak pernah di-close. Dalam bot yang berjalan berhari-hari, ini accumulate file descriptor dan memory.

```python
class MarketDiscovery:
    def __init__(self):
        ...
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(limit=10, ttl_dns_cache=300)
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10, connect=5),
                connector=connector
            )
        return self._session

    async def close(self):
        """Panggil saat shutdown."""
        if self._session and not self._session.closed:
            await self._session.close()
```

#### Bug #11 — Strike Parsing Sangat Fragile

```python
parts = group_item.split()
strike_str = parts[-1].replace("$", "").replace(",", "")
strike = float(strike_str)
```

Tidak ada validasi range — kalau parse menghasilkan angka di luar range BTC yang masuk akal, sistem trading terhadap strike yang salah.

**Solusi dengan validasi:**
```python
def _parse_strike(self, market: dict) -> float:
    """Parse strike price dari berbagai field dengan fallback chain."""
    
    BTC_MIN, BTC_MAX = 1_000.0, 1_000_000.0  # Sanity range
    
    def validate(price: float) -> float | None:
        return price if BTC_MIN < price < BTC_MAX else None

    # Attempt 1: groupItemTitle
    try:
        group_item = market.get("groupItemTitle", "")
        if group_item and group_item != "0":
            parts = group_item.split()
            strike_str = parts[-1].replace("$", "").replace(",", "")
            result = validate(float(strike_str))
            if result:
                return result
    except (ValueError, IndexError):
        pass

    # Attempt 2: question field regex
    try:
        import re
        question = market.get("question", "")
        match = re.search(r'\$([\d,]+\.?\d*)', question)
        if match:
            result = validate(float(match.group(1).replace(",", "")))
            if result:
                return result
    except (ValueError, AttributeError):
        pass

    # Attempt 3: outcome prices midpoint jika ada
    logger.warning(f"Could not parse strike for market: {market.get('slug', 'unknown')}")
    return 0.0
```

#### Bug #12 — Epoch Target Discovery Ambigu

```python
# Di directional_engine.py:
epoch = self.discovery.get_current_epoch()
market_data = await self.discovery.discover_tokens(epoch)
```

`get_current_epoch()` mengembalikan epoch yang **sedang berjalan**. Market Polymarket untuk epoch ini mungkin sudah settle atau belum tersedia. Perlu discovery untuk **next epoch** saat mendekati akhir current epoch.

**Solusi:**
```python
# Di _discovery_loop:
now = int(time.time())
epoch = self.discovery.get_current_epoch()
t_until_next = self.discovery.get_next_epoch() - now

# Prioritas: gunakan next epoch jika current epoch sudah > 250 detik berjalan
# (artinya sudah melewati semua execution windows)
if t_until_next < 50:
    # Sudah sangat dekat pergantian epoch, discovery untuk epoch berikutnya
    target_epoch = self.discovery.get_next_epoch()
else:
    target_epoch = epoch
```

---

### 3.5 `directional_engine.py`

**Rating: ❌ 5.5/10** — *Modul paling kritis, mengandung bug logic terbanyak*

#### Bug #13 — Window Reset Logic Salah (Highest Priority Logic Bug)

**Kode saat ini:**
```python
current_window = int(now - (now % 300))
if current_window != self.window_start:
    self.window_start = current_window
    self.order_sent = False  # Reset order flag
```

**Masalah:** Reset `order_sent` berbasis UNIX modulo 300 (wall clock), bukan pergantian epoch Polymarket. Epoch Polymarket memiliki offset tersendiri dari UNIX epoch. Ini bisa menyebabkan:
- `order_sent` di-reset di tengah epoch → **duplikasi order pada market yang sama**
- Atau epoch berganti tapi window UNIX belum → **tidak bisa order di epoch baru**

**Solusi — Reset berbasis epoch, bukan wall clock:**
```python
# Di _discovery_loop, saat epoch berganti:
if epoch != self.current_epoch:
    await self._async_log(f"NETWORK: New Epoch Detected: {epoch}")
    self.current_epoch = epoch
    self.token_up = None
    
    # Reset order state HANYA saat epoch benar-benar berganti
    self.order_sent = False
    self.status = "IDLE"
    self.gate_passed = False
    await self._async_log("ORDER LOCK RELEASED: New epoch")

# Di run() loop, HAPUS window reset logic berbasis wall clock:
# REMOVED: current_window = int(now - (now % 300))
# REMOVED: if current_window != self.window_start: self.order_sent = False
```

#### Bug #14 — State Machine Dead Zone dan UI Mismatch

**Dengan config `.env`:** `CONFIRMATION_WINDOW_START=45`, `OVERRIDE_WINDOW_START=90`

```python
max_window = max(45, 90) = 90

# Status SNIPER_READY aktif mulai T-105
elif SNIPER_ZONE_END < self.t_minus <= max_window + 15:  # 15 < t <= 105
    self.status = "SNIPER_READY"

# Tapi eksekusi triple HANYA bisa T-45 ke bawah:
if SNIPER_ZONE_END <= self.t_minus <= CONFIRMATION_WINDOW_START:  # 15 <= t <= 45
    can_execute = True
```

**Hasil:** T-105 hingga T-46 → UI bilang `SNIPER_READY` tapi tidak ada yang bisa ditrigger → **misleading dan confusing untuk monitoring**.

**Solusi — State machine yang akurat:**
```python
# Status lebih granular dan akurat
if self.t_minus > OVERRIDE_WINDOW_START + 15:
    self.status = "IDLE"
elif OVERRIDE_WINDOW_START < self.t_minus <= OVERRIDE_WINDOW_START + 15:
    self.status = "ARMING"          # Mendekati override window
elif CONFIRMATION_WINDOW_START < self.t_minus <= OVERRIDE_WINDOW_START:
    self.status = "OVERRIDE_WATCH"  # Dalam override window saja
elif SNIPER_ZONE_END < self.t_minus <= CONFIRMATION_WINDOW_START:
    self.status = "SNIPER_READY"    # Dalam KEDUA windows — siap eksekusi
elif self.t_minus <= SNIPER_ZONE_END:
    self.status = "CEASE_FIRE"      # Terlalu dekat settlement
```

#### Bug #15 — Veto Threshold Hardcoded dan Inkonsisten

```python
# Veto threshold hardcoded di -30/+30
if self.bias == "UP" and cvd < -30:    # Hardcoded
    veto = True
elif self.bias == "DOWN" and cvd > 30:  # Hardcoded

# Tapi CVD gate dari config = 15%
# Zone 15% - 30% = ambigu: pass CVD gate tapi tidak kena veto
```

**Solusi:**
```python
# Di config.py tambahkan:
VETO_MULTIPLIER = _optional("VETO_MULTIPLIER", 2.0, float)  # 2x threshold = veto

# Di engine:
veto_threshold = CVD_THRESHOLD_PCT * VETO_MULTIPLIER  # = 30% default, tapi konfigurasional
veto = False
if self.bias == "UP" and cvd < -veto_threshold:
    veto = True
    await self._async_log(f"VETO: Bearish CVD {cvd:.1f}% opposes UP bias")
elif self.bias == "DOWN" and cvd > veto_threshold:
    veto = True
    await self._async_log(f"VETO: Bullish CVD {cvd:.1f}% opposes DOWN bias")
```

#### Bug #16 — `asyncio.create_task` Fire-and-Forget Silent Failure

```python
asyncio.create_task(self.executor.execute(
    bias=self.bias,
    size=BASE_SHARES,
    ...
))
```

Task ini tidak ada error handling — jika executor throw exception, error **hilang tanpa trace** di log.

**Solusi:**
```python
async def _execute_with_guard(self, **kwargs):
    """Wrapper dengan proper error handling dan state feedback."""
    try:
        success = await self.executor.execute(**kwargs)
        if success:
            await self._async_log(f"EXECUTION SUCCESS: {kwargs['bias']} @ {kwargs['target_ask']}")
        else:
            await self._async_log(f"EXECUTION REJECTED by exchange: {kwargs['bias']}")
            # Pertimbangkan: apakah order_sent harus di-reset jika rejected?
            # Umumnya TIDAK — untuk mencegah retry spam
    except Exception as e:
        await self._async_log(f"EXECUTION EXCEPTION: {type(e).__name__}: {e}")
        # Jangan reset order_sent — hindari double-order pada partial fill scenario

asyncio.create_task(self._execute_with_guard(
    bias=self.bias,
    size=BASE_SHARES,
    target_ask=target_ask,
    token_up=self.token_up,
    token_down=self.token_down
))
```

#### Bug #17 — `inventory_risk` Tidak Pernah Reset dan Tidak Akurat

```python
self.inventory_risk += (BASE_SHARES * target_ask)
```

Ini accumulate selamanya, tidak reset per epoch, tidak track apakah order fill atau tidak. Angka ini tidak berguna untuk risk management nyata.

**Solusi minimal:**
```python
# Di __init__:
self.epoch_orders = []  # List of {epoch, bias, size, ask, status}
self.total_spent = 0.0
self.current_epoch_spent = 0.0

# Saat order dikirim:
order_record = {
    "epoch": self.current_epoch,
    "bias": self.bias,
    "size": BASE_SHARES,
    "ask": target_ask,
    "cost": BASE_SHARES * target_ask,
    "status": "SENT",
    "timestamp": time.time()
}
self.epoch_orders.append(order_record)
self.total_spent += order_record["cost"]

# Reset saat epoch berganti:
self.current_epoch_spent = 0.0
```

---

### 3.6 `executor.py`

**Rating: ❌ 6/10** — *Mengandung bug paling kritis: blocking event loop*

#### Bug #18 — 🔴 BLOCKING SYNCHRONOUS CALL DI ASYNC CONTEXT

**Ini adalah bug paling serius di seluruh sistem.**

```python
async def execute(self, ...):
    ...
    resp = self.client.create_and_post_order(order_args)  # ← BLOCKING!
```

`py_clob_client` menggunakan library `requests` yang **synchronous**. Memanggil ini dari `async def` **memblokir seluruh event loop** Python selama HTTP request berlangsung (biasanya 200ms - 2000ms).

**Dampak nyata:**
- Seluruh WebSocket feed (HL + Poly) berhenti menerima data
- Heartbeat berhenti
- Discovery loop berhenti
- Semua ini terjadi **tepat di momen paling kritis** — saat order baru dikirim

**Solusi — Jalankan di thread pool:**
```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

class Executor:
    def __init__(self):
        ...
        self._thread_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="clob_exec")

    async def execute(self, bias, size, target_ask, token_up, token_down):
        if not self.is_ready:
            logger.error("Executor not ready. Skipping trade.")
            return False

        token_to_buy = token_up if bias == "UP" else token_down
        expiry = int(time.time()) + 280

        order_args = OrderArgs(
            price=target_ask,
            size=size,
            side="BUY",
            token_id=token_to_buy,
            expiration=expiry
        )

        loop = asyncio.get_event_loop()
        try:
            # NON-BLOCKING: jalankan di thread pool
            resp = await loop.run_in_executor(
                self._thread_pool,
                self.client.create_and_post_order,
                order_args
            )
            
            if resp and resp.get("success"):
                logger.info(f"LIVE EXECUTED: BUY {bias} | {size} shares @ {target_ask} | Token: {token_to_buy}")
                return True
            else:
                logger.error(f"ORDER REJECTED: {resp}")
                return False
        except Exception as e:
            logger.error(f"Execution Error: {type(e).__name__}: {e}")
            return False

    async def shutdown(self):
        self._thread_pool.shutdown(wait=True)
```

#### Bug #19 — Expiry Tidak Berhubungan dengan Epoch End Time

```python
expiry = int(time.time()) + 280  # Hardcoded 4m40s
```

Jika eksekusi terjadi di T-20 (20 detik sebelum settlement), order ini akan expire di T+260 — **jauh setelah settlement sudah terjadi**. Order bisa matched ke epoch yang salah atau floating di pasar yang sudah resolved.

**Solusi:**
```python
async def execute(self, bias, size, target_ask, token_up, token_down, 
                  epoch_end_time: int):  # TAMBAH parameter
    ...
    # Expire 10 detik sebelum epoch end, tapi minimum 30 detik dari sekarang
    now = int(time.time())
    expiry = max(
        now + 30,                   # Minimal 30 detik agar bisa filled
        epoch_end_time - 10         # Expire sebelum settlement
    )
    ...
```

#### Bug #20 — Tidak Ada Retry Logic untuk Network Errors

```python
resp = self.client.create_and_post_order(order_args)
# Satu kali coba — network blip = miss opportunity
```

**Solusi dengan retry terbatas:**
```python
MAX_RETRIES = 2

for attempt in range(MAX_RETRIES + 1):
    try:
        resp = await loop.run_in_executor(
            self._thread_pool,
            self.client.create_and_post_order,
            order_args
        )
        if resp and resp.get("success"):
            return True
        elif attempt < MAX_RETRIES:
            logger.warning(f"Order attempt {attempt+1} rejected, retrying... {resp}")
            await asyncio.sleep(0.1 * (attempt + 1))
    except Exception as e:
        if attempt == MAX_RETRIES:
            raise
        logger.warning(f"Order attempt {attempt+1} failed: {e}, retrying...")
        await asyncio.sleep(0.2 * (attempt + 1))
```

---

### 3.7 `main.py` & `headless.py`

**Rating: ⚠️ 7/10**

#### Bug #21 — Tidak Ada Task Supervision / Auto-Restart

```python
tasks = [
    asyncio.create_task(hl_feed.run()),    # Kalau crash?
    asyncio.create_task(poly_feed.run()),   # Kalau crash?
    asyncio.create_task(engine.run()),      # Kalau crash?
]
await asyncio.gather(*tasks)
```

Jika satu task crash (mis: `hl_feed` koneksi putus tidak ter-handle), `asyncio.gather` akan cancel semua task lain lalu exit. **Bot mati tanpa restart.**

**Solusi — Supervised task pattern:**
```python
async def supervised(name: str, coro_factory, restart_delay: float = 5.0):
    """Restart coroutine jika crash, dengan delay dan logging."""
    attempt = 0
    while True:
        attempt += 1
        try:
            logging.info(f"[{name}] Starting (attempt {attempt})")
            await coro_factory()
            logging.warning(f"[{name}] Exited cleanly — restarting in {restart_delay}s")
        except asyncio.CancelledError:
            logging.info(f"[{name}] Cancelled. Shutting down.")
            raise
        except Exception as e:
            logging.error(f"[{name}] CRASHED: {type(e).__name__}: {e}. Restarting in {restart_delay}s")
        
        await asyncio.sleep(restart_delay)

# Di main():
tasks = [
    asyncio.create_task(supervised("HL_Feed",   hl_feed.run)),
    asyncio.create_task(supervised("Poly_Feed", poly_feed.run)),
    asyncio.create_task(supervised("Engine",    engine.run)),
]
```

---

### 3.8 `ui.py`

**Rating: ✅ 7.5/10** — *Relatif baik, beberapa minor issues*

#### Minor Issue — Window Display Logic Tidak Sinkron dengan Engine

```python
# Di ui.py:
if 15 <= t <= 45: win_text = "[bold green]TRIPLE WINDOW[/]"
if 15 <= t <= 120 and e_state['gap'] >= 110:  # Hardcoded 110
    win_text = "[bold magenta]OVERRIDE WINDOW[/]"
```

Nilai threshold hardcoded di UI tidak membaca dari `config.py` — jika config diubah, UI tampil salah. Perbaikan: import config dan gunakan nilai yang sama.

---

## 4. Analisa Strategy & Edge

### 4.1 Signal Architecture Assessment

```
Signal Stack:
┌─────────────────────────────────────────────────────┐
│  GAP = HL_Price - Strike                            │
│  → Mengukur seberapa jauh spot dari strike          │
│  → Valid tapi tidak dinormalisasi terhadap vol      │
├─────────────────────────────────────────────────────┤
│  OFI (mislabeled CVD) = (BuyVol - SellVol) / Total │
│  → Order flow pressure dalam 60 detik terakhir     │
│  → Valid metric, nama salah saja                    │
├─────────────────────────────────────────────────────┤
│  VELOCITY = Price[-1] - Price[0] dalam 2 detik      │
│  → Micro-momentum filter                            │
│  → Terlalu noise, perlu smoothing                   │
└─────────────────────────────────────────────────────┘
```

### 4.2 Fundamental Edge Question

Strategy ini betting bahwa **price momentum 90 detik sebelum resolution predicts binary outcome**. Ada beberapa hal yang perlu dipikirkan:

**Kekuatan:**
- Market Polymarket biner punya settlement yang **deterministik** (price di atas/bawah strike saat settlement)
- Gap yang besar memang informasi valid tentang probabilitas outcome
- Execution window T-90 sampai T-15 adalah sweet spot — cukup waktu untuk execute, cukup informasi

**Kelemahan yang perlu diatasi:**

1. **Gap tidak dinormalisasi vs volatility:**
   ```
   Gap $45 saat BTC daily range $200 = strong signal (22.5% of range)
   Gap $45 saat BTC daily range $2000 = weak signal (2.25% of range)
   ```
   Gunakan ATR atau realized vol sebagai normalizer.

2. **Hyperliquid adalah perp futures, bukan spot:**
   - CVD/OFI dari perp dipengaruhi funding rate
   - Saat funding sangat positif (long-heavy), ada tekanan sell dari hedgers
   - Bisa cause false bearish OFI signal meski price naik
   - **Solusi:** Tambahkan Binance spot sebagai co-signal, atau filter berdasarkan funding rate

3. **Market maker sudah price-in informasi yang sama:**
   - Kalau gap = $90 (BTC $90 di atas strike), UP token kemungkinan sudah di-price ~0.82-0.88 oleh MM
   - Dengan `DIRECTIONAL_MAX_ODDS = 0.78`, kamu tidak akan beli kalau odds terlalu tinggi
   - Tapi ini berarti kamu hanya beli di situasi di mana market masih belum sepenuhnya priced-in → artinya signal belum sekuat yang kamu pikirkan

4. **Tidak ada historical backtesting:**
   - Threshold (45, 15%, 3.0) dipilih secara intuitif, bukan berdasarkan data
   - Perlu: collect data → backtest → kalibrasikan threshold secara empiris

### 4.3 Saran Enhancement Strategy

```python
# 1. Gap normalization
from config import GAP_THRESHOLD_DEFAULT

def normalized_gap(gap: float, recent_volatility: float) -> float:
    """Gap sebagai multiple dari recent volatility."""
    return gap / recent_volatility if recent_volatility > 0 else 0.0

# 2. Multi-source signal (tambahkan Binance spot feed)
# Signal lebih kuat kalau Binance spot OFI ALIGN dengan HL perp OFI

# 3. Adaptive threshold berdasarkan time-to-expiry
# Semakin dekat T-0, butuh gap lebih kecil (lebih certain)
def adaptive_gap_threshold(t_minus: int) -> float:
    base = GAP_THRESHOLD_DEFAULT
    if t_minus < 30:
        return base * 0.7  # Lebih lenient dekat settlement
    return base

# 4. Track win rate per gap range untuk kalibrasi
class PerformanceTracker:
    def record_outcome(self, gap_range: str, bias: str, won: bool):
        ...
    def get_win_rate(self, gap_range: str) -> float:
        ...
```

---

## 5. Arsitektur & Pipeline Issues

### 5.1 Data Flow Diagram (Current — Bermasalah)

```
HyperliquidFeed (WS)  ──→  DirectionalEngine.run()  ──→  Executor.execute() [BLOCKS!]
                                      ↑                          │
PolyFeed (WS) ─────────────────────────┘                         │
                                                                  ↓
MarketDiscovery (HTTP) ──→ _discovery_loop()              py_clob_client (sync HTTP)
                                                          [FREEZES EVENT LOOP]
```

### 5.2 Data Flow Diagram (Target — Fixed)

```
HyperliquidFeed (WS) ──┐
                        ├──→ DirectionalEngine.run()  ──→ _execute_with_guard()
PolyFeed (WS) ─────────┘              ↑                        │
                                       │                        ↓
MarketDiscovery (HTTP) → _discovery_loop()          run_in_executor(thread_pool)
                                                              │
                                                              ↓
                                                    py_clob_client (sync, isolated)
```

### 5.3 Missing Components untuk Production-Grade

| Komponen | Status | Prioritas |
|---|---|---|
| Credential rotation | Missing | P0 — Security |
| Task supervision/restart | Missing | P0 — Reliability |
| Blocking call fix | Missing | P0 — Performance |
| Order fill tracking | Missing | P1 — Accounting |
| P&L per epoch | Missing | P1 — Risk Mgmt |
| Backtesting framework | Missing | P1 — Strategy |
| Alerting (Telegram/Discord) | Missing | P2 — Monitoring |
| Rate limiter (API calls) | Missing | P2 — Stability |
| Config hot-reload | Missing | P3 — Ops |

---

## 6. Priority Fix Roadmap

### 🔴 P0 — Critical (Fix Sekarang, Sebelum Run Berikutnya)

| # | Issue | File | Impact |
|---|---|---|---|
| 1 | Rotate credentials yang exposed | `.env` | Security — wallet bisa dikuras |
| 2 | Fix blocking `run_in_executor` | `executor.py` | Event loop freeze saat order |
| 3 | Fix window reset ke epoch-based | `directional_engine.py` | Double order risk |
| 4 | Add stale ask price guard | `poly_feed.py` | Order dengan harga invalid |

### 🟡 P1 — High (Fix Sebelum Live Trading Serius)

| # | Issue | File | Impact |
|---|---|---|---|
| 5 | Fix config default mismatch | `config.py` | Silent misconfiguration |
| 6 | Fix executor expiry calculation | `executor.py` | Order melewati settlement |
| 7 | Add task supervision | `main.py` | Bot mati tanpa restart |
| 8 | Fix state machine dead zone | `directional_engine.py` | UI misleading |
| 9 | Fix `_execute_with_guard` | `directional_engine.py` | Silent execution failures |
| 10 | Add session close/cleanup | `discovery.py` | Resource leak |

### 🟢 P2 — Medium (Enhancement)

| # | Issue | File | Impact |
|---|---|---|---|
| 11 | Fix velocity calculation | `hyperliquid_feed.py` | Noise signal |
| 12 | Add exponential backoff | `hyperliquid_feed.py` | Server hammering |
| 13 | Fix veto threshold config | `directional_engine.py` | Inconsistent logic |
| 14 | Add ping_interval WS | `hyperliquid_feed.py` | Silent disconnects |
| 15 | Fix strike parsing validation | `discovery.py` | Wrong strike price |
| 16 | Fix subscription race condition | `poly_feed.py` | Wrong price assignment |
| 17 | Add P&L tracking per epoch | `directional_engine.py` | No risk visibility |
| 18 | Add execution retry | `executor.py` | Miss on network blip |

### 🔵 P3 — Strategy Enhancement

| # | Enhancement | Benefit |
|---|---|---|
| 19 | Gap normalization vs ATR/vol | More adaptive thresholds |
| 20 | Spot CVD feed (Binance) | Eliminate perp-bias false signals |
| 21 | Historical backtesting framework | Empirical threshold calibration |
| 22 | Dynamic position sizing | Kelly-based risk management |
| 23 | Alerting integration | Real-time monitoring |

---

## 7. Score Card

| Modul | Score | Critical Issue |
|---|---|---|
| `config.py` | **6/10** | Default mismatch, no validation |
| `hyperliquid_feed.py` | **6.5/10** | CVD formula salah, no backoff |
| `poly_feed.py` | **6/10** | Stale price risk, race condition |
| `discovery.py` | **6/10** | Session leak, fragile parsing |
| `directional_engine.py` | **5.5/10** | Window reset bug, dead zone, silent failures |
| `executor.py` | **5/10** | **Blocking event loop (P0)**, bad expiry |
| `main.py` / `headless.py` | **7/10** | No task supervision |
| `ui.py` | **7.5/10** | Hardcoded thresholds |
| **Strategy Logic** | **6/10** | Gap not normalized, perp bias, no backtest |
| **Overall System** | **6/10** | Fondasi valid, implementasi butuh hardening |

---

## 8. 🤖 MASTER PROMPT — AI Agent Refactor

> Copy prompt di bawah ini secara lengkap dan berikan ke AI agent (Claude, GPT-4, dll) bersama dengan seluruh file source code. Agent akan melakukan perbaikan sistematis berdasarkan temuan audit ini.

---

```
===========================================================================
MASTER PROMPT: ADS v1.0 — FULL SYSTEM REFACTOR
Senior Python Developer + HFT Architect Perspective
===========================================================================

KONTEKS:
Kamu adalah Senior Python Developer, Senior Quant Developer, dan HFT Architect
yang bertugas melakukan refactor menyeluruh pada sistem trading bot bernama
ADS v1.0 (Automated Directional Sniper) untuk Polymarket BTC 5-minute binary
market. Sistem ini menggunakan asyncio Python, WebSocket feeds (Hyperliquid +
Polymarket), dan py_clob_client untuk eksekusi order.

File yang perlu di-refactor:
- config.py
- hyperliquid_feed.py
- poly_feed.py
- discovery.py
- directional_engine.py
- executor.py
- main.py
- headless.py

FILOSOFI REFACTOR:
1. JANGAN ubah logika strategy inti (gap/OFI/velocity signal) kecuali diminta
2. JANGAN ubah nama variabel publik yang dipakai oleh modul lain
3. PRIORITASKAN: Correctness → Reliability → Performance → Maintainability
4. Setiap perubahan harus backward-compatible dengan .env yang sudah ada
5. Pertahankan async architecture — JANGAN convert ke synchronous
6. Semua perubahan harus include logging yang informatif

===========================================================================
TASK LIST — Lakukan dalam urutan ini:
===========================================================================

--- TASK 1: config.py ---
Refactor config.py dengan requirements berikut:

a) Ganti mekanisme load_dotenv biasa dengan strict validation:
   - Jika .env tidak ditemukan → print error + sys.exit(1)
   - Jika REQUIRED variable kosong → print error yang spesifik + sys.exit(1)
   - REQUIRED variables: POLYMARKET_PRIVATE_KEY, POLYMARKET_API_KEY,
     POLYMARKET_API_SECRET, POLYMARKET_API_PASSPHRASE

b) SYNC semua default values agar IDENTIK dengan nilai di .env:
   - CVD_THRESHOLD_PCT default: 15.0 (bukan 25.0)
   - VELOCITY_MIN_DELTA default: 3.0 (bukan 15.0)
   - CONFIRMATION_WINDOW_START default: 45 (bukan 120)
   - OVERRIDE_WINDOW_START default: 90 (bukan 25)

c) Tambahkan parameter baru:
   - VETO_MULTIPLIER: float = 2.0
   - ASK_STALENESS_THRESHOLD: float = 10.0
   - WS_PING_INTERVAL: float = 20.0
   - WS_PING_TIMEOUT: float = 10.0
   - MAX_RECONNECT_DELAY: float = 30.0
   - ORDER_EXPIRY_BUFFER: int = 10 (detik sebelum epoch end)
   - MAX_ORDER_RETRIES: int = 2

d) Tambahkan sanity check assertions setelah semua variabel di-load:
   - 0 < GAP_THRESHOLD_DEFAULT < 10000
   - 0 < CVD_THRESHOLD_PCT < 100
   - 0 < DIRECTIONAL_MAX_ODDS <= 1.0
   - SNIPER_ZONE_END < CONFIRMATION_WINDOW_START < OVERRIDE_WINDOW_START

--- TASK 2: executor.py ---
CRITICAL FIX — ini adalah bug paling serius di seluruh sistem.

a) FIX BLOCKING CALL: Wrap `self.client.create_and_post_order()` dengan
   `asyncio.get_event_loop().run_in_executor()` menggunakan ThreadPoolExecutor:
   ```
   self._thread_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="clob_exec")
   resp = await loop.run_in_executor(self._thread_pool, 
                                      self.client.create_and_post_order, 
                                      order_args)
   ```
   JANGAN pernah call synchronous HTTP/requests dari dalam async function tanpa ini.

b) FIX EXPIRY: Tambahkan parameter `epoch_end_time: int` ke method `execute()`.
   Hitung expiry sebagai:
   ```
   expiry = max(int(time.time()) + 30, epoch_end_time - ORDER_EXPIRY_BUFFER)
   ```

c) Tambahkan retry logic dengan MAX_ORDER_RETRIES dari config:
   - Retry hanya untuk network errors, bukan untuk rejection dari exchange
   - Delay antar retry: 0.1 * (attempt + 1) detik
   - Log setiap attempt

d) Tambahkan method `async def shutdown(self)` yang memanggil
   `self._thread_pool.shutdown(wait=False)`

--- TASK 3: directional_engine.py ---

a) FIX WINDOW RESET — Hapus window reset logic berbasis wall clock (modulo 300):
   ```python
   # HAPUS INI:
   current_window = int(now - (now % 300))
   if current_window != self.window_start:
       self.order_sent = False
   ```
   Ganti dengan: reset `order_sent = False` dan `status = "IDLE"` HANYA di dalam
   `_discovery_loop()` saat `epoch != self.current_epoch` terdeteksi.

b) FIX STATE MACHINE — Ganti status logic dengan yang lebih akurat:
   - `IDLE`: t_minus > OVERRIDE_WINDOW_START + 15
   - `ARMING`: OVERRIDE_WINDOW_START < t_minus <= OVERRIDE_WINDOW_START + 15
   - `OVERRIDE_WATCH`: CONFIRMATION_WINDOW_START < t_minus <= OVERRIDE_WINDOW_START
   - `SNIPER_READY`: SNIPER_ZONE_END < t_minus <= CONFIRMATION_WINDOW_START
   - `CEASE_FIRE`: t_minus <= SNIPER_ZONE_END

c) FIX VETO THRESHOLD — Hapus hardcoded -30/+30, ganti dengan:
   ```python
   veto_threshold = CVD_THRESHOLD_PCT * VETO_MULTIPLIER  # dari config
   ```

d) FIX EXECUTOR CALL — Buat wrapper `_execute_with_guard()` async method:
   - Panggil `self.executor.execute()` dengan try/except
   - Log success dan failure dengan detail
   - Pass `epoch_end_time` ke executor (gunakan `self.discovery.get_next_epoch()`)
   - Ganti `asyncio.create_task(self.executor.execute(...))` dengan
     `asyncio.create_task(self._execute_with_guard(...))`

e) FIX INVENTORY TRACKING — Tambahkan:
   - `self.epoch_orders: list = []` — list order per epoch
   - `self.total_spent: float = 0.0` — total uang yang dikeluarkan
   - Reset `epoch_orders` dan `current_epoch_spent` saat epoch berganti
   - Record setiap order ke `epoch_orders` dengan field: epoch, bias, size, ask, cost, timestamp

--- TASK 4: hyperliquid_feed.py ---

a) FIX VELOCITY — Ganti edge-to-edge price delta dengan VWAP-based velocity:
   - Bagi trades dalam vel_trades menjadi dua paruh: early dan late
   - Hitung VWAP untuk masing-masing paruh
   - velocity = late_vwap - early_vwap
   - Jika jumlah trades < 3, set velocity = 0.0

b) FIX RECONNECT — Ganti fixed sleep(1) dengan exponential backoff:
   ```python
   backoff = min(0.5 * (2 ** attempt), MAX_RECONNECT_DELAY)
   await asyncio.sleep(backoff)
   ```
   Reset `attempt = 0` setiap kali berhasil connect.

c) FIX WEBSOCKET — Tambahkan parameter ke `websockets.connect()`:
   ```python
   ping_interval=WS_PING_INTERVAL,
   ping_timeout=WS_PING_TIMEOUT,
   close_timeout=5
   ```

d) UPDATE DOCSTRING — Tambahkan komentar bahwa metric yang dihitung adalah
   "Order Flow Imbalance (OFI)" bukan CVD, meskipun nama variabel tetap sama
   untuk backward compatibility.

--- TASK 5: poly_feed.py ---

a) FIX STALE PRICE — Tambahkan timestamp tracking per ask:
   - `self.up_ask_updated_at: float = 0.0`
   - `self.down_ask_updated_at: float = 0.0`
   - Update timestamp setiap kali ask price diperbarui
   - Di `get_state()`, kembalikan `0.0` untuk ask yang sudah lebih tua dari
     `ASK_STALENESS_THRESHOLD` detik (dari config)

b) FIX FLOAT CAST — Buat helper `_safe_float(val, default=0.0) -> float` dan
   gunakan di semua tempat yang memparse price dari WebSocket message.
   Handle: None, empty string, "None", non-numeric string.

c) FIX SUBSCRIPTION UPDATE — Saat `update_subscription()` dipanggil:
   - Reset `up_ask = 0.0`, `down_ask = 0.0`
   - Reset `up_ask_updated_at = 0.0`, `down_ask_updated_at = 0.0`
   - Ini mencegah stale price dari subscription sebelumnya

d) FIX RECONNECT — Sama dengan hyperliquid_feed: tambahkan exponential backoff
   (ganti `await asyncio.sleep(5)` dengan backoff logic)

--- TASK 6: discovery.py ---

a) FIX SESSION LEAK — Tambahkan method `async def close(self)`:
   ```python
   async def close(self):
       if self._session and not self._session.closed:
           await self._session.close()
   ```

b) FIX STRIKE PARSING — Buat method `_parse_strike(self, market: dict) -> float`
   dengan:
   - Fallback chain: groupItemTitle → question regex → default 0.0
   - Validasi range: 1_000.0 < strike < 1_000_000.0
   - Log warning jika semua parsing gagal

c) FIX SESSION CONFIG — Saat membuat ClientSession, tambahkan:
   ```python
   connector = aiohttp.TCPConnector(limit=10, ttl_dns_cache=300)
   timeout = aiohttp.ClientTimeout(total=10, connect=5)
   ```

--- TASK 7: main.py dan headless.py ---

a) Tambahkan `supervised()` async function:
   ```python
   async def supervised(name: str, coro_factory, restart_delay: float = 5.0):
       attempt = 0
       while True:
           attempt += 1
           try:
               await coro_factory()
           except asyncio.CancelledError:
               raise
           except Exception as e:
               logging.error(f"[{name}] CRASHED (attempt {attempt}): {e}")
           await asyncio.sleep(restart_delay)
   ```

b) Bungkus semua tasks dengan `supervised()`:
   ```python
   tasks = [
       asyncio.create_task(supervised("HL_Feed", hl_feed.run)),
       asyncio.create_task(supervised("Poly_Feed", poly_feed.run)),
       asyncio.create_task(supervised("Engine", engine.run)),
   ]
   ```

c) Di finally block, panggil `await executor.shutdown()` dan
   `await discovery.close()` untuk clean resource.

===========================================================================
CONSTRAINTS — WAJIB DIIKUTI:
===========================================================================

1. PERTAHANKAN semua nama class dan method yang ada (publik interface)
2. PERTAHANKAN format log yang ada (engine sudah punya log parser)
3. JANGAN import library baru selain yang sudah ada di codebase, KECUALI
   `concurrent.futures.ThreadPoolExecutor` (sudah di stdlib)
4. Setiap method baru HARUS punya docstring singkat
5. JANGAN ubah WebSocket URL atau API endpoint
6. JANGAN hapus `order_sent` atomic lock — ini critical untuk mencegah
   double-order, hanya pindahkan tempat reset-nya
7. Semua kode harus kompatibel dengan Python 3.10+

===========================================================================
OUTPUT FORMAT:
===========================================================================

Untuk setiap file yang dimodifikasi:
1. Tulis HEADER: `## FILE: nama_file.py`
2. Tulis CHANGELOG: list perubahan yang dilakukan (bullet points)
3. Tulis FULL FILE CONTENT: kode lengkap (bukan diff/patch)
4. Tulis TEST CASES: minimal 2 unit test per perubahan kritikal

Urutan output: config.py → executor.py → directional_engine.py →
hyperliquid_feed.py → poly_feed.py → discovery.py → main.py → headless.py

===========================================================================
VALIDATION CHECKLIST (Cek setiap file sebelum output):
===========================================================================

[ ] Tidak ada synchronous blocking call di dalam async function
[ ] Semua WebSocket memiliki ping_interval dan reconnect backoff
[ ] Semua float parsing menggunakan safe_float helper
[ ] order_sent hanya di-reset saat epoch berganti (bukan wall clock)
[ ] executor.execute() menerima epoch_end_time parameter
[ ] Semua asyncio.create_task() memiliki error handling
[ ] Tidak ada hardcoded threshold (semua dari config)
[ ] Session/resource cleanup ada di shutdown path
[ ] Tidak ada import yang hilang
[ ] Setiap method baru memiliki docstring

===========================================================================
SETELAH REFACTOR SELESAI:
===========================================================================

Berikan summary dalam format tabel:
| File | Lines Changed | Bugs Fixed | New Features |
|------|--------------|------------|--------------|
| ... | ... | ... | ... |

Dan berikan "Next Steps" untuk enhancement strategy yang disarankan
(normalisasi gap terhadap ATR, spot CVD dari Binance, backtesting framework).

===========================================================================
END OF MASTER PROMPT
===========================================================================
```

---

*Dokumen ini dibuat berdasarkan deep audit ADS v1.0 source code.*  
*Semua temuan diverifikasi terhadap kode aktual, bukan asumsi.*  
*Prioritas perbaikan berbasis impact: Security > Reliability > Correctness > Performance.*

---
**© ADS Audit Report — Confidential**
