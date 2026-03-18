"""
E-mail verzenden via Gmail SMTP.
Vereist: GMAIL_USER en GMAIL_APP_PASSWORD in .env / Fly.io secrets.
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import config

APP_NAME = "Herinneringen"
APP_URL  = "https://memoryvault.fly.dev"

# Snapchat-geel
YELLOW = "#FFFC00"
BG     = "#0a0a0a"
CARD   = "#111111"
BORDER = "#222222"
GRAY   = "#888888"


def _send(to_email: str, subject: str, html: str):
    if not config.GMAIL_USER or not config.GMAIL_APP_PASSWORD:
        raise RuntimeError("GMAIL_USER of GMAIL_APP_PASSWORD niet ingesteld.")

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
<html lang="nl">
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
                Dit is een automatisch bericht van {APP_NAME}.<br>
                Als je deze mail niet verwachtte, kun je hem negeren.
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
        Je bent uitgenodigd! 🎉
      </h1>
      <p style="margin:0 0 24px;color:{GRAY};font-size:15px;line-height:1.6;">
        Hoi <strong style="color:#ffffff;">{user_id}</strong>,<br><br>
        Je hebt toegang gekregen tot een privégallery met herinneringen.
        Klik op de knop hieronder om je wachtwoord in te stellen en in te loggen.
      </p>

      <table cellpadding="0" cellspacing="0" style="margin:0 0 24px;">
        <tr>
          <td style="background:{YELLOW};border-radius:10px;">
            <a href="{link}"
               style="display:block;padding:14px 28px;color:#000000;font-weight:700;
                      font-size:15px;text-decoration:none;letter-spacing:-0.2px;">
              Wachtwoord instellen →
            </a>
          </td>
        </tr>
      </table>

      <p style="margin:0;color:{GRAY};font-size:13px;line-height:1.6;">
        Of kopieer deze link in je browser:<br>
        <a href="{link}" style="color:{YELLOW};word-break:break-all;">{link}</a>
      </p>
      <p style="margin:16px 0 0;color:{GRAY};font-size:12px;">
        Deze link is 7 dagen geldig.
      </p>
    """
    _send(to_email, f"Je bent uitgenodigd — {APP_NAME}", _base_template(content))


def send_password_reset(to_email: str, user_id: str, token: str):
    link = f"{APP_URL}/reset/{token}"
    content = f"""
      <h1 style="margin:0 0 8px;color:#ffffff;font-size:22px;font-weight:700;">
        Wachtwoord resetten 🔑
      </h1>
      <p style="margin:0 0 24px;color:{GRAY};font-size:15px;line-height:1.6;">
        Hoi <strong style="color:#ffffff;">{user_id}</strong>,<br><br>
        Er is een wachtwoordreset aangevraagd voor jouw account.
        Klik op de knop hieronder om een nieuw wachtwoord in te stellen.
      </p>

      <table cellpadding="0" cellspacing="0" style="margin:0 0 24px;">
        <tr>
          <td style="background:{YELLOW};border-radius:10px;">
            <a href="{link}"
               style="display:block;padding:14px 28px;color:#000000;font-weight:700;
                      font-size:15px;text-decoration:none;letter-spacing:-0.2px;">
              Nieuw wachtwoord instellen →
            </a>
          </td>
        </tr>
      </table>

      <p style="margin:0;color:{GRAY};font-size:13px;line-height:1.6;">
        Of kopieer deze link in je browser:<br>
        <a href="{link}" style="color:{YELLOW};word-break:break-all;">{link}</a>
      </p>
      <p style="margin:16px 0 0;color:{GRAY};font-size:12px;">
        Deze link is 1 uur geldig. Als jij dit niet hebt aangevraagd, hoef je niets te doen.
      </p>
    """
    _send(to_email, f"Wachtwoord resetten — {APP_NAME}", _base_template(content))
