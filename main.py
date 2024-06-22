import requests
import json
import time
import os
import os.path
import re
from web3 import Web3
from keep_alive import keep_alive

# Update the following variables with your own Etherscan and BscScan API keys and Telegram bot token
# ETHERSCAN_API_KEY = '<your_etherscan_api_key>'
# BSCSCAN_API_KEY = '<your_bscscan_api_key>'

BASE_API_KEY = os.environ['base_api']
TELEGRAM_BOT_TOKEN = os.environ['bot_token']
TELEGRAM_CHAT_ID = os.environ['telegram_chat_ids'].split(',')


# Define some helper functions
def get_wallet_transactions(wallet_address, blockchain):
  # if blockchain == 'eth':
  #     url = f'https://api.etherscan.io/api?module=account&action=txlist&address={wallet_address}&sort=desc&apikey={ETHERSCAN_API_KEY}'
  # elif blockchain == 'bnb':
  #     url = f'https://api.bscscan.com/api?module=account&action=txlist&address={wallet_address}&sort=desc&apikey={BSCSCAN_API_KEY}'
  if blockchain == 'base':
    url = f'https://api.basescan.org/api?module=account&action=txlist&address={wallet_address}&sort=desc&apikey={BASE_API_KEY}'
  else:
    raise ValueError('Invalid blockchain specified')

  response = requests.get(url)
  data = json.loads(response.text)

  result = data.get('result', [])
  if not isinstance(result, list):
    print(
        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Error fetching transactions for {wallet_address} on {blockchain.upper()} blockchain: {data}"
    )
    return []

  return result


def send_telegram_notification(message, token, token_ca, value, usd_value,
                               tx_hash, blockchain):
  # if blockchain == 'eth':
  #     etherscan_link = f'<a href="https://etherscan.io/tx/{tx_hash}">Etherscan</a>'
  # elif blockchain == 'bnb':
  #     etherscan_link = f'<a href="https://bscscan.com/tx/{tx_hash}">BscScan</a>'
  if blockchain == 'base':
    etherscan_link = f'<a href="https://basescan.org/tx/{tx_hash}">BaseScan</a>'
    dexscreener_link = f'<a href="https://dexscreener.com/base/{token_ca}">DexScreener</a>'
  else:
    raise ValueError('Invalid blockchain specified')

  currency = blockchain.upper()
  if currency == 'BASE':
    currency = 'ETH'

  url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
  payload = {
      'text':
      f'{message}:\n{token}: {token_ca}\n{dexscreener_link}\n{etherscan_link}\nValue: {value:.6f} {currency} (${usd_value:.2f})',
      'parse_mode': 'HTML'
  }

  for chat_id in TELEGRAM_CHAT_ID:
    payload['chat_id'] = chat_id
    response = requests.post(url, data=payload)
    print(
        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Telegram notification sent with message: {message}, value: {value} {blockchain.upper()} (${usd_value:.2f})"
    )
  return response


