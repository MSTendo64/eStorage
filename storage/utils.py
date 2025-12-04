from django.conf import settings
import subprocess
import json
import os
import tempfile
import hashlib
from pathlib import Path

VIDEO_EXTENSIONS = {
    '.mp4', '.mov', '.m4v', '.avi', '.wmv', '.flv', '.webm',
    '.mkv', '.mpg', '.mpeg', '.3gp', '.ts', '.m2ts'
}

BASELINE_HEIGHT = 720
BASELINE_FPS = 24
BASELINE_BITRATE = 1_000_000

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


def get_available_qualities(height):
    """
    Возвращает список доступных качеств для видео на основе исходного разрешения.
    Если видео больше 144p, возвращает список качеств от исходного до 144p.
    """
    quality_map = {
        2160: [2160, 1440, 1080, 720, 480, 360, 240, 144],
        1440: [1440, 1080, 720, 480, 360, 240, 144],
        1080: [1080, 720, 480, 360, 240, 144],
        720: [720, 480, 360, 240, 144],
        480: [480, 360, 240, 144],
        360: [360, 240, 144],
        240: [240, 144],
        144: [144]
    }
    
    # Определяем ближайшее стандартное качество сверху
    for quality in sorted(quality_map.keys(), reverse=True):
        if height >= quality:
            return quality_map[quality]
    
    # Если видео меньше 144p, возвращаем только исходное
    return [height] if height else []


def transcode_video(input_path, output_path, target_height):
    """
    Перекодирует видео в указанное качество используя ffmpeg.
    
    Args:
        input_path: Путь к исходному видео файлу
        output_path: Путь для сохранения перекодированного видео
        target_height: Целевая высота в пикселях (например, 720 для 720p)
    
    Returns:
        True если успешно, False в противном случае
    """
    if not os.path.exists(input_path):
        return False
    
    try:
        # Проверяем доступность ffmpeg
        try:
            subprocess.run(['ffmpeg', '-version'], 
                         capture_output=True, 
                         timeout=5, 
                         check=True)
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            print("ffmpeg не найден или недоступен")
            return False
        
        # Получаем метаданные исходного видео для определения пропорций
        metadata = get_video_metadata(input_path)
        if not metadata or not metadata.get('width') or not metadata.get('height'):
            print("Не удалось получить метаданные исходного видео")
            return False
        
        original_width = metadata['width']
        original_height = metadata['height']
        
        # Вычисляем новую ширину с сохранением пропорций
        aspect_ratio = original_width / original_height
        new_width = int(target_height * aspect_ratio)
        
        # Убеждаемся, что ширина четная (требование для некоторых кодеков)
        if new_width % 2 != 0:
            new_width += 1
        
        # Создаем директорию для выходного файла, если её нет
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Команда ffmpeg для перекодирования
        cmd = [
            'ffmpeg',
            '-i', input_path,
            '-vf', f'scale={new_width}:{target_height}',
            '-c:v', 'libx264',
            '-preset', 'medium',
            '-crf', '23',
            '-c:a', 'aac',
            '-b:a', '128k',
            '-movflags', '+faststart',
            '-y',  # Перезаписать выходной файл, если существует
            output_path
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600  # Максимум 1 час на перекодирование
        )
        
        if result.returncode != 0:
            print(f"ffmpeg error: {result.stderr}")
            return False
        
        return os.path.exists(output_path)
        
    except subprocess.TimeoutExpired:
        print("Перекодирование видео превысило время ожидания")
        return False
    except Exception as e:
        print(f"Error transcoding video: {e}")
        return False


def get_video_quality_path(file_path, target_height):
    """
    Возвращает путь к видео в указанном качестве.
    Если видео уже перекодировано, возвращает путь к кешированному файлу.
    Иначе перекодирует и возвращает путь к новому файлу.
    
    Args:
        file_path: Путь к исходному видео файлу
        target_height: Целевая высота в пикселях
    
    Returns:
        Путь к видео в нужном качестве или None в случае ошибки
    """
    if not os.path.exists(file_path):
        return None
    
    # Создаем уникальное имя для кешированного файла на основе исходного файла и качества
    file_hash = hashlib.md5(f"{file_path}_{target_height}".encode()).hexdigest()
    cache_dir = os.path.join(settings.MEDIA_ROOT, 'video_cache')
    os.makedirs(cache_dir, exist_ok=True)
    
    # Определяем расширение исходного файла
    file_ext = os.path.splitext(file_path)[1]
    cached_path = os.path.join(cache_dir, f"{file_hash}{file_ext}")
    
    # Если файл уже существует, возвращаем его
    if os.path.exists(cached_path):
        return cached_path
    
    # Иначе перекодируем видео
    if transcode_video(file_path, cached_path, target_height):
        return cached_path
    
    return None 


