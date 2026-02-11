import re

def analyze_review(text):
    """
    Анализирует отзыв и возвращает:
    1. Категорию (Screen, Battery, Performance, etc.)
    2. Тональность (Positive/Negative/Neutral)
    3. Краткое резюме (Summary)
    """
    if not text:
        return "OTHER", "Neutral", ""
    
    text_lower = text.lower()
    
    # === 1. ОПРЕДЕЛЕНИЕ ТОНАЛЬНОСТИ (ПРОСТОЕ) ===
    # (Для более сложного нужен DeepSeek/GPT, но это локальный вариант)
    positive_words = ['отличн', 'супер', 'класс', 'доволен', 'рекомендую', 'топ', 'летает', 'быстр', 'хорош']
    negative_words = ['ужас', 'плох', 'слома', 'глючит', 'тормоз', 'верните', 'брак', 'отстой', 'шум', 'греет']
    
    pos_score = sum(1 for w in positive_words if w in text_lower)
    neg_score = sum(1 for w in negative_words if w in text_lower)
    
    if neg_score > 0 and neg_score >= pos_score:
        sentiment = "Negative"
    elif pos_score > neg_score:
        sentiment = "Positive"
    else:
        sentiment = "Neutral"

    # === 2. УМНАЯ КАТЕГОРИЗАЦИЯ (ВЕСОВАЯ СИСТЕМА) ===
    categories = {
        "SCREEN": ['экран', 'дисплей', 'матриц', 'битые', 'пиксели', 'засвет', 'ярк', 'монитор', 'изображение', 'цветопередача'],
        "PERFORMANCE": ['производител', 'мощн', 'игр', 'фпс', 'fps', 'лаг', 'тормоз', 'быстр', 'шустр', 'зависа', 'тянет'],
        "BUILD_QUALITY": ['сборк', 'корпус', 'люфт', 'скрип', 'пластик', 'метал', 'петл', 'клавиатур', 'тачпад', 'крышка'],
        "BATTERY": ['батаре', 'заряд', 'аккум', 'автоном', 'держит', 'разряд'],
        "SOUND": ['звук', 'динамик', 'громк', 'тихий', 'аудио', 'колонк'],
        "NOISE_HEAT": ['шум', 'греет', 'вентилятор', 'кулер', 'горяч', 'температур', 'охлажден', 'тишин'],
        "SOFTWARE": ['винд', 'windows', 'драйвер', 'bios', 'биос', 'установ', 'система', 'ось', 'linux'],
        "DELIVERY": ['доставк', 'упаковк', 'коробк', 'пришел', 'пункт', 'пвз', 'задерж'],
        "PRICE": ['цен', 'рублей', 'стоим', 'деньг', 'бюджет']
    }
    
    scores = {cat: 0 for cat in categories}
    
    for cat, keywords in categories.items():
        for word in keywords:
            if word in text_lower:
                scores[cat] += 1
    
    # Находим категорию с максимальным весом
    best_cat = max(scores, key=scores.get)
    
    # Если совпадений нет вообще -> OTHER
    if scores[best_cat] == 0:
        category = "OTHER"
    else:
        category = best_cat

    # === 3. ГЕНЕРАЦИЯ САММАРИ (ЭВРИСТИКА) ===
    # Берем первое предложение или кусок до 50 символов
    summary = text[:60].replace('\n', ' ') + "..."
    
    return category, sentiment, summary