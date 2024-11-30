import yt_dlp
import os
import logging
import ssl
import certifi
from django.conf import settings
from .models import UserFile, DownloadTask
from django.utils import timezone
import subprocess

logger = logging.getLogger(__name__)

class VideoDownloader:
    def __init__(self, task_id):
        self.task_id = task_id
        self.task = DownloadTask.objects.get(id=task_id)
        
    def progress_callback(self, d):
        if d['status'] == 'downloading':
            try:
                total_bytes = d.get('total_bytes')
                downloaded_bytes = d.get('downloaded_bytes', 0)
                if total_bytes:
                    percentage = (downloaded_bytes / total_bytes) * 100
                    speed = d.get('speed', 0)
                    speed_mb = speed / 1024 / 1024 if speed else 0
                    
                    self.task.progress = percentage
                    self.task.speed = speed_mb
                    self.task.save(update_fields=['progress', 'speed', 'updated_at'])
            except Exception as e:
                logger.error(f"Progress callback error: {str(e)}")
                
    def download(self):
        try:
            self.task.status = 'processing'
            self.task.save(update_fields=['status'])
            
            # Создаем папку пользователя
            user_folder = os.path.join(settings.MEDIA_ROOT, str(self.task.user.id))
            os.makedirs(user_folder, exist_ok=True)

            # Общие настройки для всех загрузок
            common_opts = {
                'quiet': True,
                'no_warnings': True,
                'nocheckcertificate': True,
                'socket_timeout': 30,
                'retries': 10,
                'fragment_retries': 10,
                'http_chunk_size': 10485760,  # 10MB
                'ssl_verify': False,
                'legacy_server_connect': True
            }
            
            # Настройки для аудио
            audio_opts = common_opts.copy()
            audio_opts.update({
                'format': 'worstvideo[ext=mp4]+bestaudio[ext=m4a]/worst[ext=mp4]',
                'outtmpl': os.path.join(user_folder, 'temp_audio.%(ext)s'),
            })

            # Скачиваем аудио
            with yt_dlp.YoutubeDL(audio_opts) as ydl:
                try:
                    ydl.download([self.task.url])
                except Exception as e:
                    logger.error(f"Audio download error: {str(e)}")
                    raise

            # Настройки для видео
            video_opts = common_opts.copy()
            video_opts.update({
                'format': self.task.format_id if self.task.format_id else 'bestvideo[height<=1080][ext=mp4]',
                'outtmpl': os.path.join(user_folder, '%(title)s.%(ext)s'),
                'progress_hooks': [self.progress_callback],
            })
            
            with yt_dlp.YoutubeDL(video_opts) as ydl:
                # Получаем информацию о видео
                info = ydl.extract_info(self.task.url, download=False)
                filename = ydl.prepare_filename(info)
                
                # Скачиваем видео
                ydl.download([self.task.url])

                try:
                    # Объединяем видео и аудио с помощью ffmpeg
                    temp_audio = os.path.join(user_folder, 'temp_audio.mp4')
                    final_video = os.path.join(user_folder, os.path.basename(filename))
                    output_file = os.path.join(user_folder, 'final_' + os.path.basename(filename))

                    subprocess.run([
                        'ffmpeg',
                        '-i', final_video,  # видео
                        '-i', temp_audio,   # аудио
                        '-c:v', 'copy',     # копируем видео без перекодирования
                        '-c:a', 'aac',      # кодируем аудио в AAC
                        '-strict', 'experimental',
                        '-map', '0:v:0',    # берем видео из первого файла
                        '-map', '1:a:0',    # берем аудио из второго файла
                        '-y',               # перезаписываем файл если существует
                        output_file
                    ], check=True)

                    # Удаляем временные файлы
                    os.remove(temp_audio)
                    os.remove(final_video)
                    os.rename(output_file, final_video)

                except subprocess.CalledProcessError as e:
                    logger.error(f"FFmpeg error: {str(e)}")
                    raise
                except Exception as e:
                    logger.error(f"File processing error: {str(e)}")
                    raise

                # Создаем запись файла
                UserFile.objects.create(
                    user=self.task.user,
                    file=f'{self.task.user.id}/{os.path.basename(filename)}',
                    filename=os.path.basename(filename),
                    file_type='video',
                    title=info.get('title', ''),
                    description=info.get('description', ''),
                    duration=info.get('duration', 0),
                    thumbnail_url=info.get('thumbnail', '')
                )
                
                self.task.status = 'completed'
                self.task.completed_at = timezone.now()
                self.task.save()
                
        except Exception as e:
            logger.error(f"Download error: {str(e)}")
            self.task.status = 'failed'
            self.task.error = str(e)
            self.task.save()
            raise