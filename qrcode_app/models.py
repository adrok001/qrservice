from django.db import models


class QRCode(models.Model):
    data = models.TextField(verbose_name='Data')
    image = models.ImageField(upload_to='qrcodes/', verbose_name='QR Code Image')
    logo = models.ImageField(upload_to='logos/', verbose_name='Logo', blank=True, null=True)
    fill_color = models.CharField(max_length=20, default='black', verbose_name='Fill Color')
    back_color = models.CharField(max_length=20, default='white', verbose_name='Background Color')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'QR Code'
        verbose_name_plural = 'QR Codes'

    def __str__(self):
        return f"QR: {self.data[:50]}"
