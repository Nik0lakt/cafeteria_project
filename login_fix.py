@router.post("/login")
async def login(data: LoginRequest):
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    # Берем пароль из .env, если его нет - admin123
    target_pass = os.getenv("ADMIN_PASSWORD", "admin123")
    
    # Печатаем в логи для тебя (потом удалим)
    print(f"--- LOGIN ATTEMPT ---")
    print(f"Received: {data.password}")
    print(f"Expected: {target_pass}")
    
    if data.password == target_pass:
        return {"success": True}
    return {"success": False}
