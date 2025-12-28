"""
Views для QR Service.

Тонкие views — вся логика в services/qr_generator.py
"""
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.core.files.base import ContentFile

from .models import QRCode
from .services import QRGeneratorService


def index(request):
    """Главная страница со списком последних QR-кодов."""
    qr_codes = QRCode.objects.all()[:10]
    return render(request, 'qrcode_app/index.html', {'qr_codes': qr_codes})


def generate_qr(request):
    """Генерация QR-кода с сохранением в БД."""
    if request.method == 'POST':
        data = request.POST.get('data', '')
        fill_color = request.POST.get('fill_color', '#000000')
        back_color = request.POST.get('back_color', '#ffffff')
        logo_file = request.FILES.get('logo')

        if data:
            buffer = QRGeneratorService.generate_to_buffer(
                data,
                fill_color=fill_color,
                back_color=back_color,
                logo_file=logo_file
            )

            qr_code = QRCode(
                data=data,
                fill_color=QRGeneratorService.validate_color(fill_color, 'black'),
                back_color=QRGeneratorService.validate_color(back_color, 'white')
            )
            qr_code.image.save(f'qr_{qr_code.id or "new"}.png', ContentFile(buffer.getvalue()))

            if logo_file:
                logo_file.seek(0)
                qr_code.logo.save(f'logo_{qr_code.id or "new"}.png', ContentFile(logo_file.read()))

            qr_code.save()
            return redirect('qrcode_detail', pk=qr_code.pk)

    return render(request, 'qrcode_app/generate.html')


def qrcode_detail(request, pk):
    """Детальная страница QR-кода."""
    qr_code = QRCode.objects.get(pk=pk)
    return render(request, 'qrcode_app/detail.html', {'qr_code': qr_code})


def generate_inline(request):
    """Быстрая генерация QR-кода без сохранения в БД."""
    context = {
        'qr_image': None,
        'data': '',
        'fill_color': '#000000',
        'back_color': '#ffffff',
    }

    if request.method == 'POST':
        data = request.POST.get('data', '')
        fill_color = request.POST.get('fill_color', '#000000')
        back_color = request.POST.get('back_color', '#ffffff')
        logo_file = request.FILES.get('logo')

        if data:
            qr_image = QRGeneratorService.generate_to_base64(
                data,
                fill_color=fill_color,
                back_color=back_color,
                logo_file=logo_file
            )
            context.update({
                'qr_image': qr_image,
                'data': data,
                'fill_color': fill_color,
                'back_color': back_color,
            })

    return render(request, 'qrcode_app/generate_inline.html', context)


def download_qr(request):
    """Скачивание QR-кода как PNG файл."""
    data = request.GET.get('data', '')
    if not data:
        return HttpResponse('Данные не указаны', status=400)

    fill_color = request.GET.get('fill_color', 'black')
    back_color = request.GET.get('back_color', 'white')

    buffer = QRGeneratorService.generate_to_buffer(
        data,
        fill_color=fill_color,
        back_color=back_color
    )

    response = HttpResponse(buffer.getvalue(), content_type='image/png')
    response['Content-Disposition'] = 'attachment; filename="qrcode.png"'
    return response
