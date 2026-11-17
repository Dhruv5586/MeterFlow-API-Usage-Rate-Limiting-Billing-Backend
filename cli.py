#!/usr/bin/env python3
"""
===============================================================================
 MeterFlow Unified Terminal CLI
===============================================================================
A complete terminal management utility for MeterFlow.

Usage:
  meterflow                       Launch the interactive terminal menu
  meterflow server [--port 8000]  Start the FastAPI development server
  meterflow status                Check database connectivity and record counts
  meterflow users                 List tenants, subscriptions, and API keys
  meterflow plans                 Display available subscription plans & quotas
  meterflow usage                 Display usage analytics & traffic breakdown
  meterflow billing               Display invoices and billing ledger
  meterflow rollup [--date DATE]  Run daily usage aggregation rollup
  meterflow test                  Run the automated pytest test suite
  meterflow validate              Run database relational integrity checks
  meterflow transform             Clean & transform raw access logs
  meterflow import                Import transformed events into PostgreSQL
===============================================================================
"""

import sys
import os
import argparse
import subprocess
from pathlib import Path

# Enable UTF-8 and ANSI sequences on Windows console
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    # Initialize Windows virtual terminal processing
    os.system("")

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Colors for terminal output
class Colors:
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

def print_banner():
    banner = f"""{Colors.CYAN}{Colors.BOLD}
  __  __      _            _____ _               
 |  \\/  |    | |          |  ___| |              
 | \\  / | ___| |_ ___ _ __| |_  | | _____      __
 | |\\/| |/ _ \\ __/ _ \\ '__|  _| | |/ _ \\ \\ /\\ / /
 | |  | |  __/ ||  __/ |  | |   | | (_) \\ V  V / 
 |_|  |_|\\___|\\__\\___|_|  \\_|   |_|\\___/ \\_/\\_/  
{Colors.DIM} API Usage, Rate Limiting & Billing Management Engine{Colors.RESET}
"""
    print(banner)

def get_python_exe() -> str:
    """Find the virtual environment Python executable."""
    venv_python = ROOT_DIR / ".venv" / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")
    if venv_python.exists():
        return str(venv_python)
    return sys.executable

def cmd_server(port: int = 8000, reload: bool = True):
    """Start the FastAPI backend server."""
    print_banner()
    print(f"{Colors.GREEN}[*] Starting MeterFlow API Server on http://127.0.0.1:{port}...{Colors.RESET}")
    print(f"{Colors.DIM}    Interactive Docs : http://127.0.0.1:{port}/docs")
    print(f"    Health Endpoint  : http://127.0.0.1:{port}/health")
    print(f"    Press Ctrl+C to stop the server.{Colors.RESET}\n")

    py_exe = get_python_exe()
    cmd = [
        py_exe,
        "-m", "uvicorn",
        "app.main:app",
        "--host", "127.0.0.1",
        "--port", str(port),
    ]
    if reload:
        cmd.append("--reload")

    try:
        subprocess.run(cmd, cwd=str(ROOT_DIR))
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}[!] MeterFlow server stopped.{Colors.RESET}")

