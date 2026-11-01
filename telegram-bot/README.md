# Telegram 动态验证器机器人

包含多用户隔离、TOTP 六位动态码、二维码图片绑定、Base32/otpauth 链接绑定、多账号列表与删除、管理员统计、Fernet 密钥加密。

## 本地运行
Python 3.11+
1. `pip install -r requirements.txt`
2. 设置环境变量 `BOT_TOKEN`、`FERNET_KEY`，可选 `ADMIN_IDS`。
3. 生成加密密钥：`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
4. `python bot.py`

## Render
把文件放入 GitHub 仓库的 `telegram-bot/` 子目录，保留网页文件不动。Render 新建 Background Worker，Root Directory 填 `telegram-bot`，Build Command 填 `pip install -r requirements.txt`，Start Command 填 `python bot.py`。设置 `BOT_TOKEN`、`FERNET_KEY`、`ADMIN_IDS` 和 `DB_PATH=/var/data/authenticator.db`。长期保存真实密钥必须配置持久化磁盘并确认当前套餐支持。

安全提示：只绑定本人有权管理的验证器。Bot Token 和 TOTP 密钥不要上传 GitHub 或发给他人。本项目是独立实现，不是对第三方机器人的源码复制。
