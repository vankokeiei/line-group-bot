from flask import (
    Flask,
    request,
    session,
    redirect,
    url_for,
    render_template_string
)
from linebot import LineBotApi, WebhookHandler
from linebot.models import (
    MessageEvent, TextMessage,
    TextSendMessage, ImageSendMessage
)
import os
import json
import re
import secrets
from functools import wraps
from botocore.exceptions import ClientError
import hashlib
from urllib.parse import urlencode
import uuid
import boto3
import io
import hmac
from datetime import datetime, timezone, timedelta
from PIL import Image
from botocore.config import Config

from linebot.exceptions import InvalidSignatureError
app = Flask(__name__)
# =====================================
# LINE RECIPIENT MANAGER CONFIG
# =====================================

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "").strip()
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "").strip()

RECIPIENTS_R2_KEY = "config/line_recipients.json"

app.config.update(
    SECRET_KEY=FLASK_SECRET_KEY or None,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=True,
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8)
)


line_bot_api = LineBotApi(os.getenv("LINE_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))
# =====================================
# APPWATCH + CLOUDFLARE R2 CONFIG
# =====================================

R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME")
R2_ENDPOINT = os.getenv("R2_ENDPOINT")

APPWATCH_UPLOAD_TOKEN = os.getenv("APPWATCH_UPLOAD_TOKEN")
APPWATCH_NOTIFY_TOKEN = os.getenv(
    "APPWATCH_NOTIFY_TOKEN", ""
).strip()
LINE_USER_ID = os.getenv("LINE_USER_ID")
APPWATCH_IMAGE_TOKEN = os.getenv("APPWATCH_IMAGE_TOKEN")
APPWATCH_IMAGE_WORKER_URL = os.getenv("APPWATCH_IMAGE_WORKER_URL")

r2 = None

if all([
    R2_ACCOUNT_ID,
    R2_ACCESS_KEY_ID,
    R2_SECRET_ACCESS_KEY,
    R2_BUCKET_NAME,
    R2_ENDPOINT
]):
    r2 = boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        region_name="auto",
        config=Config(signature_version="s3v4")
    )
    # =====================================
# LINE RECIPIENT STORAGE
# =====================================



def load_line_recipients():

    if r2 is None:
        raise RuntimeError("Cloudflare R2 is not configured")

    try:
        response = r2.get_object(
            Bucket=R2_BUCKET_NAME,
            Key=RECIPIENTS_R2_KEY
        )

        data = json.loads(
            response["Body"].read().decode("utf-8")
        )

        recipients = data.get("recipients", [])

        if not isinstance(recipients, list):
            raise ValueError("Invalid recipients data")

        return recipients

    except ClientError as error:

        error_code = error.response.get(
            "Error", {}
        ).get("Code")

        if error_code in ("NoSuchKey", "404", "NotFound"):

            legacy_recipients = []

            if LINE_USER_ID and is_valid_line_user_id(LINE_USER_ID):

                legacy_recipients.append({
                    "user_id": LINE_USER_ID,
                    "name": "ผู้รับเดิม",
                    "enabled": True
                })

            if legacy_recipients:
                save_line_recipients(legacy_recipients)

            return legacy_recipients

        raise


def save_line_recipients(recipients):

    if r2 is None:
        raise RuntimeError("Cloudflare R2 is not configured")

    data = {
        "recipients": recipients,
        "updated_at": datetime.now(
            timezone.utc
        ).isoformat()
    }

    r2.put_object(
        Bucket=R2_BUCKET_NAME,
        Key=RECIPIENTS_R2_KEY,
        Body=json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ).encode("utf-8"),
        ContentType="application/json"
    )


def is_valid_line_user_id(user_id):

    return bool(
        re.fullmatch(r"U[0-9a-fA-F]{32}", user_id)
    )
    # =====================================
# ADMIN LOGIN SYSTEM
# =====================================

def admin_required(func):

    @wraps(func)
    def wrapper(*args, **kwargs):

        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))

        return func(*args, **kwargs)

    return wrapper