def cmd_status():
    """Check database connection and show record statistics."""
    print_banner()
    print(f"{Colors.BOLD}[1] Database Connectivity Check{Colors.RESET}")
    
    try:
        from app.core.config import settings
        from app.core.database import SessionLocal, check_database_health
        from sqlalchemy import text
        
        db_host = settings.DATABASE_URL.split("@")[-1] if "@" in settings.DATABASE_URL else "configured"
        print(f"    Connecting to: {Colors.DIM}{db_host}{Colors.RESET}")
        
        check_database_health()
        print(f"    {Colors.GREEN}[OK] Database Status: HEALTHY (PostgreSQL 16 active & responsive){Colors.RESET}")
        
        # Check Redis & Rate Limiter status
        from app.core.redis import check_redis_health
        redis_status = check_redis_health()
        backend_name = redis_status.get("backend", "in_memory")
        if redis_status.get("connected"):
            print(f"    {Colors.GREEN}[OK] Redis Rate Limiter: HEALTHY ({backend_name}){Colors.RESET}\n")
        else:
            print(f"    {Colors.YELLOW}[!] Redis Rate Limiter: DEGRADED ({redis_status.get('error', 'unreachable')}){Colors.RESET}\n")
        
        session = SessionLocal()
        print(f"{Colors.BOLD}[2] Database Tables & Record Counts{Colors.RESET}")
        tables = [
            ("users", "Registered tenant accounts"),
            ("api_keys", "Tenant API keys (SHA-256 hashed)"),
            ("subscription_plans", "Billing tiers & request quotas"),
            ("subscriptions", "Active tenant subscriptions"),
            ("usage_events", "Ingested API usage logs"),
            ("usage_daily", "Daily aggregated rollups"),
            ("usage_quotas", "Active rate/monthly quotas"),
            ("invoices", "Billing invoice headers"),
            ("invoice_items", "Detailed line items"),
            ("payments", "Razorpay payment transactions"),
            ("payment_webhook_events", "Idempotent webhook audit logs"),
            ("audit_logs", "Security & change audit logs"),
        ]
        
        print(f"    {'Table Name':<22} {'Rows':>8}   {'Description'}")
        print(f"    {'-'*22} {'-'*8}   {'-'*35}")
        total_rows = 0
        for tbl, desc in tables:
            try:
                cnt = session.execute(text(f"SELECT COUNT(*) FROM {tbl};")).scalar()
                total_rows += cnt
                color = Colors.GREEN if cnt > 0 else Colors.DIM
                print(f"    {tbl:<22} {color}{cnt:>8}{Colors.RESET}   {Colors.DIM}{desc}{Colors.RESET}")
            except Exception as e:
                print(f"    {tbl:<22} {Colors.RED}  ERROR{Colors.RESET}   {e}")
        
        print(f"    {'-'*22} {'-'*8}")
        print(f"    {'Total Records':<22} {Colors.BOLD}{total_rows:>8}{Colors.RESET}\n")
        session.close()

    except Exception as exc:
        print(f"    {Colors.RED}[FAIL] Connection Failed: {exc}{Colors.RESET}")
        print(f"\n{Colors.YELLOW}[!] Check your .env file in {ROOT_DIR}\\.env{Colors.RESET}")

def cmd_users():
    """List all tenants, plans, and API keys."""
    print_banner()
    print(f"{Colors.BOLD}Registered Tenants & Subscription Status{Colors.RESET}\n")
    
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text
        session = SessionLocal()
        
        rows = session.execute(text("""
            SELECT 
                u.id,
                u.display_name,
                u.email,
                u.status AS user_status,
                p.name AS plan_name,
                p.price,
                k.key_prefix,
                s.status AS sub_status
            FROM users u
            LEFT JOIN subscriptions s ON s.user_id = u.id
            LEFT JOIN subscription_plans p ON s.plan_id = p.id
            LEFT JOIN api_keys k ON k.user_id = u.id
            ORDER BY p.price DESC NULLS LAST;
        """)).fetchall()
        
        for idx, u in enumerate(rows, 1):
            sub_state = u.sub_status or "none"
            status_color = Colors.GREEN if sub_state == 'active' else Colors.YELLOW
            plan_str = f"{u.plan_name} (${u.price}/mo)" if u.plan_name else "No Plan"
            prefix_str = f"{u.key_prefix}****************" if u.key_prefix else "None"
            print(f"  {Colors.BOLD}{idx}. {u.display_name}{Colors.RESET} ({u.email})")
            print(f"     ID:          {u.id}")
            print(f"     Status:      {u.user_status}")
            print(f"     Plan:        {plan_str} -- {status_color}[{sub_state.upper()}]{Colors.RESET}")
            print(f"     Key Prefix:  {Colors.CYAN}{prefix_str}{Colors.RESET} (SHA-256 Hashed)")
            print()
            
        session.close()
    except Exception as exc:
        print(f"{Colors.RED}Error loading tenants: {exc}{Colors.RESET}")

