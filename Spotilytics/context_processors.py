def assets_root(request):
    from django.conf import settings

    return {"ASSETS_ROOT": settings.ASSETS_ROOT}