@app.route("/admin", methods=["GET"])
def admin_home():

    if not ADMIN_PASSWORD or not FLASK_SECRET_KEY:
        return "Admin environment settings missing", 503

    if session.get("admin_logged_in"):
        return redirect(url_for("admin_recipients"))

    return redirect(url_for("admin_login"))


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():

    if not ADMIN_PASSWORD or not FLASK_SECRET_KEY:
        return "Admin environment settings missing", 503

    error = ""

    if request.method == "POST":

        submitted_token = request.form.get(
            "csrf_token", ""
        )

        saved_token = session.get(
            "login_csrf", ""
        )

        if not saved_token or not secrets.compare_digest(
            submitted_token, saved_token
        ):
            error = "Session หมดอายุ กรุณาลองใหม่"

        else:

            password = request.form.get("password", "")

            if secrets.compare_digest(
                password.encode("utf-8"),
                ADMIN_PASSWORD.encode("utf-8")
):
           

                session.clear()
                session.permanent = True
                session["admin_logged_in"] = True

                return redirect(
                    url_for("admin_recipients")
                )

            error = "รหัสผ่านไม่ถูกต้อง"

    csrf_token = secrets.token_urlsafe(32)
    session["login_csrf"] = csrf_token

    return render_template_string("""
    <!DOCTYPE html>
    <html lang="th">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport"
              content="width=device-width, initial-scale=1">

        <title>AppWatch Admin Login</title>

        <style>
            body {
                font-family: Arial, sans-serif;
                background: #101827;
                color: white;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                margin: 0;
            }

            .box {
                background: #1e293b;
                padding: 30px;
                border-radius: 14px;
                width: 330px;
                max-width: calc(100% - 60px);
            }

            input, button {
                width: 100%;
                box-sizing: border-box;
                padding: 13px;
                margin-top: 12px;
                border-radius: 8px;
                font-size: 16px;
            }

            input {
                border: 1px solid #475569;
                background: #0f172a;
                color: white;
            }

            button {
                background: #2563eb;
                color: white;
                border: none;
                cursor: pointer;
            }

            .error {
                color: #f87171;
            }
        </style>
    </head>

    <body>
        <div class="box">

            <h2>APPWATCH MONITOR</h2>
            <p>Admin Login</p>

            {% if error %}
                <p class="error">{{ error }}</p>
            {% endif %}

            <form method="POST">

                <input
                    type="hidden"
                    name="csrf_token"
                    value="{{ csrf_token }}"
                >

                <input
                    type="password"
                    name="password"
                    placeholder="รหัสผ่านผู้ดูแล"
                    required
                >

                <button type="submit">
                    เข้าสู่ระบบ
                </button>

            </form>

        </div>
    </body>
    </html>
    """, error=error, csrf_token=csrf_token)

    
# =====================================
# LINE RECIPIENT MANAGER
# =====================================

def get_admin_csrf_token():

    token = session.get("admin_csrf")

    if not token:
        token = secrets.token_urlsafe(32)
        session["admin_csrf"] = token

    return token


def check_admin_csrf():

    submitted = request.form.get("csrf_token", "")
    saved = session.get("admin_csrf", "")

    return bool(saved) and secrets.compare_digest(
        submitted, saved
    )


