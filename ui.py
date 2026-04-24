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

        return Panel(f"[bold cyan]🎯 WINDOW:[/bold cyan] {slug} | [bold yellow]⏱️ T-MINUS:[/bold yellow] {t_minus}s | [bold]STATUS:[/bold] [{status_color}]{status}[/]", 
                     style="white on blue")

    def generate_market_panel(self):
        hl_state = self.hl_feed.get_state()
        poly_state = self.poly_feed.get_state()
        engine_state = self.engine.get_state()

        hl_price = hl_state["price"]
        strike = poly_state["strike_price"]
        gap = engine_state["gap"]
        cvd = hl_state["cvd"]
        vel = hl_state["velocity"]

        gap_pass = "[green]PASSED[/green]" if engine_state["gap_pass"] else "[red]FAILED[/red]"
        cvd_pass = "[green]PASSED[/green]" if engine_state["cvd_pass"] else "[red]FAILED[/red]"
        vel_pass = "[green]PASSED[/green]" if engine_state["vel_pass"] else "[red]FAILED[/red]"

        text = f"""[bold]Live Market & Triple Confirmation[/bold]

HL Spot Price : ${hl_price:,.2f}
Poly Strike   : ${strike:,.2f}

[bold yellow][TRIPLE CONFIRMATION GATE][/bold yellow]
• GAP ($)     : {abs(gap):.2f}    {gap_pass}
• CVD (%)     : {abs(cvd):.2f}%    {cvd_pass}
• VELOCITY    : {abs(vel):.2f} $/s  {vel_pass}
"""
        return Panel(text, title="Live Market", border_style="cyan")

    def generate_inventory_panel(self):
        poly_state = self.poly_feed.get_state()
        engine_state = self.engine.get_state()
        
        text = f"""[bold]Inventory & Risk[/bold]

POSITION : [{engine_state["inventory_position"]}]
RISK USD : ${engine_state["inventory_risk"]:.2f}

[bold yellow][TARGET ODDS LIMIT][/bold yellow]
• UP Ask   : {poly_state["up_ask"]:.2f}
• DOWN Ask : {poly_state["down_ask"]:.2f}
"""
        return Panel(text, title="Inventory", border_style="magenta")

    def generate_logs_panel(self):
        engine_state = self.engine.get_state()
        current_log = engine_state["last_log"]
        if current_log != self.last_engine_log and current_log:
            self.logs.append(current_log)
            self.last_engine_log = current_log
            
        log_text = "\n".join(self.logs)
        return Panel(log_text, title="Execution Logs", border_style="white")

    async def run(self):
        with Live(self.layout, refresh_per_second=10) as live:
            while True:
                self.layout["header"].update(self.generate_header())
                self.layout["main"]["market"].update(self.generate_market_panel())
                self.layout["main"]["inventory"].update(self.generate_inventory_panel())
                self.layout["logs"].update(self.generate_logs_panel())
                await asyncio.sleep(0.1)
