from .utils import extract_indian_invoice
from .models import Invoice
from django.shortcuts import render, redirect
from .utils import extract_indian_invoice, parse_date, parse_amount
from django.db.models import Sum
from django.db.models.functions import TruncDate
from datetime import datetime
import json
import psycopg2

def upload_image(request):
    print("Enter upload image")
    monthly_total = 0
    chart_labels = []
    chart_data = []
    if request.method == 'POST' and request.FILES.get('image'):
        img = request.FILES['image']

        invoice = Invoice.objects.create(
            image=img,
            invoice_no='',
            gst='',
            date=None,
            amount=0
        )
        extracted = extract_indian_invoice(invoice.image.path)
        date = parse_date(extracted.get('date')) if extracted.get('date') else None
        amount = parse_amount(extracted.get('amount') or "")
        invoice.date = date
        invoice.amount = amount
        invoice.save()
        request.session['extracted'] = extracted
        return redirect('upload')

    data = request.session.pop('extracted', {})
    # ---- Monthly total ----
    today = datetime.today()
    monthly_total = Invoice.objects.filter(
        date__month=today.month,
        date__year=today.year
    ).aggregate(total=Sum('amount'))['total'] or 0

    # ---- Chart data (daily spending) ----
    daily_data = (
        Invoice.objects
        .filter(date__month=today.month, date__year=today.year)
        .annotate(day=TruncDate('date'))
        .values('day')
        .annotate(total=Sum('amount'))
        .order_by('day')
    )
    chart_labels = [str(item['day']) for item in daily_data]
    chart_data = [float(item['total']) for item in daily_data]

    return render(request, 'upload.html', {
        'data': data,
        'monthly_total': monthly_total,
        'chart_labels': json.dumps(chart_labels),
        'chart_data': json.dumps(chart_data),
    })

def test_postgresql_connection():
    # Basic connection to PostgreSQL
    conn = psycopg2.connect(
        host="your_host",
        database="your_database",
        user="your_user",
        password="your_password"
    )
    # Create a cursor
    cur = conn.cursor()
    # Example query
    cur.execute("SELECT version()")
    # Fetch result
    version = cur.fetchone()
    print(version)
    # Close cursor and connection
    cur.close()
    conn.close()