import asyncio
import csv
from datetime import datetime
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from decouple import config

PHONE_NUMBER=config("PHONE")

async def scrape_telegram(client, keyword, chat_name=None, limit=30):
        
    try:
        # Connect and authenticate
        await client.start(phone=PHONE_NUMBER)
        print("✓ Connected to Telegram")
        
        # Check if password is needed
        if await client.is_user_authorized() == False:
            await client.send_code_request(PHONE_NUMBER)
            try:
                await client.sign_in(PHONE_NUMBER, input('Enter code: '))
            except SessionPasswordNeededError:
                await client.sign_in(password=input('Password: '))
        
        messages = []
        
        if chat_name:
            # Search in specific chat
            try:
                entity = await client.get_entity(chat_name)
                print(f"✓ Searching in: {chat_name}")
                
                async for message in client.iter_messages(entity, limit=limit*2):
                    if message.text and keyword.lower() in message.text.lower():
                        messages.append(message)
                        if len(messages) >= limit:
                            break
            except ValueError:
                print(f"✗ Chat '{chat_name}' not found")
                return
        else:
            # Search across all dialogs
            print("✓ Searching across all chats...")
            dialogs = await client.get_dialogs()
            for dialog in dialogs:
                if len(messages) >= limit:
                    break
                    
                async for message in client.iter_messages(dialog.entity, limit=limit):
                    if message.text and keyword.lower() in message.text.lower():
                        messages.append(message)
                        if len(messages) >= limit:
                            break
        
        # Display results
        if messages:
            print(f"\n✓ Found {len(messages)} message(s)\n")
            for i, msg in enumerate(messages, 1):
                chat = await client.get_entity(msg.chat_id)
                print(f"--- Message {i} ---")
                print(f"Chat: {chat.title if hasattr(chat, 'title') else chat.first_name}")
                print(f"Date: {msg.date}")
                print(f"Sender: {msg.sender_id}")
                print(f"Message: {msg.text[:200]}...")
                print()
            
            # Save to CSV
            save_to_csv(messages, keyword)
        else:
            print(f"✗ No messages found containing '{keyword}'")
    
    except Exception as e:
        print(f"✗ Error: {e}")
    finally:
        await client.disconnect()

def save_to_csv(messages, keyword):
    """Save scraped messages to CSV file"""
    filename = f"telegram_scrape_{keyword}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Date', 'Sender ID', 'Chat ID', 'Message'])
        
        for msg in messages:
            writer.writerow([msg.date, msg.sender_id, msg.chat_id, msg.text])
    
    print(f"✓ Results saved to {filename}")

# Main execution
if __name__ == "__main__":
    keyword = input("Enter keyword to search: ").strip()
    chat = input("Enter chat name (leave blank to search all): ").strip() or None
    limit = int(input("Maximum messages to retrieve (default 100): ") or 100)
    
    if not keyword:
        print("✗ Keyword cannot be empty")
    else:
        asyncio.run(scrape_telegram(keyword, chat, limit))