def monitor_wallets():
  watched_wallets = set()
  file_path = "watched_wallets.txt"
  if not os.path.exists(file_path):
    open(file_path, 'w').close()

  latest_tx_hashes = {}
  latest_tx_hashes_path = "latest_tx_hashes.json"
  if os.path.exists(latest_tx_hashes_path):
    with open(latest_tx_hashes_path, "r") as f:
      latest_tx_hashes = json.load(f)

  last_run_time = 0
  last_run_time_path = "last_run_time.txt"
  if os.path.exists(last_run_time_path):
    with open(last_run_time_path, "r") as f:
      last_run_time = int(f.read())

  while True:
    try:
      # Fetch current ETH and BNB prices in USD from CoinGecko API
      eth_usd_price_url = 'https://api.coingecko.com/api/v3/simple/price?ids=ethereum%2Cbinancecoin&vs_currencies=usd'
      response = requests.get(eth_usd_price_url)
      data = json.loads(response.text)
      eth_usd_price = data['ethereum']['usd']
      bnb_usd_price = data['binancecoin']['usd']

      # Read from file
      with open(file_path, 'r') as f:
        watched_wallets = set(f.read().splitlines())

      for wallet in watched_wallets:
        blockchain, name, wallet_address = wallet.split(':')
        transactions = get_wallet_transactions(wallet_address, blockchain)
        for tx in transactions:
          tx_hash = tx['hash']
          tx_time = int(tx['timeStamp'])

          token = ''
          token_ca = ''

          if tx_hash not in latest_tx_hashes and tx_time > last_run_time:
            value = float(
                tx['value']) / 10**18  # Convert from wei to ETH or BNB
            usd_value = value * (eth_usd_price if blockchain == 'eth'
                                 or blockchain == 'base' else bnb_usd_price
                                 )  # Calculate value in USD
            # if tx['to'].lower() == wallet_address.lower():
            if usd_value == 0:
              message = f'🚨 Incoming transaction detected on {name.upper()}\'s wallet ({wallet_address})'
              send_telegram_notification(message, token, token_ca, value,
                                         usd_value, tx['hash'], blockchain)
              #print(f'\n{message}, Value: {value} {blockchain.upper()}, ${usd_value:.2f}\n')
            # elif tx['from'].lower() == wallet_address.lower():
            elif usd_value != 0:
              value = float(
                  tx['value']) / 10**18  # Convert from wei to ETH or BNB
              usd_value = value * (eth_usd_price if blockchain == 'eth'
                                   or blockchain == 'base' else bnb_usd_price
                                   )  # Calculate value in USD
              message = f'🚨 Outgoing transaction detected on {name.upper()}\'s wallet ({wallet_address})'
              send_telegram_notification(message, token, token_ca, value,
                                         usd_value, tx['hash'], blockchain)
              #print(f'\n{message}, Value: {value} {blockchain.upper()}, ${usd_value:.2f}\n')

            latest_tx_hashes[tx_hash] = int(tx['blockNumber'])

      # Save latest_tx_hashes to file
      with open(latest_tx_hashes_path, "w") as f:
        json.dump(latest_tx_hashes, f)

      # Update last_run_time
      last_run_time = int(time.time())
      with open(last_run_time_path, "w") as f:
        f.write(str(last_run_time))

      # Sleep for 1 minute
      time.sleep(60)
    except Exception as e:
      print(f'An error occurred: {e}')
      # Sleep for 10 seconds before trying again
      time.sleep(10)


def add_wallet(wallet_address, name, blockchain):
  file_path = "watched_wallets.txt"
  with open(file_path, 'a') as f:
    f.write(f'{blockchain}:{name}:{wallet_address}\n')


def remove_wallet(wallet_address, name, blockchain):
  file_path = "watched_wallets.txt"
  temp_file_path = "temp.txt"
  with open(file_path, 'r') as f, open(temp_file_path, 'w') as temp_f:
    for line in f:
      if line.strip() != f'{blockchain}:{name}:{wallet_address}':
        temp_f.write(line)
  os.replace(temp_file_path, file_path)


# Define the command handlers for the Telegram bot
def start(update, context):
  message = """
👋 Welcome to the Ethereum and Binance Wallet Monitoring Bot!

Use /add <blockchain> <name> <wallet_address> to add a new wallet to monitor.

Example: /add ETH david 0x123456789abcdef

Use /remove <blockchain> <name> <wallet_address> to stop monitoring a wallet.

Example: /remove ETH david 0x123456789abcdef

Use /list <blockchain> to list all wallets being monitored for a specific blockchain.

Example: /list ETH or just /list
    """
  context.bot.send_message(chat_id=update.message.chat_id, text=message)


def send_message(update, context):
  if len(context.args) <= 0:
    context.bot.send_message(chat_id=update.message.chat_id,
                             text="Please provide the message.")
    return

  message = ' '.join(context.args)

  url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
  payload = {'text': f'{message}', 'parse_mode': 'HTML'}

  for chat_id in TELEGRAM_CHAT_ID:
    payload['chat_id'] = chat_id
    response = requests.post(url, data=payload)
    print(f"Message sent to chat_id: {chat_id}")
  return response


