import yt_dlp
import os
import logging
from django.conf import settings
from .models import UserFile, DownloadTask
from django.utils import timezone

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
            
            # Сначала скачиваем видео в низком качестве для аудио
            audio_opts = {
                'format': 'best[height<=360][ext=mp4]/best[height<=144][ext=mp4]',
                'quiet': True,
                'no_warnings': True,
                'outtmpl': os.path.join(user_folder, 'temp_audio.mp4'),
            }

            with yt_dlp.YoutubeDL(audio_opts) as ydl:
                ydl.download([self.task.url])
                temp_audio_path = os.path.join(user_folder, 'temp_audio.mp4')

            # Настройки для загрузки основного видео
            ydl_opts = settings.YOUTUBE_DOWNLOAD_SETTINGS.copy()
            ydl_opts.update({
                'format': self.task.format_id if self.task.format_id else 'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
                'outtmpl': os.path.join(user_folder, '%(title)s.%(ext)s'),
                'progress_hooks': [self.progress_callback],
                'nocheckcertificate': True,
                'no_warnings': True
            })
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Получаем информацию о видео
                info = ydl.extract_info(self.task.url, download=False)
                filename = ydl.prepare_filename(info)
                
                # Скачиваем видео
                ydl.download([self.task.url])
                
                # Извлекаем аудио из низкого качества
                import subprocess
                subprocess.run([
                    'ffmpeg', '-i', temp_audio_path,
                    '-vn', '-acodec', 'copy',
                    os.path.join(user_folder, 'temp_audio_only.aac')
                ])

                # Комбинируем видео с аудио
                final_path = os.path.join(user_folder, os.path.basename(filename))
                subprocess.run([
                    'ffmpeg', '-i', final_path,
                    '-i', os.path.join(user_folder, 'temp_audio_only.aac'),
                    '-c:v', 'copy', '-c:a', 'aac',
                    os.path.join(user_folder, 'final_' + os.path.basename(filename))
                ])

                # Удаляем временные файлы
                os.remove(temp_audio_path)
                os.remove(os.path.join(user_folder, 'temp_audio_only.aac'))
                os.remove(final_path)
                os.rename(
                    os.path.join(user_folder, 'final_' + os.path.basename(filename)),
                    final_path
                )
                
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