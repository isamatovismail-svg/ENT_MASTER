from django.shortcuts import render

def pricing_view(request):
    """
    Subscription Plans & Pricing View.
    Clearly marks platform as completely free during initial launch.
    """
    return render(request, 'payments/pricing.html')