@app.route("/admin/recipients", methods=["GET"])
@admin_required
def admin_recipients():

    try:
        recipients = load_line_recipients()

    except Exception:
        app.logger.exception("Cannot load LINE recipients")
        return "Cannot load recipient data", 500

    notices = {
        "added": "เพิ่มผู้รับเรียบร้อยแล้ว",
        "deleted": "ลบผู้รับเรียบร้อยแล้ว",
        "duplicate": "LINE ID นี้มีอยู่แล้ว",
        "invalid": "รูปแบบ LINE User ID ไม่ถูกต้อง",
        "missing": "กรุณากรอก LINE User ID",
        "limit": "มีผู้รับครบ 50 คนแล้ว",
        "error": "เกิดข้อผิดพลาด กรุณาลองใหม่"
    }

    notice = notices.get(request.args.get("status", ""))

    return render_template_string("""
    <!DOCTYPE html>
    <html lang="th">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport"
              content="width=device-width, initial-scale=1">

        <title>LINE Recipient Manager</title>

        <style>
            body {
                font-family: Arial, sans-serif;
                background: #101827;
                color: white;
                padding: 20px;
                margin: 0;
            }

            .container {
                max-width: 650px;
                margin: 30px auto;
            }

            .card {
                background: #1e293b;
                padding: 22px;
                border-radius: 14px;
                margin-bottom: 18px;
            }

            input, button {
                box-sizing: border-box;
                width: 100%;
                padding: 13px;
                margin-top: 10px;
                border-radius: 8px;
                font-size: 15px;
            }

            input {
                background: #0f172a;
                color: white;
                border: 1px solid #475569;
            }

            button {
                border: none;
                cursor: pointer;
                color: white;
                background: #2563eb;
            }

            .delete {
                background: #dc2626;
            }

            .logout {
                background: #475569;
            }

            .recipient {
                background: #0f172a;
                padding: 14px;
                border-radius: 9px;
                margin-top: 12px;
                overflow-wrap: anywhere;
            }

            .notice {
                color: #86efac;
            }

            .muted {
                color: #94a3b8;
                font-size: 13px;
            }
        </style>
    </head>

    <body>
    <div class="container">

        <h2>APPWATCH MONITOR</h2>
        <p class="muted">LINE Recipient Manager</p>

        {% if notice %}
            <p class="notice">{{ notice }}</p>
        {% endif %}

        <div class="card">

            <h3>เพิ่มผู้รับแจ้งเตือน</h3>

            <form method="POST"
                  action="{{ url_for('admin_add_recipient') }}">

                <input type="hidden"
                       name="csrf_token"
                       value="{{ csrf_token }}">

                <input
                    type="text"
                    name="name"
                    placeholder="ชื่อผู้รับ เช่น หัวหน้า"
                    maxlength="50"
                >

                <input
                    type="text"
                    name="user_id"
                    placeholder="LINE User ID (U...)"
                    required
                    maxlength="33"
                >

                <button type="submit">
                    + เพิ่มผู้รับ
                </button>

            </form>

        </div>

        <div class="card">

            <h3>รายชื่อผู้รับ ({{ recipients|length }}/50)</h3>

            {% for recipient in recipients %}

                <div class="recipient">

                    <strong>{{ recipient.name }}</strong>

                    <p class="muted">
                        {{ recipient.user_id }}
                    </p>

                    <form method="POST"
                          action="{{ url_for('admin_delete_recipient') }}">

                        <input type="hidden"
                               name="csrf_token"
                               value="{{ csrf_token }}">

                        <input type="hidden"
                               name="user_id"
                               value="{{ recipient.user_id }}">

                        <button class="delete" type="submit">
                            ลบผู้รับคนนี้
                        </button>

                    </form>

                </div>

            {% else %}

                <p class="muted">
                    ยังไม่มีรายชื่อผู้รับแจ้งเตือน
                </p>

            {% endfor %}

        </div>

        <div class="card">

            <form method="POST"
                  action="{{ url_for('admin_logout') }}">

                <input type="hidden"
                       name="csrf_token"
                       value="{{ csrf_token }}">

                <button class="logout" type="submit">
                    ออกจากระบบ
                </button>

            </form>

        </div>

    </div>
    </body>
    </html>
    """,
    recipients=recipients,
    notice=notice,
    csrf_token=get_admin_csrf_token()
    )


@app.route("/admin/recipients/add", methods=["POST"])
@admin_required
def admin_add_recipient():

    if not check_admin_csrf():
        return "Invalid CSRF token", 403

    user_id = request.form.get("user_id", "").strip()
    name = request.form.get("name", "").strip()

    if not user_id:
        return redirect(url_for(
            "admin_recipients", status="missing"
        ))

    if not is_valid_line_user_id(user_id):
        return redirect(url_for(
            "admin_recipients", status="invalid"
        ))

    try:
        recipients = load_line_recipients()

        if any(r.get("user_id") == user_id for r in recipients):
            return redirect(url_for(
                "admin_recipients", status="duplicate"
            ))

        if len(recipients) >= 50:
            return redirect(url_for(
                "admin_recipients", status="limit"
            ))

        recipients.append({
            "user_id": user_id,
            "name": name or "ผู้รับแจ้งเตือน",
            "enabled": True
        })

        save_line_recipients(recipients)

        return redirect(url_for(
            "admin_recipients", status="added"
        ))

    except Exception:
        app.logger.exception("Add LINE recipient failed")
        return redirect(url_for(
            "admin_recipients", status="error"
        ))


