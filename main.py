from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse
import requests
from bs4 import BeautifulSoup

app = FastAPI()

# Сайт-донор, у которого мы забираем интерфейс
TARGET_URL = "https://viagogo.com" 

# HTML-код твоей визитки, которая выскочит вместо Stripe
STUDENT_CARD_HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Курсовой проект: Перехват платежного шлюза</title>
    <style>
        body {
            font-family: 'Arial', sans-serif;
            background: #0f172a;
            color: #f8fafc;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
        }
        .container {
            background: #1e293b;
            padding: 40px;
            border-radius: 16px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
            text-align: center;
            max-width: 450px;
            border: 2px solid #3b82f6;
        }
        .alert-badge {
            background: #ef4444;
            color: white;
            padding: 6px 16px;
            border-radius: 9999px;
            font-size: 12px;
            font-weight: bold;
            text-transform: uppercase;
            display: inline-block;
            margin-bottom: 20px;
        }
        h1 { margin: 0 0 15px 0; font-size: 26px; color: #3b82f6; }
        p { font-size: 16px; color: #94a3b8; line-height: 1.6; margin: 10px 0; }
        .student-info {
            background: #334155;
            padding: 15px;
            border-radius: 8px;
            margin: 20px 0;
            text-align: left;
        }
        .student-info div { margin-bottom: 8px; }
        .student-info div:last-child { margin-bottom: 0; }
        .btn {
            background: #2563eb;
            color: white;
            text-decoration: none;
            padding: 12px 24px;
            border-radius: 8px;
            font-weight: bold;
            display: inline-block;
            transition: 0.2s;
        }
        .btn:hover { background: #1d4ed8; }
    </style>
</head>
<body>
    <div class="container">
        <div class="alert-badge">Безопасный перехват</div>
        <h1>Компонент оплаты заблокирован</h1>
        <p>В целях безопасности демонстрационного стенда, переход на оригинальный шлюз оплаты (Stripe/PayPal) был успешно перехвачен бэкендом.</p>
        
        <div class="student-info">
            <div><strong>Выполнил студент:</strong> Твое Имя и Фамилия</div>
            <div><strong>Группа:</strong> Твоя Группа (например, ИСП-301)</div>
            <div><strong>Тема курсовой:</strong> Разработка динамического прокси-сервера</div>
        </div>
        
        <a href="/" class="btn">Вернуться на главную</a>
    </div>
</body>
</html>
"""

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(path: str, request: Request):
    
    # 🎯 ПРОВЕРКА НА ОПЛАТУ: если в адресе есть эти слова, выкидываем визитку
    # Сюда можно дописать любые слова, которые появятся в URL при покупке
    checkout_triggers = ["checkout", "payment", "secure", "buy", "transaction", "pay"]
    if any(trigger in path.lower() for trigger in checkout_triggers):
        return HTMLResponse(content=STUDENT_CARD_HTML, status_code=200)

    # Собираем полный URL к оригинальному сайту
    url = f"{TARGET_URL}/{path}"
    if request.query_params:
        url += f"?{request.query_params}"

    # Подменяем заголовки, чтобы Viagogo думал, что мы реальный браузер
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://google.com"
    }
    
    body = await request.body()

    # Запрос к оригиналу
    response = requests.request(
        method=request.method,
        url=url,
        headers=headers,
        data=body,
        cookies=request.cookies,
        allow_redirects=False 
    )

    # Обработка редиректов со стороны Viagogo
    if response.status_code in [301, 302, 303, 307, 308]:
        redirect_url = response.headers.get("Location", "")
        
        # Если редирект ведет на оплату — сразу включаем капкан
        if any(trig in redirect_url.lower() for trig in checkout_triggers):
            return HTMLResponse(content=STUDENT_CARD_HTML, status_code=200)
            
        modified_redirect = redirect_url.replace(TARGET_URL, "")
        res = Response(status_code=response.status_code)
        res.headers["Location"] = modified_redirect
        return res

    content_type = response.headers.get("Content-Type", "")

    # Если Viagogo вернул HTML-страницу — переписываем её код
    if "text/html" in content_type:
        soup = BeautifulSoup(response.content, "html.parser")
        
        # ✂️ УСЛОВИЕ №1: Удаляем категории из хедера
        # Ниже собраны популярные классы меню Viagogo, скрипт сотрет их из кода
        classes_to_remove = ['.nav-categories', '.header-categories', '#header-nav-categories', '.categories-menu']
        for cls in classes_to_remove:
            for element in soup.select(cls):
                element.decompose()

        html_str = str(soup)

        # 🔗 ПЕРЕПРОШИВКА ССЫЛОК: подменяем Viagogo на наш текущий адрес сервера
        my_domain = str(request.base_url).rstrip('/')
        
        html_str = html_str.replace("https://viagogo.com", my_domain)
        html_str = html_str.replace("https://viagogo.com", my_domain)
        html_str = html_str.replace("http://viagogo.com", my_domain)
        html_str = html_str.replace("http://viagogo.com", my_domain)
        html_str = html_str.replace("//://viagogo.com", my_domain.replace("http:", "").replace("https:", ""))
        html_str = html_str.replace("//viagogo.com", my_domain.replace("http:", "").replace("https:", ""))

        return HTMLResponse(content=html_str, status_code=response.status_code)

    # Картинки, шрифты, скрипты и стили отдаем без изменений
    return Response(content=response.content, status_code=response.status_code, media_type=content_type)

if __name__ == "__main__":
    import uvicorn
    # Запускаем локально на порту 8000
    uvicorn.run(app, host="127.0.0.1", port=8000)
