import os
import re
import logging
import asyncio
import tempfile
import shutil
from datetime import datetime

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import FSInputFile
import yt_dlp

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = "7865242401:AAFi1WUf5QwzBVsj8Uc2eswtoDKSZb3qUiU"  # Токен от @BotFather
ALLOWED_USER_ID = 984155832  # Ваш Telegram ID

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== ИНИЦИАЛИЗАЦИЯ ====================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ==================== ПАТТЕРНЫ ДЛЯ ПЛАТФОРМ ====================
PLATFORM_PATTERNS = {
    'tiktok': re.compile(r'(https?://)?(www\.)?(tiktok\.com|vm\.tiktok\.com)'),
    'instagram': re.compile(r'(https?://)?(www\.)?(instagram\.com|instagr\.am)'),
    'pinterest': re.compile(r'(https?://)?(www\.)?(pinterest\.|pin\.it)')
}

# ==================== ФУНКЦИИ ЗАГРУЗКИ ====================
def detect_platform(url):
    """Определение платформы по URL"""
    for platform, pattern in PLATFORM_PATTERNS.items():
        if pattern.search(url):
            return platform
    return None

def download_content(url, temp_dir):
    """Универсальная функция загрузки контента"""
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'max_filesize': 50 * 1024 * 1024,  # 50 MB лимит
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Получаем информацию
            info = ydl.extract_info(url, download=False)
            
            # Проверяем размер файла
            filesize = info.get('filesize') or info.get('filesize_approx', 0)
            if filesize > 50 * 1024 * 1024:
                return {
                    'success': False,
                    'error': f'Файл слишком большой: {filesize / 1024 / 1024:.1f} MB (макс. 50 MB)'
                }
            
            # Скачиваем
            ydl.download([url])
            
            # Получаем информацию о контенте
            title = info.get('title', 'Media')
            uploader = info.get('uploader', 'Unknown')
            duration = info.get('duration', 0)
            
            # Находим скачанный файл
            files = []
            for filename in os.listdir(temp_dir):
                if filename != '.gitkeep':
                    files.append(os.path.join(temp_dir, filename))
            
            if not files:
                return {'success': False, 'error': 'Файл не найден после загрузки'}
            
            # Определяем тип контента
            file_path = files[0]
            is_video = file_path.endswith(('.mp4', '.webm', '.mov', '.avi'))
            
            return {
                'success': True,
                'file_path': file_path,
                'title': title,
                'uploader': uploader,
                'duration': duration,
                'is_video': is_video,
                'multiple_files': len(files) > 1,
                'all_files': files
            }
            
    except Exception as e:
        error_msg = str(e)
        if 'Private video' in error_msg:
            return {'success': False, 'error': 'Это приватное видео'}
        elif 'Video unavailable' in error_msg:
            return {'success': False, 'error': 'Видео недоступно'}
        else:
            return {'success': False, 'error': f'Ошибка загрузки: {error_msg}'}

# ==================== ОБРАБОТЧИКИ КОМАНД ====================
@dp.message(CommandStart())
async def start_command(message: types.Message):
    """Обработчик команды /start"""
    if message.from_user.id != ALLOWED_USER_ID:
        await message.answer("❌ Доступ запрещен. Этот бот только для личного использования.")
        return
    
    await message.answer(
        "👋 Привет! Я помогу скачать контент из:\n\n"
        "• TikTok\n"
        "• Instagram (Reels, Posts, IGTV)\n"
        "• Pinterest\n\n"
        "Просто отправь мне ссылку!"
    )

@dp.message(F.text.regexp(r'https?://'))
async def handle_url(message: types.Message):
    """Обработчик ссылок"""
    if message.from_user.id != ALLOWED_USER_ID:
        await message.answer("❌ Доступ запрещен.")
        return
    
    url = message.text.strip()
    platform = detect_platform(url)
    
    if not platform:
        await message.answer(
            "❌ Неподдерживаемая ссылка!\n"
            "Поддерживаются: TikTok, Instagram, Pinterest"
        )
        return
    
    # Отправляем сообщение о начале загрузки
    status_msg = await message.answer(
        f"⏳ Загружаю с {platform.capitalize()}...\n"
        "Это может занять несколько секунд."
    )
    
    # Создаем временную директорию
    temp_dir = tempfile.mkdtemp()
    
    try:
        # Загружаем контент
        result = download_content(url, temp_dir)
        
        if result['success']:
            # Формируем описание
            caption = f"✅ {result['title']}\n"
            if result['uploader'] != 'Unknown':
                caption += f"👤 {result['uploader']}\n"
            if result['duration'] > 0:
                minutes = result['duration'] // 60
                seconds = result['duration'] % 60
                caption += f"⏱ {minutes}:{seconds:02d}"
            
            # Отправляем файл(ы)
            if result['multiple_files']:
                # Несколько файлов (обычно для Instagram каруселей)
                media_group = []
                for i, file_path in enumerate(result['all_files'][:10]):  # Максимум 10
                    if file_path.endswith(('.mp4', '.webm', '.mov')):
                        media_group.append(types.InputMediaVideo(
                            media=FSInputFile(file_path),
                            caption=caption if i == 0 else None
                        ))
                    else:
                        media_group.append(types.InputMediaPhoto(
                            media=FSInputFile(file_path),
                            caption=caption if i == 0 else None
                        ))
                
                await message.answer_media_group(media_group)
            else:
                # Один файл
                if result['is_video']:
                    await message.answer_video(
                        video=FSInputFile(result['file_path']),
                        caption=caption
                    )
                else:
                    await message.answer_photo(
                        photo=FSInputFile(result['file_path']),
                        caption=caption
                    )
            
            # Удаляем статусное сообщение
            await status_msg.delete()
            
        else:
            # Ошибка загрузки
            await status_msg.edit_text(
                f"❌ Не удалось загрузить!\n"
                f"Причина: {result['error']}"
            )
    
    except Exception as e:
        logger.error(f"Error processing {url}: {e}")
        await status_msg.edit_text(
            "❌ Произошла ошибка при обработке.\n"
            "Попробуйте другую ссылку."
        )
    
    finally:
        # ВАЖНО: Удаляем временную директорию и все файлы
        try:
            shutil.rmtree(temp_dir)
            logger.info(f"Cleaned up temp directory: {temp_dir}")
        except Exception as e:
            logger.error(f"Error cleaning up {temp_dir}: {e}")

@dp.message()
async def handle_other_messages(message: types.Message):
    """Обработчик всех остальных сообщений"""
    if message.from_user.id != ALLOWED_USER_ID:
        return
    
    await message.answer(
        "📎 Отправьте ссылку на контент из:\n"
        "• TikTok\n"
        "• Instagram\n"
        "• Pinterest"
    )

# ==================== ЗАПУСК БОТА ====================
async def main():
    """Основная функция запуска"""
    logger.info(f"Starting bot for user ID: {ALLOWED_USER_ID}")
    
    # Удаляем вебхук (для pythonanywhere)
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Запускаем polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())