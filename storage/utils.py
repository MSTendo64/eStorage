import yt_dlp
from django.conf import settings

def download_youtube_video(url, output_path):
    """
    Скачивает видео с YouTube с учетом требований к качеству
    """
    ydl_opts = settings.YOUTUBE_DOWNLOAD_SETTINGS.copy()
    ydl_opts.update({
        'outtmpl': output_path,
        'format_sort': [
            'res:1080',
            'fps>30',
            'codec:h264',
            'size',
            'br',
            'asr'
        ],
        'postprocessor_args': [
            '-preset', 'medium',  # Баланс между качеством и скоростью
            '-crf', '23',  # Хорошее качество (меньше = лучше, диапазон 0-51)
            '-movflags', '+faststart',  # Для быстрого старта воспроизведения
            '-vsync', '1',  # Для стабильного FPS
        ]
    })

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get('formats', [])
            
            # Фильтруем форматы по нашим требованиям
            suitable_formats = [
                f for f in formats
                if f.get('fps', 0) >= settings.VIDEO_QUALITY_REQUIREMENTS['min_fps']
                and f.get('height', 0) >= 720  # минимум 720p
                and 'acodec' in f  # проверяем наличие аудио
                and f.get('vcodec', '').startswith('avc')  # h264 кодек
            ]
            
            if suitable_formats:
                # Выбираем лучший формат
                best_format = max(suitable_formats, 
                                key=lambda x: (x.get('fps', 0), x.get('height', 0)))
                ydl_opts['format'] = best_format['format_id']
            
            # Скачиваем видео
            ydl.download([url])
            
            return True
    except Exception as e:
        print(f"Error downloading video: {e}")
        return False 