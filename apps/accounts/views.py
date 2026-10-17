from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required(login_url="/auth/telegram/login/")
def home(request):
    return render(request, "accounts/home.html", {"user": request.user})
