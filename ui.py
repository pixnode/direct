import asyncio
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from collections import deque

class Dashboard:
    def __init__(self, engine, hl_feed, poly_feed):
        self.engine = engine
        self.hl_feed = hl_feed
        self.poly_feed = poly_feed
        self.logs = deque(maxlen=10)
        self.last_engine_log = ""
        
        self.layout = Layout()
        self.layout.split(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1),
            Layout(name="logs", size=12)
        )
        self.layout["main"].split_row(
            Layout(name="market"),
            Layout(name="inventory")
        )

    def generate_header(self):
        engine_state = self.engine.get_state()
        slug = engine_state.get("slug", "WAITING...")
        t_minus = engine_state.get("t_minus", 0)
        status = engine_state.get("status", "IDLE")
        
        status_color = "white"
        if status == "SNIPER_ZONE": status_color = "bold green"
        elif status == "WARMING_UP": status_color = "bold yellow"
        elif status == "CEASE_FIRE": status_color = "bold red"

        # Memusatkan teks seperti di PRD
        header_text = Text.assemble(
            ("🎯 TARGET WINDOW: ", "bold cyan"), (f"{slug} ", "white"),
            ("| ", "bright_black"),
            ("⏱️ T-MINUS: ", "bold yellow"), (f"{t_minus}s ", "white"),
            ("| ", "bright_black"),
            ("STATUS: ", "bold"), (f"[{status}]", status_color)
        )
        return Panel(header_text, style="white on blue", box=None, justify="center")

    def generate_market_panel(self):
        hl_state = self.hl_feed.get_state()
        poly_state = self.poly_feed.get_state()
        engine_state = self.engine.get_state()

        hl_price = hl_state["price"]
        strike = poly_state["strike_price"]
        gap = engine_state["gap"]
        cvd = hl_state["cvd"]
        vel = hl_state["velocity"]

        gap_pass = "[bold green][PASSED][/]" if engine_state["gap_pass"] else "[bold red][FAILED][/]"
        cvd_pass = "[bold green][PASSED][/]" if engine_state["cvd_pass"] else "[bold red][FAILED][/]"
        vel_pass = "[bold green][PASSED][/]" if engine_state["vel_pass"] else "[bold red][FAILED][/]"

        text = f"""
[bold white]HL Spot Price :[/] [cyan]${hl_price:,.2f}[/]
[bold white]Poly Strike    :[/] [cyan]${strike:,.2f}[/]

[bold yellow][TRIPLE CONFIRMATION GATE][/]
• GAP ($)     : {abs(gap):<8.2f} {gap_pass}
• CVD (%)     : {abs(cvd):<8.2f}% {cvd_pass}
• VELOCITY    : {abs(vel):<8.2f} $/s {vel_pass}
"""
        return Panel(text, title="[bold]LIVE MARKET & TRIPLE CONFIRMATION[/]", border_style="cyan")

    def generate_inventory_panel(self):
        poly_state = self.poly_feed.get_state()
        engine_state = self.engine.get_state()
        
        pos_color = "white"
        if engine_state["inventory_position"] == "UP": pos_color = "green"
        elif engine_state["inventory_position"] == "DOWN": pos_color = "red"

        text = f"""
[bold white]POSITION :[/] [{pos_color}]{engine_state["inventory_position"]}[/]
[bold white]RISK USD :[/] [green]${engine_state["inventory_risk"]:.2f}[/]

[bold yellow][TARGET ODDS LIMIT][/]
• UP Ask   : {poly_state["up_ask"]:.2f}
• DOWN Ask : {poly_state["down_ask"]:.2f}
"""
        return Panel(text, title="[bold]INVENTORY & RISK[/]", border_style="magenta")

    def generate_logs_panel(self):
        engine_state = self.engine.get_state()
        current_log = engine_state["last_log"]
        if current_log != self.last_engine_log and current_log:
            self.logs.append(current_log)
            self.last_engine_log = current_log
            
        log_text = "\n".join(self.logs)
        return Panel(log_text, title="[bold]EXECUTION LOGS[/]", border_style="white")

    async def run(self):
        # Gunakan refresh rate yang lebih rendah (4Hz) agar UI lebih "tenang"
        with Live(self.layout, refresh_per_second=4, screen=False) as live:
            while True:
                try:
                    self.layout["header"].update(self.generate_header())
                    self.layout["main"]["market"].update(self.generate_market_panel())
                    self.layout["main"]["inventory"].update(self.generate_inventory_panel())
                    self.layout["logs"].update(self.generate_logs_panel())
                except Exception:
                    pass
                # Update setiap 250ms (4 kali per detik)
                await asyncio.sleep(0.25)
