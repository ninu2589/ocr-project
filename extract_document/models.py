from django.db import models

# Create your models here.
# extract_document/models.py

class Invoice(models.Model):
    image = models.ImageField(upload_to='images/')
    invoice_no = models.CharField(max_length=100, null=True, blank=True)
    gst = models.CharField(max_length=50, null=True, blank=True)
    date = models.DateField(null=True, blank=True)
    amount = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