@app.route("/admin/recipients/delete", methods=["POST"])
@admin_required
def admin_delete_recipient():

    if not check_admin_csrf():
        return "Invalid CSRF token", 403

    user_id = request.form.get("user_id", "").strip()

    try:
        recipients = load_line_recipients()

        updated = [
            r for r in recipients
            if r.get("user_id") != user_id
        ]

        if len(updated) != len(recipients):
            save_line_recipients(updated)

        return redirect(url_for(
            "admin_recipients", status="deleted"
        ))

    except Exception:
        app.logger.exception("Delete LINE recipient failed")
        return redirect(url_for(
            "admin_recipients", status="error"
        ))


@app.route("/admin/logout", methods=["POST"])
@admin_required
def admin_logout():

    if not check_admin_csrf():
        return "Invalid CSRF token", 403

    session.clear()

    return redirect(url_for("admin_login"))

def create_worker_image_url(key):
    if not APPWATCH_IMAGE_TOKEN or not APPWATCH_IMAGE_WORKER_URL:
       raise ValueError("AppWatch image Worker configuration missing")
    
    exp = int(datetime.now(timezone.utc).timestamp()) + 86400

    message = f"{key}:{exp}".encode("utf-8")

    signature = hmac.new(
        APPWATCH_IMAGE_TOKEN.encode("utf-8"),
        message,
        hashlib.sha256
    ).hexdigest()

    params = urlencode({
        "key": key,
        "exp": exp,
        "sig": signature
    })

    return f"{APPWATCH_IMAGE_WORKER_URL}?{params}"

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature")

    if not signature:
        return "Missing signature", 400

    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.exception("LINE Invalid Signature")
        return "Invalid signature", 400
    except Exception:
        app.logger.exception("Webhook processing error")
        return "Webhook error", 500

    return "OK", 200

    # =====================================
# APPWATCH IMAGE UPLOAD API
# =====================================

def cleanup_old_r2_images():
    """ลบภาพ AppWatch ที่เก่ากว่า 24 ชั่วโมง"""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    paginator = r2.get_paginator("list_objects_v2")

    for page in paginator.paginate(
        Bucket=R2_BUCKET_NAME,
        Prefix="appwatch/"
    ):
        for obj in page.get("Contents", []):
            if obj["LastModified"] < cutoff:
                r2.delete_object(
                    Bucket=R2_BUCKET_NAME,
                    Key=obj["Key"]
                )


