import os, time, sqlite3, logging, io
from urllib.parse import urlparse, parse_qs, unquote
import pyotp, cv2, numpy as np
from cryptography.fernet import Fernet, InvalidToken
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

logging.basicConfig(level=logging.INFO)
TOKEN=os.environ["BOT_TOKEN"]
cipher=Fernet(os.environ["FERNET_KEY"].encode())
DB_PATH=os.getenv("DB_PATH","authenticator.db")
ADMINS={int(x) for x in os.getenv("ADMIN_IDS","").split(",") if x.strip()}
def conn():
 c=sqlite3.connect(DB_PATH)
 c.execute("CREATE TABLE IF NOT EXISTS accounts(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,label TEXT,secret BLOB,created INTEGER)")
 return c
def parse(value):
 value=value.strip()
 if value.startswith("otpauth://"):
  p=urlparse(value)
  if p.netloc!="totp": raise ValueError("只支持 TOTP 二维码")
  q=parse_qs(p.query); secret=q.get("secret",[""])[0].replace(" ","").upper()
  label=unquote(p.path.lstrip("/")) or q.get("issuer",["账号"])[0]
 else: secret=value.replace(" ","").replace("-","").upper(); label="我的账号"
 if not secret: raise ValueError("二维码或密钥为空")
 pyotp.TOTP(secret).now()
 return label,secret
def add(uid,label,secret):
 with conn() as c: c.execute("INSERT INTO accounts(user_id,label,secret,created) VALUES(?,?,?,?)",(uid,label[:80],cipher.encrypt(secret.encode()),int(time.time())))
def rows(uid):
 with conn() as c: data=c.execute("SELECT id,label,secret FROM accounts WHERE user_id=? ORDER BY id",(uid,)).fetchall()
 out=[]
 for i,l,s in data:
  try: out.append((i,l,cipher.decrypt(s).decode()))
  except InvalidToken: logging.exception("decrypt failed")
 return out
bot=Bot(TOKEN,default=DefaultBotProperties(parse_mode=ParseMode.HTML)); dp=Dispatcher()
@dp.message(Command("start"))
async def start(m):
 await m.answer("<b>🔐 动态验证器</b>\n发送 TOTP 二维码图片、otpauth:// 链接或 Base32 密钥绑定。\n/list 查看账号，/code 查看验证码，/delete 编号 删除账号。\n只绑定你本人有权管理的账号，请勿分享密钥。")
@dp.message(Command("help"))
async def help_(m): await start(m)
@dp.message(F.photo)
async def photo(m):
 try:
  f=await bot.get_file(m.photo[-1].file_id); b=io.BytesIO(); await bot.download_file(f.file_path,b)
  img=cv2.imdecode(np.frombuffer(b.getvalue(),np.uint8),cv2.IMREAD_COLOR)
  value,_,_=cv2.QRCodeDetector().detectAndDecode(img)
  if not value: raise ValueError("二维码不清晰或无法识别")
  label,secret=parse(value); add(m.from_user.id,label,secret)
  await m.answer(f"✅ 已绑定：<b>{label}</b>")
 except Exception as e: await m.answer("绑定失败："+str(e))
@dp.message(Command("list"))
async def listing(m):
 a=rows(m.from_user.id)
 await m.answer("\n".join([f"{i}. {l}" for i,l,s in a]) if a else "还没有绑定账号。")
@dp.message(Command("code"))
async def codes(m):
 a=rows(m.from_user.id)
 if not a: return await m.answer("还没有绑定账号。")
 left=30-int(time.time())%30
 await m.answer("\n\n".join(f"<b>{l}</b>\n<code>{pyotp.TOTP(s).now()}</code>（{left} 秒后刷新）" for i,l,s in a))
@dp.message(Command("delete"))
async def delete(m):
 p=(m.text or "").split()
 if len(p)!=2 or not p[1].isdigit(): return await m.answer("用法：/delete 编号")
 with conn() as c: cur=c.execute("DELETE FROM accounts WHERE id=? AND user_id=?",(int(p[1]),m.from_user.id))
 await m.answer("已删除。" if cur.rowcount else "没有找到该账号。")
@dp.message(Command("stats"))
async def stats(m):
 if m.from_user.id not in ADMINS: return
 with conn() as c:
  u=c.execute("SELECT COUNT(DISTINCT user_id) FROM accounts").fetchone()[0]
  n=c.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
 await m.answer(f"绑定用户数：{u}\n账号总数：{n}")
@dp.message(F.text)
async def textadd(m):
 t=(m.text or "").strip()
 if t.startswith("/"): return
 try:
  label,secret=parse(t); add(m.from_user.id,label,secret); await m.answer(f"✅ 已绑定：<b>{label}</b>")
 except Exception: await m.answer("无法识别。请发送 TOTP Base32 密钥或 otpauth:// 链接。")
async def main():
 conn().close()
 await dp.start_polling(bot)
if __name__=="__main__":
 import asyncio; asyncio.run(main())
