from playwright.async_api import Page

async def apply_stealth(page: Page):
    """
    Маскирует Playwright под обычный браузер Chrome.
    Убирает флаг navigator.webdriver и подменяет некоторые свойства.
    """
    await page.add_init_script("""
        // 1. Убираем флаг webdriver
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });

        // 2. Подменяем языки (чтобы было похоже на русского пользователя)
        Object.defineProperty(navigator, 'languages', {
            get: () => ['ru-RU', 'ru', 'en-US', 'en']
        });

        // 3. Эмулируем window.chrome
        window.chrome = {
            runtime: {},
            loadTimes: function() {},
            csi: function() {},
            app: {}
        };

        // 4. Подменяем плагины (у ботов их обычно 0)
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });

        // 5. Маскируем разрешения
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
            Promise.resolve({ state: Notification.permission }) :
            originalQuery(parameters)
        );
    """)