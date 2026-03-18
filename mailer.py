"""
Send email via Gmail SMTP.
Requires: GMAIL_USER and GMAIL_APP_PASSWORD in .env / Fly.io secrets.
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import config

APP_NAME = "Memory Vault"
APP_URL  = "https://memoryvault.fly.dev"

# Snapchat yellow
YELLOW = "#FFFC00"
BG     = "#0a0a0a"
CARD   = "#111111"
BORDER = "#222222"
GRAY   = "#888888"


def _send(to_email: str, subject: str, html: str):
    if not config.GMAIL_USER or not config.GMAIL_APP_PASSWORD:
        raise RuntimeError("GMAIL_USER or GMAIL_APP_PASSWORD is not configured.")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{APP_NAME} \U0001F4F8 <{config.GMAIL_USER}>"
    msg["To"]      = to_email

    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(config.GMAIL_USER, config.GMAIL_APP_PASSWORD)
        smtp.sendmail(config.GMAIL_USER, to_email, msg.as_string())


def _base_template(content: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{APP_NAME}</title>
</head>
<body style="margin:0;padding:0;background:{BG};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:{BG};padding:40px 20px;">
    <tr>
      <td align="center">
        <table width="100%" style="max-width:480px;background:{CARD};border-radius:16px;border:1px solid {BORDER};overflow:hidden;">

          <!-- Header -->
          <tr>
            <td style="padding:32px 32px 24px;border-bottom:1px solid {BORDER};">
              <table cellpadding="0" cellspacing="0">
                <tr>
                  <td style="width:40px;height:40px;background:{YELLOW};border-radius:50%;text-align:center;vertical-align:middle;">
                    <span style="font-size:20px;line-height:40px;">👻</span>
                  </td>
                  <td style="padding-left:12px;">
                    <span style="color:{YELLOW};font-size:18px;font-weight:700;letter-spacing:-0.3px;">{APP_NAME}</span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Content -->
          <tr>
            <td style="padding:32px;">
              {content}
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:20px 32px;border-top:1px solid {BORDER};text-align:center;">
              <p style="margin:0;color:{GRAY};font-size:12px;">
                This is an automated message from {APP_NAME}.<br>
                If you did not expect this email, you can safely ignore it.
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def send_invite(to_email: str, user_id: str, token: str):
    link = f"{APP_URL}/invite/{token}"
    content = f"""
      <h1 style="margin:0 0 8px;color:#ffffff;font-size:22px;font-weight:700;">
        You're invited! 🎉
      </h1>
      <p style="margin:0 0 24px;color:{GRAY};font-size:15px;line-height:1.6;">
        Hi <strong style="color:#ffffff;">{user_id}</strong>,<br><br>
        You've been granted access to a private memories gallery.
        Click the button below to set your password and log in.
      </p>

      <table cellpadding="0" cellspacing="0" style="margin:0 0 24px;">
        <tr>
          <td style="background:{YELLOW};border-radius:10px;">
            <a href="{link}"
               style="display:block;padding:14px 28px;color:#000000;font-weight:700;
                      font-size:15px;text-decoration:none;letter-spacing:-0.2px;">
              Set password →
            </a>
          </td>
        </tr>
      </table>

      <p style="margin:0;color:{GRAY};font-size:13px;line-height:1.6;">
        Or copy this link into your browser:<br>
        <a href="{link}" style="color:{YELLOW};word-break:break-all;">{link}</a>
      </p>
      <p style="margin:16px 0 0;color:{GRAY};font-size:12px;">
        This link is valid for 7 days.
      </p>
    """
    _send(to_email, f"You're invited — {APP_NAME}", _base_template(content))


def send_password_reset(to_email: str, user_id: str, token: str):
    link = f"{APP_URL}/reset/{token}"
    content = f"""
      <h1 style="margin:0 0 8px;color:#ffffff;font-size:22px;font-weight:700;">
        Reset your password 🔑
      </h1>
      <p style="margin:0 0 24px;color:{GRAY};font-size:15px;line-height:1.6;">
        Hi <strong style="color:#ffffff;">{user_id}</strong>,<br><br>
        A password reset was requested for your account.
        Click the button below to set a new password.
      </p>

      <table cellpadding="0" cellspacing="0" style="margin:0 0 24px;">
        <tr>
          <td style="background:{YELLOW};border-radius:10px;">
            <a href="{link}"
               style="display:block;padding:14px 28px;color:#000000;font-weight:700;
                      font-size:15px;text-decoration:none;letter-spacing:-0.2px;">
              Set new password →
            </a>
          </td>
        </tr>
      </table>

      <p style="margin:0;color:{GRAY};font-size:13px;line-height:1.6;">
        Or copy this link into your browser:<br>
        <a href="{link}" style="color:{YELLOW};word-break:break-all;">{link}</a>
      </p>
      <p style="margin:16px 0 0;color:{GRAY};font-size:12px;">
        This link is valid for 1 hour. If you did not request this, no action is needed.
      </p>
    """
    _send(to_email, f"Password reset — {APP_NAME}", _base_template(content))
