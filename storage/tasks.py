import yt_dlp
import os
import logging
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
                
    def replace_audio(self, video_path, audio_path, output_path):
        try:
            # Заменяем аудио дорожку с помощью ffmpeg
            cmd = [
                'ffmpeg', '-y',
                '-i', video_path,  # Видео файл
                '-i', audio_path,  # Аудио файл
                '-c:v', 'copy',    # Копируем видео без перекодирования
                '-c:a', 'aac',     # Кодируем аудио в AAC
                '-map', '0:v:0',   # Берем видео из первого файла
                '-map', '1:a:0',   # Берем аудио из второго файла
                output_path
            ]
            subprocess.run(cmd, check=True)
            return True
        except Exception as e:
            logger.error(f"Error replacing audio: {str(e)}")
            return False
                
    def download(self):
        try:
            self.task.status = 'processing'
            self.task.save(update_fields=['status'])
            
            # Создаем папку пользователя
            user_folder = os.path.join(settings.MEDIA_ROOT, str(self.task.user.id))
            os.makedirs(user_folder, exist_ok=True)
            
            # Скачиваем видео в лучшем качестве
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
                
                # Сохраняем заголовок
                self.task.title = info.get('title', '')
                self.task.save(update_fields=['title'])
                
                # Скачиваем видео
                ydl.download([self.task.url])
                
                # Скачиваем аудио из низкого качества
                audio_opts = ydl_opts.copy()
                audio_opts.update({
                    'format': 'worstaudio/worst',
                    'outtmpl': os.path.join(user_folder, 'temp_audio.%(ext)s')
                })
                
                with yt_dlp.YoutubeDL(audio_opts) as audio_ydl:
                    audio_ydl.download([self.task.url])
                
                # Заменяем аудио дорожку
                video_path = filename
                audio_path = os.path.join(user_folder, 'temp_audio.webm')  # или другое расширение
                output_path = os.path.join(user_folder, f'final_{os.path.basename(filename)}')
                
                if self.replace_audio(video_path, audio_path, output_path):
                    # Удаляем временные файлы
                    os.remove(video_path)
                    os.remove(audio_path)
                    os.rename(output_path, video_path)
                
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
                
                if self.task.progress >= 100:
                    self.task.status = 'saving'
                    self.task.save(update_fields=['status'])
                
                self.task.status = 'completed'
                self.task.completed_at = timezone.now()
                self.task.save()
                
        except Exception as e:
            logger.error(f"Download error: {str(e)}")
            self.task.status = 'failed'
            self.task.error = str(e)
            self.task.save()
            raise