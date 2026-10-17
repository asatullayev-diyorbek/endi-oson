from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required(login_url="/auth/telegram/login/")
def device_list_page(request):
    return render(request, "devices/list.html")
