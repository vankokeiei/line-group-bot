from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.models import (
    MessageEvent, TextMessage,
    TextSendMessage, ImageSendMessage
)
import os

app = Flask(__name__)

line_bot_api = LineBotApi(os.getenv("LINE_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

@app.route("/callback", methods=["POST"])
def callback():
    try:
        signature = request.headers["X-Line-Signature"]
        body = request.get_data(as_text=True)
        handler.handle(body, signature)
    except Exception as e:
        print(e)
    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
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
                "รายงานkiosk\nยอด\nรายงาน\n"
                "บัตรครึ่งใบ / บัตร\n"
                "Wifi / ci\n"
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
                "Password: 10101010"
            )
        ))

    elif text in ("บัตรครึ่งใบ", "บัตร"):
        messages.append(TextSendMessage(
            text="🎫 วิธีแก้ปริ้นครึ่งใบ (ดูรายละเอียดในคู่มือ)"
        ))

    elif text in ("wifi", "ci"):
        messages.append(TextSendMessage(
            text="📶 Wifi CI\nPi@FDMS464690"
        ))

    elif text in ("เบอร์", "เบอ", "เบอร์โทร", "เบอร์โทรศัพท์"):
        messages.append(TextSendMessage(
            text="📞 เบอร์ทีมงาน (ดูในโพสต์ปักหมุด)"
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
    app.run(port=50000)
# To run the app, set the environment variables LINE_ACCESS_TOKEN and LINE_CHANNEL_SECRET
# Then execute: python app.py