def is_video_filename(filename: str) -> bool:
    """
    Проверяет, относится ли файл к видео по расширению.
    """
    if not filename:
        return False
    _, ext = os.path.splitext(filename)
    return ext.lower() in VIDEO_EXTENSIONS


def transcode_video_with_profile(input_path: str,
                                 output_path: str,
                                 target_height: int = None,
                                 target_fps: int = None,
                                 target_bitrate: int = None,
                                 crf: int = None) -> bool:
    """
    Перекодирует видео с кастомными параметрами.
    """
    if not os.path.exists(input_path):
        return False
    
    try:
        subprocess.run(
            ['ffmpeg', '-version'],
            capture_output=True,
            timeout=5,
            check=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        print("ffmpeg не найден или недоступен")
        return False
    
    filters = []
    if target_height:
        filters.append(f"scale=-2:{target_height}")
    if target_fps:
        filters.append(f"fps={target_fps}")
    
    cmd = ['ffmpeg', '-y', '-i', input_path]
    
    if filters:
        cmd += ['-vf', ','.join(filters)]
    
    cmd += ['-c:v', 'libx264', '-preset', 'medium']
    
    if target_bitrate:
        bitrate_k = max(int(target_bitrate / 1000), 300)
        buf_k = max(bitrate_k * 2, 600)
        cmd += ['-b:v', f'{bitrate_k}k', '-maxrate', f'{bitrate_k}k', '-bufsize', f'{buf_k}k']
    else:
        cmd += ['-crf', str(crf if crf is not None else 23)]
    
    cmd += ['-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', output_path]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600
        )
        if result.returncode != 0:
            print(f"ffmpeg error: {result.stderr}")
            return False
        return os.path.exists(output_path)
    except subprocess.TimeoutExpired:
        print("Перекодирование видео превысило время ожидания")
        return False
    except Exception as exc:
        print(f"Ошибка перекодирования видео: {exc}")
        return False


def apply_video_quality_profile(file_path: str, quality_option: str):
    """
    Применяет выбранный профиль качества к видео файлу.
    """
    if not quality_option or quality_option == 'original':
        return True, None
    
    metadata = get_video_metadata(file_path)
    if not metadata:
        return False, 'Не удалось получить параметры видео. Убедитесь, что ffprobe установлен.'
    
    height = metadata.get('height') or 0
    fps = metadata.get('fps') or 0
    bitrate = metadata.get('bitrate') or 0
    
    baseline_met = (
        height >= BASELINE_HEIGHT and
        fps >= BASELINE_FPS and
        bitrate >= BASELINE_BITRATE
    )
    
    target_height = None
    target_fps = None
    target_bitrate = None
    crf = None
    
    if quality_option == 'minimum':
        if baseline_met:
            target_height = min(height, BASELINE_HEIGHT)
            target_fps = BASELINE_FPS if fps > BASELINE_FPS else None
            target_bitrate = BASELINE_BITRATE
        else:
            target_bitrate = int(bitrate * 0.5) if bitrate else None
            crf = 28 if not target_bitrate else None
    elif quality_option == 'medium':
        target_bitrate = int(bitrate * 0.8) if bitrate else None
        if not target_bitrate:
            crf = 25
    else:
        return True, None
    
    if target_bitrate:
        target_bitrate = max(target_bitrate, 300_000)
    
    temp_output = f"{file_path}.quality.tmp"
    success = transcode_video_with_profile(
        input_path=file_path,
        output_path=temp_output,
        target_height=target_height,
        target_fps=target_fps,
        target_bitrate=target_bitrate,
        crf=crf
    )
    
    if not success:
        if os.path.exists(temp_output):
            os.remove(temp_output)
        return False, 'Не удалось обработать выбранное качество. Убедитесь, что ffmpeg установлен.'
    
    try:
        os.replace(temp_output, file_path)
    except Exception as exc:
        if os.path.exists(temp_output):
            os.remove(temp_output)
        return False, f'Ошибка при сохранении перекодированного видео: {exc}'
    
    return True, None