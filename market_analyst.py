import pandas as pd
import numpy as np
import time
import logging
import json
import os
from datetime import datetime

class MarketAnalyst:
    def __init__(self, trades_csv="trades.csv", log_file="ads_execution.log"):
        self.trades_csv = trades_csv
        self.log_file = log_file
        self.logger = logging.getLogger("Analyst")

    def analyze_performance(self):
        """Analyzes the trades.csv to find success rates and habits."""
        if not os.path.exists(self.trades_csv):
            return {"error": "No trades recorded yet."}
        
        try:
            df = pd.read_csv(self.trades_csv)
            if df.empty:
                return {"error": "Trades file is empty."}
            
            total_trades = len(df)
            filled_trades = len(df[df['fill_status'] == 'FILLED'])
            rejected_trades = len(df[df['fill_status'] == 'REJECTED'])
            
            # Analyze Bias Habit
            up_trades = len(df[df['bias'] == 'UP'])
            down_trades = len(df[df['bias'] == 'DOWN'])
            
            summary = {
                "total_trades": total_trades,
                "success_rate": f"{(filled_trades/total_trades)*100:.1f}%" if total_trades > 0 else "0%",
                "rejections": rejected_trades,
                "bias_distribution": {"UP": up_trades, "DOWN": down_trades},
                "avg_latency": df['latency'].str.replace('ms', '').astype(float).mean() if 'latency' in df.columns else 0
            }
            return summary
        except Exception as e:
            return f"Error analyzing trades: {e}"

    def get_market_habits(self):
        """Extracts market patterns from the logs."""
        if not os.path.exists(self.log_file):
            return "Log file not found."
        
        habits = []
        try:
            # Read last 1000 lines of log
            with open(self.log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()[-1000:]
            
            # Look for specific patterns
            feed_deaths = [l for l in lines if "DEAD" in l]
            rejections = [l for l in lines if "REJECTED" in l]
            
            if feed_deaths:
                habits.append(f"Detected {len(feed_deaths)} feed instability events recently.")
            
            if rejections:
                habits.append(f"Market is rejecting orders. High volatility or low liquidity detected.")

            # Logic for 'Habit' - e.g. clustering of signals
            return habits
        except Exception as e:
            return f"Error reading logs: {e}"

    def get_realtime_state(self):
        """Reads the realtime state exported by the engine."""
        state_file = "/root/direct/bot_state.json"
        if not os.path.exists(state_file):
            return "No realtime state found. Is the bot running?"
        
        try:
            with open(state_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            return f"Error reading state: {e}"

    def generate_report(self):
        perf = self.analyze_performance()
        habits = self.get_market_habits()
        rt_state = self.get_realtime_state()
        
        report = f"📊 **LAPORAN INTELIJEN MARKET ADS v1.0** 📊\n"
        report += f"Waktu Laporan: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        report += "🔍 **1. Status Bot Real-time:**\n"
        if isinstance(rt_state, dict):
            report += f"- Status: {rt_state.get('status', 'Tidak Diketahui')}\n"
            report += f"- Sisa Waktu (T-Minus): {rt_state.get('t_minus', 'N/A')} detik\n"
            report += f"- Gap Saat Ini: {rt_state.get('gap', 0.0):.2f}\n"
            report += f"- Bias: {rt_state.get('bias', 'NETRAL')}\n"
            report += f"- Kesehatan Feed: HL={'✅ OK' if rt_state.get('binance_connected', False) else '❌ MATI'} | PL={'✅ OK' if rt_state.get('binance_connected', False) else '❌ MATI'}\n"
        else:
            report += f"- {rt_state}\n"

        report += "\n📈 **2. Performa Historis:**\n"
        if isinstance(perf, dict) and "error" in perf:
            report += f"- Status: {perf['error']}\n"
        elif isinstance(perf, dict):
            report += f"- Total Percobaan Sinyal: {perf.get('total_trades', 0)}\n"
            report += f"- Tingkat Penolakan (Rejected): {perf.get('rejections', 0)}\n"
            report += f"- Dominasi Bias: {perf.get('bias_distribution', {})}\n"
        
        report += "\n🧠 **3. Kebiasaan Market & Anomali:**\n"
        obs = ', '.join(habits) if isinstance(habits, list) and habits else "Market bergerak normal."
        report += f"- Observasi: {obs}\n"

        report += "\n💡 **4. Saran Strategis Quant:**\n"
        if isinstance(perf, dict) and perf.get('rejections', 0) > 0:
            report += "- SARAN: Naikkan saldo wallet untuk menghindari penolakan order minimal (min $5).\n"
        else:
            report += "- SARAN: Logika eksekusi sudah optimal, menunggu sinyal berikutnya.\n"
            
        return report

if __name__ == "__main__":
    analyst = MarketAnalyst()
    print(analyst.generate_report())
