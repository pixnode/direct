import asyncio
import time
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from rich.console import Console
from rich.align import Align
from collections import deque

class Dashboard:
    def __init__(self, engine, hl_feed, poly_feed):
        self.engine = engine
        self.hl_feed = hl_feed
        self.poly_feed = poly_feed
        self.logs = deque(maxlen=8)
        self.last_engine_log = ""
        self.start_time = time.time()
        
        # Build Base Layout
        self.layout = Layout()
        self.layout.split(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1),
            Layout(name="logs", size=10)
        )
        self.layout["main"].split_row(
            Layout(name="market"),
            Layout(name="inventory")
        )

    def get_header(self, state):
        status = state.get("status", "IDLE")
        color = "cyan"
        if status == "SNIPER_READY": color = "bold green"
        elif status == "CEASE_FIRE": color = "bold red"
        elif status == "IDLE": color = "yellow"

        uptime = int(time.time() - self.start_time)
        
        grid = Table.grid(expand=True)
        grid.add_column(justify="left", ratio=1)
        grid.add_column(justify="center", ratio=1)
        grid.add_column(justify="right", ratio=1)
        
        grid.add_row(
            Text(f" 🤖 ADS v1.0 | UP: {uptime}s", style="bold white"),
            Text(f"🎯 {state.get('slug', 'SEARCHING...')}", style="bold magenta"),
            Text(f"STATUS: [{status}] ", style=color)
        )
        
        return Panel(grid, style="white on blue", box=None)

    def get_market_table(self, e_state, h_state, p_state):
        table = Table(show_header=False, box=None, padding=(0, 1), expand=True)
        table.add_column("Key", style="bold white", width=15)
        table.add_column("Val", justify="right", width=12)
        table.add_column("Ind", justify="center", width=10)

        # Feed Health
        loop_now = asyncio.get_event_loop().time()
        h_ok = (loop_now - h_state.get("last_msg_time", 0)) < 5
        p_ok = (loop_now - p_state.get("last_msg_time", 0)) < 5
        
        def ok_fail(cond): return "[bold green]OK[/]" if cond else "[bold red]FAIL[/]"

        table.add_row("HL Spot Price", f"${h_state['price']:,.2f}", "[cyan]LIVE[/]")
        table.add_row("Poly Strike", f"${p_state['strike_price']:,.2f}", "[magenta]SYNC[/]")
        table.add_row("", "", "") # Spacer
        table.add_row("GAP ($)", f"{e_state['gap']:,.2f}", ok_fail(e_state["gap_pass"]))
        table.add_row("CVD (%)", f"{h_state['cvd']:.1f}%", ok_fail(e_state["cvd_pass"]))
        table.add_row("VELOCITY", f"{h_state['velocity']:.1f}", ok_fail(e_state["vel_pass"]))
        table.add_row("", "", "") # Spacer
        table.add_row("T-MINUS", f"{e_state['t_minus']}s", "[yellow]COUNT[/]")
        table.add_row("FEED HEALTH", f"HL:{'OK' if h_ok else '!!'}", f"PL:{'OK' if p_ok else '!!'}")

        return Panel(table, title="[bold cyan]MARKET STREAM[/]", border_style="cyan")

    def get_inventory_table(self, e_state, p_state):
        table = Table(show_header=False, box=None, padding=(0, 1), expand=True)
        table.add_column("Key", style="bold white", width=15)
        table.add_column("Val", justify="right")

        pos = e_state["inventory_position"]
        pos_style = "bold green" if pos == "UP" else "bold red" if pos == "DOWN" else "white"

        table.add_row("POSITION", Text(pos, style=pos_style))
        table.add_row("RISK USD", f"${e_state['inventory_risk']:,.2f}")
        table.add_row("", "")
        table.add_row("[yellow]ORDERBOOK ODDS[/]", "")
        table.add_row("• UP Ask", f"{p_state['up_ask']:.3f}")
        table.add_row("• DOWN Ask", f"{p_state['down_ask']:.3f}")
        
        # Add a small visual indicator for the window
        t = e_state['t_minus']
        win_text = "[red]WAITING[/]"
        if 15 <= t <= 120: 
            if 15 <= t <= 45: win_text = "[bold green]TRIPLE WINDOW[/]"
            if 15 <= t <= 120 and e_state['gap'] >= 110: # Special logic for display
                win_text = "[bold magenta]OVERRIDE WINDOW[/]"
            elif 15 <= t <= 120:
                # If we are in the long tail but gap not enough for override
                if t > 45: win_text = "[yellow]OBSERVING[/]"
        
        if t < 15: win_text = "[bold red]CLOSED[/]"
        
        table.add_row("", "")
        table.add_row("ACTIVE WIN", win_text)

        return Panel(table, title="[bold magenta]INVENTORY & RISK[/]", border_style="magenta")

    def get_logs_panel(self, state):
        curr_log = state.get("last_log", "")
        if curr_log and curr_log != self.last_engine_log:
            # Clean log timestamp if exists to save space
            display_log = curr_log
            if "]" in display_log:
                display_log = display_log.split("]", 1)[1].strip()
            
            self.logs.append(f"[bright_black]{time.strftime('%H:%M:%S')}[/] {display_log}")
            self.last_engine_log = curr_log
        
        log_content = "\n".join(self.logs)
        return Panel(log_content, title="[bold white]LIVE EXECUTION LOGS[/]", border_style="white")

    async def run(self):
        # Ultra-Light Mode: 5 FPS dan tanpa screen=True agar tidak berat di terminal
        with Live(self.layout, refresh_per_second=5, screen=False) as live:
            while True:
                try:
                    # Atomic state fetch
                    e_state = self.engine.get_state()
                    h_state = self.hl_feed.get_state()
                    p_state = self.poly_feed.get_state()
                    
                    # Update components
                    self.layout["header"].update(self.get_header(e_state))
                    self.layout["main"]["market"].update(self.get_market_table(e_state, h_state, p_state))
                    self.layout["main"]["inventory"].update(self.get_inventory_table(e_state, p_state))
                    self.layout["logs"].update(self.get_logs_panel(e_state))
                    
                except Exception:
                    pass
                
                await asyncio.sleep(0.1) # Lebih santai agar tidak berat
