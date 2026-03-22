from typing import Dict, Any
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fastapi import HTTPException


class Template:
    def __init__(self):
        self.name = ""

    def build(self, **kwargs) -> str:
        raise NotImplementedError


class OtpTemplate(Template):
    def __init__(self):
        super().__init__()
        self.name = "otp"

    def build(self, otp: str, username: str = "there", **kwargs) -> str:
        return f"""
        <html>
        <body style="font-family: Arial, sans-serif; background: #f4f4f4; padding: 20px;">
          <div style="max-width: 480px; margin: auto; background: #fff; border-radius: 8px; padding: 32px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">
            <h2 style="color: #1a1a1a; margin-top: 0;">Verify your gitDeploy account</h2>
            <p style="color: #555;">Hi {username},</p>
            <p style="color: #555;">Use the code below to verify your email address. It expires in <strong>10 minutes</strong>.</p>
            <div style="text-align: center; margin: 32px 0;">
              <span style="font-size: 36px; font-weight: bold; letter-spacing: 12px; color: #1a1a1a; background: #f4f4f4; padding: 16px 24px; border-radius: 8px; display: inline-block;">{otp}</span>
            </div>
            <p style="color: #888; font-size: 13px;">If you did not create a gitDeploy account, you can safely ignore this email.</p>
          </div>
        </body>
        </html>
        """


class PasswordResetTemplate(Template):
    def __init__(self):
        super().__init__()
        self.name = "password_reset"

    def build(self, reset_link: str, username: str = "there", **kwargs) -> str:
        return f"""
        <html>
        <body style="font-family: Arial, sans-serif; background: #f4f4f4; padding: 20px;">
          <div style="max-width: 480px; margin: auto; background: #fff; border-radius: 8px; padding: 32px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">
            <h2 style="color: #1a1a1a; margin-top: 0;">Reset your password</h2>
            <p style="color: #555;">Hi {username},</p>
            <p style="color: #555;">Click the button below to reset your gitDeploy password. This link expires in <strong>15 minutes</strong>.</p>
            <div style="text-align: center; margin: 32px 0;">
              <a href="{reset_link}" style="background: #1a1a1a; color: #fff; text-decoration: none; padding: 12px 28px; border-radius: 6px; font-weight: bold; display: inline-block;">Reset Password</a>
            </div>
            <p style="color: #888; font-size: 13px;">If you didn't request a password reset, you can safely ignore this email. Your password will not change.</p>
            <p style="color: #bbb; font-size: 12px; word-break: break-all;">Or copy this link: {reset_link}</p>
          </div>
        </body>
        </html>
        """


_TEMPLATE_SUBJECTS: Dict[str, str] = {
    "otp": "Your gitDeploy verification code",
    "password_reset": "Reset your gitDeploy password",
}


class CommunicationBuilder:
    def __init__(self, recipient: str, template: Template, data: Dict[str, Any]):
        self.recipient = recipient
        self.template = template
        self.data = data

    def build_message(self) -> str:
        if not self.template:
            raise ValueError("Template is required")
        return self.template.build(**self.data)

    def send(self) -> Dict[str, Any]:
        message = self.build_message()
        smtp_email = os.environ.get("SMTP_EMAIL")
        smtp_pass = os.environ.get("SMTP_PASSWORD")

        if not smtp_email or not smtp_pass:
            raise HTTPException(500, "Email not configured on the server")

        subject = _TEMPLATE_SUBJECTS.get(self.template.name, "gitDeploy notification")

        email = MIMEMultipart("alternative")
        email["Subject"] = subject
        email["From"] = smtp_email
        email["To"] = self.recipient
        email.attach(MIMEText(message, "html"))

        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
                smtp.login(smtp_email, smtp_pass)
                smtp.sendmail(smtp_email, self.recipient, email.as_string())
        except smtplib.SMTPAuthenticationError:
            raise HTTPException(500, "SMTP auth failed — check your App Password")
        except Exception as e:
            raise HTTPException(500, f"Failed to send email: {str(e)}")

        return {"ok": True, "recipient": self.recipient}