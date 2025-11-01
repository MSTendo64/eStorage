import yt_dlp
from django.conf import settings
import subprocess
import json
import os

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

def get_video_metadata(file_path):
    """
    Получает метаданные видео файла, включая FPS, разрешение, битрейт и т.д.
    Использует ffprobe для анализа видео файла.
    """
    if not os.path.exists(file_path):
        return None
    
    try:
        # Проверяем доступность ffprobe
        try:
            subprocess.run(['ffprobe', '-version'], 
                         capture_output=True, 
                         timeout=5, 
                         check=True)
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            print("ffprobe не найден или недоступен")
            return None
        
        # Используем ffprobe для получения метаданных в формате JSON
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            file_path
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            # Логируем ошибку для отладки
            error_msg = result.stderr if result.stderr else "Unknown error"
            print(f"ffprobe error (returncode {result.returncode}): {error_msg}")
            return None
        
        if not result.stdout:
            print("ffprobe returned empty output")
            return None
        
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            print(f"Error parsing ffprobe JSON: {e}")
            return None
        
        # Находим видео поток
        video_stream = None
        for stream in data.get('streams', []):
            if stream.get('codec_type') == 'video':
                video_stream = stream
                break
        
        if not video_stream:
            return None
        
        # Извлекаем информацию
        width = video_stream.get('width')
        height = video_stream.get('height')
        
        # Определяем качество видео в формате (например, 1080p, 720p)
        quality = None
        if height:
            # Стандартные разрешения для качества
            if height >= 2160:
                quality = '4K (2160p)'
            elif height >= 1440:
                quality = '1440p'
            elif height >= 1080:
                quality = '1080p (Full HD)'
            elif height >= 720:
                quality = '720p (HD)'
            elif height >= 480:
                quality = '480p (SD)'
            elif height >= 360:
                quality = '360p'
            elif height >= 240:
                quality = '240p'
            else:
                quality = f'{height}p'
        
        metadata = {
            'fps': None,
            'width': width,
            'height': height,
            'quality': quality,
            'duration': None,
            'bitrate': None,
            'codec': video_stream.get('codec_name'),
            'codec_long': video_stream.get('codec_long_name'),
        }
        
        # Получаем FPS
        # FPS может быть указан как r_frame_rate (например, "30/1" или "29970/1000")
        r_frame_rate = video_stream.get('r_frame_rate')
        if r_frame_rate:
            try:
                parts = r_frame_rate.split('/')
                if len(parts) == 2:
                    num = float(parts[0])
                    den = float(parts[1])
                    if den != 0:
                        metadata['fps'] = round(num / den, 2)
            except:
                pass
        
        # Альтернативный способ получения FPS через avg_frame_rate
        if not metadata['fps']:
            avg_frame_rate = video_stream.get('avg_frame_rate')
            if avg_frame_rate:
                try:
                    parts = avg_frame_rate.split('/')
                    if len(parts) == 2:
                        num = float(parts[0])
                        den = float(parts[1])
                        if den != 0:
                            metadata['fps'] = round(num / den, 2)
                except:
                    pass
        
        # Длительность
        duration = video_stream.get('duration') or data.get('format', {}).get('duration')
        if duration:
            try:
                metadata['duration'] = float(duration)
            except:
                pass
        
        # Битрейт
        bitrate = video_stream.get('bit_rate') or data.get('format', {}).get('bit_rate')
        if bitrate:
            try:
                metadata['bitrate'] = int(bitrate)
            except:
                pass
        
        return metadata
        
    except subprocess.TimeoutExpired:
        return None
    except json.JSONDecodeError:
        return None
    except Exception as e:
        print(f"Error getting video metadata: {e}")
        return None 