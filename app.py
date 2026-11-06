from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.models import (
    MessageEvent, TextMessage,
    TextSendMessage, ImageSendMessage
)
import os
import uuid
import boto3
import io
import hmac
from datetime import datetime, timezone, timedelta
from PIL import Image
from botocore.config import Config

from linebot.exceptions import InvalidSignatureError
app = Flask(__name__)


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
LINE_USER_ID = os.getenv("LINE_USER_ID")

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

    if r2 is None or not LINE_USER_ID:
        return "R2 or LINE configuration missing", 500

    image_data = request.get_data()

    if not image_data or len(image_data) > 10 * 1024 * 1024:
        return "Invalid image size", 400

    try:
        # ตรวจสอบว่าเป็นไฟล์ภาพจริง
        Image.open(io.BytesIO(image_data)).verify()

        img = Image.open(io.BytesIO(image_data))
        img.load()

        # เตรียมภาพต้นฉบับ PNG
        original = io.BytesIO()
        img.save(original, format="PNG", optimize=True)
        original_data = original.getvalue()

        # เตรียมภาพตัวอย่างขนาดเล็กสำหรับ LINE
        preview_img = img.convert("RGB")
        preview_img.thumbnail((240, 240))

        preview = io.BytesIO()
        preview_img.save(
            preview,
            format="JPEG",
            quality=85,
            optimize=True
        )

        # สร้างชื่อไฟล์ไม่ให้ซ้ำกัน
        now = datetime.now(timezone.utc)
        file_id = uuid.uuid4().hex

        key = (
            f"appwatch/{now.strftime('%Y/%m/%d')}/"
            f"overview_{now.strftime('%H%M%S')}_{file_id}.png"
        )

        preview_key = key.replace(".png", "_preview.jpg")

        # อัปโหลดภาพทั้งสองขนาดเข้า R2
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

        # สร้างลิงก์ชั่วคราวให้ LINE เปิดอ่านภาพได้
        original_url = r2.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": R2_BUCKET_NAME,
                "Key": key
            },
            ExpiresIn=86400
        )

        preview_url = r2.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": R2_BUCKET_NAME,
                "Key": preview_key
            },
            ExpiresIn=86400
        )

        # ส่งภาพเข้า LINE
        line_bot_api.push_message(
            LINE_USER_ID,
            [
                TextSendMessage(
                    text=f"📊 AppWatch Overview\nเวลา: {now.strftime('%d/%m/%Y %H:%M:%S')} UTC"
                ),
                ImageSendMessage(
                    original_content_url=original_url,
                    preview_image_url=preview_url
                )
            ]
        )

        # ลบภาพที่เก่ากว่า 24 ชั่วโมง
        try:
            cleanup_old_r2_images()
        except Exception:
            app.logger.exception("R2 cleanup failed")

        return "Image uploaded and sent", 200

    except Exception:
        app.logger.exception("AppWatch image upload failed")
        return "Image upload failed", 500

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