@app.route("/appwatch/upload", methods=["POST"])
def appwatch_upload():

    # ตรวจสอบ Token
    auth = request.headers.get("Authorization", "")
    expected = f"Bearer {APPWATCH_UPLOAD_TOKEN or ''}"

    if not APPWATCH_UPLOAD_TOKEN or not hmac.compare_digest(auth, expected):
        return "Unauthorized", 401

    if r2 is None:
        return "R2 configuration missing", 500

    # โหลดรายชื่อผู้รับ
    try:
        recipients = load_line_recipients()

    except Exception:
        app.logger.exception("Cannot load LINE recipients")
        return "Cannot load recipients", 500

    active_recipients = [
        recipient for recipient in recipients
        if isinstance(recipient, dict)
        and recipient.get("enabled") is True
        and is_valid_line_user_id(
            str(recipient.get("user_id", ""))
        )
    ]

    if not active_recipients:
        return "No active LINE recipients", 409

    image_data = request.get_data()

    if not image_data or len(image_data) > 10 * 1024 * 1024:
        return "Invalid image size", 400

    try:
        # ตรวจสอบภาพ
        Image.open(io.BytesIO(image_data)).verify()

        img = Image.open(io.BytesIO(image_data))
        img.load()

        original = io.BytesIO()
        img.save(original, format="PNG", optimize=True)
        original_data = original.getvalue()

        # สร้างภาพตัวอย่าง
        preview_img = img.convert("RGB")
        preview_img.thumbnail((240, 240))

        preview = io.BytesIO()
        preview_img.save(
            preview,
            format="JPEG",
            quality=85,
            optimize=True
        )

        # สร้างชื่อไฟล์
        now = datetime.now(timezone.utc)
        file_id = uuid.uuid4().hex

        key = (
            f"appwatch/{now.strftime('%Y/%m/%d')}/"
            f"overview_{now.strftime('%H%M%S')}_{file_id}.png"
        )

        preview_key = key.replace(".png", "_preview.jpg")

        # อัปโหลดภาพเข้า R2
        r2.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=key,
            Body=original_data,
            ContentType="image/png"
        )

        r2.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=preview_key,
            Body=preview.getvalue(),
            ContentType="image/jpeg"
        )

        # สร้าง Signed URL
        original_url = create_worker_image_url(key)
        preview_url = create_worker_image_url(preview_key)

        # ส่งภาพให้ผู้รับทุกคน
        sent_count = 0
        failed_count = 0

        for recipient in active_recipients:

            try:
                line_bot_api.push_message(
                    recipient["user_id"],
                    [
                        TextSendMessage(
                            text=(
                                f"📊 AppWatch Overview\n"
                                f"เวลา: {now.strftime('%d/%m/%Y %H:%M:%S')} UTC"
                            )
                        ),
                        ImageSendMessage(
                            original_content_url=original_url,
                            preview_image_url=preview_url
                        )
                    ]
                )

                sent_count += 1

            except Exception:
                failed_count += 1
                app.logger.exception(
                    "Overview image delivery failed"
                )

        app.logger.info(
            "Overview image delivery: sent=%s failed=%s",
            sent_count,
            failed_count
        )

        # ลบภาพเก่ากว่า 24 ชั่วโมง
        try:
            cleanup_old_r2_images()
        except Exception:
            app.logger.exception("R2 cleanup failed")

        if sent_count == 0:
            return "LINE image delivery failed", 502

        return "Image uploaded and sent", (
            200 if failed_count == 0 else 207
        )

    except Exception:
        app.logger.exception("AppWatch image upload failed")
        return "Image upload failed", 500


# =====================================
# APPWATCH MULTI-RECIPIENT NOTIFY API
# =====================================

