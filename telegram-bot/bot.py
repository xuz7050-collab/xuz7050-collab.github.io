import os, html, sqlite3, logging, time
import cv2
import numpy as np
import pyotp
from cryptography.fernet import Fernet, InvalidToken
from fastapi import FastAPI, Request, HTTPException
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, Update
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from urllib.parse import urlparse, parse_qs

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ["BOT_TOKEN"]
cipher = Fernet(os.environ["FERNET_KEY"].encode())
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]
PUBLIC_URL = os.environ["RENDER_EXTERNAL_URL"].rstrip("/")
DB_PATH = os.getenv("DB_PATH", "/tmp/authenticator.db")

bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
app = FastAPI()

def db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS accounts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL, label TEXT NOT NULL,
        secret BLOB NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    c.commit()
    return c

def add_account(uid, label, secret):
    with db() as c:
        c.execute("INSERT INTO accounts(user_id,label,secret) VALUES(?,?,?)",
                  (uid, label, cipher.encrypt(secret.encode())))

def parse_qr(value):
    p = urlparse(value)
    if p.scheme != "otpauth" or p.netloc != "totp":
        raise ValueError()
    q = parse_qs(p.query)
    secret = q.get("secret", [""])[0].replace(" ", "").upper()
    if not secret:
        raise ValueError()
    pyotp.TOTP(secret).now()
    label = p.path.lstrip("/") or "Authenticator"
    label = label.split(":")[-1]
    issuer = q.get("issuer", [""])[0]
    return (f"{issuer} - {label}" if issuer else label)[:100], secret

@dp.message(Command("start"))
async def start(m: Message):
    await m.answer("🔐 <b>动态验证码助手</b>\\n发送 TOTP 二维码图片绑定。\\n\\n"
                   "/add 名称 密钥：手动添加\\n/list：查看账号\\n"
                   "/code 编号：获取验证码\\n/delete 编号：删除账号\\n/help：帮助")

@dp.message(Command("help"))
async def help_cmd(m: Message):
    await start(m)

@dp.message(Command("add"))
async def add_cmd(m: Message):
    a = (m.text or "").split(maxsplit=2)
    if len(a) < 3:
        await m.answer("格式：<code>/add 名称 密钥</code>")
        return
    label, secret = a[1][:100], a[2].replace(" ", "").upper()
    try:
        pyotp.TOTP(secret).now()
        add_account(m.from_user.id, label, secret)
        await m.answer(f"✅ 已添加：<b>{html.escape(label)}</b>")
    except Exception:
        await m.answer("密钥格式不正确，请检查后重试。")

@dp.message(Command("list"))
async def list_cmd(m: Message):
    with db() as c:
        rows = c.execute("SELECT id,label FROM accounts WHERE user_id=? ORDER BY id",
                         (m.from_user.id,)).fetchall()
    if not rows:
        await m.answer("还没有绑定账号。发送二维码图片，或使用 /add 添加。")
        return
    await m.answer("<b>你的账号：</b>\\n" + "\\n".join(
        f"{r['id']}. {html.escape(r['label'])}" for r in rows) +
        "\\n\\n使用 <code>/code 编号</code> 获取验证码。")

@dp.message(Command("code"))
async def code_cmd(m: Message):
    a = (m.text or "").split(maxsplit=1)
    if len(a) != 2 or not a[1].isdigit():
        await m.answer("格式：<code>/code 编号</code>")
        return
    with db() as c:
        r = c.execute("SELECT label,secret FROM accounts WHERE user_id=? AND id=?",
                      (m.from_user.id, int(a[1]))).fetchone()
    if not r:
        await m.answer("没有找到这个账号。")
        return
    try:
        secret = cipher.decrypt(r["secret"]).decode()
        left = 30 - int(time.time()) % 30
        await m.answer(f"<b>{html.escape(r['label'])}</b>\\n<code>{pyotp.TOTP(secret).now()}</code>\\n约 {left} 秒后更新。")
    except InvalidToken:
        await m.answer("解密失败，请检查加密密钥是否变更。")

@dp.message(Command("delete"))
async def delete_cmd(m: Message):
    a = (m.text or "").split(maxsplit=1)
    if len(a) != 2 or not a[1].isdigit():
        await m.answer("格式：<code>/delete 编号</code>")
        return
    with db() as c:
        cur = c.execute("DELETE FROM accounts WHERE user_id=? AND id=?",
                        (m.from_user.id, int(a[1])))
    await m.answer("✅ 已删除。" if cur.rowcount else "没有找到这个账号。")

@dp.message(F.photo)
async def qr_photo(m: Message):
    f = await bot.get_file(m.photo[-1].file_id)
    stream = await bot.download_file(f.file_path)
    img = cv2.imdecode(np.frombuffer(stream.read(), np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        await m.answer("无法读取图片，请重新发送清晰二维码。")
        return
    text, _, _ = cv2.QRCodeDetector().detectAndDecode(img)
    try:
        label, secret = parse_qr(text)
        add_account(m.from_user.id, label, secret)
        await m.answer(f"✅ 已绑定：<b>{html.escape(label)}</b>")
    except Exception:
        await m.answer("未识别到有效的 TOTP 验证器二维码。")

@app.get("/")
async def health():
    return {"status": "ok"}

@app.post("/telegram-webhook")
async def webhook(req: Request):
    if req.headers.get("X-Telegram-Bot-Api-Secret-Token", "") != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")
    payload = await req.json()
    update = Update.model_validate(payload, context={"bot": bot})
    await dp.feed_update(bot, update)
    return {"ok": True}

@app.on_event("startup")
async def startup():
    db().close()
    await bot.set_webhook(PUBLIC_URL + "/telegram-webhook",
                          secret_token=WEBHOOK_SECRET, drop_pending_updates=False)

@app.on_event("shutdown")
async def shutdown():
    await bot.session.close()
