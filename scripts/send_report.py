import json
import os
import sys
from datetime import datetime

import requests


def send_email_report(report_file: str, recipient_email: str, resend_api_key: str):
    """Send daily report via Resend email service."""
    
    # Read the report
    try:
        with open(report_file, "r") as f:
            report_data = json.load(f)
    except FileNotFoundError:
        print(f"Report file {report_file} not found")
        return False
    
    # Format email content
    day0_count = report_data.get("day0_signals_count", 0)
    confirmed_count = report_data.get("confirmed_signals_count", 0)
    confirmed_signals = report_data.get("confirmed_signals", [])
    
    # Build HTML email body
    html_body = f"""
    <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                h1 {{ color: #333; }}
                .summary {{ background: #f0f0f0; padding: 10px; border-radius: 5px; }}
                .signal {{ background: #fff; padding: 10px; margin: 10px 0; border-left: 4px solid #007bff; }}
                .bullish {{ border-left-color: #28a745; }}
                .bearish {{ border-left-color: #dc3545; }}
                table {{ width: 100%; border-collapse: collapse; }}
                th, td {{ padding: 8px; text-align: left; border-bottom: 1px solid #ddd; }}
                th {{ background-color: #f8f9fa; }}
            </style>
        </head>
        <body>
            <h1>Daily Options Signal Report</h1>
            <p>Report Date: {report_data.get("date", "N/A")}</p>
            
            <div class="summary">
                <h2>Summary</h2>
                <p><strong>Day-0 Signals Generated:</strong> {day0_count}</p>
                <p><strong>Confirmed Signals (OI Retention):</strong> {confirmed_count}</p>
            </div>
    """
    
    if confirmed_signals:
        html_body += "<h2>Confirmed Signals Details</h2>"
        for signal in confirmed_signals:
            direction_class = "bullish" if signal.get("direction") == "bullish" else "bearish"
            html_body += f"""
            <div class="signal {direction_class}">
                <h3>{signal.get("ticker")} - {signal.get("direction").upper()}</h3>
                <p><strong>ETF Source:</strong> {signal.get("etf_source")}</p>
                <p><strong>Average OI Retention:</strong> {signal.get("average_oi_retention", 0):.2%}</p>
                <p><strong>Confirmed Contracts:</strong> {signal.get("confirmed_contract_count", 0)}</p>
            </div>
            """
    else:
        html_body += "<p>No confirmed signals today.</p>"
    
    html_body += """
        </body>
    </html>
    """
    
    # Send email via Resend
    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {resend_api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "from": "noreply@optiondashboard.com",
        "to": [recipient_email],
        "subject": f"Daily Options Signal Report - {report_data.get('date', 'N/A')}",
        "html": html_body
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        
        if response.status_code in [200, 201]:
            print(f"✓ Email sent successfully to {recipient_email}")
            return True
        else:
            print(f"✗ Failed to send email. Status: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"✗ Error sending email: {e}")
        return False


if __name__ == "__main__":
    # Get parameters from environment or command line
    report_file = os.getenv("REPORT_FILE", "daily_report.json")
    recipient_email = os.getenv("RECIPIENT_EMAIL", "j810717@gmail.com")
    resend_api_key = os.getenv("RESEND_API_KEY", "")
    
    if not resend_api_key:
        print("Error: RESEND_API_KEY environment variable not set")
        sys.exit(1)
    
    success = send_email_report(report_file, recipient_email, resend_api_key)
    sys.exit(0 if success else 1)