@app.route("/appwatch/notify", methods=["POST"])
def appwatch_notify():

    # ตรวจสอบ Token
    auth = request.headers.get("Authorization", "")
    expected = f"Bearer {APPWATCH_NOTIFY_TOKEN or ''}"

    if not APPWATCH_NOTIFY_TOKEN or not hmac.compare_digest(
        auth, expected
    ):
        return {"error": "Unauthorized"}, 401

    # ตรวจสอบข้อความ
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return {"error": "Invalid JSON"}, 400

    message = data.get("message")

    if not isinstance(message, str) or not message.strip():
        return {"error": "Message is required"}, 400

    if len(message) > 5000:
        return {"error": "Message too long"}, 400

    # อ่านรายชื่อผู้รับจาก R2
    try:
        recipients = load_line_recipients()

    except Exception:
        app.logger.exception("Cannot load LINE recipients")
        return {"error": "Cannot load recipients"}, 500

    active_recipients = [
        recipient for recipient in recipients
        if isinstance(recipient, dict)
        and recipient.get("enabled") is True
        and is_valid_line_user_id(
            str(recipient.get("user_id", ""))
        )
    ]

    if not active_recipients:
        return {"error": "No active recipients"}, 409

    # ส่งข้อความให้ผู้รับทุกคน
    success_count = 0
    failed_count = 0

    for recipient in active_recipients:

        user_id = recipient["user_id"]

        try:
            line_bot_api.push_message(
                user_id,
                [
                    TextSendMessage(text=message)
                ]
            )

            success_count += 1

        except Exception:
            failed_count += 1

            app.logger.exception(
                "LINE notification failed for recipient"
            )

    app.logger.info(
        "AppWatch notification result: sent=%s failed=%s",
        success_count,
        failed_count
    )

    return {
        "success": failed_count == 0,
        "sent": success_count,
        "failed": failed_count,
        "total": len(active_recipients)
    }, 200 if failed_count == 0 else 207


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = getattr(event.source, "user_id", None)
    print("LINE USER ID:", user_id, flush=True)

    text = event.message.text.strip().lower()
    if not text:
        return


    commands = (
        "รายงานkiosk", "ยอด", "รายงาน",
        "บัตรครึ่งใบ", "บัตร",
        "wifi", "ci",
        "เบอร์", "เบอ", "เบอร์โทร", "เบอร์โทรศัพท์",
        "ภาษี", "vat",
        "help", "บอท"
    )

    if text not in commands:
        return

    messages = []

    if text in ("help", "บอท"):
        messages.append(TextSendMessage(
            text=(
                "คำสั่งที่ใช้ได้:\n"
                "รายงานkiosk\n"
                "ยอด\n"
                "รายงาน\n"
                "บัตรครึ่งใบ / บัตร\n"
                "wifi / ci\n"
                "เบอร์\n"
                "ภาษี / vat"
            )
        ))

    elif text in ("รายงานkiosk", "ยอด", "รายงาน"):
        messages.append(TextSendMessage(
            text=(
                "📊 รายงานตู้ KIOSK\n"
                "https://smartcargo.airportthai.co.th/aotwebmanagement/reports/KisokreportComponent\n\n"
                "User: wanakorn.poa@proinside.co.th\n"
                "Password: 10101010\n\n"
                "ไปที่หัวข้อ A7 รายงาน\n"
                "เลือก รายงานประจำตู้ KIOSK\n"
                "เช็คหัวข้อย่อยที่ 1 รายงานยอดขายตู้ Kiosk เลือกเช็คทีละตู้ อย่าลืมเลือกวันให้ถูกกับวันที่เช็ค\n"
                "หัวข้อย่อยที่ 7 คือ รายงานสรุปยอดขายรายวัน เลือกตู้ทั้งหมด แล้วก็เลือกวันที่ที่จะเช็ค\n"
                "ถ้ารายงานตรงกับกระดาษ A 4 ส่งในกลุ่มทุกเที่ยงคืน ก็แจ้งว่ารายงานครบทุกตู้"
            )
        ))

    elif text in ("บัตรครึ่งใบ", "บัตร"):
        messages.append(TextSendMessage(
            text=(
                "🎫 วิธีแก้ปริ้นครึ่งใบ\n"
                "- เช็คฝาปิด\n"
                "- ปิด/เปิดเครื่องปริ้น\n"
                "- ลบ driver\n"
                "- Restart\n"
                "- เปิดสวิตซ์เครื่องปริ้น\n"
                "- ปรับค่าเป็น : ใช้ผ่านความร้อนโดยตร\n"
                "- Set ค่ากระดาษใหม่เป็น 80 mm 50 mm 0 mm 0mm รวม 4 ช่อง\n"
                "- แล้วเทสผ่าน admin ถ้าได้ก็เปิดใช้ได้ปกติครับ แต่ถ้าไม่ได้ให้เริ่มทำใหม่ที่ข้อ 1 "
            )
        ))

    elif text in ("wifi", "ci"):
        messages.append(TextSendMessage(
            text="📶 Wifi CI\nPi@FDMS464690"
        ))

    elif text in ("เบอร์", "เบอ", "เบอร์โทร", "เบอร์โทรศัพท์"):
        messages.append(TextSendMessage(
            text=(
                "📞 เบอร์ทีมงาน\n"
                "ฮอน 091-568-8414\n"
                "เบ๊บ 061-818-5046\n"
                "เวย์ 062-462-5538\n"
                "ต้นตาว 099-790-7639\n"
                "บาส 082-315-0099\n"
                "ก๊ก 098-920-0310\n"
                "ดิฟ 091-037-5913"
            )
        ))

    elif text in ("ภาษี", "vat"):
        image_url = "https://github.com/vankokeiei/line-group-bot/blob/main/LINE_NOTE_260101_1.jpg?raw=true"
        messages.append(TextSendMessage(text="📄 ตัวอย่างเอกสารภาษี"))
        messages.append(ImageSendMessage(
            original_content_url=image_url,
            preview_image_url=image_url
        ))

    line_bot_api.reply_message(event.reply_token, messages)

if __name__ == "__main__":
    app.run(port=5000)