def cmd_plans():
    """Display subscription plans, pricing, and limits."""
    print_banner()
    print(f"{Colors.BOLD}Subscription Plans & Limits{Colors.RESET}\n")
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text
        session = SessionLocal()
        
        plans = session.execute(text("""
            SELECT code, name, price, currency, billing_interval, is_active
            FROM subscription_plans
            ORDER BY price ASC;
        """)).fetchall()
        
        print(f"  {'Plan Code':<14} {'Plan Name':<16} {'Price':<14} {'Interval':<12} {'Status'}")
        print(f"  {'-'*14} {'-'*16} {'-'*14} {'-'*12} {'-'*10}")
        for p in plans:
            status_str = f"{Colors.GREEN}[ACTIVE]{Colors.RESET}" if p.is_active else f"{Colors.RED}[INACTIVE]{Colors.RESET}"
            price_str = f"{p.currency} ${p.price:.2f}"
            print(f"  {p.code:<14} {Colors.BOLD}{p.name:<16}{Colors.RESET} {price_str:<14} {p.billing_interval:<12} {status_str}")
        print()
        session.close()
    except Exception as exc:
        print(f"{Colors.RED}Error loading plans: {exc}{Colors.RESET}")

def cmd_usage():
    """Display live usage analytics and breakdown."""
    print_banner()
    print(f"{Colors.BOLD}Usage Analytics & Traffic Summary{Colors.RESET}\n")
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text
        session = SessionLocal()
        
        # Global summary
        stats = session.execute(text("""
            SELECT 
                COUNT(*) AS total_events,
                COUNT(DISTINCT user_id) AS active_users,
                ROUND(AVG(latency_ms), 2) AS avg_latency,
                ROUND(MIN(latency_ms), 2) AS min_latency,
                ROUND(MAX(latency_ms), 2) AS max_latency,
                SUM(response_size_bytes) AS total_bytes
            FROM usage_events;
        """)).fetchone()
        
        print(f"  Total Ingested Events : {Colors.BOLD}{stats.total_events:,}{Colors.RESET}")
        print(f"  Active Demo Tenants   : {stats.active_users}")
        print(f"  Average Latency       : {Colors.CYAN}{stats.avg_latency} ms{Colors.RESET} (Min: {stats.min_latency} ms | Max: {stats.max_latency} ms)")
        print(f"  Total Transferred     : {stats.total_bytes / (1024*1024):.2f} MB ({stats.total_bytes:,} bytes)")
        print()
        
        # Per tenant summary
        print(f"  {Colors.BOLD}Tenant Breakdown:{Colors.RESET}")
        tenant_rows = session.execute(text("""
            SELECT 
                u.display_name,
                COUNT(e.id) AS event_count,
                ROUND(AVG(e.latency_ms), 1) AS avg_lat,
                COUNT(CASE WHEN e.status_code >= 400 THEN 1 END) AS errors
            FROM usage_events e
            JOIN users u ON e.user_id = u.id
            GROUP BY u.display_name
            ORDER BY event_count DESC;
        """)).fetchall()
        
        for t in tenant_rows:
            err_color = Colors.GREEN if t.errors == 0 else Colors.YELLOW
            print(f"    * {t.display_name:<26}: {t.event_count:>4} events | Avg Latency: {t.avg_lat:>5}ms | Errors: {err_color}{t.errors}{Colors.RESET}")
        print()

        # HTTP method breakdown
        print(f"  {Colors.BOLD}HTTP Methods Distribution:{Colors.RESET}")
        method_rows = session.execute(text("""
            SELECT http_method, COUNT(*) AS count
            FROM usage_events
            GROUP BY http_method
            ORDER BY count DESC;
        """)).fetchall()
        for m in method_rows:
            pct = (m.count / stats.total_events) * 100 if stats.total_events else 0
            bar = "#" * int(pct / 4)
            print(f"    * {m.http_method:<6}: {m.count:>4} ({pct:>5.1f}%) {Colors.CYAN}{bar}{Colors.RESET}")
        print()
        session.close()
    except Exception as exc:
        print(f"{Colors.RED}Error loading usage: {exc}{Colors.RESET}")

