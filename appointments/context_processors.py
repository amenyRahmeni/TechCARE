from .permissions import is_technician


def workspace(request):
    namespace = "backoffice" if getattr(request.resolver_match, "namespace", "") == "backoffice" else "appointments"
    navigation = {
        "workspace_base": "backoffice/base.html" if namespace == "backoffice" else "base.html",
        "in_backoffice": namespace == "backoffice",
        "workflow_urls": {name: f"{namespace}:{name}" for name in ("list", "create", "update", "detail", "cancel", "status_update", "intervention_update", "availability", "documents", "pdf")},
    }
    if not request.user.is_authenticated:
        return {"is_technician": False, **navigation}
    return {"is_technician": is_technician(request.user), **navigation}
