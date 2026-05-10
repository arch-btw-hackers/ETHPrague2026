import asyncio
import os
from web3 import AsyncWeb3
from dotenv import load_dotenv

# Подгружаем переменные из .env
load_dotenv()

async def main():
    rpc_url = os.environ.get("WEB3_RPC_URL")
    contract_addr = os.environ.get("CONTRACT_ADDRESS")
    
    if not rpc_url or not contract_addr:
        print("Ошибка: В .env не хватает WEB3_RPC_URL или CONTRACT_ADDRESS")
        return

    print(f"Пробуем подключиться к ноде: {rpc_url}")
    w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(rpc_url))
    
    # 1. Проверяем связь с нодой
    is_connected = await w3.is_connected()
    if not is_connected:
        print("ХРЕНОВО: Связи с блокчейном нет. Проверь RPC URL.")
        return
    print("ОК: Нода отвечает.")

    # 2. Проверяем, жив ли контракт
    print(f"Ищем контракт по адресу: {contract_addr}")
    checksum_addr = AsyncWeb3.to_checksum_address(contract_addr)
    
    # Достаем байткод по адресу. Если там пусто, вернет 0x
    code = await w3.eth.get_code(checksum_addr)
    
    if len(code) > 2:
        print(f"ОК: Контракт на месте! Размер байткода: {len(code)} байт.")
    else:
        print("ХРЕНОВО: По этому адресу пусто. Либо не та сеть, либо кривой адрес.")

if __name__ == "__main__":
    asyncio.run(main())