def cmd_test():
    """Run pytest automated test suite."""
    print_banner()
    print(f"{Colors.GREEN}[*] Running MeterFlow Pytest Suite...{Colors.RESET}\n")
    py_exe = get_python_exe()
    subprocess.run([py_exe, "-m", "pytest", "tests", "-v"], cwd=str(ROOT_DIR))

def cmd_validate():
    """Run relational and constraint validation script."""
    print_banner()
    print(f"{Colors.GREEN}[*] Running Final Database Validation & EXPLAIN ANALYZE Benchmarks...{Colors.RESET}\n")
    py_exe = get_python_exe()
    subprocess.run([py_exe, "scripts/final_validation.py"], cwd=str(ROOT_DIR))

def cmd_transform():
    """Run dataset transformation."""
    print_banner()
    print(f"{Colors.GREEN}[*] Running Dataset Cleaning and Transformation...{Colors.RESET}\n")
    py_exe = get_python_exe()
    subprocess.run([py_exe, "scripts/transform_dataset.py"], cwd=str(ROOT_DIR))

def cmd_import():
    """Run usage events import."""
    print_banner()
    print(f"{Colors.GREEN}[*] Importing Transformed Usage Events into PostgreSQL...{Colors.RESET}\n")
    py_exe = get_python_exe()
    subprocess.run([py_exe, "scripts/import_usage_events.py"], cwd=str(ROOT_DIR))

def cmd_rollup(target_date: str = None):
    """Run daily usage rollup aggregation."""
    print_banner()
    print(f"{Colors.GREEN}[*] Running Daily Usage Aggregation Rollup...{Colors.RESET}\n")
    py_exe = get_python_exe()
    args = [py_exe, "scripts/run_aggregation.py"]
    if target_date:
        args.extend(["--date", target_date])
    subprocess.run(args, cwd=str(ROOT_DIR))

def cmd_billing():
    """Display billing preview and generated invoices."""
    print_banner()
    print(f"{Colors.BOLD}MeterFlow Invoices & Billing Ledger{Colors.RESET}\n")
    
    try:
        from app.core.database import SessionLocal
        from app.models.invoice import Invoice
        from app.models.user import User
        from sqlalchemy import select, desc
        
        session = SessionLocal()
        invoices = session.scalars(
            select(Invoice).order_by(desc(Invoice.created_at)).limit(10)
        ).all()
        
        if not invoices:
            print(f"{Colors.YELLOW}[i] No invoices have been generated yet.{Colors.RESET}")
            print(f"{Colors.DIM}    Generate invoices via API: POST /api/v1/billing/invoices/generate{Colors.RESET}\n")
        else:
            print(f"  {'Invoice #':<18} {'Status':<10} {'Period':<23} {'Subtotal':>10} {'Total':>10}  {'Customer'}")
            print(f"  {'-'*18} {'-'*10} {'-'*23} {'-'*10} {'-'*10}  {'-'*25}")
            
            for inv in invoices:
                user = session.get(User, inv.user_id)
                user_email = user.email if user else str(inv.user_id)[:8]
                period = f"{inv.issued_at.strftime('%Y-%m-%d')}"
                if inv.due_at:
                    period += f" (Due: {inv.due_at.strftime('%m-%d')})"
                status_color = Colors.GREEN if inv.status == "paid" else (Colors.YELLOW if inv.status == "open" else Colors.RED)
                
                print(f"  {inv.invoice_number:<18} {status_color}{inv.status.upper():<10}{Colors.RESET} {period:<23} ${inv.subtotal:>9.2f} ${inv.total:>9.2f}  {user_email}")
                
                # Show line items
                if inv.items:
                    for it in inv.items:
                        print(f"    {Colors.DIM}↳ {it.description}: {it.quantity} units @ ${it.unit_price:.4f} = ${it.line_amount:.2f}{Colors.RESET}")
            print()
        session.close()
    except Exception as exc:
        print(f"{Colors.RED}[!] Error loading billing records: {exc}{Colors.RESET}\n")

