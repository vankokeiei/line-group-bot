from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.models import (
    MessageEvent, TextMessage,
    TextSendMessage, ImageSendMessage
)
import os

from linebot.exceptions import InvalidSignatureError
app = Flask(__name__)


line_bot_api = LineBotApi(os.getenv("LINE_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

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
