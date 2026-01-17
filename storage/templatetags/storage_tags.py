from django import template
from urllib.parse import quote
from storage.models import DownloadToken

register = template.Library()


@register.simple_tag(takes_context=True)
def file_view_url(context, file):
    """
    Генерирует URL для просмотра файла.
    Для S3 файлов использует presigned URL для прямого доступа (быстрее).
    Для локальных файлов использует raw_file эндпоинт.
    """
    request = context.get('request')
    
    # Для S3 файлов используем presigned URL для прямого доступа (быстрее)
    if file.storage and file.storage.storage_type == 's3':
        from storage.helpers import generate_s3_presigned_url
        s3_key = f"{file.user.id}/{file.filename}"
        presigned_url = generate_s3_presigned_url(file.storage, s3_key, expiration=3600)
        if presigned_url:
            return presigned_url
    
    # Для локальных файлов и файлов без хранилища используем raw_file эндпоинт
    download_token = DownloadToken.get_or_create_valid_token(file)
    encoded_filename = quote(file.filename, safe='')
    
    # Если request передан, возвращаем полный URL
    if request:
        return request.build_absolute_uri(f'/storage/raw/{encoded_filename}?token={download_token.token}')
    
    # Иначе возвращаем относительный URL
    return f'/storage/raw/{encoded_filename}?token={download_token.token}'
