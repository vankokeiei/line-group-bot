from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os

app = Flask(__name__)

line_bot_api = LineBotApi(os.getenv("LINE_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    handler.handle(body, signature)
    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()

    # ตอบเฉพาะคำสั่ง !
    if not text.startswith("!"):
        return

    if text == "help":
        reply = (
            "คำสั่งที่ใช้ได้:\n"
            "รายงานkiosk , รายงาน , ยอด"
        )

    elif text == "รายงานkiosk , รายงาน , ยอด":
        reply = (
            "📊 รายงานตู้ KIOSK\n"
            "https://smartcargo.airportthai.co.th/aotwebmanagement/reports/KisokreportComponent\n\n"
            "วิธีใช้งาน:\n"
            "ไปที่หัวข้อ A7 รายงาน\n"
            "เลือกไปที่รายงานประจำตู้ KIOSK\n"
            "เช็คที่หัวข้อย่อยที่ 1 กับหัวข้อย่อยที่ 7\n\n"
            "หัวข้อย่อยที่ 1:\n"
            "- รายงานยอดขายตู้ Kiosk\n"
            "- เลือกเช็คทีละตู้\n"
            "- อย่าลืมเลือกวันให้ตรงกับวันที่เช็ค\n\n"
            "หัวข้อย่อยที่ 7:\n"
            "- รายงานสรุปยอดขายรายวัน\n"
            "- เลือกตู้ทั้งหมด\n"
            "- เลือกวันที่ที่จะเช็ค\n\n"
            "ถ้ารายงานตรงกับกระดาษ A4\n"
            "และส่งในกลุ่มทุกเที่ยงคืน\n"
            "ให้แจ้งว่า: รายงานครบทุกตู้"
        )
        
    else:
        reply = "ไม่รู้จักคำสั่งนี้ พิมพ์ help"
    if text == "สวัสดี":
        reply = "สวัสดีครับ ผมคือบอทกลุ่ม 🤖"
    elif text == "help":
        reply = "คำสั่ง: สวัสดี / ราคา / สถานะ"
    elif text == "ราคา":
        reply = "กรุณาติดต่อแอดมินครับ"
    else:
        reply = "ไม่รู้จักคำสั่งนี้ พิมพ์ help"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )

if __name__ == "__main__":
    app.run()