def add(update, context):
  if len(context.args) < 2:
    context.bot.send_message(
        chat_id=update.message.chat_id,
        text="Please provide a blockchain and wallet address to add.")
    return

  blockchain = context.args[0].lower()
  name = context.args[1].lower()
  wallet_address = context.args[2]

  # Check if the wallet address is in the correct format for the specified blockchain
  # if blockchain == 'eth':
  #     if not re.match(r'^0x[a-fA-F0-9]{40}$', wallet_address):
  #         context.bot.send_message(
  #             chat_id=update.message.chat_id,
  #             text=f"{wallet_address} is not a valid Ethereum wallet address."
  #         )
  #         return
  # elif blockchain == 'bnb':
  #     if not re.match(r'^0x[a-fA-F0-9]{40}$', wallet_address):
  #         context.bot.send_message(
  #             chat_id=update.message.chat_id,
  #             text=
  #             f"{wallet_address} is not a valid Binance Smart Chain wallet address."
  #         )
  #         return
  if blockchain == 'base':
    if not re.match(r'^0x[a-fA-F0-9]{40}$', wallet_address):
      context.bot.send_message(
          chat_id=update.message.chat_id,
          text=f"{wallet_address} is not a valid Basescan wallet address.")
  else:
    context.bot.send_message(
        chat_id=update.message.chat_id,
        text=f"Invalid blockchain specified: {blockchain}")
    return

  add_wallet(wallet_address, name, blockchain)
  message = f'Added {wallet_address} to the list of watched {blockchain.upper()} wallets.'
  context.bot.send_message(chat_id=update.message.chat_id, text=message)


def remove(update, context):
  if len(context.args) < 2:
    context.bot.send_message(
        chat_id=update.message.chat_id,
        text=
        "Please provide a blockchain and wallet address to remove.\nUsage: /remove ETH 0x123456789abcdef"
    )
    return
  blockchain = context.args[0].lower()
  wallet_address = context.args[1]
  remove_wallet(wallet_address, name, blockchain)
  message = f'Removed {wallet_address} from the list of watched {blockchain.upper()} wallets.'
  context.bot.send_message(chat_id=update.message.chat_id, text=message)


def list_wallets(update, context):
  with open("watched_wallets.txt", "r") as f:
    wallets = [line.strip() for line in f.readlines()]
  if wallets:
    # eth_wallets = []
    # bnb_wallets = []
    base_wallets = []
    base_name = []
    for wallet in wallets:
      blockchain, name, wallet_address = wallet.split(':')
      # if blockchain == 'eth':
      #     eth_wallets.append(wallet_address)
      # elif blockchain == 'bnb':
      #     bnb_wallets.append(wallet_address)
      if blockchain == 'base':
        base_wallets.append(wallet_address)
        base_name.append(name)

    message = "The following wallets are currently being monitored\n"
    message += "\n"
    # if eth_wallets:
    #     message += "Ethereum Wallets:\n"
    #     for i, wallet in enumerate(eth_wallets):
    #         message += f"{i+1}. {wallet}\n"
    #     message += "\n"
    # if bnb_wallets:
    #     message += "Binance Coin Wallets:\n"
    #     for i, wallet in enumerate(bnb_wallets):
    #         message += f"{i+1}. {wallet}\n"
    if base_wallets:
      message += "Basescan Wallets:\n"
      for i, wallet in enumerate(base_wallets):
        message += f"{i+1}. ({base_name[i]}) {wallet}\n"
    context.bot.send_message(chat_id=update.message.chat_id, text=message)
  else:
    message = "There are no wallets currently being monitored."
    context.bot.send_message(chat_id=update.message.chat_id, text=message)


# Set up the Telegram bot
from telegram.ext import Updater, CommandHandler

updater = Updater(token=TELEGRAM_BOT_TOKEN, use_context=True)
# updater = Updater(token=TELEGRAM_BOT_TOKEN, use_context=True)
dispatcher = updater.dispatcher

# Define the command handlers
start_handler = CommandHandler('start', start)
add_handler = CommandHandler('add', add)
remove_handler = CommandHandler('remove', remove)
list_handler = CommandHandler('list', list_wallets)
send_message_handler = CommandHandler('message', send_message)

# Add the command handlers to the dispatcher
dispatcher.add_handler(start_handler)
dispatcher.add_handler(add_handler)
dispatcher.add_handler(remove_handler)
dispatcher.add_handler(list_handler)
dispatcher.add_handler(send_message_handler)

# send_message('Dogbwifhat: 0x6dC87FBE9F6382fB156308050fEb765BCdDf459A')

keep_alive()
updater.start_polling()
print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Telegram bot started.")

print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Monitoring wallets...")
monitor_wallets()