def cmd_payments():
    """Display Razorpay payments and settlement status."""
    print_banner()
    print(f"{Colors.BOLD}MeterFlow Payment Transactions (Razorpay Gateway){Colors.RESET}\n")
    
    try:
        from app.core.database import SessionLocal
        from app.models.payment import Payment
        from app.models.invoice import Invoice
        from sqlalchemy import select, desc
        
        session = SessionLocal()
        payments = session.scalars(
            select(Payment).order_by(desc(Payment.created_at)).limit(15)
        ).all()
        
        if not payments:
            print(f"{Colors.YELLOW}[i] No payment transactions recorded yet.{Colors.RESET}")
            print(f"{Colors.DIM}    Create payment orders via: POST /api/v1/payments/orders{Colors.RESET}\n")
        else:
            print(f"  {'Order ID':<22} {'Payment ID':<22} {'Status':<12} {'Amount':>10}  {'Created At':<19}  {'Invoice #'}")
            print(f"  {'-'*22} {'-'*22} {'-'*12} {'-'*10}  {'-'*19}  {'-'*16}")
            
            for p in payments:
                pay_id_str = p.razorpay_payment_id or "— (pending)"
                status_color = Colors.GREEN if p.status == "captured" else (Colors.YELLOW if p.status in ("created", "authorized") else Colors.RED)
                inv = session.get(Invoice, p.invoice_id)
                inv_num = inv.invoice_number if inv else str(p.invoice_id)[:8]
                created_str = p.created_at.strftime("%Y-%m-%d %H:%M")
                
                print(f"  {p.razorpay_order_id:<22} {pay_id_str:<22} {status_color}{p.status.upper():<12}{Colors.RESET} ${p.amount:>9.2f}  {created_str:<19}  {inv_num}")
            print()
        session.close()
    except Exception as exc:
        print(f"{Colors.RED}[!] Error loading payments: {exc}{Colors.RESET}\n")

def interactive_menu():
    """Interactive terminal dashboard menu for quick navigation."""
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        print_banner()
        print(f"{Colors.BOLD}MeterFlow Terminal Control Panel{Colors.RESET}")
        print(f"{Colors.DIM}Choose an action by typing its number and pressing Enter:{Colors.RESET}\n")
        
        print(f"  {Colors.CYAN}[1]{Colors.RESET}  Start API Development Server  (Uvicorn on port 8000)")
        print(f"  {Colors.CYAN}[2]{Colors.RESET}  Check Database & System Status (Table counts, health check)")
        print(f"  {Colors.CYAN}[3]{Colors.RESET}  View Tenants & API Keys        (Tenants, plans, keys)")
        print(f"  {Colors.CYAN}[4]{Colors.RESET}  View Subscription Plans        (Quotas, pricing, overage)")
        print(f"  {Colors.CYAN}[5]{Colors.RESET}  View Live Usage Analytics      (Latency, traffic, breakdown)")
        print(f"  {Colors.CYAN}[6]{Colors.RESET}  View Billing & Invoices        (Ledger, line items, status)")
        print(f"  {Colors.CYAN}[7]{Colors.RESET}  View Payment Transactions      (Razorpay orders & captures)")
        print(f"  {Colors.CYAN}[8]{Colors.RESET}  Run Daily Usage Rollup         (Aggregate raw logs into daily)")
        print(f"  {Colors.CYAN}[9]{Colors.RESET}  Run Automated Test Suite       (54 Pytest unit/integration tests)")
        print(f"  {Colors.CYAN}[10]{Colors.RESET} Run Database Integrity Check   (EXPLAIN ANALYZE & constraint audits)")
        print(f"  {Colors.CYAN}[11]{Colors.RESET} Transform Access Logs Dataset  (CSV cleaning & URL normalization)")
        print(f"  {Colors.CYAN}[12]{Colors.RESET} Import Events to PostgreSQL    (Batch ingestion with deduplication)")
        print(f"  {Colors.CYAN}[0]{Colors.RESET}  Exit Terminal\n")
        
        choice = input(f"{Colors.BOLD}meterflow > {Colors.RESET}").strip()
        
        if choice == "1":
            cmd_server()
            input(f"\n{Colors.DIM}Press Enter to return to menu...{Colors.RESET}")
        elif choice == "2":
            cmd_status()
            input(f"\n{Colors.DIM}Press Enter to return to menu...{Colors.RESET}")
        elif choice == "3":
            cmd_users()
            input(f"\n{Colors.DIM}Press Enter to return to menu...{Colors.RESET}")
        elif choice == "4":
            cmd_plans()
            input(f"\n{Colors.DIM}Press Enter to return to menu...{Colors.RESET}")
        elif choice == "5":
            cmd_usage()
            input(f"\n{Colors.DIM}Press Enter to return to menu...{Colors.RESET}")
        elif choice == "6":
            cmd_billing()
            input(f"\n{Colors.DIM}Press Enter to return to menu...{Colors.RESET}")
        elif choice == "7":
            cmd_payments()
            input(f"\n{Colors.DIM}Press Enter to return to menu...{Colors.RESET}")
        elif choice == "8":
            cmd_rollup()
            input(f"\n{Colors.DIM}Press Enter to return to menu...{Colors.RESET}")
        elif choice == "9":
            cmd_test()
            input(f"\n{Colors.DIM}Press Enter to return to menu...{Colors.RESET}")
        elif choice == "10":
            cmd_validate()
            input(f"\n{Colors.DIM}Press Enter to return to menu...{Colors.RESET}")
        elif choice == "11":
            cmd_transform()
            input(f"\n{Colors.DIM}Press Enter to return to menu...{Colors.RESET}")
        elif choice == "12":
            cmd_import()
            input(f"\n{Colors.DIM}Press Enter to return to menu...{Colors.RESET}")
        elif choice in ("0", "exit", "quit", "q"):
            print(f"\n{Colors.GREEN}Goodbye!{Colors.RESET}\n")
            break
        else:
            print(f"{Colors.RED}Invalid option '{choice}'. Please enter a number from 0 to 12.{Colors.RESET}")
            input(f"\n{Colors.DIM}Press Enter to try again...{Colors.RESET}")

