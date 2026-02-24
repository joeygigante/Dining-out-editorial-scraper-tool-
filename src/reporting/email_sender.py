"""Email delivery for reports.

Supports two backends:
1. SMTP (default) — works with any email provider (Gmail, Outlook, etc.)
2. SendGrid API — more reliable for production use

Configure via SEND_METHOD in config: "smtp" or "sendgrid".
"""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


class EmailSender:
    def __init__(self, config: dict):
        self.config = config
        self.method = config.get("email_method", "smtp")

    def send_report(
        self,
        html: str,
        subject: str,
        recipients: list[str] | None = None,
    ) -> bool:
        """Send an HTML report email to configured recipients.

        Returns True if sent successfully.
        """
        recipients = recipients or self.config.get("email_recipients", [])
        if not recipients:
            logger.warning("No email recipients configured — skipping send")
            return False

        if self.method == "sendgrid":
            return self._send_via_sendgrid(html, subject, recipients)
        else:
            return self._send_via_smtp(html, subject, recipients)

    def _send_via_smtp(self, html: str, subject: str, recipients: list[str]) -> bool:
        """Send email using SMTP."""
        smtp_host = self.config.get("smtp_host", "smtp.gmail.com")
        smtp_port = self.config.get("smtp_port", 587)
        smtp_user = self.config.get("smtp_user", "")
        smtp_password = self.config.get("smtp_password", "")
        from_addr = self.config.get("email_from", smtp_user)

        if not smtp_user or not smtp_password:
            logger.error("SMTP credentials not configured")
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = ", ".join(recipients)

        # Plain text fallback
        plain = "This report is best viewed in an HTML-capable email client."
        msg.attach(MIMEText(plain, "plain"))
        msg.attach(MIMEText(html, "html"))

        try:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(smtp_user, smtp_password)
                server.sendmail(from_addr, recipients, msg.as_string())

            logger.info("Report sent via SMTP to %d recipients", len(recipients))
            return True
        except Exception:
            logger.exception("SMTP send failed")
            return False

    def _send_via_sendgrid(self, html: str, subject: str, recipients: list[str]) -> bool:
        """Send email using SendGrid API."""
        api_key = self.config.get("sendgrid_api_key", "")
        from_addr = self.config.get("email_from", "")

        if not api_key or not from_addr:
            logger.error("SendGrid API key or from address not configured")
            return False

        try:
            from sendgrid import SendGridAPIClient
            from sendgrid.helpers.mail import Content, Email, Mail, To

            from_email = Email(from_addr)
            to_emails = [To(r) for r in recipients]
            content = Content("text/html", html)
            mail = Mail(
                from_email=from_email,
                to_emails=to_emails,
                subject=subject,
                html_content=content,
            )

            sg = SendGridAPIClient(api_key)
            response = sg.send(mail)

            if response.status_code in (200, 201, 202):
                logger.info("Report sent via SendGrid to %d recipients", len(recipients))
                return True
            else:
                logger.error("SendGrid returned status %d", response.status_code)
                return False
        except ImportError:
            logger.error("sendgrid package not installed — run: pip install sendgrid")
            return False
        except Exception:
            logger.exception("SendGrid send failed")
            return False