def main():
    parser = argparse.ArgumentParser(
        description="MeterFlow Command-Line Management Utility",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")
    
    # server subcommand
    server_parser = subparsers.add_parser("server", help="Start the FastAPI API development server")
    server_parser.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000)")
    server_parser.add_argument("--no-reload", action="store_true", help="Disable auto-reload")
    
    # other commands
    subparsers.add_parser("status", help="Check database health and row statistics")
    subparsers.add_parser("users", help="List all registered tenants and API keys")
    subparsers.add_parser("plans", help="List subscription plans and rate limits")
    subparsers.add_parser("usage", help="Display usage analytics and traffic breakdown")
    subparsers.add_parser("billing", help="Display invoices and billing ledger")
    subparsers.add_parser("payments", help="Display Razorpay payment transactions and status")
    rollup_parser = subparsers.add_parser("rollup", help="Run daily usage rollup aggregation")
    rollup_parser.add_argument("--date", type=str, default=None, help="Target date to aggregate (YYYY-MM-DD)")
    subparsers.add_parser("test", help="Run pytest automated test suite")
    subparsers.add_parser("validate", help="Run relational integrity validation checks")
    subparsers.add_parser("transform", help="Clean & transform access_logs.csv")
    subparsers.add_parser("import", help="Import transformed logs into PostgreSQL")
    subparsers.add_parser("menu", help="Open the interactive menu")
    
    args = parser.parse_args()
    
    if args.command == "server":
        cmd_server(port=args.port, reload=not args.no_reload)
    elif args.command == "status":
        cmd_status()
    elif args.command == "users":
        cmd_users()
    elif args.command == "plans":
        cmd_plans()
    elif args.command == "usage":
        cmd_usage()
    elif args.command == "billing":
        cmd_billing()
    elif args.command == "payments":
        cmd_payments()
    elif args.command == "rollup":
        cmd_rollup(target_date=args.date)
    elif args.command == "test":
        cmd_test()
    elif args.command == "validate":
        cmd_validate()
    elif args.command == "transform":
        cmd_transform()
    elif args.command == "import":
        cmd_import()
    elif args.command == "menu" or args.command is None:
        # Default with no args: launch interactive menu
        interactive_menu()

if __name__ == "__main__":
    main()
